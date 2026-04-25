import logging
from datetime import datetime, UTC
from typing import Optional
from pymongo import MongoClient, ASCENDING, DESCENDING
from dataclasses import asdict
import os

from backend.modules.execution.domain.entities.trade_record import TradeJournalEntry

logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv(
    "MONGODB_URI", "mongodb://localhost:27017"
)
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "botero_trade")

_mongo_client: Optional[MongoClient] = None

def _get_mongo_db():
    """Lazy singleton para la conexión MongoDB."""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        logger.info(f"MongoDB conectado: {MONGODB_DB_NAME}")
    return _mongo_client[MONGODB_DB_NAME]

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
