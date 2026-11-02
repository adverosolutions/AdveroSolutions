"""Pure rendering and local QA for the approved achievement template (Python 3.9)."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NICHES = {
    'recruiting': r'recruit\w*|search|staffing|placements?|hiring',
    'cleaning': r'cleaning|janitorial',
    'bookkeeping': r'tax\w*|accounting|bookkeeping|cpa|payroll',
    'marketing_agency': r'ppc|paid search|google ads|ads|advertising|seo|marketing|web design|branding|social media',
    'pest_control': r'pest|termite|wildlife|mosquito|rodent|extermination',
    'msp': r'it support|managed it|network\w*|cybersecurity|help desk|computer',
    'insurance_broker': r'insurance|benefits|coverage',
    'landscaping': r'landscap\w*|lawn|grounds|tree|snow|irrigation|hardscap\w*',
}
BANNED = r'\b(?:must|bet|probably|gotta|AI|automation|solutions|premier|unparalleled|tailored|comprehensive|innovative|leading|best|strategic|growth|trusted|quality)\b|state.of.the.art|full.service'


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def config():
    return read_json(ROOT / 'personalize/prompts.json', {})


def render(first_name, record):
    cfg = config()
    mode = record.get('mode')
    if mode not in ('researched', 'cold_read'):
        raise ValueError('mode must be researched or cold_read; legacy Y is not supported')
    key = 'template' if mode == 'researched' else 'cold_read_template'
    if not (first_name or '').strip():
        key += '_no_name'
    return cfg[key].format(first_name=(first_name or '').strip(), x=record.get('x', ''),
                           specific=record.get('specific', ''), cold_read=record.get('cold_read', ''))


def digest(record, line):
    return hashlib.sha256(json.dumps({'record': record, 'line': line}, sort_keys=True).encode()).hexdigest()


def evidence_ok(bdir, lid, evidence):
    if not isinstance(evidence, dict):
        return False
    quote, url = evidence.get('quote', ''), evidence.get('url', '')
    if not quote or not url:
        return False
    pages = read_json(Path(bdir) / (lid + '.research.json'), {}).get('pages', [])
    # Exact phrase, allowing only whitespace normalization, on the exact cited page.
    norm = lambda s: ' '.join(s.split())
    return any(p['url'] == url and norm(quote) in norm(p['text']) for p in pages)


def numbers(text):
    text = text.lower().replace(',', '')
    # Compare spoken amounts with website shorthand, preserving the numeric value.
    def expand(m):
        from decimal import Decimal
        scale = {'k': 1000, 'thousand': 1000, 'm': 1000000, 'million': 1000000,
                 'b': 1000000000, 'billion': 1000000000}[m.group(2)]
        return str(Decimal(m.group(1)) * scale)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*(thousand|million|billion|k|m|b)\b', expand, text)
    from decimal import Decimal
    return {Decimal(n) for n in re.findall(r'\d+(?:\.\d+)?', text)}


def validate(bdir, lead, record, line):
    lid = lead['lead_id']
    if not isinstance(record, dict):
        return 'record must be an object'
    for field in ('x', 'specific', 'cold_read', 'specialty', 'mode'):
        if not isinstance(record.get(field, ''), str):
            return 'invalid field type: ' + field
    if not lead.get('company_name', '').strip():
        return 'unresolved company identity'
    country = (lead.get('country') or lead.get('company_country') or '').strip().lower()
    if country and country not in ('us', 'usa', 'united states', 'united states of america'):
        return 'skipped: foreign company'
    if record.get('mode') == 'hold':
        return 'writer hold: ' + str(record.get('hold_reason') or 'unresolved research or approved wording')
    if record.get('y'):
        return 'retired Y field'
    try:
        if line != render(lead.get('first_name', ''), record):
            return 'line differs from the current template or record'
    except (ValueError, KeyError) as exc:
        return str(exc)
    specialty = record.get('specialty', '')
    if specialty and (lead.get('campaign') != 'recruiting' or len(specialty.split()) > 4 or re.search(r'[.!?—–\n\r]|\b(?:AI|automation)\b', specialty, re.I)):
        return 'invalid recruiting specialty'
    x = record.get('x', '')
    if not 3 <= len(x.split()) <= 10:
        return 'X must contain 3-10 words'
    if re.search(r'[.\d&—–?!\n\r-]|\b(you|your|we|our|I)\b', x, re.I):
        return 'invalid punctuation, number or pronoun in X'
    if re.search(BANNED, x, re.I):
        return 'marketing or forbidden word in X'
    if not re.search(r'\b(?:' + NICHES.get(lead.get('campaign'), r'(?!)') + r')\b', x, re.I):
        return 'X does not name the niche'
    for place in (lead.get('company_city', ''), lead.get('company_state', ''), lead.get('company_name', '')):
        if len(place.strip()) > 2 and re.search(r'\b' + re.escape(place.strip()) + r'\b', x, re.I):
            return 'company or location in X'
    if re.search(r'[—–!\n\r]|\d\s*\+|\b(?:must|bet|probably|gotta|AI|automation)\b|no wonder|saw that you do|that.s exciting', line, re.I):
        return 'forbidden wording or punctuation'
    if not evidence_ok(bdir, lid, record.get('x_evidence')):
        # A dead-site fallback may cite an exact reliable lead-data field instead.
        ev = record.get('x_evidence', {})
        if not isinstance(ev, dict):
            return 'invalid X evidence'
        field = ev.get('lead_field')
        if record.get('mode') != 'cold_read' or field not in ('company_description', 'headline') or not ev.get('quote') or ev['quote'] not in lead.get(field, ''):
            return 'missing or unverifiable X evidence'
    if record.get('mode') == 'researched':
        specific = record.get('specific', '')
        if record.get('cold_read') or not 3 <= len(specific.split()) <= 14:
            return 'researched mode needs one specific of 3-14 words'
        if specific.endswith('.') or re.search(r'[!?\n\r]|\$\d+(?:\.\d+)?[KMB]\b', specific):
            return 'specific punctuation or number shorthand'
        ev = record.get('specific_evidence', {})
        if not evidence_ok(bdir, lid, ev):
            return 'missing or unverifiable achievement evidence'
        claim_nums, quote_nums = numbers(specific), numbers(ev['quote'])
        if record.get('achievement_kind') == 'years_in_business' and record.get('founded_year'):
            from datetime import date
            year = record['founded_year']
            if not isinstance(year, int) or year not in quote_nums or year > date.today().year:
                return 'founding year is not supported'
            # Founding year only establishes approximate tenure, not an anniversary date.
            quote_nums = quote_nums | {date.today().year - year}
        if not claim_nums <= quote_nums:
            return 'achievement number not supported by quote'
        if record.get('achievement_kind') == 'review_rating' and not any(n >= 25 for n in quote_nums):
            return 'review achievement requires at least 25 reviews'
        if record.get('achievement_kind') not in config()['achievement_kinds']:
            return 'unknown achievement kind'
    else:
        if record.get('specific') or record.get('specific_evidence'):
            return 'cold read must not carry a fabricated achievement'
        variants = config().get('cold_reads', {}).get(lead.get('campaign'), [])
        if record.get('cold_read') not in variants:
            return 'cold read has no approved variant for this niche'
        cold = record['cold_read']
        if ('Amazon' in cold) != ('amazon' in x.lower()):
            return 'Amazon cold read does not match X'
        if 'leads' in cold and re.search(r'ecommerce|e-commerce|amazon|consumer brands', x, re.I):
            return 'leads cold read does not fit ecommerce'
        if 'campaigns' in cold and not re.search(r'ads|advertising|ppc|marketing|paid search', x, re.I):
            return 'campaign cold read does not fit X'
    return ''


def company_key(lead):
    return ((lead.get('company_name') or '').strip().casefold(),
            (lead.get('company_city') or '').strip().casefold())


def content(line):
    return line.split(', ', 1)[-1].casefold()


def evaluate(bdir, leads, selections, records, lines, history=()):
    flags, counts, used = {}, {}, {}
    seen_ids = set()
    for lead, line in history:
        if lead['lead_id'] in seen_ids:
            continue
        seen_ids.add(lead['lead_id'])
        key = company_key(lead)
        counts[key] = counts.get(key, 0) + 1
        used.setdefault(key, set()).add(content(line))
    for lid, selection in selections.items():
        if selection['tier'] == 'skip':
            continue
        if lid not in leads:
            flags[lid] = 'missing lead'; continue
        lead, rec, line = leads[lid], records.get(lid, {}), lines.get(lid, '')
        why = validate(bdir, lead, rec, line)
        key = company_key(lead)
        if counts.get(key, 0) >= 2:
            why = 'skipped: duplicate company (already 2 contacts)'
        elif content(line) in used.get(key, set()):
            why = 'duplicate company personalization after greeting'
        if why:
            flags[lid] = why
        else:
            counts[key] = counts.get(key, 0) + 1
            used.setdefault(key, set()).add(content(line))
    return flags


def history(bdir):
    """Conservatively count prior exports, deduping lead ids; never scan remote systems."""
    import csv
    bdir = Path(bdir).resolve()
    info = {}
    for path in (ROOT / 'personalize/batches').glob('*/leads.json'):
        if path.parent.resolve() != bdir:
            info.update({r['lead_id']: r for r in read_json(path, [])})
    rows = []
    for path in (ROOT / 'output/daily').glob('day_*.csv'):
        if path.stem == 'day_' + bdir.name:
            continue
        with path.open(encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                if row.get('lead_id') in info:
                    rows.append((info[row['lead_id']], row.get('personalization', '')))
    return rows
