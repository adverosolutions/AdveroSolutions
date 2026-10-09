"""final_view.py <batch>: print lines after autofix (fix_<batch>.json) for a last hand review"""
import json,os,sys
SP=os.path.dirname(os.path.abspath(__file__)); os.chdir("/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026")
B=sys.argv[1]; x=json.load(open(B+"/x.json")); L={l["lead_id"]:l for l in json.load(open(B+"/leads.json"))}
S={s["lead_id"]:s for s in json.load(open(B+"/select.json"))}
F=json.load(open(f"{SP}/fix_{os.path.basename(B)}.json"))
for lid in sorted(x):
    if S[lid]["tier"]=="skip" or lid in F["skip"]: continue
    v=dict(x[lid],**F["fix"].get(lid,{})); l=L[lid]; m="*" if lid in F["fix"] else " "
    print(f"{m}{lid} | {l['company_name'][:26]} | {l['company_city']},{l['company_state'][:5]} || {v['x']} || {v['y']}")
