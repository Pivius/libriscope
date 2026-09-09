import argparse
import gzip
import json
import os
from typing import Dict, List, Set

from sqlalchemy import create_engine, text

from etl.core.config import load_env


def _parse_vector(emb_text: str) -> List[float]:
	inner = emb_text.strip("[]")
	if not inner:
		return []
	return [float(x) for x in inner.split(",")]


def _embedding_literal(vec: List[float]) -> str:
	return "[" + ",".join(str(float(x)) for x in vec) + "]"


def load_author_names(dump_path: str, needed: Set[str]) -> Dict[str, str]:
	"""Stream the raw `ol_dump_authors.txt.gz` and resolve author key -> name.

	Only keys in `needed` are kept, so the 763MB file is scanned once and we
	stop early once every requested key has been found.
	"""
	names: Dict[str, str] = {}
	if not needed or not os.path.exists(dump_path):
		return names

	with gzip.open(dump_path, "rt", encoding="utf-8", errors="ignore") as fh:
		for line in fh:
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

	# collect each work's author keys + its embedding
	works: List[tuple] = []  # (work_id, [author_keys], vector)
	author_keys: Set[str] = set()
	with engine.connect() as conn:
		rows = conn.execute(text(
			"SELECT w.id, w.authors, we.embedding::text "
			"FROM works w "
			"JOIN work_embeddings we ON we.work_id = w.id"
		)).fetchall()
		for work_id, authors, emb_text in rows:
			vec = _parse_vector(emb_text)
			if not vec:
				continue
			keys = list(authors or [])
			works.append((work_id, keys, vec))
			author_keys.update(keys)

	# resolve key -> name from the raw dump
	names = load_author_names(args.authors_dump, author_keys)
	unresolved = author_keys - set(names)

	# aggregate vectors by display name (fallback to the key when unresolved)
	accums: Dict[str, List[List[float]]] = {}
	resolved_works: List[tuple] = []  # (work_id, [display names], changed)
	for work_id, keys, vec in works:
		display = [names.get(k, k) for k in keys]
		resolved_works.append((work_id, display, display != keys))
		for name in display:
			accums.setdefault(name, []).append(vec)

	author_rows = []
	for name, vectors in accums.items():
		dim = len(vectors[0])
		centroid = [0.0] * dim
		for vec in vectors:
			for i in range(dim):
				centroid[i] += vec[i]
		n = len(vectors)
		centroid = [v / n for v in centroid]
		author_rows.append({
			"name": name,
			"work_count": n,
			"embedding": _embedding_literal(centroid),
		})

	with engine.begin() as conn:
		conn.execute(text("DELETE FROM authors"))
		conn.execute(text("DELETE FROM map_coords WHERE entity = 'author'"))
		if author_rows:
			conn.execute(text(
				"INSERT INTO authors (name, work_count, embedding) "
				"VALUES (:name, :work_count, :embedding)"
			), author_rows)

		# backfill works.authors with human-readable names (keys -> names)
		changed = [
			{"id": work_id, "authors": display}
			for work_id, display, is_changed in resolved_works
			if is_changed
		]
		if changed:
			conn.execute(text(
				"UPDATE works SET authors = :authors WHERE id = :id"
			), [
				{"id": r["id"], "authors": r["authors"]}
				for r in changed
			])

	print(
		f"Wrote {len(author_rows)} authors from {len(works)} works "
		f"({len(names)} names resolved, {len(unresolved)} unresolved keys)"
	)
	if unresolved:
		print("Unresolved keys (kept as-is):", sorted(unresolved)[:20])


if __name__ == "__main__":
	main()
