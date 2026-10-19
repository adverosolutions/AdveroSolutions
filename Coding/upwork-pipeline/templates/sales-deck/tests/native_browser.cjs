'use strict';
const {chromium}=require('playwright');const crypto=require('node:crypto');
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const root=path.resolve(__dirname,'..');const out=path.resolve(root,'../../.local/native-template-review');const qa=path.join(root,'native-templates/qa');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});const results=[];const errors=[];
for(const product of ['ghl','n8n','zapier','claude']){
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(product+': '+e.message));let requests=[];page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});await page.clock.install();await page.goto('file://'+out+'/'+product+'/page.html');await page.evaluate(()=>document.fonts.ready);
 for(const route of ['1','2','3']){
  await page.locator('#durationSelect').selectOption(route);const chapters=await page.locator('[data-chapter]').count();
  for(let i=1;i<chapters-1;i++){
   await page.locator('[data-chapter="'+i+'"]').click();const id=await page.locator('#stage').getAttribute('data-scene');const scene=JSON.parse(fs.readFileSync(path.join(root,'native-templates/'+product+'.json'))).scenes.find(s=>s.id===id);
   assert.equal(await page.locator('.ns-frame').getAttribute('data-step'),String(scene.statuses.length-1),'Entry is immediately settled '+id);
   assert.ok((await page.locator('.ns-render').innerText()).length>60,'Useful screen '+id);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Desktop overflow '+id);
   await page.locator('#replay').click();await page.locator('#replay').click();assert.equal(await page.locator('.ns-frame').getAttribute('data-step'),'0');await page.clock.fastForward(5000);assert.equal(await page.locator('.ns-frame').getAttribute('data-step'),String(scene.statuses.length-1));
   await page.locator('#replay').click();await page.locator('#showResult').click();await page.clock.fastForward(5000);assert.equal(await page.locator('.ns-frame').getAttribute('data-step'),String(scene.statuses.length-1));
   if(route==='3'){await page.screenshot({path:path.join(qa,id+'-desktop.png'),fullPage:true,animations:'disabled'});await page.locator('.ns-frame').screenshot({path:path.join(qa,id+'-native.png'),animations:'disabled'});}
  }
 }
 // Stale timers cannot repaint a later chapter.
 await page.locator('[data-chapter="1"]').click();await page.locator('#replay').click();await page.locator('#next').click();const after=await page.locator('#stage').getAttribute('data-scene');const finalHTML=await page.locator('.ns-render').innerHTML();await page.clock.fastForward(6000);assert.equal(await page.locator('#stage').getAttribute('data-scene'),after);assert.equal(await page.locator('.ns-render').innerHTML(),finalHTML);
 if(product==='ghl'){
  await page.locator('[data-chapter="3"]').click();assert.equal(await page.locator('[data-sample-card]').count(),1);assert.ok((await page.locator('[data-sample-card]').innerText()).includes('$8,450.00'));await page.locator('#replay').click();assert.ok((await page.locator('.ns-column').first().innerText()).includes('Avery Morgan'));await page.clock.fastForward(5000);assert.ok((await page.locator('.ns-column').nth(2).innerText()).includes('Avery Morgan'));
  await page.locator('[data-chapter="2"]').click();assert.equal(await page.locator('.ns-message').count(),3);assert.ok((await page.locator('.ns-message.email').innerText()).includes('side gate'));
 }
 if(product==='n8n'){
  await page.locator('[data-chapter="2"]').click();
  const body=page.locator('.ns-parameters textarea');assert.ok((await body.inputValue()).includes('sample-avery-1042'));assert.ok((await body.inputValue()).includes('8450'));
  await page.locator('[data-ns-pane-key="output"][data-ns-data-view="table"]').click();assert.equal(await page.locator('.ns-data-table').count(),1);await page.locator('[data-ns-pane-key="output"][data-ns-data-view="json"]').click();assert.ok((await page.locator('[data-ns-pane="output"] .ns-json').innerText()).includes('sample-opp-2841'));
 }
 if(product==='zapier'){
  await page.locator('[data-chapter="3"]').click();assert.ok((await page.locator('.ns-inspector').innerText()).includes('Maya will contact you'));assert.ok((await page.locator('.ns-inspector').innerText()).includes('avery.morgan@example.com'));
 }
 if(product==='n8n'||product==='zapier'){
  await page.locator('[data-chapter="1"]').click();const node=product==='n8n'?'create':'row';await page.locator('[data-ns-node="'+node+'"]').click();assert.equal(await page.locator('.ns-inspector').isVisible(),true);await page.locator('[data-ns-close]').click();assert.equal(await page.locator('.ns-inspector').isVisible(),false);
 }
 if(product==='claude'){
  await page.locator('[data-chapter="1"]').click();await page.locator('[data-ns-skill-tab="contents"]').click();assert.ok((await page.locator('.ns-skill-contents').innerText()).includes('SKILL.md'));const sw=page.locator('[data-ns-toggle]');await sw.click();assert.equal(await sw.getAttribute('aria-checked'),'false');await sw.click();assert.equal(await sw.getAttribute('aria-checked'),'true');await page.screenshot({path:path.join(qa,'claude-skill-contents-desktop.png'),fullPage:true,animations:'disabled'});await page.locator('[data-ns-skills-back]').click();assert.equal(await page.locator('[data-ns-toggle]').count(),0,'No invented list toggles');await page.screenshot({path:path.join(qa,'claude-skill-list-desktop.png'),fullPage:true,animations:'disabled'});await page.locator('[data-chapter="2"]').click();const bounds=await page.locator('.ns-frame').boundingBox();for(const file of await page.locator('.ns-project-context .ns-file').all()){const box=await file.boundingBox();assert.ok(box.y+box.height<=bounds.y+bounds.height,'Both project source cards fit entry viewport');}
 }
 await page.setViewportSize({width:390,height:844});const chapters=await page.locator('[data-chapter]').count();for(let i=1;i<chapters-1;i++){await page.locator('[data-chapter="'+i+'"]').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Mobile page overflow');if(i===1&&product==='ghl'){assert.equal(await page.locator('.ns-push').isVisible(),false,'Mobile publish toolbar hidden');const boxes=await page.locator('.ns-builder-tabs>span:not(.ns-push)').evaluateAll(xs=>xs.map(x=>{const r=x.getBoundingClientRect();return {left:r.left,right:r.right}}));for(let j=1;j<boxes.length;j++)assert.ok(boxes[j].left>=boxes[j-1].right,'No mobile header label intersection');}if(i===1)await page.screenshot({path:path.join(qa,product+'-mobile.png'),fullPage:true,animations:'disabled'});}
 await page.emulateMedia({reducedMotion:'reduce'});await page.locator('[data-chapter="1"]').click();await page.locator('#replay').click();const first=JSON.parse(fs.readFileSync(path.join(root,'native-templates/'+product+'.json'))).scenes[0];assert.equal(await page.locator('.ns-frame').getAttribute('data-step'),String(first.statuses.length-1));
 assert.deepEqual(requests,[],'No external runtime calls');results.push({product,routes:3,entrySettled:true,rapidReplay:true,showResult:true,staleTimersCancelled:true,reducedMotion:true,noPageOverflow:true,noNetwork:true});await page.close();
}
assert.deepEqual(errors,[]);fs.writeFileSync(path.join(qa,'browser-checks.json'),JSON.stringify({checkedAt:'2026-10-19',pageHashes:Object.fromEntries(['ghl','n8n','zapier','claude'].map(p=>[p,crypto.createHash('sha256').update(fs.readFileSync(path.join(out,p,'page.html'))).digest('hex')])),viewport:{width:1440,height:1000},mobile:{width:390,height:844},products:results,errors},null,2)+'\n');await browser.close();console.log('PASS four native fixtures, three routes, replay/navigation/data/native controls/mobile/reduced-motion/no-network checks');})().catch(e=>{console.error(e);process.exit(1);});
