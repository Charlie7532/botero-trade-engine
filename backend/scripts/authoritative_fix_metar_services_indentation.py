"""
Authoritative Fix for Indentation in all 9 METAR Services
"""
from pathlib import Path
import re

SERVICES_DIR = Path("backend/modules/entry_decision/domain/services")

for f in SERVICES_DIR.glob("*_metar_service.py"):
    lines = f.read_text(encoding="utf-8").splitlines()
    new_lines = []
    
    # Determine base indentation for s_val block
    in_service = False
    for i, line in enumerate(lines):
        if "s_val = " in line:
            # Find indentation of line above
            prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
            indent_str = " " * (prev_indent if prev_indent > 0 else 8)
            new_lines.append(indent_str + "s_val = " + line.split("s_val = ")[1].strip())
            # Fix next 6 lines
            j = i + 1
            while j < len(lines) and any(kw in lines[j] for kw in ["vol_5d", "vol_20d", "s_vol_norm", "vol_norm", "vol_d3", "guidance ="]):
                new_lines.append(indent_str + lines[j].strip())
                j += 1
            # Skip the lines we just handled
            while i + 1 < j:
                lines.pop(i + 1)
        else:
            new_lines.append(line)
            
    f.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"✅ Indentation fixed in {f.name}")

print("All 9 METAR services fixed.")
