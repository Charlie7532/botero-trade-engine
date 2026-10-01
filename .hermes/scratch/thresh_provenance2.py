import json
# Valor VIVO de los vel thresholds (wave)
for f in ('rc_wave_derived.json', 'rc_wave_probability_table.json', 'rc_wave_ev_derived.json'):
    p = 'backend/modules/quality_swing/domain/rules/' + f
    try:
        d = json.load(open(p))
    except Exception as e:
        print(f, "ERR", e); continue
    vt = d.get('vel_thresholds')
    cl = (d.get('classification') or {}).get('vel_svw_thresholds')
    print(f"--- {f} ---")
    print("   vel_thresholds:", vt)
    print("   classification.vel_svw_thresholds:", cl)

# Multiscale: buscar 0.30 en metadata / generator
import re
m = json.load(open('backend/modules/quality_swing/domain/rules/rc_ev_multiscale_tree.json'))
doc = m.get('_documentation', {})
dtd = doc.get('dimension_thresholds_definition')
print("\n=== MULTISCALE dimension_thresholds_definition ===")
print(json.dumps(dtd, ensure_ascii=False, indent=1)[:1500] if dtd else "NO PRESENTE")
