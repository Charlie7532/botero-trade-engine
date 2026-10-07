import json
import subprocess
from pathlib import Path

def run_bilateral_audit():
    rules_dir = Path("backend/modules/entry_decision/domain/rules")
    stations = ["vix", "vvix", "pcr", "fg", "sv5_turbulence", "skew", "credit", "yield_curve", "rotation", "bsi", "dxy"]

    print("=" * 80)
    print("AUDITORIA DE DELTA BILATERAL: HEAD vs WORKTREE")
    print("=" * 80)
    header = f"{'Estacion':16s} | {'HEAD legs':10s} | {'WT legs':10s} | {'Delta':8s} | {'Estados modificados':22s}"
    print(header)
    print("-" * len(header))

    for s in stations:
        rel_path = f"backend/modules/entry_decision/domain/rules/{s}_fact_store.json"
        try:
            head_json_str = subprocess.check_output(["git", "show", f"HEAD:{rel_path}"], text=True)
            head_d = json.loads(head_json_str)
            head_states = head_d.get("states", {})
            head_n_legs = sum(v.get("zigzag_kinematic", {}).get("zz25", {}).get("n_pos", 0) + v.get("zigzag_kinematic", {}).get("zz25", {}).get("n_neg", 0) for v in head_states.values())
        except Exception:
            head_n_legs = -1
            head_states = {}

        p = rules_dir / f"{s}_fact_store.json"
        with open(p, "r", encoding="utf-8") as f:
            wt_d = json.load(f)
        wt_states = wt_d.get("states", {})
        wt_n_legs = sum(v.get("zigzag_kinematic", {}).get("zz25", {}).get("n_pos", 0) + v.get("zigzag_kinematic", {}).get("zz25", {}).get("n_neg", 0) for v in wt_states.values())

        delta = wt_n_legs - head_n_legs

        mod_count = 0
        p_bull_shifts = []
        for k, v in wt_states.items():
            if k in head_states:
                old_zk = head_states[k].get("zigzag_kinematic", {}).get("zz25", {})
                new_zk = v.get("zigzag_kinematic", {}).get("zz25", {})
                if old_zk != new_zk:
                    mod_count += 1
                    if "p_bull" in old_zk and "p_bull" in new_zk:
                        p_bull_shifts.append(abs(new_zk["p_bull"] - old_zk["p_bull"]))
            else:
                mod_count += 1

        max_shift = max(p_bull_shifts) if p_bull_shifts else 0.0
        pct_mod = (mod_count / max(1, len(wt_states))) * 100.0
        print(f"{s:16s} | {head_n_legs:10d} | {wt_n_legs:10d} | {delta:+8d} | {mod_count:3d}/{len(wt_states):3d} ({pct_mod:5.1f}%) max_dp={max_shift:.3f}")

if __name__ == "__main__":
    run_bilateral_audit()
