#!/usr/bin/env python3
"""Normalize gosom google-maps-scraper CSV -> pest lead CSV, dedupe vs final-leads + pool (domain & email).
Usage: maps_postprocess.py RAW_CSV OUT_CSV [--stats STATS_JSON] [--suppress-file DO_NOT_RELOAD_CSV]
Suppression (Lorenzo's rule 2026-10-21): emails in ~/advero/state/reactivation/do_not_reload.csv
with suppress_until still in the future (America/Chicago) are removed from every email column.
A row left with no email that would otherwise be new gets dedupe_status=suppressed, so it is not
appended or sent to QuickEnrich Domain w/Emails. Stats: suppressed (emails removed), suppressed_rows,
suppression on/off. Missing/unreadable file -> loud warning, run continues, suppression off.
reviews_as_of (2026-10-22): last column, YYYY-MM-DD (America/Chicago) date the Maps rating/reviews
were pulled, set on rows with rating or reviews (blank otherwise). Default = today in CT (the scrape
night); override with --reviews-as-of YYYY-MM-DD when re-processing an older raw file.
"""
import csv, sys, re, glob, json, os
from urllib.parse import urlparse
from datetime import datetime
from zoneinfo import ZoneInfo
csv.field_size_limit(10**9)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suppression  # do_not_reload hold-out (read only)
import client_index  # shared client INDEX.csv check (read only)
HOME = os.path.expanduser("~")
FINAL = f"{HOME}/advero/state/leads/final-leads/final_pest_control_all_sources_output.csv"
POOL_GLOB = f"{HOME}/advero/state/leads/pool/*pest*.csv"
MAPS_GLOB = f"{HOME}/advero/state/leads/maps/pest_*.csv"
GENERIC = {"info","contact","office","admin","sales","service","services","support","hello","help",
  "customerservice","customercare","care","inquiries","inquiry","enquiries","mail","email","team","billing",
  "accounts","accounting","dispatch","schedule","scheduling","booking","appointments","reception","frontdesk",
  "marketing","hr","jobs","careers","webmaster","noreply","no-reply","pest","pestcontrol","bugs","termite",
  "estimates","quotes","customers","general","main","owner","contactus","customerinfo","ask","askus","questions","request","requests","solutions","pestcontrolservice","press","media","orders"}
FREEMAIL = {"gmail.com","yahoo.com","hotmail.com","outlook.com","aol.com","icloud.com","live.com","msn.com","comcast.net","att.net","sbcglobal.net","bellsouth.net","verizon.net","ymail.com","me.com"}
JUNK_DOM = ("sentry","wixpress.com","example.com","domain.com","godaddy.com","yourdomain","email.com","sentry.io","wix.com","squarespace.com","png","jpg","jpeg","gif","webp","svg")
PLATFORM = ("facebook.com","instagram.com","yelp.com","google.com","business.site","linktr.ee","nextdoor.com","angi.com","homeadvisor.com","thumbtack.com","bbb.org","sites.google.com")

def domain_of(url):
    if not url: return ""
    u = url.strip()
    if "://" not in u: u = "http://" + u
    try: h = urlparse(u).hostname or ""
    except Exception: return ""
    h = h.lower()
    h = h[4:] if h.startswith("www.") else h
    parts = h.split(".")
    if len(parts) > 2 and not (len(parts[-1]) == 2 and parts[-2] in ("co","com","org","net")):
        h = ".".join(parts[-2:])   # locations.trulynolen.com -> trulynolen.com
    return h

def clean_emails(raw):
    out=[]
    for e in re.split(r"[,;\s]+", raw or ""):
        e=re.sub(r"^(%20|%3c|mailto:)+","",e.strip().strip(".").lower())
        if not re.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", e): continue
        d=e.split("@")[1]
        if any(j in d for j in JUNK_DOM) or re.search(r"\.(png|jpe?g|gif|webp|svg)$", e): continue
        if re.fullmatch(r"[0-9a-f]{20,}", e.split("@")[0]): continue
        if e.split("@")[0] in ("example","you","your","name","yourname","email","user","test","john.doe","jane","johndoe"): continue
        if e not in out: out.append(e)
    return out

