#!/usr/bin/env python3
"""Merge SOS 11/2 chunk CSVs into per-niche <seg>.csv (contacted rows first). Rerun anytime."""
import csv,glob,os,re,collections
D=os.path.expanduser('~/advero/state/leadgen/personalized/sos_20261102'); by=collections.defaultdict(list)
for f in sorted(glob.glob(f'{D}/*_[cu][0-9][0-9][0-9].csv')):
  seg=re.sub(r'_[cu]\d{3}\.csv$','',os.path.basename(f)); by[seg]+=list(csv.DictReader(open(f)))
for seg,rows in by.items():
  for r in rows: r['queue_flag']='re_add_last' if r.get('contacted')=='True' else ''
  rows.sort(key=lambda r:r.get('contacted')=='True')
  #key=lambda r:r.get('contacted')!='True')
  with open(f'{D}/{seg}.csv','w',newline='') as o:
    w=csv.DictWriter(o,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
  print(seg,len(rows),collections.Counter(r['personalization_status'] for r in rows))
