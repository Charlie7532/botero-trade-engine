class FundamentalFilter:
    """
    Tier 2: Filtro fundamental vía GuruFocus MCP.
    
    Define la interfaz para consultar:
    - Acumulación de Gurus (13F Buy/Add)
    - Descuento vs Valor Intrínseco (DCF)
    - Insider buying
    
    Los datos reales vienen del MCP Server de GuruFocus.
    Este módulo define QUÉ preguntar y CÓMO interpretar las respuestas.
    """

    @staticmethod
    def evaluate_guru_signals(guru_picks: list[dict]) -> dict:
        """
        Evalúa señales de acumulación institucional desde datos de GuruFocus.
        
        Args:
            guru_picks: Lista de picks del MCP (get_guru_picks response).
            
        Returns:
            Dict con métricas de acumulación por ticker.
        """
        accumulation = {}
        for pick in guru_picks:
            symbol = pick.get("symbol", "")
            action = pick.get("action", "").lower()

            if symbol not in accumulation:
                accumulation[symbol] = {
                    "buys": 0, "sells": 0, "adds": 0,
                    "reduces": 0, "net_signal": 0,
                }

            if action in ("buy", "new buy"):
                accumulation[symbol]["buys"] += 1
                accumulation[symbol]["net_signal"] += 2
            elif action == "add":
                accumulation[symbol]["adds"] += 1
                accumulation[symbol]["net_signal"] += 1
            elif action == "reduce":
                accumulation[symbol]["reduces"] += 1
                accumulation[symbol]["net_signal"] -= 1
            elif action in ("sell", "sold out"):
                accumulation[symbol]["sells"] += 1
                accumulation[symbol]["net_signal"] -= 2

        return accumulation

    @staticmethod
    def evaluate_valuation(summary: dict) -> float:
        """
        Calcula el descuento porcentual vs valor intrínseco.
        
        Args:
            summary: Respuesta del MCP get_stock_summary.
            
        Returns:
            Descuento en %. Positivo = infravalorado. Negativo = sobrevalorado.
        """
        price = summary.get("price", 0)
        intrinsic = summary.get("intrinsic_value", 0)

        if intrinsic and intrinsic > 0 and price and price > 0:
            return ((intrinsic - price) / intrinsic) * 100
        return 0.0
