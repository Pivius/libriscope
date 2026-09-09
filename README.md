# Libriscope

A semantic literature discovery system that recommends books based on meaning, themes and tone, rather than

The goal of this project is to explore how vector databases and semantic similarity can be used to recommend literature based on meaning, themes, tone, and reader preference, rather than simple genre matching.

Download the latest database dump OpenLibrary ingest scripts [here](https://openlibrary.org/developers/dumps).

---

## Build

Make commands are provided to coordinate the ETL, backend and frontend.

```
make install			# Install ETL dependencies
make db-init			# Apply database schema
make etl				# Run ingest (raw -> embeddings -> DB)
make backend-build		# Build Rust API
make backend-run		# Run Rust API
make frontend-dev		# Start frontend dev server
```

Set `DATABASE_URL` and `EMBEDDINGS_MODEL` in your `.env` file

---

## Use

Libriscope exposes a simple REST API in Rust and pgvector for low-latency similarity queries:

```bash
# Get similarity-based recommendations for a work
curl -X POST http://localhost:8080/recommend \
	-H "Content-Type: application/json" \
	-d '{"work_id": "OL45883W", "limit": 5}'

# Inspect a raw OpenLibrary dump file
make inspect FILE=data/ol_dump_works.txt.gz
```

---

## Data Architecture

The pipeline consists of four stages:
- ETL: Parses raw OpenLibrary dumps (works, authors, editions), normalizes metadata and sends chunks to Ollama to generate vector embeddings.
- Database: A PostgreSQL + pgvector database that persists entity models alongside high-dimensional vector embeddings with HNSW indexing for cos-dist queries.
- Backend: API handling vector search, metadata filtering and result aggregation.
- Frontend: Visual client for browsing 2D projections and semantic recommendations

---

See [docs/deployment.md](docs/deployment.md) for full details.
