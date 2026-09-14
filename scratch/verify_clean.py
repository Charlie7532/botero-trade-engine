from pathlib import Path
dossiers = list(Path('/root/botero-trade/.hermes/dossiers/capa1_personalidades').glob('*.md'))
all_clean = True
for d in sorted(dossiers):
    txt = d.read_text()
    stk_c = txt.count('STK_')
    anec_c = txt.count('ANECDOTAL')
    low_c = txt.count('`LOW`') + txt.count('| LOW |')
    if stk_c > 0 or anec_c > 0 or low_c > 0:
        print(f'ERROR: {d.name} has STK_={stk_c}, ANECDOTAL={anec_c}, LOW={low_c}')
        all_clean = False
    else:
        dia_c = txt.count('DIAMOND')
        mkt_c = txt.count('MKT_')
        print(f'{d.name:28s} | CLEAN! (MKT_={mkt_c:2d}, DIAMOND={dia_c:2d})')

if all_clean:
    print('\nALL 11 DOSSIERS ARE 100% CLEAN OF STK_ AND LEGACY TIERS!')
