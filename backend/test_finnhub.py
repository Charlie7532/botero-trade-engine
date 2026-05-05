import finnhub
import os

client = finnhub.Client(api_key="d7gffopr01qmqj4553cgd7gffopr01qmqj4553d0")
try:
    filings = client.filings(symbol='AAPL', _from="2023-01-01", to="2024-01-01")
    print(filings[:2])
except Exception as e:
    print("Error:", e)
