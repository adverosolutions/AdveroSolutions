'use strict';
const {chromium}=require('playwright');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');
const cinematic=process.argv.includes('--cinematic');const out=path.resolve(__dirname,cinematic?'../.local/cinematic-sales-preview':'../.local/animated-sales-preview');const qa=path.join(out,'qa');fs.mkdirSync(qa,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[],remote=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))remote.push(r.url())});
 await page.goto('file://'+out+'/index.html');await page.evaluate(()=>document.fonts.ready);if(cinematic){await page.waitForTimeout(900);await page.screenshot({path:path.join(qa,'intro.png'),fullPage:true});}await page.waitForTimeout(cinematic?3600:1300);if(cinematic){assert.equal(await page.locator('.cin-intro').count(),1,'Intro holds until presenter starts');await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#stage').getAttribute('data-scene'),'cover','Underlying navigation blocked while intro waits');assert.equal(await page.locator('.cin-duration').inputValue(),'2');await page.locator('.cin-duration').selectOption('3');assert.equal(await page.locator('.cin-intro').count(),1);await page.locator('.cin-duration').selectOption('2');await page.locator('.cin-present').click();await page.waitForTimeout(1400);assert.equal(await page.locator('.cin-intro').count(),1,'Present must hold the intro');assert.equal(await page.locator('.cin-intro-controls').isVisible(),false);assert.equal(await page.locator('#stage').getAttribute('data-scene'),'cover');await page.keyboard.press('Escape');assert.equal(await page.locator('.cin-intro-controls').isVisible(),true);await page.locator('.cin-present').click();await page.keyboard.press('ArrowRight');await page.waitForTimeout(2400);assert.equal(await page.locator('.cin-intro').count(),0);assert.equal(await page.locator('#durationSelect').inputValue(),'2');assert.ok((await page.locator('body').getAttribute('class')).includes('presenting'));await page.keyboard.press('Escape');}
 assert.equal(await page.locator('.motion-client').count(),1);assert.ok((await page.locator('h1').innerText()).includes('Respond to estimate enquiries'));
 assert.equal(await page.locator('h1 em .motion-word').count(),0,'Gradient emphasis is kept on its own painted element');
 assert.ok((await page.locator('h1 em').boundingBox()).height>40);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:path.join(qa,'cover.png'),fullPage:true});
 await page.locator('#seeWorkflow').click();await page.waitForTimeout(900);assert.equal(await page.locator('#stage').getAttribute('data-scene'),'ghl-workflow');
 await page.screenshot({path:path.join(qa,'workflow.png'),fullPage:true});
 await page.locator('#next').click();await page.waitForTimeout(800);assert.equal(await page.locator('#stage').getAttribute('data-scene'),'ghl-messages');
 await page.locator('#replay').click();await page.waitForTimeout(120);await page.locator('#next').click();await page.waitForTimeout(800);
 assert.equal(await page.locator('#stage').getAttribute('data-scene'),'ghl-pipeline');
 await page.waitForTimeout(800);assert.equal(await page.locator('#stage').getAttribute('data-scene'),'ghl-pipeline','Previous replay cannot repaint next chapter');
 await page.locator('#next').click();await page.waitForTimeout(800);await page.screenshot({path:path.join(qa,'close.png'),fullPage:true});
 assert.ok((await page.locator('.success-cta').innerText()).includes('15-minute call'));
 await page.evaluate(()=>{for(let i=0;i<6;i++)document.querySelector('#previous').click()});await page.waitForTimeout(1000);
 assert.equal(await page.locator('#stage').getAttribute('data-scene'),'cover');
 await page.locator('#motionToggle').click();assert.equal(await page.locator('#motionToggle').getAttribute('aria-pressed'),'false');
 await page.locator('#motionReplay').click();if(cinematic){assert.equal(await page.locator('.cin-intro').count(),1);await page.locator('.cin-start').click();}await page.locator('#motionToggle').click();await page.locator('#motionReplay').click();if(cinematic){await page.waitForTimeout(100);assert.equal(await page.locator('.cin-intro').count(),1);await page.locator('.cin-start').click();await page.waitForTimeout(1100);assert.equal(await page.locator('.cin-intro').count(),0);}await page.waitForTimeout(1100);
 assert.equal(await page.locator('.motion-client').count(),1,'Entrance replay cannot duplicate personalization');
 await page.setViewportSize({width:1280,height:800});await page.screenshot({path:path.join(qa,'small-desktop.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 if(cinematic){await page.setViewportSize({width:1024,height:900});await page.locator('#motionReplay').click();await page.locator('.cin-start').click();const jump=await page.locator('.cin-system').evaluate(el=>{const a=el.getAnimations().find(a=>a.effect.getTiming().duration===1500);const t=a.effect.getTiming();a.currentTime=t.delay+t.duration-1;const before=el.getBoundingClientRect().width;a.finish();return Math.abs(before-el.getBoundingClientRect().width)});assert.ok(jump<.5,'Responsive system has no finish-scale jump');await page.waitForTimeout(1100);await page.screenshot({path:path.join(qa,'cover-1024.png'),fullPage:true});}
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(qa,'mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.emulateMedia({reducedMotion:'reduce'});await page.locator('#motionReplay').click();if(cinematic){assert.equal(await page.locator('.cin-intro').count(),1);await page.locator('.cin-start').click();assert.equal(await page.locator('.cin-intro').count(),0);}
 assert.equal(await page.evaluate(()=>document.getAnimations().filter(a=>a.playState==='running').length),0);
 await page.locator('#seeWorkflow').click();assert.equal(await page.locator('#stage').getAttribute('data-scene'),'ghl-workflow');
 assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);await browser.close();
 fs.writeFileSync(path.join(out,'checks.json'),JSON.stringify({pageHash:crypto.createHash('sha256').update(fs.readFileSync(path.join(out,'index.html'))).digest('hex'),checks:['opening/repeated entrance','chapter transitions','no stale replay after navigation','rapid repeated navigation','presentation motion toggle','1440x1000 and1280x800 cover','390px cover containment','reduced motion','no remote requests/page errors',...(cinematic?['held intro with route selector, default two-minute Present, Preview and reduced-motion support','responsive scale handoff']:[]) ],errors,remote},null,2)+'\n');
 console.log('PASS motion preview: transitions, narration entry, replay/navigation, three viewports, reduced motion, no errors/network');
})().catch(e=>{console.error(e);process.exit(1)});
