/* Presentation-only movement. Native software states and replay logic are untouched. */
(function(){
 'use strict';
 const stage=document.querySelector('#stage');
 const media=matchMedia('(prefers-reduced-motion: reduce)');
 let enabled=true, active=null, generation=0, animations=[], lastScene='', firstOpening=true;
 const ease='cubic-bezier(.18,.82,.22,1)';
 function cancel(keepIntro=false){if(!keepIntro){document.querySelectorAll('.cin-intro,.cin-curtain').forEach(x=>x.remove());document.querySelector('#app').inert=false;}animations.forEach(a=>a.cancel());animations=[];}
 function animate(el,frames,duration=650,delay=0){
  if(!el||!enabled||media.matches)return;
  const a=el.animate(frames,{duration,delay,easing:ease,fill:'backwards'});animations.push(a);return a;
 }
 function reveal(el,delay=0,distance=18,duration=700){return animate(el,[{opacity:.12,transform:'translateY('+distance+'px)',filter:'blur(2px)'},{opacity:1,transform:'translateY(0)',filter:'blur(0)'}],duration,delay);}
 function words(el){
  if(!el)return [];
  if(!el.querySelector('.motion-word')){
   const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
   nodes.forEach(node=>{if(node.parentElement.closest('em'))return;const fragment=document.createDocumentFragment();node.textContent.split(/(\s+)/).forEach(part=>{if(!part)return;if(/^\s+$/.test(part))fragment.append(document.createTextNode(part));else{const span=document.createElement('span');span.className='motion-word';span.textContent=part;fragment.append(span);}});node.replaceWith(fragment);});
  }
  return [...el.querySelectorAll('.motion-word')];
 }
 function personalize(){
  const copy=stage.querySelector('.cover-slide .hero-copy');if(!copy||copy.querySelector('.motion-client'))return;
  const client=document.createElement('div');client.className='motion-client';
  const mark=document.createElement('div');mark.className='motion-monogram';mark.textContent=window.MotionConfig.initials;
  const text=document.createElement('div');const label=document.createElement('span');label.textContent='Prepared for';const name=document.createElement('strong');name.textContent=window.MotionConfig.company;
  text.append(label,name);client.append(mark,text);copy.prepend(client);
 }
 function escape(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
 function cinematicCover(cover){
  if(cover.classList.contains('cinematic-cover'))return;
  const title=cover.querySelector('h1').childNodes[0].textContent.trim(),accent=cover.querySelector('h1 em').textContent,caption=cover.querySelector('.hero-copy>p').textContent;
  cover.classList.add('cinematic-cover');
  cover.innerHTML='<div class="cin-hero-copy"><div class="motion-client"><div class="motion-monogram">'+escape(MotionConfig.initials)+'</div><div><span>Prepared for</span><strong>'+escape(MotionConfig.company)+'</strong></div></div><h1><span class="cin-headline">'+escape(title)+'</span><em>'+escape(accent)+'</em></h1><p class="cin-caption">'+escape(caption)+'</p><button id="seeWorkflow" class="primary cover-cta">Walk through the system <span>↗</span></button><div class="cin-footnote"><i></i>GoHighLevel · Estimate enquiry follow-up</div></div><div class="cin-system"><div class="cin-system-label"><span>System overview</span><span>Sample enquiry</span></div><div class="cin-orbit cin-orbit-a"><i></i></div><div class="cin-orbit cin-orbit-b"><i></i></div><div class="cin-orbit cin-orbit-c"></div><svg class="cin-route" viewBox="0 0 600 540" aria-hidden="true"><path class="cin-route-base" d="M150 110 C480 110 100 265 385 270 S100 430 310 430"/><path class="cin-route-light" d="M150 110 C480 110 100 265 385 270 S100 430 310 430"/></svg><div class="cin-tile-wrap cin-tile-a"><article class="cin-tile"><span class="cin-tile-number">01</span><div><small>THE ENQUIRY</small><h3>Estimate request received.</h3><p>Avery Morgan · Replacement estimate</p></div><span class="cin-tile-state">↗</span></article></div><div class="cin-tile-wrap cin-tile-b"><article class="cin-tile"><span class="cin-tile-number">02</span><div><small>THE HANDOFF</small><h3>Maya takes ownership.</h3><p>Contacted · $8,450.00</p></div><span class="cin-tile-state">✓</span></article></div><div class="cin-tile-wrap cin-tile-c"><article class="cin-tile"><span class="cin-tile-number">03</span><div><small>THE RESPONSE</small><h3>SMS and email sent.</h3><p>Await visit confirmation</p></div><span class="cin-tile-state">✓</span></article></div></div>';
  cover.querySelector('#seeWorkflow').addEventListener('click',()=>document.querySelector('#next').click());
 }
 function intro(onStart){
  const layer=document.createElement('div');layer.className='cin-intro';layer.setAttribute('role','dialog');layer.setAttribute('aria-modal','true');layer.setAttribute('aria-label','Personalized opening');
  layer.innerHTML='<div class="cin-intro-grid"></div><div class="cin-intro-orb"></div><div class="cin-intro-content"><span class="cin-intro-kicker">PREPARED EXCLUSIVELY FOR</span><strong>'+escape(MotionConfig.company)+'</strong><div class="cin-intro-rule"></div><span class="cin-intro-bottom">YOUR ESTIMATE ENQUIRY FOLLOW-UP</span><button class="cin-start primary">Start presentation <span>↗</span></button></div><span class="cin-intro-index">ADVEROSOLUTIONS / 01</span>';
  document.body.append(layer);document.querySelector('#app').inert=true;
  const start=layer.querySelector('.cin-start');start.focus({preventScroll:true});
  layer.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key))event.stopPropagation();if(event.key==='Tab'){event.preventDefault();start.focus();}});
  animate(layer.querySelector('.cin-intro-kicker'),[{opacity:0,letterSpacing:'.55em',transform:'translateY(20px)'},{opacity:1,letterSpacing:'.22em',transform:'none'}],900,100);
  animate(layer.querySelector('strong'),[{opacity:0,transform:'perspective(1000px) translateY(90px) rotateX(35deg)',filter:'blur(16px)'},{opacity:1,transform:'none',filter:'blur(0)'}],1200,260);
  animate(layer.querySelector('.cin-intro-rule'),[{transform:'scaleX(0)'},{transform:'scaleX(1)'}],1100,500);
  reveal(layer.querySelector('.cin-intro-bottom'),750,18,900);
  start.addEventListener('click',()=>{
   if(layer.dataset.started)return;layer.dataset.started='true';start.disabled=true;
   const finish=()=>{layer.remove();document.querySelector('#app').inert=false;stage.querySelector('#seeWorkflow')?.focus({preventScroll:true});};
   if(!enabled||media.matches){finish();onStart(0);return;}
   const leaving=animate(layer,[{clipPath:'inset(0 0 0 0 round 0px)',transform:'scale(1)',opacity:1},{clipPath:'inset(0 0 100% 0 round 0px)',transform:'scale(1.04)',opacity:1}],1000,0);
   onStart(200);leaving.finished.then(finish).catch(()=>{});
  });
 }
 function playCover(cover,delay=0){
   reveal(cover.querySelector('.motion-client'),delay,45,950);
   animate(cover.querySelector('.cin-headline'),[{opacity:0,transform:'translateY(100px) rotateX(15deg)',filter:'blur(8px)'},{opacity:1,transform:'none',filter:'blur(0)'}],1100,delay+90);
   animate(cover.querySelector('h1 em'),[{opacity:0,transform:'translateY(90px) scale(.9)',filter:'blur(8px)'},{opacity:1,transform:'none',filter:'blur(0)'}],1200,delay+220);
   reveal(cover.querySelector('.cin-caption'),delay+430,30,1000);
   reveal(cover.querySelector('.cover-cta'),delay+570,24,1000);
   reveal(cover.querySelector('.cin-footnote'),delay+700,15,900);
   const system=cover.querySelector('.cin-system'), finalTransform=getComputedStyle(system).transform;
   animate(system,[{opacity:0,transform:'perspective(1200px) rotateY(-22deg) translateX(100px) scale(.82)'},{opacity:1,transform:finalTransform}],1500,delay+150);
   cover.querySelectorAll('.cin-tile').forEach((el,i)=>animate(el,[{opacity:0,transform:'translate3d(70px,100px,-100px) rotateX(35deg) rotateZ(-8deg) scale(.8)',filter:'blur(8px)'},{opacity:1,transform:'none',filter:'blur(0)'}],1250,delay+300+i*240));
 }
 function entrance(force=false){
  cancel();
  const cover=stage.querySelector('.cover-slide');
  if(cover){
   cinematicCover(cover);
   const playIntro=firstOpening||force;firstOpening=false;
   if(playIntro){intro(delay=>playCover(cover,delay));return;}
   playCover(cover,0);
  }else{
   const close=stage.querySelector('.success-slide');
   if(close){reveal(close.querySelector('.success-heading'),0,65,1000);close.querySelectorAll('.success-metric').forEach((x,i)=>reveal(x,150+i*180,80,1100));reveal(close.querySelector('.baseline-note'),200,8,650);reveal(close.querySelector('.success-cta'),520,80,1300);}
   else{reveal(stage.querySelector('.chapterhead'),70,35,800);animate(stage.querySelector('.demo'),[{opacity:.1,transform:'perspective(1600px) translateY(70px) rotateX(7deg) scale(.94)'},{opacity:1,transform:'none'}],1100,130);}
  }
  document.querySelectorAll('.haze i').forEach((el,i)=>animate(el,[{transform:'translate3d(0,0,0)'},{transform:'translate3d('+(i%2?'-':'')+'35px,-20px,0)'},{transform:'translate3d(0,0,0)'}],14000+i*1000));
 }
 function change(update,direction=1){
  const token=++generation;active?.skipTransition();cancel();
  document.documentElement.style.setProperty('--motion-direction',direction);
  if(!enabled||media.matches||!document.startViewTransition){update();return;}
  try{
   const next=document.startViewTransition(()=>{if(token===generation)update();});active=next;
   next.ready.catch(()=>{});
   next.finished.catch(()=>{}).finally(()=>{if(active===next)active=null;});
  }catch(_){if(token===generation)update();}
 }
 function controls(){
  const bar=document.querySelector('.reviewbar');
  const replay=document.createElement('button');replay.type='button';replay.id='motionReplay';replay.className='motion-control';replay.innerHTML='<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 7a6 6 0 1 1-1 5M4 2v5h5"/></svg>Replay opening';replay.addEventListener('click',()=>entrance(true));
  const toggle=document.createElement('button');toggle.type='button';toggle.id='motionToggle';toggle.className='motion-control';toggle.title='Toggle presentation effects. Workflow replay remains independent.';toggle.textContent='Motion on';toggle.setAttribute('aria-pressed','true');toggle.addEventListener('click',()=>{enabled=!enabled;document.body.classList.toggle('motion-off',!enabled);toggle.textContent=enabled?'Motion on':'Motion off';toggle.setAttribute('aria-pressed',String(enabled));active?.skipTransition();cancel();if(enabled)entrance();});
  const label=bar.querySelector('label');label.after(replay,toggle);
 }
 new MutationObserver(()=>{const id=stage.dataset.scene;if(id!==lastScene||stage.querySelector('.cover-slide:not([data-motion-ready])')){lastScene=id;const cover=stage.querySelector('.cover-slide');if(cover)cover.dataset.motionReady='true';entrance();}}).observe(stage,{childList:true});
 media.addEventListener('change',()=>{active?.skipTransition();const intro= document.querySelector('.cin-intro');cancel(Boolean(intro&&!intro.dataset.started));});
 window.addEventListener('pagehide',()=>{active?.skipTransition();cancel();});
 window.DemoMotion={change,entrance};controls();
})();
