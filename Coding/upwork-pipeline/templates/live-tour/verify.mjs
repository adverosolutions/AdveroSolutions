// Live tour verify (templates/live-tour). Usage:
//   node verify.mjs <out-dir> <tour-url> [compare-url]
// Serve the job folder over http first (python3 -m http.server). Checks desktop 1440x900,
// mobile 390x844 and reduced motion: console errors, page overflow, dock/top-bar fit,
// spotlight inside the frame, text clipping, panel spill, fonts loaded, and that motion
// settles (running animations 0) and back navigation returns to step 1.
// Pass: every step has bad [] and docOverflow false, running 0, font true, errors [].
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const OUT = process.argv[2];
const URL0 = process.argv[3];
const COMPARE = process.argv[4] || '';
if (!OUT || !URL0) { console.error('usage: node verify.mjs <out-dir> <tour-url> [compare-url]'); process.exit(2); }
let N = 0;
fs.mkdirSync(OUT, { recursive: true });
// Parallel builders: each run gets its own debugging port (set CDP_PORT to pin one).
const port = +process.env.CDP_PORT || (9400 + Math.floor(Math.random() * 400));
const prof = fs.mkdtempSync('/tmp/livetour-chrome-');
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, '--no-first-run', '--hide-scrollbars', '--force-device-scale-factor=1', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 50; i++) { try { await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); break; } catch { await sleep(200); } }
const tgt = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(tgt.webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const pend = new Map(); const errors = [];
ws.onmessage = ev => { const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); return; }
  if (m.method === 'Runtime.consoleAPICalled' && (m.params.type === 'error' || m.params.type === 'warning')) errors.push(m.params.type + ': ' + m.params.args.map(a => a.value ?? a.description).join(' '));
  if (m.method === 'Runtime.exceptionThrown') errors.push('exception: ' + JSON.stringify(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
  if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errors.push('log: ' + m.params.entry.text + ' ' + (m.params.entry.url || ''));
};
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
const probe = `(() => {
  const W = innerWidth, H = innerHeight, bad = [];
  const running = document.getAnimations().filter(a => a.playState === 'running').length;
  const dock = document.getElementById('dock').getBoundingClientRect();
  const topb = document.querySelector('.top').getBoundingClientRect();
  if (dock.left < 0 || dock.right > W || dock.bottom > H || dock.top < topb.bottom) bad.push('dock ' + JSON.stringify(dock));
  document.querySelectorAll('.dock *, .top *').forEach(el => { const r = el.getBoundingClientRect(); if (!r.width) return; if (r.right > W + 1 || r.left < -1) bad.push('chrome-x:' + (el.id||el.className)); if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflow !== 'visible') bad.push('chrome-clip:' + (el.id||el.className)); });
  // focus element must be fully visible between top bar and dock
  const sp = document.getElementById('spot');
  let spotR = null;
  if (sp.classList.contains('on')) { const r = sp.getBoundingClientRect(); spotR = [r.left, r.top, r.right, r.bottom].map(Math.round);
    if (r.left < -1 || r.right > W + 1 || r.top < topb.bottom - 1 || r.bottom > dock.top + 1) bad.push('spot-out ' + spotR); }
  // text clipping inside app
  document.querySelectorAll('#app *').forEach(el => { const cs = getComputedStyle(el); if (cs.overflow === 'visible') return; if (el.classList.contains('panel') || el.classList.contains('app')) { if (el.scrollHeight > el.clientHeight + 1) bad.push('panel-overflow:' + (el.id||el.className)); return; }
    if (el.scrollWidth > el.clientWidth + 1) bad.push('clip:' + (el.id||el.className)); });
  // children of panels spilling outside the panel box
  document.querySelectorAll('.app .view .panel').forEach(p => { if (getComputedStyle(p.closest('.view')).opacity === '0') return; const pr = p.getBoundingClientRect(); p.querySelectorAll('*').forEach(c => { const r = c.getBoundingClientRect(); if (!r.width || getComputedStyle(c).opacity === '0') return; if (r.right > pr.right + 1 || r.bottom > pr.bottom + 1) bad.push('spill:' + (p.id) + '>' + (c.className||c.tagName)); }); });
  const m = new DOMMatrix(getComputedStyle(document.getElementById('app')).transform);
  return { step: location.hash, running, docOverflow: document.documentElement.scrollWidth > W || document.documentElement.scrollHeight > H, scale: +m.a.toFixed(3), spot: spotR, bad: [...new Set(bad)].slice(0, 12), font: document.fonts.check('16px Geist'), cap: document.getElementById('cap').innerText.replace(/\\s+/g, ' ') };
})()`;
const modes = [
  { name: 'desktop', w: 1440, h: 900, mobile: false, rm: false, wait: 3600 },
  { name: 'mobile', w: 390, h: 844, mobile: true, rm: false, wait: 3600 },
  { name: 'reduced', w: 1440, h: 900, mobile: false, rm: true, wait: 200 },
];
const report = {};
for (const m of modes) {
  await send('Emulation.setDeviceMetricsOverride', { width: m.w, height: m.h, deviceScaleFactor: m.mobile ? 2 : 1, mobile: m.mobile });
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: m.rm ? 'reduce' : 'no-preference' }] });
  await send('Page.navigate', { url: URL0 + '?v=' + Date.now() + '#1' }); await sleep(2000);
  if (!N) N = await ev(`document.querySelectorAll('#dots button').length`);
  report[m.name] = [];
  for (let i = 1; i <= N; i++) {
    if (i > 1) { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 }); }
    let early; if (!m.rm) { await sleep(300); early = await ev(`document.getAnimations().filter(a=>a.playState==='running').length`); }
    await sleep(m.wait);
    const p = await ev(probe); p.runningAt300ms = early;
    const shot = await send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(OUT, `${m.name}-${String(i).padStart(2, '0')}.png`), Buffer.from(shot.result.data, 'base64'));
    if (m.name !== 'desktop') delete p.cap;
    report[m.name].push(p);
  }
}
// back navigation sanity: go back to step 1 then forward, check state classes
await send('Emulation.setEmulatedMedia', { features: [] });
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: URL0 + '?v=' + Date.now() + '#' + N }); await sleep(1500);
for (let i = 0; i < N - 1; i++) for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'ArrowLeft', code: 'ArrowLeft', windowsVirtualKeyCode: 37 });
await sleep(2500);
report.backToStart = await ev(`({hash:location.hash, cls:document.getElementById('app').className})`);
const shot = await send('Page.captureScreenshot', { format: 'png' });
fs.writeFileSync(path.join(OUT, `back-to-01.png`), Buffer.from(shot.result.data, 'base64'));
// compare page
for (const [nm, w, h, mob] of (COMPARE ? [['compare-desktop', 1440, 900, false], ['compare-mobile', 390, 844, true]] : [])) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: mob ? 2 : 1, mobile: mob });
  await send('Page.navigate', { url: COMPARE + '?v=' + Date.now() }); await sleep(2200);
  const full = await ev(`({w:document.documentElement.scrollWidth,h:document.documentElement.scrollHeight,cards:[...document.querySelectorAll('.card')].map(c=>c.querySelector('.tag').innerText+' | '+c.querySelector('.btn').innerText)})`);
  report[nm] = full;
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: Math.min(full.h, 6000), deviceScaleFactor: mob ? 2 : 1, mobile: mob });
  await sleep(600);
  const s2 = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(path.join(OUT, `${nm}.png`), Buffer.from(s2.result.data, 'base64'));
}
report.steps = N;
report.errors = errors;
fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 1));
console.log(JSON.stringify(report, null, 1));
ws.close(); chrome.kill();
await new Promise(r => { chrome.once('exit', r); setTimeout(r, 3000); });
try { fs.rmSync(prof, { recursive: true, force: true, maxRetries: 5 }); } catch {}
