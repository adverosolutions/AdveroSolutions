#!/usr/bin/env python3
"""Maps rolling runner, per-batch post steps (Maps Bot 2026-11-01).
usage: maps_rolling_post.py pest|cleaning TAG BATCHDIR DATE
Maps out csv -> email rows -> qe_dedupe -> fit (pest: refit rules; cleaning: 10/30 c_step2 rules) -> pool file
-> sheet values json (pest A:V, cleaning A:T) -> QE domain file. No manual overrides. Never runs MV/QE/qe_fit.py CLI."""
import csv,sys,os,re,json,glob,subprocess,collections
csv.field_size_limit(10**9)
niche,TAG,BD,DATE=sys.argv[1:5]
H=os.path.expanduser('~'); sys.path.insert(0,f'{H}/advero/bin')
MAPS=f'{H}/advero/state/leads/maps/pest_{TAG}.csv'
NI='pest_control' if niche=='pest' else 'cleaning'
POOL=f'{H}/advero/state/leads/pool/{DATE}_{NI}_google_maps_maps_{TAG}_new.csv'
QED=f'/workspace/qe_bulk/maps_{TAG}'; os.makedirs(QED,exist_ok=True)
UP=f'{QED}/maps_{niche}_domains_upload_{TAG}.csv'; META=f'{QED}/{niche}_domains_meta.csv'
ST={'Alabama':'AL','Alaska':'AK','Arizona':'AZ','Arkansas':'AR','California':'CA','Colorado':'CO','Connecticut':'CT','Delaware':'DE','District of Columbia':'DC','Florida':'FL','Georgia':'GA','Hawaii':'HI','Idaho':'ID','Illinois':'IL','Indiana':'IN','Iowa':'IA','Kansas':'KS','Kentucky':'KY','Louisiana':'LA','Maine':'ME','Maryland':'MD','Massachusetts':'MA','Michigan':'MI','Minnesota':'MN','Mississippi':'MS','Missouri':'MO','Montana':'MT','Nebraska':'NE','Nevada':'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY','North Carolina':'NC','North Dakota':'ND','Ohio':'OH','Oklahoma':'OK','Oregon':'OR','Pennsylvania':'PA','Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD','Tennessee':'TN','Texas':'TX','Utah':'UT','Vermont':'VT','Virginia':'VA','Washington':'WA','West Virginia':'WV','Wisconsin':'WI','Wyoming':'WY'}
S={'tag':TAG,'niche':NI,'date':DATE}
maps=list(csv.DictReader(open(MAPS)))
S['places_out']=len(maps); S['dedupe_status']=dict(collections.Counter(r['dedupe_status'] for r in maps))
S['client_known']=S['dedupe_status'].get('client_known',0)
for r in maps:
    r['state']=ST.get(r['state'].strip(),r['state'].strip())
    if not r['state'] and '#' not in r['query'] and '|' in r['query']:
        mc,ms=r['query'].split('|')[0].rsplit(', ',1); r['state']=ms; r['city']=r['city'] or mc
    elif not r['state']:
        m=re.search(r', ([A-Z]{2})\b',r['query'])
        if m: r['state']=m.group(1)
# 1 email rows
out=[]
for r in maps:
    if r['dedupe_status']!='new' or r['email_type']=='none': continue
    first=lambda f:[e.strip() for e in r[f].split(';') if e.strip()]
    if r['email_named']: e=first('email_named')[0]; t='named'
    elif r['email_freemail']: e=first('email_freemail')[0]; t='gmail'
    else: e=first('email_generic')[0]; t='generic'
    out.append({'First Name':'','Last Name':'','Title':'','Email':e,'Company':r['business_name'],'Company URL':r['website'],'City':r['city'],'State':r['state'],'Country':'US','email_type':t,'phone':r['phone'],'maps_link':r['maps_link'],'rating':r['rating'],'reviews':r['reviews'],'reviews_as_of':r['reviews_as_of'],'maps_category':r['category'],'maps_query':r['query']})
