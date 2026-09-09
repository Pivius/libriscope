import argparse
import os

from etl.core.pipeline import run_pipeline


def main() -> None:
	parser = argparse.ArgumentParser(description="Recompute embeddings for existing works (metadata-only, no upsert).")
	parser.add_argument("--dir", "-d", default=os.environ.get("PROCESSED_DIR", "data/processed/openlibrary"))
	parser.add_argument("--batch-size", type=int, default=int(os.environ.get("BATCH_SIZE", "32")))
	parser.add_argument("--max-aux", type=int, default=int(os.environ.get("MAX_AUX", "500000")))
	args = parser.parse_args()

	count = run_pipeline(
		processed_dir=args.dir,
		batch_size=args.batch_size,
		write_db=False,
		write_embeddings=True,
		max_aux=args.max_aux,
	)
	print(f"Rebuilt embeddings for {count} works")


if __name__ == "__main__":
	main()
