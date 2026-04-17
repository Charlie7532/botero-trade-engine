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
"""
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Directorio de persistencia local
JOURNAL_DIR = Path(os.getenv("JOURNAL_DIR", "/root/botero-trade/data/journal"))
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = JOURNAL_DIR / "trade_journal.db"


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


class TradeJournal:
    """
    Gestor del Trade Journal.
    Persiste cada entrada en SQLite local + JSON para análisis.
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()
    
    def _init_db(self):
        """Crea las tablas si no existen."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                direction TEXT,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT,
                entry_time TEXT,
                exit_time TEXT,
                entry_price REAL,
                exit_price REAL,
                pnl_dollars REAL DEFAULT 0,
                pnl_pct REAL DEFAULT 0,
                pnl_r_multiple REAL DEFAULT 0,
                was_winner INTEGER DEFAULT 0,
                exit_reason TEXT,
                entry_thesis TEXT,
                alpha_score REAL,
                qualifier_grade TEXT,
                rs_vs_spy REAL,
                insider_signal TEXT,
                sector_alignment TEXT,
                lesson_learned TEXT,
                grade TEXT,
                full_data TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT,
                snapshot_type TEXT,
                timestamp TEXT,
                data TEXT,
                FOREIGN KEY (trade_id) REFERENCES trades(trade_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT,
                pattern_name TEXT,
                context TEXT,
                outcome TEXT,
                confidence REAL,
                created_at TEXT,
                FOREIGN KEY (trade_id) REFERENCES trades(trade_id)
            )
        """)
        conn.commit()
        conn.close()
        logger.info(f"Trade Journal DB: {self.db_path}")
    
    def open_trade(self, entry: TradeJournalEntry) -> str:
        """Registra una nueva entrada de trade."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO trades 
            (trade_id, ticker, direction, status, created_at, entry_time,
             entry_price, entry_thesis, alpha_score, qualifier_grade,
             rs_vs_spy, insider_signal, sector_alignment, full_data, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.trade_id, entry.ticker, entry.direction, 'OPEN',
            entry.created_at, entry.entry_time, entry.entry_price,
            entry.entry_thesis, entry.alpha_score, entry.qualifier_grade,
            entry.rs_vs_spy, entry.insider_signal, entry.sector_alignment,
            json.dumps(asdict(entry), default=str),
            datetime.now(UTC).isoformat(),
        ))
        
        # Guardar snapshot de entrada
        if entry.entry_snapshot:
            conn.execute("""
                INSERT INTO trade_snapshots (trade_id, snapshot_type, timestamp, data)
                VALUES (?, 'ENTRY', ?, ?)
            """, (entry.trade_id, entry.entry_time, json.dumps(entry.entry_snapshot)))
        
        conn.commit()
        conn.close()
        
        # También guardar JSON completo
        json_path = JOURNAL_DIR / f"{entry.trade_id}.json"
        with open(json_path, 'w') as f:
            json.dump(asdict(entry), f, indent=2, default=str)
        
        logger.info(f"📝 Journal OPEN: {entry.ticker} @ ${entry.entry_price:.2f} — {entry.entry_thesis[:80]}")
        return entry.trade_id
    
    def close_trade(self, entry: TradeJournalEntry) -> None:
        """Actualiza el journal al cerrar un trade."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE trades SET
                status = 'CLOSED',
                exit_time = ?,
                exit_price = ?,
                pnl_dollars = ?,
                pnl_pct = ?,
                pnl_r_multiple = ?,
                was_winner = ?,
                exit_reason = ?,
                lesson_learned = ?,
                grade = ?,
                full_data = ?,
                updated_at = ?
            WHERE trade_id = ?
        """, (
            entry.exit_time, entry.exit_price,
            entry.pnl_dollars, entry.pnl_pct, entry.pnl_r_multiple,
            1 if entry.was_winner else 0,
            entry.exit_reason, entry.lesson_learned, entry.grade,
            json.dumps(asdict(entry), default=str),
            datetime.now(UTC).isoformat(),
            entry.trade_id,
        ))
        
        # Guardar snapshot de salida
        if entry.exit_snapshot:
            conn.execute("""
                INSERT INTO trade_snapshots (trade_id, snapshot_type, timestamp, data)
                VALUES (?, 'EXIT', ?, ?)
            """, (entry.trade_id, entry.exit_time, json.dumps(entry.exit_snapshot)))
        
        # Guardar patrones
        for tag in entry.pattern_tags:
            conn.execute("""
                INSERT INTO patterns (trade_id, pattern_name, context, outcome, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                entry.trade_id, tag, entry.entry_thesis,
                'WIN' if entry.was_winner else 'LOSS',
                abs(entry.pnl_r_multiple),
                datetime.now(UTC).isoformat(),
            ))
        
        conn.commit()
        conn.close()
        
        # Actualizar JSON
        json_path = JOURNAL_DIR / f"{entry.trade_id}.json"
        with open(json_path, 'w') as f:
            json.dump(asdict(entry), f, indent=2, default=str)
        
        emoji = "✅" if entry.was_winner else "❌"
        logger.info(
            f"{emoji} Journal CLOSE: {entry.ticker} "
            f"PnL: {entry.pnl_pct:+.2f}% (${entry.pnl_dollars:+,.0f}) "
            f"R: {entry.pnl_r_multiple:+.2f} "
            f"Reason: {entry.exit_reason} "
            f"Grade: {entry.grade}"
        )
    
    def get_performance_summary(self) -> dict:
        """Resumen de performance de todos los trades cerrados."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT * FROM trades WHERE status = 'CLOSED'"
        )
        rows = cursor.fetchall()
        cols = [d[0] for d in cursor.description]
        trades = [dict(zip(cols, r)) for r in rows]
        conn.close()
        
        if not trades:
            return {"total_trades": 0, "message": "Sin trades cerrados"}
        
        wins = [t for t in trades if t['was_winner']]
        losses = [t for t in trades if not t['was_winner']]
        
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
        """Estadísticas de patrones para aprendizaje."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT pattern_name, 
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                   AVG(confidence) as avg_confidence
            FROM patterns
            GROUP BY pattern_name
            ORDER BY total DESC
        """)
        results = [
            {
                "pattern": r[0],
                "total": r[1],
                "wins": r[2],
                "win_rate": r[2] / r[1] * 100 if r[1] > 0 else 0,
                "avg_r": r[3],
            }
            for r in cursor.fetchall()
        ]
        conn.close()
        return results
    
    def get_exit_reason_stats(self) -> list[dict]:
        """Estadísticas por razón de salida para ajustar trailing/exits."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT exit_reason,
                   COUNT(*) as total,
                   SUM(CASE WHEN was_winner = 1 THEN 1 ELSE 0 END) as wins,
                   AVG(pnl_pct) as avg_pnl,
                   AVG(pnl_r_multiple) as avg_r
            FROM trades
            WHERE status = 'CLOSED' AND exit_reason IS NOT NULL
            GROUP BY exit_reason
            ORDER BY total DESC
        """)
        results = [
            {
                "exit_reason": r[0],
                "total": r[1],
                "wins": r[2],
                "win_rate": r[2] / r[1] * 100 if r[1] > 0 else 0,
                "avg_pnl": r[3],
                "avg_r": r[4],
            }
            for r in cursor.fetchall()
        ]
        conn.close()
        return results
    
    def get_open_trades(self) -> list[dict]:
        """Retorna trades abiertos."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT trade_id, ticker, entry_price, entry_time, alpha_score, qualifier_grade "
            "FROM trades WHERE status = 'OPEN'"
        )
        results = [dict(zip([d[0] for d in cursor.description], r)) for r in cursor.fetchall()]
        conn.close()
        return results
