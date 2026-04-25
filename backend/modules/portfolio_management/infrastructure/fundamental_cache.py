"""
Fundamental Data Cache Manager
==============================
Gestiona la persistencia de datos fundamentales en MongoDB.
Evita golpear las APIs de GuruFocus/Finnhub de forma innecesaria.
Utiliza la "Huella Digital Financiera" y el Calendario de Earnings
para invalidar inteligentemente la caché.
"""
import os
import logging
from datetime import datetime, UTC
from typing import Optional, Dict, Any

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger(__name__)

class FundamentalCache:
    def __init__(self, mongo_uri: str = None):
        self._uri = mongo_uri or os.getenv("MONGODB_URI", "")
        self._client = None
        self._db = None
        self._collection = None
        self._available = False
        
        self._connect()

    def _connect(self):
        if not self._uri:
            logger.warning("MONGODB_URI no encontrada. Caché fundamental deshabilitada.")
            return
            
        try:
            self._client = MongoClient(self._uri, serverSelectionTimeoutMS=5000)
            self._client.admin.command('ping')
            self._db = self._client.get_database("botero_trade")
            self._collection = self._db.get_collection("fundamental_cache")
            
            # Crear índice para búsqueda rápida
            self._collection.create_index("ticker", unique=True)
            self._available = True
            logger.info("✅ Conexión a MongoDB (Fundamental Cache) establecida.")
        except Exception as e:
            logger.error(f"Error conectando a MongoDB para caché: {e}")
            self._available = False

    def get_cached_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Recupera datos fundamentales de la caché.
        Devuelve None si no existe o si está marcada como obsoleta 
        basado en el reloj de arena (next_earnings_date).
        """
        if not self._available:
            return None
            
        try:
            doc = self._collection.find_one({"ticker": ticker})
            if not doc:
                return None
                
            # Verificar expiración basada en fecha de ganancias
            status = doc.get("status", "fresh")
            next_earnings = doc.get("next_earnings_date")
            
            if next_earnings and status == "fresh":
                try:
                    earnings_date = datetime.strptime(next_earnings, "%Y-%m-%d").date()
                    today = datetime.now(UTC).date()
                    
                    # Si hoy es o ya pasó la fecha de earnings, la caché entra en pending
                    if today >= earnings_date:
                        self.mark_as_pending(ticker)
                        logger.info(f"⏳ {ticker}: Earnings day reached ({next_earnings}). Cache marcada como pending.")
                        return None # Forzar nueva descarga
                except ValueError:
                    pass
            
            # Si está en pending, intentaremos usar los datos viejos solo como último recurso
            # pero por diseño, preferimos retornar None para forzar al engine a verificar
            # si GuruFocus ya tiene los datos nuevos (la Huella Digital).
            if status == "update_pending":
                logger.debug(f"⏳ {ticker} tiene actualización pendiente de earnings.")
                # No retornamos None inmediatamente, dejamos que el orquestador 
                # decida si intenta descargar o usa lo viejo.
            
            return doc
            
        except Exception as e:
            logger.error(f"Error leyendo caché de {ticker}: {e}")
            return None

    def save_fundamental_data(self, ticker: str, data: Dict[str, Any], next_earnings_date: str = None) -> bool:
        """
        Guarda o actualiza la caché fundamental de un ticker.
        """
        if not self._available:
            return False
            
        try:
            doc = {
                "ticker": ticker,
                "data": data,
                "latest_quarter_date": data.get("latest_quarter_date", "unknown"),
                "status": "fresh",
                "last_updated": datetime.now(UTC).isoformat()
            }
            
            if next_earnings_date:
                doc["next_earnings_date"] = next_earnings_date
                
            self._collection.update_one(
                {"ticker": ticker},
                {"$set": doc},
                upsert=True
            )
            logger.debug(f"💾 Caché fundamental guardada para {ticker}")
            return True
            
        except Exception as e:
            logger.error(f"Error guardando caché de {ticker}: {e}")
            return False

    def mark_as_pending(self, ticker: str) -> bool:
        """Marca una caché como pendiente de actualización (e.g. llegó su día de earnings)"""
        if not self._available:
            return False
            
        try:
            self._collection.update_one(
                {"ticker": ticker},
                {"$set": {"status": "update_pending"}}
            )
            return True
        except Exception:
            return False

    def check_fingerprint_updated(self, ticker: str, new_quarter_date: str) -> bool:
        """
        Verifica si la huella digital (fecha fiscal) del nuevo payload
        es más reciente que la que tenemos en caché.
        """
        if not self._available:
            return True # Si no hay caché, asume que es nueva
            
        doc = self._collection.find_one({"ticker": ticker})
        if not doc:
            return True
            
        cached_date = doc.get("latest_quarter_date")
        
        # Si la fecha que nos manda GuruFocus es igual a la que ya teníamos,
        # significa que GuruFocus AÚN no ha procesado el reporte de earnings de hoy.
        if cached_date and cached_date != "unknown" and cached_date == new_quarter_date:
            return False
            
        return True
