#!/usr/bin/env python3
# print cities whose every query got >=90% of the places gosom reported. usage: maps_rolling_full.py TAG
import csv,re,sys,collections
csv.field_size_limit(10**9)
B='/home/box/advero/state/leads/maps/'; TAG=sys.argv[1]
found={}
for l in open(B+f'logs/pest_{TAG}.log',errors='replace'):
    m=re.search(r'"jobid":"([^"]*)".*"message":"(\d+) places found"',l)
    if m: found[m.group(1)]=int(m.group(2))
rows=collections.Counter()
try:
    for r in csv.DictReader(open(B+f'raw/pest_{TAG}_raw.csv',errors='replace')): rows[r['input_id']]+=1
except FileNotFoundError: pass
lines=[l.rstrip('\n').split('#!#')[1] for l in open(B+f'raw/queries_{TAG}.txt') if '#!#' in l]
ok=lambda q: found.get(q) is not None and rows.get(q,0)>=found[q]*0.9
cities=[]; [cities.append(q.split('|')[0]) for q in lines if q.split('|')[0] not in cities]
for c in cities:
    if all(ok(q) for q in lines if q.split('|')[0]==c): print(c)
