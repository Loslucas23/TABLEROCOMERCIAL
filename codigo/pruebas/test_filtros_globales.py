"""
Los filtros de arriba (api/servicio.py): «todo menos», por número, período,
«(sin dato)», cartera, escritos siempre igual y lo que se avisa en pantalla
(dónde no recortan, qué no tiene equivalente, qué ya no está).
"""
import pandas as pd

import datos as D
from api import servicio as S


def _datos():
    v = pd.DataFrame({"Cliente": ["A", "A", "B", "C"], "Canal": ["CADENAS", "CADENAS", "MAYORISTAS", "VARIOS"],
                      "Linea": ["L1", "L2", "L1", "L1"], "Mes": ["julio", "agosto", "julio", "octubre"],
                      "CajasAct": [100.0, 50.0, 30.0, 5.0], "CajasAnt": [100.0, 100.0, 10.0, 0.0]})
    h = pd.DataFrame({"Cliente": ["A", "B", "C"], "Canal": ["CADENAS", "MAYORISTAS", "VARIOS"],
                      "Mes": ["julio", "agosto", "julio"], "Cajas": [1.0, 2.0, 4.0]})
    st = pd.DataFrame({"Producto": ["p"], "Cajas": [9.0]})
    return {"venta": v, "historico": h, "stock": st}


def test_leer_y_escribir_siempre_igual():
    assert S.normalizar_global("B||A") == S.normalizar_global("A||B") == "A||B"
    assert S.normalizar_global("!B||A") == "!A||B"
    f = S.leer_global("#var<-20")
    assert f.umbral == ("var", "<", -20.0) and not f.vals
    assert S.leer_global("#cualquier cosa") == S.FiltroGlobal()      # mal escrito: no filtra
    assert S.valores_global("!X||Y") == {"X", "Y"}


def test_todo_menos():
    r = S.aplicar_globales(_datos(), {"Canal": "!CADENAS"})
    assert r["venta"]["CajasAct"].sum() == 35 and r["historico"]["Cajas"].sum() == 6
    assert r["stock"]["Cajas"].sum() == 9                  # sin la columna: no se recorta


def test_por_numero_sobre_lo_ya_recortado():
    # «Línea L1» y «más de 20 cajas»: los clientes con más de 20 cajas DE L1
    r = S.aplicar_globales(_datos(), {"Linea": "L1", "Cliente": "#cajas>20"})
    assert set(r["venta"]["Cliente"]) == {"A", "B"} and r["venta"]["CajasAct"].sum() == 130
    assert set(r["historico"]["Cliente"]) == {"A", "B"}
    # cayeron más de 20 %: A (150 contra 200); C no tiene año anterior y no entra
    r = S.aplicar_globales(_datos(), {"Cliente": "#var<-20"})
    assert set(r["venta"]["Cliente"]) == {"A"}


def test_periodo_recorta_los_dos_años():
    r = S.aplicar_globales(_datos(), {"Mes": "julio"})
    assert r["venta"]["CajasAct"].sum() == 130 and r["venta"]["CajasAnt"].sum() == 110
    assert r["historico"]["Cajas"].sum() == 5


def test_sin_dato_incluye_lo_vacio():
    d = {"venta": pd.DataFrame({"Departamento": [D.SIN_DATO, None, "SALTO"], "CajasAct": [1.0, 2.0, 4.0]})}
    r = S.aplicar_globales(d, {"Departamento": D.SIN_DATO})
    assert r["venta"]["CajasAct"].sum() == 3


def test_cartera(monkeypatch):
    monkeypatch.setattr(S.db, "clientes_de", lambda v, f: {"A", "C"} if v == "Ana" else set())
    r = S.aplicar_globales(_datos(), {"Cartera": "Ana"})
    assert set(r["venta"]["Cliente"]) == {"A", "C"}


def test_estado_dice_donde_no_recorta_y_que_no_esta():
    e = S.estado_globales(_datos(), {"Cliente": "A||NADIE", "Canal": "!CADENAS"})
    c = e["dims"]["Cliente"]
    assert c["aplica"] == ["retiros", "histórico"] and c["no_aplica"] == ["stock"]
    assert c["no_estan"] == ["NADIE"]
    assert e["cajas_total"] == 185 and e["cajas_quedan"] == 0     # A es de CADENAS: no queda nada
    n = S.estado_globales(_datos(), {"Cliente": "#cajas>20"})["dims"]["Cliente"]
    assert n["cuantos"] == 2


