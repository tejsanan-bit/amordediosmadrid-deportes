"""Semáforo de compatibilidad entre partidos consecutivos (solo informativo)."""

def huecos(a, b):
    """(mínimo, completo) en minutos entre el fin de a y el inicio de b."""
    margen = a["margen"] if (a["fuera"] or b["fuera"]) else 0   # entre dos partidos en el cole no hace falta
    minimo = margen + (b["desp"] if b["fuera"] else 0)
    return minimo, minimo + b["pres"]

def analizar(evs):
    evs = sorted(evs, key=lambda e: e["inicio"])
    out = []
    for a, b in zip(evs, evs[1:]):
        if a["inicio"].date() != b["inicio"].date():
            continue
        real = (b["inicio"] - a["fin"]).total_seconds() / 60
        mn, co = huecos(a, b)
        color = "verde" if real >= co else "amarillo" if real >= mn else "rojo"
        out.append({"a": a, "b": b, "color": color, "real": real, "min": mn, "comp": co})
    return out
