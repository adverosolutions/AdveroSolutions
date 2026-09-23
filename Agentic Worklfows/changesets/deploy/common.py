"""Shared plumbing for the deploy scripts. Python 3.9."""
import os
import sys
from typing import Callable, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.dirname(HERE))          # .../Agentic Worklfows
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

WEB_URL_NAME = "web_url.txt"     # written by install_schedules.sh --deploy


def tmp_subdir(name: str) -> str:
    """<.tmp>/<name>, honouring ADVERO_TMP_DIR like every other writer."""
    from shared.paths import tmp_dir

    path = os.path.join(str(tmp_dir()), name)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def deploy_tmp() -> str:
    return tmp_subdir("deploy")


def web_url_file() -> str:
    return os.path.join(deploy_tmp(), WEB_URL_NAME)


def confirm_from_tty(expected: str, prompt: str, opener: Optional[Callable] = None) -> bool:
    """Ask for a typed word on the controlling terminal, never stdin.

    stdin can be a pipe (``echo CREATE | ...``); /dev/tty is the person at the
    keyboard. With no terminal (an agent session, cron) this refuses."""
    opener = opener or open
    try:
        with opener("/dev/tty", "r+") as tty:
            tty.write("%s [type %s] " % (prompt, expected))
            tty.flush()
            answer = tty.readline().strip()
    except OSError:
        sys.stderr.write("no terminal to confirm on; refusing (run this from your own terminal)\n")
        return False
    return answer == expected
