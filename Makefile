PYTHON ?= python
PIP ?= pip
PYTEST ?= pytest
CARGO ?= cargo

.PHONY: help install test etl process-data rebuild-embeddings author-embeddings map-coords axis-labels db-up db-down db-init db-clear inspect model-check backend-build backend-run backend-test frontend-install frontend-dev frontend-build frontend-lint

help:
	@echo "Available targets:"
	@echo "  install              Install ETL Python dependencies"
	@echo "  test                 Run unit tests"
	@echo "  process-data         Process raw OpenLibrary dumps into CSVs"
	@echo "  etl                  Run OpenLibrary ingest (ARGS=\"--max-works N [--reset|--skip-editions]\"). Defaults to continuing where you left off"
	@echo "  rebuild-embeddings   Recompute embeddings only"
	@echo "  author-embeddings    Build author embeddings from work embeddings"
	@echo "  map-coords           Compute 2D PCA map coordinates (books + authors)"
	@echo "  axis-labels          Regenerate frontend/public/axis-labels.json quadrant labels (ARGS=--out FILE)"
	@echo "  db-init              Apply infra/init.sql schema"
	@echo "  db-clear             Truncate all data tables (keeps schema)"
	@echo "  inspect              Inspect a gz dump (FILE=<file>)"
	@echo "  db-up / db-down      Manage local Postgres via docker-compose"
	@echo "  model-check          Load/verify the sentence-transformers embedding model (downloads on first run)"
	@echo "  backend-build        Build the Rust backend"
	@echo "  backend-run          Run the Rust backend (cargo run)"
	@echo "  backend-test         Run Rust backend tests"
	@echo "  frontend-install     Install frontend dependencies"
	@echo "  frontend-dev         Run the Next.js dev server"
	@echo "  frontend-build       Build the Next.js app"
	@echo "  frontend-lint        Lint the Next.js app"

install:
	$(PIP) install -r etl/requirements.txt

test:
	$(PYTEST) -q

etl:
	$(PYTHON) -m etl.jobs.run_openlibrary $(ARGS)

process-data:
	$(PYTHON) data/openlibrary_data_process.py $(ARGS)

rebuild-embeddings:
	$(PYTHON) -m etl.jobs.rebuild_embeddings

author-embeddings:
	$(PYTHON) -m etl.jobs.run_author_embeddings

map-coords:
	$(PYTHON) -m etl.jobs.run_map_coords

axis-labels:
	$(PYTHON) -m etl.jobs.run_axis_labels $(ARGS)

db-init:
	psql "$(DATABASE_URL)" -f infra/init.sql

db-clear:
	psql "$(DATABASE_URL)" -c "TRUNCATE TABLE works, work_embeddings, ratings, authors, map_coords CASCADE;"

inspect:
	$(PYTHON) scripts/inspect_gz_json.py "$(PATH)" --show-keys

db-up:
	docker compose -f infra/docker-compose.yml up -d db

db-down:
	docker compose -f infra/docker-compose.yml down

model-check:
	$(PYTHON) -c "from etl.embeddings.model import get_model; m = get_model(); print(f'Embedding model {m.model_name} ready (dim {m.dimension})')"

backend-build:
	$(CARGO) build --manifest-path backend/Cargo.toml

backend-run:
	$(CARGO) run --manifest-path backend/Cargo.toml

backend-test:
	$(CARGO) test --manifest-path backend/Cargo.toml

frontend-install:
	npm --prefix frontend install

frontend-dev:
	npm --prefix frontend run dev

frontend-build:
	npm --prefix frontend run build

frontend-lint:
	npm --prefix frontend run lint
