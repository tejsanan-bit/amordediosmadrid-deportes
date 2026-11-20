import hmac
import html
import os
import secrets as sec
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
import streamlit as st

import calendario_jdm as jdm
import correcciones as cr
import db
import semaforo as sm

st.set_page_config(page_title="Calendario deportivo", page_icon="🏅", layout="centered")
st.markdown("""<style>
h1,h2,h3{letter-spacing:-.01em} .block-container{max-width:760px;padding-top:1.5rem}
.sem{display:inline-block;width:.8em;height:.8em;border-radius:50%;margin-right:.4em}
</style>""", unsafe_allow_html=True)


def S(k, d=""):
    try:
        return st.secrets[k]
    except Exception:
        return os.environ.get(k, d)


COLEGIO, TEMP = S("COLEGIO", "amor de dios"), 12
DEPORTES = {"Baloncesto": 1, "Fútbol sala": 2, "Voleibol": 3}
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
COL = {"verde": "#2e9e5b", "amarillo": "#e0a800", "rojo": "#d64545"}
EMO = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}
PAL = ["#3b82f6", "#a855f7", "#f97316", "#14b8a6", "#ec4899", "#84cc16"]
leer = st.cache_data(ttl=30, show_spinner=False)(db.get)


def enlace(p, v):
    return f"{S('BASE_URL').rstrip('/')}/?{p}={v}"


# ---------- datos oficiales + correcciones ----------
def bruto(dep, comp, cat, grp):
    out = []
    for p in leer("partidos", grupo_id=grp):
        d = dict(p["datos"])
        d["fecha"] = datetime.fromisoformat(d["fecha"]) if d.get("fecha") else None
        out.append(d)
    return out


@st.cache_data(ttl=60, show_spinner=False)
def correcciones():
    try:
        return cr.cargar(S("OVERRIDES_CSV_URL"))
    except requests.RequestException:
        return {}


def minutos(d):
    h, m, _ = (int(x) for x in d.split(":"))
    return h * 60 + m


def evento(**k):
    k["fin"] = k["inicio"] + timedelta(minutes=k.pop("dur"))
    return k


def eventos_equipo(eq):
    corr, out = correcciones(), []
    for r in bruto(eq["deporte_id"], eq["competicion_id"], eq["categoria_id"], eq["grupo_id"]):
        if jdm.norm(COLEGIO) not in jdm.norm(r["local"] + " " + r["visitante"]):
            continue
        r = cr.aplicar(r, corr.get(r["id"]))
        if not r["fecha"]:
            continue
        casa = jdm.norm(COLEGIO) in jdm.norm(r["local"])
        out.append(evento(id=r["id"], tipo="cole", equipo=eq["nombre"], deporte=eq["nombre"],
                          titulo=f"{eq['nombre']} ({'casa' if casa else 'fuera'})", inicio=r["fecha"],
                          dur=minutos(r["duracion"]), ok=r["hora_definida"], fuera=not casa, pres=r["pres"],
                          desp=r["desp"], margen=r["margen"], estado=r["estado"], row=r, campo=r["campo"]))
    return out


def anulado(e):
    return any(k in jdm.norm(e["estado"]) for k in ("suspend", "aplaz"))


def eventos_jugador(j, equipos, insc, ext):
    evs = []
    for i in insc:
        if i["jugador_id"] == j["id"] and i["equipo_id"] in equipos:
            evs += [{**e, "jugador": j["iniciales"], "prio": i["prioridad"]} for e in eventos_equipo(equipos[i["equipo_id"]])]
    for x in ext:
        if x["jugador_id"] == j["id"]:
            evs.append(evento(id=-x["id"], tipo="ext", jugador=j["iniciales"], prio=1, deporte=x["deporte"],
                              titulo=f"{x['deporte']}: {x['titulo']}", inicio=datetime.fromisoformat(x["inicio"]),
                              dur=x["duracion_min"], ok=True, fuera=not x["en_colegio"], pres=x["pres_min"],
                              desp=x["desp_min"], margen=x["margen_min"], estado="", campo=x["lugar"]))
    return [e for e in evs if e["ok"] and not anulado(e)]


