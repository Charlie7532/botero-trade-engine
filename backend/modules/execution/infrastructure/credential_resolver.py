"""Resolves broker credentials per portfolio from the internal Payload API,
instead of the engine reading static global env vars.

Why this exists: `build_quality_broker()` / `build_speculative_broker()` in
execution_factory.py read exactly two hardcoded env vars, so the engine can
only ever operate the two accounts baked into its configuration — adding a
third portfolio means editing code and redeploying, not creating a database
record. This resolver calls the new `/api/internal/broker-credentials`
endpoint (see that route's docstring for the full request/response shape and
why it uses its own service token instead of Payload's per-user API keys),
so any BrokerAccount created in Payload becomes tradeable without a code
change.

This does NOT touch the existing build_quality_broker() / build_speculative_broker()
functions — those keep working exactly as before. This is an additive path;
switching the orchestrator over to it is a separate decision (see
build_broker_registry_dynamic() in execution_factory.py) once this has been
exercised against a real deployment.

NOT yet verified against a live deployment (no ENGINE_SERVICE_TOKEN has been
issued yet, and the Next.js endpoint hasn't been deployed) — reviewed and
unit-testable in isolation, but treat as unproven until it's been run
against the real Payload instance.
"""
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes — arbitrary, not from any external
                                  # spec; tune based on how often credentials
                                  # actually rotate vs. how many extra requests
                                  # per minute the Payload API should absorb.

DEFAULT_MAX_RETRIES = 3          # total attempts, including the first —
                                  # arbitrary, not from any spec.
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5  # doubles each retry: 0.5s, 1s, 2s...

# Failures worth retrying: the request never got a real answer (connection
# refused, DNS hiccup, timeout) or the server said it's having a bad time
# (5xx). NOT retried: 401 (wrong token — retrying sends the same wrong token
# again), 404 (account doesn't exist — retrying won't create it), 501 (not
# implemented server-side — retrying won't implement it). Retrying those
# would just delay a definitive answer instead of fixing anything.
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


class CredentialResolutionError(RuntimeError):
    """Raised when the internal API can't return usable credentials.

    Deliberately loud: unlike PayloadInstrumentsAdapter (which returns an
    empty result on failure, fine for market/indicator data), a broker
    adapter must never silently end up with blank or stale credentials and
    try to trade with them. Every failure path here raises instead of
    returning None/{}.
    """


@dataclass
class AlpacaCredentials:
    api_key: str
    secret_key: str
    base_url: str
    environment: str
    account_record_id: str


@dataclass
class IBCredentials:
    account_id: str
    consumer_key: str
    access_token: str
    access_token_secret: str
    dh_prime_hex: str
    signature_key_pem: str
    encryption_key_pem: str
    account_record_id: str


