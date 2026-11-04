import sys,os,json,urllib.request
sys.path.insert(0,os.path.expanduser('~/advero/bin')); import _load_box_secrets as s; s.apply()
K=os.environ['INSTANTLY_API_KEY']
def api(p,m='GET',b=None):
  r=urllib.request.Request('https://api.instantly.ai/api/v2'+p,method=m,data=json.dumps(b).encode() if b is not None else None,headers={'Authorization':'Bearer '+K,'User-Agent':'advero-ops/1.0','Content-Type':'application/json'})
  try: return json.load(urllib.request.urlopen(r,timeout=60))
  except urllib.error.HTTPError as e: return {'_err':e.code,'_body':e.read().decode()[:400]}
