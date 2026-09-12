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
	#[serde(default)]
	pub genre_mode: Option<String>,
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

#[derive(Debug, Clone, Serialize, FromRow)]
pub struct MapNode {
	pub id: String,
	pub label: String,
	pub x: f64,
	pub y: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct MapBooksResponse {
	pub nodes: Vec<MapNode>,
	pub total: i64,
}

#[derive(Debug, Clone, Serialize, FromRow)]
pub struct AuthorNode {
	pub name: String,
	pub work_count: i32,
	pub x: f64,
	pub y: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct MapAuthorsResponse {
	pub nodes: Vec<AuthorNode>,
	pub total: i64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MapQuery {
	pub limit: Option<i64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MapPointsQuery {
	pub entity: String,
	pub z: i32,
	pub x0: f64,
	pub y0: f64,
	pub x1: f64,
	pub y1: f64,
}

#[derive(Debug, Clone, Serialize, FromRow)]
pub struct GridRow {
	pub cx: i32,
	pub cy: i32,
	pub count: i32,
	pub x_avg: f64,
	pub y_avg: f64,
	pub sample_id: String,
	pub sample_label: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct MapPointNode {
	pub id: String,
	pub label: String,
	pub x: f64,
	pub y: f64,
	pub count: i32,
}

#[derive(Debug, Clone, Serialize)]
pub struct MapPointsResponse {
	pub nodes: Vec<MapPointNode>,
	pub total: i64,
	pub level: i32,
}

#[derive(Debug, Clone, Serialize)]
pub struct CountsResponse {
	pub books: i64,
	pub authors: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct AuthorDetail {
	pub name: String,
	pub work_count: i32,
	pub works: Vec<Book>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AuthorRecommendRequest {
	pub author_names: Vec<String>,
	#[serde(default = "default_limit")]
	pub limit: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct AuthorRecommendation {
	pub name: String,
	pub similarity: f32,
}

#[derive(Debug, Clone, Serialize)]
pub struct AuthorRecommendResponse {
	pub recommendations: Vec<AuthorRecommendation>,
}
