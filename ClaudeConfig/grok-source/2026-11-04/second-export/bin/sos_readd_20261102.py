#!/usr/bin/env python3
"""SOS 11/2 re-add (Lorenzo 7:33 PM CT 11/2). Idempotent; rerun as fix_*.json land.
Removed leads -> /leads/add to original campaign (skip_if_in_workspace). In-place leads (4,324 still in core
campaigns) -> PATCH personalization. Contacted removed leads (re_add_last) only after every other removed lead.
QA gate below; failures go to qa_fail.jsonl for manual fix. KILL_SWITCH checked before every batch."""
import sys,os,json,csv,glob,re,time,collections
sys.path.insert(0,'/workspace'); from inst import api as _api
def api(*a):
  for i in range(8):
    try:
      r=_api(*a)
      if isinstance(r,dict) and r.get('_err') in(429,500,502,503,504): raise RuntimeError(r)
      return r
    except Exception as e:
      if i==7: return {'_err':'net','_body':str(e)[:200]}
      time.sleep(min(5*2**i,120))
H=os.path.expanduser('~/advero/state'); D=f'{H}/leadgen/personalized/sos_20261102'; B=f'{H}/backups/sos_personalization_20261102'
DONE=f'{D}/readd_done.json'; done=json.load(open(DONE)) if os.path.exists(DONE) else {}
MAN=f'{D}/manual_fixes.json'; man=json.load(open(MAN)) if os.path.exists(MAN) else {}
def log(**k):
  k.update(ts=time.strftime('%Y-%m-%dT%H:%M:%S%z'),actor='leadgen_manager',decision='sos_readd_batch'); open(f'{H}/decisions.jsonl','a').write(json.dumps(k)+'\n')
