import os
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from etl.recommend.similarity import mean


class SimilarityStore:
	"""Query precomputed vectors for nearest-neighbor recommendations."""

	def __init__(self, database_url: Optional[str] = None) -> None:
		from etl.core.config import load_env
		load_env()
		url = database_url or os.environ.get("DATABASE_URL")
		if not url:
			raise RuntimeError("DATABASE_URL is not set")
		self.engine: Engine = create_engine(url)

	def _literal(self, vec: Sequence[float]) -> str:
		return "[" + ",".join(str(float(x)) for x in vec) + "]"

	def get_vectors(self, work_ids: Sequence[str]) -> Dict[str, List[float]]:
		"""Return {work_id: vector} for the ids that have embeddings."""
		if not work_ids:
			return {}
		sql = text("""
			SELECT work_id, embedding::text
			FROM work_embeddings
			WHERE work_id = ANY(:ids)
		""")
		out: Dict[str, List[float]] = {}
		with self.engine.connect() as conn:
			rows = conn.execute(sql, {"ids": list(work_ids)}).fetchall()
			for work_id, emb_text in rows:
				inner = emb_text.strip("[]")
				if not inner:
					continue
				out[work_id] = [float(x) for x in inner.split(",")]
		return out

	def recommend(
		self,
		work_ids: Sequence[str],
		limit: int = 10,
		exclude: Optional[Sequence[str]] = None,
	) -> List[Tuple[str, float]]:
		"""Return ranked [(work_id, cosine_similarity)] similar to the input set.

		Builds the centroid of the input works' embeddings and runs a cosine
		kNN query, excluding the inputs themselves.
		"""
		vectors = self.get_vectors(work_ids)
		if not vectors:
			return []

		centroid = mean(list(vectors.values()))
		exclude_set = set(work_ids)
		if exclude:
			exclude_set.update(exclude)

		sql = text("""
			SELECT w.id, 1 - (we.embedding <=> :q) AS similarity
			FROM work_embeddings we
			JOIN works w ON w.id = we.work_id
			WHERE NOT (we.work_id = ANY(:exclude))
			ORDER BY we.embedding <=> :q
			LIMIT :limit
		""")
		with self.engine.connect() as conn:
			rows = conn.execute(
				sql,
				{
					"q": self._literal(centroid),
					"exclude": list(exclude_set),
					"limit": limit,
				},
			).fetchall()
		return [(r[0], float(r[1])) for r in rows]
