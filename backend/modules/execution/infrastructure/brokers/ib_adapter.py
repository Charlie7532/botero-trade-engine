"""Interactive Brokers adapter using IBKR's Web API (OAuth 1.0a Extended).

Auth model (decided Aug 2026, see docs/architecture-diagram.md — Security):
IB does NOT use a simple API-key/secret pair like Alpaca. Authenticating as
ourselves ("First Party OAuth", self-service — we are not a third-party
vendor selling this to other IBKR customers) requires:

  - a consumer key chosen in the OAuth self-service portal
  - an RSA *signature* key pair (signs every request)
  - an RSA *encryption* key pair (decrypts the access token secret)
  - a Diffie-Hellman parameters file (dhparam.pem) -> its prime, in hex
  - an access token + access token secret, generated in the portal

From these, a Live Session Token (LST) is derived once per session via a
Diffie-Hellman exchange, and every subsequent request is HMAC-SHA256-signed
with that LST. A background "tickler" keeps the brokerage session alive.

We do not hand-roll this signing/DH math: `ibind` (Voyz) implements it and is
the most actively maintained Python client for this API. Its `oauth` extra
depends on `pycryptodome` (maintained), NOT the abandoned `pyCrypto` package
that older guidance warned about — verified by inspecting ibind's
pyproject.toml (`oauth = ['pycryptodome>=3.21', ...]`), so no dependency
swap is needed; just install with `pip install ibind[oauth]`.

Because each IBKR account structure in Botero maps 1:1 to a portfolio (one
real IB account per person, confirmed Aug 2026 — no shared master/OAuth
connection across portfolios), every BrokerAccount needs its OWN full set of
these credentials. This adapter takes them as constructor args, injected by
the composition root (execution_factory.py) from that account's vault
entry — never read implicitly from a single global env var, since there is
no single global IB identity.

Registration (per account, one-time, self-service):
  https://ndcdyn.interactivebrokers.com/sso/Login?action=OAUTH&RL=1&ip2loc=US
  (non-US: append &action=OAUTH to the local login URL)
Key generation reference:
  openssl genrsa -out private_signature.pem 2048
  openssl rsa -in private_signature.pem -outform PEM -pubout -out public_signature.pem
  openssl genrsa -out private_encryption.pem 2048
  openssl rsa -in private_encryption.pem -outform PEM -pubout -out public_encryption.pem
  openssl dhparam -out dhparam.pem 2048
Upload both public keys + dhparam.pem in the portal, then generate the
access token + secret there. Activation is NOT instant (can take up to the
following weekend's server restart) — do this well ahead of when the
account needs to trade.

IMPORTANT — not yet verified against a live IBKR account:
This module has NOT been exercised against real IBKR credentials (no
account has completed OAuth registration yet, per the Aug 2026 decision to
start that process this weekend on a paper account). Treat this as a
reviewed-but-unverified implementation until a real end-to-end login +
paper order has been confirmed.
"""
import logging
from datetime import datetime
from typing import Optional

from backend.modules.execution.domain.entities.order_models import Broker, Order, OrderSide, OrderStatus
from backend.modules.portfolio_management.domain.entities.portfolio_models import Portfolio, Position
from backend.modules.shared.domain.entities.market_data import Bar
from backend.modules.execution.infrastructure.brokers.base import BrokerAdapter

logger = logging.getLogger(__name__)

# BrokerPort uses '1m' / '1h' / '1d'; IBKR's Web API uses '1min' / '1h' / '1d'.
_TIMEFRAME_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "1d": "1d",
}


class IBCredentialsError(RuntimeError):
    """Raised when an IBAdapter is built without a complete OAuth credential set."""


