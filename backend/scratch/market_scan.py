"""
Comprehensive Market Scan — May 1, 2026
Gate 1: Rotation Intelligence (Weinstein Stage Analysis)
Gate 2: Quality Candidate Screening
Gate 3: Speculative Opportunity Detection
"""
import json
import sys
import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────
# GATE 1: ROTATION INTELLIGENCE — Weinstein Stage Analysis
# ─────────────────────────────────────────────────────────────────

SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Healthcare", "XLI": "Industrials", "XLY": "Consumer Disc.",
    "XLP": "Consumer Staples", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLC": "Comm. Services", "XLB": "Materials"
}

INTERNATIONAL_ETFS = {
    "EFA": "Developed ex-US", "EEM": "Emerging", "FXI": "China",
    "EWZ": "Brazil", "EWJ": "Japan", "INDA": "India",
    "VGK": "Europe", "EWG": "Germany"
}

ASSET_CLASS_ETFS = {
    "SPY": "US Equities", "TLT": "Long Treasuries", "GLD": "Gold",
    "USO": "Oil", "UUP": "Dollar", "HYG": "High Yield", "LQD": "Inv. Grade"
}

def classify_weinstein_stage(prices, volumes, current_price):
    """Classify into Weinstein Stage 1-4 using 30-week MA."""
    if len(prices) < 150:
        return "INSUFFICIENT DATA", {}

    prices_s = pd.Series(prices)
    ma_150 = prices_s.rolling(150).mean()
    ma_50 = prices_s.rolling(50).mean()

    current_ma150 = ma_150.iloc[-1]
    prev_ma150 = ma_150.iloc[-20] if len(ma_150) > 20 else ma_150.iloc[-1]
    ma_slope = (current_ma150 - prev_ma150) / prev_ma150 * 100

    # Price position relative to 30-week MA
    price_vs_ma = (current_price - current_ma150) / current_ma150 * 100

    # Volume trend (recent 20d vs prior 20d)
    if len(volumes) >= 40:
        recent_vol = np.mean(volumes[-20:])
        prior_vol = np.mean(volumes[-40:-20])
        vol_ratio = recent_vol / prior_vol if prior_vol > 0 else 1.0
    else:
        vol_ratio = 1.0

    # Relative strength vs SPY will be computed separately
    details = {
        "price_vs_ma150_pct": round(price_vs_ma, 2),
        "ma150_slope_pct": round(ma_slope, 2),
        "volume_ratio": round(vol_ratio, 2),
        "current_price": round(current_price, 2),
        "ma_150": round(current_ma150, 2)
    }

    # Classification logic
    if price_vs_ma > 2 and ma_slope > 0.5:
        stage = "STAGE 2 — Advancing"
    elif price_vs_ma < -2 and ma_slope < -0.5:
        stage = "STAGE 4 — Declining"
    elif abs(price_vs_ma) <= 3 and abs(ma_slope) <= 0.5:
        stage = "STAGE 1 — Basing"
    elif price_vs_ma < 2 and ma_slope < 0.3 and price_vs_ma > -3:
        stage = "STAGE 3 — Topping"
    elif price_vs_ma > 0 and ma_slope > 0:
        stage = "STAGE 2 — Advancing"
    elif price_vs_ma < 0 and ma_slope < 0:
        stage = "STAGE 4 — Declining"
    else:
        stage = "STAGE 1 — Basing"  # Transitional

    return stage, details


def compute_relative_strength(symbol_prices, benchmark_prices, window=60):
    """RS = symbol return / benchmark return over window."""
    if len(symbol_prices) < window or len(benchmark_prices) < window:
        return 0.0
    sym_ret = (symbol_prices[-1] - symbol_prices[-window]) / symbol_prices[-window]
    bench_ret = (benchmark_prices[-1] - benchmark_prices[-window]) / benchmark_prices[-window]
    if bench_ret == 0:
        return 0.0
    return round(sym_ret / bench_ret, 3) if bench_ret != 0 else 0.0


