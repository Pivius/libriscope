from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class CanonicalItem:
	# identity
	id: str  # OpenLibrary work key

	# core metadata
	title: str # type/works
	subtitle: Optional[str] = None # type/works

	# semantic fields
	description: Optional[str] = None # type/works
	first_sentence: Optional[str] = None # type/works

	subjects: List[str] = field(default_factory=list) # type/works
	genres: List[str] = field(default_factory=list) # type/works (lc_classifications fallback)

	# authors simplified (no nested role objects)
	authors: List[str] = field(default_factory=list) # type/works

	# language detected via fasttext on the title (ISO 639-1 mapped label)
	languages: List[str] = field(default_factory=list)

	# publication signals (lightweight, optional ranking features later)
	first_publish_date: Optional[str] = None # type/works

	# extra
	series: List[str] = field(default_factory=list) # type/works

	# raw safety net (optional debugging / reprocessing)
	raw: Optional[Dict[str, Any]] = None

	# embedding input, NOT stored in DB
	embedding_text: Optional[str] = None