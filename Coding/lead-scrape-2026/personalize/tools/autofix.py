"""autofix.py <batch> [manual.json] -> writes fix_<batch>.json combining rule fixes + manual {"fix":{},"skip":{}} and prints changes"""
import json,re,sys,os,collections
SP=os.path.dirname(os.path.abspath(__file__)); ROOT="/Users/lorenzovillarreal/Desktop/AdveroSolutions/Coding/lead-scrape-2026"; os.chdir(ROOT)
B=sys.argv[1]; man=json.load(open(sys.argv[2])) if len(sys.argv)>2 else {"fix":{},"skip":{}}
D="you must have a desk at half your clients' offices by now"; sd=lambda c: f"you must have half of {c} on speed dial"
x=json.load(open(B+"/x.json")); L={l["lead_id"]:l for l in json.load(open(B+"/leads.json"))}
S={s["lead_id"]:s for s in json.load(open(B+"/select.json"))}
FIXC={"Saint Anthny Vlg":"St. Anthony","Parsippany-troy Hills":"Parsippany","Redford Charter Township":"Redford","Winston-salem":"Winston-Salem","Coeur D'alene":"Coeur d'Alene","King Of Prussia":"King of Prussia","Fond Du Lac":"Fond du Lac","Mcallen":"McAllen"}
def city(l):
    c=(l.get("company_city") or "").strip()
    c=FIXC.get(c,c)
    c=re.sub(r"\s+(Township|Charter Township|Village|Vlg)$","",c)
    return c
BAD_SLEEP=r"\b(handle|spot|identify|close|find|scale|guarantee|diagnose|read|crunch|forecast agency|manage both|audit a company|match|source an executive|top talent|anything)\b"
def head(n): 
    w=n.lower().split()[-1]; return re.sub(r"(ies)$","y",re.sub(r"(?<!s)s$","",w))
IRR={"people":"person","businesses":"business","companies":"company","facilities":"facility","agencies":"agency","properties":"property","practices":"practice","nonprofits":"nonprofit","startups":"startup","firms":"firm","schools":"school","offices":"office","hospitals":"hospital","restaurants":"restaurant","warehouses":"warehouse","banks":"bank","clinics":"clinic","homes":"home","dealerships":"dealership","contractors":"contractor","owners":"owner","organizations":"organization","attorneys":"attorney","engineers":"engineer","nurses":"nurse","physicians":"physician","developers":"developer","funds":"fund","brands":"brand","manufacturers":"manufacturer","hotels":"hotel","buildings":"building","churches":"church","dentists":"dentist","retailers":"retailer","families":"family","HOAs":"HOA"}
BADN={"all","levels","roles","industries","sectors","professionals","talent","leadership","leaders","positions","needs","clients","individuals","services","various","multiple","regions"}
def noun_from_x(X):
    m=re.search(r"\bfor ([a-z0-9 -]+?)$",X)
    if not m: return None
    ph=re.split(r",| and ",m.group(1))[-1].strip().split()
    if not ph or len(ph)>3: return None
    last=ph[-1]
    if last in BADN or last not in IRR: return None
    out=" ".join(ph[:-1]+[IRR[last]])
    return None if out in {"business","company","organization","firm"} else out
def sleep_from_x(X):
    m=re.search(r"\b(?:recruiting|placing|placement of|staffing) ([a-z ]+?)s\b",X)
    if not m: return None
    n=m.group(1).split(" and ")[0].strip()
    if n.split()[0] in {"for","of","and","with","across","to"}: return None
    if len(n.split())>2 or n.split()[-1] in BADN|{"talent","professional","role"}: return None
    return f"you must be able to place a{'n' if n[0] in 'aeiou' else ''} {n} in your sleep"
used_sd=collections.Counter(re.match(r"you must have half of (.+?) on speed dial$",v["y"]).group(1) for v in x.values() if re.match(r"you must have half of (.+?) on speed dial$",v["y"]))
N=len(x); state={"sd":sum(used_sd.values())}
def fallback(lid,X,c):
    n=noun_from_x(X)
    if n and c: return f"you must know every {n} in {c} by name"
    s=sleep_from_x(X)
    if s: return s
    if c and used_sd[c]==0 and state["sd"]<N*0.36:
        used_sd[c]+=1; state["sd"]+=1; return sd(c)
    return D
fix={}; why={}
for lid,v in x.items():
    if lid in man.get("skip",{}) or S.get(lid,{}).get("tier")=="skip": continue
    y=v["y"]; X=v["x"].lower(); c=city(L[lid]); new=None; r=""
    if y==D: continue
    m=re.match(r"you must have half (?:of )?(.+?) on speed dial$",y)
    if m:
        if c and m.group(1)!=c: new=fallback(lid,X,c); r="speed-dial place"
        elif not c: new=D; r="no city"
    elif "by now" in y: new=fallback(lid,X,c); r="by now"
    elif y.endswith("by name"):
        m=re.match(r"you must know every (.+?) (?:in|on|around) (.+?) by name$",y)
        if not m: new=fallback(lid,X,c); r="by-name shape"
        else:
            n,p=m.group(1),m.group(2)
            hw=head(n); ok=hw in re.sub(r"[^a-z ]"," ",X) or n.lower() in X
            if not ok: new=fallback(lid,X,c); r=f"noun '{n}' not in X"
            elif c and p!=c: new=f"you must know every {n} in {c} by name"; r="by-name place"
            elif not c: new=D; r="no city"
    elif "in your sleep" in y:
        if re.search(BAD_SLEEP,y): new=fallback(lid,X,c); r="vague sleep task"
    else: new=sd(c) if c else D; r="unknown shape"
    if len(y.split())>12 and not new: new=sd(c) if c else D; r="too long"
    if new and new!=y: fix[lid]={"y":new}; why[lid]=r
for lid,f in man.get("fix",{}).items(): fix.setdefault(lid,{}).update(f); why[lid]=why.get(lid,"")+" +manual"
json.dump({"fix":fix,"skip":man.get("skip",{})},open(f"{SP}/fix_{os.path.basename(B)}.json","w"),indent=1)
fin={l:dict(v,**fix.get(l,{})) for l,v in x.items() if l not in man.get("skip",{})}
cnt=collections.Counter("sd" if "speed dial" in v["y"] else "desk" if v["y"]==D else "name" if "by name" in v["y"] else "sleep" for v in fin.values())
for l in sorted(fix): print(l, why[l], "|", x[l]["y"], "->", fix[l].get("y",x[l]["y"]), ("| X-> "+fix[l]["x"]) if "x" in fix[l] else "")
print(len(fix),"fixes", dict(cnt))
