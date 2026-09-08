import os
from typing import Any, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from etl.core.canonical import CanonicalItem


class EmbeddingStore:
	"""Write CanonicalItems + embeddings into Postgres (pgvector)."""

	def __init__(self, database_url: Optional[str] = None) -> None:
		url = database_url or os.environ.get("DATABASE_URL")
		if not url:
			raise RuntimeError("DATABASE_URL is not set")
		if url.startswith("postgresql+psycopg2"):
			url = url  # keep psycopg2 scheme as-is
		self.engine: Engine = create_engine(url)

	def _embedding_literal(self, vector) -> str:
		return "[" + ",".join(str(float(x)) for x in vector) + "]"

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
