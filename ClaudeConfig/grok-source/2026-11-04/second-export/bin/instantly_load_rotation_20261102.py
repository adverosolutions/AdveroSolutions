#!/usr/bin/env python3
"""Overnight 11/1-11/2 (Lorenzo mass approval 10:36 PM CT; valid+catch_all OK per 10:27 PM). Loads the
QE-verified overnight_*_results.csv (mv/) into niche B campaigns. Mirrors instantly_load_20261101.py:
dedupe vs leads/pool, prior loaded.json, mv backlog, do_not_reload suppression, skip_if_in_workspace.
Cap: Instantly total_lead_limit - current_lead_count (checked live before each batch).
Allocation under the cap: one contact per domain first, water-filled evenly across niches.
Idempotent via loaded.json in load_overnight_20261102/. --dry prints the plan only."""
import csv,glob,json,os,sys,time
sys.path.insert(0,'/workspace'); from inst import api
sys.path.insert(0,os.path.expanduser('~/advero/bin')); import suppression
H=os.path.expanduser('~/advero/state'); OUT=f'{H}/leadgen/load_overnight_20261102'; DRY='--dry' in sys.argv
NEW=json.load(open(f'{OUT}/campaigns.json'))
CAMP={k:v['id'] for k,v in NEW.items()}
CAMP.update({'cleaning':'4d9998d5-4761-4290-b232-56237d774b32','cleaning_specialty':'4d9998d5-4761-4290-b232-56237d774b32',
 'residential_cleaning':'ee300e46-db39-4e63-ab1c-e8a29eea9497','upholstery_tile_cleaning':'ee300e46-db39-4e63-ab1c-e8a29eea9497',
 'pest_control':'f13b219a-c68e-4087-8ea1-a1c629605708'})
CLEAN='Love how much your clients clearly trust you with their homes. Definitely refreshing to see.'
FB={'cleaning':CLEAN,'cleaning_specialty':CLEAN,'residential_cleaning':CLEAN,'upholstery_tile_cleaning':CLEAN,
 'pest_control':'Love how much trust people clearly put in you inside their homes. Definitely refreshing to see.'}
pool=set()
for f in glob.glob(f'{H}/leads/pool/*.csv'):
  for r in csv.DictReader(open(f,encoding='utf-8-sig')): pool.add((r.get('email') or '').strip().lower())
prior=set(json.load(open(f'{H}/leadgen/load_20261101/loaded.json')))
prior|={r['email'].strip().lower() for r in csv.DictReader(open(f'{H}/mv/mv_backlog_20261101_results.csv'))}
sup=suppression.load()['active']
donep=f'{OUT}/loaded.json'; done=json.load(open(donep)) if os.path.exists(donep) else {}
def log(**k):
  k['ts']=time.strftime('%Y-%m-%dT%H:%M:%S%z'); open(f'{OUT}/log.jsonl','a').write(json.dumps(k)+'\n')
def cap():
  o=api('/workspace-billing/plan-details')['subscriptions']['outreach']; return o['total_lead_limit']-o['current_lead_count']
stats={}; cand={}; seen=set()
for f in sorted(glob.glob(f'{H}/mv/overnight_*_results.csv')):
  seg=os.path.basename(f)[10:-12]; rows=list(csv.DictReader(open(f))); s=stats[seg]={'rows':len(rows),'dupes':0,'valid':0,'catch_all':0,'other':0}
  first=[];rest=[];doms=set()
  for r in rows:
    e=r['email'].strip().lower(); st=r['email_status'].strip().lower().replace('-','_')
    if not e or e in pool or e in prior or e in sup or e in seen or e in done: s['dupes']+=1; continue
    seen.add(e)
    if st in('valid','ok'): s['valid']+=1; st='valid'
    elif st in('catch_all','catchall','accept_all'): s['catch_all']+=1; st='catch_all'
    else: s['other']+=1; continue
    r['_st']=st; d=r['domain'].strip().lower()
    (rest if d in doms else first).append(r); doms.add(d)
  cand[seg]=first+rest; s['unique_domains']=len(first)
C=cap(); print('cap',C)
# 11/2 7:19 AM order: core (pest, cleaning) first, then adjacent niches by largest valid pool; valid before catch_all
for k in cand: cand[k].sort(key=lambda r: r['_st']!='valid')
order=[k for k in cand if k in FB]+sorted([k for k in cand if k not in FB and k in CAMP],key=lambda k:-stats[k]['valid'])
alloc={k:0 for k in cand}; left=C
for k in order: alloc[k]=min(len(cand[k]),left); left-=alloc[k]
print(json.dumps(alloc)); json.dump({'stats':stats,'alloc':alloc,'cap_start':C},open(f'{OUT}/plan.json','w'),indent=1)
if DRY: sys.exit()
for seg in order:
  rows=cand[seg]
  part_all=rows[:alloc[seg]]; stats[seg]['loaded']=0
  for i in range(0,len(part_all),500):
    c=cap()
    if c<=0: log(event='cap_hit',seg=seg); break
    part=part_all[i:i+500][:c]
    leads=[{'email':r['email'].strip(),'first_name':r['first_name'],'last_name':r['last_name'],'company_name':r['company'],'website':r['domain'],
      'personalization':FB.get(seg,''),'custom_variables':{'Segment':seg,'MV Result':r['_st'],'lead_id':f"{r['tab']}-{r['sheet_row']}",'City':'',
      'source_folder':'qe_cf_allnight_20261101'}} for r in part]
    res=api('/leads/add','POST',{'campaign_id':CAMP[seg],'skip_if_in_workspace':True,'leads':leads})
    if '_err' in res: log(event='err',seg=seg,err=res); print(seg,res); break
    for r in part: done[r['email'].strip().lower()]={'seg':seg,'campaign':CAMP[seg]}
    json.dump(done,open(donep,'w'))
    stats[seg]['loaded']+=res.get('leads_uploaded',0)
    log(event='batch',seg=seg,n=len(part),res={k:v for k,v in res.items() if not isinstance(v,list)}); print(seg,len(part),res.get('leads_uploaded'),res.get('remaining_in_plan'))
json.dump({'stats':stats,'alloc':alloc,'cap_start':C,'cap_end':cap()},open(f'{OUT}/summary.json','w'),indent=1)
log(event='finished',loaded=len(done))
