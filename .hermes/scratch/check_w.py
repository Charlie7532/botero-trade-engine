import json
th = json.load(open('backend/modules/quality_swing/domain/rules/rc_vol_normalized_thresholds.json'))
print("=== NORMATIVO ACTUAL (rc_vol_normalized_thresholds.json) ===")
for k, v in th.items():
    if isinstance(v, dict):
        print(f"  {k}: {len(v)} anclas -> {list(v.keys())}")
    else:
        print(f"  {k}: {v}")
w = json.load(open('backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json'))
print("\n=== WAVE EV: key ejemplo ===")
print("  ", list(w['states'])[0])
t = json.load(open('backend/modules/quality_swing/domain/rules/rc_tide_ev_derived.json'))
print("=== TIDE EV: key ejemplo ===")
print("  ", list(t['l3_full_state'])[0])
m = json.load(open('backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json'))
print("=== MULTISCALE s3_triad: key ejemplo ===")
print("  ", list(m['s3_triad'])[0])
