import argparse
import os

from etl.core.pipeline import run_pipeline


def _env_int(name: str, default: int) -> int:
		raw = os.environ.get(name)
		if raw is None or raw.strip() == "":
			return default
		return int(raw)


def main() -> None:
	parser = argparse.ArgumentParser(description="Run OpenLibrary ingest ETL end-to-end.")
	parser.add_argument("--dir", "-d", default=os.environ.get("PROCESSED_DIR", "data/processed/openlibrary"))
	parser.add_argument("--batch-size", type=int, default=_env_int("BATCH_SIZE", 64))
	parser.add_argument("--embed-batch-size", type=int, default=None,
		help="GPU encode chunk size (default EMBED_BATCH_SIZE=192). This is the throughput knob.")
	parser.add_argument("--max-seq-length", type=int, default=None,
		help="Max tokens per text for the embedder (default 512). Lowering speeds up long-tail batches.")
	parser.add_argument("--no-db", action="store_true", help="Skip writing works metadata to DB.")
	parser.add_argument("--no-embeddings", action="store_true", help="Skip embedding generation.")
	parser.add_argument("--max-aux", type=int, default=_env_int("MAX_AUX", 500000))
	parser.add_argument("--max-works", type=int, default=None,
		help="Stop after embedding this many NEW works. Unset (or MAX_WORKS env) = process everything remaining.")
	parser.add_argument("--no-skip", action="store_true", default=False,
		help="Re-embed works that already have embeddings (default is to continue/skip them).")
	parser.add_argument("--reset", "-r", action="store_true",
		help="Truncate all DB tables first, then process from scratch.")
	parser.add_argument("--skip-editions", action="store_true",
		help="Stream works only: skip the editions (+authors) index pre-pass. Much faster, "
			"but loses edition-enriched metadata (languages, edition subjects/authors, merged dates).")
	args = parser.parse_args()

	max_works = args.max_works if args.max_works is not None else _env_int("MAX_WORKS", 0) or None

	enabled = None
	if args.skip_editions:
		enabled = {"works", "deletes", "redirects"}

	count = run_pipeline(
		processed_dir=args.dir,
		enabled=enabled,
		batch_size=args.batch_size,
		write_db=not args.no_db,
		write_embeddings=not args.no_embeddings,
		max_aux=args.max_aux,
		max_works=max_works,
		skip_existing=not args.no_skip,
		reset_db=args.reset,
		embed_batch_size=args.embed_batch_size,
		max_seq_length=args.max_seq_length,
	)
	print(f"Processed {count} items")


if __name__ == "__main__":
	main()
