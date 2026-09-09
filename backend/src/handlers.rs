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
    State(_state): State<AppState>,
    Path(_id): Path<String>,
) -> Result<Json<Book>, AppError> {
    // TODO: fetch a book by work id from `works`.
    Err(AppError::NotFound("not implemented".to_string()))
}

pub async fn recommend_books(
    State(_state): State<AppState>,
    Json(req): Json<RecommendRequest>,
) -> Result<Json<RecommendResponse>, AppError> {
    // TODO: pipeline request validation (e.g. non-empty work_ids, limit cap).
    let recommendations = recommend::recommend(&req).await?;
    Ok(Json(RecommendResponse { recommendations }))
}
