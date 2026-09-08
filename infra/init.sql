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

    -- gte-base-en-v1.5 is 768 dims
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
