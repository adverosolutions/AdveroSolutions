/* Reusable sales presentation runtime. Job text is supplied only by DATA. */
(function () {
  'use strict';

  const job = typeof DATA !== 'undefined' ? DATA : window.DATA;
  const query = (selector, root = document) => root.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));
  const paths = {
    dashboard: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
    contact: 'M20 21v-2a6 6 0 0 0-12 0v2M14 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M3 8h3M3 12h3',
    conversation: 'M21 11a8 8 0 0 1-8 8H8l-5 3V6a3 3 0 0 1 3-3h7a8 8 0 0 1 8 8zM7 9h9M7 13h6',
    opportunity: 'M4 3h16v18H4zM8 7h8M8 11h5M8 15h8',
    workflow: 'M9 3h6v5H9zM3 17h6v5H3zM15 17h6v5h-6zM12 8v5M6 17v-4h12v4'
  };
  const icon = key => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[key] || paths.workflow}"></path></svg>`;
  const initials = name => {
    const words = String(name ?? '').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return '';
    const first = Array.from(words[0])[0];
    const last = words.length > 1 ? Array.from(words[words.length - 1])[0] : '';
    return (first + last).toLocaleUpperCase();
  };
  const avatar = (value = job) => `<div class="avatar" aria-hidden="true">${esc(typeof value === 'string' ? value : value?.account?.initials)}</div>`;
  const fields = values => (values || []).map(field => `<div class="field-row"><span>${esc(field.label)}</span><b>${esc(field.value)}</b></div>`).join('');

  // Platform functions may be loaded first, but must defer helper lookup until render.
  window.SalesUI = { esc, icon, avatar, fields, initials };

  if (!job) throw new Error('The presentation requires a normalized DATA object.');
  let duration = '1';
  let chapterIndex = 0;
  let timers = [];
  let generation = 0;
  const motion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  const sceneLabels = { workflow: 'The workflow', record: 'Capture', messages: 'Messages', outcome: 'The result', workshop: 'The result', carousel: 'Content preview', native: 'Native workspace' };
  const sceneLabel = scene => scene.kind === 'native' ? ({builder:'Workflow',pipeline:'Pipeline',conversations:'Conversation',editor:scene.platform==='zapier'?'The Zap':'Workflow',node:'The result',execution:'Execution',test:scene.content.selectedNode==='email'?'Customer response':'Saved enquiry',skills:'The skill',project:'Project context',chat:'The brief'}[scene.content.surface]) : sceneLabels[scene.kind];
  const routes = () => [
    { id: 'cover', kind: 'cover', ...job.cover },
    ...job.scenes.filter(scene => duration === '3' || !scene.optional),
    { id: 'close', kind: 'close', ...job.close }
  ];
  const current = () => routes()[chapterIndex];
  const badge = (text, color = '') => `<span class="badge ${color}">${esc(text)}</span>`;
  const contact = content => `<div class="contact-title">${avatar(initials(content.name))}<div><h3>${esc(content.name)}</h3><p>${esc(content.subtitle)}</p></div></div>`;
  const event = (value, index) => `<div class="event" data-step="${index}"><span class="dot">✓</span><div><b>${esc(value.title)}</b><small>${esc(value.detail)}</small></div></div>`;

  function cancel() {
    generation += 1;
    timers.forEach(window.clearTimeout);
    timers = [];
  }

  if (window.NativeScreens) window.NativeScreens.cancelReplay = cancel;

  function native(scene, title, active, tabs, body) {
    if (scene.platform !== 'ghl') {
      const names = { workbench: 'Custom project workspace', 'claude-code': 'Claude Code · project output', codex: 'Codex · project output' };
      if (!Object.prototype.hasOwnProperty.call(names, scene.platform) || !['record', 'messages', 'outcome', ...(scene.platform === 'workbench' ? ['carousel'] : [])].includes(scene.kind)) throw new Error('Unsupported project output adapter.');
      const labels = { record: ['Project record', 'Activity'], messages: ['Drafts and notes', 'Review'], outcome: ['Project result', 'Evidence'], carousel: ['Content approval', 'Carousel preview'] };
      return `<div class="native project-output po-${esc(scene.platform)}" data-platform="${esc(scene.platform)}"><div class="gbody"><div class="gtop"><strong>${names[scene.platform]}</strong><span class="location">${esc(job.account.name)}</span><span class="me">${esc(job.account.operatorInitials)}</span></div><div class="native-tabs">${labels[scene.kind].map((label, index) => `<span class="${index === 0 ? 'active' : ''}">${label}</span>`).join('')}<span class="po-sample">Illustrative sample</span></div>${body}</div></div>`;
    }
    return `<div class="native"><aside class="gnav" aria-label="GoHighLevel navigation">
      <div class="acct">${esc(job.account.initials)}</div>
      ${Object.keys(paths).map(key => `<div class="ni ${active === key ? 'active' : ''}" title="${esc(key)}">${icon(key)}</div>`).join('')}
      </aside><div class="gbody"><div class="gtop"><strong>${esc(title)}</strong>
      <span class="location">${esc(job.account.name)}</span><span class="me">${esc(job.account.operatorInitials)}</span></div>
      <div class="native-tabs">${tabs.map((tab, index) => `<span class="${index === 0 ? 'active' : ''}">${esc(tab)}</span>`).join('')}</div>${body}</div></div>`;
  }

  function cover(scene) {
    const greeting = job.personalization?.firstName ? `<div class="prepared-for">Prepared for ${esc(job.personalization.firstName)}</div>` : '';
    return `<div class="hero cover-slide"><div class="hero-copy">${greeting}
      <span class="eyebrow">${esc(scene.eyebrow)}</span><h1>${esc(scene.title)}<br><em>${esc(scene.accent)}</em></h1>
      <p>${esc(scene.caption)}</p><div class="anchors">${scene.anchors.map(anchor => `<span class="anchor">${esc(anchor)}</span>`).join('')}</div>
      <button id="seeWorkflow" class="primary cover-cta">${job.scenes[0].kind === 'native' && job.scenes[0].platform === 'claude' ? 'See the setup' : 'See the workflow'} <span aria-hidden="true">→</span></button></div>
      <div class="journey panel cover-preview"><div class="cover-preview-top"><span class="eyebrow">${esc(job.systemName)}</span><span class="preview-dot"></span></div>
      ${scene.previewSteps.map((step, index) => `<div class="journey-item"><div class="step-icon">${String(index + 1).padStart(2, '0')}</div><div><b>${esc(step.title)}</b><small>${esc(step.detail)}</small></div></div>`).join('')}
      <div class="journey-bottom"><span>${esc(scene.footer)}</span></div></div></div>`;
  }

  function close(scene) {
    return `<div class="success-slide"><div class="success-heading"><span class="eyebrow">${esc(scene.eyebrow)}</span>
      <h2>${esc(scene.title)} <em>${esc(scene.accent)}</em></h2><p>${esc(scene.caption)}</p></div>
      <div class="success-metrics">${scene.metrics.map(metric => `<div class="success-metric panel"><div class="metric-top">
      <span class="direction ${metric.direction}" aria-label="${metric.direction === 'down' ? 'Decrease' : 'Increase'}">${metric.direction === 'down' ? '↓' : '↑'}</span>
      <span class="metric-direction">${metric.direction === 'down' ? 'Reduce' : 'Increase'}</span></div><h3>${esc(metric.name)}</h3><p>${esc(metric.aim)}</p></div>`).join('')}</div>
      <div class="baseline-note">${esc(scene.baselineNote)}</div><div class="success-cta panel"><div><h3>${esc(scene.ctaTitle)}</h3><p>${esc(scene.ctaCopy)}</p></div>
      <div class="call-time"><b>15</b><span>minutes</span></div></div></div>`;
  }

  function record(scene) {
    const content = scene.content;
    return native(scene, 'Contacts', 'contact', ['Contact', 'Activity'], `<div class="content"><div class="two-col">
      <div class="source-card"><div class="record-heading"><strong>${esc(content.sourceTitle)}</strong></div>
      ${contact(content)}<hr class="rule">${fields(content.sourceFields)}<div class="notice" data-step="0">${esc(content.notice)}</div></div>
      <div class="record-card">${contact(content)}${fields(content.fields)}<div class="event-list">${content.events.map(event).join('')}</div></div>
      </div></div>`);
  }

  function message(item, index) {
    const classes = [item.direction === 'incoming' ? 'incoming' : '', item.channel === 'email' ? 'email' : '', item.channel === 'internal' ? 'internal' : ''].filter(Boolean).join(' ');
    return `<div class="message ${classes}" data-step="${index}"><small>${esc(item.channel.toUpperCase())} · ${esc(item.sender)} · ${esc(item.time)}</small>
      <div class="bubble">${item.subject ? `<b>${esc(item.subject)}</b>` : ''}${esc(item.body)}</div></div>`;
  }

  function messages(scene) {
    const content = scene.content;
    // Outgoing email sequences retain the approved email-preview interior.
    const emailOnly = content.items.every(item => item.channel === 'email' && item.direction === 'outgoing');
    if (emailOnly) {
      return native(scene, 'Conversations', 'conversation', ['Conversations', 'Email templates'], `<div class="email-layout">
        <aside class="inbox-list"><div class="inbox-title">Email sequence</div>${content.items.map((item, index) => `<div class="template-item ${index === 0 ? 'active' : ''}" data-template="${index}">${esc(item.subject || item.channel)}<small>${esc(item.time)}</small></div>`).join('')}</aside>
        <div class="email-preview"><div class="email-envelope" id="emailEnvelope"></div><div class="email-paper" id="emailPaper"></div></div>
        <aside class="email-side"><h4>${esc(content.name)}</h4>${fields(content.fields)}<div class="event-list">${content.items.map((item, index) => event({ title: item.subject || item.channel, detail: `${item.sender} · ${item.time}` }, index)).join('')}</div>
        <div class="notice green" data-step="${content.items.length - 1}">${esc(content.notice)}</div></aside></div>`);
    }
    return native(scene, 'Conversations', 'conversation', ['Conversations', 'Manual Actions', 'Snippets'], `<div class="conversation-layout">
      <aside class="inbox-list"><div class="inbox-title">All conversations</div><div class="inbox-item">${avatar(initials(content.name))}<div><b>${esc(content.name)}</b><small>${esc(content.subtitle)}</small></div></div></aside>
      <div class="thread"><div class="thread-top"><span>${esc(content.name)}</span>${badge([...new Set(content.items.map(item => item.channel.toUpperCase()))].join(' + '))}</div>${content.items.map(message).join('')}</div>
      <aside class="contact-side">${contact(content)}${fields(content.fields)}<div class="notice green" data-step="${content.items.length - 1}">${esc(content.notice)}</div></aside></div>`);
  }

  function outcome(scene) {
    const content = scene.content;
    const proof = content.proof;
    return native(scene, 'Dashboard', 'dashboard', ['Overview', 'Attribution'], `<div class="content"><div class="outcome-grid"><div>
      <div class="table-toolbar"><strong>${esc(content.name)}</strong>${badge('Illustrative sample', 'gray')}</div>
      <div class="metrics">${content.metrics.map((metric, index) => `<div class="metric" data-step="${index}"><small>${esc(metric.label)}</small><b>${esc(metric.value)}</b><small>${esc(metric.note)}</small></div>`).join('')}</div>
      <div class="record-strip">${avatar(initials(content.name))}<div><b>${esc(content.name)}</b><small>${esc(content.subtitle)}</small></div><span id="outcomeStage" class="badge green"></span></div>
      <div class="stage-track">${content.stages.map((stage, index) => `<span data-stage="${index}">${esc(stage)}</span>`).join('')}</div>
      ${fields(content.fields)}<div class="notice" data-step="${stepCount(scene) - 1}">${esc(content.note)}</div></div>
      ${proof ? `<div class="proof-card"><span class="proof-label">${esc(proof.label)}</span><div class="proof-big">${esc(proof.value)}</div><p>${esc(proof.description)}</p><hr class="rule"><p class="tiny">${esc(proof.sourceNote)}</p></div>` : ''}</div></div>`);
  }

  function workshop(scene) {
    const content = scene.content;
    return native(scene, 'Contacts', 'contact', [content.name, 'Activity', 'Workshop history'], `<div class="content"><div class="workshop-result">
      <div class="workshop-card">${contact(content)}<div class="event-list">${content.events.map(event).join('')}</div>
      <div class="attendance-email" data-step="${Math.max(1, content.events.length - 1)}"><h4>${esc(content.followup.subject)}</h4><p>${esc(content.followup.body)}</p></div>
      <div class="notice green" data-step="${stepCount(scene) - 1}">${esc(content.historyNote)}</div></div>
      <div class="workshop-card"><span class="eyebrow" id="eventKicker"></span><div class="date-big" id="eventDate"></div><div class="tiny" id="eventId"></div>
      <h4 id="eventTitle"></h4><div class="reuse-grid">${content.reusable.map(value => `<div class="reuse-item"><i>✓</i>${esc(value)}</div>`).join('')}</div>
      <div class="notice" id="registrationNote"></div><div class="tiny" id="historyNote">${esc(content.historyNote)}</div></div></div></div>`);
  }

  function carousel(scene) {
    const content = scene.content;
    let total = 0;
    if (!Array.isArray(content.slides) || content.slides.length < 2 || content.slides.length > 5 || scene.statuses.length !== content.slides.length) throw new Error('Carousel requires 2–5 slides and one status per slide.');
    content.slides.forEach(slide => {
      const value = slide.imageData;
      const match = typeof value === 'string' && value.length <= 2800000 && /^data:image\/(jpeg|png|webp);base64,([A-Za-z0-9+/]+={0,2})$/.exec(value);
      if (!match || match[2].length % 4) throw new Error('Invalid inline carousel image.');
      let raw;
      try { raw = window.atob(match[2]); } catch (_) { throw new Error('Invalid carousel image base64.'); }
      const valid = match[1] === 'jpeg' ? raw.startsWith('\xff\xd8\xff') : match[1] === 'png' ? raw.startsWith('\x89PNG\r\n\x1a\n') : raw.length >= 12 && raw.slice(0, 4) === 'RIFF' && raw.slice(8, 12) === 'WEBP';
      total += raw.length;
      if (!raw.length || !valid || total > 2 * 1024 * 1024) throw new Error('Carousel image MIME signature or total size is invalid.');
    });
    const first = content.slides[0];
    return native(scene, '', '', [], `<div class="carousel-layout"><section class="carousel-preview" aria-label="Custom carousel preview"><div class="carousel-toolbar"><strong>${esc(content.name)}</strong><span id="carouselCount" aria-live="polite"></span></div><div class="carousel-slide"><img id="carouselImage" src="${esc(first.imageData)}" alt="${esc(first.alt)}"><div class="carousel-copy"><span class="eyebrow">${esc(content.subtitle)}</span><h3 id="carouselTitle"></h3><p id="carouselBody"></p></div></div><div class="carousel-thumbnails" aria-label="Carousel slide sequence">${content.slides.map((slide, index) => `<div class="carousel-thumb" data-carousel-thumb="${index}"><img src="${esc(slide.imageData)}" alt=""><span>${index + 1}</span></div>`).join('')}</div></section><aside class="carousel-caption"><span class="eyebrow">Social caption</span><h3>Ready for your review</h3><p>${esc(content.caption)}</p>${fields(content.fields)}<div class="notice">Custom content approval preview · Illustrative sample</div></aside></div>`);
  }

  function sceneBody(scene) {
    if (scene.kind === 'native') return window.NativeScreens.render(scene, job);
    const compatible = { ghl: ['workflow', 'record', 'messages', 'outcome', 'workshop'], n8n: ['workflow'], make: ['workflow'], workbench: ['record', 'messages', 'outcome', 'carousel'], 'claude-code': ['workflow', 'record', 'messages', 'outcome'], codex: ['workflow', 'record', 'messages', 'outcome'] };
    if (!Object.prototype.hasOwnProperty.call(compatible, scene.platform) || !compatible[scene.platform].includes(scene.kind)) throw new Error('Unsupported scene/platform combination.');
    if (scene.kind === 'workflow') {
      if (!window.SalesPlatforms) throw new Error('Workflow adapters are unavailable.');
      return window.SalesPlatforms.renderWorkflow(scene, job);
    }
    return { record, messages, outcome, workshop, carousel }[scene.kind](scene);
  }

  function stepCount(scene) {
    const content = scene.content;
    if (!content) return 0;
    if (scene.kind === 'native') return scene.statuses.length;
    const visibleSteps = {
      workflow: () => content.runOrder.length,
      record: () => content.events.length,
      carousel: () => content.slides.length,
      messages: () => content.items.length,
      outcome: () => Math.max(content.stageSequence.length, content.metrics.length),
      workshop: () => Math.max(3, content.events.length + 1)
    }[scene.kind]();
    return Math.max(1, visibleSteps, scene.statuses.length);
  }

  function applyStep(scene, index) {
    const stage = query('#stage');
    if (scene.kind === 'native') window.NativeScreens.apply(scene, index, job);
    stage.querySelectorAll('[data-step]').forEach(element => element.classList.toggle('pending', Number(element.dataset.step) > index));
    if (scene.kind === 'workflow') window.SalesPlatforms.applyStep(scene, Math.min(index, scene.content.runOrder.length - 1));
    if (scene.kind === 'messages' && query('#emailPaper', stage)) {
      const item = scene.content.items[Math.min(index, scene.content.items.length - 1)];
      query('#emailEnvelope', stage).innerHTML = `<b>From:</b> ${esc(item.sender)} <span>•</span> <b>Subject:</b> ${esc(item.subject)}`;
      query('#emailPaper', stage).innerHTML = `<span class="eyebrow">${esc(item.time)}</span><h3>${esc(item.subject)}</h3><p>${esc(item.body).replace(/\n/g, '<br>')}</p>`;
      stage.querySelectorAll('[data-template]').forEach(element => element.classList.toggle('active', Number(element.dataset.template) === Math.min(index, scene.content.items.length - 1)));
    }
    if (scene.kind === 'carousel') {
      const position = Math.min(Math.max(0, index), scene.content.slides.length - 1);
      const slide = scene.content.slides[position];
      const image = query('#carouselImage', stage);
      image.src = slide.imageData;
      image.alt = slide.alt;
      query('#carouselTitle', stage).textContent = slide.title;
      query('#carouselBody', stage).textContent = slide.body;
      query('#carouselCount', stage).textContent = `${position + 1} / ${scene.content.slides.length}`;
      stage.querySelectorAll('[data-carousel-thumb]').forEach(element => element.classList.toggle('active', Number(element.dataset.carouselThumb) === position));
    }
    if (scene.kind === 'outcome') {
      const position = scene.content.stageSequence[Math.min(index, scene.content.stageSequence.length - 1)];
      query('#outcomeStage', stage).textContent = scene.content.stages[position];
      stage.querySelectorAll('[data-stage]').forEach(element => {
        element.classList.toggle('done', Number(element.dataset.stage) < position);
        element.classList.toggle('current', Number(element.dataset.stage) === position);
      });
    }
    if (scene.kind === 'workshop') {
      const settled = index >= stepCount(scene) - 1;
      const value = settled ? scene.content.next : scene.content.current;
      query('#eventKicker', stage).textContent = settled ? 'Next workshop ready' : 'Current workshop setup';
      query('#eventDate', stage).textContent = value.date;
      query('#eventId', stage).textContent = `${value.time} · ${value.id}`;
      query('#eventTitle', stage).textContent = value.title;
      query('#registrationNote', stage).textContent = settled ? `${value.id}: no registrations yet` : `${value.id}: current registration`;
    }
    const status = query('#replayStatus', stage);
    if (status) status.textContent = scene.statuses[Math.min(index, scene.statuses.length - 1)];
    query('.demo', stage)?.setAttribute('data-replay-step', String(index));
  }

  function finish() {
    cancel();
    const scene = current();
    if (scene.content) applyStep(scene, stepCount(scene) - 1);
  }

  function replay() {
    cancel();
    const scene = current();
    if (!scene.content) return;
    if (motion.matches) {
      applyStep(scene, stepCount(scene) - 1);
      return;
    }
    applyStep(scene, 0);
    const count = stepCount(scene);
    const token = generation;
    // All sequences, including twelve-node workflows, settle within five seconds.
    for (let index = 1; index < count; index += 1) {
      timers.push(window.setTimeout(() => {
        if (generation !== token || current().id !== scene.id) return;
        applyStep(scene, index);
      }, Math.round(index * 4500 / (count - 1))));
    }
  }

  function notes() {
    const scene = current();
    const details = scene.kind === 'cover' ? scene.anchors : scene.kind === 'close' ? scene.metrics.map(metric => `${metric.name}: ${metric.definition}`) : scene.details;
    const seconds = Math.round(Number(duration) * 60 / routes().length);
    query('#notesBody').innerHTML = `<span class="note-time">${duration}-minute route · about ${seconds} seconds here</span>
      <p>${esc(scene.beat)}</p><h4>${scene.kind === 'close' ? 'How we define the measures' : 'What to point out'}</h4>
      <ul>${details.map(detail => `<li>${esc(detail)}</li>`).join('')}</ul>
      ${scene.kind === 'close' ? `<p>${esc(scene.baselineNote)}</p>` : ''}
      <h4>Recording controls</h4><p>Native scenes open on their result. Replay shows the sequence and holds. Use Show result to finish immediately. Next or right arrow advances; Escape exits Present.</p>`;
  }

  function render() {
    cancel();
    const scene = current();
    query('#systemName').textContent = job.systemName;
    const stage = query('#stage');
    stage.dataset.scene = scene.id;
    if (scene.kind === 'cover' || scene.kind === 'close') {
      stage.innerHTML = scene.kind === 'cover' ? cover(scene) : close(scene);
    } else {
      stage.innerHTML = `<div class="chapterhead"><span class="eyebrow">${String(chapterIndex + 1).padStart(2, '0')} / ${esc(sceneLabel(scene))}</span>
        <h2>${esc(scene.title)}</h2><p>${esc(scene.caption)}</p></div><div class="demo panel">${sceneBody(scene)}
        <div class="demo-tools"><span class="status" id="replayStatus" role="status" aria-live="polite"></span>
        <button id="showResult" class="replay">Show result</button>${scene.kind === 'native' && scene.statuses.length === 1 ? '' : '<button id="replay" class="replay"><span class="replay-icon" aria-hidden="true">↻</span>Replay</button>'}</div></div>`;
      query('#replay')?.addEventListener('click', replay);
      query('#showResult').addEventListener('click', finish);
      if (scene.kind === 'native') finish(); else replay();
    }
    query('#chapters').innerHTML = routes().map((value, index) => `<button class="chapter-dot ${index === chapterIndex ? 'active' : ''}" data-chapter="${index}" ${index === chapterIndex ? 'aria-current="step"' : ''}><i></i><span>${esc(value.kind === 'cover' ? 'Your project' : value.kind === 'close' ? '15-minute call' : sceneLabel(value))}</span></button>`).join('');
    query('#chapters').querySelectorAll('[data-chapter]').forEach(button => button.addEventListener('click', () => go(Number(button.dataset.chapter))));
    query('#previous').disabled = chapterIndex === 0;
    query('#next').disabled = chapterIndex === routes().length - 1;
    query('#seeWorkflow')?.addEventListener('click', () => go(chapterIndex + 1));
    notes();
  }

  function go(index) {
    if (index < 0 || index >= routes().length) return;
    chapterIndex = index;
    render();
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }

  function showNotes(visible) {
    query('#notes').hidden = !visible;
    query('#notesToggle').setAttribute('aria-expanded', String(visible));
  }

  query('#durationSelect').addEventListener('change', event => {
    duration = event.target.value;
    chapterIndex = 0;
    render();
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  });
  query('#previous').addEventListener('click', () => go(chapterIndex - 1));
  query('#next').addEventListener('click', () => go(chapterIndex + 1));
  query('#notesToggle').addEventListener('click', () => showNotes(query('#notes').hidden));
  query('#closeNotes').addEventListener('click', () => showNotes(false));
  query('#present').addEventListener('click', () => {
    document.body.classList.add('presenting');
    showNotes(false);
    query('#present').blur();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      document.body.classList.remove('presenting');
      showNotes(false);
      return;
    }
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName) || event.target.isContentEditable || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      go(chapterIndex + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  if (motion.addEventListener) motion.addEventListener('change', () => { if (motion.matches) finish(); });
  window.addEventListener('pagehide', cancel);
  window.addEventListener('beforeunload', cancel);
  render();
})();
