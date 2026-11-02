"""Read-only website research: homepage plus up to four same-site proof pages."""
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

LIMIT = 2_000_000
PROOF = re.compile(r'case.?stud|results?|portfolio|testimonials?|reviews?|awards?|press|about|our.story|who.we.are|success.stor|our.work|recognition|certification|our.company', re.I)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.hidden = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg', 'template'):
            self.hidden.append(tag)
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    @property
    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(self.parts)).strip()


def host(url):
    return re.sub(r'^www\.', '', (urllib.parse.urlsplit(url).hostname or '').lower())


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError('page exceeds research size limit; not retained as complete')
        if 'html' not in response.headers.get('Content-Type', 'text/html'):
            raise ValueError('not an HTML page')
        return response.geturl(), raw.decode(response.headers.get_content_charset() or 'utf-8', 'replace')


def collect(site, fetch_fn=None):
    fetch_fn = fetch_fn or fetch
    if not site:
        return {'pages': [], 'errors': [{'url': '', 'reason': 'missing website'}]}
    site = site if site.startswith(('http://', 'https://')) else 'https://' + site
    pages, errors, queue, seen = [], [], [site], set()
    allowed_host = None
    while queue and len(seen) < 5:
        target = queue.pop(0)
        if target in seen:
            continue
        seen.add(target)
        try:
            url, markup = fetch_fn(target)
            if allowed_host and host(url) != allowed_host:
                raise ValueError('proof page redirects off the company site')
            page = Page(); page.feed(markup)
            if not page.text:
                raise ValueError('empty readable page')
            if allowed_host is None:
                allowed_host = host(url)
            if not any(p['url'] == url for p in pages):
                pages.append({'url': url, 'text': page.text, 'kind': 'home' if len(seen) == 1 else 'proof'})
            candidates = []
            for href in page.links:
                candidate = urllib.parse.urldefrag(urllib.parse.urljoin(url, html.unescape(href)))[0]
                parsed = urllib.parse.urlsplit(candidate)
                if parsed.scheme not in ('https', 'http') or host(candidate) != allowed_host:
                    continue
                if PROOF.search(parsed.path) and candidate not in seen and candidate not in queue:
                    candidates.append(candidate)
            # Results and case studies outrank generic about pages.
            queue.extend(sorted(set(candidates), key=lambda u: (bool(re.search(r'about|our.story|who.we.are', u, re.I)), u)))
        except Exception as exc:
            errors.append({'url': target, 'reason': str(exc)[:250]})
    return {'pages': pages, 'errors': errors}


def save(bdir, lead_id, result):
    bdir = Path(bdir)
    (bdir / (lead_id + '.research.json')).write_text(json.dumps(result, indent=2))
    text = '\n\n'.join('[{} {}]\n{}'.format(p['kind'].upper(), p['url'], p['text']) for p in result['pages'])
    (bdir / (lead_id + '.txt')).write_text(text)
    return text, [p['url'] for p in result['pages']]


def main():
    import sys
    bdir = Path(sys.argv[1])
    leads = json.loads((bdir / 'leads.json').read_text())
    for lead in leads:
        text, urls = save(bdir, lead['lead_id'], collect(lead.get('company_website', '')))
        lead.update(text_file=lead['lead_id'] + '.txt', source_urls=urls,
                    route='TIER2_CANDIDATE' if text else 'TIER1_ONLY')
        print(lead['lead_id'], len(urls), 'pages')
    (bdir / 'leads.json').write_text(json.dumps(leads, indent=2))


if __name__ == '__main__':
    main()
