"""Local merge and QA only: never opens Sheets or clears flags."""
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
batch = Path(sys.argv[1]).resolve()
for script, args in [('daily_fill.py', ['--merge']), ('daily_apply.py', [])]:
    subprocess.run([sys.executable, str(ROOT / 'personalize' / script), str(batch)] + args, check=True)
