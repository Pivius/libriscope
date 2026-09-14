import argparse
import math
import os
import time
from collections.abc import Iterable
from typing import Dict, List, Tuple

from sqlalchemy import create_engine, text
from etl.core import progress

from etl.core.config import load_env

# Cell side in world units is 2 / 2^z. At z=13 that's 2/8192 ≈ 0.000244 world
# units ≈ 3 px at the frontend's max zoom (WORLD_SCALE=380 px/unit, k=40).
MAX_LEVEL = 13
_STREAM_CHUNK = 4000
_IN_CHUNK = 1000
_WRITE_CHUNK = 50000

_INSERT_SQL = text(
	"""
	INSERT INTO map_grids (entity, level, cx, cy, count, x_avg, y_avg, sample_id, sample_label)
	VALUES (:entity, :level, :cx, :cy, :count, :x_avg, :y_avg, :sample_id, :sample_label)
	"""
)


def cell_of(coord: float, level: int) -> int:
	"""Index of the grid cell containing `coord` at `level`.

		World coords are in [-1, 1]; cell `c` spans world
		[-1 + c * 2/2^z, -1 + (c + 1) * 2/2^z). The exact right edge (coord == 1)
		clamps into the last cell so the returned index is always in [0, 2^z).
	"""
	span = 1 << level
	c = int(math.floor((coord + 1.0) * 0.5 * span))
	if c >= span:
		return span - 1
	if c < 0:
		return 0
	return c


def aggregate_rows(
	rows: Iterable[Tuple[str, float, float]],
	level: int,
) -> Dict[Tuple[int, int], Tuple[int, float, float, str]]:
	"""Bucket `(entity_id, x, y)` rows into grid cells.

		`rows` must already be ordered by `entity_id`; the first row seen per cell
		becomes the deterministic sample (the smallest entity_id in that cell).

		Returns {(cx, cy): (count, x_avg, y_avg, sample_id)}.
	"""
	acc: Dict[Tuple[int, int], Tuple[int, float, float, str]] = {}
	for entity_id, x, y in rows:
		key = (cell_of(x, level), cell_of(y, level))
		entry = acc.get(key)
		if entry is None:
			acc[key] = (1, x, y, entity_id)
		else:
			count, sx, sy, sample = entry
			acc[key] = (count + 1, sx + x, sy + y, sample)

	out: Dict[Tuple[int, int], Tuple[int, float, float, str]] = {}
	for key, (count, sx, sy, sample) in acc.items():
		out[key] = (count, sx / count, sy / count, sample)
	return out


def _chunks(items: List[str], size: int):
	for i in range(0, len(items), size):
		yield items[i:i + size]


def _fetch_labels(conn, entity: str, sample_ids: List[str]) -> Dict[str, str]:
	"""Denormalized label lookup: works.title for books, authors.name for authors."""
	out: Dict[str, str] = {}
	for chunk in _chunks(sample_ids, _IN_CHUNK):
		placeholders = ",".join(f":id_{i}" for i in range(len(chunk)))
		params = {f"id_{i}": value for i, value in enumerate(chunk)}
		if entity == "book":
			stmt = text(
				f"SELECT id, title FROM works WHERE id IN ({placeholders})"
			)
		else:
			stmt = text(
				f"SELECT name, name AS label FROM authors WHERE name IN ({placeholders})"
			)
		for _id, label in conn.execute(stmt, params):
			out[_id] = label or _id
	return out


def _rows_for_entity(conn, entity: str) -> List[Tuple[str, float, float]]:
	result = conn.execution_options(yield_per=_STREAM_CHUNK).execute(
		text(
			"SELECT entity_id, x, y FROM map_coords "
			"WHERE entity = :entity ORDER BY entity_id"
		),
		{"entity": entity},
	)
	return [(r.entity_id, float(r.x), float(r.y)) for r in result]


def build_entity_grid(
	read_conn,
	write_conn,
	entity: str,
	levels: List[int],
) -> int:
	"""Aggregate every `level` of one entity into map_grids. Returns rows written.

		`read_conn` streams map_coords with a server-side cursor (yield_per);
		`write_conn` performs the DELETE + chunked executemany inserts. psycopg2 does
		not support executemany on a connection that has an open server-side cursor,
		so the two must be separate connections.
	"""
	rows = _rows_for_entity(read_conn, entity)
	written = 0
	for level in progress.bar(levels, f"gridding {entity}", unit="level"):
		acc = aggregate_rows(rows, level)
		if not acc:
			continue

		sample_ids = sorted({sample for _, _, _, sample in acc.values()})
		labels = _fetch_labels(read_conn, entity, sample_ids)

		inserts = [
			{
				"entity": entity,
				"level": level,
				"cx": cx,
				"cy": cy,
				"count": count,
				"x_avg": x_avg,
				"y_avg": y_avg,
				"sample_id": sample,
				"sample_label": labels.get(sample, sample),
			}
			for (cx, cy), (count, x_avg, y_avg, sample) in sorted(acc.items())
		]
		num_batches = (len(inserts) + _WRITE_CHUNK - 1) // _WRITE_CHUNK
		bar = progress.bar(
			range(0, len(inserts), _WRITE_CHUNK),
			f"writing {entity} level {level}",
			total=num_batches, unit="batch", leave=False,
		)
		for i in bar:
			write_conn.execute(_INSERT_SQL, inserts[i:i + _WRITE_CHUNK])
			bar.set_postfix_str(f"{min(i + _WRITE_CHUNK, len(inserts)):,}/{len(inserts):,} rows")
		written += len(inserts)
	return written


def main() -> None:
	parser = argparse.ArgumentParser(
		description=(
			"Build level-of-detail grid aggregates (map_grids) from map_coords. "
			"Idempotent: the table is deleted and rebuilt from scratch."
		)
	)
	parser.add_argument("--database-url", default=None)
	parser.add_argument(
		"--levels",
		default=None,
		help="Comma-separated level list to build (default: all of 0..13).",
	)
	args = parser.parse_args()

	load_env()
	url = args.database_url or os.environ.get("DATABASE_URL")
	if not url:
		raise RuntimeError("DATABASE_URL is not set")

	levels = list(range(MAX_LEVEL + 1)) if args.levels is None else \
		[int(v) for v in args.levels.split(",")]

	engine = create_engine(url)
	t0 = time.monotonic()
	progress.init()

	with engine.begin() as write_conn:
		write_conn.execute(text("DELETE FROM map_grids"))
		total = 0
		with engine.connect() as read_conn:
			for entity in ("book", "author"):
				total += build_entity_grid(read_conn, write_conn, entity, levels)

	progress.summary(f"Rebuilt map_grids: {total:,} rows "
		f"({len(levels)} levels)")


if __name__ == "__main__":
	main()