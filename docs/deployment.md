# Deployment

Local Postgres with pgvector, Python with CUDA-capable PyTorch, a Rust backend, and a Next.js frontend.

## Prerequisites

* Python 3.11+
* PostgreSQL + pgvector extension
* PyTorch with CUDA for GPU embedding.
* Rust toolchain for the backend
* Node.js for the frontend

The embedding model downloads from Hugging Face on first use. The fastText language model downloads on the first ETL run.

## Environment

```bash
cp .env.example .env
```

| Variable           | Default                                                    | Description                                                                            |
| ------------------ | ---------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `DATABASE_URL`     | `postgresql://postgres:postgres@localhost:5432/libriscope` | Postgres connection string                                                             |
| `BIND_ADDR`        | `0.0.0.0:8080`                                             | Backend bind address                                                                   |
| `EMBEDDINGS_MODEL` | `BAAI/bge-base-en-v1.5`                                    | sentence-transformers model. Changing it clears stale vectors and resizes the columns. |
| `EMBED_BATCH_SIZE` | `192`                                                      | Texts per GPU encode batch                                                             |
| `PROCESSED_DIR`    | `data/processed/openlibrary`                               | Input TSV chunk directory                                                              |
| `BATCH_SIZE`       | `64`                                                       | Items per ETL queue batch                                                              |
| `MAX_AUX`          | `500000`                                                   | Cap on the in-memory author index                                                      |
| `MAX_WORKS`        | unset                                                      | Stop after N streamed works                                                            |

The Makefile reads `.env`, so `make` targets can see `DATABASE_URL` without exporting it manually.

## Database

```bash
make db-init
```

`psql` applies `infra/init.sql`, which creates missing tables and indexes. Then `scripts/migrate_schema.py` compares that file with the live schema and adds or drops columns and tables to match.

These steps are also idempotent. You can run `make db-init` after changing `init.sql` and it will update an existing database without losing any data.

```bash
make db-clear    # truncate all data tables, keep the schema
```

## Embedding model

Embeddings are calculated in the ETL and then reused afterwards. The model can be any sentence-transformers and Hugging Face encoder set using `EMBEDDINGS_MODEL`.

When the model is switched for the first time, it resizes the vector columns to the new dimension, then drops and rebuilds the HNSW indexes, clearing `work_embeddings`, `authors`, and `map_coords`. Vectors from different models aren't comparable.

```bash
make model-check    # downloads and loads the model, prints its dimension
```

| Model                                | Parameters | Dimensions |
| ------------------------------------ | ---------- | ---------- |
| `BAAI/bge-base-en-v1.5`              | 109M       | 768        |
| `BAAI/bge-small-en-v1.5`             | 24M        | 384        |
| `mixedbread-ai/mxbai-embed-large-v1` | 335M       | 1024       |

Measured throughput on a GTX 1660 with in-process sentence-transformers: 150 to 300 works per second at a batch size of 64.

## Data pipeline

`make process-data` splits the raw dumps into gzipped TSV chunks of 2,000,000 lines named `{type}_{upper_bound}.csv.gz`.

```bash
make process-data                 # all identifiers
make process-data ARGS="--test"   # small sample
```

`make etl` streams the works chunks. It skips deleted and redirected keys, rejects works with non-English titles, 
uses the authors index to resolve author keys to names, builds and encodes the embedding text, then upserts the row and vector.

The HNSW index on `work_embeddings` is dropped before the load and rebuilt once at the end.

When it starts, the pipeline counts the committed rows in work_embeddings and skips that many works. 
If a run is cancelled mid-batch, it re-embeds at most one partial batch. 

### ETL flags

Pass flags through `ARGS=`.

| Flag                   | Effect                                                                                                            |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `--max-works N`        | Stop after streaming N works. Enforced in the adapter, so the stream stops early instead of filtering downstream. |
| `--no-skip`            | Re-embed works that already have vectors. Default is to skip them.                                                |
| `--reset`              | Truncate all data tables first.                                                                                   |
| `--no-db`              | Skip metadata writes.                                                                                             |
| `--no-embeddings`      | Skip encoding.                                                                                                    |
| `--dir PATH`           | Override `PROCESSED_DIR`.                                                                                         |
| `--batch-size N`       | Override `BATCH_SIZE`.                                                                                            |
| `--embed-batch-size N` | Override `EMBED_BATCH_SIZE`.                                                                                      |
| `--max-seq-length N`   | Cap tokens per text. Default 512.                                                                                 |
| `--max-aux N`          | Override `MAX_AUX`.                                                                                               |
| `--skip-editions`      | Deprecated. Editions are not processed.                                                                           |

### Common flows

```bash
make etl ARGS="--max-works 500000 --reset"  # 500k map
make etl ARGS="--max-works 700000"          # continue where the last run stopped
```

The full OpenLibrary dump holds about 40M works. 
Embedding all of them on one GPU takes days and produces a map too dense to read. 
Its probably best to filter for rating, genre, etc.

## Downstream jobs

```bash
make author-embeddings     # centroid vector per author, into authors
make map-coords            # PCA projection into map_coords
make map-grids             # LOD aggregates into map_grids, levels 0 to 13
make axis-labels           # quadrant labels into frontend/public/axis-labels.json
```

Run them in that order after any ETL run that added works.

## Backend

```bash
make backend-build
make backend-run
```

| Method | Path                 | Description                                 |
| ------ | -------------------- | ------------------------------------------- |
| GET    | `/health`            | Liveness and database check                 |
| GET    | `/books/{id}`        | Full work record                            |
| GET    | `/authors/{name}`    | Author record with their works              |
| POST   | `/recommend`         | Similar books for a list of work ids        |
| POST   | `/recommend-authors` | Similar authors for a list of names         |
| GET    | `/search`            | Title or name search over the whole catalog |
| GET    | `/map/books`         | First N book nodes, bounded at 5000         |
| GET    | `/map/authors`       | First N author nodes, bounded at 5000       |
| GET    | `/map/points`        | LOD cells intersecting a viewport box       |
| GET    | `/map/counts`        | Total book and author counts                |

Examples:

```bash
curl -s -X POST http://localhost:8080/recommend \
    -H 'content-type: application/json' \
    -d '{"work_ids":["/works/OL10000266W"],"limit":5}'

curl -s 'http://localhost:8080/search?q=gatsby&entity=book&limit=8'

curl -s 'http://localhost:8080/map/points?entity=book&z=6&x0=-0.5&y0=-0.5&x1=0.5&y1=0.5'
```

Work ids start with a slash and must be URL-encoded in path segments. All vector computation happens in Postgres through pgvector.

## Frontend

```bash
make frontend-install

make frontend-dev      # dev server, proxies /api to the backend

make frontend-build

make frontend-lint
```

## Tests

```bash
make test           # ETL unit tests
make backend-test   # backend tests, needs DATABASE_URL
```

## Docker

```bash
make db-up      # Postgres with pgvector from infra/docker-compose.yml
make db-down
```
