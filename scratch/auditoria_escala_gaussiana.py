#!/usr/bin/env python3
"""
Auditoria Gaussiana por Estacion - Calculo sigma, robustez, fat-tails y overflow
Lake: data/research/continuous_metar_lake.parquet
"""
import numpy as np
import pandas as pd
from scipy import stats

LAKE_PATH = "data/research/continuous_metar_lake.parquet"
STATIONS = [
    "vix", "vvix", "pcr", "fg", "sv5_turbulence",
    "skew", "credit", "yield_curve", "rotation", "dxy", "bsi"
]

# Current STATION_MU_SIGMA from sigma_overflow.py for D1
PARAMETRIC_MU_SIGMA_D1 = {
    "vix": (19.4419, 7.7300),
    "vvix": (93.4701, 16.3885),
    "pcr": (0.9445, 0.1747),
    "fg": (48.8497, 21.0618),
    "sv5_turbulence": (7.0381, 3.9006),
    "skew": (132.1308, 11.9337),
    "credit": (0.6241, 0.0502),
    "yield_curve": (1.3942, 1.2675),
    "rotation": (0.5301, 2.4011),
    "bsi": (56.6184, 20.7608),
    "dxy": (97.4445, 14.0207),
}

def hill_estimator(data, k_ratio=0.05):
    """
    Hill estimator for tail index alpha (heavy-tail exponent).
    Lower alpha means heavier tail (alpha < 2: infinite variance; alpha < 4: heavy tails/infinite kurtosis).
    """
    s = np.sort(data[data > 0])
    n = len(s)
    k = int(n * k_ratio)
    if k < 2:
        return np.nan
    tail = s[-k:]
    # Hill formula: 1 / gamma, where gamma = (1/k) * sum(log(tail_i) - log(tail_0))
    threshold = tail[0]
    log_excess = np.log(tail) - np.log(threshold)
    gamma = np.mean(log_excess)
    return 1.0 / gamma if gamma > 0 else np.nan

