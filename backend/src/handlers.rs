use axum::extract::{Path, Query, State};
use axum::http::HeaderValue;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Serialize;

use crate::error::AppError;
use crate::models::{
	AuthorDetail, AuthorNode, AuthorRecommendRequest, AuthorRecommendResponse, Book, HealthResponse,
	MapAuthorsResponse, MapBooksResponse, MapNode, MapQuery, RecommendRequest, RecommendResponse,
};

const MAP_LIMIT_DEFAULT: i64 = 5000;
const MAP_LIMIT_MAX: i64 = 5000;

/// Serializes `body` as JSON and attaches `total` as the `X-Total-Count` header.
pub(crate) struct TotalCountResponse<T>(T, i64);

impl<T: Serialize> IntoResponse for TotalCountResponse<T> {
	fn into_response(self) -> Response {
		let mut res = Json(self.0).into_response();
		if let Ok(value) = HeaderValue::from_str(&self.1.to_string()) {
			res.headers_mut().insert("X-Total-Count", value);
		}
		res
	}
}

async fn map_count(pool: &sqlx::PgPool, entity: &str) -> Result<i64, AppError> {
	Ok(sqlx::query_scalar("SELECT count(*) FROM map_coords WHERE entity = $1")
		.bind(entity)
		.fetch_one(pool)
		.await?)
}
use crate::recommend;
use crate::state::AppState;

pub async fn health(State(AppState { pool, .. }): State<AppState>) -> Result<Json<HealthResponse>, AppError> {
	sqlx::query("SELECT 1").execute(pool.as_ref()).await?;
	Ok(Json(HealthResponse {
		status: "ok".to_string(),
	}))
}

pub async fn get_book(
	State(AppState { pool, .. }): State<AppState>,
	Path(id): Path<String>,
) -> Result<Json<Book>, AppError> {
	let book = sqlx::query_as::<_, Book>(
		r#"
		SELECT id, title, subtitle, description, subjects, genres, authors,
			languages, first_publish_date, series
		FROM works
		WHERE id = $1
		"#,
	)
		.bind(&id)
		.fetch_optional(pool.as_ref())
		.await?
		.ok_or_else(|| AppError::NotFound(format!("book '{id}' not found")))?;

	Ok(Json(book))
}

pub async fn recommend_books(
	State(AppState { pool, .. }): State<AppState>,
	Json(req): Json<RecommendRequest>,
) -> Result<Json<RecommendResponse>, AppError> {
	let recommendations = recommend::recommend(pool.as_ref(), &req).await?;
	Ok(Json(RecommendResponse { recommendations }))
}

pub async fn map_books(
	State(AppState { pool, .. }): State<AppState>,
	Query(q): Query<MapQuery>,
) -> Result<TotalCountResponse<MapBooksResponse>, AppError> {
	let limit = q.limit.unwrap_or(MAP_LIMIT_DEFAULT).clamp(1, MAP_LIMIT_MAX);
	let total = map_count(pool.as_ref(), "book").await?;

	let nodes = sqlx::query_as::<_, MapNode>(
		r#"
			SELECT mc.entity_id AS id, COALESCE(w.title, mc.entity_id) AS label, mc.x, mc.y
			FROM map_coords mc
			LEFT JOIN works w ON w.id = mc.entity_id
			WHERE mc.entity = 'book'
			ORDER BY mc.entity_id
			LIMIT $1
		"#,
	)
		.bind(limit)
		.fetch_all(pool.as_ref())
		.await?;

	Ok(TotalCountResponse(
		MapBooksResponse { nodes, total },
		total,
	))
}

pub async fn map_authors(
	State(AppState { pool, .. }): State<AppState>,
	Query(q): Query<MapQuery>,
) -> Result<TotalCountResponse<MapAuthorsResponse>, AppError> {
	let limit = q.limit.unwrap_or(MAP_LIMIT_DEFAULT).clamp(1, MAP_LIMIT_MAX);
	let total = map_count(pool.as_ref(), "author").await?;

	let nodes = sqlx::query_as::<_, AuthorNode>(
		r#"
			SELECT mc.entity_id AS name, COALESCE(a.work_count, 0) AS work_count, mc.x, mc.y
			FROM map_coords mc
			LEFT JOIN authors a ON a.name = mc.entity_id
			WHERE mc.entity = 'author'
			ORDER BY mc.entity_id
			LIMIT $1
		"#,
	)
		.bind(limit)
		.fetch_all(pool.as_ref())
		.await?;

	Ok(TotalCountResponse(
		MapAuthorsResponse { nodes, total },
		total,
	))
}

pub async fn get_author(
	State(AppState { pool, .. }): State<AppState>,
	Path(name): Path<String>,
) -> Result<Json<AuthorDetail>, AppError> {
	let work_count: i32 = sqlx::query_scalar(
		"SELECT work_count FROM authors WHERE name = $1",
	)
		.bind(&name)
		.fetch_optional(pool.as_ref())
		.await?
		.ok_or_else(|| AppError::NotFound(format!("author '{name}' not found")))?;

	let works = sqlx::query_as::<_, Book>(
		r#"
			SELECT id, title, subtitle, description, subjects, genres, authors,
				languages, first_publish_date, series
			FROM works
			WHERE $1 = ANY(authors)
		"#,
	)
		.bind(&name)
		.fetch_all(pool.as_ref())
		.await?;

	Ok(Json(AuthorDetail {
		name,
		work_count,
		works,
	}))
}

pub async fn recommend_authors(
	State(AppState { pool, .. }): State<AppState>,
	Json(req): Json<AuthorRecommendRequest>,
) -> Result<Json<AuthorRecommendResponse>, AppError> {
	let recommendations = recommend::recommend_authors(pool.as_ref(), &req).await?;
	Ok(Json(AuthorRecommendResponse { recommendations }))
}
