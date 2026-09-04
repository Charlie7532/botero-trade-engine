import sys, json
sys.path.insert(0, '/root/botero-trade')
import pandas as pd
from comite_metar.scripts import common
from comite_metar.agentes._agente_base import Agente

lake = common.cargar_lake()
perfiles = common.cargar_perfiles()
episodios = json.load(open('comite_metar/salidas/episodios.json'))

# Encontrar un episodio donde TODAS las 11 estaciones tengan datos validos
# (periodo maduro ~2015-2024). Contar estaciones activas por episodio.
def n_estaciones_activas(t0):
    n = 0
    for p in perfiles:
        est = p['estacion']
        col = f"{est}_d1_bin"
        if col in lake.columns:
            v = lake.iloc[t0][col]
            if v is not None and not (isinstance(v, float) and pd.isna(v)) and v != -1:
                n += 1
    return n

# Buscar episodio con mas estaciones activas (ideal 11)
mejor = None
for ep in episodios:
    n = n_estaciones_activas(ep['t0'])
    if mejor is None or n > mejor[1]:
        mejor = (ep, n)
ep, n_act = mejor
print(f"Episodio con más estaciones activas: id={ep['episodio_id']}, t0={ep['t0']}, fecha={ep['fecha_inicio']}, activas={n_act}/11")

# Ejecutar los 11 agentes
print(f"\n{'estacion':<16} {'rol':<12} {'dirSPY':<9} {'conv':<8} {'accion':<10} {'state'}")
print("-"*78)
for perfil in perfiles:
    est = perfil['estacion']
    ag = Agente(est, perfil, lake=lake)
    r = ag.leer(ep['t0'], episodio=ep['episodio_id'])
    if not r.get('maduro'):
        print(f"{est:<16} PRE-INCEPTION/NO-ACTIVA")
        continue
    lec = r.get('lectura') or {}
    print(f"{est:<16} {str(lec.get('rol_precognitivo')):<12} {str(lec.get('direccion_anticipada_spy')):<9} {str(lec.get('conviccion')):<8} {str(lec.get('accion')):<10} {r.get('estado',{}).get('state_key')}")
print("-"*78)