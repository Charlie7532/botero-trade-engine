"""
Market METAR Broadcast Formatter — Pure Domain Service
======================================================
Formats the full Market Weather Observatory output as a structured ASCII
broadcast suitable for terminal/CLI consumption, logging, and AI agents.

Consumes:
  - ConvergenceReport (METAR compositor output)
  - TAF composite dict (from taf_service.compute_composite_taf)
  - SIGMET hazard list (from market_sigmet_hazard_service)
  - NOTAM incident list (from notam_incident_service)

Clean Architecture: Pure formatting function. No I/O, no decisions.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime


def format_market_broadcast(
    report: 'ConvergenceReport',
    taf_composite: Dict[str, Any],
    sigmets: list,
    notam_data: List[Dict[str, Any]],
) -> str:
    """Format the complete Market Weather Observatory broadcast.

    Args:
        report: ConvergenceReport from ConvergenceCompositor.compute()
        taf_composite: Dict from compute_composite_taf() or compute_composite_taf_from_summaries()
        sigmets: List of SigmetHazard objects (with .to_dict())
        notam_data: List of NOTAM dicts (pre-serialized)

    Returns:
        Multi-line ASCII broadcast string
    """
    lines = []

    # ── Header ────────────────────────────────────────────────────────
    guidance_icon = _guidance_icon(report.unified_guidance)
    lines.append("=" * 80)
    lines.append(f"  {guidance_icon} MARKET WEATHER OBSERVATORY — BROADCAST TERMINAL")
    lines.append("=" * 80)
    lines.append(f"  📅 Date: {report.as_of_date}  |  ⏱️ Computed in {report.execution_time_ms:.0f}ms")
    lines.append(f"  📡 Stations: {report.active_stations}/{report.total_stations} active")
    if report.blind_stations:
        lines.append(f"  ⚠️  Blind: {', '.join(report.blind_stations[:3])}")
    lines.append("-" * 80)

    # ── Executive Diagnosis ──────────────────────────────────────────
    lines.append("")
    lines.append("  EXECUTIVE DIAGNOSIS")
    lines.append(f"  ├── Guidance:   {report.unified_guidance} ({report.guidance_horizon})")
    lines.append(f"  ├── Confidence: {report.confidence_level}")
    lines.append(f"  ├── D1 Votes:   {report.bullish_vote_ratio:.0%} bull / {report.bearish_vote_ratio:.0%} bear")
    lines.append(f"  ├── EV(1d):     {report.composite_ev_1d:+.5f}  |  EV(5d): {report.composite_ev_5d:+.5f}")
    lines.append(f"  ├── Rarity:     {report.rarity_score:.2f}  ({len(report.extreme_territory_stations)} stations extreme)")
    lines.append(f"  ├── Cascade:    {report.cascade_tercile} (c50={report.cascade_conviction_50:+.3f}, c75={report.cascade_conviction_75:+.3f})")

    # Family sequence phase
    fs = report.family_sequence or {}
    phase = fs.get("phase", "NEUTRAL")
    lines.append(f"  └── Phase:      {phase}")

    # ── TAF Forecast Cone ─────────────────────────────────────────────
    lines.append("")
    lines.append("-" * 80)
    lines.append("  TAF — TERMINAL MARKET FORECAST")
    composite_regime = taf_composite.get("composite_divergence_regime", "EQUILIBRIUM")
    ev_accel = taf_composite.get("composite_ev_acceleration", 0.0)
    n_cones = taf_composite.get("n_stations", 0)
    lines.append(f"  ├── Regime:       {composite_regime}")
    lines.append(f"  ├── EV Accel:     {ev_accel:+.6f} {'↑ maturing' if ev_accel > 0.005 else '↓ decaying' if ev_accel < -0.005 else '→ stable'}")
    lines.append(f"  ├── Asymmetry:    {taf_composite.get('composite_asymmetry', 1.0):.3f}")
    lines.append(f"  ├── Convergence:  {taf_composite.get('composite_convergence', 0.0):+.4f}")
    n_bull_s = taf_composite.get("n_bullish_scaling", 0)
    n_bear_s = taf_composite.get("n_bearish_scaling", 0)
    lines.append(f"  └── Scaling:      {n_bull_s} bull / {n_bear_s} bear  ({n_cones} cones)")

    # ── Station Matrix ────────────────────────────────────────────────
    lines.append("")
    lines.append("-" * 80)
    lines.append("  STATION TELEMETRY MATRIX")
    lines.append(f"  {'Station':<16} {'State':>10} {'D1V':>4} {'EV(1d)':>9} {'EV(5d)':>9} {'Tier':>8} {'Alert':>8}")
    lines.append("  " + "─" * 68)

    for code, summary in report.station_summaries.items():
        state = summary.get("state_key", "—")[:10]
        vote = summary.get("d1_vote", 0)
        vote_sym = "▲" if vote > 0 else "▼" if vote < 0 else "●"
        ev1 = summary.get("ev_1d", 0.0)
        ev5 = summary.get("ev_5d", 0.0)
        tier = summary.get("tier", "—")[:8]
        alert = summary.get("alert_priority", "NONE")[:8]
        lines.append(f"  {code:<16} {state:>10} {vote_sym:>4} {ev1:>+9.5f} {ev5:>+9.5f} {tier:>8} {alert:>8}")

    # ── Cross-Signals ─────────────────────────────────────────────────
    if report.cross_signals:
        lines.append("")
        lines.append("-" * 80)
        lines.append(f"  CROSS-STATION SIGNALS ({len(report.cross_signals)})")
        for sig in report.cross_signals:
            lines.append(f"    ⚡ {sig}")

    # ── SIGMET ────────────────────────────────────────────────────────
    lines.append("")
    lines.append("-" * 80)
    sigmet_status = "CLEAR" if not sigmets else "⚠️ HAZARD WARNING"
    lines.append(f"  SIGMET — SEVERE MARKET WEATHER: {sigmet_status}")
    if sigmets:
        for s in sigmets:
            sd = s.to_dict() if hasattr(s, 'to_dict') else s
            lines.append(f"    🚨 [{sd.get('severity', '?')}] {sd.get('hazard_type', '?')}: {sd.get('title', '?')}")
            lines.append(f"       Action: {sd.get('action_code', '?')}")
    else:
        lines.append("    ✅ No severe weather hazards detected.")

    # ── NOTAM ─────────────────────────────────────────────────────────
    lines.append("")
    lines.append("-" * 80)
    notam_status = "CLEAR" if not notam_data else f"⚠️ {len(notam_data)} ACTIVE"
    lines.append(f"  NOTAM — OPERATIONAL DISRUPTIONS: {notam_status}")
    if notam_data:
        for n in notam_data:
            sev = n.get("severity", "?")
            icon = "🚨" if sev == "CRITICAL" else "⚠️"
            lines.append(f"    {icon} [{n.get('notam_id', '?')}] {n.get('incident_type', '?')} ({sev})")
            lines.append(f"       {n.get('title', '?')}")
    else:
        lines.append("    ✅ All systems operational. No disruptions.")

    # ── Situational Orientation ───────────────────────────────────────
    lines.append("")
    lines.append("-" * 80)
    lines.append("  SITUATIONAL ORIENTATION")
    lines.append(f"  📦 Open Positions: {report.open_positions_summary}")
    lines.append(f"  💰 New Capital:    {report.new_allocations_summary}")

    # ── Stale Stations ────────────────────────────────────────────────
    if report.stale_stations:
        lines.append("")
        lines.append("-" * 80)
        lines.append(f"  ⏳ STALE STATIONS ({len(report.stale_stations)})")
        for st in report.stale_stations:
            lines.append(f"    • {st['station']:16s} last={st.get('station_date', '?')} (lag={st.get('lag_days', '?')}d)")

    lines.append("=" * 80)
    return "\n".join(lines)


def _guidance_icon(guidance: str) -> str:
    """Return an icon for the unified guidance code."""
    icons = {
        "MKT_ACCUMULATE_STRUCTURAL": "🟢",
        "MKT_BUY_DIP_TACTICAL": "🔵",
        "MKT_HOLD_STABLE": "🟡",
        "MKT_TRIM_TACTICAL": "🟠",
    }
    return icons.get(guidance, "⚪")