S['new_with_email']=len(out)
rows=[]
if out and not os.path.exists(POOL):
    ER=f'{BD}/maps_email_rows.csv'
    with open(ER,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    p=subprocess.run(['python3',f'{H}/advero/bin/qe_dedupe.py',ER,'--niche',NI,'--source','quickenrich','--label',f'maps_{TAG}','--date',DATE,'--out-dir',BD],capture_output=True,text=True)
    open(f'{BD}/qe_dedupe.out','w').write(p.stdout+p.stderr)
    if p.returncode: print(p.stdout,p.stderr); sys.exit(4)
    D=glob.glob(f'{BD}/{DATE}_{NI}_quickenrich_maps_{TAG}_new.csv')
    rows=list(csv.DictReader(open(D[0]))) if D else []
elif os.path.exists(POOL):
    rows=list(csv.DictReader(open(POOL)))
# 2 fit
from qe_fit import pest_fit, cleaning_fit
src=open(f'{H}/advero/bin/qe_cf_domains.py').read(); ns={}
_a=sys.argv; sys.argv=['x','/dev/null','/tmp/unused']+(['--niche=cleaning'] if niche=='cleaning' else [])
exec(src.split("rows = list(csv.DictReader(open(SRC")[0].replace("from qe_cf_fit import fit",""), ns); sys.argv=_a
big_brand=ns['big_brand']
BIG=re.compile(r"jani-?king|coverall|servicemaster|stanley ?steemer|aramark|cintas|ecolab|\babm\b|merry maids|molly maid|the maids|two maids|maid brigade|maidpro|mr\.? ?rooter|jan-?pro|anago|vanguard cleaning|stratus building|city wide|openworks|duraclean|chem-?dry|window genie|fish window|men in kilts|aaa window")
COM_CAT=re.compile(r"commercial cleaning|janitorial|office cleaning|building maintenance|facility|industrial cleaning|floor cleaning",re.I)
RES_CAT=re.compile(r"house cleaning|maid|pressure washing|window cleaning|gutter|carpet|upholster|roof|soft wash|home cleaning|residential",re.I)
OFFCAT=re.compile(r"car wash|car detail|auto detail|detailing|dry clean|laundr|supplier|store|equipment|employment agency|staffing|water damage|restoration|hvac|air duct|plumb|roofing contractor|pool clean|septic|waste management|dumpster",re.I)
US=set(ST.values())
if rows and not os.path.exists(POOL):
    for r in rows:
        e=r['email']; m=re.match(r'^\d{5}([a-z].*)$',e)
        if m and '@' in e: r['email']=m.group(1)
        r['source']='google_maps'; r['source_search']='MAPS'; r['website']=r['website'].split('?')[0]
        cat=r.get('maps_category','') or ''
        tail=f"; company email from Google Maps listing site, no person title ({r['email_type']}), unverified"
        if niche=='pest':
            v,why=pest_fit(r['company'],r['domain'],'','','MAPS')
        else:
            v,why=cleaning_fit(r['company'],r['domain'],'','','MAPS'); s=f"{r['company']} {r['domain']}".lower()
            if OFFCAT.search(cat): v,why='off-niche',f"Maps category {cat}, not building/home cleaning"
            elif BIG.search(s) or big_brand(r['domain'],r['company']): v,why='off-niche','national brand/franchise, excluded'
            elif v=='off-niche' and COM_CAT.search(cat): v,why=None,f"generic name; Maps category {cat}"
            elif v=='off-niche' and RES_CAT.search(cat) and not re.search(r'pool|auto|car wash|detail|hvac|plumb|roofing|restor',s): v,why='cleaning_residential',f"generic name; Maps category {cat}"
            elif v is None and RES_CAT.search(cat) and not COM_CAT.search(cat) and not re.search(r'janitor|custodi|commercial|office|building|facilit|corporate|industrial',s): v,why='cleaning_residential',f"Maps category {cat} (residential/exterior), no commercial word in name"
        if v is None: r['fit'],r['fit_reason']='good',f"[MAPS] {why}{tail}"
        elif v=='cleaning_residential': r['fit'],r['fit_reason']='cleaning_residential',f"[MAPS] cleaning_residential: {why}{tail}"
        else: r['fit'],r['fit_reason']=v,f"[MAPS] {why}"
        if r['country']!='US' or (r['state'] or '').strip().upper() not in US: r['fit'],r['fit_reason']='off-niche','[MAPS] non-US or no US state'
    with open(POOL,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
S['pool_file']=POOL if rows else ''
S['rows']=len(rows); S['fit']=dict(collections.Counter(r['fit'] for r in rows)); S['email_type']=dict(collections.Counter(r['email_type'] for r in rows))
# 3 sheet values
HD=["first_name","last_name","full_name","title","email","email_verification_date","company","domain","website","linkedin_url","employee_count","city","state","country","niche","source","pulled_at","fit","fit_reason","mv_result"]
if niche=='pest': HD+=["email_type","reviews_as_of"]
json.dump([[str(r.get(h,'') or '') for h in HD] for r in rows],open(f'{BD}/values.json','w'))
S['sheet_tab']=NI; S['sheet_cols']='A:V' if niche=='pest' else 'A:T'
# 4 QE domain file (no-email + generic-only new rows)
from qe_dedupe import norm_domain
fd,pdm,fd_r,pd_r,HOSTED,PLATFORM,FREE,canon,root=[ns[k] for k in "fd pdm fd_r pd_r HOSTED PLATFORM FREE canon root".split()]
tonight={(r['domain'] or '').strip().lower() for r in rows}
prev=set()
pats=([f'/workspace/qe_bulk/pest_domains_upload*.csv','/workspace/qe_bulk/maps_*/maps_pest_domains_upload_*.csv','/workspace/qe_bulk/2026-10-22_P-CF*/*upload*.csv','/workspace/qe_bulk/t2_retry/pest_t2_upload.csv'] if niche=='pest' else
      ['/workspace/qe_bulk/**/cleaning_*upload*.csv','/workspace/qe_bulk/maps_*/maps_cleaning_domains_upload_*.csv','/workspace/qe_bulk/2026-10-22_C-*/*domains_part*.csv'])
for pat in pats:
    for p in glob.glob(pat,recursive=True):
        if os.path.abspath(p)==os.path.abspath(UP) or 'domain_results' in p: continue
        for r in csv.DictReader(open(p)): prev.add((r.get('domain') or '').strip().lower())
PEST_ON=re.compile(r"pest|termite|extermin|wildlife|critter|rodent|mosquito|bed ?bug|animal (removal|control)|bird control|bat removal|bee removal|wasp|gopher|mole|squirrel|raccoon|skunk|snake|ant control|fumigat",re.I)
PEST_CAT=re.compile(r"pest control|exterminator|wildlife|animal control|bird control|termite|fumigat|mosquito",re.I)
PEST_OFF=re.compile(r"lawn|landscap|tree service|home inspector|inspection|animal shelter|animal rescue|humane society|pet |veterinar|pool|hvac|plumb|roof",re.I)
c=collections.Counter(); up=[]; meta=[]; seen=set()
for r in maps:
    if r['dedupe_status']!='new' or r['email_type'] not in ('none','generic'): continue
    cat=r['category'] or ''
    d=norm_domain(r['domain'] or r['website'])
    if not d or '.' not in d or PLATFORM.search(d+'.') or d in FREE: c['no_usable_domain']+=1; continue
    d=canon(d)
    if HOSTED.search(d): c['site_builder']+=1; continue
    if big_brand(d,r['business_name']) or (niche=='cleaning' and BIG.search(f"{r['business_name']} {d}".lower())): c['big_brand']+=1; continue
    fc=''
    if niche=='pest':
        if PEST_OFF.search(cat+' | '+r['business_name']) and not PEST_ON.search(r['business_name']): c['off_niche']+=1; continue
        v,why=pest_fit(r['business_name'],d,'','','MAPS')
        if v=='off-niche' and not (PEST_ON.search(r['business_name']+' '+d) or PEST_CAT.search(cat)): c['off_niche']+=1; continue
    else:
        if OFFCAT.search(cat): c['off_niche']+=1; continue
        v,why=cleaning_fit(r['business_name'],d,'','','MAPS')
        if v=='off-niche' and COM_CAT.search(cat): v=None
        elif v=='off-niche' and RES_CAT.search(cat): v='cleaning_residential'
        elif v is None and RES_CAT.search(cat) and not COM_CAT.search(cat) and not re.search(r'janitor|custodi|commercial|office|building|facilit|corporate|industrial',f"{r['business_name']} {d}".lower()): v='cleaning_residential'
        if v=='off-niche': c['off_niche']+=1; continue
        fc='cleaning_residential' if v=='cleaning_residential' else 'commercial'
    if d in fd or root(d) in fd_r: c['in_final']+=1; continue
    if (d in pdm or root(d) in pd_r) and d not in tonight: c['in_pool']+=1; continue
    if d in prev: c['already_looked_up']+=1; continue
    if d in seen: c['dup']+=1; continue
    seen.add(d); up.append((fc,d)); c['no_email' if r['email_type']=='none' else 'generic_only']+=1
    m=dict(domain=d,company_name=r['business_name'],city=r['city'],state=r['state'],employee_count='',fit_reason=('cleaning_residential: ' if fc=='cleaning_residential' else '')+f"google maps {niche} category/query: "+(cat or r['query'])[:60],note='')
    if niche=='cleaning': m['fit_class']=fc
    meta.append(m)
if niche=='cleaning':
    up.sort(key=lambda x:x[0]=='cleaning_residential'); c['commercial']=sum(1 for x in up if x[0]=='commercial'); c['residential']=len(up)-c['commercial']
c['upload']=len(up)
with open(UP,'w',newline='') as f:
    w=csv.writer(f); w.writerow(['domain']); [w.writerow([d]) for _,d in up]
with open(META,'w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['domain','company_name','city','state','employee_count','fit_reason','note']+(['fit_class'] if niche=='cleaning' else [])); w.writeheader(); w.writerows(meta)
S['qe']=dict(c); S['qe_file']=UP
json.dump(S,open(f'{BD}/post_summary.json','w'),indent=1); print(json.dumps(S))
