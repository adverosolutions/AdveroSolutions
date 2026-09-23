#!/bin/bash
cd "$(dirname "$0")/.."
KEY=$(grep MILLIONVERIFIER .env | cut -d= -f2)
LAST=""
for i in $(seq 1 150); do
  R=$(curl -s "https://bulkapi.millionverifier.com/bulkapi/v2/fileinfo?key=$KEY&file_id=31730178")
  echo "$R" > verify/fileinfo_w2.json
  CUR=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['status'],d['percent'],d['verified'])" 2>/dev/null)
  [ "$CUR" != "$LAST" ] && { echo "$(date +%H:%M:%S) $CUR" >> verify/watch2.log; LAST="$CUR"; }
  case "$CUR" in finished*) echo "FINISHED" >> verify/watch2.log; break;; error*|canceled*) echo "HALTED" >> verify/watch2.log; break;; esac
  python3 -c "import time;time.sleep(20)"
done
