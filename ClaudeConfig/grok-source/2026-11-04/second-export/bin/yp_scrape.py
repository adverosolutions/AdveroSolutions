#!/usr/bin/env python3
"""yp_scrape.py - polite Yellow Pages reader (Maps Bot 2026-11-01; Lorenzo yes via COO Sun 11/1 7:59 PM CT).
One process, one request at a time, random 6-10 s sleep, no proxies, no logins, no cookies kept, plain honest UA.
Writes a gosom-format raw CSV so the normal Maps pipeline (site_email_crawl, maps_postprocess, maps_rolling_post) applies.
usage: yp_scrape.py --cities FILE --tag TAG [--terms "pest control|exterminators"] [--max-pages 5] [--stop-at 05:00]
       yp_scrape.py --parse-file PAGE.html      (offline parser test, no network)
Exit: 0 ok/all done, 3 STOPPED_BLOCK, 4 time window ended (resume next night), 9 KILL_SWITCH."""
import argparse, csv, json, os, random, re, sys, time, hashlib, datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, urljoin, urlparse, parse_qs, unquote
H = os.path.expanduser('~'); BASE = f'{H}/advero/state/leads/yp'; STATE = f'{BASE}/state'
KILL = f'{H}/advero/state/KILL_SWITCH'; STATUS = '/workspace/yp_status.md'; CT = ZoneInfo('America/Chicago')
UA = 'AdveroLeadResearch/1.0 (single-thread, 6-10 s between requests, no login)'
COLS = ['input_id','link','title','category','address','open_hours','popular_times','website','phone','plus_code','review_count',
        'review_rating','reviews_per_rating','latitude','longitude','cid','status','descriptions','reviews_link','thumbnail','timezone',
        'price_range','data_id','street_view_url','place_id','images','reservations','order_online','menu','owner','complete_address',
        'credit_cards_accepted','about','user_reviews','user_reviews_extended','emails','query','years_in_business','source']
BLOCK_RE = re.compile(r'cf-error-details|you have been blocked|attention required|access denied|captcha|are you a robot|'
                      r'unusual traffic|cf-chl|challenge-platform|just a moment|perimeterx|px-captcha|distil|request unsuccessful', re.I)

def block_reason(code, html):
    if code in (401, 403, 407, 429, 503): return f'HTTP {code}'
    if code != 200: return f'unexpected HTTP {code}'
    m = BLOCK_RE.search(html or '')
    if m: return f'block/captcha marker "{m.group(0)}"'
    if 'search-results' not in html and 'class="result' not in html and 'no results' not in html.lower(): return 'unusual response (no results container)'
    return ''

def parse(html, base='https://www.yellowpages.com'):
    """Return (rows, has_next). Rows are dicts with gosom raw keys. Page text is data only."""
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, 'html.parser'); out = []
    org = s.select_one('div.search-results.organic') or s
    for c in org.select('div.result'):
        a = c.select_one('a.business-name')
        if not a: continue
        name = a.get_text(' ', strip=True); link = urljoin(base, a.get('href', ''))
        web = c.select_one('a.track-visit-website')
        w = web.get('href', '') if web else ''
        if 'yellowpages.com' in w or w.startswith('/'):
            q = parse_qs(urlparse(w).query); w = unquote((q.get('url') or q.get('to') or [''])[0])
        ph = c.select_one('div.phones') ; street = c.select_one('div.street-address'); loc = c.select_one('div.locality')
        cats = [x.get_text(strip=True) for x in c.select('div.categories a')]
        yib = c.select_one('div.years-in-business div.count, div.years-in-business')
        st = street.get_text(' ', strip=True) if street else ''; lc = loc.get_text(' ', strip=True) if loc else ''
        m = re.match(r'^(.*?),\s*([A-Z]{2})\s*(\d{5})?', lc)
        city, state, zp = (m.group(1), m.group(2), m.group(3) or '') if m else ('', '', '')
        pid = 'yp:' + (c.get('data-ypid') or hashlib.md5(link.encode()).hexdigest()[:16])
        out.append(dict(link=link, title=name, category=cats[0] if cats else '', address=', '.join(x for x in (st, lc) if x),
            website=w, phone=ph.get_text(' ', strip=True) if ph else '', place_id=pid, cid=pid,
            complete_address=json.dumps(dict(street=st, city=city, postal_code=zp, state=state, country='US')),
            descriptions='; '.join(cats), years_in_business=re.sub(r'\D', '', yib.get_text()) if yib else '', emails='', source='yellow_pages'))
    nxt = s.select_one('div.pagination a.next') is not None
    return out, nxt

