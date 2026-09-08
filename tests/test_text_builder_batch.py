from etl.core.canonical import CanonicalItem
from etl.core.text_builder import build_text
from etl.embeddings.batch import iter_batches


def test_build_text_includes_semantic_fields():
	ci = CanonicalItem(
		id="/works/OL1W",
		title="Dune",
		description="A story about a desert planet.",
		subjects=["Science fiction", "Space"],
		authors=["Frank Herbert"],
	)
	text = build_text(ci)
	assert "Dune" in text
	assert "desert planet" in text
	assert "Science fiction" in text
	assert "Frank Herbert" in text


def test_build_text_omits_blank_fields():
	ci = CanonicalItem(id="/works/OL2W", title="")
	assert build_text(ci) == ""


def test_iter_batches_chunks_and_final_partial():
	items = [CanonicalItem(id=f"/works/{i}W", title=str(i)) for i in range(5)]
	batches = list(iter_batches(items, 2))
	ids = [i for _, batch in batches for i in [c.id for c in batch]]

	assert len(batches) == 3
	assert ids == [f"/works/{i}W" for i in range(5)]
	assert len(batches[0][1]) == 2
	assert len(batches[1][1]) == 2
	assert len(batches[2][1]) == 1
