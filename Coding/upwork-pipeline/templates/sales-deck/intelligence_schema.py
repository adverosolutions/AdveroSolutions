"""Bounded editorial intelligence briefing; fictional evidence, local decisions only."""
def validate_intelligence(scene, path):
    from schema import obj, text, fail
    import re
    def record(value, where, keys):
        obj(value, where, keys)
    def string(value, where, maximum=280):
        text(value, where)
        if len(value) > maximum:
            fail(where, 'exceeds intelligence display bound of %s characters' % maximum)
        if '://' in value:
            fail(where, 'fictional evidence uses source labels, never URL-shaped claims')
    def identifier(value, where):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}', value):
            fail(where, 'expected safe bounded identifier')
    def records(value, where, minimum, maximum):
        if not isinstance(value, list) or not minimum <= len(value) <= maximum:
            fail(where, 'expected %s–%s items' % (minimum, maximum))
    if scene['platform'] != 'workbench':
        fail(path, 'intelligence requires workbench')
    c = scene['content']; p = path + '.content'
    record(c,p,('surface','name','reportId','edition','schedule','objective','summary','topics','stories','health','history'))
    for k in ('surface','name','reportId','edition','schedule','objective','summary'):
        string(c[k],p+'.'+k,180 if k in ('objective','summary') else 70)
    if c['surface'] not in ('workflow','briefing'):
        fail(p+'.surface','expected workflow or briefing')
    records(c['topics'],p+'.topics',3,3)
    topics = []
    for i,t in enumerate(c['topics']):
        q = p+'.topics[%s]' % i
        record(t,q,('id','label','priority'))
        for k in ('id','label','priority'): string(t[k],q+'.'+k,40)
        if t['priority'] not in ('high','medium','low'): fail(q,'invalid topic priority')
        identifier(t['id'],q+'.id')
        topics.append(t['id'])
    if len(set(topics)) != len(topics): fail(p+'.topics','duplicate topic IDs')
    records(c['stories'],p+'.stories',3,3)
    ids = []; evidence_ids = []
    for i,s in enumerate(c['stories']):
        q = p+'.stories[%s]' % i
        record(s,q,('id','title','category','topicId','priority','summary','why','action','urgency','confidence','uncertainty','evidence'))
        for k in ('id','title','category','topicId','priority','summary','why','action','urgency','confidence','uncertainty'):
            string(s[k],q+'.'+k,110 if k == 'title' else 220)
        if s['category'] != ('risk','opportunity','watch')[i]: fail(q,'stories must be ranked risk, opportunity, watch')
        if s['topicId'] not in topics: fail(q,'unknown topic ID')
        records(s['evidence'],q+'.evidence',1,2)
        for j,e in enumerate(s['evidence']):
            ep = q+'.evidence[%s]' % j
            record(e,ep,('id','title','kind','excerpt'))
            for k in ('id','title','kind','excerpt'): string(e[k],ep+'.'+k,220)
            if e['kind'] not in ('primary','repost','unverified'): fail(ep,'invalid evidence kind')
            evidence_ids.append(e['id'])
        identifier(s['id'],q+'.id')
        ids.append(s['id'])
    if len(set(ids)) != 3: fail(p+'.stories','duplicate story IDs')
    if len(set(evidence_ids)) != len(evidence_ids): fail(p+'.stories','duplicate evidence IDs')
    h = c['health']; record(h,p+'.health',('fetched','developments','failedSource','failure','retry'))
    for k in ('fetched','developments'):
        if type(h[k]) is not int or not 1 <= h[k] <= 99: fail(p+'.health.'+k,'expected bounded positive integer')
    if h['developments'] != len(c['stories']) or h['fetched'] != len(evidence_ids):
        fail(p+'.health','counts must agree with story and evidence counts')
    for k in ('failedSource','failure','retry'): string(h[k],p+'.health.'+k,110)
    records(c['history'],p+'.history',2,3)
    for i,h in enumerate(c['history']):
        q = p+'.history[%s]' % i; record(h,q,('id','time','status'))
        for k in ('id','time','status'): string(h[k],q+'.'+k,65)
    if len(scene['statuses']) != 3: fail(path+'.statuses','intelligence requires three replay states')
