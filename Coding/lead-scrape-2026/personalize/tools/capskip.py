# capskip.py <batch_dir>: mark the ids in tools/cap_<id>.json as skipped in select.json (keeps approved.json intact)
import json,sys,os
B=sys.argv[1].rstrip('/'); bid=os.path.basename(B).split('_')[-1]
ids=set(json.load(open('personalize/tools/cap_%s.json'%bid)))
S=json.load(open(B+'/select.json')); n=0
for s in S:
    if s['lead_id'] in ids and s.get('tier')!='skip': s['tier']='skip'; s['angle']='skipped: company cap (2 per company)'; n+=1
json.dump(S,open(B+'/select.json','w'),indent=1); print('cap-skipped',n,sorted(ids))
