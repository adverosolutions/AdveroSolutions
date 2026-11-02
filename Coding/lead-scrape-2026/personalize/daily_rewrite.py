#!/usr/bin/env python3
"""Stage failed current records for a writer's correction; merge via daily_fill.py."""
import json
import sys
from pathlib import Path
from daily_apply import review
from current import read_json
if '--merge' in sys.argv:
    raise SystemExit('Write x_rewrite_<n>.json with full records, then daily_fill.py <batch> --merge')
batch = Path(sys.argv[1])
leads = {r['lead_id']: r for r in read_json(batch / 'leads.json', [])}
rows = [dict(r, lead=leads[r['lead_id']], research=read_json(batch / (r['lead_id'] + '.research.json'), {}))
        for r in review(batch) if r['status'] == 'held']
(batch / 'rewrite_needed.json').write_text(json.dumps(rows, indent=2))
print('[rewrite] {} held records -> rewrite_needed.json; two writer passes max, then hand review'.format(len(rows)))
