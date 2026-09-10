import os
from typing import List, Optional


class SentenceTransformerEmbedder:
	"""In-process embedding via sentence-transformers running on local GPU/CPU.

	The ETL encodes the *corpus* side of the search (works metadata), so no query
	instruction prefix is applied (that only matters for queries at search time).
	"""

	def __init__(self, model_name: Optional[str] = None, batch_size: int = 64) -> None:
		from etl.core.config import load_env
		load_env()
		self.model_name = model_name or os.environ.get("EMBEDDINGS_MODEL", "BAAI/bge-base-en-v1.5")
		self.batch_size = batch_size or int(os.environ.get("EMBED_BATCH_SIZE", "64") or 64)
		self.model_id = f"sentence-transformers/{self.model_name}"
		self._model = None
		self._dimension: Optional[int] = None

	def _get_sentence_transformer(self):
		if self._model is None:
			from sentence_transformers import SentenceTransformer
			self._model = SentenceTransformer(self.model_name)
		return self._model

	@property
	def dimension(self) -> int:
		if self._dimension is None:
			model = self._get_sentence_transformer()
			getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
			self._dimension = getter()
		return int(self._dimension)

	def encode(self, texts: List[str], *, batch_size: int = 64, normalize: bool = True,
			show_progress_bar: bool = False) -> List[List[float]]:
		"""Encode a list of texts, returning a list of vectors (each a list of floats)."""
		if not texts:
			return []

		vectors = self._get_sentence_transformer().encode(
			texts,
			batch_size=batch_size or self.batch_size,
			normalize_embeddings=normalize,
			show_progress_bar=show_progress_bar,
			convert_to_numpy=True,
		)
		return [list(map(float, vec)) for vec in vectors]

	def ping(self) -> bool:
		"""Return True if the embedding model can be loaded."""
		try:
			self._get_sentence_transformer()
			return True
		except Exception:
			return False


_embedder: Optional[SentenceTransformerEmbedder] = None


def get_model() -> SentenceTransformerEmbedder:
	global _embedder
	if _embedder is None:
		_embedder = SentenceTransformerEmbedder()
	return _embedder