#!/bin/bash
cd "$(dirname "$0")/.."
KEY=$(grep MILLIONVERIFIER .env | cut -d= -f2)
for i in $(seq 1 240); do
  R=$(curl -s "https://bulkapi.millionverifier.com/bulkapi/v2/fileinfo?key=$KEY&file_id=31726725")
  echo "$R" > verify/fileinfo.json
  ST=$(echo "$R" | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])" 2>/dev/null)
  echo "$(date +%H:%M:%S) $(echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['status'],d['percent'],d['verified'])" 2>/dev/null)" >> verify/poll.log
  if [ "$ST" = "finished" ] || [ "$ST" = "error" ] || [ "$ST" = "canceled" ]; then echo DONE >> verify/poll.log; break; fi
  python3 -c "import time;time.sleep(15)"
done