# ---------- visualización ----------
def pos(dt):  # 8:00 -> 0 %, 21:00 -> 100 %
    return (dt.hour * 60 + dt.minute - 480) / 780 * 100


def pista(evs, sem):
    h = '<div style="position:relative;height:32px;background:rgba(128,128,128,.14);border-radius:6px;margin:2px 0 8px;overflow:hidden">'
    for e in evs:
        c = PAL[sum(map(ord, e["deporte"])) % len(PAL)]
        a = max(0, pos(e["inicio"] - timedelta(minutes=e["pres"] + (e["desp"] if e["fuera"] else 0))))
        i, f = max(0, pos(e["inicio"])), min(100, pos(e["fin"]))
        borde = COL.get(sem.get(id(e)), "transparent")
        t = html.escape(f"{e['titulo']} · {e['inicio']:%H:%M}")
        h += f'<div title="{t}" style="position:absolute;left:{a}%;width:{max(i - a, 1)}%;top:0;bottom:0;background:{c}55"></div>'
        h += (f'<div title="{t}" style="position:absolute;left:{i}%;width:{max(f - i, 2)}%;top:0;bottom:0;background:{c};'
              f'border:3px solid {borde};box-sizing:border-box;color:#fff;font-size:11px;padding:1px 4px;overflow:hidden;'
              f'white-space:nowrap">{e["inicio"]:%H:%M}</div>')
    return h + "</div>"


def semaforo_ui(por_jugador, un_adulto, dias=21):
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    lim = hoy + timedelta(days=dias)
    filt = {j: [e for e in l if hoy <= e["inicio"] < lim] for j, l in por_jugador.items()}
    todos = [e for l in filt.values() for e in l]
    if not todos:
        st.info("No hay partidos con hora en los próximos 21 días.")
        return
    res = [r for g in ([todos] if not un_adulto else filt.values()) for r in sm.analizar(g)]
    sem = {id(r["b"]): r["color"] for r in res}
    st.caption("Bloque oscuro = partido · franja clara = llegada y desplazamiento · borde = encaje con el partido anterior")
    for dia in sorted({e["inicio"].date() for e in todos}):
        st.markdown(f"**{DIAS[dia.weekday()]} {dia:%d/%m}**")
        for j, l in filt.items():
            d = [e for e in l if e["inicio"].date() == dia]
            if d:
                st.caption(j)
                st.markdown(pista(d, sem), unsafe_allow_html=True)
    malos = [r for r in res if r["color"] != "verde"]
    for r in malos:
        a, b = r["a"], r["b"]
        p = a if a["prio"] <= b["prio"] else b
        st.markdown(f"{EMO[r['color']]} **{r['b']['inicio']:%a %d/%m}** · {a['titulo']} ({a['jugador']}) → {b['titulo']} ({b['jugador']}): "
                    f"hay {r['real']:.0f} min; lo ideal son {r['comp']} y el mínimo {r['min']}. Prioridad: {p['titulo']}")
    if not malos:
        st.success("🟢 Todo encaja con holgura.")


def otras_ligas(ext, con_jugador=None):
    ahora = datetime.now()
    fut = sorted([x for x in ext if datetime.fromisoformat(x["inicio"]) >= ahora], key=lambda x: x["inicio"])
    if not fut:
        st.caption("Nadie ha añadido partidos de otras ligas.")
    for x in fut:
        d = datetime.fromisoformat(x["inicio"])
        quien = f" · {con_jugador[x['jugador_id']]}" if con_jugador else ""
        st.markdown(f"**{DIAS[d.weekday()]} {d:%d/%m %H:%M}** · {x['deporte']} · {x['lugar'] or 'lugar sin indicar'}{quien}")


def proximos(evs):
    ahora = datetime.now()
    return sorted([e for e in evs if e["tipo"] == "cole" and e["inicio"] >= ahora], key=lambda e: e["inicio"])


