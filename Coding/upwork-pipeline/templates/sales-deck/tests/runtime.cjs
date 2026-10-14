'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const root = path.resolve(__dirname, '..');
const shell = fs.readFileSync(path.join(root, 'runtime/shell.html'), 'utf8');
const runtime = fs.readFileSync(path.join(root, 'runtime/app.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));

function fixture() {
  const name = 'Taylor Fresh';
  const event = title => ({ title, detail: `${name} · complete context` });
  const scene = (kind, content, optional = false) => ({
    id: `${kind}-chapter`, kind, platform: 'ghl', title: `${name}: ${kind}`,
    caption: `New job ${kind} caption`, beat: `Explain ${kind} for ${name}`,
    details: [`Point out ${name}`], optional, content,
    statuses: [`${name}: starting`, `${name}: working`, `${name}: settled`]
  });
  return {
    schemaVersion: 1, id: 'new-client', title: 'New job', systemName: 'Fresh system',
    account: { name: 'Fresh Account', initials: 'TF', operatorInitials: 'OP' },
    personalization: { firstName: 'New Client' }, entities: {},
    cover: { eyebrow: 'New opening', title: 'Fresh title', accent: 'Fresh accent',
      caption: "I've already put this workflow together for you. Let me walk you through how it works.",
      anchors: ['Fresh anchor'], previewSteps: [{ title: 'Fresh first step', detail: 'Fresh detail' }], footer: 'Fresh footer', beat: 'Fresh cover beat' },
    scenes: [
      scene('workflow', { name: 'Fresh workflow', nodes: ['first', 'second', 'third', 'skipped'].map(id => ({ id, type: 'email', label: id, detail: name })),
        edges: [], runOrder: ['first', 'second', 'third'], context: { name, subtitle: 'Fresh context', fields: [], states: ['Starting', 'Working', 'Complete'] }, related: [] }),
      scene('record', { name, subtitle: 'Fresh record', sourceTitle: 'Fresh source', sourceFields: [{ label: 'Source', value: 'New campaign' }],
        fields: [{ label: 'Owner', value: 'Fresh Operator' }], events: [event('New capture'), event('New assignment'), event('New response')], notice: 'Fresh notice' }, true),
      scene('messages', { name, subtitle: 'Fresh conversation', fields: [{ label: 'Owner', value: 'Fresh Operator' }],
        items: ['sms', 'email', 'internal'].map((channel, index) => ({ channel, direction: index === 1 ? 'incoming' : 'outgoing', sender: name, time: `10:0${index}`, subject: index === 1 ? 'Fresh subject' : undefined, body: `${name} message ${index}` })), notice: 'Fresh message notice' }),
      scene('outcome', { name, subtitle: 'Fresh outcome', fields: [], stages: ['Fresh enquiry', 'Fresh appointment', 'Fresh customer'], stageSequence: [0, 1, 2],
        metrics: [0, 1, 2].map(index => ({ label: `Fresh metric ${index}`, value: String(index + 2), note: 'Illustrative' })), note: 'Fresh result note',
        proof: { label: 'Fresh past project', value: 'Fresh result', description: 'Fresh proof detail', sourceNote: 'Fresh proof qualification' } }),
      scene('workshop', { name, subtitle: 'Fresh attendance', current: { id: 'W1', title: 'Fresh current event', date: 'Fresh date one', time: 'Fresh time' },
        next: { id: 'W2', title: 'Fresh next event', date: 'Fresh date two', time: 'Fresh time two' }, events: [event('Fresh attended'), event('Fresh follow-up sent')],
        followup: { subject: 'Fresh follow-up', body: 'Fresh resources' }, reusable: ['Fresh form', 'Fresh timing'], historyNote: 'Fresh W1 history retained' })
    ],
    close: { eyebrow: 'Fresh close', title: 'Fresh measures', accent: 'Fresh result', caption: 'Fresh close caption',
      metrics: ['up', 'down', 'up'].map((direction, index) => ({ name: `Fresh measure ${index}`, direction, aim: 'Fresh aim', definition: 'Fresh definition' })),
      baselineNote: 'Fresh baseline', ctaTitle: 'Fresh call title', ctaCopy: 'Fresh call next step', beat: 'Fresh close beat' }
  };
}

function mount(data = fixture(), reduced = false, realAdapters = false) {
  const dom = new JSDOM(shell.replace(/<script>[\s\S]*<\/script>/, ''), { runScripts: 'outside-only', url: 'https://example.test/deck' });
  const { window } = dom;
  let timerId = 0;
  const pending = new Map();
  const scheduled = [];
  const scrollCalls = [];
  window.scrollTo = options => scrollCalls.push(options);
  const media = { matches: reduced, addEventListener: (_, callback) => { media.change = callback; } };
  window.matchMedia = () => media;
  window.setTimeout = (callback, delay) => { const id = ++timerId; pending.set(id, { callback, delay }); scheduled.push(callback); return id; };
  window.clearTimeout = id => pending.delete(id);
  window.DATA = clone(data);
  if (realAdapters) {
    window.PLATFORM_CATALOG = JSON.parse(fs.readFileSync(path.join(root, 'platforms.json'), 'utf8'));
    window.eval(fs.readFileSync(path.join(root, 'runtime/platforms.js'), 'utf8'));
  } else {
    window.SalesPlatforms = {
      renderWorkflow(scene, job) {
        assert.ok(window.SalesUI, 'Helpers exist before workflow render');
        return `<div class="native" data-workflow-scene="${window.SalesUI.esc(scene.id)}">${window.SalesUI.avatar(job)}${scene.content.nodes.map(node => `<div data-test-node="${window.SalesUI.esc(node.id)}">${window.SalesUI.esc(node.detail)}</div>`).join('')}</div>`;
      },
      applyStep(scene, index) {
        window.document.querySelectorAll('[data-test-node]').forEach(node => node.classList.toggle('active', scene.content.runOrder.slice(0, index + 1).includes(node.dataset.testNode)));
      }
    };
  }
  window.eval(runtime);
  const query = selector => window.document.querySelector(selector);
  const click = selector => { const element = query(selector); assert.ok(element, selector); element.click(); };
  const chapter = id => {
    const index = [ 'cover', ...data.scenes.filter(scene => query('#durationSelect').value === '3' || !scene.optional).map(scene => scene.id), 'close' ].indexOf(id);
    click(`[data-chapter="${index}"]`);
  };
  const flush = () => { [...pending.values()].sort((a, b) => a.delay - b.delay).forEach(timer => timer.callback()); pending.clear(); };
  const route = value => { query('#durationSelect').value = value; query('#durationSelect').dispatchEvent(new window.Event('change')); };
  return { dom, window, query, click, chapter, flush, route, pending, scheduled, media, scrollCalls };
}

function test(name, run) {
  run();
  console.log(`PASS ${name}`);
}

test('normalized new job data populates cover, every scene, and close without stale names', () => {
  const app = mount();
  app.route('3');
  assert.match(app.query('#stage').textContent, /Fresh title/);
  assert.match(app.query('#stage').textContent, /Prepared for New Client/);
  for (const kind of ['workflow', 'record', 'messages', 'outcome', 'workshop']) {
    app.chapter(`${kind}-chapter`);
    app.flush();
    assert.match(app.query('#stage').textContent, /Taylor Fresh/);
    assert.match(app.query('#notesBody').textContent, new RegExp(`Explain ${kind}`));
    assert.doesNotMatch(app.query('#stage').textContent, /Avery|Jamie|Maya|Skool|Financial Services/);
  }
  app.chapter('close');
  assert.match(app.query('#stage').textContent, /Fresh call next step/);
  assert.match(app.query('#notesBody').textContent, /Fresh definition/);
  assert.equal(app.query('#next').disabled, true);
  app.dom.window.close();
});

test('quick and standard omit optional scenes; detailed includes them', () => {
  const app = mount();
  for (const value of ['1', '2', '3']) {
    app.route(value);
    assert.equal(app.query('#stage').dataset.scene, 'cover');
    assert.equal(app.window.document.querySelectorAll('[data-chapter]').length, value === '3' ? 7 : 6);
  }
  app.dom.window.close();
});

test('chapter and route navigation reset page scroll immediately while replay keeps its position', () => {
  const app = mount();
  assert.equal(app.scrollCalls.length, 0, 'Initial render does not change page position');
  app.chapter('workflow-chapter');
  assert.equal(app.scrollCalls.length, 1);
  assert.equal(app.scrollCalls[0].top, 0);
  assert.equal(app.scrollCalls[0].left, 0);
  assert.equal(app.scrollCalls[0].behavior, 'instant');
  app.flush();
  app.click('#replay');
  app.click('#showResult');
  assert.equal(app.scrollCalls.length, 1, 'Replay and steps preserve page position');
  app.route('3');
  assert.equal(app.scrollCalls.length, 2);
  assert.equal(app.scrollCalls[1].top, 0);
  assert.equal(app.scrollCalls[1].behavior, 'instant');
  app.dom.window.close();
});

test('workflow starts immediately, settles within five seconds, skips branch and replays', () => {
  const app = mount();
  app.chapter('workflow-chapter');
  assert.equal(app.query('.demo').dataset.replayStep, '0');
  assert.equal(app.window.document.querySelectorAll('[data-test-node].active').length, 1);
  assert.ok([...app.pending.values()].every(timer => timer.delay <= 5000));
  app.flush();
  assert.equal(app.window.document.querySelectorAll('[data-test-node].active').length, 3);
  assert.equal(app.query('[data-test-node="skipped"]').classList.contains('active'), false);
  assert.equal(app.query('#stage').dataset.scene, 'workflow-chapter', 'No auto-advance');
  app.click('#replay');
  assert.equal(app.window.document.querySelectorAll('[data-test-node].active').length, 1);
  app.click('#showResult');
  assert.equal(app.pending.size, 0);
  assert.equal(app.query('#replayStatus').textContent, 'Taylor Fresh: settled');
  app.dom.window.close();
});

test('outcome stage moves through its supplied sequence and result holds', () => {
  const app = mount();
  app.chapter('outcome-chapter');
  assert.equal(app.query('#outcomeStage').textContent, 'Fresh enquiry');
  app.flush();
  assert.equal(app.query('#outcomeStage').textContent, 'Fresh customer');
  assert.equal(app.query('[data-stage="2"]').classList.contains('current'), true);
  app.click('#replay');
  assert.equal(app.query('#outcomeStage').textContent, 'Fresh enquiry');
  app.dom.window.close();
});

test('workshop attendance, follow-up, next event and empty registrations reset on replay', () => {
  const app = mount();
  app.chapter('workshop-chapter');
  assert.equal(app.query('#eventDate').textContent, 'Fresh date one');
  assert.equal(app.query('.attendance-email').classList.contains('pending'), true);
  app.flush();
  assert.equal(app.query('#eventDate').textContent, 'Fresh date two');
  assert.equal(app.query('#registrationNote').textContent, 'W2: no registrations yet');
  assert.match(app.query('#historyNote').textContent, /W1 history retained/);
  app.click('#replay');
  assert.equal(app.query('#eventDate').textContent, 'Fresh date one');
  app.dom.window.close();
});

test('navigation and replay cancel stale callbacks even if already queued', () => {
  const app = mount();
  app.chapter('workflow-chapter');
  const stale = [...app.scheduled];
  app.chapter('messages-chapter');
  const before = app.query('#stage').innerHTML;
  stale.forEach(callback => callback());
  assert.equal(app.query('#stage').innerHTML, before);
  app.click('#replay');
  const replayGeneration = [...app.scheduled].slice(stale.length);
  const step = app.query('.demo').dataset.replayStep;
  replayGeneration.slice(0, 2).forEach(callback => callback());
  assert.equal(app.query('.demo').dataset.replayStep, step);
  app.window.dispatchEvent(new app.window.Event('pagehide'));
  assert.equal(app.pending.size, 0);
  app.dom.window.close();
});

test('arrow keys navigate, form fields keep their keys, Escape exits Present and notes', () => {
  const app = mount();
  const key = (value, target = app.window.document) => target.dispatchEvent(new app.window.KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true }));
  key('ArrowRight');
  assert.equal(app.query('#stage').dataset.scene, 'workflow-chapter');
  key('ArrowRight', app.query('#durationSelect'));
  assert.equal(app.query('#stage').dataset.scene, 'workflow-chapter');
  key('ArrowLeft');
  assert.equal(app.query('#stage').dataset.scene, 'cover');
  app.click('#notesToggle');
  assert.equal(app.query('#notesToggle').getAttribute('aria-expanded'), 'true');
  app.click('#present');
  assert.ok(app.window.document.body.classList.contains('presenting'));
  key('Escape');
  assert.ok(!app.window.document.body.classList.contains('presenting'));
  assert.equal(app.query('#notes').hidden, true);
  app.dom.window.close();
});

