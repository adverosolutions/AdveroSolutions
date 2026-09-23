#!/bin/bash
cd "$(dirname "$0")/.."
KEY=$(grep MILLIONVERIFIER .env | cut -d= -f2); FID=31966348
for i in $(seq 1 240); do
  R=$(curl -s "https://bulkapi.millionverifier.com/bulkapi/v2/fileinfo?key=$KEY&file_id=$FID")
  ST=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['status'],d['percent'],d['verified'])" 2>/dev/null)
  echo "$(date +%H:%M:%S) $ST" >> verify/watch_cl3.log
  case "$ST" in
    finished*) curl -s "https://bulkapi.millionverifier.com/bulkapi/v2/download?key=$KEY&file_id=$FID&filter=all" -o verify/results_cl3.csv
               python3 - <<'PY'
import csv
from collections import Counter
new=list(csv.DictReader(open('verify/results_cl3.csv',encoding='utf-8-sig')))
seen={r['email'].strip().lower() for r in csv.DictReader(open('verify/results.csv',encoding='utf-8-sig'))}
with open('verify/results.csv','a',newline='',encoding='utf-8-sig') as fh:
    w=csv.DictWriter(fh,fieldnames=['email','quality','result','free','role'])
    for r in new:
        if r['email'].strip().lower() not in seen: w.writerow({k:r.get(k,'') for k in w.fieldnames})
c=Counter(r['result'] for r in new); n=len(new)
open('verify/watch_cl3.log','a').write(f"DONE cleaning-3: {dict(c)} clean={100*c['ok']//n}%\n")
PY
               python3 merge_verified.py >> verify/watch_cl3.log 2>&1
               python3 deliver_final.py  >> verify/watch_cl3.log 2>&1
               echo "FINAL FILES BUILT" >> verify/watch_cl3.log
               break;;
    error*|canceled*) echo "HALTED" >> verify/watch_cl3.log; break;;
  esac
  python3 -c "import time;time.sleep(60)"
done
