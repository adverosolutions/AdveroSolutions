#!/usr/bin/env python3
"""Export the private Upwork knowledge/build handbook. No queue or service calls."""
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
REPO = PIPELINE.parents[1]
DECK = PIPELINE / 'templates/sales-deck'
OUT = PIPELINE / '.local/upwork-master-handbook'
AS_OF = '2026-10-20'
DOCS = ['00-MASTER.md', '01-OPERATIONS.md', '02-UI-REFERENCE-GUIDE.md',
        '03-TEST-THE-NEXT-MODEL.md', 'NEW_MODEL_PROMPT.txt', 'VERIFICATION.md']
EXTENSIONS = {'.md','.txt','.json','.html','.css','.js','.cjs','.py','.sh',
              '.png','.jpg','.jpeg','.webp','.gif','.svg','.woff2'}
EXCLUDED_PARTS = {'.git','.tmp','__pycache__','node_modules','.pytest_cache','.DS_Store'}
EXCLUDED_NAMES = {'credentials.json','token.json','registry.json','.env'}
NATIVE = {
 'ghl': ('Desktop sales candidate; not blanket production parity',
         'Builder, Conversations, Opportunities',
         'Exact current account/settings and other GHL surfaces remain unverified.'),
 'n8n': ('Desktop sales candidate; bounded editor/node scope',
         'Editor canvas and returned-node output table',
         'Literal sample requests; no executed API/dynamic-expression proof. Mobile whole-flow entry limited. Full execution chrome/AI subnodes not accepted.'),
 'zapier': ('Desktop sales candidate; current native evidence incomplete',
            'Visual Zap editor, row test and acknowledgement test',
            'Current full editor/test-panel reference gap. Paths/Next Gen not implemented.'),
 'claude': ('Desktop sales candidate; Skills/chat evidence bounded',
            'Claude app Skills and source-linked document/chat result',
            'Current Contents and populated chat/artifact references incomplete; no Cowork/Code substitution.')}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def product_guide():
    catalog = json.loads((DECK/'visual-reference/catalog.json').read_text())
    references = json.loads((DECK/'visual-reference/references.json').read_text())['images']
    supplement = json.loads((DECK/'native-templates/references/supplement.json').read_text())
    demand = json.loads((DECK/'visual-reference/research/local-demand.json').read_text())
    rows = ['# Native UI reference and readiness guide', '',
            'Compiled on '+AS_OF+' from saved research checked 19 October 2026 and the later repaired desktop review. No new web/account inspection is implied.', '',
            'Read this product selectively: do not load every image into every worker context. The source board is [the saved visual library](sources/pipeline/templates/sales-deck/visual-reference/index.html).', '',
            '## Readiness hierarchy', '',
            'The dated research catalog has 29 product plans and productionReady:false throughout. Its older no-adapter descriptions predate the four native candidates. The candidate overlay below records that later implementation without granting production approval. Current review: [whole-walkthrough findings](sources/pipeline/templates/sales-deck/native-templates/SALES-REVIEW-2026-10-19.md).', '',
            'A saved image, technical action catalog, implemented screen and accepted exact generation are four different states. Do not collapse them into supported/ready. Product-specific remaining evidence is mandatory.', '',
            '## Historical prioritization evidence', '',
            'The selected local corpus contained '+str(demand['uniqueJobs'])+' deduplicated original posts with genuine Upwork URLs. This is Lorenzo’s historical selection, not all Upwork. Mentions overlap; conservative Make aliases can undercount. No fresh counts were collected for this handoff.', '',
            '| Tool | Posts in that selected corpus |', '| --- | --- |']
    for entry in sorted(demand['platforms'], key=lambda x:x['jobs'], reverse=True)[:12]:
        rows.append('| '+entry['platform']+' | '+str(entry['jobs'])+' |')
    rows += ['', 'Public search-index signals have mixed crawl dates and category overlap; see the saved research for its limitations. Do not present them as live market share.', '', '## Product-by-product saved knowledge', '']
    for p in catalog['products']:
        key=p['id']; candidate=NATIVE.get(key)
        rows += ['### '+p['name']+' (`'+key+'`)', '',
                 '- Product category: '+p['category'],
                 '- Surface plan: '+ '; '.join(p['surfaces']),
                 '- Current implementation/readiness: '+(candidate[0] if candidate else 'Research/reference plan only; no accepted native renderer.'),
                 '- Research snapshot adapter note (dated, not approval): '+p['currentAdapter']]
        if candidate:
            rows += ['- Rebuilt scope: '+candidate[1], '- Current boundary: '+candidate[2],
                     '- Candidate preview: ['+p['name']+'](previews/'+key+'/page.html)',
                     '- Seed spec: [JSON](sources/pipeline/templates/sales-deck/native-templates/'+key+'.json)']
        rows += ['', '**Visual anchors to reproduce**', '']+['- '+v for v in p['visualAnchors']]
        rows += ['', '**Sales evidence to make visible**', '']+['- '+v for v in p['salesProof']]
        rows += ['', '**Do not substitute:** '+p['neverSubstitute'], '',
                 '**Research snapshot remaining work:** '+p['remainingWork'], '']
        refs=[r for r in references if r.get('platform')==key]
        if refs:
            rows += ['**Saved image evidence** (inspect the full image, including its qualification):', '']
            for r in refs:
                relative='sources/pipeline/templates/sales-deck/visual-reference/'+r['path']
                rows += ['- ['+r['id']+']('+relative+'): '+r.get('surface','')+'; '+r.get('qualification','')+
                         (' Historical capture.' if r.get('historical') else '')+
                         ' Source: ['+r.get('sourceId',r['id'])+']('+r['sourcePage']+'). SHA-256 `'+r['sha256']+'`.']
        else:
            rows += ['**Image gap:** no curated image in the saved main image inventory for this product. Documentation/identity research does not establish a full workspace. Obtain and record an applicable current reference before building a native interior.']
        if key in ('ghl','claude'):
            rows += ['', '**Supplemental current-rebuild references**', '']
            for r in supplement:
                path=r.get('path','')
                if (key=='ghl' and '/ghl-' in path) or (key=='claude' and '/claude-' in path):
                    rows.append('- [Saved capture](sources/pipeline/templates/sales-deck/'+path+'); provenance/qualification: `native-templates/references/supplement.json`. SHA-256 `'+r.get('sha256','not supplied')+'`.')
        rows += ['']
    rows += ['## If a platform is not in this guide', '',
             'Identify the exact product/surface first. Collect current full-workspace and relevant detail images from primary sources or an authorized actual workspace. Record provenance/date/hash/theme/version and the needed state map. Implement a bounded adapter separately, preserve the outer identity, compare pixels and semantics, test behavior and obtain whole-walkthrough review. Do not improvise a generic native UI while the recording queue waits.', '',
             'This guide preserves the known UI knowledge. It does not claim every product/version has already been implemented or that captured software can never change.', '']
    result='\n'.join(rows)
    (HERE/'02-UI-REFERENCE-GUIDE.md').write_text(result, encoding='utf-8')
    return catalog, references


