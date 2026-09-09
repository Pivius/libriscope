mod config;
mod db;
mod error;
mod handlers;
mod models;
mod recommend;
mod state;

use std::sync::Arc;

use axum::{routing::get, Router};
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

use crate::config::Config;
use crate::db::Db;
use crate::state::AppState;

fn app(state: AppState) -> Router {
    Router::new()
        .route("/health", get(handlers::health))
        .route("/books/{id}", get(handlers::get_book))
        .route("/recommend", axum::routing::post(handlers::recommend_books))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .init();

    let config = Config::from_env();
    let db = Db::connect(&config.database_url)
        .await
        .expect("failed to connect to database");

    let state = AppState {
        db: Arc::new(db),
    };

    let listener = tokio::net::TcpListener::bind(config.bind_addr)
        .await
        .expect("failed to bind listener");

    tracing::info!("listening on {}", config.bind_addr);

    axum::serve(listener, app(state))
        .with_graceful_shutdown(shutdown_signal())
        .await
        .expect("server error");
}

async fn shutdown_signal() {
    let _ = tokio::signal::ctrl_c().await;
    tracing::info!("shutdown signal received");
}