# ---------- vista de familia ----------
def vista_familia(tok):
    js = leer("jugadores", familia=tok)
    if not js:
        st.error("Este enlace no es válido. Pídele uno nuevo al gestor deportivo.")
        return
    equipos = {e["id"]: e for e in leer("equipos")}
    insc = [i for i in leer("inscripciones") if i["jugador_id"] in {j["id"] for j in js}]
    ext_all = leer("externos")
    ids = {j["id"]: j["iniciales"] for j in leer("jugadores")}
    st.title("Calendario de tu familia")
    un_adulto = st.checkbox("Voy con un adulto por jugador (no cuenta el choque entre hermanos)", value=js[0]["un_adulto"])
    if un_adulto != js[0]["un_adulto"]:
        db.upd("jugadores", {"familia": tok}, {"un_adulto": un_adulto})
        leer.clear()
    por = {f"{j['iniciales']} #{j['dorsal'] or '-'}": eventos_jugador(j, equipos, insc, ext_all) for j in js}
    t1, t2, t3, t4 = st.tabs(["Semáforo", "Asistencia", "Añadir partido de otra liga", "Otras ligas"])
    with t1:
        semaforo_ui(por, un_adulto)
        with st.expander("Prioridad de cada equipo"):
            for j in js:
                for i in [i for i in insc if i["jugador_id"] == j["id"]]:
                    v = st.number_input(f"{j['iniciales']} · {equipos[i['equipo_id']]['nombre']} (1 = la más importante)",
                                        1, 9, i["prioridad"], key=f"p{j['id']}_{i['equipo_id']}")
                    if v != i["prioridad"]:
                        db.upd("inscripciones", {"jugador_id": j["id"], "equipo_id": i["equipo_id"]}, {"prioridad": v})
                        leer.clear()
        filas = [e["row"] for l in por.values() for e in l if e["tipo"] == "cole"]
        if filas:
            st.download_button("Descargar calendario (.ics)", jdm.generar_ics(sorted(filas, key=lambda r: r["fecha"])),
                               "partidos.ics", "text/calendar")
    with t2:
        asis = {(a["jugador_id"], a["partido_id"]): a["estado"] for a in leer("asistencias")}
        for j in js:
            st.markdown(f"**{j['iniciales']} #{j['dorsal'] or '-'}**")
            for e in proximos(por[f"{j['iniciales']} #{j['dorsal'] or '-'}"]):
                op = ["Sin confirmar", "Voy", "No voy", "Duda"]
                act = asis.get((j["id"], e["id"]), op[0])
                v = st.radio(f"{DIAS[e['inicio'].weekday()]} {e['inicio']:%d/%m %H:%M} · {e['titulo']}", op,
                             index=op.index(act), horizontal=True, key=f"a{j['id']}_{e['id']}")
                if v != act:
                    db.upsert("asistencias", {"jugador_id": j["id"], "partido_id": e["id"], "estado": v}, "jugador_id,partido_id")
                    leer.clear()
    with t3:
        with st.form("ext", clear_on_submit=True):
            quien = st.selectbox("Jugador", [j["iniciales"] for j in js])
            dep, tit = st.text_input("Deporte (p. ej. Fútbol)"), st.text_input("Rival o torneo")
            c1, c2, c3 = st.columns(3)
            fecha, hora, dur = c1.date_input("Fecha"), c2.time_input("Hora", value=None), c3.number_input("Duración (min)", 15, 300, 60)
            lugar, cole = st.text_input("Lugar"), st.checkbox("Es en el colegio")
            with st.expander("Ajustes de tiempos"):
                d1, d2, d3 = st.columns(3)
                pr, de, ma = d1.number_input("Llegar antes (min)", 0, 120, 30), d2.number_input("Desplazamiento (min)", 0, 120, 15), d3.number_input("Margen después (min)", 0, 120, 15)
            if st.form_submit_button("Guardar partido") and dep and hora:
                jid = next(j["id"] for j in js if j["iniciales"] == quien)
                db.ins("externos", {"jugador_id": jid, "deporte": dep, "titulo": tit, "inicio": datetime.combine(fecha, hora).isoformat(),
                                    "duracion_min": dur, "lugar": lugar, "en_colegio": cole, "pres_min": pr, "desp_min": de, "margen_min": ma})
                leer.clear()
                st.rerun()
        for x in [x for x in ext_all if x["jugador_id"] in {j["id"] for j in js}]:
            if st.button(f"Borrar: {x['deporte']} {x['inicio'][:16].replace('T', ' ')}", key=f"b{x['id']}"):
                db.borrar("externos", id=x["id"])
                leer.clear()
                st.rerun()
    with t4:
        st.caption("Partidos de otras ligas añadidos por las familias. Comprueba que el tuyo está.")
        otras_ligas(ext_all)


