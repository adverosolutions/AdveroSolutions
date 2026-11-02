#!/usr/bin/env python3
"""Stage grounded achievement fill records, or --merge writer JSON locally."""
import json
import sys
from pathlib import Path
from current import read_json, render

CHUNK = 12


def main():
    bdir = Path(sys.argv[1])
    selections = {s['lead_id']: s for s in read_json(bdir / 'select.json', [])}
    leads = {l['lead_id']: l for l in read_json(bdir / 'leads.json', [])}
    if '--merge' in sys.argv:
        records = {}
        files = sorted(bdir.glob('x_[0-9]*.json')) + sorted(bdir.glob('x_rewrite*.json'))
        for path in files:
            seen = set()
            for item in read_json(path, []):
                lid = item['lead_id']
                if lid not in leads or lid in seen or ('rewrite' not in path.name and lid in records):
                    raise ValueError('unknown or duplicate lead id in ' + str(path))
                seen.add(lid)
                records[lid] = {k: v for k, v in item.items() if k != 'lead_id'}
        lines = []
        for lid, selection in selections.items():
            if selection['tier'] == 'skip':
                continue
            rec = records.get(lid, {})
            try:
                line = render(leads[lid].get('first_name', ''), rec)
            except (ValueError, KeyError):
                line = ''  # The gate reports missing or retired fields; never reuse an old line.
            lines.append({'lead_id': lid, 'icebreaker': line, 'mode': rec.get('mode', ''),
                          'x_evidence': rec.get('x_evidence', {}),
                          'specific_evidence': rec.get('specific_evidence', {})})
        (bdir / 'x.json').write_text(json.dumps(records, indent=2))
        (bdir / 'lines.json').write_text(json.dumps(lines, indent=2))
        print('[fill] merged {} records -> x.json, lines.json'.format(len(records)))
        return
    extracts = {e['lead_id']: e for e in read_json(bdir / 'extract.json', [])}
    rows = []
    for lid, selection in selections.items():
        if selection['tier'] == 'skip':
            continue
        lead = leads[lid]
        rows.append(dict(lead, extraction=extracts.get(lid, {}),
                         research=read_json(bdir / (lid + '.research.json'), {})))
    for path in bdir.glob('fill_chunk_*.json'):
        path.unlink()
    for i in range(0, len(rows), CHUNK):
        (bdir / ('fill_chunk_{}.json'.format(i // CHUNK))).write_text(json.dumps(rows[i:i + CHUNK], indent=2))
    print('[fill] {} leads -> {} fill chunks'.format(len(rows), (len(rows) + CHUNK - 1) // CHUNK))


if __name__ == '__main__':
    main()
