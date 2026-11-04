"""Regression coverage for typed native and bespoke sales-demo surfaces."""
import copy
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build import read_json, page
from schema import validate, ValidationError, public_job
CAT=read_json(ROOT/'platforms.json')
def fixture(key):
    return read_json(ROOT/'tests/fixtures'/str(key+'.json'))
def scene(value,kind):
    return next(x for x in value['scenes'] if x['kind']==kind)
@pytest.mark.parametrize('key',['ai-agent','gmail-draft','booking-funnel','fintech-app','intelligence'])
def test_fixture_is_valid_and_private_sources_are_not_public(key):
    value=validate(fixture(key),CAT)
    public=public_job(value)
    assert 'source' not in public
    text=page(public,CAT)
    assert 'Synthetic regression fixture' not in text
    assert 'window.MotionConfig=' in text
    assert 'Northstar' not in text and 'Avery Morgan' not in text
@pytest.mark.parametrize('change',['missing-model','wrong-port','wrong-target','duplicate-subnode'])
def test_ai_connection_integrity(change):
    value=fixture('ai-agent');c=value['scenes'][0]['content']
    if change=='missing-model':c['aiConnections']=[e for e in c['aiConnections'] if e['type']!='ai_languageModel']
    if change=='wrong-port':c['aiConnections'][0]['type']='ai_tool'
    if change=='wrong-target':c['aiConnections'][0]['to']=c['graph']['nodes'][0]['id']
    if change=='duplicate-subnode':c['aiNodes'].append(copy.deepcopy(c['aiNodes'][0]))
    with pytest.raises(ValidationError):validate(value,CAT)
@pytest.mark.parametrize('field,value',[('recipient','someone-else@example.com'),('status','sent')])
def test_gmail_cannot_relabel_sending_or_reply_to_other_contact(field,value):
    spec=fixture('gmail-draft');scene(spec,'gmail')['content']['draft'][field]=value
    with pytest.raises(ValidationError):validate(spec,CAT)
@pytest.mark.parametrize('field,value',[('grossMinor',True),('expectedMinor',120.5),('grossMinor',-1),('providerStatus','Paid by AI')])
def test_financial_sample_integrity(field,value):
    spec=fixture('fintech-app');scene(spec,'product')['content']['transaction'][field]=value
    with pytest.raises(ValidationError):validate(spec,CAT)
def test_reject_custom_architecture_cycle():
    spec=fixture('intelligence');c=scene(spec,'architecture')['content'];c['edges'].append({'from':c['runOrder'][-1],'to':c['runOrder'][0]})
    with pytest.raises(ValidationError,match='acyclic'):validate(spec,CAT)
@pytest.mark.parametrize('field,value',[('dateISO','2026-02-30'),('selectedSlot','25:30'),('staff','Not in this calendar'),('smsConsent','yes')])
def test_booking_cannot_contradict_calendar(field,value):
    spec=fixture('booking-funnel');scene(spec,'funnel')['content']['booking'][field]=value
    with pytest.raises(ValidationError):validate(spec,CAT)
def test_confirmation_required_on_short_routes():
    spec=fixture('booking-funnel')
    spec['scenes']=[s for s in spec['scenes'] if s['kind'] in ('native','funnel')]
    for s in spec['scenes']:
        if s['kind']=='funnel' and s['content']['surface']=='confirmation':s['optional']=True
    with pytest.raises(ValidationError,match='visible result'):validate(spec,CAT)
