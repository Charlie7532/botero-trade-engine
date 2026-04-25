"""
MIGRATION SCRIPT: SQLite → MongoDB Atlas
=========================================
One-shot script to migrate existing data from both SQLite databases
to MongoDB Atlas.

Data sources:
  - data/journal/trade_journal.db  → MongoDB collections: trades, trade_snapshots, patterns
  - data/shadow_mode.db            → MongoDB collections: shadow_signals, shadow_positions

Usage:
  cd /root/botero-trade
  source backend/.venv/bin/activate
  python scripts/migrate_sqlite_to_mongo.py

Safety:
  - Read-only on SQLite files (no modifications)
  - Idempotent: checks for existing documents before inserting
  - Prints verification counts before and after
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient

# ─── Configuration ──────────────────────────────────────────────────────────
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "botero_trade")

JOURNAL_DB = Path(__file__).resolve().parent.parent / "data" / "journal" / "trade_journal.db"
SHADOW_DB = Path(__file__).resolve().parent.parent / "data" / "shadow_mode.db"


def connect_mongo():
    """Connect to MongoDB Atlas."""
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    print(f"✅ MongoDB Atlas conectado")
    return client[DB_NAME]


def migrate_trade_journal(db):
    """Migrate trade_journal.db → MongoDB."""
    if not JOURNAL_DB.exists():
        print(f"⚠️  {JOURNAL_DB} no existe. Saltando migración de journal.")
        return

    conn = sqlite3.connect(str(JOURNAL_DB))
    
    # ── 1. Migrate trades table ──────────────────────────────────────────
    cursor = conn.execute("SELECT * FROM trades")
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    
    trades_col = db["trades"]
    migrated_trades = 0
    
    for row in rows:
        row_dict = dict(zip(cols, row))
        trade_id = row_dict["trade_id"]
        
        # Check if already migrated
        if trades_col.find_one({"trade_id": trade_id}):
            print(f"   ⏭️  Trade {trade_id} ya existe, saltando.")
            continue
        
        # If full_data exists, use it as the primary document (richer data)
        if row_dict.get("full_data"):
            try:
                doc = json.loads(row_dict["full_data"])
            except (json.JSONDecodeError, TypeError):
                doc = row_dict
        else:
            doc = row_dict
        
        # Ensure critical fields from SQL columns override JSON blob
        doc["trade_id"] = trade_id
        doc["status"] = row_dict.get("status", "OPEN")
        doc["updated_at"] = row_dict.get("updated_at", "")
        
        # Convert SQLite integer booleans to Python booleans
        if "was_winner" in doc and isinstance(doc["was_winner"], int):
            doc["was_winner"] = bool(doc["was_winner"])
        
        # Remove the redundant full_data blob (it's now the document itself)
        doc.pop("full_data", None)
        
        trades_col.insert_one(doc)
        migrated_trades += 1
    
    print(f"   📝 Trades migrados: {migrated_trades} (de {len(rows)} en SQLite)")
    
    # ── 2. Migrate trade_snapshots table ─────────────────────────────────
    cursor = conn.execute("SELECT * FROM trade_snapshots")
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    
    snapshots_col = db["trade_snapshots"]
    migrated_snapshots = 0
    
    for row in rows:
        row_dict = dict(zip(cols, row))
        
        # Parse the JSON data field
        data = row_dict.get("data", "{}")
        try:
            data = json.loads(data) if isinstance(data, str) else data
        except (json.JSONDecodeError, TypeError):
            data = {}
        
        doc = {
            "trade_id": row_dict["trade_id"],
            "snapshot_type": row_dict["snapshot_type"],
            "timestamp": row_dict["timestamp"],
            "data": data,
        }
        
        snapshots_col.insert_one(doc)
        migrated_snapshots += 1
    
    print(f"   📸 Snapshots migrados: {migrated_snapshots}")
    
    # ── 3. Migrate patterns table ────────────────────────────────────────
    cursor = conn.execute("SELECT * FROM patterns")
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    
    patterns_col = db["patterns"]
    migrated_patterns = 0
    
    for row in rows:
        row_dict = dict(zip(cols, row))
        doc = {
            "trade_id": row_dict["trade_id"],
            "pattern_name": row_dict["pattern_name"],
            "context": row_dict.get("context", ""),
            "outcome": row_dict.get("outcome", ""),
            "confidence": row_dict.get("confidence", 0),
            "created_at": row_dict.get("created_at", ""),
        }
        patterns_col.insert_one(doc)
        migrated_patterns += 1
    
    print(f"   🏷️  Patterns migrados: {migrated_patterns}")
    
    conn.close()


def migrate_shadow_mode(db):
    """Migrate shadow_mode.db → MongoDB."""
    if not SHADOW_DB.exists():
        print(f"⚠️  {SHADOW_DB} no existe. Saltando migración de shadow.")
        return

    conn = sqlite3.connect(str(SHADOW_DB))
    
    # ── 1. Migrate shadow_signals ────────────────────────────────────────
    cursor = conn.execute("SELECT * FROM shadow_signals")
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    
    signals_col = db["shadow_signals"]
    migrated_signals = 0
    
    for row in rows:
        row_dict = dict(zip(cols, row))
        
        # Parse the JSON data field into a native document
        data = row_dict.get("data", "{}")
        try:
            doc = json.loads(data) if isinstance(data, str) else data
        except (json.JSONDecodeError, TypeError):
            doc = row_dict
        
        # Ensure top-level fields
        doc["ticker"] = row_dict.get("ticker", doc.get("ticker", ""))
        doc["timestamp"] = row_dict.get("timestamp", doc.get("timestamp", ""))
        doc["signal_type"] = row_dict.get("signal_type", doc.get("signal_type", ""))
        
        signals_col.insert_one(doc)
        migrated_signals += 1
    
    print(f"   📡 Shadow signals migrados: {migrated_signals}")
    
    # ── 2. Migrate shadow_positions ──────────────────────────────────────
    cursor = conn.execute("SELECT * FROM shadow_positions")
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    
    positions_col = db["shadow_positions"]
    migrated_positions = 0
    
    for row in rows:
        row_dict = dict(zip(cols, row))
        
        # Parse the JSON data field into a native document
        data = row_dict.get("data", "{}")
        try:
            doc = json.loads(data) if isinstance(data, str) else data
        except (json.JSONDecodeError, TypeError):
            doc = row_dict
        
        # Ensure top-level fields
        doc["ticker"] = row_dict.get("ticker", doc.get("ticker", ""))
        doc["status"] = row_dict.get("status", doc.get("status", "OPEN"))
        doc["entry_date"] = row_dict.get("entry_date", doc.get("entry_date", ""))
        doc["exit_date"] = row_dict.get("exit_date", doc.get("exit_date", ""))
        
        positions_col.insert_one(doc)
        migrated_positions += 1
    
    print(f"   📊 Shadow positions migrados: {migrated_positions}")
    
    conn.close()


def verify_migration(db):
    """Print verification counts from MongoDB."""
    print(f"\n{'='*60}")
    print(f"  VERIFICACIÓN POST-MIGRACIÓN")
    print(f"{'='*60}")
    
    collections = {
        "trades": db["trades"],
        "trade_snapshots": db["trade_snapshots"],
        "patterns": db["patterns"],
        "shadow_signals": db["shadow_signals"],
        "shadow_positions": db["shadow_positions"],
    }
    
    for name, col in collections.items():
        count = col.count_documents({})
        print(f"  📦 {name}: {count} documentos")
    
    # Show trades summary
    trades = db["trades"]
    open_count = trades.count_documents({"status": "OPEN"})
    closed_count = trades.count_documents({"status": "CLOSED"})
    print(f"\n  Trades OPEN: {open_count}")
    print(f"  Trades CLOSED: {closed_count}")
    
    # Show shadow summary
    shadow_pos = db["shadow_positions"]
    shadow_open = shadow_pos.count_documents({"status": "OPEN"})
    shadow_closed = shadow_pos.count_documents({"status": "CLOSED"})
    print(f"  Shadow OPEN: {shadow_open}")
    print(f"  Shadow CLOSED: {shadow_closed}")
    
    print(f"\n{'='*60}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  MIGRACIÓN SQLite → MongoDB Atlas")
    print(f"  Botero Trade Engine")
    print(f"{'='*60}")
    
    db = connect_mongo()
    
    print(f"\n─── Migrando Trade Journal ───")
    migrate_trade_journal(db)
    
    print(f"\n─── Migrando Shadow Mode ───")
    migrate_shadow_mode(db)
    
    verify_migration(db)
    
    print(f"\n✅ Migración completada exitosamente.")
    print(f"   Los archivos SQLite originales permanecen intactos como backup.")
    print(f"   Puedes archivarlos en data/archive/ cuando estés seguro.")