test('reduced motion shows settled state immediately and media change cancels animation', () => {
  const app = mount(fixture(), true);
  app.chapter('workshop-chapter');
  assert.equal(app.pending.size, 0);
  assert.equal(app.query('#registrationNote').textContent, 'W2: no registrations yet');
  app.click('#replay');
  assert.equal(app.query('.demo').dataset.replayStep, '2');
  app.dom.window.close();
  const moving = mount();
  moving.chapter('workflow-chapter');
  moving.media.matches = true;
  moving.media.change();
  assert.equal(moving.pending.size, 0);
  assert.equal(moving.query('.demo').dataset.replayStep, '2');
  moving.dom.window.close();
});

test('all text is escaped in helpers, messages, proof and workshop events', () => {
  const data = fixture();
  const attack = '<img src=x onerror="window.injected=true"> & \'literal\'';
  data.cover.title = attack;
  data.scenes[2].content.items[0].body = attack;
  data.scenes[3].content.proof.description = attack;
  data.scenes[4].content.next.title = attack;
  const app = mount(data);
  assert.equal(app.query('#stage img'), null);
  assert.match(app.query('#stage').textContent, /<img/);
  assert.equal(app.window.SalesUI.fields([{ label: attack, value: attack }]).includes('<img'), false);
  for (const id of ['messages-chapter', 'outcome-chapter', 'workshop-chapter']) {
    app.chapter(id);
    app.flush();
    assert.equal(app.query('#stage img'), null);
    assert.match(app.query('#stage').textContent, /<img/);
  }
  assert.equal(app.window.injected, undefined);
  app.dom.window.close();
});

