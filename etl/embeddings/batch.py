from typing import Iterable, Iterator, List, Tuple, Any
from etl.core.canonical import CanonicalItem
from etl.core.text_builder import build_text


def iter_batches(items: Iterable[CanonicalItem], batch_size: int) -> Iterator[Tuple[List[str], List[CanonicalItem]]]:
	"""Yield (ids, items) batches sized by batch_size."""
	ids: List[str] = []
	batch: List[CanonicalItem] = []
	for item in items:
		ids.append(item.id)
		batch.append(item)
		if len(batch) >= batch_size:
			yield ids, batch
			ids = []
			batch = []
	if batch:
		yield ids, batch


def embed_stream(items: Iterable[CanonicalItem], model, batch_size: int = 32, show_progress: bool = False) -> Iterator[Tuple[str, Any]]:
	"""Encode items in batches, yielding (id, embedding_vector)."""
	for ids, batch in iter_batches(items, batch_size):
		texts = [build_text(item) for item in batch]
		vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=show_progress)
		for id_, vec in zip(ids, vectors):
			yield id_, vec
