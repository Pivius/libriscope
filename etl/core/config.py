import os
from pathlib import Path

_loaded = False


def load_env() -> None:
	"""Load .env from the project root into os.environ."""
	global _loaded
	if _loaded:
		return
	try:
		from dotenv import load_dotenv
	except ImportError:
		return

	# search upward from cwd for a .env file
	root = Path.cwd()
	for candidate in [root / ".env", root / "etl" / ".env"]:
		if candidate.exists():
			load_dotenv(candidate)
			break
	_loaded = True


def get_env(name: str, default: str = "") -> str:
	load_env()
	return os.environ.get(name, default)
