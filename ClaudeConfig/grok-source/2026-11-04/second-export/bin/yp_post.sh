#!/bin/bash
# yp_post.sh TAG - Yellow Pages raw -> website email crawl -> maps_postprocess (dedupe vs final-leads, pool, all Maps outputs,
# suppression, client-index skip) -> maps_rolling_post (qe_dedupe, fit tagging, pool file, values.json, QE domain file).
# Stages for the sheet only. Never runs MV, QE or qe_fit.py. Nothing goes to Instantly.
set -eu
TAG=$1; T=yp_$TAG; H=$HOME; M=$H/advero/state/leads/maps; YP=$H/advero/state/leads/yp
[ -e $H/advero/state/KILL_SWITCH ] && { echo KILL_SWITCH; exit 9; }
RAW=$YP/raw/pest_yp_${TAG}_raw.csv; EM=$YP/raw/pest_yp_${TAG}_raw_emails.csv; BD=$YP/batches/$T; mkdir -p $BD
python3 $H/advero/bin/site_email_crawl.py $RAW $EM --workers 6
python3 $H/advero/bin/site_email_crawl.py $EM $EM --workers 3 --retry-status fetch_error,error || true
python3 $H/advero/bin/maps_postprocess.py $EM $M/pest_${T}.csv --stats $YP/logs/pest_${T}_stats.json
python3 $H/advero/bin/maps_rolling_post.py pest $T $BD $(date +%F)
python3 - $BD $RAW $YP/cities/pest_test10.txt <<'P'
import json,csv,sys,os,collections
bd,raw,cl=sys.argv[1:4]; S=json.load(open(bd+'/post_summary.json'))
if S.get('pool_file'):
    rows=list(csv.DictReader(open(S['pool_file'])))
    for r in rows:
        r['source']='yellow_pages'; r['source_search']='YP'; r['fit_reason']=r['fit_reason'].replace('[MAPS]','[YP]').replace('Google Maps listing site','Yellow Pages listing site')
    w=csv.DictWriter(open(S['pool_file'],'w',newline=''),fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    v=json.load(open(bd+'/values.json'))
    for x,r in zip(v,rows): x[15]='yellow_pages'; x[18]=r['fit_reason']
    json.dump(v,open(bd+'/values.json','w'))
cs=sorted({r['input_id'].split('|')[0] for r in csv.DictReader(open(raw))}); allc=[l.strip() for l in open(cl) if l.strip()]
idx=[allc.index(c)+1 for c in cs if c in allc] or [0]
json.dump(dict(batch=S['tag'],tag=S['tag'],phase='yellow_pages_pest_test10',cities=cs,first_idx=min(idx),last_idx=max(idx),
  terms='YP: pest control|exterminators',places=sum(1 for _ in csv.DictReader(open(raw)))),open(bd+'/batch.json','w'),indent=1)
open(bd+'/READY_FOR_SHEET','w').write('1'); print(json.dumps({k:S.get(k) for k in ('rows','fit','email_type','client_known','qe_file')}))
P
