"""Copia los datos de la web oficial a Supabase.
Ejecutar desde un equipo que SÍ llegue a juegosdeportivos.ecmadrid.org (un PC en España, o GitHub Actions).
  python sincronizar.py --catalogo   # competiciones y grupos (una vez, y cuando cambie la temporada)
  python sincronizar.py              # partidos de los equipos creados (cada pocas horas)
Variables de entorno: SUPABASE_URL, SUPABASE_KEY, COLEGIO (por defecto 'amor de dios'), TEMPORADA (12)"""
import os
import sys
from datetime import datetime, timezone

import requests

import calendario_jdm as jdm

URL = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
K = os.environ["SUPABASE_KEY"]
COLEGIO = os.environ.get("COLEGIO", "amor de dios")
TEMP = int(os.environ.get("TEMPORADA", "12"))
H = {"apikey": K, "Content-Type": "application/json"}
if K.startswith("eyJ"):
    H["Authorization"] = "Bearer " + K


def sb(metodo, tabla, params=None, datos=None, prefer="return=minimal"):
    r = requests.request(metodo, URL + tabla, headers={**H, "Prefer": prefer}, params=params, json=datos, timeout=60)
    if not r.ok:
        sys.exit(f"Error de Supabase {r.status_code}: {r.text[:300]}")
    return r.json() if "representation" in prefer else None


def subir(tabla, filas, conflicto):
    for i in range(0, len(filas), 200):
        sb("POST", tabla, {"on_conflict": conflicto}, filas[i:i + 200], "resolution=merge-duplicates,return=minimal")


def catalogo(cli):
    filas = []
    for dep in (1, 2, 3):
        for comp in cli.competiciones(dep, TEMP):
            for cat in cli.categorias(comp["Id"]):
                for g in cli.grupos(dep, comp["Id"], cat["Id"]):
                    filas.append({"deporte_id": dep, "competicion_id": comp["Id"], "competicion": comp["Nombre"],
                                  "categoria_id": cat["Id"], "grupo_id": g["Id"], "grupo": g["Nombre"]})
        print(f"Deporte {dep}: {len(filas)} grupos acumulados")
    subir("catalogo", filas, "deporte_id,competicion_id,categoria_id,grupo_id")


def partidos(cli):
    filas = []
    for e in sb("GET", "equipos", {"select": "*"}, prefer="return=representation"):
        n = 0
        for p in cli.partidos(e["deporte_id"], e["competicion_id"], e["categoria_id"], e["grupo_id"]):
            f = jdm.fila(p)
            if jdm.norm(COLEGIO) not in jdm.norm(f["local"] + " " + f["visitante"]):
                continue
            f["fecha"] = f["fecha"].isoformat() if f["fecha"] else None
            filas.append({"id": f["id"], "grupo_id": e["grupo_id"], "datos": f})
            n += 1
        print(f"{e['nombre']}: {n} partidos del colegio")
    subir("partidos", filas, "id")


if __name__ == "__main__":
    cli = jdm.Cliente()
    try:
        catalogo(cli) if "--catalogo" in sys.argv else partidos(cli)
    except requests.RequestException as ex:
        sys.exit(f"No se pudo leer la web oficial: {ex}")
    subir("sync", [{"id": 1, "ultima": datetime.now(timezone.utc).isoformat()}], "id")
    print("Sincronización terminada.")
