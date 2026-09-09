mod config;
mod db;
mod error;
mod handlers;
mod models;
mod recommend;
mod state;

use std::sync::Arc;

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

	let state = AppState {
		pool: Arc::new(pool),
	};

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
		Some(app(AppState {
			pool: Arc::new(pool),
		}))
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

		// /map/books returns nodes with id + label + coordinates
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
		assert!(body.contains("\"label\""));
		assert!(body.contains("\"x\""));

		// /map/authors returns nodes with name + coordinates
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
		let body = body_string(res.into_body()).await;
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
}
