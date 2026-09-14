"""Bring the live database schema in line with infra/init.sql.

init.sql can only create (CREATE TABLE/INDEX IF NOT EXISTS); it never adds
columns to existing tables, and it never drops anything. This script diffs
the desired schema (parsed from init.sql) against the actual schema
(information_schema / pg_indexes) and applies the difference:

	- column added to init.sql    -> ALTER TABLE ... ADD COLUMN IF NOT EXISTS
	- column removed from init.sql -> ALTER TABLE ... DROP COLUMN IF EXISTS
	- table removed from init.sql  -> DROP TABLE ... CASCADE
	- index removed from init.sql  -> DROP INDEX IF EXISTS

Additions of tables/indexes are already handled by running init.sql first
(see the db-init Makefile target). Column type changes are applied by
dropping and re-adding the column with the new type — destructive by design,
since a schema change implies a re-ingest.

Usage: python scripts/migrate_schema.py [database_url]
"""

import os
import re
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.core.config import load_env  # noqa: E402

INIT_SQL = os.path.join("infra", "init.sql")


def parse_init_sql(path: str):
	"""Extract desired tables and indexes from init.sql.

	Returns ({table: {col_name: col_definition}}, {index_name: create_sql}).
	Column definitions keep their full type text (e.g. "TEXT[]", "VECTOR(768)").
	"""
	with open(path, encoding="utf-8") as fh:
		sql = fh.read()

	# strip comments so they don't leak into column definitions
	sql = re.sub(r"--[^\n]*", "", sql)

	tables: dict = {}
	for m in re.finditer(
		r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\)\s*;",
		sql,
		flags=re.S | re.I,
	):
		name, body = m.group(1), m.group(2)
		cols: dict = {}
		depth = 0
		current = []
		# split on top-level commas (parentheses may nest, e.g. VECTOR(768))
		for ch in body:
			if ch == "(":
				depth += 1
			elif ch == ")":
				depth -= 1
			if ch == "," and depth == 0:
				parts = "".join(current).strip()
				current = []
				if parts:
					_m = re.match(r"(\w+)\s+(.+)", parts, flags=re.S)
					if _m and _m.group(1).lower() not in ("primary", "foreign", "unique", "check", "constraint"):
						cols[_m.group(1).lower()] = re.sub(r"\s+", " ", _m.group(2)).strip()
			else:
				current.append(ch)
		parts = "".join(current).strip()
		if parts:
			_m = re.match(r"(\w+)\s+(.+)", parts, flags=re.S)
			if _m and _m.group(1).lower() not in ("primary", "foreign", "unique", "check", "constraint"):
				cols[_m.group(1).lower()] = re.sub(r"\s+", " ", _m.group(2)).strip()
		tables[name] = cols

	indexes: dict = {}
	for m in re.finditer(
		r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+ON\s+(\w+)[^;]*;",
		sql,
		flags=re.S | re.I,
	):
		indexes[m.group(1)] = m.group(2)

	return tables, indexes


def actual_schema(engine):
	"""Read the live schema: {table: {col: type}}, {index: table}."""
	cols: dict = {}
	indexes: dict = {}

	with engine.connect() as conn:
		for table, column, data_type, udt in conn.execute(text(
			"SELECT table_name, column_name, data_type, udt_name "
			"FROM information_schema.columns WHERE table_schema = 'public'"
		)):
			cols.setdefault(table, {})[column.lower()] = (data_type or "").lower(), (udt or "").lower()

		indexes: dict = {}
		for index_name, table in conn.execute(text(
			"SELECT indexname, tablename FROM pg_indexes WHERE schemaname = 'public'"
		)):
			indexes[index_name] = table

	return cols, indexes


def _type_matches(desired_def: str, actual: tuple) -> bool:
	"""Loose comparison of desired column definition against the live type."""
	data_type, udt = actual
	d = desired_def.strip().lower()
	if "text[]" in d or "character varying[]" in d:
		return data_type == "array"
	if "vector" in d:
		return udt == "vector"
	if "double precision" in d:
		return data_type == "double precision"
	if "smallint" in d:
		return data_type == "smallint"
	if "int" in d:
		return data_type in ("integer", "bigint", "smallint")
	if "timestamp" in d:
		return data_type in ("timestamp without time zone", "timestamp with time zone")
	if "text" in d:
		return data_type in ("text", "character varying")
	return True  # unknown shape -> don't touch


def generate_diff(desired_tables, desired_indexes, actual_cols, actual_indexes):
	stmts = []

	# tables removed from init.sql
	for table in actual_cols:
		if table not in desired_tables and table != "pipeline_meta":
			stmts.append(f"DROP TABLE IF EXISTS {table} CASCADE")

	# columns per table
	for table, want_cols in desired_tables.items():
		have_cols = actual_cols.get(table, {})
		for col, defn in want_cols.items():
			if col not in have_cols:
				stmts.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {defn}")
			elif not _type_matches(defn, have_cols[col]):
				stmts.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")
				stmts.append(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
		for col in have_cols:
			if col not in want_cols:
				stmts.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

	# indexes removed from init.sql (keep primary-key-ish constraints alone;
	# pg_indexes lists those too but they never appear in init.sql)
	for index_name, table in actual_indexes.items():
		if index_name not in desired_indexes and not index_name.startswith(("works_pkey", "authors_pkey", "map_coords_pkey", "map_grids_pkey", "work_embeddings_pkey", "pipeline_meta_pkey")):
			stmts.append(f"DROP INDEX IF EXISTS {index_name}")

	return stmts


def main() -> None:
	load_env()
	url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL")
	if not url:
		raise RuntimeError("DATABASE_URL is not set")

	engine = create_engine(url)
	desired_tables, desired_indexes = parse_init_sql(INIT_SQL)
	actual_cols, actual_indexes = actual_schema(engine)

	stmts = generate_diff(desired_tables, desired_indexes, actual_cols, actual_indexes)
	if not stmts:
		print("schema is up to date")
		return

	with engine.begin() as conn:
		for stmt in stmts:
			print(f"  {stmt}")
			conn.execute(text(stmt))
	print(f"applied {len(stmts)} schema change(s)")


if __name__ == "__main__":
	main()
