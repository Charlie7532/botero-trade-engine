import json, re, collections

def dims_from_keys(keys, sep='|'):
    pos = collections.defaultdict(collections.Counter)
    for k in keys:
        base = k.split('#')[0]
        for i, part in enumerate(base.split(sep)):
            pos[i][part] += 1
    return pos

print("="*70)
print("VERIFICACIÓN INDEPENDIENTE DE DIMENSIONES (3 Fact Stores EV)")
print("="*70)

# 1) TIDE EV
t = json.load(open('backend/modules/quality_swing/domain/rules/rc_tide_ev_derived.json'))
ks = list(t['l3_full_state'].keys())
print(f"\n[1] TIDE EV — {len(ks)} estados L3")
print("    key ejemplo:", ks[0])
for i, c in sorted(dims_from_keys(ks).items()):
    print(f"    dim{i}: {len(c)} valores -> {sorted(c)}")

# 2) WAVE EV
w = json.load(open('backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json'))
ks2 = list(w['states'].keys())
print(f"\n[2] WAVE EV — {len(ks2)} estados")
print("    key ejemplo:", ks2[0])
for i, c in sorted(dims_from_keys(ks2).items()):
    print(f"    dim{i}: {len(c)} valores -> {sorted(c)}")
doc = w.get('_documentation', {})
dtd = doc.get('dimension_thresholds_definition') or doc.get('state_definitions') or {}
print("    _documentation.dimension_thresholds_definition:", list(dtd.keys()) if isinstance(dtd, dict) else str(dtd)[:80])

# 3) MULTISCALE
m = json.load(open('backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json'))
for lvl in ('s1_full', 's3_triad'):
    d = m.get(lvl, {})
    if not isinstance(d, dict): continue
    ks3 = list(d.keys())
    print(f"\n[3] MULTISCALE {lvl} — {len(ks3)} estados")
    print("    key ejemplo:", ks3[0])
    for i, c in sorted(dims_from_keys(ks3, sep='|').items()):
        vals = sorted(c)
        print(f"    dim{i}: {len(vals)} valores -> {vals[:9]}{'...' if len(vals)>9 else ''}")