print("=" * 80)
print(f"BOTERO TRADE — COMPREHENSIVE MARKET SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 80)

# Fetch all ETF data (1 year for 30-week MA + buffer)
all_symbols = list(SECTOR_ETFS.keys()) + list(INTERNATIONAL_ETFS.keys()) + list(ASSET_CLASS_ETFS.keys())
print(f"\nFetching data for {len(all_symbols)} ETFs...")

data = {}
for sym in all_symbols:
    try:
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="1y")
        if not hist.empty:
            data[sym] = {
                "prices": hist["Close"].tolist(),
                "volumes": hist["Volume"].tolist(),
                "current": hist["Close"].iloc[-1],
                "high_52w": hist["Close"].max(),
                "low_52w": hist["Close"].min()
            }
    except Exception as e:
        print(f"  Error fetching {sym}: {e}")

spy_prices = data.get("SPY", {}).get("prices", [])

# ─── STAGE ANALYSIS ───
print("\n" + "=" * 80)
print("GATE 1: ROTATION INTELLIGENCE — WEINSTEIN STAGE MAP")
print("=" * 80)

stage_results = {}
for category_name, etf_map in [("SECTORS", SECTOR_ETFS), ("INTERNATIONAL", INTERNATIONAL_ETFS), ("ASSET CLASS", ASSET_CLASS_ETFS)]:
    print(f"\n{'─' * 40}")
    print(f"  {category_name}")
    print(f"{'─' * 40}")
    print(f"{'ETF':<6} {'Name':<18} {'Stage':<25} {'Price vs MA150':>14} {'MA Slope':>10} {'RS60':>8}")
    print(f"{'─'*6} {'─'*18} {'─'*25} {'─'*14} {'─'*10} {'─'*8}")

    for sym, name in etf_map.items():
        if sym not in data:
            continue
        d = data[sym]
        stage, details = classify_weinstein_stage(d["prices"], d["volumes"], d["current"])
        rs = compute_relative_strength(d["prices"], spy_prices, 60) if spy_prices else 0.0
        details["rs_60"] = rs
        stage_results[sym] = {"name": name, "stage": stage, "details": details, "rs": rs}

        emoji = "🟢" if "2" in stage else ("🔴" if "4" in stage else ("🟡" if "3" in stage else "⚪"))
        print(f"{sym:<6} {name:<18} {stage:<25} {details.get('price_vs_ma150_pct', 0):>13.1f}% {details.get('ma150_slope_pct', 0):>9.1f}% {rs:>7.2f}")

# ─── PRING CYCLE PHASE ───
print(f"\n{'─' * 40}")
print("  PRING INTERMARKET CYCLE ASSESSMENT")
print(f"{'─' * 40}")

bond_stage = stage_results.get("TLT", {}).get("stage", "N/A")
equity_stage = stage_results.get("SPY", {}).get("stage", "N/A")
gold_stage = stage_results.get("GLD", {}).get("stage", "N/A")
oil_stage = stage_results.get("USO", {}).get("stage", "N/A")
dollar_stage = stage_results.get("UUP", {}).get("stage", "N/A")
hyg_stage = stage_results.get("HYG", {}).get("stage", "N/A")

print(f"  Bonds (TLT):     {bond_stage}")
print(f"  Equities (SPY):  {equity_stage}")
print(f"  Gold (GLD):      {gold_stage}")
print(f"  Oil (USO):       {oil_stage}")
print(f"  Dollar (UUP):    {dollar_stage}")
print(f"  Credit (HYG):    {hyg_stage}")

# Identify advancing sectors for quality candidate screening
advancing_sectors = [sym for sym, r in stage_results.items() if "2" in r["stage"] and sym in SECTOR_ETFS]
print(f"\n  ✅ Stage 2 Sectors (FOCUS): {', '.join(advancing_sectors) if advancing_sectors else 'None'}")
declining_sectors = [sym for sym, r in stage_results.items() if "4" in r["stage"] and sym in SECTOR_ETFS]
print(f"  ❌ Stage 4 Sectors (VETO): {', '.join(declining_sectors) if declining_sectors else 'None'}")

