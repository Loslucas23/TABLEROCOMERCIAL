"""
Fragmento de api/servicio.py: el motor de los filtros de arriba.

Un filtro elegido una vez recorta cuatro archivos que no se parecen (lo que
la empresa factura, lo que los distribuidores colocan en el mercado, el
stock y el histórico). Cada archivo nombra las cosas a su manera, así que
el trabajo está en `columna_global`: decidir con qué columna y con qué
valores se aplica cada filtro en cada archivo, o que ahí no se puede.

Es un fragmento para leer, no un módulo suelto: usa `db`, `nucleo`, `datos`
(D) y `analitica` (A) del proyecto.
"""
# En la venta al mercado tres columnas se llaman igual que en retiros pero
# dicen otra cosa: «Canal» (en el Excel, «Canal Grupo»: Tradicionales,
# Kioscos…) no es a quién le factura eQuim (CADENAS, MAYORISTAS…); «Grupo»
# no es el del histórico; y «Cliente» es quien le compra al
# distribuidor. Arriba no se ofrecen (se filtran en Ventas › Al mercado), y
# el Canal y el Grupo de arriba no se le aplican al mercado.
MERCADO_OTRA_COSA = {"Canal", "Grupo", "Cliente"}
NO_EN_MERCADO = {"Canal", "Grupo"}


def _es_mercado(fuente: str) -> bool:
    return fuente.startswith("mercado")


def _cartera(vendedores: set[str], fuente: str) -> set[str]:
    out: set[str] = set()
    for v in vendedores:
        out |= db.clientes_de(v, fuente)
    return out


def columna_global(fuente: str, df: pd.DataFrame, dim: str, vals: set[str]):
    """
    (columna, valores) con que un filtro de arriba recorta este archivo, o
    (None, None) si en este archivo no se puede aplicar (el stock no tiene
    Cliente: queda como está).

    «Cliente» en el mercado es el distribuidor que es ese cliente de eQuim
    (el mismo emparejamiento que el sell-in/sell-out, con las equivalencias);
    «Distribuidor» en retiros y el histórico, el cliente que es ese
    distribuidor. Así un distribuidor elegido arriba muestra lo que eQuim le
    facturó y lo que él colocó. «Cartera», los clientes asignados a esos
    vendedores (en el mercado, sus distribuidores).
    """
    cols = df.columns
    if dim == CARTERA:
        if _es_mercado(fuente):
            return ("Distribuidor", _cartera(vals, "mercado")) if "Distribuidor" in cols else (None, None)
        return ("Cliente", _cartera(vals, "venta")) if "Cliente" in cols else (None, None)
    if _es_mercado(fuente):
        if dim in NO_EN_MERCADO:
            return None, None
        if dim == "Cliente" and "Distribuidor" in cols:
            distrib = _unicos(df, "Distribuidor")
            return "Distribuidor", (vals & set(distrib)) | nucleo._distribuidores_de(tuple(sorted(vals)), distrib)
    else:
        if dim == "Distribuidor" and "Distribuidor" not in cols and "Cliente" in cols:
            return "Cliente", _clientes_de(vals, df)
    if dim in DE_PRODUCTO and "Codigo" in cols and not fuente.startswith(FUENTES_HECHOS):
        m = _maestro(dim)
        if m is not None:
            return "Codigo", _codigos(df, dim, vals, m)
    return (dim, vals) if dim in cols else (None, None)


# El stock y lo que sale de él (lotes, quiebres, quebrados) nombran la
# Categoría y la Familia a su manera (cada uno con sus nombres) y no traen Marca, Presentación ni Grupo
# artículo: «Familia: LAVANDINA TRADICIONAL» dejaba Inventario vacío y
# «Marca: PRIX» no lo recortaba. Un filtro de producto los recorta por el
# Código, con lo que dicen retiros (o el histórico) de ese código; lo que
# nunca se vendió, por su propia columna.
DE_PRODUCTO = {"Marca", "Familia", "MarcaFamilia", "Categoria", "Linea", "GrupoArticulo",
               "Presentacion", "Producto"}
