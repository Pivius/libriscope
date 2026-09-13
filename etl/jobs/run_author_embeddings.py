import argparse
import gzip
import json
import os
import time
from typing import Dict, List, Optional, Set

import numpy as np
from sqlalchemy import create_engine, text
from tqdm import tqdm

from etl.core import progress
from etl.core.config import load_env

_STREAM_CHUNK = 2000
_WRITE_CHUNK = 50000


def _parse_vector(emb_text: str) -> Optional[np.ndarray]:
	"""Parse a pgvector text literal into a float32 numpy array or None."""
	inner = emb_text.strip("[]")
	if not inner:
		return None
	return np.array(inner.split(","), dtype=np.float32)


def _embedding_literal(vec: np.ndarray) -> str:
	return str(vec.tolist())


def load_author_names(dump_path: str, needed: Set[str]) -> Dict[str, str]:
	"""Stream the raw `ol_dump_authors.txt.gz` and resolve author key -> name.

		Only keys in `needed` are kept, so the 763MB file is scanned once and we
		return early once every requested key has been found.
	"""
	names: Dict[str, str] = {}
	if not needed or not os.path.exists(dump_path):
		return names

	with gzip.open(dump_path, "rt", encoding="utf-8", errors="ignore") as fh:
		for line in progress.bar(fh, "scanning authors dump", unit="row"):
			parts = line.split("\t", 4)
			if len(parts) < 5:
				continue
			key = parts[1]
			if key not in needed:
				continue
			try:
				obj = json.loads(parts[4])
			except Exception:
				continue
			name = obj.get("name")
			if name:
				names[key] = name
				if len(names) >= len(needed):
					break
	return names


def _stream_work_embedding_rows(conn, chunk_size: int, select_embedding: bool):
	"""Server-side cursor over works rows.

		The DB paginates results and keeps peak memory usage flat. Don't hold all 1M+ vector literals in Python. 
		Pass 1 only needs the author keys, so the 2.8 GB of embedding text is transferred only once, during pass 2.
	"""
	cols = "w.id, w.authors" + (", we.embedding::text" if select_embedding else "")
	result = conn.execution_options(yield_per=chunk_size).execute(text(
		f"SELECT {cols} "
		"FROM works w "
		"JOIN work_embeddings we ON we.work_id = w.id"
	))
	yield from result


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Compute author embeddings (centroid of an author's works) from work_embeddings, resolving human names from the raw authors dump."
	)
	parser.add_argument("--database-url", default=None)
	parser.add_argument(
		"--authors-dump",
		default=os.environ.get("AUTHORS_DUMP", "data/raw/openlibrary/ol_dump_authors.txt.gz"),
		help="Path to the raw OpenLibrary authors dump (ol_dump_authors.txt.gz).",
	)
	args = parser.parse_args()

	load_env()

	url = args.database_url or os.environ.get("DATABASE_URL")
	if not url:
		raise RuntimeError("DATABASE_URL is not set")

	engine = create_engine(url)
	t0 = time.monotonic()
	progress.init()

	# pass 1: collect every work's author keys (no vectors kept in memory)
	with engine.connect() as conn:
		n_works = conn.execute(text(
			"SELECT count(*) FROM works w JOIN work_embeddings we ON we.work_id = w.id"
		)).scalar()

	author_keys: Set[str] = set()
	with engine.connect() as conn:
		for work_id, authors in progress.bar(
			_stream_work_embedding_rows(conn, _STREAM_CHUNK, select_embedding=False),
			"collecting author keys", total=n_works, unit="work",
		):
			author_keys.update(a for a in (authors or []) if a)
	progress.summary(f"collected {len(author_keys):,} author keys")

	# resolve key -> name from the raw dump
	names = load_author_names(args.authors_dump, author_keys)
	unresolved = author_keys - set(names)
	progress.summary(f"resolved {len(names):,} names, {len(unresolved):,} unresolved")

	# pass 2: stream again, aggregating per-author running sums + counts in numpy
	sums: Dict[str, np.ndarray] = {}
	counts: Dict[str, int] = {}
	changed: List[dict] = []
	dtype = np.float32
	with engine.connect() as conn:
		for work_id, authors, emb_text in progress.bar(
			_stream_work_embedding_rows(conn, _STREAM_CHUNK, select_embedding=True),
			"aggregating authors", total=n_works, unit="work",
		):
			vec = _parse_vector(emb_text)
			if vec is None or vec.size == 0:
				continue

			keys = [k for k in (authors or []) if k is not None]
			display = [names.get(k) or k for k in keys if k is not None]

			if display != keys:
				changed.append({"id": work_id, "authors": display})
			for name in display:
				if name not in sums:
					sums[name] = vec.astype(dtype, copy=True)
					counts[name] = 1
				else:
					sums[name] += vec
					counts[name] += 1
	progress.summary(
		f"aggregated {len(sums):,} display names over {n_works:,} works; "
		f"{len(changed):,} works need backfill"
	)

	author_rows = []
	for name, total_vec in progress.bar(sums.items(), "computing centroids", unit="author"):
		centroid = total_vec / counts[name]
		author_rows.append({
			"name": name,
			"work_count": counts[name],
			"embedding": _embedding_literal(centroid),
		})
	progress.summary(f"computed {len(author_rows):,} author centroids")

	with engine.begin() as conn:
		# Drop the HNSW index for the bulk load: per-insert index maintenance on
		# the growing graph made each 50k chunk slower than the last (88s -> 232s).
		conn.execute(text("DROP INDEX IF EXISTS idx_authors_embedding"))
		conn.execute(text("DELETE FROM authors"))
		conn.execute(text("DELETE FROM map_coords WHERE entity = 'author'"))

		insert_sql = text(
			"INSERT INTO authors (name, work_count, embedding) "
			"VALUES (:name, :work_count, :embedding)"
		)
		for i in progress.bar(range(0, len(author_rows), _WRITE_CHUNK), "writing authors", total=len(author_rows), unit="author"):
			conn.execute(insert_sql, author_rows[i:i + _WRITE_CHUNK])

		# backfill works.authors with readable names
		update_sql = text("UPDATE works SET authors = :authors WHERE id = :id")
		for i in progress.bar(range(0, len(changed), _WRITE_CHUNK), "backfilling works.authors", total=len(changed), unit="work"):
			conn.execute(update_sql, changed[i:i + _WRITE_CHUNK])

	# Build the HNSW index in its own transaction: if it fails or is
	# interrupted, the committed author data above must survive.
	progress.summary(f"building hnsw index...")
	with engine.begin() as conn:
		conn.execute(text(
			"CREATE INDEX idx_authors_embedding "
			"ON authors USING hnsw (embedding vector_cosine_ops)"
		))

	progress.summary(
		f"wrote {len(author_rows):,} authors from {n_works:,} works "
		f"({len(names):,} names resolved, {len(unresolved):,} unresolved keys)"
	)
	if unresolved:
		print("Unresolved keys (kept as-is):", sorted(unresolved)[:20])


if __name__ == "__main__":
	main()