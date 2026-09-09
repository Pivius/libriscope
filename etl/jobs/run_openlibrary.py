import argparse
import os

from etl.core.pipeline import run_pipeline


def main() -> None:
	parser = argparse.ArgumentParser(description="Run OpenLibrary ingest ETL end-to-end.")
	parser.add_argument("--dir", "-d", default=os.environ.get("PROCESSED_DIR", "data/processed/openlibrary"))
	parser.add_argument("--batch-size", type=int, default=int(os.environ.get("BATCH_SIZE", "32")))
	parser.add_argument("--no-db", action="store_true", help="Skip writing works metadata to DB.")
	parser.add_argument("--no-embeddings", action="store_true", help="Skip embedding generation.")
	parser.add_argument("--max-aux", type=int, default=int(os.environ.get("MAX_AUX", "500000")))
	args = parser.parse_args()

	count = run_pipeline(
		processed_dir=args.dir,
		batch_size=args.batch_size,
		write_db=not args.no_db,
		write_embeddings=not args.no_embeddings,
		max_aux=args.max_aux,
	)
	print(f"Processed {count} items")


if __name__ == "__main__":
	main()
