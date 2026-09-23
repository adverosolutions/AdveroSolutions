"""Filesystem anchors for the shared library.

Every path the library writes to is derived from here so tests can redirect
the whole tree with one environment variable (ADVERO_TMP_DIR).
"""
import os
from pathlib import Path

# .../AdveroSolutions/Agentic Worklfows
BASE_DIR = Path(__file__).resolve().parent.parent
# .../AdveroSolutions
ROOT_DIR = BASE_DIR.parent

CONFIG_DIR = BASE_DIR / "config"
IDS_PATH = CONFIG_DIR / "ids.json"
OFFERS_PATH = CONFIG_DIR / "offers.md"
ENV_PATHS = (BASE_DIR / ".env", ROOT_DIR / ".env")


def tmp_dir() -> Path:
    """Directory for intermediate files. Defaults to <BASE_DIR>/.tmp.

    Override with ADVERO_TMP_DIR (the test conftest points it at a temp dir so
    tests never touch the real job log, shadow log or store).
    """
    override = os.environ.get("ADVERO_TMP_DIR")
    path = Path(override) if override else BASE_DIR / ".tmp"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


def tmp_file(name: str) -> Path:
    return tmp_dir() / name
