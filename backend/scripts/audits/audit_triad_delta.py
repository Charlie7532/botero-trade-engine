import json
import subprocess
from pathlib import Path

def audit_file(path_str):
    print("=" * 80)
    print(f"AUDITORIA DELTA: {path_str}")
    print("=" * 80)
    head_content = subprocess.check_output(["git", "show", f"HEAD:{path_str}"], text=True)
    head_json = json.loads(head_content)
    with open(path_str, "r") as f:
        wt_json = json.load(f)

    print(f"HEAD generated_at: {head_json.get('generated_at')}")
    print(f"WT   generated_at: {wt_json.get('generated_at')}")

    if "cells" in wt_json:
        head_cells = head_json.get("cells", {})
        wt_cells = wt_json.get("cells", {})
        deltas = []
        for k, wt_c in wt_cells.items():
            hd_c = head_cells.get(k, {})
            wt_glob = wt_c.get("global", wt_c)
            hd_glob = hd_c.get("global", hd_c)

            p_bot_wt = wt_glob.get("P_bot_5_0", 0.0)
            p_bot_hd = hd_glob.get("P_bot_5_0", 0.0)
            p_top_wt = wt_glob.get("P_top_5_0", 0.0)
            p_top_hd = hd_glob.get("P_top_5_0", 0.0)
            n_wt = wt_glob.get("n", 0)
            n_hd = hd_glob.get("n", 0)

            d_p_bot = p_bot_wt - p_bot_hd
            d_p_top = p_top_wt - p_top_hd
            d_n = n_wt - n_hd
            if abs(d_p_bot) > 0.0001 or abs(d_p_top) > 0.0001 or d_n != 0:
                deltas.append((k, d_n, d_p_bot, d_p_top, p_bot_wt, n_wt))

        print(f"Total celdas: {len(wt_cells)} | Celdas con delta: {len(deltas)} ({len(deltas)/max(1, len(wt_cells)):.1%})")
        if deltas:
            print(f"\nTop 10 mayores desplazamientos de P_bot_5_0:")
            print(f"{'Celda':20s} | {'N (WT)':8s} | {'Delta N':8s} | {'P_bot_5_0':10s} | {'Delta P_bot':12s} | {'Delta P_top':12s}")
            print("-" * 75)
            for k, dn, dpb, dpt, pb, n in sorted(deltas, key=lambda x: abs(x[2]), reverse=True)[:10]:
                print(f"{k:20s} | {n:8d} | {dn:+8d} | {pb:10.3f} | {dpb:+12.4f} | {dpt:+12.4f}")
        else:
            print("Celdas 100% idénticas.")

    elif "bins" in wt_json:
        head_bins = head_json.get("bins", {})
        wt_bins = wt_json.get("bins", {})
        print(f"Bins comparados: {list(wt_bins.keys())}")
        for b, wt_v in wt_bins.items():
            hd_v = head_bins.get(b, {})
            print(f"  Bin {b}: WT N={wt_v.get('n')} (HEAD N={hd_v.get('n')}) | bot_factor WT={wt_v.get('bot_factor')} HEAD={hd_v.get('bot_factor')}")


if __name__ == "__main__":
    audit_file("backend/modules/entry_decision/domain/rules/s5v_triad_table.json")
    audit_file("backend/modules/entry_decision/domain/rules/s5v_relative_modifier.json")
    audit_file("backend/modules/entry_decision/domain/rules/s5_triad_table.json")
    audit_file("backend/modules/entry_decision/domain/rules/s5_relative_modifier.json")
