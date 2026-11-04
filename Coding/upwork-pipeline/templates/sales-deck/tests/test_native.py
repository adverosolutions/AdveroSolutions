"""Native surfaces must keep product identity, useful proof, and bounded data."""
import copy,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from schema import validate,ValidationError,public_job
CAT=json.loads((ROOT/'platforms.json').read_text())
def spec(name):return json.loads((ROOT/'native-templates'/(name+'.json')).read_text())
@pytest.mark.parametrize('name',['ghl','n8n','zapier','claude'])
def test_native_fixture_accepts_and_hides_private_source(name):
 value=validate(spec(name),CAT)
 assert 'source' not in public_job(value)
 assert all(x['kind']=='native' for x in value['scenes'])
 assert value['scenes'][0]['platform']==name
@pytest.mark.parametrize('name,surface',[('claude','builder'),('ghl','skills'),('n8n','chat'),('zapier','execution')])
def test_wrong_product_surface_rejected(name,surface):
 value=spec(name);value['scenes'][0]['content']['surface']=surface
 with pytest.raises(ValidationError,match='unsupported native surface'):validate(value,CAT)
def test_claude_needs_real_result_scene():
 value=spec('claude');value['scenes']=[value['scenes'][0],spec('claude')['scenes'][1]];value['scenes'][1]['optional']=True
 with pytest.raises(ValidationError,match='result/proof'):validate(value,CAT)
def test_inspector_must_match_all_nodes():
 value=spec('n8n');value['scenes'][0]['content']['inspectors'][0]['node']='missing-node'
 with pytest.raises(ValidationError,match='unknown node'):validate(value,CAT)
def test_ai_node_without_required_subnodes_stays_blocked():
 value=spec('n8n');value['scenes'][0]['content']['graph']['nodes'][1]['type']='ai_agent'
 with pytest.raises(ValidationError,match='requires one chat model and at least one tool'):validate(value,CAT)
def test_zero_value_contact_and_invalid_stage_rejected():
 for key,data in [('value','$0.00'),('stageSequence',[0,1,999])]:
  value=spec('ghl');value['scenes'][2]['content'][key]=data
  with pytest.raises(ValidationError):validate(value,CAT)
def test_markup_and_extra_fields_are_not_native_content():
 value=spec('claude');value['scenes'][0]['content']['skills'][0]['instructions']='<script>alert(1)</script>'
 with pytest.raises(ValidationError,match='markup'):validate(value,CAT)
 value=spec('claude');value['scenes'][0]['content']['fakeApprovalButton']='Approve client'
 with pytest.raises(ValidationError,match='unknown fields'):validate(value,CAT)
def test_execution_requires_run_metadata():
 value=spec('n8n');value['scenes'][1]['content']['surface']='execution'
 with pytest.raises(ValidationError,match='metadata required'):validate(value,CAT)

def test_handoff_request_and_output_share_contact_and_value():
    value=validate(spec('n8n'),CAT)
    c=value['scenes'][1]['content']; last=c['inspectors'][-1]
    request=json.loads(next(r['value'] for r in last['parameters'] if r['label']=='JSON'))
    output={r['label']:r['value'] for r in last['output']}
    assert request['contactId']==output['contactId']=='sample-avery-1042'
    assert request['monetaryValue']==int(output['monetaryValue'])==8450
    for step in c['inspectors']:
        assert not {'Operation','Account'}.intersection(r['label'] for r in step['parameters'])

def test_zapier_value_mapping_and_readable_acknowledgement():
    value=validate(spec('zapier'),CAT)
    steps=value['scenes'][0]['content']['inspectors']
    row={r['label']:r['value'] for r in steps[1]['input']}
    assert row['estimate_value']=='8450'
    email={r['label']:r['value'] for r in steps[2]['input']}
    assert email['To']=='avery.morgan@example.com'
    assert 'Maya' in email['Body'] and 'estimate request' in email['Body']
    assert value['scenes'][2]['content']['selectedNode']=='email'

def test_request_body_cannot_crash_native_inspector():
    value=spec('n8n')
    body=next(r for r in value['scenes'][0]['content']['inspectors'][3]['parameters'] if r['label']=='JSON')
    body['value']='{broken'
    with pytest.raises(ValidationError,match='valid object'):validate(value,CAT)

def test_zapier_cannot_fall_into_legacy_workflow_renderer():
    value=spec('zapier')
    value['scenes'][0]['kind']='workflow'
    value['scenes'][0]['content']=value['scenes'][0]['content']['graph']
    with pytest.raises(ValidationError,match='requires_adapter'):validate(value,CAT)


def test_sales_routes_have_distinct_stops_and_concrete_measures():
    for name in ('ghl','n8n','zapier','claude'):
        value=spec(name)
        for detailed in (False,True):
            scenes=[s for s in value['scenes'] if detailed or not s['optional']]
            assert 2 <= len(scenes) <= 3
            signatures=[(s['content']['surface'],s['content'].get('selectedNode')) for s in scenes]
            assert len(signatures)==len(set(signatures)), name
            assert len({s['title'] for s in scenes})==len(scenes)
        assert all(m['name'] not in ('Manual handling','Complete records','Time to useful output') for m in value['close']['metrics'])
    assert [s['content']['surface'] for s in spec('n8n')['scenes']]==['editor','node']
    assert [s['content']['surface'] for s in spec('claude')['scenes']]==['skills','chat']

def test_ghl_result_does_not_invent_confirmation():
    value=spec('ghl')
    items=value['scenes'][1]['content']['items']
    assert all(m['direction']=='outgoing' for m in items)
    assert len(items)==2
    assert value['scenes'][2]['content']['stageSequence'][-1]==1
    assert value['scenes'][2]['content']['stages'][1]=='Contacted'
    assert value['scenes'][2]['content']['stageSequence']==[1]
    assert value['scenes'][0]['content']['graph']['nodes'][2]['label']=='Create opportunity in Contacted'
    assert [n['type'] for n in value['scenes'][0]['content']['graph']['nodes']][-2:]==['sms','email']


def test_relabelled_duplicate_proof_is_rejected():
    value=spec('n8n')
    duplicate=copy.deepcopy(value['scenes'][1])
    duplicate.update(id='repeated-result',title='A different headline')
    duplicate['content'].update(surface='execution',execution=dict(id='1042',started='Today',duration='1s'))
    value['scenes'].append(duplicate)
    with pytest.raises(ValidationError,match='duplicate native proof screen'):
        validate(value,CAT)
