import os
import sys
import json
from dotenv import load_dotenv

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.modules.flow_intelligence.infrastructure.uw_mcp_bridge import UWDataBridge

def test_technicals():
    load_dotenv()
    bridge = UWDataBridge()
    
    if not bridge.is_configured():
        print("UW_API_KEY not found. Cannot run test.")
        return

    ticker = "SPY"
    function = "RSI" # Or SMA, MACD, etc.
    
    print(f"Testing Technical Indicator API for {ticker} - {function}")
    
    # Endpoint: /api/stock/{ticker}/technical-indicator/{function}
    endpoint = f"/api/stock/{ticker}/technical-indicator/{function}"
    params = {
        "interval": "daily",
        "time_period": 14,
        "series_type": "close"
    }
    
    data = bridge._request(endpoint, params=params)
    
    if data:
        print("Success! Data preview:")
        # Print first few data points if it's a list or dict
        if isinstance(data, dict):
            # Check what's inside
            for k, v in list(data.items())[:5]:
                if isinstance(v, list) or isinstance(v, dict):
                    print(f"  {k}: {str(v)[:100]}...")
                else:
                    print(f"  {k}: {v}")
        elif isinstance(data, list):
            print(json.dumps(data[:3], indent=2))
        else:
            print(data)
    else:
        print("Failed to fetch data or returned None.")

if __name__ == "__main__":
    test_technicals()
