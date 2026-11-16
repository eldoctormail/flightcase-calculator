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

from .malla import ComponentLayer, PolygonFace3D, Point3D, Segment3D, WireframeMesh3D
from .modelo import ResultadoTaller

Vec = Tuple[float, float, float]

# Pasos del instructivo (los mismos números que flightcase.scad)
P_AROS, P_CUERPO, P_TAPA, P_ARISTAS, P_ESQ, P_CIERRES, P_MANIJAS, P_RUEDAS = 2, 3, 4, 5, 6, 7, 8, 9

# Colores de cada grupo (los de flightcase.scad), para las láminas y el STEP
COLORES: Dict[str, str] = {
    "base": "#deb887",        # BurlyWood: color_placa por defecto de flightcase.scad
    "lid": "#deb887",         # color_tapa vacío = igual que la placa
    "profile": "#b0c4de",     # LightSteelBlue: aro macho
    "profile_h": "#708090",   # SlateGray: aro hembra
    "aluminio": "#c0c0c0",    # Silver: ángulos de arista
    "herraje": "#696969",     # DimGray: esquineros, manijas
    "cierre": "#dcdcdc",      # Gainsboro: cierres y bisagras
    "rueda": "#222222",
    "rueda_placa": "#444444",
    "rueda_horq": "#777777",
    "freno": "#ff0000",
    "rueda_freno": "#222222",
    "base_ruedas": "#5a3d22",
    "plato": "#3a3a3a",
    "wall": "#deb887",        # bandejas (color de la placa)
    "equipo": "#3d4b5c",      # equipos dentro del case
    "rack_frente": "#2f2f2f",
    "espuma": "#3a3a3a",      # espuma gris oscura
    "forro_alfombra": "#2c2c34",  # forro interior de alfombra
    "forro_espuma": "#474747",    # forro interior de espuma
    "cajon": "#c9a26b",
    "resalte": "#ffa500",     # Orange: lo que se agrega en el paso
    "rotulo": "#ffffff",
    "remache": "#b4b4b4",
}

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
    interior: bool = True           # equipos, espuma, cajones y rack (sólo con paso = 99)
    resaltar_interior: str = ""     # tipos del interior en naranja, separados por coma ("espuma,equipo")
    resaltar_manuales: bool = False  # herrajes puestos a mano en naranja

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
                   cubierta_abierta=float(defs.get("cubierta_abierta", 0)), etiquetas=dict(et),
                   resaltar_interior=str(defs.get("resaltar_interior", "")),
                   resaltar_manuales=bool(defs.get("resaltar_manuales", False)))


@dataclass
class Rotulo:
    """Etiqueta de un panel para dibujar sobre la lámina."""
    texto: str
    centro: Point3D
    normal: Vec          # hacia donde mira la cara del panel
    tam: float = 30.0    # alto de letra en mm (como rotulo() de flightcase.scad)
    der: Vec = (1.0, 0.0, 0.0)     # dirección de lectura sobre la cara (mundo)
    arriba: Vec = (0.0, 0.0, 1.0)  # hacia arriba del texto (mundo)


def _ejes_rotulo(normal: Vec) -> Tuple[Vec, Vec]:
    """(der, arriba) para que el rótulo se lea derecho mirando la cara desde `normal`:
    arriba es la vertical del mundo proyectada en la cara (o el fondo, si la cara es horizontal)."""
    for ref in ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)):
        d = sum(a * b for a, b in zip(ref, normal))
        up = tuple(r - d * nn for r, nn in zip(ref, normal))
        l = math.sqrt(sum(c * c for c in up))
        if l > 0.3:
            up = tuple(c / l for c in up)
            der = (up[1] * normal[2] - up[2] * normal[1], up[2] * normal[0] - up[0] * normal[2],
                   up[0] * normal[1] - up[1] * normal[0])
            return der, up  # type: ignore[return-value]
    return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)


@dataclass
class Solido3D:
    """Un cuerpo cerrado de la malla: las caras faces[desde:hasta] (para exportar a STEP).
    `agujeros` son los calados pasantes de un panel, sobre una de sus caras."""
    nombre: str
    color: str
    desde: int
    hasta: int
    agujeros: List[List[Point3D]] = field(default_factory=list)


