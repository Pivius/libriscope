import os
from typing import List, Optional


class SentenceTransformerEmbedder:
	"""In-process embedding via sentence-transformers running on local GPU/CPU.

		The ETL encodes the *corpus* side of the search (works metadata), so no query
		instruction prefix is applied (that only matters for queries at search time).

		On CUDA the model is loaded in FP16 (halves memory use and roughly doubles
		throughput on Turing+ GPUs). Batch sizes default to larger than the ETL
		write batch so the GPU stays saturated.
	"""

	DEFAULT_MODEL = "all-MiniLM-L6-v2"
	DEFAULT_BATCH_SIZE = 192
	DEFAULT_MAX_SEQ_LENGTH = 512

	def __init__(self, model_name: Optional[str] = None, batch_size: int = DEFAULT_BATCH_SIZE,
			max_seq_length: Optional[int] = None) -> None:

		from etl.core.config import load_env
		load_env()

		self.model_name = model_name or os.environ.get("EMBEDDINGS_MODEL", self.DEFAULT_MODEL)
		self.batch_size = batch_size or int(os.environ.get("EMBED_BATCH_SIZE", self.DEFAULT_BATCH_SIZE) or self.DEFAULT_BATCH_SIZE)
		raw_seq = max_seq_length if max_seq_length is not None else os.environ.get("EMBED_MAX_SEQ_LENGTH")
		self.max_seq_length = int(raw_seq) if raw_seq not in (None, "") else self.DEFAULT_MAX_SEQ_LENGTH
		self.model_id = f"sentence-transformers/{self.model_name}"
		self._model = None
		self._dimension: Optional[int] = None

	def _get_sentence_transformer(self):
		if self._model is None:
			import torch 
			from sentence_transformers import SentenceTransformer

			torch.backends.cudnn.benchmark = True
			model_kwargs = {"torch_dtype": torch.float16} if torch.cuda.is_available() else {}
			self._model = SentenceTransformer(self.model_name, model_kwargs=model_kwargs)

			if torch.cuda.is_available():
				self._model = self._model.to("cuda")
			if self.max_seq_length and self.max_seq_length != self._model.max_seq_length:
				self._model.max_seq_length = self.max_seq_length
			self._model.eval()

		return self._model

	@property
	def dimension(self) -> int:
		if self._dimension is None:
			model = self._get_sentence_transformer()
			getter = getattr(
				model,
				"get_embedding_dimension",
				getattr(model, "get_sentence_embedding_dimension", None),
			)
			if getter is None:
				raise AttributeError("Model does not expose an embedding dimension method")

			dim = getter()
			self._dimension = int(dim)

		return self._dimension

	def encode(self, texts: List[str], *, batch_size: Optional[int] = None, normalize: bool = True,
			show_progress_bar: bool = False):
		"""Encode a list of texts, returning an (n, dim) float32 numpy array.

			Empty input returns an empty list.
		"""
		if not texts:
			return []

		import torch

		model = self._get_sentence_transformer()
		with torch.inference_mode():
			vectors = model.encode(
				texts,
				batch_size=batch_size or self.batch_size,
				normalize_embeddings=normalize,
				show_progress_bar=show_progress_bar,
				convert_to_numpy=True,
			)
		return vectors

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