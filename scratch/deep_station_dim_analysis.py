#!/usr/bin/env python3
"""
Deep Analysis Script for Gaussian Scale Audit across 11 METAR stations
Dimensions: D1 (level), D2 (3d velocity), D3 (vol ratio std(2)/std(10))
"""
import numpy as np
import pandas as pd
from scipy import stats

LAKE_PATH = "data/research/continuous_metar_lake.parquet"
STATIONS = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence",
    "skew", "credit", "yield_curve", "rotation", "dxy", "bsi"
]

PARAMETRIC_MU_SIGMA = {
    "vix": {"d1": (19.4419, 7.7300), "d2": (-0.0012, 2.5911), "d3": (0.5399, 0.4583)},
    "vvix": {"d1": (93.4701, 16.3885), "d2": (0.0295, 8.7782), "d3": (0.5268, 0.4535)},
    "pcr": {"d1": (0.9445, 0.1747), "d2": (0.0, 0.1765), "d3": (0.7357, 0.5432)},
    "fg": {"d1": (48.8497, 21.0618), "d2": (-0.0119, 8.9751), "d3": (0.4525, 0.4315)},
    "sv5_turbulence": {"d1": (7.0381, 3.9006), "d2": (0.0066, 2.5386), "d3": (0.3924, 0.5172)},
    "skew": {"d1": (132.1308, 11.9337), "d2": (0.0066, 5.3562), "d3": (0.5709, 0.4866)},
    "credit": {"d1": (0.6241, 0.0502), "d2": (0.0001, 0.0064), "d3": (0.5344, 0.4325)},
    "yield_curve": {"d1": (1.3942, 1.2675), "d2": (-0.0001, 0.1506), "d3": (0.4868, 0.4206)},
    "rotation": {"d1": (0.5301, 2.4011), "d2": (0.0006, 0.6358), "d3": (0.5065, 0.4118)},
    "bsi": {"d1": (56.6184, 20.7608), "d2": (0.0014, 14.8147), "d3": (0.4936, 0.4375)},
    "dxy": {"d1": (97.4445, 14.0207), "d2": (-0.0044, 0.8609), "d3": (0.4854, 0.4207)},
}

def hill_tail_index(data, k_percent=5):
    """Computes upper tail Hill index."""
    s = np.sort(data)
    n = len(s)
    k = max(int(n * (k_percent / 100.0)), 2)
    tail = s[-k:]
    threshold = tail[0]
    # For data that might be <= 0, shift so threshold is positive
    shift = 0.0
    if threshold <= 0:
        shift = abs(threshold) + 1.0
        tail = tail + shift
        threshold = threshold + shift
    excess = np.log(tail) - np.log(threshold)
    gamma = np.mean(excess)
    alpha = 1.0 / gamma if gamma > 0 else np.nan
    return alpha

