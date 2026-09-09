use crate::error::AppError;
use crate::models::{Recommendation, RecommendRequest};

pub async fn recommend(_req: &RecommendRequest) -> Result<Vec<Recommendation>, AppError> {
    // TODO: implement against the database.
    Ok(Vec::new())
}
