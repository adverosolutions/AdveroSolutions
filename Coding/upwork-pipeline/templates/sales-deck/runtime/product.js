/* Custom reconciliation app concept. No external services or money movement. */
(function(){
 'use strict';
 const money = n => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n/100);
 function update(root,scene,index){
  const c=scene.content,step=Math.max(0,Math.min(Number(index)||0,2));root.dataset.productStep=String(step);
  root.querySelectorAll('[data-product-ai]').forEach(el=>el.hidden=step<1);
  root.querySelectorAll('[data-product-approved]').forEach(el=>el.hidden=step<2);
  root.querySelector('[data-product-review-state]').textContent=step===2?'Classification approved':step===1?'Suggestion ready':'Open exception';
  root.querySelector('[data-product-classification]').textContent=step===2?c.decision.classification:'Awaiting reviewer';
  const approve=root.querySelector('[data-product-approve]');approve.disabled=step!==1;approve.textContent=step===2?'Classification approved':'Approve classification';
  root.querySelector('[data-product-again]').hidden=step!==2;
  root.querySelector('[data-product-live]').textContent=scene.statuses[step];
  const replayStatus=document.querySelector('#replayStatus');if(replayStatus)replayStatus.textContent=scene.statuses[step];
  root.closest('.demo')?.setAttribute('data-replay-step',String(step));
  {const expanded=step===0;root.querySelector('[data-product-evidence]').hidden=!expanded;const toggle=root.querySelector('[data-product-evidence-toggle]');toggle.setAttribute('aria-expanded',String(expanded));toggle.textContent=expanded?'Hide evidence':'Show evidence';}
 }
 window.ProductScreens={
  cancelReplay:null,
  render(scene){
   const {esc}=window.SalesUI,c=scene.content,t=c.transaction,r=c.reviewer,delta=t.grossMinor-t.expectedMinor;
   return `<section class="native product-app" data-product="${esc(scene.id)}" aria-label="Custom transaction review application"><header class="product-top"><div class="product-brand"><span class="product-mark">R</span><div><strong>${esc(c.name)}</strong><small>Custom application concept</small></div></div><div class="product-identity"><span class="product-role">${esc(r.role)} · ${esc(r.tenant)}</span><span>${esc(r.name)}</span></div></header><div class="product-layout"><aside class="product-queue"><div class="product-queue-title"><strong>Reconciliation</strong><span>1 exception</span></div><p>${esc(c.subtitle)}</p><div class="product-table-head"><span>Transaction</span><span>Difference</span></div><button type="button" class="product-row" data-product-inspect aria-label="Inspect transaction ${esc(t.id)}" aria-pressed="true"><span><b>${esc(t.id)}</b><small>${esc(t.invoice)}</small></span><strong>${esc(money(delta))}</strong></button><div class="product-queue-note"><b>Backend permission scope</b><p>Reviewer access to tenant ${esc(r.tenant)}. Provider state is read-only.</p></div><div class="product-safe"><span>✓</span> No transfer or ledger posting</div></aside><main class="product-detail"><div class="product-detail-head"><div><span class="product-kicker">TRANSACTION EXCEPTION</span><h3>${esc(t.id)}</h3><p>${esc(t.description)}</p></div><span class="product-state" data-product-review-state></span></div><div class="product-amounts"><div><small>Provider · ${esc(t.providerStatus)}</small><b>${esc(money(t.grossMinor))}</b></div><div><small>Invoice · ${esc(t.invoice)}</small><b>${esc(money(t.expectedMinor))}</b></div><div class="product-delta"><small>Unexplained difference</small><b>${esc(money(delta))}</b></div></div><div class="product-evidence-top"><strong>Source evidence</strong><button type="button" data-product-evidence-toggle aria-expanded="true">Hide evidence</button></div><div class="product-evidence" data-product-evidence>${c.evidence.map(e=>`<article><span>${esc(e.id)}</span><b>${esc(e.title)}</b><p>${esc(e.detail)}</p></article>`).join('')}</div><section class="product-ai" data-product-ai hidden><div class="product-ai-top"><span>✧ AI review assistant</span><b>${esc(c.analysis.confidence)}</b></div><p>${esc(c.analysis.summary)}</p><div class="product-recommend"><small>Suggested classification</small><strong>${esc(c.decision.classification)}</strong><p>${esc(c.analysis.recommendation)}</p></div><small class="product-boundary">AI input: ${esc(c.analysis.dataBoundary)}</small></section><div class="product-decision"><div><small>Classification</small><b data-product-classification></b><span>Reconciliation remains open</span></div><div class="product-actions"><button type="button" data-product-again hidden>Review again</button><button type="button" class="product-approve" data-product-approve disabled>Approve classification</button></div></div><section class="product-audit" data-product-approved hidden><span class="product-audit-icon">✓</span><div><b>${esc(c.decision.auditId)} · ${esc(r.name)}</b><p>${esc(c.decision.reason)}</p><small>Local sample approval · provider remains ${esc(t.providerStatus.toLowerCase())} · reconciliation open</small></div></section><div class="product-foot"><span>${esc(t.event)} · duplicate event ignored</span><span role="status" aria-live="polite" data-product-live></span></div></main></div></section>`;
  },
  applyStep(scene,index){
   const root=document.querySelector('[data-product]');if(!root||root.dataset.product!==scene.id)return;
   if(!root.dataset.productBound){
    root.dataset.productBound='true';
    root.addEventListener('click',e=>{
     const button=e.target.closest('button');if(!button||!root.contains(button))return;
     if(button.hasAttribute('data-product-evidence-toggle')){const box=root.querySelector('[data-product-evidence]');box.hidden=!box.hidden;button.setAttribute('aria-expanded',String(!box.hidden));button.textContent=box.hidden?'Show evidence':'Hide evidence';}
     if(button.hasAttribute('data-product-inspect'))root.querySelector('.product-detail-head').scrollIntoView({block:'nearest',behavior:'auto'});
     if(button.hasAttribute('data-product-approve')&&!button.disabled){window.ProductScreens.cancelReplay?.();update(root,scene,2);}
     if(button.hasAttribute('data-product-again')){window.ProductScreens.cancelReplay?.();update(root,scene,1);}
    });
   }
   update(root,scene,index);
  }
 };
})();
