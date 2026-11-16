"""Vista 3D de las formas de case de formas.py (rack inclinado, funda de rack, baúl plegable).

formas.py ya deja cada pieza ubicada en el mundo (paneles con su marco o, u, v, n, ángulos
de arista, perfiles de cierre, esquineros, cierres y bisagras), así que acá sólo se dibujan.
Cada pieza tiene un grupo de movimiento: "tapa" se levanta al abrir (sobre la normal del
plano de cierre) y, en el baúl plegable, cada pared gira sobre su bisagra con
vista_parte = "plegado". Admite los mismos parámetros que las láminas del instructivo
(paso, explotar, abrir_tapa, etiquetas).
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from .geometria import (Malla3D, Opciones3D, Rotulo, _bisagra, _cierre_mariposa, _Constructor, _ejes_rotulo,
                        _gancho_cierre, _interior_3d, _manija_embutida, _manija_superficie, _mul,
                        _rect_redondeado, _remache, _rueda, _sum, _COLOR_INTERIOR)
from .malla import ComponentLayer, Point3D
from .modelo import ResultadoTaller
from .formas import F_AROS, F_CIERRES, F_CUERPO, F_ESQ, F_MANIJAS, F_RUEDAS

Vec = Tuple[float, float, float]


def malla_formas(res: ResultadoTaller, op: Optional[Opciones3D] = None) -> Malla3D:
    op = op or Opciones3D()
    geo = res.valores["geo"]
    k = _Constructor(lambda p: p, lambda n: n, op)
    ex = op.explotar
    plegado = op.vista_parte == "plegado" and geo.get("pliegue")
    paneles = {p.id: p for p in res.paneles}
    calados: Dict[str, list] = {}
    for c in res.calados:
        calados.setdefault(c.panel, []).append(c)
    marcas: Dict[str, list] = {}
    for m in res.marcas:
        marcas.setdefault(m.panel, []).append(m)

    # cómo se mueve cada grupo: traslación y giro (centro, eje, ángulo)
    mov: Dict[str, Tuple[Vec, Optional[Tuple[Vec, Vec, float]]]] = {}
    dir_tapa = (geo.get("mover") or {}).get("tapa")
    if dir_tapa:
        lift = op.abrir_tapa + (ex * 2.2 if ex > 0 else 0)
        mov["tapa"] = (_mul(dir_tapa, lift), None)
    if plegado:
        for pl in geo["pliegue"]:
            mov[pl["mueve"]] = ((0.0, 0.0, 0.0), (tuple(pl["centro"]), tuple(pl["eje"]), math.radians(90)))
        # la tapa queda apoyada sobre las paredes plegadas
        dz = geo["alto_plegado"] - geo["z_cierre"] + geo["cierre_m_alto"] + (op.abrir_tapa if op.abrir_tapa else 0)
        mov["tapa"] = ((0.0, 0.0, dz), None)

    def poner(grupo: str) -> Vec:
        d, giro = mov.get(grupo, ((0.0, 0.0, 0.0), None))
        k.giro = giro
        return d

    def color(paso: int, c: str) -> str:
        return k.color(paso, c)

    # ---- paneles ----
    for col in geo["colocaciones"]:
        p = paneles[col["id"]]
        paso = col.get("paso", F_CUERPO)
        if not k.visible(paso):
            continue
        d = poner(col.get("mueve", col["grupo"]))
        u, vv, n = col["u"], col["v"], col["n"]
        o = _sum(col["o"], d, _mul(n, -ex))
        tp = col.get("esp", geo["espesor"])
        c_ = color(paso, "lid" if col["grupo"] == "tapa" else "base")
        capa = ComponentLayer.LID_WALLS if col["grupo"] == "tapa" else ComponentLayer.OUTER_BASE_WALLS
        d_c, d_s = len(k.caras), len(k.solidos)
        if col.get("contorno"):
            k.prisma(o, u, vv, n, col["contorno"], tp, c_, capa, p.nombre)
        else:
            k.caja(o, u, vv, n, p.ancho, col.get("alto_3d", p.alto), tp, c_, capa, p.nombre)
        k.marcar(d_c, d_s, p.id, (geo.get("colores_paneles") or {}).get(p.id, "") if c_ != "resalte" else "")
        sol = k.solidos[-1]
        fuera = _mul(n, -1)
        if col["id"] in op.etiquetas:
            cx, cy = p.ancho / 2, (col.get("alto_3d", p.alto)) / 2
            if col.get("contorno"):
                cy = min(y for _, y in col["contorno"] if y > 0) / 2
            tam = max(min(min(p.ancho, p.alto) * 0.3, 60), 12)
            for nn, h in ((k.girar(fuera), -0.5), (k.girar(n), tp + 0.5)):
                centro = _sum(o, _mul(u, cx), _mul(vv, cy), _mul(n, h))
                k.rotulos.append(Rotulo(op.etiquetas[col["id"]], k._p(centro, False), nn, tam, *_ejes_rotulo(nn)))
        for c in calados.get(p.id, []):
            x0, x1, y0, y1 = c.cx - c.ancho / 2, c.cx + c.ancho / 2, c.cy - c.alto / 2, c.cy + c.alto / 2
            k.contorno([_sum(o, _mul(fuera, 0.2), _mul(u, a), _mul(vv, b)) for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))],
                       "profile", f"{p.nombre}: {c.tipo}")
            k.calados.append((p.nombre, [k._p(_sum(o, _mul(u, a), _mul(vv, b)), False)
                                         for a, b in _rect_redondeado(x0, y0, x1, y1, c.radio)]))
            sol.agujeros.append(k.calados[-1][1])
            if c.tipo == "manija" and k.visible(F_MANIJAS):
                _manija_embutida(k, o, u, vv, n, x0, y0, x1, y1, color(F_MANIJAS, "herraje"))
        for m in marcas.get(p.id, []):
            if m.tipo == "manija_sup" and k.visible(F_MANIJAS):
                _manija_superficie(k, o, u, vv, n, m.x, m.y, m.ancho, color(F_MANIJAS, "herraje"))
    k.giro = None

    # ---- perfiles de cierre, suplementos y bisagras de piano ----
    for b in geo["bloques"]:
        if not k.visible(b["paso"]):
            continue
        d = poner(b["mueve"])
        k.caja(_sum(b["o"], d), b["u"], b["v"], b["n"], b["a"], b["b"], b["c"],
               k.color_perfil(b["paso"], b["color"]) if b["paso"] == F_AROS else color(b["paso"], b["color"]),
               ComponentLayer.BASE_ALU, b["etiqueta"])
    k.giro = None

    # ---- ángulos de arista ----
    e_ar, ala = geo["arista_esp"], geo["ala"]
    for a_ in geo["aristas"]:
        if not k.visible(a_["paso"]):
            continue
        d = poner(a_["mueve"])
        a, b, c = a_["a"], a_["b"], a_["c"]
        o = _sum(a_["o"], d, _mul(_sum(a, b), ex * 1.7))
        L = a_["L"]
        col = color(a_["paso"], "aluminio")
        k.caja(_sum(o, _mul(b, -ala)), a, b, c, e_ar, ala + e_ar, L, col, ComponentLayer.BASE_ALU, "Ángulo de arista")
        k.caja(_sum(o, _mul(a, -ala)), a, b, c, ala + e_ar, e_ar, L, col, ComponentLayer.BASE_ALU, "Ángulo de arista")
        n_r = max(2, int(L // 150) + 1)
        for i in range(n_r):
            zc_ = 25 + (L - 50) * i / max(n_r - 1, 1)
            _remache(k, _sum(o, _mul(a, e_ar), _mul(b, -ala / 2), _mul(c, zc_)), a, b, c)
            _remache(k, _sum(o, _mul(b, e_ar), _mul(a, -ala / 2), _mul(c, zc_)), b, a, c)
    k.giro = None

    # ---- esquineros ----
    if k.visible(F_ESQ):
        p_, e = geo["esq_pata"], 1.5
        for q in geo["esquineros"]:
            d = poner(q["mueve"])
            a, b, c = q["a"], q["b"], q["c"]
            o = _sum(q["o"], d, _mul(_sum(a, b, c), ex * 2.4 + e_ar))
            col = color(F_ESQ, "herraje")
            k.caja(_sum(o, _mul(b, -p_), _mul(c, -p_)), a, b, c, e, p_, p_, col, ComponentLayer.BASE_ALU, "Esquinero")
            k.caja(_sum(o, _mul(a, -p_), _mul(c, -p_)), a, b, c, p_, e, p_, col, ComponentLayer.BASE_ALU, "Esquinero")
            k.caja(_sum(o, _mul(a, -p_), _mul(b, -p_)), a, b, c, p_, p_, e, col, ComponentLayer.BASE_ALU, "Esquinero")
            k.esfera(o, 12, col, ComponentLayer.BASE_ALU, "Esquinero")
        k.giro = None

    # ---- cierres, ganchos y bisagras ----
    if k.visible(F_CIERRES):
        s_ = geo["cierre_saliente"]
        for h in geo["herrajes"]:
            d = poner(h["mueve"])
            o = _sum(h["o"], d)
            col = color(F_CIERRES, "cierre")
            if h["tipo"] == "cierre":
                _cierre_mariposa(k, o, h["u"], h["v"], h["n"], h["x"], h["ys"], s_, col)
            elif h["tipo"] == "gancho":
                _gancho_cierre(k, o, h["u"], h["v"], h["n"], h["x"], h["ys"], s_, col)
            else:
                _bisagra(k, o, h["u"], h["v"], h["n"], h["x"], h["ys"], h["d"], s_, col)
        k.giro = None

    # ---- ruedas y pies ----
    if k.visible(F_RUEDAS):
        for r in geo["ruedas_abajo"]:
            _rueda(k, geo, r["o"], r["u"], r["v"], (0.0, 0.0, -1.0), r["x"], r["y"], r["freno"], ex,
                   "freno" if r["freno"] else "giratoria")
        for c in geo["pies_abajo"]:
            k.cilindro((c[0], c[1], c[2] - ex * 2.2 - geo["pie_h"] / 2), (0, 0, 1), (1, 0, 0), (0, 1, 0),
                       geo["pie_d"] / 2, geo["pie_h"], color(F_RUEDAS, "rueda"), ComponentLayer.BASE_ALU, "Pie")

    # ---- interior: rieles de rack (en la funda, en el mundo; en el inclinado, sobre la pendiente) ----
    interior = geo.get("interior")
    if interior is not None and op.interior and op.paso >= 99 and not op.resaltar_que and not plegado:
        marco = geo.get("marco_interior")
        if marco is None:
            _interior_3d(k, interior, 0.0)
        else:
            _interior_inclinado(k, interior, marco)

    pts = [p for f in k.caras for p in f.vertices] or [Point3D(0, 0, 0)]
    caja = (Point3D(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)),
            Point3D(max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return Malla3D(faces=k.caras, segments=k.segmentos, bounding_box=caja, rotulos=k.rotulos, calados=k.calados,
                   solidos=k.solidos)


def _interior_inclinado(k: _Constructor, interior, marco: dict) -> None:
    """Los sólidos del rack se calculan en una caja virtual (tapa superior) y acá se pasan al plano
    inclinado: (x, y, z) virtual -> p0 + x·e1 + y·e2 + z·e3."""
    p0, e1, e2, e3 = marco["p0"], marco["e1"], marco["e2"], marco["e3"]
    T = lambda x, y, z: _sum(p0, _mul(e1, x), _mul(e2, y), _mul(e3, z))
    resaltar = {x.strip() for x in k.op.resaltar_interior.split(",") if x.strip()}
    for so in interior.solidos:
        if so.tipo in ("espuma", "bandeja"):
            continue
        c = so.caja
        col = _COLOR_INTERIOR.get(so.tipo, "equipo")
        if so.tipo == "rack" and so.nombre.endswith("(frente)"):
            col = "rack_frente"
        if so.tipo in resaltar:
            col = "resalte"
        v8 = [T(c.x0, c.y0, c.z0), T(c.x1, c.y0, c.z0), T(c.x1, c.y1, c.z0), T(c.x0, c.y1, c.z0),
              T(c.x0, c.y0, c.z1), T(c.x1, c.y0, c.z1), T(c.x1, c.y1, c.z1), T(c.x0, c.y1, c.z1)]
        k.hexaedro(v8, col, ComponentLayer.INTERNAL_DIVIDERS, so.nombre)
