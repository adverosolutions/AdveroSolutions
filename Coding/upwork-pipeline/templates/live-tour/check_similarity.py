#!/usr/bin/python3
"""U-021: fail a tour if its content matches another tour too closely.
Usage: check_similarity.py <job tour folder> [--max-copy 0.20] [--max-labels 0.35] [--max-struct 0.50]
Compares the tour page against every other P/jobs/*/tour/tour.html (and the HubSpot v5 reference).
Text that also appears in the template (the shared frame) is ignored.
Copy score: share of 5-word phrases in common (Jaccard). Label score: share of short labels
(panel titles, chips, nav items, 1 to 4 words) in common. Struct score: share of
element/class sequences inside the app window in common (same panels and layout filled with new words). Exit 0 only if every pair is under both limits."""
import sys, re, glob, os, json, html
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.abspath(os.path.join(HERE, '..', '..'))

class T(HTMLParser):
    def __init__(s):
        super().__init__(); s.skip = 0; s.out = []
    def handle_starttag(s, t, a):
        if t in ('style', 'svg'): s.skip += 1
    def handle_endtag(s, t):
        if t in ('style', 'svg') and s.skip: s.skip -= 1
    def handle_data(s, d):
        if not s.skip and d.strip(): s.out.append(d.strip())

def texts(path):
    return texts_from(open(path, encoding='utf-8', errors='ignore').read())

def texts_from(raw):
    raw = re.sub(r'<!--.*?-->', ' ', raw, flags=re.S)
    p = T(); p.feed(raw)
    out = []
    for chunk in p.out:
        # script blocks: keep quoted strings (captions, notes, data), drop code
        if re.search(r'[;{}()=]', chunk) and len(chunk) > 200:
            out += [html.unescape(m) for m in re.findall(r'"((?:[^"\\]|\\.){3,})"|\'((?:[^\'\\]|\\.){3,})\'', chunk) for m in m if m]
        else:
            out.append(html.unescape(chunk))
    return [re.sub(r'\s+', ' ', x).strip() for x in out if x.strip()]

class S(HTMLParser):
    """Class-token sequence inside the app window (id="app"): the structure a builder fills."""
    def __init__(s):
        super().__init__(); s.depth = 0; s.seq = []
    def handle_starttag(s, t, a):
        d = dict(a)
        if s.depth: s.depth += 1
        elif d.get('id') == 'app': s.depth = 1
        if s.depth and t not in ('br', 'img', 'input', 'path'):
            s.seq.append(t + '.' + '.'.join(sorted((d.get('class') or '').split())))
        if t in ('br', 'img', 'input', 'meta', 'link') and s.depth: s.depth -= 1
    def handle_endtag(s, t):
        if s.depth: s.depth -= 1

def struct(path, n=6):
    raw = open(path, encoding='utf-8', errors='ignore').read()
    p = S(); p.feed(raw); q = p.seq
    return {' '.join(q[i:i+n]) for i in range(len(q)-n+1)}

def frame_texts(path):
    """Text outside the app window in the template = shared frame."""
    raw = open(path, encoding='utf-8', errors='ignore').read()
    i = raw.find('id="app"')
    return texts_from(raw[:raw.rfind('<', 0, i)] if i > 0 else raw)

def norm(x): return re.sub(r'[^a-z0-9 ]', ' ', x.lower())
def shingles(ts, n=5):
    w = norm(' '.join(ts)).split()
    return {' '.join(w[i:i+n]) for i in range(len(w)-n+1)}
def labels(ts):
    return {norm(x).strip() for x in ts if 1 <= len(norm(x).split()) <= 4 and not re.fullmatch(r'[0-9 ]+', norm(x).strip())}

def main():
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(2)
    folder = os.path.abspath(a[0])
    mc = float(a[a.index('--max-copy')+1]) if '--max-copy' in a else 0.20
    mx = float(a[a.index('--max-struct')+1]) if '--max-struct' in a else 0.50
    ml = float(a[a.index('--max-labels')+1]) if '--max-labels' in a else 0.35
    page = next((os.path.join(folder, f) for f in ('tour.html', 'index.html') if os.path.exists(os.path.join(folder, f))), None)
    if not page: print('FAIL no tour.html in', folder); sys.exit(1)
    tpl = frame_texts(os.path.join(HERE, 'tour.html'))
    fs = shingles(tpl)
    fl = labels(texts(os.path.join(HERE, 'tour.html'))) | labels(tpl)  # template labels and code strings never count
    me = texts(page); ms, ml_ = shingles(me) - fs, labels(me) - fl; mst = struct(page)
    others = [p for p in glob.glob(os.path.join(P, 'jobs', '*', 'tour', 'tour.html')) if os.path.abspath(p) != os.path.abspath(page)]
    ref = os.path.join(P, '.local/demo-builder-queue/variants/hubspot-agentic-v5/page-v5.html')
    if os.path.exists(ref): others.append(ref)
    rows, bad = [], 0
    for o in others:
        ot = texts(o); os_, ol = shingles(ot) - fs, labels(ot) - fl; ost = struct(o)
        c = len(ms & os_) / max(1, len(ms | os_)); l = len(ml_ & ol) / max(1, min(len(ml_), len(ol)) or 1)
        x = len(mst & ost) / max(1, len(mst | ost))
        ok = c <= mc and l <= ml and x <= mx
        bad += not ok
        rows.append({'other': os.path.relpath(o, P), 'copy': round(c, 3), 'labels': round(l, 3), 'struct': round(x, 3), 'pass': ok,
                     'shared_labels': sorted(ml_ & ol)[:15] if not ok else []})
    for r in sorted(rows, key=lambda r: -max(r['copy'], r['labels'], r['struct'])):
        print(('PASS' if r['pass'] else 'FAIL'), r['other'], 'copy', r['copy'], 'labels', r['labels'], 'struct', r['struct'], (' shared: ' + ', '.join(r['shared_labels'])) if r['shared_labels'] else '')
    print(json.dumps({'tour': os.path.relpath(page, P), 'compared': len(rows), 'failed': bad, 'max_copy': mc, 'max_labels': ml, 'max_struct': mx}))
    sys.exit(1 if bad else 0)

if __name__ == '__main__': main()