FUENTES_HECHOS = ("venta", "mercado", "historico")
VACIOS = ("nan", "", "None", "<NA>")
_MAESTRO: dict = {}


def _maestro(dim: str) -> pd.Series | None:
    """Código -> `dim` en retiros y, lo que no está ahí, en el histórico (su último año)."""
    base = nucleo.datos()
    tablas = [base.get(k) for k in ("venta_full", "venta", "historico")]
    tablas = [df for df in tablas if isinstance(df, pd.DataFrame) and len(df)
              and {"Codigo", dim} <= set(df.columns)]
    if not tablas:
        return None
    e = _MAESTRO.get(dim)
    # por identidad: con «==» pandas compara las tablas celda por celda
    if e is not None and len(e[0]) == len(tablas) and all(r() is df for r, df in zip(e[0], tablas)):
        return e[1]
    partes = []
    for df in tablas:
        # solo las tres columnas: ordenar el histórico entero copiaba 280 mil filas de todo
        x = df[["Codigo", dim] + (["FY"] if "FY" in df.columns else [])]
        if "FY" in x.columns:
            x = x.sort_values("FY", kind="stable")
        x = x.drop_duplicates("Codigo", keep="last")
        partes.append(pd.Series(x[dim].astype(str).to_numpy(), index=x["Codigo"].astype(str)))
    m = pd.concat(partes)
    # con pandas 3 el vacío sigue vacío al pasarlo a texto: también es «(sin dato)»
    m = m[~m.index.duplicated(keep="first")].fillna(D.SIN_DATO).replace(list(VACIOS), D.SIN_DATO)
    _MAESTRO[dim] = ([weakref.ref(df) for df in tablas], m)
    return m


def _codigos(df: pd.DataFrame, dim: str, vals: set[str], m: pd.Series) -> set[str]:
    """Los códigos de esta tabla que son de esos valores (ver DE_PRODUCTO)."""
    cod = pd.Index(_unicos(df, "Codigo"))
    dice = m.reindex(cod)
    ok = set(cod[dice.isin(vals).to_numpy()])
    nunca = cod[dice.isna().to_numpy()]
    if len(nunca) and dim in df.columns:
        x = df[df["Codigo"].astype(str).isin(nunca)]
        ok |= set(x.loc[_mascara(x, dim, vals, False), "Codigo"].astype(str))
    return ok


# Los valores distintos de una columna, ordenados, por tabla: los piden el
# Cliente en el mercado, el Distribuidor en retiros y el estado de cada
# filtro, varias veces por pedido y sobre las mismas tablas (256 mil filas
# del mercado: 10 ms cada vez). Se olvidan solos cuando la tabla deja de
# existir (weakref): una tabla nueva es otra entrada, nunca valores viejos.
_UNICOS: dict = {}
_UNICOS_CANDADO = threading.Lock()


def _unicos(df: pd.DataFrame, col: str) -> tuple:
    clave = id(df)
    with _UNICOS_CANDADO:
        e = _UNICOS.get(clave)
        if e is None or e[0]() is not df:
            e = (weakref.ref(df, lambda _r, k=clave: _UNICOS.pop(k, None)), {})
            _UNICOS[clave] = e
        hechos = e[1]
    if col not in hechos:
        hechos[col] = tuple(sorted(map(str, pd.unique(df[col].astype(str)))))
    return hechos[col]


_clientes_memo: dict = {}


def _clientes_de(distribuidores: set[str], df: pd.DataFrame) -> set[str]:
    """Los clientes de retiros (o del histórico) que son esos distribuidores del mercado."""
    clientes = _unicos(df, "Cliente")
    manuales = db.equivalencias()
    clave = (tuple(sorted(distribuidores)), hash(clientes), repr(sorted(manuales.items())))
    if clave not in _clientes_memo:
        if len(_clientes_memo) > 200:
            _clientes_memo.clear()
        import datos as D
        equiv = D.emparejar(list(clientes), sorted(distribuidores), manuales)
        hay = set(clientes)
        _clientes_memo[clave] = ({equiv.get(x, x) for x in distribuidores} | distribuidores) & hay
    return _clientes_memo[clave]


