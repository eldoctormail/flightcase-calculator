"""Lectura de dibujos vectoriales (SVG y DXF) para las placas de logo.

Devuelve el dibujo como una lista de polilíneas (listas de puntos x, y con el eje y hacia
arriba), en las unidades del archivo. Las curvas se aproximan con tramos rectos. No hace
falta precisión de CAD: el logo se escala después a la medida de la placa.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Iterable, List, Sequence, Tuple

Punto = Tuple[float, float]
Polilinea = List[Punto]
Matriz = Tuple[float, float, float, float, float, float]   # a b c d e f, como transform="matrix(...)"

_ID = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_TRAMOS = 16   # tramos por curva


class ErrorVector(ValueError):
    pass


def leer(ruta: str) -> List[Polilinea]:
    """Polilíneas del archivo (según la extensión: .svg o .dxf)."""
    ext = ruta.lower().rsplit(".", 1)[-1]
    with open(ruta, "rb") as f:
        crudo = f.read()
    if ext == "svg":
        lineas = leer_svg(crudo.decode("utf-8", errors="replace"))
    elif ext == "dxf":
        lineas = leer_dxf(crudo.decode("utf-8", errors="replace"))
    else:
        raise ErrorVector("el logo tiene que ser un archivo .svg o .dxf")
    lineas = [p for p in lineas if len(p) >= 2]
    if not lineas:
        raise ErrorVector("el archivo no tiene trazos que se puedan leer")
    return lineas


def caja(lineas: Iterable[Sequence[Punto]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for l in lineas for p in l]
    ys = [p[1] for l in lineas for p in l]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def encajar(lineas: List[Polilinea], ancho: float, alto: float) -> Tuple[List[Polilinea], float, float]:
    """Escala el dibujo (sin deformarlo) para que entre en ancho x alto, centrado en (0, 0).
    Con alto <= 0 el alto sale de la proporción del dibujo. Devuelve (líneas, ancho, alto)."""
    x0, y0, x1, y1 = caja(lineas)
    w, h = x1 - x0, y1 - y0
    if w <= 0 and h <= 0:
        return [], ancho, max(alto, 0.0)
    if alto <= 0:
        alto = ancho * h / w if w > 0 else ancho
    if ancho <= 0:
        ancho = alto * w / h if h > 0 else alto
    k = min(ancho / w if w > 0 else math.inf, alto / h if h > 0 else math.inf)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [[((x - cx) * k, (y - cy) * k) for x, y in l] for l in lineas], ancho, alto


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def _mult(m: Matriz, n: Matriz) -> Matriz:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def _aplicar(m: Matriz, x: float, y: float) -> Punto:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _nums(texto: str) -> List[float]:
    return [float(v) for v in _NUM.findall(texto or "")]


def _transform(texto: str) -> Matriz:
    m = _ID
    for nombre, args in re.findall(r"(\w+)\s*\(([^)]*)\)", texto or ""):
        v = _nums(args)
        if nombre == "matrix" and len(v) == 6:
            t = tuple(v)
        elif nombre == "translate" and v:
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif nombre == "scale" and v:
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif nombre == "rotate" and v:
            a = math.radians(v[0])
            r = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
            if len(v) >= 3:
                t = _mult(_mult((1, 0, 0, 1, v[1], v[2]), r), (1, 0, 0, 1, -v[1], -v[2]))
            else:
                t = r
        elif nombre == "skewX" and v:
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif nombre == "skewY" and v:
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            continue
        m = _mult(m, t)  # type: ignore[arg-type]
    return m


def _arco_svg(x1, y1, rx, ry, phi, fa, fs, x2, y2) -> List[Punto]:
    """Arco elíptico de SVG (notación de extremos) como puntos, sin el inicial."""
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(num / den, 0)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(2, int(abs(dt) / (math.pi / 12)))
    out = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        out.append((cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp,
                    cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp))
    return out


def _path(d: str) -> List[Polilinea]:
    fichas = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|" + _NUM.pattern, d or "")
    out: List[Polilinea] = []
    actual: Polilinea = []
    x = y = 0.0
    x0 = y0 = 0.0
    ctrl = None       # último punto de control (para S/T)
    cmd = None
    i = 0

    def tomar(n: int) -> List[float]:
        nonlocal i
        v = [float(t) for t in fichas[i:i + n]]
        if len(v) < n or any(re.match(r"[A-Za-z]", t) for t in fichas[i:i + n]):
            raise ErrorVector("trazo SVG incompleto")
        i += n
        return v

    def cerrar_actual():
        nonlocal actual
        if len(actual) >= 2:
            out.append(actual)
        actual = []

    while i < len(fichas):
        t = fichas[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                if actual:
                    actual.append((x0, y0))
                cerrar_actual()
                x, y = x0, y0
                ctrl = None
                continue
        elif cmd is None:
            raise ErrorVector("trazo SVG sin comando")
        rel = cmd.islower()
        c = cmd.upper()
        bx, by = (x, y) if rel else (0.0, 0.0)
        if c != "M" and not actual:
            actual = [(x, y)]
        try:
            if c == "M":
                px, py = tomar(2)
                cerrar_actual()
                x, y = bx + px, by + py
                x0, y0 = x, y
                actual = [(x, y)]
                cmd = "l" if rel else "L"   # pares siguientes son líneas
                ctrl = None
            elif c == "L":
                px, py = tomar(2)
                x, y = bx + px, by + py
                actual.append((x, y))
                ctrl = None
            elif c == "H":
                (px,) = tomar(1)
                x = bx + px
                actual.append((x, y))
                ctrl = None
            elif c == "V":
                (py,) = tomar(1)
                y = (y if rel else 0.0) + py
                actual.append((x, y))
                ctrl = None
            elif c in "CS":
                if c == "C":
                    c1x, c1y, c2x, c2y, px, py = tomar(6)
                    c1 = (bx + c1x, by + c1y)
                else:
                    c2x, c2y, px, py = tomar(4)
                    c1 = (2 * x - ctrl[0], 2 * y - ctrl[1]) if ctrl and ctrl[2] == "C" else (x, y)
                c2 = (bx + c2x, by + c2y)
                p3 = (bx + px, by + py)
                for k in range(1, _TRAMOS + 1):
                    s = k / _TRAMOS
                    m = 1 - s
                    actual.append((m ** 3 * x + 3 * m * m * s * c1[0] + 3 * m * s * s * c2[0] + s ** 3 * p3[0],
                                   m ** 3 * y + 3 * m * m * s * c1[1] + 3 * m * s * s * c2[1] + s ** 3 * p3[1]))
                ctrl = (c2[0], c2[1], "C")
                x, y = p3
            elif c in "QT":
                if c == "Q":
                    cx_, cy_, px, py = tomar(4)
                    c1 = (bx + cx_, by + cy_)
                else:
                    px, py = tomar(2)
                    c1 = (2 * x - ctrl[0], 2 * y - ctrl[1]) if ctrl and ctrl[2] == "Q" else (x, y)
                p2 = (bx + px, by + py)
                for k in range(1, _TRAMOS + 1):
                    s = k / _TRAMOS
                    m = 1 - s
                    actual.append((m * m * x + 2 * m * s * c1[0] + s * s * p2[0],
                                   m * m * y + 2 * m * s * c1[1] + s * s * p2[1]))
                ctrl = (c1[0], c1[1], "Q")
                x, y = p2
            elif c == "A":
                rx, ry, phi, fa, fs, px, py = tomar(7)
                p2 = (bx + px, by + py)
                actual += _arco_svg(x, y, rx, ry, phi, bool(fa), bool(fs), p2[0], p2[1])
                x, y = p2
                ctrl = None
            else:
                i += 1
        except ErrorVector:
            break
    cerrar_actual()
    return out


def _elipse(cx: float, cy: float, rx: float, ry: float) -> Polilinea:
    n = 48
    return [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def leer_svg(texto: str) -> List[Polilinea]:
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as e:
        raise ErrorVector(f"el SVG no se puede leer ({e})") from None
    out: List[Polilinea] = []

    def visitar(nodo, m: Matriz) -> None:
        tag = _local(nodo.tag)
        if tag in ("defs", "clipPath", "mask", "symbol", "metadata", "title", "desc", "style", "text"):
            return
        m = _mult(m, _transform(nodo.get("transform", "")))
        a = nodo.get
        f = lambda k, d=0.0: (_nums(a(k)) or [d])[0]
        lineas: List[Polilinea] = []
        if tag == "path":
            lineas = _path(a("d", ""))
        elif tag in ("polygon", "polyline"):
            v = _nums(a("points", ""))
            pts = list(zip(v[0::2], v[1::2]))
            if tag == "polygon" and pts:
                pts.append(pts[0])
            lineas = [pts]
        elif tag == "line":
            lineas = [[(f("x1"), f("y1")), (f("x2"), f("y2"))]]
        elif tag == "rect":
            x, y, w, h = f("x"), f("y"), f("width"), f("height")
            if w > 0 and h > 0:
                lineas = [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
        elif tag == "circle":
            r = f("r")
            if r > 0:
                lineas = [_elipse(f("cx"), f("cy"), r, r)]
        elif tag == "ellipse":
            if f("rx") > 0 and f("ry") > 0:
                lineas = [_elipse(f("cx"), f("cy"), f("rx"), f("ry"))]
        for l in lineas:
            # SVG tiene el eje y hacia abajo
            out.append([(px, -py) for px, py in (_aplicar(m, x, y) for x, y in l)])
        for hijo in nodo:
            visitar(hijo, m)

    visitar(raiz, _ID)
    return out


# ---------------------------------------------------------------------------
# DXF (LINE, LWPOLYLINE, POLYLINE, CIRCLE, ARC, ELLIPSE, SPLINE de la sección ENTITIES)
# ---------------------------------------------------------------------------

def _pares(texto: str) -> List[Tuple[int, str]]:
    v = texto.splitlines()
    out = []
    for i in range(0, len(v) - 1, 2):
        try:
            out.append((int(v[i].strip()), v[i + 1].strip()))
        except ValueError:
            continue
    return out


def _bulge(p: Punto, q: Punto, b: float) -> List[Punto]:
    """Tramo con abombado (bulge) de una LWPOLYLINE, sin el punto inicial."""
    if abs(b) < 1e-9:
        return [q]
    ang = 4 * math.atan(b)
    dx, dy = q[0] - p[0], q[1] - p[1]
    cuerda = math.hypot(dx, dy)
    if cuerda == 0:
        return [q]
    r = cuerda / (2 * math.sin(abs(ang) / 2))
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    h = math.sqrt(max(r * r - (cuerda / 2) ** 2, 0)) * (1 if (b > 0) == (abs(ang) < math.pi) else -1)
    cx, cy = mx - dy / cuerda * h, my + dx / cuerda * h
    a0 = math.atan2(p[1] - cy, p[0] - cx)
    n = max(2, int(abs(ang) / (math.pi / 12)))
    return [(cx + r * math.cos(a0 + ang * k / n), cy + r * math.sin(a0 + ang * k / n)) for k in range(1, n + 1)]


def leer_dxf(texto: str) -> List[Polilinea]:
    pares = _pares(texto)
    out: List[Polilinea] = []
    en_entidades = False
    i = 0
    n = len(pares)
    while i < n:
        cod, val = pares[i]
        if cod == 2 and i > 0 and pares[i - 1] == (0, "SECTION"):
            en_entidades = val == "ENTITIES"
        if cod != 0 or not en_entidades or val in ("SECTION", "ENDSEC", "VERTEX", "SEQEND"):
            i += 1
            continue
        tipo = val
        j = i + 1
        campos: List[Tuple[int, str]] = []
        while j < n and pares[j][0] != 0:
            campos.append(pares[j])
            j += 1
        g = {}
        for c, v in campos:
            g.setdefault(c, v)
        num = lambda c, d=0.0: float(g.get(c, d))
        if tipo == "LINE":
            out.append([(num(10), num(20)), (num(11), num(21))])
        elif tipo == "CIRCLE":
            out.append(_elipse(num(10), num(20), num(40), num(40)))
        elif tipo == "ARC":
            cx, cy, r = num(10), num(20), num(40)
            a0, a1 = num(50), num(51)
            barrido = (a1 - a0) % 360 or 360
            k = max(2, int(barrido / 7.5))
            out.append([(cx + r * math.cos(math.radians(a0 + barrido * t / k)),
                         cy + r * math.sin(math.radians(a0 + barrido * t / k))) for t in range(k + 1)])
        elif tipo == "ELLIPSE":
            cx, cy, mx, my, rel = num(10), num(20), num(11), num(21), num(40, 1)
            t0, t1 = num(41, 0), num(42, 2 * math.pi)
            if t1 <= t0:
                t1 += 2 * math.pi
            k = 48
            a = math.hypot(mx, my)
            ux, uy = (mx / a, my / a) if a else (1, 0)
            pts = []
            for t in range(k + 1):
                s = t0 + (t1 - t0) * t / k
                px, py = a * math.cos(s), a * rel * math.sin(s)
                pts.append((cx + px * ux - py * uy, cy + px * uy + py * ux))
            out.append(pts)
        elif tipo == "LWPOLYLINE":
            pts: List[Punto] = []
            bulges: List[float] = []
            for c, v in campos:
                if c == 10:
                    pts.append((float(v), 0.0))
                    bulges.append(0.0)
                elif c == 20 and pts:
                    pts[-1] = (pts[-1][0], float(v))
                elif c == 42 and bulges:
                    bulges[-1] = float(v)
            cerrada = int(float(g.get(70, 0))) & 1
            if pts:
                linea = [pts[0]]
                tramos = len(pts) if cerrada else len(pts) - 1
                for k in range(tramos):
                    linea += _bulge(pts[k], pts[(k + 1) % len(pts)], bulges[k])
                out.append(linea)
        elif tipo == "POLYLINE":
            cerrada = int(float(g.get(70, 0))) & 1
            pts = []
            k = j
            while k < n and pares[k] != (0, "SEQEND"):
                if pares[k] == (0, "VERTEX"):
                    vx = vy = 0.0
                    m = k + 1
                    while m < n and pares[m][0] != 0:
                        if pares[m][0] == 10:
                            vx = float(pares[m][1])
                        elif pares[m][0] == 20:
                            vy = float(pares[m][1])
                        m += 1
                    pts.append((vx, vy))
                    k = m
                else:
                    k += 1
            if cerrada and pts:
                pts.append(pts[0])
            out.append(pts)
            j = k
        elif tipo == "SPLINE":
            # se toman los puntos de control (o de ajuste) como polilínea: alcanza para ubicar el logo
            pts = []
            for c, v in campos:
                if c in (10, 11):
                    pts.append((float(v), 0.0))
                elif c in (20, 21) and pts:
                    pts[-1] = (pts[-1][0], float(v))
            out.append(pts)
        i = j
    return out
