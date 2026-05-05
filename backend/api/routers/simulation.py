"""
Simulation API Router — REST Endpoints
==========================================
Exposes simulation capabilities via FastAPI REST endpoints.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["Simulation"])


# ── Request/Response schemas ──────────────────────────────

class CalibrateRequest(BaseModel):
    ticker: str
    timeframe: str = "1d"
    category: str = "SPECULATIVE_SPRING"


class CalibrateResponse(BaseModel):
    ticker: str
    category: str
    n_viable_signals: int
    calibration_sharpe: float
    signal_weights: dict


class GateRequest(BaseModel):
    ticker: str
    category: str = "QUALITY_VALUE"
    portfolio_id: str = ""


class GateResponse(BaseModel):
    approved: bool
    reason: str
    conviction: float
    snapshot_id: str
    execution_intent: dict | None = None


class QualityResponse(BaseModel):
    ticker: str | None
    category: str | None
    total_trades: int
    signals: list[dict]
    recommendation: str


# ── Endpoints ─────────────────────────────────────────────

@router.post("/calibrate", response_model=CalibrateResponse)
async def calibrate_strategy(req: CalibrateRequest):
    """Run full calibration pipeline for a ticker × category."""
    try:
        from backend.modules.simulation.domain.entities.strategy_profile import InvestmentCategory
        from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
        from backend.modules.simulation.infrastructure.triple_barrier_adapter import TripleBarrierAdapter
        from backend.modules.simulation.infrastructure.signal_adapters import create_all_signals
        from backend.modules.simulation.application.use_cases.oracle_backtest import OracleBacktester
        from backend.modules.simulation.application.use_cases.calibrate_strategy import StrategyCalibrator

        store = TimescaleDataStore()
        labeler = TripleBarrierAdapter()
        oracle = OracleBacktester(store, labeler)
        signals = create_all_signals()

        category = InvestmentCategory(req.category)
        calibrator = StrategyCalibrator(store, oracle, signals)
        profile = calibrator.calibrate(req.ticker, req.timeframe, category)

        return CalibrateResponse(
            ticker=profile.ticker,
            category=profile.category.value,
            n_viable_signals=len(profile.enabled_signals),
            calibration_sharpe=profile.calibration_sharpe,
            signal_weights={s.name: s.weight for s in profile.enabled_signals},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Calibration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gate", response_model=GateResponse)
async def evaluate_gate(req: GateRequest):
    """Run pre-trade gate evaluation."""
    try:
        from backend.modules.simulation.domain.entities.strategy_profile import InvestmentCategory
        from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
        from backend.modules.simulation.infrastructure.smc_adapter import SMCAdapter
        from backend.modules.simulation.infrastructure.signal_adapters import create_all_signals
        from backend.modules.simulation.application.use_cases.strategy_composer import StrategyComposer
        from backend.modules.simulation.application.use_cases.pre_trade_gate import PreTradeGate

        store = TimescaleDataStore()
        category = InvestmentCategory(req.category)

        # Load profile
        profile_data = store.load_profile(category.value, req.ticker)
        if not profile_data:
            raise HTTPException(
                status_code=404,
                detail=f"No calibrated profile for {req.ticker}/{category.value}. Run /calibrate first.",
            )

        from backend.modules.simulation.domain.entities.strategy_profile import StrategyProfile, SignalConfig
        profile = StrategyProfile(
            ticker=req.ticker,
            category=category,
            signals=[SignalConfig(**s) for s in profile_data.get("signals", [])],
        )

        gate = PreTradeGate(
            store=store,
            structure_analyzer=SMCAdapter(),
            signals=create_all_signals(),
            composer=StrategyComposer(),
        )

        intent, snapshot = gate.evaluate(
            ticker=req.ticker,
            category=category,
            profile=profile,
            portfolio_id=req.portfolio_id,
        )

        from dataclasses import asdict
        return GateResponse(
            approved=snapshot.gate_approved,
            reason=snapshot.gate_reason,
            conviction=snapshot.gate_conviction,
            snapshot_id=snapshot.snapshot_id,
            execution_intent=asdict(intent) if intent else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gate evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality", response_model=QualityResponse)
async def quality_report(
    ticker: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    """Get per-signal quality report from vaulted trade history."""
    try:
        from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
        from backend.modules.simulation.application.use_cases.analyze_indicators import IndicatorAnalyzer

        store = TimescaleDataStore()
        analyzer = IndicatorAnalyzer(store)
        report = analyzer.quality_report(ticker=ticker, category=category)

        return QualityResponse(
            ticker=report.ticker,
            category=report.category,
            total_trades=report.total_with_outcomes,
            signals=[
                {
                    "name": s.name,
                    "precision": s.precision,
                    "appearances": s.total_appearances,
                    "lift": s.lift,
                    "avg_pnl_active": s.avg_pnl_when_active,
                }
                for s in report.signals
            ],
            recommendation=report.recommendation,
        )
    except Exception as e:
        logger.error(f"Quality report failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/retrain-check")
async def check_retrain(ticker: str, category: str):
    """Check if recalibration is needed."""
    try:
        from backend.modules.simulation.infrastructure.timescale_data_store import TimescaleDataStore
        from backend.modules.simulation.application.use_cases.analyze_indicators import IndicatorAnalyzer
        from backend.modules.simulation.application.use_cases.retrain_trigger import RetrainTrigger

        store = TimescaleDataStore()
        analyzer = IndicatorAnalyzer(store)
        trigger = RetrainTrigger(store, analyzer)
        result = trigger.check(ticker, category)

        return {
            "needs_retrain": result["needs_retrain"],
            "reasons": result["reasons"],
            "profile_age_days": result["profile_age_days"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