def test_describir():
    assert S.describir_global("Canal", "!CADENAS") == "Canal: todo menos CADENAS"
    assert S.describir_global("Mes", "agosto||julio") == "Período: julio, agosto"
    assert S.describir_global("TipoVenta", "VENTA") == "Tipo de venta: VENTA"
    assert S.describir_global("Linea", "!LIMPIEZA") == "Línea de negocio: todo menos LIMPIEZA"
    assert S.describir_global("Cliente", "#cajas>100") == "Cliente: más de 100 cajas en retiros"
    assert S.describir_global("Producto", "#var<-20") == "Producto: cayeron más de 20 % en retiros"


def test_solo_recorta_las_pedidas_y_mide_igual():
    d = _datos()
    r = S.aplicar_globales(d, {"Linea": "L1", "Cliente": "#cajas>20"}, solo=("historico",))
    assert r["venta"] is d["venta"]                         # no pedida: la misma tabla
    assert set(r["historico"]["Cliente"]) == {"A", "B"}     # medido en retiros igual
    assert S.aplicar_globales(d, {"Canal": "!NADA"})["venta"] is d["venta"]   # no saca filas: sin copiar


def test_lo_que_ya_no_esta_trae_el_parecido():
    d = _datos()
    d["venta"].loc[3, "Cliente"] = "PAYSANDÚ"
    e = S.estado_globales(d, {"Cliente": "A||PAYSANDU"})["dims"]["Cliente"]
    assert e["no_estan"] == ["PAYSANDU"] and e["parecidos"] == {"PAYSANDU": "PAYSANDÚ"}
    e = S.estado_globales(d, {"Cliente": "MARTE"})["dims"]["Cliente"]
    assert e["parecidos"] == {}


def test_datos_de_guarda_lo_recortado(monkeypatch):
    import nucleo
    d = _datos()
    monkeypatch.setattr(nucleo, "datos", lambda: d)
    monkeypatch.setattr(nucleo, "firma", lambda: "f1")
    import api.seguridad as seg
    monkeypatch.setattr(seg, "alcance", lambda u: (None, None))
    u = {"usuario": "x", "rol": "admin"}
    S.poner_globales({"Canal": "CADENAS"})
    try:
        a, b = S.datos_de(u), S.datos_de(u)
        assert a["venta"] is b["venta"] and a is not b       # la misma cuenta, otro diccionario
        assert a["venta"]["CajasAct"].sum() == 150
        S.poner_globales({"Canal": "VARIOS"})
        assert S.datos_de(u)["venta"]["CajasAct"].sum() == 5
        monkeypatch.setattr(nucleo, "firma", lambda: "f2")     # datos nuevos: no sirve lo guardado
        S.poner_globales({"Canal": "CADENAS"})
        assert S.datos_de(u)["venta"] is not a["venta"]
        S.poner_globales({})
        assert S.datos_de(u) is d                             # sin nada que recortar, lo de siempre
    finally:
        S.poner_globales({})


def _recortado(monkeypatch, globales, d=None, limpiar=True):
    import nucleo
    import api.seguridad as seg
    d = d or _datos()
    monkeypatch.setattr(nucleo, "datos", lambda: d)
    monkeypatch.setattr(nucleo, "firma", lambda: "f-perezoso")
    monkeypatch.setattr(seg, "alcance", lambda u: (None, None))
    if limpiar:
        S._RECORTADOS.clear()
    S.poner_globales(globales)
    try:
        return d, S.datos_de({"usuario": "x", "rol": "admin"})
    finally:
        S.poner_globales({})


def test_cada_tabla_se_recorta_recien_cuando_se_pide(monkeypatch):
    d, r = _recortado(monkeypatch, {"Canal": "CADENAS"})
    assert r.get("venta")["CajasAct"].sum() == 150
    rec = next(iter(S._RECORTADOS.values()))
    assert set(rec.hechas) == {"venta"}                    # el histórico no se tocó
    assert r["historico"]["Cajas"].sum() == 1 and "historico" in rec.hechas
    assert r["stock"] is d["stock"]                        # sin la columna: la misma tabla


