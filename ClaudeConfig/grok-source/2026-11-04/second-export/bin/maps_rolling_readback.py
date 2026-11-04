import json,csv,io,sys
t=open(sys.argv[1]).read(); j=json.loads(t[t.index('{'):t.rindex('}')+1])
got=list(csv.reader(io.StringIO(j['ranges'][0]['content'])))
exp=json.load(open(sys.argv[2])); n=len(exp[0])
bad=sum(1 for a,b in zip(got,exp) if (a+['']*n)[:n]!=b)
print('got',len(got),'exp',len(exp),'mismatch',bad)
