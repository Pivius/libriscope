import os
import glob
import gzip
import json
from typing import Iterator, Dict, Any, List, Optional, Iterable
from etl.core.canonical import CanonicalItem
from etl.core.languages import is_allowed
from etl.core import progress
from etl.adapters.base import DatasetAdapter


def _open_maybe_gzip(path: str):
	"""Open a file that may be gzip-compressed based on extension."""
	if path.endswith(".gz"):
		return gzip.open(path, "rt", encoding="utf-8", errors="ignore", newline="")
	return open(path, "r", encoding="utf-8", errors="ignore", newline="")


# Helper parsers
def _text_block(val: Any) -> Optional[str]:
	if val is None: return None
	if isinstance(val, str): return val.strip() or None
	if isinstance(val, dict): return (val.get("value") or val.get("text") or "").strip() or None
	return None

def _list_of_str(val: Any) -> List[str]:
	if not val: return []
	if isinstance(val, list): return [str(x) for x in val if x is not None]
	return [str(val)]

def _extract_authors(obj: Dict[str, Any]) -> List[str]:
	"""Work authors are role objects: {"type": "/type/author_role", "author": {"key": ...}}."""
	authors: List[str] = []
	for a in obj.get("authors") or []:
		if isinstance(a, dict):
			auth = a.get("author") or a.get("name") or a.get("key")
			if isinstance(auth, dict):
				v = auth.get("name") or auth.get("key")
				if v: authors.append(str(v))
			elif auth:
				authors.append(str(auth))
		elif a:
			authors.append(str(a))
	return authors

def _iter_dump_json(path: str, require: Optional[str] = None) -> Iterator[Dict[str, Any]]:
	"""Iterate a dump file yielding parsed JSON objects.

	Uses rsplit on the last tab instead of csv.reader (no per-row CSV state)
	and applies a cheap substring pre-check before json.loads so lines that
	cannot possibly qualify never pay for deserialization."""
	with _open_maybe_gzip(path) as fh:
		for line in fh:
			raw = line.rstrip()
			if not raw:
				continue
			json_part = raw.rsplit("\t", 1)[-1]
			if require is not None and require not in json_part:
				continue
			try:
				yield json.loads(json_part)
			except ValueError:
				continue

LINES_PER_FILE = 2_000_000


def _numeric_key(path: str):
	"""Sort key ordering dump chunks by their numeric suffix.

	Filenames are `{dump}_{upper_bound}.csv.gz`; lexicographic sort would put
	`works_10000000` before `works_2000000` ("1" < "2").
	"""
	basename = os.path.basename(path)
	suffix = basename.split("_")[-1].split(".")[0]
	return int(suffix) if suffix.isdigit() else 0


