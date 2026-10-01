import json, re, collections

# ---------- 1) Wave EV: poblacion por 'vel' ----------
w = json.load(open('backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json'))
st = w['states']
vel_n = collections.Counter(); vel_states = collections.Counter()
for k, v in st.items():
    m = re.search(r'vel[:=]?([^|#]+)', k)
    if not m: continue
    lab = m.group(1).strip()
    n = v.get('n_total') or v.get('n') or 0
    vel_n[lab] += n; vel_states[lab] += 1
tot = sum(vel_n.values()) or 1
print("=== WAVE EV: 'vel' (poblacion) ===")
for lab, n in vel_n.most_common():
    print(f"  vel {lab!r}: n={n:,}  ({100*n/tot:5.1f}%)  estados={vel_states[lab]}")
print(f"  TOTAL n = {tot:,}")

# ---------- 2) Multiscale: poblacion por traj (#SUFFIX) ----------
m = json.load(open('backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json'))
print("\n=== MULTISCALE top keys ===", list(m.keys()))
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, path + "/" + str(k))
    else:
        yield path, o
tri = m.get('s3_triad') or {}
print("s3_triad len:", len(tri) if isinstance(tri, dict) else type(tri))
if isinstance(tri, dict):
    k0 = list(tri.keys())[0]
    print("ejemplo s3_triad:", k0, "->", list(tri[k0].keys())[:12] if isinstance(tri[k0], dict) else tri[k0])
    suf_n = collections.Counter(); suf_states = collections.Counter()
    for k, v in tri.items():
        mm = re.search(r'#([A-Z_]+)', k)
        if not mm: continue
        nn = (v.get('n') if isinstance(v, dict) else None) or (v.get('n_total') if isinstance(v, dict) else 0) or 0
        suf_n[mm.group(1)] += nn; suf_states[mm.group(1)] += 1
    tots = sum(suf_n.values()) or 1
    print("\n=== MULTISCALE s3_triad: traj/FATIGUE (poblacion) ===")
    for lab, n in suf_n.most_common():
        print(f"  {lab}: n={n:,}  ({100*n/tots:5.1f}%)  estados={suf_states[lab]}")
    print(f"  TOTAL n = {tots:,}")
