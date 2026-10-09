"""xcheck.py <batch>: flag extract_<k>.json chunks that look script-made or pasted (dupe/pasted what_it_is, missing ids)"""
import json,glob,os,sys,re,collections
B=sys.argv[1].rstrip("/"); chunks=json.load(open(B+"/_chunks.json"))
for k,ids in enumerate(chunks):
    f=f"{B}/extract_{k}.json"
    if not os.path.exists(f): print(k,"MISSING"); continue
    try: d=json.load(open(f))
    except Exception as e: print(k,"BADJSON",e); continue
    got={r.get("lead_id") for r in d}; miss=[i for i in ids if i not in got]
    w=[(r.get("what_it_is") or "").strip() for r in d]
    dup=sum(c-1 for c in collections.Counter(x for x in w if x).values() if c>1)
    pasted=sum(1 for x in w if re.search(r"\[HOME|\[ABOUT|-->|https?://|☎|\|",x))
    generic=sum(1 for x in w if re.match(r"^An? [a-z ]+(company|provider|agency|broker|firm) (serving|offering|providing)",x))
    bad = miss or dup>2 or pasted>2 or generic>5
    print(k, "BAD" if bad else "ok", f"n={len(d)} miss={len(miss)} dup={dup} pasted={pasted} generic={generic}")
