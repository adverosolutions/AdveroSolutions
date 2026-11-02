import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

PERSONALIZE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PERSONALIZE))
from current import config, digest, evaluate, render, validate
from research import collect, save
from daily_apply import review


@pytest.fixture
def batch(tmp_path):
    lead = {'lead_id': 'TEST-1', 'first_name': 'Brian', 'company_name': 'Example Agency',
            'company_city': 'Austin', 'company_state': 'Texas', 'campaign': 'marketing_agency',
            'sheet_row': 2, 'route': 'TIER2_CANDIDATE'}
    rec = {'mode': 'researched', 'x': 'SEO and PPC', 'specific': 'serving over 500 clients',
           'achievement_kind': 'total', 'cold_read': '', 'specialty': '',
           'x_evidence': {'quote': 'We do SEO and PPC.', 'url': 'https://example.test/'},
           'specific_evidence': {'quote': 'We have served over 500 clients.', 'url': 'https://example.test/results'}}
    save(tmp_path, lead['lead_id'], {'pages': [
        {'kind': 'home', 'url': 'https://example.test/', 'text': 'We do SEO and PPC.'},
        {'kind': 'proof', 'url': 'https://example.test/results', 'text': 'We have served over 500 clients.'}], 'errors': []})
    (tmp_path / 'leads.json').write_text(json.dumps([lead]))
    (tmp_path / 'select.json').write_text(json.dumps([dict(lead, tier=2, angle='test')]))
    return tmp_path, lead, rec


def test_research_retains_home_tail_proof_and_errors():
    pages = {'https://example.test/': ('https://example.test/', '<script>fake</script><p>' + 'content ' * 1500 + 'Tail achievement</p><a href="/results">Results</a><a href="/awards">Awards</a><a href="https://foreign.test/reviews">external</a>'),
             'https://example.test/results': ('https://example.test/results', '<p>Revenue grew 30% &amp; more.</p>')}
    def fetch(url):
        if url not in pages:
            raise RuntimeError('unavailable')
        return pages[url]
    result = collect('https://example.test/', fetch)
    assert 'Tail achievement' in result['pages'][0]['text']
    assert 'fake' not in result['pages'][0]['text']
    assert len(result['pages']) == 2
    assert 'Revenue grew 30% & more.' in result['pages'][1]['text']
    assert len(result['errors']) == 1


def test_research_page_limit_and_offsite_redirect():
    called = []
    def fetch(url):
        called.append(url)
        return url, '<p>Text</p>' + ''.join('<a href="/results/{}">proof</a>'.format(i) for i in range(8))
    assert len(collect('https://example.test/', fetch)['pages']) == 5
    assert len(called) == 5
    def redirect(url):
        if url.endswith('results'):
            return 'https://foreign.test/', '<p>Foreign result</p>'
        return url, '<p>Home</p><a href="/results">Result</a>'
    result = collect('https://example.test/', redirect)
    assert len(result['pages']) == 1 and result['errors']


def test_current_and_no_name_render(batch):
    path, lead, record = batch
    line = render('Brian', record)
    assert line == 'Hey Brian, I know that you do SEO and PPC. Congrats on serving over 500 clients. Was wondering if I can run something by you.'
    assert validate(path, lead, record, line) == ''
    assert render('', record).startswith('Hey, I know')
    assert validate(path, lead, record, line.replace('I know', 'saw'))


@pytest.mark.parametrize('change', ['quote', 'url', 'number', 'legacy', 'blank', 'line'])
def test_factual_and_template_errors_hold(batch, change):
    path, lead, rec = batch
    if change == 'quote': rec['specific_evidence']['quote'] = 'Invented 500 clients.'
    elif change == 'url': rec['specific_evidence']['url'] = 'https://another.test/'
    elif change == 'number': rec['specific'] = 'serving over 900 clients'
    elif change == 'legacy': rec['y'] = 'you must know everyone'
    elif change == 'blank': rec['specific'] = ''
    line = render('Brian', rec)
    if change == 'line': line += ' No more chasing leads.'
    assert validate(path, lead, rec, line)


def test_spoken_millions_and_review_threshold(batch):
    path, lead, rec = batch
    result = json.loads((path / 'TEST-1.research.json').read_text())
    result['pages'][1]['text'] = 'Managed $6M in monthly ad spend. Rated 4.9 with 12 reviews.'
    save(path, 'TEST-1', result)
    rec.update(specific='managing $6 million in monthly ad spend')
    rec['specific_evidence']['quote'] = 'Managed $6M in monthly ad spend.'
    assert validate(path, lead, rec, render('Brian', rec)) == ''
    rec.update(specific='the 4.9 rating across 12 reviews', achievement_kind='review_rating')
    rec['specific_evidence']['quote'] = 'Rated 4.9 with 12 reviews.'
    assert '25 reviews' in validate(path, lead, rec, render('Brian', rec))


def test_cold_read_and_unapproved_niche(batch):
    path, lead, rec = batch
    rec.update(mode='cold_read', specific='', specific_evidence={}, achievement_kind='',
               cold_read=config()['cold_reads']['marketing_agency'][3])
    assert validate(path, lead, rec, render('Brian', rec)) == ''
    assert 'Congrats on' not in render('Brian', rec)
    lead['campaign'] = 'bookkeeping'; rec['x'] = 'taxes and bookkeeping'
    assert 'approved variant' in validate(path, lead, rec, render('Brian', rec))


