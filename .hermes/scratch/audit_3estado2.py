import json, re, collections

# ===== Wave EV: EV por 'vel' (poblacion zz50) =====
w = json.load(open('backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json'))
st = w['states']
agg = collections.defaultdict(lambda: {'n':0,'ev':0.0,'p':0.0})
for k, v in st.items():
    m = re.search(r'vel[:=]?([^|#]+)', k)
    if not m: continue
    lab = m.group(1).strip()
    zz = (v.get('derived_levels') or {}).get('zz50') or {}
    n = zz.get('n', 0) or 0
    agg[lab]['n'] += n
    agg[lab]['ev'] += n * (zz.get('ev', 0.0) or 0.0)
    agg[lab]['p']  += n * (zz.get('p_bull', 0.0) or 0.0)
print("=== WAVE EV — por 'vel' (zz50, ponderado por n) ===")
tot = sum(a['n'] for a in agg.values()) or 1
for lab in ['▼','~','▲']:
    a = agg[lab]; n = a['n'] or 1
    print(f"  vel {lab}: n={a['n']:,} ({100*a['n']/tot:4.1f}%)  EV={a['ev']/n:+.4f}  p_bull={a['p']/n:.4f}")

# ===== Multiscale: EV por 'traj' =====
m = json.load(open('backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json'))
tri = m['s3_triad']
agg2 = collections.defaultdict(lambda: {'n':0,'ev50':0.0,'ev25':0.0})
for k, v in tri.items():
    mm = re.search(r'#([A-Z_]+)', k)
    if not mm: continue
    lab = mm.group(1); n = (v.get('n') or 0)
    agg2[lab]['n'] += n
    agg2[lab]['ev50'] += n * (v.get('ev_net_50') or 0.0)
    agg2[lab]['ev25'] += n * (v.get('ev_net_25') or 0.0)
print("\n=== MULTISCALE s3_triad — por 'traj/FATIGUE' (ponderado por n) ===")
tot2 = sum(a['n'] for a in agg2.values()) or 1
for lab in ['ABSORBING','STABLE','EXHAUSTING']:
    a = agg2[lab]; n = a['n'] or 1
    print(f"  {lab}: n={a['n']:,} ({100*a['n']/tot2:4.1f}%)  EV_net_50={a['ev50']/n:+.4f}  EV_net_25={a['ev25']/n:+.4f}")

# ===== ¿Cuántos estados tienen n=0 en el centro de traj? (rareza real) =====
zero = sum(1 for k,v in tri.items() if (v.get('n') or 0) < 21)
print(f"\n  estados s3_triad con n<21 (diamantes §3.3): {zero}/{len(tri)}")
