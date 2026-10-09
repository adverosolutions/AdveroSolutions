import json,subprocess,sys,ast,os
ROOT="/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026"; os.chdir(ROOT)
B=sys.argv[1]
subprocess.run(["python3","personalize/daily_fill.py",B,"--merge"],capture_output=True)
out=subprocess.run(["python3","personalize/daily_apply.py",B],capture_output=True,text=True).stdout
print([l for l in out.splitlines() if "[apply]" in l])
fl={}
for line in out.splitlines():
    if "flagged:" in line:
        for t in ast.literal_eval(line.split("flagged:",1)[1].strip()): fl[t[0]]=t[2]
x=json.load(open(B+"/x.json")); L={l["lead_id"]:l for l in json.load(open(B+"/leads.json"))}
S={s["lead_id"]:s for s in json.load(open(B+"/select.json"))}
for lid in sorted(x):
    l=L[lid]; f=fl.get(lid,"")
    print(f"{lid} {S[lid]['tier']}{' !!'+f if f else ''} | {l['company_name'][:28]} | {l['company_city']},{l['company_state'][:5]} || {x[lid]['x']} || {x[lid]['y']} || {x[lid].get('specialty','')}")
