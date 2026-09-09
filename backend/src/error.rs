use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;

#[derive(Debug)]
pub enum AppError {
	NotFound(String),
	BadRequest(String),
	Internal(String),
}

impl IntoResponse for AppError {
	fn into_response(self) -> Response {
		let (status, message) = match self {
			AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
			AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
			AppError::Internal(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg),
		};
		(status, Json(serde_json::json!({ "error": message }))).into_response()
	}
}

impl<E: std::fmt::Display> From<E> for AppError {
	fn from(err: E) -> Self {
		AppError::Internal(err.to_string())
	}
}