def _con_vacios(vals: set[str]) -> set[str]:
    # «(sin dato)» elegido arriba: también lo que llegó vacío
    return vals | set(VACIOS) if D.SIN_DATO in vals else vals


def _mascara(df: pd.DataFrame, col: str, vals: set[str], excluir: bool) -> np.ndarray:
    """Las filas que deja el filtro (True = queda)."""
    ok = np.array(df[col].astype(str).isin(_con_vacios(vals)), dtype=bool)
    if D.SIN_DATO in vals:
        ok |= df[col].isna().to_numpy()  # con pandas 3 el vacío sigue vacío al pasarlo a texto
    return ~ok if excluir else ok


def _recortar(df: pd.DataFrame, col: str, vals: set[str], excluir: bool) -> pd.DataFrame:
    return _quedarse(df, _mascara(df, col, vals, excluir))


def _quedarse(df: pd.DataFrame, ok: np.ndarray | None) -> pd.DataFrame:
    # recortar copia todas las columnas (60 ms el histórico): si no saca
    # ninguna fila, la misma tabla
    return df if ok is None or ok.all() else df[ok]


def resolver_umbral(d: dict, dim: str, umbral: tuple) -> set[str] | None:
    """
    Los valores de la dimensión que cumplen el número, medidos en retiros
    (los meses comparables de los dos años, ya recortados por lo demás).
    None si retiros no tiene esa dimensión: no hay con qué medirlo.
    """
    v = d.get("venta")
    if v is None or dim not in v.columns or not {"CajasAct", "CajasAnt"} <= set(v.columns):
        return None
    g = v.groupby(v[dim].astype(str))[["CajasAct", "CajasAnt"]].sum()
    medida, op, n = umbral
    if medida == "cajas":
        x = g["CajasAct"]
    else:
        g = g[g["CajasAnt"] > 0]           # sin año anterior no hay variación
        x = (g["CajasAct"] / g["CajasAnt"] - 1) * 100
    return set(map(str, x[x > n].index if op == ">" else x[x < n].index))


def aplicar_globales(d: dict, filtros: dict, solo: tuple | None = None) -> dict:
    """
    Recorta todos los hechos por las dimensiones elegidas arriba.

    Cualquier dimensión y varios valores por dimensión, «todo menos» esos o
    por número (los que pasan de tantas cajas, los que cayeron más de
    tanto). Un hecho que no tiene esa columna (el stock no tiene Cliente)
    queda como está: no se puede recortar por algo que no sabe. En el
    mercado, ver columna_global. Los de número van al final, sobre lo ya
    recortado: «Línea PRIX» y «más de 100 cajas» son 100 cajas de PRIX.
    `solo`: recortar únicamente esas tablas (las demás quedan como están);
    para quien solo mira retiros, copiar el histórico y el mercado sobra.
    """
    if not filtros:
        return d
    leidos = {dim: leer_global(v) for dim, v in filtros.items()}
    leidos = {dim: f for dim, f in leidos.items() if f.vals or f.umbral}
    if not leidos:
        return d
    # cada filtro marca qué filas quedan y cada tabla se recorta UNA vez al
    # final: recortar copia todas las columnas, y con tres filtros eran tres
    # copias del histórico. Todo se marca sobre las tablas de entrada; los de
    # número se miden en retiros ya recortado por los demás
    tablas = {k: df for k, df in d.items() if isinstance(df, pd.DataFrame) and len(df)
              and (solo is None or k in solo or k == "venta")}     # retiros mide los de número
    quedan: dict[str, np.ndarray | None] = dict.fromkeys(tablas)

    def marcar(dim: str, vals: set[str], excluir: bool):
        for nombre, df in tablas.items():
            col, vs = columna_global(nombre, df, dim, vals)
            if col is not None:
                ok = _mascara(df, col, vs, excluir)
                quedan[nombre] = ok if quedan[nombre] is None else quedan[nombre] & ok

    for dim, f in leidos.items():
        if not f.umbral:
            marcar(dim, set(f.vals), f.excluir)
    numeros = {dim: f for dim, f in leidos.items() if f.umbral}
    if numeros:
        v = tablas.get("venta")
        medido = {"venta": _quedarse(v, quedan["venta"])} if v is not None else {}
        for dim, f in numeros.items():
            vals = resolver_umbral(medido, dim, f.umbral)
            if vals is not None:
                marcar(dim, vals, False)
    out = dict(d)
    for nombre, df in tablas.items():
        if solo is None or nombre in solo:
            out[nombre] = _quedarse(df, quedan[nombre])
    return out


