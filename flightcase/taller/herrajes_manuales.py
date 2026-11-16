"""Herrajes colocados a mano sobre las caras del case.

Además de los herrajes que ubican las reglas del taller (manijas, cierres, ruedas...), el
proyecto puede tener una lista ``herrajes_manuales`` con piezas puestas a mano en
cualquier cara. Cada fila es::

    [ref, cara, x, y, giro, espejo, ancho, alto, archivo, modo]

- ``ref``: referencia del catálogo (manija, cierre, bisagra, tope, pie, rueda, plato o
  extra), ``"logo"`` para una placa de logo hecha con un dibujo vectorial, o cualquier
  otro texto para una pieza propia (va a la lista con ese nombre).
- ``cara``: ``"frente"``, ``"trasera"``, ``"izq"``, ``"der"``, ``"arriba"`` o ``"abajo"``
  (las caras del case antes de acostarlo o pararlo; ver :func:`caras`).
- ``x``, ``y``: centro del herraje en mm, medido sobre la cara vista desde afuera y
  derecha (con el case parado como queda en uso): desde el borde izquierdo y desde
  el borde de abajo.
- ``giro``: 0, 90, 180 o 270 grados (antihorario, en la misma vista).
- ``espejo``: 1 da vuelta la pieza (sólo cambia algo en los logos).
- ``ancho``, ``alto``: medida de la pieza cuando no la da el catálogo (logos, extras y
  piezas propias). En un logo, alto = 0 la saca de la proporción del dibujo.
- ``archivo``: el .svg o .dxf del logo (ruta absoluta o relativa al .scad).
- ``modo`` (logos): ``"placa"`` (placa remachada con el logo) o ``"grabado"`` (se graba
  sobre la madera: el dibujo va al DXF en la capa GRABADO).

Los cierres y bisagras se centran solos sobre la junta de cierre más cercana (la ``y``
se ignora) y se marcan en el cuerpo y en la tapa, igual que los automáticos. Todo lo
demás sale como calado (manijas embutidas, platos), agujeros (ruedas) o marca de
superficie en el panel que queda debajo del centro, y pasa a la lista de materiales,
los DXF, la vista 3D, planos.pdf y el instructivo.

OpenSCAD no conoce ``herrajes_manuales``: lo guarda en el .scad y lo ignora.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .modelo import CatalogoTaller, fmt, s

CARAS = ("frente", "trasera", "izq", "der", "arriba", "abajo")
OPUESTA = {"frente": "trasera", "trasera": "frente", "izq": "der", "der": "izq", "arriba": "abajo", "abajo": "arriba"}
SUFIJO = " a mano"          # tipo de los calados y marcas de los herrajes manuales
CATEGORIAS = ("manija", "cierre", "bisagra", "tope", "pie", "rueda", "rueda_otra", "plato", "escuadra",
              "extra", "esquinero", "rack")
_REMACHES_DEF = {"manija": 6, "cierre": 6, "bisagra": 6, "tope": 8, "plato": 6}
_MEDIDA_DEF = {"cierre": (50, 70), "bisagra": (60, 60), "tope": (60, 30), "manija": (120, 35),
               "escuadra": (40, 40), "esquinero": (50, 50)}
MAX_PUNTOS_LOGO = 1500

Vec = Tuple[float, float, float]
Rect = Tuple[float, float, float, float]    # x0, y0, x1, y1


def _resta(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _punto(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _rect(x0: float, y0: float, x1: float, y1: float) -> Rect:
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _solapa(a: Rect, b: Rect, holgura: float = 0.0) -> bool:
    return a[0] < b[2] + holgura and b[0] < a[2] + holgura and a[1] < b[3] + holgura and b[1] < a[3] + holgura


def _dentro(a: Rect, b: Rect, tol: float = 0.01) -> bool:
    return a[0] >= b[0] - tol and a[1] >= b[1] - tol and a[2] <= b[2] + tol and a[3] <= b[3] + tol


# ---------------------------------------------------------------------------
# Caras del case
# ---------------------------------------------------------------------------

@dataclass
class PanelCara:
    id: str
    nombre: str
    grupo: str
    ancho: float
    alto: float
    o: Vec
    u: Vec
    v: Vec


@dataclass
class Cara:
    """Una cara del case vista desde afuera, con el case parado como se usa.

    Las coordenadas de "vista" (x desde la izquierda, y desde abajo) son las que ve y
    escribe el usuario; las de "cara" (fu, fv) siguen los ejes del panel (u, v) en el
    case sin acostar. `giro` es el giro de la vista (cuartos de vuelta antihorarios)."""
    id: str
    nombre: str
    W: float
    H: float
    F0: Vec
    U: Vec
    V: Vec
    giro: int
    paneles: List[PanelCara] = field(default_factory=list)
    juntas: List[Dict[str, Any]] = field(default_factory=list)      # en coordenadas de cara
    aluminio: List[Rect] = field(default_factory=list)              # en coordenadas de cara

    @property
    def ancho(self) -> float:
        return self.H if self.giro % 2 else self.W

    @property
    def alto(self) -> float:
        return self.W if self.giro % 2 else self.H

    # vista <-> cara
    def a_cara(self, x: float, y: float) -> Tuple[float, float]:
        r, W, H = self.giro % 4, self.W, self.H
        return ((x, y), (y, H - x), (W - x, H - y), (W - y, x))[r]

    def a_vista(self, fu: float, fv: float) -> Tuple[float, float]:
        r, W, H = self.giro % 4, self.W, self.H
        return ((fu, fv), (H - fv, fu), (W - fu, H - fv), (fv, W - fu))[r]

    def rect_a_vista(self, r: Rect) -> Rect:
        a, b = self.a_vista(r[0], r[1]), self.a_vista(r[2], r[3])
        return _rect(a[0], a[1], b[0], b[1])

    def rect_a_cara(self, r: Rect) -> Rect:
        a, b = self.a_cara(r[0], r[1]), self.a_cara(r[2], r[3])
        return _rect(a[0], a[1], b[0], b[1])

    # cara <-> panel
    def _mundo(self, fu: float, fv: float) -> Vec:
        F, U, V = self.F0, self.U, self.V
        return (F[0] + U[0] * fu + V[0] * fv, F[1] + U[1] * fu + V[1] * fv, F[2] + U[2] * fu + V[2] * fv)

    def panel_a_cara(self, p: PanelCara, px: float, py: float) -> Tuple[float, float]:
        q = tuple(p.o[i] + p.u[i] * px + p.v[i] * py for i in range(3))
        d = _resta(q, self.F0)
        return _punto(d, self.U), _punto(d, self.V)

    def cara_a_panel(self, p: PanelCara, fu: float, fv: float) -> Tuple[float, float]:
        d = _resta(self._mundo(fu, fv), p.o)
        return _punto(d, p.u), _punto(d, p.v)

    def rect_panel(self, p: PanelCara) -> Rect:
        a = self.panel_a_cara(p, 0, 0)
        b = self.panel_a_cara(p, p.ancho, p.alto)
        return _rect(a[0], a[1], b[0], b[1])

    def panel(self, pid: str) -> Optional[PanelCara]:
        return next((p for p in self.paneles if p.id == pid), None)

    def panel_en(self, fu: float, fv: float) -> Optional[PanelCara]:
        for p in self.paneles:
            r = self.rect_panel(p)
            if r[0] - 0.01 <= fu <= r[2] + 0.01 and r[1] - 0.01 <= fv <= r[3] + 0.01:
                return p
        return None

    def gira_panel(self, p: PanelCara) -> bool:
        """True si el ancho del panel corre a lo alto de la cara (no pasa con los paneles del case)."""
        return abs(_punto(p.u, self.U)) < 0.5


def _cuarto(ejes: Sequence[Vec], vertical: bool) -> int:
    """Giro de la vista para que la cara se vea derecha: arriba del dibujo = arriba del mundo
    (o el fondo del case, si la cara queda acostada)."""
    U, V = ejes
    arriba = [V, U, tuple(-c for c in V), tuple(-c for c in U)]
    ref = (0.0, 0.0, 1.0) if vertical else (0.0, 1.0, 0.0)
    return max(range(4), key=lambda r: _punto(arriba[r], ref))


def caras_desde(geo: Dict[str, Any], paneles: Sequence[Any], X: float, Y: float, Z: float) -> List[Cara]:
    """Las seis caras del case con sus paneles, juntas de cierre y zonas de aluminio."""
    hz, fr = geo["horizontal"], geo["frontal"]
    if hz:
        girar = lambda n: (-n[2], n[1], n[0])
    elif fr:
        girar = lambda n: (n[0], -n[2], n[1])
    else:
        girar = lambda n: n
    por_id = {p.id: p for p in paneles}
    defs = {
        "frente": ((0, 0, 0), (1, 0, 0), (0, 0, 1), X, Z, (0, 1, 0)),
        "trasera": ((X, Y, 0), (-1, 0, 0), (0, 0, 1), X, Z, (0, -1, 0)),
        "izq": ((0, Y, 0), (0, -1, 0), (0, 0, 1), Y, Z, (1, 0, 0)),
        "der": ((X, 0, 0), (0, 1, 0), (0, 0, 1), Y, Z, (-1, 0, 0)),
        "arriba": ((0, 0, Z), (1, 0, 0), (0, 1, 0), X, Y, (0, 0, -1)),
        "abajo": ((0, 0, 0), (1, 0, 0), (0, 1, 0), X, Y, (0, 0, 1)),
    }
    ala, pata = geo["ala_arista"], geo["esq_pata"]
    m_alto, h_alto = geo["cierre_m_alto"], geo["cierre_h_alto"]
    out = []
    for cid in CARAS:
        F0, U, V, W, H, n_in = defs[cid]
        n_mundo = girar(tuple(-c for c in n_in))
        vertical = abs(n_mundo[2]) < 0.5
        cara = Cara(cid, "", W, H, F0, U, V, _cuarto((girar(U), girar(V)), vertical))
        for col in geo["colocaciones"]:
            if tuple(col["n"]) != tuple(n_in) or col["id"] not in por_id:
                continue
            p = por_id[col["id"]]
            cara.paneles.append(PanelCara(p.id, p.nombre, col["grupo"], p.ancho, p.alto,
                                          tuple(col["o"]), tuple(col["u"]), tuple(col["v"])))
        # nombre: el del panel del cuerpo, sin "cuerpo"
        if cid in ("arriba", "abajo"):
            p0 = cara.paneles[0] if cara.paneles else None
            cara.nombre = p0.nombre if p0 else cid
        else:
            p0 = cara.panel(f"cuerpo_{cid}") or (cara.paneles[0] if cara.paneles else None)
            nom = p0.nombre if p0 else cid
            cara.nombre = nom.replace(" cuerpo", "").replace(" (parte fija)", "")
        # aluminio: aristas y esquineros
        al = [(0, 0, W, ala), (0, H - ala, W, H), (0, 0, ala, H), (W - ala, 0, W, H)]
        al += [(0, 0, pata, pata), (W - pata, 0, W, pata), (0, H - pata, pata, H), (W - pata, H - pata, W, H)]
        if cid not in ("arriba", "abajo"):
            juntas = [dict(nombre="Junta de cierre" + (" (tapa 1)" if geo["dos_tapas"] else ""), plano="c1",
                           fv=geo["z_cierre"], banda=(geo["z_cierre"] - m_alto, geo["z_cierre"] + h_alto))]
            if geo["dos_tapas"]:
                juntas.append(dict(nombre="Junta de cierre (tapa 2)", plano="c2", fv=geo["z_cierre2"],
                                   banda=(geo["z_cierre2"] - h_alto, geo["z_cierre2"] + m_alto)))
            for j in juntas:
                cara.juntas.append(dict(j, horizontal=True))
                al.append((0, j["banda"][0], W, j["banda"][1]))
            # junta de la tapa de acceso lateral (vertical en la cara)
            acc = cara.panel(f"acceso_{cid}")
            fija = cara.panel(f"cuerpo_{cid}")
            if acc and fija:
                ra, rf = cara.rect_panel(acc), cara.rect_panel(fija)
                c = (ra[2] + rf[0]) / 2 if ra[0] < rf[0] else (rf[2] + ra[0]) / 2
                banda = (c - max(m_alto, h_alto), c + max(m_alto, h_alto))
                cara.juntas.append(dict(nombre="Junta de la tapa de acceso", plano="acceso", fu=c, banda=banda,
                                        horizontal=False, v0=min(ra[1], rf[1]), v1=max(ra[3], rf[3])))
                al.append((banda[0], min(ra[1], rf[1]), banda[1], max(ra[3], rf[3])))
        cara.aluminio = [_rect(*r) for r in al]
        out.append(cara)
    return out


def caras(res) -> List[Cara]:
    v = res.valores
    if v["geo"].get("forma"):     # formas.py: los herrajes a mano todavía no se ubican
        return []
    return caras_desde(v["geo"], res.paneles, v["ext_ancho"], v["ext_prof"], v["ext_alto"])


# ---------------------------------------------------------------------------
# Filas de la lista
# ---------------------------------------------------------------------------

def _num(v: Any, d: float = 0.0) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return d
    return float(v)


@dataclass
class Fila:
    ref: str
    cara: str
    x: float
    y: float
    giro: int = 0
    espejo: bool = False
    ancho: float = 0.0
    alto: float = 0.0
    archivo: str = ""
    modo: str = "placa"

    @staticmethod
    def de(e: Any) -> Optional["Fila"]:
        if not isinstance(e, list) or len(e) < 4 or not isinstance(e[0], str) or not isinstance(e[1], str):
            return None
        if not isinstance(e[2], (int, float)) or not isinstance(e[3], (int, float)):
            return None
        g = int(round(_num(e[4] if len(e) > 4 else 0) / 90.0)) % 4 * 90
        return Fila(e[0], e[1], float(e[2]), float(e[3]), g, bool(_num(e[5] if len(e) > 5 else 0)),
                    _num(e[6] if len(e) > 6 else 0), _num(e[7] if len(e) > 7 else 0),
                    e[8] if len(e) > 8 and isinstance(e[8], str) else "",
                    e[9] if len(e) > 9 and isinstance(e[9], str) and e[9] else "placa")

    def lista(self) -> list:
        """Fila para el .scad, sin los campos finales que quedan en su valor por defecto."""
        out: list = [self.ref, self.cara, _limpio(self.x), _limpio(self.y), self.giro, 1 if self.espejo else 0,
                     _limpio(self.ancho), _limpio(self.alto), self.archivo, self.modo]
        defecto = [None, None, None, None, 0, 0, 0, 0, "", "placa"]
        while len(out) > 4 and out[-1] == defecto[len(out) - 1]:
            out.pop()
        return out


def _limpio(v: float) -> Any:
    v = round(float(v), 2)
    return int(v) if v.is_integer() else v


# ---------------------------------------------------------------------------
# Resolución
# ---------------------------------------------------------------------------

@dataclass
class Colocado:
    indice: int
    fila: Fila
    nombre: str
    categoria: str           # categoría del catálogo, "logo" u "otro"
    forma: str               # calado, junta, rueda, pie, logo, superficie
    cara: str
    cara_nombre: str
    x: float                 # centro en la vista (ya centrado en la junta si es cierre o bisagra)
    y: float
    ancho: float             # medida en la vista (girada)
    alto: float
    panel: str = ""          # panel bajo el centro ("" si cae en una junta o fuera)
    px: float = 0.0          # centro en el panel
    py: float = 0.0
    pw: float = 0.0          # medida en el panel
    ph: float = 0.0
    giro_panel: int = 0      # giro total en el panel (grados)
    datos: Dict[str, Any] = field(default_factory=dict)
    lineas: List[List[Tuple[float, float]]] = field(default_factory=list)       # logo, en la vista
    lineas_panel: List[List[Tuple[float, float]]] = field(default_factory=list)  # logo, en el panel
    marcas: List[Any] = field(default_factory=list)     # Marca del modelo que generó
    calados: List[Any] = field(default_factory=list)    # Calado del modelo que generó
    avisos: List[str] = field(default_factory=list)

    @property
    def rect_vista(self) -> Rect:
        return (self.x - self.ancho / 2, self.y - self.alto / 2, self.x + self.ancho / 2, self.y + self.alto / 2)


@dataclass
class ResultadoManuales:
    colocados: List[Colocado] = field(default_factory=list)
    calados: list = field(default_factory=list)
    marcas: list = field(default_factory=list)
    herrajes: List[list] = field(default_factory=list)     # [nombre, cant, detalle, ref]
    avisos: List[str] = field(default_factory=list)
    remaches: int = 0


def _medidas(cat: CatalogoTaller, f: Fila, categoria: str) -> Tuple[str, float, float, Dict[str, Any]]:
    """(forma, ancho, alto, datos) sin girar."""
    d = dict(cat.fila(f.ref)["datos"]) if cat.existe(f.ref) else {}
    if categoria == "logo":
        return "logo", f.ancho or 100.0, f.alto, d
    if categoria == "manija":
        if d.get("tipo", "embutida") == "embutida" and d.get("corte"):
            return "calado", float(d["corte"][0]), float(d["corte"][1]), d
        ext = d.get("exterior") or _MEDIDA_DEF["manija"]
        return "manija_sup", f.ancho or float(ext[0]), f.alto or float(ext[1]), d
    if categoria in ("cierre", "bisagra"):
        if d.get("largo"):    # bisagra de piano: es un tramo a lo largo, va como pieza de superficie
            return "superficie", f.ancho or 300.0, f.alto or 40.0, d
        w, h = d.get("corte") or _MEDIDA_DEF[categoria]
        return "junta", float(w), float(h), d
    if categoria == "plato" and d.get("corte"):
        return "calado", float(d["corte"][0]), float(d["corte"][1]), d
    if categoria in ("rueda", "rueda_otra"):
        pl = d.get("placa") or [100, 85]
        return "rueda", float(pl[0]), float(pl[1]), d
    if categoria == "pie":
        dm = float(d.get("diametro", 38))
        return "pie", dm, dm, d
    w, h = _MEDIDA_DEF.get(categoria, (40, 40))
    return "superficie", f.ancho or float(w), f.alto or float(h), d


def _girada(w: float, h: float, giro: int) -> Tuple[float, float]:
    return (h, w) if (giro // 90) % 2 else (w, h)


def _rotar(x: float, y: float, giro: int) -> Tuple[float, float]:
    a = (giro // 90) % 4
    return ((x, y), (-y, x), (-x, -y), (y, -x))[a]


def _logo(f: Fila, base: str) -> Tuple[List[List[Tuple[float, float]]], float, float, Optional[str]]:
    """Líneas del logo centradas en (0, 0) y medidas finales; error si no se pudo leer."""
    from . import vectores
    if not f.archivo:
        return [], f.ancho or 100.0, f.alto or (f.ancho or 100.0) / 2, "falta el archivo del logo (.svg o .dxf)"
    ruta = f.archivo if os.path.isabs(f.archivo) or not base else os.path.join(base, f.archivo)
    try:
        lineas = vectores.leer(ruta)
    except (OSError, ValueError) as e:
        return [], f.ancho or 100.0, f.alto or (f.ancho or 100.0) / 2, f"no se pudo leer {os.path.basename(f.archivo)}: {e}"
    total = sum(len(l) for l in lineas)
    if total > MAX_PUNTOS_LOGO:   # demasiado detalle para la vista: se simplifica
        paso = math.ceil(total / MAX_PUNTOS_LOGO)
        lineas = [l[::paso] + ([l[-1]] if (len(l) - 1) % paso else []) for l in lineas]
        lineas = [l for l in lineas if len(l) >= 2]
    lineas, w, h = vectores.encajar(lineas, f.ancho or 100.0, f.alto)
    return lineas, w, h, None


def aplicar(P: Dict[str, Any], geo: Dict[str, Any], paneles: Sequence[Any], X: float, Y: float, Z: float,
            calados_auto: Sequence[Any], cat: CatalogoTaller) -> ResultadoManuales:
    """Resuelve P["herrajes_manuales"] contra las caras del case (`calados_auto`: los calados
    que ya puso el modelo, para avisar si se pisan)."""
    from .modelo import Calado, Marca
    R = ResultadoManuales()
    filas = P.get("herrajes_manuales") or []
    if not isinstance(filas, list):
        R.avisos.append("herrajes_manuales tiene que ser una lista de filas [ref, cara, x, y, ...].")
        return R
    lista_caras = {c.id: c for c in caras_desde(geo, paneles, X, Y, Z)}
    base = P.get("_carpeta") or ""
    m_alto, h_alto = geo["cierre_m_alto"], geo["cierre_h_alto"]
    por_panel_calados: Dict[str, List[Any]] = {}
    for c in calados_auto:
        por_panel_calados.setdefault(c.panel, []).append(c)
    nombres_panel = {p.id: p.nombre for p in paneles}

    for i, e in enumerate(filas):
        f = Fila.de(e)
        if f is None:
            R.avisos.append(s("La fila ", i + 1, " de herrajes_manuales está mal escrita: va [ref, cara, x, y, giro, espejo, ...]."))
            continue
        cara = lista_caras.get(f.cara)
        if cara is None:
            R.avisos.append(s("Herraje a mano ", i + 1, " (", f.ref, "): la cara «", f.cara, "» no existe (",
                              ", ".join(CARAS), ")."))
            continue
        if f.ref == "logo":
            categoria, nombre = "logo", "Placa de logo" if f.modo != "grabado" else "Logo grabado"
        elif cat.existe(f.ref):
            categoria, nombre = cat.categoria(f.ref), cat.nombre(f.ref)
        else:
            categoria, nombre = "otro", f.ref or "Pieza"
        forma, w0, h0, datos = _medidas(cat, f, categoria)
        lineas0: List[List[Tuple[float, float]]] = []
        if forma == "logo":
            lineas0, w0, h0, err = _logo(f, base)
            if err:
                R.avisos.append(s("Logo (herraje a mano ", i + 1, "): ", err, ". Se dibuja como un rectángulo."))
        if forma == "junta" and not any(j["horizontal"] for j in cara.juntas):
            R.avisos.append(s(nombre, " (herraje a mano ", i + 1, "): en ", cara.nombre,
                              " no hay junta de cierre; queda como pieza de superficie."))
            forma = "superficie"
        giro = 0 if forma == "junta" else f.giro
        # un cierre va siempre derecho sobre la junta: en la vista gira con la cara
        w, h = _girada(w0, h0, cara.giro * 90 if forma == "junta" else giro)
        col = Colocado(i, f, nombre, categoria, forma, f.cara, cara.nombre, f.x, f.y, w, h, datos=datos)
        etiqueta = s(nombre, " (a mano, ", cara.nombre.lower(), ")")

        fu, fv = cara.a_cara(f.x, f.y)
        if forma == "junta":
            js = [j for j in cara.juntas if j["horizontal"]]
            j = min(js, key=lambda j: abs(j["fv"] - fv))
            fv = j["fv"]
            col.x, col.y = cara.a_vista(fu, fv)
            tipo_m = "bisagra" if categoria == "bisagra" else "cierre"
            if j["plano"] == "c1":
                lados = ((j["fv"] - m_alto, "cuerpo"), (j["fv"] + h_alto, "tapa"))
            else:
                lados = ((j["fv"] + m_alto, "cuerpo"), (j["fv"] - h_alto, "tapa2"))
            ok = True
            for fv_m, grupo in lados:
                p = cara.panel_en(fu, fv_m)
                if p is None or p.grupo != grupo:
                    ok = False
                    continue
                px, py = cara.cara_a_panel(p, fu, fv_m)
                m = Marca(p.id, tipo_m, px, py, 0, 0, j["plano"])
                col.marcas.append(m)
                if grupo == "cuerpo":
                    col.panel, col.px, col.py = p.id, px, py
                    if categoria == "cierre" and datos.get("tipo") == "embutido" and datos.get("corte"):
                        cw, ch = datos["corte"]
                        cy = py - 2 - ch / 2 if j["plano"] == "c1" else py + 2 + ch / 2
                        col.calados.append(Calado(p.id, "cierre" + SUFIJO, px, cy, cw, ch, datos.get("radio", 8)))
            if not ok:
                col.avisos.append(s(etiqueta, ": a esa altura de la junta no hay panel de los dos lados "
                                    "(cae sobre una esquina o una tapa de acceso)."))
            col.pw, col.ph = (w, h)
        else:
            p = cara.panel_en(fu, fv)
            rf = cara.rect_a_cara(col.rect_vista)
            if p is None:
                col.avisos.append(s(etiqueta, " queda fuera de los paneles (sobre la junta o el aluminio): no se marca."))
            else:
                px, py = cara.cara_a_panel(p, fu, fv)
                gira = (cara.giro * 90 + giro) % 360
                pw, ph = _girada(w0, h0, gira)
                col.panel, col.px, col.py, col.pw, col.ph, col.giro_panel = p.id, px, py, pw, ph, gira
                rp = (px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2)
                if not _dentro(rp, (0, 0, p.ancho, p.alto)):
                    col.avisos.append(s(etiqueta, " se sale del panel ", p.nombre, ": movelo hacia adentro."))
                if forma == "calado":
                    tipo_c = ("manija" if categoria == "manija" else "encastre") + SUFIJO
                    col.calados.append(Calado(p.id, tipo_c, px, py, pw, ph, float(datos.get("radio", 8))))
                elif forma == "rueda":
                    ag = datos.get("agujeros") or [80, 60]
                    dag = float(datos.get("agujero_d", 9))
                    if dag > 0:
                        for ax in (-1, 1):
                            for ay in (-1, 1):
                                dx, dy = _rotar(ax * ag[0] / 2, ay * ag[1] / 2, gira)
                                col.calados.append(Calado(p.id, "agujero" + SUFIJO, px + dx, py + dy, dag, dag, dag / 2))
                    col.marcas.append(Marca(p.id, "herraje" + SUFIJO, px, py, pw, ph, nombre))
                else:
                    col.marcas.append(Marca(p.id, "herraje" + SUFIJO, px, py, pw, ph, nombre))
            # aluminio: lo que va sobre la cara no puede pisar ángulos, perfiles ni esquineros
            ext = datos.get("exterior")
            if forma == "calado" and ext:
                ew, eh = _girada(float(ext[0]), float(ext[1]), giro)
                huella = cara.rect_a_cara((col.x - ew / 2, col.y - eh / 2, col.x + ew / 2, col.y + eh / 2))
            else:
                huella = rf
            if any(_solapa(huella, a) for a in cara.aluminio):
                col.avisos.append(s(etiqueta, " pisa el aluminio (ángulo, perfil de cierre o esquinero): "
                                    "corrélo hacia el centro del panel."))
        if forma == "logo":
            for l in lineas0:
                pts = []
                for lx, ly in l:
                    if f.espejo:
                        lx = -lx
                    dx, dy = _rotar(lx, ly, giro)
                    pts.append((col.x + dx, col.y + dy))
                col.lineas.append(pts)
            if col.panel:
                pc = cara.panel(col.panel)
                col.lineas_panel = [[cara.cara_a_panel(pc, *cara.a_cara(x, y)) for x, y in l] for l in col.lineas]
        # choques con otros calados del mismo panel
        for c in col.calados:
            if c.tipo.startswith("agujero"):
                continue
            rc = (c.cx - c.ancho / 2, c.cy - c.alto / 2, c.cx + c.ancho / 2, c.cy + c.alto / 2)
            for o in por_panel_calados.get(c.panel, []):
                if o.tipo.startswith("agujero"):
                    continue
                ro = (o.cx - o.ancho / 2, o.cy - o.alto / 2, o.cx + o.ancho / 2, o.cy + o.alto / 2)
                if _solapa(rc, ro, 10):
                    col.avisos.append(s("En ", nombres_panel.get(c.panel, c.panel), " el calado de ", c.tipo,
                                        " queda a menos de 10 mm del de ", o.tipo, ": se pisan."))
                    break
        for c in col.calados:
            por_panel_calados.setdefault(c.panel, []).append(c)
        R.colocados.append(col)
        R.calados += col.calados
        R.marcas += col.marcas
        R.avisos += col.avisos

    # superficies que se pisan entre sí
    sup = [c for c in R.colocados if c.forma not in ("junta", "calado") and c.panel]
    for a_i, a in enumerate(sup):
        for b in sup[a_i + 1:]:
            if a.panel == b.panel and _solapa(a.rect_vista, b.rect_vista) and a.cara == b.cara:
                R.avisos.append(s(a.nombre, " y ", b.nombre, " (a mano) se pisan en ", nombres_panel.get(a.panel, a.panel), "."))

    _lista(R, cat)
    return R


def _lista(R: ResultadoManuales, cat: CatalogoTaller) -> None:
    """Herrajes para la lista de materiales y remaches que suman."""
    grupos: Dict[Tuple[str, str], Dict[str, Any]] = {}
    ruedas = 0
    remaches = 0
    for c in R.colocados:
        f = c.fila
        if c.categoria == "logo":
            if f.modo == "grabado":
                clave = ("", s("Grabado de logo ", os.path.basename(f.archivo) or ""))
                detalle = s(fmt(c.ancho), " x ", fmt(c.alto), " mm, grabado sobre la placa")
            else:
                clave = ("", s("Placa de logo ", os.path.basename(f.archivo) or ""))
                detalle = s(fmt(c.ancho), " x ", fmt(c.alto), " mm, remachada")
                remaches += 4
        else:
            clave = (f.ref if cat.existe(f.ref) else "", c.nombre)
            detalle = ""
            remaches += int(c.datos.get("remaches", _REMACHES_DEF.get(c.categoria, 0)))
        if c.forma == "rueda":
            ruedas += 1
        g = grupos.setdefault(clave, dict(cant=0, donde=[], detalle=detalle))
        g["cant"] += 1
        if c.cara_nombre.lower() not in g["donde"]:
            g["donde"].append(c.cara_nombre.lower())
    for (ref, nombre), g in grupos.items():
        R.herrajes.append([nombre.strip(), g["cant"], (g["detalle"] + "; " if g["detalle"] else "")
                           + "a mano: " + ", ".join(g["donde"]), ref])
    if ruedas:
        R.herrajes.append(["Bulón M8 + arandela + tuerca autofrenante", 4 * ruedas, "ruedas puestas a mano", ""])
    R.remaches = remaches


def unir_herrajes(herrajes: List[Any], nuevos: List[list], Herraje) -> None:
    """Suma los herrajes a mano a la lista: si la referencia ya está, suma la cantidad."""
    for n in nuevos:
        nombre, cant, detalle, ref = n
        previo = next((h for h in herrajes if ref and h.ref == ref), None)
        if previo is not None:
            previo.cantidad += cant
            previo.detalle = s(previo.detalle, " + ", cant, " a mano")
        else:
            herrajes.append(Herraje(nombre, cant, detalle, ref))


# ---------------------------------------------------------------------------
# Edición (para la vista 2D)
# ---------------------------------------------------------------------------

def espejar(f: Fila, cara: Cara) -> Fila:
    """La misma pieza en la cara opuesta, en la posición simétrica (vista desde afuera)."""
    return Fila(f.ref, OPUESTA[f.cara], round(cara.ancho - f.x, 2), f.y, (360 - f.giro) % 360,
                (not f.espejo) if f.ref == "logo" else f.espejo, f.ancho, f.alto, f.archivo, f.modo)


def catalogo_colocable(cat: CatalogoTaller) -> List[Dict[str, Any]]:
    """Filas del catálogo que se pueden poner a mano, en el orden de CATEGORIAS."""
    orden = {c: i for i, c in enumerate(CATEGORIAS)}
    filas = [f for f in cat.filas if f["categoria"] in orden]
    return sorted(filas, key=lambda f: (orden[f["categoria"]], f["nombre"]))


# ---------------------------------------------------------------------------
# Instructivo
# ---------------------------------------------------------------------------

def _mm(v: float) -> str:
    return fmt(round(v, 1)).replace(".", ",")


def pasos_instructivo(res, piezas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Paso «Colocar los herrajes a mano», con el formato de instructivo.armar_pasos."""
    man = res.valores.get("manuales")
    if man is None or not man.colocados:
        return []
    num = {i: pz["num"] for pz in piezas for i in pz.get("ids", [])}
    nombres = {p.id: p.nombre for p in res.paneles}
    texto = ["Con el case armado y cerrado. Medidas al centro de cada herraje, desde el borde izquierdo y desde "
             "el de abajo del panel visto desde afuera (como en planos.pdf, en azul)."]
    k = 1
    for c in man.colocados:
        if not c.panel:
            continue
        pn = f"P{num[c.panel]} ({nombres.get(c.panel, c.panel).lower()})" if c.panel in num else nombres.get(c.panel, c.panel)
        pos = f"a {_mm(c.px)} mm del borde izquierdo y {_mm(c.py)} mm del de abajo"
        ref = f" ({c.fila.ref})" if c.categoria not in ("logo", "otro") else ""
        if c.forma == "junta":
            t = (f"{c.nombre}{ref}: centrado sobre la junta de cierre, a {_mm(c.px)} mm del borde izquierdo de {pn}; "
                 "la contraparte va en la tapa, con el case cerrado." +
                 (" Va en su calado." if c.calados else ""))
        elif c.forma == "calado":
            t = f"{c.nombre}{ref}: en su calado de {pn}, {pos}. Remachá por el reborde."
        elif c.forma == "rueda":
            t = (f"{c.nombre}{ref}: en {pn}, sobre sus 4 agujeros ({pos}); bulón desde adentro con arandela grande "
                 "y tuerca autofrenante del lado de la rueda.")
        elif c.forma == "logo" and c.fila.modo == "grabado":
            t = f"Logo grabado ({os.path.basename(c.fila.archivo)}): en {pn}, {pos}; el dibujo está en la capa GRABADO del DXF."
        elif c.forma == "logo":
            t = (f"Placa de logo {_mm(c.ancho)} × {_mm(c.alto)} mm: en {pn}, {pos}"
                 + (", dada vuelta" if c.fila.espejo else "") + ". Remachala en las 4 esquinas.")
        else:
            t = f"{c.nombre}{ref}: en {pn}, {pos}" + (f", girado {c.fila.giro}°" if c.fila.giro else "") + "."
        texto.append(f"{k}. {t}")
        k += 1
    if k == 1:
        return []
    detras = sum(1 for c in man.colocados if c.cara in ("trasera", "izq"))
    camara = "0,0,0,62,0,212,0" if detras > len(man.colocados) / 2 else "0,0,0,62,0,32,0"
    return [dict(titulo="Colocar los herrajes a mano", vista="herrajes_manuales", camara=camara,
                 defs={"paso": 99, "resaltar_manuales": True}, texto=texto)]
