"""
ARM Flow Intelligence — Live Unusual Whales Pull
Fetches current options flow, dark pool, and GEX data for ARM
"""
import sys
import os
import logging
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, "/root/botero-trade")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv("/root/botero-trade/.env")

from backend.modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge
from backend.modules.flow_intelligence.infrastructure.uw_adapter import UnusualWhalesIntelligence

TICKER = "ARM"

print("=" * 80)
print(f"UNUSUAL WHALES LIVE PULL — {TICKER}")
print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 80)

# Initialize bridge
bridge = UWDataBridge()
if not bridge.is_configured():
    print("❌ UW_API_KEY not configured!")
    sys.exit(1)

print("✅ UW API Key configured\n")

# Initialize adapter
uw = UnusualWhalesIntelligence()

# ─── 1. OPTIONS FLOW (Volume/Premium) ───
print("─" * 60)
print(f"1. OPTIONS FLOW — {TICKER}")
print("─" * 60)
flow_data = bridge.fetch_flow_alerts(TICKER)
if flow_data:
    print(f"   📊 Raw alerts received: {len(flow_data)}")
    signal = uw.parse_flow_alerts(TICKER, flow_data)
    print(f"   🔹 Flow Score:      {signal.flow_score}/100")
    print(f"   🔹 Calls:           {signal.n_calls:,}")
    print(f"   🔹 Puts:            {signal.n_puts:,}")
    print(f"   🔹 Call/Put Ratio:  {signal.call_put_ratio:.2f}")
    print(f"   🔹 Sweeps:          {signal.n_sweeps}")
    print(f"   🔹 Call Premium:    ${signal.call_premium:,.0f}")
    print(f"   🔹 Put Premium:     ${signal.put_premium:,.0f}")
    print(f"   🔹 Net Premium:     ${signal.net_premium:+,.0f}")
    print(f"   🔹 Ask/Bid Ratio:   {signal.ask_bid_ratio:.2f}")
    print(f"   🔹 VOI Ratio (avg): {signal.avg_voi_ratio:.2f}")
    print(f"   🔹 Last Updated:    {signal.last_updated}")
    
    # Interpretation
    print(f"\n   {'─'*40}")
    if signal.flow_score >= 70:
        print(f"   🟢 STRONG BULLISH FLOW — Institutional buying confirmed")
    elif signal.flow_score >= 50:
        print(f"   🟡 MODERATE BULLISH LEAN — Some conviction present")
    elif signal.flow_score >= 30:
        print(f"   ⚪ NEUTRAL FLOW — No clear directional bias")
    else:
        print(f"   🔴 BEARISH/ABSENT FLOW — No institutional interest")
    
    if signal.n_sweeps > 3:
        print(f"   ⚡ SWEEP CLUSTER: {signal.n_sweeps} sweeps — urgency signal (Karsan: forced delta-hedging)")
    elif signal.n_sweeps > 0:
        print(f"   ⚡ Sweeps present ({signal.n_sweeps}) — some urgency")
    else:
        print(f"   💤 No sweeps — no urgency signal")
    
    # Print raw data sample
    if isinstance(flow_data, list) and flow_data:
        print(f"\n   📋 Sample alert fields: {list(flow_data[0].keys())[:15]}")
        # Show most recent 3 entries
        print(f"\n   📋 Most recent data points:")
        for entry in flow_data[:3]:
            date = entry.get('date', entry.get('executed_at', 'N/A'))
            print(f"      Date: {date}")
            for key in ['call_volume', 'put_volume', 'call_premium', 'put_premium', 
                       'bullish_premium', 'bearish_premium', 'net_call_premium', 'net_put_premium',
                       'call_volume_ask_side', 'put_volume_ask_side', 'avg_30_day_call_volume']:
                if key in entry:
                    val = entry[key]
                    if isinstance(val, (int, float)) and val > 1000:
                        print(f"        {key}: {val:,.0f}")
                    else:
                        print(f"        {key}: {val}")
            print()
else:
    print("   ❌ No flow data returned")

# ─── 2. RECENT HIGH-PREMIUM FLOW ───
print("\n" + "─" * 60)
print(f"2. HIGH-PREMIUM FLOW (>$50k) — {TICKER}")
print("─" * 60)
recent_flow = bridge.fetch_ticker_flow_recent(TICKER, min_premium=50000)
if recent_flow:
    print(f"   📊 High-premium trades: {len(recent_flow)}")
    for trade in recent_flow[:8]:
        side = trade.get('sentiment', trade.get('type', '?'))
        prem = trade.get('premium', trade.get('total_premium', 0))
        strike = trade.get('strike', '?')
        exp = trade.get('expiry', trade.get('expires', '?'))
        is_sweep = trade.get('is_sweep', trade.get('has_sweep', False))
        vol = trade.get('volume', 0)
        oi = trade.get('open_interest', 0)
        
        sweep_tag = " 🔥SWEEP" if is_sweep else ""
        if isinstance(prem, (int, float)):
            prem_str = f"${prem:,.0f}"
        else:
            prem_str = str(prem)
        print(f"   {side:>6} | Strike ${strike} | Exp {exp} | Prem {prem_str} | V/OI {vol}/{oi}{sweep_tag}")
