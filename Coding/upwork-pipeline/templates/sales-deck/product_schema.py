"""Bounded custom reconciliation product, never a vendor surface."""
def validate_product(scene, path):
    from schema import obj, text, rows, fail
    if scene['platform'] != 'workbench':
        fail(path, 'product requires workbench')
    c = scene['content']; p = path + '.content'
    obj(c, p, ('name','subtitle','reviewer','transaction','evidence','analysis','decision'))
    for k in ('name','subtitle'):
        text(c[k], p+'.'+k)
    for key, keys in [('reviewer',('name','role','tenant')), ('analysis',('summary','recommendation','confidence','dataBoundary')), ('decision',('classification','reason','auditId'))]:
        obj(c[key], p+'.'+key, keys)
        for k in keys:
            text(c[key][k], p+'.'+key+'.'+k)
    if c['reviewer']['role'] != 'Reviewer':
        fail(p+'.reviewer.role','bounded sample requires Reviewer role')
    if c['decision']['classification'] != 'Needs provider evidence':
        fail(p+'.decision.classification','bounded sample only approves Needs provider evidence')
    t = c['transaction']
    obj(t,p+'.transaction',('id','event','invoice','currency','grossMinor','expectedMinor','providerStatus','description'))
    for k in ('id','event','invoice','currency','providerStatus','description'):
        text(t[k],p+'.transaction.'+k)
    if t['currency'] != 'USD':
        fail(p+'.transaction.currency','only USD sample amounts are supported')
    for k in ('grossMinor','expectedMinor'):
        if type(t[k]) is not int or not 0 <= t[k] <= 999999999:
            fail(p+'.transaction.'+k,'expected nonnegative bounded integer minor units')
    if t['grossMinor'] == t['expectedMinor']:
        fail(p+'.transaction','exception requires different amounts')
    if t['providerStatus'] != 'Settled':
        fail(p+'.transaction.providerStatus','bounded sample requires Settled provider state')
    rows(c['evidence'],p+'.evidence',('id','title','detail'),minimum=2,maximum=4)
    if len(set(x['id'] for x in c['evidence'])) != len(c['evidence']):
        fail(p+'.evidence','duplicate evidence IDs')
    if len(scene['statuses']) != 3:
        fail(path+'.statuses','product requires exception, suggestion and approval states')
