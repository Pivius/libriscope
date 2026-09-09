use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct Book {
    pub id: String,
    pub title: Option<String>,
    pub subtitle: Option<String>,
    pub description: Option<String>,
    pub subjects: Vec<String>,
    pub genres: Vec<String>,
    pub authors: Vec<String>,
    pub languages: Vec<String>,
    pub first_publish_date: Option<String>,
    pub series: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RecommendRequest {
    pub work_ids: Vec<String>,
    #[serde(default = "default_limit")]
    pub limit: u32,
}

fn default_limit() -> u32 {
    10
}

#[derive(Debug, Clone, Serialize)]
pub struct Recommendation {
    pub work_id: String,
    pub title: Option<String>,
    pub similarity: f32,
}

#[derive(Debug, Clone, Serialize)]
pub struct RecommendResponse {
    pub recommendations: Vec<Recommendation>,
}

#[derive(Debug, Clone, Serialize)]
pub struct HealthResponse {
    pub status: String,
}
