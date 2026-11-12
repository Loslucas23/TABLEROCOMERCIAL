"""
habiles - los días hábiles de eQuim: de lunes a viernes, sin los feriados
que no se trabaja.

Lucas eligió (19/10/2026): los 5 feriados no laborables (1/1, 1/5, 18/7,
25/8, 25/12) más Carnaval y la Semana de Turismo. Los laborables (6/1,
19/4, 18/5, 19/6, 12/10, 2/11) se trabajan. Los sábados no son hábiles.

Los feriados salen de la librería «holidays» (los de Uruguay, con sus
traslados). Sin ella en el servidor, los mismos a mano: los fijos y,
Carnaval y Turismo, contados desde la Pascua (dateutil, que viene con
pandas).
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

# los de «holidays» que vienen como «bank» (bancarios) y eQuim no trabaja
NO_SE_TRABAJA = ("Carnaval", "Semana de Turismo")
FIJOS = ((1, 1, "Año Nuevo"), (5, 1, "Día de los Trabajadores"), (7, 18, "Jura de la Constitución"),
         (8, 25, "Declaratoria de la Independencia"), (12, 25, "Día de la Familia"))


@lru_cache(maxsize=32)
def feriados(anio: int) -> dict[dt.date, str]:
    """Los días de ese año que eQuim no trabaja (además de sábados y domingos)."""
    try:
        import holidays
        publicos = holidays.country_holidays("UY", years=anio)
        bancarios = holidays.country_holidays("UY", years=anio, categories=("bank",))
        out = dict(publicos.items())
        out.update({d: n for d, n in bancarios.items() if any(n.startswith(x) for x in NO_SE_TRABAJA)})
        return out
    except Exception:
        return _a_mano(anio)


def _a_mano(anio: int) -> dict[dt.date, str]:
    """Los mismos feriados sin la librería: los fijos, y Carnaval y Turismo desde la Pascua."""
    from dateutil.easter import easter
    out = {dt.date(anio, m, d): n for m, d, n in FIJOS}
    pascua = easter(anio)
    for k in (48, 47):                      # lunes y martes de Carnaval
        out[pascua - dt.timedelta(days=k)] = "Carnaval"
    for k in range(6, 1, -1):               # de lunes a viernes de la Semana de Turismo
        out[pascua - dt.timedelta(days=k)] = "Semana de Turismo"
    return out


def es_habil(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in feriados(d.year)


def contar(desde: dt.date, hasta: dt.date) -> int:
    """Los días hábiles de `desde` a `hasta`, los dos incluidos (0 si hasta < desde)."""
    if hasta < desde:
        return 0
    n, d = 0, desde
    while d <= hasta:
        if es_habil(d):
            n += 1
        d += dt.timedelta(days=1)
    return n
