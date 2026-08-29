
import sys, inspect
sys.path.insert(0, "/root/botero-trade/research/01_señales_entry_exit")
import numpy as np, pandas as pd
from medir_senal import SEÑALES, _CERTEZA, cargar_datos
from evaluador_vela_a_vela import first_passage, BLANCOS

df, spy = cargar_datos()
prices = spy["close"].astype(float).values
spy_idx = spy.close.index
dates = pd.DatetimeIndex(df["pivot_date"])

# señales activas evaluables (sin pivot_type, sin RETIRADA)
activas = {}
for n in SEÑALES:
    if "pivot_type" in inspect.getsource(SEÑALES[n]): continue
    cert = str(_CERTEZA.get(n, {}).get("validacion", ""))
    if "RETIRADA" in cert or "DEGRADADA" in cert: continue
    s = SEÑALES[n](df).astype(bool)
    if s.mean() <= 0.20:
        activas[n] = s

FAMILIA = ["bsi_washed_out","capitulacion","credit_stress","vix_crisis_spike",
           "pcr_put_panic","fg_extreme_fear","vvix_entry","panico_total"]
FAMILIA = [f for f in FAMILIA if f in activas]

def fechas_de(sig): return dates[sig.values]

# ══ PARTE 1: matriz de anticipación/retardo entre pares de la familia ══
print("PARTE 1 — OFFSET TEMPORAL ENTRE PARES (días calendario, B respecto a A)")
print(f'{'A → B':>38s} | co-disparo | B antes | B después | offset_med')
for a in FAMILIA:
    for b in FAMILIA:
        if a == b: continue
        da, db = fechas_de(activas[a]), fechas_de(activas[b])
        if len(da)==0 or len(db)==0: continue
        offs = []
        for d in da:
            diff = (db - d).days
            near = diff[(diff >= -10) & (diff <= 10)]
            if len(near):
                # el más cercano; si empate, el anterior
                m = near[np.argmin(np.abs(near))]
                offs.append(m)
        offs = np.array(offs)
        if len(offs)==0:
            print(f"{a+' → '+b:>38s} | sin cercanía ±10d")
            continue
        mismo = (offs == 0).mean()
        antes = (offs < 0).mean()
        despues = (offs > 0).mean()
        med = np.median(offs)
        print(f"{a+' → '+b:>38s} | {mismo:>9.0%} | {antes:>6.0%} | {despues:>8.0%} | {med:>+9.1f}")

# ══ PARTE 2: ¿quién anticipa a quién? (offset medio firmado por par) ══
print()
print("PARTE 2 — LÍDERES Y SEGUIDORES (offset medio firmado: negativo = B anticipa a A)")
for a in FAMILIA:
    da = fechas_de(activas[a])
    leads = []
    for b in FAMILIA:
        if b == a: continue
        db = fechas_de(activas[b])
        offs = []
        for d in da:
            diff = (db - d).days
            near = diff[(diff >= -10) & (diff <= 10)]
            if len(near): offs.append(near[np.argmin(np.abs(near))])
        if offs: leads.append((np.mean(offs), b))
    leads.sort()
    desc = ", ".join(f"{b}({o:+.1f}d)" for o, b in leads[:3])
    print(f"  {a:>18s}: {desc}")

# ══ PARTE 3: valor de CONFIRMACIÓN — hit rate condicionado ══
print()
print("PARTE 3 — ¿LA HERMANA ANTICIPADA CONFIRMA? (hit zz25 condicionado)")
print(f'{'señal':>18s} | {'condición':>22s} | {'N':>4s} | {'hit':>5s} | {'fav_med':>8s}')
for s_name in ["capitulacion","pcr_put_panic","credit_stress","bsi_washed_out","vix_crisis_spike"]:
    sig = activas[s_name]
    blanco = BLANCOS[s_name]
    disp = df[sig]
    hermanas = {n: activas[n] for n in FAMILIA if n != s_name}
    grupos = {"sola": [], "co-disparo": [], "confirmada_previa": []}
    for _, row in disp.iterrows():
        d = pd.Timestamp(row["pivot_date"])
        t = spy_idx.searchsorted(d)
        if t >= len(prices)-1: continue
        r = first_passage(prices, t, 0.025, blanco)
        if not r or not r["resuelto"]: continue
        misma = any(((dates == d) & h.values).any() for h in hermanas.values())
        previa = any(((dates >= d - pd.Timedelta(days=5)) & (dates < d) & h.values).any() for h in hermanas.values())
        if misma: grupos["co-disparo"].append(r)
        elif previa: grupos["confirmada_previa"].append(r)
        else: grupos["sola"].append(r)
    for g, rs in grupos.items():
        if not rs: continue
        h = np.mean([x["hit"] for x in rs])
        f = np.mean([x["favorable"] for x in rs])
        print(f"{s_name:>18s} | {g:>22s} | {len(rs):>4d} | {h:>4.0%} | {f:>+7.2%}")
