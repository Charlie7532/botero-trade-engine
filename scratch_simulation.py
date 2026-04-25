"""
SIMULACIÓN HOHN: ¿Qué acciones recomendaría el motor CORE hoy?
================================================================
Evalúa 30 S&P500 + 5 Guru Gems con métricas de calidad pura.
"""
import yfinance as yf
import pandas as pd

# Universo
sp500_sample = ['AAPL','MSFT','NVDA','AMZN','GOOGL','META','BRK-B','TSLA','LLY','JPM',
                'UNH','V','XOM','JNJ','MA','PG','COST','HD','AVGO','ABBV',
                'MRK','CVX','CRM','AMD','PEP','KO','ADBE','WMT','TMO','MCD']
guru_gems = ['MELI','SPOT','CRWD','PANW','TTD']
all_tickers = sp500_sample + guru_gems

print('Descargando datos de mercado...')
spy = yf.download('SPY', period='3mo', interval='1d', progress=False)
vix_data = yf.download('^VIX', period='5d', interval='1d', progress=False)

if isinstance(spy.columns, pd.MultiIndex):
    spy.columns = spy.columns.get_level_values(0)
if isinstance(vix_data.columns, pd.MultiIndex):
    vix_data.columns = vix_data.columns.get_level_values(0)

spy_ret_20d = float(spy['Close'].iloc[-1] / spy['Close'].iloc[-20] - 1)
vix = float(vix_data['Close'].iloc[-1]) if not vix_data.empty else 20.0

print(f'\nVIX actual: {vix:.1f}')
print(f'SPY retorno 20d: {spy_ret_20d*100:+.2f}%')