# ─────────────────────────────────────────────────────────────────
# GATE 2: QUALITY CANDIDATE SCREENING
# ─────────────────────────────────────────────────────────────────

# Tollkeeper candidates — essential infrastructure, payment networks,
# exchanges, data monopolies, healthcare/pharma tollkeepers
QUALITY_CANDIDATES = {
    # Payment networks (tollkeepers)
    "V": "Visa", "MA": "Mastercard",
    # Exchanges & data monopolies
    "SPGI": "S&P Global", "MCO": "Moody's", "ICE": "Intercontinental Exchange",
    "CME": "CME Group", "MSCI": "MSCI Inc",
    # Infrastructure tollkeepers
    "ASML": "ASML Holdings", "AVGO": "Broadcom",
    # Software tollkeepers
    "MSFT": "Microsoft", "ORCL": "Oracle", "ADBE": "Adobe",
    # Healthcare tollkeepers
    "UNH": "UnitedHealth", "ISRG": "Intuitive Surgical", "TMO": "Thermo Fisher",
    # Defense/Aero (government tollkeepers)
    "LMT": "Lockheed Martin", "RTX": "RTX Corp",
    # Insurance (essential)
    "BRK-B": "Berkshire Hathaway",
    # Consumer essential (pricing power)
    "COST": "Costco",
    # Infrastructure
    "NEE": "NextEra Energy", "AMT": "American Tower",
}

print("\n\n" + "=" * 80)
print("GATE 2: QUALITY CANDIDATES — TOLLKEEPER SCREENING")
print("=" * 80)
print(f"\n{'Ticker':<8} {'Name':<24} {'Price':>8} {'52W Hi':>8} {'52W Lo':>8} {'vs 200MA':>9} {'vs 52H':>8} {'Zone':>12}")
print(f"{'─'*8} {'─'*24} {'─'*8} {'─'*8} {'─'*8} {'─'*9} {'─'*8} {'─'*12}")

quality_results = {}
for sym, name in QUALITY_CANDIDATES.items():
    try:
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="1y")
        if hist.empty:
            continue

        current = hist["Close"].iloc[-1]
        high_52 = hist["Close"].max()
        low_52 = hist["Close"].min()
        ma_200 = hist["Close"].rolling(200).mean().iloc[-1] if len(hist) >= 200 else hist["Close"].mean()
        pct_vs_200ma = (current - ma_200) / ma_200 * 100
        pct_from_high = (current - high_52) / high_52 * 100

        # Simple zone classification (will be refined with GF Value in production)
        # Using distance from 52w high as proxy
        if pct_from_high < -25:
            zone = "BUY ZONE"
        elif pct_from_high < -15:
            zone = "ADD ZONE"
        elif pct_from_high < -5:
            zone = "FAIR VALUE"
        elif pct_from_high >= -5:
            zone = "REDUCE"
        else:
            zone = "WATCH"

        # Override: if below 200 DMA, it's not quality buy territory (PTJ filter)
        if pct_vs_200ma < -5:
            zone = "BELOW 200DMA ⚠️"

        quality_results[sym] = {
            "name": name,
            "current": round(current, 2),
            "high_52": round(high_52, 2),
            "low_52": round(low_52, 2),
            "pct_vs_200ma": round(pct_vs_200ma, 2),
            "pct_from_high": round(pct_from_high, 2),
            "zone": zone
        }

        zone_emoji = "🟢" if "BUY" in zone else ("🔵" if "ADD" in zone else ("⚪" if "FAIR" in zone else ("🟡" if "REDUCE" in zone else "🔴")))
        print(f"{sym:<8} {name:<24} {current:>8.2f} {high_52:>8.2f} {low_52:>8.2f} {pct_vs_200ma:>8.1f}% {pct_from_high:>7.1f}% {zone_emoji} {zone}")

    except Exception as e:
        print(f"{sym:<8} {name:<24} ERROR: {e}")

