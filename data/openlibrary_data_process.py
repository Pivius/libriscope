"""
This script processes the bulk download data from the Open Library project.
It converts the large text files into smaller csv files which are easier to load into the db.
Decide how large you would like to make each chunk using LINES_PER_FILE
For editions, 3 million lines was about 3.24 gigs and about an hour to load.
"""
# https://github.com/LibrariesHacked/openlibrary-search/blob/main/openlibrary_data_process.py

import csv
import gzip
import ctypes as ct
from multiprocessing import Pool
import os

# Optional if you want to make a smaller copy from the unzipped version for testing
# sed -i '' '100000,$ d' ./data/raw/openlibrary/ol_dump_editions.txt

# You can run this file once with all 3 downloaded and unzipped files or run it as they come in.
# Just make sure the end product in filenames.txt  looks like this
# authors	0	False	{authors_2000.csv,authors_4000.csv,authors_6000.csv}
# works	1	False	{works_2000.csv,works_4000.csv,works_6000.csv,works_8000.csv}
# editions	2	False	{editions_2000.csv,editions_4000.csv,editions_6000.csv}

# Field size limit: See https://stackoverflow.com/a/54517228 for more info on this setting
csv.field_size_limit(int(ct.c_ulong(-1).value // 2))

LINES_PER_FILE = 2000000

INPUT_PATH = "./data/raw/openlibrary/"
OUTPUT_PATH = "./data/processed/openlibrary"
FILE_IDENTIFIERS = ["authors", "works", "editions", "wikidata", "redirects", "deletes", "reading-log", "ratings", "covers_metadata"]
FILE_LAYOUTS = {
	"authors": (["type", "key", "revision", "last_modified", "json"], True),
	"works": (["type", "key", "revision", "last_modified", "json"], True),
	"editions": (["type", "key", "revision", "last_modified", "json"], True),
	"wikidata": (["wikidata_id", "json"], True),
	"redirects": (["type", "key", "revision", "last_modified", "json"], True),
	"deletes": (["type", "key", "revision", "last_modified", "json"], True),
	"reading-log": (["work_key", "edition_key", "shelf", "date"], False),
	"ratings": (["work_key", "edition_key", "rating", "date"], False),
	"covers_metadata": (["id", "width", "height", "created"], False),
}

def process_file(source_file: str, file_id) -> None:
	"""
	Processes a single file by chunking it into smaller csv files.
	Supports .txt and .txt.gz (or .gz) input files.
	"""
	print(f"Currently processing {source_file}")

	base_path = os.path.join(INPUT_PATH, f"ol_dump_{source_file}.txt")
	gz_path = base_path + ".gz"

	if os.path.exists(gz_path):
		input_path = gz_path
		opener = lambda p: gzip.open(p, mode="rt", encoding="utf-8", errors="ignore")
	elif os.path.exists(base_path):
		input_path = base_path
		opener = lambda p: open(p, encoding="utf-8", errors="ignore")
	else:
		print(f"Source not found: {base_path} or {gz_path}")
		return

	filenames = []
	writer = None
	output_fh = None

	try:
		with opener(input_path) as csv_input_file:
			reader = csv.reader(csv_input_file, delimiter="\t")

			for line, row in enumerate(reader):
				# Every time the row limit is reached, open a new chunked csv file
				if line % LINES_PER_FILE == 0:
					# close previous chunk file if open
					if output_fh is not None:
						output_fh.close()

					chunked_filename = source_file + f"_{line + LINES_PER_FILE}.csv"
					filenames.append(chunked_filename)
					output_fh = open(
						os.path.join(OUTPUT_PATH, chunked_filename),
						"w",
						newline="",
						encoding="utf-8",
					)
					writer = csv.writer(
						output_fh, delimiter="\t", quotechar="|", quoting=csv.QUOTE_MINIMAL
					)

				# determine expected layout for this source file
				cols, json_last = FILE_LAYOUTS.get(
					source_file,
					(["type", "key", "revision", "last_modified", "json"], True),
				)
				expected = len(cols)

				if writer is not None:
					if json_last:
						if len(row) >= expected:
							first = row[: expected - 1]
							last = "\t".join(row[expected - 1 :])
							out_row = first + [last]
						else:
							out_row = row + [""] * (expected - len(row))
					else:
						out_row = row[:expected] + [""] * max(0, expected - len(row))

					writer.writerow(out_row)
	finally:
		if output_fh is not None:
			output_fh.close()

	# append filenames metadata
	with open(
		os.path.join(OUTPUT_PATH, "filenames.txt"), "a", newline="", encoding="utf-8"
	) as filenames_output:
		filenames_writer = csv.writer(
			filenames_output, delimiter="\t", quotechar="|", quoting=csv.QUOTE_MINIMAL
		)
		filenames_writer.writerow(
			[source_file, file_id, False, "{" + ",".join(filenames).strip("'") + "}"]
		)
		print(f"{source_file} text file has now been processed")


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(
		description="Process OpenLibrary dump files (optionally select specific identifiers)."
	)
	parser.add_argument(
		"--only",
		"-o",
		help="Comma-separated identifiers to process (e.g. ratings,wikidata). Defaults to all.",
		default=None,
	)
	args = parser.parse_args()

	if args.only:
		requested = [s.strip() for s in args.only.split(",") if s.strip()]
		targets = [t for t in requested if t in FILE_IDENTIFIERS]
		unknown = [t for t in requested if t not in FILE_IDENTIFIERS]
		if unknown:
			print(f"Warning: unknown identifiers ignored: {', '.join(unknown)}")
		if not targets:
			print("No valid identifiers to process. Exiting.")
			raise SystemExit(1)
	else:
		targets = FILE_IDENTIFIERS

	with Pool() as pool:
		results = []
		for filename in targets:
			file_id = FILE_IDENTIFIERS.index(filename)
			results.append(pool.apply_async(process_file, args=(filename, file_id)))
		for res in results:
			res.wait()
	print("Process complete")