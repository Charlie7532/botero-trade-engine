#!/usr/bin/env python3
"""
Audit Triad Delta
=================
Compares S5 and S5V Triad probability tables and relative modifiers across
git revisions or against the working tree.

Resolves the methodological flaw where comparing `HEAD:` against a committed
working tree yields 0 delta. Allows fixed base revisions (--base <rev>)
and persists a permanent audit artifact (JSON and CSV) for full reproducibility.
"""
import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE_REV = "a8f11aa"  # Pre-retraining commit on 2026-10-07
DEFAULT_TARGET_REV = "HEAD"
FILES_TO_AUDIT = [
    "backend/modules/entry_decision/domain/rules/s5v_triad_table.json",
    "backend/modules/entry_decision/domain/rules/s5v_relative_modifier.json",
    "backend/modules/entry_decision/domain/rules/s5_triad_table.json",
    "backend/modules/entry_decision/domain/rules/s5_relative_modifier.json",
]


def load_file_content(path_str: str, rev: str | None = None) -> dict:
    """Load JSON from git revision or working tree."""
    if rev and rev.upper() != "WORKTREE":
        cmd = ["git", "show", f"{rev}:{path_str}"]
        content = subprocess.check_output(cmd, text=True)
        return json.loads(content)
    with open(path_str, "r", encoding="utf-8") as f:
        return json.load(f)


def audit_triad(base_rev: str, target_rev: str) -> tuple[dict, list[dict]]:
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_rev": base_rev,
        "target_rev": target_rev,
        "files": {},
    }
    all_delta_rows = []

    for path_str in FILES_TO_AUDIT:
        print("=" * 80)
        print(f"AUDITORIA DELTA: {path_str} ({base_rev} -> {target_rev})")
        print("=" * 80)

        base_json = load_file_content(path_str, base_rev)
        target_json = load_file_content(path_str, target_rev)

        base_gen = base_json.get("generated_at")
        target_gen = target_json.get("generated_at")
        print(f"Base   ({base_rev:10s}) generated_at: {base_gen}")
        print(f"Target ({target_rev:10s}) generated_at: {target_gen}")

        file_report = {
            "base_generated_at": base_gen,
            "target_generated_at": target_gen,
            "type": "cells" if "cells" in target_json else "bins",
        }

        if "cells" in target_json:
            base_cells = base_json.get("cells", {})
            target_cells = target_json.get("cells", {})
            deltas = []

            for k, tgt_c in target_cells.items():
                bsc_c = base_cells.get(k, {})
                tgt_g = tgt_c.get("global", tgt_c)
                bsc_g = bsc_c.get("global", bsc_c)

                p_bot_tgt = tgt_g.get("P_bot_5_0", 0.0)
                p_bot_bsc = bsc_g.get("P_bot_5_0", 0.0)
                p_top_tgt = tgt_g.get("P_top_5_0", 0.0)
                p_top_bsc = bsc_g.get("P_top_5_0", 0.0)
                n_tgt = tgt_g.get("n", 0)
                n_bsc = bsc_g.get("n", 0)

                d_p_bot = p_bot_tgt - p_bot_bsc
                d_p_top = p_top_tgt - p_top_bsc
                d_n = n_tgt - n_bsc

                if abs(d_p_bot) > 0.0001 or abs(d_p_top) > 0.0001 or d_n != 0:
                    delta_info = {
                        "file": Path(path_str).name,
                        "cell": k,
                        "n_target": n_tgt,
                        "delta_n": d_n,
                        "p_bot_target": round(p_bot_tgt, 4),
                        "delta_p_bot": round(d_p_bot, 4),
                        "delta_p_top": round(d_p_top, 4),
                    }
                    deltas.append(delta_info)
                    all_delta_rows.append(delta_info)

            file_report["total_cells"] = len(target_cells)
            file_report["cells_with_delta"] = len(deltas)
            file_report["pct_with_delta"] = round(len(deltas) / max(1, len(target_cells)) * 100.0, 2)
            file_report["top_displacements"] = sorted(deltas, key=lambda x: abs(x["delta_p_bot"]), reverse=True)[:15]

            print(f"Total celdas: {len(target_cells)} | Celdas con delta: {len(deltas)} ({file_report['pct_with_delta']}%)")
            if deltas:
                print(f"\nTop 10 mayores desplazamientos de P_bot_5_0:")
                print(f"{'Celda':20s} | {'N (Tgt)':8s} | {'Delta N':8s} | {'P_bot_5_0':10s} | {'Delta P_bot':12s} | {'Delta P_top':12s}")
                print("-" * 75)
                for d in file_report["top_displacements"][:10]:
                    print(f"{d['cell']:20s} | {d['n_target']:8d} | {d['delta_n']:+8d} | {d['p_bot_target']:10.3f} | {d['delta_p_bot']:+12.4f} | {d['delta_p_top']:+12.4f}")
            else:
                print("Celdas 100% idénticas.")

        elif "bins" in target_json:
            base_bins = base_json.get("bins", {})
            target_bins = target_json.get("bins", {})
            file_report["bins"] = {}
            print(f"Bins comparados: {list(target_bins.keys())}")
            for b, tgt_v in target_bins.items():
                bsc_v = base_bins.get(b, {})
                file_report["bins"][b] = {
                    "n_target": tgt_v.get("n"),
                    "n_base": bsc_v.get("n"),
                    "bot_factor_target": tgt_v.get("bot_factor"),
                    "bot_factor_base": bsc_v.get("bot_factor"),
                }
                print(f"  Bin {b}: Target N={tgt_v.get('n')} (Base N={bsc_v.get('n')}) | bot_factor Target={tgt_v.get('bot_factor')} Base={bsc_v.get('bot_factor')}")

        report["files"][path_str] = file_report

    return report, all_delta_rows


def main():
    parser = argparse.ArgumentParser(description="Audit Triad table and modifier deltas across revisions.")
    parser.add_argument("--base", default=DEFAULT_BASE_REV, help=f"Base revision (default: {DEFAULT_BASE_REV})")
    parser.add_argument("--target", default=DEFAULT_TARGET_REV, help=f"Target revision (default: {DEFAULT_TARGET_REV})")
    parser.add_argument("--out-json", default="backend/scripts/logs/triad_delta_audit_report.json", help="Path to write JSON report")
    parser.add_argument("--out-csv", default="backend/scripts/logs/triad_delta_audit_report.csv", help="Path to write CSV report")
    args = parser.parse_args()

    report, delta_rows = audit_triad(args.base, args.target)

    # Save JSON report
    out_json_path = Path(args.out_json)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved JSON report: {out_json_path}")

    # Save CSV report
    out_csv_path = Path(args.out_csv)
    if delta_rows:
        keys = ["file", "cell", "n_target", "delta_n", "p_bot_target", "delta_p_bot", "delta_p_top"]
        with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(delta_rows)
        print(f"Saved CSV report:  {out_csv_path} ({len(delta_rows)} rows)")


if __name__ == "__main__":
    main()
