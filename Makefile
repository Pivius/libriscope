PYTHON ?= python
PIP ?= pip
PYTEST ?= pytest

.PHONY: help install test etl rebuild-embeddings db-up db-down db-init inspect ollama-pull ollama-check

help:
	@echo "Available targets:"
	@echo "  install              Install ETL Python dependencies"
	@echo "  test                 Run unit tests"
	@echo "  etl                  Run full OpenLibrary ingest (raw -> embed -> DB)"
	@echo "  rebuild-embeddings   Recompute embeddings only"
	@echo "  db-init              Apply infra/init.sql schema"
	@echo "  inspect              Inspect a gz dump (PATH=<file>)"
	@echo "  db-up / db-down      Manage local Postgres via docker-compose"
	@echo "  ollama-pull          Download the embedding model into Ollama"
	@echo "  ollama-check         Verify Ollama + embedding model are reachable"

install:
	$(PIP) install -r etl/requirements.txt

test:
	PYTHONPATH=. $(PYTEST) -q

etl:
	PYTHONPATH=. $(PYTHON) -m etl.jobs.run_openlibrary

rebuild-embeddings:
	PYTHONPATH=. $(PYTHON) -m etl.jobs.rebuild_embeddings

db-init:
	psql "$(DATABASE_URL)" -f infra/init.sql

inspect:
	$(PYTHON) scripts/inspect_gz_json.py "$(PATH)" --show-keys

db-up:
	docker compose -f infra/docker-compose.yml up -d db

db-down:
	docker compose -f infra/docker-compose.yml down

ollama-pull:
	ollama pull $(EMBEDDINGS_MODEL)

ollama-check:
	PYTHONPATH=. $(PYTHON) -c "from etl.embeddings.model import get_model; ok = get_model().ping(); print('Ollama reachable and model available' if ok else 'Ollama unreachable or model missing'); exit(0 if ok else 1)"
