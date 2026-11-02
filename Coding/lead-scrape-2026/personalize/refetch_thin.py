#!/usr/bin/env python3
"""Retry thin research without replacing complete retained pages with truncated text."""
import json
import sys
from pathlib import Path
from current import read_json
from research import collect, save
batch = Path(sys.argv[1])
leads = read_json(batch / 'leads.json', [])
for lead in leads:
    old = read_json(batch / (lead['lead_id'] + '.research.json'), {})
    if sum(len(p['text']) for p in old.get('pages', [])) >= 300:
        continue
    result = collect(lead.get('company_website', ''))
    if sum(len(p['text']) for p in result['pages']) < sum(len(p['text']) for p in old.get('pages', [])):
        result = old
    text, urls = save(batch, lead['lead_id'], result)
    lead.update(text_file=lead['lead_id'] + '.txt', source_urls=urls,
                route='TIER2_CANDIDATE' if text else 'TIER1_ONLY')
(batch / 'leads.json').write_text(json.dumps(leads, indent=2))
print('[refetch] research retained with fetch diagnostics')
