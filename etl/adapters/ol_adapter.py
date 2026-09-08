import os
import glob
import csv
import gzip
import json
from typing import Iterator, Dict, Any, List, Optional, Iterable
from etl.core.canonical import CanonicalItem
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

def _parse_tsv_json_row(row: List[str]) -> Optional[Dict[str, Any]]:
	# OpenLibrary processed CSV layout: type, key, revision, last_modified, JSON
	if not row: return None
	# some rows may include extra tabs; JSON is last column
	json_part = row[-1]
	try:
		return json.loads(json_part)
	except Exception:
		return None

def _norm_lang(l: Any) -> Optional[str]:
	if isinstance(l, dict):
		k = l.get("key")
		if isinstance(k, str) and k.startswith("/languages/"):
			return k.split("/")[-1]
	if isinstance(l, str) and l:
		return l
	return None

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
			for f in sorted(glob.glob(p)):
				if f not in seen:
					seen.add(f)
					files.append(f)
		return files

	def stream_dump(self, dump_name: str, file_path: str) -> Iterator[CanonicalItem]:
		with _open_maybe_gzip(file_path) as fh:
			reader = csv.reader(fh, delimiter="\t")
			for row in reader:
				obj = _parse_tsv_json_row(row)
				if obj is None:
					continue
				if dump_name == "works":
					yield self._work_to_canonical(obj)
				elif dump_name == "editions":
					yield self._edition_to_canonical(obj)
				elif dump_name == "authors":
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

	def _work_to_canonical(self, obj: Dict[str, Any]) -> CanonicalItem:
		work_key = obj.get("key") or obj.get("id")
		title = obj.get("title") or ""
		subtitle = obj.get("subtitle")
		description = _text_block(obj.get("description"))
		first_sentence = _text_block(obj.get("first_sentence"))
		subjects = _list_of_str(obj.get("subjects"))
		genres = _list_of_str(obj.get("genres") or obj.get("lc_classifications"))
		# authors on work often are role objects
		authors = []
		for a in obj.get("authors") or []:
			if isinstance(a, dict):
				auth = a.get("author") or a.get("name") or a.get("key")
				if isinstance(auth, dict):
					authors.append(auth.get("name") or auth.get("key"))
				elif auth:
					authors.append(str(auth))
			else:
				authors.append(str(a))
		first_publish_date = obj.get("first_publish_date")
		series = _list_of_str(obj.get("series"))
		embedding_text = " ".join(p for p in [title, subtitle or "", description or "", first_sentence or "", " ".join(subjects), " ".join(genres)] if p)
		return CanonicalItem(
			id=str(work_key),
			title=title,
			subtitle=subtitle,
			description=description,
			first_sentence=first_sentence,
			subjects=subjects,
			genres=genres,
			authors=authors,
			languages=[],
			first_publish_date=first_publish_date,
			series=series,
			raw=obj,
			embedding_text=embedding_text
		)

	def _edition_to_canonical(self, obj: Dict[str, Any]) -> CanonicalItem:
		edition_key = obj.get("key") or obj.get("id")
		# prefer canonical id to be the work key if edition links to works
		works = obj.get("works") or []
		work_key = None
		if isinstance(works, list) and works:
			first = works[0]
			if isinstance(first, dict):
				work_key = first.get("key")
			else:
				work_key = str(first)
		canonical_id = str(work_key or edition_key)

		title = obj.get("title") or ""
		subtitle = obj.get("subtitle")
		description = _text_block(obj.get("description"))
		first_sentence = _text_block(obj.get("first_sentence"))
		subjects = _list_of_str(obj.get("subjects"))
		genres = _list_of_str(obj.get("genres") or obj.get("lc_classifications"))
		authors = []
		for a in obj.get("authors") or []:
			if isinstance(a, dict):
				if a.get("name"):
					authors.append(a.get("name"))
				elif a.get("key"):
					authors.append(a.get("key"))
				else:
					authors.append(str(a))
			else:
				authors.append(str(a))
		languages = []
		for l in obj.get("languages") or []:
			nl = _norm_lang(l)
			if nl and nl not in languages:
				languages.append(nl)
		first_publish_date = obj.get("publish_date") or obj.get("first_publish_date")
		series = _list_of_str(obj.get("series") or obj.get("work_titles"))

		embedding_text = " ".join(p for p in [title, subtitle or "", description or "", first_sentence or "", " ".join(subjects), " ".join(genres)] if p)

		return CanonicalItem(
			id=canonical_id,
			title=title,
			subtitle=subtitle,
			description=description,
			first_sentence=first_sentence,
			subjects=subjects,
			genres=genres,
			authors=authors,
			languages=languages,
			first_publish_date=first_publish_date,
			series=series,
			raw=obj,
			embedding_text=embedding_text
		)

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
		max_aux: Optional[int] = 500000) -> Iterator[CanonicalItem]:
		"""Load authors+editions into small indexes and then stream merged works (one CanonicalItem per work)."""
		if enabled is None:
			enabled = {"works", "editions", "authors", "deletes", "redirects"}
		else:
			enabled = set(enabled)

		authors_by_key: Dict[str, Dict[str, Any]] = {}
		editions_by_work: Dict[str, List[Dict[str, Any]]] = {}
		deletes = set()
		redirects: Dict[str, str] = {}

		# load authors
		if "authors" in enabled:
			for f in self._find_files(root, "authors"):
				for ci in self.stream_dump("authors", f):
					if ci and ci.raw:
						key = ci.raw.get("key") or ci.raw.get("id")
						if key and (max_aux is None or len(authors_by_key) < max_aux):
							authors_by_key[str(key)] = {"name": ci.title, "bio": ci.description}

		# load editions (index by work link or edition key)
		if "editions" in enabled:
			for f in self._find_files(root, "editions"):
				with _open_maybe_gzip(f) as fh:
					reader = csv.reader(fh, delimiter="\t")
					for row in reader:
						obj = _parse_tsv_json_row(row)
						if not obj: continue
						mined = {
							"key": obj.get("key") or obj.get("id"),
							"title": obj.get("title"),
							"description": _text_block(obj.get("description")),
							"subjects": _list_of_str(obj.get("subjects")),
							"genres": _list_of_str(obj.get("genres") or obj.get("lc_classifications")),
							"authors": [a.get("key") if isinstance(a, dict) else str(a) for a in (obj.get("authors") or [])],
							"languages": [nl for nl in (_norm_lang(l) for l in (obj.get("languages") or [])) if nl],
							"publish_date": obj.get("publish_date") or obj.get("first_publish_date"),
							"series": _list_of_str(obj.get("series") or obj.get("work_titles")),
							"raw": None
						}
						works = obj.get("works") or []
						work_keys = []
						if isinstance(works, list) and works:
							for w in works:
								if isinstance(w, dict):
									wk = w.get("key")
								else:
									wk = str(w)
								if wk:
									work_keys.append(str(wk))
						if not work_keys:
							work_keys = [mined.get("key") or ""]
						for wk in work_keys:
							if not wk: continue
							editions_by_work.setdefault(wk, [])
							if max_aux is None or len(editions_by_work[wk]) < max_aux:
								editions_by_work[wk].append(mined)

		# load deletes
		if "deletes" in enabled:
			for f in self._find_files(root, "deletes"):
				with _open_maybe_gzip(f) as fh:
					reader = csv.reader(fh, delimiter="\t")
					for row in reader:
						obj = _parse_tsv_json_row(row)
						if not obj: continue
						tid = obj.get("id") or obj.get("key")
						if tid:
							deletes.add(str(tid))

		# load redirects
		if "redirects" in enabled:
			for f in self._find_files(root, "redirects"):
				with _open_maybe_gzip(f) as fh:
					reader = csv.reader(fh, delimiter="\t")
					for row in reader:
						obj = _parse_tsv_json_row(row)
						if not obj: continue
						src = obj.get("from") or obj.get("key")
						dst = obj.get("to")
						if src and dst:
							redirects[str(src)] = str(dst)

		# now stream works and merge
		for f in self._find_files(root, "works"):
			with _open_maybe_gzip(f) as fh:
				reader = csv.reader(fh, delimiter="\t")
				for row in reader:
					obj = _parse_tsv_json_row(row)
					if not obj: continue
					work_key = obj.get("key") or obj.get("id")
					if not work_key: continue
					work_key = str(work_key)
					if work_key in redirects:
						work_key = redirects[work_key]
					if work_key in deletes:
						yield CanonicalItem(id=work_key, title="", raw={"_meta": "deleted"}, embedding_text=None)
						continue

					# base work
					base_ci = self._work_to_canonical(obj)

					# merge editions
					editions = editions_by_work.get(work_key, [])
					subjects_set = set(base_ci.subjects)
					genres_set = set(base_ci.genres)
					languages = list(base_ci.languages or [])
					series = list(base_ci.series or [])
					edition_author_names: List[str] = []
					first_dates = []
					for ed in editions:
						for s in ed.get("subjects", []):
							if s: subjects_set.add(s)
						for g in ed.get("genres", []):
							if g: genres_set.add(g)
						for l in ed.get("languages", []):
							if l and l not in languages: languages.append(l)
						for akey in ed.get("authors", []):
							if akey and akey in authors_by_key:
								an = authors_by_key[akey].get("name")
								if an and an not in edition_author_names:
									edition_author_names.append(an)
							elif akey and akey not in edition_author_names:
								edition_author_names.append(akey)
						if ed.get("publish_date"):
							first_dates.append(ed.get("publish_date"))
						for s in ed.get("series", []):
							if s and s not in series:
								series.append(s)

					final_authors = []
					for a in (base_ci.authors or []) + edition_author_names:
						if a and a not in final_authors:
							final_authors.append(a)

					first_publish_date = base_ci.first_publish_date or (min(first_dates) if first_dates else None)

					embedding_parts = [
						base_ci.title,
						base_ci.subtitle or "",
						base_ci.description or "",
						base_ci.first_sentence or "",
						" ".join(sorted(subjects_set)),
						" ".join(sorted(genres_set)),
						" ".join(final_authors),
						" ".join(series),
						first_publish_date or ""
					]
					embedding_text = " ".join(p for p in embedding_parts if p)

					yield CanonicalItem(
						id=work_key,
						title=base_ci.title,
						subtitle=base_ci.subtitle,
						description=base_ci.description,
						first_sentence=base_ci.first_sentence,
						subjects=list(subjects_set),
						genres=list(genres_set),
						authors=final_authors,
						languages=languages,
						first_publish_date=first_publish_date,
						series=series,
						raw={"work": obj},
						embedding_text=embedding_text
					)