import argparse
import os
import time
from typing import List, Optional
from collections.abc import Sequence

import numpy as np
from sqlalchemy import create_engine, text, TextClause
from tqdm import tqdm

from etl.core.config import load_env

_STREAM_CHUNK = 4000
_WRITE_CHUNK = 50000


def _parse_vector(emb_text: str) -> Optional[np.ndarray]:
	inner = emb_text.strip("[]")
	if not inner:
		return None
	return np.fromstring(inner, sep=",").astype(np.float32)


def _load_vectors(conn, sql: TextClause, total: int, desc: str):
	"""Stream id and embedding::text rows into a preallocated float32 matrix.

		Returns ids and matrix. Builds the NumPy matrix directly to keep memory near the final matrix size, about 1.6 GB per million rows.
	"""
	ids: list[int] = []
	matrix = np.empty((total, 384), dtype=np.float32)
	n = 0

	result = conn.execution_options(
		yield_per=_STREAM_CHUNK
	).execute(sql)

	for row_id, emb_text in tqdm(result, desc=desc, total=total):
		vec = _parse_vector(emb_text)

		if vec is None:
			continue

		ids.append(row_id)
		matrix[n] = vec
		n += 1

	return ids, matrix[:n]


def _pca_2d(matrix: np.ndarray) -> np.ndarray:
	"""Project rows onto the top two principal components using the Gram matrix method.

		Computes the 384×384 Gram matrix and eigendecomposes it without creating a centered copy or full SVD. 

		Returns an n×2 float32 array.
	"""
	n, d = matrix.shape
	if n < 2 or d < 2:
		return np.zeros((n, 2), dtype=np.float32)

	sums = matrix.sum(axis=0, dtype=np.float64)
	gram = matrix.T @ matrix
	gram = gram - np.outer(sums, sums).astype(np.float32) / n

	w, v = np.linalg.eigh(gram.astype(np.float64))
	top2 = v[:, -2:].astype(np.float32)

	mean = (sums / n).astype(np.float32)
	proj = matrix @ top2 - (top2.T @ mean)[None, :]
	return proj


def _normalize_axes(coords: np.ndarray) -> np.ndarray:
	"""Normalize each axis independently to [-1, 1], preserving aspect.

	Zero-variance axes = 0.
	"""
	out = np.zeros_like(coords, dtype=np.float32)
	for col in range(coords.shape[1]):
		axis = coords[:, col]
		lo, hi = float(axis.min()), float(axis.max())
		if hi - lo < 1e-12:
			out[:, col] = 0.0
		else:
			out[:, col] = 2.0 * (axis - lo) / (hi - lo) - 1.0
	return out


def _coord_rows(ids: Sequence[object], matrix: np.ndarray, entity: str) -> List[dict]:
	rows = []
	if len(ids) > 0:
		print(f"Running PCA on {len(ids):,} {entity} embeddings ...", flush=True)
		proj = _normalize_axes(_pca_2d(matrix))
		for eid, coord in tqdm(zip(ids, proj), desc=f"computing {entity} coords", total=len(ids)):
			rows.append({
				"entity": entity,
				"entity_id": eid,
				"x": float(coord[0]),
				"y": float(coord[1]),
			})
	return rows


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Compute 2D PCA map coordinates for books and authors and store them in map_coords."
	)
	parser.add_argument("--database-url", default=None)
	args = parser.parse_args()

	load_env()
	url = args.database_url or os.environ.get("DATABASE_URL")
	if not url:
		raise RuntimeError("DATABASE_URL is not set")

	engine = create_engine(url)
	t0 = time.monotonic()

	with engine.connect() as conn:
		n_books = conn.execute(text(
			"SELECT count(*) FROM work_embeddings"
		)).scalar_one()
		n_authors = conn.execute(text(
			"SELECT count(*) FROM authors"
		)).scalar_one()
	print(f"[{time.monotonic()-t0:.0f}s] {n_books:,} books, {n_authors:,} authors", flush=True)

	with engine.connect() as conn:
		book_ids, book_matrix = _load_vectors(
			conn,
			text("SELECT work_id, embedding::text FROM work_embeddings ORDER BY work_id"),
			n_books,
			"loading books",
		)
		author_ids, author_matrix = _load_vectors(
			conn,
			text("SELECT name, embedding::text FROM authors ORDER BY name"),
			n_authors,
			"loading authors",
		)
	print(f"[{time.monotonic()-t0:.0f}s] loaded {len(book_ids):,} books, {len(author_ids):,} authors", flush=True)

	rows = _coord_rows(book_ids, book_matrix, "book") + _coord_rows(author_ids, author_matrix, "author")

	sql = text("""
		INSERT INTO map_coords (entity, entity_id, x, y)
		VALUES (:entity, :entity_id, :x, :y)
		ON CONFLICT (entity, entity_id) DO UPDATE SET
			x = EXCLUDED.x,
			y = EXCLUDED.y
	""")
	with engine.begin() as conn:
		for i in tqdm(range(0, len(rows), _WRITE_CHUNK), desc="writing map_coords"):
			conn.execute(sql, rows[i:i + _WRITE_CHUNK])

	print(f"[{time.monotonic()-t0:.0f}s] Wrote {len(rows):,} map coordinates ({len(book_ids):,} books, {len(author_ids):,} authors)", flush=True)


if __name__ == "__main__":
	main()