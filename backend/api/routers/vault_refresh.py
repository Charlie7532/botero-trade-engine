"""
Vault Refresh Router — On-demand data refresh
================================================
Allows API consumers to trigger immediate data refresh for specific tickers.
Uses the same VaultProvider infrastructure as the daemon drain.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore
from backend.modules.shared.infrastructure.vault_refresh_adapter import VaultRefreshAdapter
from backend.modules.shared.domain.ports.vault_refresh_port import RefreshRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vault", tags=["vault"])


class RefreshBody(BaseModel):
    ticker: str
    category: str  # 'ohlcv', 'fundamental', 'flow', 'options', 'breadth', 'macro'
    priority: str = "normal"


class RefreshResponse(BaseModel):
    request_id: int
    status: str
    message: str


@router.post("/refresh", response_model=RefreshResponse)
def request_refresh(body: RefreshBody):
    """Enqueue a data refresh request for a specific ticker/category.

    The daemon will process this on its next cycle (Tier 0).
    For 'urgent' priority, the daemon processes before any scheduled work.
    """
    store = TimescaleDataStore()
    try:
        adapter = VaultRefreshAdapter(store)
        req = RefreshRequest(
            ticker=body.ticker.upper(),
            category=body.category.lower(),
            priority=body.priority.lower(),
            requested_by="api_user",
        )
        request_id = adapter.request_refresh(req)
        return RefreshResponse(
            request_id=request_id,
            status="queued",
            message=f"Refresh queued for {body.ticker}/{body.category} (priority={body.priority})",
        )
    finally:
        store.close()


@router.get("/refresh/status/{request_id}")
def refresh_status(request_id: int):
    """Check the status of a refresh request."""
    store = TimescaleDataStore()
    try:
        conn = store._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, ticker, category, status, requested_at, completed_at, error "
                    "FROM vault.refresh_queue WHERE id = %s",
                    (request_id,)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Request not found")
                return {
                    "request_id": row[0], "ticker": row[1], "category": row[2],
                    "status": row[3], "requested_at": str(row[4]),
                    "completed_at": str(row[5]) if row[5] else None,
                    "error": row[6],
                }
        finally:
            store._put(conn)
    finally:
        store.close()


@router.get("/refresh/pending")
def pending_requests():
    """List all pending refresh requests."""
    store = TimescaleDataStore()
    try:
        adapter = VaultRefreshAdapter(store)
        pending = adapter.pending_requests(limit=50)
        return {
            "count": len(pending),
            "requests": [
                {
                    "request_id": r.request_id,
                    "ticker": r.ticker,
                    "category": r.category,
                    "status": r.status,
                    "requested_at": str(r.requested_at),
                }
                for r in pending
            ],
        }
    finally:
        store.close()
