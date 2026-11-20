"""Acceso a Supabase (API REST). La clave service_role solo vive en los Secrets del servidor."""
import requests
import streamlit as st

def _req(metodo, tabla, params=None, json=None, prefer="return=representation"):
    url = st.secrets["SUPABASE_URL"].rstrip("/") + "/rest/v1/" + tabla
    k = st.secrets["SUPABASE_KEY"]
    h = {"apikey": k, "Authorization": "Bearer " + k, "Content-Type": "application/json", "Prefer": prefer}
    r = requests.request(metodo, url, headers=h, params=params, json=json, timeout=20)
    r.raise_for_status()
    return r.json() if r.text else []

def _eq(f):
    return {k: f"eq.{v}" for k, v in f.items()}

def get(tabla, **f):
    return _req("GET", tabla, {"select": "*", **_eq(f)})

def ins(tabla, fila):
    return _req("POST", tabla, json=fila)[0]

def upsert(tabla, fila, conflicto):
    return _req("POST", tabla, {"on_conflict": conflicto}, fila, "resolution=merge-duplicates,return=representation")

def upd(tabla, filtros, fila):
    return _req("PATCH", tabla, _eq(filtros), fila)

def borrar(tabla, **f):
    return _req("DELETE", tabla, _eq(f))