def test_lo_recortado_se_porta_como_un_diccionario(monkeypatch):
    _, r = _recortado(monkeypatch, {"Canal": "CADENAS"})
    assert "venta" in r and "nada" not in r and r.get("nada", 7) == 7 and bool(r)
    assert set(r) == {"venta", "historico", "stock"} and len(r) == 3
    todo = {**r}
    assert todo["venta"]["CajasAct"].sum() == 150 and dict(r).keys() == todo.keys()
    r["extra"] = 1
    del r["stock"]
    assert "stock" not in r and r.get("stock") is None and r["extra"] == 1
    _, otro = _recortado(monkeypatch, {"Canal": "CADENAS"})
    assert "stock" in otro and "extra" not in otro         # lo escrito no pasa a otro pedido


def test_por_numero_perezoso_mide_en_retiros(monkeypatch):
    _, r = _recortado(monkeypatch, {"Linea": "L1", "Cliente": "#cajas>20"})
    assert set(r["historico"]["Cliente"]) == {"A", "B"}    # pedido antes que retiros
    assert r["venta"]["CajasAct"].sum() == 130


def test_comparar_da_lo_mismo_que_la_cuenta_a_mano(monkeypatch):
    from api import personal as P
    d = _datos()
    monkeypatch.setattr(S, "datos_sin_globales", lambda u: d)
    monkeypatch.setattr(S, "memo", lambda u, n, a, f: f())
    r = P.filtros_globales_comparar("Canal", "CADENAS", "MAYORISTAS||VARIOS", {"usuario": "x", "rol": "admin"})
    a, b = r["lados"]
    assert (a["cajas_act"], a["cajas_ant"], a["clientes"]) == (150, 200, 1)
    assert (b["cajas_act"], b["cajas_ant"], b["clientes"], b["var"]) == (35, 10, 2, 250.0)
    assert b["texto"] == "Canal: MAYORISTAS, VARIOS"


def test_compartidos_los_ve_el_equipo_y_nadie_mas():
    import db
    db.guardar_usuario("cmp_jefe", "Jefe", "gerencia")
    db.guardar_usuario("cmp_vend", "Vend", "comercial", jefe="cmp_jefe")
    db.guardar_usuario("cmp_otro", "Otro", "comercial")
    db.filtros_compartir("cmp_jefe", "Norte", {"Departamento": "SALTO"})
    db.filtros_compartir("cmp_jefe", "Norte", {"Departamento": "ARTIGAS"})      # mismo nombre: reemplaza
    ve = db.filtros_compartidos_para("cmp_vend")
    assert [(x["nombre"], x["g"], x["mio"]) for x in ve if x["de"] == "cmp_jefe"] == [
        ("Norte", {"Departamento": "ARTIGAS"}, False)]
    assert not [x for x in db.filtros_compartidos_para("cmp_otro") if x["de"] == "cmp_jefe"]
    fid = next(x["id"] for x in ve if x["de"] == "cmp_jefe")
    assert not db.filtros_compartido_borrar(fid, "cmp_vend")                  # no es suyo
    assert db.filtros_compartido_borrar(fid, "cmp_jefe")


def test_con_datos_nuevos_se_suelta_lo_recortado_viejo(monkeypatch):
    _recortado(monkeypatch, {"Canal": "CADENAS"})
    viejo = next(iter(S._RECORTADOS.values()))
    assert len(S._RECORTADOS) == 1
    _, r = _recortado(monkeypatch, {"Canal": "VARIOS"}, d=_datos(), limpiar=False)     # otra base
    assert r["venta"]["CajasAct"].sum() == 5
    assert len(S._RECORTADOS) == 1 and viejo not in S._RECORTADOS.values()


def _con_stock():
    # el stock nombra la Familia a su manera y no trae Marca; el 9 nunca se vendió
    v = pd.DataFrame({"Codigo": ["1", "2", "3"], "Marca": ["PRIX", "PRIX", "ARONELA"],
                      "Familia": ["LAVANDINA", "JABON", "LAVANDINA"], "Cliente": ["A", "B", "A"],
                      "CajasAct": [10.0, 20.0, 30.0], "CajasAnt": [5.0, 5.0, 5.0]})
    st = pd.DataFrame({"Codigo": ["1", "2", "3", "9"], "Familia": ["PRIX LAVANDINAS", "PRIX JABONES",
                                                                   "ARONELA LAVANDINAS", "LAVANDINA"],
                       "Cajas": [1.0, 2.0, 3.0, 4.0]})
    q = pd.DataFrame({"Codigo": ["2", "9"], "Veces": [1, 2]})
    return {"venta": v, "stock": st, "quiebres": q}


