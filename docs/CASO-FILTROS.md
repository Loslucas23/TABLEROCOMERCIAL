# Un caso: «los filtros no funcionan»

El aviso llegó así: *«en el filtro global puedo filtrar por la persona, pero no por su
distribuidora»*. Los nombres de este relato son inventados; el caso es real.

## 1. Reproducir antes de tocar

Se cargaron los datos y se aplicó el filtro directamente contra el motor, sin pasar por la
pantalla:

| Filtro | Retiros | Venta al mercado |
|---|---|---|
| Cliente = «PÉREZ JUAN» (razón social) | recorta | recorta, a su distribuidora |
| Cliente = «DISTRIBUIDORA DEL ESTE» (como todos lo conocen) | **0 filas** | recorta |

El motor recortaba bien. El problema estaba antes: **en la lista para elegir, ese nombre no
existía**.

## 2. La causa de datos

La misma empresa figura con dos nombres: en lo que se le factura, la razón social; en la
venta al mercado, el nombre de fantasía de la distribuidora. El sistema ya sabía que eran
la misma (hay una tabla de equivalencias que se usa para cruzar lo que se le vende con lo
que coloca), pero el filtro ofrecía solo el primer nombre. Quien escribía el segundo veía
«Nada con…».

Pasaba con 16 de los 21 distribuidores.

**Arreglo:** cada cliente se ofrece con su otro nombre al lado (`alias`), y el buscador
encuentra por cualquiera de los dos. De paso, ignora la puntuación palabra por palabra:
escribir `abc` encuentra `A.B.C. S.A.`.

```python
def _alias_clientes(d, clientes):
    """Cliente de retiros -> cómo se llama como distribuidor, cuando el nombre es otro."""
    distrib = S._unicos(d["mercado_full"], "Distribuidor")
    equiv = D.emparejar(sorted(clientes), list(distrib), db.equivalencias())
    out = {}
    for x in distrib:
        c = equiv.get(x, x)
        if c != x and c in clientes:
            out[c] = f"{out[c]} · {x}" if c in out else x
    return out
```

Código: [`filtros_ofrecer.py`](../codigo/api/filtros_ofrecer.py) y [`ElegirFiltro.tsx`](../codigo/web/ElegirFiltro.tsx).

## 3. La segunda falla, que apareció al comprobar

Al verificar el arreglo con un navegador automático (Playwright), elegir un valor no dejaba
el filtro puesto. Midiendo las cajas en el navegador:

```
ef-lista  y=203 h=124 pos=static
ef-pie    y=254 h=49  pos=absolute   <- ¿absolute?
```

El pie de la ventanita (el botón «Listo») usaba una clase CSS, `.ef-pie`, que **ya existía
en otra parte de la hoja de estilos** con `position: absolute`. El pie quedaba flotando
encima de la lista y tapaba los renglones: casi no se podía elegir nada. Se renombró la
clase y la lista volvió a verse entera.

Sin la comprobación en un navegador de verdad, el primer arreglo se habría entregado «listo»
con la ventanita todavía rota.

## 4. Comprobar con los datos reales, no solo con la prueba

- Los **21 distribuidores**, uno por uno: que se encuentren por su nombre y que el filtro
  recorte los dos archivos y deje solo a ese distribuidor.
- Una **prueba de regresión** con un caso mínimo ([`test_filtros_globales.py`](../codigo/pruebas/test_filtros_globales.py)).
- La batería completa y la captura de la pantalla con el filtro puesto.

![El filtro, puesto](capturas/21-filtro-puesto.png)

## Lo que deja

- Un «no funciona» suele ser más de una cosa. La primera causa encontrada no cierra el caso.
- Los nombres de clases CSS cortos y sin prefijo propio chocan tarde o temprano.
- Lo visual se comprueba mirándolo.