def inline(s):
    # Escape before a bounded Markdown transform; no raw HTML from source prose.
    s=html.escape(s)
    s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
    def link(m):
        target=html.unescape(m.group(2))
        if not (target.startswith(('https://','http://')) or not re.match(r'^[a-zA-Z][\w+.-]*:',target)):
            return m.group(1)
        if target.endswith('.md') and not target.startswith(('https://','http://')) and '/' not in target:
            target=target[:-3]+'.html'
        return '<a href="'+html.escape(target,quote=True)+'">'+m.group(1)+'</a>'
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,s)


def render_md(text):
    out=[]; paragraph=[]; table=[]; code=[]; in_code=False; in_list=False
    def flush_p():
        if paragraph:out.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph.clear()
    def flush_t():
        if table:
            cells=lambda line:[x.strip() for x in line.strip().strip('|').split('|')]
            header=cells(table[0]);out.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+inline(x)+'</th>' for x in header)+'</tr></thead><tbody>')
            for row in table[2:]:out.append('<tr>'+''.join('<td>'+inline(x)+'</td>' for x in cells(row))+'</tr>')
            out.append('</tbody></table></div>');table.clear()
    for line in text.splitlines()+['']:
        if line.startswith('```'):
            flush_p();flush_t()
            if in_list:out.append('</ul>');in_list=False
            if in_code:out.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>');code=[]
            in_code=not in_code;continue
        if in_code:code.append(line);continue
        if line.startswith('|'):flush_p();table.append(line);continue
        flush_t()
        if line.startswith('#'):
            flush_p()
            if in_list:out.append('</ul>');in_list=False
            depth=min(4,len(line)-len(line.lstrip('#')));out.append('<h'+str(depth)+'>'+inline(line.lstrip('#').strip())+'</h'+str(depth)+'>');continue
        if line.startswith('- ') or re.match(r'^\d+\. ',line):
            flush_p()
            if not in_list:out.append('<ul>');in_list=True
            out.append('<li>'+inline(re.sub(r'^(?:- |\d+\. )','',line))+'</li>');continue
        if in_list and (not line.strip() or not line.startswith('  ')):out.append('</ul>');in_list=False
        if not line.strip():flush_p();continue
        if line.startswith('> '):flush_p();out.append('<blockquote>'+inline(line[2:])+'</blockquote>');continue
        paragraph.append(line.strip())
    return '\n'.join(out)


