import json,re
L=" https://www.loom.com/share/[LOOMURL]"
old=json.load(open('openers.json'))[:2]
new=[
("1","Still chasing leads by hand after they fill out your form? I built the follow-up that does it for you. Watch it run:","Pointed question about their problem."),
("2","Your post says leads go quiet after the first call. That's a follow-up gap, and this build already closes it. 4-min video:","Direct observation quoting their post (swap in their real line)."),
("3","$750M+ in annual bid volume runs through a routing and follow-up system I built. Here's the version I made for you:","Bold one-line result. FLAG: proposal P.S. fact (bullet R), word for word, needs Lorenzo's OK outside the P.S."),
("4","Built it. Four minutes, start to finish:","Short and blunt. Deliberately well under the 133 floor."),
("5","Watch what happens when a new lead comes in and nobody on your team lifts a finger. Your system, 4-min video:","Curiosity hook: you'll see it in the video."),
("6","Most freelancers will send you a pitch. I'd rather show you the finished thing. Your lead follow-up, running, 4-min video:","Contrarian take against the rest of the proposals."),
("7","My guess: the leads aren't the problem, the follow-up after day one is. So that's what I built. 4-min video:","Quick diagnosis of their likely bottleneck."),
("8","Read your post, sketched it out, and ended up building the whole thing. Here it is running, 4 minutes:","One-sentence mini-story."),
("9","ok so I kind of went ahead and built your lead follow-up already \U0001F605 4-min video, take a look:","Ultra casual, lowercase, texting tone."),
("10","Hello. Below is a 4-minute walkthrough of your completed lead follow-up system, built to the requirements in your post:","Crisp, formal, no greeting fluff."),
]
out=old[:]
for n,t,a in new:
    full=t+L
    assert not re.search('[\u2013\u2014!]',full)
    c=len(full[:full.index("https://www.loom")+16])
    assert c<150,(n,c)
    out.append([n,full,c,a]); print(c,n)
rows=[['#','Variation','Char count','Angle',"Lorenzo's pick"]]+[[r[0],r[1],r[2],r[3],''] for r in out]
rows.append(['','Notes: char count runs from the first character through https://www.loom (UPWORK_PROCESS.md section 6). Counts use the example job shown (lead follow-up system, 4-min video); a different job changes the count. Row 2 needs their real post line swapped in. Row 3 uses a proposal P.S. fact. Drafts only, nothing used until Lorenzo gives the final go.','','',''])
json.dump(rows,open('openers_rows2.json','w'),ensure_ascii=False)
