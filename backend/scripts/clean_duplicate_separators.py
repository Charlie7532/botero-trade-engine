#!/usr/bin/env python3
"""
Clean Duplicate Separators in Reference Documents
=================================================
Removes duplicate horizontal rules ('---\\n---') in all .agents/references/*_intelligence.md files.
"""
import re
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
ref_dir = root_dir / ".agents/references"

def clean_file(file_path: Path):
    if not file_path.exists():
        return
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Clean double separators
    cleaned = re.sub(r'---\s*\n\s*---', '---', content)
    
    if cleaned != content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(cleaned)
        print(f"🧹 Cleaned separators in {file_path.name}")

def main():
    for file_path in ref_dir.glob("*_intelligence.md"):
        clean_file(file_path)

if __name__ == "__main__":
    main()
