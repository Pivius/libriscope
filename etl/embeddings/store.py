import os
from typing import Any, Iterable, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from etl.core.canonical import CanonicalItem
from etl.core.config import load_env


class EmbeddingStore:
	"""Write CanonicalItems + embeddings into Postgres (pgvector)."""

	def __init__(self, database_url: Optional[str] = None) -> None:
		load_env()
		url = database_url or os.environ.get("DATABASE_URL")
		if not url:
			raise RuntimeError("DATABASE_URL is not set")
		if url.startswith("postgresql+psycopg2"):
			url = url  # keep psycopg2 scheme as-is
		self.engine: Engine = create_engine(url)

	def _embedding_literal(self, vector) -> str:
		return "[" + ",".join(str(float(x)) for x in vector) + "]"

	def embedding_dimension(self) -> int:
		"""Read the configured VECTOR(n) width from the work_embeddings table.

			pgvector stores the dimension directly in the column's atttypmod
			(e.g. vector(768) -> atttypmod = 768).
		"""
		with self.engine.connect() as conn:
			row = conn.execute(text(
				"SELECT a.atttypmod "
				"FROM pg_attribute a "
				"JOIN pg_class c ON c.oid = a.attrelid "
				"JOIN pg_namespace n ON n.oid = c.relnamespace "
				"WHERE n.nspname = 'public' AND c.relname = 'work_embeddings' "
				"AND a.attname = 'embedding'"
			)).first()
		if row is None or row[0] is None or row[0] < 0:
			raise RuntimeError("work_embeddings.embedding column has no fixed vector dimension")
		return int(row[0])

	def _ensure_meta_table(self) -> None:
		"""Create pipeline_meta if missing (pre-existing DBs not updated via db-init)."""
		with self.engine.begin() as conn:
			conn.execute(text(
				"CREATE TABLE IF NOT EXISTS pipeline_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
			))

	def get_meta(self, key: str) -> Optional[str]:
		"""Read a key from the pipeline_meta table (or None)."""
		self._ensure_meta_table()
		with self.engine.connect() as conn:
			row = conn.execute(text(
				"SELECT value FROM pipeline_meta WHERE key = :key"
			), {"key": key}).first()
		return row[0] if row else None

	def set_meta(self, key: str, value: str) -> None:
		sql = text("""
			INSERT INTO pipeline_meta (key, value) VALUES (:key, :value)
			ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
		""")
		with self.engine.begin() as conn:
			conn.execute(sql, {"key": key, "value": value})

	def _migrate_embedding_dimension(self, target_dim: int) -> None:
		"""Resize work_embeddings.embedding and authors.embedding to VECTOR(target_dim)."""
		print(f"Resizing embedding columns to VECTOR({target_dim}) ...", flush=True)
		d = int(target_dim)
		with self.engine.begin() as conn:
			conn.execute(text("DROP INDEX IF EXISTS idx_work_embeddings_vector"))
			conn.execute(text("DROP INDEX IF EXISTS idx_authors_embedding"))
			conn.execute(text(
				f"ALTER TABLE work_embeddings ALTER COLUMN embedding TYPE VECTOR({d}) "
				f"USING embedding::vector({d})"
			))
			conn.execute(text(
				f"ALTER TABLE authors ALTER COLUMN embedding TYPE VECTOR({d}) "
				f"USING embedding::vector({d})"
			))
			conn.execute(text("CREATE INDEX idx_work_embeddings_vector ON work_embeddings USING hnsw (embedding vector_cosine_ops)"))
			conn.execute(text("CREATE INDEX idx_authors_embedding ON authors USING hnsw (embedding vector_cosine_ops)"))

	def prepare_embedding_model(self, model_name: str, target_dim: int) -> None:
		"""Make the schema match the active embedder.

		- Clears stale embeddings (work_embeddings, authors, map_coords) when the model
			changed versus the one recorded in pipeline_meta.
		- Resizes the embedding columns afterwards when the model's dimension differs
			(on an empty table, so the cast can never fail).

		Safe to call on every ETL run; a no-op when nothing changed.
		"""
		stored = self.get_meta("embedding_model")
		model_changed = stored != model_name
		dim_changed = self.embedding_dimension() != target_dim
		if not model_changed and not dim_changed:
			return

		if model_changed:
			if stored is not None:
				print(
					f"Embedding model changed ({stored} -> {model_name}): clearing stale "
					f"embeddings/authors/map_coords. Re-run after this to re-embed everything.",
					flush=True,
				)
			else:
				print(f"Recording embedding model '{model_name}' in pipeline_meta.", flush=True)
		else:
			print(f"Resizing embedding dimension {self.embedding_dimension()} -> {target_dim}; clearing existing vectors.", flush=True)
		with self.engine.begin() as conn:
			conn.execute(text("TRUNCATE TABLE work_embeddings, authors CASCADE"))
			conn.execute(text("DELETE FROM map_coords"))

		if dim_changed:
			self._migrate_embedding_dimension(target_dim)
		self.set_meta("embedding_model", model_name)
		print("Schema is ready for the embedding model.", flush=True)

	def clear_all(self) -> None:
		"""Truncate every data table, leaving the schema in place."""
		with self.engine.begin() as conn:
			conn.execute(text(
				"TRUNCATE TABLE works, work_embeddings, ratings, authors, map_coords CASCADE"
			))

	def existing_work_ids(self) -> set:
		"""Return the set of work_ids that already have embeddings (for resume/continue)."""
		with self.engine.connect() as conn:
			rows = conn.execute(text("SELECT work_id FROM work_embeddings"))
			return {r[0] for r in rows}

	def upsert_work(self, item: CanonicalItem) -> None:
		sql = text("""
			INSERT INTO works (id, title, subtitle, description, first_sentence, subjects, genres, authors, languages, first_publish_date, series, source)
			VALUES (:id, :title, :subtitle, :description, :first_sentence, :subjects, :genres, :authors, :languages, :first_publish_date, :series, 'openlibrary')
			ON CONFLICT (id) DO UPDATE SET
				title = EXCLUDED.title,
				subtitle = EXCLUDED.subtitle,
				description = EXCLUDED.description,
				first_sentence = EXCLUDED.first_sentence,
				subjects = EXCLUDED.subjects,
				genres = EXCLUDED.genres,
				authors = EXCLUDED.authors,
				languages = EXCLUDED.languages,
				first_publish_date = EXCLUDED.first_publish_date,
				series = EXCLUDED.series
		""")
		params = {
			"id": item.id,
			"title": item.title,
			"subtitle": item.subtitle,
			"description": item.description,
			"first_sentence": item.first_sentence,
			"subjects": list(item.subjects),
			"genres": list(item.genres),
			"authors": list(item.authors),
			"languages": list(item.languages),
			"first_publish_date": item.first_publish_date,
			"series": list(item.series),
		}
		with self.engine.begin() as conn:
			conn.execute(sql, params)

	def upsert_embedding(self, work_id: str, vector) -> None:
		sql = text("""
			INSERT INTO work_embeddings (work_id, embedding)
			VALUES (:work_id, :embedding)
			ON CONFLICT (work_id) DO UPDATE SET embedding = EXCLUDED.embedding
		""")
		with self.engine.begin() as conn:
			conn.execute(sql, {"work_id": work_id, "embedding": self._embedding_literal(vector)})

	def bulk_upsert(self, items: Iterable[CanonicalItem], ids_to_vectors, batch_size: int = 500) -> None:
		"""Write many items + their (id -> vector) pairs efficiently."""
		work_sql = text("""
			INSERT INTO works (id, title, subtitle, description, first_sentence, subjects, genres, authors, languages, first_publish_date, series, source)
			VALUES (:id, :title, :subtitle, :description, :first_sentence, :subjects, :genres, :authors, :languages, :first_publish_date, :series, 'openlibrary')
			ON CONFLICT (id) DO UPDATE SET
				title = EXCLUDED.title,
				subtitle = EXCLUDED.subtitle,
				description = EXCLUDED.description,
				first_sentence = EXCLUDED.first_sentence,
				subjects = EXCLUDED.subjects,
				genres = EXCLUDED.genres,
				authors = EXCLUDED.authors,
				languages = EXCLUDED.languages,
				first_publish_date = EXCLUDED.first_publish_date,
				series = EXCLUDED.series
		""")
		emb_sql = text("""
			INSERT INTO work_embeddings (work_id, embedding)
			VALUES (:work_id, :embedding)
			ON CONFLICT (work_id) DO UPDATE SET embedding = EXCLUDED.embedding
		""")

		def _work_params(item: CanonicalItem) -> dict:
			return {
				"id": item.id,
				"title": item.title,
				"subtitle": item.subtitle,
				"description": item.description,
				"first_sentence": item.first_sentence,
				"subjects": list(item.subjects),
				"genres": list(item.genres),
				"authors": list(item.authors),
				"languages": list(item.languages),
				"first_publish_date": item.first_publish_date,
				"series": list(item.series),
			}

		with self.engine.begin() as conn:
			work_rows = []
			emb_rows = []
			for item in items:
				work_rows.append(_work_params(item))
				vec = ids_to_vectors.get(item.id)
				if vec is not None:
					emb_rows.append({"work_id": item.id, "embedding": self._embedding_literal(vec)})
				if len(work_rows) >= batch_size:
					conn.execute(work_sql, work_rows)
					work_rows = []
				if len(emb_rows) >= batch_size:
					conn.execute(emb_sql, emb_rows)
					emb_rows = []
			if work_rows:
				conn.execute(work_sql, work_rows)
			if emb_rows:
				conn.execute(emb_sql, emb_rows)
