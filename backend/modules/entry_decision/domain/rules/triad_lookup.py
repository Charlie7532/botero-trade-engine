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

    triad_key: str          # "<<|<<|<<|+"
    sector_etf: str         # "XLK"
    th_bin: str             # "<<"
    fi_bin: str             # "<<"
    tw_bin: str             # "<<"
    dir_bin: str            # "+"

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
_s5v_triad_table: Optional[dict] = None
_s5v_rel_modifier: Optional[dict] = None


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


def _get_s5v_triad_table() -> dict:
    global _s5v_triad_table
    if _s5v_triad_table is None:
        _s5v_triad_table = _load_json("s5v_triad_table.json")
    return _s5v_triad_table


def _get_s5v_rel_modifier() -> dict:
    global _s5v_rel_modifier
    if _s5v_rel_modifier is None:
        _s5v_rel_modifier = _load_json("s5v_relative_modifier.json")
    return _s5v_rel_modifier


def lookup_triad_signal(
    th_val: float,
    fi_val: float,
    tw_val: float,
    sector_etf: str,
    spy_fi_val: float = 50.0,
    tw_prev_val: Optional[float] = None,
) -> TriadSignal:
    """
    Classify TH/FI/TW into bins, lookup triad table, apply relative modifier.

    Args:
        th_val: S5_TH value (0-100) for the sector.
        fi_val: S5_FI value (0-100) for the sector.
        tw_val: S5_TW value (0-100) for the sector.
        sector_etf: Sector ETF symbol (e.g. 'XLK') or 'SPY'.
        spy_fi_val: S5FI value for SPY (0-100), for relative modifier.
        tw_prev_val: Previous S5_TW value (0-100) for direction detection.

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
    
    # Direction defaults to "-" if previous is None or if no change
    if tw_prev_val is not None:
        direction = "+" if tw_val > tw_prev_val else "-"
    else:
        direction = "-"

    triad_key = f"{th_bin}|{fi_bin}|{tw_bin}|{direction}"

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
        dir_bin=direction,
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


def lookup_s5v_triad_signal(
    vth_val: float,
    vfi_val: float,
    vtw_val: float,
    sector_etf: str,
    spy_vfi_val: float = 50.0,
    vtw_prev_val: Optional[float] = None,
    roc_5d: Optional[float] = None,
) -> TriadSignal:
    """
    Classify S5V TH/FI/TW into bins, lookup volume triad table, apply RoM relative modifier.

    v2.0: Z-Score per-sector normalization + RoC modifier dimension.

    Args:
        vth_val: S5V_TH value (0-100) for the sector.
        vfi_val: S5V_FI value (0-100) for the sector.
        vtw_val: S5V_TW value (0-100) for the sector.
        sector_etf: Sector ETF symbol (e.g. 'XLK') or 'SPY'.
        spy_vfi_val: S5V_FI value for SPY (0-100), for relative modifier.
        vtw_prev_val: Previous S5V_TW value (0-100) for direction detection.
        roc_5d: 5-day change of RoM deviation (rel_fi[t] - rel_fi[t-5]).
                None = skip RoC modifier. Computed by caller from Vault history.

    Returns:
        TriadSignal with probabilities, lift, bias, and context.
    """
    table = _get_s5v_triad_table()
    rel_mod = _get_s5v_rel_modifier()

    # ── Step 1: Classify bins ──
    bin_edges = table["bin_edges"]
    labels = table["bin_labels"]

    th_bin = _classify_bin(vth_val, bin_edges["TH"], labels)
    fi_bin = _classify_bin(vfi_val, bin_edges["FI"], labels)
    tw_bin = _classify_bin(vtw_val, bin_edges["TW"], labels)

    if vtw_prev_val is not None:
        direction = "+" if vtw_val > vtw_prev_val else "-"
    else:
        direction = "-"

    triad_key = f"{th_bin}|{fi_bin}|{tw_bin}|{direction}"

    # ── Step 2: Lookup cell with fallback L1 → L2 ──
    cell = table["cells"].get(triad_key, {})
    baseline = table["baselines"]["global"]

    if sector_etf == "SPY":
        l1_key = "SPY"
    else:
        l1_key = _ETF_TO_TIER_LABEL.get(sector_etf)

    stats = None
    level = "L2_global"

    if l1_key and l1_key in cell:
        stats = cell[l1_key]
        level = f"L1_{l1_key}"

    if stats is None and "global" in cell:
        stats = cell["global"]
        level = "L2_global"

    if stats is None:
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

    # ── Step 4: RoM (Rest of Market) Subtraction + Z-Score ──
    SECTOR_WEIGHTS = {
        "XLK": 65 / 500,
        "XLF": 72 / 500,
        "XLV": 64 / 500,
        "XLY": 52 / 500,
        "XLI": 78 / 500,
        "XLP": 38 / 500,
        "XLE": 23 / 500,
        "XLU": 30 / 500,
        "XLB": 28 / 500,
        "XLRE": 31 / 500,
        "XLC": 23 / 500,
    }

    if sector_etf != "SPY" and sector_etf in SECTOR_WEIGHTS:
        w = SECTOR_WEIGHTS[sector_etf]
        rom_vfi = (spy_vfi_val - w * vfi_val) / (1.0 - w)
        rel_fi = vfi_val - rom_vfi
    else:
        rel_fi = 0.0

    # ── Step 4b: Z-Score normalization per-sector (v2.0) ──
    modifier_version = rel_mod.get("version", "1.0")
    labels = rel_mod.get("bin_labels", ["<<", "<", "~", ">", ">>"])

    if modifier_version >= "2.0" and "sector_params" in rel_mod:
        # v2.0: Z-Score per-sector for relative modifier
        s_params = rel_mod["sector_params"].get(sector_etf, {})
        dev_mean = s_params.get("dev_mean", 0.0)
        dev_std = s_params.get("dev_std", 1.0)
        z_dev = (rel_fi - dev_mean) / dev_std if dev_std > 0 else 0.0

        z_edges = rel_mod.get("z_bin_edges", [-2.0, -1.0, 1.0, 2.0])
        rel_bin = _classify_bin(z_dev, z_edges, labels)

        z_data = rel_mod.get("z_bins", rel_mod.get("bins", {})).get(rel_bin, {})
        rel_bot_factor = z_data.get("bot_factor", 1.0)
        rel_top_factor = z_data.get("top_factor", 1.0)

        # ── Step 4c: RoC modifier (second multiplicative layer) ──
        roc_bot_factor = 1.0
        roc_top_factor = 1.0
        roc_bin = "~"
        roc_z = 0.0
        if "roc_bins" in rel_mod and roc_5d is not None:
            roc_std = rel_mod.get("roc_global_std", 1.0)
            roc_z = roc_5d / roc_std if roc_std > 0 else 0.0
            roc_edges = rel_mod.get("roc_z_bin_edges", [-1.5, -0.5, 0.5, 1.5])
            roc_bin = _classify_bin(roc_z, roc_edges, labels)
            roc_data = rel_mod["roc_bins"].get(roc_bin, {})
            roc_bot_factor = roc_data.get("bot_factor", 1.0)
            roc_top_factor = roc_data.get("top_factor", 1.0)

        adj_p_bot = min(p_bot_50 * rel_bot_factor * roc_bot_factor, 1.0)
        adj_p_top = min(p_top_50 * rel_top_factor * roc_top_factor, 1.0)
    else:
        # v1.0 legacy: fixed pp bins
        rel_edges = rel_mod.get("bin_edges", [-30, -10, 10, 30])
        rel_bin = _classify_bin(rel_fi, rel_edges, labels)
        z_dev = 0.0
        roc_z = 0.0
        roc_bin = "~"

        rel_data = rel_mod.get("bins", {}).get(rel_bin, {})
        rel_bot_factor = rel_data.get("bot_factor", 1.0)
        rel_top_factor = rel_data.get("top_factor", 1.0)
        roc_bot_factor = 1.0
        roc_top_factor = 1.0

        adj_p_bot = min(p_bot_50 * rel_bot_factor, 1.0)
        adj_p_top = min(p_top_50 * rel_top_factor, 1.0)

    # ── Step 5: Build context label ──
    label_parts = []
    if net_bias > 0.10:
        label_parts.append(
            f"🏆 S5V_ACCUMULATION: {triad_key} "
            f"P_bot={p_bot_50:.0%} (lift={lift_bot:.1f}x) "
            f"N={n} [{level}]"
        )
    elif net_bias < -0.10:
        label_parts.append(
            f"⚠️ S5V_DISTRIBUTION: {triad_key} "
            f"P_top={p_top_50:.0%} (lift={lift_top:.1f}x) "
            f"N={n} [{level}]"
        )
    else:
        label_parts.append(
            f"S5V_NEUTRAL: {triad_key} "
            f"bias={net_bias:+.1%} N={n} [{level}]"
        )

    if sector_etf != "SPY":
        label_parts.append(
            f"(Z_dev={z_dev:+.1f} [{rel_bin}] "
            f"bot×{rel_bot_factor:.2f}"
        )
        if roc_bin != "~":
            label_parts.append(
                f" RoC_z={roc_z:+.1f} [{roc_bin}] roc×{roc_bot_factor:.2f}"
            )
        label_parts.append(")")

    return TriadSignal(
        triad_key=triad_key,
        sector_etf=sector_etf,
        th_bin=th_bin,
        fi_bin=fi_bin,
        tw_bin=tw_bin,
        dir_bin=direction,
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
        rel_bot_factor=round(rel_bot_factor * roc_bot_factor, 3),
        rel_top_factor=round(rel_top_factor * roc_top_factor, 3),
        adj_p_bot_50=round(adj_p_bot, 4),
        adj_p_top_50=round(adj_p_top, 4),
        context_label=" ".join(label_parts),
    )

