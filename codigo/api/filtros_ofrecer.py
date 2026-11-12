"""
Fragmento de api/personal.py: qué se ofrece para filtrar y cuánto pesa cada valor.

Incluye `_alias_clientes`: un cliente que como distribuidor figura con otro
nombre se encuentra escribiendo cualquiera de los dos (ver docs/CASO-FILTROS.md).
"""
# lo que no se filtra arriba: medidas, fechas y códigos
NO_FILTRABLE = {"Mes", "MesNro", "MesNombre", "Anio", "Trimestre", "FY", "Codigo",
                "Estado", "EstadoCobertura", "Urgencia", "Clasificacion",
                # los vendedores de los distribuidores: se miran en Ventas ›
                # Al mercado; arriba, «Vendedor» es solo el de eQuim
                "Vendedor del distribuidor"}
# el orden en que se ofrecen: lo más usado primero, el resto alfabético
PRIMERO = ["Canal", "TipoVenta", "Linea", "Marca", "Categoria", "Familia", "Departamento",
           "Vendedor", "Cliente", "Producto"]


@ruteo_personal.get("/filtros-globales")
def filtros_globales(usuario: dict = Depends(usuario_actual)):
    """
    Todo por lo que se puede filtrar arriba, con sus valores y cuánto pesa
    cada uno. Sale de TODOS los archivos (retiros, mercado, stock,
    histórico), sin los filtros ya puestos: si no, al elegir un canal los
    demás desaparecían de la lista y no había forma de sumar otro.
    """
    d = S.datos_sin_globales(usuario)
    # la memoria de S.memo lleva los filtros puestos en la clave; acá no importan
    return S.memo({**usuario}, "filtros_globales", (), lambda: _ofrecer(d))


FUENTES_OFRECER = ("venta_full", "mercado_full", "stock", "historico")
# de qué archivo sale el peso de cada valor: el primero que tenga la columna.
# Sumar las cajas de varios archivos no da un número real (las de retiros
# están también en el histórico); retiros es la base.
MEDIDA_DE = {"venta": "cajas de retiros", "historico": "cajas del histórico",
             "stock": "cajas en stock", "mercado": "cajas al mercado"}
ORDEN_PESO = ("venta", "historico", "stock", "mercado")


def _columnas_filtrables(df: pd.DataFrame, fuente: str) -> list[str]:
    return [c for c in df.columns
            if c not in NO_FILTRABLE and not c.startswith(("Cajas", "Pesos", "Unidades", "Dolares"))
            and not pd.api.types.is_numeric_dtype(df[c])
            # en el mercado, Canal, Grupo y Cliente dicen otra cosa (S.MERCADO_OTRA_COSA):
            # sus valores no van en la lista de los de retiros
            and not (fuente == "mercado" and c in S.MERCADO_OTRA_COSA)]


def _pesos(df: pd.DataFrame, c: str) -> dict[str, float]:
    medida = next((m for m in ("CajasAct", "Cajas") if m in df.columns), None)
    g = (df.groupby(df[c].astype(str), dropna=False, observed=True)[medida].sum() if medida
         else df[c].astype(str).value_counts(dropna=False))
    # lo que llegó vacío cuenta como «(sin dato)»: se puede filtrar para encontrar lo que falta cargar
    out: dict[str, float] = {}
    for k, v in g.items():
        k = D.SIN_DATO if k in ("nan", "", "None", "<NA>") else str(k)
        out[k] = out.get(k, 0.0) + float(v)
    return out


def _valores(df: pd.DataFrame, c: str) -> set[str]:
    return {D.SIN_DATO if k in ("nan", "", "None", "<NA>") else k for k in S._unicos(df, c)}


