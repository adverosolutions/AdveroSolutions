"""applyfix.py <batch> <fixes.json>  fixes.json = {"fix":{id:{x?,y?,specialty?}}, "skip":{id:reason}}"""
import json,os,sys
B,F=sys.argv[1],sys.argv[2]; d=json.load(open(F))
x=json.load(open(B+"/x.json"))
r9=json.load(open(B+"/x_rewrite_9.json")) if os.path.exists(B+"/x_rewrite_9.json") else []
fix=d.get("fix",{}); r9=[o for o in r9 if o["lead_id"] not in fix]
for l,f in fix.items():
    o={"lead_id":l,"x":x[l]["x"],"y":x[l]["y"],"specialty":x[l].get("specialty","")}; o.update(f); r9.append(o)
json.dump(r9,open(B+"/x_rewrite_9.json","w"),indent=1); json.dump({"lead_ids":list(fix)},open(B+"/approved.json","w"))
S=json.load(open(B+"/select.json"))
for s in S:
    if s["lead_id"] in d.get("skip",{}): s["tier"]="skip"; s["angle"]="skipped: "+d["skip"][s["lead_id"]]
json.dump(S,open(B+"/select.json","w"),indent=1); print("fixed",len(fix),"skipped",len(d.get("skip",{})))
