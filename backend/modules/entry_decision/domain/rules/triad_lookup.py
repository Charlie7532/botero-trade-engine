"""
S5 Triad Lookup — Pure Domain Rule
====================================
Reads s5_triad_table.json and s5_relative_modifier.json,
classifies current TH/FI/TW values into bins, looks up
P(near_turn | state) with Tier Pooling fallback (L1→L2).

Zero infrastructure dependencies. Pure function, fully testable.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).parent

# Tier name mapping (ETF → tier label used in JSON keys)
_ETF_TO_TIER_LABEL: dict[str, str] = {
    "XLP": "Defensive", "XLV": "Defensive", "XLU": "Defensive",
    "XLRE": "Defensive", "XLB": "Defensive",
    "XLE": "Mixed", "XLF": "Mixed", "XLC": "Mixed",
    "XLK": "Cyclical", "XLY": "Cyclical", "XLI": "Cyclical",
}


@dataclass(frozen=True)
class TriadSignal:
    """Result of a triad table lookup."""

    triad_key: str          # "<<|<<|<<"
    sector_etf: str         # "XLK"
    th_bin: str             # "<<"
    fi_bin: str             # "<<"
    tw_bin: str             # "<<"

    # ZZ coincidence probabilities (from table)
    p_bot_25: float
    p_bot_50: float
    p_bot_75: float
    p_top_25: float
    p_top_50: float
    p_top_75: float

    # Derived
    lift_bot_50: float      # vs global baseline
    lift_top_50: float
    net_bias: float         # P_bot_50 - P_top_50

    n_samples: int
    level: str              # "L1_Defensive", "L1_SPY", "L2_global"

    # Relative modifier
    rel_fi_bin: str         # "<<", "<", "~", ">", ">>"
    rel_bot_factor: float   # Multiplicative factor for P_bot
    rel_top_factor: float   # Multiplicative factor for P_top

    # Adjusted probabilities (triad × relative modifier)
    adj_p_bot_50: float
    adj_p_top_50: float

    context_label: str      # Human-readable summary


def _classify_bin(value: float, edges: list[float], labels: list[str]) -> str:
    """Classify a value into one of N bins based on edges."""
    for i, edge in enumerate(edges):
        if value < edge:
            return labels[i]
    return labels[-1]


def _load_json(filename: str) -> dict:
    """Load a JSON file from the rules directory."""
    path = _RULES_DIR / filename
    with open(path) as f:
        return json.load(f)


# ── Lazy-loaded table singletons ──
_triad_table: Optional[dict] = None
_rel_modifier: Optional[dict] = None


def _get_triad_table() -> dict:
    global _triad_table
    if _triad_table is None:
        _triad_table = _load_json("s5_triad_table.json")
    return _triad_table


def _get_rel_modifier() -> dict:
    global _rel_modifier
    if _rel_modifier is None:
        _rel_modifier = _load_json("s5_relative_modifier.json")
    return _rel_modifier


def lookup_triad_signal(
    th_val: float,
    fi_val: float,
    tw_val: float,
    sector_etf: str,
    spy_fi_val: float = 50.0,
) -> TriadSignal:
    """
    Classify TH/FI/TW into bins, lookup triad table, apply relative modifier.

    Args:
        th_val: S5_TH value (0-100) for the sector.
        fi_val: S5_FI value (0-100) for the sector.
        tw_val: S5_TW value (0-100) for the sector.
        sector_etf: Sector ETF symbol (e.g. 'XLK') or 'SPY'.
        spy_fi_val: S5FI value for SPY (0-100), for relative modifier.

    Returns:
        TriadSignal with probabilities, lift, bias, and context.
    """
    table = _get_triad_table()
    rel_mod = _get_rel_modifier()

    # ── Step 1: Classify bins ──
    bin_edges = table["bin_edges"]
    labels = table["bin_labels"]

    th_bin = _classify_bin(th_val, bin_edges["TH"], labels)
    fi_bin = _classify_bin(fi_val, bin_edges["FI"], labels)
    tw_bin = _classify_bin(tw_val, bin_edges["TW"], labels)
    triad_key = f"{th_bin}|{fi_bin}|{tw_bin}"

    # ── Step 2: Lookup cell with fallback L1 → L2 ──
    cell = table["cells"].get(triad_key, {})
    baseline = table["baselines"]["global"]

    # Determine L1 key
    if sector_etf == "SPY":
        l1_key = "SPY"
    else:
        l1_key = _ETF_TO_TIER_LABEL.get(sector_etf)

    # Try L1 (tier/SPY), fallback to L2 (global)
    stats = None
    level = "L2_global"

    if l1_key and l1_key in cell:
        stats = cell[l1_key]
        level = f"L1_{l1_key}"

    if stats is None and "global" in cell:
        stats = cell["global"]
        level = "L2_global"

    if stats is None:
        # State never observed — use baseline
        stats = baseline
        level = "L2_baseline"

    # ── Step 3: Extract probabilities ──
    p_bot_25 = stats.get("P_bot_2_5", 0.0)
    p_bot_50 = stats.get("P_bot_5_0", 0.0)
    p_bot_75 = stats.get("P_bot_7_5", 0.0)
    p_top_25 = stats.get("P_top_2_5", 0.0)
    p_top_50 = stats.get("P_top_5_0", 0.0)
    p_top_75 = stats.get("P_top_7_5", 0.0)
    n = stats.get("n", 0)

    base_bot = baseline.get("P_bot_5_0", 0.01)
    base_top = baseline.get("P_top_5_0", 0.01)
    lift_bot = round(p_bot_50 / base_bot, 2) if base_bot > 0 else 0.0
    lift_top = round(p_top_50 / base_top, 2) if base_top > 0 else 0.0
    net_bias = round(p_bot_50 - p_top_50, 4)

    # ── Step 4: Relative modifier ──
    rel_fi = fi_val - spy_fi_val
    rel_edges = rel_mod.get("bin_edges", [-30, -10, 10, 30])
    rel_labels = rel_mod.get("bin_labels", labels)
    rel_bin = _classify_bin(rel_fi, rel_edges, rel_labels)

    rel_data = rel_mod.get("bins", {}).get(rel_bin, {})
    rel_bot_factor = rel_data.get("bot_factor", 1.0)
    rel_top_factor = rel_data.get("top_factor", 1.0)

    # Adjusted probabilities (capped at 1.0)
    adj_p_bot = min(p_bot_50 * rel_bot_factor, 1.0)
    adj_p_top = min(p_top_50 * rel_top_factor, 1.0)

    # ── Step 5: Build context label ──
    label_parts = []

    if net_bias > 0.10:
        label_parts.append(
            f"🏆 TRIAD_ACCUMULATION: {triad_key} "
            f"P_bot={p_bot_50:.0%} (lift={lift_bot:.1f}x) "
            f"N={n} [{level}]"
        )
    elif net_bias < -0.10:
        label_parts.append(
            f"⚠️ TRIAD_DISTRIBUTION: {triad_key} "
            f"P_top={p_top_50:.0%} (lift={lift_top:.1f}x) "
            f"N={n} [{level}]"
        )
    else:
        label_parts.append(
            f"TRIAD_NEUTRAL: {triad_key} "
            f"bias={net_bias:+.1%} N={n} [{level}]"
        )

    if sector_etf != "SPY":
        label_parts.append(
            f"(rel_FI={rel_fi:+.1f}pp [{rel_bin}] "
            f"bot×{rel_bot_factor:.2f} top×{rel_top_factor:.2f})"
        )

    return TriadSignal(
        triad_key=triad_key,
        sector_etf=sector_etf,
        th_bin=th_bin,
        fi_bin=fi_bin,
        tw_bin=tw_bin,
        p_bot_25=p_bot_25,
        p_bot_50=p_bot_50,
        p_bot_75=p_bot_75,
        p_top_25=p_top_25,
        p_top_50=p_top_50,
        p_top_75=p_top_75,
        lift_bot_50=lift_bot,
        lift_top_50=lift_top,
        net_bias=net_bias,
        n_samples=n,
        level=level,
        rel_fi_bin=rel_bin,
        rel_bot_factor=rel_bot_factor,
        rel_top_factor=rel_top_factor,
        adj_p_bot_50=round(adj_p_bot, 4),
        adj_p_top_50=round(adj_p_top, 4),
        context_label=" ".join(label_parts),
    )