# ---------- vista de equipo (solo lectura) ----------
def vista_equipo(slug):
    eq = next(iter(leer("equipos", slug=slug)), None)
    if not eq:
        st.error("Enlace de equipo no válido.")
        return
    st.title(eq["nombre"])
    insc = [i for i in leer("inscripciones") if i["equipo_id"] == eq["id"]]
    js = {j["id"]: j for j in leer("jugadores")}
    asis = leer("asistencias")
    for e in proximos(eventos_equipo(eq)):
        st.markdown(f"**{DIAS[e['inicio'].weekday()]} {e['inicio']:%d/%m %H:%M}** · {e['titulo']} · {e['campo']}")
        if e["estado"] and e["estado"] != "Pendiente de Jugar":
            st.caption(f"{e['estado']} {e['row'].get('nota', '')}")
        c = {"Voy": [], "No voy": [], "Duda": []}
        for i in insc:
            j = js.get(i["jugador_id"])
            est = next((a["estado"] for a in asis if a["jugador_id"] == i["jugador_id"] and a["partido_id"] == e["id"]), None)
            if j and est in c:
                c[est].append(f"{j['iniciales']} #{j['dorsal'] or '-'}")
        st.caption(" · ".join(f"{k}: {', '.join(v) or '—'}" for k, v in c.items()))
    st.subheader("Otras ligas")
    otras_ligas(leer("externos"))


# ---------- gestor / administrador ----------
def lista_comps(dep):
    v = {c["competicion_id"]: c["competicion"] for c in leer("catalogo", deporte_id=dep)}
    return [{"Id": k, "Nombre": n} for k, n in sorted(v.items(), key=lambda x: x[1])]


def lista_grupos(dep, comp):
    return [{"id": c["grupo_id"], "nombre": c["grupo"], "cat": c["categoria_id"]}
            for c in leer("catalogo", deporte_id=dep, competicion_id=comp)]


