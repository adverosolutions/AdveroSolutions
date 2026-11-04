import json,re
LINKLEN=len("https://www.loom.com/share/")+32   # real Loom share URL = 59 chars
prev=json.load(open('openers_rows3.json'))
control,chall,row4=prev[1],prev[2],prev[6]
assert row4[0]=='4'
new=[
("1","[LOOM] built this straight off your post. rough edges are mine, the logic is all yours","Credit to them: their post, my build."),
("2","[LOOM] \U0001F446 that's your lead follow-up, not a demo of someone else's. built from your post","Pointer emoji, 'not a recycled demo' contrast."),
("3","[LOOM] \u2705 built \u2705 connected \u2705 running. 4 min, then tell me what to change","Checklist interrupt, hands them control."),
("4","\U0001F3A5 [LOOM] \u2190 your system. Already built. 4 min.","ROUND 3 ROW 4, unchanged (Lorenzo's pick to test)."),
("5","[LOOM] no slides, no pitch deck. just your lead follow-up running, 4 min","Anti-pitch, what it isn't."),
("6","[LOOM] made this before writing a single word of this proposal","Order of work: build first, words second. No emoji."),
("7","[LOOM] \u23F1\uFE0F 4 min. every step from your post, in order, start to finish","Maps the video to their post, step by step."),
("8","[LOOM] your lead follow-up as a working prototype. I can start this week","Honest prototype label + availability."),
("9","[LOOM] \U0001F527 you wrote out the problem. this is me fixing it. 4 min","Problem to fix, tool emoji."),
("10","[LOOM] 4 min of your lead follow-up actually running. the rest of this proposal is just details","Video is the proposal, text is secondary."),
]
out=[control,chall]
for n,t,a in new:
    assert '?' not in t and not re.search('[\u2013\u2014!]',t) and not re.search('quick|game.changer|hope this|I noticed|streamline|seamless|leverage|elevate',t,re.I),n
    i=t.index('[LOOM]'); assert i<=3,n
    full=len(t)-len('[LOOM]')+LINKLEN
    assert full<150,(n,full)
    a2=a+(' Full preview count, link counted at 59 chars.' if n!='4' else ' Full preview count, link counted at 59 chars.')
    out.append([n,t,full,a]); print(full,n)
rows=[['#','Variation','Char count','Angle',"Lorenzo's pick"]]+[[r[0],r[1],r[2],r[3],''] for r in out]
rows.append(['','Notes: link first in every row. [LOOM] = the Loom link, counted as a real share URL (https://www.loom.com/share/ + 32-char id = 59 chars). Rows 1 to 10 show the FULL count of everything up to 150 so you can see the whole preview fits; counted the section 6 way (through "https://www.loom") every row would be 16 to 18 chars, under the 133 floor. CONTROL and CHALLENGER keep their section 6 counts. Example job: lead follow-up system, 4-min video. Drafts only, nothing used until Lorenzo gives the final go.','','',''])
json.dump(rows,open('openers_rows4.json','w'),ensure_ascii=False)
