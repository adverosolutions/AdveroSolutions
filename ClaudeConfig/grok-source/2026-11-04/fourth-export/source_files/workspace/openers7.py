import json
L=59
def c(s): return len(s.replace("[LOOM]","x"*L))
rows=[
("A","I can turn your [THEIR STACK] mess into one clean system that scales. My approach: [LOOM]","I can turn your ClickUp and Zapier mess into one clean system that scales. My approach: [LOOM]","Model A: stack chaos to clean system, labeled Loom. No proof fact"),
("A","Your [THEIR STACK] workflows can run as one clean system. I work in n8n and Make daily. [LOOM]","Your n8n workflows can run as one clean system. I work in n8n and Make daily. [LOOM]","Model A + approved fact (n8n/Make daily)"),
("A","Your [THEIR STACK] pipeline, cleaned up and running on its own. How I'd set it up: [LOOM]","Your HubSpot pipeline, cleaned up and running on its own. How I'd set it up: [LOOM]","Model A: labeled Loom, no proof fact"),
("A","Scattered intake into one clean CRM flow. I built the intake system for a PI law firm. [LOOM]","Scattered intake into one clean CRM flow. I built the intake system for a PI law firm. [LOOM]","Model A + approved fact (PI intake). Legal/intake posts only"),
("A","Your [THEIR STACK] setup, turned into a clean system. I set up GHL accounts all the time. [LOOM]","Your GHL setup, turned into a clean system. I set up GHL accounts all the time. [LOOM]","Model A + approved fact (GHL). GHL posts only"),
("A","[THEIR WORKFLOW] as one clean system. My approach: [LOOM]","Instantly sends, inbox replies and CRM updates as one clean system. My approach: [LOOM]","Model A: shortest, workflow-led, labeled Loom"),
("B","[EXACT PAIN] is a problem I've solved [N] times. [LOOM]","Your GHL to Calendly sync dropping no-shows is a problem I've solved [N] times. [LOOM]","Model B: exact pain + count. [N] must be a real number from Lorenzo"),
("B","[EXACT PAIN] is something I've fixed [N] times. [LOOM]","Zapier tasks failing silently on large HubSpot imports is something I've fixed [N] times. [LOOM]","Model B: exact pain + count. [N] from Lorenzo"),
("B","[EXACT PAIN] is a problem I've solved [N] times. Fix: [LOOM]","Make scenarios stopping on blank form fields is a problem I've solved [N] times. Fix: [LOOM]","Model B: exact pain + count + short Loom label. [N] from Lorenzo"),
("B","[EXACT PAIN]. I send 100k+ cold emails a month on Instantly. [LOOM]","Replies sorted by hand in Instantly. I send 100k+ cold emails a month on Instantly. [LOOM]","Model B variant: approved fact replaces count (Instantly)"),
("B","[EXACT PAIN]. I built the intake system for a PI law firm. [LOOM]","After-hours intake calls going to voicemail. I built the intake system for a PI law firm. [LOOM]","Model B variant: approved fact replaces count (PI intake)"),
("B","[EXACT PAIN]. Just finished a similar build last week. [LOOM]","An AI agent answering from your database. Just finished a similar build last week. [LOOM]","Model B variant: approved line for AI agent on client database builds"),
]
out=[["Batch D (2026-10-22 10:55 CT, Lorenzo's 10:52 models A and B)","","","","","","","Model"]]
for i,(m,t,f,a) in enumerate(rows,1):
    n=c(f); assert n<=150,(i,n,f)
    assert "—" not in f and "!" not in f
    out.append([f"D{i}","D",t,f,n,a,"","Model "+m])
out.append(["Notes","D","[LOOM] counted as 59 chars (full Loom share URL). Model B count rows need a real [N] from Lorenzo before use; no approved count exists. Facts are from UPWORK_PROCESS.md section 7, each fits only its matching post type. Nothing sent or tested.","","","","",""])
json.dump(out,open("openers_rows7.json","w"))
for r in out[1:-1]: print(r[0],r[4],r[3])
