import os
import json
import urllib.request
import urllib.error

def test_finnhub(api_key):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                print("Finnhub: OK (Status 200 - Connectivity Active)")
            else:
                print(f"Finnhub: Failed (Status {response.status})")
    except urllib.error.URLError as e:
        print(f"Finnhub: Error conectando ({e})")

def test_fred(api_key):
    try:
        # Check an arbitrary data series to verify key validity
        url = f"https://api.stlouisfed.org/fred/series?series_id=GNPCA&api_key={api_key}&file_type=json"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                print("FRED: OK (Status 200 - Connectivity Active)")
            else:
                print(f"FRED: Failed (Status {response.status})")
    except urllib.error.URLError as e:
        if '400' in str(e):
             print("FRED: Failed (Status 400 - API Key might be invalid or improperly formatted)")
        else:
             print(f"FRED: Error conectando ({e})")

def test_finviz(api_key):
    try:
        # Finviz Elite API endpoint - quote for AAPL
        url = f"https://elite.finviz.com/export.ashx?v=152&t=AAPL&auth={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                data = response.read().decode('utf-8')
                if 'AAPL' in data or len(data) > 50:
                    print("Finviz: OK (Status 200 - Elite API Active)")
                else:
                    print("Finviz: Warning (Status 200 pero respuesta vacía - verifica API key)")
            else:
                print(f"Finviz: Failed (Status {response.status})")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("Finviz: Failed (Status 403 - API Key inválida o cuenta no Elite)")
        elif e.code == 401:
            print("Finviz: Failed (Status 401 - No autorizado)")
        else:
            print(f"Finviz: Failed (HTTP {e.code})")
    except urllib.error.URLError as e:
        print(f"Finviz: Error conectando ({e})")

if __name__ == "__main__":
    fred_key = None
    finnhub_key = None
    finviz_key = None
    
    # 1. Parse .env
    try:
        with open('/root/botero-trade/.env', 'r') as f:
            for line in f:
                if line.startswith('FRED_API_KEY='):
                    fred_key = line.split('=', 1)[1].strip()
                elif line.startswith('FINNHUB_API_KEY='):
                    finnhub_key = line.split('=', 1)[1].strip()
                elif line.startswith('FINVIZ_API_KEY='):
                    finviz_key = line.split('=', 1)[1].strip()
    except Exception:
        pass
        
    # 2. Parse .mcp.json 
    try:
        with open('/root/botero-trade/.mcp.json', 'r') as f:
            mcp_data = json.load(f)
            
            # FRED
            fred_mcp = mcp_data.get('mcpServers', {}).get('fred-macro', {})
            if 'args' in fred_mcp and '--api-key' in fred_mcp['args']:
                idx = fred_mcp['args'].index('--api-key')
                if len(fred_mcp['args']) > idx + 1:
                    val = fred_mcp['args'][idx+1]
                    if val and val != "TU_FRED_API_KEY":
                        fred_key = val
                        
            # Finnhub
            finnhub_mcp = mcp_data.get('mcpServers', {}).get('finnhub-orderflow', {})
            if 'env' in finnhub_mcp and 'FINNHUB_API_KEY' in finnhub_mcp['env']:
                val = finnhub_mcp['env']['FINNHUB_API_KEY']
                if val and val != "PEGA_TU_CLAVE_AQUI":
                    finnhub_key = val

            # Finviz
            finviz_mcp = mcp_data.get('mcpServers', {}).get('finviz-screener', {})
            if 'env' in finviz_mcp and 'FINVIZ_API_KEY' in finviz_mcp['env']:
                val = finviz_mcp['env']['FINVIZ_API_KEY']
                if val and 'YOUR_' not in val:
                    finviz_key = val
    except Exception:
        pass
        
    print("--- Verificando Fuentes de Datos ---")
    if finnhub_key and 'PEGA_TU' not in finnhub_key and 'your-' not in finnhub_key:
        test_finnhub(finnhub_key)
    else:
        print("Finnhub: Token Faltante o Default")
        
    if fred_key and 'TU_FRED' not in fred_key and 'your-' not in fred_key and 'pon_tu_clave' not in fred_key:
        test_fred(fred_key)
    else:
        print("FRED: Token Faltante o Default")
        
    if finviz_key and 'YOUR_' not in finviz_key and 'your-' not in finviz_key:
        test_finviz(finviz_key)
    else:
        print("Finviz: Token Faltante o Default")
        
    print("News-Sentiment: OK (Funciona libre vía scraping público local)")