test('outgoing email sequence updates native preview with supplied escaped content', () => {
  const data = fixture();
  data.scenes[2].content.items = [0, 1, 2].map(index => ({ channel: 'email', direction: 'outgoing', sender: 'Fresh sender', time: `Fresh time ${index}`, subject: `Fresh email ${index}`, body: `Fresh paragraph ${index}\nNext line` }));
  const app = mount(data);
  app.chapter('messages-chapter');
  assert.match(app.query('#emailPaper').textContent, /Fresh email 0/);
  app.flush();
  assert.match(app.query('#emailPaper').textContent, /Fresh email 2/);
  app.click('#replay');
  assert.match(app.query('#emailPaper').textContent, /Fresh email 0/);
  app.dom.window.close();
});

test('contact initials follow each scene name while account and operator initials remain in chrome', () => {
  const data = fixture();
  data.account.initials = 'AC';
  data.account.operatorInitials = 'OP';
  for (const scene of data.scenes) scene.content.name = '  Robin  Newname  ';
  const app = mount(data);
  assert.equal(app.window.SalesUI.initials('  Robin  Newname  '), 'RN');
  assert.equal(app.window.SalesUI.initials('Élodie'), 'É');
  assert.equal(app.window.SalesUI.initials('李 明'), '李明');
  assert.equal(app.window.SalesUI.initials(''), '');
  app.route('3');
  for (const kind of ['record', 'messages', 'outcome', 'workshop']) {
    app.chapter(`${kind}-chapter`);
    const avatars = [...app.window.document.querySelectorAll('#stage .avatar')];
    assert.ok(avatars.length > 0, `${kind} has a contact avatar`);
    assert.ok(avatars.every(avatar => avatar.textContent === 'RN'), `${kind} uses contact initials`);
    assert.ok(avatars.every(avatar => avatar.getAttribute('aria-hidden') === 'true'));
    assert.equal(app.query('.acct').textContent, 'AC');
    assert.equal(app.query('.me').textContent, 'OP');
  }
  app.dom.window.close();
});

