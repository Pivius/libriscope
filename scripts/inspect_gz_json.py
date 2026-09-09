# scripts/inspect_gz_json.py
import gzip, json, argparse, collections
from typing import Any

def load_sample(path: str, n: int):
	with gzip.open(path, "rt", encoding="utf-8") as fh:
		for i, line in enumerate(fh):
			line = line.strip()
			if not line:
				continue
			try:
				yield json.loads(line)
			except Exception:
				continue
			if i >= n-1:
				break

def summarize_sample(objs):
	key_counts = collections.Counter()
	key_types = {}
	samples = []
	for o in objs:
		samples.append(o)
		if isinstance(o, dict):
			for k, v in o.items():
				key_counts[k] += 1
				key_types.setdefault(k, set()).add(type(v).__name__)
	return samples, key_counts, key_types

def pretty_print(o: Any):
	print(json.dumps(o, indent=2, ensure_ascii=False))

def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("path")
	ap.add_argument("--sample", "-n", type=int, default=5)
	ap.add_argument("--show-keys", action="store_true")
	args = ap.parse_args()

	objs = list(load_sample(args.path, args.sample))
	if not objs:
		print("no JSON objects found in", args.path)
		return
	print(f"Printed {len(objs)} sample objects from {args.path}\n")
	for i, o in enumerate(objs):
		print(f"--- sample #{i+1} ---")
		pretty_print(o)
		print()

	samples, key_counts, key_types = summarize_sample(objs)
	if args.show_keys:
		print("Top-level key frequency (in sample):")
		for k, c in key_counts.most_common():
			types = ", ".join(sorted(key_types.get(k, [])))
			print(f"- {k}: {c} occurrences; types: {types}")

if __name__ == "__main__":
	main()