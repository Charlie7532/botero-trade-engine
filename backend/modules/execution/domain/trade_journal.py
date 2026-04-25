"""
TRADE JOURNAL: Sistema de Registro Institucional
=================================================
"No hay que llegar primero, hay que saber llegar."

Cada trade se registra con TODAS las variables que lo motivaron.
Al cierre, se anota resultado, lecciones, y patrones.
Esto alimenta el sistema de aprendizaje continuo.

Estructura del Journal Entry:
─ PRE-TRADE: Qué vemos antes de entrar
─ EXECUTION: Qué pasó al ejecutar
─ POST-TRADE: Resultado y análisis
─ LESSONS: Qué aprendimos

Persistencia: MongoDB Atlas (migrado desde SQLite + JSON dual-write).
Cada trade es un documento completo — sin JSON blobs en columnas SQL.
"""
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional

from pymongo import MongoClient, ASCENDING, DESCENDING

logger = logging.getLogger(__name__)

# MongoDB connection — lazy singleton
_mongo_client: Optional[MongoClient] = None

MONGODB_URI = os.getenv(
    "MONGODB_URI", "mongodb://localhost:27017"
)
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "botero_trade")


def _get_mongo_db():
    """Lazy singleton para la conexión MongoDB."""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        logger.info(f"MongoDB conectado: {MONGODB_DB_NAME}")
    return _mongo_client[MONGODB_DB_NAME]


@dataclass
class MarketSnapshot:
    """Estado completo del mercado al momento de una decisión."""
    timestamp: str
    # Precio
    price: float
    daily_change_pct: float
    distance_from_20sma_pct: float
    distance_from_52w_high_pct: float
    # Volumen
    volume: float
    relative_volume: float
    volume_trend: str  # accumulation, distribution, neutral
    # Técnicos
    atr: float
    atr_pct: float
    rsi_14: float
    macd_signal: str  # bullish, bearish, neutral
    bollinger_position: str  # upper, middle, lower
    # Macro
    vix: float
    spy_daily_change_pct: float
    yield_spread_10y_13w: float
    # Breadth
    s5th_pct: float  # % stocks sobre 200MA
    s5tw_pct: float  # % stocks sobre 20MA
    fear_greed_index: float
    # Sector
    sector: str
    sector_breadth_pct: float
    sector_vs_spy_rs: float
    tide_wave_status: str  # WITH_TIDE, AGAINST_TIDE, etc.


