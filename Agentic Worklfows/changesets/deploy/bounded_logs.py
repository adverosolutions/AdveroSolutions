#!/usr/bin/env python3
"""A time-boxed read of ``modal app logs`` (the CLI streams forever while the app runs).

    cd "/Users/lorenzovillarreal/Desktop/AdveroSolutions/Agentic Worklfows"
    python3 changesets/deploy/bounded_logs.py --seconds 30                       # print 30 s of logs
    python3 changesets/deploy/bounded_logs.py --seconds 60 --grep "BASE_URL is unset" --count

Starts ``python3 -m modal app logs advero-reply-engine --timestamps``, reads
lines until the time is up, then stops the process. ``--count`` prints only
the number of matching lines (0 is the answer you want for an error string).
The primary evidence for the watch is changesets/deploy/watch_report.py; this
is for a quick look. It reads logs and writes nothing. Python 3.9.
"""
import argparse
import subprocess
import sys
import threading
import time
from typing import Callable, List, Optional

APP_NAME = "advero-reply-engine"


def read_bounded(seconds: float, popen: Callable = subprocess.Popen) -> List[str]:
    """Lines printed by `modal app logs` within ``seconds``; the process is
    always stopped, whatever happens."""
    proc = popen([sys.executable, "-m", "modal", "app", "logs", APP_NAME, "--timestamps"],
                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    lines = []  # type: List[str]

    def pump():
        for line in proc.stdout:
            lines.append(line.rstrip("\n"))

    reader = threading.Thread(target=pump)
    reader.daemon = True
    reader.start()
    try:
        reader.join(timeout=seconds)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return list(lines)


def main(argv: Optional[List[str]] = None, popen: Callable = subprocess.Popen) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--grep", help="keep only lines containing this text")
    parser.add_argument("--count", action="store_true", help="print only the number of kept lines")
    args = parser.parse_args(argv)
    lines = read_bounded(max(1.0, min(args.seconds, 600.0)), popen=popen)
    if args.grep:
        lines = [l for l in lines if args.grep in l]
    if args.count:
        print(len(lines))
    else:
        for line in lines:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
