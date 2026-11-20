#!/usr/bin/env python3
"""
Consulta los calendarios de juegosdeportivos.ecmadrid.org para un colegio,
un deporte y (opcionalmente) un grupo.

Uso:
  pip install requests
  python calendario_jdm.py --colegio "sagrado corazon" --deporte voleibol
  python calendario_jdm.py --colegio "sagrado corazon" --deporte voleibol --grupo 8
  python calendario_jdm.py -c "nuestra senora" -d voleibol --competicion benjamin --csv out.csv --ics out.ics

Los filtros ignoran mayúsculas y tildes y buscan "contiene".
Usa los mismos endpoints JSON que la propia web (ver el HAR analizado).
Hazlo con moderación (una consulta ocasional, no cada pocos minutos).
"""
import argparse
import csv
import sys
import time
import unicodedata
from datetime import datetime, timedelta

import requests

BASE = "https://juegosdeportivos.ecmadrid.org"
DEPORTES = {"baloncesto": 1, "futbol sala": 2, "voleibol": 3}
TEMPORADA_DEFECTO = 12  # TEMPORADA 2026-2027
PAUSA = 0.3  # segundos entre peticiones, para no cargar el servidor


def norm(s):
    """minúsculas, sin tildes, sin espacios extra"""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


class Cliente:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": BASE + "/Calendarios/CalendarioTemporada",
            "User-Agent": "calendario-colegio/1.0 (uso personal)",
        })

    def get(self, ruta, **params):
        params["_"] = int(time.time() * 1000)
        r = self.s.get(BASE + ruta, params=params, timeout=30)
        r.raise_for_status()
        time.sleep(PAUSA)
        return r.json()

    def competiciones(self, id_deporte, id_temporada):
        d = self.get("/api/CompeticionesPorDeporte",
                     action="ObtenerCompeticionesDeporteListado",
                     IdDeporte=id_deporte, IdTemporada=id_temporada,
                     elementoTodas="false", soloActivas="true")
        return d.get("data", [])

    def categorias(self, id_competicion):
        d = self.get("/api/CategoriasPorCompeticion",
                     action="ObtenerCategoriasCompeticionListado",
                     IdCompeticion=id_competicion, elementoTodas="false")
        return d.get("data", [])

    def grupos(self, id_deporte, id_competicion, id_categoria):
        d = self.get("/api/GruposPorCategoria",
                     action="ObtenerGruposCategoriaListado",
                     IdCategoria=id_categoria, IdCompeticion=id_competicion,
                     IdDeporte=id_deporte, elementoTodos="false")
        return d.get("data", [])

    def partidos(self, id_deporte, id_competicion, id_categoria, id_grupo):
        """Todos los enfrentamientos del grupo (paginando)."""
        out, skip, take = [], 0, 200
        while True:
            d = self.get("/api/JornadaEnfrentamientosPorGrupo",
                         action="ObtenerEnfrentamientosGrupoListado",
                         skip=skip, take=take,
                         sort='[{"selector":"FechaHora","desc":false}]',
                         IdDeporte=id_deporte, IdCompeticion=id_competicion,
                         IdCategoria=id_categoria, IdGrupo=id_grupo,
                         IdJornada=0, IdEquipo=0)
            data = d.get("data", [])
            out.extend(data)
            if len(data) < take:
                return out
            skip += take


def fila(p):
    """Convierte un enfrentamiento de la API en un dict simple."""
    fh = datetime.fromisoformat(p["FechaHora"]) if p.get("FechaHora") else None
    campo = p.get("CampoJuego") or {}
    return {
        "id": p.get("Id"),
        "competicion": p.get("Competicion", ""),
        "grupo": p.get("Grupo", ""),
        "jornada": p.get("NumeroJornada", ""),
        "fecha": fh,
        # La web guarda 00:00 cuando aún no hay hora asignada
        "hora_definida": bool(fh and (fh.hour or fh.minute)),
        "local": p.get("EquipoLocal") or "(por determinar)",
        "visitante": p.get("EquipoVisitante") or "(por determinar)",
        "campo": p.get("Campo") or "",
        "direccion": campo.get("Direccion", ""),
        "estado": p.get("EstadoPartido", ""),
        "res_local": p.get("ResultadoEquipoLocal", 0),
        "res_visit": p.get("ResultadoEquipoVisitante", 0),
        "duracion": p.get("Duracion") or "01:30:00",
    }


