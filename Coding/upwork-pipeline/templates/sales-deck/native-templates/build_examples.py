#!/usr/bin/env python3
"""Maintain four isolated native-template fixtures, never the recording queue."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from schema import OPENING

def write(p,d):
 tighten_sales(d)
 p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def tighten_sales(d):
 """Each stop adds a new buyer-visible fact; node inspection stays in the workflow."""
 platform=d['scenes'][0]['platform']
 if platform=='n8n':
  d['scenes']=[d['scenes'][0],d['scenes'][1]]
  result=d['scenes'][1];result['optional']=False
  result.update(title='Avery is ready for follow-up.',caption='The returned opportunity contains Avery’s contact, the $8,450 value and an open status.')
 elif platform=='zapier':
  d['scenes'][1]['optional']=False
  d['scenes'][1].update(title='The enquiry is saved in row 42.',caption='Name, email and estimate value are captured together in the enquiry sheet.')
  d['scenes'][2].update(title='The customer gets an answer.',caption='Avery receives the acknowledgement. Maya owns the next step: arranging the visit.')
 elif platform=='claude':
  d['scenes']=[d['scenes'][0],d['scenes'][2]]
  d['scenes'][0].update(title='The checklist becomes a reusable skill.',caption='The instructions require source references and flag missing visit details before dispatch.')
  d['scenes'][1].update(title='A brief with the missing detail flagged.',caption='The draft preserves Thursday at 2 PM and the gate note. The address stays on hold for confirmation.')
 elif platform=='ghl':
  flow=d['scenes'][0]['content']['graph']
  flow['nodes'][2].update(label='Create opportunity in Contacted',detail='Contacted · $8,450.00')
  flow['nodes'].append(dict(id='email',type='email',label='Acknowledge the estimate request',detail='Acknowledgement email sent'))
  flow['edges'].append(dict(**{'from':'sms','to':'email'}));flow['runOrder'].append('email');flow['context']['states'].append('Acknowledgement email sent')
  d['scenes'][0]['content']['inspectors'].append(dict(node='email',input=[dict(label='Contact',value='{{lead.name}}')],output=[dict(label='Email',value='Acknowledgement sent')],parameters=[dict(label='Subject',value='Your replacement estimate request')]))
  d['scenes'][0]['statuses'].append('Acknowledgement email sent')
  d['scenes'][0].update(title='An enquiry gets an owner and a response.',caption='The form starts the workflow: assign Maya, create it in Contacted, then send the SMS and acknowledgement email.')
  conversation=d['scenes'][1];conversation['content']['items']=[conversation['content']['items'][0],conversation['content']['items'][2]]
  conversation['content']['items'][1].update(time='10:02 AM',subject='Your replacement estimate request',body='Hey Avery, I have your replacement estimate request. Maya will contact you to confirm a visit time.')
  conversation['statuses']=['SMS sent; awaiting Avery’s reply','Acknowledgement email delivered']
  conversation.update(title='Both messages are on the contact.',caption='Avery is asked to confirm a visit time. The acknowledgement email is visible alongside the SMS.')
  pipeline=d['scenes'][2];pipeline['content'].update(stages=['New enquiry','Contacted','Visit confirmed','Estimate sent'],stageSequence=[1],fields=[dict(label='Service',value='Replacement estimate'),dict(label='Next step',value='Await visit confirmation')]);pipeline['statuses']=['Created in Contacted · $8,450.00']
  pipeline.update(title='Maya can pick up the enquiry.',caption='Avery is in Contacted with a value of $8,450. Visit confirmation is still the next step.')
 covers={
  'ghl':('Respond to estimate enquiries','inside GoHighLevel.','An enquiry comes in. Someone still has to assign it, create the opportunity and respond.', [('The workflow','Assign Maya, create the opportunity, send SMS and email.'),('The customer response','See both messages in Avery’s conversation.'),('The handoff','Avery appears in Contacted with the next action visible.')]),
  'n8n':('Turn an enquiry into','a GHL opportunity.','An enquiry arrives as a webhook. The team needs a usable CRM record.', [('The workflow','Webhook → Edit Fields → contact → opportunity.'),('The returned record','Avery’s contact ID, open status and $8,450 value.'),('Your account','Confirm the source, pipeline and fields on a short call.')]),
  'zapier':('Save the enquiry.','Send the acknowledgement.','Each new enquiry needs a spreadsheet record and a customer response.', [('The Zap','Catch Hook → Google Sheets → Email by Zapier.'),('The response','Avery receives an email with Maya as the next contact.'),('Your account','Confirm the enquiry source and destination sheet.')]),
  'claude':('Turn visit notes into','a dispatch brief.','Confirmed details arrive in notes. Dispatch still needs a complete, checked brief.', [('The skill','Require the checklist and a source for every visit detail.'),('The result','Read the brief and the missing-address warning.'),('Your process','Agree the source files and review rules on a short call.')])}
 title,accent,problem,steps=covers[platform]
 d['systemName']={'ghl':'Estimate enquiry follow-up','n8n':'Enquiry to GHL opportunity','zapier':'Enquiry capture and acknowledgement','claude':'Visit notes to dispatch brief'}[platform]
 d['cover'].update(title=title,accent=accent,anchors=[problem],previewSteps=[dict(title=a,detail=b) for a,b in steps])
 measures={
 'ghl':[('First response time','down','Respond sooner','Time between form submission and the first delivered response.'),('Assigned enquiries','up','Give each enquiry an owner','Share of new opportunities assigned to the responsible team member.'),('Unanswered enquiries','down','Reduce enquiries without a response','New enquiries without a delivered SMS or email.')],
 'n8n':[('Manual CRM entry','down','Reduce rekeying','Manual contact and opportunity entry steps per enquiry.'),('Complete opportunities','up','Keep the required fields together','Returned opportunities with the expected contact, pipeline and value.'),('Time to CRM','down','Get enquiries into follow-up sooner','Elapsed time from webhook receipt to opportunity creation.')],
 'zapier':[('Manual spreadsheet entry','down','Reduce copying between tools','Manual fields copied for each incoming enquiry.'),('Acknowledged enquiries','up','Respond to each captured enquiry','Captured enquiries with a delivered acknowledgement.'),('Time to acknowledgement','down','Shorten the wait for a response','Elapsed time between receiving the enquiry and sending the email.')],
 'claude':[('Brief preparation time','down','Reduce time drafting briefs','Time spent preparing a visit brief from source notes.'),('Source-backed details','up','Keep facts traceable','Brief fields with references to the supplied notes.'),('Incomplete dispatches','down','Catch missing visit details','Briefs sent to dispatch while required details are missing.')]}
 d['close'].update(eyebrow='Your rollout',title='What we would',accent='measure together.',caption='Use your current process as the starting point.',metrics=[dict(name=a,direction=b,aim=c,definition=e) for a,b,c,e in measures[platform]],ctaTitle='Let’s map this to your account.',ctaCopy='Reply here and I’ll send times for a 15-minute call.')
 cues={
 'ghl-workflow':('The form assigns Maya, creates Avery in Contacted and sends both messages.', ['Point to the form trigger, Maya’s assignment and the Contacted creation step.','Trace the SMS and email actions at the end.']),
 'ghl-messages':('This is the SMS asking Avery about Thursday, followed by the acknowledgement email.', ['Read the visit-time question in the SMS.','The email acknowledges the request; it does not confirm a booking.']),
 'ghl-pipeline':('Here is Avery’s opportunity, assigned to Maya, with confirmation still pending.', ['Point to $8,450, Maya Chen and Await visit confirmation.','This opportunity is created in Contacted; no separate stage movement is claimed.']),
 'n8n-canvas':('The enquiry comes through the webhook; these requests create the contact and opportunity.', ['Trace Webhook, Edit Fields and the two HTTP Request nodes.','Click a node only if the prospect needs to see its sample settings.']),
 'n8n-node':('The returned record has Avery’s contact ID, the estimate value and an open status.', ['Point to contactId sample-avery-1042, monetaryValue 8450 and status open.','The output is a sample response; do not describe it as a live account test.']),
 'zapier-editor':('This Zap catches the enquiry, creates the sheet row and sends the email.', ['Follow Catch Hook to Create Spreadsheet Row to Send Outbound Email.']),
 'zapier-test':('Row 42 keeps Avery’s name, email and estimate value together.', ['Compare name, email and estimate_value with the created row’s fields.','Point to Row 42 and Estimate value 8450 in Data out.']),
 'zapier-email':('Here is the email Avery receives, with Maya arranging the next step.', ['Point to Avery’s recipient address and read the acknowledgement body.','This message leaves the visit time to be confirmed.']),
 'claude-skills':('These instructions require a source for the visit details and flag missing information.', ['Open Contents to inspect the checklist rules if useful.','The skill must not infer a price or a confirmed visit.']),
 'claude-output':('The brief keeps the confirmed time and gate note, and flags the missing address.', ['Point to Thursday at 2 PM and the open side gate, with source filenames.','Show Property address: not provided before moving to the call ask.'])}
 for item in d['scenes']:
  item['beat'],item['details']=cues[item['id']]

def scene(key,platform,surface,title,caption,data,statuses,optional=False):
 return dict(id=key,kind='native',platform=platform,title=title,caption=caption,beat=caption,details=[caption],optional=optional,content=dict(name=data.pop('name',title),subtitle=data.pop('subtitle','Illustrative sample'),surface=surface,**data),statuses=statuses)
def base(platform,title,accent,anchors):
 d=json.loads((ROOT/'examples/financial.json').read_text());d.update(id='native-'+platform,title=platform+' native template review',systemName=title,account=dict(name='Northstar Home Services',initials='NH',operatorInitials='LV'),source=dict(jobUrl='fixture:native-'+platform,facts=['Invented template acceptance fixture; not a saved Upwork job.']),entities=dict(lead=dict(name='Avery Morgan',email='avery.morgan@example.com',phone='+1 (512) 555-0148'),owner=dict(name='Maya Chen'),deal=dict(value='$8,450.00')),scenes=[]);d.pop('personalization',None)
 d['cover'].update(eyebrow='Prepared for Northstar Home Services',title=title,accent=accent,caption=OPENING,anchors=anchors,previewSteps=[dict(title='The setup',detail='The native screen and the exact sample input.'),dict(title='The result',detail='The record, message or document the team receives.'),dict(title='The next step',detail='Agree the account details on a 15-minute call.')],footer='Template review · Illustrative sample',beat=OPENING)
 d['close'].update(title='Measure the result',accent='against your baseline.',caption='Agree the starting point and the target before rollout.',metrics=[dict(name='Manual handling',direction='down',aim='Reduce manual steps',definition='Count the steps a team member completes for each enquiry.'),dict(name='Complete records',direction='up',aim='Capture the required details',definition='Track enquiries with all fields required by the next team member.'),dict(name='Time to useful output',direction='down',aim='Return the result sooner',definition='Measure elapsed time from receiving the input to a usable output.')],baselineNote='Directional goals. These are not measured performance results.',ctaTitle='Worth a quick 15-minute call?',ctaCopy="Reply here and I'll send times.",beat="Reply here and I'll send times for a 15-minute call.")
 return d

def workflow(platform,steps):
 nodes=[dict(id=k,type=t,label=label,detail=detail) for k,t,label,detail in steps]
 g=dict(name='New enquiry follow-up',nodes=nodes,edges=[dict(from_=a['id'],to=b['id']) for a,b in zip(nodes,nodes[1:])],runOrder=[n['id'] for n in nodes],context=dict(name='{{lead.name}}',subtitle='Replacement estimate',fields=[dict(label='Email',value='{{lead.email}}'),dict(label='Opportunity value',value='{{deal.value}}')],states=[x[3] for x in steps]),related=[])
 for ed in g['edges']:ed['from']=ed.pop('from_')
 inp=[dict(label='name',value='{{lead.name}}'),dict(label='email',value='{{lead.email}}')]
 inspectors=[]
 for n in nodes:
  out=copy.deepcopy(inp)+[dict(label='result',value=n['detail'])]
  inspectors.append(dict(node=n['id'],input=copy.deepcopy(inp),output=out,parameters=[dict(label='Operation',value=n['label']),dict(label='Account',value='Northstar Home Services')]))
 return dict(name=g['name'],graph=g,inspectors=inspectors,selectedNode=nodes[-1]['id'])

def main():
 d=base('ghl','Every estimate enquiry,','followed through.',['Native GHL automation','A visible pipeline move','SMS and email in Conversations'])
 g=workflow('ghl',[('capture','facebook_lead','Replacement estimate form','Estimate enquiry received'),('assign','assign_user','Assign Maya Chen','Owner: Maya Chen'),('deal','opportunity','Create replacement estimate','Replacement estimate · $8,450.00'),('sms','sms','Ask for visit confirmation','SMS sent; awaiting Avery’s reply')])
 d['scenes']=[scene('ghl-workflow','ghl','builder','The follow-up lives in GoHighLevel.','Avery submits an estimate enquiry. The workflow assigns Maya, creates the opportunity and asks Avery to confirm the visit.',copy.deepcopy(g),['Enquiry received','Owner assigned','Opportunity created','SMS sent; awaiting Avery’s reply']),scene('ghl-messages','ghl','conversations','The conversation stays with Avery.','The SMS reply and confirmation email appear in the same contact conversation.',dict(name='Conversations',contact='{{lead.name}}',fields=[dict(label='Email',value='{{lead.email}}'),dict(label='Phone',value='{{lead.phone}}'),dict(label='Assigned to',value='{{owner.name}}')],items=[dict(channel='sms',direction='outgoing',sender='Maya Chen',time='10:02 AM',body='Hey Avery, this is Maya at Northstar. I have your replacement estimate request. Does Thursday at 2 PM work for the visit?'),dict(channel='sms',direction='incoming',sender='{{lead.name}}',time='10:04 AM',body='Thursday at 2 works. The side gate will be open.'),dict(channel='email',direction='outgoing',sender='Maya Chen',time='10:05 AM',subject='Your replacement estimate visit',body='Avery, your visit is confirmed for Thursday at 2 PM. Maya has your access note: the side gate will be open.')]),['SMS sent','Avery confirms and adds access note','Confirmation email delivered']),scene('ghl-pipeline','ghl','pipeline','Dispatch sees the confirmed estimate.','Avery moves from New enquiry to Estimate confirmed with the value, owner and access note intact.',dict(name='Replacement estimates',subtitle='Replacement estimate',contact='{{lead.name}}',value='{{deal.value}}',owner='{{owner.name}}',fields=[dict(label='Visit',value='Thursday, 2:00 PM'),dict(label='Access note',value='Side gate will be open')],stages=['New enquiry','Contacted','Estimate confirmed','Estimate sent'],stageSequence=[0,1,2]),['New enquiry','Contacted','Estimate confirmed · $8,450.00'])]
 write(ROOT/'native-templates/ghl.json',d)
 d=base('n8n','From enquiry payload','to a clean handoff.',['Native node inspection','Mapped input and output','A useful execution result'])
 g=workflow('n8n',[('capture','webhook','Receive enquiry','POST /replacement-estimate'),('normalize','edit_fields','Normalize enquiry fields','service_type = replacement estimate'),('create','http_request','Create GHL contact','contact_id = sample-avery-1042'),('notify','http_request','Create GHL opportunity','opportunity_id = sample-opp-2841')])
 payload=dict(name='Avery Morgan',email='avery.morgan@example.com',service_type='replacement estimate',monetaryValue=8450)
 contact=dict(id='sample-avery-1042',name='Avery Morgan',email='avery.morgan@example.com')
 normal=[dict(label=k,value=str(v)) for k,v in payload.items()]
 contact_input=[dict(label='contact',value=json.dumps(contact))]
 request=dict(locationId='sample-location-northstar',pipelineId='sample-estimate-pipeline',pipelineStageId='sample-new-enquiry',contactId='sample-avery-1042',name='Avery Morgan - Replacement estimate',status='open',monetaryValue=8450)
 g['inspectors'][0]=dict(node='capture',input=[dict(label='body',value=json.dumps(payload))],output=[dict(label='body',value=json.dumps(payload))],parameters=[dict(label='HTTP Method',value='POST'),dict(label='Path',value='replacement-estimate'),dict(label='Authentication',value='None'),dict(label='Respond',value='Immediately')])
 g['inspectors'][1]=dict(node='normalize',input=[dict(label='body',value=json.dumps(payload))],output=normal,parameters=normal)
 g['inspectors'][2]=dict(node='create',input=normal,output=contact_input,parameters=[dict(label='Method',value='POST'),dict(label='URL',value='https://services.leadconnectorhq.com/contacts/'),dict(label='JSON',value=json.dumps(dict(locationId='sample-location-northstar',name=payload['name'],email=payload['email']))),dict(label='Authentication',value='Generic Credential Type'),dict(label='Generic Auth Type',value='Header Auth'),dict(label='Header Auth',value='HighLevel API (sample)')])
 g['inspectors'][3]=dict(node='notify',input=contact_input,parameters=[dict(label='Method',value='POST'),dict(label='URL',value='https://services.leadconnectorhq.com/opportunities/'),dict(label='JSON',value=json.dumps(request,separators=(',',':'))),dict(label='Authentication',value='Generic Credential Type'),dict(label='Generic Auth Type',value='Header Auth'),dict(label='Header Auth',value='HighLevel API (sample)')],output=[dict(label='id',value='sample-opp-2841'),dict(label='contactId',value='sample-avery-1042'),dict(label='name',value='Avery Morgan - Replacement estimate'),dict(label='monetaryValue',value='8450'),dict(label='status',value='open')])
 d['scenes']=[scene('n8n-canvas','n8n','editor','The complete handoff in n8n.','The webhook receives Avery, Edit Fields normalizes the enquiry, and HTTP Request creates the GHL contact and opportunity.',copy.deepcopy(g),['Webhook received Avery','Fields normalized','Contact created','Opportunity created']),scene('n8n-node','n8n','node','Inspect the data at the handoff.','The request and returned opportunity share the same contact ID and $8,450 sample value.',copy.deepcopy(g),['Webhook sample','Normalized sample','Contact sample','Opportunity output visible'],True),scene('n8n-execution','n8n','execution','A usable result for the team.','The execution returns sample-opp-2841 for Avery Morgan. The opportunity is open with a value of 8450.',dict(copy.deepcopy(g),execution=dict(id='1042',started='Today, 10:02:00',duration='1.8s')),['Input received','Mapping complete','Contact returned','Opportunity returned'])]
 write(ROOT/'native-templates/n8n.json',d)
 d=base('zapier','Each new enquiry,','logged and acknowledged.',['Visual Zap editor','Real Zapier action names','Mapped test output'])
 g=workflow('zapier',[('capture','webhook','Catch Hook','Avery enquiry received'),('row','sheets','Create Spreadsheet Row','row = 42 - Avery Morgan'),('email','email','Send Outbound Email','Acknowledgement sent to avery.morgan@example.com')])
 incoming=[dict(label='name',value='{{lead.name}}'),dict(label='email',value='{{lead.email}}'),dict(label='estimate_value',value='8450')]
 acknowledgement=[dict(label='To',value='{{lead.email}}'),dict(label='Subject',value='Your replacement estimate request'),dict(label='Body',value='Hey Avery, I have your replacement estimate request. Maya will contact you to confirm a visit time.')]
 g['inspectors'][0]=dict(node='capture',input=incoming,parameters=[dict(label='Webhook',value='Northstar estimate enquiry')],output=incoming)
 g['inspectors'][1]=dict(node='row',input=incoming,parameters=[dict(label='Spreadsheet',value='Northstar enquiries'),dict(label='Worksheet',value='Replacement estimates')]+incoming,output=[dict(label='Row',value='42'),dict(label='Name',value='{{lead.name}}'),dict(label='Email',value='{{lead.email}}'),dict(label='Estimate value',value='8450')])
 g['inspectors'][2]=dict(node='email',input=acknowledgement,parameters=acknowledgement,output=[dict(label='Message ID',value='sample-email-1042'),dict(label='Status',value='Sent (illustrative sample)')]);g['selectedNode']='row'
 email_graph=copy.deepcopy(g);email_graph['selectedNode']='email'
 d['scenes']=[scene('zapier-editor','zapier','editor','The enquiry becomes a row and an email.','Catch Hook receives the enquiry. Google Sheets records it, then Email by Zapier sends the acknowledgement.',copy.deepcopy(g),['Hook sample received','Spreadsheet row 42 created','Acknowledgement sample ready']),scene('zapier-test','zapier','test','Trace the estimate value into row 42.','The input and created row both contain Avery, the email address and the $8,450 estimate value.',copy.deepcopy(g),['Hook sample','Row sample','Output ready to inspect']),scene('zapier-email','zapier','test','Avery gets the acknowledgement.','The email goes to Avery with the estimate request acknowledged. It does not claim the visit is confirmed.',email_graph,['Hook sample','Row sample','Acknowledgement sample sent'])]
 write(ROOT/'native-templates/zapier.json',d)
 d=base('claude','From service notes','to a reviewed brief.',['Claude app Skills','Project context','A readable draft with source references'])
 d['account']['name']='Northstar operations'
 skills=[dict(name='estimate-visit-brief',description='Prepare a dispatch brief from confirmed estimate notes. Preserve contact details, visit time and source references.',instructions='Read the supplied visit notes. Extract the customer, appointment and access instructions. Cite the source file next to each fact. If a required fact is absent, list it as missing. Do not infer prices or mark the visit confirmed without an explicit confirmation.')]
 files=[dict(name='avery-visit-notes.txt',detail='Customer reply and estimate details'),dict(name='dispatch-checklist.md',detail='Required visit fields and review steps')]
 d['scenes']=[scene('claude-skills','claude','skills','A reusable skill for the visit brief.','The skill preserves the customer details and flags missing information. Open it to inspect the instructions.',dict(name='Customize',skills=skills),['Skill available','Skill instructions ready']),scene('claude-project','claude','project','Keep the source material in the project.','The project contains Avery’s visit notes and the dispatch checklist.',dict(name='Replacement estimate briefs',subtitle='Prepare dispatch briefs from customer confirmations.',instructions='Use the visit notes and dispatch checklist.',files=files),['Source context visible','Project context ready'],True),scene('claude-output','claude','chat','The team gets a brief it can use.','The brief includes Avery’s confirmed time, the gate note and the missing property address. It is ready for a person to review.',dict(name='Avery’s replacement estimate brief',prompt='Prepare the dispatch brief for Avery from the attached notes. Use the checklist and flag anything missing.',response='I prepared the visit brief from the supplied notes. The time and access instructions are cited. The property address is missing, so I left it for confirmation.',files=files,exception='The source does not contain a property address. Ask Avery for it before dispatching the visit.',document=dict(title='Avery Morgan · Visit brief',sections=[dict(title='Customer and visit',body='Avery Morgan\navery.morgan@example.com\nThursday at 2:00 PM, explicitly confirmed by Avery.\nSource: avery-visit-notes.txt, customer reply.'),dict(title='Access instructions',body='The side gate will be open.\nSource: avery-visit-notes.txt, customer reply.'),dict(title='Required before dispatch',body='Property address: not provided.\nAsk Avery for the address and confirm the service area.\nSource: dispatch-checklist.md, required visit fields.')])) ,['Source notes received','Draft brief visible','Missing address flagged'])]
 write(ROOT/'native-templates/claude.json',d)
 print('Wrote four native-template fixtures')
if __name__=='__main__':main()
