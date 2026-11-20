"""Correcciones manuales (Google Sheets publicado como CSV) que prevalecen sobre la web oficial.
Columnas: id | estado | nueva_fecha | nueva_hora | nuevo_campo | nota | presentacion_min | desplazamiento_min | margen_min"""
import csv
import io
from datetime import datetime

import requests


def _fecha(t):
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, f)
        except ValueError:
            pass


def _hora(t):
    for f in ("%H:%M", "%H.%M", "%H:%M:%S"):
        try:
            return datetime.strptime(t, f).time()
        except ValueError:
            pass


def cargar(url):
    if not url:
        return {}
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    out = {}
    for row in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            out[int(row.get("id", ""))] = row
        except ValueError:
            pass
    return out


def _num(ov, k, d):
    try:
        return int(ov.get(k, ""))
    except ValueError:
        return d


def aplicar(r, ov):
    ov = ov or {}
    r = dict(r)
    r["modificado"], r["fecha_web"], r["nota"] = bool(ov), r["fecha"], ov.get("nota", "")
    nf, nh = _fecha(ov.get("nueva_fecha", "")), _hora(ov.get("nueva_hora", ""))
    base = r["fecha"] or datetime.min
    if nf or nh:
        dia = (nf or base).date()
        if nh:
            r["fecha"], r["hora_definida"] = datetime.combine(dia, nh), True
        else:
            r["fecha"] = datetime.combine(dia, base.time() if r["hora_definida"] else datetime.min.time())
    if ov.get("nuevo_campo"):
        r["campo"] = ov["nuevo_campo"]
    if ov.get("estado"):
        r["estado"] = ov["estado"]
    r["pres"], r["desp"], r["margen"] = (_num(ov, "presentacion_min", 30), _num(ov, "desplazamiento_min", 15),
                                         _num(ov, "margen_min", 15))
    return r
