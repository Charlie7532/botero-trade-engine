"""
Research Director Sourcing Router
====================================
Exposes three sourcing intelligence endpoints for the Research Department.
Reads exclusively from Neon vault (Rule 13). No external API calls at request time.

Endpoints:
    GET /api/research/guru           — Guru realtime picks (Form 4)
    GET /api/research/insider/cluster — Insider cluster buys + CEO buys
    GET /api/research/political       — Congressional trading activity
"""
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

router = APIRouter(prefix="/research", tags=["Research Intelligence"])


# ═══════════════════════════════════════════════════════════
# PYDANTIC RESPONSE MODELS
# ═══════════════════════════════════════════════════════════


class DepartmentRelevance(BaseModel):
    quality: str = "NONE"        # PRIMARY, HIGH, MODERATE, NONE
    speculative: str = "NONE"    # PRIMARY, HIGH, MODERATE, CONDITIONAL, NONE
    note: str = ""


class GuruPickItem(BaseModel):
    ticker: str = ""
    guru_name: str = ""
    action: str = ""             # buy, sell, add, reduce
    shares: int = 0
    portfolio_pct: float = 0.0
    portfolio_value: float = 0.0  # AUM proxy for believability ranking
    date: str = ""
    price: float = 0.0


class GuruPicksResponse(BaseModel):
    picks: list[GuruPickItem] = Field(default_factory=list)
    count: int = 0
    pages_fetched: int = 0
    last_updated: str = ""
    source: str = "gurufocus"
    department_relevance: DepartmentRelevance = Field(
        default_factory=lambda: DepartmentRelevance(
            quality="PRIMARY",
            speculative="NONE",
            note="Guru AUM is believability-weighted (Dalio). Speculative ignores GuruFocus entirely.",
        )
    )


class InsiderClusterItem(BaseModel):
    ticker: str = ""
    company: str = ""
    insider_count: int = 0
    total_value: float = 0.0
    date: str = ""


class InsiderCEOItem(BaseModel):
    ticker: str = ""
    company: str = ""
    ceo_name: str = ""
    shares: int = 0
    value: float = 0.0
    date: str = ""


class InsiderClusterResponse(BaseModel):
    clusters: list[InsiderClusterItem] = Field(default_factory=list)
    ceo_buys: list[InsiderCEOItem] = Field(default_factory=list)
    cluster_count: int = 0
    ceo_count: int = 0
    pages_fetched: int = 0
    last_updated: str = ""
    source: str = "gurufocus"
    department_relevance: DepartmentRelevance = Field(
        default_factory=lambda: DepartmentRelevance(
            quality="HIGH",
            speculative="CONDITIONAL",
            note="Quality: thesis confirmation. Speculative: only with neg GEX (tactical 48hr window).",
        )
    )


class PoliticalTradeItem(BaseModel):
    politician: str = ""
    ticker: str = ""
    action: str = ""             # purchase, sale
    amount_range: str = ""
    date: str = ""
    party: str = ""


class PoliticalTradesResponse(BaseModel):
    trades: list[PoliticalTradeItem] = Field(default_factory=list)
    count: int = 0
    pages_fetched: int = 0
    last_updated: str = ""
    source: str = "gurufocus"
    department_relevance: DepartmentRelevance = Field(
        default_factory=lambda: DepartmentRelevance(
            quality="MODERATE",
            speculative="MODERATE",
            note="30-45 day disclosure delay. Quality: regulatory direction. Speculative: catalyst detection.",
        )
    )


# ═══════════════════════════════════════════════════════════
# RANKING HELPERS (read-time, not ingestion-time)
# ═══════════════════════════════════════════════════════════

_ACTION_RANK = {"buy": 0, "add": 1, "reduce": 2, "sell": 3}


def _rank_guru_picks(picks: list[dict]) -> list[dict]:
    """Rank by: 1) Portfolio value (AUM proxy), 2) Action type, 3) Recency."""
    def sort_key(p: dict):
        pv = _safe_float(p.get("portfolio_value", p.get("current_shares_value", 0)))
        action = str(p.get("action", p.get("type", ""))).lower()
        action_score = _ACTION_RANK.get(action, 99)
        date_str = str(p.get("date", p.get("filing_date", "0")))
        return (-pv, action_score, date_str)

    return sorted(picks, key=sort_key)


def _rank_insider_clusters(clusters: list[dict]) -> list[dict]:
    """Rank by: 1) Insider count, 2) Total value, 3) Recency."""
    def sort_key(c: dict):
        count = int(c.get("insider_count", c.get("count", 0)) or 0)
        value = _safe_float(c.get("total_value", c.get("value", 0)))
        date_str = str(c.get("date", c.get("filing_date", "0")))
        return (-count, -value, date_str)

    return sorted(clusters, key=sort_key)


