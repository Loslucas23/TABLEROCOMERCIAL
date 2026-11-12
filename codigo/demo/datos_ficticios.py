"""La intranet sobre datos FICTICIOS: nombres inventados y cifras cambiadas. Solo para capturas."""
import hashlib, os, random, sys
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]   # la carpeta del proyecto
sys.path.insert(0, str(BASE)); os.chdir(BASE)
import numpy as np, pandas as pd
import nucleo

TIPOS = ["Almacén", "Autoservicio", "Supermercado", "Distribuidora", "Mayorista", "Comercial", "Provisión", "Mercado", "Casa", "Cooperativa"]
LUGARES = ["Del Puerto", "El Ceibo", "Los Aromos", "La Paloma", "Del Litoral", "El Hornero", "Santa Clara", "El Trébol", "Las Acacias",
           "Del Centro", "La Estrella", "El Faro", "Los Pinos", "San Jorge", "La Cumbre", "El Mirador", "Del Sur", "La Pradera",
           "El Ombú", "Las Piedras Blancas", "Don Pedro", "La Esquina", "El Molino", "Villa Serena", "El Timbó", "La Rivera",
           "Buen Día", "El Tala", "Los Teros", "La Querencia", "El Sauce", "Punta Norte", "La Colmena", "El Arriero", "Doña Rosa"]
SUF = ["", " S.A.", " S.R.L.", "", " Ltda.", ""]
NOM = ["Ana", "Bruno", "Carla", "Diego", "Elena", "Fabián", "Gimena", "Hugo", "Inés", "Joaquín", "Karen", "Leandro", "Mónica", "Nicolás", "Olga", "Pedro"]
APE = ["Acosta", "Bentos", "Cabrera", "Duarte", "Espino", "Ferrari", "Giménez", "Herrera", "Ibarra", "Juárez", "Lemos", "Medina", "Núñez", "Olivera", "Pintos", "Quiroga"]
_m: dict = {}; _usados: set = set()

def _h(s): return int(hashlib.sha256(("demo7|" + s).encode()).hexdigest(), 16)

def falso(real: str, persona=False) -> str:
    if real in ("(sin dato)", "nan", "", "None", "<NA>"): return real
    k = (real.strip().upper(), persona)
    if k not in _m:
        h = _h(real.strip().upper()); i = 0
        while True:
            x = h + i * 7919
            n = (f"{NOM[x % 16]} {APE[(x // 16) % 16]}" if persona
                 else f"{TIPOS[x % 10]} {LUGARES[(x // 10) % 35]}{SUF[(x // 350) % 6]}").upper()
            if i > 3: n = f"{n} {i}"
            if n not in _usados: break
            i += 1
        _usados.add(n); _m[k] = n
    return _m[k]

EMPRESA = {"Cliente", "Distribuidor", "Grupo"}; PERSONA = {"Vendedor", "Vendedor del distribuidor"}
MEDIDAS = ("Cajas", "Pesos", "Unidades", "Dolares")

def anonimizar(d: dict) -> dict:
    out = {}
    for k, df in d.items():
        if not isinstance(df, pd.DataFrame) or not len(df): out[k] = df; continue
        df = df.copy()
        quien = next((c for c in ("Cliente", "Distribuidor") if c in df.columns), None)
        # cada cliente con su factor (0,45 a 1,5) y uno general: ni los totales ni el ranking son los reales
        if quien:
            u = pd.Series(df[quien].astype(str).unique())
            f = dict(zip(u, [0.62 * (0.45 + (_h("f" + x) % 1000) / 950) for x in u]))
            factor = df[quien].astype(str).map(f).to_numpy()
        else:
            cod = df["Codigo"].astype(str) if "Codigo" in df.columns else pd.Series(["x"] * len(df))
            factor = cod.map(lambda x: 0.62 * (0.6 + (_h("p" + x) % 1000) / 1100)).to_numpy()
        for c in df.columns:
            if c.startswith(MEDIDAS) and pd.api.types.is_numeric_dtype(df[c]):
                df[c] = (df[c].to_numpy() * factor).round(0 if c.startswith(("Cajas", "Unidades")) else 2)
        for c in df.columns:
            if c in EMPRESA or c in PERSONA:
                u = df[c].astype(str).unique()
                df[c] = df[c].astype(str).map({x: falso(x, c in PERSONA) for x in u})
        for c in ("Rut", "CodCliente"):
            if c in df.columns:
                u = df[c].astype(str).unique()
                df[c] = df[c].astype(str).map({x: str(100000 + _h("r" + x) % 899999) for x in u})
        out[k] = df
    return out

_orig = nucleo.cargar
def cargar(firma_=None):
    return anonimizar(_orig(firma_))
nucleo.cargar = cargar

import uvicorn
from api.app import api
uvicorn.run(api, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
