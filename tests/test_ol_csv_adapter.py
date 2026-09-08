# tests/test_ol_csv_adapter.py
from pathlib import Path
from etl.adapters.ol_adapter import OpenLibraryCSVAdapter

def test_collate_from_test_dir():
	root = Path("data/processed/openlibrary/test")
	assert root.exists(), f"{root} not found; put your small CSVs there"

	adapter = OpenLibraryCSVAdapter()
	items = list(adapter.collate_from_dir(str(root), enabled=["works","editions","authors"], max_aux=None))

	assert items, "collate_from_dir returned no CanonicalItem"
	ci = items[0]
	assert isinstance(ci.id, str) and ci.id
	assert isinstance(ci.title, str)
	assert ci.embedding_text is None or isinstance(ci.embedding_text, str)