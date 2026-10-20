/* Presentation-only movement. Native software states and replay logic are untouched. */
(function(){
 'use strict';
 const stage=document.querySelector('#stage');
 const media=matchMedia('(prefers-reduced-motion: reduce)');
 let enabled=true, active=null, generation=0, animations=[], lastScene='';
 const ease='cubic-bezier(.18,.82,.22,1)';
 function cancel(){animations.forEach(a=>a.cancel());animations=[];}
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
 function entrance(){
  cancel();personalize();
  const cover=stage.querySelector('.cover-slide');
  if(cover){
   reveal(cover.querySelector('.motion-client'),0,12,650);
   words(cover.querySelector('h1')).forEach((word,i)=>reveal(word,90+Math.min(i,7)*38,23,740));
   reveal(cover.querySelector('h1 em'),210,20,740);
   reveal(cover.querySelector('.hero-copy>p'),170,12,720);
   reveal(cover.querySelector('.anchors'),240,10,700);
   reveal(cover.querySelector('.cover-cta'),310,10,650);
   animate(cover.querySelector('.cover-preview'),[{opacity:.12,transform:'perspective(1200px) translateX(28px) rotateY(-4deg) scale(.98)'},{opacity:1,transform:'perspective(1200px) translateX(0) rotateY(0) scale(1)'}],880,80);
   cover.querySelectorAll('.journey-item').forEach((item,i)=>{reveal(item,170+i*100,12,680);animate(item.querySelector('.step-icon'),[{transform:'scale(.86)'},{transform:'scale(1)'}],720,200+i*100);});
   reveal(cover.querySelector('.journey-bottom'),400,8,650);
  }else{
   const close=stage.querySelector('.success-slide');
   if(close){reveal(close.querySelector('.success-heading'),0,12,650);close.querySelectorAll('.success-metric').forEach((x,i)=>reveal(x,80+i*80,16,660));reveal(close.querySelector('.baseline-note'),200,8,650);reveal(close.querySelector('.success-cta'),270,16,760);}
   else{reveal(stage.querySelector('.chapterhead'),30,9,550);reveal(stage.querySelector('.demo'),75,15,650);}
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
  const replay=document.createElement('button');replay.type='button';replay.id='motionReplay';replay.className='motion-control';replay.innerHTML='<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 7a6 6 0 1 1-1 5M4 2v5h5"/></svg>Replay entrance';replay.addEventListener('click',entrance);
  const toggle=document.createElement('button');toggle.type='button';toggle.id='motionToggle';toggle.className='motion-control';toggle.title='Toggle presentation effects. Workflow replay remains independent.';toggle.textContent='Motion on';toggle.setAttribute('aria-pressed','true');toggle.addEventListener('click',()=>{enabled=!enabled;document.body.classList.toggle('motion-off',!enabled);toggle.textContent=enabled?'Motion on':'Motion off';toggle.setAttribute('aria-pressed',String(enabled));active?.skipTransition();cancel();if(enabled)entrance();});
  const label=bar.querySelector('label');label.after(replay,toggle);
 }
 new MutationObserver(()=>{const id=stage.dataset.scene;if(id!==lastScene||stage.querySelector('.cover-slide:not([data-motion-ready])')){lastScene=id;const cover=stage.querySelector('.cover-slide');if(cover)cover.dataset.motionReady='true';entrance();}}).observe(stage,{childList:true});
 media.addEventListener('change',()=>{active?.skipTransition();cancel();});
 window.addEventListener('pagehide',()=>{active?.skipTransition();cancel();});
 window.DemoMotion={change,entrance};controls();
})();
