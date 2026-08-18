"""
Audit 9 Intelligence Reference Files vs JSON Fact Stores
=========================================================
Checks:
1. Are P_bull, EV_net, E_days in .md files actual data or placeholders (50.0%, +0.00%)?
2. What are the REAL values in the .json fact stores for each station across scales (zz25, zz50, zz75)?
3. What are the REAL top empirical anomalies in each JSON fact store (with N >= 20)?
4. What DSR scores / Grades are hardcoded vs mathematically calculated?
"""
import json
from pathlib import Path

REF_DIR = Path(".agents/references")
FACT_STORE_DIR = Path("backend/modules/entry_decision/domain/rules")

STATIONS = {
    "vix": ("vix_intelligence.md", "vix_fact_store.json"),
    "vvix": ("vvix_intelligence.md", "vvix_fact_store.json"),
    "pcr": ("pcr_intelligence.md", "pcr_fact_store.json"),
    "fg": ("fg_intelligence.md", "fg_fact_store.json"),
    "sv5_turbulence": ("sv5_turbulence_intelligence.md", "sv5_turbulence_fact_store.json"),
    "skew": ("skew_intelligence.md", "skew_fact_store.json"),
    "credit": ("credit_intelligence.md", "credit_fact_store.json"),
    "yield_curve": ("yield_curve_intelligence.md", "yield_curve_fact_store.json"),
    "rotation": ("rotation_intelligence.md", "rotation_fact_store.json"),
    "bsi": ("bsi_intelligence.md", "bsi_fact_store.json"),
}

print("="*80)
print("AUDIT: REFERENCE FILES (.md) vs JSON FACT STORES (.json)")
print("="*80)

audit_results = []

for key, (md_name, json_name) in STATIONS.items():
    md_path = REF_DIR / md_name
    json_path = FACT_STORE_DIR / json_name
    
    md_exists = md_path.exists()
    json_exists = json_path.exists()
    
    # Check MD content
    md_placeholders_pbull = 0
    md_placeholders_ev = 0
    if md_exists:
        content = md_path.read_text(encoding="utf-8")
        md_placeholders_pbull = content.count("50.0%")
        md_placeholders_ev = content.count("+0.00%")
    
    # Check JSON content
    json_n_states = 0
    json_sample_size = 0
    top_anomalies = []
    scale_summary = {"zz25": {"n_tot": 0, "ev_weighted": 0, "pb_weighted": 0},
                     "zz50": {"n_tot": 0, "ev_weighted": 0, "pb_weighted": 0},
                     "zz75": {"n_tot": 0, "ev_weighted": 0, "pb_weighted": 0}}
    
    if json_exists:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        json_sample_size = data.get("sample_size", 0)
        states = data.get("states", {})
        json_n_states = len(states)
        
        # Calculate real weighted averages for zz25, zz50, zz75
        for scale in ["zz25", "zz50", "zz75"]:
            tot_n = 0
            weighted_ev = 0.0
            weighted_pb = 0.0
            for s_name, s_data in states.items():
                if scale in s_data:
                    sc = s_data[scale]
                    n_raw = sc.get("n_raw", 0)
                    if n_raw > 0:
                        tot_n += n_raw
                        weighted_ev += sc.get("ev_net", 0.0) * n_raw
                        weighted_pb += sc.get("p_bull", 0.5) * n_raw
            if tot_n > 0:
                scale_summary[scale] = {
                    "n_tot": tot_n,
                    "ev_weighted": weighted_ev / tot_n,
                    "pb_weighted": weighted_pb / tot_n,
                }
        
        # Extract top 3 anomalies by highest positive EV and top 3 by most negative EV (N >= 20)
        valid_anomalies = []
        for s_name, s_data in states.items():
            n = s_data.get("n", 0)
            if n >= 20:
                zz25 = s_data.get("zz25", {})
                ev = zz25.get("ev_net", 0.0)
                pb = zz25.get("p_bull", 0.5)
                guidance = s_data.get("operational_guidance", "UNKNOWN")
                valid_anomalies.append({
                    "state": s_name,
                    "n": n,
                    "pbull": pb,
                    "ev": ev,
                    "guidance": guidance
                })
        
        valid_anomalies.sort(key=lambda x: abs(x["ev"]), reverse=True)
        top_anomalies = valid_anomalies[:5]

    print(f"\n--- Station: {key.upper()} ---")
    print(f"MD file: {md_name} (Placeholders: 50.0% count={md_placeholders_pbull}, +0.00% count={md_placeholders_ev})")
    print(f"JSON file: {json_name} (Sample size={json_sample_size}, Populated states={json_n_states})")
    print(f"REAL Weighted Averages from JSON:")
    for sc, stats in scale_summary.items():
        print(f"  {sc}: P(bull)={stats['pb_weighted']*100:.2f}%, EV={stats['ev_weighted']*100:+.4f}% (N={stats['n_tot']})")
    
    print(f"REAL Top Anomalies in JSON (N >= 20, ranked by |EV|):")
    if top_anomalies:
        for a in top_anomalies:
            print(f"  • {a['state'][:55]:55s} | N={a['n']:3d} | P(bull)={a['pbull']*100:.1f}% | EV={a['ev']*100:+.3f}% | {a['guidance']}")
    else:
        print("  ⚠️ NO states with N >= 20 found!")

    audit_results.append({
        "station": key.upper(),
        "md_file": md_name,
        "json_file": json_name,
        "md_corrupted": md_placeholders_pbull > 0,
        "json_sample_size": json_sample_size,
        "json_n_states": json_n_states,
        "scale_summary": scale_summary,
        "top_anomalies": top_anomalies
    })

# Save audit json
with open("/root/.gemini/antigravity-ide/brain/9a53440e-00d8-462a-a24c-5de375c3d552/audit_fact_stores_raw.json", "w") as f:
    json.dump(audit_results, f, indent=2)

print("\nSaved audit raw JSON to artifact directory.")
