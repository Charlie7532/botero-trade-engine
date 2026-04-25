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
