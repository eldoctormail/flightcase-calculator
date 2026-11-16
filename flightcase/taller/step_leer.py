"""Lee modelos 3D de archivos STEP (AP203, AP214, AP242) sin librerías de CAD.

Sirve para los herrajes propios: el fabricante da el modelo de la pieza en STEP y la app lo
muestra en la vista 3D y lo vuelve a meter, tal cual, en el STEP del case.

Se lee el texto del archivo (ISO 10303-21), se arma el árbol de piezas con sus ubicaciones y
cada cara del B-rep se pasa a triángulos: planos, cilindros, conos, esferas, toros, superficies
de revolución y de extrusión, y B-splines (también racionales). Las caras que no se entienden se
saltean y se avisa. Las aristas reales del modelo salen como líneas, para dibujarlo como en un
programa de CAD.

Para el STEP del case no se usan los triángulos: :class:`ModeloStep` guarda el texto de cada
entidad, y :func:`entidades_de` devuelve las que hacen falta para copiar un sólido entero.
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

Vec = Tuple[float, float, float]


class ErrorStep(ValueError):
    """El archivo no es un STEP que se pueda leer."""


# ---------------------------------------------------------------------------
# Texto ISO 10303-21
# ---------------------------------------------------------------------------

class Ref(int):
    """Referencia a otra entidad (#123)."""


class Enum(str):
    """Valor enumerado (.T., .MILLI.)."""


@dataclass
class Tipado:
    """Parámetro con tipo, como LENGTH_MEASURE(1.E-03)."""
    nombre: str
    args: list


@dataclass
class Entidad:
    id: int
    tipo: str                       # el tipo, o "" si es compleja
    args: list
    partes: Dict[str, list] = field(default_factory=dict)    # compleja: tipo -> args
    desde: int = 0                  # posición del texto (después del '=')
    hasta: int = 0

    def es(self, *tipos: str) -> bool:
        return self.tipo in tipos or any(t in self.partes for t in tipos)

    def parte(self, tipo: str) -> Optional[list]:
        if self.tipo == tipo:
            return self.args
        return self.partes.get(tipo)


_TOKENS = re.compile(r"""
    (?P<str>'(?:[^']|'')*')
  | (?P<ref>\#\d+)
  | (?P<enum>\.[A-Za-z_][A-Za-z0-9_]*\.)
  | (?P<num>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)
  | (?P<kw>!?[A-Za-z_][A-Za-z0-9_]*)
  | (?P<sym>[()=,;$*])
  | (?P<bin>"[0-9A-Fa-f]*")
""", re.VERBOSE)
_COMENTARIO = re.compile(r"/\*.*?\*/", re.DOTALL)


def _texto_step(s: str) -> str:
    """Decodifica una cadena STEP ('' y \\X2\\...\\X0\\)."""
    s = s[1:-1].replace("''", "'")

    def x2(m: "re.Match[str]") -> str:
        h = m.group(1)
        return "".join(chr(int(h[i:i + 4], 16)) for i in range(0, len(h) - 3, 4))
    s = re.sub(r"\\X2\\([0-9A-Fa-f]*)\\X0\\", x2, s)
    s = re.sub(r"\\X\\([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), s)
    return s.replace("\\\\", "\\")


class _Lector:
    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.toks: List[Tuple[str, str, int, int]] = []
        for m in _TOKENS.finditer(texto):
            self.toks.append((m.lastgroup or "", m.group(), m.start(), m.end()))
        self.i = 0

    def valor(self) -> Any:
        k, t, _a, _b = self.toks[self.i]
        self.i += 1
        if k == "sym":
            if t == "(":
                return self.lista()
            if t == "$":
                return None
            if t == "*":
                return "*"
            raise ErrorStep(f"símbolo inesperado {t!r}")
        if k == "ref":
            return Ref(int(t[1:]))
        if k == "num":
            return float(t)
        if k == "str":
            return _texto_step(t)
        if k == "enum":
            return Enum(t[1:-1].upper())
        if k == "kw":       # parámetro con tipo
            if self.toks[self.i][1] != "(":
                return Enum(t)
            self.i += 1
            return Tipado(t.upper(), self.lista())
        return t

    def lista(self) -> list:
        """Lee hasta el ')' que cierra (el '(' ya se leyó)."""
        out = []
        while True:
            k, t, _a, _b = self.toks[self.i]
            if t == ")":
                self.i += 1
                return out
            if t == ",":
                self.i += 1
                continue
            out.append(self.valor())


def leer_texto(texto: str) -> Dict[int, Entidad]:
    """Todas las entidades de la sección DATA."""
    texto = _COMENTARIO.sub(lambda m: " " * len(m.group()), texto)
    m = re.search(r"\bDATA\s*(\([^;]*\))?\s*;", texto)
    if not texto.lstrip().upper().startswith("ISO-10303-21") or not m:
        raise ErrorStep("no es un archivo STEP (falta ISO-10303-21 o la sección DATA)")
    fin = texto.find("ENDSEC", m.end())
    lector = _Lector(texto[:fin if fin > 0 else len(texto)])
    # saltear hasta DATA
    while lector.i < len(lector.toks) and lector.toks[lector.i][3] <= m.end():
        lector.i += 1
    ents: Dict[int, Entidad] = {}
    toks = lector.toks
    n = len(toks)
    while lector.i < n:
        k, t, _a, _b = toks[lector.i]
        if k != "ref" or lector.i + 2 >= n or toks[lector.i + 1][1] != "=":
            lector.i += 1
            continue
        eid = int(t[1:])
        lector.i += 2
        desde = toks[lector.i][2]
        try:
            k2, t2, _a2, _b2 = toks[lector.i]
            if k2 == "kw":
                lector.i += 1
                if toks[lector.i][1] != "(":
                    raise ErrorStep("falta '('")
                lector.i += 1
                e = Entidad(eid, t2.upper(), lector.lista())
            elif t2 == "(":       # entidad compleja: ( A(...) B(...) )
                lector.i += 1
                partes: Dict[str, list] = {}
                while toks[lector.i][1] != ")":
                    nom = toks[lector.i][1].upper()
                    lector.i += 2
                    partes[nom] = lector.lista()
                lector.i += 1
                e = Entidad(eid, "", [], partes)
            else:
                raise ErrorStep(f"entidad #{eid} mal escrita")
        except IndexError:
            raise ErrorStep(f"el archivo termina en la mitad de la entidad #{eid}") from None
        # hasta el ';'
        while lector.i < n and toks[lector.i][1] != ";":
            lector.i += 1
        e.desde, e.hasta = desde, toks[lector.i][2] if lector.i < n else len(lector.texto)
        lector.i += 1
        ents[eid] = e
    if not ents:
        raise ErrorStep("el archivo no tiene entidades")
    return ents


# ---------------------------------------------------------------------------
# Álgebra
# ---------------------------------------------------------------------------

def _unit(v: Sequence[float]) -> np.ndarray:
    a = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(a))
    return a / n if n > 1e-15 else a


def _marco(z: Sequence[float], x: Optional[Sequence[float]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    zz = _unit(z)
    if x is None or float(np.linalg.norm(np.cross(zz, x))) < 1e-9:
        x = (1.0, 0.0, 0.0) if abs(zz[0]) < 0.9 else (0.0, 1.0, 0.0)
    xx = np.asarray(x, dtype=float)
    xx = _unit(xx - zz * float(np.dot(xx, zz)))
    return xx, np.cross(zz, xx), zz


def _matriz(o: Sequence[float], x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, y, z, o
    return m


def _area2(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2.0


# ---------------------------------------------------------------------------
# Triangulación de polígonos con agujeros (algoritmo "earcut", de Mapbox)
# ---------------------------------------------------------------------------

class _N:
    __slots__ = ("i", "x", "y", "prev", "next", "steiner")

    def __init__(self, i: int, x: float, y: float) -> None:
        self.i, self.x, self.y = i, x, y
        self.prev: "_N" = self
        self.next: "_N" = self
        self.steiner = False


def _ar(p: _N, q: _N, r: _N) -> float:
    return (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y)


def _igual(a: _N, b: _N) -> bool:
    return a.x == b.x and a.y == b.y


def _en_tri(ax, ay, bx, by, cx, cy, px, py) -> bool:
    return ((cx - px) * (ay - py) >= (ax - px) * (cy - py) and (ax - px) * (by - py) >= (bx - px) * (ay - py)
            and (bx - px) * (cy - py) >= (cx - px) * (by - py))


def _insertar(i: int, x: float, y: float, last: Optional[_N]) -> _N:
    p = _N(i, x, y)
    if last is not None:
        p.next, p.prev = last.next, last
        last.next.prev = p
        last.next = p
    return p


def _sacar(p: _N) -> None:
    p.next.prev = p.prev
    p.prev.next = p.next


def _lista_enlazada(pts: Sequence[Tuple[float, float]], desde: int, hasta: int, horario: bool) -> Optional[_N]:
    s = 0.0
    j = hasta - 1
    for i in range(desde, hasta):
        s += (pts[j][0] - pts[i][0]) * (pts[i][1] + pts[j][1])
        j = i
    last: Optional[_N] = None
    orden = range(desde, hasta) if horario == (s > 0) else range(hasta - 1, desde - 1, -1)
    for i in orden:
        last = _insertar(i, pts[i][0], pts[i][1], last)
    if last is not None and _igual(last, last.next):
        _sacar(last)
        last = last.next
    return last


def _filtrar(start: Optional[_N], end: Optional[_N] = None) -> Optional[_N]:
    if start is None:
        return start
    end = end or start
    p = start
    while True:
        otra = False
        if not p.steiner and (_igual(p, p.next) or _ar(p.prev, p, p.next) == 0):
            _sacar(p)
            p = end = p.prev
            if p is p.next:
                break
            otra = True
        else:
            p = p.next
        if not (otra or p is not end):
            break
    return end


def _es_oreja(ear: _N) -> bool:
    a, b, c = ear.prev, ear, ear.next
    if _ar(a, b, c) >= 0:
        return False
    p = ear.next.next
    while p is not ear.prev:
        if _en_tri(a.x, a.y, b.x, b.y, c.x, c.y, p.x, p.y) and _ar(p.prev, p, p.next) >= 0:
            return False
        p = p.next
    return True


def _signo(v: float) -> int:
    return (v > 0) - (v < 0)


def _sobre(p: _N, q: _N, r: _N) -> bool:
    return min(p.x, r.x) <= q.x <= max(p.x, r.x) and min(p.y, r.y) <= q.y <= max(p.y, r.y)


def _cruzan(p1: _N, q1: _N, p2: _N, q2: _N) -> bool:
    o1, o2 = _signo(_ar(p1, q1, p2)), _signo(_ar(p1, q1, q2))
    o3, o4 = _signo(_ar(p2, q2, p1)), _signo(_ar(p2, q2, q1))
    if o1 != o2 and o3 != o4:
        return True
    return ((o1 == 0 and _sobre(p1, p2, q1)) or (o2 == 0 and _sobre(p1, q2, q1))
            or (o3 == 0 and _sobre(p2, p1, q2)) or (o4 == 0 and _sobre(p2, q1, q2)))


def _adentro_local(a: _N, b: _N) -> bool:
    if _ar(a.prev, a, a.next) < 0:
        return _ar(a, b, a.next) >= 0 and _ar(a, a.prev, b) >= 0
    return _ar(a, b, a.prev) < 0 or _ar(a, a.next, b) < 0


def _medio_adentro(a: _N, b: _N) -> bool:
    p, adentro = a, False
    px, py = (a.x + b.x) / 2, (a.y + b.y) / 2
    while True:
        if ((p.y > py) != (p.next.y > py)) and p.next.y != p.y and \
                px < (p.next.x - p.x) * (py - p.y) / (p.next.y - p.y) + p.x:
            adentro = not adentro
        p = p.next
        if p is a:
            return adentro


def _corta_poligono(a: _N, b: _N) -> bool:
    p = a
    while True:
        if p.i != a.i and p.next.i != a.i and p.i != b.i and p.next.i != b.i and _cruzan(p, p.next, a, b):
            return True
        p = p.next
        if p is a:
            return False


def _diagonal_ok(a: _N, b: _N) -> bool:
    return (a.next.i != b.i and a.prev.i != b.i and not _corta_poligono(a, b) and (
        (_adentro_local(a, b) and _adentro_local(b, a) and _medio_adentro(a, b)
         and bool(_ar(a.prev, a, b.prev) or _ar(a, b.prev, b)))
        or (_igual(a, b) and _ar(a.prev, a, a.next) > 0 and _ar(b.prev, b, b.next) > 0)))


def _partir(a: _N, b: _N) -> _N:
    a2, b2 = _N(a.i, a.x, a.y), _N(b.i, b.x, b.y)
    an, bp = a.next, b.prev
    a.next, b.prev = b, a
    a2.next, an.prev = an, a2
    b2.next, a2.prev = a2, b2
    bp.next, b2.prev = b2, bp
    return b2


def _curar(start: _N, tris: List[Tuple[int, int, int]]) -> Optional[_N]:
    p = start
    while True:
        a, b = p.prev, p.next.next
        if not _igual(a, b) and _cruzan(a, p, p.next, b) and _adentro_local(a, b) and _adentro_local(b, a):
            tris.append((a.i, p.i, b.i))
            _sacar(p)
            _sacar(p.next)
            p = start = b
        p = p.next
        if p is start:
            break
    return _filtrar(p)


def _dividir(start: _N, tris: List[Tuple[int, int, int]], prof: int) -> None:
    a = start
    while True:
        b = a.next.next
        while b is not a.prev:
            if a.i != b.i and _diagonal_ok(a, b):
                c = _partir(a, b)
                a2 = _filtrar(a, a.next)
                c2 = _filtrar(c, c.next)
                _orejas(a2, tris, 0, prof + 1)
                _orejas(c2, tris, 0, prof + 1)
                return
            b = b.next
        a = a.next
        if a is start:
            return


def _orejas(ear: Optional[_N], tris: List[Tuple[int, int, int]], pasada: int, prof: int = 0) -> None:
    if ear is None or prof > 200:
        return
    stop = ear
    while ear.prev is not ear.next:
        prev, nxt = ear.prev, ear.next
        if _es_oreja(ear):
            tris.append((prev.i, ear.i, nxt.i))
            _sacar(ear)
            ear = nxt.next
            stop = nxt.next
            continue
        ear = nxt
        if ear is stop:
            if pasada == 0:
                _orejas(_filtrar(ear), tris, 1, prof)
            elif pasada == 1:
                _orejas(_curar(_filtrar(ear), tris), tris, 2, prof)  # type: ignore[arg-type]
            else:
                _dividir(ear, tris, prof)
            break


def _mas_izq(start: _N) -> _N:
    p, izq = start, start
    while True:
        if p.x < izq.x or (p.x == izq.x and p.y < izq.y):
            izq = p
        p = p.next
        if p is start:
            return izq


def _sector(m: _N, p: _N) -> bool:
    return _ar(m.prev, m, p.prev) < 0 and _ar(p.next, m, m.next) < 0


def _puente(hole: _N, outer: _N) -> Optional[_N]:
    p = outer
    hx, hy = hole.x, hole.y
    qx = -math.inf
    m: Optional[_N] = None
    while True:
        if p.next.y != p.y and hy <= p.y and hy >= p.next.y:
            x = p.x + (hy - p.y) * (p.next.x - p.x) / (p.next.y - p.y)
            if hx >= x > qx:
                qx = x
                m = p if p.x < p.next.x else p.next
                if x == hx:
                    return m
        p = p.next
        if p is outer:
            break
    if m is None:
        return None
    stop, mx, my, tmin = m, m.x, m.y, math.inf
    p = m
    while True:
        if hx >= p.x >= mx and hx != p.x and _en_tri(hx if hy < my else qx, hy, mx, my, qx if hy < my else hx, hy, p.x, p.y):
            tan = abs(hy - p.y) / (hx - p.x)
            if _adentro_local(p, hole) and (tan < tmin or (tan == tmin and (p.x > m.x or (p.x == m.x and _sector(m, p))))):
                m, tmin = p, tan
        p = p.next
        if p is stop:
            return m


def triangular(lazos: Sequence[Sequence[Tuple[float, float]]]) -> List[Tuple[int, int, int]]:
    """Triángulos (índices en la lista de puntos de todos los lazos, en orden) del polígono
    cuyo primer lazo es el borde y los demás son agujeros."""
    pts: List[Tuple[float, float]] = []
    inicios = []
    for l in lazos:
        inicios.append(len(pts))
        pts.extend((float(a), float(b)) for a, b in l)
    if not lazos or len(lazos[0]) < 3:
        return []
    fin0 = inicios[1] if len(inicios) > 1 else len(pts)
    outer = _lista_enlazada(pts, 0, fin0, True)
    tris: List[Tuple[int, int, int]] = []
    if outer is None or outer.next is outer.prev:
        return tris
    if len(inicios) > 1:
        cola = []
        for k in range(1, len(inicios)):
            fin = inicios[k + 1] if k + 1 < len(inicios) else len(pts)
            if fin - inicios[k] < 3:
                continue
            l = _lista_enlazada(pts, inicios[k], fin, False)
            if l is None:
                continue
            if l is l.next:
                l.steiner = True
            cola.append(_mas_izq(l))
        cola.sort(key=lambda n: (n.x, n.y))
        for h in cola:
            b = _puente(h, outer)
            if b is None:
                continue
            br = _partir(b, h)
            _filtrar(br, br.next)
            outer = _filtrar(b, b.next)  # type: ignore[assignment]
    _orejas(outer, tris, 0)
    return tris


def _dominio(sup: "Superficie") -> Optional[Tuple[float, float, float, float]]:
    if isinstance(sup, Revolucion) and sup.tipo == "esfera":
        return 0.0, 2 * math.pi, -math.pi / 2, math.pi / 2
    if isinstance(sup, Revolucion) and sup.tipo == "toro":
        return 0.0, 2 * math.pi, 0.0, 2 * math.pi
    if isinstance(sup, BSplineSup):
        return sup.u0, sup.u1, sup.v0, sup.v1
    return None


def _en_circulo(a, b, c, d) -> bool:
    """d dentro del círculo que pasa por a, b, c (a, b, c antihorarios)."""
    adx, ady = a[0] - d[0], a[1] - d[1]
    bdx, bdy = b[0] - d[0], b[1] - d[1]
    cdx, cdy = c[0] - d[0], c[1] - d[1]
    det = ((adx * adx + ady * ady) * (bdx * cdy - cdx * bdy) - (bdx * bdx + bdy * bdy) * (adx * cdy - cdx * ady)
           + (cdx * cdx + cdy * cdy) * (adx * bdy - bdx * ady))
    L = max(abs(adx), abs(ady), abs(bdx), abs(bdy), abs(cdx), abs(cdy))
    return det > 1e-10 * L ** 4


def _delaunay(pts: Sequence[Tuple[float, float]], tris: List[Tuple[int, int, int]]) -> List[Tuple[int, int, int]]:
    """Da vuelta diagonales (sin tocar los bordes) hasta que los triángulos sean de Delaunay:
    el abanico que deja earcut pasa a tiras de triángulos parejos."""
    def ccw(t):
        a, b, c = t
        o = (pts[b][0] - pts[a][0]) * (pts[c][1] - pts[a][1]) - (pts[b][1] - pts[a][1]) * (pts[c][0] - pts[a][0])
        return t if o > 0 else (a, c, b)
    T = [ccw(t) for t in tris]
    lado: Dict[Tuple[int, int], int] = {}     # lado dirigido -> triángulo
    for i, (a, b, c) in enumerate(T):
        lado[(a, b)], lado[(b, c)], lado[(c, a)] = i, i, i
    pila = list(lado.keys())
    vueltas = 0
    while pila and vueltas < 400 * len(T) + 1000:
        a, b = pila.pop()
        i, j = lado.get((a, b)), lado.get((b, a))
        if i is None or j is None or i == j:
            continue
        c = next(x for x in T[i] if x != a and x != b)
        d = next(x for x in T[j] if x != a and x != b)
        if not _en_circulo(pts[a], pts[b], pts[c], pts[d]):
            continue
        # el cuadrilátero tiene que ser convexo para dar vuelta la diagonal
        def o(p, q, r):
            return (pts[q][0] - pts[p][0]) * (pts[r][1] - pts[p][1]) - (pts[q][1] - pts[p][1]) * (pts[r][0] - pts[p][0])
        if o(c, d, b) <= 0 or o(d, c, a) <= 0:
            continue
        for k in ((a, b), (b, c), (c, a)):
            lado.pop(k, None)
        for k in ((b, a), (a, d), (d, b)):
            lado.pop(k, None)
        T[i], T[j] = (c, a, d), (d, b, c)
        for k in ((c, a), (a, d), (d, c)):
            lado[k] = i
        for k in ((d, b), (b, c), (c, d)):
            lado[k] = j
        pila += [(a, d), (d, b), (b, c), (c, a)]
        vueltas += 1
    return T


# ---------------------------------------------------------------------------
# B-splines
# ---------------------------------------------------------------------------

def _nudos(mults: Sequence[float], knots: Sequence[float]) -> np.ndarray:
    out: List[float] = []
    for m, k in zip(mults, knots):
        out += [float(k)] * int(m)
    return np.asarray(out, dtype=float)


def _base(nudos: np.ndarray, p: int, n: int, t: np.ndarray) -> np.ndarray:
    """Funciones base N_{i,p}(t) (len(t) x n), con el algoritmo A2.2 de «The NURBS Book»."""
    k = nudos.tolist()
    t0, t1 = k[p], k[n]
    ts = np.atleast_1d(np.asarray(t, dtype=float)).tolist()
    out = np.zeros((len(ts), n))
    izq = [0.0] * (p + 1)
    der = [0.0] * (p + 1)
    for fila, x in enumerate(ts):
        x = t0 if x < t0 else t1 if x > t1 else x
        span = bisect.bisect_right(k, x) - 1
        span = p if span < p else n - 1 if span > n - 1 else span
        N = [1.0] + [0.0] * p
        for j in range(1, p + 1):
            izq[j] = x - k[span + 1 - j]
            der[j] = k[span + j] - x
            guardado = 0.0
            for r in range(j):
                den = der[r + 1] + izq[j - r]
                tmp = N[r] / den if den else 0.0
                N[r] = guardado + der[r + 1] * tmp
                guardado = izq[j - r] * tmp
            N[j] = guardado
        out[fila, span - p:span + 1] = N
    return out


# ---------------------------------------------------------------------------
# Curvas
# ---------------------------------------------------------------------------

class Curva:
    t0 = 0.0
    t1 = 1.0
    periodo: Optional[float] = None

    def pt(self, t: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def param(self, p: np.ndarray) -> float:
        """Parámetro del punto más cercano de la curva."""
        ts = np.linspace(self.t0, self.t1, 241)
        d = np.linalg.norm(self.pt(ts) - p, axis=1)
        i = int(np.argmin(d))
        a, b = ts[max(i - 1, 0)], ts[min(i + 1, len(ts) - 1)]
        for _ in range(30):        # sección dorada alrededor del mínimo
            m1, m2 = a + (b - a) * 0.382, a + (b - a) * 0.618
            d1, d2 = np.linalg.norm(self.pt(np.array([m1, m2])) - p, axis=1)
            if d1 < d2:
                b = m2
            else:
                a = m1
        return (a + b) / 2


class Linea(Curva):
    def __init__(self, o: np.ndarray, d: np.ndarray) -> None:
        self.o, self.d = o, _unit(d)
        self.t0, self.t1 = -1e9, 1e9

    def pt(self, t):
        t = np.atleast_1d(t)
        return self.o[None, :] + t[:, None] * self.d[None, :]

    def param(self, p):
        return float(np.dot(p - self.o, self.d))


class Conica(Curva):
    """Círculo (a = b = radio) o elipse en su marco."""

    def __init__(self, o, x, y, a: float, b: float) -> None:
        self.o, self.x, self.y, self.a, self.b = o, x, y, a, b
        self.t0, self.t1, self.periodo = 0.0, 2 * math.pi, 2 * math.pi

    def pt(self, t):
        t = np.atleast_1d(t)
        return (self.o[None, :] + (self.a * np.cos(t))[:, None] * self.x[None, :]
                + (self.b * np.sin(t))[:, None] * self.y[None, :])

    def param(self, p):
        d = p - self.o
        return math.atan2(float(np.dot(d, self.y)) / max(self.b, 1e-12), float(np.dot(d, self.x)) / max(self.a, 1e-12)) % (2 * math.pi)


class Hiperbola(Curva):
    def __init__(self, o, x, y, a: float, b: float, parabola: bool = False) -> None:
        self.o, self.x, self.y, self.a, self.b, self.parabola = o, x, y, a, b, parabola
        self.t0, self.t1 = -50.0, 50.0

    def pt(self, t):
        t = np.atleast_1d(t)
        if self.parabola:     # a = distancia focal
            cx, cy = self.a * t * t, 2 * self.a * t
        else:
            cx, cy = self.a * np.cosh(t), self.b * np.sinh(t)
        return self.o[None, :] + cx[:, None] * self.x[None, :] + cy[:, None] * self.y[None, :]

    def param(self, p):
        dy = float(np.dot(p - self.o, self.y))
        return dy / (2 * self.a) if self.parabola else math.asinh(dy / max(self.b, 1e-12))


class BSplineCurva(Curva):
    def __init__(self, grado: int, ctrl: np.ndarray, nudos: np.ndarray, pesos: Optional[np.ndarray],
                 cerrada: bool) -> None:
        self.p, self.c, self.k = grado, ctrl, nudos
        self.w = pesos
        n = len(ctrl)
        self.t0, self.t1 = float(nudos[grado]), float(nudos[n])
        self.cerrada = cerrada

    def pt(self, t):
        N = _base(self.k, self.p, len(self.c), np.atleast_1d(t))
        if self.w is None:
            return N @ self.c
        Nw = N * self.w[None, :]
        return (Nw @ self.c) / Nw.sum(axis=1)[:, None]


class Polilinea(Curva):
    def __init__(self, pts: np.ndarray) -> None:
        self.ps = pts
        self.t0, self.t1 = 0.0, float(len(pts) - 1)

    def pt(self, t):
        t = np.clip(np.atleast_1d(t), 0, len(self.ps) - 1)
        i = np.minimum(np.floor(t).astype(int), len(self.ps) - 2)
        f = (t - i)[:, None]
        return self.ps[i] * (1 - f) + self.ps[i + 1] * f


# ---------------------------------------------------------------------------
# Superficies
# ---------------------------------------------------------------------------

class Superficie:
    periodo_u: Optional[float] = None
    periodo_v: Optional[float] = None
    plana = False

    def pt(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def uv(self, p: np.ndarray) -> Tuple[float, float]:
        raise NotImplementedError

    def normal(self, u: float, v: float) -> np.ndarray:
        h = 1e-5
        uu = np.array([u - h, u + h, u, u])
        vv = np.array([v, v, v - h, v + h])
        q = self.pt(uu, vv)
        return _unit(np.cross(q[1] - q[0], q[3] - q[2]))


class Plano(Superficie):
    plana = True

    def __init__(self, o, x, y, z) -> None:
        self.o, self.x, self.y, self.z = o, x, y, z

    def pt(self, u, v):
        u, v = np.atleast_1d(u), np.atleast_1d(v)
        return self.o[None, :] + u[:, None] * self.x[None, :] + v[:, None] * self.y[None, :]

    def uv(self, p):
        d = p - self.o
        return float(np.dot(d, self.x)), float(np.dot(d, self.y))

    def normal(self, u, v):
        return self.z


class Revolucion(Superficie):
    """Cilindro, cono, esfera y toro: u es el ángulo alrededor del eje z del marco."""
    periodo_u = 2 * math.pi

    def __init__(self, o, x, y, z, tipo: str, r: float, r2: float = 0.0, ang: float = 0.0) -> None:
        self.o, self.x, self.y, self.z = o, x, y, z
        self.tipo, self.r, self.r2, self.ang = tipo, r, r2, ang
        if tipo == "toro":
            self.periodo_v = 2 * math.pi

    def pt(self, u, v):
        u, v = np.atleast_1d(u).astype(float), np.atleast_1d(v).astype(float)
        cu, su = np.cos(u)[:, None], np.sin(u)[:, None]
        radial = cu * self.x[None, :] + su * self.y[None, :]
        if self.tipo == "cilindro":
            return self.o + self.r * radial + v[:, None] * self.z
        if self.tipo == "cono":
            return self.o + (self.r + v * math.tan(self.ang))[:, None] * radial + v[:, None] * self.z
        if self.tipo == "esfera":
            return self.o + self.r * (np.cos(v)[:, None] * radial + np.sin(v)[:, None] * self.z)
        # toro: r = radio mayor, r2 = menor
        return self.o + (self.r + self.r2 * np.cos(v))[:, None] * radial + (self.r2 * np.sin(v))[:, None] * self.z

    def uv(self, p):
        d = p - self.o
        px, py, pz = float(np.dot(d, self.x)), float(np.dot(d, self.y)), float(np.dot(d, self.z))
        u = math.atan2(py, px)
        if self.tipo in ("cilindro", "cono"):
            return u, pz
        if self.tipo == "esfera":
            return u, math.asin(max(-1.0, min(1.0, pz / max(self.r, 1e-12))))
        return u, math.atan2(pz, math.hypot(px, py) - self.r)

    def normal(self, u, v):
        radial = math.cos(u) * self.x + math.sin(u) * self.y
        if self.tipo == "cilindro":
            return radial
        if self.tipo == "cono":
            return _unit(radial - math.tan(self.ang) * self.z)
        return _unit(math.cos(v) * radial + math.sin(v) * self.z)


class BSplineSup(Superficie):
    def __init__(self, gu: int, gv: int, ctrl: np.ndarray, ku: np.ndarray, kv: np.ndarray,
                 pesos: Optional[np.ndarray], cerrada_u: bool, cerrada_v: bool) -> None:
        self.gu, self.gv, self.c, self.ku, self.kv, self.w = gu, gv, ctrl, ku, kv, pesos
        nu, nv = ctrl.shape[0], ctrl.shape[1]
        self.u0, self.u1 = float(ku[gu]), float(ku[nu])
        self.v0, self.v1 = float(kv[gv]), float(kv[nv])
        if cerrada_u:
            self.periodo_u = self.u1 - self.u0
        if cerrada_v:
            self.periodo_v = self.v1 - self.v0
        self._malla: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None

    def pt(self, u, v):
        u, v = np.atleast_1d(u), np.atleast_1d(v)
        nu, nv = self.c.shape[0], self.c.shape[1]
        if self.periodo_u:
            u = self.u0 + np.mod(u - self.u0, self.periodo_u)
        if self.periodo_v:
            v = self.v0 + np.mod(v - self.v0, self.periodo_v)
        Bu = _base(self.ku, self.gu, nu, u)       # (m, nu)
        Bv = _base(self.kv, self.gv, nv, v)       # (m, nv)
        if self.w is None:
            return np.einsum("mi,mj,ijk->mk", Bu, Bv, self.c)
        W = np.einsum("mi,mj,ij->m", Bu, Bv, self.w)
        return np.einsum("mi,mj,ij,ijk->mk", Bu, Bv, self.w, self.c) / W[:, None]

    def uv(self, p):
        if self._malla is None:
            us = np.linspace(self.u0, self.u1, 33)
            vs = np.linspace(self.v0, self.v1, 33)
            U, V = np.meshgrid(us, vs, indexing="ij")
            self._malla = (U.ravel(), V.ravel(), self.pt(U.ravel(), V.ravel()))
        U, V, P = self._malla
        i = int(np.argmin(np.sum((P - p) ** 2, axis=1)))
        u, v = float(U[i]), float(V[i])
        du, dv = (self.u1 - self.u0) * 1e-6, (self.v1 - self.v0) * 1e-6
        for _ in range(12):        # Newton sobre la distancia
            q = self.pt(np.array([u, u + du, u]), np.array([v, v, v + dv]))
            Su, Sv = (q[1] - q[0]) / du, (q[2] - q[0]) / dv
            r = q[0] - p
            A = np.array([[Su @ Su, Su @ Sv], [Su @ Sv, Sv @ Sv]])
            b = -np.array([r @ Su, r @ Sv])
            try:
                d = np.linalg.solve(A, b)
            except np.linalg.LinAlgError:
                break
            u = min(max(u + d[0], self.u0), self.u1) if not self.periodo_u else u + d[0]
            v = min(max(v + d[1], self.v0), self.v1) if not self.periodo_v else v + d[1]
            if abs(d[0]) < du and abs(d[1]) < dv:
                break
        return u, v


class Barrido(Superficie):
    """Superficie de revolución (u = ángulo, v = parámetro del perfil) o de extrusión
    (u = parámetro de la curva, v = distancia)."""

    def __init__(self, curva: Curva, tipo: str, o: np.ndarray, d: np.ndarray, largo: float = 1.0) -> None:
        self.curva, self.tipo, self.o, self.d, self.largo = curva, tipo, o, _unit(d), largo
        if tipo == "rev":
            self.periodo_u = 2 * math.pi
        self._perfil: Optional[Tuple[np.ndarray, np.ndarray]] = None

    def pt(self, u, v):
        u, v = np.atleast_1d(u).astype(float), np.atleast_1d(v).astype(float)
        if self.tipo == "ext":
            return self.curva.pt(u) + (v * self.largo)[:, None] * self.d[None, :]
        c = self.curva.pt(v) - self.o
        ax = (c @ self.d)[:, None] * self.d[None, :]
        rad = c - ax
        return self.o + ax + np.cos(u)[:, None] * rad + np.sin(u)[:, None] * np.cross(self.d, rad)

    def _muestras(self) -> Tuple[np.ndarray, np.ndarray]:
        if self._perfil is None:
            c = self.curva
            t0, t1 = (c.t0, c.t1) if abs(c.t1 - c.t0) < 1e8 else (-1e3, 1e3)
            ts = np.linspace(t0, t1, 400)
            self._perfil = (ts, c.pt(ts))
        return self._perfil

    def uv(self, p):
        ts, P = self._muestras()
        if self.tipo == "ext":
            q = p - P
            q = q - (q @ self.d)[:, None] * self.d[None, :]
            i = int(np.argmin(np.sum(q * q, axis=1)))
            return float(ts[i]), float((p - P[i]) @ self.d) / self.largo
        rel = P - self.o
        h = rel @ self.d
        rr = np.linalg.norm(rel - h[:, None] * self.d[None, :], axis=1)
        q = p - self.o
        hp = float(q @ self.d)
        radp = q - hp * self.d
        rp = float(np.linalg.norm(radp))
        i = int(np.argmin((h - hp) ** 2 + (rr - rp) ** 2))
        v = float(ts[i])
        c = rel[i] - h[i] * self.d
        if np.linalg.norm(c) < 1e-9 or rp < 1e-9:
            return 0.0, v
        e1 = _unit(c)
        e2 = np.cross(self.d, e1)
        return math.atan2(float(radp @ e2), float(radp @ e1)), v


class Desplazada(Superficie):
    def __init__(self, base: Superficie, dist: float) -> None:
        self.base, self.dist = base, dist
        self.periodo_u, self.periodo_v = base.periodo_u, base.periodo_v

    def pt(self, u, v):
        u, v = np.atleast_1d(u), np.atleast_1d(v)
        q = self.base.pt(u, v)
        n = np.array([self.base.normal(a, b) for a, b in zip(u, v)])
        return q + self.dist * n

    def uv(self, p):
        return self.base.uv(p)

    def normal(self, u, v):
        return self.base.normal(u, v)


# ---------------------------------------------------------------------------
# El modelo
# ---------------------------------------------------------------------------

SOLIDOS = ("MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS", "FACETED_BREP", "SHELL_BASED_SURFACE_MODEL")


@dataclass
class Malla:
    """Triángulos del modelo ya en mm y en las coordenadas del archivo."""
    vertices: np.ndarray            # (n, 3)
    triangulos: np.ndarray          # (m, 3) índices, girando hacia afuera
    aristas: List[np.ndarray]       # polilíneas (k, 3) de las aristas reales
    avisos: List[str] = field(default_factory=list)
    solidos: List[Tuple[int, np.ndarray]] = field(default_factory=list)   # (id del sólido, matriz en mm)
    escala: float = 1.0             # mm por unidad del archivo

    @property
    def caja(self) -> Tuple[np.ndarray, np.ndarray]:
        if len(self.vertices) == 0:
            return np.zeros(3), np.zeros(3)
        return self.vertices.min(axis=0), self.vertices.max(axis=0)


class ModeloStep:
    """Un archivo STEP leído: sus entidades y cómo pasarlo a triángulos."""

    def __init__(self, texto: str) -> None:
        self.texto = _COMENTARIO.sub(lambda m: " " * len(m.group()), texto)
        self.e = leer_texto(self.texto)
        self.avisos: List[str] = []
        self._pts: Dict[int, np.ndarray] = {}
        self._curvas: Dict[int, Optional[Curva]] = {}
        self._sup: Dict[int, Optional[Superficie]] = {}
        self._aristas: Dict[int, np.ndarray] = {}
        self._no_entiendo: Dict[str, int] = {}
        self._tramos: List[Tuple[int, int]] = []
        self.angulo = self._unidad_angulo()
        self.escala = self._unidad_largo()
        self.tol = 0.1

    # ---------------------------------------------------------------- utilidades
    def ent(self, r: Any) -> Entidad:
        if not isinstance(r, Ref) or int(r) not in self.e:
            raise ErrorStep(f"falta la entidad #{r}")
        return self.e[int(r)]

    def texto_de(self, eid: int) -> str:
        e = self.e[eid]
        return self.texto[e.desde:e.hasta].strip()

    def _no(self, que: str) -> None:
        self._no_entiendo[que] = self._no_entiendo.get(que, 0) + 1

    def _unidad_largo(self) -> float:
        """mm por unidad de largo del archivo (del primer contexto con unidades)."""
        for e in self.e.values():
            g = e.parte("GLOBAL_UNIT_ASSIGNED_CONTEXT")
            if not g:
                continue
            for r in g[0]:
                f = self._factor_unidad(self.ent(r), "LENGTH_UNIT")
                if f:
                    return f
        return 1.0

    def _unidad_angulo(self) -> float:
        for e in self.e.values():
            g = e.parte("GLOBAL_UNIT_ASSIGNED_CONTEXT")
            if not g:
                continue
            for r in g[0]:
                f = self._factor_unidad(self.ent(r), "PLANE_ANGLE_UNIT", radianes=True)
                if f:
                    return f
        return 1.0

    def _factor_unidad(self, u: Entidad, clase: str, radianes: bool = False) -> Optional[float]:
        if clase not in u.partes and u.tipo != clase:
            return None
        si = u.parte("SI_UNIT")
        if si is not None:
            pref = {"MILLI": 1e-3, "CENTI": 1e-2, "DECI": 0.1, "MICRO": 1e-6, "KILO": 1e3, "NANO": 1e-9}.get(
                si[0] or "", 1.0) if si and si[0] else 1.0
            return pref if radianes else pref * 1000.0
        cb = u.parte("CONVERSION_BASED_UNIT")
        if cb is not None:
            m = self.ent(cb[1])
            args = m.parte(m.tipo or next(iter(m.partes))) or []
            val = args[0].args[0] if args and isinstance(args[0], Tipado) else (args[0] if args else 1.0)
            base = self._factor_unidad(self.ent(args[1]), clase, radianes) if len(args) > 1 and isinstance(args[1], Ref) else None
            return float(val) * (base if base else (1.0 if radianes else 1000.0))
        return None

    def punto(self, r: Any) -> np.ndarray:
        i = int(r)
        if i not in self._pts:
            e = self.ent(r)
            if e.tipo == "VERTEX_POINT":
                self._pts[i] = self.punto(e.args[1])
            else:
                c = list(e.args[1]) + [0.0] * (3 - len(e.args[1]))
                self._pts[i] = np.array(c[:3], dtype=float)
        return self._pts[i]

    def direccion(self, r: Any) -> np.ndarray:
        e = self.ent(r)
        c = list(e.args[1]) + [0.0] * (3 - len(e.args[1]))
        return np.array(c[:3], dtype=float)

    def ejes(self, r: Any) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(origen, x, y, z) de un AXIS2_PLACEMENT_3D."""
        e = self.ent(r)
        o = self.punto(e.args[1])
        if e.tipo == "AXIS2_PLACEMENT_2D":
            x = self.direccion(e.args[2]) if len(e.args) > 2 and e.args[2] is not None else None
            x_, y_, z_ = _marco((0, 0, 1), x)
            return o, x_, y_, z_
        z = self.direccion(e.args[2]) if len(e.args) > 2 and e.args[2] is not None else np.array([0, 0, 1.0])
        x = self.direccion(e.args[3]) if len(e.args) > 3 and e.args[3] is not None else None
        x_, y_, z_ = _marco(z, x)
        return o, x_, y_, z_

    def matriz_ejes(self, r: Any) -> np.ndarray:
        return _matriz(*self.ejes(r))

    # ---------------------------------------------------------------- curvas
    def curva(self, r: Any) -> Optional[Curva]:
        i = int(r)
        if i in self._curvas:
            return self._curvas[i]
        e = self.ent(r)
        c: Optional[Curva] = None
        try:
            c = self._curva(e)
        except (ErrorStep, IndexError, TypeError, ValueError, np.linalg.LinAlgError):
            c = None
        self._curvas[i] = c
        return c

    def _curva(self, e: Entidad) -> Optional[Curva]:
        t = e.tipo
        if t == "LINE":
            o = self.punto(e.args[1])
            v = self.ent(e.args[2])
            return Linea(o, self.direccion(v.args[1]))
        if t == "CIRCLE":
            o, x, y, _z = self.ejes(e.args[1])
            return Conica(o, x, y, float(e.args[2]), float(e.args[2]))
        if t == "ELLIPSE":
            o, x, y, _z = self.ejes(e.args[1])
            return Conica(o, x, y, float(e.args[2]), float(e.args[3]))
        if t == "HYPERBOLA":
            o, x, y, _z = self.ejes(e.args[1])
            return Hiperbola(o, x, y, float(e.args[2]), float(e.args[3]))
        if t == "PARABOLA":
            o, x, y, _z = self.ejes(e.args[1])
            return Hiperbola(o, x, y, float(e.args[2]), 0.0, True)
        if t in ("SURFACE_CURVE", "SEAM_CURVE", "INTERSECTION_CURVE"):
            return self.curva(e.args[1])
        if t == "TRIMMED_CURVE":
            return self.curva(e.args[1])
        if t == "POLYLINE":
            return Polilinea(np.array([self.punto(p) for p in e.args[1]]))
        if t == "B_SPLINE_CURVE_WITH_KNOTS":
            a = e.args
            ctrl = np.array([self.punto(p) for p in a[2]])
            return BSplineCurva(int(a[1]), ctrl, _nudos(a[6], a[7]), None, a[4] == "T")
        if e.partes and "B_SPLINE_CURVE" in e.partes:
            bc = e.partes["B_SPLINE_CURVE"]
            ctrl = np.array([self.punto(p) for p in bc[1]])
            kn = e.partes.get("B_SPLINE_CURVE_WITH_KNOTS")
            if kn is None:
                if "BEZIER_CURVE" in e.partes:
                    g = int(bc[0])
                    nudos = np.array([0.0] * (g + 1) + [1.0] * (g + 1))
                else:
                    self._no("curva B-spline sin nudos")
                    return None
            else:
                nudos = _nudos(kn[0], kn[1])
            ra = e.partes.get("RATIONAL_B_SPLINE_CURVE")
            pesos = np.array(ra[0], dtype=float) if ra else None
            return BSplineCurva(int(bc[0]), ctrl, nudos, pesos, bc[3] == "T")
        self._no(f"curva {e.tipo or '/'.join(e.partes)}")
        return None

    def _pasos(self, angulo: float, radio: float) -> int:
        if radio <= 0:
            return 1
        cuerda = 2 * math.acos(max(-1.0, min(1.0, 1 - self.tol / radio))) if radio > self.tol else math.pi / 2
        paso = min(max(cuerda, math.radians(6)), math.radians(20))
        return max(1, int(math.ceil(abs(angulo) / paso)))

    def arista(self, r: Any) -> np.ndarray:
        """Puntos (en unidades del archivo) de un EDGE_CURVE, del vértice inicial al final."""
        i = int(r)
        if i in self._aristas:
            return self._aristas[i]
        e = self.ent(r)
        a, b = self.punto(e.args[1]), self.punto(e.args[2])
        c = self.curva(e.args[3]) if len(e.args) > 3 else None
        mismo = len(e.args) < 5 or e.args[4] != "F"
        pts: np.ndarray
        if isinstance(c, Polilinea):
            pts = c.ps if mismo else c.ps[::-1]
        elif c is None or isinstance(c, Linea):
            pts = np.array([a, b])
        else:
            ta, tb = c.param(a), c.param(b)
            cerrada = float(np.linalg.norm(a - b)) < 1e-7 * max(1.0, float(np.linalg.norm(a)))
            if c.periodo:
                if mismo:
                    if tb <= ta + 1e-9:
                        tb += c.periodo
                else:
                    if tb >= ta - 1e-9:
                        tb -= c.periodo
                if cerrada:
                    tb = ta + (c.periodo if mismo else -c.periodo)
            elif cerrada:
                ta, tb = (c.t0, c.t1) if mismo else (c.t1, c.t0)
            if isinstance(c, Conica):
                n = self._pasos(tb - ta, max(c.a, c.b))
            else:
                ts = np.linspace(ta, tb, 33)
                q = c.pt(ts)
                largo = float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1)))
                # cuánto se dobla: ángulo total entre tramos
                d = np.diff(q, axis=0)
                d = d / np.maximum(np.linalg.norm(d, axis=1), 1e-12)[:, None]
                giro = float(np.sum(np.arccos(np.clip(np.sum(d[1:] * d[:-1], axis=1), -1, 1))))
                n = max(1, int(math.ceil(giro / math.radians(10))), int(largo / max(self.tol * 400, 1e-9)))
                n = min(n, 200)
            ts = np.linspace(ta, tb, n + 1)
            pts = c.pt(ts)
            pts[0], pts[-1] = a, b
        self._aristas[i] = pts
        return pts

    def lazo(self, r: Any, sentido: bool) -> Tuple[List[np.ndarray], List[int]]:
        """Puntos de un lazo (sin repetir el primero) y las aristas que lo forman."""
        e = self.ent(r)
        if e.tipo == "POLY_LOOP":
            pts = [self.punto(p) for p in e.args[1]]
            return (pts if sentido else pts[::-1]), []
        if e.tipo == "VERTEX_LOOP":
            return [self.punto(e.args[1])], []
        if e.tipo != "EDGE_LOOP":
            self._no(f"lazo {e.tipo}")
            return [], []
        pts: List[np.ndarray] = []
        usadas = []
        self._tramos = []
        for oe_r in e.args[1]:
            oe = self.ent(oe_r)
            ec = oe.args[3]
            q = self.arista(ec)
            if oe.args[4] == "F":
                q = q[::-1]
            usadas.append(int(ec))
            self._tramos.append((int(ec), len(pts)))
            pts.extend(q[:-1])
        if not sentido:
            pts = pts[::-1]
            n = len(pts)
            self._tramos = [(a, n - i) for a, i in self._tramos]
        return pts, usadas

    # ---------------------------------------------------------------- superficies
    def superficie(self, r: Any) -> Optional[Superficie]:
        i = int(r)
        if i in self._sup:
            return self._sup[i]
        try:
            s = self._superficie(self.ent(r))
        except (ErrorStep, IndexError, TypeError, ValueError, np.linalg.LinAlgError):
            s = None
        self._sup[i] = s
        return s

    def _superficie(self, e: Entidad) -> Optional[Superficie]:
        t = e.tipo
        if t == "PLANE":
            return Plano(*self.ejes(e.args[1]))
        if t == "CYLINDRICAL_SURFACE":
            return Revolucion(*self.ejes(e.args[1]), "cilindro", float(e.args[2]))
        if t == "CONICAL_SURFACE":
            return Revolucion(*self.ejes(e.args[1]), "cono", float(e.args[2]), ang=float(e.args[3]) * self.angulo)
        if t == "SPHERICAL_SURFACE":
            return Revolucion(*self.ejes(e.args[1]), "esfera", float(e.args[2]))
        if t == "TOROIDAL_SURFACE" or t == "DEGENERATE_TOROIDAL_SURFACE":
            return Revolucion(*self.ejes(e.args[1]), "toro", float(e.args[2]), float(e.args[3]))
        if t == "SURFACE_OF_REVOLUTION":
            c = self.curva(e.args[1])
            ax = self.ent(e.args[2])
            if c is None:
                return None
            return Barrido(c, "rev", self.punto(ax.args[1]), self.direccion(ax.args[2]))
        if t == "SURFACE_OF_LINEAR_EXTRUSION":
            c = self.curva(e.args[1])
            v = self.ent(e.args[2])
            if c is None:
                return None
            return Barrido(c, "ext", np.zeros(3), self.direccion(v.args[1]), float(v.args[2]))
        if t == "OFFSET_SURFACE":
            b = self.superficie(e.args[1])
            return Desplazada(b, float(e.args[2])) if b else None
        if t in ("RECTANGULAR_TRIMMED_SURFACE", "CURVE_BOUNDED_SURFACE"):
            return self.superficie(e.args[1])
        if t == "B_SPLINE_SURFACE_WITH_KNOTS":
            a = e.args
            ctrl = np.array([[self.punto(p) for p in fila] for fila in a[3]])
            return BSplineSup(int(a[1]), int(a[2]), ctrl, _nudos(a[8], a[10]), _nudos(a[9], a[11]), None,
                              a[5] == "T", a[6] == "T")
        if e.partes and "B_SPLINE_SURFACE" in e.partes:
            bs = e.partes["B_SPLINE_SURFACE"]
            ctrl = np.array([[self.punto(p) for p in fila] for fila in bs[2]])
            kn = e.partes.get("B_SPLINE_SURFACE_WITH_KNOTS")
            if kn is None:
                if "BEZIER_SURFACE" in e.partes:
                    gu, gv = int(bs[0]), int(bs[1])
                    ku = np.array([0.0] * (gu + 1) + [1.0] * (gu + 1))
                    kv = np.array([0.0] * (gv + 1) + [1.0] * (gv + 1))
                else:
                    self._no("superficie B-spline sin nudos")
                    return None
            else:
                ku, kv = _nudos(kn[0], kn[2]), _nudos(kn[1], kn[3])
            ra = e.partes.get("RATIONAL_B_SPLINE_SURFACE")
            pesos = np.array(ra[0], dtype=float) if ra else None
            return BSplineSup(int(bs[0]), int(bs[1]), ctrl, ku, kv, pesos, bs[4] == "T", bs[5] == "T")
        self._no(f"superficie {e.tipo or '/'.join(e.partes)}")
        return None

    # ---------------------------------------------------------------- caras
    def cara(self, r: Any, V: List[np.ndarray], T: List[Tuple[int, int, int]],
             usos: Dict[int, int]) -> None:
        """Agrega los triángulos de una cara (en unidades del archivo)."""
        e = self.ent(r)
        if e.tipo == "FACE_SURFACE" or e.tipo == "ADVANCED_FACE":
            limites, sup_r, mismo = e.args[1], e.args[2], e.args[3] != "F"
        elif e.tipo in ("FACE", "ORIENTED_FACE"):
            if e.tipo == "ORIENTED_FACE":
                return self.cara(e.args[2], V, T, usos)
            limites, sup_r, mismo = e.args[1], None, True
        else:
            self._no(f"cara {e.tipo}")
            return
        lazos: List[List[np.ndarray]] = []
        tramos: List[List[Tuple[int, int]]] = []
        aristas_cara: List[int] = []
        for lr in limites:
            lb = self.ent(lr)
            self._tramos = []
            pts, usadas = self.lazo(lb.args[1], lb.args[2] != "F")
            aristas_cara += usadas
            if len(pts) >= 3:
                lazos.append(pts)
                tramos.append(list(self._tramos))
        # las aristas que la cara usa dos veces son costuras (no se dibujan)
        cuenta: Dict[int, int] = {}
        for a in aristas_cara:
            cuenta[a] = cuenta.get(a, 0) + 1
        for a, n in cuenta.items():
            usos[a] = usos.get(a, 0) + (1 if n == 1 else -1000)
        sup = self.superficie(sup_r) if sup_r is not None else None
        if sup_r is not None and sup is None:
            return
        if not lazos:
            # esfera, toro o superficie cerrada entera (sólo un VERTEX_LOOP o nada de borde)
            dom = _dominio(sup) if sup is not None else None
            if dom is None:
                return
            u0, u1, v0, v1 = dom
            n = 8
            uv = np.array([(u0 + (u1 - u0) * i / n, v0) for i in range(n)] + [(u1, v0 + (v1 - v0) * i / n) for i in range(n)]
                          + [(u1 - (u1 - u0) * i / n, v1) for i in range(n)] + [(u0, v1 - (v1 - v0) * i / n) for i in range(n)])
            pts = list(sup.pt(uv[:, 0], uv[:, 1]))
            self._triangular_lazos(sup, [(pts, uv, 0)], mismo, V, T)
            return
        if sup is None:       # FACE / POLY_LOOP: el plano del borde
            p = np.array(lazos[0])
            n = np.zeros(3)
            for i in range(len(p)):
                q, w = p[i], p[(i + 1) % len(p)]
                n += np.cross(q, w)
            o = p[0]
            x_, y_, z_ = _marco(n if np.linalg.norm(n) > 1e-12 else (0, 0, 1), p[1] - p[0])
            sup = Plano(o, x_, y_, z_)
        self._triangular_cara(sup, lazos, mismo, V, T, tramos)

    def _a_uv(self, sup: Superficie, pts: List[np.ndarray]) -> np.ndarray:
        uv = np.array([sup.uv(p) for p in pts], dtype=float)
        for k, per in ((0, sup.periodo_u), (1, sup.periodo_v)):
            if per:
                for i in range(1, len(uv)):    # sin saltos de un período
                    d = uv[i, k] - uv[i - 1, k]
                    uv[i, k] -= per * round(d / per)
        # polos de la esfera: u indefinido, se toma el de los vecinos
        if isinstance(sup, Revolucion) and sup.tipo in ("esfera", "cono"):
            for i, p in enumerate(pts):
                d = p - sup.o
                eje = float(np.dot(d, sup.z))
                if np.linalg.norm(d - eje * sup.z) < 1e-9 * max(1.0, sup.r) and len(pts) > 2:
                    a, b = uv[i - 1, 0], uv[(i + 1) % len(pts), 0]
                    uv[i, 0] = (a + b) / 2
        return uv

    def _costura(self, sup: Superficie, uv: np.ndarray, tramos: List[Tuple[int, int]]) -> np.ndarray:
        """Un lazo que pasa dos veces por la misma arista (la costura de una esfera, sin otras
        aristas) da área cero en (u, v): la segunda pasada va un período más allá."""
        if abs(_area2(uv)) > 1e-9 or not (sup.periodo_u or sup.periodo_v):
            return uv
        vistos: Dict[int, int] = {}
        segunda = None
        for a, i in sorted(tramos, key=lambda t: t[1]):
            if a in vistos:
                segunda = i
                break
            vistos[a] = i
        if segunda is None:
            return uv
        mejor, area = uv, 0.0
        for k, per in ((0, sup.periodo_u), (1, sup.periodo_v)):
            if not per:
                continue
            for signo in (1, -1):
                prueba = uv.copy()
                prueba[segunda:, k] += signo * per
                ar = abs(_area2(prueba))
                if ar > area + 1e-9:
                    mejor, area = prueba, ar
        return mejor

    def _triangular_cara(self, sup: Superficie, lazos: List[List[np.ndarray]], mismo: bool,
                         V: List[np.ndarray], T: List[Tuple[int, int, int]],
                         tramos: Optional[List[List[Tuple[int, int]]]] = None) -> None:
        uvs = [self._a_uv(sup, l) for l in lazos]
        for i, uv in enumerate(uvs):
            uvs[i] = self._costura(sup, uv, (tramos or [])[i] if tramos and i < len(tramos) else [])
        # lazos que dan toda la vuelta en un período (cilindro sin costura): se cierran por un lado
        abiertos = []
        cerrados = []
        for l, uv in zip(lazos, uvs):
            vuelta = 0
            for k, per in ((0, sup.periodo_u), (1, sup.periodo_v)):
                if per and abs(round((uv[0, k] - uv[-1, k]) / per)) == 1:
                    vuelta = k + 1
            (abiertos if vuelta else cerrados).append((l, uv, vuelta))
        if abiertos:
            k = abiertos[0][2] - 1
            per = sup.periodo_u if k == 0 else sup.periodo_v
            if len(abiertos) == 2:
                (l1, a1, _), (l2, a2, _) = abiertos
                # cada lazo ordenado a lo largo del período, de inicio común
                def ordenar(l, a):
                    if a[-1, k] < a[0, k]:
                        l, a = l[::-1], a[::-1]
                    i0 = int(np.argmin(np.mod(a[:, k], per)))
                    l = l[i0:] + l[:i0]
                    a = np.vstack([a[i0:], a[:i0] + np.eye(2)[k] * per])
                    a[:, k] += -per * math.floor(a[0, k] / per)
                    return l, a
                l1, a1 = ordenar(l1, a1)
                l2, a2 = ordenar(l2, a2)
                # l1 de ida, la costura en +período, l2 de vuelta y la costura en 0
                e_k = np.eye(2)[k] * per
                pts = l1 + [l1[0]] + [l2[0]] + l2[::-1]
                uv = np.vstack([a1, a1[:1] + e_k, a2[:1] + e_k, a2[::-1]])
                cerrados.insert(0, (pts, uv, 0))
            else:
                self._no("cara de revolución completa con un solo borde")
                # se hace igual: el lazo y el segmento del período
                l, a, _ = abiertos[0]
                cerrados.insert(0, (l, a, 0))
        self._triangular_lazos(sup, cerrados, mismo, V, T)

    def _triangular_lazos(self, sup: Superficie, cerrados: list, mismo: bool, V: List[np.ndarray],
                          T: List[Tuple[int, int, int]]) -> None:
        if not cerrados:
            return
        # el borde: el lazo de más área en (u, v)
        areas = [abs(_area2(uv)) for _l, uv, _v in cerrados]
        i0 = int(np.argmax(areas))
        cerrados.insert(0, cerrados.pop(i0))
        # u y v con la medida que tienen sobre la pieza (mejores triángulos)
        todo = np.vstack([uv for _l, uv, _v in cerrados])
        esc = np.ones(2)
        if not sup.plana:
            c = (todo.max(axis=0) + todo.min(axis=0)) / 2
            h = np.maximum((todo.max(axis=0) - todo.min(axis=0)) * 1e-3, 1e-9)
            q = sup.pt(np.array([c[0] - h[0], c[0] + h[0], c[0], c[0]]), np.array([c[1], c[1], c[1] - h[1], c[1] + h[1]]))
            esc = np.array([np.linalg.norm(q[1] - q[0]) / (2 * h[0]), np.linalg.norm(q[3] - q[2]) / (2 * h[1])])
            esc = np.where(esc > 1e-9, esc, max(float(esc.max()), 1.0))
        planos = [[tuple(q) for q in uv * esc] for _l, uv, _v in cerrados]
        tris = triangular(planos)
        if not tris:
            return
        if not sup.plana:
            tris = _delaunay([p for l in planos for p in l], tris)
        uv_todos = np.vstack([uv for _l, uv, _v in cerrados])
        pts_todos = [p for l, _uv, _v in cerrados for p in l]
        base = len(V)
        if sup.plana:
            V.extend(pts_todos)
            for a, b, c in tris:
                self._agregar_tri(sup, mismo, V, T, base + a, base + b, base + c, None)
            return
        # superficies curvas: se subdividen los triángulos que se apartan de la superficie
        V.extend(pts_todos)
        uv_de: Dict[int, np.ndarray] = {base + i: uv_todos[i] for i in range(len(uv_todos))}
        medios: Dict[Tuple[int, int], int] = {}

        def medio(a: int, b: int) -> int:
            clave = (min(a, b), max(a, b))
            if clave not in medios:
                m = (uv_de[a] + uv_de[b]) / 2
                V.append(sup.pt(np.array([m[0]]), np.array([m[1]]))[0])
                uv_de[len(V) - 1] = m
                medios[clave] = len(V) - 1
            return medios[clave]

        desvio: Dict[Tuple[int, int], float] = {}

        def dev(x: int, y: int) -> float:
            clave = (min(x, y), max(x, y))
            if clave not in desvio:
                mm = (uv_de[x] + uv_de[y]) / 2
                qq = sup.pt(np.array([mm[0]]), np.array([mm[1]]))[0]
                desvio[clave] = float(np.linalg.norm(qq - (V[x] + V[y]) / 2))
            return desvio[clave]

        # los lados del borde vienen de las aristas: no se parten (pueden estar un poco fuera
        # de la superficie, según la tolerancia del programa que hizo el STEP)
        borde = set()
        k0 = base
        for l, _uv, _v in cerrados:
            n = len(l)
            for i in range(n):
                x, y = k0 + i, k0 + (i + 1) % n
                borde.add((min(x, y), max(x, y)))
            k0 += n
        for clave in borde:
            desvio[clave] = 0.0
        # se parte el lado que más se aparta de la superficie, hasta que ninguno se aparte
        pila = [(base + a, base + b, base + c, 0) for a, b, c in tris]
        while pila:
            a, b, c, prof = pila.pop()
            if prof < 16 and len(T) < 60000:
                lados = ((dev(a, b), 0), (dev(b, c), 1), (dev(c, a), 2))
                err, cual = max(lados)
                if err <= self.tol:
                    mc = (uv_de[a] + uv_de[b] + uv_de[c]) / 3
                    q = sup.pt(np.array([mc[0]]), np.array([mc[1]]))[0]
                    if float(np.linalg.norm(q - (V[a] + V[b] + V[c]) / 3)) > self.tol:
                        abc = (a, b, c)
                        libres = [i for i in range(3) if (min(abc[i], abc[(i + 1) % 3]), max(abc[i], abc[(i + 1) % 3]))
                                  not in borde]
                        if libres:      # se parte el lado más largo que no sea del borde
                            err = 2 * self.tol
                            cual = max(libres, key=lambda i: float(np.linalg.norm(V[abc[i]] - V[abc[(i + 1) % 3]])))
                if err > self.tol:
                    if cual == 0:
                        m = medio(a, b)
                        pila += [(a, m, c, prof + 1), (m, b, c, prof + 1)]
                    elif cual == 1:
                        m = medio(b, c)
                        pila += [(a, b, m, prof + 1), (a, m, c, prof + 1)]
                    else:
                        m = medio(c, a)
                        pila += [(a, b, m, prof + 1), (m, b, c, prof + 1)]
                    continue
            self._agregar_tri(sup, mismo, V, T, a, b, c, (uv_de[a] + uv_de[b] + uv_de[c]) / 3)

    def _agregar_tri(self, sup: Superficie, mismo: bool, V: List[np.ndarray], T: List[Tuple[int, int, int]],
                     a: int, b: int, c: int, uv: Optional[np.ndarray]) -> None:
        n = np.cross(V[b] - V[a], V[c] - V[a])
        if float(np.dot(n, n)) < 1e-24:
            return
        ns = sup.normal(float(uv[0]), float(uv[1])) if uv is not None else sup.normal(0.0, 0.0)
        if (float(np.dot(n, ns)) > 0) != mismo:
            b, c = c, b
        T.append((a, b, c))

    # ---------------------------------------------------------------- piezas
    def _caras_de(self, item: Entidad) -> List[Any]:
        """Caras de un sólido o modelo de superficies."""
        out: List[Any] = []
        t = item.tipo
        if t in ("MANIFOLD_SOLID_BREP", "FACETED_BREP"):
            capas = [item.args[1]]
        elif t == "BREP_WITH_VOIDS":
            capas = [item.args[1]] + list(item.args[2])
        elif t == "SHELL_BASED_SURFACE_MODEL":
            capas = list(item.args[1])
        else:
            return out
        for cr in capas:
            c = self.ent(cr)
            if c.tipo == "ORIENTED_CLOSED_SHELL":
                c = self.ent(c.args[2])
            if c.tipo in ("CLOSED_SHELL", "OPEN_SHELL"):
                out += list(c.args[1])
        return out

    def _items_rep(self, rep: Entidad) -> List[Any]:
        args = rep.args if rep.tipo else next((a for a in rep.partes.values() if len(a) >= 3), [])
        return list(args[1]) if len(args) > 1 and isinstance(args[1], list) else []

    def _reps(self) -> Dict[int, Entidad]:
        return {i: e for i, e in self.e.items()
                if (e.tipo.endswith("REPRESENTATION") and e.tipo.endswith("SHAPE_REPRESENTATION"))
                or any(p.endswith("SHAPE_REPRESENTATION") for p in e.partes)}

    def solidos_ubicados(self) -> List[Tuple[int, np.ndarray]]:
        """(id del sólido, matriz 4x4 en unidades del archivo) de cada pieza del modelo, con las
        ubicaciones del ensamble aplicadas."""
        reps = self._reps()
        padres: Dict[int, List[Tuple[int, np.ndarray]]] = {}    # hijo -> [(padre, matriz)]
        con_solidos = {i for i, r in reps.items()
                       if any(isinstance(it, Ref) and int(it) in self.e and self.e[int(it)].tipo in SOLIDOS
                              for it in self._items_rep(r))}
        for e in self.e.values():
            rr = e.parte("REPRESENTATION_RELATIONSHIP")
            if rr is None:
                if e.tipo in ("SHAPE_REPRESENTATION_RELATIONSHIP", "REPRESENTATION_RELATIONSHIP"):
                    rr = e.args
                else:
                    continue
            if len(rr) < 4 or not isinstance(rr[2], Ref) or not isinstance(rr[3], Ref):
                continue
            r1, r2 = int(rr[2]), int(rr[3])
            tr = e.parte("REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION")
            if tr:
                idt = self.ent(tr[0])
                if idt.tipo == "ITEM_DEFINED_TRANSFORMATION":
                    m = self.matriz_ejes(idt.args[3]) @ np.linalg.inv(self.matriz_ejes(idt.args[2]))
                else:
                    m = np.eye(4)
                padres.setdefault(r1, []).append((r2, m))
            else:
                # sin ubicación: une la representación de la forma con la de los sólidos
                hijo, padre = (r1, r2) if r1 in con_solidos and r2 not in con_solidos else (r2, r1)
                padres.setdefault(hijo, []).append((padre, np.eye(4)))
        # MAPPED_ITEM: una representación puesta dentro de otra
        for i, r in reps.items():
            for it in self._items_rep(r):
                if not isinstance(it, Ref) or int(it) not in self.e:
                    continue
                mi = self.e[int(it)]
                if mi.tipo != "MAPPED_ITEM":
                    continue
                rm = self.ent(mi.args[1])
                m = self.matriz_ejes(mi.args[2]) @ np.linalg.inv(self.matriz_ejes(rm.args[0]))
                padres.setdefault(int(rm.args[1]), []).append((i, m))

        memo: Dict[int, List[np.ndarray]] = {}

        def mundo(rid: int, visto: Tuple[int, ...] = ()) -> List[np.ndarray]:
            if rid in memo:
                return memo[rid]
            ps = [(p, m) for p, m in padres.get(rid, []) if p not in visto]
            if not ps:
                out = [np.eye(4)]
            else:
                out = []
                for p, m in ps:
                    for mp in mundo(p, visto + (rid,)):
                        out.append(mp @ m)
                        if len(out) > 2000:
                            break
            memo[rid] = out
            return out

        res: List[Tuple[int, np.ndarray]] = []
        for i in sorted(con_solidos):
            for it in self._items_rep(reps[i]):
                if isinstance(it, Ref) and int(it) in self.e and self.e[int(it)].tipo in SOLIDOS:
                    for m in mundo(i):
                        res.append((int(it), m))
        if not res:     # sin representaciones: todos los sólidos tal cual
            res = [(i, np.eye(4)) for i, e in self.e.items() if e.tipo in SOLIDOS]
        return res

    def malla(self, tol_mm: Optional[float] = None) -> Malla:
        """Todos los sólidos del modelo en triángulos (en mm)."""
        solidos = self.solidos_ubicados()
        if not solidos:
            raise ErrorStep("el archivo no tiene sólidos ni superficies (¿es un dibujo 2D?)")
        # tamaño aproximado para elegir la tolerancia
        pts = np.array([self.punto(e.args[1]) for e in self.e.values() if e.tipo == "VERTEX_POINT"] or [[0, 0, 0]])
        radio = 0.0
        for e in self.e.values():
            if e.tipo in ("CIRCLE", "CYLINDRICAL_SURFACE", "SPHERICAL_SURFACE", "CONICAL_SURFACE"):
                radio = max(radio, float(e.args[2]))
            elif e.tipo == "TOROIDAL_SURFACE":
                radio = max(radio, float(e.args[2]) + float(e.args[3]))
        diag = max(float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))), 2 * radio) * self.escala
        tol_mm = tol_mm or min(max(diag / 250.0, 0.02), 0.5)
        self.tol = tol_mm / self.escala
        cache: Dict[int, Tuple[np.ndarray, np.ndarray, List[np.ndarray]]] = {}
        Vt: List[np.ndarray] = []
        Tt: List[np.ndarray] = []
        At: List[np.ndarray] = []
        n0 = 0
        for sid, m in solidos:
            if sid not in cache:
                V: List[np.ndarray] = []
                T: List[Tuple[int, int, int]] = []
                usos: Dict[int, int] = {}
                for cr in self._caras_de(self.e[sid]):
                    try:
                        self.cara(cr, V, T, usos)
                    except (ErrorStep, IndexError, TypeError, ValueError, ZeroDivisionError,
                            np.linalg.LinAlgError, RecursionError):
                        self._no("cara que no se pudo leer")
                aristas = [self._aristas[a] for a, n in usos.items() if n > 0 and a in self._aristas]
                cache[sid] = (np.array(V, dtype=float).reshape(-1, 3), np.array(T, dtype=np.int64).reshape(-1, 3),
                              aristas)
            V_, T_, A_ = cache[sid]
            R, t = m[:3, :3], m[:3, 3]
            Vt.append((V_ @ R.T + t) * self.escala)
            Tt.append(T_ + n0)
            At += [(a @ R.T + t) * self.escala for a in A_]
            n0 += len(V_)
        V = np.vstack(Vt) if Vt else np.zeros((0, 3))
        T = np.vstack(Tt) if Tt else np.zeros((0, 3), dtype=np.int64)
        avisos = [f"No se pudo dibujar: {k} ({n})" for k, n in sorted(self._no_entiendo.items())]
        if len(T) == 0:
            raise ErrorStep("no se pudo pasar ninguna cara del modelo a triángulos")
        msol = [(sid, m) for sid, m in solidos]
        return Malla(V, T, At, avisos, msol, self.escala)

    # ---------------------------------------------------------------- para copiar
    def entidades_de(self, raiz: int) -> List[int]:
        """Ids de la entidad y de todas las que usa (para copiarla a otro STEP), en orden."""
        visto: Dict[int, None] = {}
        pila = [raiz]
        while pila:
            i = pila.pop()
            if i in visto or i not in self.e:
                continue
            visto[i] = None
            e = self.e[i]
            pila.extend(_refs(e.args))
            for a in e.partes.values():
                pila.extend(_refs(a))
        return sorted(visto)


def _refs(v: Any) -> Iterable[int]:
    if isinstance(v, Ref):
        yield int(v)
    elif isinstance(v, list):
        for x in v:
            yield from _refs(x)
    elif isinstance(v, Tipado):
        yield from _refs(v.args)


_REF_TEXTO = re.compile(r"'(?:[^']|'')*'|#(\d+)")


def renumerar(texto: str, nuevos: Dict[int, int]) -> str:
    """Cambia las referencias #n del texto de una entidad (sin tocar las cadenas)."""
    return _REF_TEXTO.sub(lambda m: f"#{nuevos[int(m.group(1))]}" if m.group(1) else m.group(0), texto)


def leer(ruta: str) -> ModeloStep:
    with open(ruta, "rb") as f:
        crudo = f.read()
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    return ModeloStep(texto)
