"""Show company cap failures from the same local gate used for export."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from daily_apply import review
for row in review(Path(sys.argv[1])):
    if 'duplicate company' in row['reason']:
        print(row['lead_id'], row['reason'])
