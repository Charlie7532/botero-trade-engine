import json, re, collections
w = json.load(open('backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json'))
st = w['states']
ks = list(st.keys())
print("n states:", len(ks))
print("ejemplo keys:", ks[:5])
# extraer el componente 'vel' de las keys
vel = collections.Counter()
for k in ks:
    mm = re.search(r'vel[:=]?([^|#]+)', k)
    if mm: vel[mm.group(1).strip()] += 1
print("valores vel:", dict(vel))
# estructura de un estado
k0 = ks[0]
print("estado ejemplo", k0, "->", list(st[k0].keys())[:15])
# multiscale
m = json.load(open('backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json'))
print("multiscale top:", list(m.keys())[:8])
for cand in ('states','l3_full_state','s3_triad','l1','levels'):
    if cand in m:
        d = m[cand]
        print(f"  {cand}: type={type(d).__name__} len={len(d) if hasattr(d,'__len__') else '?'}")
        if isinstance(d, dict):
            print("    ejemplo:", list(d.keys())[:3])
