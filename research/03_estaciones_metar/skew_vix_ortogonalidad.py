import numpy as np, pandas as pd
from scipy.stats import spearmanr, chi2_contingency
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

store = TimescaleDataStore()
sk = store.load_bars("SKEW","1d")["close"].dropna(); vx = store.load_bars("VIX","1d")["close"].dropna()
common = sk.index.intersection(vx.index); sk=sk.loc[common]; vx=vx.loc[common]
store.close()
n=len(sk)

# SKEW classification: LOW (<P15, ~113), NORMAL (P15-P85, 113-148), BLACK_SWAN (>P85, ~148)
sk_p15=sk.quantile(0.15); sk_p85=sk.quantile(0.85)
sk_lo=sk<sk_p15; sk_hi=sk>=sk_p85
# VIX classification: CALM (<P85, ~28), CRISIS (>P85, ~28)
vx_p85=vx.quantile(0.85)
vx_hi=vx>=vx_p85

print(f"SKEW P15={sk_p15:.0f}  P85={sk_p85:.0f}  |  VIX P85={vx_p85:.1f}")
print(f"SKEW LOW: {(sk_lo).sum():>5} ({(sk_lo).mean()*100:.0f}%)  SKEW HIGH: {(sk_hi).sum():>5} ({(sk_hi).mean()*100:.0f}%)")
print(f"VIX CRISIS: {(vx_hi).sum():>5} ({(vx_hi).mean()*100:.0f}%)\n")

# Matriz de contingencia
cells = [
    [sk_lo&~vx_hi, sk_lo&vx_hi],
    [~(sk_lo|sk_hi)&~vx_hi, ~(sk_lo|sk_hi)&vx_hi],
    [sk_hi&~vx_hi, sk_hi&vx_hi],
]
labels = ["SKEW BAJO", "SKEW NORMAL", "SKEW ALTO (BLACK_SWAN)"]
print(f"  {'':<20} {'VIX CALMO':>12} {'VIX CRISIS':>12}")
for i, row in enumerate(cells):
    print(f"  {labels[i]:<20} {row[0].sum():>12} {row[1].sum():>12}")

# Chi2 test
observed = np.array([[c.sum() for c in row] for row in cells])
chi2, p_chi2, dof, _ = chi2_contingency(observed)
print(f"\nχ²={chi2:.1f}  p={p_chi2:.2e}  dof={dof}")
print(f"  → {'SÍ hay asociación (no son independientes)' if p_chi2<0.01 else 'NO hay asociación significativa'}")

# Conditional probabilities with bootstrap
rng = np.random.default_rng(42)
print(f"\n═══ CONDICIONALES con bootstrap CI95 ═══\n")
# P(SKEW HIGH | VIX CRISIS)
p_skhi_given_vxhi = sk_hi[vx_hi].mean()
# P(VIX CRISIS | SKEW HIGH)  
p_vxhi_given_skhi = vx_hi[sk_hi].mean()
# P(SKEW LOW | VIX CRISIS)
p_sklo_given_vxhi = sk_lo[vx_hi].mean()
# P(VIX CRISIS | SKEW LOW)
p_vxhi_given_sklo = vx_hi[sk_lo].mean()

for name, base_prob, cond_prob_obs, desc in [
    ("P(SKEW ALTO | VIX CRISIS)", sk_hi.mean(), p_skhi_given_vxhi, "SKEW en pánico dado que VIX está en crisis"),
    ("P(VIX CRISIS | SKEW ALTO)", vx_hi.mean(), p_vxhi_given_skhi, "VIX en crisis dado que SKEW está en pánico"),
    ("P(SKEW BAJO | VIX CRISIS)", sk_lo.mean(), p_sklo_given_vxhi, "SKEW complaciente dado que VIX está en crisis"),
    ("P(VIX CRISIS | SKEW BAJO)", vx_hi.mean(), p_vxhi_given_sklo, "VIX en crisis dado que SKEW está complaciente"),
]:
    # Bootstrap
    bs = []
    for _ in range(2000):
        if "SKEW" in name.split("|")[0]:
            cond = vx_hi
            target = sk_hi if "ALTO" in name else sk_lo
        else:
            cond = sk_hi if "ALTO" in name else sk_lo
            target = vx_hi
        idx = rng.choice(np.where(cond)[0], size=cond.sum(), replace=True)
        bs.append(target.iloc[idx].mean())
    ci = np.percentile(bs, [2.5, 97.5])
    marker = "★ DISCREPANCIA" if abs(cond_prob_obs - base_prob) > 0.03 and (ci[1] < base_prob or ci[0] > base_prob) else ""
    print(f"  {desc}")
    print(f"    Base (incondicional): {base_prob:.1%}  |  Condicional: {cond_prob_obs:.1%}  CI95 [{ci[0]:.1%}, {ci[1]:.1%}]  {marker}")
    print()

# Joint probabilities: how often do they coincide?
joint_hi = (sk_hi & vx_hi).sum()
joint_lo = (sk_lo & vx_hi).sum()
joint_opposite = (sk_hi & ~vx_hi).sum()
print(f"  Días con AMBOS en extremo (SKEW↑ + VIX↑): {joint_hi} ({joint_hi/n*100:.1f}%)")
print(f"  Días con SKEW↓ + VIX↑ (complacencia + crisis): {joint_lo} ({joint_lo/n*100:.1f}%)")
print(f"  Días con SKEW↑ + VIX↓ (miedo cola + calma vol): {joint_opposite} ({joint_opposite/n*100:.1f}%)")