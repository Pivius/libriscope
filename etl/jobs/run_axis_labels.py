import argparse
import json
import os
from collections import Counter
from typing import Dict, List, Tuple

from sqlalchemy import create_engine, text

from etl.core.config import load_env

QUADRANTS = ("top-left", "top-right", "bottom-left", "bottom-right")


def quadrant_of(x: float, y: float) -> str:
	"""Map world coords (x,y in [-1,1], +y down on screen) to a screen quadrant."""
	if x < 0:
		return "top-left" if y < 0 else "bottom-left"
	return "top-right" if y < 0 else "bottom-right"


def tokens_of(row) -> List[str]:
	subjects, genres = row.subjects or [], row.genres or []
	out = []
	for t in list(subjects) + list(genres):
		t = (t or "").strip().lower()
		if t:
			out.append(t)
	return out


def top_terms(
	per_quadrant: Dict[str, Counter],
	total: Counter,
	top_k: int = 3,
	min_total: int = 4,
	min_quadrant: int = 2,
) -> Dict[str, List[str]]:
	n_total = sum(total.values())
	labels: Dict[str, List[str]] = {}
	for q in QUADRANTS:
		counter = per_quadrant.get(q, Counter())
		n_q = sum(counter.values()) or 1
		scored = []
		for term, cq in counter.items():
			ct = total[term]
			if ct < min_total or cq < min_quadrant:
				continue
			p_term = ct / n_total
			lift = (cq / n_q) / p_term
			# blend lift with raw prevalence so a common, dominant term still wins
			score = lift * (cq ** 0.5)
			scored.append((score, term))
		scored.sort(reverse=True)
		chosen = [term for _, term in scored[:top_k]]
		# fallback: any terms at all, by count
		if not chosen:
			chosen = [term for term, _ in counter.most_common(top_k)]
		labels[q] = chosen
	return labels


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Auto-label the four map quadrants by their dominant subjects/genres, writing axis-labels.json for the frontend."
	)
	parser.add_argument("--database-url", default=None)
	parser.add_argument(
		"--out",
		default="frontend/public/axis-labels.json",
		help="Output JSON path (default: frontend/public/axis-labels.json).",
	)
	args = parser.parse_args()

	load_env()
	url = args.database_url or os.environ.get("DATABASE_URL")
	if not url:
		raise RuntimeError("DATABASE_URL is not set")

	engine = create_engine(url)

	# ---- books ----
	with engine.connect() as conn:
		book_coords = {
			r[0]: (float(r[1]), float(r[2]))
			for r in conn.execute(text(
				"SELECT entity_id, x, y FROM map_coords WHERE entity = 'book'"
			)).fetchall()
		}
		work_rows = conn.execute(text(
			"SELECT id, subjects, genres FROM works"
		)).fetchall()

		book_q: Dict[str, Counter] = {q: Counter() for q in QUADRANTS}
		book_total: Counter = Counter()
		for row in work_rows:
			coord = book_coords.get(row[0])
			if coord is None:
				continue
			q = quadrant_of(*coord)
			for t in tokens_of(row):
				book_q[q][t] += 1
				book_total[t] += 1

	# ---- authors ----
	with engine.connect() as conn:
		author_coords = {
			r[0]: (float(r[1]), float(r[2]))
			for r in conn.execute(text(
				"SELECT entity_id, x, y FROM map_coords WHERE entity = 'author'"
			)).fetchall()
		}
		# map each author -> the subjects/genres of their works (via works.authors array)
		author_q: Dict[str, Counter] = {q: Counter() for q in QUADRANTS}
		author_total: Counter = Counter()

		work_rows = conn.execute(text(
			"SELECT authors, subjects, genres FROM works"
		)).fetchall()
		for row in work_rows:
			for name in (row[0] or []):
				coord = author_coords.get(name)
				if coord is None:
					continue
				q = quadrant_of(*coord)
				for t in tokens_of(row):
					author_q[q][t] += 1
					author_total[t] += 1

	books = top_terms(book_q, book_total)
	authors = top_terms(author_q, author_total)

	payload = {"books": books, "authors": authors}

	out_path = args.out
	os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
	with open(out_path, "w", encoding="utf-8") as fh:
		json.dump(payload, fh, ensure_ascii=False, indent=2)

	print(f"Wrote {out_path}")
	print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
	main()
