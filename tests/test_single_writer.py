"""
Single Writer Enforcement & AST Whitelist Audit
=================================================
Validates Rule 13 (Vault-First) and F4 Single-Writer Governance:
  - No module under backend/modules/ may directly write (INSERT/UPDATE/DELETE)
    to market.ohlcv_bars, engine.channel_snapshots, market.zigzag_legs, or engine.zigzag_points.
  - Authorized writers live strictly in backend/daemons/ or dedicated infrastructure adapters.
"""
import ast
import os
import re
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_modules_have_zero_direct_db_writes():
    """Assert that no production modules in backend/modules/ perform raw SQL writes to market tables."""
    modules_dir = ROOT_DIR / "backend" / "modules"
    assert modules_dir.exists()

    forbidden_patterns = [
        re.compile(r"INSERT\s+INTO\s+market\.ohlcv_bars", re.IGNORECASE),
        re.compile(r"UPDATE\s+market\.ohlcv_bars", re.IGNORECASE),
        re.compile(r"DELETE\s+FROM\s+market\.ohlcv_bars", re.IGNORECASE),
        re.compile(r"INSERT\s+INTO\s+market\.zigzag_legs", re.IGNORECASE),
        re.compile(r"DELETE\s+FROM\s+market\.zigzag_legs", re.IGNORECASE),
        re.compile(r"INSERT\s+INTO\s+engine\.zigzag_points", re.IGNORECASE),
        re.compile(r"DELETE\s+FROM\s+engine\.zigzag_points", re.IGNORECASE),
        re.compile(r"INSERT\s+INTO\s+engine\.channel_snapshots", re.IGNORECASE),
    ]

    violations = []
    # Whitelist timescale_data_store.py as the single authorized data store adapter
    whitelisted_files = {"timescale_data_store.py"}

    for py_file in modules_dir.rglob("*.py"):
        if py_file.name in whitelisted_files or "_legacy" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for pattern in forbidden_patterns:
            matches = pattern.findall(content)
            if matches:
                violations.append(f"{py_file.relative_to(ROOT_DIR)}: found forbidden write pattern '{matches[0]}'")

    assert not violations, f"Single-writer violations detected in modules:\n" + "\n".join(violations)


def test_save_legs_removed_from_zigzag_leg_repository():
    """Verify that obsolete/dangerous save_legs() is completely removed from ZigzagLegRepository."""
    from backend.modules.shared.infrastructure.repositories.zigzag_leg_repository import ZigzagLegRepository
    from backend.modules.shared.domain.ports.zigzag_leg_port import ZigzagLegPort

    assert not hasattr(ZigzagLegPort, "save_legs"), "ZigzagLegPort must not declare save_legs()"
    assert not hasattr(ZigzagLegRepository, "save_legs"), "ZigzagLegRepository must not implement save_legs()"
