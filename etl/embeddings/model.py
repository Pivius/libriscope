import os
from typing import List, Optional

import requests


class OllamaEmbedder:
	"""Client for Ollama's local /api/embed endpoint."""

	def __init__(self, host: Optional[str] = None, model_name: Optional[str] = None,
			timeout: float = 120.0, num_ctx: Optional[int] = None) -> None:
		from etl.core.config import load_env
		load_env()
		self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
		self.model_name = model_name or os.environ.get("EMBEDDINGS_MODEL", "mxbai-embed-large")
		self.timeout = timeout
		self.num_ctx = num_ctx or int(os.environ.get("EMBED_CONTEXT_LENGTH", "512") or 512)
		self._dimension: Optional[int] = None

	@property
	def dimension(self) -> int:
		if self._dimension is None:
			# probe with a single token to learn the vector width
			vec = self.encode(["probe"], batch_size=1)[0]
			self._dimension = len(vec)
		return self._dimension

	def encode(self, texts: List[str], *, batch_size: int = 32, normalize: bool = True, show_progress_bar: bool = False) -> List[List[float]]:
		"""Encode a list of texts, returning a list of vectors (each a list of floats)."""
		if not texts:
			return []

		all_vectors: List[List[float]] = []
		for i in range(0, len(texts), batch_size):
			chunk = list(texts[i:i + batch_size])
			payload = {
				"model": self.model_name,
				"input": chunk,
				"options": {"num_ctx": self.num_ctx},
			}
			resp = requests.post(f"{self.host}/api/embed", json=payload, timeout=self.timeout)
			resp.raise_for_status()
			data = resp.json()
			raw_vectors = data.get("embeddings") or []
			for vec in raw_vectors:
				if normalize and vec:
					norm = sum(v * v for v in vec) ** 0.5
					if norm > 0:
						vec = [v / norm for v in vec]
				all_vectors.append(list(vec))

		return all_vectors

	def ping(self) -> bool:
		"""Return True if Ollama is reachable and the model is available."""
		try:
			resp = requests.get(f"{self.host}/api/tags", timeout=5.0)
			resp.raise_for_status()
			models = [m.get("name", "") for m in (resp.json().get("models") or [])]
			return any(self.model_name in name for name in models)
		except Exception:
			return False


_embedder: Optional[OllamaEmbedder] = None


def get_model() -> OllamaEmbedder:
	global _embedder
	if _embedder is None:
		_embedder = OllamaEmbedder()
	return _embedder
