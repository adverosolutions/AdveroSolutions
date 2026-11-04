"""[batch B copy of step_maps61_90.py, 10/26 ~12:25 CT: Maps pest batch B termite/wildlife/mosquito/rodent metros 1-30, 466 domains maps_pest_domains_upload_20261026c.csv; adds 433 M61-90 upload, leadgen handoff files, tab readback A4590:V4689 (rows 4593-4637 = M61-90 owner append); tab rows >=4640 are batch B itself; 4638-4639 blank] [61-90 copy of step_maps518.py] Maps Bot metros 31-60 QE prep (518 domains, /workspace/qe_bulk/maps_20261026/maps_pest_domains_upload_20261026.csv)
-> untried-only QE Bulk Domain w/Emails upload (domain column). LGM ask 10/26 5:03 AM CT. Read-only on all inputs.
Reuses step_m31_60.py helpers (root, PLATFORM, HOSTED, brand, nichefit) and its dedupe sources, plus:
the 643 already run (qe_upload_maps_m31_60.csv), every week qe_upload_* (Maps 188, NF, PD7, PD10), all QE pest exports
10/20-10/26 (searched_domain + Company URL/Email Domain/Email, incl. Contact Finder PD9a-c), final-leads, Instantly-known,
client index, do_not_reload, and the pest_control tab (raw_pest3 A1:T3660 + live read A3655:V4125 at ~05:10 CT).
Tab rows 3661-4115 are this same Maps batch (generic/no-name emails) and do not block; a domain with a NAMED row anywhere
on the tab is dropped; earlier unnamed-only tab domains are kept but tagged."""
import csv,glob,json,sys,collections,os,re,io
exec(open('/tmp/head.py').read())   # helpers from step_m31_60.py (no I/O)
SRC=QB+'maps_pestday_20261026/maps_pest_domains_upload_20261026c.csv'; MMETA=QB+'maps_pestday_20261026/pest_domains_meta_c.csv'
OUT=D+'qe_upload_maps_b.csv'; AUD=D+'qe_upload_maps_b_audit.csv'; META2=D+'qe_upload_maps_b_meta.csv'
# --- prior DWE / QE export domains
dwe={}
for f in sorted(glob.glob(Q+'*.csv')):
    rd=csv.DictReader(open(f,encoding='utf-8-sig',errors='replace')); fn=rd.fieldnames or []
    pest='pest' in os.path.basename(f)
    for x in rd:
        if 'searched_domain' in fn:
            d=norm_domain(x['searched_domain'])
            if d: dwe.setdefault(d,os.path.basename(f))
        if pest:
            for k in ('Company URL','Email Domain','URL','Final Email Domain'):
                d=norm_domain(x.get(k))
                if d and d not in FREE and '.' in d: dwe.setdefault(d,os.path.basename(f)+' ('+k+')')
            e=(x.get('Email') or '').strip().lower()
            if '@' in e and e.split('@')[1] not in FREE: dwe.setdefault(e.split('@')[1],os.path.basename(f)+' (Email)')
upf=(glob.glob(QB+'pest_domains_upload*.csv')+glob.glob(QB+'2026-10-2*_P*/*upload*.csv')+glob.glob(QB+'t2_retry/pest_t2_*.csv')+glob.glob(QB+'maps_2*/maps_pest_domains_upload_*.csv')+glob.glob(QB+'maps_pest*/maps_pest_domains_upload_*.csv')
     +glob.glob(QB+'2026-10-23_PD6/*upload*.csv')+glob.glob(D+'pd10/*upload*.csv'))
upf=[p for p in upf if 'domain_results' not in p and os.path.abspath(p)!=os.path.abspath(SRC)]
for f in upf:
    for x in csv.DictReader(open(f,encoding='utf-8-sig')):
        d=norm_domain(x.get('domain'))
        if d: dwe.setdefault(d,os.path.relpath(f,'/workspace'))
week={}
for f in sorted(glob.glob(D+'qe_upload_*.csv')):
    b=os.path.basename(f)
    if b.startswith('qe_upload_maps_b') or b.endswith(('_audit.csv','_meta.csv')): continue
    for x in csv.DictReader(open(f)):
        d=norm_domain(x.get('domain'))
        if d: week.setdefault(d,b)
m3160={norm_domain(x['domain']) for x in csv.DictReader(open(D+'qe_upload_maps_m31_60.csv'))}
assert len(m3160)==643,len(m3160)
m6190={norm_domain(x['domain']) for x in csv.DictReader(open(D+'qe_upload_maps_61_90.csv'))}
assert len(m6190)==433,len(m6190)
assert all(week.get(d)=='qe_upload_maps_61_90.csv' or d in week for d in m6190)
HO=os.path.expanduser('~/advero/state/handoffs/leadgen/')
ho={}
for b in ('week_pest_20261026.csv','week_pest_672_named_20261026.csv','week_pest_addon_m61_90_20261026.csv','pest_load_ready_20261023.csv'):
    n0=len(ho)
    for x in csv.DictReader(open(HO+b,encoding='utf-8-sig',errors='replace')):
        e=(x.get('email') or x.get('Email') or '').strip().lower()
        if '@' in e and e.split('@')[1] not in FREE: ho.setdefault(e.split('@')[1],b)
        for k in ('website','domain','Company URL'):
            d=norm_domain(x.get(k))
            if d and d not in FREE and '.' in d: ho.setdefault(d,b)
    assert len(ho)>n0,b
