import numpy as np
from scipy.stats import norm

def bs_gamma(S: float, K: float, T: float, sigma: float, r: float = 0.05) -> float:
    """
    Gamma exacto de Black-Scholes.
    Gamma = N'(d1) / (S × σ × √T)
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    return norm.pdf(d1) / (S * sigma * sqrt_T)

def bs_delta(S: float, K: float, T: float, sigma: float,
              r: float = 0.05, opt: str = 'call') -> float:
    """Delta exacto de Black-Scholes."""
    if T <= 0 or sigma <= 0:
        if opt == 'call':
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    return norm.cdf(d1) if opt == 'call' else norm.cdf(d1) - 1


def bs_vanna(S: float, K: float, T: float, sigma: float, r: float = 0.05) -> float:
    """
    Vanna = ∂Delta/∂σ = -d2 × N'(d1) / σ

    When IV drops, Vanna flows create mechanical buying (calls get more delta,
    dealers must buy underlying). When IV spikes, the reverse.
    Karsan's key: Vanna flows are reflexive and amplify trends.
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return -d2 * norm.pdf(d1) / sigma


def bs_charm(S: float, K: float, T: float, sigma: float, r: float = 0.05) -> float:
    """
    Charm = -∂Delta/∂T (delta decay per day)

    As expiration approaches, OTM options lose delta and dealers must
    unwind hedges. This creates PREDICTABLE, calendar-driven flows.
    Karsan: Charm flows are the most reliable because they're non-discretionary.

    Returns charm per day (not per year).
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    # Charm = N'(d1) × [2(r-q)T - d2×σ√T] / (2T×σ×√T)
    # Simplified for q=0 (no dividend yield):
    charm_annual = -norm.pdf(d1) * (2 * r * T - d2 * sigma * sqrt_T) / (2 * T * sigma * sqrt_T)
    return charm_annual / 365.0  # Per day

