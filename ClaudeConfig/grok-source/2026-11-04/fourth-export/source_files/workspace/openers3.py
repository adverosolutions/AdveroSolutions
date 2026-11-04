import json,re
LINK="https://www.loom"   # section 6 counts through this
old=json.load(open('openers.json'))[:2]
new=[
("1","Quick q \U0001F440 how many leads slipped last month just because nobody got back to them fast? I built the fix for you: [LOOM]","Pointed question, casual 'quick q' pattern interrupt."),
("2","\u201c[their line]\u201d \U0001F448 that line in your post is exactly why I built this for you. 4 min, no fluff: [LOOM]","Quotes their post back at them. NEEDS client post text."),
("3","\U0001F3D7\uFE0F $750M+ in annual bid volume runs through a routing and follow-up system I built. Yours is here: [LOOM]","Bold proof line. FLAG: proposal P.S. fact R, word for word, needs Lorenzo's OK. Under 133 floor."),
("4","\U0001F3A5 [LOOM] \u2190 your system. Already built. 4 min.","Link first, three-word blunt lines. Under 133 floor."),
("5","Watch for the part where nobody on your team has to touch the lead \U0001F440 that's the whole point: [LOOM]","Curiosity hook about the video. Under 133 floor."),
("6","\U0001F525 Hot take: you don't need another proposal to read. You need to see it working. So here, 4 min: [LOOM]","Contrarian, emoji-first interrupt. Under 133 floor."),
("7","My guess? Leads aren't your problem. Day 2, day 3, when nobody follows up... that's the leak \U0001FA79 built that part: [LOOM]","Diagnosis, choppy uneven rhythm."),
("8","Read your post \u2615 started sketching, kept going, and ended up building the whole thing. It's here: [LOOM]","One-sentence mini-story. Under 133 floor."),
("9","ok so I kinda already built it \U0001F605 [LOOM] lmk what you think","Ultra casual lowercase text message. Under 133 floor."),
("10","Hello. Attached below is a 4-minute walkthrough of your completed lead follow-up system, built to the brief in your post. [LOOM]","Crisp formal, no emoji, stands out by contrast."),
]
out=old[:]
for n,t,a in new:
    assert not re.search('[\u2013\u2014!]',t), n
    assert not re.search('streamline|seamless|leverage|elevate',t,re.I)
    c=len(t[:t.index("[LOOM]")])+len(LINK)
    assert c<150,(n,c)
    out.append([n,t,c,a]); print(c,n)
rows=[['#','Variation','Char count','Angle',"Lorenzo's pick"]]+[[r[0],r[1],r[2],r[3],''] for r in out]
rows.append(['','Notes: [LOOM] = the Loom link. Char count runs from the first character through "https://www.loom" (16 chars), the way UPWORK_PROCESS.md section 6 counts; anything after the link is not counted. Python character count (each emoji = 1). Rows 1 to 10 use an example job (lead follow-up system, 4-min video). Drafts only, nothing used until Lorenzo gives the final go.','','',''])
json.dump(rows,open('openers_rows3.json','w'),ensure_ascii=False)
