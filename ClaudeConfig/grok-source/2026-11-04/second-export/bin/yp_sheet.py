#!/usr/bin/env python3
"""yp_sheet.py - sheet step for a staged Yellow Pages batch (pest_control A:V, sheet <REDACTED:long_token>).
The box has no Sheets credentials; Maps Bot does the reads/writes with the Google Sheets connector, this script does the math and checks.
  1) yp_sheet.py plan BATCHDIR LAST_USED_ROW GRID_ROWS   -> prints start/end row, rows to add to the grid, writes rows.tsv
       (LAST_USED_ROW: re-read column E of pest_control right before writing; GRID_ROWS: tab row count)
  2) Connector: if extend>0 append that many rows; pasteData rows.tsv at A{start}; write V{start}:V{end} RAW from v_col.json.
  3) Connector: read back pest_control!A{start}:V{end}, save JSON (list of rows) to BATCHDIR/readback.json
  4) yp_sheet.py verify BATCHDIR START   -> exact compare; on match runs maps_rolling_finalize.py (MV queue, logs, SHEET_DONE)."""
import json,sys,os,subprocess,csv
H=os.path.expanduser('~'); cmd,bd=sys.argv[1],sys.argv[2]
if os.path.exists(f'{H}/advero/state/KILL_SWITCH'): sys.exit('KILL_SWITCH present')
v=json.load(open(f'{bd}/values.json'))
if cmd=='plan':
    last,grid=int(sys.argv[3]),int(sys.argv[4]); start=last+1; end=start+len(v)-1; ext=max(0,end-grid+200) if end>grid-20 else 0
    with open(f'{bd}/rows.tsv','w') as f: f.write('\n'.join('\t'.join(c.replace('\t',' ').replace('\n',' ') for c in r[:21]) for r in v)+'\n')
    json.dump([[r[21]] for r in v],open(f'{bd}/v_col.json','w'))
    print(json.dumps(dict(rows=len(v),start=start,end=end,grid=grid,extend_rows=ext,tsv=f'{bd}/rows.tsv',range=f'pest_control!A{start}:V{end}')))
elif cmd=='verify':
    start=int(sys.argv[3]); rb=json.load(open(f'{bd}/readback.json'))
    norm=lambda r:[str(c) for c in r]+['']*(22-len(r))
    bad=[i for i,(a,b) in enumerate(zip(v,rb)) if norm(a)[:22]!=norm(b)[:22]]
    if len(rb)!=len(v) or bad: sys.exit(f'READBACK MISMATCH rows={len(rb)} vs {len(v)}; first bad index {bad[:5]}')
    print('read back exact'); subprocess.run(['python3',f'{H}/advero/bin/maps_rolling_finalize.py',bd,str(start)],check=True)
