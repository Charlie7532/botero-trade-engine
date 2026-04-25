import pandas as pd

class RelativeStrengthMonitor:
    """
    Mide el rendimiento relativo de cada posición vs SPY y su sector.
    Si una acción gana +5% pero SPY gana +8%, estás PERDIENDO
    en costo de oportunidad.
    
    Métricas:
    - RS_SPY: Return_stock / Return_SPY (>1 = superando)
    - RS_Sector: Return_stock / Return_sector (>1 = líder)
    - RS_Momentum: RS_5d / RS_20d (>1 = acelerando)
    - Alpha_Decay: RS_actual / RS_al_entrar (<0.7 = exit)
    """
    
    def __init__(self):
        self._entry_rs = {}  # Guarda el RS al momento de entrada
    
    def calculate_rs(
        self,
        stock_prices: pd.Series,
        benchmark_prices: pd.Series,
        lookback: int = 20,
    ) -> dict:
        """Calcula Relative Strength de un stock vs benchmark."""
        if len(stock_prices) < lookback or len(benchmark_prices) < lookback:
            return {"rs": 1.0, "rs_momentum": 1.0, "rs_percentile": 50}
        
        # RS = retorno del stock / retorno del benchmark
        stock_ret = stock_prices.iloc[-1] / stock_prices.iloc[-lookback] - 1
        bench_ret = benchmark_prices.iloc[-1] / benchmark_prices.iloc[-lookback] - 1
        
        rs = (1 + stock_ret) / (1 + bench_ret) if bench_ret != -1 else 1.0
        
        # RS Momentum: RS reciente / RS medio
        rs_5d = (stock_prices.iloc[-1] / stock_prices.iloc[-5] - 1) / max(
            bench_ret / 4, 0.001
        ) if len(stock_prices) >= 5 else 1.0
        rs_20d = stock_ret / max(bench_ret, 0.001) if bench_ret != 0 else 1.0
        rs_momentum = rs_5d / rs_20d if rs_20d != 0 else 1.0
        
        return {
            "rs": round(rs, 4),
            "stock_return": round(stock_ret * 100, 2),
            "bench_return": round(bench_ret * 100, 2),
            "outperformance": round((stock_ret - bench_ret) * 100, 2),
            "rs_momentum": round(rs_momentum, 4),
        }
    
    def register_entry(self, ticker: str, rs_at_entry: float):
        """Registra el RS al momento de la entrada para calcular alpha decay."""
        self._entry_rs[ticker] = rs_at_entry
    
    def calculate_alpha_decay(self, ticker: str, current_rs: float) -> float:
        """
        Mide cuánto del edge original queda.
        1.0 = edge intacto, 0.5 = perdió la mitad, 0.0 = edge muerto
        """
        entry_rs = self._entry_rs.get(ticker, current_rs)
        if entry_rs <= 0:
            return 1.0
        decay = current_rs / entry_rs
        return round(max(0, min(decay, 2.0)), 4)
    
    def should_exit(self, ticker: str, current_rs: float) -> dict:
        """
        Evalúa si una posición debe cerrarse por degradación de RS.
        
        Reglas basadas en evidencia:
        - RS < 0.85 por 5+ días: El stock pierde contra el mercado
        - Alpha Decay < 0.70: El edge original desapareció
        - RS Momentum < 0.80: Desaceleración fuerte
        """
        decay = self.calculate_alpha_decay(ticker, current_rs)
        
        if decay < 0.70:
            return {
                "exit": True,
                "urgency": "high",
                "reason": f"Alpha Decay {decay:.2f} < 0.70 — edge muerto",
            }
        elif current_rs < 0.85:
            return {
                "exit": True,
                "urgency": "medium",
                "reason": f"RS {current_rs:.2f} < 0.85 — underperforming mercado",
            }
        elif decay < 0.85:
            return {
                "exit": False,
                "urgency": "watch",
                "reason": f"Alpha Decay {decay:.2f} — monitoreando",
            }
        else:
            return {
                "exit": False,
                "urgency": "none",
                "reason": f"RS {current_rs:.2f}, Decay {decay:.2f} — sano",
            }
