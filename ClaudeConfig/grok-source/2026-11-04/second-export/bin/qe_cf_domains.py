import csv, glob, os, re, sys, json, collections
sys.path.insert(0, '/home/box/advero/bin'); 
from qe_dedupe import norm_domain, read_csv
from qe_cf_fit import fit
H = os.path.expanduser('~')
# usage: qe_cf_domains.py [COMPANY_FINDER.csv] [OUT_DIR]  (defaults below; pick a fresh OUT_DIR so earlier upload/meta files are not overwritten)
SRC = sys.argv[1] if len(sys.argv) > 1 else f'{H}/advero/state/quickenrich/2026-10-20_pest_control_companyfinder.csv'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/workspace/qe_bulk/next'
# niche (added 2026-10-20 for cleaning): from --niche=cleaning or 'cleaning' in the source file name; default pest_control.
# cleaning adds a fit_class column (commercial | cleaning_residential) to meta/heldout and prefixes residential
# fit_reason with 'cleaning_residential: '; outputs are named cleaning_domains_*.csv. pest output is unchanged.
NICHE = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--niche=')), None) or ('cleaning' if 'cleaning' in os.path.basename(SRC) else 'pest_control')
# ppc (added 2026-10-21): --niche=ppc or 'ppc' in the file name; outputs ppc_domains_*.csv, same columns as pest.
if NICHE == 'pest_control' and '--niche=pest_control' not in sys.argv and 'ppc' in os.path.basename(SRC): NICHE = 'ppc'
assert NICHE in ('pest_control', 'cleaning', 'ppc'), NICHE
PFX = {'pest_control': 'pest', 'cleaning': 'cleaning', 'ppc': 'ppc'}[NICHE]
FREE = {"gmail.com","yahoo.com","hotmail.com","outlook.com","aol.com","icloud.com","msn.com","live.com","comcast.net","att.net","bellsouth.net","sbcglobal.net","verizon.net","me.com","ymail.com","protonmail.com","cox.net","charter.net","earthlink.net"}
PLATFORM = re.compile(r"(^|\.)(facebook|fb|yelp|google|business\.site|sites\.google|wixsite|wix|godaddysites|squarespace|weebly|linkedin|instagram|angi|homeadvisor|thumbtack|bbb|nextdoor|mapquest|yellowpages|linktr)\.")
def ex_domains(paths):
    d = set()
    for p in paths:
        hdr, rows = read_csv(p)
        cols = [h for h in hdr if re.sub(r'[^a-z]','',h.lower()) in ("domain","website","companyurl","url","emaildomain","companywebsite","email")]
        for r in rows:
            for c in cols:
                x = norm_domain(r.get(c) or "")
                if x and x not in FREE and "." in x: d.add(x)
    return d
final = sorted(glob.glob(f'{H}/advero/state/leads/final-leads/*.csv'))
pool = sorted(glob.glob(f'{H}/advero/state/leads/pool/*.csv'))
fd, pdm = ex_domains(final), ex_domains(pool)
staged = ex_domains(sorted(glob.glob(f'{H}/advero/state/leads/staged_leads_*.csv')))
HOSTED = re.compile(r"\.(ueniweb\.com|gorilladesksites\.com|myworkwave\.com|wordpress\.com|godaddysites\.com|bizlistusa\.com|ctcin\.bio|weebly\.com|wixsite\.com|square\.site|business\.site|yahoo\.com)$")
if NICHE == 'cleaning':   # more site builders seen in the cleaning export (pest list left as is)
    HOSTED = re.compile(HOSTED.pattern[:-2] + r"|pagesmack\.com|yolasite\.com|webnode\.com|hostinghaas\.com|voolt\.com|setmore\.com|hocoos\.com|webador\.com|webadorsite\.com|neocities\.org|myfreesites\.net|myshopify\.com|jobbersites\.com|simdif\.com|mailchimpsites\.com|epickpro\.com)$")
JUNK_PREFIX = re.compile(r"^(m|local|signup|us|en|web|home)\.(?=[^.]+\.[a-z]+$)")
def canon(d):
    return JUNK_PREFIX.sub("", d)
def franchise(d):
    return d.count(".") >= 2 and not HOSTED.search(d)
# Lorenzo via COO 2026-10-20 9:49 PM: national chains / corporates are never uploaded
BIG_BRANDS = ["orkin", "rollins", "terminix", "rentokil", "anticimex", "trulynolen", "truly-nolen",
    "arrowexterminators", "arrow-exterminators", "ecolab", "cintas", "abm", "janiking", "jani-king",
    "coverall", "servicemaster", "stanleysteemer", "stanley-steemer", "aramark"]