# ─────────────────────────────────────────────────────────────────
# GATE 3: SPECULATIVE OPPORTUNITY DETECTION
# ─────────────────────────────────────────────────────────────────

# Look for recent momentum breakouts, unusual volume, VCP patterns
SPECULATIVE_UNIVERSE = [
    "NVDA", "AMD", "SMCI", "MSTR", "COIN", "PLTR", "RKLB", "IONQ", "RGTI",
    "APP", "HOOD", "SOFI", "MARA", "RIOT", "CLSK", "AFRM", "UPST", "SQ",
    "CRWD", "NET", "SNOW", "DDOG", "MDB", "ZS", "PANW",
    "SHOP", "SE", "GRAB", "NU", "MELI",
    "UBER", "ABNB", "DASH", "LYFT",
    "TSLA", "RIVN", "LCID",
    "ARM", "TSM", "MU", "LRCX", "KLAC",
    "HIMS", "CELH", "DUOL", "TMDX",
    "GEV", "VST", "CEG", "NRG",  # Energy/nuclear
]

print("\n\n" + "=" * 80)
print("SPECULATIVE SCAN — MOMENTUM & BREAKOUT DETECTION")
print("=" * 80)
print(f"\n{'Ticker':<7} {'Price':>8} {'5D%':>7} {'20D%':>7} {'vs200MA':>8} {'Vol Ratio':>10} {'Gap fr Hi':>9} {'Signal':>18}")
print(f"{'─'*7} {'─'*8} {'─'*7} {'─'*7} {'─'*8} {'─'*10} {'─'*9} {'─'*18}")

spec_results = {}
for sym in SPECULATIVE_UNIVERSE:
    try:
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="6mo")
        if hist.empty or len(hist) < 50:
            continue

        current = hist["Close"].iloc[-1]
        price_5d_ago = hist["Close"].iloc[-6] if len(hist) >= 6 else current
        price_20d_ago = hist["Close"].iloc[-21] if len(hist) >= 21 else current
        ma_200_val = hist["Close"].rolling(200).mean().iloc[-1] if len(hist) >= 200 else hist["Close"].rolling(50).mean().iloc[-1]
        high_52 = hist["Close"].max()

        ret_5d = (current - price_5d_ago) / price_5d_ago * 100
        ret_20d = (current - price_20d_ago) / price_20d_ago * 100
        pct_vs_200 = (current - ma_200_val) / ma_200_val * 100
        pct_from_hi = (current - high_52) / high_52 * 100

        # Volume analysis
        recent_vol = hist["Volume"].iloc[-5:].mean()
        avg_vol = hist["Volume"].iloc[-50:-5].mean()
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

        # Signal classification
        signals = []
        if ret_5d > 8 and vol_ratio > 1.5:
            signals.append("BREAKOUT 🔥")
        if ret_5d > 5 and pct_vs_200 > 0:
            signals.append("MOMENTUM ⚡")
        if vol_ratio > 2.0 and abs(ret_5d) > 3:
            signals.append("UNUSUAL VOL 📊")
        if pct_from_hi > -5 and ret_20d > 10:
            signals.append("NEW HIGH 🚀")
        if -15 < pct_from_hi < -8 and vol_ratio < 0.7:
            signals.append("VCP SETUP 🔍")
        if ret_5d < -8 and vol_ratio > 1.5:
            signals.append("CAPITULATION 💀")

        if not signals:
            signal_str = "—"
        else:
            signal_str = signals[0]

        spec_results[sym] = {
            "current": round(current, 2),
            "ret_5d": round(ret_5d, 2),
            "ret_20d": round(ret_20d, 2),
            "pct_vs_200": round(pct_vs_200, 2),
            "vol_ratio": round(vol_ratio, 2),
            "pct_from_hi": round(pct_from_hi, 2),
            "signals": signals
        }

        if signals:
            print(f"{sym:<7} {current:>8.2f} {ret_5d:>6.1f}% {ret_20d:>6.1f}% {pct_vs_200:>7.1f}% {vol_ratio:>9.1f}x {pct_from_hi:>8.1f}% {signal_str}")

    except Exception as e:
        pass