# --- pest_control tab
def tabrows():
    for f in sorted(glob.glob(D+'raw_pest4/*.json')):
        for rg in json.load(open(f))['ranges']:
            m=re.match(r"pest_control!A(\d+):",rg['range']); s=int(m.group(1))
            for i,row in enumerate(csv.reader(io.StringIO(rg['content']))): yield s+i,row
    d=json.load(open(D+'raw_maps61_90/sheet_A4110_V4600.json'))
    for i,row in enumerate(csv.reader(io.StringIO(d['ranges'][0]['content']))): yield 4110+i,row
    d=json.load(open(D+'m6190/readback_A4590_V4700.json')); assert d['ranges'][0]['range'].startswith('pest_control!A4590')
    for i,row in enumerate(csv.reader(io.StringIO(d['ranges'][0]['content']))): yield 4590+i,row
hdr=None; tab=collections.defaultdict(lambda:{'named':0,'unnamed':0}); seenrow=set()
for n,row in tabrows():
    if n==1: hdr=row[:20]; continue
    if n in seenrow or not any(x.strip() for x in row): continue
    seenrow.add(n)
    if n>=4640: continue   # batch B itself (rows 4640-4998); 4638-4639 blank
    r={k:('' if v.strip().upper()=='N/A' else v) for k,v in zip(hdr,row+['']*20)}; e=r['email'].strip().lower()
    for d in {norm_domain(r['domain']),norm_domain(r['website']),e.split('@')[1] if '@' in e else ''}-{''}:
        if d in FREE: continue
        tab[d]['named' if r['first_name'].strip() else 'unnamed']+=1
assert hdr and max(seenrow)>=4637 and all(n in seenrow for n in range(4593,4638)),(len(seenrow),max(seenrow))
tab_r={}
for d,v in tab.items():
    t=tab_r.setdefault(root(d),{'named':0,'unnamed':0}); t['named']+=v['named']; t['unnamed']+=v['unnamed']
fl=set()
for p in glob.glob(W.S+'/leads/final-leads/*.csv'):
    for r in csv.DictReader(open(p,encoding='utf-8-sig',errors='replace')):
        e=(r.get('Email') or '').lower()
        if '@' in e and e.split('@')[1] not in FREE: fl.add(e.split('@')[1])
        for k in ('Company URL','Email Domain','Company Key'):
            d=dom(r.get(k))
            if d and d not in FREE: fl.add(d)
ci=W.client_index.load(); assert ci['status']=='on'
sp=W.suppression.load(); assert sp['status']=='on'
supd={e.split('@')[1] for e in sp['active'] if '@' in e and e.split('@')[1] not in FREE}
def R(s): return s|{root(x) for x in s}
fl_r,inst_r,sup_r=R(fl),R(W.inst_d),R(supd)
dwe_r={root(k):v for k,v in dwe.items()}|dwe; week_r={root(k):v for k,v in week.items()}|week; m_r=R(m3160)
meta={norm_domain(x['domain']):x for x in csv.DictReader(open(MMETA,encoding='utf-8-sig'))}
NONUS_ST={'ontario','quebec','british columbia','alberta','manitoba','saskatchewan','nova scotia','new brunswick','on','qc','bc','ab'}
# batch B extras (manual spot-check of the first pass, 10/26 ~12:30 CT)
# Maps category 'Wildlife rescue service' on clear for-profit removal/trapping cos -> not off-niche
NICHE_OK={'crittertrapper.com':'The Critter Trapper wildlife control','animaltrackerswildlife.com':'Animal Trackers Wildlife Co','cummingtonwildlife.com':'Cummington Wildlife Inc',
 'actlivetrap.com':'Act Live Trapping Services','pittsburghwildlifecontrol.com':'Pittsburgh Wildlife Control','cincinnatianimalcontrol.com':'Advantage Wildlife Removal'}
MAN_DROP={'ma.us':'public mosquito control project, bare public-suffix domain','solanomosquito.com':'Solano County Mosquito Abatement District (public)',
 'hummingbirdrescuecenter.org':'wildlife rescue non-profit','naturesownchimneycleaning.com':'chimney cleaning co','txweedcontrol.com':'weed control co',
 'pestcontrolservicestampa.com':'Do It Yourself Pest Control (DIY retail store)'}
# blank meta state -> fill from Maps raw (head.py loc(): complete_address/address/metro+US phone)
RAWB=W.S+'/leads/maps/raw/pest_pestsub_20261026_raw.csv'; rawloc=collections.defaultdict(set)
for x in csv.DictReader(open(RAWB,encoding='utf-8-sig',errors='replace')):
    d=norm_domain(x.get('website'))
    if d: rawloc[root(d)].add(loc(x))
