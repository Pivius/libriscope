from typing import Iterable, Optional

from tqdm import tqdm

from etl.adapters.ol_adapter import OpenLibraryCSVAdapter
from etl.core.text_builder import build_text
from etl.embeddings.batch import iter_batches


def run_pipeline(
	processed_dir: str,
	enabled: Optional[Iterable[str]] = None,
	batch_size: int = 32,
	write_db: bool = True,
	write_embeddings: bool = True,
	database_url: Optional[str] = None,
	max_aux: Optional[int] = 500000,
	max_works: Optional[int] = None,
	skip_existing: bool = True,
	reset_db: bool = False,
) -> int:
	"""Collate raw TSV CSVs, build embedding text, embed, and (optionally) write to DB.

	Returns the number of newly processed CanonicalItems.
	"""
	adapter = OpenLibraryCSVAdapter()

	store = None
	model = None
	if write_db or write_embeddings:
		from etl.embeddings.store import EmbeddingStore
		store = EmbeddingStore(database_url)
	if write_embeddings:
		from etl.embeddings.model import get_model
		model = get_model()
		store.prepare_embedding_model(model.model_name, model.dimension)
		print(f"Embedder: {model.model_name} (dim {model.dimension}, num_ctx {model.num_ctx}) via {model.host}", flush=True)

	if reset_db:
		if store is None:
			raise RuntimeError("reset_db requires a database store (write_db or write_embeddings)")
		print("Resetting database: truncating all tables ...", flush=True)
		store.clear_all()

	existing = set()
	if skip_existing:
		if store is not None:
			existing = store.existing_work_ids()
			if existing:
				print(f"Resuming: {len(existing):,} work(s) already embedded, skipping", flush=True)
		else:
			print("Note: skip_existing enabled but no store available; nothing to skip", flush=True)

	count = 0
	skipped = 0
	items = adapter.collate_from_dir(processed_dir, enabled=enabled, max_aux=max_aux)

	bar = tqdm(desc="ETL", unit="batch", ncols=100)
	try:
		for ids, batch in iter_batches(items, batch_size):
			if max_works is not None and count >= max_works:
				break
			items_out = []
			ids_out = []
			for id_, item in zip(ids, batch):
				if item.id in existing:
					skipped += 1
					continue
				if max_works is not None and count + len(items_out) >= max_works:
					break
				ids_out.append(id_)
				items_out.append(item)
			if not items_out:
				continue

			vectors = None
			if model is not None:
				texts = [build_text(item) for item in items_out]
				vectors = model.encode(texts, batch_size=batch_size)

			if store is not None:
				ids_to_vec = {}
				if vectors is not None:
					for id_, vec in zip(ids_out, vectors):
						ids_to_vec[id_] = vec
				if write_db:
					store.bulk_upsert(items_out, ids_to_vec)
				elif vectors is not None:
					for id_, vec in zip(ids_out, vectors):
						store.upsert_embedding(id_, vec)

			count += len(items_out)
			bar.update(1)
			bar.set_postfix_str(f"{count:,} new / {skipped:,} skipped")
	finally:
		bar.close()
	return count