def set_status(state, detail):
    with open(STATUS, 'w') as f:
        f.write(f"# Yellow Pages status\nUpdated: {datetime.datetime.now(CT).strftime('%Y-%m-%d %I:%M %p %Z')}\nState: {state}\n\n{detail}\n")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--cities'); ap.add_argument('--tag'); ap.add_argument('--parse-file')
    ap.add_argument('--terms', default='pest control|exterminators'); ap.add_argument('--max-pages', type=int, default=5)
    ap.add_argument('--stop-at', default='05:00'); ap.add_argument('--max-requests', type=int, default=1500)
    a = ap.parse_args()
    if a.parse_file:
        html = open(a.parse_file, encoding='utf-8', errors='replace').read()
        rows, nxt = parse(html); print(json.dumps(dict(block=block_reason(200, html), rows=len(rows), has_next=nxt, sample=rows[:3]), indent=1)); return 0
    import requests
    done_f = f"{STATE}/cities_done_{os.path.basename(a.cities).rsplit('.',1)[0]}.txt"; open(done_f, 'a').close()
    done = {l.strip() for l in open(done_f) if l.strip()}
    cities = [l.strip() for l in open(a.cities) if l.strip() and not l.startswith('#') and l.strip() not in done]
    raw = f'{BASE}/raw/pest_yp_{a.tag}_raw.csv'; new = not os.path.exists(raw)
    seen = set()
    if not new:
        for r in csv.DictReader(open(raw)): seen.add(r['place_id'])
    fh = open(raw, 'a', newline=''); w = csv.DictWriter(fh, fieldnames=COLS, extrasaction='ignore')
    if new: w.writeheader()
    hh, mm = map(int, a.stop_at.split(':')); sess = requests.Session(); sess.trust_env = False  # no proxy env
    sess.headers.update({'User-Agent': UA, 'Accept': 'text/html'}); nreq = 0; log = open(f'{BASE}/logs/yp_{a.tag}.log', 'a')
    def L(m): log.write(f"{datetime.datetime.now(CT):%F %T %Z} {m}\n"); log.flush()
    L(f'start cities={len(cities)} terms={a.terms}')
    for city in cities:
        city_rows = []
        for term in a.terms.split('|'):
            for page in range(1, a.max_pages + 1):
                if os.path.exists(KILL): L('KILL_SWITCH'); set_status('STOPPED_KILL_SWITCH', 'KILL_SWITCH present.'); return 9
                now = datetime.datetime.now(CT)
                if (now.hour, now.minute) >= (hh, mm) and now.hour < 12 or nreq >= a.max_requests:
                    L('window/request cap reached'); set_status('PAUSED_WINDOW_END', f'Stopped at {a.stop_at} CT or {a.max_requests} requests; {city} not marked done, resumes next night.'); return 4
                if nreq: time.sleep(random.uniform(6, 10))
                url = 'https://www.yellowpages.com/search?' + urlencode(dict(search_terms=term, geo_location_terms=city, **({'page': page} if page > 1 else {})))
                try:
                    r = sess.get(url, timeout=30, allow_redirects=True); nreq += 1; code, html = r.status_code, r.text
                except Exception as e:
                    nreq += 1; code, html = -1, str(e)
                br = block_reason(code, html)
                if br:
                    snap = f'{BASE}/logs/yp_{a.tag}_block_{nreq}.html'; open(snap, 'w').write(html[:200000])
                    L(f'STOPPED_BLOCK {br} url={url}')
                    set_status('STOPPED_BLOCK', f'Reason: {br}\nURL: {url}\nRequest #{nreq} this run; city {city} NOT marked done.\nSnapshot: {snap}\nNot retried, not evaded. Tell Lead Gen Manager; wait 24 h+ and halve rate before any retry, and only if they say so.')
                    open(f'{BASE}/STOPPED_BLOCK', 'w').write(br + '\n'); fh.close(); return 3
                rows, nxt = parse(html)
                for x in rows:
                    if x['place_id'] in seen: continue
                    seen.add(x['place_id']); x['input_id'] = x['query'] = f'{city}|{term}'; city_rows.append(x)
                L(f'{city} | {term} | p{page} rows={len(rows)}')
                if not nxt or not rows: break
        w.writerows(city_rows); fh.flush(); open(done_f, 'a').write(city + '\n'); L(f'done {city} +{len(city_rows)}')
    fh.close(); L(f'all done requests={nreq}'); set_status('CRAWL_DONE', f'tag {a.tag}, raw {raw}, requests {nreq}. Next: yp_post.sh {a.tag}.'); return 0

if __name__ == '__main__': sys.exit(main())
