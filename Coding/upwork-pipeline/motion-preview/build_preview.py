#!/usr/bin/env python3
"""Build one isolated GHL motion direction; never edits runtime/lock/queue."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PIPELINE=HERE.parent
DECK=PIPELINE/'templates/sales-deck'
sys.path.insert(0,str(DECK))
from build import compile_job,verify_lock,atomic_text,js_json

def main():
 out=PIPELINE/'.local/animated-sales-preview'
 spec=DECK/'native-templates/ghl.json'
 data=json.loads(spec.read_text());state=verify_lock()
 compile_job(spec,out/'base',state)
 text=(out/'base/page.html').read_text()
 original="""    chapterIndex = index;
    render();
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }

  function showNotes"""
 replacement="""    const direction = index >= chapterIndex ? 1 : -1;
    chapterIndex = index;
    window.DemoMotion.change(() => {
      render();
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    }, direction);
  }

  function showNotes"""
 if text.count(original)!=1:raise SystemExit('Preview hook no longer matches runtime; inspect before updating.')
 text=text.replace(original,replacement)
 config=js_json({'company':data['account']['name'],'initials':data['account']['initials']})
 script='window.MotionConfig='+config+';\n'+(HERE/'motion.js').read_text()
 text=text.replace('</head>','<style>'+ (HERE/'motion.css').read_text()+'</style></head>',1)
 text=text.replace('<script>','<script>'+script+'</script>\n<script>',1)
 text=text.replace('<title>','<title>Motion study · ',1)
 atomic_text(out/'index.html',text)
 atomic_text(out/'recording-script.txt',(out/'base/recording-script.txt').read_text())
 report={'status':'isolated_motion_candidate_pending_user_review','purpose':'Presentation motion study only; not production template acceptance','baseTemplateHash':state['templateHash'],'basePageHash':hashlib.sha256((out/'base/page.html').read_bytes()).hexdigest(),'pageHash':hashlib.sha256(text.encode()).hexdigest(),'motionFiles':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'motion.js',HERE/'motion.css')},'queueModified':False,'productionAssetsModified':False,'fixture':'Invented Northstar sample from native-templates/ghl.json'}
 atomic_text(out/'motion-build-report.json',json.dumps(report,indent=2)+'\n')
 print(out/'index.html')
if __name__=='__main__':main()
