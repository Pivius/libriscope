use std::sync::Arc;

use crate::db::Db;

#[derive(Clone)]
pub struct AppState {
    pub db: Arc<Db>,
}
