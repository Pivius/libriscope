use std::net::SocketAddr;

#[derive(Debug, Clone)]
pub struct Config {
    pub database_url: String,
    pub bind_addr: SocketAddr,
}

impl Config {
    pub fn from_env() -> Self {
        // .env lives at the repo root
        let _ = dotenvy::dotenv();
        if let Ok(path) = std::env::current_dir() {
            let _ = dotenvy::from_path(path.join(".env"));
        }

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
