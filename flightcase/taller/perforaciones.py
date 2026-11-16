"""Perforaciones de cada panel para la CNC: los agujeros de remaches y tornillos.

Van en los DXF por pieza y por placa en capas propias (PERFORACIONES para los remaches,
TORNILLOS para los tornillos de madera), aparte del contorno y los calados de la capa 0,
para que el CAM los haga con mecha en lugar de fresa o los apague si se perfora a mano.

De dónde sale cada agujero (coordenadas del panel visto desde afuera, como los calados):

- Ángulos de las aristas y perfiles híbridos: una fila en cada ala, en el medio del ala,
  con la misma cantidad que la lista de materiales (`remache_paso`, 20 mm libres en cada punta).
- Aros de cierre (macho y hembra) y juntas de las tapas de acceso: una fila en el medio de
  la parte del perfil que cubre el panel.
- Esquineros: 1, 2 o 3 agujeros por pata, según los remaches del catálogo.
- Cierres, bisagras, manijas, cazoletas y platos: alrededor del calado o sobre la huella
  del herraje, con la cantidad de remaches del catálogo. Si el artículo del catálogo trae
  `perforaciones` ([[dx, dy], ...] en mm desde el centro del herraje; en cierres y bisagras,
  dy desde la línea de cierre, negativo del lado del cuerpo) se usan esas.
- Herrajes puestos a mano: lo mismo, según su categoría.
- Marco de la base suelta: tornillos para madera.

Los remaches de los perfiles que quedan debajo de un herraje se sacan (el herraje los tapa)
y dos agujeros a menos de 6 mm quedan en uno. Los bulones de las ruedas siguen siendo
calados de la capa 0, como en OpenSCAD.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .modelo import ResultadoTaller

CAPA_REMACHES = "PERFORACIONES"
CAPA_TORNILLOS = "TORNILLOS"
TORNILLO_D = 3.0          # mecha guía para los tornillos de madera del marco de la base
DISTANCIA_MINIMA = 6.0    # dos agujeros más cerca que esto son el mismo

Vec = Tuple[float, float, float]


@dataclass
class Agujero:
    x: float
    y: float
    d: float
    capa: str = CAPA_REMACHES
    origen: str = ""        # "perfil", "esquinero", "cierre", "manija"... (para las pruebas y el CAM)

    def tupla(self) -> tuple:
        return (self.capa, self.x, self.y, self.d)


# ---------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------

def _filas(L: float, paso: float, margen: float = 20.0) -> List[float]:
    """Posiciones a lo largo de un tramo de largo L: las mismas que cuenta la lista de
    materiales (floor((L - 40) / paso) + 1), repartidas entre las dos puntas."""
    if L <= 0:
        return []
    n = math.floor(max(L - 2 * margen, 0) / max(paso, 1)) + 1
    if n == 1:
        return [L / 2]
    return [margen + (L - 2 * margen) * i / (n - 1) for i in range(n)]


def _parejo(n: int, ancho: float) -> List[float]:
    """n posiciones centradas, repartidas en un ancho total `ancho`."""
    if n <= 0:
        return []
    if n == 1:
        return [0.0]
    return [-ancho / 2 + ancho * i / (n - 1) for i in range(n)]


def _lados(cx: float, cy: float, W: float, H: float, n: int) -> List[Tuple[float, float]]:
    """n puntos sobre los lados de un rectángulo W x H centrado, sin tocar las esquinas:
    primero los lados largos, repartidos parejo en cada lado."""
    horiz = W >= H
    largo, corto = (W, H) if horiz else (H, W)
    n_c = round(n * corto / (2 * (largo + corto))) if n >= 4 else 0
    n_l = (n - 2 * n_c) // 2
    resto = n - 2 * n_c - 2 * n_l
    pts: List[Tuple[float, float]] = []

    def lado(k: int, L: float) -> List[float]:
        return [-L / 2 + L * (i + 1) / (k + 1) for i in range(k)]

    for s in (-1, 1):
        k = n_l + (1 if (resto and s == -1) else 0)
        for a in lado(k, largo):
            pts.append((cx + a, cy + s * corto / 2) if horiz else (cx + s * corto / 2, cy + a))
        for a in lado(n_c, corto):
            pts.append((cx + s * largo / 2, cy + a) if horiz else (cx + a, cy + s * largo / 2))
    return pts


def _alrededor(cx: float, cy: float, w: float, h: float, off: float, n: int) -> List[Tuple[float, float]]:
    """n agujeros alrededor de un rectángulo w x h. off > 0: por fuera, en el reborde de un
    calado, sólo sobre los lados (las esquinas del reborde suelen ser redondeadas).
    off < 0: por dentro de la huella de un herraje de superficie, primero las cuatro esquinas."""
    if n <= 0:
        return []
    W, H = w + 2 * off, h + 2 * off
    if W <= 0 or H <= 0:
        return [(cx, cy)]
    if off < 0 and n >= 4:
        esquinas = [(cx + sx * W / 2, cy + sy * H / 2) for sx in (-1, 1) for sy in (-1, 1)]
        return esquinas + _lados(cx, cy, W, H, n - 4)
    return _lados(cx, cy, W, H, n)


def _rotar(dx: float, dy: float, giro: int) -> Tuple[float, float]:
    a = (int(giro) // 90) % 4
    return ((dx, dy), (-dy, dx), (-dx, -dy), (dy, -dx))[a]


def _lista_perforaciones(datos: Dict[str, Any]) -> Optional[List[Tuple[float, float]]]:
    v = datos.get("perforaciones") if datos else None
    if not isinstance(v, (list, tuple)):
        return None
    out = []
    for q in v:
        try:
            out.append((float(q[0]), float(q[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sum(*vs: Sequence[float]) -> Vec:
    return tuple(sum(c) for c in zip(*vs))  # type: ignore[return-value]


def _mul(v: Sequence[float], k: float) -> Vec:
    return (v[0] * k, v[1] * k, v[2] * k)


# ---------------------------------------------------------------------------
# Paneles con contorno (trapecios del rack inclinado)
# ---------------------------------------------------------------------------

def _poligono(pan) -> List[Tuple[float, float]]:
    c = getattr(pan, "contorno", None)
    return list(c) if c else [(0.0, 0.0), (pan.ancho, 0.0), (pan.ancho, pan.alto), (0.0, pan.alto)]


def _dentro(pan, x: float, y: float, r: float = 0.0) -> bool:
    """El punto está dentro del panel y a `r` o más de cada canto."""
    pts = _poligono(pan)
    n = len(pts)
    adentro = False
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            adentro = not adentro
    if not adentro:
        return False
    return all(_dist_segmento(x, y, pts[i], pts[(i + 1) % n]) >= r - 1e-6 for i in range(n)) if r > 0 else True


def _dist_segmento(x: float, y: float, p0: Tuple[float, float], p1: Tuple[float, float]) -> float:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L2 = dx * dx + dy * dy
    k = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - p0[0]) * dx + (y - p0[1]) * dy) / L2))
    return math.hypot(x - p0[0] - k * dx, y - p0[1] - k * dy)


def _tramo_dentro(pan, p0: Tuple[float, float], p1: Tuple[float, float]) -> Optional[Tuple[float, float]]:
    """La parte más larga del segmento p0-p1 que cae dentro del panel, como (t0, t1) de 0 a 1."""
    pts = _poligono(pan)
    n = len(pts)
    ts = [0.0, 1.0]
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = ((x0 - p0[0]) * ey - (y0 - p0[1]) * ex) / den
        u = ((x0 - p0[0]) * dy - (y0 - p0[1]) * dx) / den
        if 0 < t < 1 and -1e-9 <= u <= 1 + 1e-9:
            ts.append(t)
    ts.sort()
    mejor = None
    for a, b in zip(ts, ts[1:]):
        m = (a + b) / 2
        if b - a > 1e-6 and _dentro(pan, p0[0] + dx * m, p0[1] + dy * m):
            if mejor is None or b - a > mejor[1] - mejor[0]:
                mejor = (a, b)
    return mejor


def _normal_canto(pan, x: float, y: float) -> Tuple[float, float]:
    """Normal hacia afuera del canto del contorno más cercano al punto."""
    pts = _poligono(pan)
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    i = min(range(n), key=lambda k: _dist_segmento(x, y, pts[k], pts[(k + 1) % n]))
    (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
    L = math.hypot(x1 - x0, y1 - y0) or 1.0
    tx, ty = (x1 - x0) / L, (y1 - y0) / L
    return (ty, -tx) if area > 0 else (-ty, tx)


# ---------------------------------------------------------------------------
# Perfiles de las formas (formas.py): aristas, esquineros y aros de geo
# ---------------------------------------------------------------------------

def _perfiles_formas(geo: Dict[str, Any], paneles: Dict[str, Any], perfil: Dict[str, List[Agujero]],
                     d_rem: float, paso: float) -> None:
    """Las formas guardan sus perfiles como piezas 3D (aristas en L, esquineros y bloques de los
    aros y bisagras de piano): cada agujero se ubica sobre el panel que cubre el perfil."""
    cols = [c for c in geo["colocaciones"] if c["id"] in paneles]
    ala, p_ = geo["ala"], geo["esq_pata"]
    d_ar = ala / 2

    def local(c, p: Sequence[float]) -> Tuple[float, float, float]:
        rel = _sum(p, _mul(c["o"], -1))
        return _dot(rel, c["u"]), _dot(rel, c["v"]), _dot(rel, c["n"])

    def proyectar(p: Vec, fuera: Vec, origen: str) -> None:
        mejor = None
        for c in cols:
            if _dot(c["n"], fuera) > -0.99:
                continue
            x, y, prof = local(c, p)
            if prof > 0.5 or prof < -40 or not _dentro(paneles[c["id"]], x, y):
                continue
            if mejor is None or abs(prof) < abs(mejor[3]):
                mejor = (c["id"], x, y, prof)
        if mejor is not None:
            perfil[mejor[0]].append(Agujero(mejor[1], mejor[2], d_rem, CAPA_REMACHES, origen))

    for ar in geo.get("aristas") or []:
        o, a, b, c, L = ar["o"], ar["a"], ar["b"], ar["c"], ar["L"]
        if L < 30:
            continue
        for z in _filas(L, paso):
            base = _sum(o, _mul(c, z))
            proyectar(_sum(base, _mul(b, -d_ar)), a, "perfil")
            if not ar.get("solo_a"):
                proyectar(_sum(base, _mul(a, -d_ar)), b, "perfil")

    fr = [(0.35, 0.72), (0.72, 0.35)]
    for e in geo.get("esquineros") or []:
        o, a, b, c = e["o"], e["a"], e["b"], e["c"]
        for f1, f2 in fr:
            proyectar(_sum(o, _mul(b, -p_ * f1), _mul(c, -p_ * f2)), a, "esquinero")
            proyectar(_sum(o, _mul(a, -p_ * f1), _mul(c, -p_ * f2)), b, "esquinero")
            proyectar(_sum(o, _mul(a, -p_ * f1), _mul(b, -p_ * f2)), c, "esquinero")

    # aros de cierre y bisagras de piano: una fila en el medio de lo que el bloque cubre del panel
    for bl in geo.get("bloques") or []:
        if bl.get("etiqueta") == "Suplemento":
            continue
        piano = bl.get("etiqueta", "").startswith("Bisagra")
        ejes = [(tuple(bl["u"]), bl["a"]), (tuple(bl["v"]), bl["b"]), (tuple(bl["n"]), bl["c"])]
        for c in cols:
            k = max(range(3), key=lambda i: abs(_dot(ejes[i][0], c["n"])))
            if abs(_dot(ejes[k][0], c["n"])) < 0.9:
                continue
            profs = [local(c, _sum(bl["o"], _mul(ejes[k][0], f * ejes[k][1])))[2] for f in (0, 1)]
            # el bloque tiene que tocar el espesor del panel: por afuera (aros, también corridos sobre
            # un canto biselado del rack inclinado) o por adentro (bisagras de piano del baúl plegable)
            if min(profs) > float(c.get("esp") or 0) + 0.5 or max(profs) < -0.5:
                continue
            otros = [ejes[i] for i in range(3) if i != k]
            (el, L), (ec, C) = sorted(otros, key=lambda e: -e[1])
            if L < 40 or C < 4:
                continue
            pan = paneles[c["id"]]
            for z in _filas(L, 50.0 if piano else paso):
                p0 = local(c, _sum(bl["o"], _mul(el, z)))[:2]
                p1 = local(c, _sum(bl["o"], _mul(el, z), _mul(ec, C)))[:2]
                tramo = _tramo_dentro(pan, p0, p1)
                if tramo is None:
                    continue
                t = (tramo[0] + tramo[1]) / 2
                x, y = p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t
                perfil[c["id"]].append(Agujero(x, y, d_rem, CAPA_REMACHES, "bisagra" if piano else "perfil"))


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

def calcular(res: ResultadoTaller) -> Dict[str, List[Agujero]]:
    """Agujeros por panel (id del panel -> lista), en coordenadas del panel."""
    v = res.valores
    pf = v.get("perforacion")
    geo = v.get("geo")
    if not pf or not geo:
        return {}
    d_rem = float(pf["remache_d"]) + 0.1         # mecha del remache (como el instructivo)
    paso = float(pf["paso"]) or 100.0
    paneles = {p.id: p for p in res.paneles}
    out: Dict[str, List[Agujero]] = {pid: [] for pid in paneles}
    perfil: Dict[str, List[Agujero]] = {pid: [] for pid in paneles}
    huellas: Dict[str, List[Tuple[float, float, float, float]]] = {pid: [] for pid in paneles}
    m_alto, h_alto = geo["cierre_m_alto"], geo["cierre_h_alto"]
    m_sup, h_sup = geo.get("cierre_m_sup", 0), geo.get("cierre_h_sup", 0)

    def agregar(pid: str, x: float, y: float, origen: str, d: float = d_rem, capa: str = CAPA_REMACHES) -> None:
        if pid in out:
            out[pid].append(Agujero(x, y, d, capa, origen))

    def huella(pid: str, x0: float, y0: float, x1: float, y1: float) -> None:
        if pid in huellas:
            huellas[pid].append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))

    # --- 1) perfiles y esquineros: puntos en el case, proyectados sobre el panel de esa cara ---
    cols = geo["colocaciones"]

    def proyectar(p: Vec, fuera: Vec, origen: str) -> None:
        mejor = None
        for c in cols:
            n = c["n"]
            if _dot(n, fuera) > -0.99:     # el panel tiene que mirar hacia `fuera`
                continue
            pan = paneles[c["id"]]
            rel = _sum(p, _mul(c["o"], -1))
            x, y, prof = _dot(rel, c["u"]), _dot(rel, c["v"]), _dot(rel, n)
            if not (-0.01 <= x <= pan.ancho + 0.01 and -0.01 <= y <= pan.alto + 0.01):
                continue
            if prof > 0.5 or prof < -40:      # la cara del panel tiene que estar justo debajo
                continue
            if mejor is None or abs(prof) < abs(mejor[3]):
                mejor = (c["id"], x, y, prof)
        if mejor is not None:
            perfil[mejor[0]].append(Agujero(mejor[1], mejor[2], d_rem, CAPA_REMACHES, origen))

    if geo.get("forma"):     # rack inclinado, funda, baúl plegable (formas.py)
        _perfiles_formas(geo, paneles, perfil, d_rem, paso)
    else:
        X, Y, Z = v["ext_ancho"], v["ext_prof"], v["ext_alto"]
        ala, ed = geo["ala"], geo["esq_descuento"]
        zc1, zc2 = geo["z_cierre"], geo["z_cierre2"]
        dos = geo["dos_tapas"]

        # distancia de la fila de remaches a la arista exterior: medio ala del ángulo, o en el
        # perfil híbrido el medio de lo que el ala cubre del panel (que empieza a hibrido_descuento)
        if geo["hibrido"]:
            d_ar = (float(pf.get("hibrido_ala") or 20) + float(pf.get("hibrido_descuento") or 0)) / 2
        else:
            d_ar = ala / 2

        def arista(o: Vec, a: Vec, b: Vec, c: Vec, L: float) -> None:
            if L < 30:
                return
            for z in _filas(L, paso):
                base = _sum(o, _mul(c, z))
                proyectar(_sum(base, _mul(b, -d_ar)), a, "perfil")
                proyectar(_sum(base, _mul(a, -d_ar)), b, "perfil")

        for z, sz in ((0.0, -1), (Z, 1)):
            for y0, sy in ((0.0, -1), (Y, 1)):
                arista((ed, y0, z), (0, sy, 0), (0, 0, sz), (1, 0, 0), geo["L_x"])
            for x0, sx in ((0.0, -1), (X, 1)):
                arista((x0, ed, z), (sx, 0, 0), (0, 0, sz), (0, 1, 0), geo["L_y"])
        for x0, sx in ((0.0, -1), (X, 1)):
            for y0, sy in ((0.0, -1), (Y, 1)):
                z_c = zc2 + m_alto if dos else ed
                arista((x0, y0, z_c), (sx, 0, 0), (0, sy, 0), (0, 0, 1), geo["L_zc"])
                arista((x0, y0, zc1 + h_alto), (sx, 0, 0), (0, sy, 0), (0, 0, 1), geo["L_zt"])
                if dos:
                    arista((x0, y0, ed), (sx, 0, 0), (0, sy, 0), (0, 0, 1), geo["L_zt2"])

        # esquineros: 1, 2 o 3 agujeros por pata
        p_ = geo["esq_pata"]
        por_pata = max(1, min(3, round(float(pf["esq_remaches"]) / 3)))
        fr = {1: [(0.5, 0.5)], 2: [(0.35, 0.72), (0.72, 0.35)], 3: [(0.35, 0.72), (0.72, 0.35), (0.72, 0.72)]}[por_pata]
        for z, sz in ((0.0, -1), (Z, 1)):
            for x0, sx in ((0.0, -1), (X, 1)):
                for y0, sy in ((0.0, -1), (Y, 1)):
                    o, a, b, c = (x0, y0, z), (sx, 0, 0), (0, sy, 0), (0, 0, sz)
                    for f1, f2 in fr:
                        proyectar(_sum(o, _mul(b, -p_ * f1), _mul(c, -p_ * f2)), a, "esquinero")
                        proyectar(_sum(o, _mul(a, -p_ * f1), _mul(c, -p_ * f2)), b, "esquinero")
                        proyectar(_sum(o, _mul(a, -p_ * f1), _mul(b, -p_ * f2)), c, "esquinero")

        # aros de cierre: una fila en el medio de lo que el perfil cubre del panel
        s_ = geo["cierre_saliente"]
        niveles = [zc1 - (m_alto + m_sup) / 2, zc1 + (h_alto + h_sup) / 2]
        if dos:
            niveles += [zc2 + (m_alto + m_sup) / 2, zc2 - (h_alto + h_sup) / 2]
        for zn in niveles:
            for i in _filas(X + 2 * s_, paso):
                proyectar((-s_ + i, 0.0, zn), (0, -1, 0), "perfil")
                proyectar((-s_ + i, Y, zn), (0, 1, 0), "perfil")
            for i in _filas(Y + 2 * s_, paso):
                proyectar((0.0, -s_ + i, zn), (-1, 0, 0), "perfil")
                proyectar((X, -s_ + i, zn), (1, 0, 0), "perfil")

        # bisagra de piano: dos filas cada 50 mm, a lo largo de la trasera
        if pf.get("piano"):
            Lp = float(pf["piano"])
            x0p = (X - Lp) / 2
            n_p = math.floor(Lp / 50) + 1
            for i in range(n_p):
                xp = x0p + (Lp * i / (n_p - 1) if n_p > 1 else Lp / 2)
                proyectar((xp, Y, zc1 - m_alto - 8), (0, 1, 0), "bisagra")
                proyectar((xp, Y, zc1 + h_alto + 8), (0, 1, 0), "bisagra")

        # --- 2) juntas de las tapas de acceso laterales: fila vertical en el canto de la junta ---
        if geo.get("acceso"):
            w_low, a_acc = geo["w_low"], geo["a_acc"]
            for pid, x_borde, sign, cuerpo in (("cuerpo_izq", 0.0, 1, True), ("cuerpo_der", w_low, -1, True),
                                               ("acceso_izq", a_acc, -1, False), ("acceso_der", 0.0, 1, False)):
                pan = paneles.get(pid)
                if pan is None:
                    continue
                dist = (m_alto - m_sup) / 2 if cuerpo else (h_alto - h_sup) / 2
                for y in _filas(pan.alto, paso):
                    perfil[pid].append(Agujero(x_borde + sign * dist, y, d_rem, CAPA_REMACHES, "perfil"))

    # --- 3) herrajes ---
    manuales = v.get("manuales")
    man_de: Dict[int, Any] = {}
    if manuales is not None:
        for col in manuales.colocados:
            for obj in col.marcas + col.calados:
                man_de[id(obj)] = col

    def datos_de(obj, clave: str) -> Dict[str, Any]:
        col = man_de.get(id(obj))
        if col is not None:
            from .herrajes_manuales import _REMACHES_DEF
            d = dict(col.datos)
            d.setdefault("remaches", _REMACHES_DEF.get(col.categoria, 0))
            return d
        return dict(pf.get(clave) or {})

    def junta(pid: str, mx: float, my: float, e: Tuple[int, int], cuerpo: bool,
              datos: Dict[str, Any], tipo: str) -> None:
        """Cierre o bisagra: (mx, my) es la marca del modelo, `e` la dirección hacia la línea
        de cierre en el panel. dy de las perforaciones: desde la línea, negativo en el cuerpo."""
        ex, ey = e
        alto = m_alto if cuerpo else h_alto
        pan = paneles[pid]
        oblicua = None
        if getattr(pan, "contorno", None):         # canto inclinado: la línea sigue al canto más cercano
            nx, ny = _normal_canto(pan, mx, my)
            if abs(nx) > 0.01 and abs(ny) > 0.01:
                oblicua = (nx, ny)
        lx, ly = mx + ex * alto, my + ey * alto          # punto de la línea de cierre
        n = int(datos.get("remaches", 6) or 0)
        propias = _lista_perforaciones(datos)
        if propias is None:
            if tipo == "bisagra":
                k = max(1, n // 2)
                propias = ([(dx, -38.0) for dx in _parejo(k, 42)] + [(dx, 32.0) for dx in _parejo(n - k, 42)])
            elif datos.get("tipo") == "embutido" and datos.get("corte"):
                cw, ch = float(datos["corte"][0]), float(datos["corte"][1])
                n_t = 2 if n >= 4 else (1 if n >= 2 else 0)
                n_c = n - n_t
                arriba = m_alto + 2                       # el calado empieza 2 mm debajo del perfil
                filas = max(1, n_c // 2)
                ys = [-(arriba + 10 + (ch - 20) * i / (filas - 1)) if filas > 1 else -(arriba + ch / 2)
                      for i in range(filas)]
                propias = [(sx * (cw / 2 + 6), yy) for yy in ys for sx in (-1, 1)]
                if n_c % 2:
                    propias.append((0.0, -(arriba + ch + 6)))
                propias += [(dx, 32.0) for dx in _parejo(n_t, 28)]
            else:
                n_t = max(1, n // 3) if n >= 2 else 0
                n_c = n - n_t
                if n_c >= 4:
                    k = math.ceil(n_c / 2)
                    propias = [(dx, -30.0) for dx in _parejo(k, 34)] + [(dx, -46.0) for dx in _parejo(n_c - k, 34)]
                else:
                    propias = [(dx, -38.0) for dx in _parejo(n_c, 34)]
                propias += [(dx, 32.0) for dx in _parejo(n_t, 28)]
        for dx, dy in propias:
            if (dy < 0) != cuerpo or dy == 0:
                continue
            dist = abs(dy)
            # a lo largo de la junta (dx) y alejándose de la línea (dist)
            if oblicua is not None:
                nx, ny = oblicua
                agregar(pid, lx + ny * dx - nx * dist, ly - nx * dx - ny * dist, tipo)
            elif ex == 0:
                agregar(pid, lx + dx, ly - ey * dist, tipo)
            else:
                agregar(pid, lx - ex * dist, ly + dx, tipo)
        # huella del herraje: tapa los remaches del perfil que quedan debajo
        a = 30.0 if tipo == "bisagra" else 26.0
        lejos = 58.0 if cuerpo else 44.0
        if ex == 0:
            huella(pid, lx - a, ly, lx + a, ly - ey * lejos)
        else:
            huella(pid, lx, ly - a, lx - ex * lejos, ly + a)

    for m in res.marcas:
        if m.panel not in paneles:
            continue
        grupo = paneles[m.panel].grupo
        if m.tipo in ("cierre", "bisagra"):
            cuerpo = grupo == "cuerpo"
            c2 = m.texto == "c2"
            ey = (1 if not c2 else -1) if cuerpo else (-1 if not c2 else 1)
            clave = "bisagra" if m.tipo == "bisagra" else "cierre"
            junta(m.panel, m.x, m.y, (0, ey), cuerpo, datos_de(m, clave), m.tipo)
        elif m.tipo == "cierre_esquina":     # baúl plegable: traba la pared contra el ángulo del lateral
            ex = -1 if m.x < paneles[m.panel].ancho / 2 else 1
            junta(m.panel, m.x + ex * (25 - m_alto), m.y, (ex, 0), True, datos_de(m, "cierre"), "cierre")
        elif m.tipo == "cierre_acceso":
            ex = 1 if m.texto == "+" else -1
            junta(m.panel, m.x, m.y, (ex, 0), m.panel.startswith("cuerpo_"), datos_de(m, "cierre"), "cierre")
        elif m.tipo == "manija_sup" or (m.tipo.startswith("herraje") and id(m) in man_de):
            col = man_de.get(id(m))
            if col is not None and (col.forma in ("rueda", "pie") or (col.forma == "logo" and col.fila.modo == "grabado")):
                continue    # ruedas: bulones en la capa 0; pies: se pegan o atornillan al centro; grabado: sin remaches
            datos = datos_de(m, "manija")
            n = int(datos.get("remaches", 0) or 0)
            if col is not None and col.forma == "logo":
                n = 4
            w, h = (m.ancho, m.alto)
            giro = col.giro_panel if col is not None else 0
            propias = _lista_perforaciones(datos)
            if propias is not None:
                pts = [(m.x + q[0], m.y + q[1]) for q in (_rotar(dx, dy, giro) for dx, dy in propias)]
            elif col is not None and datos.get("largo"):     # bisagra de piano puesta a mano
                larga = w >= h
                L = w if larga else h
                pts = [((m.x - L / 2 + t) if larga else m.x, m.y if larga else (m.y - L / 2 + t))
                       for t in _filas(L, 50, 25)]
            elif m.tipo == "manija_sup" or (col is not None and col.categoria == "manija"):
                # asa de superficie: la mitad en cada punta, a lo largo del lado largo
                larga = w >= h
                L, C = (w, h) if larga else (h, w)
                k = max(1, n // 2)
                pts = []
                for sgn, kk in ((-1, k), (1, n - k)):
                    for c in _parejo(kk, max(C - 16, 0)):
                        a = sgn * (L / 2 - 10)
                        pts.append((m.x + a, m.y + c) if larga else (m.x + c, m.y + a))
            else:
                pts = _alrededor(m.x, m.y, w, h, -6, n)
            for x, y in pts:
                agregar(m.panel, x, y, "manija" if m.tipo == "manija_sup" else "herraje")
            huella(m.panel, m.x - w / 2, m.y - h / 2, m.x + w / 2, m.y + h / 2)

    for c in res.calados:
        if c.panel not in paneles:
            continue
        tipo = c.tipo.replace(" a mano", "")
        if tipo not in ("manija", "cazoleta", "encastre"):
            continue
        clave = {"manija": "manija", "cazoleta": "cazoleta", "encastre": "plato"}[tipo]
        datos = datos_de(c, clave)
        n = int(datos.get("remaches", 0) or 0)
        ext = datos.get("exterior")
        col = man_de.get(id(c))
        giro = col.giro_panel if col is not None else 0
        if ext:
            ew, eh = (float(ext[1]), float(ext[0])) if (c.ancho > c.alto) != (float(ext[0]) > float(ext[1])) \
                else (float(ext[0]), float(ext[1]))
            reborde = max(min((ew - c.ancho) / 2, (eh - c.alto) / 2), 4.0)
        elif "ala" in datos:
            reborde = float(datos["ala"])
        else:
            reborde = 10.0
        propias = _lista_perforaciones(datos)
        if propias is not None:
            pts = [(c.cx + q[0], c.cy + q[1]) for q in (_rotar(dx, dy, giro) for dx, dy in propias)]
        else:
            pts = _alrededor(c.cx, c.cy, c.ancho, c.alto, reborde / 2, n)
        for x, y in pts:
            agregar(c.panel, x, y, tipo)
        huella(c.panel, c.cx - c.ancho / 2 - reborde, c.cy - c.alto / 2 - reborde,
               c.cx + c.ancho / 2 + reborde, c.cy + c.alto / 2 + reborde)

    # --- 4) marco de la base suelta: tornillos para madera ---
    base = geo.get("base")
    if base and base.get("suelta") and "base_ruedas" in paneles:
        for tr in base.get("marco") or []:
            x0, x1, y0, y1 = tr["x0"], tr["x1"], tr["y0"], tr["y1"]
            if tr["borde"] in ("y0", "y1"):
                L = x1 - x0
                yy = (y0 + y1) / 2
                n = math.floor(L / 150) + 2
                for i in range(n):
                    agregar("base_ruedas", x0 + 20 + (L - 40) * i / (n - 1), yy, "marco", TORNILLO_D, CAPA_TORNILLOS)
            else:
                L = y1 - y0
                xx = (x0 + x1) / 2
                n = math.floor(L / 150) + 2
                for i in range(n):
                    agregar("base_ruedas", xx, y0 + 20 + (L - 40) * i / (n - 1), "marco", TORNILLO_D, CAPA_TORNILLOS)

    # --- 5) limpiar: perfiles tapados por herrajes, fuera del panel, dentro de calados, repetidos ---
    pasantes: Dict[str, List[Tuple[float, float, float, float]]] = {}
    for c in res.calados:
        if c.tipo != "rebaje":
            pasantes.setdefault(c.panel, []).append((c.cx - c.ancho / 2, c.cy - c.alto / 2,
                                                     c.cx + c.ancho / 2, c.cy + c.alto / 2))
    final: Dict[str, List[Agujero]] = {}
    for pid, pan in paneles.items():
        lista = list(out[pid])
        for a in perfil[pid]:
            if not any(r[0] - 1 <= a.x <= r[2] + 1 and r[1] - 1 <= a.y <= r[3] + 1 for r in huellas[pid]):
                lista.append(a)
        buenos: List[Agujero] = []
        for a in lista:
            r = a.d / 2 + 1.5
            if not (r <= a.x <= pan.ancho - r and r <= a.y <= pan.alto - r):
                continue
            if getattr(pan, "contorno", None) and not _dentro(pan, a.x, a.y, r):
                continue
            if any(q[0] - r < a.x < q[2] + r and q[1] - r < a.y < q[3] + r for q in pasantes.get(pid, [])):
                continue
            if any(math.hypot(a.x - b.x, a.y - b.y) < DISTANCIA_MINIMA for b in buenos):
                continue
            buenos.append(Agujero(round(a.x, 2), round(a.y, 2), a.d, a.capa, a.origen))
        if buenos:
            final[pid] = buenos
    return final


def tuplas(agujeros: Iterable[Agujero]) -> List[tuple]:
    """(capa, x, y, d) para panel_dxf / placa_dxf."""
    return [a.tupla() for a in agujeros]
