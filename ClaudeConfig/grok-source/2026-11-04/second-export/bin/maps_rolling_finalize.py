#!/usr/bin/env python3
"""After the sheet write + read-back of a staged rolling batch (Maps Bot 2026-11-01).
usage: maps_rolling_finalize.py BATCHDIR START_ROW
Builds MV queue (good only; cleaning_residential HELD), merges into tab + all queues, logs quickenrich_pulls.csv and decisions.jsonl, marks SHEET_DONE."""
import csv,sys,json,os,shutil,subprocess,datetime
BD,start=sys.argv[1],int(sys.argv[2]); H=os.path.expanduser('~')
if os.path.exists(f'{BD}/SHEET_DONE'): print('already finalized'); sys.exit(0)
S=json.load(open(f'{BD}/post_summary.json')); B=json.load(open(f'{BD}/batch.json'))
TAG,NI,DATE=S['tag'],S['niche'],S['date']; tab=NI
rows=list(csv.DictReader(open(S['pool_file']))) if S.get('pool_file') else []
def wr(fn,keep):
    with open(fn,'w',newline='') as f:
        w=csv.writer(f); w.writerow(['email','sheet_row','tab','email_verification_date','fit'])
        for i,r in enumerate(rows):
            if keep(r): w.writerow([r['email'],start+i,tab,r.get('email_verification_date',''),r['fit']])
mvout=f'/workspace/mv/{DATE}_maps_{TAG}_{NI}_to_verify.csv'; held=f'/workspace/qe_bulk/maps_{TAG}/{DATE}_maps_{TAG}_residential_to_verify_HELD.csv'
wr(f'{BD}/mv_pre.csv',lambda r:r['fit']=='good' and r['country']=='US' and not r.get('mv_result'))
subprocess.run(['python3',f'{H}/advero/bin/suppression.py','filter',f'{BD}/mv_pre.csv',mvout],check=True,capture_output=True)
nheld=0
if NI=='cleaning':
    wr(f'{BD}/mv_pre_res.csv',lambda r:r['fit']=='cleaning_residential' and r['country']=='US')
    subprocess.run(['python3',f'{H}/advero/bin/suppression.py','filter',f'{BD}/mv_pre_res.csv',held],check=True,capture_output=True)
    nheld=len(list(csv.reader(open(held))))-1
new=list(csv.reader(open(mvout)))[1:]
added={}
for q in [f'/workspace/mv/{tab}_to_verify.csv','/workspace/mv/all_to_verify.csv']:
    bk=q.replace('.csv',f'.bak-{TAG}-maps.csv')
    os.path.exists(bk) or shutil.copy(q,bk)
    hdr=next(csv.reader(open(q))); have={l[0].lower() for l in csv.reader(open(q)) if l}
    add=[l for l in new if l[0].lower() not in have]
    with open(q,'a',newline='') as f:
        dw=csv.DictWriter(f,fieldnames=hdr,extrasaction='ignore')
        for l in add: dw.writerow(dict(zip(['email','sheet_row','tab','email_verification_date','fit'],l)))
    added[os.path.basename(q)]=len(add)
end=start+len(rows)-1
cols=S['sheet_cols'].split(':')
rng=f"{tab}!{cols[0]}{start}:{cols[1]}{end}" if rows else 'none'
note=(f"rolling runner batch {B['tag']}; {S['rows']} new rows with email {S['email_type']}; fit {S['fit']} (no manual overrides); "
      f"{rng} read back exact; {len(new)} queued for MV (not run) {mvout}; "+(f"{nheld} residential HELD {held}; " if NI=='cleaning' else '')+
      f"{S['qe'].get('upload',0)} QE domains in {S['qe_file']}; client_known {S['client_known']}; no throttle")
with open(f'{H}/advero/state/quickenrich_pulls.csv','a',newline='') as f:
    csv.writer(f).writerow([DATE,NI,f"Google Maps free crawl (gosom), {B['phase']} {B['first_idx']}-{B['last_idx']} ({'; '.join(B['cities'])}), {B['terms']}, depth {B.get('depth',6)}, c=1, TAG {TAG}",'','',B.get('places',''),f"pest_{TAG}.csv",S['rows'],note])
ts=datetime.datetime.now().astimezone().isoformat(timespec='seconds')
with open(f'{H}/advero/state/decisions.jsonl','a') as f:
    f.write(json.dumps({'ts':ts,'bot':'maps_bot','type':'maps_rolling_batch','tag':TAG,'phase':B['phase'],'cities':B['cities'],'places':B.get('places'),'rows':S['rows'],'range':rng,'fit':S['fit'],'mv_queued':len(new),'residential_held':nheld,'qe_domains':S['qe'].get('upload',0),'source':'Lorenzo GO via COO Sun 11/1 7:53 PM CT, relayed by Lead Gen Manager'})+'\n')
R=dict(range=rng,mv=len(new),mv_file=mvout,held=nheld,added=added)
json.dump(R,open(f'{BD}/SHEET_DONE','w')); print(json.dumps(R))
