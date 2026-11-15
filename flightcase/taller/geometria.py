"""Modelo 3D de un case del taller para la vista 3D de la app.

Los paneles se ubican exactamente como en flightcase.scad (colocar/paredes/ubicar), con
sus calados dibujados sobre la cara exterior. Los perfiles de aluminio, la base de
ruedas, las ruedas y las bandejas se muestran simplificados (cajas), para dar idea del
conjunto; las medidas de corte salen siempre del modelo, no de esta vista.
"""

from __future__ import annotations

from typing import Callable, Iterable, List, Sequence, Tuple

from ..domain.services import WireframeMesh3D
from ..domain.value_objects import ComponentLayer, PolygonFace3D, Point3D, Segment3D
from .modelo import ResultadoTaller

Vec = Tuple[float, float, float]

_GRUPO_COLOR = {"cuerpo": "base", "tapa": "lid", "tapa2": "lid"}
_GRUPO_CAPA = {"cuerpo": ComponentLayer.OUTER_BASE_WALLS, "tapa": ComponentLayer.LID_WALLS,
               "tapa2": ComponentLayer.LID_WALLS}


def _sum(*vs: Sequence[float]) -> Vec:
    return tuple(sum(c) for c in zip(*vs))  # type: ignore[return-value]


def _mul(v: Sequence[float], k: float) -> Vec:
    return (v[0] * k, v[1] * k, v[2] * k)


def _ubicador(geo: dict, ext_alto: float) -> Callable[[Vec], Vec]:
    """Transformación de ubicar(): el case acostado u orientado al frente."""
    if geo["horizontal"]:
        return lambda p: (ext_alto - p[2], p[1], p[0])
    if geo["frontal"]:
        return lambda p: (p[0], ext_alto - p[2], p[1])
    return lambda p: p


def _girar(geo: dict) -> Callable[[Vec], Vec]:
    """La misma transformación sin traslación, para las normales."""
    if geo["horizontal"]:
        return lambda n: (-n[2], n[1], n[0])
    if geo["frontal"]:
        return lambda n: (n[0], -n[2], n[1])
    return lambda n: n


class _Constructor:
    def __init__(self, ubicar: Callable[[Vec], Vec], girar: Callable[[Vec], Vec]) -> None:
        self.ubicar, self.girar = ubicar, girar
        self.caras: List[PolygonFace3D] = []
        self.segmentos: List[Segment3D] = []

    def _p(self, v: Vec, mundo: bool) -> Point3D:
        x, y, z = v if mundo else self.ubicar(v)
        return Point3D(x, y, z)

    def caja(self, o: Vec, u: Vec, v: Vec, n: Vec, a: float, b: float, c: float, color: str,
             capa: int, etiqueta: str = "", mundo: bool = False) -> None:
        """Prisma o + [0,a]·u + [0,b]·v + [0,c]·n (u, v, n unitarios y perpendiculares)."""
        def P(i: float, j: float, k: float) -> Point3D:
            return self._p(_sum(o, _mul(u, i), _mul(v, j), _mul(n, k)), mundo)

        def N(vec: Vec) -> Vec:
            return vec if mundo else self.girar(vec)

        menos = lambda w: _mul(w, -1)
        caras = [
            ((P(0, 0, 0), P(a, 0, 0), P(a, b, 0), P(0, b, 0)), N(menos(n)), False),
            ((P(0, 0, c), P(0, b, c), P(a, b, c), P(a, 0, c)), N(n), False),
            ((P(0, 0, 0), P(0, 0, c), P(a, 0, c), P(a, 0, 0)), N(menos(v)), True),
            ((P(0, b, 0), P(a, b, 0), P(a, b, c), P(0, b, c)), N(v), True),
            ((P(0, 0, 0), P(0, b, 0), P(0, b, c), P(0, 0, c)), N(menos(u)), True),
            ((P(a, 0, 0), P(a, 0, c), P(a, b, c), P(a, b, 0)), N(u), True),
        ]
        for verts, normal, canto in caras:
            self.caras.append(PolygonFace3D(vertices=verts, normal=normal, color_group=color, label=etiqueta,
                                            is_endgrain=canto and color in ("base", "lid"), layer_order=capa))

    def contorno(self, puntos: Iterable[Vec], color: str, etiqueta: str = "") -> None:
        pts = [self._p(p, False) for p in puntos]
        for i in range(len(pts)):
            self.segmentos.append(Segment3D(pts[i], pts[(i + 1) % len(pts)], "solid", color, etiqueta))