def _ofrecer(d: dict) -> list[dict]:
    tablas: dict[str, dict[str, pd.DataFrame]] = {}      # dim -> fuente -> tabla
    for f in FUENTES_OFRECER:
        df = d.get(f)
        if df is None or not len(df):
            continue
        fuente = f.replace("_full", "")
        for c in _columnas_filtrables(df, fuente):
            # la Familia y la Categoría del stock, escritas a su manera, no se
            # ofrecen: el stock se recorta por lo que dice retiros de cada código
            if not (fuente == "stock" and c in ("Categoria", "Familia") and "Codigo" in df.columns):
                tablas.setdefault(c, {})[fuente] = df
    # el peso se suma solo en el archivo base; de los demás alcanza con qué
    # valores tienen (sumar los cuatro era el triple de cuentas para tirarlas)
    pesos: dict[str, dict[str, dict[str, float]]] = {}    # dim -> fuente -> valor -> cajas
    for c, por in tablas.items():
        base = next(f for f in ORDEN_PESO if f in por)
        pesos[c] = {f: _pesos(df, c) if f == base else dict.fromkeys(_valores(df, c), 0.0)
                    for f, df in por.items()}
    # arriba, solo lo que está en más de una tabla: lo que es solo de la venta
    # al mercado (Distribuidor, Localidad…) se filtra en Ventas › Al mercado
    for c in [c for c, x in pesos.items() if set(x) == {"mercado"}]:
        del pesos[c]
    out = []
    orden = [x for x in PRIMERO if x in pesos] + sorted(x for x in pesos if x not in PRIMERO)
    for c in orden:
        por = pesos[c]
        base = next(f for f in ORDEN_PESO if f in por)
        vals = set().union(*(set(x) for x in por.values()))
        # el peso, del archivo base; lo que solo está en otro archivo va con 0
        # (está, pero no pesa en la base) en vez de mezclar unidades
        n = {k: por[base].get(k, 0.0) for k in vals}
        if len([k for k in vals if k != D.SIN_DATO]) < 2:
            continue
        donde = set(por)
        # el cliente de eQuim recorta el mercado por su distribuidor (S.columna_global)
        if c == "Cliente" and d.get("mercado_full") is not None:
            donde.add("mercado")
        # y lo de producto recorta el stock por el código (S.DE_PRODUCTO)
        st = d.get("stock")
        if c in S.DE_PRODUCTO and st is not None and "Codigo" in st.columns:
            donde.add("stock")
        # el cliente que en la venta al mercado se llama de otra manera (el nombre
        # de fantasía del distribuidor contra la razón social de retiros): se lo
        # encuentra escribiendo cualquiera de los dos nombres
        alias = _alias_clientes(d, vals) if c == "Cliente" else {}
        out.append({"dim": c, "donde": sorted(donde), "medida": MEDIDA_DE[base],
                    "valores": [{"v": k, "n": round(v), **({"alias": alias[k]} if k in alias else {})}
                                for k, v in sorted(n.items(), key=lambda kv: (kv[0] == D.SIN_DATO, -kv[1]))]})
    # el Período primero (es lo que más se cambia); la Cartera junto al Vendedor
    extra = {x["dim"]: x for x in _cartera_y_periodo(d)}
    if S.CARTERA in extra:
        i = next((k + 1 for k, x in enumerate(out) if x["dim"] == "Vendedor"), len(out))
        out.insert(i, extra[S.CARTERA])
    return ([extra["Mes"]] if "Mes" in extra else []) + out


def _alias_clientes(d: dict, clientes: set[str]) -> dict[str, str]:
    """
    Cliente de retiros -> cómo se llama como distribuidor en la venta al
    mercado, cuando el nombre es otro (el mismo emparejamiento que usa el
    filtro para recortar el mercado: S.columna_global).
    """
    m = d.get("mercado_full")
    if m is None or "Distribuidor" not in m.columns:
        return {}
    distrib = S._unicos(m, "Distribuidor")
    equiv = D.emparejar(sorted(clientes), list(distrib), db.equivalencias())
    out: dict[str, str] = {}
    for x in distrib:
        c = equiv.get(x, x)
        if c != x and c in clientes:
            out[c] = f"{out[c]} · {x}" if c in out else x
    return out

