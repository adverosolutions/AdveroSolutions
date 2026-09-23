#!/bin/bash
# Long watcher: polls every 2 min for up to 4h, logs only on CHANGE.
cd "$(dirname "$0")/.."
KEY=$(grep MILLIONVERIFIER .env | cut -d= -f2)
LAST=""
for i in $(seq 1 120); do
  R=$(curl -s "https://bulkapi.millionverifier.com/bulkapi/v2/fileinfo?key=$KEY&file_id=31726725")
  echo "$R" > verify/fileinfo.json
  CUR=$(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['status'],d['percent'],d['verified'])" 2>/dev/null)
  if [ "$CUR" != "$LAST" ]; then
    echo "$(date +%H:%M:%S) CHANGE -> $CUR" >> verify/watch.log
    LAST="$CUR"
  fi
  case "$CUR" in
    finished*) echo "$(date +%H:%M:%S) FINISHED" >> verify/watch.log; break;;
    error*|canceled*) echo "$(date +%H:%M:%S) HALTED $CUR" >> verify/watch.log; break;;
  esac
  python3 -c "import time;time.sleep(120)"
done
