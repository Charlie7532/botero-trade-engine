"""CLI del arnés de medición (interfaz).

Extraído del God file medir_senal.py (refactor 22-Ago-2026).
Matemática pura, determinista, sin agentes.
"""
import argparse
import json

from .datos import cargar_datos, SCRATCH
from .medicion import medir, medir_cross_overlap

def main():
    ap = argparse.ArgumentParser(description="Arnés de medición estándar Botero Trade")
    ap.add_argument("--señal", required=True, help="Nombre de la señal registrada")
    ap.add_argument("--forward", default="next_leg", help="Columna de retorno forward")
    ap.add_argument("--bootstrap", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None, help="Ruta del JSON de salida")
    ap.add_argument("--cross-overlap", action="store_true", help="Incluir análisis de cross-signal overlap")
    args = ap.parse_args()

    df, spy = cargar_datos()
    rep = medir(args.señal, df, args.forward, spy=spy, n_iter=args.bootstrap, seed=args.seed)
    rep["meta"] = {"seed": args.seed, "bootstrap": args.bootstrap,
                   "determinista": True, "sin_agentes": True}

    if args.cross_overlap:
        rep["cross_overlap"] = medir_cross_overlap(df, args.forward, args.bootstrap, args.seed)

    out_path = args.out or str(SCRATCH / f"medicion_{args.señal}.json")
    with open(out_path, "w") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False, default=str)

    # resumen humano a stdout
    a = rep["activa"]["dist"]
    b_type = rep.get("baseline_pivot_type", "ALL")
    print(f"SEÑAL: {args.señal}  (forward={args.forward})")
    if a.get("n", 0) == 0:
        # PROTOCOLO DIAMANTES: N=0 no crashea el reporte; se documenta como diamante.
        print("  Activa: N=0 → DIAMANTE ANECDOTAL (sin activaciones en la muestra)")
        print("  ⚠️  Sin activaciones: analizar el contexto del evento individualmente.")
        return
    print(f"  Activa: N={a['n']}  mean={a['mean']:+.4f}  med={a['median']:+.4f}")
    print(f"  P5/P95: {a['p5']:+.4f} / {a['p95']:+.4f}")
    print(f"  Win rate: {rep['activa']['wl'].get('win_rate', 0):.1%}")
    print(f"  CI95 media: {rep['activa']['ci_mean']['ci_lo']:+.4f} .. {rep['activa']['ci_mean']['ci_hi']:+.4f}")
    print(f"  Δ vs baseline ({b_type}): {rep.get('delta_media', 0):+.4f}")

    if "lift_vs_baseline" in rep and rep["lift_vs_baseline"]:
        for pt, l_info in rep["lift_vs_baseline"].items():
            print(f"  LIFT ({pt}): {l_info['lift']:.3f}x  (P(cae|señal)={l_info['pct_cae_activa']:.1f}% vs baseline={l_info['pct_cae_no_activa']:.1f}%, N={l_info['n_activa']})")

    if "triada" in rep and rep["triada"]:
        tr = rep["triada"]
        c50 = tr["cascade_50"]
        c75 = tr["cascade_75"]
        dur = tr["duracion_bars"]
        print(f"  Tríada ZigZag: zz25 mean={tr['zz25']['mean']:+.4f} (WR={tr['zz25']['win_rate']:.1%})")
        print(f"  Cascade reach: zz50={c50['rate_activa']:.1%} (Δ={c50['delta']:+.1%}) | zz75={c75['rate_activa']:.1%} (Δ={c75['delta']:+.1%})")
        print(f"  Duración pierna: {dur['mean']:.1f} bars (med={dur['median']:.1f}, base={dur['baseline_mean']:.1f})")

    if "anticipacion_zigzag" in rep and rep["anticipacion_zigzag"]:
        az = rep["anticipacion_zigzag"]
        print(f"  Anticipación temporal: media={az['mean_dias']:.1f} días  mediana={az['median_dias']:.1f} días  ({az['pct_anticipados']}% con anticipación > 0)")
        print(f"  Percentiles: P5={az['p5_dias']:.0f}  P25={az['p25_dias']:.0f}  P75={az['p75_dias']:.0f}  P95={az['p95_dias']:.0f}  (N={az['n_total']})")
    if "drawdown_anticipacion" in rep and rep["drawdown_anticipacion"]:
        et = rep["drawdown_anticipacion"].get("entrada_temprana", {})
        st = rep["drawdown_anticipacion"].get("salida_tardia", {})
        if et.get("forward_mean") is not None:
            print(f"  Entrada temprana: forward={et['forward_mean']:+.4f}  MAE={et.get('mae_medio',0):+.4f}  (N={et['n']})")
        if st.get("forward_mean") is not None:
            print(f"  Salida tardía:    forward={st['forward_mean']:+.4f}  MAE={st.get('mae_medio',0):+.4f}  (N={st['n']})")
    if "capture_ratio" in rep and rep["capture_ratio"]:
        cr = rep["capture_ratio"]
        print(f"  Capture ratio: {cr['ratio']:.2f} (fwd {cr['fwd_mean']:+.4f} / |leg| {cr['abs_leg_mean']:.4f})")
        for pt_name, pt_data in cr.get("por_pivot_type", {}).items():
            print(f"    {pt_name}: ratio={pt_data['ratio']:.2f} (fwd={pt_data['fwd_mean']:+.4f}, |leg|={pt_data['abs_leg_mean']:.4f}, N={pt_data['n']})")
    if "punteria" in rep and rep["punteria"]:
        for esc, p in sorted(rep["punteria"].items()):
            print(f"  Puntería {esc}: capture={p['capture_ratio']:.2f}  WR={p['win_rate']:.1%}  MAE={p.get('mae_medio',0):+.4f}  (N={p['n']})")
    if "offset_entrada" in rep and rep["offset_entrada"]:
        for off, v in sorted(rep["offset_entrada"].items()):
            print(f"  Offset {off}: capture={v['capture_ratio']:.2f}  forward={v['forward_mean']:+.4f}  WR={v['win_rate']:.1%}  (N={v['n']})")

    # Lookback crash
    if "lookback_crash" in rep and rep["lookback_crash"]:
        print(f"  Lookback crash [T0-3, T0+2] — señales que anteceden a caídas:")
        for esc, lc in sorted(rep["lookback_crash"].items()):
            print(f"    {esc} (N={lc['n_crashes']}):")
            top = sorted(lc["señales"].items(), key=lambda x: -x[1]["pct_crashes"])[:5]
            for sig_name, info in top:
                print(f"      {sig_name:25s}  {info['pct_crashes']:5.1f}% de caídas")

    # Duración desglose
    if "duracion_desglose" in rep and rep["duracion_desglose"]:
        dd = rep["duracion_desglose"]
        c = dd["cortas"]
        l = dd["largas"]
        if c.get("fwd_mean") is not None and l.get("fwd_mean") is not None:
            print(f"  Duración desglose (med={dd['mediana_bars']:.0f}b): cortas={c['fwd_mean']:+.4f} WR={c['wr']:.0%} N={c['n']} | largas={l['fwd_mean']:+.4f} WR={l['wr']:.0%} N={l['n']} | Δ={dd['delta']:+.4f}")

    # D2×D3 desglose compacto con CI95
    if "desglose_d2d3" in rep and rep["desglose_d2d3"]:
        for station, info in rep["desglose_d2d3"].items():
            d2 = info["d2_velocity"]
            d3 = info["d3_station_vol"]
            d2_ci = info.get("d2_ci95")
            d3_ci = info.get("d3_ci95")
            if d2:
                best_d2 = max(d2.items(), key=lambda x: x[1]["mean"])
                worst_d2 = min(d2.items(), key=lambda x: x[1]["mean"])
                ci_tag = ""
                if d2_ci:
                    ci_tag = f" CI95=[{d2_ci['ci_lo']:+.4f},{d2_ci['ci_hi']:+.4f}] {'✅' if d2_ci['significativo'] else '❌'}"
                print(f"  D2 {station} [{info['d1_dominante']}]: best={best_d2[0]} ({best_d2[1]['mean']:+.4f} WR={best_d2[1]['wr']:.0%} N={best_d2[1]['n']}) | worst={worst_d2[0]} ({worst_d2[1]['mean']:+.4f} WR={worst_d2[1]['wr']:.0%} N={worst_d2[1]['n']}){ci_tag}")
            if d3:
                best_d3 = max(d3.items(), key=lambda x: x[1]["mean"])
                worst_d3 = min(d3.items(), key=lambda x: x[1]["mean"])
                ci_tag = ""
                if d3_ci:
                    ci_tag = f" CI95=[{d3_ci['ci_lo']:+.4f},{d3_ci['ci_hi']:+.4f}] {'✅' if d3_ci['significativo'] else '❌'}"
                print(f"  D3 {station} [{info['d1_dominante']}]: best={best_d3[0]} ({best_d3[1]['mean']:+.4f} WR={best_d3[1]['wr']:.0%} N={best_d3[1]['n']}) | worst={worst_d3[0]} ({worst_d3[1]['mean']:+.4f} WR={worst_d3[1]['wr']:.0%} N={worst_d3[1]['n']}){ci_tag}")

    # Estabilidad por Ciclo de Mercado
    if "estabilidad_ciclo" in rep and rep["estabilidad_ciclo"]:
        parts = []
        for cycle, vals in rep["estabilidad_ciclo"].items():
            if vals.get("mean") is not None:
                parts.append(f"{cycle}={vals['mean']:+.4f} WR={vals['wr']:.0%} N={vals['n']}")
        if parts:
            print(f"  Estabilidad por ciclo: {' | '.join(parts)}")
    # Macro-eras
    if "estabilidad_macro_era" in rep and rep["estabilidad_macro_era"]:
        parts = []
        for era, vals in rep["estabilidad_macro_era"].items():
            if vals.get("mean") is not None:
                parts.append(f"{era}={vals['mean']:+.4f} WR={vals['wr']:.0%} N={vals['n']}")
        if parts:
            print(f"  Macro-eras: {' | '.join(parts)}")
    # Ficha de credibilidad
    if "ficha_credibilidad" in rep:
        fc = rep["ficha_credibilidad"]
        print(f"  ── FICHA CREDIBILIDAD ──")
        print(f"  Grade: {fc['grade'][:60]}")
        print(f"  WR={fc['win_rate']:.1%} vs BL({fc['baseline_type']})={fc['baseline_wr']:.1%} → LIFT={fc['lift']}")
        print(f"  p-value Fisher: {fc['p_value_fisher']}")
        if fc.get('dsr_pvalue'):
            print(f"  DSR p-value: {fc['dsr_pvalue']}")
        if fc.get('diamante'):
            d = fc['diamante']
            print(f"  💎 DIAMANTE: p_raw={d['p_raw']} CI95=[{d['ci_lo']}, {d['ci_hi']}] direccional={d['ci_direccional']}")
        print(f"  Structural break: {fc['structural_break']}")
        print(f"  ▶ ACCIÓN: {fc['accion_recomendada']}")

    if "costo_tarde" in rep and rep["costo_tarde"].get("costo_medio") is not None:
        print(f"  Costo retraso k=1d: {rep['costo_tarde']['costo_medio']:+.4f} (N={rep['costo_tarde']['n']})")
    if "timing_temprano" in rep and "estadistica" in rep["timing_temprano"]:
        tt = rep["timing_temprano"]["estadistica"]
        print(f"  MAE intra-trade medio: {tt.get('mean', 0):+.4f} (med: {tt.get('median', 0):+.4f}, P5: {tt.get('p5', 0):+.4f})")

    # Cross-signal overlap
    if "cross_overlap" in rep and rep["cross_overlap"]:
        print(f"\n  CROSS-SIGNAL OVERLAP ({len(rep['cross_overlap'])} pares con N≥5):")
        for ov in sorted(rep["cross_overlap"], key=lambda x: x["ambas"]["mean"], reverse=True):
            a_info = ov["solo_a"]
            b_info = ov["solo_b"]
            both = ov["ambas"]
            tag_icon = "+" if ov["tag"] == "ADITIVA" else "−" if ov["tag"] == "CANCELATORIA" else "="
            print(f"    [{tag_icon}] {ov['par']:45s} N={both['n']:3d} ({ov['pct_overlap']:.0f}%) | ambas={both['mean']:+.4f} WR={both['wr']:.0%} | solo_a={(a_info['mean'] or 0):+.4f} solo_b={(b_info['mean'] or 0):+.4f} | {ov['tag']}")

    print(f"  Reporte: {out_path}")