def run_audit():
    df = pd.read_parquet(LAKE_PATH)
    results = []
    
    for st in STATIONS:
        col = f"{st}_val"
        s = df[col].dropna().values
        n = len(s)
        
        # 1. Descriptivos reales
        mu = float(np.mean(s))
        sigma_std = float(np.std(s, ddof=1))
        med = float(np.median(s))
        skew = float(stats.skew(s))
        kurt = float(stats.kurtosis(s)) # excess kurtosis (0 for normal)
        
        # Shapiro test (on up to 5000 random samples if n > 5000)
        sample_for_shapiro = s if n <= 5000 else np.random.RandomState(42).choice(s, 5000, replace=False)
        shapiro_stat, shapiro_p = stats.shapiro(sample_for_shapiro)
        dagostino_stat, dagostino_p = stats.normaltest(s)
        
        # 2. Robust estimators
        mad_raw = float(np.median(np.abs(s - med)))
        sigma_mad = 1.4826 * mad_raw # normal-consistent MAD
        q75, q25 = np.percentile(s, [75, 25])
        iqr = q75 - q25
        sigma_iqr = iqr / 1.349 # normal-consistent IQR
        
        inflation_ratio = sigma_std / sigma_mad if sigma_mad > 0 else np.nan
        
        # 3. Parametric vs Empirical vs Robust Overflows
        dict_mu, dict_sigma = PARAMETRIC_MU_SIGMA_D1[st]
        z_param = (s - dict_mu) / dict_sigma
        
        # Overflow thresholds
        # Nominal Gaussian 3-sigma: upper tail 0.1349898% (P99.865), lower tail 0.1349898% (P0.135)
        # Total two-sided: 0.26998% (~0.27%)
        p_low_emp = np.percentile(s, 0.135)
        p_high_emp = np.percentile(s, 99.865)
        
        # Count parametric overflows
        param_upper_count = int(np.sum(z_param > 3.0))
        param_lower_count = int(np.sum(z_param < -3.0))
        param_total_count = param_upper_count + param_lower_count
        param_total_pct = (param_total_count / n) * 100.0
        
        # Count empirical overflows (by definition ~ 0.27% two-sided, 0.135% one-sided)
        emp_upper_count = int(np.sum(s > p_high_emp))
        emp_lower_count = int(np.sum(s < p_low_emp))
        emp_total_count = emp_upper_count + emp_lower_count
        emp_total_pct = (emp_total_count / n) * 100.0
        
        # Robust z-score: (val - median) / sigma_mad
        z_robust = (s - med) / sigma_mad if sigma_mad > 0 else np.zeros_like(s)
        robust_upper_3s = int(np.sum(z_robust > 3.0))
        robust_lower_3s = int(np.sum(z_robust < -3.0))
        robust_total_3s = robust_upper_3s + robust_lower_3s
        robust_total_3s_pct = (robust_total_3s / n) * 100.0
        
        robust_upper_4s = int(np.sum(z_robust > 4.0))
        robust_lower_4s = int(np.sum(z_robust < -4.0))
        robust_total_4s = robust_upper_4s + robust_lower_4s
        
        # 4. Bin5 and Bin0 distribution in the lake
        bin_col = f"{st}_d1_bin"
        if bin_col in df.columns:
            b_s = df[bin_col].dropna().values
            n_bins = len(b_s)
            pct_bin0 = (np.sum(b_s == 0) / n_bins) * 100.0
            pct_bin5 = (np.sum(b_s == 5) / n_bins) * 100.0
        else:
            pct_bin0, pct_bin5 = np.nan, np.nan
            
        # 5. Tail thickness: Hill estimator (on shifted positive values if needed)
        shifted_s = s - np.min(s) + 1.0 if np.min(s) <= 0 else s
        alpha_hill = hill_estimator(shifted_s, k_ratio=0.05)
        
        # Multiplier of parametric over empirical (upper or total)
        # prompt specifically compares parametric z>3 vs empirical >P99.865
        # Let's compute upper multiplier
        mult_upper = (param_upper_count / max(emp_upper_count, 1)) if emp_upper_count > 0 else np.nan
        
        results.append({
            "station": st,
            "n": n,
            "mu_real": round(mu, 4),
            "sigma_real": round(sigma_std, 4),
            "med_real": round(med, 4),
            "sigma_mad": round(sigma_mad, 4),
            "sigma_iqr": round(sigma_iqr, 4),
            "inflation_ratio": round(inflation_ratio, 2),
            "skew": round(skew, 2),
            "kurt_excess": round(kurt, 2),
            "shapiro_p": f"{shapiro_p:.2e}",
            "alpha_hill": round(alpha_hill, 2),
            "pct_bin0_lake": round(pct_bin0, 2),
            "pct_bin5_lake": round(pct_bin5, 2),
            "param_mu_dict": dict_mu,
            "param_sig_dict": dict_sigma,
            "param_thresh_3s_upper": round(dict_mu + 3.0 * dict_sigma, 4),
            "emp_p99865": round(p_high_emp, 4),
            "robust_thresh_3s_upper": round(med + 3.0 * sigma_mad, 4),
            "robust_thresh_4s_upper": round(med + 4.0 * sigma_mad, 4),
            "param_ovf_upper_n": param_upper_count,
            "param_ovf_upper_pct": round((param_upper_count / n) * 100.0, 3),
            "emp_ovf_upper_n": emp_upper_count,
            "emp_ovf_upper_pct": round((emp_upper_count / n) * 100.0, 3),
            "mult_upper": round(mult_upper, 1),
            "robust_ovf_upper_3s_n": robust_upper_3s,
            "robust_ovf_upper_4s_n": robust_upper_4s,
            "param_ovf_total_n": param_total_count,
            "emp_ovf_total_n": emp_total_count,
            "robust_ovf_total_3s_n": robust_total_3s,
            "robust_ovf_total_4s_n": robust_total_4s,
        })
        
    res_df = pd.DataFrame(results)
    print("=== AUDITORIA DE ESCALA GAUSSIANA POR ESTACION ===")
    print(res_df.to_string())
    res_df.to_csv("scratch/auditoria_gaussiana_resultados.csv", index=False)
    print("\nSaved to scratch/auditoria_gaussiana_resultados.csv")

if __name__ == "__main__":
    run_audit()
