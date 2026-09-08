from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class CanonicalItem:
    # identity
    id: str  # OpenLibrary work key

    # core metadata
    title: str # type/works
    subtitle: Optional[str] = None # type/works

    # semantic fields (IMPORTANT for embeddings)
    description: Optional[str] = None # type/works
    first_sentence: Optional[str] = None # type/works

    subjects: List[str] = field(default_factory=list) # type/works
    genres: List[str] = field(default_factory=list) # type/editions

    # authors simplified (no nested role objects)
    authors: List[str] = field(default_factory=list) # type/works

    # language normalization (ISO code like "eng")
    languages: List[str] = field(default_factory=list) # type/editions

    # publication signals (lightweight, optional ranking features later)
    first_publish_date: Optional[str] = None # type/works

    # extra enrichment
    series: List[str] = field(default_factory=list) # type/editions

    # raw safety net (optional debugging / reprocessing)
    raw: Optional[Dict[str, Any]] = None

    # embedding input (computed, NOT stored in DB ideally)
    embedding_text: Optional[str] = None