@dataclass
class TradeJournalEntry:
    """Registro completo de un trade, de principio a fin."""
    # ─── IDENTIDAD ───
    trade_id: str
    ticker: str
    direction: str  # LONG, SHORT
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    
    # ─── PRE-TRADE: ¿Por qué entramos? ───
    entry_thesis: str = ""  # Tesis en texto libre
    alpha_score: float = 0.0
    qualifier_grade: str = ""
    qualifier_edge_score: float = 0.0
    optimal_model: str = ""  # lstm, xgboost
    lstm_probability: float = 0.0
    xgb_probability: float = 0.0
    
    # Señales que motivaron la entrada
    rs_vs_spy: float = 0.0
    rs_vs_sector: float = 0.0
    insider_signal: str = ""  # strong_buy, buy, neutral, caution
    insider_detail: str = ""
    earnings_safe: bool = True
    earnings_days: int = -1
    sector_alignment: str = ""  # WITH_TIDE, AGAINST_TIDE
    capitulation_level: int = 0
    
    # ─── MARKET SNAPSHOT AL ENTRAR ───
    entry_snapshot: Optional[dict] = None
    
    # ─── EXECUTION ───
    entry_price: float = 0.0
    entry_time: str = ""
    entry_shares: float = 0.0
    entry_notional: float = 0.0
    entry_kelly_pct: float = 0.0
    entry_portfolio_pct: float = 0.0
    entry_state: str = "PROBING"  # PROBING, SCALING_IN
    entry_order_id: str = ""
    entry_fill_price: float = 0.0
    entry_slippage: float = 0.0  # entry_fill_price - entry_price
    
    # ─── TRAILING STOP CONFIG ───
    trailing_type: str = "adaptive"  # adaptive, fixed, atr
    trailing_atr_mult: float = 3.0
    trailing_fixed_pct: float = 0.10
    initial_stop_price: float = 0.0
    current_stop_price: float = 0.0
    
    # ─── EVOLUTION (actualizado durante el trade) ───
    highest_price: float = 0.0
    lowest_price: float = 0.0
    max_favorable_excursion_pct: float = 0.0  # MFE: Máximo a favor
    max_adverse_excursion_pct: float = 0.0    # MAE: Máximo en contra
    bars_held: int = 0
    scaling_events: list = field(default_factory=list)  # [{type, price, time}]
    stop_adjustments: list = field(default_factory=list)
    
    # ─── EXIT ───
    exit_price: float = 0.0
    exit_time: str = ""
    exit_reason: str = ""  # STOP_HIT, RS_DECAY, ROTATION, TAKE_PROFIT, MANUAL
    exit_order_id: str = ""
    exit_fill_price: float = 0.0
    exit_slippage: float = 0.0
    exit_snapshot: Optional[dict] = None
    
    # ─── POST-TRADE RESULTS ───
    pnl_dollars: float = 0.0
    pnl_pct: float = 0.0
    pnl_r_multiple: float = 0.0  # PnL en términos de riesgo inicial
    was_winner: bool = False
    
    # ─── ANALYSIS ───
    what_went_right: str = ""
    what_went_wrong: str = ""
    lesson_learned: str = ""
    pattern_tags: list = field(default_factory=list)  # ['breakout', 'contrarian', 'mean_reversion']
    grade: str = ""  # A, B, C, D, F (calidad de la ejecución, no solo resultado)
    
    # ─── META ───
    status: str = "OPEN"  # OPEN, CLOSED, CANCELLED
    strategy_bucket: str = "CORE"  # CORE, TACTICAL, UNCLASSIFIED
    
    # ─── V2: Entry Intelligence Context ───
    # Full EntryIntelligenceReport captured for ML and post-mortem analysis.
    # Contains ~40 variables: VIX, Gamma Regime, Wyckoff State, Whale Flow,
    # Phase, R:R, dimensions confirming, Put Wall, Call Wall, etc.
    entry_intelligence: Optional[dict] = None


