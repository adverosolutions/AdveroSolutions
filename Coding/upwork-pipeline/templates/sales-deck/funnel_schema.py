"""Bounded public GHL funnel surfaces, not an admin builder or live embed."""

def validate_funnel(scene, path):
    from datetime import date
    import re
    from schema import obj, text, texts, fail
    if scene['platform'] != 'ghl':
        fail(path, 'public funnel requires ghl')
    c = scene['content']
    p = path + '.content'
    obj(c, p, ('surface', 'name', 'subtitle', 'brand', 'heading', 'body', 'cta', 'booking'), ('choices',))
    if c['surface'] not in ('landing', 'booking', 'confirmation'):
        fail(p + '.surface', 'unsupported public funnel surface')
    for key in ('name', 'subtitle', 'brand', 'heading', 'body', 'cta'):
        text(c[key], p + '.' + key)
    def choice(b, q, full=False):
        required = ('service', 'durationMinutes', 'location', 'staff', 'staffOptions', 'slots')
        obj(b, q, required + (('dateISO', 'timezone', 'timezoneLabel', 'selectedSlot', 'smsConsent', 'contact') if full else ('id',)))
        for key in ('service', 'location', 'staff'):
            text(b[key], q + '.' + key)
        if type(b['durationMinutes']) is not int or not 5 <= b['durationMinutes'] <= 480:
            fail(q + '.durationMinutes', 'expected duration between 5 and 480 minutes')
        staff = texts(b['staffOptions'], q + '.staffOptions', 1, 8)
        if b['staff'] not in staff:
            fail(q + '.staff', 'must be an eligible staff member')
        slots = texts(b['slots'], q + '.slots', 1, 12)
        if len(set(slots)) != len(slots) or any(not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', s) for s in slots):
            fail(q + '.slots', 'expected unique HH:MM slots')
        if full:
            if type(b['smsConsent']) is not bool:
                fail(q + '.smsConsent', 'expected explicit sample SMS consent boolean')
            for key in ('dateISO', 'timezone', 'timezoneLabel', 'selectedSlot'):
                text(b[key], q + '.' + key)
            try:
                date.fromisoformat(b['dateISO'])
            except ValueError:
                fail(q + '.dateISO', 'expected ISO calendar date')
            if b['selectedSlot'] not in slots:
                fail(q + '.selectedSlot', 'must refer to an available slot')
            obj(b['contact'], q + '.contact', ('name', 'email', 'phone'))
            for key in ('name', 'email', 'phone'):
                text(b['contact'][key], q + '.contact.' + key)
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', b['contact']['email']):
                fail(q + '.contact.email', 'expected sample email address')
        else:
            text(b['id'], q + '.id')
    choice(c['booking'], p + '.booking', True)
    if 'choices' in c:
        if not isinstance(c['choices'], list) or not 1 <= len(c['choices']) <= 8:
            fail(p + '.choices', 'expected 1..8 calendar choices')
        ids = []
        for i, item in enumerate(c['choices']):
            choice(item, p + '.choices[' + str(i) + ']')
            ids.append(item['id'])
        if len(set(ids)) != len(ids):
            fail(p + '.choices', 'duplicate calendar choice ids')
        matches = [x for x in c['choices'] if all(x[k] == c['booking'][k] for k in ('service', 'durationMinutes', 'location', 'staff', 'slots'))]
        if not matches:
            fail(p + '.choices', 'initial booking must match a calendar choice')
    if len(scene['statuses']) != 2:
        fail(path + '.statuses', 'funnel requires initial and settled statuses')
