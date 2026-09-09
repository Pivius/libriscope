use axum::extract::{Path, State};
use axum::Json;

use crate::error::AppError;
use crate::models::{
	AuthorDetail, AuthorNode, AuthorRecommendRequest, AuthorRecommendResponse, Book, HealthResponse,
	MapNode, RecommendRequest, RecommendResponse,
};
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
) -> Result<Json<Vec<MapNode>>, AppError> {
	let nodes = sqlx::query_as::<_, MapNode>(
		r#"
		SELECT mc.entity_id AS id, COALESCE(w.title, mc.entity_id) AS label, mc.x, mc.y
		FROM map_coords mc
		LEFT JOIN works w ON w.id = mc.entity_id
		WHERE mc.entity = 'book'
		"#,
	)
		.fetch_all(pool.as_ref())
		.await?;

	Ok(Json(nodes))
}

pub async fn map_authors(
	State(AppState { pool, .. }): State<AppState>,
) -> Result<Json<Vec<AuthorNode>>, AppError> {
	let nodes = sqlx::query_as::<_, AuthorNode>(
		r#"
		SELECT mc.entity_id AS name, COALESCE(a.work_count, 0) AS work_count, mc.x, mc.y
		FROM map_coords mc
		LEFT JOIN authors a ON a.name = mc.entity_id
		WHERE mc.entity = 'author'
		"#,
	)
		.fetch_all(pool.as_ref())
		.await?;

	Ok(Json(nodes))
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
