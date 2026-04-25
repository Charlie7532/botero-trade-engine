import logging
from backend.modules.portfolio_management.domain.entities.universe_candidate import UniverseCandidate, MarketRegime
from backend.modules.portfolio_management.domain.rules.macro_regime import MacroRegimeDetector
from backend.modules.portfolio_management.domain.rules.sector_ranker import SectorRanker
from backend.modules.portfolio_management.domain.rules.fundamental_filter import FundamentalFilter
from backend.modules.portfolio_management.domain.rules.catalyst_detector import CatalystDetector

logger = logging.getLogger(__name__)

class UniverseFilter:
    """
    Pipeline Master: Combina los 3 Tiers para producir un universo filtrado.
    
    Tier 0 (Macro): ¿Qué régimen de mercado estamos?
    Tier 1 (Sector): ¿Qué sectores tienen momentum relativo favorable?
    Tier 2 (Fundamental): ¿Qué activos están siendo acumulados por Gurus?
    Tier 3 (Catalizador): ¿Hay sobrerreacciones explotables?
    
    Output: Lista rankeada de UniverseCandidate para la LSTM.
    """

    def __init__(self, data_dir: str = "/root/botero-trade/.claude/DATA"):
        self.macro = MacroRegimeDetector()
        self.sector_ranker = SectorRanker(data_dir)
        self.fundamental = FundamentalFilter()
        self.catalyst = CatalystDetector()
        # Opciones & Breadth
        self._options = None
        self._breadth = None
        # GuruFocus Intelligence adapter (lazy init)
        self._gurufocus = None

    def _init_gurufocus(self):
        if self._gurufocus is None:
            from backend.infrastructure.data_providers.gurufocus_intelligence import GuruFocusIntelligence
            self._gurufocus = GuruFocusIntelligence()

    def _init_options(self):
        if self._options is None:
            from backend.infrastructure.data_providers.options_awareness import OptionsAwareness
            self._options = OptionsAwareness()

    def _init_breadth(self):
        if self._breadth is None:
            from backend.infrastructure.data_providers.market_breadth import MarketBreadthProvider
            self._breadth = MarketBreadthProvider()

    def filter_universe(
        self,
        guru_picks: list[dict] = None,
        stock_summaries: dict = None,
        use_live_macro: bool = True,
        vix_override: float = None,
        yield_override: float = None,
        include_options: bool = False,
        include_breadth: bool = False,
        # ─── NEW: MCP Intelligence Data ───
        qgarp_data: dict = None,           # {ticker: mcp_response}
        insider_data: dict = None,         # {ticker: {cluster, ceo, cfo}}
        guru_tracking_data: dict = None,   # {ticker: mcp_response}
        risk_data: dict = None,            # {ticker: mcp_response}
        analyst_data: dict = None,         # {ticker: mcp_response}
        political_data: dict = None,       # {ticker: mcp_response}
        fred_mcp_data: dict = None,        # FRED MCP get_economic_indicators
    ) -> list[UniverseCandidate]:
        """
        Ejecuta el pipeline completo de filtrado.
        
        Args:
            guru_picks: Datos del MCP GuruFocus (opcional).
            stock_summaries: Dict {ticker: summary} del MCP (opcional).
            use_live_macro: Si True, descarga VIX/Yields en vivo.
            vix_override: VIX manual para backtesting.
            yield_override: Yield spread manual para backtesting.
            
        Returns:
            Lista de candidatos elegibles, rankeados por score compuesto.
        """
        logger.info("=" * 60)
        logger.info("UNIVERSE FILTER: Iniciando pipeline de 3 Tiers")
        logger.info("=" * 60)

        # ── TIER 0: Macro Regime ──
        if fred_mcp_data is not None:
            # PRIMARY: FRED MCP with 6+ macro signals
            regime = self.macro.detect_from_fred(fred_mcp_data)
        elif vix_override is not None:
            regime = self.macro.detect_from_data(
                vix_override, yield_override or 0.5
            )
        elif use_live_macro:
            # FALLBACK: yfinance VIX + Yield only
            regime = self.macro.detect_from_market()
        else:
            regime = MarketRegime.NEUTRAL

        logger.info(f"Tier 0 → Régimen: {regime.value} (VIX={self.macro.vix_level:.1f})")

        # ── TIER 1: Sector Ranking ──
        rankings = self.sector_ranker.rank_sectors(regime)
        eligible_sectors = [r for r in rankings if r["eligible"]]
        logger.info(
            f"Tier 1 → {len(eligible_sectors)}/{len(rankings)} sectores elegibles"
        )

        # ── TIER 2: Fundamental (si hay datos de MCP) ──
        guru_signals = {}
        if guru_picks:
            guru_signals = self.fundamental.evaluate_guru_signals(guru_picks)
            logger.info(f"Tier 2 → {len(guru_signals)} tickers con señal de Gurus")

        # ── TIER OPTIONS: Opciones & Sentimiento (si solicitado) ──
        breadth_data = None
        fear_greed_data = None
        capitulation_signal = None

        if include_breadth:
            self._init_breadth()
            fear_greed_data = self._breadth.get_fear_greed_index()
            breadth_data = self._breadth.get_sp500_breadth()

            s5tw = breadth_data.get('pct_above_20dma', 'N/A')
            s5th = breadth_data.get('pct_above_200dma', 'N/A')
            logger.info(
                f"Tier Breadth → F&G: {fear_greed_data.get('score', 'N/A'):.1f} "
                f"({fear_greed_data.get('rating', '?')}), "
                f"S5TH: {s5th}%, S5TW: {s5tw}%"
            )

            # ── CAPITULATION DETECTOR ──
            capitulation_signal = self._breadth.detect_capitulation(
                vix=self.macro.vix_level,
                breadth_data=breadth_data,
            )

            # En capitulación nivel 3+, reactivar TODOS los sectores
            # (en crisis genuina, los fundamentales sólidos caen injustamente)
            if capitulation_signal["capitulation_level"] >= 3:
                eligible_sectors = rankings  # Todo el universo se abre
                for s in eligible_sectors:
                    s["eligible"] = True
                logger.warning(
                    f"🔥 CAPITULACIÓN NIVEL {capitulation_signal['capitulation_level']}: "
                    f"Reabriendo TODOS los sectores. "
                    f"Retorno esperado 60d: +{capitulation_signal['expected_60d_return_pct']:.1f}%"
                )

        # ── Construir Candidatos ──
        candidates = []
        for sector in eligible_sectors:
            ticker = sector["ticker"]

            candidate = UniverseCandidate(
                ticker=ticker,
                regime=regime,
                sector=sector.get("type", ""),
                relative_momentum=sector["momentum"],
                vix_at_selection=self.macro.vix_level,
            )

            # Enriquecer con fundamentales si disponibles
            if ticker in guru_signals:
                net = guru_signals[ticker]["net_signal"]
                candidate.guru_accumulation = net > 0

            if stock_summaries and ticker in stock_summaries:
                candidate.dcf_discount_pct = self.fundamental.evaluate_valuation(
                    stock_summaries[ticker]
                )

            # Enriquecer con Opciones (Max Pain, PCR, GEX)
            if include_options:
                self._init_options()
                try:
                    opt = self._options.get_full_analysis(ticker)
                    candidate.max_pain = opt.get("max_pain", 0) or 0
                    candidate.max_pain_distance_pct = opt.get("max_pain_distance_pct", 0)
                    candidate.put_call_ratio = opt.get("put_call_ratio", 0) or 0
                    candidate.mm_bias = opt.get("mm_bias", "NEUTRAL")
                    if opt.get("gex"):
                        candidate.gex_positive = opt["gex"].get("gex_positive", True)
                    logger.info(
                        f"  {ticker} Options → MP=${candidate.max_pain} "
                        f"(dist={candidate.max_pain_distance_pct:+.1f}%), "
                        f"PCR={candidate.put_call_ratio:.2f}, "
                        f"MM={candidate.mm_bias}"
                    )
                except Exception as e:
                    logger.warning(f"Error opciones {ticker}: {e}")

            # Enriquecer con Sentimiento compuesto por ticker
            if include_breadth:
                self._init_breadth()
                opt_data = {
                    "put_call_ratio": candidate.put_call_ratio,
                    "max_pain_distance_pct": candidate.max_pain_distance_pct,
                    "gex": {"gex_positive": candidate.gex_positive},
                } if include_options else None
                sentiment = self._breadth.compute_ticker_sentiment(
                    ticker, options_data=opt_data,
                    breadth_data=breadth_data, fear_greed=fear_greed_data,
                )
                candidate.sentiment_score = sentiment["sentiment_score"]
                candidate.sentiment_rating = sentiment["rating"]
                candidate.fear_greed_macro = fear_greed_data.get("score", 50)
                candidate.sp500_breadth_pct = breadth_data.get("pct_above_200dma", 50) or 50

            # ── Enriquecer con GuruFocus Intelligence (NEW) ──
            if any([qgarp_data, insider_data, guru_tracking_data, risk_data, analyst_data, political_data]):
                self._init_gurufocus()

                # QGARP Score — replaces ad-hoc dcf_discount scoring
                if qgarp_data and ticker in qgarp_data:
                    scorecard = self._gurufocus.parse_qgarp_scorecard(ticker, qgarp_data[ticker])
                    candidate.qgarp_score = scorecard.total_score
                    candidate.piotroski_f_score = scorecard.piotroski_f_score
                    candidate.altman_z_score = scorecard.altman_z_score
                    if scorecard.gf_value_discount_pct > 0:
                        candidate.dcf_discount_pct = scorecard.gf_value_discount_pct

                    # Guru Valuation — real GF metrics for scoring
                    gv = self._gurufocus.parse_guru_valuation(
                        ticker, qgarp_data[ticker],
                        keyratios_data=qgarp_data[ticker].get("keyratios"),
                    )
                    candidate.price_to_gf_value = gv["price_to_gf_value"]
                    candidate.gf_value_discount_pct = gv["gf_value_discount_pct"]
                    candidate.ps_vs_historical = gv["ps_vs_historical"]
                    candidate.price_to_fcf = gv["price_to_fcf"]
                    candidate.fcf_margin = gv["fcf_margin"]
                    candidate.beneish_m_score = gv["beneish_m_score"]

                # Insider Conviction — replaces boolean insider_signal
                if insider_data and ticker in insider_data:
                    idata = insider_data[ticker]
                    insider = self._gurufocus.parse_insider_conviction(
                        ticker,
                        cluster_data=idata.get("cluster"),
                        ceo_data=idata.get("ceo"),
                        cfo_data=idata.get("cfo"),
                    )
                    candidate.insider_conviction_score = insider.conviction_score
                    candidate.insider_sentiment = insider.net_insider_sentiment

                # Guru Tracking — replaces boolean guru_accumulation
                if guru_tracking_data and ticker in guru_tracking_data:
                    guru = self._gurufocus.parse_guru_tracking(ticker, guru_tracking_data[ticker])
                    candidate.guru_accumulation = guru.accumulation
                    candidate.guru_conviction_score = guru.net_buying_score
                    candidate.guru_count = guru.guru_count

                # 5D Risk Matrix
                if risk_data and ticker in risk_data:
                    risk = self._gurufocus.parse_risk_matrix(ticker, risk_data[ticker])
                    candidate.risk_score_5d = risk.risk_score

                # Analyst Intelligence
                if analyst_data and ticker in analyst_data:
                    analyst = self._gurufocus.parse_analyst_intelligence(ticker, analyst_data[ticker])
                    candidate.analyst_consensus = analyst.consensus
                    candidate.analyst_upside_pct = analyst.price_target_upside_pct

                # Political Signal
                if political_data and ticker in political_data:
                    pol = self._gurufocus.parse_political_trades(ticker, political_data[ticker])
                    candidate.political_signal = pol.get("net_signal", "neutral")

            # Score compuesto
            candidate.score = self._compute_score(candidate)
            candidates.append(candidate)

        # Ordenar por score descendente
        candidates.sort(key=lambda c: c.score, reverse=True)

        logger.info(f"Universe Filter → {len(candidates)} candidatos finales")
        for c in candidates:
            opt_str = ""
            if include_options:
                opt_str = f" | MP_dist={c.max_pain_distance_pct:+.1f}% | PCR={c.put_call_ratio:.2f}"
            sent_str = ""
            if include_breadth:
                sent_str = f" | Sent={c.sentiment_score:.0f}({c.sentiment_rating})"
            logger.info(
                f"  {c.ticker:>6} | Score={c.score:.2f} | "
                f"Mom={c.relative_momentum:+.4f} | "
                f"Guru={'✅' if c.guru_accumulation else '—'}"
                f"{opt_str}{sent_str} | "
                f"Regime={c.regime.value}"
            )

        return candidates

    def _compute_score(self, c: UniverseCandidate) -> float:
        """
        Score compuesto ponderado INSTITUCIONAL.
        
        v3: "La Puerta Doble" - Purga de sesgos.
        Separa la evaluación fundamental de empresas maduras (Hohn Mode)
        de las empresas emergentes (Rule of 40 / Guru Conviction).
        No incluye momentum técnico, opciones, ni opiniones de analistas.
        """
        score = 0.0

        if c.is_emerging_gem:
            # ========================================================
            # RUTA B: GURU GEMS (EMPRESAS EMERGENTES)
            # ========================================================
            # Prioridad: Convicción Institucional y Crecimiento Unitario
            
            # Guru Conviction (35% peso)
            if c.guru_conviction_score > 0:
                score += min((c.guru_conviction_score / 100) * 35.0, 35.0)
            elif c.guru_accumulation:
                score += 15.0
            
            # Insider Conviction (25% peso)
            if c.insider_conviction_score > 0:
                score += min((c.insider_conviction_score / 100) * 25.0, 25.0)
            
            # Margen Bruto como Proxy de Pricing Power incipiente (15%)
            # Nota: Asumimos que viene cargado en dcf_discount_pct u otro campo 
            # de extensión si no está en dataclass base, pero usemos fcf_margin
            # si es positivo como proxy de calidad de conversión.
            if c.fcf_margin > 0:
                score += min(c.fcf_margin * 0.5, 15.0)
            
            # Crecimiento de ingresos y Rule of 40 (Bonus)
            if c.qgarp_score > 50:
                # Usamos qgarp > 50 como indicador de que al menos hay crecimiento 
                score += 15.0
            
            # Cero penalizaciones por FCF negativo, Altman bajo o valuación alta
        
        else:
            # ========================================================
            # RUTA A: S&P 500 (BLUE CHIPS / HOHN MODE)
            # ========================================================
            # Prioridad: ROIC, FCF Margins, Pricing Power, Calidad
            
            # QGARP Quality & Growth (30% peso)
            if c.qgarp_score > 0:
                score += (c.qgarp_score / 100) * 30.0
            
            # FCF Margin - Pricing Power puro (15% peso)
            if c.fcf_margin > 25:
                score += 15.0
            elif c.fcf_margin > 15:
                score += 10.0
            elif c.fcf_margin > 10:
                score += 5.0
            
            # Piotroski F-Score (10% peso)
            if c.piotroski_f_score >= 7:
                score += 10.0
            elif c.piotroski_f_score >= 5:
                score += 5.0
            
            # Guru Conviction (15% peso)
            if c.guru_conviction_score > 0:
                score += min((c.guru_conviction_score / 100) * 15.0, 15.0)
            elif c.guru_accumulation:
                score += 7.5
                
            # Insider Conviction (10% peso)
            if c.insider_conviction_score > 0:
                score += min((c.insider_conviction_score / 100) * 10.0, 10.0)
            
            # Valoración - Descuento GF Value (10% peso)
            if c.price_to_gf_value > 0:
                if c.price_to_gf_value < 0.8:
                    score += 10.0   # Subvaluado
                elif c.price_to_gf_value < 1.0:
                    score += 5.0    # Descuento ligero
                elif c.price_to_gf_value > 1.3:
                    # Penalización por caro, A MENOS QUE sea calidad de monopolio
                    if c.qgarp_score < 80 and c.fcf_margin < 20:
                        score -= 10.0
                elif c.price_to_gf_value > 1.15:
                    if c.qgarp_score < 70:
                        score -= 5.0
                        
            # Beneish M-Score (Penalización severa por manipulación contable)
            if c.beneish_m_score > -1.78 and c.beneish_m_score != -3.0:
                score -= 15.0
                
            # Altman Z-Score (Penalización por riesgo de quiebra)
            if c.altman_z_score > 0 and c.altman_z_score < 1.8:
                score -= 10.0

        return score
