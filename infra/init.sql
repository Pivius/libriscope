CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS works (
	id TEXT PRIMARY KEY,
	title TEXT,
	subtitle TEXT,
	description TEXT,
	first_sentence TEXT,
	subjects TEXT[],
	genres TEXT[],
	authors TEXT[],
	languages TEXT[],
	first_publish_date TEXT,
	series TEXT[],
	source TEXT DEFAULT 'openlibrary'
);

CREATE TABLE IF NOT EXISTS work_embeddings (
	work_id TEXT PRIMARY KEY REFERENCES works(id) ON DELETE CASCADE,

	-- ETL auto-migrates this column when EMBEDDINGS_MODEL changes dimension
	embedding VECTOR(768)
);

CREATE TABLE IF NOT EXISTS ratings (
	work_id TEXT,
	edition_id TEXT,
	rating SMALLINT,
	date TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_work_embeddings_vector
ON work_embeddings
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_works_title
ON works (title);

CREATE INDEX IF NOT EXISTS idx_works_language
ON works (languages);

CREATE INDEX IF NOT EXISTS idx_ratings_work
ON ratings (work_id);

CREATE TABLE IF NOT EXISTS authors (
	name TEXT PRIMARY KEY,
	work_count INT NOT NULL,
	embedding VECTOR(768)
);

CREATE INDEX IF NOT EXISTS idx_authors_embedding
ON authors
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_authors_name
ON authors (name);

CREATE TABLE IF NOT EXISTS map_coords (
	entity TEXT NOT NULL,
	entity_id TEXT NOT NULL,
	x DOUBLE PRECISION NOT NULL,
	y DOUBLE PRECISION NOT NULL,
	PRIMARY KEY (entity, entity_id)
);

-- ETL bookkeeping: records which embedding model produced the current vectors
-- so switching EMBEDDINGS_MODEL automatically clears stale embeddings.
CREATE TABLE IF NOT EXISTS pipeline_meta (
	key TEXT PRIMARY KEY,
	value TEXT NOT NULL
);
