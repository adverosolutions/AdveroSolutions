/* Explicitly custom system architecture; never depicts a vendor editor. */
(function(){
 'use strict';
 window.ArchitectureScreens={
  render(scene,job){
   const {esc,fields}=window.SalesUI,c=scene.content;
   return `<div class="native custom-architecture" data-architecture="${esc(scene.id)}"><header class="architecture-top"><div><small>CUSTOM SYSTEM OVERVIEW</small><h3>${esc(c.name)}</h3><p>${esc(c.subtitle)}</p></div><span class="badge gray">Illustrative sample</span></header><div class="architecture-body"><div class="architecture-path" data-node-count="${c.nodes.length}">${c.nodes.map((n,i)=>`<article class="architecture-node" data-architecture-node="${esc(n.id)}"><span class="architecture-number">${String(i+1).padStart(2,'0')}</span><h4>${esc(n.label)}</h4><p>${esc(n.detail)}</p><div class="architecture-links">${c.edges.filter(e=>e.from===n.id).map(e=>`<span>→ ${esc(e.label||c.nodes.find(n=>n.id===e.to).label)}</span>`).join('')}</div></article>`).join('')}</div><aside class="architecture-context"><span class="eyebrow">Sample moving through the system</span><h3>${esc(c.context.name)}</h3><p>${esc(c.context.subtitle)}</p>${fields(c.context.fields)}<div class="architecture-state" role="status"></div>${c.related.map(r=>`<div class="architecture-related"><b>${esc(r.title)}</b><small>${esc(r.detail)}</small></div>`).join('')}</aside></div></div>`;
  },
  applyStep(scene,index){
   const root=document.querySelector('[data-architecture]');if(!root||root.dataset.architecture!==scene.id)return;
   const c=scene.content,step=Math.max(0,Math.min(index,c.runOrder.length-1)),visited=c.runOrder.slice(0,step+1);
   root.querySelectorAll('[data-architecture-node]').forEach(el=>{el.classList.toggle('done',visited.includes(el.dataset.architectureNode));el.classList.toggle('current',el.dataset.architectureNode===c.runOrder[step]);});
   root.querySelector('.architecture-state').textContent=c.context.states[step];
  }
 };
})();
