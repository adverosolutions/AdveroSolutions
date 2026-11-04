import json,re
LL=59
def cnt(t): return len(t)-t.count('[LOOM]')*6+t.count('[LOOM]')*LL
prev=json.load(open('openers_rows4.json'))
C,CH,R4=prev[1],prev[2],prev[6]
assert R4[0]=='4'
A=[
("“[POST DETAIL]” 👇 [LOOM] [WHAT THE DEMO SHOWS], 4 min",
 "“leads sit in New Lead for days” 👇 [LOOM] that stage texts them back on its own now, 4 min","Quotes their own words back, then the fix."),
("[THEIR STACK]. [LOOM] all [N] talking to each other now",
 "GHL, FB lead forms, a Sheet nobody updates. [LOOM] all 3 talking to each other now","Names their exact tools."),
("you said [THEIR NUMBER]. [LOOM] built around exactly that",
 "you said 40 leads a week and 2 people to answer them. [LOOM] built around exactly that","Repeats a number from their post."),
("\"[POST DETAIL]\" from your post [EMOJI] [LOOM] that's the first thing the video shows",
 "\"nobody texts back after 6pm\" from your post 🌙 [LOOM] that's the first thing the video shows","Picks the one pain line and leads the demo with it."),
("[THEIR STAGES]. those are your stages. [LOOM] watch one lead go through all of them",
 "Quote Sent, Follow Up, Won. those are your stages. [LOOM] watch one lead go through all 3","Uses their pipeline stage names."),
("your [TOOL A] isn't connected to [TOOL B] yet 🔌 [LOOM] it is in this one",
 "your Calendly isn't connected to GHL yet 🔌 [LOOM] it is in this one","The missing connection they described, shown closed."),
("the line about [BURIED REQUIREMENT] near the end of your post. [LOOM] covered",
 "the line about Spanish-speaking leads near the end of your post. [LOOM] covered","The buried requirement others skim past. Only if the build really covers it."),
("[THEIR SITUATION] [EMOJI] [LOOM] [WHAT RUNS WITHOUT THEM]",
 "storm season and one person on the phones ⛈️ [LOOM] follow-up runs with nobody at the desk","Their operating reality, not their tools."),
("[COMPANY]'s [SYSTEM], the way your post laid it out. [LOOM] [START] to [END], 4 min",
 "RestoreNow's intake, the way your post laid it out. [LOOM] form to booked call, 4 min","Company name (only when the post states it) + start-to-end."),
]
B=[
("[LOOM] [T1] [STEP 1] · [T2] [STEP 2] · [T3] [STEP 3]",
 "[LOOM] 0:20 the form · 1:40 the text back · 3:10 the booked call","Timestamp map of the video. Times must match the real Loom."),
("[LOOM] watch the first 60 seconds. if it isn't your system, close it",
 "[LOOM] watch the first 60 seconds. if it isn't your system, close it","Low-commitment dare."),
("before: [THEIR MESS]. after: [LOOM]",
 "before: leads in a Google Sheet and a lot of hoping. after: [LOOM]","Before/after with the link as the 'after'."),
("DFW-based, I set up GHL accounts all the time. yours is the newest one 👉 [LOOM]",
 "DFW-based, I set up GHL accounts all the time. yours is the newest one 👉 [LOOM]","Credentials from confirmed facts (DFW, GHL all the time)."),
("Done. [LOOM]","Done. [LOOM]","One word. Maximum white space in the list."),
("📄 your post ➜ 🛠️ this build ➜ 📅 a booked call [LOOM]",
 "📄 your post ➜ 🛠️ this build ➜ 📅 a booked call [LOOM]","Emoji flow line, reads at a glance."),
("Sound on 🔊 [LOOM] I talk through your post piece by piece, in order",
 "Sound on 🔊 [LOOM] I talk through your post piece by piece, in order","Voice and presence. Only if the Loom is narrated."),
("n8n, Make and GHL are my day job. this one's yours 👉 [LOOM]",
 "n8n, Make and GHL are my day job. this one's yours 👉 [LOOM]","Daily-tools credibility (confirmed: n8n, Make daily; GHL all the time)."),
("[LOOM] hit play first. everything under this line will make more sense after",
 "[LOOM] hit play first. everything under this line will make more sense after","Instruction tone, tells them how to read the proposal."),
]
bad=re.compile(r'quick|game.changer|hope this|I noticed|streamline|seamless|leverage|elevate|[\u2013\u2014!?]',re.I)
rows=[['#','Batch','Template','Example fill','Char count (example)','Angle',"Lorenzo's pick"]]
rows.append(['CONTROL','Reference','Hey there 👋 I do [X] builds all the time, so here\'s your [system] finished and connected, [N]-min video: [LOOM]',C[1],C[2],C[3]+' Section 6 count (through https://www.loom).',''])
rows.append(['CHALLENGER','Reference','Hey there 👋 I read your post closely and turned it into the [desk] your team would use, [N]-min product tour: [LOOM]',CH[1],CH[2],CH[3]+' Section 6 count.',''])
rows.append(['KEEP (round 3 row 4)','Reference',R4[1],R4[1],cnt(R4[1]),'Lorenzo\'s pick to test, unchanged. Link first.',''])
for b,lst in (('A',A),('B',B)):
    for i,(t,e,a) in enumerate(lst,1):
        for s in (t,e): assert not bad.search(s),(b,i,s)
        assert '[LOOM]' in t and '[LOOM]' in e
        c=cnt(e); assert c<150,(b,i,c)
        rows.append([f'{b}{i}', 'A: specificity first' if b=='A' else 'B: other directions', t,e,c,a,'']); print(b,i,c)
rows.append(['','','Notes: [LOOM] counted as a real 59-char Loom share URL. Counts are for the example fill; a real post changes them, so recheck under 150. Batch A = post detail, then link, then one line on the demo. Example job: home services company on GHL with FB lead forms. Slot fills must come from the post or the real build, never invented. Drafts only, nothing used until Lorenzo gives the final go.','','','','',''])
json.dump(rows,open('openers_rows5.json','w'),ensure_ascii=False)