class IBAdapter(BrokerAdapter):
    """Interactive Brokers adapter using IBKR's Web API (OAuth 1.0a Extended, via `ibind`).

    One instance = one real IBKR account (one BrokerAccount / one portfolio).
    All credentials are injected — this class never reads env vars directly,
    so the composition root stays the single place that knows where secrets
    come from (Rule: env vars / vault reads only happen in execution_factory.py).
    """

    def __init__(
        self,
        *,
        account_id: str,
        consumer_key: str,
        access_token: str,
        access_token_secret: str,
        dh_prime_hex: str,
        signature_key_path: Optional[str] = None,
        signature_key_pem: Optional[str] = None,
        encryption_key_path: Optional[str] = None,
        encryption_key_pem: Optional[str] = None,
        maintain_oauth: bool = True,
    ):
        missing = [
            name
            for name, value in (
                ("account_id", account_id),
                ("consumer_key", consumer_key),
                ("access_token", access_token),
                ("access_token_secret", access_token_secret),
                ("dh_prime_hex", dh_prime_hex),
            )
            if not value
        ]
        if missing:
            raise IBCredentialsError(f"IBAdapter missing required credential(s): {', '.join(missing)}")
        if not (signature_key_path or signature_key_pem):
            raise IBCredentialsError("IBAdapter requires signature_key_path or signature_key_pem")
        if not (encryption_key_path or encryption_key_pem):
            raise IBCredentialsError("IBAdapter requires encryption_key_path or encryption_key_pem")

        self._account_id = account_id
        self._consumer_key = consumer_key
        self._access_token = access_token
        self._access_token_secret = access_token_secret
        self._dh_prime_hex = dh_prime_hex
        self._signature_key_path = signature_key_path
        self._signature_key_pem = signature_key_pem
        self._encryption_key_path = encryption_key_path
        self._encryption_key_pem = encryption_key_pem
        self._maintain_oauth = maintain_oauth
        self._client = None  # lazy — first real use triggers the LST/DH handshake

    @property
    def broker(self) -> Broker:
        return Broker.INTERACTIVE_BROKERS

    def _get_client(self):
        """Lazy-build the ibind IbkrClient. Triggers the OAuth handshake on first call."""
        if self._client is not None:
            return self._client

        try:
            import importlib.util
            if importlib.util.find_spec("Crypto") is None:
                raise ImportError(
                    "ibind OAuth support missing. Install with `pip install ibind[oauth]` "
                    "(pulls pycryptodome, not the unmaintained pyCrypto)."
                )
            from ibind import IbkrClient
            from ibind.oauth.oauth1a import OAuth1aConfig
        except ImportError as e:
            raise ConnectionError(f"ibind is not installed or misconfigured: {e}") from e

        oauth_config = OAuth1aConfig(
            access_token=self._access_token,
            access_token_secret=self._access_token_secret,
            consumer_key=self._consumer_key,
            dh_prime=self._dh_prime_hex,
            signature_key_fp=self._signature_key_path,
            signature_key=self._signature_key_pem,
            encryption_key_fp=self._encryption_key_path,
            encryption_key=self._encryption_key_pem,
        )

        try:
            self._client = IbkrClient(
                account_id=self._account_id,
                use_oauth=True,
                oauth_config=oauth_config,
            )
            # oauth_init runs automatically inside IbkrClient.__init__ when use_oauth=True,
            # but we call it explicitly so a failure here raises before any trading call does.
            self._client.oauth_init(maintain_oauth=self._maintain_oauth, init_brokerage_session=True)
        except Exception as e:
            self._client = None
            raise ConnectionError(
                f"Failed to establish IBKR OAuth session for account {self._account_id}: {e}"
            ) from e

        return self._client

    async def is_connected(self) -> bool:
        try:
            client = self._get_client()
            return bool(client.check_health())
        except Exception as e:
            logger.warning(f"IBAdapter.is_connected() failed for {self._account_id}: {e}")
            return False

    async def get_price(self, symbol: str) -> float:
        client = self._get_client()
        # Required pre-flight per IBKR docs before /iserver/marketdata endpoints work.
        client.portfolio_accounts()
        conid_result = client.stock_conid_by_symbol(symbol)
        conid = conid_result.data[symbol]
        # last price = field 31; see ibind ibkr_definitions.py for the full field map
        snapshot = client.live_marketdata_snapshot(conids=[str(conid)], fields=["31"])
        data = snapshot.data
        if not data:
            raise ValueError(f"Could not fetch price for {symbol}: empty snapshot")
        price = data[0].get("31")
        if price is None:
            raise ValueError(f"Could not fetch price for {symbol}: no last-price field in response")
        return float(str(price).lstrip("C"))  # IBKR sometimes prefixes a closing-price flag

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        client = self._get_client()
        bar = _TIMEFRAME_MAP.get(timeframe, "1d")
        span_days = max((end - start).days, 1)
        period = f"{span_days}d"

        result = client.marketdata_history_by_symbol(
            symbol=symbol,
            bar=bar,
            period=period,
            start_time=start,
        )
        rows = result.data.get("data", []) if isinstance(result.data, dict) else []
        bars: list[Bar] = []
        for row in rows:
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(row["t"] / 1000),
                    open=float(row["o"]),
                    high=float(row["h"]),
                    low=float(row["l"]),
                    close=float(row["c"]),
                    volume=float(row.get("v", 0.0)),
                )
            )
        return bars

    async def place_order(self, order: Order) -> Order:
        from ibind.client.ibkr_utils import make_order_request

        client = self._get_client()
        client.portfolio_accounts()  # pre-flight
        conid_result = client.stock_conid_by_symbol(order.symbol)
        conid = conid_result.data[order.symbol]

        order_request = make_order_request(
            conid=conid,
            side="BUY" if order.side == OrderSide.BUY else "SELL",
            quantity=order.quantity or 0,
            order_type="MKT" if order.limit_price is None else "LMT",
            acct_id=self._account_id,
            price=order.limit_price,
        )

        # IBKR may return "questions" (order confirmations) that must be
        # answered before the order goes live — auto-confirm all of them,
        # since blocking on interactive input isn't viable for a live daemon.
        # NOTE for review: confirm which specific confirmations we want to
        # auto-accept vs hard-reject (e.g. a "price outside band" warning
        # should probably not be blindly accepted).
        result = client.place_order(order_request, answers={"*": True})
        placed = result.data[0] if isinstance(result.data, list) else result.data
        order.order_id = str(placed.get("order_id") or placed.get("id") or "")
        order.status = OrderStatus.PENDING
        return order

    async def cancel_order(self, order_id: str) -> bool:
        try:
            client = self._get_client()
            client.cancel_order(order_id, account_id=self._account_id)
            return True
        except Exception as e:
            logger.warning(f"IBAdapter.cancel_order({order_id}) failed: {e}")
            return False

    async def get_portfolio(self) -> Portfolio:
        client = self._get_client()

        ledger = client.get_ledger(account_id=self._account_id)
        cash = 0.0
        if isinstance(ledger.data, dict):
            base = ledger.data.get("BASE", {})
            cash = float(base.get("cashbalance", 0.0))

        positions_result = client.positions(account_id=self._account_id)
        rows = positions_result.data if isinstance(positions_result.data, list) else []
        positions = [
            Position(
                symbol=p.get("ticker") or p.get("contractDesc", ""),
                quantity=float(p.get("position", 0.0)),
                avg_cost=float(p.get("avgCost", 0.0)),
                market_price=float(p.get("mktPrice", 0.0)),
                broker=Broker.INTERACTIVE_BROKERS,
            )
            for p in rows
        ]
        return Portfolio(broker=Broker.INTERACTIVE_BROKERS, cash=cash, positions=positions)
