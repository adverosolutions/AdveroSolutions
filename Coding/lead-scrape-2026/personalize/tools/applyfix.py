"""Apply manual field/evidence fixes locally; never grants approval."""
import json
import sys
from pathlib import Path
batch, path = map(Path, sys.argv[1:3])
changes = json.loads(path.read_text())
records = json.loads((batch / 'x.json').read_text())
rewrite = []
for lid, fields in changes.get('fix', {}).items():
    if 'y' in fields:
        raise SystemExit('Retired Y fixes are not supported')
    records[lid].update(fields)
existing = batch / 'x_rewrite_9.json'
prior = {r['lead_id']: r for r in json.loads(existing.read_text())} if existing.exists() else {}
for lid in changes.get('fix', {}):
    prior[lid] = dict(records[lid], lead_id=lid)
existing.write_text(json.dumps(list(prior.values()), indent=2))
selections = json.loads((batch / 'select.json').read_text())
for row in selections:
    if row['lead_id'] in changes.get('skip', {}):
        row.update(tier='skip', angle='skipped: ' + changes['skip'][row['lead_id']])
(batch / 'select.json').write_text(json.dumps(selections, indent=2))
print('Manual fixes staged; re-merge and review. Changed records invalidate prior review digests.')