class OpenLibraryCSVAdapter(DatasetAdapter):
	"""Reads processed OpenLibrary TSV CSV files (JSON in last column)."""

	def _find_files(self, root: str, dump: str) -> List[str]:
		patterns = [
			os.path.join(root, f"{dump}_*.csv"),
			os.path.join(root, f"{dump}_*.csv.gz"),
			os.path.join(root, f"*{dump}*.csv"),
			os.path.join(root, f"*{dump}*.csv.gz"),
		]
		files = []
		seen = set()
		for p in patterns:
			for f in sorted(glob.glob(p), key=_numeric_key):
				if f not in seen:
					seen.add(f)
					files.append(f)
		return files

	def stream_dump(self, dump_name: str, file_path: str) -> Iterator[CanonicalItem]:
		with _open_maybe_gzip(file_path) as fh:
			reader = _iter_dump_json(file_path)
			for obj in reader:
				if dump_name == "authors":
					yield self._author_to_canonical(obj)
				elif dump_name == "deletes":
					key = obj.get("id") or obj.get("key")
					yield CanonicalItem(id=str(key), title="", raw={"type": "delete", **(obj or {})}, embedding_text=None)
				elif dump_name == "redirects":
					src = obj.get("from") or obj.get("key")
					dst = obj.get("to")
					yield CanonicalItem(id=str(src), title="", raw={"type": "redirect", "to": dst, **(obj or {})}, embedding_text=None)
				else:
					# misc metadata (ratings/reading-log/covers/wikidata) -> minimal CanonicalItem with raw
					key = obj.get("work_id") or obj.get("work") or obj.get("key") or obj.get("id")
					if key:
						yield CanonicalItem(id=str(key), title="", raw={ "type": dump_name, **(obj or {}) }, embedding_text=None)

	def _author_to_canonical(self, obj: Dict[str, Any]) -> CanonicalItem:
		author_key = obj.get("key") or obj.get("id")
		name = obj.get("name") or ""
		bio = _text_block(obj.get("bio"))
		embedding_text = " ".join(p for p in [name, bio or ""] if p)
		return CanonicalItem(
			id=str(author_key),
			title=name,
			subtitle=None,
			description=bio,
			first_sentence=None,
			subjects=[],
			genres=[],
			authors=[],
			languages=[],
			first_publish_date=None,
			series=[],
			raw=obj,
			embedding_text=embedding_text
		)

	def collate_from_dir(self, root: str,
		enabled: Optional[Iterable[str]] = None,
		max_aux: Optional[int] = 500000,
		max_works: Optional[int] = None,
		offset: int = 0) -> Iterator[CanonicalItem]:
		"""Stream works filtered by fasttext language detection on the title."""
		if enabled is None:
			enabled = {"works", "authors", "deletes", "redirects"}
		else:
			enabled = set(enabled)

		authors_by_key: Dict[str, Dict[str, Any]] = {}
		deletes = set()
		redirects: Dict[str, str] = {}

		# load authors (one cumulative bar across all chunks)
		if "authors" in enabled:
			rows = 0
			bar = progress.bar(self._find_files(root, "authors"), "indexing authors", unit="file")
			for f in bar:
				for ci in self.stream_dump("authors", f):
					if ci and ci.raw:
						key = ci.raw.get("key") or ci.raw.get("id")
						if key and (max_aux is None or len(authors_by_key) < max_aux):
							authors_by_key[str(key)] = {"name": ci.title, "bio": ci.description}
					rows += 1
				bar.set_postfix_str(f"{rows:,} rows")
			progress.summary(f"indexed {len(authors_by_key):,} authors")

		# load deletes
		if "deletes" in enabled:
			rows = 0
			bar = progress.bar(self._find_files(root, "deletes"), "indexing deletes", unit="file")
			for f in bar:
				for obj in _iter_dump_json(f):
					tid = obj.get("id") or obj.get("key")
					if tid:
						deletes.add(str(tid))
					rows += 1
				bar.set_postfix_str(f"{rows:,} rows")
			progress.summary(f"indexed {len(deletes):,} deletes")

		# load redirects
		if "redirects" in enabled:
			rows = 0
			bar = progress.bar(self._find_files(root, "redirects"), "indexing redirects", unit="file")
			for f in bar:
				for obj in _iter_dump_json(f):
					src = obj.get("from") or obj.get("key")
					dst = obj.get("to")
					if src and dst:
						redirects[str(src)] = str(dst)
					rows += 1
				bar.set_postfix_str(f"{rows:,} rows")
			progress.summary(f"indexed {len(redirects):,} redirects")

		works_yielded = 0
		works_capped = max_works is not None
		lines_skipped = 0
		bar = progress.bar(self._find_files(root, "works"), "streaming works", unit="file")
		for f in bar:
			if works_capped and works_yielded >= max_works:
				break

			if lines_skipped + LINES_PER_FILE <= offset:
				lines_skipped += LINES_PER_FILE
				continue
			with _open_maybe_gzip(f) as fh:

				remaining = offset - lines_skipped
				while remaining > 0:
					if not fh.readline():
						break
					remaining -= 1
				lines_skipped = offset

				for line in fh:
					raw = line.rstrip()
					if not raw:
						continue
					# no title key can never qualify
					json_part = raw.rsplit("\t", 1)[-1]
					if '"title"' not in json_part:
						continue
					try:
						obj = json.loads(json_part)
					except ValueError:
						continue

					work_key = obj.get("key") or obj.get("id")
					if not work_key: continue
					work_key = str(work_key)
					if work_key in redirects:
						work_key = redirects[work_key]
					if work_key in deletes:
						yield CanonicalItem(id=work_key, title="", raw={"_meta": "deleted"}, embedding_text=None)
						continue

					title = obj.get("title") or ""
					if not is_allowed(title):
						continue

					authors: List[str] = []
					for ak in _extract_authors(obj):
						entry = authors_by_key.get(ak)
						name = entry.get("name") if entry else None
						if name and name not in authors:
							authors.append(name)
						elif not name and ak not in authors:
							authors.append(ak)

					works_yielded += 1
					bar.set_postfix_str(f"{works_yielded:,} passed")


					yield CanonicalItem(
						id=work_key,
						title=title,
						subtitle=obj.get("subtitle"),
						description=_text_block(obj.get("description")),
						first_sentence=_text_block(obj.get("first_sentence")),
						subjects=_list_of_str(obj.get("subjects")),
						genres=_list_of_str(obj.get("genres")),
						lc_classifications=_list_of_str(obj.get("lc_classifications")),
						authors=authors,
						languages=["eng"],
						first_publish_date=obj.get("first_publish_date"),
						series=_list_of_str(obj.get("series")),
						raw={"work": obj},
						embedding_text=None
					)

					if works_capped and works_yielded >= max_works:
						break
		progress.summary(f"streamed {works_yielded:,} works")
