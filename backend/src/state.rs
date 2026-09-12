use std::sync::Arc;

use moka::sync::Cache;
use sqlx::PgPool;

use crate::models::GridRow;

/// LRU cache
pub type CellCache = Cache<(String, i32, i32, i32), Option<Arc<GridRow>>>;

#[derive(Clone)]
pub struct AppState {
	pub pool: Arc<PgPool>,
	pub grid_cache: Arc<CellCache>,
}

impl AppState {
	pub fn new(pool: PgPool) -> Self {
		Self {
			pool: Arc::new(pool),
			grid_cache: Arc::new(Cache::builder().max_capacity(50_000).build()),
		}
	}
}
