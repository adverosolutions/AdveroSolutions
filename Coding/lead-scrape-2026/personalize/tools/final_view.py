"""Display every rendered line, evidence and gate result, without live writes."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from daily_apply import review
for row in review(Path(sys.argv[1])):
    print('{} [{}] {} | {}'.format(row['lead_id'], row['status'], row['company_name'], row['reason']))
    print(row['personalization'])
    print(json.dumps(row['record'], ensure_ascii=False))
    print('Review digest:', row['review_digest'])
