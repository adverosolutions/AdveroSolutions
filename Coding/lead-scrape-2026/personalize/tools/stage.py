"""stage.py merge <batch>            -> merge extract_k into extract.json, print niche counts and False rows
   stage.py fill <batch> <niche> [restore ids...] -> set ids in-niche, select, fill, chunk 25s, render prompts"""
import json,glob,os,sys,subprocess,collections
SP=os.path.dirname(os.path.abspath(__file__)); PR=os.path.join(SP,"prompts"); ROOT="/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026"
os.chdir(ROOT)
cmd,B=sys.argv[1],sys.argv[2].rstrip("/")
if not B.startswith("/"): B=os.path.join(ROOT,B)
if cmd=="merge":
    rows={}
    for f in sorted(glob.glob(B+"/extract_[0-9]*.json")):
        for r in json.load(open(f)): rows[r["lead_id"]]=r
    chunks=json.load(open(B+"/_chunks.json")); want=[i for c in chunks for i in c]
    missing=[i for i in want if i not in rows]
    for r in rows.values():
        for k in ("what_it_is","years_claim","named_niche","guarantee","credential","about_voice_quote","source_url","evidence_quote"):
            if r.get(k) is None: r[k]=""
        if r.get("service_traits") is None: r["service_traits"]=[]
    json.dump(list(rows.values()),open(B+"/extract.json","w"),indent=1)
    L={l["lead_id"]:l for l in json.load(open(B+"/leads.json"))}
    print("merged",len(rows),"missing",missing,collections.Counter(r.get("is_in_niche") for r in rows.values()))
    for r in rows.values():
        if r.get("is_in_niche") is False: print("  FALSE",r["lead_id"],L[r["lead_id"]]["company_name"],"|",r.get("what_it_is","")[:140])
elif cmd=="fill":
    niche=sys.argv[3]; restore=set(sys.argv[4:])
    E=json.load(open(B+"/extract.json"))
    for e in E:
        if e["lead_id"] in restore: e["is_in_niche"]=True
    json.dump(E,open(B+"/extract.json","w"),indent=1)
    for s in ("daily_select.py","daily_fill.py"):
        print(subprocess.run(["python3","personalize/"+s,B],capture_output=True,text=True).stdout.strip().splitlines()[-1])
    rows=[];seen=set()
    for f in sorted(glob.glob(B+"/fill_chunk_*.json")):
        for r in json.load(open(f)):
            if r["lead_id"] not in seen: seen.add(r["lead_id"]); rows.append(r)
    for f in glob.glob(B+"/fill_chunk_*.json"): os.remove(f)
    tpl=open(f"{PR}/fill_{niche}.txt").read()
    n=0
    N=int(os.environ.get("FILL_N","25"))
    for i in range(0,len(rows),N):
        k=i//N; ch=rows[i:i+N]; json.dump(ch,open(f"{B}/fill_chunk_{k}.json","w"),indent=1)
        t=tpl.replace("BATCHDIR",B).replace("fill_chunk_K",f"fill_chunk_{k}").replace("x_K.json",f"x_{k}.json").replace("NN",str(len(ch)))
        open(f"{SP}/p_{os.path.basename(B)}_{k}.txt","w").write(t); n+=1
    print("fill rows",len(rows),"chunks",n,"prompts",f"{SP}/p_{os.path.basename(B)}_<k>.txt")
elif cmd=="prompts_extract":
    niche=sys.argv[3]; tpl=open(f"{PR}/extract_{niche}.txt").read(); chunks=json.load(open(B+"/_chunks.json"))
    for k in range(len(chunks)):
        t=tpl.replace("BATCHDIR",B).replace("chunk index K",f"chunk index {k}").replace("list[K]",f"list[{k}]").replace("extract_K.json",f"extract_{k}.json")
        t+=f"\n\nYour lead_ids, exactly these {len(chunks[k])} (they are list[{k}], zero-based): {json.dumps(chunks[k])}"
        open(f"{SP}/e_{os.path.basename(B)}_{k}.txt","w").write(t)
    print("extract prompts",len(chunks))
