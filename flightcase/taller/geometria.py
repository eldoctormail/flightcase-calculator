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

import math

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
    normal: Vec          # hacia donde mira la cara del panel
    tam: float = 30.0    # alto de letra en mm (como rotulo() de flightcase.scad)


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

    def color(self, paso: int, color: str) -> str:
        """cc(): resalta lo que se agrega en el paso (salvo en láminas con otro resaltado)."""
        op = self.op
        if op.paso < 99 and op.paso == paso and not op.resaltar_cubierta and not op.resaltar_que:
            return "resalte"
        return color

    def color_perfil(self, paso: int, color: str) -> str:
        """_col_perf(): en las láminas de perfiles o de aro, los aros van resaltados."""
        return "resalte" if self.op.resaltar_que in ("perfiles", "aro") else self.color(paso, color)

    def bloque(self, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, color: str,
               capa: int, etiqueta: str = "") -> None:
        """Caja alineada a los ejes locales del case."""
        if x1 - x0 > 0.01 and y1 - y0 > 0.01 and z1 - z0 > 0.01:
            self.caja((x0, y0, z0), (1, 0, 0), (0, 1, 0), (0, 0, 1), x1 - x0, y1 - y0, z1 - z0, color, capa, etiqueta)

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

    def cilindro(self, centro: Vec, eje: Vec, a: Vec, b: Vec, r: float, largo: float, color: str,
                 capa: int, etiqueta: str = "", lados: int = 20) -> None:
        """Cilindro de radio r centrado en `centro`, con el eje (unitario) perpendicular a a y b."""
        ang = [2 * math.pi * i / lados for i in range(lados)]
        rad = [_sum(_mul(a, math.cos(t)), _mul(b, math.sin(t))) for t in ang]
        abajo = [_sum(centro, _mul(eje, -largo / 2), _mul(d, r)) for d in rad]
        arriba = [_sum(centro, _mul(eje, largo / 2), _mul(d, r)) for d in rad]
        P = lambda q: self._p(q, False)
        self.caras.append(PolygonFace3D(vertices=tuple(P(q) for q in reversed(abajo)), normal=self.girar(_mul(eje, -1)),
                                        color_group=color, label=etiqueta, layer_order=capa))
        self.caras.append(PolygonFace3D(vertices=tuple(P(q) for q in arriba), normal=self.girar(eje),
                                        color_group=color, label=etiqueta, layer_order=capa))
        for i in range(lados):
            j = (i + 1) % lados
            normal = self.girar(_mul(_sum(rad[i], rad[j]), 0.5))
            self.caras.append(PolygonFace3D(vertices=(P(abajo[i]), P(abajo[j]), P(arriba[j]), P(arriba[i])),
                                            normal=normal, color_group=color, label=etiqueta, layer_order=capa))

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

    cub_ids = {"cuerpo_trasera", "acceso_izq", "acceso_der"} if geo["cubierta"] else set()
    ver_fija, ver_cub = op.vista_parte != "cubierta", op.vista_parte != "fija"
    cl = op.cubierta_abierta

    # Paneles, con sus calados, manijas y cierres sobre la cara exterior (colocar/herrajes_panel)
    for col in geo["colocaciones"]:
        p = paneles[col["id"]]
        grupo = col["grupo"]
        paso_p = P_CUERPO if grupo == "cuerpo" else P_TAPA
        if not k.visible(paso_p):
            continue
        cub = col["id"] in cub_ids
        if (cub and not ver_cub) or (grupo == "cuerpo" and not cub and col["id"] != "piso" and not ver_fija):
            continue
        u, vv, n = col["u"], col["v"], col["n"]
        o = _sum(col["o"], (0, 0, desplaz.get(grupo, 0.0)), _mul(n, -ex), (0, cl if cub else 0, 0))
        color = "resalte" if (cub and op.resaltar_cubierta) else k.color(paso_p, _GRUPO_COLOR.get(grupo, "base"))
        k.caja(o, u, vv, n, p.ancho, p.alto, t, color, _GRUPO_CAPA.get(grupo, 30), p.nombre)
        fuera = _mul(n, -1)
        if col["id"] in op.etiquetas:
            man = [c for c in calados.get(p.id, []) if c.tipo == "manija"]
            ly = (man[0].cy - man[0].alto / 2) / 2 if man else p.alto / 2
            centro = _sum(o, _mul(u, p.ancho / 2), _mul(vv, ly), _mul(fuera, 0.5))
            tam = max(min(min(p.ancho, p.alto) * 0.3, 60), 12)
            k.rotulos.append(Rotulo(op.etiquetas[col["id"]], k._p(centro, False), k.girar(fuera), tam))
            adentro = _sum(o, _mul(u, p.ancho / 2), _mul(vv, ly), _mul(n, t + 0.5))   # también del lado de adentro
            k.rotulos.append(Rotulo(op.etiquetas[col["id"]], k._p(adentro, False), k.girar(n), tam))
        for c in calados.get(p.id, []):
            if c.tipo == "rebaje":
                continue
            x0, x1, y0, y1 = c.cx - c.ancho / 2, c.cx + c.ancho / 2, c.cy - c.alto / 2, c.cy + c.alto / 2
            cara = _mul(fuera, 0.2)
            k.contorno([_sum(o, cara, _mul(u, a), _mul(vv, b)) for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))],
                       "profile", f"{p.nombre}: {c.tipo}")
            if c.tipo == "encastre" and k.visible(P_RUEDAS):
                # plato de apilado: reborde por fuera y cubeta metida en la tapa (encastre de flightcase.scad)
                ala, prof = geo.get("encastre_ala", 10), geo.get("encastre_prof", 30)
                col_p = k.color(P_RUEDAS, "herraje")
                for a0, b0, aw, bh in ((x0 - ala, y0 - ala, c.ancho + 2 * ala, ala), (x0 - ala, y1, c.ancho + 2 * ala, ala),
                                       (x0 - ala, y0, ala, c.alto), (x1, y0, ala, c.alto)):
                    k.caja(_sum(o, _mul(u, a0), _mul(vv, b0), _mul(fuera, 1.5)), u, vv, n, aw, bh, 1.5, col_p,
                           ComponentLayer.BASE_ALU, "Plato")
                k.caja(_sum(o, _mul(u, x0 + 0.5), _mul(vv, y0 + 0.5), _mul(n, prof - 1.5)), u, vv, n,
                       c.ancho - 1, c.alto - 1, 1.5, col_p, ComponentLayer.BASE_ALU, "Plato")
            if c.tipo == "manija" and k.visible(P_MANIJAS):
                k.caja(_sum(o, _mul(u, x0 - 10), _mul(vv, y0 - 10), _mul(fuera, 2)), u, vv, n,
                       c.ancho + 20, c.alto + 20, 2, k.color(P_MANIJAS, "herraje"), ComponentLayer.BASE_ALU, "Manija")
        for m in marcas.get(p.id, []):
            if m.tipo == "manija_sup" and k.visible(P_MANIJAS):
                k.caja(_sum(o, _mul(u, m.x - m.ancho / 2), _mul(vv, m.y - 12), _mul(fuera, 12)), u, vv, n,
                       m.ancho, 24, 12, k.color(P_MANIJAS, "herraje"), ComponentLayer.BASE_ALU, "Manija")
            elif m.tipo == "cierre_acceso" and k.visible(P_CIERRES):
                dx = 1 if m.texto == "+" else -1
                lado = m.panel in ("cuerpo_izq", "cuerpo_der")
                xs = (m.x - 35 * dx, m.x + 18 * dx) if lado else (m.x - 22 * dx, m.x + 14 * dx)
                k.caja(_sum(o, _mul(u, min(xs)), _mul(vv, m.y - 25), _mul(fuera, 6 + s)), u, vv, n,
                       abs(xs[1] - xs[0]), 50, 6, k.color(P_CIERRES, "herraje"), ComponentLayer.BASE_ALU, "Cierre")
            elif m.tipo in ("cierre", "bisagra") and k.visible(P_CIERRES):
                d = (1 if m.texto == "c1" else -1) if grupo == "cuerpo" else (-1 if grupo == "tapa" else 1)
                a = 50 if m.tipo == "cierre" else 60
                ys = ((m.y - 35 * d, m.y + (14 if m.tipo == "bisagra" else 18) * d) if grupo == "cuerpo"
                      else (m.y - 22 * d, m.y + 14 * d))
                k.caja(_sum(o, _mul(u, m.x - a / 2), _mul(vv, min(ys)), _mul(fuera, 6 + s)), u, vv, n,
                       a, abs(ys[1] - ys[0]), 6, k.color(P_CIERRES, "herraje"), ComponentLayer.BASE_ALU,
                       "Bisagra" if m.tipo == "bisagra" else "Cierre")
            elif m.tipo == "rueda" and (geo["horizontal"] or geo["frontal"]) and not geo["base"] and k.visible(P_RUEDAS):
                _rueda(k, geo, o, u, vv, fuera, m.x, m.y, m.texto == "freno", ex)
            elif m.tipo == "pie" and (geo["horizontal"] or geo["frontal"]) and k.visible(P_RUEDAS):
                k.caja(_sum(o, _mul(u, m.x - geo["pie_d"] / 2), _mul(vv, m.y - geo["pie_d"] / 2)), u, vv, fuera,
                       geo["pie_d"], geo["pie_d"], geo["pie_h"] + ex * 2.2, k.color(P_RUEDAS, "herraje"),
                       ComponentLayer.BASE_ALU, "Pie")

    # Base de ruedas bajo el panel de abajo, con sus ruedas
    base = geo["base"]
    if base and base["panel"] in paneles and k.visible(P_RUEDAS):
        col = next(c for c in geo["colocaciones"] if c["id"] == base["panel"])
        u, vv, n = col["u"], col["v"], col["n"]
        fuera = _mul(n, -1)
        o_pan = _sum(col["o"], _mul(n, -ex))
        o = _sum(o_pan, _mul(u, base["x"]), _mul(vv, base["y"]), _mul(fuera, base["separacion"] + base["esp"] + ex * 0.8))
        k.caja(o, u, vv, n, base["ancho"], base["alto"], base["esp"], k.color(P_RUEDAS, "base"),
               ComponentLayer.BASE_FLOOR, "Base de ruedas")
        for i, (rx, ry) in enumerate(geo["ruedas_en_base"]):
            _rueda(k, geo, o, u, vv, fuera, rx, ry, i < geo["rueda_frenos"], ex)

    # Aros de cierre: macho en el cuerpo, hembra en la tapa (aro_cierre); con cubierta
    # removible el del cuerpo va partido a la altura de la junta
    zc1, zc2 = geo["z_cierre"], geo["z_cierre2"]
    m_alto, h_alto, pared = geo["cierre_m_alto"], geo["cierre_h_alto"], geo["pared"]
    yj = Y - geo["j_cub"]

    def aro(z0: float, alto: float, color: str, partir: bool = False) -> None:
        def marco(ylo: float, yhi: float, dy: float) -> None:
            for x0, x1, y0, y1 in ((-s, X + s, -s, pared), (-s, X + s, Y - pared, Y + s),
                                   (-s, pared, pared, Y - pared), (X - pared, X + s, pared, Y - pared)):
                k.bloque(x0, x1, max(y0, ylo) + dy, min(y1, yhi) + dy, z0, z0 + alto, color,
                         ComponentLayer.BASE_ALU, "Perfil de cierre")
        if partir and geo["cubierta"]:
            if ver_fija:
                marco(-1e9, yj, 0.0)
            if ver_cub:
                marco(yj, 1e9, cl)
        else:
            marco(-1e9, 1e9, 0.0)

    if k.visible(P_AROS):
        sin_tapas = op.resaltar_cubierta or op.vista_parte or op.resaltar_que
        aro(zc1 - m_alto + ex * 0.7, m_alto, k.color_perfil(P_AROS, "profile"), True)
        if not sin_tapas:
            aro(zc1 + lift - ex * 0.7, h_alto, k.color_perfil(P_AROS, "profile_h"))
        if geo["dos_tapas"]:
            aro(zc2 - ex * 0.7, m_alto, k.color_perfil(P_AROS, "profile"), True)
            if not sin_tapas:
                aro(zc2 - h_alto - lift + ex * 0.7, h_alto, k.color_perfil(P_AROS, "profile_h"))

    # Ángulos de las aristas y esquineros (aristas_y_esquineros)
    paso_ar_c, paso_ar_t = (P_CUERPO, P_TAPA) if hib else (P_ARISTAS, P_ARISTAS)
    e_ar, ala = geo["arista_esp"], geo["ala"]
    ed = geo["esq_descuento"]

    def arista(o: Vec, a: Vec, b: Vec, c: Vec, L: float, paso: int, dy: float = 0.0) -> None:
        if not k.visible(paso) or L < 30:
            return
        o = _sum(o, _mul(_sum(a, b), ex * 1.7), (0, dy, 0))
        col = k.color(paso, "profile")
        k.caja(_sum(o, _mul(b, -ala)), a, b, c, e_ar, ala + e_ar, L, col, ComponentLayer.BASE_ALU, "Ángulo de arista")
        k.caja(_sum(o, _mul(a, -ala)), a, b, c, ala + e_ar, e_ar, L, col, ComponentLayer.BASE_ALU, "Ángulo de arista")

    def esquinero(o: Vec, a: Vec, b: Vec, c: Vec) -> None:
        if not k.visible(P_ESQ):
            return
        p_, e = geo["esq_pata"], 1.5
        o = _sum(o, _mul(_sum(a, b, c), ex * 2.4))
        col = k.color(P_ESQ, "herraje")
        k.caja(_sum(o, _mul(b, -p_), _mul(c, -p_)), a, b, c, e, p_, p_, col, ComponentLayer.BASE_ALU, "Esquinero")
        k.caja(_sum(o, _mul(a, -p_), _mul(c, -p_)), a, b, c, p_, e, p_, col, ComponentLayer.BASE_ALU, "Esquinero")
        k.caja(_sum(o, _mul(a, -p_), _mul(b, -p_)), a, b, c, p_, p_, e, col, ComponentLayer.BASE_ALU, "Esquinero")
        k.caja(_sum(o, (-12, -12, -12)), (1, 0, 0), (0, 1, 0), (0, 0, 1), 24, 24, 24, col, ComponentLayer.BASE_ALU, "Esquinero")

    if ver_fija or ver_cub:
        for z, sz in ((0.0, -1), (Z, 1)):
            dz = desplaz["tapa"] if z > 0 else (desplaz["tapa2"] if geo["dos_tapas"] else 0.0)
            paso_e = paso_ar_t if (z > 0 or geo["dos_tapas"]) else paso_ar_c
            if op.vista_parte and z > 0:
                continue
            for y0, sy in ((0.0, -1), (Y, 1)):
                arista((ed, y0, z + dz), (0, sy, 0), (0, 0, sz), (1, 0, 0), geo["L_x"], paso_e)
            for x0, sx in ((0.0, -1), (X, 1)):
                arista((x0, ed, z + dz), (sx, 0, 0), (0, 0, sz), (0, 1, 0), geo["L_y"], paso_e)
            for x0, sx in ((0.0, -1), (X, 1)):
                for y0, sy in ((0.0, -1), (Y, 1)):
                    esquinero((x0, y0, z + dz), (sx, 0, 0), (0, sy, 0), (0, 0, sz))
        for x0, sx in ((0.0, -1), (X, 1)):
            for y0, sy in ((0.0, -1), (Y, 1)):
                z_c = zc2 + m_alto if geo["dos_tapas"] else ed
                if ver_fija or (y0 > 0 and ver_cub):
                    arista((x0, y0, z_c), (sx, 0, 0), (0, sy, 0), (0, 0, 1), geo["L_zc"], paso_ar_c, cl if y0 > 0 else 0.0)
                if not op.vista_parte:
                    arista((x0, y0, zc1 + h_alto + lift), (sx, 0, 0), (0, sy, 0), (0, 0, 1), geo["L_zt"], paso_ar_t)
                    if geo["dos_tapas"]:
                        arista((x0, y0, ed - lift), (sx, 0, 0), (0, sy, 0), (0, 0, 1), geo["L_zt2"], paso_ar_t)

    # Juntas de las tapas de acceso laterales (juntas_acceso)
    if geo["acceso"] and k.visible(P_CUERPO):
        bm, bh = m_alto - geo["cierre_m_sup"], h_alto - geo["cierre_h_sup"]
        z0 = zc2 + m_alto if geo["dos_tapas"] else ed
        olc, a_acc, j_acc, w_low = geo["olc"], geo["a_acc"], geo["j_acc"], geo["w_low"]
        for cara in ("izq", "der"):
            y_m = Y - olc - a_acc - j_acc - bm if cara == "izq" else olc + w_low - bm
            y_h = Y - olc - a_acc if cara == "izq" else olc + w_low + j_acc
            x = -s - ex * 1.5 if cara == "izq" else X - t + ex * 1.5
            for y0, largo, es_h in ((y_m, bm + j_acc / 2, False), (y_h - j_acc / 2, bh + j_acc / 2, True)):
                if (ver_cub if es_h else ver_fija):
                    col = "resalte" if op.resaltar_que in ("perfiles", "junta") else k.color(P_AROS, "profile")
                    dy = cl if es_h else 0.0
                    k.bloque(x, x + t + s, y0 + dy, y0 + largo + dy, z0, z0 + geo["L_zc"], col,
                             ComponentLayer.BASE_ALU, "Junta de acceso")

    # Ruedas y pies bajo el piso (case parado)
    lift_pie = desplaz["tapa2"] if geo["dos_tapas"] else 0.0
    if k.visible(P_RUEDAS):
        if not base:
            for i, (cx, cy) in enumerate(geo["ruedas"]):
                _rueda(k, geo, (0, 0, lift_pie), (1, 0, 0), (0, 1, 0), (0, 0, -1), cx, cy, i < geo["rueda_frenos"], ex)
        if not (geo["horizontal"] or geo["frontal"]):
            for cx, cy in geo["pies"]:
                d = geo["pie_d"]
                k.bloque(cx - d / 2, cx + d / 2, cy - d / 2, cy + d / 2, lift_pie - geo["pie_h"] - ex * 2.2, lift_pie,
                         k.color(P_RUEDAS, "herraje"), ComponentLayer.BASE_ALU, "Pie")

    # Bandejas (ya en coordenadas del mundo)
    if k.visible(P_CUERPO) and ver_fija and op.resaltar_que != "perfiles" and \
            not (op.resaltar_que == "junta" and op.vista_parte == "fija"):
        for i, b in enumerate(geo["bandejas"]):
            col = "resalte" if op.resaltar_que == "bandeja" else k.color(P_CUERPO, "wall")
            k.caja((b["cx"] - b["ancho"] / 2, b["cy"] - b["fondo"] / 2, b["z"] + ex * 0.6), (1, 0, 0), (0, 1, 0),
                   (0, 0, 1), b["ancho"], b["fondo"], b["esp"], col,
                   ComponentLayer.INTERNAL_DIVIDERS, f"Bandeja {i + 1}", mundo=True)

    pts = [p for f in k.caras for p in f.vertices] or [Point3D(0, 0, 0)]
    caja = (Point3D(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)),
            Point3D(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return Malla3D(faces=k.caras, segments=k.segmentos, bounding_box=caja, rotulos=k.rotulos)


def _rueda(k: _Constructor, geo: dict, o: Vec, u: Vec, v: Vec, fuera: Vec, cx: float, cy: float,
           freno: bool, ex: float) -> None:
    """Rueda (rueda_3d) simplificada: placa, horquilla y rueda, hacia `fuera` desde o + cx·u + cy·v."""
    pl, d = geo["rueda_placa"], geo["rueda_diametro"]
    alto = geo["rueda_alto"] or (d + 25)
    base = _sum(o, _mul(u, cx), _mul(v, cy), _mul(fuera, ex * 2.2))
    resalta = k.op.paso < 99 and k.op.paso == P_RUEDAS
    k.caja(_sum(base, _mul(u, -pl[0] / 2), _mul(v, -pl[1] / 2)), u, v, fuera, pl[0], pl[1], 4,
           "resalte" if resalta else "herraje", ComponentLayer.BASE_ALU, "Rueda")
    k.caja(_sum(base, _mul(u, -d * 0.15), _mul(v, -d * 0.4), _mul(fuera, 4)), u, v, fuera, d * 0.3, d * 0.8,
           max(alto - d - 4, 4), "resalte" if resalta else "herraje", ComponentLayer.BASE_ALU, "Rueda")
    k.cilindro(_sum(base, _mul(fuera, alto - d / 2)), v, u, fuera, d / 2, d * 0.4,
               "rueda_freno" if freno else "rueda", ComponentLayer.BASE_ALU, "Rueda")