def recopilar(args):
    cli = Cliente()
    id_dep = DEPORTES[norm(args.deporte)]
    f_col, f_grp, f_comp = norm(args.colegio), norm(args.grupo), norm(args.competicion)
    resultado = []

    for comp in cli.competiciones(id_dep, args.temporada):
        if f_comp and f_comp not in norm(comp["Nombre"]):
            continue
        for cat in cli.categorias(comp["Id"]):
            for g in cli.grupos(id_dep, comp["Id"], cat["Id"]):
                if f_grp and f_grp not in norm(g["Nombre"]):
                    continue
                print(f"  consultando {comp['Nombre']} / {g['Nombre']}...",
                      file=sys.stderr)
                for p in cli.partidos(id_dep, comp["Id"], cat["Id"], g["Id"]):
                    if f_col in norm(p.get("EquipoLocal")) or f_col in norm(p.get("EquipoVisitante")):
                        resultado.append(fila(p))

    resultado.sort(key=lambda r: (r["fecha"] or datetime.max, r["competicion"]))
    if args.futuros:
        hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        resultado = [r for r in resultado if r["fecha"] and r["fecha"] >= hoy]
    return resultado


def mostrar(rows):
    if not rows:
        print("No se han encontrado partidos con esos filtros.")
        return
    for r in rows:
        f = r["fecha"]
        if f:
            txt = f.strftime("%a %d/%m/%Y")
            txt += f" {f:%H:%M}" if r["hora_definida"] else " (hora por confirmar)"
        else:
            txt = "sin fecha"
        marcador = ""
        if r["estado"] and "Pendiente" not in r["estado"]:
            marcador = f"  [{r['res_local']}-{r['res_visit']}] {r['estado']}"
        print(f"{txt} | {r['competicion']} {r['grupo']} J{r['jornada']}")
        print(f"    {r['local']}  vs  {r['visitante']}{marcador}")
        if r["campo"]:
            print(f"    Campo: {r['campo']}")
        print()


def guardar_csv(rows, ruta):
    campos = ["fecha", "hora_definida", "competicion", "grupo", "jornada",
              "local", "visitante", "campo", "estado", "res_local", "res_visit"]
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore", delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "fecha": r["fecha"].isoformat() if r["fecha"] else ""})
    print(f"CSV guardado en {ruta}")


def _esc(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def generar_ics(rows):
    """Texto de un calendario .ics. Si la hora no está definida, evento de día completo."""
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//calendario-colegio//ES",
         "CALSCALE:GREGORIAN", "X-WR-TIMEZONE:Europe/Madrid"]
    for i, r in enumerate(rows):
        if not r["fecha"]:
            continue
        f = r["fecha"]
        L += ["BEGIN:VEVENT",
              f"UID:jdm-{f:%Y%m%d}-{i}-{abs(hash(r['local'] + r['visitante'])) % 10**8}@calendario-colegio"]
        L.append(f"DTSTAMP:{datetime.utcnow():%Y%m%dT%H%M%SZ}")
        if r["hora_definida"]:
            h, m, _ = (int(x) for x in r["duracion"].split(":"))
            fin = f + timedelta(hours=h, minutes=m)
            L += [f"DTSTART;TZID=Europe/Madrid:{f:%Y%m%dT%H%M%S}",
                  f"DTEND;TZID=Europe/Madrid:{fin:%Y%m%dT%H%M%S}"]
        else:
            L += [f"DTSTART;VALUE=DATE:{f:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{(f + timedelta(days=1)):%Y%m%d}"]
        aviso = ""
        if r.get("estado") and any(k in norm(r["estado"]) for k in ("suspend", "aplaz")):
            aviso = "[" + r["estado"].upper() + "] "
        L.append(f"SUMMARY:{_esc(aviso + r['local'] + ' - ' + r['visitante'])}")
        L.append(f"LOCATION:{_esc(r['campo'])}")
        desc = f"{r['competicion']} {r['grupo']} - Jornada {r['jornada']} ({r['estado']})"
        if r.get("nota"):
            desc += f" - {r['nota']}"
        L.append(f"DESCRIPTION:{_esc(desc)}")
        L.append("END:VEVENT")
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def guardar_ics(rows, ruta):
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        fh.write(generar_ics(rows))
    print(f"ICS guardado en {ruta}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--colegio", required=True, help="texto a buscar en el nombre del equipo/colegio")
    ap.add_argument("-d", "--deporte", required=True, choices=list(DEPORTES) + [k.upper() for k in DEPORTES],
                    type=lambda s: norm(s), help="baloncesto | futbol sala | voleibol")
    ap.add_argument("-g", "--grupo", default="", help='p. ej. "8" o "Grupo 8" (opcional)')
    ap.add_argument("--competicion", default="", help='p. ej. "benjamin" (opcional)')
    ap.add_argument("--temporada", type=int, default=TEMPORADA_DEFECTO, help="Id de temporada (12 = 2026-27)")
    ap.add_argument("--futuros", action="store_true", help="solo partidos desde hoy")
    ap.add_argument("--csv", help="guardar en CSV")
    ap.add_argument("--ics", help="guardar en .ics")
    args = ap.parse_args()

    try:
        rows = recopilar(args)
    except requests.RequestException as e:
        sys.exit(f"Error de red/servidor: {e}")
    mostrar(rows)
    if args.csv:
        guardar_csv(rows, args.csv)
    if args.ics:
        guardar_ics(rows, args.ics)


if __name__ == "__main__":
    main()
