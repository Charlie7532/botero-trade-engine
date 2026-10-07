#!/usr/bin/env python3
"""
Audit Bilateral Delta
=====================
Compares the 11 METAR fact stores against a base git revision to quantify
the exact kinematic delta and state modifications (e.g. pre-remediation contaminated
1,680 legs vs post-remediation clean 1,584 legs).

Supports explicit base/target revisions and persists an audit artifact (JSON/CSV).
"""
import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE_REV = "4fab158"  # Pre-remediation commit (contaminated 1,680 legs)
DEFAULT_TARGET_REV = "HEAD"
STATIONS = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence",
    "skew", "credit", "yield_curve", "rotation", "bsi", "dxy"
]


def load_fact_store(station: str, rev: str | None = None) -> dict:
    rel_path = f"backend/modules/entry_decision/domain/rules/{station}_fact_store.json"
    if rev and rev.upper() != "WORKTREE":
        cmd = ["git", "show", f"{rev}:{rel_path}"]
        content = subprocess.check_output(cmd, text=True)
        return json.loads(content)
    with open(rel_path, "r", encoding="utf-8") as f:
        return json.load(f)


def audit_bilateral(base_rev: str, target_rev: str) -> tuple[dict, list[dict]]:
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_rev": base_rev,
        "target_rev": target_rev,
        "stations": {},
    }
    rows = []

    print("=" * 80)
    print(f"AUDITORIA DE DELTA BILATERAL ({base_rev} -> {target_rev})")
    print("=" * 80)
    header = f"{'Estacion':16s} | {'Base legs':10s} | {'Tgt legs':10s} | {'Delta':8s} | {'Estados modificados':22s} | {'Max dp_bull':12s}"
    print(header)
    print("-" * len(header))

    for s in STATIONS:
        try:
            base_d = load_fact_store(s, base_rev)
            base_states = base_d.get("states", {})
            base_legs = sum(
                v.get("zigzag_kinematic", {}).get("zz25", {}).get("n_pos", 0) +
                v.get("zigzag_kinematic", {}).get("zz25", {}).get("n_neg", 0)
                for v in base_states.values()
            )
        except Exception:
            base_legs = -1
            base_states = {}

        tgt_d = load_fact_store(s, target_rev)
        tgt_states = tgt_d.get("states", {})
        tgt_legs = sum(
            v.get("zigzag_kinematic", {}).get("zz25", {}).get("n_pos", 0) +
            v.get("zigzag_kinematic", {}).get("zz25", {}).get("n_neg", 0)
            for v in tgt_states.values()
        )

        delta = tgt_legs - base_legs

        mod_count = 0
        p_bull_shifts = []
        for k, v in tgt_states.items():
            if k in base_states:
                old_zk = base_states[k].get("zigzag_kinematic", {}).get("zz25", {})
                new_zk = v.get("zigzag_kinematic", {}).get("zz25", {})
                if old_zk != new_zk:
                    mod_count += 1
                    if "p_bull" in old_zk and "p_bull" in new_zk:
                        p_bull_shifts.append(abs(new_zk["p_bull"] - old_zk["p_bull"]))
            else:
                mod_count += 1

        max_shift = max(p_bull_shifts) if p_bull_shifts else 0.0
        pct_mod = (mod_count / max(1, len(tgt_states))) * 100.0

        print(f"{s:16s} | {base_legs:10d} | {tgt_legs:10d} | {delta:+8d} | {mod_count:3d}/{len(tgt_states):3d} ({pct_mod:5.1f}%) | max_dp={max_shift:.4f}")

        stat_info = {
            "station": s,
            "base_legs": base_legs,
            "target_legs": tgt_legs,
            "delta_legs": delta,
            "states_modified": mod_count,
            "total_states": len(tgt_states),
            "pct_modified": round(pct_mod, 2),
            "max_dp_bull": round(max_shift, 4),
        }
        report["stations"][s] = stat_info
        rows.append(stat_info)

    return report, rows


def main():
    parser = argparse.ArgumentParser(description="Audit Bilateral Fact Stores delta across revisions.")
    parser.add_argument("--base", default=DEFAULT_BASE_REV, help=f"Base revision (default: {DEFAULT_BASE_REV})")
    parser.add_argument("--target", default=DEFAULT_TARGET_REV, help=f"Target revision (default: {DEFAULT_TARGET_REV})")
    parser.add_argument("--out-json", default="backend/scripts/logs/bilateral_delta_audit_report.json", help="Path to write JSON report")
    parser.add_argument("--out-csv", default="backend/scripts/logs/bilateral_delta_audit_report.csv", help="Path to write CSV report")
    args = parser.parse_args()

    report, rows = audit_bilateral(args.base, args.target)

    # Save JSON report
    out_json_path = Path(args.out_json)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved JSON report: {out_json_path}")

    # Save CSV report
    out_csv_path = Path(args.out_csv)
    if rows:
        keys = list(rows[0].keys())
        with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved CSV report:  {out_csv_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
