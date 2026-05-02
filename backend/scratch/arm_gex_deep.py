"""Quick GEX deep dive — parse ARM greek exposure for Karsan map"""
import sys, os, json
sys.path.insert(0, "/root/botero-trade")
from dotenv import load_dotenv
load_dotenv("/root/botero-trade/.env")
from backend.modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge

bridge = UWDataBridge()
gex = bridge.fetch_ticker_gex("ARM")

if isinstance(gex, list) and gex:
    # Get the most recent entries
    recent = sorted(gex, key=lambda x: x.get('date', ''), reverse=True)[:10]
    print("ARM — GREEK EXPOSURE (Last 10 trading days)")
    print(f"{'Date':<12} {'Call Delta':>14} {'Put Delta':>14} {'Net Delta':>14} {'Call Charm':>14} {'Call Gamma':>14} {'Call Vanna':>14}")
    print("─"*100)
    for r in recent:
        cd = float(r.get('call_delta', 0) or 0)
        pd = float(r.get('put_delta', 0) or 0)
        nd = cd + pd
        cc = float(r.get('call_charm', 0) or 0)
        cg = float(r.get('call_gamma', 0) or 0)
        cv = float(r.get('call_vanna', 0) or 0)
        print(f"{r.get('date','?'):<12} {cd:>14,.0f} {pd:>14,.0f} {nd:>14,.0f} {cc:>14,.0f} {cg:>14,.0f} {cv:>14,.0f}")
    
    # Print all available fields from most recent
    print(f"\n📋 All fields in GEX data:")
    for k, v in recent[0].items():
        print(f"   {k}: {v}")
elif isinstance(gex, dict):
    print(json.dumps(gex, indent=2, default=str)[:3000])
else:
    print("No GEX data")

# Also fetch flow for the breakout period (mid-March)
print("\n\n" + "="*80)
print("ARM — NET PREMIUM INTRADAY TICKS (today)")
print("="*80)
ticks = bridge.fetch_ticker_net_prem_ticks("ARM")
if ticks:
    # Parse the actual intraday ticks — find the during-session ones
    session_ticks = [t for t in ticks if t.get('value') or t.get('net_premium')]
    # Look at field structure
    print(f"Total ticks: {len(ticks)}")
    print(f"Sample tick fields: {list(ticks[0].keys())}")
    print(f"\nFirst 3 ticks with non-zero data:")
    shown = 0
    for t in ticks:
        vals = {k: v for k, v in t.items() if v and v != 0 and v != '0' and v != 0.0}
        if len(vals) > 2:
            print(f"  {json.dumps(vals, default=str)[:200]}")
            shown += 1
            if shown >= 3:
                break
    
    # Cumulative net premium from ticks
    print(f"\nIntraday cumulative net premium (hourly blocks):")
    cum = 0
    hourly = {}
    for t in ticks:
        ts = t.get('tape_time', t.get('timestamp', ''))
        net = float(t.get('net_call_premium', 0) or 0) - float(t.get('net_put_premium', 0) or 0)
        if not net and t.get('value'):
            net = float(t.get('value', 0) or 0)
        cum += net
        hour = ts[:13] if ts else 'unknown'
        if hour not in hourly:
            hourly[hour] = 0
        hourly[hour] += net
    
    for hour, val in sorted(hourly.items()):
        if val != 0:
            print(f"  {hour}: ${val:+,.0f}")
    print(f"\n  CUMULATIVE NET: ${cum:+,.0f}")
