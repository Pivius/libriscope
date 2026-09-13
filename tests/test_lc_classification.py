# tests/test_lc_classification.py
import csv
import json

import etl.adapters.ol_adapter as ol_adapter
from etl.adapters.ol_adapter import OpenLibraryCSVAdapter
from etl.core.canonical import CanonicalItem
from etl.core.text_builder import build_text
from etl.jobs.run_axis_labels import lc_label


def _write_tsv(path, rows):
	with open(path, "w", encoding="utf-8", newline="") as fh:
		for row in rows:
			fh.write("\t".join(row) + "\n")


def _work(key, obj):
	return ["/type/work", key, "1", "2026-01-01", json.dumps(obj)]


def test_lc_label_mapping():
	assert lc_label("PS3511.A867") == "American Literature"
	assert lc_label("PR6001.F7") == "English Literature"
	assert lc_label("QA76.9") == "Mathematics"
	assert lc_label("QC") == "Physics"
	assert lc_label("bs70") == "The Bible"  # case-insensitive
	assert lc_label("ZZ999") == "Bibliography & Library Science"
	assert lc_label("999") == ""  # unmapped
	assert lc_label("") == ""


def test_adapter_extracts_lc_classifications(tmp_path, monkeypatch):
	works = [
		_work("/works/engW", {
			"key": "/works/engW",
			"title": "English book",
			"genres": ["Novels"],
			"lc_classifications": ["PS3511.A867", "PZ7"],
		}),
	]
	_write_tsv(tmp_path / "works_test.csv", works)

	monkeypatch.setattr(ol_adapter, "is_allowed", lambda t: True)

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(str(tmp_path), enabled={"works"}, max_aux=None))

	item = items[0]

	assert item.lc_classifications == ["PS3511.A867", "PZ7"]
	assert item.genres == ["Novels"]


def test_adapter_lc_without_genres(tmp_path, monkeypatch):
	works = [
		_work("/works/engW", {
			"key": "/works/engW",
			"title": "English book",
			"lc_classifications": ["QA76.9.A43"],
		}),
	]
	_write_tsv(tmp_path / "works_test.csv", works)

	monkeypatch.setattr(ol_adapter, "is_allowed", lambda t: True)

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(str(tmp_path), enabled={"works"}, max_aux=None))

	assert items[0].genres == []
	assert items[0].lc_classifications == ["QA76.9.A43"]


def test_text_builder_includes_lc():
	item = CanonicalItem(
		id="/works/1W",
		title="Title",
		lc_classifications=["PS3511.A867", "PZ7"],
	)
	text = build_text(item)
	assert "PS3511.A867" in text
	assert "PZ7" in text

	assert text.index("PS3511.A867") < text.index("PZ7")


def test_text_builder_omits_empty_lc():
	item = CanonicalItem(id="/works/1W", title="Title")
	text = build_text(item)
	assert text == "Title"
