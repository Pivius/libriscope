from typing import Iterable, Optional

from etl.adapters.ol_adapter import OpenLibraryCSVAdapter
from etl.core.text_builder import build_text
from etl.embeddings.batch import iter_batches


def run_pipeline(
    processed_dir: str,
    enabled: Optional[Iterable[str]] = None,
    batch_size: int = 32,
    write_db: bool = True,
    write_embeddings: bool = True,
    database_url: Optional[str] = None,
    max_aux: Optional[int] = 500000,
) -> int:
    """Collate raw TSV CSVs, build embedding text, embed, and (optionally) write to DB.

    Returns the number of processed CanonicalItems.
    """
    adapter = OpenLibraryCSVAdapter()

    store = None
    model = None
    if write_db or write_embeddings:
        from etl.embeddings.store import EmbeddingStore
        store = EmbeddingStore(database_url)
    if write_embeddings:
        from etl.embeddings.model import get_model
        model = get_model()

    count = 0
    items = adapter.collate_from_dir(processed_dir, enabled=enabled, max_aux=max_aux)

    for ids, batch in iter_batches(items, batch_size):
        vectors = None
        if model is not None:
            texts = [build_text(item) for item in batch]
            vectors = model.encode(texts, batch_size=batch_size)

        if store is not None:
            ids_to_vec = {}
            if vectors is not None:
                for id_, vec in zip(ids, vectors):
                    ids_to_vec[id_] = vec
            if write_db:
                store.bulk_upsert(batch, ids_to_vec)
            elif vectors is not None:
                for id_, vec in zip(ids, vectors):
                    store.upsert_embedding(id_, vec)

        count += len(batch)
    return count
