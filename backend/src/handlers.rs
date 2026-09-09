use axum::extract::{Path, State};
use axum::Json;

use crate::error::AppError;
use crate::models::{Book, HealthResponse, RecommendRequest, RecommendResponse};
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
    State(_state): State<AppState>,
    Json(req): Json<RecommendRequest>,
) -> Result<Json<RecommendResponse>, AppError> {
    // TODO: pipeline request validation (e.g. non-empty work_ids, limit cap).
    let recommendations = recommend::recommend(&req).await?;
    Ok(Json(RecommendResponse { recommendations }))
}