# Also print the ones that SHOULD have been caught (big recent moves)
print(f"\n{'─' * 80}")
print("MISSED ENTRIES — Recent 20D Movers that signaled earlier")
print(f"{'─' * 80}")
print(f"{'Ticker':<7} {'Price':>8} {'20D%':>7} {'5D%':>7} {'vs200MA':>8} {'Vol Ratio':>10} {'Observation'}")
print(f"{'─'*7} {'─'*8} {'─'*7} {'─'*7} {'─'*8} {'─'*10} {'─'*40}")

for sym, d in sorted(spec_results.items(), key=lambda x: x[1]["ret_20d"], reverse=True):
    if d["ret_20d"] > 15:
        obs = "Entry window likely passed — momentum chase risk"
        print(f"{sym:<7} {d['current']:>8.2f} {d['ret_20d']:>6.1f}% {d['ret_5d']:>6.1f}% {d['pct_vs_200']:>7.1f}% {d['vol_ratio']:>9.1f}x {obs}")

# Look for entries where the 5D was very strong suggesting breakout happened RECENTLY
print(f"\n{'─' * 80}")
print("ACTIVE BREAKOUTS — 5D momentum still accelerating (possible entry window)")
print(f"{'─' * 80}")
for sym, d in sorted(spec_results.items(), key=lambda x: x[1]["ret_5d"], reverse=True):
    if d["ret_5d"] > 5 and d["vol_ratio"] > 1.2 and d["pct_vs_200"] > 0:
        obs = f"Above 200DMA, vol {d['vol_ratio']:.1f}x avg, momentum intact"
        print(f"  {sym:<7} {d['current']:>8.2f}  5D: +{d['ret_5d']:.1f}%  20D: +{d['ret_20d']:.1f}%  → {obs}")


# Summary
print("\n\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

advancing = [f"{sym} ({stage_results[sym]['name']})" for sym in advancing_sectors]
print(f"\n🟢 Stage 2 (FOCUS) Sectors: {', '.join(advancing) if advancing else 'None identified'}")

buy_zone = [f"{sym} ({quality_results[sym]['name']})" for sym, d in quality_results.items() if "BUY" in d["zone"]]
add_zone = [f"{sym} ({quality_results[sym]['name']})" for sym, d in quality_results.items() if "ADD" in d["zone"]]
fair_zone = [f"{sym} ({quality_results[sym]['name']})" for sym, d in quality_results.items() if "FAIR" in d["zone"]]
below_200 = [f"{sym} ({quality_results[sym]['name']})" for sym, d in quality_results.items() if "BELOW" in d["zone"]]

print(f"\n📊 QUALITY Zones:")
print(f"  🟢 BUY ZONE:      {', '.join(buy_zone) if buy_zone else 'None'}")
print(f"  🔵 ADD ZONE:       {', '.join(add_zone) if add_zone else 'None'}")
print(f"  ⚪ FAIR VALUE:     {', '.join(fair_zone) if fair_zone else 'None'}")
print(f"  🔴 BELOW 200DMA:  {', '.join(below_200) if below_200 else 'None'}")

spec_signals = [(sym, d["signals"][0]) for sym, d in spec_results.items() if d["signals"]]
print(f"\n⚡ SPECULATIVE Signals: {len(spec_signals)} detected")
for sym, sig in spec_signals[:10]:
    print(f"  {sym}: {sig}")

print("\n" + "=" * 80)
print("END OF SCAN")
print("=" * 80)
