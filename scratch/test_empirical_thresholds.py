#!/usr/bin/env python3
"""
Test and validate empirical quantile calibration for all 11 stations
"""
import numpy as np
import pandas as pd

LAKE_PATH = "data/research/continuous_metar_lake.parquet"
STATIONS = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence",
    "skew", "credit", "yield_curve", "rotation", "dxy", "bsi"
]

def calculate_empirical_thresholds(df):
    results = {}
    for st in STATIONS:
        st_res = {}
        for dim, col_suffix in [("d1", "val"), ("d2", "d2_raw"), ("d3", "d3_raw")]:
            col = f"{st}_{col_suffix}"
            s = df[col].dropna().values
            # Quantiles corresponding to Gaussian sigmas:
            # -3s: 0.135%, -2s: 2.275%, -1s: 15.866%, med: 50%, +1s: 84.134%, +2s: 97.725%, +3s: 99.865%
            qs = [0.00135, 0.02275, 0.15866, 0.50000, 0.84134, 0.97725, 0.99865]
            vals = np.quantile(s, qs)
            p0135, p0228, p1587, p5000, p8413, p9772, p99865 = vals
            
            tail_up = p99865 - p9772
            tail_lo = p0228 - p0135
            
            st_res[dim] = {
                "n": len(s),
                "p0135": float(p0135),
                "p0228": float(p0228),
                "p1587": float(p1587),
                "p5000": float(p5000),
                "p8413": float(p8413),
                "p9772": float(p9772),
                "p99865": float(p99865),
                "tail_up": float(tail_up) if tail_up > 1e-6 else 1.0,
                "tail_lo": float(tail_lo) if tail_lo > 1e-6 else 1.0,
            }
        results[st] = st_res
    return results

def compute_empirical_z(val, thresh):
    if val is None or np.isnan(val):
        return None
    p0135 = thresh["p0135"]
    p0228 = thresh["p0228"]
    p1587 = thresh["p1587"]
    p5000 = thresh["p5000"]
    p8413 = thresh["p8413"]
    p9772 = thresh["p9772"]
    p99865 = thresh["p99865"]
    tail_up = thresh["tail_up"]
    tail_lo = thresh["tail_lo"]
    
    if val >= p99865:
        return 3.0 + (val - p99865) / tail_up
    elif val >= p9772:
        return 2.0 + (val - p9772) / (p99865 - p9772)
    elif val >= p8413:
        return 1.0 + (val - p8413) / (p9772 - p8413)
    elif val >= p5000:
        return 0.0 + (val - p5000) / (p8413 - p5000)
    elif val >= p1587:
        return -1.0 + (val - p1587) / (p5000 - p1587)
    elif val >= p0228:
        return -2.0 + (val - p0228) / (p1587 - p0228)
    elif val >= p0135:
        return -3.0 + (val - p0135) / (p0228 - p0135)
    else:
        return -3.0 - (p0135 - val) / tail_lo

def test():
    df = pd.read_parquet(LAKE_PATH)
    thresholds = calculate_empirical_thresholds(df)
    
    print("=== D1 EMPIRICAL THRESHOLDS ===")
    for st in STATIONS:
        t = thresholds[st]["d1"]
        print(f"{st:15s} | -3s: {t['p0135']:8.3f} | -2s: {t['p0228']:8.3f} | med: {t['p5000']:8.3f} | +2s: {t['p9772']:8.3f} | +3s: {t['p99865']:8.3f} | tail_up: {t['tail_up']:7.3f}")
        
    print("\n=== HISTORICAL TEST ON VIX EXTREMES ===")
    vix_thresh = thresholds["vix"]["d1"]
    test_vals = [10.0, 15.0, 17.63, 25.0, 40.0, 42.63, 50.0, 69.96, 82.69, 89.53]
    for v in test_vals:
        z = compute_empirical_z(v, vix_thresh)
        print(f"VIX = {v:5.2f} -> z_emp = {z:5.2f}")

if __name__ == "__main__":
    test()