BAN=re.compile(r"\u2014|\u2013|!|\b(must|probably|bet|gotta|no wonder|solutions|premier|innovative|best-in-class|tailored)\b|\bleading\b",re.I) if False else re.compile(r"\u2014|\u2013|!|\b([Mm]ust|[Pp]robably|[Bb]et|[Gg]otta|[Nn]o wonder|solutions|premier|innovative|best-in-class|tailored)\b")
W2N={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
REP={"Great work on the consulting. I can tell you care about giving advice people can actually use.":"Great work with your clients. I can tell you care about giving advice they can actually use.",
 "Fantastic work on the construction. I can tell you really care about getting the details right.":"Fantastic work on the builds. I can tell you really care about getting the details right.",
 "Great work on the production. I can tell you put real thought into how everything comes together.":"Great work on the shoots. I can tell you put real thought into how everything comes together."}
def yrs(m):
  w=m.group(2).lower().replace('-',' ').split(); n=sum(W2N.get(x,0) for x in w)
  return f"{n} years in business" if n and all(x in W2N for x in w) else m.group(0)
def COR(l):
  for a,b in REP.items(): l=l.replace(a,b)
  l=re.sub(r"\b(around |about |almost |nearly )?((?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|one|two|three|four|five|six|seven|eight|nine)(?:[ -](?:one|two|three|four|five|six|seven|eight|nine))?) years in business",yrs,l,flags=re.I)
  return l
def qa(l):
  if not l: return 'empty'
  if not l.startswith('Hey'): return 'no Hey'
  if not l.endswith('Was wondering if I can run something by you.'): return 'template end'
  if 'I know that you do' not in l: return 'template x'
  m=BAN.search(l); return f'banned {m.group(0)}' if m else ''
bk={it['email'].lower():it for it in json.load(open(f'{B}/leads_full_backup.json'))+json.load(open(f'{B}/extra_4324_backup.json'))}
recs=[]
for f in glob.glob(f'{D}/fix_*.json'):
  m=re.match(r'fix_(.+)_([cux]\d{3})\.json$',os.path.basename(f)); seg,ch=m.groups()
  try: fx={x['lead_id']:x for x in json.load(open(f))}
  except Exception: continue
  for r in csv.DictReader(open(f'{D}/{seg}_{ch}.csv')):
    x=fx.get(r['lead_id']); 
    if not x: continue
    r['final_line']=man.get(r['lead_id'],COR(x.get('line') or '')); r['fix']=x; r['chunk']=ch; recs.append(r)
seen=collections.Counter(); qf=[]; ready=[]
for r in recs:
  if r['fix'].get('mode')=='skipped' and r['lead_id'] not in man: continue
  dom=(r.get('domain') or '').lower(); key=(dom,r['final_line'])
  e=qa(r['final_line']) or ('dup line same company' if seen[key] else ''); seen[key]+=1
  if e: qf.append({'lead_id':r['lead_id'],'seg':r['seg'],'line':r['final_line'],'err':e}); continue
  ready.append(r)
json.dump(qf,open(f'{D}/qa_fail.json','w'),indent=1)
if '--dry' in sys.argv: print(len(recs),len(ready),len(qf)); sys.exit()
def ks():
  if os.path.exists(f'{H}/KILL_SWITCH'): log(event='kill_switch_stop'); print('KILL_SWITCH'); sys.exit(2)
allfixed=len(glob.glob(f'{D}/fix_*.json'))>=len(glob.glob(f'{D}/*_[cu][0-9][0-9][0-9].csv'))
stats=collections.Counter()
# in-place PATCH
for r in ready:
  if r.get('in_place')!='True' or r['email'].lower() in done: continue
  ks(); it=bk[r['email'].lower()]
  res=api('/leads/'+it['id'],'PATCH',{'personalization':r['final_line']})
  if '_err' in res: stats['patch_fail']+=1; open(f'{D}/readd_fail.jsonl','a').write(json.dumps({'email':r['email'],'res':res})+'\n'); continue
  done[r['email'].lower()]={'how':'patched','campaign':it['campaign'],'line':r['final_line']}; stats['patched_'+it['campaign']]+=1
  if stats['patched_'+it['campaign']]%100==0: json.dump(done,open(DONE,'w'))
json.dump(done,open(DONE,'w'))
# re-add removed
add=[r for r in ready if r.get('in_place')!='True' and r['email'].lower() not in done]
first=[r for r in add if r.get('contacted')!='True']; last=[r for r in add if r.get('contacted')=='True'] if allfixed else []
by=collections.defaultdict(list)
for r in first+last: by[(r.get('contacted')=='True',bk[r['email'].lower()]['campaign'])].append(r)
for (con,camp),rs in sorted(by.items()):
  for i in range(0,len(rs),500):
    ks(); o=api('/workspace-billing/plan-details')['subscriptions']['outreach']; cap=o['total_lead_limit']-o['current_lead_count']
    if cap<=0: log(event='cap_hit'); print('cap hit'); break
    part=rs[i:i+500][:cap]; leads=[]
    for r in part:
      it=bk[r['email'].lower()]; p=dict(it.get('payload') or {})
      cv={k:v for k,v in p.items() if k not in('firstName','lastName','companyName','website','email','personalization')}
      leads.append({'email':it['email'],'first_name':it.get('first_name',''),'last_name':it.get('last_name',''),'company_name':it.get('company_name',''),'website':it.get('website',''),'personalization':r['final_line'],'custom_variables':cv})
    res=api('/leads/add','POST',{'campaign_id':camp,'skip_if_in_workspace':True,'leads':leads})
    if '_err' in res: stats['add_fail']+=len(part); log(event='err',campaign=camp,err=res); continue
    for r in part: done[r['email'].lower()]={'how':'readded','campaign':camp,'re_add_last':con,'line':r['final_line']}
    json.dump(done,open(DONE,'w')); stats['added_'+camp]+=res.get('leads_uploaded',0); stats['skipped_dupe']+=res.get('skipped_count',0)+res.get('duplicated_leads',0)
    log(campaign=camp,n=len(part),re_add_last=con,uploaded=res.get('leads_uploaded'),skipped=res.get('skipped_count'),remaining=res.get('remaining_in_plan'))
print(json.dumps(stats),'qa_fail',len(qf),'last_pending',0 if allfixed else sum(1 for r in add if r.get('contacted')=='True'))
