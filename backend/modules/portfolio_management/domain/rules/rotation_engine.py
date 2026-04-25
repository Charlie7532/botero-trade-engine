from backend.modules.portfolio_management.domain.rules.relative_strength import RelativeStrengthMonitor

class RotationEngine:
    """
    Decide cuándo rotar posiciones del portafolio.
    
    Regla de oro: Un candidato debe ser 30% MEJOR que la peor
    posición actual para justificar la rotación. Esto evita
    "churning" (sobre-rotación que destruye rendimiento por costos).
    """
    
    ROTATION_THRESHOLD = 1.30  # Candidato debe ser 30% mejor
    
    def __init__(self):
        self.rs_monitor = RelativeStrengthMonitor()
    
    def evaluate_rotation(
        self,
        current_positions: list[dict],
        candidates: list[dict],
    ) -> list[dict]:
        """
        Evalúa si algún candidato justifica reemplazar una posición.
        
        Args:
            current_positions: [{"ticker", "alpha_score", "rs", "decay", ...}]
            candidates: [{"ticker", "alpha_score", "rs", ...}]
        
        Returns:
            Lista de rotaciones recomendadas
        """
        if not current_positions or not candidates:
            return []
        
        rotations = []
        
        # Ordenar posiciones por score (peor primero)
        positions_sorted = sorted(
            current_positions, key=lambda x: x.get('alpha_score', 0)
        )
        
        # Ordenar candidatos por score (mejor primero)
        candidates_sorted = sorted(
            candidates, key=lambda x: -x.get('alpha_score', 0)
        )
        
        for candidate in candidates_sorted:
            cand_score = candidate.get('alpha_score', 0)
            
            for position in positions_sorted:
                pos_score = position.get('alpha_score', 0)
                
                # ¿El candidato es 30% mejor?
                if pos_score > 0 and cand_score / pos_score >= self.ROTATION_THRESHOLD:
                    rotations.append({
                        "action": "ROTATE",
                        "sell": position['ticker'],
                        "sell_score": pos_score,
                        "buy": candidate['ticker'],
                        "buy_score": cand_score,
                        "improvement": f"{(cand_score/pos_score - 1)*100:+.0f}%",
                        "reason": (
                            f"{candidate['ticker']} ({cand_score:.0f}) supera a "
                            f"{position['ticker']} ({pos_score:.0f}) por "
                            f"{(cand_score/pos_score - 1)*100:.0f}%"
                        ),
                    })
                    # No rotar la misma posición dos veces
                    positions_sorted.remove(position)
                    break
        
        return rotations
