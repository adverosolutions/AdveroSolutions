"""Compatibility entrypoint: review locally; never auto-approve or write to Sheets."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name('review.py')), run_name='__main__')
