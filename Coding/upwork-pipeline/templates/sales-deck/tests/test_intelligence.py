"""Typed editorial briefing and workflow-result contract regressions."""
import copy
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build import read_json
from schema import validate,ValidationError
CAT=read_json(ROOT/'platforms.json')
def fixture():return read_json(ROOT/'tests/fixtures/intelligence-editorial.json')
def test_both_surfaces_validate():
    j=validate(fixture(),CAT)
    assert [s['content']['surface'] for s in j['scenes']]==['workflow','briefing']
@pytest.mark.parametrize('change',['surface','unsafe-id','duplicate-story','count','boolean-count','evidence-url','result-omitted'])
def test_invalid_editorial_data_is_rejected(change):
    j=fixture();c=j['scenes'][1]['content']
    if change=='surface':c['surface']='crm'
    if change=='unsafe-id':c['stories'][0]['id']='bad"]'
    if change=='duplicate-story':c['stories'][1]['id']=c['stories'][0]['id']
    if change=='count':c['health']['fetched']=9
    if change=='boolean-count':c['health']['fetched']=True
    if change=='evidence-url':c['stories'][0]['evidence'][0]['excerpt']='https://example.invalid/not-real'
    if change=='result-omitted':c['surface']='workflow'
    with pytest.raises(ValidationError):validate(j,CAT)
