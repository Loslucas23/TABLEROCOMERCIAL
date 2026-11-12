/**
 * Elegir los valores de un filtro: la misma ventanita en toda la intranet
 * (los filtros de arriba, los de la tabla de Ventas).
 *
 * Pensada para quien no quiere pensar en cómo se filtra:
 *
 * - se abre debajo del botón que se tocó, ya con el cursor en el buscador:
 *   se escriben unas letras y queda lo que coincide (sin tildes ni mayúsculas);
 * - un clic en el renglón lo marca; «solo este» lo deja a él solo y cierra:
 *   para el caso de siempre (un vendedor, un cliente) son dos clics;
 * - «Listo» aplica. Un clic afuera también: lo marcado no se pierde.
 *   Escape cierra sin cambiar nada;
 * - Enter con un solo resultado a la vista lo elige.
 *
 * Los renglones son altos y la letra grande a propósito.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Search, X } from "lucide-react";
import { Esqueleto } from "./Esqueleto";

export interface OpcionFiltro {
  v: string;
  /** cuánto pesa (cajas): se muestra a la derecha, y con 0 va al final en gris */
  n?: number;
  /** el otro nombre con que se lo conoce (el del distribuidor): también se busca por él */
  alias?: string;
}

const sinAcento = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
// sin puntos ni espacios: «abc» encuentra «A.B.C. S.A.»
const pelado = (s: string) => s.replace(/[^a-z0-9]/g, "");
/** El texto por el que se busca una opción: su nombre y su alias. */
export const textoDe = (o: { v: string; alias?: string }) => sinAcento(o.alias ? `${o.v} ${o.alias}` : o.v);
/** ¿Lo escrito (ya sin tildes) está en ese texto? También sin puntuación. */
export function coincide(texto: string, t: string) {
  if (texto.includes(t)) return true;
  // palabra por palabra: juntando todo, «roca» aparecía en «…matadeRO CArrasco»
  const tp = pelado(t);
  return tp.length >= 3 && !/\s/.test(t) && texto.split(/\s+/).some((p) => pelado(p).includes(tp));
}
const NUM = new Intl.NumberFormat("es-UY", { maximumFractionDigits: 0 });
const TOPE = 300;   // más que esto no se lee: se pide escribir un poco más
const ANCHO = 360;

