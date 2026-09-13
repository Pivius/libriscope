"""Language filter configuration for the ETL pipeline.

The embedding model is English-centric, so non-English works produce poor
vectors and pollute the map. Works are filtered by detecting the language of
their title with fasttext (via ftlangdetect).

Note: ftlangdetect returns ISO 639-1 codes ("en"), not the ISO 639-2/B codes
("eng") that OpenLibrary editions use.
"""

from ftlangdetect import detect as _detect

# ISO 639-1 codes
ALLOWED_LANGUAGES: frozenset[str] = frozenset({"en"})

_MIN_TEXT_LEN = 3

def is_allowed(text: str) -> bool:
	"""Detect the language of `text` and return True if it is allowed.

	Undetectable or too-short text is skipped (conservative).
	"""
	if not text or len(text) < _MIN_TEXT_LEN:
		return False
	try:
		result = _detect(text, low_memory=True)
	except Exception:
		return False
	return result.get("lang") in ALLOWED_LANGUAGES
