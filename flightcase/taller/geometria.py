"""Modelo 3D de un case del taller, para la vista 3D de la app y las láminas del instructivo.

Los paneles se ubican exactamente como en flightcase.scad (colocar/paredes/ubicar), con
sus calados dibujados sobre la cara exterior. El aluminio (aros de cierre y ángulos),
los esquineros, cierres, manijas, la base de ruedas, las ruedas y las bandejas se
muestran simplificados (cajas), para dar idea del conjunto; las medidas de corte salen
siempre del modelo, no de esta vista.

Igual que el modelo de OpenSCAD, admite los parámetros de las láminas del instructivo:
`paso` (muestra hasta ese paso y resalta lo que se agrega), `explotar`, `abrir_tapa`,
`resaltar_que`, `resaltar_cubierta` y `vista_parte`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ..domain.services import WireframeMesh3D
from ..domain.value_objects import ComponentLayer, PolygonFace3D, Point3D, Segment3D
from .modelo import ResultadoTaller

Vec = Tuple[float, float, float]

# Pasos del instructivo (los mismos números que flightcase.scad)
P_AROS, P_CUERPO, P_TAPA, P_ARISTAS, P_ESQ, P_CIERRES, P_MANIJAS, P_RUEDAS = 2, 3, 4, 5, 6, 7, 8, 9

_GRUPO_COLOR = {"cuerpo": "base", "tapa": "lid", "tapa2": "lid"}
_GRUPO_CAPA = {"cuerpo": ComponentLayer.OUTER_BASE_WALLS, "tapa": ComponentLayer.LID_WALLS,
               "tapa2": ComponentLayer.LID_WALLS}


@dataclass
class Opciones3D:
    paso: int = 99
    explotar: float = 0.0
    abrir_tapa: float = 0.0
    resaltar_que: str = ""          # "perfiles", "aro", "junta" o "bandeja"
    resaltar_cubierta: bool = False
    vista_parte: str = ""           # "fija" o "cubierta"
    cubierta_abierta: float = 0.0
    etiquetas: Dict[str, str] = field(default_factory=dict)   # id de panel -> "P3"

    @classmethod
    def desde_defs(cls, defs: dict) -> "Opciones3D":
        """Toma los mismos parámetros que instructivo.py le pasa a OpenSCAD."""
        et = defs.get("etiquetas", {})
        if isinstance(et, str):    # '[["piso","P1"],...]'
            import json
            et = {a: b for a, b in json.loads(et)}
        return cls(paso=int(defs.get("paso", 99)), explotar=float(defs.get("explotar", 0)),
                   abrir_tapa=float(defs.get("abrir_tapa", 0)), resaltar_que=str(defs.get("resaltar_que", "")),
                   resaltar_cubierta=bool(defs.get("resaltar_cubierta", False)),
                   vista_parte=str(defs.get("vista_parte", "")),
                   cubierta_abierta=float(defs.get("cubierta_abierta", 0)), etiquetas=dict(et))


@dataclass
class Rotulo:
    """Etiqueta de un panel para dibujar sobre la lámina."""
    texto: str
    centro: Point3D
    normal: Vec          # hacia afuera del case


@dataclass
class Malla3D(WireframeMesh3D):
    rotulos: List[Rotulo] = field(default_factory=list)


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
    def __init__(self, ubicar: Callable[[Vec], Vec], girar: Callable[[Vec], Vec], op: Opciones3D) -> None:
        self.ubicar, self.girar, self.op = ubicar, girar, op
        self.caras: List[PolygonFace3D] = []
        self.segmentos: List[Segment3D] = []
        self.rotulos: List[Rotulo] = []

    def visible(self, paso: int) -> bool:
        return self.op.paso >= paso

    def color(self, paso: int, color: str, tipo: str = "") -> str:
        op = self.op
        if op.resaltar_que:
            if op.resaltar_que in ("perfiles", "aro") and tipo in ("aro", "perfil"):
                return "resalte" if op.resaltar_que == "perfiles" or tipo == "aro" else color
            if op.resaltar_que == "bandeja" and tipo == "bandeja":
                return "resalte"
            if op.resaltar_que == "junta" and tipo == "junta":
                return "resalte"
            return color
        if op.paso < 99 and op.paso == paso and not op.resaltar_cubierta:
            return "resalte"
        return color

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


def malla_3d(res: ResultadoTaller, op: Optional[Opciones3D] = None) -> Malla3D:
    """Malla para Schema3DCanvas (y para las láminas) a partir del resultado del taller."""
    op = op or Opciones3D()
    geo = res.valores["geo"]
    v = res.valores
    X, Y, Z = v["ext_ancho"], v["ext_prof"], v["ext_alto"]
    k = _Constructor(_ubicador(geo, Z), _girar(geo), op)
    t = geo["espesor"]
    ex = op.explotar
    lift = op.abrir_tapa + (ex * 2.2 if ex > 0 else 0)
    desplaz = {"cuerpo": 0.0, "tapa": lift, "tapa2": -lift}
    paneles = {p.id: p for p in res.paneles}
    calados: Dict[str, list] = {}
    for c in res.calados:
        calados.setdefault(c.panel, []).append(c)
    marcas: Dict[str, list] = {}
    for m in res.marcas:
        marcas.setdefault(m.panel, []).append(m)
    hib = geo["hibrido"]
    s = geo["cierre_saliente"]

    # Paneles, con sus calados, manijas y cierres sobre la cara exterior
    for col in geo["colocaciones"]:
        p = paneles[col["id"]]
        grupo = col["grupo"]
        paso_p = P_CUERPO if grupo == "cuerpo" else P_TAPA
        if not k.visible(paso_p):
            continue
        cub = "cubierta" in p.nombre.lower() or (p.id.startswith("acceso") and geo.get("cubierta"))
        if (op.vista_parte == "fija" and cub) or (op.vista_parte == "cubierta" and grupo == "cuerpo" and not cub):
            continue
        u, vv, n = col["u"], col["v"], col["n"]
        o = _sum(col["o"], (0, 0, desplaz.get(grupo, 0.0)), _mul(n, -ex))
        if cub and op.cubierta_abierta:
            o = _sum(o, (0, 0, op.cubierta_abierta))
        color = "resalte" if (cub and op.resaltar_cubierta) else k.color(paso_p, _GRUPO_COLOR.get(grupo, "base"))
        k.caja(o, u, vv, n, p.ancho, p.alto, t, color, _GRUPO_CAPA.get(grupo, 30), p.nombre)
        fuera = _mul(n, -1)
        if col["id"] in op.etiquetas:
            man = [c for c in calados.get(p.id, []) if c.tipo == "manija"]
            ly = (man[0].cy - man[0].alto / 2) / 2 if man else p.alto / 2
            centro = _sum(o, _mul(u, p.ancho / 2), _mul(vv, ly), _mul(fuera, 0.5))
            k.rotulos.append(Rotulo(op.etiquetas[col["id"]], k._p(centro, False), k.girar(fuera)))
        for c in calados.get(p.id, []):
            if c.tipo == "rebaje":
                continue
            x0, x1, y0, y1 = c.cx - c.ancho / 2, c.cx + c.ancho / 2, c.cy - c.alto / 2, c.cy + c.alto / 2
            cara = _mul(fuera, 0.2)
            k.contorno([_sum(o, cara, _mul(u, a), _mul(vv, b)) for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))],
                       "profile", f"{p.nombre}: {c.tipo}")
            if c.tipo == "manija" and k.visible(P_MANIJAS):
                k.caja(_sum(o, _mul(u, x0 - 10), _mul(vv, y0 - 10), _mul(fuera, 2)), u, vv, n,
                       c.ancho + 20, c.alto + 20, 2, k.color(P_MANIJAS, "herraje"), ComponentLayer.BASE_ALU, "Manija")
        for m in marcas.get(p.id, []):
            if m.tipo in ("cierre", "bisagra", "cierre_acceso") and k.visible(P_CIERRES):
                a = 60 if m.tipo == "bisagra" else 50
                k.caja(_sum(o, _mul(u, m.x - a / 2), _mul(vv, m.y - 25), _mul(fuera, 6 + s)), u, vv, n,
                       a, 50, 6, k.color(P_CIERRES, "herraje"), ComponentLayer.BASE_ALU,
                       "Bisagra" if m.tipo == "bisagra" else "Cierre")
            elif m.tipo == "manija_sup" and k.visible(P_MANIJAS):
                k.caja(_sum(o, _mul(u, m.x - m.ancho / 2), _mul(vv, m.y - 12), _mul(fuera, 12)), u, vv, n,
                       m.ancho, 24, 12, k.color(P_MANIJAS, "herraje"), ComponentLayer.BASE_ALU, "Manija")

    # Base de ruedas (bajo el panel de abajo)
    base = geo["base"]
    if base and base["panel"] in paneles and k.visible(P_RUEDAS):
        col = next(c for c in geo["colocaciones"] if c["id"] == base["panel"])
        o = _sum(col["o"], _mul(col["u"], base["x"]), _mul(col["v"], base["y"]),
                 _mul(col["n"], -base["separacion"] - base["esp"] - ex * 0.8 - ex))
        k.caja(o, col["u"], col["v"], col["n"], base["ancho"], base["alto"], base["esp"],
               k.color(P_RUEDAS, "base"), ComponentLayer.BASE_FLOOR, "Base de ruedas")

    # Aros de cierre (por fuera de las caras): macho en el cuerpo, hembra en la tapa
    zc1, zc2 = geo["z_cierre"], geo["z_cierre2"]
    m_alto, h_alto = geo["cierre_m_alto"], geo["cierre_h_alto"]
    aros = [(zc1 - m_alto + ex * 0.7, m_alto), (zc1 + lift - ex * 0.7, h_alto)]
    if geo["dos_tapas"]:
        aros += [(zc2 - ex * 0.7, m_alto), (zc2 - h_alto - lift + ex * 0.7, h_alto)]
    if k.visible(P_AROS):
        col_aro = k.color(P_AROS, "profile", "aro")
        for z0, alto in aros:
            for o, u, n, largo in (((0, -s, z0), (1, 0, 0), (0, 1, 0), X),
                                   ((X, Y + s, z0), (-1, 0, 0), (0, -1, 0), X),
                                   ((-s, Y, z0), (0, -1, 0), (1, 0, 0), Y),
                                   ((X + s, 0, z0), (0, 1, 0), (-1, 0, 0), Y)):
                k.caja(o, u, (0, 0, 1), n, largo, alto, s, col_aro, ComponentLayer.BASE_ALU, "Perfil de cierre")

    # Ángulos de las aristas (con perfil híbrido van con los paneles)
    ala, e = geo["ala_arista"], 1.5
    paso_ar_c, paso_ar_t = (P_CUERPO, P_TAPA) if hib else (P_ARISTAS, P_ARISTAS)
    juntas = [zc1 - m_alto, zc1 + h_alto]
    if geo["dos_tapas"]:
        juntas = [zc2 - h_alto, zc2 + m_alto] + juntas
    cortes = [0.0] + juntas + [Z]
    tramos = [(a, b) for a, b in zip(cortes[::2], cortes[1::2]) if b - a > 1]

    def dz_de(z: float) -> Tuple[float, int]:
        """Desplazamiento y paso de lo que está a la altura z (cuerpo o una tapa)."""
        if z > zc1:
            return desplaz["tapa"], paso_ar_t
        if geo["dos_tapas"] and z < zc2:
            return desplaz["tapa2"], paso_ar_t
        return 0.0, paso_ar_c

    for (cx, cy, sx, sy) in ((0, 0, 1, 1), (X, 0, -1, 1), (X, Y, -1, -1), (0, Y, 1, -1)):
        for z0, z1 in tramos:
            dz, paso_a = dz_de((z0 + z1) / 2)
            if not k.visible(paso_a):
                continue
            c = k.color(paso_a, "profile", "perfil")
            k.caja((cx, cy - sy * e, z0 + dz), (sx, 0, 0), (0, 0, 1), (0, sy, 0), ala, z1 - z0, e, c,
                   ComponentLayer.BASE_ALU, "Ángulo de arista")
            k.caja((cx - sx * e, cy, z0 + dz), (0, sy, 0), (0, 0, 1), (sx, 0, 0), ala, z1 - z0, e, c,
                   ComponentLayer.BASE_ALU, "Ángulo de arista")
    for z, sz in ((0.0, 1), (Z, -1)):   # aristas horizontales de abajo y de arriba
        dz, paso_a = dz_de(Z if z == Z else 0.0)
        if not k.visible(paso_a):
            continue
        c = k.color(paso_a, "profile", "perfil")
        for o, u, n, largo in (((0, -e, z + dz), (1, 0, 0), (0, 1, 0), X), ((0, Y, z + dz), (1, 0, 0), (0, 1, 0), X),
                               ((-e, 0, z + dz), (0, 1, 0), (1, 0, 0), Y), ((X, 0, z + dz), (0, 1, 0), (1, 0, 0), Y)):
            k.caja(o, u, (0, 0, sz), n, largo, ala, e, c, ComponentLayer.BASE_ALU, "Ángulo de arista")

    # Esquineros en las esquinas de cada tramo (cuerpo y tapas)
    if k.visible(P_ESQ):
        lado = 34
        for z0, z1 in (tramos or [(0.0, Z)]):
            dz, _ = dz_de((z0 + z1) / 2)
            for zc, sz in ((z0, 1), (z1, -1)):
                for cx, cy, sx, sy in ((0, 0, 1, 1), (X, 0, -1, 1), (X, Y, -1, -1), (0, Y, 1, -1)):
                    k.caja((cx - sx * 4, cy - sy * 4, zc + dz - sz * 4), (sx, 0, 0), (0, sy, 0), (0, 0, sz),
                           lado, lado, lado, k.color(P_ESQ, "herraje"), ComponentLayer.BASE_ALU, "Esquinero")

    # Ruedas (case parado sin base): bloques bajo el piso
    if k.visible(P_RUEDAS):
        for cx, cy in geo["ruedas"]:
            h = geo["rueda_alto"] or 100
            k.caja((cx - 30, cy - 40, -h - ex * 2.2), (1, 0, 0), (0, 1, 0), (0, 0, 1), 60, 80, h,
                   k.color(P_RUEDAS, "herraje"), ComponentLayer.BASE_ALU, "Rueda")

    # Bandejas (ya en coordenadas del mundo)
    if k.visible(P_CUERPO) and op.vista_parte != "cubierta" and op.resaltar_que != "perfiles":
        for i, b in enumerate(geo["bandejas"]):
            k.caja((b["cx"] - b["ancho"] / 2, b["cy"] - b["fondo"] / 2, b["z"] + ex * 0.6), (1, 0, 0), (0, 1, 0),
                   (0, 0, 1), b["ancho"], b["fondo"], b["esp"], k.color(P_CUERPO, "wall", "bandeja"),
                   ComponentLayer.INTERNAL_DIVIDERS, f"Bandeja {i + 1}", mundo=True)

    pts = [p for f in k.caras for p in f.vertices] or [Point3D(0, 0, 0)]
    caja = (Point3D(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)),
            Point3D(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return Malla3D(faces=k.caras, segments=k.segmentos, bounding_box=caja, rotulos=k.rotulos)
