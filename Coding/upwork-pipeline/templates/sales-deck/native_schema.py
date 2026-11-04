"""Strict native-screen extension. Vendor surfaces are explicit, never inferred."""
import json
from schema import obj, text, texts, rows, fail, slug

SURFACES = {
    'ghl': ('builder', 'pipeline', 'conversations'),
    'n8n': ('editor', 'node', 'execution'),
    'zapier': ('editor', 'test'),
    'claude': ('skills', 'project', 'chat'),
}
NATIVE_ACTIONS = {'n8n': {'webhook','edit_fields','http_request','ai_agent','openai_chat_model','http_request_tool'}, 'zapier': {'webhook','sheets','email'}, 'ghl': {'facebook_lead','contact_tag','assign_user','opportunity','sms','email','notification','wait','event_date','appointment_status'}}
MECHANISMS = {'builder', 'editor', 'skills', 'project'}
RESULTS = {'node', 'pipeline', 'conversations', 'execution', 'test', 'chat'}


def validate_native(scene, platform, path, validate_content):
    c = scene['content']; p = path + '.content'
    if not isinstance(c,dict):fail(p,'expected object')
    if scene['platform'] not in SURFACES or c.get('surface') not in SURFACES[scene['platform']]:
        fail(p, 'requires_adapter: unsupported native surface')
    surface = c['surface']; base = ('name', 'subtitle', 'surface')
    if surface in ('builder', 'editor', 'node', 'execution', 'test'):
        obj(c, p, base + ('graph', 'inspectors', 'selectedNode'), (('execution',) if surface == 'execution' else ()) + ('aiNodes','aiConnections'))
        if surface == 'execution':
            if 'execution' not in c:fail(p+'.execution','execution metadata required')
            rows([c['execution']],p+'.execution',('id','started','duration'))
        graph = c['graph']
        fake = dict(scene, kind='workflow', content=graph)
        validate_content(fake, platform, path)
        for node in graph['nodes']:
            if node['type'] not in NATIVE_ACTIONS.get(scene['platform'],set()):
                fail(p+'.graph.nodes','requires_adapter: unsupported action in native surface '+node['type'])
        ai_nodes = c.get('aiNodes', [])
        ai_edges = c.get('aiConnections', [])
        if ai_nodes or ai_edges:
            if scene['platform'] != 'n8n': fail(p, 'AI subnodes are n8n-only')
            rows(ai_nodes,p+'.aiNodes',('id','type','label','detail'),minimum=2,maximum=6)
            rows(ai_edges,p+'.aiConnections',('from','to','type'),minimum=2,maximum=6)
        main_ids = {n['id'] for n in graph['nodes']}
        sub_ids = {n['id'] for n in ai_nodes}
        if len(sub_ids) != len(ai_nodes) or main_ids & sub_ids: fail(p+'.aiNodes','duplicate node ids')
        agents = {n['id'] for n in graph['nodes'] if n['type']=='ai_agent'}
        if any(n['type'] in ('openai_chat_model','http_request_tool') for n in graph['nodes']):
            fail(p+'.graph.nodes','AI subnodes must not appear in the main graph')
        for n in ai_nodes:
            slug(n['id'],p+'.aiNodes.id')
            if n['type'] not in ('openai_chat_model','http_request_tool'):fail(p+'.aiNodes','unsupported AI subnode')
        attached = set()
        for edge in ai_edges:
            if edge['from'] not in sub_ids or edge['to'] not in agents:fail(p+'.aiConnections','connect subnodes only to an AI Agent')
            node=next(n for n in ai_nodes if n['id']==edge['from'])
            expected='ai_languageModel' if node['type']=='openai_chat_model' else 'ai_tool'
            if edge['type'] != expected or edge['from'] in attached:fail(p+'.aiConnections','wrong typed port or duplicate subnode connection')
            attached.add(edge['from'])
        if attached != sub_ids:fail(p+'.aiConnections','all subnodes must attach to an agent')
        for agent in agents:
            attached_types=[e['type'] for e in ai_edges if e['to']==agent]
            if attached_types.count('ai_languageModel')!=1 or 'ai_tool' not in attached_types:
                fail(p+'.aiConnections','each AI Agent requires one chat model and at least one tool')
        all_nodes = graph['nodes'] + ai_nodes
        ids = [n['id'] for n in all_nodes]
        if c['selectedNode'] not in ids: fail(p + '.selectedNode', 'unknown node')
        if not isinstance(c['inspectors'], list) or len(c['inspectors']) != len(ids):
            fail(p + '.inspectors', 'one inspector per node is required')
        seen = set()
        for inspector in c['inspectors']:
            obj(inspector, p+'.inspectors', ('node', 'input', 'output', 'parameters'))
            if inspector['node'] not in ids or inspector['node'] in seen: fail(p+'.inspectors', 'duplicate or unknown node')
            seen.add(inspector['node'])
            for key in ('input','output','parameters'):
                rows(inspector[key],p+'.inspectors.'+key,('label','value'),minimum=1,maximum=12)
                labels=[r['label'] for r in inspector[key]]
                if len(set(labels))!=len(labels):fail(p+'.inspectors.'+key,'duplicate data keys')
            node=next(n for n in all_nodes if n['id']==inspector['node'])
            params={r['label']:r['value'] for r in inspector['parameters']}
            if scene['platform']=='n8n' and node['type'] in ('http_request','http_request_tool'):
                if not {'Method','URL','Authentication'}.issubset(params):fail(p+'.inspectors.parameters','HTTP Request needs Method, URL and Authentication')
                if params['Method'] not in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'):fail(p+'.inspectors.parameters','invalid HTTP method')
                if params['Method'] in ('POST','PUT','PATCH') and 'JSON' not in params:fail(p+'.inspectors.parameters','write request requires JSON sample body')
                if 'JSON' in params:
                    try:
                        body=json.loads(params['JSON'],parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                        if not isinstance(body,dict):raise ValueError('object required')
                    except (ValueError,TypeError):fail(p+'.inspectors.parameters','JSON request body must be a valid object')
            if scene['platform']=='n8n' and node['type']=='ai_agent' and not {'Prompt (User Message)','System Message'}.issubset(params):
                fail(p+'.inspectors.parameters','AI Agent needs prompt and system message')
            if scene['platform']=='n8n' and node['type']=='openai_chat_model' and 'Model' not in params:
                fail(p+'.inspectors.parameters','OpenAI Chat Model needs Model')
            if scene['platform']=='n8n' and node['type']=='webhook'  and not {'HTTP Method','Path','Authentication','Respond'}.issubset(params):
                fail(p+'.inspectors.parameters','Webhook settings incomplete')
            if scene['platform']=='zapier' and node['type']=='email':
                if not {'To','Subject','Body'}.issubset(r['label'] for r in inspector['input']):fail(p+'.inspectors.input','email acknowledgement requires To, Subject and Body')

    elif surface == 'pipeline':
        obj(c,p,base+('contact','fields','stages','stageSequence','value','owner'))
        for key in ('contact','value','owner'):text(c[key],p+'.'+key)
        rows(c['fields'],p+'.fields',('label','value'),minimum=1,maximum=8)
        stages=texts(c['stages'],p+'.stages',2,6); seq=c['stageSequence']
        if not isinstance(seq,list) or len(seq)!=len(scene['statuses']) or any(type(x) is not int or not 0<=x<len(stages) for x in seq):fail(p+'.stageSequence','one valid stage index per status required')
        if not c['value'].strip() or c['value'].strip() in ('0','0.00','$0','$0.00'):fail(p+'.value','supply the meaningful sample opportunity value')
    elif surface == 'conversations':
        obj(c,p,base+('contact','fields','items'))
        text(c['contact'],p+'.contact');rows(c['fields'],p+'.fields',('label','value'),minimum=1,maximum=8)
        items=rows(c['items'],p+'.items',('channel','direction','sender','time','body'),('subject',),minimum=2,maximum=8)
        for item in items:
            if item['channel'] not in ('sms','email') or item['direction'] not in ('incoming','outgoing'):fail(p+'.items','invalid channel/direction')
        if len(items)!=len(scene['statuses']):fail(path+'.statuses','one status per message required')
    elif surface == 'skills':
        obj(c,p,base+('skills',))
        rows(c['skills'],p+'.skills',('name','description','instructions'),minimum=1,maximum=5)
        if len(scene['statuses'])!=2:fail(path+'.statuses','skills requires two replay states')
    elif surface == 'project':
        obj(c,p,base+('instructions','files'))
        text(c['instructions'],p+'.instructions')
        rows(c['files'],p+'.files',('name','detail'),minimum=1,maximum=5)
        if len(scene['statuses'])!=2:fail(path+'.statuses','project requires two replay states')
    elif surface == 'chat':
        obj(c,p,base+('prompt','response','files','document','exception'))
        for key in ('prompt','response','exception'):text(c[key],p+'.'+key)
        rows(c['files'],p+'.files',('name','detail'),minimum=1,maximum=4)
        obj(c['document'],p+'.document',('title','sections'))
        text(c['document']['title'],p+'.document.title')
        rows(c['document']['sections'],p+'.document.sections',('title','body'),minimum=2,maximum=6)
        if len(scene['statuses'])!=3:fail(path+'.statuses','chat requires input, output and exception states')
    for key in base:text(c[key],p+'.'+key)
