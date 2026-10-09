import json,re,subprocess,sys,os,time
B=sys.argv[1]
misses=0
for it in range(25):
    subprocess.run(["python3","personalize/daily_fill.py",B,"--merge"],capture_output=True,text=True)
    out=subprocess.run(["python3","personalize/daily_apply.py",B],capture_output=True,text=True).stdout
    summary=[l for l in out.splitlines() if "[apply]" in l]
    if not summary:
        misses+=1
        print(f"iter {it}: no [apply] line (sheet rate limit?), retry {misses}")
        if misses>5: sys.exit("daily_apply kept failing")
        time.sleep(30); continue
    flag=set()
    grab=False
    for line in out.splitlines():
        if "flagged:" in line: grab=True
        if grab or re.match(r"\s+[A-Z]{2}-\d{5} \[",line):
            for m in re.finditer(r"([A-Z]{2}-\d{5})",line):
                seg=line[m.end():m.end()+120]
                if "foreign" not in seg: flag.add(m.group(1))
    print(f"iter {it}: {summary[-1] if summary else out[-200:]} | flagged(non-foreign)={sorted(flag)}")
    if not flag: break
    x=json.load(open(B+"/x.json")); r9=json.load(open(B+"/x_rewrite_9.json")) if os.path.exists(B+"/x_rewrite_9.json") else []
    ap=json.load(open(B+"/approved.json")) if os.path.exists(B+"/approved.json") else {"lead_ids":[]}
    have={o["lead_id"] for o in r9}
    for l in flag:
        if l in x and l not in have: r9.append({"lead_id":l,"x":x[l]["x"],"y":x[l]["y"],"specialty":x[l].get("specialty","")})
    ap["lead_ids"]=sorted(set(ap["lead_ids"])|flag)
    json.dump(r9,open(B+"/x_rewrite_9.json","w"),indent=1); json.dump(ap,open(B+"/approved.json","w"))
