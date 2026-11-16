"""Cómo se ve el case en la vista 3D: tapas abiertas sobre su bisagra, cajones afuera,
piezas ocultas y una sola parte del case (cuerpo o tapas).

Trabaja sobre la malla ya armada por geometria.malla_3d (con las tapas cerradas): cada
sólido de la malla se clasifica una vez (¿es de la tapa 1, de la tapa 2 o del cuerpo?
¿es placa, perfil, herraje, rueda, espuma...?) y después, para cada cuadro de la
animación, sólo se giran o mueven los sólidos que cambian. Así abrir una tapa o sacar un
cajón no recalcula el case.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .geometria import Malla3D
from .malla import DimensionCallout3D, Point3D, PolygonFace3D, Segment3D, WireframeMesh3D
from .modelo import ResultadoTaller

# Qué se puede ocultar, en el orden en que aparece en el panel «Vista»
CATEGORIAS: Tuple[Tuple[str, str], ...] = (
    ("paneles", "Placas (paneles)"),
    ("perfiles", "Perfiles de aluminio"),
    ("herrajes", "Herrajes (esquineros, cierres, manijas)"),
    ("ruedas", "Ruedas, pies y patines"),
    ("patas", "Patas de mesa"),
    ("bandejas", "Bandejas"),
    ("equipos", "Equipos y rack"),
    ("espuma", "Espuma"),
    ("cajones", "Cajones"),
)

SECCIONES: Tuple[Tuple[str, str], ...] = (("todo", "Todo"), ("cuerpo", "Solo cuerpo"), ("tapas", "Solo tapas"))

ANGULO_ABIERTA = 100.0        # grados que gira una tapa abierta del todo sobre su bisagra
TOL = 0.5


@dataclass
class EstadoVista:
    """Lo que el usuario eligió en el panel «Vista» (0 = cerrada / adentro, 1 = abierta / afuera)."""
    tapas: List[float] = field(default_factory=lambda: [0.0, 0.0])
    tapas_ocultas: List[bool] = field(default_factory=lambda: [False, False])
    seccion: str = "todo"
    ocultos: Set[str] = field(default_factory=set)
    cajones: Dict[int, float] = field(default_factory=dict)     # índice del cajón (0, 1...) -> 0..1


@dataclass
class Tapa:
    """Una tapa del case, en coordenadas del mundo de la vista 3D."""
    numero: int          # 1 o 2
    nombre: str          # «Tapa delantera», «Tapa», ...
    eje: int             # eje del mundo sobre el que se separa del cuerpo
    signo: int           # hacia dónde queda la tapa sobre ese eje
    plano: float         # coordenada del plano de cierre sobre `eje`
    bisagra: bool = True  # False: se saca deslizándola (la tapa de abajo de un case parado)


def tapas_del_case(res: ResultadoTaller) -> List[Tapa]:
    """Las tapas del case con su plano de cierre (mismas transformaciones que _ubicador)."""
    v, geo = res.valores, res.valores["geo"]
    Z = v["ext_alto"]
    zc1, zc2 = geo["z_cierre"], geo["z_cierre2"]
    dos = bool(geo.get("dos_tapas"))
    if geo.get("horizontal"):
        t = [Tapa(1, "Tapa izquierda", 0, -1, Z - zc1), Tapa(2, "Tapa derecha", 0, 1, Z - zc2)]
    elif geo.get("frontal"):
        t = [Tapa(1, "Tapa delantera", 1, -1, Z - zc1), Tapa(2, "Tapa trasera", 1, 1, Z - zc2)]
    else:
        t = [Tapa(1, "Tapa", 2, 1, zc1), Tapa(2, "Tapa de abajo", 2, -1, zc2, bisagra=False)]
    return t if dos else t[:1]


def _centro(puntos: Sequence[Point3D]) -> Tuple[float, float, float]:
    n = len(puntos) or 1
    return (sum(p.x for p in puntos) / n, sum(p.y for p in puntos) / n, sum(p.z for p in puntos) / n)


def _de_que_tapa(c: Sequence[float], tapas: Sequence[Tapa]) -> int:
    for t in tapas:
        if (c[t.eje] - t.plano) * t.signo > TOL:
            return t.numero
    return 0


def _categoria(color: str, nombre: str, interior: bool) -> str:
    n = nombre.lower()
    if interior:
        if color == "espuma":
            return "espuma"
        if color == "cajon" or n.startswith("cajón") or "corredera" in n:
            return "cajones"
        return "equipos"
    if n.startswith("pata de mesa") or n.startswith("soporte de pata"):
        return "patas"
    if n == "patín":
        return "ruedas"
    if color in ("base", "lid"):
        return "paneles"
    if color == "wall":
        return "bandejas"
    if color in ("profile", "profile_h", "aluminio") or n.startswith("junta"):
        return "perfiles"
    if color.startswith("rueda") or color in ("freno", "base_ruedas") or n in ("pie", "base de ruedas"):
        return "ruedas"
    return "herrajes"


def _numero_cajon(nombre: str) -> Optional[int]:
    """«Cajón 2 (frente)» -> 1 (índice desde 0)."""
    if not nombre.startswith("Cajón "):
        return None
    resto = nombre[6:].split(" ", 1)[0]
    return int(resto) - 1 if resto.isdigit() else None


@dataclass
class _Grupo:
    desde: int
    hasta: int
    tapa: int
    categoria: str
    cajon: Optional[int] = None
    corredera: bool = False


class VistaCase:
    """La malla de un case lista para mostrar con distintos estados de vista."""

    def __init__(self, malla: Malla3D, res: ResultadoTaller) -> None:
        self.malla = malla
        self.tapas = tapas_del_case(res)
        interior = res.valores.get("interiores")
        self.recorridos: Dict[int, float] = {}
        if interior is not None:
            for i, c in enumerate(interior.cajones):
                self.recorridos[i] = 0.9 * float(c.get("largo") or 0)
        self.grupos: List[_Grupo] = []
        cubiertas = [False] * len(malla.faces)
        for i, so in enumerate(malla.solidos):
            caras = malla.faces[so.desde:so.hasta]
            if not caras:
                continue
            es_int = 0 <= malla.interior_desde <= i
            c = _centro([p for f in caras for p in f.vertices])
            g = _Grupo(so.desde, so.hasta, _de_que_tapa(c, self.tapas), _categoria(so.color, so.nombre, es_int))
            if es_int:
                g.cajon = _numero_cajon(so.nombre)
                g.corredera = "corredera" in so.nombre
            self.grupos.append(g)
            for j in range(so.desde, so.hasta):
                cubiertas[j] = True
        for j, f in enumerate(malla.faces):        # caras sueltas (no deberían quedar)
            if not cubiertas[j]:
                c = _centro(f.vertices)
                self.grupos.append(_Grupo(j, j + 1, _de_que_tapa(c, self.tapas),
                                          _categoria(f.color_group, f.label, False)))
        self._caja = self.caja_paneles()
        self.tapa_segmento = [_de_que_tapa(_centro((s.p1, s.p2)), self.tapas) for s in malla.segments]
        # bisagra de cada tapa: arriba (o atrás, en un case parado), en el borde de la propia tapa
        self.bisagras: Dict[int, Tuple[int, float]] = {}
        for t in self.tapas:
            b = 1 if t.eje == 2 else 2
            vals = [getattr(p, "xyz"[b]) for g in self.grupos if g.tapa == t.numero
                    for f in malla.faces[g.desde:g.hasta] for p in f.vertices]
            if vals:
                self.bisagras[t.numero] = (b, max(vals))

    def caja_paneles(self) -> Tuple[Point3D, Point3D]:
        """Caja de los paneles del case cerrado (sin ruedas ni herrajes que sobresalen)."""
        pts = [p for g in self.grupos if g.categoria == "paneles"
               for f in self.malla.faces[g.desde:g.hasta] for p in f.vertices] or \
            [self.malla.bounding_box[0], self.malla.bounding_box[1]]
        return (Point3D(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)),
                Point3D(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))

    def cotas(self, estado: EstadoVista) -> List[DimensionCallout3D]:
        """Cotas del case: ancho, fondo y alto por fuera (sin ruedas), y el alto de cada tapa
        cerrada, separadas del case para que no tapen nada."""
        a, b = self._caja
        dx, dy, dz = b.x - a.x, b.y - a.y, b.z - a.z
        sep = max(40.0, 0.12 * max(dx, dy, dz))
        P = Point3D
        fmt_ = lambda v: f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        out = [
            DimensionCallout3D(P(a.x, a.y, a.z), P(b.x, a.y, a.z), f"{fmt_(dx)} mm", dx, (0.0, -sep, 0.0), "length"),
            DimensionCallout3D(P(b.x, a.y, a.z), P(b.x, b.y, a.z), f"{fmt_(dy)} mm", dy, (sep, 0.0, 0.0), "width"),
            DimensionCallout3D(P(b.x, a.y, a.z), P(b.x, a.y, b.z), f"{fmt_(dz)} mm", dz, (sep * 0.7, -sep * 0.7, 0.0),
                               "height"),
        ]
        lo, hi = (a.x, a.y, a.z), (b.x, b.y, b.z)
        for t in self.tapas:
            i = t.numero - 1
            if t.numero not in self.bisagras or estado.tapas[i] > 0 or estado.tapas_ocultas[i] \
                    or estado.seccion == "cuerpo":
                continue
            borde = hi[t.eje] if t.signo > 0 else lo[t.eje]
            h = abs(borde - t.plano)
            k = 0.7 * sep
            # sobre una arista que no use la cota del alto total, y corrida hacia afuera
            base, off = {2: ([a.x, a.y, 0.0], (-k, -k, 0.0)),     # case parado: arista de adelante a la izq.
                         1: ([b.x, 0.0, b.z], (k, 0.0, k)),       # frontal: arista de arriba a la der.
                         0: ([0.0, a.y, b.z], (0.0, -k, k))}[t.eje]  # acostado: arista de arriba adelante
            p1, p2 = list(base), list(base)
            p1[t.eje], p2[t.eje] = t.plano, borde
            out.append(DimensionCallout3D(P(*p1), P(*p2), f"{t.nombre}: {fmt_(h)} mm", h, off, "lid_height"))
        return out

    @property
    def nombres_tapas(self) -> List[str]:
        return [t.nombre for t in self.tapas if t.numero in self.bisagras]

    @property
    def cantidad_cajones(self) -> int:
        return len(self.recorridos)

    def ocultas(self, estado: EstadoVista) -> List[str]:
        """Lo que no se ve, para el aviso sobre la vista («Oculta: tapa delantera»)."""
        out = [t.nombre.lower() for t in self.tapas
               if t.numero <= len(estado.tapas_ocultas) and estado.tapas_ocultas[t.numero - 1]]
        if estado.seccion == "cuerpo":
            out.append("tapas")
        elif estado.seccion == "tapas":
            out.append("cuerpo")
        nombres = dict(CATEGORIAS)
        out += [nombres[c].split(" (")[0].lower() for c, _ in CATEGORIAS if c in estado.ocultos]
        return out

    # ------------------------------------------------------------------ transformación
    def _movimiento(self, tapa: int, estado: EstadoVista):
        """Función punto/normal -> punto/normal para una tapa abierta (o None si está cerrada)."""
        if tapa == 0 or tapa > len(estado.tapas):
            return None
        f = max(0.0, min(1.0, estado.tapas[tapa - 1]))
        if f <= 0 or tapa not in self.bisagras:
            return None
        t = self.tapas[tapa - 1]
        b, hb = self.bisagras[tapa]
        a = t.eje
        if not t.bisagra:          # se desliza hacia afuera
            d = [0.0, 0.0, 0.0]
            d[a] = t.signo * f * 250.0

            def mover(p: Point3D) -> Point3D:
                return Point3D(p.x + d[0], p.y + d[1], p.z + d[2])
            return mover, (lambda n: n)
        phi = math.radians(t.signo * ANGULO_ABIERTA * f)
        co, si = math.cos(phi), math.sin(phi)

        def girar_v(q: List[float]) -> List[float]:
            da, db = q[a], q[b]
            q[a], q[b] = da * co - db * si, da * si + db * co
            return q

        def mover(p: Point3D) -> Point3D:
            q = [p.x, p.y, p.z]
            q[a] -= t.plano
            q[b] -= hb
            girar_v(q)
            q[a] += t.plano
            q[b] += hb
            return Point3D(q[0], q[1], q[2])

        def normal(n: Tuple[float, float, float]) -> Tuple[float, float, float]:
            q = girar_v(list(n))
            return (q[0], q[1], q[2])
        return mover, normal

    def aplicar(self, estado: EstadoVista) -> WireframeMesh3D:
        m = self.malla
        movs = {t.numero: self._movimiento(t.numero, estado) for t in self.tapas}
        ocultas = {t.numero for t in self.tapas
                   if t.numero <= len(estado.tapas_ocultas) and estado.tapas_ocultas[t.numero - 1]}
        caras: List[PolygonFace3D] = []
        for g in self.grupos:
            if g.categoria in estado.ocultos or g.tapa in ocultas:
                continue
            if (estado.seccion == "cuerpo" and g.tapa) or (estado.seccion == "tapas" and not g.tapa):
                continue
            mov = movs.get(g.tapa)
            dy = 0.0
            if g.cajon is not None:
                dy = -self.recorridos.get(g.cajon, 0.0) * max(0.0, min(1.0, estado.cajones.get(g.cajon, 0.0)))
                if g.corredera:
                    dy *= 0.5            # la corredera telescópica sale la mitad
            for f in m.faces[g.desde:g.hasta]:
                if mov is not None:
                    mover, normal = mov
                    f = replace(f, vertices=tuple(mover(p) for p in f.vertices), normal=normal(f.normal))
                elif dy:
                    f = replace(f, vertices=tuple(Point3D(p.x, p.y + dy, p.z) for p in f.vertices))
                caras.append(f)
        segmentos: List[Segment3D] = []
        if "paneles" not in estado.ocultos:
            for s, tapa in zip(m.segments, self.tapa_segmento):
                if tapa in ocultas or (estado.seccion == "cuerpo" and tapa) or \
                        (estado.seccion == "tapas" and not tapa):
                    continue
                mov = movs.get(tapa)
                if mov is not None:
                    s = Segment3D(mov[0](s.p1), mov[0](s.p2), s.style, s.color_group, s.label, s.wall_index)
                segmentos.append(s)
        # la caja de referencia es la del case cerrado: la cámara no salta al abrir una tapa
        return WireframeMesh3D(faces=caras, segments=segmentos, dimensions=list(m.dimensions) + self.cotas(estado),
                               bounding_box=m.bounding_box)
