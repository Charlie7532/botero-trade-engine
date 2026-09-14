#!/usr/bin/env python3
"""
Fix Dossiers: Replace STK_ with MKT_ and replace legacy tiers with Opus sigma x N Matrix
"""
import re
from pathlib import Path

DOSSIERS_DIR = Path("/root/botero-trade/.hermes/dossiers/capa1_personalidades")

def process_file(p: Path):
    txt = p.read_text(encoding="utf-8")
    orig = txt

    # 1. Replace STK_ with MKT_ everywhere
    txt = txt.replace("STK_", "MKT_")

    # 2. Update table headers
    txt = txt.replace("| Tier Cred (§3.3) |", "| Tier Cred (Opus σ×N) |")
    txt = txt.replace("| Acción Canónica (Regla 20) |", "| Directiva Canónica MKT (Regla 20) |")

    # 3. Replace legacy tiers in markdown table rows
    # Pattern: | ... | N | `TIER` | ...
    # Match integer N and tier
    def tier_sub(match):
        prefix = match.group(1)
        n = int(match.group(2))
        old_tier = match.group(3)
        suffix = match.group(4)
        if n < 10:
            new_tier = "DIAMOND"
        elif n < 30:
            new_tier = "UNUSUAL_COMBO"
        else:
            new_tier = "CONFIRMED_ALERT"
        return f"{prefix}{n} | `{new_tier}`{suffix}"

    # Pattern covers: | {n} | `{old_tier}` |
    tier_pattern = re.compile(r'(\|\s*)(\d+)(\s*\|\s*`)(ANECDOTAL|LOW|MODERATE|HIGH|ROBUST)(`\s*\|)')
    txt = tier_pattern.sub(tier_sub, txt)

    # 4. Clean up any lingering text references to ANECDOTAL / LOW
    txt = txt.replace("`ANECDOTAL`", "`DIAMOND`")
    txt = txt.replace("`LOW`", "`DIAMOND`")
    txt = txt.replace("`MODERATE`", "`UNUSUAL_COMBO`")

    p.write_text(txt, encoding="utf-8")
    print(f"Fixed {p.name}: STK_ count={orig.count('STK_')} -> {txt.count('STK_')}, ANECDOTAL count={orig.count('ANECDOTAL')} -> {txt.count('ANECDOTAL')}")

if __name__ == "__main__":
    for f in sorted(DOSSIERS_DIR.glob("*.md")):
        process_file(f)
