use std::net::SocketAddr;
use std::path::PathBuf;

/// Load `.env` from the current directory, searching upward until one is found.
///
/// The `.env` lives at the repo root, but the backend may be run from either
/// the repo root or `backend/`
pub fn load_dotenv() {
	let _ = dotenvy::dotenv();

	let mut dir = std::env::current_dir().ok();
	while let Some(current) = dir {
		let candidate = current.join(".env");
		if candidate.exists() && dotenvy::from_path(&candidate).is_ok() {
			return;
		}
		dir = current.parent().map(PathBuf::from);
	}
}

#[derive(Debug, Clone)]
pub struct Config {
	pub database_url: String,
	pub bind_addr: SocketAddr,
}

impl Config {
	pub fn from_env() -> Self {
		load_dotenv();

		let database_url =
			std::env::var("DATABASE_URL").expect("DATABASE_URL must be set");

		let bind_addr: SocketAddr = std::env::var("BIND_ADDR")
			.unwrap_or_else(|_| "0.0.0.0:8080".to_string())
			.parse()
			.expect("BIND_ADDR must be a valid socket address");

		Config {
			database_url,
			bind_addr,
		}
	}
}
