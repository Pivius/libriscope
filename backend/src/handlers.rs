use axum::extract::{Path, Query, State};
use axum::http::HeaderValue;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Serialize;
use std::sync::Arc;

use crate::error::AppError;
use crate::grid;
use crate::models::{
	AuthorDetail, AuthorNode, AuthorRecommendRequest, AuthorRecommendResponse, Book, CountsResponse,
	GridRow, HealthResponse, MapAuthorsResponse, MapBooksResponse, MapNode, MapPointNode,
	MapPointsQuery, MapPointsResponse, MapQuery, RecommendRequest, RecommendResponse,
	SearchNode, SearchQuery, SearchResponse,
};

const MAP_LIMIT_DEFAULT: i64 = 5000;
const MAP_LIMIT_MAX: i64 = 5000;
const MAX_CELLS: i64 = 4096;

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

const SEARCH_LIMIT_DEFAULT: i64 = 10;
const SEARCH_LIMIT_MAX: i64 = 50;

pub async fn search(
	State(AppState { pool, .. }): State<AppState>,
	Query(q): Query<SearchQuery>,
) -> Result<Json<SearchResponse>, AppError> {
	let term = q.q.trim();
	if term.is_empty() {
		return Ok(Json(SearchResponse { nodes: Vec::new() }));
	}
	let entity = q.entity.as_deref().unwrap_or("book");
	if entity != "book" && entity != "author" {
		return Err(AppError::BadRequest(
			"entity must be 'book' or 'author'".to_string(),
		));
	}
	let limit = q.limit.unwrap_or(SEARCH_LIMIT_DEFAULT).clamp(1, SEARCH_LIMIT_MAX);
	let pattern = format!("%{}%", term.replace('%', "\\%").replace('_', "\\_"));

	let nodes = if entity == "book" {
		sqlx::query_as::<_, SearchNode>(
			r#"
			SELECT w.id AS id, w.title AS label, mc.x, mc.y
			FROM works w
			JOIN map_coords mc ON mc.entity = 'book' AND mc.entity_id = w.id
			WHERE w.title ILIKE $1
			ORDER BY w.title
			LIMIT $2
			"#,
		)
			.bind(&pattern)
			.bind(limit)
			.fetch_all(pool.as_ref())
			.await?
	} else {
		sqlx::query_as::<_, SearchNode>(
			r#"
			SELECT a.name AS id, a.name AS label, mc.x, mc.y
			FROM authors a
			JOIN map_coords mc ON mc.entity = 'author' AND mc.entity_id = a.name
			WHERE a.name ILIKE $1
			ORDER BY a.name
			LIMIT $2
			"#,
		)
			.bind(&pattern)
			.bind(limit)
			.fetch_all(pool.as_ref())
			.await?
	};

	Ok(Json(SearchResponse { nodes }))
}

#[derive(Debug, sqlx::FromRow)]
struct GridRowOpt {
	cx: i32,
	cy: i32,
	count: Option<i32>,
	x_avg: Option<f64>,
	y_avg: Option<f64>,
	sample_id: Option<String>,
	sample_label: Option<String>,
}

impl GridRowOpt {
	fn into_row(self) -> Option<GridRow> {
		Some(GridRow {
			cx: self.cx,
			cy: self.cy,
			count: self.count?,
			x_avg: self.x_avg?,
			y_avg: self.y_avg?,
			sample_id: self.sample_id?,
			sample_label: self.sample_label?,
		})
	}
}

pub async fn map_points(
	State(AppState { pool, grid_cache }): State<AppState>,
	Query(q): Query<MapPointsQuery>,
) -> Result<Json<MapPointsResponse>, AppError> {
	if q.entity != "book" && q.entity != "author" {
		return Err(AppError::BadRequest(
			"entity must be 'book' or 'author'".to_string(),
		));
	}
	if !(0..=grid::MAX_LEVEL).contains(&q.z) {
		return Err(AppError::BadRequest(format!(
			"z must be in 0..={}",
			grid::MAX_LEVEL
		)));
	}
	if !(q.x0 < q.x1) || !(q.y0 < q.y1) {
		return Err(AppError::BadRequest(
			"viewport must satisfy x0 < x1 and y0 < y1".to_string(),
		));
	}

	if q.x1 < -1.0 || q.x0 > 1.0 || q.y1 < -1.0 || q.y0 > 1.0 {
		return Ok(Json(MapPointsResponse {
			nodes: Vec::new(),
			total: 0,
			level: q.z,
		}));
	}

	// Degrade the level until the bbox cell range stays within the scan cap so
	// a huge viewport at a high level can never explode the query.
	let mut z = q.z;
	while z > 0 && grid::cell_range_size(q.x0, q.x1, q.y0, q.y1, z) > MAX_CELLS {
		z -= 1;
	}

	let entity = q.entity.as_str();
	let cx0 = grid::cell_of(q.x0, z);
	let cx1 = grid::cell_of(q.x1, z);
	let cy0 = grid::cell_of(q.y0, z);
	let cy1 = grid::cell_of(q.y1, z);

	let mut rows: Vec<GridRow> = Vec::new();
	let mut misses: Vec<(i32, i32)> = Vec::new();
	for cx in cx0..=cx1 {
		for cy in cy0..=cy1 {
			match grid_cache.get(&(entity.to_owned(), z, cx, cy)) {
				Some(Some(row)) => rows.push((*row).clone()),
				Some(None) => {}
				None => misses.push((cx, cy)),
			}
		}
	}

	if !misses.is_empty() {
		let (xs, ys): (Vec<i32>, Vec<i32>) = misses.into_iter().unzip();
		let fetched = sqlx::query_as::<_, GridRowOpt>(
			r#"
				SELECT c.cx, c.cy, mg.count, mg.x_avg, mg.y_avg, mg.sample_id, mg.sample_label
				FROM unnest($1::int4[], $2::int4[]) AS c(cx, cy)
				LEFT JOIN map_grids mg
					ON mg.entity = $3 AND mg.level = $4
					AND mg.cx = c.cx AND mg.cy = c.cy
			"#,
		)
			.bind(&xs)
			.bind(&ys)
			.bind(entity)
			.bind(z)
			.fetch_all(pool.as_ref())
			.await?;

		for opt in fetched {
			let key = (entity.to_owned(), z, opt.cx, opt.cy);
			let row = opt.into_row();

			grid_cache.insert(key, row.clone().map(Arc::new));
			
			if let Some(r) = row {
				rows.push(r);
			}
		}
	}

	rows.sort_by_key(|r| (r.cx, r.cy));
	let total: i64 = rows.iter().map(|r| i64::from(r.count)).sum();
	let nodes = rows
		.into_iter()
		.map(|r| MapPointNode {
			id: r.sample_id,
			label: r.sample_label,
			x: r.x_avg,
			y: r.y_avg,
			count: r.count,
		})
		.collect();

	Ok(Json(MapPointsResponse {
		nodes,
		total,
		level: z,
	}))
}

pub async fn map_counts(
	State(AppState { pool, .. }): State<AppState>,
) -> Result<Json<CountsResponse>, AppError> {
	let rows: Vec<(String, i32)> = sqlx::query_as(
		"SELECT entity, count FROM map_grids WHERE level = 0 AND cx = 0 AND cy = 0",
	)
	.fetch_all(pool.as_ref())
	.await?;

	let mut counts = CountsResponse {
		books: 0,
		authors: 0,
	};
	for (entity, count) in rows {
		match entity.as_str() {
			"book" => counts.books = i64::from(count),
			"author" => counts.authors = i64::from(count),
			_ => {}
		}
	}

	Ok(Json(counts))
}
