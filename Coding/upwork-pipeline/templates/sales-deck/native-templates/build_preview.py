#!/usr/bin/env python3
"""Build isolated template previews. Never registers or alters queue jobs."""
import hashlib,html,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from build import compile_job,verify_lock,atomic_text

def main():
 out=ROOT.parents[1]/'.local/native-template-review'
 state=verify_lock();reports={}
 for name in ('ghl','n8n','zapier','claude'):
  reports[name]=compile_job(ROOT/'native-templates'/(name+'.json'),out/name,state)
 links=''.join('<a href="'+key+'/page.html"><strong>'+label+'</strong><span>'+desc+'</span><b>Open demo →</b></a>' for key,label,desc in [('ghl','GoHighLevel','Workflow Builder · Conversations · Opportunities'),('n8n','n8n','Canvas · Node input/output · Execution result'),('zapier','Zapier','Visual Zap editor · Step test and mapped data'),('claude','Claude','Current Skills list/detail · Projects · Chat and document')])
 page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Native template review</title><style>@font-face{font-family:Inter;src:url('../../templates/sales-deck/assets/inter-variable.woff2')}*{box-sizing:border-box}body{margin:0;color:#1d2939;font:14px Inter,Arial,sans-serif;background:linear-gradient(145deg,#d7e6fa,#edf3f9);min-height:100vh;padding:60px 7vw}main{max-width:1160px;margin:auto}.eyebrow{color:#2f74f5;font-size:11px;letter-spacing:.12em;text-transform:uppercase}h1{font-size:46px;letter-spacing:-.045em;font-weight:600;margin:17px 0}p{line-height:1.8;color:#657185;max-width:780px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;margin-top:35px}a{background:#ffffffd9;border:1px solid #fff;border-radius:20px;padding:30px;text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:15px;box-shadow:0 15px 40px -35px #42648a}a:hover{border-color:#8db6fc}a strong{font-size:27px;font-weight:550;letter-spacing:-.025em}a span{font-size:12px;color:#657185;line-height:1.7}a b{color:#2f74f5;font-size:12px;margin-top:14px}.foot{font-size:11px;margin-top:30px}@media(max-width:700px){body{padding:35px 20px}.grid{grid-template-columns:1fr}h1{font-size:35px}}</style><main><span class="eyebrow">AdveroSolutions · Template review</span><h1>Four tools. Their own native screens.</h1><p>The presentation palette, opening and closing CTA are preserved. These isolated sample decks show the rebuilt interiors and their replay controls. They are not connected to live accounts.</p><div class="grid">'''+links+'''</div><p class="foot">Native-template candidates · Independent review and version-specific acceptance are recorded in the repository. Existing recording jobs are untouched.</p></main></html>'''
 atomic_text(out/'index.html',page)
 packet={'templateHash':state['templateHash'],'pages':{k:v['files']['page.html'] for k,v in reports.items()},'previewRoot':str(out),'queueModified':False}
 atomic_text(ROOT/'native-templates/qa/page-hashes.json',json.dumps(packet,indent=2)+'\n')
 print(out/'index.html')
if __name__=='__main__':main()
