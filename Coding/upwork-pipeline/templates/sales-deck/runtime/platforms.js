(function () {
  'use strict';

  // Semantic interface icons, not copies of vendor marks. No network assets.
  const glyphs = {
    bolt: '<path d="M13 2 4 14h7l-1 8 10-13h-7z"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    briefcase: '<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V3h8v4M3 12h18M10 12v3h4v-3"/>',
    chat: '<path d="M4 4h16v12H9l-5 4zM8 8h8M8 12h5"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    bell: '<path d="M6 9a6 6 0 0 1 12 0v5l3 3H3l3-3zM9 20h6"/>',
    tag: '<path d="M3 3h8l10 10-8 8L3 11z"/><circle cx="7" cy="7" r="1"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6M17 2v6M3 11h18M7 15h3M14 15h3"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>',
    branch: '<circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 12h5V5h5M12 12v7h5"/>',
    webhook: '<circle cx="6" cy="16" r="4"/><circle cx="18" cy="16" r="4"/><circle cx="12" cy="5" r="3"/><path d="m10 7-4 9h12l-4-9"/>',
    edit: '<path d="m15 3 6 6-12 12H3v-6zM12 6l6 6"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18z"/>',
    grid: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>'
  };
  function svg(key) {
    const shape = glyphs[key];
    if (!shape) throw new Error('Unknown catalog icon: ' + key);
    return '<svg viewBox="0 0 24 24" aria-hidden="true">' + shape + '</svg>';
  }
  function helpers() {
    if (!window.SalesUI || typeof window.SalesUI.esc !== 'function') {
      throw new Error('SalesUI must be initialized before workflow rendering.');
    }
    return window.SalesUI;
  }
  function catalogPlatform(key) {
    const catalog = typeof PLATFORM_CATALOG !== 'undefined' ? PLATFORM_CATALOG : window.PLATFORM_CATALOG;
    if (!catalog || !catalog.platforms || !Object.prototype.hasOwnProperty.call(catalog.platforms, key)) {
      throw new Error('Unsupported workflow platform: ' + key);
    }
    const platform = catalog.platforms[key];
    if (platform.status !== 'supported' || !['ghl', 'n8n', 'make', 'claude-code', 'codex'].includes(key)) {
      throw new Error('Unsupported workflow platform: ' + key);
    }
    return platform;
  }
  function graph(scene) {
    if (!scene || scene.kind !== 'workflow') throw new Error('Expected workflow scene.');
    const platform = catalogPlatform(scene.platform);
    const content = scene.content;
    if (!content || !Array.isArray(content.nodes) || content.nodes.length < 2 || content.nodes.length > 12) {
      throw new Error('Workflow requires 2–12 nodes.');
    }
    if (!Array.isArray(content.edges) || !Array.isArray(content.runOrder) || !content.runOrder.length) {
      throw new Error('Workflow edges and sample runOrder are required.');
    }
    const nodes = new Map(), incoming = new Map(), outgoing = new Map();
    content.nodes.forEach(function (node) {
      if (!node || typeof node.id !== 'string' || !node.id || nodes.has(node.id)) {
        throw new Error('Workflow node IDs must be unique nonempty strings.');
      }
      const action = Object.prototype.hasOwnProperty.call(platform.actions, node.type) ? platform.actions[node.type] : null;
      if (!action || action.available !== true) throw new Error('Unsupported ' + scene.platform + ' action: ' + node.type);
      if (!/^#[0-9a-f]{6}$/i.test(action.color) || !glyphs[action.icon]) throw new Error('Invalid visual action catalog.');
      nodes.set(node.id, Object.assign({}, node, { action: action }));
      incoming.set(node.id, []); outgoing.set(node.id, []);
    });
    const pairs = new Set();
    content.edges.forEach(function (edge, index) {
      if (!edge || !nodes.has(edge.from) || !nodes.has(edge.to) || edge.from === edge.to) {
        throw new Error('Invalid workflow edge.');
      }
      const pair = JSON.stringify([edge.from, edge.to]);
      if (pairs.has(pair)) throw new Error('Duplicate workflow edge.');
      pairs.add(pair);
      const copy = Object.assign({}, edge, { index: index });
      incoming.get(edge.to).push(copy); outgoing.get(edge.from).push(copy);
    });
    const degree = new Map(), ranks = new Map(), queue = [], ordered = [];
    nodes.forEach(function (_, id) {
      degree.set(id, incoming.get(id).length); ranks.set(id, 0);
      if (!degree.get(id)) queue.push(id);
    });
    while (queue.length) {
      const id = queue.shift(); ordered.push(id);
      outgoing.get(id).forEach(function (edge) {
        ranks.set(edge.to, Math.max(ranks.get(edge.to), ranks.get(id) + 1));
        degree.set(edge.to, degree.get(edge.to) - 1);
        if (!degree.get(edge.to)) queue.push(edge.to);
      });
    }
    if (ordered.length !== nodes.size) throw new Error('Workflow graph must be acyclic.');
    const triggers = Array.from(nodes.values()).filter(function (node) { return node.action.kind === 'trigger'; });
    if (triggers.length !== 1 || incoming.get(triggers[0].id).length) throw new Error('Workflow requires one root trigger.');
    const reachable = new Set(), pending = [triggers[0].id];
    while (pending.length) {
      const id = pending.shift();
      if (reachable.has(id)) continue;
      reachable.add(id); outgoing.get(id).forEach(function (edge) { pending.push(edge.to); });
    }
    if (reachable.size !== nodes.size) throw new Error('Every workflow node must be reachable from the trigger.');
    if (content.runOrder[0] !== triggers[0].id) throw new Error('Sample path must start at the trigger.');
    const visited = new Set();
    content.runOrder.forEach(function (id, index) {
      if (!nodes.has(id) || visited.has(id) || (index && !pairs.has(JSON.stringify([content.runOrder[index - 1], id])))) {
        throw new Error('runOrder must describe one connected sample path.');
      }
      visited.add(id);
    });
    if (outgoing.get(content.runOrder[content.runOrder.length - 1]).length) throw new Error('Sample path must end at a terminal result.');
    if (['claude-code', 'codex'].includes(scene.platform) && (content.runOrder.length !== nodes.size || content.edges.length !== nodes.size - 1 || Array.from(outgoing.values()).some(function (edges) { return edges.length > 1; }))) throw new Error('Agent transcript requires one linear chain containing every task stage.');
    nodes.forEach(function (node, id) {
      if (scene.platform === 'n8n' && node.type === 'if' && outgoing.get(id).length > 2) {
        throw new Error('n8n If supports only true and false outputs.');
      }
    });
    return { platform: platform, content: content, nodes: nodes, incoming: incoming, outgoing: outgoing, ordered: ordered, ranks: ranks };
  }
  // Layered DAG placement. Ordering is stable; siblings follow their source edges.
  // Size is computed from graph depth, lane count and text length, never job IDs.
  function layout(g, platform) {
    const vertical = platform === 'ghl';
    const groups = [];
    g.ordered.forEach(function (id) {
      const rank = g.ranks.get(id);
      if (!groups[rank]) groups[rank] = [];
      groups[rank].push(id);
    });
    const positions = new Map();
    const textLines = function (text, chars) { return Math.max(1, Math.ceil(Array.from(String(text || '')).length / chars)); };
    let nodeHeight = vertical ? 64 : 178;
    g.nodes.forEach(function (node) {
      const label = node.label || node.action.label;
      const detail = node.detail === label ? '' : node.detail || '';
      const actionLabel = (node.action.app ? node.action.app + ' · ' : '') + node.action.label;
      const height = vertical ? 18 + textLines(actionLabel, 34) * 12 + textLines(label, 36) * 14 + textLines(detail, 42) * 12 : 92 + textLines(label, 23) * 14 + textLines(actionLabel, 25) * 12 + textLines(detail, 26) * 12;
      nodeHeight = Math.max(nodeHeight, height);
    });
    const w = vertical ? 310 : 168, h = nodeHeight;
    const gapX = vertical ? 84 : 64, gapY = vertical ? 20 : 42;
    const skipped = g.content.edges.filter(function (edge) { return g.ranks.get(edge.to) - g.ranks.get(edge.from) > 1; });
    const margin = 24 + skipped.length * 10;
    const maxLanes = Math.max.apply(null, groups.map(function (group) { return group.length; }));
    const width = vertical ? 2 * margin + maxLanes * w + (maxLanes - 1) * gapX : 2 * margin + groups.length * w + (groups.length - 1) * gapX;
    const height = vertical ? 2 * margin + groups.length * h + (groups.length - 1) * gapY : 2 * margin + maxLanes * h + (maxLanes - 1) * gapY;
    groups.forEach(function (group, rank) {
      group.forEach(function (id, lane) {
        const span = vertical ? group.length * w + (group.length - 1) * gapX : group.length * h + (group.length - 1) * gapY;
        const x = vertical ? (width - span) / 2 + lane * (w + gapX) : margin + rank * (w + gapX);
        const y = vertical ? margin + rank * (h + gapY) : (height - span) / 2 + lane * (h + gapY);
        positions.set(id, { x: x, y: y, w: w, h: h });
      });
    });
    return { positions: positions, width: width, height: height, vertical: vertical, skipped: skipped };
  }
  function outputIndex(g, node, edge) {
    const outgoing = g.outgoing.get(node.id);
    if (node.type === 'if') {
      const label = String(edge.label || '').toLowerCase().trim();
      if (label === 'false') return 1;
      if (label === 'true') return 0;
    }
    // Adjacency lists contain indexed copies; renderers iterate content edges.
    return outgoing.findIndex(function (candidate) { return candidate.from === edge.from && candidate.to === edge.to; });
  }
  function points(g, l, edge, platform) {
    const a = l.positions.get(edge.from), b = l.positions.get(edge.to), source = g.nodes.get(edge.from);
    if (l.vertical) {
      const outputs = g.outgoing.get(edge.from).length;
      const idx = outputIndex(g, source, edge);
      return [[a.x + a.w * (idx + 1) / (outputs + 1), a.y + a.h], [b.x + b.w / 2, b.y]];
    }
    const core = platform === 'make' ? 84 : 72;
    const sourceRadius = platform === 'make' && source.action.kind === 'branch' ? 32 : core / 2;
    const targetRadius = platform === 'make' && g.nodes.get(edge.to).action.kind === 'branch' ? 32 : core / 2;
    const isIf = platform === 'n8n' && source.type === 'if';
    const idx = outputIndex(g, source, edge);
    const sy = a.y + core / 2 + (isIf ? (idx ? 16 : -16) : 0);
    return [[a.x + a.w / 2 + sourceRadius, sy], [b.x + b.w / 2 - targetRadius, b.y + core / 2]];
  }
  function connections(g, l, platform, esc) {
    let html = '<svg class="sp-lines" width="' + l.width + '" height="' + l.height + '" aria-hidden="true">';
    g.content.edges.forEach(function (edge) {
      const p = points(g, l, edge, platform), a = p[0], b = p[1];
      const bend = l.vertical ? (a[1] + b[1]) / 2 : (a[0] + b[0]) / 2;
      let d = l.vertical ? 'M' + a[0] + ',' + a[1] + ' C' + a[0] + ',' + bend + ' ' + b[0] + ',' + bend + ' ' + b[0] + ',' + b[1] : 'M' + a[0] + ',' + a[1] + ' C' + bend + ',' + a[1] + ' ' + bend + ',' + b[1] + ' ' + b[0] + ',' + b[1];
      if (g.ranks.get(edge.to) - g.ranks.get(edge.from) > 1) {
        const track = 12 + l.skipped.indexOf(edge) * 10;
        if (l.vertical) {
          d = 'M' + a[0] + ',' + a[1] + ' V' + (a[1] + 10) + ' H' + track + ' V' + (b[1] - 10) + ' H' + b[0] + ' V' + b[1];
        } else {
          const sourceBox = l.positions.get(edge.from), targetBox = l.positions.get(edge.to);
          const right = sourceBox.x + sourceBox.w + 12, left = targetBox.x - 12;
          d = 'M' + a[0] + ',' + a[1] + ' H' + right + ' V' + track + ' H' + left + ' V' + b[1] + ' H' + b[0];
        }
      }
      html += '<path data-edge-from="' + esc(edge.from) + '" data-edge-to="' + esc(edge.to) + '" d="' + d + '"/>';
    });
    html += '</svg>';
    g.content.edges.forEach(function (edge) {
      if (!edge.label) return;
      const p = points(g, l, edge, platform);
      const skipped = g.ranks.get(edge.to) - g.ranks.get(edge.from) > 1;
      const track = 12 + l.skipped.indexOf(edge) * 10;
      let x = skipped && l.vertical ? track : (p[0][0] + p[1][0]) / 2;
      let y = skipped && !l.vertical ? track : (p[0][1] + p[1][1]) / 2;
      if (!l.vertical && !skipped) {
        // Near the source's curve, inside the whitespace between node columns.
        // Keeping the label inside that gap avoids downstream detail text.
        const sourceBox = l.positions.get(edge.from), targetBox = l.positions.get(edge.to);
        x = (sourceBox.x + sourceBox.w + targetBox.x) / 2;
        const t = 0.3;
        y = p[0][1] * (1 - 3 * t * t + 2 * t * t * t) + p[1][1] * (3 * t * t - 2 * t * t * t) - 6;
      }
      html += '<span class="sp-edge-label" data-edge-from="' + esc(edge.from) + '" data-edge-to="' + esc(edge.to) + '" style="left:' + x + 'px;top:' + y + 'px">' + esc(edge.label) + '</span>';
    });
    return html;
  }
  function ports(g, node, platform) {
    if (platform !== 'n8n') return '';
    let html = node.action.kind === 'trigger' ? '' : '<span class="sp-port sp-input"></span>';
    if (node.type === 'if') {
      html += '<span class="sp-port sp-output sp-output-true"></span><small class="sp-port-name sp-true">true</small><span class="sp-port sp-output sp-output-false"></span><small class="sp-port-name sp-false">false</small>';
    } else {
      html += '<span class="sp-port sp-output"></span>';
    }
    return html;
  }
  function nodeHTML(g, l, node, platform, index, esc) {
    const p = l.positions.get(node.id), action = node.action;
    const label = node.label || action.label;
    const detail = node.detail === label ? '' : node.detail || '';
    const detailHTML = detail ? '<span>' + esc(detail) + '</span>' : '';
    const actionText = (action.app ? action.app + ' · ' : '') + action.label;
    const style = 'left:' + p.x + 'px;top:' + p.y + 'px;width:' + p.w + 'px;min-height:' + p.h + 'px;--action-color:' + action.color;
    const attributes = ' data-workflow-node="' + esc(node.id) + '" data-kind="' + esc(action.kind) + '" aria-label="' + esc(label + '. ' + actionText + (detail ? '. ' + detail : '')) + '" style="' + style + '"';
    if (platform === 'ghl') {
      return '<div class="sp-node sp-ghl-node"' + attributes + '><span class="sp-node-icon">' + svg(action.icon) + '</span><div class="sp-node-copy"><small>' + esc(action.kind === 'trigger' ? 'Trigger' : action.kind === 'branch' ? 'Condition' : 'Action') + ' · ' + esc(action.label) + '</small><b>' + esc(label) + '</b>' + detailHTML + '</div><span class="sp-complete" aria-hidden="true">✓</span></div>';
    }
    return '<div class="sp-node sp-' + platform + '-node"' + attributes + '><div class="sp-node-core">' + svg(action.icon) + ports(g, node, platform) + (platform === 'make' ? '<span class="sp-module-number">' + (index + 1) + '</span>' : '') + '<span class="sp-complete" aria-hidden="true">✓</span></div><div class="sp-node-copy"><b>' + esc(label) + '</b><small>' + esc(actionText) + '</small>' + detailHTML + '</div></div>';
  }
  function contextHTML(content, job, esc, agent) {
    const ui = helpers(), c = content.context || {};
    let html = '<aside class="sp-context"><div class="sp-contact"><div class="contact-title">' + ui.avatar(ui.initials(c.name)) + '<div><h3>' + esc(c.name || '') + '</h3><p>' + esc(c.subtitle || '') + '</p></div></div>' + ui.fields(c.fields || []) + '<div class="sp-context-state" role="status">' + esc((c.states || [])[0] || '') + '</div></div>';
    if (content.related && content.related.length) {
      html += '<div class="sp-related"><span class="sp-related-title">' + (agent ? 'Project artifacts' : 'Related workflows') + '</span>' + content.related.map(function (item) {
        return '<div class="sp-related-item"><span class="sp-related-icon">' + svg('branch') + '</span><div><b>' + esc(item.title) + '</b><p>' + esc(item.detail) + '</p></div></div>';
      }).join('') + '</div>';
    }
    return html + '</aside>';
  }
  function renderAgent(scene, job, g) {
    const ui = helpers(), esc = ui.esc;
    const items = g.content.runOrder.map(function (id, index) {
      const node = g.nodes.get(id);
      return '<article class="sp-task" data-workflow-node="' + esc(id) + '"><span class="sp-task-check" aria-hidden="true">✓</span><div><small>' + esc(node.action.label) + '</small><b>' + esc(node.label) + '</b><p>' + esc(node.detail) + '</p></div><span class="sp-task-index">' + String(index + 1).padStart(2, '0') + '</span></article>';
    }).join('');
    return '<div class="native sales-workflow sp-agent sp-' + esc(scene.platform) + '" data-workflow-scene="' + esc(scene.id) + '" data-platform="' + esc(scene.platform) + '"><div class="gbody"><div class="gtop sp-top"><strong>' + esc(g.platform.name) + '</strong><span class="sp-workflow-name">' + esc(g.content.name) + '</span><span class="location">' + esc(job.account.name) + '</span><span class="me">' + esc(job.account.operatorInitials) + '</span></div><div class="native-tabs"><span class="active">Terminal session</span><span>Project context</span><span class="sp-sample-label">Illustrative sample</span></div><div class="sp-workspace"><div class="sp-transcript" tabindex="0" role="region" aria-label="' + esc(g.platform.name) + ' illustrative task transcript"><div class="sp-terminal-head"><span aria-hidden="true">›</span> ' + esc(g.content.name) + '<small>Conceptual task stages · sample output</small></div>' + items + '</div>' + contextHTML(g.content,job,esc,true) + '</div></div></div>';
  }
  function renderWorkflow(scene, job) {
    const ui = helpers(), esc = ui.esc, g = graph(scene);
    if (['claude-code', 'codex'].includes(scene.platform)) return renderAgent(scene, job, g);
    const l = layout(g, scene.platform);
    const nav = scene.platform === 'ghl' ? '<aside class="gnav" aria-label="GoHighLevel navigation"><div class="acct">' + esc(job.account.initials) + '</div>' + ['dashboard','contact','conversation','opportunity','workflow'].map(function (key) { return '<div class="ni ' + (key === 'workflow' ? 'active' : '') + '" title="' + esc(key) + '">' + ui.icon(key) + '</div>'; }).join('') + '</aside>' : '';
    const tabs = scene.platform === 'ghl' ? ['Workflows','Builder'] : scene.platform === 'n8n' ? ['Editor','Executions'] : ['Scenario','History'];
    let html = '<div class="native sales-workflow sp-' + scene.platform + '" data-workflow-scene="' + esc(scene.id) + '" data-platform="' + esc(scene.platform) + '">' + nav + '<div class="gbody"><div class="gtop sp-top"><strong>' + esc(scene.platform === 'ghl' ? 'Automation' : g.platform.name) + '</strong><span class="sp-workflow-name">' + esc(g.content.name) + '</span><span class="location">' + esc(job.account.name) + '</span><span class="me">' + esc(job.account.operatorInitials) + '</span></div><div class="native-tabs">' + tabs.map(function (tab,index) { return '<span class="' + (!index ? 'active' : '') + '">' + esc(tab) + '</span>'; }).join('') + '<span class="sp-sample-label">Illustrative sample</span></div><div class="sp-workspace"><div class="sp-canvas-scroll" tabindex="0" role="region" aria-label="' + esc(g.platform.name + ' workflow canvas. Scroll to inspect the full graph.') + '"><div class="sp-canvas-size" style="width:' + l.width + 'px;height:' + l.height + 'px"><div class="sp-canvas" style="width:' + l.width + 'px;height:' + l.height + 'px">' + connections(g,l,scene.platform,esc);
    g.content.nodes.forEach(function (node,index) { html += nodeHTML(g,l,g.nodes.get(node.id),scene.platform,index,esc); });
    html += '</div></div></div>' + contextHTML(g.content,job,esc) + '</div></div></div>';
    return html;
  }
  function fitCanvas(frame) {
    const viewport = frame.querySelector('.sp-canvas-scroll');
    if (!viewport || !viewport.clientWidth || !viewport.clientHeight) return null;
    const canvas = frame.querySelector('.sp-canvas'), sizing = frame.querySelector('.sp-canvas-size');
    const canvasWidth = parseFloat(canvas.style.width), canvasHeight = parseFloat(canvas.style.height);
    const desktopHorizontal = frame.dataset.platform !== 'ghl' && window.innerWidth > 760;
    const scale = desktopHorizontal ? Math.max(0.7, Math.min(1, viewport.clientWidth / canvasWidth, viewport.clientHeight / canvasHeight)) : 1;
    canvas.style.transform = 'scale(' + scale + ')';
    sizing.style.width = canvasWidth * scale + 'px'; sizing.style.height = canvasHeight * scale + 'px';
    frame.dataset.canvasScale = String(scale);
    const fitsX = canvasWidth * scale <= viewport.clientWidth + 0.5, fitsY = canvasHeight * scale <= viewport.clientHeight + 0.5;
    if (fitsX) viewport.scrollLeft = 0;
    if (fitsY) viewport.scrollTop = 0;
    return { viewport: viewport, scale: scale, fitsX: fitsX, fitsY: fitsY };
  }
  // One document-lifetime listener; mounted frames are looked up on each event.
  // It retains no scene/frame references and creates no per-navigation observers.
  window.addEventListener('resize', function () {
    const root = document.querySelector('#stage') || document;
    root.querySelectorAll('.sales-workflow').forEach(fitCanvas);
  });
  function applyStep(scene, stepIndex) {
    if (!scene || scene.kind !== 'workflow') return;
    const root = document.querySelector('#stage') || document;
    const frame = Array.from(root.querySelectorAll('.sales-workflow')).find(function (candidate) {
      return candidate.dataset.workflowScene === scene.id && candidate.dataset.platform === scene.platform;
    });
    if (!frame) return;
    const order = scene.content.runOrder;
    const step = Math.min(order.length - 1, Math.max(-1, Number.isFinite(stepIndex) ? Math.floor(stepIndex) : -1));
    const done = new Set(order.slice(0, step + 1));
    const activeEdges = new Set();
    for (let i = 1; i <= step; i++) activeEdges.add(JSON.stringify([order[i - 1],order[i]]));
    frame.querySelectorAll('[data-workflow-node]').forEach(function (node) {
      node.classList.toggle('active', done.has(node.dataset.workflowNode));
      node.classList.toggle('is-current', node.dataset.workflowNode === order[step]);
      node.dataset.runState = done.has(node.dataset.workflowNode) ? 'visited' : 'inactive';
    });
    frame.querySelectorAll('[data-edge-from]').forEach(function (edge) {
      edge.classList.toggle('active', activeEdges.has(JSON.stringify([edge.dataset.edgeFrom,edge.dataset.edgeTo])));
    });
    const states = scene.content.context.states;
    const state = frame.querySelector('.sp-context-state');
    if (state) state.textContent = step < 0 ? '' : states[Math.min(step, states.length - 1)] || '';
    frame.dataset.step = String(step);
    // Pan only the canvas when the sample's current node leaves its viewport.
    // This never scrolls the page or creates timers. Replay starts at the trigger.
    const current = Array.from(frame.querySelectorAll('[data-workflow-node]')).find(function (node) { return node.dataset.workflowNode === order[step]; });
    const transcript = frame.querySelector('.sp-transcript');
    if (current && transcript) {
      if (step === 0) transcript.scrollTop = 0;
      else if (current.offsetTop < transcript.scrollTop || current.offsetTop + current.offsetHeight > transcript.scrollTop + transcript.clientHeight) transcript.scrollTop = Math.max(0, current.offsetTop - 16);
    }
    const fitted = fitCanvas(frame);
    if (current && fitted) {
      const viewport = fitted.viewport, scale = fitted.scale, fitsX = fitted.fitsX, fitsY = fitted.fitsY;
      const x = parseFloat(current.style.left) * scale, y = parseFloat(current.style.top) * scale;
      const w = parseFloat(current.style.width) * scale, h = parseFloat(current.style.minHeight) * scale;
      if (fitsX) viewport.scrollLeft = 0;
      else if (step === 0 || x < viewport.scrollLeft || x + w > viewport.scrollLeft + viewport.clientWidth) viewport.scrollLeft = Math.max(0, x + w / 2 - viewport.clientWidth / 2);
      if (fitsY) viewport.scrollTop = 0;
      else if (step === 0 || y < viewport.scrollTop || y + h > viewport.scrollTop + viewport.clientHeight) viewport.scrollTop = Math.max(0, y + h / 2 - viewport.clientHeight / 2);
    }
  }
  window.SalesPlatforms = { renderWorkflow: renderWorkflow, applyStep: applyStep };
}());
