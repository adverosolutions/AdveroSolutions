from math import comb, sqrt
def fisher(a,n1,b,n2):
    # two-sided Fisher exact, sum of probs <= observed
    K=a+b; N=n1+n2
    def p(x): return comb(n1,x)*comb(n2,K-x)/comb(N,K)
    po=p(a); lo=max(0,K-n2); hi=min(K,n1)
    return min(1.0,sum(p(x) for x in range(lo,hi+1) if p(x)<=po*(1+1e-7)))
data={ # niche: (A contacted, A replies, A pos, B contacted, B replies, B pos)
 "Pest":(764,16,1,762,9,2),"PPC":(758,6,0,758,4,2),"Cleaning":(762,7,1,757,8,1)}
tot=[sum(v[i] for v in data.values()) for i in range(6)]; data["Pooled"]=tuple(tot)
for k,(na,ra,pa,nb,rb,pb) in data.items():
    print(f"{k}: A {pa}/{na}={pa/na:.3%} pos, {ra}/{na}={ra/na:.2%} rep | B {pb}/{nb}={pb/nb:.3%} pos, {rb}/{nb}={rb/nb:.2%} rep | p_pos={fisher(pa,na,pb,nb):.3f} p_rep={fisher(ra,na,rb,nb):.3f}")
# strict positives (exclude Dave conditional/declined, Laura question)
print("strict pooled", fisher(2,2284,3,2277), "B excl Dave only", fisher(2,2284,4,2277))
za,zb=1.959964,0.841621
def n(p1,p2):
    pb=(p1+p2)/2
    return (za*sqrt(2*pb*(1-pb))+zb*sqrt(p1*(1-p1)+p2*(1-p2)))**2/(p1-p2)**2
for p2 in (0.0036,0.005,0.01):
    m=n(0.0018,p2); print(p2, round(m), "days@750:", 2*m/750, "days@652:",2*m/652)
def mdr(N,p1=0.0018):
    lo,hi=p1+1e-6,0.2
    for _ in range(100):
        mid=(lo+hi)/2
        if n(p1,mid)>N: lo=mid
        else: hi=mid
    return hi
for N in (1781,3563/2, 10491/2, 13896/2):
    print(N, f"{mdr(N):.3%}")
