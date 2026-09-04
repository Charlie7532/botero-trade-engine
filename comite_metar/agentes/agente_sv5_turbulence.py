# -*- coding: utf-8 -*-
# agente de estacion sv5_turbulence -> turbulencia_de_mercado.
# Rol: regimen_fondo. Ancla de validacion: cambio_de_regimen_quietud_estallido.
# Lee SOLO su estacion en t (sin lookahead, via estado_en), decodifica
# D1xD2xD3 con sus labels canonicos + direccion fisica, aplica el sentido
# de la combinacion y emite su lectura respaldada por el catalogo
# homogenizado (ranking / EV continuo / N limpio / timing). La verdad habla.

from comite_metar.agentes._agente_base import Agente
from comite_metar.scripts import common


__all__ = ['AGENTE', 'leer', 'evidencia_catalogo', 'CUESTIONARIO', 'ESTACION']

ESTACION = "sv5_turbulence"


def _get_agente():
    perfiles = common.perfiles_por_estacion()
    return Agente(ESTACION, perfiles[ESTACION])


AGENTE = _get_agente()


def leer(t, episodio=None):
    """Lectura del agente en t (usa solo columnas <= t)."""
    return AGENTE.leer(t, episodio)


def evidencia_catalogo():
    """Evidencia del catalogo que respalda a este mundo."""
    return AGENTE._evidencia()


CUESTIONARIO = AGENTE.CUESTIONARIO