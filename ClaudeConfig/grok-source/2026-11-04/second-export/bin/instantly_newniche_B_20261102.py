#!/usr/bin/env python3
"""Overnight 11/1-11/2 (Lorenzo mass approval 10:36 PM CT): create per-niche B campaigns as copies of
ee300e46 (Residential Cleaning B), changing ONLY the industry words. Same inboxes, same settings, Mon-Sat 7-7 CT.
Idempotent: reuses a campaign with the exact name if it already exists. --dry prints the diffs only."""
import json,os,sys,time,copy
sys.path.insert(0,'/workspace'); from inst import api
OUT=os.path.expanduser('~/advero/state/leadgen/load_overnight_20261102'); DRY='--dry' in sys.argv
SRC='ee300e46-db39-4e63-ab1c-e8a29eea9497'
A1='new cleaning inquiries and help turn them into booked cleanings'
A2='new cleaning inquiries and help get those cleanings booked'
def svc(x): return (f'new inquiries about your {x} services and help turn them into booked discovery calls',
                    f'new inquiries about your {x} services and help get those discovery calls booked')
def biz(x,y): return (f'new {x} inquiries and help turn them into booked {y}', f'new {x} inquiries and help get those {y} booked')
NICHES={
 'general_contractors':('General Contractors',biz('construction','estimates')),
 'consulting':('Business Consulting',svc('consulting')),
 'staffing_agencies':('Staffing Agencies',svc('staffing')),
 'restaurants_catering':('Catering',biz('catering','events')),
 'web_design_agencies':('Web Design Agencies',svc('web design')),
 'seo_agencies':('SEO Agencies',svc('SEO')),
 'social_media_agencies':('Social Media Agencies',svc('social media')),
 'branding_design':('Branding & Design Agencies',svc('branding and design')),
 'software_dev_agencies':('Software Development Agencies',svc('software development')),
 'video_production':('Video Production',svc('video production')),
 'photography':('Photography',biz('photography','shoots')),
}
def name(ind): return f'Launch 2026-11 | {ind} | B: New Inquiry Response | Live'
def allc():
  out=[];sa=None
  while True:
    r=api('/campaigns?limit=100'+(f'&starting_after={sa}' if sa else '')); out+=r['items']; sa=r.get('next_starting_after')
    if not sa: return out
def log(**k):
  k['ts']=time.strftime('%Y-%m-%dT%H:%M:%S%z'); open(f'{OUT}/campaigns.jsonl','a').write(json.dumps(k)+'\n')
src=api('/campaigns/'+SRC); assert src.get('id')==SRC, src
SKIP={'id','name','status','timestamp_created','timestamp_updated','organization','owned_by','created_by','not_sending_status'}
existing={c['name']:c['id'] for c in allc()}
res={}
for key,(ind,(p1,p2)) in NICHES.items():
  nm=name(ind)
  if nm in existing: res[key]={'id':existing[nm],'name':nm,'new':False}; print('exists',nm); continue
  body={k:copy.deepcopy(v) for k,v in src.items() if k not in SKIP}; body['name']=nm
  n=0
  for st in body['sequences'][0]['steps']:
    for v in st['variants']:
      for a,b in ((A1,p1),(A2,p2)):
        n+=v['body'].count(a); v['body']=v['body'].replace(a,b)
  assert n==3,(key,n)
  if DRY: print(nm,'|',p1,'|',p2); continue
  r=api('/campaigns','POST',body)
  if '_err' in r or not r.get('id'): log(event='create_err',niche=key,err=r); print('ERR',key,r); continue
  log(event='created',niche=key,id=r['id'],name=nm); res[key]={'id':r['id'],'name':nm,'new':True}; print('created',nm,r['id'])
if not DRY: json.dump(res,open(f'{OUT}/campaigns.json','w'),indent=1)
