import json, re, collections
w = json.load(open('backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json'))
st = w['states']
comp = collections.defaultdict(collections.Counter)
for k in st:
    # L1:W+++|σVc:<<|σc:<<|vel:▼
    for part in k.split('|'):
        if ':' in part:
            name, val = part.split(':', 1)
            comp[name][val] += 1
        elif 'W' in part and part.startswith('L1:'):
            comp['W'][part.replace('L1:', '')] += 1
print("=== DIMS del Wave EV (valores distintos) ===")
for name, c in comp.items():
    print(f"  {name}: {len(c)} valores -> {sorted(c)[:8]}")

m = json.load(open('backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json'))
tri = m['s3_triad']
ck = collections.defaultdict(collections.Counter)
for k in list(tri)[:5000]:
    base = k.split('#')[0]
    for i, part in enumerate(base.split('|')):
        ck[f"dim{i}"][part] += 1
print("\n=== DIMS del Multiscale s3_triad ===")
for name, c in ck.items():
    print(f"  {name}: {len(c)} valores -> {sorted(c)[:8]}")
print("\nclave ejemplo:", list(tri)[0])
