#!/usr/bin/env python3
"""Lorenzo greenlight 11/1 10:27 PM CT: load MV valid + catch_all backlog leads into the B campaigns.
Valid leads load once their personalization chunk lands; catch_all load now with the approved niche fallback.
Idempotent: tracks loaded emails; Instantly also skips anyone already in the workspace. Loops until the feeder finishes."""
import csv,glob,json,os,sys,time
sys.path.insert(0,'/workspace'); from inst import api
H=os.path.expanduser('~/advero/state'); OUT=f'{H}/leadgen/load_20261101'; P=f'{H}/leadgen/personalized'
CAMP={'pest_control':'f13b219a-c68e-4087-8ea1-a1c629605708','cleaning':'4d9998d5-4761-4290-b232-56237d774b32',
 'ppc':'49cd2de9-8f78-4543-b6d8-86106e46928d','residential':'ee300e46-db39-4e63-ab1c-e8a29eea9497'}
FB={'pest_control':'Love how much trust people clearly put in you inside their homes. Definitely refreshing to see.',
 'cleaning':'Love how much your clients clearly trust you with their homes. Definitely refreshing to see.'}
FB['ppc']='I know how seriously you take the numbers behind every account. Definitely refreshing to see.'
FB['residential']=FB['cleaning']
DRY='--dry' in sys.argv
mv=list(csv.DictReader(open(f'{H}/mv/mv_backlog_20261101_results.csv')))
det={}
for f in sorted(glob.glob(f'{H}/leads/pool/*.csv')):
  for r in csv.DictReader(open(f,encoding='utf-8-sig')): det.setdefault((r.get('email') or '').lower(),r)
donep=f'{OUT}/loaded.json'; done=json.load(open(donep)) if os.path.exists(donep) else {}
def log(**k):
  k['ts']=time.strftime('%Y-%m-%dT%H:%M:%S%z'); open(f'{OUT}/log.jsonl','a').write(json.dumps(k)+'\n')
def plines():
  m={}
  for f in glob.glob(f'{P}/*_c*.csv'):
    for r in csv.DictReader(open(f)): m[r['email'].lower()]=r
  return m
def lead(b,line):
  d=det.get(b['email'].lower(),{})
  return {'email':b['email'],'first_name':d.get('first_name',''),'last_name':d.get('last_name',''),'company_name':d.get('company',''),
   'website':d.get('website',''),'personalization':line,'custom_variables':{'Segment':b['segment'],'MV Result':'valid' if b['mv_result_raw']=='ok' else 'catch_all',
   'lead_id':f"{b['tab']}-{b['row']}",'City':d.get('city',''),'source_folder':'mv_backlog_20261101'}}
while True:
  pl=plines(); batch={}; stats={}
  for b in mv:
    e=b['email'].lower(); r=b['mv_result_raw']
    if e in done or r not in('ok','catch_all'): continue
    seg=b['segment']
    if r=='ok':
      p=pl.get(e)
      if not p: continue
      line=p['personalization_line'] or FB.get(seg,''); kind='skill' if p['personalization_line'] else ('fallback' if line else 'none')
    else:
      line=FB.get(seg,''); kind='fallback' if line else 'none'
    batch.setdefault(seg,[]).append((e,kind,lead(b,line)))
  for seg,items in batch.items():
    for i in range(0,len(items),500):
      part=items[i:i+500]
      if DRY: print(seg,len(part),{k:sum(1 for x in part if x[1]==k) for k in('skill','fallback','none')}); continue
      res=api('/leads/add','POST',{'campaign_id':CAMP[seg],'skip_if_in_workspace':True,'leads':[x[2] for x in part]})
      if '_err' in res: log(event='err',seg=seg,err=res); print(res); continue
      for e,k,_ in part: done[e]={'seg':seg,'kind':k}
      json.dump(done,open(donep,'w'))
      log(event='batch',seg=seg,n=len(part),res={k:v for k,v in res.items() if not isinstance(v,list)})
  if DRY: break
  fs=json.load(open(f'{P}/_work/feeder_status.json'))
  if not fs.get('running') and all(os.path.exists(f'{P}/{os.path.basename(f)[6:-5]}.csv') or os.path.exists(f'{P}/_work/{os.path.basename(f)[6:-5]}.failed2') for f in glob.glob(f'{P}/_work/chunk_*.json')):
    log(event='finished',loaded=len(done)); break
  time.sleep(300)
