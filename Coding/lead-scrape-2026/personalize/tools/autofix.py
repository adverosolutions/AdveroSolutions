"""Stage explicit manual fixes; never invent copy or rotate achievement/fallback text."""
import json
import sys
from pathlib import Path
batch = Path(sys.argv[1])
manual = json.loads(Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else {'fix': {}, 'skip': {}}
if any('y' in fields for fields in manual.get('fix', {}).values()):
    raise SystemExit('Retired Y fixes are not supported')
path = batch / ('fix_' + batch.name + '.json')
path.write_text(json.dumps(manual, indent=2))
print('Staged explicit manual fixes:', path)
