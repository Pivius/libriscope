import argparse
import os
from typing import List, Tuple

import numpy as np
from sqlalchemy import create_engine, text

from etl.core.config import load_env


def _parse_vector(emb_text: str) -> List[float]:
	inner = emb_text.strip("[]")
	if not inner:
		return []
	return [float(x) for x in inner.split(",")]


def _pca_2d(matrix: np.ndarray) -> np.ndarray:
	"""Project rows of `matrix` onto the top two principal components.

	Returns an (n, 2) array. Falls back to zeros when there are fewer than two
	samples or two dimensions.
	"""
	if matrix.shape[0] < 2 or matrix.shape[1] < 2:
		return np.zeros((matrix.shape[0], 2), dtype=float)

	centered = matrix - matrix.mean(axis=0)
	_, _, vt = np.linalg.svd(centered, full_matrices=False)
	top = vt[:2, :]
	proj = centered @ top.T
	return proj


def _normalize_axes(coords: np.ndarray) -> np.ndarray:
	"""Normalize each axis independently to [-1, 1], preserving aspect.

	Zero-variance axes are left at 0.
	"""
	out = np.zeros_like(coords, dtype=float)
	for col in range(coords.shape[1]):
		axis = coords[:, col]
		lo, hi = float(axis.min()), float(axis.max())
		if hi - lo < 1e-12:
			out[:, col] = 0.0
		else:
			out[:, col] = 2.0 * (axis - lo) / (hi - lo) - 1.0
	return out


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

	book_ids, author_names = [], []
	book_vecs, author_vecs = [], []
	with engine.connect() as conn:
		for work_id, emb_text in conn.execute(text(
			"SELECT work_id, embedding::text FROM work_embeddings"
		)).fetchall():
			vec = _parse_vector(emb_text)
			if not vec:
				continue
			book_ids.append(work_id)
			book_vecs.append(vec)

		for name, emb_text in conn.execute(text(
			"SELECT name, embedding::text FROM authors"
		)).fetchall():
			vec = _parse_vector(emb_text)
			if not vec:
				continue
			author_names.append(name)
			author_vecs.append(vec)

	def _coord_rows(ids, vecs, entity):
		rows = []
		if vecs:
			matrix = np.array(vecs, dtype=float)
			proj = _pca_2d(matrix)
			proj = _normalize_axes(proj)
			for eid, coord in zip(ids, proj):
				rows.append({
					"entity": entity,
					"entity_id": eid,
					"x": float(coord[0]),
					"y": float(coord[1]),
				})
		return rows

	rows = _coord_rows(book_ids, book_vecs, "book") + _coord_rows(author_names, author_vecs, "author")

	sql = text("""
		INSERT INTO map_coords (entity, entity_id, x, y)
		VALUES (:entity, :entity_id, :x, :y)
		ON CONFLICT (entity, entity_id) DO UPDATE SET
			x = EXCLUDED.x,
			y = EXCLUDED.y
	""")
	with engine.begin() as conn:
		conn.execute(sql, rows)

	print(f"Wrote {len(rows)} map coordinates ({len(book_ids)} books, {len(author_names)} authors)")


if __name__ == "__main__":
	main()
