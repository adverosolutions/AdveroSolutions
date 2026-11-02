#!/bin/zsh
# pick_rounds.sh <rounds>: pick 100 per niche per round, refetch thin pages, write _chunks.json, print READY
cd "${0:A:h}/../.." || exit 1
for r in $(seq 1 $1); do
for n in recruiting bookkeeping cleaning; do
  out=$(python3 personalize/daily_pick.py --n 100 --niche $n 2>&1 | grep -v -i warn)
  echo "$out" | grep "\[pick\] batch\|Traceback\|Error"
  B=$(echo "$out" | sed -n 's/.*\[pick\] dir: //p' | tail -1)
  [ -z "$B" ] && { echo "NOBATCH $n"; continue; }
  B=${B#$PWD/}
  cnt=$(python3 -c "import json;print(len(json.load(open('$B/leads.json'))))")
  [ "$cnt" = 0 ] && { echo "EMPTY $n $B"; continue; }
  python3 personalize/refetch_thin.py $B 2>&1 | grep -v -i warn | tail -1
  python3 - "$B" <<'EOF'
import json,collections,csv,sys
B=sys.argv[1]
leads=json.load(open(B+'/leads.json'))
ids=[l['lead_id'] for l in leads if l['route']=='TIER2_CANDIDATE']
chunks=[ids[i:i+12] for i in range(0,len(ids),12)]
json.dump(chunks,open(B+'/_chunks.json','w'))
print('READY',B.split('/')[-1],dict(collections.Counter(l['campaign'] for l in leads)),'mv',dict(collections.Counter(l.get('mv_result') for l in leads)),'tier2',len(ids),'chunks',[len(c) for c in chunks], flush=True)
EOF
  sleep 61
done; done
echo ROUNDS_DONE