results = []
for ticker in all_tickers:
    try:
        data = yf.download(ticker, period='6mo', interval='1d', progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        if len(data) < 40:
            continue
        
        close = float(data['Close'].iloc[-1])
        lookback = min(20, len(data) - 1)
        stock_ret = float(data['Close'].iloc[-1] / data['Close'].iloc[-lookback] - 1)
        rs = (1 + stock_ret) / (1 + spy_ret_20d) if spy_ret_20d != -1 else 1.0
        
        sma_len = min(200, len(data))
        sma200 = float(data['Close'].rolling(sma_len).mean().iloc[-1])
        above_sma200 = close > sma200
        
        atr = float((data['High'] - data['Low']).rolling(14).mean().iloc[-1])
        atr_pct = atr / close * 100
        
        delta_c = data['Close'].diff()
        gain = delta_c.where(delta_c > 0, 0).rolling(14).mean()
        loss_s = (-delta_c.where(delta_c < 0, 0)).rolling(14).mean()
        loss_val = float(loss_s.iloc[-1])
        rsi = float(100 - (100 / (1 + float(gain.iloc[-1]) / loss_val))) if loss_val != 0 else 50
        
        info = yf.Ticker(ticker).info
        sector = info.get('sector', 'Unknown')
        pe = info.get('trailingPE') or 0
        profit_margin = (info.get('profitMargins') or 0) * 100
        gross_margin = (info.get('grossMargins') or 0) * 100
        roe = (info.get('returnOnEquity') or 0) * 100
        revenue_growth = (info.get('revenueGrowth') or 0) * 100
        
        is_gem = ticker in guru_gems
        
        # Score HOHN puro (sin sesgos de momentum/opciones/analistas)
        hohn_score = 0.0
        
        # CALIDAD (peso ~50%)
        if roe > 30: hohn_score += 18
        elif roe > 20: hohn_score += 15
        elif roe > 15: hohn_score += 10
        elif roe > 10: hohn_score += 5
        
        if profit_margin > 25: hohn_score += 12
        elif profit_margin > 15: hohn_score += 8
        elif profit_margin > 10: hohn_score += 4
        
        if gross_margin > 70: hohn_score += 12
        elif gross_margin > 50: hohn_score += 8
        elif gross_margin > 40: hohn_score += 4
        
        # CRECIMIENTO (peso ~20%)
        if revenue_growth > 20: hohn_score += 10
        elif revenue_growth > 10: hohn_score += 7
        elif revenue_growth > 5: hohn_score += 4
        
        # TENDENCIA ESTRUCTURAL (peso ~10%)
        if above_sma200: hohn_score += 5
        
        # RS contra SPY (peso ~10%)
        if rs > 1.10: hohn_score += 8
        elif rs > 1.02: hohn_score += 5
        elif rs > 0.98: hohn_score += 2
        elif rs < 0.90: hohn_score -= 5
        
        # Para GEMS: Rule of 40 + Gross Margin premium
        gem_bonus = 0
        rule_of_40 = revenue_growth + profit_margin
        if is_gem:
            if rule_of_40 > 40: gem_bonus = 15
            elif rule_of_40 > 25: gem_bonus = 8
            if gross_margin > 65: gem_bonus += 5
        
        total_score = hohn_score + gem_bonus
        
        results.append({
            'ticker': ticker,
            'price': round(close, 2),
            'sector': sector,
            'rs': round(rs, 3),
            'rsi': round(rsi, 1),
            'roe': round(roe, 1),
            'pm': round(profit_margin, 1),
            'gm': round(gross_margin, 1),
            'rg': round(revenue_growth, 1),
            'pe': round(pe, 1) if pe else 0,
            'sma': above_sma200,
            'gem': is_gem,
            'r40': round(rule_of_40, 1) if is_gem else None,
            'score': round(total_score, 1),
        })
    except Exception as e:
        print(f'Error {ticker}: {e}')

results.sort(key=lambda x: -x['score'])

print(f'\n{"="*130}')
print(f'{"SIMULACION HOHN: RANKING DE CALIDAD ESTRUCTURAL":^130}')
print(f'{"="*130}')
header = f'{"Rk":>3} {"Ticker":>7} {"Precio":>9} {"Sector":>22} {"RS/SPY":>7} {"RSI":>5} {"ROE%":>6} {"PM%":>6} {"GM%":>6} {"RevGr%":>7} {"PE":>6} {"SMA":>4} {"Score":>6} {"Tipo":>10}'
print(header)
print('-'*130)

for i, r in enumerate(results[:25], 1):
    tipo = 'GEM' if r['gem'] else 'SP500'
    sma_flag = 'Y' if r['sma'] else 'N'
    print(f'{i:>3} {r["ticker"]:>7} ${r["price"]:>8.2f} {r["sector"]:>22} {r["rs"]:>7.3f} {r["rsi"]:>5.1f} {r["roe"]:>5.1f}% {r["pm"]:>5.1f}% {r["gm"]:>5.1f}% {r["rg"]:>6.1f}% {r["pe"]:>6.1f} {sma_flag:>4} {r["score"]:>5.1f} {tipo:>10}')

print(f'\n{"="*130}')
print(f'{"DECISION HOHN: TOP 5 RECOMENDACIONES CORE (80%)":^130}')
print(f'{"="*130}')
top5 = [r for r in results if r['sma'] and r['rs'] > 0.95][:5]
for i, r in enumerate(top5, 1):
    tipo = 'GURU GEM' if r['gem'] else 'BLUE CHIP'
    r40_str = f' | Rule40={r["r40"]:.0f}' if r['r40'] else ''
    print(f'  {i}. {r["ticker"]} @ ${r["price"]:.2f} | Score={r["score"]:.0f} | RS={r["rs"]:.3f} | ROE={r["roe"]:.1f}% | ProfitMargin={r["pm"]:.1f}% | GrossMargin={r["gm"]:.1f}%{r40_str} | [{tipo}]')

regime = "RISK_ON" if vix < 18 else "NEUTRAL" if vix < 25 else "RISK_OFF" if vix < 35 else "CRISIS"
print(f'\n  Macro: VIX={vix:.1f} -> Regimen={regime} | SPY 20d={spy_ret_20d*100:+.2f}%')

print(f'\n{"="*130}')
print(f'{"EMPRESAS RECHAZADAS POR HOHN (Score bajo o sin tendencia)":^130}')
print(f'{"="*130}')
rejected = [r for r in results if not r['sma'] or r['rs'] < 0.90 or r['score'] < 20][:8]
for r in rejected:
    reasons = []
    if not r['sma']: reasons.append('Bajo SMA200')
    if r['rs'] < 0.90: reasons.append(f'RS={r["rs"]:.3f} debil')
    if r['score'] < 20: reasons.append(f'Score={r["score"]:.0f} bajo')
    print(f'  RECHAZADO: {r["ticker"]} @ ${r["price"]:.2f} | {" | ".join(reasons)}')
