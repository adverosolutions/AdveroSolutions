#!/usr/bin/env python3
"""Polite email finder for business websites listed in a gosom raw CSV.
Fetches at most 4 pages per site (home, contact, about + 1 linked contact/about page),
one request at a time per site, N sites in parallel, 10s timeout, honest User-Agent,
respects robots.txt. Writes emails into the 'emails' column (in place copy -> OUT).
Capped copy (Maps Bot 2026-10-26): bounded EMAIL_RE, 400 KB/response cap, skip >3 MB, .partial checkpoints.
Usage: site_email_crawl.py RAW_IN RAW_OUT [--workers 6] [--retry-status fetch_error,error]
"""
import csv, sys, re, html, time, concurrent.futures as cf
from urllib.parse import urljoin, urlparse
from urllib import robotparser
import requests
csv.field_size_limit(10**9)
UA = "Mozilla/5.0 (X11; Linux x86_64) AdveroLeadResearch/1.0 (+https://adverosolutions.com)"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,24}")  # bounded (capped copy 2026-10-26)
MAX_BYTES = 400000          # cap per response before extract/link-finding
MAX_CONTENT_LENGTH = 3_000_000  # skip responses that declare more than 3 MB
def get_capped(s, url, timeout):
    r = s.get(url, timeout=timeout, allow_redirects=True, stream=True)
    try:
        cl = int(r.headers.get("content-length") or 0)
    except ValueError:
        cl = 0
    if cl > MAX_CONTENT_LENGTH:
        r.close(); r._capped_text = ""; r._too_big = True; return r
    buf = b""; t0 = time.time()
    for chunk in r.iter_content(65536):
        buf += chunk
        if len(buf) >= MAX_BYTES or time.time() - t0 > 20: break
    r.close()
    enc = r.encoding or "utf-8"
    try: txt = buf[:MAX_BYTES].decode(enc, errors="replace")
    except LookupError: txt = buf[:MAX_BYTES].decode("utf-8", errors="replace")
    r._capped_text = txt[:MAX_BYTES]; r._too_big = False
    return r
SKIP_HOSTS = ("facebook.com","instagram.com","yelp.com","google.com","business.site","linktr.ee","nextdoor.com")
def cf_decode(hexs):
    try:
        k=int(hexs[:2],16); return "".join(chr(int(hexs[i:i+2],16)^k) for i in range(2,len(hexs),2))
    except Exception: return ""
def extract(text):
    t=html.unescape(text)
    found=set(m.group(0) for m in EMAIL_RE.finditer(t))
    for h in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', text): found.add(cf_decode(h))
    for h in re.findall(r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)', text): found.add(cf_decode(h))
    return {e.lower().strip(".") for e in found if e and not re.search(r"\.(png|jpe?g|gif|webp|svg|css|js)$", e, re.I)}
def crawl(url):
    if not url: return "", "no_website"
    u=url if "://" in url else "https://"+url
    p=urlparse(u); base=f"https://{p.netloc}"  # try https first; some hosts block/timeout on :80
    if any(h in p.netloc for h in SKIP_HOSTS): return "", "platform_url"
    s=requests.Session(); s.headers["User-Agent"]=UA
    rp=robotparser.RobotFileParser()
    try:
        r=get_capped(s,base+"/robots.txt",8); rp.parse(r._capped_text.splitlines() if r.status_code==200 else [])
    except Exception: rp.parse([])
    pages=[base+"/", base+"/contact", base+"/contact-us", base+"/about-us"]
    emails=set(); status="ok"; fetched=0; extra_added=False
    while pages and fetched<5:
        pg=pages.pop(0)
        if not rp.can_fetch(UA,pg): status="robots_disallow"; continue
        try:
            r=get_capped(s,pg,10); fetched+=1
        except Exception as e:
            if fetched==0 and pg==base+"/" and base.startswith("https://"):
                base="http://"+p.netloc; pages=[base+"/", base+"/contact", base+"/contact-us", base+"/about-us"]; continue
            status="fetch_error"
            if fetched==0 and pg==base+"/": break
            continue
        if r.status_code in (403,429,503) and fetched==1: status=f"http_{r.status_code}"
        if r.status_code!=200 or "html" not in r.headers.get("content-type","") or r._too_big: continue
        text=r._capped_text
        emails|=extract(text)
        if not extra_added:
            for href in re.findall(r'href="([^"#]{1,2000})"', text):
                if re.search(r"contact|about|team|staff", href, re.I):
                    full=urljoin(r.url, href)
                    if urlparse(full).netloc.replace("www.","")==p.netloc.replace("www.","") and full not in pages:
                        pages.insert(0, full); extra_added=True; break
        time.sleep(0.5)
    return ";".join(sorted(emails)), (status if emails or status!="ok" else "no_email_found")
def main():
    src,dst=sys.argv[1],sys.argv[2]
    workers=int(sys.argv[sys.argv.index("--workers")+1]) if "--workers" in sys.argv else 6
    rows=list(csv.DictReader(open(src,newline="",encoding="utf-8",errors="replace")))
    if not rows: print("no rows"); return
    cols=list(rows[0].keys())
    if "email_crawl_status" not in cols: cols.append("email_crawl_status")
    retry=sys.argv[sys.argv.index("--retry-status")+1].split(",") if "--retry-status" in sys.argv else None
    todo=[r for r in rows if retry is None or r.get("email_crawl_status") in retry]
    if retry:
        for r in todo: r["emails"]=""
    def dump(path):
        w=csv.DictWriter(open(path,"w",newline="",encoding="utf-8"),fieldnames=cols); w.writeheader(); w.writerows(rows)
    done=0; t_last=time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        futs={ex.submit(crawl,(r.get("website") or "").strip()):r for r in todo}
        for f in cf.as_completed(futs):
            r=futs[f]
            try: em,stt=f.result()
            except Exception as e: em,stt="",f"error"
            r["emails"]=";".join(x for x in [r.get("emails",""),em] if x); r["email_crawl_status"]=stt
            done+=1
            if done%100==0 or time.time()-t_last>120:
                dump(dst+".partial"); t_last=time.time()
                print(f"progress {done}/{len(todo)} {time.strftime('%H:%M:%S')}", flush=True)
    w=csv.DictWriter(open(dst,"w",newline="",encoding="utf-8"),fieldnames=cols); w.writeheader(); w.writerows(rows)
    from collections import Counter; print(Counter(r["email_crawl_status"] for r in rows))
main()
