import sys, json
sys.path.insert(0, '/root/botero-trade')
from comite_metar.scripts import common, episodios as EP
from comite_metar.agentes._agente_base import Agente

lake = common.cargar_lake()
perf = common.cargar_perfiles()
eps = EP.generar(escribir=False, solo_vista_completa=True)
print('episodios:', len(eps))
agentes = [Agente(p['estacion'], p, lake=lake) for p in perf]
for idx in (0, 4, 99, 199, 499, 729):
    ep = eps[idx]
    pos = ep.get('t0')
    lecturas = [ag.leer(pos, episodio=ep) for ag in agentes]
    maduros = [(r['estacion'], bool(r.get('maduro'))) for r in lecturas]
    nm = sum(m for _, m in maduros)
    print(f'idx={idx} id={ep["episodio_id"]} fecha={ep["fecha_inicio"]} t0={pos} maduros={nm}')
    for e, m in maduros:
        if not m:
            pass
print('done')