def gestor():
    G = S("GESTORES", {})
    if "user" not in st.session_state:
        st.title("Acceso del gestor")
        with st.form("login"):
            u, k = st.text_input("Usuario"), st.text_input("Clave", type="password")
            if st.form_submit_button("Entrar"):
                if u in G and hmac.compare_digest(str(G[u]), k):
                    st.session_state.user = u
                    st.rerun()
                st.error("Usuario o clave incorrectos.")
        st.caption("Las familias entran con el enlace personal que les envía el gestor.")
        return
    st.title("Gestión deportiva")
    st.caption(f"Sesión de {st.session_state.user}")
    sync = leer("sync")
    if sync:
        st.caption(f"Datos oficiales sincronizados por última vez: {sync[0]['ultima'][:16].replace('T', ' ')} (hora UTC)")
    else:
        st.warning("Aún no se han sincronizado datos de la web oficial. Ejecuta sincronizar.py (ver instrucciones).")
    t1, t2, t3, t4 = st.tabs(["Equipos", "Jugadores", "Calendario y semáforo", "Aviso por WhatsApp"])
    equipos = {e["id"]: e for e in leer("equipos")}
    with t1:
        nom = st.text_input("Nombre (p. ej. Voleibol Benjamín)", key="nom_eq")
        dep = st.selectbox("Deporte", list(DEPORTES))
        comps = lista_comps(DEPORTES[dep])
        comp = st.selectbox("Competición", [c["Nombre"] for c in comps]) if comps else None
        gr = lista_grupos(DEPORTES[dep], next(c["Id"] for c in comps if c["Nombre"] == comp)) if comp else []
        g = st.selectbox("Grupo en la web oficial", [x["nombre"] for x in gr]) if gr else None
        if st.button("Crear equipo") and nom and g:
            gg = next(x for x in gr if x["nombre"] == g)
            db.ins("equipos", {"nombre": nom, "slug": sec.token_urlsafe(6), "deporte_id": DEPORTES[dep],
                               "competicion_id": next(c["Id"] for c in comps if c["Nombre"] == comp), "categoria_id": gg["cat"], "grupo_id": gg["id"]})
            leer.clear()
            st.rerun()
        for e in equipos.values():
            st.markdown(f"**{e['nombre']}** — enlace del equipo: `{enlace('e', e['slug'])}`")
            if st.button("Eliminar", key=f"de{e['id']}"):
                db.borrar("equipos", id=e["id"])
                leer.clear()
                st.rerun()
    with t2:
        js, insc = leer("jugadores"), leer("inscripciones")
        fams = sorted({j["familia"] for j in js})
        with st.form("ju", clear_on_submit=True):
            c1, c2 = st.columns(2)
            ini, dor = c1.text_input("Iniciales"), c2.number_input("Nº de camiseta", 0, 99, 0)
            eqs = st.multiselect("Equipos", [e["nombre"] for e in equipos.values()])
            fam = st.selectbox("Familia", ["Nueva familia"] + [f"Familia de {next(j['iniciales'] for j in js if j['familia'] == f)} ({f[:4]})" for f in fams])
            if st.form_submit_button("Dar de alta") and ini:
                tok = sec.token_urlsafe(9) if fam == "Nueva familia" else fams[[f"Familia de {next(j['iniciales'] for j in js if j['familia'] == f)} ({f[:4]})" for f in fams].index(fam)]
                nj = db.ins("jugadores", {"iniciales": ini.upper(), "dorsal": dor or None, "familia": tok})
                for e in equipos.values():
                    if e["nombre"] in eqs:
                        db.ins("inscripciones", {"jugador_id": nj["id"], "equipo_id": e["id"], "prioridad": 1})
                leer.clear()
                st.rerun()
        for j in js:
            nombres = ", ".join(equipos[i["equipo_id"]]["nombre"] for i in insc if i["jugador_id"] == j["id"] and i["equipo_id"] in equipos)
            st.markdown(f"**{j['iniciales']} #{j['dorsal'] or '-'}** · {nombres or 'sin equipo'}  \nEnlace de la familia: `{enlace('f', j['familia'])}`")
            if st.button("Dar de baja", key=f"dj{j['id']}"):
                db.borrar("jugadores", id=j["id"])
                leer.clear()
                st.rerun()
    with t3:
        js, insc, ext = leer("jugadores"), leer("inscripciones"), leer("externos")
        por = {f"{j['iniciales']} #{j['dorsal'] or '-'}": eventos_jugador(j, equipos, insc, ext) for j in js}
        semaforo_ui(por, True)
        st.subheader("Partidos de otras ligas")
        otras_ligas(ext, {j["id"]: j["iniciales"] for j in js})
    with t4:
        evs = [e for eq in equipos.values() for e in proximos(eventos_equipo(eq))]
        if evs:
            e = st.selectbox("Partido", evs, format_func=lambda e: f"{e['inicio']:%d/%m %H:%M} · {e['titulo']}")
            motivo = st.text_input("Motivo", "lluvia")
            txt = st.text_area("Mensaje", f"⚠️ Partido suspendido: {e['titulo']} del {DIAS[e['inicio'].weekday()]} {e['inicio']:%d/%m} a las {e['inicio']:%H:%M} ({motivo}). Os avisaremos de la nueva fecha.")
            st.link_button("Abrir en WhatsApp", "https://wa.me/?text=" + quote(txt))
            st.caption(f"Para que la web lo refleje, añade una fila en la hoja de correcciones con el id {e['id']}.")
    if st.button("Cerrar sesión"):
        del st.session_state["user"]
        st.rerun()


q = st.query_params
try:
    if "f" in q:
        vista_familia(q["f"])
    elif "e" in q:
        vista_equipo(q["e"])
    else:
        gestor()
except requests.RequestException as ex:
    st.error("No se ha podido conectar con la base de datos. Inténtalo en unos minutos.")
    st.code(repr(ex)[:500])
