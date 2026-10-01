import json
w = json.load(open('backend/modules/quality_swing/domain/rules/rc_wave_ev_derived.json'))
print("=== WAVE EV: 'vel_thresholds' presente? ===")
print("  ", w.get('vel_thresholds', 'NO PRESENTE'))
print("\n=== WAVE EV _documentation: claves ===")
doc = w.get('_documentation', {})
for k in doc:
    print("  ", k)
dtd = doc.get('dimension_thresholds_definition') or {}
if isinstance(dtd, dict):
    print("\n=== dimension_thresholds_definition ===")
    print(json.dumps(dtd, ensure_ascii=False, indent=1)[:1200])

m = json.load(open('backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json'))
print("\n=== MULTISCALE _documentation: claves ===")
for k in m.get('_documentation', {}):
    print("  ", k)
for cand in ('kinematic_trajectory_thresholds','trajectory_thresholds','fatigue_thresholds','delta_svw_thresholds'):
    if cand in m.get('_documentation', {}):
        print(f"  {cand}:", m['_documentation'][cand])
    if cand in m:
        print(f"  (top) {cand}:", m[cand])