def analyze_station_dim(df, st, dim):
    if dim == "d1":
        col = f"{st}_val"
    elif dim == "d2":
        col = f"{st}_d2_raw"
    else:
        col = f"{st}_d3_raw"
        
    s = df[col].dropna().values
    n = len(s)
    if n == 0:
        return None
        
    mu = float(np.mean(s))
    sigma = float(np.std(s, ddof=1))
    med = float(np.median(s))
    skew = float(stats.skew(s))
    kurt = float(stats.kurtosis(s))
    
    mad_raw = float(np.median(np.abs(s - med)))
    sigma_mad = 1.4826 * mad_raw
    q75, q25 = np.percentile(s, [75, 25])
    sigma_iqr = (q75 - q25) / 1.349
    
    # Parametric dict values
    p_mu, p_sig = PARAMETRIC_MU_SIGMA[st][dim]
    z_param = (s - p_mu) / p_sig if p_sig > 0 else np.zeros_like(s)
    
    # Empirical percentiles
    # Nominal 2-sigma: 2.275% on tails (P2.275 and P97.725)
    # Nominal 3-sigma: 0.135% on tails (P0.135 and P99.865)
    p0135, p99865 = np.percentile(s, [0.135, 99.865])
    p0228, p9772 = np.percentile(s, [2.275, 97.725])
    
    # Overflows:
    # 1. Parametric z > 3 or z < -3
    ovf_param_upper = int(np.sum(z_param > 3.0))
    ovf_param_lower = int(np.sum(z_param < -3.0))
    
    # 2. Empirical > P99.865 or < P0.135
    ovf_emp_upper = int(np.sum(s > p99865))
    ovf_emp_lower = int(np.sum(s < p0135))
    
    # 3. Robust z_mad > 3 or < -3
    z_mad = (s - med) / sigma_mad if sigma_mad > 0 else np.zeros_like(s)
    ovf_mad_upper_3s = int(np.sum(z_mad > 3.0))
    ovf_mad_lower_3s = int(np.sum(z_mad < -3.0))
    ovf_mad_upper_4s = int(np.sum(z_mad > 4.0))
    ovf_mad_lower_4s = int(np.sum(z_mad < -4.0))
    ovf_mad_upper_5s = int(np.sum(z_mad > 5.0))
    ovf_mad_lower_5s = int(np.sum(z_mad < -5.0))
    
    # Hill index for upper tail
    alpha_upper = hill_tail_index(s, k_percent=5)
    # Hill index for lower tail (invert and shift)
    alpha_lower = hill_tail_index(-s, k_percent=5)
    
    # What z_mad corresponds to the empirical P99.865?
    z_mad_at_p99865 = (p99865 - med) / sigma_mad if sigma_mad > 0 else np.nan
    z_mad_at_p0135 = (p0135 - med) / sigma_mad if sigma_mad > 0 else np.nan
    
    return {
        "station": st,
        "dim": dim,
        "n": n,
        "mu": mu,
        "sigma": sigma,
        "med": med,
        "sigma_mad": sigma_mad,
        "sigma_iqr": sigma_iqr,
        "ratio_sig_mad": sigma / sigma_mad if sigma_mad > 0 else np.nan,
        "skew": skew,
        "kurt_excess": kurt,
        "alpha_upper": alpha_upper,
        "alpha_lower": alpha_lower,
        "p_mu_dict": p_mu,
        "p_sig_dict": p_sig,
        "p_thresh_3s_up": p_mu + 3.0 * p_sig,
        "p_thresh_3s_lo": p_mu - 3.0 * p_sig,
        "emp_p0135": p0135,
        "emp_p99865": p99865,
        "emp_p0228": p0228,
        "emp_p9772": p9772,
        "ovf_param_up": ovf_param_upper,
        "ovf_param_lo": ovf_param_lower,
        "ovf_param_tot": ovf_param_upper + ovf_param_lower,
        "ovf_emp_up": ovf_emp_upper,
        "ovf_emp_lo": ovf_emp_lower,
        "ovf_emp_tot": ovf_emp_upper + ovf_emp_lower,
        "ovf_mad_up_3s": ovf_mad_upper_3s,
        "ovf_mad_lo_3s": ovf_mad_lower_3s,
        "ovf_mad_tot_3s": ovf_mad_upper_3s + ovf_mad_lower_3s,
        "ovf_mad_up_4s": ovf_mad_upper_4s,
        "ovf_mad_lo_4s": ovf_mad_lower_4s,
        "ovf_mad_tot_4s": ovf_mad_upper_4s + ovf_mad_lower_4s,
        "ovf_mad_up_5s": ovf_mad_upper_5s,
        "ovf_mad_lo_5s": ovf_mad_lower_5s,
        "ovf_mad_tot_5s": ovf_mad_upper_5s + ovf_mad_lower_5s,
        "z_mad_at_p99865": z_mad_at_p99865,
        "z_mad_at_p0135": z_mad_at_p0135,
    }

def main():
    df = pd.read_parquet(LAKE_PATH)
    all_res = []
    for st in STATIONS:
        for dim in ["d1", "d2", "d3"]:
            r = analyze_station_dim(df, st, dim)
            if r:
                all_res.append(r)
    res_df = pd.DataFrame(all_res)
    res_df.to_csv("scratch/deep_station_dim_analysis.csv", index=False)
    
    print("=== D1 SUMMARY TABLE ===")
    d1_df = res_df[res_df["dim"] == "d1"].copy()
    cols = [
        "station", "mu", "sigma", "med", "sigma_mad", "ratio_sig_mad",
        "skew", "kurt_excess", "alpha_upper",
        "ovf_param_up", "ovf_emp_up", "ovf_mad_up_3s", "ovf_mad_up_4s", "ovf_mad_up_5s",
        "z_mad_at_p99865"
    ]
    print(d1_df[cols].to_string())

if __name__ == "__main__":
    main()