else:
    print("   ❌ No high-premium flow data")

# ─── 3. NET PREMIUM TICKS (intraday flow direction) ───
print("\n" + "─" * 60)
print(f"3. NET PREMIUM TICKS — {TICKER}")
print("─" * 60)
prem_ticks = bridge.fetch_ticker_net_prem_ticks(TICKER)
if prem_ticks:
    print(f"   📊 Premium ticks: {len(prem_ticks)}")
    # Show cumulative net premium trend
    cum_net = 0
    for tick in prem_ticks[-10:]:
        net = float(tick.get('net_premium', 0) or tick.get('value', 0) or 0)
        cum_net += net
        time_str = tick.get('tape_time', tick.get('timestamp', tick.get('date', '?')))
        print(f"   {time_str}: net=${net:+,.0f}  cum=${cum_net:+,.0f}")
else:
    print("   ❌ No net premium tick data")

# ─── 4. DARK POOL ───
print("\n" + "─" * 60)
print(f"4. DARK POOL PRINTS — {TICKER}")
print("─" * 60)
dp_data = bridge.fetch_darkpool_trades(TICKER)
if dp_data:
    print(f"   📊 Dark pool prints: {len(dp_data)}")
    total_dp_vol = 0
    for trade in dp_data[:8]:
        price = trade.get('price', trade.get('execution_price', '?'))
        size = trade.get('size', trade.get('volume', 0))
        total_dp_vol += int(size) if size else 0
        notional = float(price) * float(size) if price and size else 0
        time_str = trade.get('tracking_timestamp', trade.get('executed_at', trade.get('date', '?')))
        print(f"   {time_str}: {size:>8,} shares @ ${float(price):>8.2f} = ${notional:>12,.0f}")
    print(f"\n   Total DP volume (shown): {total_dp_vol:,} shares")
else:
    print("   ❌ No dark pool data")

# ─── 5. GREEK EXPOSURE (GEX) ───
print("\n" + "─" * 60)
print(f"5. GREEK EXPOSURE (GEX) — {TICKER}")
print("─" * 60)
gex_data = bridge.fetch_ticker_gex(TICKER)
if gex_data:
    print(f"   📊 GEX data received")
    if isinstance(gex_data, dict):
        for key, val in gex_data.items():
            if isinstance(val, (int, float)):
                print(f"   🔹 {key}: {val:,.2f}")
            elif isinstance(val, list) and len(val) <= 5:
                print(f"   🔹 {key}: {val}")
            elif isinstance(val, list):
                print(f"   🔹 {key}: [{len(val)} items]")
            else:
                print(f"   🔹 {key}: {str(val)[:80]}")
    elif isinstance(gex_data, list):
        print(f"   📊 {len(gex_data)} GEX entries")
        for entry in gex_data[:5]:
            print(f"   {json.dumps(entry, default=str)[:120]}")
else:
    print("   ❌ No GEX data (may require higher API tier)")

# ─── 6. SPY MACRO CONTEXT ───
print("\n" + "─" * 60)
print(f"6. SPY MACRO GATE (market context)")
print("─" * 60)
spy_flow = bridge.fetch_spy_flow()
if spy_flow:
    macro = uw.parse_spy_macro_gate(spy_flow)
    print(f"   🔹 Composite Score:  {macro.composite_score:+d}")
    print(f"   🔹 Signal:           {macro.signal}")
    print(f"   🔹 Scale Factor:     {macro.position_scale_factor:.2f}")
    print(f"   🔹 Confidence:       {macro.confidence:.2f}")
    print(f"   🔹 Cum Delta:        {macro.cum_delta:+,.0f}")
    print(f"   🔹 Net Premium:      ${macro.cum_net_premium:+,.0f}")
    print(f"   🔹 C/P Vol Ratio:    {macro.call_put_vol_ratio:.2f}")
    print(f"   🔹 AM/PM Divergence: {'YES ⚠️' if macro.am_pm_diverges else 'No'}")
    print(f"   🔹 Last Updated:     {macro.last_updated}")
else:
    print("   ❌ No SPY flow data")

# ─── SUMMARY ───
print("\n" + "=" * 80)
print(f"EIFERT/KARSAN ASSESSMENT FOR {TICKER}")
print("=" * 80)
print("""
Interpret above data through the Three-Voice chain:

KARSAN: Map the gamma structure
  → GEX regime (positive/negative)? 
  → Where are Put/Call Walls?
  → What Vanna/Charm flows are expected?

EIFERT: WHO is on the other side?
  → Are these sweeps from price-insensitive hedgers (structural alpha)?
  → Or sophisticated flow (no edge)?
  → Does the dark pool confirm institutional positioning?

PTJ: Is the tape confirming?
  → Is the flow score supporting direction?
  → Is SPY macro gate friendly?
  → Can we get 5:1 with the gamma map?
""")