@dataclass
class Malla3D(WireframeMesh3D):
    rotulos: List[Rotulo] = field(default_factory=list)
    # calados pasantes: (nombre del panel, contorno en el mundo sobre la cara exterior)
    calados: List[Tuple[str, List[Point3D]]] = field(default_factory=list)
    solidos: List[Solido3D] = field(default_factory=list)


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
        self.calados: List[Tuple[str, List[Point3D]]] = []
        self.solidos: List[Solido3D] = []

    def cerrar(self, desde: int, color: str, etiqueta: str) -> None:
        """Las caras agregadas desde `desde` forman un cuerpo cerrado."""
        if len(self.caras) > desde:
            self.solidos.append(Solido3D(etiqueta, color, desde, len(self.caras)))

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
        desde = len(self.caras)
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
        self.cerrar(desde, color, etiqueta)

    def hexaedro(self, v8: Sequence[Vec], color: str, capa: int, etiqueta: str = "") -> None:
        """Hexaedro convexo: v8 = 4 vértices de abajo y 4 de arriba, en el mismo orden (coords locales)."""
        P = [self._p(q, False) for q in v8]
        cen = _mul(_sum(*v8), 1 / 8)
        desde = len(self.caras)
        for idx in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            a, b, c = (v8[i] for i in idx[:3])
            e1, e2 = _sum(b, _mul(a, -1)), _sum(c, _mul(a, -1))
            nrm = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            l = math.sqrt(sum(x * x for x in nrm))
            if l < 1e-9:
                continue
            nrm = _mul(nrm, 1 / l)
            fc = _mul(_sum(*(v8[i] for i in idx)), 0.25)
            if sum((fc[i] - cen[i]) * nrm[i] for i in range(3)) < 0:
                nrm = _mul(nrm, -1)
            self.caras.append(PolygonFace3D(vertices=tuple(P[i] for i in idx), normal=self.girar(nrm),
                                            color_group=color, label=etiqueta, layer_order=capa))
        self.cerrar(desde, color, etiqueta)

    def esfera(self, centro: Vec, r: float, color: str, capa: int, etiqueta: str = "",
               lados: int = 16, pisos: int = 8) -> None:
        """Esfera en coordenadas locales (como sphere() con $fn bajo)."""
        def pt(i: int, j: int) -> Vec:
            th, ph = 2 * math.pi * i / lados, math.pi * j / pisos
            return (math.sin(ph) * math.cos(th), math.sin(ph) * math.sin(th), math.cos(ph))
        desde = len(self.caras)
        for j in range(pisos):
            for i in range(lados):
                dirs = [pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1)]
                verts = [self._p(_sum(centro, _mul(d, r)), False) for d in dirs]
                if j == 0:
                    verts = [verts[0], verts[2], verts[3]]
                elif j == pisos - 1:
                    verts = verts[:3]
                nrm = _mul(_sum(*dirs), 0.25)
                l = math.sqrt(sum(x * x for x in nrm)) or 1.0
                self.caras.append(PolygonFace3D(vertices=tuple(verts), normal=self.girar(_mul(nrm, 1 / l)),
                                                color_group=color, label=etiqueta, layer_order=capa))
        self.cerrar(desde, color, etiqueta)

    def cilindro(self, centro: Vec, eje: Vec, a: Vec, b: Vec, r: float, largo: float, color: str,
                 capa: int, etiqueta: str = "", lados: int = 20) -> None:
        """Cilindro de radio r centrado en `centro`, con el eje (unitario) perpendicular a a y b."""
        ang = [2 * math.pi * i / lados for i in range(lados)]
        rad = [_sum(_mul(a, math.cos(t)), _mul(b, math.sin(t))) for t in ang]
        abajo = [_sum(centro, _mul(eje, -largo / 2), _mul(d, r)) for d in rad]
        arriba = [_sum(centro, _mul(eje, largo / 2), _mul(d, r)) for d in rad]
        P = lambda q: self._p(q, False)
        desde = len(self.caras)
        self.caras.append(PolygonFace3D(vertices=tuple(P(q) for q in reversed(abajo)), normal=self.girar(_mul(eje, -1)),
                                        color_group=color, label=etiqueta, layer_order=capa))
        self.caras.append(PolygonFace3D(vertices=tuple(P(q) for q in arriba), normal=self.girar(eje),
                                        color_group=color, label=etiqueta, layer_order=capa))
        for i in range(lados):
            j = (i + 1) % lados
            normal = self.girar(_mul(_sum(rad[i], rad[j]), 0.5))
            self.caras.append(PolygonFace3D(vertices=(P(abajo[i]), P(abajo[j]), P(arriba[j]), P(arriba[i])),
                                            normal=normal, color_group=color, label=etiqueta, layer_order=capa))
        self.cerrar(desde, color, etiqueta)

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
    manuales = v.get("manuales")
    man_panel: Dict[str, list] = {}
    man_ids = set()
    if manuales is not None:
        for c in manuales.colocados:
            if c.panel:
                man_panel.setdefault(c.panel, []).append(c)
        man_ids = {id(x) for x in manuales.calados + manuales.marcas}
    res_man = op.resaltar_manuales

    def col_m(obj, paso: int, color: str) -> str:
        return "resalte" if (res_man and id(obj) in man_ids) else k.color(paso, color)

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
        tp = col.get("esp", t)
        k.caja(o, u, vv, n, p.ancho, p.alto, tp, color, _GRUPO_CAPA.get(grupo, 30), p.nombre)
        sol_panel = k.solidos[-1]
        fuera = _mul(n, -1)
        if col["id"] in op.etiquetas:
            man = [c for c in calados.get(p.id, []) if c.tipo == "manija"]
            ly = (man[0].cy - man[0].alto / 2) / 2 if man else p.alto / 2
            centro = _sum(o, _mul(u, p.ancho / 2), _mul(vv, ly), _mul(fuera, 0.5))
            tam = max(min(min(p.ancho, p.alto) * 0.3, 60), 12)
            nf = k.girar(fuera)
            k.rotulos.append(Rotulo(op.etiquetas[col["id"]], k._p(centro, False), nf, tam, *_ejes_rotulo(nf)))
            adentro = _sum(o, _mul(u, p.ancho / 2), _mul(vv, ly), _mul(n, tp + 0.5))   # también del lado de adentro
            ni = k.girar(n)
            k.rotulos.append(Rotulo(op.etiquetas[col["id"]], k._p(adentro, False), ni, tam, *_ejes_rotulo(ni)))
        for c in calados.get(p.id, []):
            if c.tipo == "rebaje":
                continue
            x0, x1, y0, y1 = c.cx - c.ancho / 2, c.cx + c.ancho / 2, c.cy - c.alto / 2, c.cy + c.alto / 2
            cara = _mul(fuera, 0.2)
            k.contorno([_sum(o, cara, _mul(u, a), _mul(vv, b)) for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))],
                       "profile", f"{p.nombre}: {c.tipo}")
            k.calados.append((p.nombre, [k._p(_sum(o, _mul(u, a), _mul(vv, b)), False)
                                         for a, b in _rect_redondeado(x0, y0, x1, y1, c.radio)]))
            sol_panel.agujeros.append(k.calados[-1][1])
            if c.tipo.startswith("encastre") and k.visible(P_RUEDAS):
                # plato de apilado: reborde por fuera y cubeta metida en la tapa (encastre de flightcase.scad)
                ala, prof = geo.get("encastre_ala", 10), geo.get("encastre_prof", 30)
                col_p = col_m(c, P_RUEDAS, "plato")
                for a0, b0, aw, bh in ((x0 - ala, y0 - ala, c.ancho + 2 * ala, ala), (x0 - ala, y1, c.ancho + 2 * ala, ala),
                                       (x0 - ala, y0, ala, c.alto), (x1, y0, ala, c.alto)):
                    k.caja(_sum(o, _mul(u, a0), _mul(vv, b0), _mul(fuera, 1.5)), u, vv, n, aw, bh, 1.5, col_p,
                           ComponentLayer.BASE_ALU, "Plato")
                k.caja(_sum(o, _mul(u, x0 + 0.5), _mul(vv, y0 + 0.5), _mul(n, prof - 1.5)), u, vv, n,
                       c.ancho - 1, c.alto - 1, 1.5, col_p, ComponentLayer.BASE_ALU, "Plato")
                e_ = 1.5   # paredes de la cubeta
                for a0, b0, aw, bh in ((x0, y0, c.ancho, e_), (x0, y1 - e_, c.ancho, e_),
                                       (x0, y0, e_, c.alto), (x1 - e_, y0, e_, c.alto)):
                    k.caja(_sum(o, _mul(u, a0), _mul(vv, b0)), u, vv, n, aw, bh, prof, col_p,
                           ComponentLayer.BASE_ALU, "Plato")
            if c.tipo == "cazoleta" and k.visible(P_RUEDAS):
                # cazoleta de rueda: reborde por fuera del piso y cubeta metida en el case
                cz = geo.get("cazoleta") or {}
                ala, prof = cz.get("ala", 12), cz.get("prof", 35)
                col_p = col_m(c, P_RUEDAS, "plato")
                for a0, b0, aw, bh in ((x0 - ala, y0 - ala, c.ancho + 2 * ala, ala), (x0 - ala, y1, c.ancho + 2 * ala, ala),
                                       (x0 - ala, y0, ala, c.alto), (x1, y0, ala, c.alto)):
                    k.caja(_sum(o, _mul(u, a0), _mul(vv, b0), _mul(fuera, 1.5)), u, vv, n, aw, bh, 1.5, col_p,
                           ComponentLayer.BASE_ALU, "Cazoleta")
                k.caja(_sum(o, _mul(u, x0 + 0.5), _mul(vv, y0 + 0.5), _mul(n, prof)), u, vv, n,
                       c.ancho - 1, c.alto - 1, 1.5, col_p, ComponentLayer.BASE_ALU, "Cazoleta")
                e_ = 1.5
                for a0, b0, aw, bh in ((x0, y0, c.ancho, e_), (x0, y1 - e_, c.ancho, e_),
                                       (x0, y0, e_, c.alto), (x1 - e_, y0, e_, c.alto)):
                    k.caja(_sum(o, _mul(u, a0), _mul(vv, b0)), u, vv, n, aw, bh, prof + 1.5, col_p,
                           ComponentLayer.BASE_ALU, "Cazoleta")
            if c.tipo in ("manija", "manija a mano") and k.visible(P_MANIJAS):
                _manija_embutida(k, o, u, vv, n, x0, y0, x1, y1, col_m(c, P_MANIJAS, "herraje"))
        for m in marcas.get(p.id, []):
            if m.tipo == "manija_sup" and k.visible(P_MANIJAS):
                _manija_superficie(k, o, u, vv, n, m.x, m.y, m.ancho, k.color(P_MANIJAS, "herraje"))
            elif m.tipo == "cierre_acceso" and k.visible(P_CIERRES):
                dx = 1 if m.texto == "+" else -1
                lado = m.panel in ("cuerpo_izq", "cuerpo_der")
                xs = (m.x - 35 * dx, m.x + 18 * dx) if lado else (m.x - 22 * dx, m.x + 14 * dx)
                # el mismo cierre mariposa, acostado (cruza la junta de la tapa de acceso a lo ancho)
                if lado:
                    _cierre_mariposa(k, o, vv, u, n, m.y, xs, s, k.color(P_CIERRES, "cierre"))
                else:
                    _gancho_cierre(k, o, vv, u, n, m.y, xs, s, k.color(P_CIERRES, "cierre"))
            elif m.tipo in ("cierre", "bisagra") and k.visible(P_CIERRES):
                d = (1 if m.texto == "c1" else -1) if grupo == "cuerpo" else (-1 if grupo == "tapa" else 1)
                a = 50 if m.tipo == "cierre" else 60
                ys = ((m.y - 35 * d, m.y + (14 if m.tipo == "bisagra" else 18) * d) if grupo == "cuerpo"
                      else (m.y - 22 * d, m.y + 14 * d))
                col_c = col_m(m, P_CIERRES, "cierre")
                if m.tipo == "bisagra":
                    _bisagra(k, o, u, vv, n, m.x, ys, d, s, col_c)
                elif grupo == "cuerpo":
                    _cierre_mariposa(k, o, u, vv, n, m.x, ys, s, col_c)
                else:
                    _gancho_cierre(k, o, u, vv, n, m.x, ys, s, col_c)
            elif m.tipo == "rueda" and (geo["horizontal"] or geo["frontal"]) and not geo["base"] and k.visible(P_RUEDAS):
                _rueda(k, geo, o, u, vv, fuera, m.x, m.y, m.texto == "freno", ex,
                       "fija" if m.texto == "fija" else "", (geo.get("cazoleta") or {}).get("prof", 0.0))
            elif m.tipo == "pie" and (geo["horizontal"] or geo["frontal"]) and k.visible(P_RUEDAS):
                k.caja(_sum(o, _mul(u, m.x - geo["pie_d"] / 2), _mul(vv, m.y - geo["pie_d"] / 2)), u, vv, fuera,
                       geo["pie_d"], geo["pie_d"], geo["pie_h"] + ex * 2.2, k.color(P_RUEDAS, "herraje"),
                       ComponentLayer.BASE_ALU, "Pie")
        if k.visible(P_MANIJAS):
            for hm_ in man_panel.get(p.id, []):
                _herraje_manual(k, geo, o, u, vv, n, hm_, "resalte" if res_man else None, ex)

    # Base de ruedas bajo el panel de abajo, con sus ruedas
    base = geo["base"]
    if base and base["panel"] in paneles and k.visible(P_RUEDAS):
        col = next(c for c in geo["colocaciones"] if c["id"] == base["panel"])
        u, vv, n = col["u"], col["v"], col["n"]
        fuera = _mul(n, -1)
        o_pan = _sum(col["o"], _mul(n, -ex))
        o = _sum(o_pan, _mul(u, base["x"]), _mul(vv, base["y"]), _mul(fuera, base["separacion"] + base["esp"] + ex * 0.8))
        k.caja(o, u, vv, n, base["ancho"], base["alto"], base["esp"], k.color(P_RUEDAS, "base_ruedas"),
               ComponentLayer.BASE_FLOOR, "Base de ruedas")
        for i, (rx, ry) in enumerate(geo["ruedas_en_base"]):
            tipo = _tipo_i(geo, i)
            _rueda(k, geo, o, u, vv, fuera, rx, ry, tipo == "freno", ex, tipo)
        # base suelta: marco de ángulo sobre la base, con un ala parada contra el case
        ala_m, e_m = base.get("marco_ala", 32), base.get("marco_esp", 2)
        tope = _sum(o, _mul(n, base["esp"]))    # cara de arriba de la base (n apunta hacia el case)
        col_m_ = k.color(P_RUEDAS, "aluminio")
        for tr in base.get("marco") or []:
            x0, x1, y0, y1 = tr["x0"], tr["x1"], tr["y0"], tr["y1"]
            k.caja(_sum(tope, _mul(u, x0), _mul(vv, y0)), u, vv, n, x1 - x0, y1 - y0, e_m, col_m_,
                   ComponentLayer.BASE_ALU, "Marco de la base")
            b = tr["borde"]
            if b in ("y0", "y1"):
                yb = y0 if b == "y0" else y1 - e_m
                k.caja(_sum(tope, _mul(u, x0), _mul(vv, yb)), u, vv, n, x1 - x0, e_m, ala_m, col_m_,
                       ComponentLayer.BASE_ALU, "Marco de la base")
            else:
                xb = x0 if b == "x0" else x1 - e_m
                k.caja(_sum(tope, _mul(u, xb), _mul(vv, y0)), u, vv, n, e_m, y1 - y0, ala_m, col_m_,
                       ComponentLayer.BASE_ALU, "Marco de la base")

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
        col = k.color(paso, "aluminio")
        k.caja(_sum(o, _mul(b, -ala)), a, b, c, e_ar, ala + e_ar, L, col, ComponentLayer.BASE_ALU, "Ángulo de arista")
        k.caja(_sum(o, _mul(a, -ala)), a, b, c, ala + e_ar, e_ar, L, col, ComponentLayer.BASE_ALU, "Ángulo de arista")
        # remaches cada ~150 mm en las dos alas
        n_r = max(2, int(L // 150) + 1)
        for i in range(n_r):
            zc_ = 25 + (L - 50) * i / max(n_r - 1, 1)
            _remache(k, _sum(o, _mul(a, e_ar), _mul(b, -ala / 2), _mul(c, zc_)), a, b, c)
            _remache(k, _sum(o, _mul(b, e_ar), _mul(a, -ala / 2), _mul(c, zc_)), b, a, c)

    def esquinero(o: Vec, a: Vec, b: Vec, c: Vec) -> None:
        if not k.visible(P_ESQ):
            return
        p_, e = geo["esq_pata"], 1.5
        # va por encima de los ángulos: corrido hacia afuera el espesor del perfil en las tres caras
        o = _sum(o, _mul(_sum(a, b, c), ex * 2.4 + e_ar))
        col = k.color(P_ESQ, "herraje")
        k.caja(_sum(o, _mul(b, -p_), _mul(c, -p_)), a, b, c, e, p_, p_, col, ComponentLayer.BASE_ALU, "Esquinero")
        k.caja(_sum(o, _mul(a, -p_), _mul(c, -p_)), a, b, c, p_, e, p_, col, ComponentLayer.BASE_ALU, "Esquinero")
        k.caja(_sum(o, _mul(a, -p_), _mul(b, -p_)), a, b, c, p_, p_, e, col, ComponentLayer.BASE_ALU, "Esquinero")
        k.esfera(o, 12, col, ComponentLayer.BASE_ALU, "Esquinero")
        for f1, f2 in ((0.35, 0.72), (0.72, 0.35)):     # dos remaches por ala
            _remache(k, _sum(o, _mul(a, e), _mul(b, -p_ * f1), _mul(c, -p_ * f2)), a, b, c)
            _remache(k, _sum(o, _mul(b, e), _mul(a, -p_ * f1), _mul(c, -p_ * f2)), b, a, c)
            _remache(k, _sum(o, _mul(c, e), _mul(a, -p_ * f1), _mul(b, -p_ * f2)), c, a, b)

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
            hundir = (geo.get("cazoleta") or {}).get("prof", 0.0)
            for i, (cx, cy) in enumerate(geo["ruedas"]):
                tipo = _tipo_i(geo, i)
                _rueda(k, geo, (0, 0, lift_pie), (1, 0, 0), (0, 1, 0), (0, 0, -1), cx, cy, tipo == "freno", ex,
                       tipo, hundir)
        if not (geo["horizontal"] or geo["frontal"]):
            for cx, cy in geo["pies"]:
                d = geo["pie_d"]
                k.cilindro((cx, cy, lift_pie - ex * 2.2 - geo["pie_h"] / 2), (0, 0, 1), (1, 0, 0), (0, 1, 0), d / 2,
                           geo["pie_h"], k.color(P_RUEDAS, "rueda"), ComponentLayer.BASE_ALU, "Pie")

    # Bandejas (ya en coordenadas del mundo)
    if k.visible(P_CUERPO) and ver_fija and op.resaltar_que != "perfiles" and \
            not (op.resaltar_que == "junta" and op.vista_parte == "fija"):
        for i, b in enumerate(geo["bandejas"]):
            col = "resalte" if op.resaltar_que == "bandeja" else k.color(P_CUERPO, "wall")
            k.caja((b["cx"] - b["ancho"] / 2, b["cy"] - b["fondo"] / 2, b["z"] + ex * 0.6), (1, 0, 0), (0, 1, 0),
                   (0, 0, 1), b["ancho"], b["fondo"], b["esp"], col,
                   ComponentLayer.INTERNAL_DIVIDERS, f"Bandeja {i + 1}", mundo=True)

    # Forro interior por cara (alfombra o espuma), se mueve con su tapa
    if geo.get("forro") and op.interior and op.paso >= 99 and not op.resaltar_que and not op.vista_parte:
        resaltar = {x.strip() for x in op.resaltar_interior.split(",") if x.strip()}
        for pz in geo["forro"]:
            col = "resalte" if "forro" in resaltar else f"forro_{pz['tipo']}"
            for x0, y0, z0, x1, y1, z1 in pz.get("celdas") or [pz["caja"]]:   # partida alrededor de los huecos
                k.caja((x0, y0, z0 + desplaz.get(pz["grupo"], 0.0)), (1, 0, 0), (0, 1, 0), (0, 0, 1),
                       x1 - x0, y1 - y0, z1 - z0, col, ComponentLayer.INTERNAL_DIVIDERS, pz["nombre"])

    # Interiores (equipos, espuma, cajones, rack), en coordenadas del mundo
    if geo.get("interior") is not None and op.interior and op.paso >= 99 and not op.resaltar_que \
            and not op.vista_parte:
        _interior_3d(k, geo["interior"], lift)

    pts = [p for f in k.caras for p in f.vertices] or [Point3D(0, 0, 0)]
    caja = (Point3D(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)),
            Point3D(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return Malla3D(faces=k.caras, segments=k.segmentos, bounding_box=caja, rotulos=k.rotulos, calados=k.calados,
                   solidos=k.solidos)


_COLOR_INTERIOR = {"equipo": "equipo", "rack": "equipo", "riel": "aluminio", "corredera": "aluminio",
                   "cajon": "cajon", "suplemento": "cajon", "caratula": "herraje"}


def _interior_3d(k: _Constructor, interior, lift: float = 0.0) -> None:
    """Sólidos del interior (interiores.py): cajas, y la espuma con sus calados. Lo que
    está dentro de una tapa (espuma de la tapa, un equipo que entra en ella) se mueve con ella."""
    capa = ComponentLayer.INTERNAL_DIVIDERS
    arriba = k.girar((0.0, 0.0, 1.0))   # hacia la tapa 1, en el mundo
    resaltar = {x.strip() for x in k.op.resaltar_interior.split(",") if x.strip()}

    def mover(c):
        t = interior.en_tapa(c) * interior.signo_tapa * lift
        if not t:
            return c
        return type(c)(c.x0 + arriba[0] * t, c.y0 + arriba[1] * t, c.z0 + arriba[2] * t,
                       c.x1 + arriba[0] * t, c.y1 + arriba[1] * t, c.z1 + arriba[2] * t)
    for so in interior.solidos:
        if so.tipo in ("espuma", "bandeja"):
            continue   # la espuma se dibuja con sus calados; las bandejas ya están
        c = mover(so.caja)
        color = _COLOR_INTERIOR.get(so.tipo, "equipo")
        if so.tipo == "rack" and so.nombre.endswith("(frente)"):
            color = "rack_frente"
        if so.tipo in resaltar:
            color = "resalte"
        k.caja((c.x0, c.y0, c.z0), (1, 0, 0), (0, 1, 0), (0, 0, 1), c.med(0), c.med(1), c.med(2), color, capa,
               so.nombre, mundo=True)
    for bl in interior.espumas:
        _espuma_3d(k, bl, capa, mover(bl.caja), "resalte" if "espuma" in resaltar else "espuma")


def _espuma_3d(k: _Constructor, bl, capa: int, c=None, color: str = "espuma") -> None:
    """Bloque de espuma como relieve: cada celda de la grilla que forman los calados tiene su
    propia altura (el fondo del calado o la cara abierta del bloque)."""
    c, a = c or bl.caja, bl.eje
    ua, va = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[a]
    Wu, Wv, L = c.med(ua), c.med(va), c.med(a)
    sg = 1.0 if bl.abre_arriba else -1.0

    def P(u: float, v: float, d: float) -> Point3D:
        q = [0.0, 0.0, 0.0]
        q[ua], q[va] = c.lo(ua) + u, c.lo(va) + v
        q[a] = c.lo(a) + d if bl.abre_arriba else c.hi(a) - d
        return Point3D(q[0], q[1], q[2])

    def eje(i: int, signo: float) -> Vec:
        n = [0.0, 0.0, 0.0]
        n[i] = signo
        return (n[0], n[1], n[2])

    def cara(verts, normal):
        k.caras.append(PolygonFace3D(vertices=tuple(verts), normal=normal, color_group=color,
                                     label=bl.nombre, layer_order=capa))

    # Los calados con forma van en escalones: la grilla sale de los vértices del contorno
    # simplificado (en 3D alcanza con eso; el DXF lleva el contorno exacto).
    from .formas_espuma import dentro, simplificar
    formas = {id(b): [simplificar(p, 2.0) for p in b["contorno"]] for b in bl.bolsillos if b.get("contorno")}
    us_, vs_ = {0.0, Wu}, {0.0, Wv}
    for b in bl.bolsillos:
        if id(b) in formas:
            us_ |= {round(x, 0) for p in formas[id(b)] for x, _ in p}
            vs_ |= {round(y, 0) for p in formas[id(b)] for _, y in p}
        else:
            us_ |= {round(b["u0"], 3), round(b["u1"], 3)}
            vs_ |= {round(b["v0"], 3), round(b["v1"], 3)}
    us = sorted(x for x in us_ if 0.0 <= x <= Wu)
    vs = sorted(y for y in vs_ if 0.0 <= y <= Wv)
    nu, nv = len(us) - 1, len(vs) - 1
    alto = [[L] * nv for _ in range(nu)]
    for i in range(nu):
        for j in range(nv):
            um, vm = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
            for b in bl.bolsillos:
                f = formas.get(id(b))
                if (dentro(f, um, vm) if f else (b["u0"] < um < b["u1"] and b["v0"] < vm < b["v1"])):
                    alto[i][j] = min(alto[i][j], b["fondo"])
    # Para que el bloque sea un sólido cerrado (STEP), el fondo va partido en las celdas
    # de la grilla y cada pared lleva vértices en todas las alturas que se juntan en sus
    # aristas verticales: así cada arista la comparten exactamente dos caras.
    H = lambda i, j: alto[i][j] if 0 <= i < nu and 0 <= j < nv and alto[i][j] > 0.01 else 0.0
    desde = len(k.caras)

    def alturas(i: int, j: int, lo_: float, hi_: float) -> List[float]:
        """Alturas de las celdas que tocan el nudo (i, j) de la grilla, entre lo_ y hi_."""
        hs = {H(i - 1, j - 1), H(i, j - 1), H(i - 1, j), H(i, j), 0.0}
        return sorted(h for h in hs if lo_ + 0.01 < h < hi_ - 0.01)

    def pared(n0, n1, punto, lo_, hi_, normal):
        """Pared vertical entre los nudos n0 y n1 (de lo_ a hi_), subiendo por n1 y bajando por n0."""
        verts = [punto(n0, lo_), punto(n1, lo_)]
        verts += [punto(n1, h) for h in alturas(*n1, lo_, hi_)]
        verts += [punto(n1, hi_), punto(n0, hi_)]
        verts += [punto(n0, h) for h in reversed(alturas(*n0, lo_, hi_))]
        cara(verts, normal)

    nudo = lambda nd, d: P(us[nd[0]], vs[nd[1]], d)
    for i in range(nu):
        for j in range(nv):
            h = H(i, j)
            if h > 0:
                cara([P(us[i], vs[j], 0), P(us[i + 1], vs[j], 0), P(us[i + 1], vs[j + 1], 0), P(us[i], vs[j + 1], 0)],
                     eje(a, -sg))
                cara([P(us[i], vs[j], h), P(us[i + 1], vs[j], h), P(us[i + 1], vs[j + 1], h), P(us[i], vs[j + 1], h)],
                     eje(a, sg))
    for i in range(nu + 1):          # paredes perpendiculares a u
        for j in range(nv):
            h0, h1 = H(i - 1, j), H(i, j)
            if abs(h0 - h1) > 0.01:
                pared((i, j), (i, j + 1), nudo, min(h0, h1), max(h0, h1), eje(ua, 1.0 if h0 > h1 else -1.0))
    for j in range(nv + 1):          # paredes perpendiculares a v
        for i in range(nu):
            h0, h1 = H(i, j - 1), H(i, j)
            if abs(h0 - h1) > 0.01:
                pared((i, j), (i + 1, j), nudo, min(h0, h1), max(h0, h1), eje(va, 1.0 if h0 > h1 else -1.0))
    k.cerrar(desde, color, bl.nombre)


def _rect_redondeado(x0: float, y0: float, x1: float, y1: float, r: float, por_esquina: int = 8):
    """Contorno (antihorario) de un rectángulo con esquinas de radio r, como rect_redondeado()."""
    r = max(0.0, min(r or 0.0, (x1 - x0) / 2 - 0.01, (y1 - y0) / 2 - 0.01))
    if r <= 0.5:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(por_esquina + 1):
            a = math.radians(a0 + 90 * i / por_esquina)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _tipo_i(geo: dict, i: int) -> str:
    tipos = geo.get("ruedas_tipos") or []
    return tipos[i] if i < len(tipos) else ("freno" if i < geo["rueda_frenos"] else "giratoria")


def _rueda(k: _Constructor, geo: dict, o: Vec, u: Vec, v: Vec, fuera: Vec, cx: float, cy: float,
           freno: bool, ex: float, tipo: str = "", hundir: float = 0.0) -> None:
    """rueda_3d(): placa, giratorio, horquilla, rueda y freno, hacia `fuera` desde o + cx·u + cy·v.

    `tipo` "fija" dibuja la rueda sin giratorio, con el eje bajo el centro de la placa; las medidas
    de cada tipo salen de geo["rueda_dims"]. `hundir` mete la placa dentro del case (cazoleta)."""
    pl, d = geo["rueda_placa"], geo["rueda_diametro"]
    alto = geo["rueda_alto"] or (d + 25)
    dims = (geo.get("rueda_dims") or {}).get(tipo or ("freno" if freno else "giratoria"))
    if dims and geo["rueda_alto"]:
        d, alto = dims[0], dims[1]
    fija = tipo == "fija"
    r = d / 2
    hf = alto - d
    base = _sum(o, _mul(u, cx), _mul(v, cy), _mul(fuera, ex * 2.2 - hundir))
    L = lambda a, b, c: _sum(base, _mul(u, a), _mul(v, b), _mul(fuera, c))   # coords de rueda_3d
    resalta = k.op.paso < 99 and k.op.paso == P_RUEDAS
    c_placa = "resalte" if resalta else "rueda_placa"
    c_horq = "resalte" if resalta else "rueda_horq"
    k.caja(L(-pl[0] / 2, -pl[1] / 2, 0), u, v, fuera, pl[0], pl[1], 4, c_placa, ComponentLayer.BASE_ALU, "Rueda")
    nombre = "Rueda fija" if fija else "Rueda"
    za = 4
    if not fija:
        hg = max(hf - 4, 1) * 0.35
        k.cilindro(L(0, 0, 4 + hg / 2), fuera, u, v, pl[1] * 0.3, hg, c_horq, ComponentLayer.BASE_ALU, "Rueda")
    eje = 0.0 if fija else r * 0.35          # la giratoria lleva el eje corrido (avance)
    ze = alto - r
    for s_ in (-1, 1):   # horquilla: de la placa al eje (hull de rueda_3d)
        y0, y1 = s_ * r * 0.55 - 1.5, s_ * r * 0.55 + 1.5
        xa0, xa1 = (-r * 0.45, r * 0.45) if fija else (-r * 0.2, r * 0.4)
        k.hexaedro([L(xa0, y0, za), L(xa1, y0, za), L(xa1, y1, za), L(xa0, y1, za),
                    L(eje - 6, y0, ze + 6), L(eje + 6, y0, ze + 6), L(eje + 6, y1, ze + 6),
                    L(eje - 6, y1, ze + 6)], c_horq, ComponentLayer.BASE_ALU, nombre)
    k.cilindro(L(eje, 0, alto - r), v, u, fuera, r, r * 0.8, "rueda", ComponentLayer.BASE_ALU, nombre)
    if freno:
        k.caja(L(eje + r * 0.7, -6, alto - r * 1.4), u, v, fuera, 10, 12, 6, "freno",
               ComponentLayer.BASE_ALU, "Freno")


# ---- herrajes con su forma (coordenadas del panel: u ancho, v alto, n hacia adentro) ----

def _remache(k: _Constructor, centro: Vec, eje: Vec, a: Vec, b: Vec, r: float = 2.6) -> None:
    """Cabeza de remache: disco bajo apoyado en `centro`, hacia `eje`."""
    k.cilindro(_sum(centro, _mul(eje, 0.5)), eje, a, b, r, 1.0, "remache", ComponentLayer.BASE_ALU, "Remache", lados=8)


def _cierre_mariposa(k: _Constructor, o: Vec, u: Vec, v: Vec, n: Vec, x: float, ys, s: float, col: str) -> None:
    """Cierre mariposa embutido: placa con cazoleta y la mariposa encima."""
    fuera = _mul(n, -1)
    y0, y1 = min(ys), max(ys)
    a = 50.0
    P = lambda i, j, h: _sum(o, _mul(u, i), _mul(v, j), _mul(fuera, s + h))
    k.caja(P(x - a / 2, y0, 1.5), u, v, n, a, y1 - y0, 1.5, col, ComponentLayer.BASE_ALU, "Cierre")
    yc = y0 + (y1 - y0) * 0.42
    k.cilindro(P(x, yc, 3.5), fuera, u, v, a * 0.34, 4, "herraje", ComponentLayer.BASE_ALU, "Cierre", lados=20)
    # mariposa: dos alas en rombo sobre el eje
    for sx in (-1, 1):
        k.hexaedro([P(x, yc - 4, 5.5), P(x + sx * a * 0.3, yc - 2, 5.5), P(x + sx * a * 0.3, yc + 2, 5.5), P(x, yc + 4, 5.5),
                    P(x, yc - 4, 8), P(x + sx * a * 0.3, yc - 2, 7.5), P(x + sx * a * 0.3, yc + 2, 7.5), P(x, yc + 4, 8)],
                   col, ComponentLayer.BASE_ALU, "Cierre")
    k.cilindro(P(x, yc, 8.5), fuera, u, v, 5, 1.5, col, ComponentLayer.BASE_ALU, "Cierre", lados=12)


def _gancho_cierre(k: _Constructor, o: Vec, u: Vec, v: Vec, n: Vec, x: float, ys, s: float, col: str) -> None:
    """Contraparte del cierre en la tapa: placa con el gancho."""
    fuera = _mul(n, -1)
    y0, y1 = min(ys), max(ys)
    a = 44.0
    P = lambda i, j, h: _sum(o, _mul(u, i), _mul(v, j), _mul(fuera, s + h))
    k.caja(P(x - a / 2, y0, 1.5), u, v, n, a, y1 - y0, 1.5, col, ComponentLayer.BASE_ALU, "Cierre")
    ym = (y0 + y1) / 2
    k.caja(P(x - a * 0.25, ym - 4, 6), u, v, n, a * 0.5, 8, 4.5, col, ComponentLayer.BASE_ALU, "Cierre")
    for sx in (-1, 1):
        k.caja(P(x + sx * a * 0.25 - 2, ym - 5, 6), u, v, n, 4, 10, 4.5, "herraje", ComponentLayer.BASE_ALU, "Cierre")


def _bisagra(k: _Constructor, o: Vec, u: Vec, v: Vec, n: Vec, x: float, ys, d: float, s: float, col: str) -> None:
    """Bisagra: hoja atornillada al panel y el nudo (eje) en la línea de cierre."""
    fuera = _mul(n, -1)
    y0, y1 = min(ys), max(ys)
    a = 60.0
    P = lambda i, j, h: _sum(o, _mul(u, i), _mul(v, j), _mul(fuera, s + h))
    k.caja(P(x - a / 2, y0, 1.5), u, v, n, a, y1 - y0, 1.5, col, ComponentLayer.BASE_ALU, "Bisagra")
    yn = y1 if d > 0 else y0
    k.cilindro(P(x, yn, 4.5), u, v, fuera, 4.5, a * 0.9, col, ComponentLayer.BASE_ALU, "Bisagra", lados=12)
    for i in (-0.3, 0.3):
        _remache(k, P(x + a * i, (y0 + y1) / 2, 1.5), fuera, u, v, 2.4)


def _manija_embutida(k: _Constructor, o: Vec, u: Vec, v: Vec, n: Vec, x0: float, y0: float, x1: float, y1: float,
                     col: str) -> None:
    """Manija embutida: reborde alrededor del calado, cubeta hacia adentro y el asa (a lo largo
    del lado más largo del calado)."""
    if y1 - y0 > x1 - x0:
        _manija_embutida(k, o, v, u, n, y0, x0, y1, x1, col)
        return
    fuera = _mul(n, -1)
    P = lambda i, j, h: _sum(o, _mul(u, i), _mul(v, j), _mul(fuera, h))
    ala, e, prof = 10.0, 1.5, 38.0
    for a0, b0, aw, bh in ((x0 - ala, y0 - ala, x1 - x0 + 2 * ala, ala), (x0 - ala, y1, x1 - x0 + 2 * ala, ala),
                           (x0 - ala, y0, ala, y1 - y0), (x1, y0, ala, y1 - y0)):
        k.caja(P(a0, b0, 2), u, v, n, aw, bh, 2, col, ComponentLayer.BASE_ALU, "Manija")
    for a0, b0, aw, bh in ((x0, y0, x1 - x0, e), (x0, y1 - e, x1 - x0, e), (x0, y0, e, y1 - y0), (x1 - e, y0, e, y1 - y0)):
        k.caja(P(a0, b0, 0), u, v, n, aw, bh, prof, "plato", ComponentLayer.BASE_ALU, "Manija")
    k.caja(_sum(P(x0, y0, 0), _mul(n, prof - e)), u, v, n, x1 - x0, y1 - y0, e, "plato", ComponentLayer.BASE_ALU, "Manija")
    # asa: barra a lo ancho, arriba de la cubeta, con sus dos soportes
    ya = y1 - (y1 - y0) * 0.3
    largo = (x1 - x0) * 0.8
    k.cilindro(_sum(P((x0 + x1) / 2, ya, 0), _mul(n, 8)), u, v, fuera, 6, largo, col, ComponentLayer.BASE_ALU,
               "Manija", lados=12)
    for xs_ in ((x0 + x1) / 2 - largo / 2, (x0 + x1) / 2 + largo / 2 - 6):
        k.caja(_sum(P(xs_, ya - 6, 0), _mul(n, 2)), u, v, n, 6, 12, 12, col, ComponentLayer.BASE_ALU, "Manija")


def _manija_superficie(k: _Constructor, o: Vec, u: Vec, v: Vec, n: Vec, x: float, y: float, ancho: float,
                       col: str) -> None:
    """Asa de superficie: dos soportes atornillados y la barra entre ellos."""
    fuera = _mul(n, -1)
    P = lambda i, j, h: _sum(o, _mul(u, i), _mul(v, j), _mul(fuera, h))
    for xs_ in (x - ancho / 2, x + ancho / 2 - 22):
        k.caja(P(xs_, y - 15, 3), u, v, n, 22, 30, 3, col, ComponentLayer.BASE_ALU, "Manija")
        k.caja(P(xs_ + 4, y - 7, 14), u, v, n, 14, 14, 11, col, ComponentLayer.BASE_ALU, "Manija")
    k.cilindro(P(x, y, 10), u, v, fuera, 7, ancho - 30, "rueda", ComponentLayer.BASE_ALU, "Manija", lados=14)


def _herraje_manual(k: _Constructor, geo: dict, o: Vec, u: Vec, v: Vec, n: Vec, h, resalte: Optional[str],
                    ex: float) -> None:
    """Herraje puesto a mano que no sale de un calado ni de una marca de cierre: piezas de
    superficie, pies, ruedas, asas de superficie y placas de logo."""
    fuera = _mul(n, -1)
    P = lambda i, j, z: _sum(o, _mul(u, i), _mul(v, j), _mul(fuera, z))
    x0, y0 = h.px - h.pw / 2, h.py - h.ph / 2
    col = resalte or "herraje"
    capa = ComponentLayer.BASE_ALU
    if h.forma == "rueda":
        d = h.datos
        g2 = dict(geo, rueda_placa=list(d.get("placa") or [h.pw, h.ph]),
                  rueda_diametro=float(d.get("diametro", 100)), rueda_alto=float(d.get("alto", 0)),
                  rueda_dims=None)
        if h.giro_panel % 180:
            _rueda(k, g2, o, v, u, fuera, h.py, h.px, bool(d.get("freno")), ex, "fija" if d.get("tipo") == "fija" else "")
        else:
            _rueda(k, g2, o, u, v, fuera, h.px, h.py, bool(d.get("freno")), ex, "fija" if d.get("tipo") == "fija" else "")
    elif h.forma == "pie":
        alto = float(h.datos.get("alto", 15))
        k.cilindro(P(h.px, h.py, alto / 2), fuera, u, v, h.pw / 2, alto, col, capa, h.nombre, lados=16)
    elif h.forma == "manija_sup":
        if h.pw >= h.ph:
            _manija_superficie(k, o, u, v, n, h.px, h.py, h.pw, col)
        else:
            _manija_superficie(k, o, v, u, n, h.py, h.px, h.ph, col)
    elif h.forma == "logo":
        grabado = h.fila.modo == "grabado"
        z = 0.2
        if not grabado:
            k.caja(P(x0, y0, 0), u, v, fuera, h.pw, h.ph, 1.5, resalte or "cierre", capa, h.nombre)
            z = 1.6
        trazo = max(min(h.pw, h.ph) / 120, 0.6)
        color_t = resalte or ("plato" if grabado else "herraje")
        for linea in h.lineas_panel:
            for (a, b), (c, d) in zip(linea, linea[1:]):
                L = math.hypot(c - a, d - b)
                if L < 1e-6:
                    continue
                # cada trazo es una barra fina sobre la cara (un sólido, también para el STEP)
                tx, ty = (c - a) / L, (d - b) / L
                dir_ = _sum(_mul(u, tx), _mul(v, ty))
                perp = _sum(_mul(u, -ty), _mul(v, tx))
                k.caja(_sum(P(a, b, z), _mul(perp, -trazo / 2)), dir_, perp, fuera, L, trazo, 0.3, color_t, capa,
                       h.nombre)
    else:
        alto = 8.0 if h.categoria != "tope" else 12.0
        k.caja(P(x0, y0, 0), u, v, fuera, h.pw, h.ph, alto, col, capa, h.nombre)
