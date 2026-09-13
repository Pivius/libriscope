# tests/test_ol_language_filter.py
import csv
import json

import etl.adapters.ol_adapter as ol_adapter
from etl.adapters.ol_adapter import OpenLibraryCSVAdapter


def _write_tsv(path, rows):
	with open(path, "w", encoding="utf-8", newline="") as fh:
		for row in rows:
			fh.write("\t".join(row) + "\n")


def _row(type_key, key, obj):
	return [type_key, key, "1", "2026-01-01", json.dumps(obj)]


def _work(key, title, **extra):
	obj = {"key": key, "title": title}
	obj.update(extra)
	return _row("/type/work", key, obj)


def _fake_detector(allowed_titles):
	"""Deterministic is_allowed stand-in keyed by title."""
	def detect(title):
		return title in allowed_titles
	return detect


def test_collate_filters_non_english_by_title(tmp_path, monkeypatch):
	works = [
		_work("/works/engW", "English book"),
		_work("/works/freW", "Livre francais"),
		_work("/works/eng2W", "Another English one"),
		_work("/works/nolangW", "No language"),
	]
	_write_tsv(tmp_path / "works_test.csv", works)

	monkeypatch.setattr(ol_adapter, "is_allowed",
		_fake_detector({"English book", "Another English one"}))

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(str(tmp_path), enabled={"works"}, max_aux=None))

	assert [i.id for i in items] == ["/works/engW", "/works/eng2W"]
	# language is the fasttext-derived label
	assert all(i.languages == ["eng"] for i in items)
	assert all(i.embedding_text is None for i in items)


def test_collate_skips_titleless_works_before_json_parse(tmp_path, monkeypatch):
	# line without a "title" key must be skipped by the substring pre-check
	works = [
		_work("/works/engW", "English book"),
		_row("/type/work", "/works/notitleW", {"key": "/works/notitleW"}),
		_work("/works/eng2W", "Second"),
	]
	_write_tsv(tmp_path / "works_test.csv", works)

	monkeypatch.setattr(ol_adapter, "is_allowed", _fake_detector({"English book", "Second"}))

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(str(tmp_path), enabled={"works"}, max_aux=None))

	assert [i.id for i in items] == ["/works/engW", "/works/eng2W"]


def test_collate_resolves_authors_via_index(tmp_path, monkeypatch):
	authors = [
		_row("/type/author", "/authors/OL1A", {"key": "/authors/OL1A", "name": "Jane Austen"}),
		_row("/type/author", "/authors/OL2A", {"key": "/authors/OL2A", "name": "Unknown Author"}),
	]
	works = [
		_work("/works/engW", "English book", authors=[
			{"type": "/type/author_role", "author": {"key": "/authors/OL1A"}},
			{"type": "/type/author_role", "author": {"key": "/authors/OL999A"}},
		]),
	]
	_write_tsv(tmp_path / "authors_test.csv", authors)
	_write_tsv(tmp_path / "works_test.csv", works)

	monkeypatch.setattr(ol_adapter, "is_allowed", _fake_detector({"English book"}))

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(
		str(tmp_path), enabled={"works", "authors"}, max_aux=None))

	assert items[0].authors == ["Jane Austen", "/authors/OL999A"]


def test_collate_deletes_and_redirects(tmp_path, monkeypatch):
	works = [
		_work("/works/engW", "English book"),
		_work("/works/oldW", "Old title"),
		_work("/works/goneW", "Deleted book"),
	]
	deletes = [_row("/type/delete", "/works/goneW", {"key": "/works/goneW"})]
	redirects = [_row("/type/redirect", "/works/oldW",
		{"key": "/works/oldW", "location": "/works/engW", "from": "/works/oldW", "to": "/works/engW"})]
	_write_tsv(tmp_path / "works_test.csv", works)
	_write_tsv(tmp_path / "deletes_test.csv", deletes)
	_write_tsv(tmp_path / "redirects_test.csv", redirects)

	monkeypatch.setattr(ol_adapter, "is_allowed", _fake_detector({"English book", "Old title", "Deleted book"}))

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(
		str(tmp_path), enabled={"works", "deletes", "redirects"}, max_aux=None))

	assert [i.id for i in items] == ["/works/engW", "/works/engW", "/works/goneW"]
	assert items[2].raw == {"_meta": "deleted"}


def test_collate_respects_max_works(tmp_path, monkeypatch):
	works = [
		_work(f"/works/w{i}", f"title {i}") for i in range(5)
	]
	_write_tsv(tmp_path / "works_test.csv", works)

	monkeypatch.setattr(ol_adapter, "is_allowed", lambda t: True)

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(
		str(tmp_path), enabled={"works"}, max_aux=None, max_works=2))

	assert [i.id for i in items] == ["/works/w0", "/works/w1"]


def test_collate_offset_skips_works(tmp_path, monkeypatch):
	works = [
		_work(f"/works/w{i}", f"title {i}") for i in range(5)
	]
	_write_tsv(tmp_path / "works_test.csv", works)

	monkeypatch.setattr(ol_adapter, "is_allowed", lambda t: True)

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(
		str(tmp_path), enabled={"works"}, max_aux=None, offset=3))

	assert [i.id for i in items] == ["/works/w3", "/works/w4"]


def test_numeric_file_sort(tmp_path):
	for n in (2000000, 10000000, 4000000):
		_write_tsv(tmp_path / f"works_{n}.csv", [])

	from etl.adapters.ol_adapter import _numeric_key
	import glob as glob_mod
	files = sorted(glob_mod.glob(str(tmp_path / "works_*.csv")), key=_numeric_key)
	assert [f.split("_")[-1].split(".")[0] for f in files] == ["2000000", "4000000", "10000000"]


def test_is_allowed_real_detection():
	from etl.core.languages import is_allowed
	assert is_allowed("The Great Gatsby")
	assert is_allowed("Crime and Punishment")
	assert not is_allowed("Le Petit Prince")
	assert not is_allowed("")
	assert not is_allowed("ab")  # below min length
