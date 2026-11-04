"""Bounded Gmail desktop thread/reply-draft simulation, no sending capability."""
def validate_gmail(scene, path):
    from schema import obj, text, fail
    c = scene['content']; p = path + '.content'
    if scene['platform'] != 'gmail': fail(path, 'Gmail scene requires gmail platform')
    obj(c, p, ('name','subtitle','surface','thread','draft'))
    for key in ('name','subtitle','surface'): text(c[key],p+'.'+key)
    if c['surface'] != 'thread': fail(p+'.surface','requires_adapter: only Gmail desktop thread is supported')
    obj(c['thread'],p+'.thread',('id','subject','fromName','fromEmail','toEmail','received','body','label'))
    for key,value in c['thread'].items(): text(value,p+'.thread.'+key)
    obj(c['draft'],p+'.draft',('id','recipient','body','status'))
    for key,value in c['draft'].items(): text(value,p+'.draft.'+key)
    if c['draft']['recipient'] != c['thread']['fromEmail']: fail(p+'.draft.recipient','reply recipient must match original sender')
    if c['draft']['status'] != 'draft': fail(p+'.draft.status','only unsent draft state is supported')
    if len(scene['statuses']) != 2: fail(path+'.statuses','Gmail requires original thread and unsent draft states')