class CredentialResolver:
    """Fetches and caches broker credentials from the internal Payload API.

    One instance can be shared across the process — the cache is keyed by
    (portfolio_id or department, broker_type), so it's safe to reuse for
    multiple portfolios/departments.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_token: Optional[str] = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    ):
        # Same env var name/convention as PayloadInstrumentsAdapter
        # (PAYLOAD_API_URL), so both adapters point at the same place
        # without needing two separate configs.
        self.base_url = (
            base_url if base_url is not None else os.getenv("PAYLOAD_API_URL", "http://localhost:3000/api")
        ).rstrip("/")
        self.service_token = service_token if service_token is not None else os.getenv("ENGINE_SERVICE_TOKEN", "")
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_retries = max(1, max_retries)  # always at least one attempt
        self.retry_backoff_seconds = retry_backoff_seconds
        self._cache: dict[str, tuple[float, dict]] = {}
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _cache_key(self, broker_type: str, portfolio_id: Optional[str], department: Optional[str]) -> str:
        return f"{broker_type}:{portfolio_id or ''}:{department or ''}"

    def _fetch(self, broker_type: str, portfolio_id: Optional[str], department: Optional[str]) -> dict:
        if not self.service_token:
            raise CredentialResolutionError(
                "ENGINE_SERVICE_TOKEN is not set — cannot authenticate to the "
                "internal broker-credentials endpoint."
            )
        if not portfolio_id and not department:
            raise CredentialResolutionError("Must provide portfolio_id or department.")

        body = {"brokerType": broker_type}
        if portfolio_id:
            body["portfolioId"] = portfolio_id
        else:
            body["department"] = department

        last_error: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            is_last_attempt = attempt == self.max_retries

            try:
                resp = self.session.post(
                    f"{self.base_url}/internal/broker-credentials",
                    json=body,
                    headers={"Authorization": f"Bearer {self.service_token}"},
                    timeout=10,
                )
            except requests.RequestException as e:
                last_error = f"Could not reach internal broker-credentials endpoint: {e}"
                if is_last_attempt:
                    raise CredentialResolutionError(
                        f"{last_error} (gave up after {attempt} attempt(s))"
                    ) from e
                self._sleep_before_retry(attempt, broker_type, portfolio_id, department, last_error)
                continue

            # Definitive answers — never retried, raised immediately.
            if resp.status_code == 401:
                raise CredentialResolutionError(
                    "Internal broker-credentials endpoint rejected ENGINE_SERVICE_TOKEN (401)."
                )
            if resp.status_code == 404:
                target = portfolio_id or department
                raise CredentialResolutionError(
                    f"No active {broker_type} BrokerAccount found for '{target}' (404)."
                )
            if resp.status_code == 501:
                raise CredentialResolutionError(
                    f"{broker_type} credential resolution not implemented server-side yet (501): {resp.text}"
                )

            # Transient-looking answers — worth retrying.
            if resp.status_code in _RETRYABLE_STATUS_CODES:
                last_error = f"Internal broker-credentials endpoint returned {resp.status_code}: {resp.text}"
                if is_last_attempt:
                    raise CredentialResolutionError(f"{last_error} (gave up after {attempt} attempt(s))")
                self._sleep_before_retry(attempt, broker_type, portfolio_id, department, last_error)
                continue

            # Any other non-OK status: don't guess whether it's transient —
            # surface it immediately rather than retrying blindly.
            if not resp.ok:
                raise CredentialResolutionError(
                    f"Internal broker-credentials endpoint returned {resp.status_code}: {resp.text}"
                )

            return resp.json()

        # Unreachable in practice (the loop always returns or raises), but
        # keeps type-checkers happy and fails loudly if that ever changes.
        raise CredentialResolutionError(f"Exhausted retries without a definitive result: {last_error}")

    def _sleep_before_retry(
        self,
        attempt: int,
        broker_type: str,
        portfolio_id: Optional[str],
        department: Optional[str],
        reason: str,
    ) -> None:
        delay = self.retry_backoff_seconds * (2 ** (attempt - 1))
        target = portfolio_id or department
        logger.warning(
            f"CredentialResolver: attempt {attempt}/{self.max_retries} failed for "
            f"{broker_type}:{target} ({reason}) — retrying in {delay:.1f}s"
        )
        time.sleep(delay)

    def get_alpaca_credentials(
        self,
        portfolio_id: Optional[str] = None,
        department: Optional[str] = None,
    ) -> AlpacaCredentials:
        """Get Alpaca credentials for a portfolio (preferred) or a department
        (transitional — matches today's two fixed accounts by department
        instead of by portfolio, until real per-portfolio BrokerAccounts
        exist for everyone)."""
        key = self._cache_key("alpaca", portfolio_id, department)
        cached = self._cache.get(key)
        if cached and (time.time() - cached[0]) < self.cache_ttl_seconds:
            data = cached[1]
        else:
            data = self._fetch("alpaca", portfolio_id, department)
            self._cache[key] = (time.time(), data)

        try:
            return AlpacaCredentials(
                api_key=data["apiKey"],
                secret_key=data["secretKey"],
                base_url=data["baseUrl"],
                environment=data["environment"],
                account_record_id=data["accountRecordId"],
            )
        except KeyError as e:
            # Don't cache a malformed response, and don't hand back a
            # half-built credentials object.
            self._cache.pop(key, None)
            raise CredentialResolutionError(f"Malformed response from broker-credentials endpoint: missing {e}") from e

    def get_ib_credentials(self, portfolio_id: str) -> IBCredentials:
        """Get Interactive Brokers OAuth credentials for a portfolio.

        Unlike Alpaca, there is no department-based transitional path here —
        IB isn't in use by any account yet, so every caller must already
        know which portfolio it wants (no legacy two-department fallback to
        preserve).
        """
        key = self._cache_key("interactive_brokers", portfolio_id, None)
        cached = self._cache.get(key)
        if cached and (time.time() - cached[0]) < self.cache_ttl_seconds:
            data = cached[1]
        else:
            data = self._fetch("interactive_brokers", portfolio_id, None)
            self._cache[key] = (time.time(), data)

        try:
            return IBCredentials(
                account_id=data["accountId"],
                consumer_key=data["consumerKey"],
                access_token=data["accessToken"],
                access_token_secret=data["accessTokenSecret"],
                dh_prime_hex=data["dhPrimeHex"],
                signature_key_pem=data["signatureKeyPem"],
                encryption_key_pem=data["encryptionKeyPem"],
                account_record_id=data["accountRecordId"],
            )
        except KeyError as e:
            self._cache.pop(key, None)
            raise CredentialResolutionError(f"Malformed IB response from broker-credentials endpoint: missing {e}") from e

    def invalidate(self, broker_type: str, portfolio_id: Optional[str] = None, department: Optional[str] = None):
        """Force the next call to re-fetch instead of using the cache — use
        after rotating a BrokerAccount's credentials in Payload."""
        self._cache.pop(self._cache_key(broker_type, portfolio_id, department), None)
