import sys, json
sys.path.insert(0, '/root/botero-trade')
from comite_metar.scripts import common
from comite_metar.agentes._agente_base import Agente

# Cargar entornos
lake = common.cargar_lake()
perfiles = common.cargar_perfiles()
episodios = json.load(open('comite_metar/salidas/episodios.json'))

# Tomar un episodio maduro (donde VIX este activo y sea reciente -> mejor lectura)
ep = episodios[-1]  # el mas reciente
print(f"Episodio de prueba: id={ep['episodio_id']}, t0={ep['t0']}, fecha={ep['fecha_inicio']}, activos={ep.get('estaciones_activas_t0')}")

# Instanciar 11 agentes y leer en t0
resultados = []
for perfil in perfiles:
    est = perfil['estacion']
    ag = Agente(est, perfil, lake=lake)
    r = ag.leer(ep['t0'], episodio=ep['episodio_id'])
    resultados.append({
        'estacion': est,
        'maduro': r.get('maduro'),
        'pre_inception': r.get('pre_inception'),
        'rol_precognitivo': (r.get('lectura') or {}).get('rol_precognitivo'),
        'direccion_spy': (r.get('lectura') or {}).get('direccion_anticipada_spy'),
        'conviccion': (r.get('lectura') or {}).get('conviccion'),
        'accion': (r.get('lectura') or {}).get('accion'),
        'state_key': (r.get('estado') or {}).get('state_key'),
        'evidencia_top': (r.get('lectura') or {}).get('razon'),
    })

print(f"\n{'estacion':<16} {'maduro':<7} {'rol':<12} {'dir':<9} {'conv':<8} {'accion':<10}")
print("-"*80)
maduros = 0
for r in resultados:
    if r['maduro']:
        maduros += 1
    print(f"{r['estacion']:<16} {str(r['maduro']):<7} {str(r['rol_precognitivo']):<12} {str(r['direccion_spy']):<9} {str(r['conviccion']):<8} {str(r['accion']):<10} | {r['state_key']}")
print("-"*80)
print(f"\nMaduros en t0={ep['t0']} ({ep['fecha_inicio']}): {maduros}/11")
print("\n=== Ejemplo lectura completa de 2 agentes maduros ===")
for r in resultados:
    if r['maduro']:
        print(f"\n--- {r['estacion']} ---")
        print(f"  razon: {r['evidencia_top']}")