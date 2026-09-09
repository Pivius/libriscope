use std::format;
use sqlx::PgPool;

use crate::error::AppError;
use crate::models::{
	AuthorRecommendation, AuthorRecommendRequest, Recommendation, RecommendRequest,
};

/// Mean of a slice of equal-length vectors.
fn centroid(vectors: &[Vec<f32>]) -> Vec<f32> {
	let dim = vectors[0].len();
	let mut out = vec![0.0f32; dim];

	for vec in vectors {
		for (i, &v) in vec.iter().enumerate() {
			out[i] += v;
		}
	}

	let n = vectors.len() as f32;
	for v in &mut out {
		*v /= n;
	}
	out
}

/// Parse a pgvector text literal into a `Vec<f32>`.
fn parse_vector(text: &str) -> Vec<f32> {
	text.trim()
	.trim_start_matches('[')
	.trim_end_matches(']')
	.split(',')
	.filter_map(|s| s.trim().parse::<f32>().ok())
	.collect()
}

/// Format a `Vec<f32>` as a pgvector text literal.
fn format_vector(vec: &[f32]) -> String {
	let body = vec
		.iter()
		.map(|v| v.to_string())
		.collect::<Vec<_>>()
		.join(",");
	format!("[{body}]")
}

pub async fn recommend(pool: &PgPool, req: &RecommendRequest) -> Result<Vec<Recommendation>, AppError> {
	if req.work_ids.is_empty() {
		return Err(AppError::BadRequest(
			"work_ids must contain at least one id".to_string(),
		));
	}

	// fetch the input works' embeddings
	let rows = sqlx::query_as::<_, (String, String)>(
		"SELECT work_id, embedding::text FROM work_embeddings WHERE work_id = ANY($1)",
	)
		.bind(&req.work_ids)
		.fetch_all(pool)
		.await?;

	if rows.is_empty() {
		return Ok(Vec::new());
	}

	let vectors: Vec<Vec<f32>> = rows.iter().map(|(_, t)| parse_vector(t)).collect();
	let centroid = centroid(&vectors);
	let query_vec = format_vector(&centroid);

	// cosine kNN
	let limit = req.limit.min(50) as i64;

	let recs = sqlx::query_as::<_, (String, Option<String>, f64)>(
		r#"
		SELECT w.id, w.title, 1 - (we.embedding <=> $1::vector) AS similarity
		FROM work_embeddings we
		JOIN works w ON w.id = we.work_id
		WHERE NOT (we.work_id = ANY($2))
		ORDER BY we.embedding <=> $1::vector
		LIMIT $3
		"#,
	)
		.bind(&query_vec)
		.bind(&req.work_ids)
		.bind(limit)
		.fetch_all(pool)
		.await?;

	let recommendations = recs
		.into_iter()
		.map(|(work_id, title, similarity)| Recommendation {
			work_id,
			title,
			similarity: similarity as f32,
		})
		.collect();

	Ok(recommendations)
}

pub async fn recommend_authors(
	pool: &PgPool,
	req: &AuthorRecommendRequest,
) -> Result<Vec<AuthorRecommendation>, AppError> {
	if req.author_names.is_empty() {
		return Err(AppError::BadRequest(
			"author_names must contain at least one name".to_string(),
		));
	}

	// fetch the input authors' embeddings
	let rows = sqlx::query_as::<_, (String, String)>(
		"SELECT name, embedding::text FROM authors WHERE name = ANY($1)",
	)
		.bind(&req.author_names)
		.fetch_all(pool)
		.await?;

	if rows.is_empty() {
		return Ok(Vec::new());
	}

	let vectors: Vec<Vec<f32>> = rows.iter().map(|(_, t)| parse_vector(t)).collect();
	let centroid = centroid(&vectors);
	let query_vec = format_vector(&centroid);

	let limit = req.limit.min(50) as i64;

	let recs = sqlx::query_as::<_, (String, f64)>(
		r#"
		SELECT a.name, 1 - (a.embedding <=> $1::vector) AS similarity
		FROM authors a
		WHERE NOT (a.name = ANY($2))
		ORDER BY a.embedding <=> $1::vector
		LIMIT $3
		"#,
	)
		.bind(&query_vec)
		.bind(&req.author_names)
		.bind(limit)
		.fetch_all(pool)
		.await?;

	let recommendations = recs
		.into_iter()
		.map(|(name, similarity)| AuthorRecommendation {
			name,
			similarity: similarity as f32,
		})
		.collect();

	Ok(recommendations)
}

#[cfg(test)]
mod tests {
	use super::*;

	#[test]
	fn centroid_is_mean() {
		let v = vec![vec![1.0, 3.0], vec![3.0, 1.0]];
		let c = centroid(&v);
		assert_eq!(c, vec![2.0, 2.0]);
	}

	#[test]
	fn parse_roundtrip() {
		assert_eq!(parse_vector("[1.0,2.5,3]"), vec![1.0, 2.5, 3.0]);
		assert_eq!(format_vector(&[1.0, 2.5, 3.0]), "[1,2.5,3]");
	}
}
