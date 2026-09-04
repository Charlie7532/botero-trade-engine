import sys, json
sys.path.insert(0, '/root/botero-trade')
from comite_metar.scripts import common
from comite_metar.agentes._agente_base import Agente

lake = common.cargar_lake()
perf = common.cargar_perfiles()
eps = json.load(open('/root/botero-trade/comite_metar/salidas/episodios.json'))
for pos in (253, 2000, 4000, 6000):
    mad = []
    for p in perf:
        try:
            ag = Agente(p['estacion'], p, lake=lake)
        except Exception as e:
            print('CTOR ERR', p['estacion'], e); continue
        r = ag.leer(pos)
        mad.append((p['estacion'], bool(r.get('maduro')), r.get('pre_inception'),
                    (r.get('lectura') or {}).get('direccion_anticipada_spy')))
    nm = sum(1 for _, m, _, _ in mad if m)
    print('pos', pos, 'maduros=', nm)
    for m in mad:
        if not m[1]:
            print('   pre_inception:', m[0], 'pi=', m[2])
print('row253 bins:', {e: lake.iloc[253].get(f'{e}_d1_bin') for e in ['vix', 'fg', 'credit', 'bsi']})