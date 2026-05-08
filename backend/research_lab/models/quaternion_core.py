"""
Market Quaternion — 4D Market State Decomposition
=====================================================
Transforms each OHLCV bar into a 4-dimensional state vector
that captures the mechanical forces acting on price:

  Q = (w, x, y, z) where:
    w = Equilibrium  — consensus position (close vs VWAP z-score)
    x = Displacement — session winner (body / true_range, [-1, +1])
    y = Intensity    — energy injected (relative volume z-score)
    z = Absorption   — rejection bias (wick skew, [-1, +1])

Plus 8 derived metrics: norm, 4 deltas, rotation angle, money flow,
divergence. Total: 12 base dimensions.

The `extras` parameter allows injecting additional dimensions
(VIX, SKEW, RSI, etc.) for the FeatureDiscoveryRunner to test.

Dependencies: numpy, pandas only (pure domain math).
"""
import numpy as np
import pandas as pd


class MarketQuaternion:
    """Transforms OHLCV bars into a 4D market state + derivatives."""

    # Base quaternion dimension names
    BASE_DIMS = ["Q_w", "Q_x", "Q_y", "Q_z"]
    DERIVATIVE_DIMS = [
        "Q_norm", "Q_w_delta", "Q_x_delta", "Q_y_delta", "Q_z_delta",
        "Q_rotation_angle", "Q_money_flow", "Q_divergence",
    ]

    @staticmethod
    def compute(
        df: pd.DataFrame,
        include_derivatives: bool = True,
        extras: dict[str, pd.Series] | None = None,
    ) -> pd.DataFrame:
        """
        Compute the Market Quaternion from OHLCV data.

        Args:
            df: DataFrame with columns [open, high, low, close, volume].
                Optional: [vwap] (from Alpaca enrichment).
            include_derivatives: If True, add norm, deltas, rotation, etc.
            extras: Optional dict of {name: pd.Series} for additional
                dimensions (e.g., {"vix_zscore": series, "skew_delta": series}).
                Used by FeatureDiscoveryRunner for ablation studies.

        Returns:
            DataFrame with Q_w, Q_x, Q_y, Q_z + derivatives + extras,
            indexed same as input.
        """
        # ── Prerequisite: True Range ──
        true_range = (df["high"] - df["low"]).clip(lower=1e-8)

        # ── VWAP: use Alpaca's if available, else approximate ──
        if "vwap" in df.columns and df["vwap"].notna().any():
            vwap = df["vwap"].copy()
            # Fill gaps with typical price approximation
            typical = (df["high"] + df["low"] + df["close"]) / 3
            vwap = vwap.fillna(typical)
        else:
            typical = (df["high"] + df["low"] + df["close"]) / 3
            cum_vp = (typical * df["volume"]).rolling(20, min_periods=1).sum()
            cum_vol = df["volume"].rolling(20, min_periods=1).sum().clip(lower=1)
            vwap = cum_vp / cum_vol

        # ── Q_w: EQUILIBRIUM ──
        # Where is price relative to consensus (VWAP)?
        # Z-Score rolling for stationarity.
        vwap_diff = df["close"] - vwap
        vwap_std = vwap_diff.rolling(20, min_periods=5).std().clip(lower=1e-8)
        Q_w = vwap_diff / vwap_std

        # ── Q_x: DISPLACEMENT ──
        # Who won the session? Normalized [-1, +1].
        # +1 = buyers dominated, -1 = sellers dominated.
        Q_x = (df["close"] - df["open"]) / true_range

        # ── Q_y: INTENSITY ──
        # Relative Volume as Z-Score (stationary, cross-ticker comparable).
        vol_float = df["volume"].astype(float)
        rvol = vol_float / vol_float.rolling(20, min_periods=5).mean().clip(lower=1)
        rvol_mean = rvol.rolling(50, min_periods=10).mean()
        rvol_std = rvol.rolling(50, min_periods=10).std().clip(lower=1e-8)
        Q_y = (rvol - rvol_mean) / rvol_std

        # ── Q_z: ABSORPTION ──
        # Wick bias: +1 = bearish rejection (long lower wick, bullish signal)
        #            -1 = bullish rejection (long upper wick, bearish signal)
        body_high = df[["open", "close"]].max(axis=1)
        body_low = df[["open", "close"]].min(axis=1)
        upper_wick = df["high"] - body_high
        lower_wick = body_low - df["low"]
        Q_z = (lower_wick - upper_wick) / true_range

        result = pd.DataFrame({
            "Q_w": Q_w,
            "Q_x": Q_x,
            "Q_y": Q_y,
            "Q_z": Q_z,
        }, index=df.index)

        # ── Derivatives ──
        if include_derivatives:
            # Norm: magnitude of the 4D state vector
            result["Q_norm"] = np.sqrt(Q_w**2 + Q_x**2 + Q_y**2 + Q_z**2)

            # Deltas: rate of change (first derivative)
            for col in ["Q_w", "Q_x", "Q_y", "Q_z"]:
                result[f"{col}_delta"] = result[col].diff()

            # Rotation angle between consecutive states
            # cos(θ) = (Q_t · Q_{t-1}) / (|Q_t| × |Q_{t-1}|)
            dot = sum(
                result[c] * result[c].shift(1)
                for c in ["Q_w", "Q_x", "Q_y", "Q_z"]
            )
            norm_product = (
                result["Q_norm"] * result["Q_norm"].shift(1)
            ).clip(lower=1e-8)
            cos_angle = (dot / norm_product).clip(-1, 1)
            result["Q_rotation_angle"] = np.arccos(cos_angle)

            # Money Flow: directional energy (displacement × intensity)
            result["Q_money_flow"] = Q_x * Q_y

            # Divergence: volume grows but price doesn't advance
            result["Q_divergence"] = Q_y.abs() - Q_x.abs()

        # ── Extras (injected by FeatureDiscoveryRunner) ──
        if extras:
            for name, series in extras.items():
                # Align index and add
                aligned = series.reindex(df.index)
                result[name] = aligned

        return result

    @staticmethod
    def dimension_names(
        include_derivatives: bool = True,
        extra_names: list[str] | None = None,
    ) -> list[str]:
        """Return the list of dimension names for a given configuration."""
        dims = list(MarketQuaternion.BASE_DIMS)
        if include_derivatives:
            dims.extend(MarketQuaternion.DERIVATIVE_DIMS)
        if extra_names:
            dims.extend(extra_names)
        return dims