STYLE='''*{box-sizing:border-box}body{margin:0;background:#edf3fa;color:#1d2939;font:15px/1.75 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1140px;margin:0 auto;padding:44px 28px 90px}header{display:flex;justify-content:space-between;gap:20px;margin-bottom:32px;font-size:12px;color:#596b83}h1{font-size:38px;line-height:1.2;letter-spacing:-.04em;margin:18px 0}h2{font-size:25px;line-height:1.3;margin-top:42px;letter-spacing:-.025em}h3{font-size:19px;margin-top:30px}a{color:#2367db;text-decoration:none}a:hover{text-decoration:underline}.intro{max-width:820px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:30px 0}.card,article{background:white;border:1px solid #dce6f2;border-radius:16px;padding:26px;box-shadow:0 10px 30px -25px #4a6489}.card h2{margin:0 0 8px;font-size:20px}.card p{color:#657185;margin:0 0 12px}.label{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#2367db}.notice{border-left:4px solid #3c7deb;padding:12px 18px;background:#e1edff;margin:20px 0}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0}th,td{border:1px solid #dfe6ef;padding:10px 12px;text-align:left;vertical-align:top}th{background:#edf3fa}code{font:12px/1.6 ui-monospace,monospace;overflow-wrap:anywhere;background:#f2f5f9;border-radius:3px;padding:2px 4px}pre{background:#f2f5f9;padding:18px;overflow:auto;border-radius:9px}pre code{white-space:pre;padding:0}blockquote{border-left:3px solid #367df4;margin:20px 0;padding:8px 20px;background:#edf4ff}li{margin:7px 0}img{max-width:100%;height:auto;border:1px solid #dce6f2;border-radius:8px}.gallery{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.gallery figure{margin:0}.gallery figcaption{font-size:12px;color:#657185}.small{font-size:12px;color:#657185}article{overflow-wrap:anywhere}@media(max-width:700px){main{padding:24px 16px 50px}h1{font-size:30px}.cards,.gallery{grid-template-columns:1fr}article{padding:20px}}'''


def page(title,body):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style><main><header><a href="START_HERE.html">AdveroSolutions · Upwork master</a><span>Saved '+AS_OF+' · Private local handbook</span></header>'+body+'</main></html>'


def write_verifier(stage):
    (stage/'verify_package.py').write_text('''#!/usr/bin/env python3
"""Offline verification; no models, network, queue mutation or installation."""
import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'MANIFEST.json').read_text())
errors=[]
for rel,info in manifest['files'].items():
 p=root/rel
 if p.is_symlink() or not p.is_file():errors.append('Missing/unsafe: '+rel);continue
 if hashlib.sha256(p.read_bytes()).hexdigest()!=info['sha256']:errors.append('Changed: '+rel)
actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='MANIFEST.json' and '__pycache__' not in p.parts}
extra=actual-set(manifest['files'])
errors+=['Unexpected file: '+p for p in sorted(extra)]
if errors:print('FAIL\\n'+'\\n'.join(errors));sys.exit(1)
print('PASS '+str(len(manifest['files']))+' files; hashes and inventory match. Research/approval limits remain as documented.')
''',encoding='utf-8')


