# cap.py <batch_dir>: list fill rows that would exceed 2 contacts per (company, city) across all pushed day files
import csv,glob,collections,json,sys,os
B=sys.argv[1].rstrip('/'); bid=os.path.basename(B)
info={}
for f in glob.glob('personalize/batches/*/leads.json'):
    for l in json.load(open(f)): info[l['lead_id']]=(l['company_name'].strip().lower(), (l.get('company_city') or '').strip().lower())
pushed=collections.Counter()
for f in glob.glob('output/daily/day_*.csv'):
    if bid in f: continue
    for r in csv.DictReader(open(f,encoding='utf-8-sig')):
        k=info.get(r['lead_id'])
        if k: pushed[k]+=1
ids=[]
for f in sorted(glob.glob(B+'/fill_chunk_*.json')): ids+=[o['lead_id'] for o in json.load(open(f))]
seen=collections.Counter(); skip=[]
for i in ids:
    k=info[i]
    if pushed[k]+seen[k]>=2: skip.append(i); print(i,k[0],'pushed',pushed[k])
    else: seen[k]+=1
json.dump(skip,open(os.path.dirname(os.path.abspath(__file__))+'/cap_%s.json'%bid.split('_')[-1],'w')); print('cap skips',len(skip))