def is_generic(e):
    lp=e.split("@")[0]
    return lp in GENERIC or re.sub(r"[0-9._\-]","",lp) in GENERIC

CHAINS = {"terminix.com","orkin.com","rollins.com","rentokil.com","aptivepestcontrol.com","arrowexterminators.com",
  "trulynolen.com","hawxservices.com","moxieservices.com","pestdefense.com","jcehrlich.com","ehrlichpest.com",
  "massey.com","masseyservices.com","cooksbugs.com","abchomeandcommercial.com","critterstop.com","crittercontrol.com",
  "altapestcontrol.com","northwestexterminating.com","hometeampestdefense.com","sprague.com","clarkpest.com",
  "westernpest.com","presto-x.com","bulwarkexterminating.com","pointepest.com","mosquitojoe.com","mosquitosquad.com",
  "mosquitoshield.com","naturalcarepestcontrol.com","greenix.com","brookspestsolutions.com","schendelpest.com"}
FIT_RE = re.compile(r"pest|extermin|termite|wildlife|mosquito|bee |bee$|rodent|bed ?bug|fumigat|animal control", re.I)
STATE_RE = re.compile(r",\s*([A-Za-z .'-]+),\s*([A-Z]{2})\s*\d{5}")

def load_existing(exclude_path):
    doms, ems = set(), set()
    files=[FINAL]+glob.glob(POOL_GLOB)+[f for f in glob.glob(MAPS_GLOB) if os.path.abspath(f)!=os.path.abspath(exclude_path)]
    for f in files:
        if not os.path.exists(f): continue
        with open(f, newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                for k,v in r.items():
                    if not k or not v: continue
                    kl=k.lower().strip()
                    if kl in ("email","emails","emails_all","home page email","email_named","email_generic"):
                        for e in clean_emails(v): ems.add(e)
                    if kl in ("domain","company url","website","email domain"):
                        d=domain_of(v)
                        if d and d not in FREEMAIL and not any(p in d for p in PLATFORM): doms.add(d)
    return doms, ems, files

def main():
    raw, out = sys.argv[1], sys.argv[2]
    stats_path = sys.argv[sys.argv.index("--stats")+1] if "--stats" in sys.argv else None
    as_of = sys.argv[sys.argv.index("--reviews-as-of")+1] if "--reviews-as-of" in sys.argv else datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of): sys.exit(f"--reviews-as-of must be YYYY-MM-DD, got {as_of!r}")
    doms, ems, files = load_existing(out)
    sup = suppression.load(sys.argv[sys.argv.index("--suppress-file")+1] if "--suppress-file" in sys.argv else None)
    sup_hits = []
    cli = client_index.load(); cli_hits = []
    rows=[]; seen_place=set(); seen_dom=set()
    st=dict(raw_rows=0,places=0,with_website=0,with_any_email=0,with_named_email=0,generic_only=0,
            dup_existing=0,dup_in_batch=0,new_after_dedupe=0,new_with_email=0,new_named=0,new_generic_only=0,
            closed_skipped=0, suppressed=0, suppressed_rows=0, existing_domains=len(doms), existing_emails=len(ems))
    with open(raw, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            st["raw_rows"]+=1
            pid=r.get("place_id") or r.get("cid") or r.get("link")
            if pid in seen_place: continue
            seen_place.add(pid); st["places"]+=1
            status=(r.get("status") or "").lower()
            if "closed" in status and "permanent" in status: st["closed_skipped"]+=1
            web=(r.get("website") or "").strip()
            dom=domain_of(web)
            if dom and any(p in dom for p in PLATFORM): dom=""
            emails=[e for e in clean_emails(r.get("emails",""))
                    if dom and (e.split("@")[1]==dom or e.split("@")[1].endswith("."+dom) or e.split("@")[1] in FREEMAIL)]
            if len(emails)>4: emails=[]  # multi-location role boxes (dallas@, houston@...) - not useful
            hit=[e for e in emails if e in sup["active"]]
            if hit:
                st["suppressed"]+=len(hit); sup_hits.extend(hit)
                emails=[e for e in emails if e not in sup["active"]]
            only_suppressed = bool(hit) and not emails
            chain = dom in CHAINS
            fit = "good" if FIT_RE.search((r.get("category","") or "")+" "+(r.get("title","") or "")) else "check"
            named=[e for e in emails if not is_generic(e) and e.split("@")[1] not in FREEMAIL]
            freem=[e for e in emails if e.split("@")[1] in FREEMAIL]
            generic=[e for e in emails if is_generic(e) and e not in freem]
            if web: st["with_website"]+=1
            if emails: st["with_any_email"]+=1
            if named: st["with_named_email"]+=1
            elif freem: st["freemail_only"]=st.get("freemail_only",0)+1
            elif generic: st["generic_only"]+=1
            addr=r.get("address","")
            city=state=""
            try:
                ca=json.loads(r.get("complete_address") or "{}")
                city=ca.get("city",""); state=ca.get("state","")
            except Exception: pass
            m=STATE_RE.search(addr)
            if m:
                city = city or m.group(1).strip()
                if not state or len(state)!=2: state=m.group(2)
            iid=r.get("input_id","")
            is_dup = (dom and dom in doms) or any(e in ems for e in emails)
            in_batch = bool(dom) and dom in seen_dom
            if dom: seen_dom.add(dom)
            if is_dup: st["dup_existing"]+=1; dd="existing"
            elif in_batch: st["dup_in_batch"]+=1; dd="batch_dup"
            elif only_suppressed: st["suppressed_rows"]+=1; dd="suppressed"
            elif any(client_index.match(cli, e, dom) for e in (emails or [""])):
                cli_hits.append(dom or emails[0]); dd="client_known"
            elif chain: st["national_chain"]=st.get("national_chain",0)+1; dd="national_chain"
            else:
                dd="new"; st["new_after_dedupe"]+=1
                if emails: st["new_with_email"]+=1
                if named: st["new_named"]+=1
                elif freem: st["new_freemail_only"]=st.get("new_freemail_only",0)+1
                elif generic: st["new_generic_only"]+=1
            rows.append({"business_name":r.get("title",""),"category":r.get("category",""),"phone":r.get("phone",""),
              "website":web,"domain":dom,"address":addr,"city":city,"state":state,
              "rating":r.get("review_rating",""),"reviews":r.get("review_count",""),
              "emails_all":";".join(emails),"email_named":";".join(named),"email_freemail":";".join(freem),"email_generic":";".join(generic),
              "email_type":"named" if named else ("freemail" if freem else ("generic" if generic else "none")),
              "dedupe_status":dd,"fit":fit,"chain":"yes" if chain else "","business_status":r.get("status",""),"query":(r.get("query") or iid),
              "maps_link":r.get("link",""),"place_id":r.get("place_id",""),"source":"google_maps_gosom",
              "reviews_as_of": as_of if ((r.get("review_rating") or "").strip() or (r.get("review_count") or "").strip()) else ""})
    cols=list(rows[0].keys()) if rows else ["business_name"]
    with open(out,"w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); w.writerows(rows)
    p=lambda a: round(100*a/st["places"],1) if st["places"] else 0
    st.update(pct_website=p(st["with_website"]),pct_any_email=p(st["with_any_email"]),
              pct_named=p(st["with_named_email"]),pct_generic_only=p(st["generic_only"]),pct_freemail_only=p(st.get("freemail_only",0)),dedupe_files=len(files))
    st.update(suppression.summary(sup, st["suppressed"], sup_hits))
    st.update(client_index.summary(cli, cli_hits))
    print(json.dumps(st,indent=1))
    if stats_path: json.dump(st,open(stats_path,"w"),indent=1)
main()
