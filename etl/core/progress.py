"""Unified progress bars and shell summaries."""

import time
from typing import Iterable, Optional

from tqdm import tqdm as _tqdm

_t0: float = time.monotonic()


def init() -> None:
	"""Start the run-wide clock used by `elapsed()` and `summary()`."""
	global _t0
	_t0 = time.monotonic()


def elapsed() -> str:
	"""Formatted seconds since `init()`: '58s'."""
	return f"{time.monotonic() - _t0:.0f}s"


def bar(iterable: Iterable, desc: str, total: Optional[int] = None, unit: str = "row", **kw):
	"""Standard tqdm bar: meaningful unit, fixed width, percentage + rate."""
	return _tqdm(iterable, desc=desc, total=total, unit=unit, ncols=100, **kw)


def summary(msg: str) -> None:
	"""Print a phase summary line with the run-wide elapsed time."""
	print(f"[{elapsed()}] {msg}", flush=True)