def big_brand(dom, name=""):
    labels = dom.split(".")[:-1]  # all labels except the TLD
    n = re.sub(r"[^a-z]", "", (name or "").lower())
    for b in BIG_BRANDS:
        bb = b.replace("-", "")
        # domain label starts with the brand (orkin.com, orkinnow.com, abm.com) or the name starts with it
        if any(l.replace("-", "").startswith(bb) for l in labels) or n.startswith(bb):
            if b == "abm" and not any(l == "abm" or l.startswith("abm-") for l in labels):
                continue  # 'abm' prefix is too short to match loosely (abmpest...), exact label only
            if b == "coverall" and not any(l in ("coverall", "coverallnorthamerica", "coverallusa") for l in labels):
                continue  # Coverall cleaning franchise only, not e.g. coverallpests.com
            return b
    return ""
def root(d):  # registrable-ish: last 2 labels (US cos are almost all .com/.net)
    return ".".join(d.split(".")[-2:])
fd_r = {root(x) for x in fd}; pd_r = {root(x) for x in pdm}

rows = list(csv.DictReader(open(SRC, newline='', encoding='utf-8-sig')))
c = collections.Counter(raw=len(rows)); drop = collections.Counter()
kept, seen, meta, held = [], {}, [], []
for r in rows:
    k, why = fit(r, NICHE)
    if not k: drop[why.split("'")[0].split('(')[0].strip()[:70]] += 1; continue
    c['fit_kept'] += 1
    if NICHE == 'cleaning': c[f'fit_kept_{k}'] += 1
    dom = norm_domain(r['URL']) or norm_domain(r['Final Email Domain']) or norm_domain(r['Email Domain'])
    if not dom or "." not in dom or PLATFORM.search(dom + "."):
        alt = norm_domain(r['Final Email Domain']) or norm_domain(r['Email Domain'])
        if alt and "." in alt and not PLATFORM.search(alt + ".") and alt not in FREE: dom = alt
        else: c['no_usable_domain'] += 1; continue
    dom = canon(dom)
    if HOSTED.search(dom):
        c['held_out_site_builder_subdomain'] += 1; held.append(dict(domain=dom, company_name=r['Company Name'].strip(), reason='site-builder subdomain, no own domain', fit_class=k)); continue
    bb = big_brand(dom, r['Company Name'])
    if bb:
        c['excl_big_brand'] += 1; held.append(dict(domain=dom, company_name=r['Company Name'].strip(), reason=f'big brand ({bb})', fit_class=k)); continue
    if dom in seen: c['dup_domain_in_file'] += 1; continue
    seen[dom] = 1
    meta.append(dict(domain=dom, company_name=r['Company Name'].strip(), city=r['City'].strip(), state=r['State'].strip(),
                     employee_count=r['Employee Count'].strip(),
                     fit_reason=(f"cleaning_residential: {why}" if k == 'cleaning_residential' else why),
                     note='franchise/location subdomain: lookup may return franchisor contacts' if franchise(dom) else '', fit_class=k))
c['unique_domains'] = len(meta)
out = []
for m in meta:
    d = m['domain']
    if d in fd: c['excl_final_leads'] += 1; continue
    if d in pdm: c['excl_pool'] += 1; continue
    if d in staged: c['in_staged_2026-10-12_not_excluded'] += 1
    out.append(m)
c['after_exclusion'] = len(out)
if NICHE == 'cleaning': out.sort(key=lambda m: m['fit_class'] != 'commercial')  # commercial first (stable)
os.makedirs(OUT, exist_ok=True)
XC = ['fit_class'] if NICHE == 'cleaning' else []
with open(f'{OUT}/{PFX}_domains_upload.csv','w',newline='') as f:
    w = csv.writer(f); w.writerow(['domain']); [w.writerow([m['domain']]) for m in out]
with open(f'{OUT}/{PFX}_domains_meta.csv','w',newline='',encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['domain','company_name','city','state','employee_count','fit_reason','note'] + XC, extrasaction='ignore'); w.writeheader(); w.writerows(out)
with open(f'{OUT}/{PFX}_domains_heldout.csv','w',newline='',encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['domain','company_name','reason'] + XC, extrasaction='ignore'); w.writeheader(); w.writerows(held)
c['franchise_subdomains_in_upload'] = sum(1 for m in out if m['note'])
if NICHE == 'cleaning':
    for kk in ('commercial', 'cleaning_residential'):
        c[f'unique_{kk}'] = sum(1 for m in meta if m['fit_class'] == kk); c[f'upload_{kk}'] = sum(1 for m in out if m['fit_class'] == kk)
c['final_domains'] = len(fd); c['pool_domains'] = len(pdm)
print(json.dumps(dict(c), indent=1)); print(json.dumps(drop.most_common(), indent=1))
