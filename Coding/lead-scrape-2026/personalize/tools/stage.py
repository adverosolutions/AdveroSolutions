"""Local extraction/selection/fill staging; all prompts stay in the batch folder."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = Path(__file__).resolve().parent / 'prompts'
sys.path.insert(0, str(ROOT / 'personalize'))
from current import read_json

cmd, batch_arg = sys.argv[1:3]
batch = Path(batch_arg).resolve()
if cmd == 'merge':
    wanted = [lid for chunk in read_json(batch / '_chunks.json', []) for lid in chunk]
    rows = {}
    for path in sorted(batch.glob('extract_[0-9]*.json')):
        for row in read_json(path, []):
            lid = row['lead_id']
            if lid in rows or lid not in wanted:
                raise SystemExit('Duplicate or unknown extraction id: ' + lid)
            rows[lid] = row
    if set(wanted) != set(rows):
        raise SystemExit('Missing extraction ids: ' + str(sorted(set(wanted) - set(rows))))
    (batch / 'extract.json').write_text(json.dumps(list(rows.values()), indent=2))
    print('merged', len(rows))
    for row in rows.values():
        if row.get('is_in_niche') is False:
            print('OFF-NICHE', row['lead_id'], row.get('what_it_is', ''))
elif cmd == 'fill':
    niche = sys.argv[3]
    restore = set(sys.argv[4:])
    extracts = read_json(batch / 'extract.json', [])
    for row in extracts:
        if row['lead_id'] in restore:
            row['is_in_niche'] = True
    (batch / 'extract.json').write_text(json.dumps(extracts, indent=2))
    for script in ('daily_select.py', 'daily_fill.py'):
        subprocess.run([sys.executable, str(ROOT / 'personalize' / script), str(batch)], check=True)
    template = (PROMPTS / ('fill_' + niche + '.txt')).read_text()
    for path in sorted(batch.glob('fill_chunk_*.json')):
        k = path.stem.removeprefix('fill_chunk_')
        text = template.replace('BATCHDIR', str(batch)).replace('fill_chunk_K', path.stem).replace('x_K.json', 'x_' + k + '.json').replace('NN', str(len(read_json(path, []))))
        (batch / ('prompt_fill_' + k + '.txt')).write_text(text)
    print('Fill prompts in', batch)
elif cmd == 'prompts_extract':
    niche = sys.argv[3]
    template = (PROMPTS / ('extract_' + niche + '.txt')).read_text()
    for k, ids in enumerate(read_json(batch / '_chunks.json', [])):
        text = template.replace('BATCHDIR', str(batch)).replace('list[K]', 'list[{}]'.format(k)).replace('extract_K.json', 'extract_{}.json'.format(k))
        (batch / ('prompt_extract_{}.txt'.format(k))).write_text(text + '\nExact lead ids: ' + json.dumps(ids))
    print('Extraction prompts in', batch)
else:
    raise SystemExit('Use merge, fill or prompts_extract')