def test_el_stock_se_recorta_por_codigo(monkeypatch):
    d = _con_stock()
    monkeypatch.setattr(S.nucleo, "datos", lambda: d)
    S._MAESTRO.clear()
    r = S.aplicar_globales(d, {"Marca": "PRIX"})
    assert list(r["stock"]["Codigo"]) == ["1", "2"] and list(r["quiebres"]["Codigo"]) == ["2"]
    # la Familia como la dice retiros; lo que nunca se vendió, por su propia columna
    r = S.aplicar_globales(d, {"Familia": "LAVANDINA"})
    assert list(r["stock"]["Codigo"]) == ["1", "3", "9"]
    r = S.aplicar_globales(d, {"Marca": "!PRIX"})
    assert list(r["stock"]["Codigo"]) == ["3", "9"]
    # por número: ninguna marca pasa de 35 cajas (PRIX 30, ARONELA 30)
    assert list(S.aplicar_globales(d, {"Marca": "#cajas>35"})["stock"]["Codigo"]) == []
    # un filtro de cliente no toca el stock
    assert S.aplicar_globales(d, {"Cliente": "A"})["stock"] is d["stock"]
    e = S.estado_globales(d, {"Marca": "PRIX"})["dims"]["Marca"]
    assert "stock" in e["aplica"] and not e["no_aplica"] and not e["sin_equivalente"]


def test_arriba_no_se_ofrece_la_familia_del_stock(monkeypatch):
    from api import personal as P
    d = _con_stock()
    d["venta_full"] = d.pop("venta")
    dims = {x["dim"]: x for x in P._ofrecer(d)}
    assert {v["v"] for v in dims["Familia"]["valores"]} == {"LAVANDINA", "JABON"}
    assert "stock" in dims["Familia"]["donde"] and "stock" in dims["Marca"]["donde"]


def test_con_datos_nuevos_el_maestro_se_rehace(monkeypatch):
    d = _con_stock()
    monkeypatch.setattr(S.nucleo, "datos", lambda: d)
    S._MAESTRO.clear()
    assert list(S.aplicar_globales(d, {"Marca": "PRIX"})["stock"]["Codigo"]) == ["1", "2"]
    # otra carga: el 3 pasó a ser PRIX (tablas nuevas, otro tamaño)
    d["venta"] = pd.DataFrame({"Codigo": ["1", "3"], "Marca": ["ARONELA", "PRIX"],
                               "CajasAct": [1.0, 1.0], "CajasAnt": [1.0, 1.0]})
    assert list(S.aplicar_globales(d, {"Marca": "PRIX"})["stock"]["Codigo"]) == ["3"]


def test_un_trimestre_entero_se_lee_como_en_la_barra():
    assert S.describir_global("Mes", "agosto||julio||setiembre") == "Período: 1er trimestre"
    assert S.describir_global("Mes", "!enero||febrero||marzo") == "Período: todo menos el 3er trimestre"


def test_comparar_cuenta_clientes_en_neto_y_no_reparte_el_mercado(monkeypatch):
    from api import personal as P
    d = _datos()
    # B devolvió más de lo que compró: no es un cliente que compró
    d["venta"] = pd.concat([d["venta"], pd.DataFrame({"Cliente": ["B"], "Canal": ["MAYORISTAS"], "Linea": ["L1"],
                                                      "Mes": ["julio"], "CajasAct": [-40.0], "CajasAnt": [0.0]})])
    d["mercado"] = pd.DataFrame({"Distribuidor": ["X"], "Canal": ["Tradicionales"], "CajasAct": [7.0], "CajasAnt": [1.0]})
    monkeypatch.setattr(S, "datos_sin_globales", lambda u: d)
    monkeypatch.setattr(S, "memo", lambda u, n, a, f: f())
    r = P.filtros_globales_comparar("Canal", "MAYORISTAS", "VARIOS", {"usuario": "x", "rol": "admin"})
    a, b = r["lados"]
    assert a["clientes"] == 0 and b["clientes"] == 1
    # el Canal de arriba no es el del mercado: no se muestra de cada lado
    assert r["mercado_no_separa"] and a["mercado_act"] is None and b["mercado_act"] is None