def _rank_political_trades(trades: list[dict]) -> list[dict]:
    """Rank by: 1) Transaction value, 2) Recency."""
    _AMOUNT_RANK = {
        "$15,001 - $50,000": 1, "$50,001 - $100,000": 2,
        "$100,001 - $250,000": 3, "$250,001 - $500,000": 4,
        "$500,001 - $1,000,000": 5, "$1,000,001 - $5,000,000": 6,
        "$5,000,001 - $25,000,000": 7, "$25,000,001 - $50,000,000": 8,
        "Over $50,000,000": 9,
    }

    def sort_key(t: dict):
        amount = str(t.get("amount_range", t.get("amount", "")))
        amount_score = _AMOUNT_RANK.get(amount, 0)
        date_str = str(t.get("date", t.get("transaction_date", "0")))
        return (-amount_score, date_str)

    return sorted(trades, key=sort_key)


def _safe_float(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


# ═══════════════════════════════════════════════════════════
# STORE SINGLETON
# ═══════════════════════════════════════════════════════════

_store: Optional[TimescaleDataStore] = None


def _get_store() -> TimescaleDataStore:
    global _store
    if _store is None:
        _store = TimescaleDataStore()
    return _store


# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════


@router.get("/guru", response_model=GuruPicksResponse)
async def get_guru_picks():
    """Guru realtime picks (Form 4). Ranked by AUM (believability-weighted)."""
    store = _get_store()
    data = store.load_mcp_latest("sourcing/guru_picks", "MARKET")
    if not data:
        return GuruPicksResponse(last_updated="never")

    raw_picks = data.get("picks", [])
    ranked = _rank_guru_picks(raw_picks)

    picks = []
    for p in ranked:
        picks.append(GuruPickItem(
            ticker=str(p.get("symbol", p.get("ticker", ""))),
            guru_name=str(p.get("guru_name", p.get("name", ""))),
            action=str(p.get("action", p.get("type", ""))).lower(),
            shares=int(_safe_float(p.get("shares", p.get("current_shares", 0)))),
            portfolio_pct=_safe_float(p.get("portfolio_pct", p.get("percentage", 0))),
            portfolio_value=_safe_float(p.get("portfolio_value", p.get("current_shares_value", 0))),
            date=str(p.get("date", p.get("filing_date", ""))),
            price=_safe_float(p.get("price", p.get("avg_price", 0))),
        ))

    return GuruPicksResponse(
        picks=picks,
        count=len(picks),
        pages_fetched=data.get("pages_fetched", 0),
        last_updated=data.get("timestamp", ""),
    )


@router.get("/insider/cluster", response_model=InsiderClusterResponse)
async def get_insider_clusters():
    """Insider cluster buys + CEO buys. Ranked by insider count and value."""
    store = _get_store()
    data = store.load_mcp_latest("sourcing/insider_clusters", "MARKET")
    if not data:
        return InsiderClusterResponse(last_updated="never")

    raw_clusters = _rank_insider_clusters(data.get("clusters", []))
    raw_ceo = data.get("ceo_buys", [])

    clusters = []
    for c in raw_clusters:
        clusters.append(InsiderClusterItem(
            ticker=str(c.get("symbol", c.get("ticker", ""))),
            company=str(c.get("company", c.get("name", ""))),
            insider_count=int(_safe_float(c.get("insider_count", c.get("count", 0)))),
            total_value=_safe_float(c.get("total_value", c.get("value", 0))),
            date=str(c.get("date", c.get("filing_date", ""))),
        ))

    ceo_buys = []
    for cb in raw_ceo:
        ceo_buys.append(InsiderCEOItem(
            ticker=str(cb.get("symbol", cb.get("ticker", ""))),
            company=str(cb.get("company", cb.get("name", ""))),
            ceo_name=str(cb.get("insider_name", cb.get("ceo_name", ""))),
            shares=int(_safe_float(cb.get("shares", 0))),
            value=_safe_float(cb.get("value", cb.get("total_value", 0))),
            date=str(cb.get("date", cb.get("filing_date", ""))),
        ))

    return InsiderClusterResponse(
        clusters=clusters,
        ceo_buys=ceo_buys,
        cluster_count=len(clusters),
        ceo_count=len(ceo_buys),
        pages_fetched=data.get("pages_fetched", 0),
        last_updated=data.get("timestamp", ""),
    )


@router.get("/political", response_model=PoliticalTradesResponse)
async def get_political_trades():
    """Congressional trading activity. Ranked by transaction value."""
    store = _get_store()
    data = store.load_mcp_latest("sourcing/political_trades", "MARKET")
    if not data:
        return PoliticalTradesResponse(last_updated="never")

    raw_trades = _rank_political_trades(data.get("trades", []))

    trades = []
    for t in raw_trades:
        trades.append(PoliticalTradeItem(
            politician=str(t.get("politician", t.get("representative", ""))),
            ticker=str(t.get("symbol", t.get("ticker", ""))),
            action=str(t.get("type", t.get("transaction_type", ""))).lower(),
            amount_range=str(t.get("amount_range", t.get("amount", ""))),
            date=str(t.get("date", t.get("transaction_date", ""))),
            party=str(t.get("party", "")),
        ))

    return PoliticalTradesResponse(
        trades=trades,
        count=len(trades),
        pages_fetched=data.get("pages_fetched", 0),
        last_updated=data.get("timestamp", ""),
    )