test('real n8n and GHL connectors start at their assigned branch output ports', () => {
  function branchJob(platform, explicitLabels = false) {
    const data = fixture();
    const scene = data.scenes[0];
    scene.platform = platform;
    const types = platform === 'n8n' ? ['webhook', 'if', 'gmail', 'slack'] : ['facebook_lead', 'condition', 'sms', 'email'];
    scene.content.nodes = types.map((type, index) => ({ id: `n${index}`, type, label: `Step ${index}`, detail: 'Sample' }));
    scene.content.edges = [{ from: 'n0', to: 'n1' }, { from: 'n1', to: 'n2' }, { from: 'n1', to: 'n3' }];
    scene.content.runOrder = ['n0', 'n1', 'n2'];
    if (explicitLabels) {
      scene.content.edges[1].label = 'false';
      scene.content.edges[2].label = 'true';
    }
    return data;
  }
  function start(app, from, to) {
    const command = app.query(`path[data-edge-from="${from}"][data-edge-to="${to}"]`).getAttribute('d');
    return /^M([\d.-]+),([\d.-]+)/.exec(command).slice(1).map(Number);
  }
  for (const explicit of [false, true]) {
    const app = mount(branchJob('n8n', explicit), false, true);
    app.chapter('workflow-chapter');
    const branch = app.query('[data-workflow-node="n1"]');
    const x = parseFloat(branch.style.left) + 168 / 2 + 72 / 2;
    const centerY = parseFloat(branch.style.top) + 72 / 2;
    assert.deepEqual(start(app, 'n1', 'n2'), [x, centerY + (explicit ? 16 : -16)]);
    assert.deepEqual(start(app, 'n1', 'n3'), [x, centerY + (explicit ? -16 : 16)]);
    app.dom.window.close();
  }
  const app = mount(branchJob('ghl'), false, true);
  app.chapter('workflow-chapter');
  const trigger = app.query('[data-workflow-node="n0"]');
  const branch = app.query('[data-workflow-node="n1"]');
  const bottom = node => parseFloat(node.style.top) + parseFloat(node.style.minHeight);
  assert.deepEqual(start(app, 'n0', 'n1'), [parseFloat(trigger.style.left) + 310 / 2, bottom(trigger)]);
  assert.deepEqual(start(app, 'n1', 'n2'), [parseFloat(branch.style.left) + 310 / 3, bottom(branch)]);
  assert.deepEqual(start(app, 'n1', 'n3'), [parseFloat(branch.style.left) + 310 * 2 / 3, bottom(branch)]);
  app.dom.window.close();
});

console.log('Runtime checks complete.');