export function ElegirFiltro({ titulo, opciones, elegidos, alCambiar, cerrar, ancla, unidad = "cajas", nota, enOrden = false }: {
  /** «Vendedor», «Línea de negocio»: como se lee, no la columna por dentro */
  titulo: string;
  /** null = todavía cargando */
  opciones: OpcionFiltro[] | null;
  elegidos: string[];
  /** Se llama una sola vez, al cerrar con cambios. Vacío = sin filtro. */
  alCambiar: (vals: string[]) => void;
  cerrar: () => void;
  /** El botón que la abrió: se acomoda debajo. */
  ancla: HTMLElement | null;
  unidad?: string;
  nota?: string;
  /** Respetar el orden en que llegan (los meses): si no, lo marcado va arriba. */
  enOrden?: boolean;
}) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string[]>(elegidos);
  const caja = useRef<HTMLDivElement>(null);
  // lo último marcado, para aplicar al cerrar con un clic afuera
  const selRef = useRef(sel);
  selRef.current = sel;
  const cerrado = useRef(false);

  function terminar(vals: string[] | null) {
    if (cerrado.current) return;
    cerrado.current = true;
    if (vals && JSON.stringify([...vals].sort()) !== JSON.stringify([...elegidos].sort())) alCambiar(vals);
    cerrar();
  }
  const terminarRef = useRef(terminar);
  terminarRef.current = terminar;

  useEffect(() => {
    const fuera = (e: MouseEvent) => {
      const t = e.target as Node;
      if (caja.current?.contains(t) || ancla?.contains(t)) return;
      terminarRef.current(selRef.current);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); terminarRef.current(null); }
    };
    // en el próximo ciclo: si no, el mismo clic que la abrió la cierra
    const id = setTimeout(() => document.addEventListener("mousedown", fuera));
    document.addEventListener("keydown", tecla, true);
    return () => {
      clearTimeout(id);
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", tecla, true);
    };
  }, [ancla]);

  // debajo del botón, sin salirse de la pantalla
  const [lugar, setLugar] = useState<{ left: number; top: number; alto: number } | null>(null);
  useLayoutEffect(() => {
    const r = ancla?.getBoundingClientRect();
    const izq = Math.max(8, Math.min(r ? r.left : 80, window.innerWidth - ANCHO - 8));
    const arriba = r ? r.bottom + 6 : 80;
    const alto = Math.max(260, Math.min(520, window.innerHeight - arriba - 12));
    // si abajo no entra, se sube lo necesario
    setLugar({ left: izq, top: Math.max(8, Math.min(arriba, window.innerHeight - alto - 8)), alto });
  }, [ancla]);

  // lo que estaba marcado al abrir va arriba (no se reordena en cada clic: marea)
  const lista = useMemo(() => {
    if (!opciones) return [];
    const t = sinAcento(q);
    const conocidos = new Set(opciones.map((o) => o.v));
    // lo ya elegido se sigue viendo aunque hoy no esté en los datos: si no, no se puede sacar
    const todas: OpcionFiltro[] = [...opciones, ...elegidos.filter((v) => !conocidos.has(v)).map((v) => ({ v, n: 0 }))];
    const base = t ? todas.filter((o) => coincide(textoDe(o), t)) : todas;
    if (t) {
      // primero los que empiezan así (por el nombre o por el alias)
      const empieza = (o: OpcionFiltro) => sinAcento(o.v).startsWith(t) || (!!o.alias && sinAcento(o.alias).startsWith(t));
      return [...base.filter(empieza), ...base.filter((o) => !empieza(o))];
    }
    if (enOrden) return base;
    const rango = (o: OpcionFiltro) => (elegidos.includes(o.v) ? 0 : o.n !== undefined && o.n <= 0 ? 2 : 1);
    return base.map((o, i) => ({ o, i })).sort((a, b) => rango(a.o) - rango(b.o) || a.i - b.i).map((x) => x.o);
  }, [opciones, q, elegidos, enOrden]);
  const visibles = lista.slice(0, TOPE);
  const hayPesos = visibles.some((o) => o.n !== undefined);

  function alternar(v: string) {
    setSel((s) => (s.includes(v) ? s.filter((x) => x !== v) : [...s, v]));
  }
  const todosMarcados = visibles.length > 0 && visibles.every((o) => sel.includes(o.v));

  if (!lugar) return null;
  return createPortal(
    <div className="ef" ref={caja} role="dialog" aria-label={`Filtrar por ${titulo}`}
         style={{ left: lugar.left, top: lugar.top, maxHeight: lugar.alto, width: ANCHO }}>
      <div className="ef-cab">
        <b>{titulo}</b>
        <button className="ef-x" onClick={() => terminar(null)} aria-label="Cerrar sin cambiar" title="Cerrar sin cambiar (Esc)"><X /></button>
      </div>
      <label className="ef-buscar">
        <Search aria-hidden="true" />
        <input autoFocus value={q} placeholder="Escribí para buscar…" aria-label={`Buscar en ${titulo}`}
               onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => {
                 if (e.key !== "Enter") return;
                 e.preventDefault();
                 // un solo resultado: es ese
                 if (q.trim() && visibles.length === 1) terminar([...new Set([...sel, visibles[0].v])]);
                 else terminar(sel);
               }} />
        {q && <button className="ef-x" onClick={() => setQ("")} aria-label="Borrar lo escrito"><X /></button>}
      </label>
      {nota && <p className="ef-nota">{nota}</p>}
      <div className="ef-lista">
        {!opciones && <Esqueleto forma="linea" texto="Cargando…" />}
        {opciones && q.trim() && visibles.length > 1 && (
          <label className="ef-op ef-todos">
            <input type="checkbox" checked={todosMarcados}
                   onChange={() => setSel((s) => (todosMarcados
                     ? s.filter((v) => !visibles.some((o) => o.v === v))
                     : [...new Set([...s, ...visibles.map((o) => o.v)])]))} />
            <span className="ef-nombre">Marcar los {visibles.length} que coinciden</span>
          </label>
        )}
        {visibles.map((o) => {
          const on = sel.includes(o.v);
          return (
            <div key={o.v} className={`ef-op ${on ? "on" : ""} ${o.n !== undefined && o.n <= 0 ? "ef-cero" : ""}`}>
              <label title={o.alias ? `${o.v} · ${o.alias}` : o.v}>
                <input type="checkbox" checked={on} onChange={() => alternar(o.v)} />
                <span className="ef-nombre">{o.v}{o.alias && <i className="ef-alias"> · {o.alias}</i>}</span>
                {hayPesos && <small>{o.n ? NUM.format(o.n) : ""}</small>}
              </label>
              <button className="ef-solo" onClick={() => terminar([o.v])}
                      title={`Dejar solo ${o.v} y cerrar`}>solo este</button>
            </div>
          );
        })}
        {opciones && !visibles.length && <p className="ef-nota">Nada con «{q}».</p>}
        {lista.length > TOPE && <p className="ef-nota">Hay {NUM.format(lista.length)}: escribí arriba para achicar.</p>}
      </div>
      <div className="ef-abajo">
        {hayPesos && <span className="ef-unidad">{unidad}</span>}
        {(sel.length > 0 || elegidos.length > 0) && (
          <button className="chiquito" onClick={() => terminar([])}
                  title={`Sacar el filtro de ${titulo}: vuelve a verse todo`}>Ver todo</button>
        )}
        <button className="boton principal" onClick={() => terminar(sel)}>
          Listo{sel.length ? ` (${sel.length})` : ""}</button>
      </div>
    </div>,
    document.body);
}
