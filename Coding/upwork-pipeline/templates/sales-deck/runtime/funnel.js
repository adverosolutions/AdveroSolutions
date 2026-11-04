/* Public funnel preview with a Neo calendar interior; local sample interaction only. */
(function(){
 'use strict';
 const scenes = new Map();
 const journeys = new Map();
 const copy = x => JSON.parse(JSON.stringify(x));
 const esc = x => window.SalesUI.esc(x);
 const icon = key => {const paths={clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',location:'<path d="M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z"/>'};return '<svg class="funnel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths[key]+'</svg>';};
 const dayDate = b => new Date(b.dateISO+'T12:00:00Z');
 const dateText = b => dayDate(b).toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric',timeZone:'UTC'});
 const timeText = s => { const [h,m]=s.split(':').map(Number);return `${h%12||12}:${String(m).padStart(2,'0')} ${h>=12?'PM':'AM'}`; };
 const summary = b => `${dateText(b)} at ${timeText(b.selectedSlot)} ${b.timezoneLabel}`;
 function rootOf(id){return [...document.querySelectorAll('[data-funnel]')].find(x=>x.dataset.funnel===id);}
 function bookingSummary(b){return `<div class="funnel-calendar-meta"><div>${icon('clock')}<b>${b.durationMinutes} min</b></div><div>${icon('calendar')}<b>${esc(summary(b))}</b></div><div>${icon('location')}<b>${esc(b.location)}</b></div><div>${icon('globe')}<b>${esc(b.timezone)} (${esc(b.timezoneLabel)})</b></div></div>`;}
 function landing(c,b){
  return `<div class="funnel-public-head"><strong>${esc(c.brand)}</strong><span>Appointments</span></div><div class="funnel-landing-grid"><div class="funnel-landing-copy"><span class="funnel-kicker">BOOK AN APPOINTMENT</span><h2>${esc(c.heading)}</h2><p>${esc(c.body)}</p><div class="funnel-facts"><span>${esc(b.service)}</span><span>${b.durationMinutes} minutes</span></div><button class="funnel-primary" data-funnel-action="book">${esc(c.cta)} <span aria-hidden="true">→</span></button><small>Choose an available time on the next page.</small></div><div class="funnel-offer-panel"><div class="funnel-offer-label">Your appointment</div><h3>${esc(b.service)}</h3><p>${esc(b.location)}</p><div class="funnel-process"><b>01</b><span>Choose your appointment</span><b>02</b><span>Select a time</span><b>03</b><span>Get your confirmation</span></div>${c.choices?`<label class="funnel-choice-label">Location and service<select data-funnel-choice>${c.choices.map((v,i)=>`<option value="${i}" ${v.location===b.location&&v.service===b.service?'selected':''}>${esc(v.location)} · ${esc(v.service)} · ${v.durationMinutes} min</option>`).join('')}</select></label>`:''}</div></div>`;
 }
 function monthGrid(b){
  const d=dayDate(b),year=d.getUTCFullYear(),month=d.getUTCMonth(),count=new Date(Date.UTC(year,month+1,0)).getUTCDate();
  const offset=(new Date(Date.UTC(year,month,1)).getUTCDay()+6)%7,selected=d.getUTCDate();
  return `<div class="funnel-month-header"><b>${d.toLocaleDateString('en-US',{month:'long',year:'numeric',timeZone:'UTC'})}</b><div><button disabled aria-label="Previous month">‹</button><button disabled aria-label="Next month">›</button></div></div><div class="funnel-month-grid">${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(s=>`<span class="funnel-weekday">${s}</span>`).join('')}${Array.from({length:offset},()=>'<span></span>').join('')}${Array.from({length:count},(_,i)=>`<button ${i+1===selected?'class="selected" aria-pressed="true" data-funnel-action="date"':'disabled'} aria-label="${year}-${String(month+1).padStart(2,'0')}-${String(i+1).padStart(2,'0')}">${i+1}</button>`).join('')}</div>`;
 }
 function widget(c,b,form){
  const names=b.contact.name.trim().split(/\s+/),first=names.shift()||'',last=names.join(' ');
  return `<div class="funnel-widget"><aside class="funnel-calendar-left">${form?'<button type="button" class="funnel-form-back" data-funnel-action="back" aria-label="Back to available times">←</button>':''}<p>${esc(c.brand)}</p><h3>${esc(b.service)}</h3>${!form?`<div class="funnel-staff"><label>Select a staff member<select data-funnel-staff>${b.staffOptions.map(n=>`<option ${n===b.staff?'selected':''}>${esc(n)}</option>`).join('')}</select></label></div>`:''}${bookingSummary(b)}</aside><div class="funnel-calendar-right">${form?`<form class="funnel-details-form"><h3>Enter details</h3><div class="funnel-form-grid"><label>First name *<input name="firstName" autocomplete="off" required value="${esc(first)}"></label><label>Last name *<input name="lastName" autocomplete="off" required value="${esc(last)}"></label><label>Phone *<input name="phone" autocomplete="off" type="tel" required value="${esc(b.contact.phone)}"></label><label>Email *<input name="email" autocomplete="off" type="email" required value="${esc(b.contact.email)}"></label></div><label class="funnel-additional">Additional information<textarea name="additional" placeholder="Is there anything you would like us to know before your appointment?"></textarea></label><label class="funnel-consent"><input type="checkbox" name="sms" ${b.smsConsent?'checked':''}> I agree to receive appointment texts. Reply STOP to opt out.</label><div class="funnel-form-submit"><button type="submit" class="funnel-primary">Schedule meeting</button></div></form>`:`<h3>Select Date &amp; Time</h3><div class="funnel-date-slots"><div>${monthGrid(b)}<div class="funnel-timezone"><span>Time zone</span><div>${icon('globe')} ${esc(b.timezone)} (${esc(b.timezoneLabel)})</div></div></div><div class="funnel-slots">${b.slots.map(t=>`<div class="funnel-slot-row ${t===b.selectedSlot?'selected':''}"><button data-funnel-slot="${esc(t)}" class="${t===b.selectedSlot?'selected':''}" aria-pressed="${t===b.selectedSlot}">${timeText(t)}</button>${t===b.selectedSlot?'<button class="funnel-select-slot" data-funnel-action="continue">Select</button>':''}</div>`).join('')}</div></div>`}</div></div>`;
 }
 function confirmation(c,b){
  return `<div class="funnel-public-head"><strong>${esc(c.brand)}</strong><span>Appointment confirmation</span></div><div class="funnel-confirm"><div class="funnel-check" aria-hidden="true">✓</div><span class="funnel-kicker">APPOINTMENT CONFIRMED</span><h2>You're booked, ${esc(b.contact.name.split(' ')[0])}.</h2><p>${esc(c.surface==='confirmation'?c.body:'Your appointment details are below.')}</p><div class="funnel-confirm-card"><h3>${esc(b.service)}</h3><dl><dt>When</dt><dd>${esc(summary(b))}</dd><dt>Duration</dt><dd>${b.durationMinutes} minutes</dd><dt>Location</dt><dd>${esc(b.location)}</dd><dt>With</dt><dd>${esc(b.staff)}</dd><dt>Appointment email</dt><dd>${esc(b.contact.email)}</dd><dt>SMS reminders</dt><dd>${b.smsConsent?'Consent recorded in this sample':'Held, SMS consent not given'}</dd></dl></div><small>Keep these details for your appointment.</small></div>`;
 }
 function draw(root,state){
  const c=state.scene.content,b=state.booking;
  root.dataset.funnelSurface=state.surface;
  root.innerHTML=state.surface==='landing'?landing(c,b):state.surface==='confirmation'?confirmation(c,b):widget(c,b,state.form);
 }
 document.addEventListener('click',function(event){
  const button=event.target.closest('[data-funnel-action],[data-funnel-slot]');if(!button)return;
  const root=button.closest('[data-funnel]'),state=root&&scenes.get(root.dataset.funnel);if(!state)return;
  if(button.dataset.funnelSlot){state.booking.selectedSlot=button.dataset.funnelSlot;draw(root,state);return;}
  const action=button.dataset.funnelAction;
  if(action==='book'){state.surface='booking';state.form=false;}
  if(action==='continue')state.form=true;
  if(action==='back')state.form=false;
  if(action==='date')return;
  draw(root,state);
 });
 document.addEventListener('change',function(event){
  const root=event.target.closest('[data-funnel]'),state=root&&scenes.get(root.dataset.funnel);if(!state)return;
  if(event.target.matches('input[name=sms]'))state.booking.smsConsent=event.target.checked;
  if(event.target.matches('[data-funnel-choice]')){const v=state.scene.content.choices[Number(event.target.value)];Object.assign(state.booking,copy(v));state.booking.selectedSlot=v.slots[0];draw(root,state);}
  if(event.target.matches('[data-funnel-staff]')){state.booking.staff=event.target.value;draw(root,state);}
 });
 document.addEventListener('input',function(event){
  if(!event.target.matches('.funnel-details-form input[name=firstName],.funnel-details-form input[name=lastName],.funnel-details-form input[name=email],.funnel-details-form input[name=phone]'))return;
  const root=event.target.closest('[data-funnel]'),state=root&&scenes.get(root.dataset.funnel);if(state){if(event.target.name==='firstName'||event.target.name==='lastName'){const form=event.target.form;state.booking.contact.name=[form.elements.firstName.value,form.elements.lastName.value].filter(Boolean).join(' ');}else state.booking.contact[event.target.name]=event.target.value;}
 });
 document.addEventListener('submit',function(event){
  const form=event.target.closest('.funnel-details-form');if(!form)return;event.preventDefault();
  const root=form.closest('[data-funnel]'),state=scenes.get(root.dataset.funnel);if(!state||state.submitted||!form.checkValidity())return;
  const values=new FormData(form);state.booking.smsConsent=form.elements.sms.checked;state.booking.contact={name:[values.get('firstName'),values.get('lastName')].filter(Boolean).join(' '),email:String(values.get('email')),phone:String(values.get('phone'))};state.submitted=true;state.surface='confirmation';draw(root,state);
 });
 window.FunnelScreens={
  render(scene,job){
   const journeyKey=job.id||scene.id;
   if(!journeys.has(journeyKey))journeys.set(journeyKey,copy(scene.content.booking));
   const state={scene,journeyKey,booking:journeys.get(journeyKey),surface:scene.content.surface,form:false,submitted:false};scenes.set(scene.id,state);
   const body=state.surface==='landing'?landing(scene.content,state.booking):state.surface==='confirmation'?confirmation(scene.content,state.booking):widget(scene.content,state.booking,false);
   return `<div class="native funnel-public" data-funnel="${esc(scene.id)}" data-funnel-surface="${esc(state.surface)}">${body}</div>`;
  },
  applyStep(scene,index){
   const root=rootOf(scene.id),state=scenes.get(scene.id);if(!root||!state)return;
   if(index<=0){Object.keys(state.booking).forEach(k=>delete state.booking[k]);Object.assign(state.booking,copy(scene.content.booking));state.surface=scene.content.surface;state.form=false;state.submitted=false;}
   // A settled booking screen is the selected slot, never a fabricated service response.
   draw(root,state);
  }
 };
})();
