from typing import Iterable, Iterator
from etl.core.canonical import CanonicalItem

class DatasetAdapter:
	"""Adapter must implement stream_<dump>(gz_path) -> Iterator[CanonicalItem]."""
	def stream_dump(self, dump_name: str, file_path: str) -> Iterator[CanonicalItem]:
		raise NotImplementedError
	
	"""Helper to collate items from multiple dump files in a directory."""
	def find_files(self, root: str, dump_name: str) -> Iterator[str]:
		raise NotImplementedError
	
	"""Collate items from multiple dump files in a directory, filtered by enabled dump names."""
	def collate_from_directory(self, root: str, enabled: Iterable[str]) -> Iterator[CanonicalItem]:
		raise NotImplementedError