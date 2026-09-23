"""Command line: spec in, HTML mockup out, browser tab open.

Deliberately thin. Everything that decides how the page looks lives in
render.py and theme.py; this file only handles files, flags and the one-line
report that gets read at speed.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import List, Optional

from .render import render
from .spec import PLATFORMS, MockupSpec, SpecError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "out")


def slugify(text: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "mockup"


def open_in_browser(path: str, browser: Optional[str]) -> bool:
    command = ["open"]
    if browser:
        command += ["-a", browser]
    command.append(path)
    try:
        return subprocess.call(command) == 0
    except (OSError, subprocess.SubprocessError):
        return False


def build_one(spec: MockupSpec, out_dir: str) -> str:
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(
        out_dir, "{}.{}.html".format(slugify(spec.title), spec.platform))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(spec))
    return path


def cmd_build(args: argparse.Namespace) -> int:
    try:
        raw_spec = MockupSpec.load(args.spec)
    except (SpecError, OSError) as exc:
        print("\n  spec rejected: {}\n".format(exc), file=sys.stderr)
        return 1

    platforms: List[str] = list(PLATFORMS) if args.both else [
        args.platform or raw_spec.platform]

    paths = []
    warnings = raw_spec.validate()
    for platform in platforms:
        raw_spec.platform = platform
        paths.append(build_one(raw_spec, args.out or OUT_DIR))

    print("\n  {}".format(raw_spec.title))
    print("  {} cards · {}".format(
        raw_spec.card_count, " + ".join(platforms)))
    for path in paths:
        print("  {}".format(os.path.relpath(path, ROOT)))

    if warnings:
        print("\n  notes:")
        for warning in warnings:
            print("    - {}".format(warning))

    if not args.no_open:
        for path in paths:
            open_in_browser(path, args.browser)
        print("\n  opened in the browser — full-screen the tab before recording")
    print("")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mockup",
        description="Render an automation spec as a GoHighLevel or Zapier "
                    "builder mockup for a proposal recording.")
    sub = parser.add_subparsers(dest="command")

    build = sub.add_parser("build", help="render a spec")
    build.add_argument("spec", help="path to a spec JSON file")
    build.add_argument("--platform", choices=PLATFORMS,
                       help="override the spec's platform")
    build.add_argument("--both", action="store_true",
                       help="render both platforms from the one spec")
    build.add_argument("--out", help="output directory (default ./out)")
    build.add_argument("--browser", help="app name, e.g. Arc")
    build.add_argument("--no-open", action="store_true",
                       help="write the file without opening a tab")
    build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)