raw=[x['domain'] for x in csv.DictReader(open(SRC,encoding='utf-8-sig'))]
c=collections.Counter(); audit=[]; keep=[]; meta_out=[]; seen={}
c['input']=len(raw)
for w in raw:
    h=norm_domain(w); mt=meta.get(h,{}); a=dict(input=w,domain=h,root='',company=mt.get('company_name',''),city=mt.get('city',''),state=mt.get('state',''),decision='drop',reason='')
    def done(reason,stage): a['reason']=reason; c[stage]+=1; audit.append(a)
    if not h or '.' not in h or re.search(r'[^a-z0-9.-]',h): done('bad_url','bad_url'); continue
    if PLATFORM.search(h+'.') or HOSTED.search('.'+h) or h in FREE: done('social/site-builder host','social_sitebuilder'); continue
    r=root(h); a['root']=r
    st=(mt.get('state') or '').strip(); st=ST.get(st.lower(),st)
    if not st:
        ls=rawloc.get(r,set())
        if ls and all(l[2]=='US' for l in ls): st=sorted(ls)[0][1]; a['state']=st+' (raw)'; a['city']=a['city'] or sorted(ls)[0][0]
        elif any(l[2] not in ('US',) for l in ls): done(f'non-US (raw loc {sorted(ls)})','non_us'); continue
    if r in MAN_DROP: done('off-niche: spotcheck: '+MAN_DROP[r],'off_niche'); continue
    if st.lower() in NONUS_ST or re.search(r'\.(ca|uk|au|ie|nz|mx)$',r): done(f'non-US ({(mt.get("state") or "").strip() or "TLD"}: {r})','non_us'); continue
    b=brand(r,mt.get('company_name',''))
    if b: done('big brand: '+b,'big_brand'); continue
    cat=(mt.get('fit_reason','').split('category/query:')[-1]).strip()
    nf='' if r in NICHE_OK else nichefit(dict(title=mt.get('company_name',''),category=cat,website=h),r)
    if nf: done('off-niche: '+nf,'off_niche'); continue
    if r in seen: done('dup_root_in_file (first: '+seen[r]+')','dup_in_file'); continue
    seen[r]=h; why=''
    if r in m_r or h in m3160: why='already_run_m31_60_643'
    elif r in fl_r or h in fl: why='final_leads'
    elif W.client_index.match(ci,'',r) or W.client_index.match(ci,'',h): why='client_index'
    elif r in inst_r or h in W.inst_d: why='instantly_known'
    elif r in sup_r or h in supd: why='do_not_reload_domain'
    elif r in m6190 or h in m6190: why='already_run_m61_90_433'
    elif r in R(set(ho)) or h in ho: why='leadgen_handoff: '+(ho.get(h) or ho.get(r) or next(v for k,v in ho.items() if root(k)==r))
    elif r in dwe_r or h in dwe: why='prior_QE_upload_or_export: '+(dwe.get(h) or dwe.get(r) or dwe_r.get(r))
    elif r in week_r or h in week: why='this_week_qe_upload: '+(week.get(h) or week.get(r) or week_r.get(r))
    elif (tab_r.get(r) or tab.get(h) or {}).get('named'): why='pest_tab_named'
    if why: done(why,why.split(':')[0]); continue
    t=tab_r.get(r) or tab.get(h)
    a['decision']='keep'; a['reason']='new'+(' (earlier pest tab row without first_name)' if t else ''); c['kept']+=1
    if t: c['kept_tab_unnamed_earlier']+=1
    audit.append(a); keep.append(r)
    meta_out.append(dict(domain=r,company_name=mt.get('company_name',''),city=mt.get('city',''),state=st,employee_count='',fit_reason=mt.get('fit_reason',''),note='maps daytime batch B sub-niche metros 1-30'))
with open(OUT,'w',newline='') as f: k=csv.writer(f); k.writerow(['domain']); [k.writerow([d]) for d in keep]
parts=[]
if len(keep)>500:
    for j in range(0,len(keep),500):
        p=D+f'qe_upload_maps_b_part{j//500+1}.csv'; parts.append((p,len(keep[j:j+500])))
        with open(p,'w',newline='') as f: k=csv.writer(f); k.writerow(['domain']); [k.writerow([d]) for d in keep[j:j+500]]
c['parts']=len(parts)
with open(AUD,'w',newline='') as f: k=csv.DictWriter(f,fieldnames=list(audit[0])); k.writeheader(); k.writerows(audit)
with open(META2,'w',newline='') as f: k=csv.DictWriter(f,fieldnames=['domain','company_name','city','state','employee_count','fit_reason','note']); k.writeheader(); k.writerows(meta_out)
print(json.dumps(dict(counts=c,dwe_prior=len(dwe),week_upload_domains=len(week),m3160=len(m3160),tab_domains=len(tab),upload_files=len(upf)),indent=1))
