#!/usr/bin/env python3
"""Stage extraction facts for the writer; no legacy anchor substitutions or live writes."""
import json
import sys
from pathlib import Path
from current import read_json


def main():
    bdir = Path(sys.argv[1])
    ext = {e['lead_id']: e for e in read_json(bdir / 'extract.json', [])}
    out = []
    for lead in read_json(bdir / 'leads.json', []):
        facts = ext.get(lead['lead_id'], {})
        country = str(facts.get('country') or lead.get('company_country') or lead.get('country') or '').strip().lower()
        foreign = bool(country) and country not in ('us', 'usa', 'united states', 'united states of america')
        skip = foreign or facts.get('is_in_niche') is False or lead.get('route') == 'SKIP'
        candidates = facts.get('achievements', [])
        out.append(dict(lead, tier='skip' if skip else (2 if candidates else 1),
                        angle=('skipped: foreign company' if foreign else 'skipped: off-niche') if skip else 'pending achievement review' if candidates else 'pending cold-read review',
                        facts=facts, source_url=''))
    (bdir / 'select.json').write_text(json.dumps(out, indent=2))
    print('[select] {} leads -> select.json'.format(len(out)))


if __name__ == '__main__':
    main()
