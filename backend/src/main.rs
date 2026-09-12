mod config;
mod db;
mod error;
mod grid;
mod handlers;
mod models;
mod recommend;
mod state;

use axum::{routing::get, Router};
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

use crate::config::Config;
use crate::state::AppState;

fn app(state: AppState) -> Router {
	Router::new()
		.route("/health", get(handlers::health))
		.route("/books/{id}", get(handlers::get_book))
		.route("/recommend", axum::routing::post(handlers::recommend_books))
		.route("/map/books", get(handlers::map_books))
		.route("/map/authors", get(handlers::map_authors))
		.route("/map/points", get(handlers::map_points))
		.route("/map/counts", get(handlers::map_counts))
		.route("/authors/{name}", get(handlers::get_author))
		.route("/recommend-authors", axum::routing::post(handlers::recommend_authors))
		.layer(CorsLayer::permissive())
		.layer(TraceLayer::new_for_http())
		.with_state(state)
}

#[tokio::main]
async fn main() {
	tracing_subscriber::fmt()
		.with_env_filter(
			tracing_subscriber::EnvFilter::try_from_default_env()
				.unwrap_or_else(|_| "info".into()),
		)
		.init();

	let config = Config::from_env();
	let pool = db::connect(&config.database_url)
		.await
		.expect("failed to connect to database");

	let state = AppState::new(pool);

	let listener = tokio::net::TcpListener::bind(config.bind_addr)
		.await
		.expect("failed to bind listener");

	tracing::info!("listening on {}", config.bind_addr);

	axum::serve(listener, app(state))
		.with_graceful_shutdown(shutdown_signal())
		.await
		.expect("server error");
}

async fn shutdown_signal() {
	let _ = tokio::signal::ctrl_c().await;
	tracing::info!("shutdown signal received");
}

#[cfg(test)]
mod tests {
	use super::*;
	use axum::body::Body;
	use axum::http::{Request, StatusCode};
	use http_body_util::BodyExt;
	use tower::ServiceExt;

	async fn test_pool() -> Option<sqlx::PgPool> {
		// bootstrap env so DATABASE_URL is available for `cargo test`.
		crate::config::load_dotenv();
		let url = std::env::var("DATABASE_URL").ok()?;
		let pool = db::connect(&url).await.ok()?;
		Some(pool)
	}

	async fn app_for_test() -> Option<Router> {
		let pool = test_pool().await?;
		Some(app(AppState::new(pool)))
	}

	async fn body_string(body: Body) -> String {
		let bytes = body.collect().await.unwrap().to_bytes();
		String::from_utf8(bytes.to_vec()).unwrap()
	}

	#[tokio::test]
	async fn health_returns_ok() {
		let Some(app) = app_for_test().await else { return };

		let res = app
			.oneshot(Request::builder().uri("/health").body(Body::empty()).unwrap())
			.await
			.unwrap();

		assert_eq!(res.status(), StatusCode::OK);
		assert!(body_string(res.into_body()).await.contains("\"ok\""));
	}

