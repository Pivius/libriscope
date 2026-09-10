# Deployment

Local installation of a Postgres instance with `pgvector` and Ollama are required.

## Prerequisites

- Python 3.11+
- PostgreSQL with the `pgvector` extension (`CREATE EXTENSION vector;`)
- [Ollama](https://ollama.com) with the `bge-m3` embedding model

## 0. Start Ollama + pull the model

```bash
ollama serve            # if not already running as a service
make ollama-pull        # ollama pull bge-m3
make ollama-check       # check reachability + model presence
```

Embeddings are computed **during ETL only** and reused afterwards.

## 1. Configure environment

```bash
cp .env.example .env
# set DATABASE_URL, EMBEDDINGS_MODEL, etc.
```

Key evnironment variables:

| Environment Variable| Default                                                       | Description                      |
| ------------------- | ------------------------------------------------------------- | -------------------------------- |
| `DATABASE_URL`      | `postgresql://postgres:postgres@localhost:5432/libriscope`    | connection to Postgres/pgvector  |
| `OLLAMA_HOST`       | `http://localhost:11434`                                      | Ollama host url                  |
| `EMBEDDINGS_MODEL`  | `bge-m3`                                                      | embedding model (1024 dims on the installed Ollama F16 build) |
| `PROCESSED_DIR`     | `data/processed/openlibrary`                                  | Input TSV/CSV files directory    |
| `BATCH_SIZE`        | `32`                                                          | Embedding per batch              |
| `MAX_AUX`           | `500000`                                                      | Limit on the number of in-memory authors/editions index |

## 2. Init the database

```bash
psql "$DATABASE_URL" -f infra/init.sql
```

`infra/init.sql` creates `works`, `work_embeddings` (VECTOR(1024)), and `ratings` tables as well as HNSW and btree indexes.

## 3. Install ETL dependencies

```bash
make install   # pip install -r etl/requirements.txt
```

## 4. Data ingestion & embedding

```bash
make etl             # full ingest: collation -> build text -> embedding -> writing to DB
make rebuild-embeddings   # only recompute embeddings (no upsert for metadata)
```

Or run directly:

```bash
PYTHONPATH=. python -m etl.jobs.run_openlibrary --dir data/processed/openlibrary
```

## 5. Tests

```bash
make test              # ETL unit tests
make backend-test      # backend tests (requires DATABASE_URL)
```

## 6. Backend API

```bash
make backend-build     # cargo build
make backend-run       # cargo run (by default runs at 0.0.0.0:8080)
```

Endpoints:

| Method | Path           | Description                          |
| ------ | -------------- | ------------------------------------ |
| GET    | `/health`      | liveness + DB connectivity check     |
| GET    | `/books/{id}`  | book details by work id (URL-encoded) |
| POST   | `/recommend`   | similar books from a list of work ids |

Example:

```bash
curl -s -X POST http://localhost:8080/recommend \
	-H 'content-type: application/json' \
	-d '{"work_ids":["/works/OL10000266W"],"limit":5}'
```

Pure vector calculations happen on the backend using pre-computed embeddings (centroid of the input works vectors + pgvector cosine kNN).
It never queries any AI models.

## Notes

- **Dimensionality of embeddings**: The pipeline uses `bge-m3` embeddings (1024 dimensions on a locally installed Ollama build). The embedding dimension can be different depending on the Ollama build.
- **Work IDs**: IDs start with `/` (`/works/OL...`) so they need to be encoded in URLs.
- **Docker Postgres**:

	```bash
	make db-up     # runs the db service only from infra/docker-compose.yml
	make db-down
	```