def main():
    catalog, references=product_guide()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if OUT.is_symlink() or OUT.parent.is_symlink():raise SystemExit('Unsafe export root')
    stage=Path(tempfile.mkdtemp(prefix='.handbook-',dir=str(OUT.parent)))
    try:
        for name in DOCS:shutil.copy2(HERE/name,stage/name)
        process=(PIPELINE/'UPWORK_PROCESS.md').read_text()
        locked='# Locked proposal and approved facts\n\nVerbatim snapshot from UPWORK_PROCESS.md, section 6 onward. Current user instructions and applicable factual constraints still apply.\n\n'+process[process.index('## 6. Proposal'):]
        (stage/'04-LOCKED-PROPOSAL-AND-FACTS.md').write_text(locked,encoding='utf-8')
        target=stage/'sources/pipeline/templates/sales-deck'
        for src in DECK.rglob('*'):
            rel=src.relative_to(DECK)
            if any(p in EXCLUDED_PARTS for p in rel.parts):continue
            if src.is_symlink():raise SystemExit('Refusing source symlink: '+str(src))
            if not src.is_file() or src.suffix.lower() not in EXTENSIONS or src.name in EXCLUDED_NAMES or src.name.startswith('.env'):continue
            dest=target/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
        for name in ['UPWORK_PROCESS.md','AGENTS.md','recording-queue','templates/ps-case-studies.md']:
            dest=stage/'sources/pipeline'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PIPELINE/name,dest)
        voice=stage/'sources/voice';voice.mkdir(parents=True)
        for key in ('lorenzo-voice','claudeisms'):
            shutil.copy2(Path.home()/'.agents/skills'/key/'SKILL.md',voice/(key+'.md'))
        for tool in NATIVE:
            src=PIPELINE/'.local/native-template-review'/tool
            for name in ('page.html','recording-script.txt','build-report.json'):
                dest=stage/'previews'/tool/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src/name,dest)
        packet=json.loads((DECK/'native-templates/qa/page-hashes.json').read_text())
        checks=json.loads((DECK/'native-templates/qa/browser-checks.json').read_text())
        if packet['pages']!=checks['pageHashes']:raise SystemExit('Current QA and preview hashes disagree')
        for tool,expected in packet['pages'].items():
            if sha(stage/'previews'/tool/'page.html')!=expected:raise SystemExit('Stale candidate page: '+tool)
        for name in DOCS[:4]+['04-LOCKED-PROPOSAL-AND-FACTS.md']:
            (stage/(Path(name).stem+'.html')).write_text(page(name, '<article>'+render_md((stage/name).read_text())+'</article>'),encoding='utf-8')
        cards=[('00-MASTER.html','Read the master','Sales purpose, fixed visual identity, native rules, behavior and lessons.'),('01-OPERATIONS.html','Run and deliver','Intake, roles, queue, review, Loom and locked proposal finalization.'),('02-UI-REFERENCE-GUIDE.html','Find the exact UI','29 product plans, saved images, provenance and current readiness boundaries.'),('03-TEST-THE-NEXT-MODEL.html','Test another model','One small invented-job test and a concrete 100-point acceptance rubric.'),('04-LOCKED-PROPOSAL-AND-FACTS.html','Use the exact proposal','Verbatim current locked copy, P.S. facts and approved Lorenzo claims.'),('NEW_MODEL_PROMPT.txt','Start a fresh model','Paste-ready handoff; no reliance on the old chat.')]
        content='<span class="label">Lorenzo’s reusable handoff</span><h1>Upwork demos, UI and delivery.</h1><p class="intro">The consolidated instructions, saved native references, reusable compiler and four exact reviewed candidate walkthroughs. Read the master once, then give a worker only the relevant job, template and references.</p><div class="notice">Four desktop sales candidates have bounded review. The 29-product library is research coverage; remaining native-reference gaps are documented. This is not blanket production approval.</div><div class="cards">'
        for href,title,desc in cards:content+='<section class="card"><h2><a href="'+href+'">'+title+'</a></h2><p>'+desc+'</p></section>'
        content+='</div><h2>Inspect the saved examples</h2><p>These are illustrative samples, not client deliveries or live account tests. No queue actions are performed by this handbook.</p><div class="gallery">'
        for key,label in [('ghl','GoHighLevel'),('n8n','n8n'),('zapier','Zapier'),('claude','Claude app')]:
            shot={'ghl':'ghl-pipeline-desktop','n8n':'n8n-node-desktop','zapier':'zapier-email-desktop','claude':'claude-output-desktop'}[key]
            content+='<figure><a href="previews/'+key+'/page.html"><img loading="lazy" alt="'+label+' illustrative result screen" src="sources/pipeline/templates/sales-deck/native-templates/qa/'+shot+'.png"></a><figcaption><a href="previews/'+key+'/page.html">Open '+label+' candidate</a> · <a href="previews/'+key+'/recording-script.txt">recording cues</a></figcaption></figure>'
        content+='</div><h2>Evidence and maintenance</h2><p><a href="sources/pipeline/templates/sales-deck/visual-reference/index.html">Visual reference board</a> · <a href="sources/pipeline/templates/sales-deck/native-templates/SALES-REVIEW-2026-10-19.md">Latest whole-walkthrough review</a> · <a href="MANIFEST.json">Exact export manifest</a> · <a href="VERIFICATION.md">Verification record</a></p><p class="small">Run verify_package.py to check file integrity. Export excludes real job folders, live queue state, credentials and proposal logs. Software/version changes still require an evidence refresh.</p>'
        (stage/'START_HERE.html').write_text(page('Lorenzo — Upwork master handbook',content),encoding='utf-8')
        write_verifier(stage)
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
        dirty=bool(subprocess.check_output(['git','status','--porcelain','--','CLAUDE.md','UPWORK_MASTER.html','Coding/upwork-pipeline/master-handoff','Coding/upwork-pipeline/UPWORK_PROCESS.md','Coding/upwork-pipeline/AGENTS.md','Coding/upwork-pipeline/templates/sales-deck'],cwd=REPO,text=True).strip())
        manifest={'schemaVersion':1,'asOf':AS_OF,'sourceCommit':commit,'sourceWorkingTreeHadChanges':dirty,'purpose':'Private knowledge/build transfer, not production approval','productPlans':len(catalog['products']),'curatedMainImages':len(references),'reviewedCandidatePages':packet['pages'],'excludes':['credentials/environment files','real job folders','live recording queue state','proposal logs','Loom recordings','Git history','account connections'],'files':{}}
        for path in sorted(stage.rglob('*')):
            if path.is_file():manifest['files'][str(path.relative_to(stage))]={'sha256':sha(path),'bytes':path.stat().st_size}
        (stage/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        subprocess.run([sys.executable,str(stage/'verify_package.py')],check=True)
        backup=OUT.with_name('upwork-master-handbook.previous')
        if backup.exists():shutil.rmtree(backup)
        if OUT.exists():OUT.rename(backup)
        stage.rename(OUT)
        if backup.exists():shutil.rmtree(backup)
        zip_path=OUT.parent/'upwork-master-handbook.zip'
        zip_tmp=zip_path.with_suffix('.zip.tmp')
        with zipfile.ZipFile(zip_tmp,'w',zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(OUT.rglob('*')):
                if p.is_file():archive.write(p,str(Path('upwork-master-handbook')/p.relative_to(OUT)))
        zip_tmp.replace(zip_path)
        launcher=REPO/'UPWORK_MASTER.html'
        launcher.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Upwork master</title><meta http-equiv="refresh" content="0; url=Coding/upwork-pipeline/.local/upwork-master-handbook/START_HERE.html"><p><a href="Coding/upwork-pipeline/.local/upwork-master-handbook/START_HERE.html">Open Lorenzo’s Upwork master handbook</a></p><p>If the export is missing, run Coding/upwork-pipeline/master-handoff/build_handbook.py.</p></html>\n',encoding='utf-8')
        print('Handbook: '+str(OUT/'START_HERE.html'))
        print('ZIP: '+str(zip_path))
        print('Launcher: '+str(launcher))
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':main()