	#[tokio::test]
	async fn recommend_empty_ids_bad_request() {
		let Some(app) = app_for_test().await else { return };

		let res = app
			.oneshot(
				Request::builder()
					.method("POST")
					.uri("/recommend")
					.header("content-type", "application/json")
					.body(Body::from(r#"{"work_ids":[]}"#))
					.unwrap(),
			)
			.await
			.unwrap();

		assert_eq!(res.status(), StatusCode::BAD_REQUEST);
	}

	#[tokio::test]
	async fn book_lookup_and_recommend_roundtrip() {
		let Some(app) = app_for_test().await else { return };

		// pick any seeded work from the DB so the test is data-independent
		let Some(pool) = test_pool().await else { return };
		let (id,): (String,) =
			sqlx::query_as("SELECT id FROM works LIMIT 1").fetch_one(&pool).await.unwrap();
		let encoded = id.replace('/', "%2F");

		// book lookup
		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.uri(format!("/books/{encoded}"))
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		assert!(body.contains("\"title\""));

		// recommend
		let req_body = format!(r#"{{"work_ids":["{}"],"limit":5}}"#, id.replace('"', ""));
		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.method("POST")
					.uri("/recommend")
					.header("content-type", "application/json")
					.body(Body::from(req_body))
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		assert!(body.contains("\"recommendations\""));

		// unknown book -> 404
		let res = app
			.oneshot(
				Request::builder()
					.uri("/books/does-not-exist")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::NOT_FOUND);
	}

	#[tokio::test]
	async fn map_and_author_endpoints_roundtrip() {
		let Some(app) = app_for_test().await else { return };
		let Some(pool) = test_pool().await else { return };

		// /map/books returns { nodes, total } with id + label + coordinates
		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.uri("/map/books")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		assert!(
			res.headers().get("x-total-count").is_some(),
			"X-Total-Count header present"
		);
		let body = body_string(res.into_body()).await;
		assert!(body.contains("\"nodes\""));
		assert!(body.contains("\"label\""));
		assert!(body.contains("\"x\""));

		// /map/authors returns { nodes, total } with name + coordinates
		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.uri("/map/authors")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		assert!(
			res.headers().get("x-total-count").is_some(),
			"X-Total-Count header present"
		);
		let body = body_string(res.into_body()).await;
		assert!(body.contains("\"nodes\""));
		assert!(body.contains("\"name\""));
		assert!(body.contains("\"work_count\""));

		// pick a real author name and exercise /authors/{name} + /recommend-authors
		let (name,): (String,) =
			sqlx::query_as("SELECT name FROM authors LIMIT 1").fetch_one(&pool).await.unwrap();
		let encoded = name.replace('/', "%2F").replace(' ', "%20");

		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.uri(format!("/authors/{encoded}"))
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		assert!(body.contains("\"works\""));

		// recommend-authors
		let req_body = format!(
			r#"{{"author_names":[{}],"limit":5}}"#,
			serde_json::to_string(&name).unwrap()
		);
		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.method("POST")
					.uri("/recommend-authors")
					.header("content-type", "application/json")
					.body(Body::from(req_body))
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		assert!(body.contains("\"recommendations\""));

		// unknown author -> 404
		let res = app
			.oneshot(
				Request::builder()
					.uri("/authors/does-not-exist")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::NOT_FOUND);
	}

	#[tokio::test]
	async fn map_books_ordered_and_limited() {
		let Some(app) = app_for_test().await else { return };

		// ordering: nodes must be sorted by entity_id ascending
		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.uri("/map/books")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		let json: serde_json::Value = serde_json::from_str(&body).unwrap();
		let nodes = json["nodes"].as_array().unwrap();
		let total = json["total"].as_i64().unwrap();
		assert_eq!(nodes.len() as i64, total.min(5000), "returns up to 5000 nodes");
		let ids: Vec<&str> = nodes.iter().map(|n| n["id"].as_str().unwrap()).collect();
		let mut sorted = ids.clone();
		sorted.sort();
		assert_eq!(ids, sorted, "/map/books nodes must be ordered by entity_id");

		// ?limit bounds the number of returned nodes
		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.uri("/map/books?limit=3")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		let json: serde_json::Value = serde_json::from_str(&body).unwrap();
		assert_eq!(json["nodes"].as_array().unwrap().len(), 3.min(total as usize));

		// an oversized limit is clamped to the hard max
		let res = app
			.clone()
			.oneshot(
				Request::builder()
					.uri("/map/books?limit=100000")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		let json: serde_json::Value = serde_json::from_str(&body).unwrap();
		assert_eq!(json["nodes"].as_array().unwrap().len(), 5000.min(total as usize));
	}

	#[tokio::test]
	async fn map_counts_matches_map_coords() {
		let Some(app) = app_for_test().await else { return };
		let Some(pool) = test_pool().await else { return };

		let res = app
			.oneshot(
				Request::builder()
					.uri("/map/counts")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		let counts: serde_json::Value = serde_json::from_str(&body).unwrap();

		let (books,): (i64,) = sqlx::query_as("SELECT count(*) FROM map_coords WHERE entity = 'book'")
			.fetch_one(&pool)
			.await
			.unwrap();
		let (authors,): (i64,) =
			sqlx::query_as("SELECT count(*) FROM map_coords WHERE entity = 'author'")
				.fetch_one(&pool)
				.await
				.unwrap();

		assert_eq!(counts["books"].as_i64().unwrap(), books);
		assert_eq!(counts["authors"].as_i64().unwrap(), authors);
	}

	#[tokio::test]
	async fn map_points_level0_full_world() {
		let Some(app) = app_for_test().await else { return };
		let Some(pool) = test_pool().await else { return };

		let res = app
			.oneshot(
				Request::builder()
					.uri("/map/points?entity=book&z=0&x0=-1&y0=-1&x1=1&y1=1")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		let json: serde_json::Value = serde_json::from_str(&body).unwrap();

		let (total,): (i64,) = sqlx::query_as("SELECT count(*) FROM map_coords WHERE entity = 'book'")
			.fetch_one(&pool)
			.await
			.unwrap();
		if total == 0 {
			return; // no map data seeded
		}

		let nodes = json["nodes"].as_array().unwrap();
		assert_eq!(nodes.len(), 1, "level 0 aggregates the whole world into one cell");
		assert_eq!(nodes[0]["count"].as_i64().unwrap(), total);
		assert_eq!(json["total"].as_i64().unwrap(), total);
		assert_eq!(json["level"].as_i64().unwrap(), 0);
		assert!(nodes[0]["id"].is_string());
		assert!(nodes[0]["label"].is_string());
	}

	#[tokio::test]
	async fn map_points_rejects_invalid_params() {
		let Some(app) = app_for_test().await else { return };

		for uri in [
			"/map/points?entity=planet&z=3&x0=-1&y0=-1&x1=1&y1=1",
			"/map/points?entity=book&z=99&x0=-1&y0=-1&x1=1&y1=1",
			"/map/points?entity=book&z=-1&x0=-1&y0=-1&x1=1&y1=1",
			"/map/points?entity=book&z=3&x0=1&y0=-1&x1=-1&y1=1",
		] {
			let res = app
				.clone()
				.oneshot(
					Request::builder()
						.uri(uri)
						.body(Body::empty())
						.unwrap(),
				)
				.await
				.unwrap();
			assert_eq!(res.status(), StatusCode::BAD_REQUEST, "{uri}");
		}
	}

	#[tokio::test]
	async fn map_points_high_zoom_returns_intersecting_cells() {
		let Some(app) = app_for_test().await else { return };
		let Some(pool) = test_pool().await else { return };

		let Some((px, py)): Option<(f64, f64)> = sqlx::query_as(
			"SELECT x, y FROM map_coords WHERE entity = 'book' LIMIT 1",
		)
		.fetch_optional(&pool)
		.await
		.unwrap() else {
			return; // no map data seeded
		};

		let z = 13;
		let side = 2.0 / (1i64 << z) as f64;
		let x0 = px - side * 0.25;
		let x1 = px + side * 0.25;
		let y0 = py - side * 0.25;
		let y1 = py + side * 0.25;

		let uri = format!(
			"/map/points?entity=book&z={z}&x0={x0}&y0={y0}&x1={x1}&y1={y1}"
		);
		let res = app
			.oneshot(
				Request::builder()
					.uri(uri)
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		let json: serde_json::Value = serde_json::from_str(&body).unwrap();
		let nodes = json["nodes"].as_array().unwrap();
		assert!(
			!nodes.is_empty(),
			"the cell containing the seeded point must be returned"
		);
		for n in nodes {
			let nx = n["x"].as_f64().unwrap();
			let ny = n["y"].as_f64().unwrap();
			assert!(
				nx >= x0 - side && nx <= x1 + side && ny >= y0 - side && ny <= y1 + side,
				"returned cell positions must be near the viewport"
			);
		}
	}

	#[tokio::test]
	async fn map_points_degrades_huge_viewport_level() {
		let Some(app) = app_for_test().await else { return };

		let res = app
			.oneshot(
				Request::builder()
					.uri("/map/points?entity=book&z=13&x0=-1&y0=-1&x1=1&y1=1")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		let json: serde_json::Value = serde_json::from_str(&body).unwrap();
		let nodes = json["nodes"].as_array().unwrap();
		assert!(nodes.len() <= 4096, "cell scan cap must hold");
		assert_eq!(json["level"].as_i64().unwrap(), 6);
	}

	#[tokio::test]
	async fn map_points_off_world_viewport_is_empty() {
		let Some(app) = app_for_test().await else { return };

		let res = app
			.oneshot(
				Request::builder()
					.uri("/map/points?entity=book&z=5&x0=2&y0=2&x1=3&y1=3")
					.body(Body::empty())
					.unwrap(),
			)
			.await
			.unwrap();
		assert_eq!(res.status(), StatusCode::OK);
		let body = body_string(res.into_body()).await;
		let json: serde_json::Value = serde_json::from_str(&body).unwrap();
		assert_eq!(json["nodes"].as_array().unwrap().len(), 0);
		assert_eq!(json["total"].as_i64().unwrap(), 0);
	}
}
