import json
import pandas as pd
import os

CACHE_FILE = "data/sim_7d_cache.json"

def run_forensics():
    if not os.path.exists(CACHE_FILE):
        print("Caché no encontrado.")
        return

    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)

    prices_dict = cache.get("prices", {})
    if not prices_dict:
        print("No hay precios.")
        return

    # Extraer ventana de 5 días
    first_ticker = list(prices_dict.keys())[0]
    all_dates = sorted(list(prices_dict[first_ticker].keys()))
    sim_dates = all_dates[-5:]
    
    start_date = sim_dates[0]
    end_date = sim_dates[-1]

    results = []

    for ticker, p_data in prices_dict.items():
        if ticker == "^VIX" or not p_data:
            continue
            
        if start_date in p_data and end_date in p_data:
            start_price = p_data[start_date]["Close"]
            end_price = p_data[end_date]["Close"]
            pnl_pct = ((end_price / start_price) - 1.0) * 100
            
            # Extract highest high during this window
            highs = [p_data[d]["High"] for d in sim_dates if d in p_data]
            max_high = max(highs) if highs else start_price
            mfe_pct = ((max_high / start_price) - 1.0) * 100
            
            results.append({
                "Ticker": ticker,
                "Start Price": start_price,
                "End Price": end_price,
                "Return (%)": pnl_pct,
                "Max Run-Up (%)": mfe_pct
            })

    df = pd.DataFrame(results)
    
    # Filtrar solo las que subieron más de un 4%
    top_gainers = df[df["Return (%)"] > 4.0].sort_values(by="Return (%)", ascending=False)
    
    print(f"VENTANA: {start_date} -> {end_date}")
    print(f"Total acciones procesadas: {len(df)}")
    print(f"Acciones con retorno > 4%: {len(top_gainers)}")
    print("\nTOP 25 GAINERS:")
    print(top_gainers.head(25).to_string(index=False))

    # Guardar a un markdown temporal para facilitar el copiado al artefacto
    with open("data/forensic_results.md", "w") as f:
        f.write(f"## Top Gainers (>{4}% Return) in Window {start_date} to {end_date}\n\n")
        f.write(top_gainers.to_markdown(index=False))

if __name__ == "__main__":
    run_forensics()
