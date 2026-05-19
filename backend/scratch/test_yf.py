import yfinance as yf
ticker = yf.Ticker("AAPL")
print("Earnings Estimate:", ticker.earnings_estimate if hasattr(ticker, 'earnings_estimate') else 'N/A')
print("Info:", ticker.info.get('earningsEstimate', 'N/A'))
print("Keys:", [k for k in ticker.info.keys() if 'earn' in k.lower() or 'est' in k.lower()])