def malla_3d(res: ResultadoTaller) -> WireframeMesh3D:
    """Malla para Schema3DCanvas a partir del resultado del modelo del taller."""
    geo = res.valores["geo"]
    v = res.valores
    X, Y, Z = v["ext_ancho"], v["ext_prof"], v["ext_alto"]
    k = _Constructor(_ubicador(geo, Z), _girar(geo))
    t = geo["espesor"]
    paneles = {p.id: p for p in res.paneles}
    calados = {}
    for c in res.calados:
        calados.setdefault(c.panel, []).append(c)

    # Paneles, con sus calados marcados sobre la cara exterior
    for col in geo["colocaciones"]:
        p = paneles[col["id"]]
        o, u, vv, n = col["o"], col["u"], col["v"], col["n"]
        color = _GRUPO_COLOR.get(col["grupo"], "base")
        k.caja(o, u, vv, n, p.ancho, p.alto, t, color, _GRUPO_CAPA.get(col["grupo"], 30), p.nombre)
        for c in calados.get(p.id, []):
            if c.tipo == "rebaje":
                continue
            x0, x1, y0, y1 = c.cx - c.ancho / 2, c.cx + c.ancho / 2, c.cy - c.alto / 2, c.cy + c.alto / 2
            cara = _mul(n, -0.2)   # apenas por fuera, para que no lo tape el panel
            k.contorno([_sum(o, cara, _mul(u, a), _mul(vv, b)) for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))],
                       "profile", f"{p.nombre}: {c.tipo}")

    # Base de ruedas (bajo el panel de abajo)
    base = geo["base"]
    if base and base["panel"] in paneles:
        col = next(c for c in geo["colocaciones"] if c["id"] == base["panel"])
        o = _sum(col["o"], _mul(col["u"], base["x"]), _mul(col["v"], base["y"]),
                 _mul(col["n"], -base["separacion"] - base["esp"]))
        k.caja(o, col["u"], col["v"], col["n"], base["ancho"], base["alto"], base["esp"], "base",
               ComponentLayer.BASE_FLOOR, "Base de ruedas")

    # Aluminio simplificado: aros de cierre y ángulos de las aristas, por fuera de las caras
    s = geo["cierre_saliente"]
    ala, e = geo["ala_arista"], 1.5
    zs = [geo["z_cierre"]] + ([geo["z_cierre2"]] if geo["dos_tapas"] else [])
    for zc in zs:
        z0, alto = zc - geo["cierre_m_alto"], geo["cierre_m_alto"] + geo["cierre_h_alto"]
        k.caja((0, -s, z0), (1, 0, 0), (0, 0, 1), (0, 1, 0), X, alto, s, "profile", ComponentLayer.BASE_ALU, "Perfil de cierre")
        k.caja((X, Y + s, z0), (-1, 0, 0), (0, 0, 1), (0, -1, 0), X, alto, s, "profile", ComponentLayer.BASE_ALU, "Perfil de cierre")
        k.caja((-s, Y, z0), (0, -1, 0), (0, 0, 1), (1, 0, 0), Y, alto, s, "profile", ComponentLayer.BASE_ALU, "Perfil de cierre")
        k.caja((X + s, 0, z0), (0, 1, 0), (0, 0, 1), (-1, 0, 0), Y, alto, s, "profile", ComponentLayer.BASE_ALU, "Perfil de cierre")
    # tramos verticales entre aros
    cortes = sorted({0.0, Z} | {z for zc in zs for z in (zc - geo["cierre_m_alto"], zc + geo["cierre_h_alto"])})
    tramos = [(a, b) for a, b in zip(cortes[::2], cortes[1::2]) if b - a > 1]
    for (cx, cy, sx, sy) in ((0, 0, 1, 1), (X, 0, -1, 1), (X, Y, -1, -1), (0, Y, 1, -1)):
        for z0, z1 in tramos:
            k.caja((cx, cy - sy * e, z0), (sx, 0, 0), (0, 0, 1), (0, sy, 0), ala, z1 - z0, e, "profile",
                   ComponentLayer.BASE_ALU, "Ángulo de arista")
            k.caja((cx - sx * e, cy, z0), (0, sy, 0), (0, 0, 1), (sx, 0, 0), ala, z1 - z0, e, "profile",
                   ComponentLayer.BASE_ALU, "Ángulo de arista")
    for z, sz in ((0.0, 1), (Z, -1)):   # aristas horizontales de abajo y de arriba
        k.caja((0, -e, z), (1, 0, 0), (0, 0, sz), (0, 1, 0), X, ala, e, "profile", ComponentLayer.BASE_ALU, "Ángulo de arista")
        k.caja((0, Y, z), (1, 0, 0), (0, 0, sz), (0, 1, 0), X, ala, e, "profile", ComponentLayer.BASE_ALU, "Ángulo de arista")
        k.caja((-e, 0, z), (0, 1, 0), (0, 0, sz), (1, 0, 0), Y, ala, e, "profile", ComponentLayer.BASE_ALU, "Ángulo de arista")
        k.caja((X, 0, z), (0, 1, 0), (0, 0, sz), (1, 0, 0), Y, ala, e, "profile", ComponentLayer.BASE_ALU, "Ángulo de arista")

    # Ruedas (case parado sin base): bloques bajo el piso
    for cx, cy in geo["ruedas"]:
        h = geo["rueda_alto"] or 100
        k.caja((cx - 30, cy - 40, -h), (1, 0, 0), (0, 1, 0), (0, 0, 1), 60, 80, h, "profile",
               ComponentLayer.BASE_ALU, "Rueda")

    # Bandejas (ya en coordenadas del mundo)
    for i, b in enumerate(geo["bandejas"]):
        k.caja((b["cx"] - b["ancho"] / 2, b["cy"] - b["fondo"] / 2, b["z"]), (1, 0, 0), (0, 1, 0), (0, 0, 1),
               b["ancho"], b["fondo"], b["esp"], "wall", ComponentLayer.INTERNAL_DIVIDERS, f"Bandeja {i + 1}",
               mundo=True)

    pts = [p for f in k.caras for p in f.vertices] or [Point3D(0, 0, 0)]
    caja = (Point3D(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)),
            Point3D(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return WireframeMesh3D(faces=k.caras, segments=k.segmentos, bounding_box=caja)
