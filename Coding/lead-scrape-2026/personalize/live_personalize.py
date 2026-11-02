#!/usr/bin/env python3
"""Compatibility entrypoint for reviewed batches; no model API calls.

Usage: python3 personalize/live_personalize.py <batch_dir> [--write-sheet]
Generate extraction/fill JSON in the current Codex session using DAILY_RUN.md.
The former per-row paid-model generator has been retired.
"""
import runpy
from pathlib import Path

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('daily_apply.py')), run_name='__main__')
