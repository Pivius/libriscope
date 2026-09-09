
#[derive(Clone)]
pub struct Db;

impl Db {
    pub async fn connect(_database_url: &str) -> Result<Self, String> {
        // TODO: create a connection pool from `database_url`.
        Ok(Db)
    }
}