class TradeJournal:
    """
    Gestor del Trade Journal.
    Persiste cada entrada en MongoDB Atlas como documento nativo.

    Migrado desde SQLite + JSON dual-write. Ahora cada trade es un
    documento completo sin el anti-patrón full_data TEXT blob.
    """
    
    def __init__(self, db=None, db_name: str = None):
        """
        Args:
            db: Instancia de pymongo Database (para tests con mongomock).
                Si None, usa la conexión real a MongoDB Atlas.
            db_name: Nombre alternativo de la DB (para tests).
        """
        if db is not None:
            self._db = db
        else:
            if db_name:
                global _mongo_client
                if _mongo_client is None:
                    _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
                self._db = _mongo_client[db_name]
            else:
                self._db = _get_mongo_db()
        self._init_collections()
    
    def _init_collections(self):
        """Crea índices en las colecciones si no existen."""
        self.trades = self._db["trades"]
        self.snapshots = self._db["trade_snapshots"]
        self.patterns = self._db["patterns"]
        
        # Índices para queries frecuentes
        self.trades.create_index("trade_id", unique=True)
        self.trades.create_index([("ticker", ASCENDING), ("status", ASCENDING)])
        self.trades.create_index([("created_at", DESCENDING)])
        self.trades.create_index([("exit_reason", ASCENDING), ("was_winner", ASCENDING)])
        
        self.snapshots.create_index([("trade_id", ASCENDING), ("snapshot_type", ASCENDING)])
        self.patterns.create_index([("trade_id", ASCENDING)])
        self.patterns.create_index([("pattern_name", ASCENDING)])
        
        # V7 Note: Atlas Vector Search index is created via Atlas UI or Admin API,
        # not standard pymongo. It should index the `entry_vector` field on `trades`.
        
        logger.info(f"Trade Journal MongoDB: {self._db.name}")
    
    def open_trade(self, entry: TradeJournalEntry) -> str:
        """Registra una nueva entrada de trade."""
        doc = asdict(entry)
        doc["_trade_id"] = entry.trade_id  # Redundante pero útil para queries
        doc["updated_at"] = datetime.now(UTC).isoformat()
        
        self.trades.insert_one(doc)
        
        # Guardar snapshot de entrada como subdocumento separado
        if entry.entry_snapshot:
            self.snapshots.insert_one({
                "trade_id": entry.trade_id,
                "snapshot_type": "ENTRY",
                "timestamp": entry.entry_time,
                "data": entry.entry_snapshot,
            })
        
        logger.info(f"📝 Journal OPEN: {entry.ticker} @ ${entry.entry_price:.2f} — {entry.entry_thesis[:80]}")
        return entry.trade_id
    
    def close_trade(self, entry: TradeJournalEntry) -> None:
        """Actualiza el journal al cerrar un trade."""
        update_fields = {
            "status": "CLOSED",
            "exit_time": entry.exit_time,
            "exit_price": entry.exit_price,
            "exit_order_id": entry.exit_order_id,
            "exit_fill_price": entry.exit_fill_price,
            "exit_slippage": entry.exit_slippage,
            "exit_snapshot": entry.exit_snapshot,
            "pnl_dollars": entry.pnl_dollars,
            "pnl_pct": entry.pnl_pct,
            "pnl_r_multiple": entry.pnl_r_multiple,
            "was_winner": entry.was_winner,
            "exit_reason": entry.exit_reason,
            "what_went_right": entry.what_went_right,
            "what_went_wrong": entry.what_went_wrong,
            "lesson_learned": entry.lesson_learned,
            "grade": entry.grade,
            "pattern_tags": entry.pattern_tags,
            "highest_price": entry.highest_price,
            "lowest_price": entry.lowest_price,
            "max_favorable_excursion_pct": entry.max_favorable_excursion_pct,
            "max_adverse_excursion_pct": entry.max_adverse_excursion_pct,
            "bars_held": entry.bars_held,
            "scaling_events": entry.scaling_events,
            "stop_adjustments": entry.stop_adjustments,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        
        self.trades.update_one(
            {"trade_id": entry.trade_id},
            {"$set": update_fields},
        )
        
        # Guardar snapshot de salida
        if entry.exit_snapshot:
            self.snapshots.insert_one({
                "trade_id": entry.trade_id,
                "snapshot_type": "EXIT",
                "timestamp": entry.exit_time,
                "data": entry.exit_snapshot,
            })
        # Guardar patrones
        if entry.pattern_tags:
            pattern_docs = [
                {
                    "trade_id": entry.trade_id,
                    "pattern_name": tag,
                    "context": entry.entry_thesis,
                    "outcome": "WIN" if entry.was_winner else "LOSS",
                    "confidence": abs(entry.pnl_r_multiple),
                    "created_at": datetime.now(UTC).isoformat(),
                }
                for tag in entry.pattern_tags
            ]
            self.patterns.insert_many(pattern_docs)
        
        emoji = "✅" if entry.was_winner else "❌"
        logger.info(
            f"{emoji} Journal CLOSE: {entry.ticker} "
            f"PnL: {entry.pnl_pct:+.2f}% (${entry.pnl_dollars:+,.0f}) "
            f"R: {entry.pnl_r_multiple:+.2f} "
            f"Reason: {entry.exit_reason} "
            f"Grade: {entry.grade}"
        )
    
    def get_trade_full_data(self, trade_id: str) -> Optional[dict]:
        """
        Retorna el documento completo de un trade por ID.
        Reemplaza el patrón SQLite de leer full_data TEXT blob.
        """
        doc = self.trades.find_one({"trade_id": trade_id}, {"_id": 0})
        return doc
    
    def get_performance_summary(self) -> dict:
        """Resumen de performance de todos los trades cerrados."""
        trades = list(self.trades.find(
            {"status": "CLOSED"},
            {"_id": 0},
        ))
        
        if not trades:
            return {"total_trades": 0, "message": "Sin trades cerrados"}
        
        wins = [t for t in trades if t.get('was_winner')]
        losses = [t for t in trades if not t.get('was_winner')]
        
        avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0
        
        return {
            "total_trades": len(trades),
            "winners": len(wins),
            "losers": len(losses),
            "win_rate": len(wins) / len(trades) * 100 if trades else 0,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "total_pnl": sum(t['pnl_dollars'] for t in trades),
            "profit_factor": abs(
                sum(t['pnl_dollars'] for t in wins) / 
                sum(t['pnl_dollars'] for t in losses)
            ) if losses and sum(t['pnl_dollars'] for t in losses) != 0 else 0,
            "best_trade": max(trades, key=lambda t: t['pnl_pct']),
            "worst_trade": min(trades, key=lambda t: t['pnl_pct']),
        }
    
    def get_pattern_stats(self) -> list[dict]:
        """Estadísticas de patrones para aprendizaje — usando aggregation pipeline."""
        pipeline = [
            {"$group": {
                "_id": "$pattern_name",
                "total": {"$sum": 1},
                "wins": {"$sum": {"$cond": [{"$eq": ["$outcome", "WIN"]}, 1, 0]}},
                "avg_confidence": {"$avg": "$confidence"},
            }},
            {"$sort": {"total": -1}},
            {"$project": {
                "_id": 0,
                "pattern": "$_id",
                "total": 1,
                "wins": 1,
                "win_rate": {
                    "$cond": [
                        {"$gt": ["$total", 0]},
                        {"$multiply": [{"$divide": ["$wins", "$total"]}, 100]},
                        0,
                    ]
                },
                "avg_r": "$avg_confidence",
            }},
        ]
        return list(self.patterns.aggregate(pipeline))
    
    def get_exit_reason_stats(self) -> list[dict]:
        """Estadísticas por razón de salida — usando aggregation pipeline."""
        pipeline = [
            {"$match": {
                "status": "CLOSED",
                "exit_reason": {"$ne": None, "$ne": ""},
            }},
            {"$group": {
                "_id": "$exit_reason",
                "total": {"$sum": 1},
                "wins": {"$sum": {"$cond": [{"$eq": ["$was_winner", True]}, 1, 0]}},
                "avg_pnl": {"$avg": "$pnl_pct"},
                "avg_r": {"$avg": "$pnl_r_multiple"},
            }},
            {"$sort": {"total": -1}},
            {"$project": {
                "_id": 0,
                "exit_reason": "$_id",
                "total": 1,
                "wins": 1,
                "win_rate": {
                    "$cond": [
                        {"$gt": ["$total", 0]},
                        {"$multiply": [{"$divide": ["$wins", "$total"]}, 100]},
                        0,
                    ]
                },
                "avg_pnl": 1,
                "avg_r": 1,
            }},
        ]
        return list(self.trades.aggregate(pipeline))
    
    def get_open_trades(self) -> list[dict]:
        """Retorna trades abiertos."""
        return list(self.trades.find(
            {"status": "OPEN"},
            {
                "_id": 0,
                "trade_id": 1,
                "ticker": 1,
                "entry_price": 1,
                "entry_time": 1,
                "alpha_score": 1,
                "qualifier_grade": 1,
                "strategy_bucket": 1,
            },
        ))

    # ═══════════════════════════════════════════════════════════
    # V7: VECTOR SEARCH MEMORY
    # ═══════════════════════════════════════════════════════════

    def find_similar_trades(self, vector: list[float], limit: int = 5) -> list[dict]:
        """
        Consulta la base de datos vectorial de MongoDB Atlas para encontrar
        trades históricos similares a las condiciones actuales de mercado.
        
        Requiere un Atlas Vector Search Index en el campo `entry_vector`.
        """
        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "entry_vector",
                        "queryVector": vector,
                        "numCandidates": 100,
                        "limit": limit
                    }
                },
                {
                    "$project": {
                        "trade_id": 1,
                        "ticker": 1,
                        "status": 1,
                        "was_winner": 1,
                        "exit_reason": 1,
                        "pnl_pct": 1,
                        "grade": 1,
                        "lesson_learned": 1,
                        "score": { "$meta": "vectorSearchScore" }
                    }
                }
            ]
            results = list(self.trades.aggregate(pipeline))
            return results
        except Exception as e:
            logger.warning(f"Vector Search no disponible o falló: {e}")
            return []