TOPE_PARECIDOS = 10
FUENTES_GLOBALES = {"venta": "retiros", "mercado": "mercado", "stock": "stock", "historico": "histórico"}


def estado_globales(d: dict, filtros: dict) -> dict:
    """
    Qué hace cada filtro de arriba en cada archivo, para decirlo en pantalla:
    dónde recorta, dónde no se puede aplicar (el stock no tiene Cliente),
    qué valores no tienen con qué recortar un archivo (un cliente que no es
    distribuidor no tiene venta al mercado) y cuáles ya no están en los
    datos (una vista vieja, un producto dado de baja). Y cuántas cajas de
    retiros quedan de cuántas.
    """
    dims = {}
    for dim, valor in filtros.items():
        f = leer_global(valor)
        vals = set(f.vals)
        if f.umbral:
            resto = aplicar_globales(d, {k: v for k, v in filtros.items() if k != dim
                                         and not leer_global(v).umbral}, solo=("venta",))
            vals = resolver_umbral(resto, dim, f.umbral)
        e = {"aplica": [], "no_aplica": [], "sin_equivalente": {}, "no_estan": [], "parecidos": {},
             "cuantos": len(vals) if f.umbral and vals is not None else None}
        dims[dim] = e
        if vals is None:
            e["no_aplica"] = [n for k, n in FUENTES_GLOBALES.items() if isinstance(d.get(k), pd.DataFrame)]
            continue
        hay, directo = set(), False
        for clave, nombre in FUENTES_GLOBALES.items():
            df = d.get(clave)
            if not isinstance(df, pd.DataFrame) or not len(df):
                continue
            col, _ = columna_global(clave, df, dim, vals)
            if col is None:
                e["no_aplica"].append(nombre)
                continue
            e["aplica"].append(nombre)
            presentes = set(_unicos(df, col))
            if col == dim:
                directo = True
                hay |= presentes
            elif not f.umbral and col != "Codigo":
                # lo elegido que en este archivo no tiene con qué recortar
                # (por código, lo que no está en el stock es que no hay)
                faltan = sorted(x for x in vals
                                if not set(columna_global(clave, df, dim, {x})[1] or ()) & presentes)
                if faltan:
                    e["sin_equivalente"][nombre] = faltan
        if directo and not f.umbral:
            e["no_estan"] = sorted(vals - hay - {D.SIN_DATO})
            # lo que ya no está, con el que más se le parece de lo que sí
            # (un producto renombrado, una vista vieja): se ofrece, no se cambia solo
            import parecidos as PA
            otros = sorted(hay - vals) if e["no_estan"] else []
            for x in e["no_estan"][:TOPE_PARECIDOS]:
                if (p := PA.el_mas_parecido(x, otros)):
                    e["parecidos"][x] = p
            # lo que no está en ningún lado se avisa una vez, como «ya no está»
            e["sin_equivalente"] = {k: x for k, x in ((k, [y for y in x if y not in e["no_estan"]])
                                                      for k, x in e["sin_equivalente"].items()) if x}
    v0, v1 = d.get("venta"), aplicar_globales(d, filtros, solo=("venta",)).get("venta")
    cajas = lambda x: float(x["CajasAct"].sum()) if x is not None and "CajasAct" in x.columns else None
    return {"dims": dims, "cajas_total": cajas(v0), "cajas_quedan": cajas(v1)}
