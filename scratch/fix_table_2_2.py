#!/usr/bin/env python3
import re
from pathlib import Path

DOSSIERS_DIR = Path("/root/botero-trade/.hermes/dossiers/capa1_personalidades")

def fix_content(txt: str) -> str:
    # 1. Ensure all STK_ are MKT_
    txt = txt.replace("STK_", "MKT_")

    # 2. Update Table headers if not updated
    txt = txt.replace("| Tier Cred (§3.3) |", "| Tier Cred (Opus σ×N) |")
    txt = txt.replace("| Acción Canónica (Regla 20) |", "| Directiva Canónica MKT (Regla 20) |")

    # 3. Fix Table 2.2 rows
    # Each row looks like:
    # | `0__0__3` | `LABEL1` | `LABEL2` | `LABEL3` | +46.1% | 100.0% | 1.7 | 5 | ...
    lines = txt.split("\n")
    fixed_lines = []
    in_subtable_2_2 = False

    for line in lines:
        if "### 2.2 Tríadas Singulares" in line:
            in_subtable_2_2 = True
            fixed_lines.append(line)
            continue
        elif line.startswith("## 3. ") or line.startswith("> 📌 **Regla de Lookup"):
            in_subtable_2_2 = False
            fixed_lines.append(line)
            continue

        if in_subtable_2_2 and line.strip().startswith("| `"):
            # This is a triad row in 2.2!
            # Example format:
            # | `state_key` | `d1` | `d2` | `d3` | edge | hr | rr | n | tier_col...
            # Let's extract with regex
            # r"\|\s*(`\d__\d__\d`)\s*\|\s*(`[^`]+`)\s*\|\s*(`[^`]+`)\s*\|\s*(`[^`]+`)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*(\d+)\s*\|(.*)"
            m = re.match(r"^\|\s*(`\d__\d__\d`)\s*\|\s*(`[^`]+`)\s*\|\s*(`[^`]+`)\s*\|\s*(`[^`]+`)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*(\d+)\s*\|(.*)$", line.strip())
            if m:
                sk, d1, d2, d3, edge, hr, rr, n_str, rest = m.groups()
                n = int(n_str)
                if n < 10:
                    tier = "DIAMOND"
                elif n < 30:
                    tier = "UNUSUAL_COMBO"
                else:
                    tier = "CONFIRMED_ALERT"

                # In rest, clean up any lingering old tier words and ensure format is: | `TIER` | directive |
                # Look for the directive text starting with **
                d_idx = rest.find("**")
                if d_idx != -1:
                    directive = rest[d_idx:].strip()
                    if directive.endswith("|"):
                        directive = directive[:-1].strip()
                    fixed_line = f"| {sk} | {d1} | {d2} | {d3} | {edge.strip()} | {hr.strip()} | {rr.strip()} | {n} | `{tier}` | {directive} |"
                    fixed_lines.append(fixed_line)
                    continue
        fixed_lines.append(line)

    return "\n".join(fixed_lines)

if __name__ == "__main__":
    for f in sorted(DOSSIERS_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        fixed = fix_content(content)
        f.write_text(fixed, encoding="utf-8")
        print(f"Processed {f.name}: STK_ count={fixed.count('STK_')}, ANECDOTAL count={fixed.count('ANECDOTAL')}")