def test_lo_de_abajo_de_ventas_usa_los_filtros_de_la_tabla():
    from api import rutas4 as R4
    v = _datos()["venta"]
    r = R4._con_filtros(v, '{"Linea": ["L1"], "Canal": ["CADENAS", "VARIOS"]}')
    assert r["CajasAct"].sum() == 105                       # A (L1, CADENAS) + C (VARIOS)
    assert R4._con_filtros(v, "") is v
    assert R4._con_filtros(v, '{"NoEsta": ["x"]}') is v      # una columna que no tiene: no recorta


def test_inventario_no_se_cae_si_el_filtro_deja_el_stock_vacio(monkeypatch):
    # quedan quebrados que nunca se vendieron (sin línea) y el maestro no tiene nada que darles
    import api.rutas2 as R2
    cob = pd.DataFrame({"Codigo": ["9"], "Linea": pd.array([None], dtype="str"), "Categoria": pd.array([None], dtype="str"),
                        "Cajas": [0.0], "VentaDia": [0.0], "Cobertura": [float("nan")]})
    monkeypatch.setattr(S, "datos_de", lambda u: {"stock": pd.DataFrame(columns=["Codigo", "Cajas", "Estado"]),
                                                 "quebrados": pd.DataFrame({"Codigo": ["9"], "Producto": ["X"], "DiasQuebrado": [3]})})
    monkeypatch.setattr(S, "cobertura_de", lambda u: (cob, None))
    monkeypatch.setattr(R2, "_maestro_por_codigo", lambda d: pd.DataFrame({"Codigo": [], "Linea": [], "Categoria": []}))
    monkeypatch.setattr(R2, "_plazos", lambda: (10, 5))
    monkeypatch.setattr(R2, "_codigos_stock", lambda d: set())
    r = R2.inventario_resumen(usuario={"usuario": "x", "rol": "admin"})
    assert r["categorias"][0]["linea"] == "(sin dato)" and r["estado"]["sin_stock"] == 1


def test_los_quebrados_tienen_linea_y_categoria(monkeypatch):
    # su hoja no trae Línea ni Categoría: salen del maestro por código
    import api.rutas2 as R2
    base = {"venta": pd.DataFrame({"Codigo": ["7", "8"], "Linea": ["MASIVOS", "IND"], "Categoria": ["LAVADO", "PISCINAS"],
                                   "CajasAct": [1.0, 1.0]})}
    monkeypatch.setattr(R2.nucleo, "datos", lambda: base)
    cob = pd.DataFrame({"Codigo": ["7", "8", "9"], "Linea": [None, "IND", None], "Categoria": [None, None, None]})
    r = R2._con_linea(cob)
    assert list(r["Linea"])[:2] == ["MASIVOS", "IND"] and pd.isna(r["Linea"].iloc[2])          # el 9 nunca se vendió
    assert list(r["Categoria"])[:2] == ["LAVADO", "PISCINAS"]


def test_el_cliente_se_encuentra_por_su_nombre_de_distribuidor(monkeypatch):
    # «DISTRIBUIDORA DEL ESTE» (mercado) es «PEREZ JUAN» en retiros: arriba
    # se ofrece el de retiros con el otro nombre al lado, y recorta los dos archivos
    v = pd.DataFrame({"Cliente": ["PEREZ JUAN", "OTRO"], "Canal": ["D", "D"],
                      "CajasAct": [10.0, 5.0], "CajasAnt": [1.0, 1.0]})
    m = pd.DataFrame({"Distribuidor": ["DISTRIBUIDORA DEL ESTE", "OTRA"], "Cliente": ["ALMACEN", "KIOSCO"],
                      "CajasAct": [3.0, 4.0], "CajasAnt": [1.0, 1.0]})
    d = {"venta": v, "venta_full": v, "mercado": m, "mercado_full": m}
    import db
    from api import personal as P
    monkeypatch.setattr(db, "equivalencias", lambda *a: {"DISTRIBUIDORA DEL ESTE": "PEREZ JUAN"})
    cli = next(x for x in P._ofrecer(d) if x["dim"] == "Cliente")
    assert {x["v"]: x.get("alias") for x in cli["valores"]} == {"PEREZ JUAN": "DISTRIBUIDORA DEL ESTE", "OTRO": None}
    assert "mercado" in cli["donde"]
    r = S.aplicar_globales(d, {"Cliente": "PEREZ JUAN"})
    assert list(r["venta"]["Cliente"]) == ["PEREZ JUAN"]
    assert list(r["mercado"]["Distribuidor"]) == ["DISTRIBUIDORA DEL ESTE"]
