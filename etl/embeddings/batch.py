from typing import Iterable, Iterator, List, Tuple

from etl.core.canonical import CanonicalItem


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
