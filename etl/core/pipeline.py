import os
from queue import Queue
from threading import Thread
from typing import Dict, Iterable, List, Optional, Tuple

from tqdm import tqdm

from etl.adapters.ol_adapter import OpenLibraryCSVAdapter
from etl.core.text_builder import build_text
from etl.embeddings.batch import iter_batches

_QUEUE_SIZE = 4
_WRITER_BATCH = 2000
_SENTINEL = object()

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
	embed_batch_size: Optional[int] = None,
	max_seq_length: Optional[int] = None,
) -> int:
	"""Raw TSV CSVs are collated, embedding text is built, and items are embedded, with optional writing to a database.

		It runs as a 3-stage pipeline with threads.

		1. Reader thread, streams/parses the CSV dumps, applies the
			skip-existing and max_works filtering, then builds embedding text and enqueues
			chunks of specified embed_batch_size or the model's batch size.
		2. Main thread, owns the FP16 model and encodes as fast as it
			will go and enqueues the IDs, items, and vectors for each chunk.
		3. Writer thread, accumulates vectors across chunks and flushes via
			bulk_upsert in large batches to reduce the number of database round trips.

		While embeddings are running, the work_embeddings HNSW index is temporarily dropped 
		for the duration of the load, and it's recreated at the end, avoiding per-insert index cost.
		Set ``ETL_SERIAL=1`` to fall back to a single-threaded loop.

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

		assert store is not None
		if embed_batch_size is not None:
			model.batch_size = embed_batch_size
		if max_seq_length is not None:
			model.max_seq_length = max_seq_length

		store.prepare_embedding_model(model.model_name, model.dimension)
		print(f"Embedder: {model.model_name} (dim {model.dimension}) via sentence-transformers", flush=True)

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

	chunk_size = batch_size

	if model is not None:
		chunk_size = embed_batch_size if embed_batch_size is not None else model.batch_size

	if store is None or os.environ.get("ETL_SERIAL") == "1":
		return _run_serial(adapter, store, model, processed_dir, enabled, max_aux, chunk_size,
			existing, max_works, write_db)
	return _run_parallel(adapter, store, model, processed_dir, enabled, max_aux,
		chunk_size, existing, max_works, write_db)


def _read_worker(adapter, processed_dir: str, enabled, max_aux, chunk_size: int,
		existing: set, max_works: Optional[int], in_q: Queue, result: Dict) -> None:
	"""Stream/parse, filter, build text, and queue chunks. Ends with a sentinel."""
	count = 0
	skipped = 0

	try:
		items = adapter.collate_from_dir(processed_dir, enabled=enabled, max_aux=max_aux)

		for ids, batch in iter_batches(items, chunk_size):
			if max_works is not None and count >= max_works:
				break

			ids_out: List[str] = []
			items_out: List = []

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

			texts = [build_text(item) for item in items_out]
			in_q.put((ids_out, texts, items_out))
			count += len(items_out)
			result["count"] = count
			result["skipped"] = skipped
	except BaseException as exc:
		result["exc"] = exc
	finally:
		in_q.put(_SENTINEL)
		result["count"] = count
		result["skipped"] = skipped


def _write_flush(store, items: List, vectors: List, write_db: bool) -> None:
	if write_db:
		store.bulk_upsert(items, dict(vectors), batch_size=max(_WRITER_BATCH, len(items)))
	else:
		for id_, vec in vectors:
			store.upsert_embedding(id_, vec)


def _write_worker(store, out_q: Queue, write_db: bool, result: Dict) -> None:
	"""Consume ids, items and vector chunks, flushing in large batches."""
	failed = False
	acc_items: List = []
	acc_vectors: List = []

	while True:
		payload = out_q.get()

		if payload is _SENTINEL:
			break

		ids, items, vectors = payload
		acc_items.extend(items)

		if vectors is not None:
			acc_vectors.extend(zip(ids, vectors))
		if len(acc_items) >= _WRITER_BATCH:
			if not failed:
				try:
					_write_flush(store, acc_items, acc_vectors, write_db)
				except BaseException as exc:
					failed = True
					result["exc"] = exc

			acc_items = []
			acc_vectors = []
	if not failed and acc_items:
		try:
			_write_flush(store, acc_items, acc_vectors, write_db)
		except BaseException as exc:
			result["exc"] = exc


def _run_parallel(adapter, store, model, processed_dir: str, enabled,
		max_aux, chunk_size: int, existing: set, max_works: Optional[int],
		write_db: bool) -> int:
	in_q: Queue = Queue(maxsize=_QUEUE_SIZE)
	out_q: Queue = Queue(maxsize=_QUEUE_SIZE)
	read_result: Dict = {"count": 0, "skipped": 0}
	write_result: Dict = {}
	read_worker = Thread(
		target=_read_worker,
		kwargs={"adapter": adapter, "processed_dir": processed_dir, "enabled": enabled,
			"max_aux": max_aux, "chunk_size": chunk_size, "existing": existing,
			"max_works": max_works, "in_q": in_q, "result": read_result},
		daemon=True,
	)
	write_worker = Thread(
		target=_write_worker,
		kwargs={"store": store, "out_q": out_q, "write_db": write_db, "result": write_result},
		daemon=True,
	)

	out_ended = False
	bar = tqdm(desc="ETL", unit="batch", ncols=100)

	try:
		if model is not None:
			print("Dropping HNSW index for bulk insert (recreated when done)...", flush=True)
			store.drop_embedding_index()

		read_worker.start()
		write_worker.start()

		while True:
			payload = in_q.get()

			if payload is _SENTINEL:
				break

			ids, texts, items = payload
			vectors = None

			if model is not None:
				vectors = model.encode(texts, batch_size=chunk_size)

			out_q.put((ids, items, vectors))
			bar.update(1)
			bar.set_postfix_str(f"{read_result['count']:,} new / {read_result['skipped']:,} skipped")

		read_worker.join()
		out_q.put(_SENTINEL)
		out_ended = True
		write_worker.join()

		for result, name in ((read_result, "reader"), (write_result, "writer")):
			if result.get("exc") is not None:
				raise RuntimeError(f"pipeline {name} thread failed") from result["exc"]
	finally:
		bar.close()

		if not out_ended:
			try:
				out_q.put(_SENTINEL)
			except Exception:
				pass

			write_worker.join(timeout=60)
			read_worker.join(timeout=5)
		if model is not None:
			print("Recreating HNSW index ...", flush=True)
			store.create_embedding_index()
	return read_result["count"]


def _run_serial(adapter, store, model, processed_dir: str, enabled,
		max_aux, chunk_size: int, existing: set, max_works: Optional[int], write_db: bool) -> int:
	"""Single-threaded fallback loop.
		
		ETL_SERIAL=1 or no store
	"""
	count = 0
	skipped = 0
	items = adapter.collate_from_dir(processed_dir, enabled=enabled, max_aux=max_aux)
	bar = tqdm(desc="ETL", unit="batch", ncols=100)

	try:
		if model is not None and store is not None:
			print("Dropping HNSW index for bulk insert (recreated when done)...", flush=True)
			store.drop_embedding_index()

		for ids, batch in iter_batches(items, chunk_size):
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
				vectors = model.encode(texts, batch_size=chunk_size)

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
		
		if model is not None and store is not None:
			print("Recreating HNSW index ...", flush=True)
			store.create_embedding_index()
	return count