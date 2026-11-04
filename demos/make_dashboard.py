import sys, html
ready = set(sys.argv[1:])  # job ids that are ready
jobs = [
 ("2113409159971093497","GHL UK plumbing and heating (Marvellous)","ghl-automation-specialist-crm-lead-management","Record on the Detailed route. Fill in [AVAILABILITY]."),
 ("2113396734814561387","n8n AI support email workflow ($380)","n8n-support-email-rag-workflow","Fill or delete the [LORENZO] bracket."),
 ("2113387550517732459","Klaviyo AI campaigns (LA jewelry)","klaviyo-ai-campaign-automation","Opens with KLAVIYO. Confirm 11 AM to 6 PM PT availability. Newest client review is 1 star."),
 ("2113394730633503851","GHL real estate brokerage","ghl-architect-real-estate-brokerage","Opens with Pipeline First. Fill or delete [REAL ESTATE PROJECT]."),
]
rows=""
for jid,title,slug,note in jobs:
    ok = jid in ready
    demo = f"http://127.0.0.1:8769/jobs/{slug}-{jid}/page.html"
    up = f"https://www.upwork.com/jobs/~02{jid}"
    st = '<span class="ok">Ready to record</span>' if ok else '<span class="wait">Building</span>'
    db = f'<a class="btn" href="{demo}" target="_blank">Open demo</a>' if ok else '<span class="btn off">Demo not ready</span>'
    rows += f'<div class="card"><div class="top"><h2>{html.escape(title)}</h2>{st}</div><p>{html.escape(note)}</p><div class="btns">{db}<a class="btn" href="{up}" target="_blank">Open Upwork post</a></div></div>'
page=f'''<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="20"><title>Tonight's demos</title>
<style>body{{font-family:Inter,system-ui,sans-serif;background:#0b0f17;color:#e8ecf3;margin:0;padding:32px}}h1{{margin:0 0 20px}}.card{{background:#121a2a;border:1px solid #23304a;border-radius:14px;padding:18px 20px;margin-bottom:14px;max-width:820px}}.top{{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}h2{{font-size:18px;margin:0}}p{{color:#9fb0cc;margin:8px 0 14px}}.ok{{color:#4ade80;font-weight:600}}.wait{{color:#fbbf24;font-weight:600}}.btns{{display:flex;gap:10px;flex-wrap:wrap}}.btn{{background:#2563eb;color:#fff;text-decoration:none;padding:9px 14px;border-radius:9px;font-weight:600}}.off{{background:#334155;color:#94a3b8}}</style></head>
<body><h1>Tonight's demos</h1>{rows}<p>This page refreshes every 20 seconds.</p></body></html>'''
open("/Users/lorenzovillarreal/Desktop/AdveroSolutions/demos/tonight.html","w").write(page)