def test_company_duplicate_and_historical_cap(batch):
    path, lead, rec = batch
    other = dict(lead, lead_id='TEST-2', first_name='Anne')
    save(path, 'TEST-2', json.loads((path / 'TEST-1.research.json').read_text()))
    selections = {l['lead_id']: dict(l, tier=2) for l in (lead, other)}
    records = {'TEST-1': rec, 'TEST-2': rec}
    lines = {l['lead_id']: render(l['first_name'], rec) for l in (lead, other)}
    flags = evaluate(path, {'TEST-1': lead, 'TEST-2': other}, selections, records, lines)
    assert 'duplicate' in flags['TEST-2']
    prior = [(dict(lead, lead_id='OLD-1'), 'Old one'), (dict(lead, lead_id='OLD-2'), 'Old two')]
    flags = evaluate(path, {'TEST-1': lead, 'TEST-2': other}, selections, records, lines, prior)
    assert all('already 2' in value for value in flags.values())


def test_local_cli_review_never_opens_sheets_or_autoapproves(batch):
    path, lead, rec = batch
    (path / 'x_0.json').write_text(json.dumps([dict(rec, lead_id='TEST-1')]))
    command = [sys.executable, str(PERSONALIZE / 'tools/review.py'), str(path)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    rows = json.loads((path / 'review.json').read_text())
    assert rows[0]['status'] == 'needs_review'
    assert len((path / 'reviewed.csv').read_text().splitlines()) == 1
    (path / 'approved.json').write_text('{"lead_ids":["TEST-1"]}')
    assert review(path)[0]['status'] == 'needs_review'
    (path / 'human_review.json').write_text(json.dumps({'TEST-1': rows[0]['review_digest']}))
    assert review(path)[0]['status'] == 'reviewed'
    rec['specific'] = 'serving over 900 clients'
    (path / 'x.json').write_text(json.dumps({'TEST-1': rec}))
    assert review(path)[0]['status'] == 'held'
    failed = subprocess.run([sys.executable, str(PERSONALIZE / 'daily_apply.py'), str(path), '--write-sheet'], capture_output=True, text=True)
    assert failed.returncode != 0 and 'Refusing Sheets' in failed.stderr


def test_manual_fix_does_not_approve_and_keeps_evidence(batch):
    path, lead, rec = batch
    (path / 'x_0.json').write_text(json.dumps([dict(rec, lead_id='TEST-1')]))
    subprocess.run([sys.executable, str(PERSONALIZE / 'daily_fill.py'), str(path), '--merge'], check=True, capture_output=True)
    fixes = path / 'fixes.json'
    fixes.write_text(json.dumps({'fix': {'TEST-1': {'specific': 'serving more than 500 clients'}}, 'skip': {}}))
    subprocess.run([sys.executable, str(PERSONALIZE / 'tools/applyfix.py'), str(path), str(fixes)], check=True, capture_output=True)
    subprocess.run([sys.executable, str(PERSONALIZE / 'tools/review.py'), str(path)], check=True, capture_output=True)
    row = review(path)[0]
    assert row['record']['specific_evidence'] == rec['specific_evidence']
    assert row['status'] == 'needs_review'
    assert not (path / 'human_review.json').exists()


def test_merge_rejects_duplicate_and_missing_lead_stays_held(batch):
    path, lead, rec = batch
    (path / 'x_0.json').write_text(json.dumps([dict(rec, lead_id='TEST-1')]))
    (path / 'x_1.json').write_text(json.dumps([dict(rec, lead_id='TEST-1')]))
    result = subprocess.run([sys.executable, str(PERSONALIZE / 'daily_fill.py'), str(path), '--merge'], capture_output=True, text=True)
    assert result.returncode != 0
    (path / 'x_1.json').unlink(); (path / 'x_0.json').write_text('[]')
    subprocess.run([sys.executable, str(PERSONALIZE / 'daily_fill.py'), str(path), '--merge'], check=True, capture_output=True)
    assert review(path)[0]['status'] == 'held'


def test_invalid_field_types_and_foreign_country(batch):
    path, lead, rec = batch
    line = render('Brian', rec)
    invalid = dict(rec, x=None)
    assert 'type' in validate(path, lead, invalid, line)
    assert 'foreign' in validate(path, dict(lead, company_country='Canada'), rec, line)


def test_extract_stage_refuses_missing_ids(batch):
    path, lead, rec = batch
    (path / '_chunks.json').write_text('[["TEST-1", "TEST-2"]]')
    (path / 'extract_0.json').write_text('[{"lead_id":"TEST-1"}]')
    result = subprocess.run([sys.executable, str(PERSONALIZE / 'tools/stage.py'), 'merge', str(path)], capture_output=True, text=True)
    assert result.returncode != 0 and 'Missing extraction' in result.stderr


def test_legacy_live_entrypoint_is_now_offline_review(batch):
    path, lead, rec = batch
    (path / 'x_0.json').write_text(json.dumps([dict(rec, lead_id='TEST-1')]))
    subprocess.run([sys.executable, str(PERSONALIZE / 'daily_fill.py'), str(path), '--merge'], check=True, capture_output=True)
    result = subprocess.run([sys.executable, str(PERSONALIZE / 'live_personalize.py'), str(path)], capture_output=True, text=True)
    assert result.returncode == 0
    assert '[review]' in result.stdout
    assert review(path)[0]['status'] == 'needs_review'
