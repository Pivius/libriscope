import argparse
import os
import time
from typing import Dict, List, Optional, Set

import numpy as np
from sqlalchemy import create_engine, text

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


def _stream_work_embedding_rows(conn, chunk_size: int, select_embedding: bool):
	"""Server-side cursor over works rows.

		The DB paginates results and keeps peak memory usage flat. Don't hold all 1M+ vector literals in Python.
		Pass 1 only needs the author names, so the 2.8 GB of embedding text is transferred only once, during pass 2.
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
		description="Compute author embeddings from work_embeddings. ")
	parser.add_argument("--database-url", default=None)
	parser.add_argument(
		"--authors-dump",
		default=None,
		help="(deprecated) Name resolution now happens in the ETL adapter.")
	args = parser.parse_args()

	load_env()

	url = args.database_url or os.environ.get("DATABASE_URL")
	if not url:
		raise RuntimeError("DATABASE_URL is not set")

	engine = create_engine(url)
	t0 = time.monotonic()
	progress.init()

	# pass 1: collect every work's author names
	with engine.connect() as conn:
		n_works = conn.execute(text(
			"SELECT count(*) FROM works w JOIN work_embeddings we ON we.work_id = w.id"
		)).scalar()

	author_names: Set[str] = set()
	with engine.connect() as conn:
		for work_id, authors in progress.bar(
			_stream_work_embedding_rows(conn, _STREAM_CHUNK, select_embedding=False),
			"collecting author names", total=n_works, unit="work",
		):
			author_names.update(a for a in (authors or []) if a)
	progress.summary(f"collected {len(author_names):,} author names")

	# pass 2: stream again, aggregating per-author running sums + counts in numpy
	sums: Dict[str, np.ndarray] = {}
	counts: Dict[str, int] = {}
	dtype = np.float32
	with engine.connect() as conn:
		for work_id, authors, emb_text in progress.bar(
			_stream_work_embedding_rows(conn, _STREAM_CHUNK, select_embedding=True),
			"aggregating authors", total=n_works, unit="work",
		):
			vec = _parse_vector(emb_text)
			if vec is None or vec.size == 0:
				continue

			for name in (a for a in (authors or []) if a):
				if name not in sums:
					sums[name] = vec.astype(dtype, copy=True)
					counts[name] = 1
				else:
					sums[name] += vec
					counts[name] += 1
	progress.summary(
		f"aggregated {len(sums):,} authors over {n_works:,} works"
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
		conn.execute(text("DROP INDEX IF EXISTS idx_authors_embedding"))
		conn.execute(text("DELETE FROM authors"))
		conn.execute(text("DELETE FROM map_coords WHERE entity = 'author'"))

		insert_sql = text(
			"INSERT INTO authors (name, work_count, embedding) "
			"VALUES (:name, :work_count, :embedding)"
		)
		num_batches = (len(author_rows) + _WRITE_CHUNK - 1) // _WRITE_CHUNK
		bar = progress.bar(range(0, len(author_rows), _WRITE_CHUNK), "writing authors",
			total=num_batches, unit="batch")
		for i in bar:
			conn.execute(insert_sql, author_rows[i:i + _WRITE_CHUNK])
			bar.set_postfix_str(f"{min(i + _WRITE_CHUNK, len(author_rows)):,}/{len(author_rows):,} authors")

	t0_index = time.monotonic()
	with engine.begin() as conn:
		conn.execute(text(
			"CREATE INDEX idx_authors_embedding "
			"ON authors USING hnsw (embedding vector_cosine_ops)"
		))
	progress.summary(f"rebuilt authors HNSW index in {time.monotonic() - t0_index:.0f}s")

	progress.summary(
		f"wrote {len(author_rows):,} authors from {n_works:,} works"
	)


if __name__ == "__main__":
	main()
