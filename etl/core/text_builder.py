from typing import List
from etl.core.canonical import CanonicalItem


class TextBuilder:
	"""Deterministically build embedding input text from a CanonicalItem."""

	def build(self, item: CanonicalItem) -> str:
		parts: List[str] = [
			item.title or "",
			item.subtitle or "",
			item.description or "",
			item.first_sentence or "",
			" ".join(sorted(item.subjects)) if item.subjects else "",
			" ".join(sorted(item.genres)) if item.genres else "",
			" ".join(item.authors) if item.authors else "",
			" ".join(item.series) if item.series else "",
			item.first_publish_date or "",
		]
		return " ".join(p for p in parts if p and p.strip())


_builder = TextBuilder()


def build_text(item: CanonicalItem) -> str:
	return _builder.build(item)
