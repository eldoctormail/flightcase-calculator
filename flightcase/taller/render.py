"""Imágenes PNG del case del taller sin OpenGL (para las láminas del instructivo).

Rasteriza la malla de geometria.py con un z-buffer en numpy (cada píxel guarda la pieza
más cercana, así nada se dibuja delante de lo que no corresponde), con supermuestreo para
bordes suaves y contornos sacados del propio z-buffer. Usa la convención de cámara de
OpenSCAD (`--camera=tx,ty,tz,rx,ry,rz,dist`: rx inclina desde arriba, rz gira alrededor
de Z). Funciona en cualquier equipo, sin placa de video ni OpenSCAD.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QTransform

from .geometria import COLORES, Malla3D

FONDO = (255, 255, 255)
SUPER = 2          # supermuestreo (antialias)
FOV = 22.5         # campo visual de la cámara de OpenSCAD (grados)


def _norm(v: Sequence[float]) -> Tuple[float, float, float]:
    l = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


def _camara(texto: str) -> Tuple[float, float]:
    """(rx, rz) en grados desde '0,0,0,62,0,32,0'."""
    c = [float(x) for x in texto.split(",")]
    return (c[3], c[5]) if len(c) >= 6 else (62.0, 32.0)


def _rgb(hex_: str) -> np.ndarray:
    c = QColor(hex_)
    return np.array([c.red(), c.green(), c.blue()], dtype=np.float32)


class _Lienzo:
    """z-buffer: color, profundidad (mayor = más cerca), id de cara y normal por píxel."""

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.z = np.full((h, w), -np.inf, dtype=np.float64)
        self.col = np.empty((h, w, 3), dtype=np.float32)
        self.col[:] = FONDO
        self.ident = np.full((h, w), -1, dtype=np.int32)
        self.grupo = np.full((h, w), -1, dtype=np.int16)

    def triangulo(self, p: np.ndarray, color: np.ndarray, ident: int, grupo: int, sesgo: float = 0.0,
                  agujeros: Sequence[np.ndarray] = ()) -> None:
        """p: 3×3 (x, y pantalla en píxeles; z profundidad). `agujeros`: polígonos convexos que no se pintan."""
        x0 = max(int(math.floor(p[:, 0].min())), 0)
        x1 = min(int(math.ceil(p[:, 0].max())), self.w - 1)
        y0 = max(int(math.floor(p[:, 1].min())), 0)
        y1 = min(int(math.ceil(p[:, 1].max())), self.h - 1)
        if x1 < x0 or y1 < y0:
            return
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = p
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            return
        xs = np.arange(x0, x1 + 1) + 0.5
        ys = np.arange(y0, y1 + 1)[:, None] + 0.5
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        l3 = 1.0 - l1 - l2
        eps = -1e-6
        dentro = (l1 >= eps) & (l2 >= eps) & (l3 >= eps)
        for ag in agujeros:
            # sólo la parte de la grilla que cae en el recuadro del agujero
            i0 = max(int(math.floor(ag[:, 0].min())) - x0, 0)
            i1 = min(int(math.ceil(ag[:, 0].max())) - x0, x1 - x0) + 1
            j0 = max(int(math.floor(ag[:, 1].min())) - y0, 0)
            j1 = min(int(math.ceil(ag[:, 1].max())) - y0, y1 - y0) + 1
            if i1 > i0 and j1 > j0:
                dentro[j0:j1, i0:i1] &= ~_dentro_convexo(ag, xs[i0:i1], ys[j0:j1])
        if not dentro.any():
            return
        z = l1 * az + l2 * bz + l3 * cz + sesgo
        zona = self.z[y0:y1 + 1, x0:x1 + 1]
        gana = dentro & (z > zona * (1 + 2e-5))   # empate (caras coplanares): gana la primera, sin parpadeo
        if not gana.any():
            return
        zona[gana] = z[gana]
        self.col[y0:y1 + 1, x0:x1 + 1][gana] = color
        self.ident[y0:y1 + 1, x0:x1 + 1][gana] = ident
        self.grupo[y0:y1 + 1, x0:x1 + 1][gana] = grupo

    def contornos(self, normales: np.ndarray, colores_id: np.ndarray, grosor: int) -> None:
        """Oscurece los píxeles donde cambia la pieza (o la cara, si dobla en arista viva)."""
        borde = np.zeros((self.h, self.w), dtype=bool)
        ident = self.ident
        for dy, dx in ((0, 1), (1, 0)):
            a = ident[: self.h - dy, : self.w - dx]
            b = ident[dy:, dx:]
            distinto = a != b
            ambos = (a >= 0) & (b >= 0)
            na = normales[np.maximum(a, 0)]
            nb = normales[np.maximum(b, 0)]
            dobla = (na * nb).sum(axis=-1) < 0.9
            otro_color = colores_id[np.maximum(a, 0)] != colores_id[np.maximum(b, 0)]
            za = self.z[: self.h - dy, : self.w - dx]
            zb = self.z[dy:, dx:]
            with np.errstate(invalid="ignore"):
                # z = 1/distancia: 3 mm de salto de profundidad
                salto = np.abs(np.where(ambos, za - zb, 0.0)) > np.where(ambos, 3.0 * za * zb, np.inf)
            e = distinto & (~ambos | dobla | otro_color | salto)
            borde[: self.h - dy, : self.w - dx] |= e
            borde[dy:, dx:] |= e
        for _ in range(grosor - 1):
            b2 = borde.copy()
            b2[1:, :] |= borde[:-1, :]
            b2[:, 1:] |= borde[:, :-1]
            borde = b2
        self.col[borde] = self.col[borde] * 0.45


def renderizar(malla: Malla3D, ruta: str, camara: str = "0,0,0,62,0,32,0", tam: str = "1400,1050",
               colores: Optional[Dict[str, str]] = None) -> bool:
    """Dibuja la malla y la guarda en `ruta` (PNG). Devuelve True si pudo. `colores` reemplaza
    colores de grupos (por ejemplo el color de la placa: base, lid, wall)."""
    paleta = dict(COLORES, **(colores or {}))
    if QGuiApplication.instance() is None:
        QGuiApplication([])
    w, h = (int(x) for x in tam.split(","))
    W, H = w * SUPER, h * SUPER
    rx, rz = (math.radians(a) for a in _camara(camara))
    ojo = np.array(_norm((math.sin(rz) * math.sin(rx), -math.cos(rz) * math.sin(rx), math.cos(rx))))
    der = np.array(_norm((-ojo[1], ojo[0], 0.0)) if abs(ojo[2]) < 0.999 else (1.0, 0.0, 0.0))
    arriba = np.cross(ojo, der)
    luz = np.array(_norm(-0.35 * der + 0.55 * arriba + 0.75 * ojo))   # luz fija respecto de la cámara, como OpenSCAD
    base = np.stack([der, arriba, ojo], axis=1)          # (p - centro) · base = (x, y, hacia la cámara)

    caras = [f for f in malla.faces if len(f.vertices) >= 3]
    if not caras:
        return False
    # perspectiva como OpenSCAD con --viewall --autocenter --projection=p (campo visual de 22,5°)
    todos = np.array([(p.x, p.y, p.z) for f in caras for p in f.vertices])
    centro = (todos.max(axis=0) + todos.min(axis=0)) / 2
    radio = max(float(np.linalg.norm(todos.max(axis=0) - todos.min(axis=0))) / 2, 1.0)
    medio = math.radians(FOV / 2)
    dist = radio / math.sin(medio)
    focal = (min(W, H) / 2) / math.tan(medio)
    camara_pos = centro + ojo * dist

    def pantalla(pts: np.ndarray) -> np.ndarray:
        q = (pts - centro) @ base
        zc = dist - q[:, 2]
        return np.stack([W / 2 + focal * q[:, 0] / zc, H / 2 - focal * q[:, 1] / zc, 1.0 / zc], axis=1)

    lienzo = _Lienzo(W, H)
    grupos = {g: i for i, g in enumerate(COLORES)}
    normales: List[Tuple[float, float, float]] = []
    colores_id: List[int] = []
    tangentes: List[Tuple[float, float, float]] = []
    materiales: List[int] = []

    def poligono(pts3: np.ndarray, normal: np.ndarray, grupo: str, agujeros: Sequence[np.ndarray] = (),
                 plano: bool = False, material: int = MAT_NINGUNO) -> int:
        ident = len(normales)
        normales.append(tuple(normal))
        lados = [pts3[(i + 1) % len(pts3)] - pts3[i] for i in range(len(pts3))]
        largo = max(lados, key=lambda d: float(d @ d))
        tangentes.append(tuple(_norm(largo)))
        materiales.append(material)
        gi = grupos.get(grupo, 0)
        colores_id.append(gi)
        luzf = 1.0 if plano else 0.6 + 0.45 * max(0.0, float(normal @ luz))
        color = _rgb(paleta.get(grupo, paleta["base"])) * luzf
        s = pantalla(pts3)
        for i in range(1, len(s) - 1):
            lienzo.triangulo(s[[0, i, i + 1]], color, ident, gi, 0.0, agujeros)
        return ident

    def mira(n: np.ndarray, p0: np.ndarray) -> bool:
        return float(n @ (camara_pos - p0)) > 1e-6

    # calados pasantes: se recortan de las dos caras grandes del panel, así se ve lo que hay detrás
    calados: Dict[str, List[np.ndarray]] = {}
    for panel, contorno in getattr(malla, "calados", []):
        calados.setdefault(panel, []).append(np.array([(q.x, q.y, q.z) for q in contorno]))

    for f in caras:
        n = np.array(_norm(f.normal))
        pts = np.array([(p.x, p.y, p.z) for p in f.vertices])
        if not mira(n, pts[0]):
            continue       # de espaldas: la tapa otra cara más cercana
        agujeros = []
        if f.label in calados and not f.is_endgrain:
            for q in calados[f.label]:
                if abs(float(_norm(np.cross(q[1] - q[0], q[2] - q[0])) @ n)) < 0.99:
                    continue   # cara de canto
                sobre = q - np.outer((q - pts[0]) @ n, n)      # el calado llevado al plano de esta cara
                agujeros.append(pantalla(sobre)[:, :2])
        poligono(pts, n, f.color_group, agujeros, material=_material(f))

    # rótulos como en rotulo(): placa blanca redondeada apoyada sobre el panel, con el texto encima
    textos = []
    for r in malla.rotulos:
        n = np.array(_norm(r.normal))
        c = np.array([r.centro.x, r.centro.y, r.centro.z])
        if not mira(n, c):
            continue
        s = r.tam
        ex_, ey_ = np.array(r.der), np.array(r.arriba)
        ancho_r, alto_r = s * 0.68 * len(r.texto) + s * 0.8, s * 1.6
        contorno = [c + ex_ * a + ey_ * b + n * 0.3 for a, b in
                    _rect_redondeado_2d(-ancho_r / 2, -alto_r / 2, ancho_r / 2, alto_r / 2, s * 0.3)]
        ident = poligono(np.array(contorno), n, "rotulo", plano=True)
        textos.append((ident, r, c + n * 0.3, ex_, ey_))

    _texturas(lienzo, np.array(normales + [(0, 0, 1)]), np.array(tangentes + [(1, 0, 0)]),
              np.array(materiales + [MAT_NINGUNO]), luz, camara_pos, centro, base, dist, focal)
    lienzo.contornos(np.array(normales + [(0, 0, 1)]), np.array(colores_id + [-1]), grosor=SUPER)

    if textos:
        capa = QImage(W, H, QImage.Format_ARGB32_Premultiplied)
        capa.fill(Qt.transparent)
        pin = QPainter(capa)
        pin.setRenderHint(QPainter.Antialiasing)
        pin.setRenderHint(QPainter.TextAntialiasing)
        for ident, r, c, ex_, ey_ in textos:
            s = r.tam
            p0, px, py = pantalla(np.array([c, c + ex_ * s, c - ey_ * s]))[:, :2]
            k = 1 / (10 * s)   # el texto se dibuja en décimas de mm
            pin.setTransform(QTransform((px - p0)[0] * k, (px - p0)[1] * k, (py - p0)[0] * k, (py - p0)[1] * k,
                                        p0[0], p0[1]))
            fuente = QFont("Sans Serif")
            fuente.setBold(True)
            fuente.setPixelSize(max(1, int(s * 10 * 1.35)))
            pin.setFont(fuente)
            pin.setPen(QColor("#000000"))
            pin.drawText(QRectF(-s * 40, -s * 10, s * 80, s * 20), Qt.AlignCenter, r.texto)
        pin.end()
        buf = np.frombuffer(capa.constBits(), dtype=np.uint8).reshape(H, capa.bytesPerLine() // 4, 4)[:, :W]
        alfa = buf[:, :, 3].astype(np.float32) / 255.0
        alfa *= np.isin(lienzo.ident, [t_[0] for t_ in textos])
        lienzo.col *= (1 - alfa)[:, :, None]

    rgb = np.ascontiguousarray(np.clip(lienzo.col, 0, 255).astype(np.uint8))
    img = QImage(rgb.data, W, H, 3 * W, QImage.Format_RGB888).copy()
    return img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(ruta)


MAT_NINGUNO, MAT_MADERA, MAT_CANTO, MAT_ALUMINIO, MAT_METAL, MAT_GOMA = range(6)
_ALUMINIO = {"Ángulo de arista", "Perfil de cierre", "Junta de acceso", "Perfil híbrido"}
_METAL = {"Esquinero", "Cierre", "Bisagra", "Manija", "Plato", "Remache", "Tope"}


def _material(f) -> int:
    """Material de una cara según la pieza (la etiqueta) y su color."""
    g, et = f.color_group, f.label or ""
    if et in _ALUMINIO or g in ("aluminio", "profile", "profile_h"):
        return MAT_ALUMINIO
    if et in _METAL or g in ("herraje", "cierre", "plato", "rueda_placa", "rueda_horq"):
        return MAT_METAL
    if g in ("rueda", "rueda_freno"):
        return MAT_GOMA
    if g in ("base", "lid", "wall", "base_ruedas", "resalte"):
        return MAT_CANTO if f.is_endgrain else MAT_MADERA
    return MAT_NINGUNO


_RUIDO = np.random.default_rng(7).random((256, 256)).astype(np.float32)


def _ruido(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Ruido de valores 2D suave (0..1), periódico cada 256 unidades."""
    xi, yi = np.floor(x), np.floor(y)
    fx, fy = x - xi, y - yi
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    xi, yi = xi.astype(np.int64) & 255, yi.astype(np.int64) & 255
    x1, y1 = (xi + 1) & 255, (yi + 1) & 255
    a = _RUIDO[yi, xi] * (1 - fx) + _RUIDO[yi, x1] * fx
    b = _RUIDO[y1, xi] * (1 - fx) + _RUIDO[y1, x1] * fx
    return a * (1 - fy) + b * fy


def _texturas(lienzo: "_Lienzo", normales: np.ndarray, tangentes: np.ndarray, materiales: np.ndarray,
              luz: np.ndarray, camara_pos: np.ndarray, centro: np.ndarray, base: np.ndarray,
              dist: float, focal: float) -> None:
    """Veta de madera, aluminio cepillado y brillo de los metales, píxel por píxel."""
    ys, xs = np.nonzero(lienzo.ident >= 0)
    if len(xs) == 0:
        return
    ident = lienzo.ident[ys, xs]
    mat = materiales[ident]
    usar = mat != MAT_NINGUNO
    ys, xs, ident, mat = ys[usar], xs[usar], ident[usar], mat[usar]
    H, W = lienzo.h, lienzo.w
    # posición en el mundo de cada píxel a partir de su profundidad (z = 1/distancia a la cámara)
    zc = 1.0 / lienzo.z[ys, xs]
    cx = (xs + 0.5 - W / 2) * zc / focal
    cy = -(ys + 0.5 - H / 2) * zc / focal
    pos = centro + cx[:, None] * base[:, 0] + cy[:, None] * base[:, 1] + (dist - zc)[:, None] * base[:, 2]
    n, tg = normales[ident], tangentes[ident]
    bt = np.cross(n, tg)
    s = (pos * tg).sum(axis=1)          # a lo largo de la pieza
    t = (pos * bt).sum(axis=1)          # a lo ancho
    sem = (ident * 37 % 251).astype(np.float64)   # cada pieza con su propia veta
    f = np.ones(len(xs), dtype=np.float32)

    m = mat == MAT_MADERA                 # veta: anillos ondulados a lo largo de la pieza
    if m.any():
        sm, tm, se = s[m], t[m], sem[m]
        onda = _ruido(sm / 220 + se, tm / 35 + se) * 7.0 + _ruido(sm / 40, tm / 12) * 1.2
        veta = np.sin((tm / 6.5 + onda) * 2 * np.pi) * (0.5 + _ruido(sm / 300 + 50, tm / 25 + se))
        poro = _ruido(sm / 2.5 + se * 3, tm / 0.6)
        f[m] = 1 + 0.045 * veta + 0.05 * (poro - 0.5) + 0.06 * (_ruido(sm / 60 + se, tm / 60) - 0.5)
    m = mat == MAT_CANTO                  # canto del multilaminado: capas finas
    if m.any():
        f[m] = 0.92 + 0.06 * np.sin(t[m] / 1.3 * 2 * np.pi)
    m = mat == MAT_ALUMINIO               # cepillado: rayas finas a lo largo del perfil
    if m.any():
        f[m] = 1 + 0.07 * (_ruido(s[m] / 90, t[m] * 2.5) - 0.5) + 0.04 * (_ruido(s[m] / 9, t[m] * 6) - 0.5)

    # brillo especular (Blinn) según el material
    brillo = np.zeros(len(xs), dtype=np.float32)
    vista = camara_pos - pos
    vista /= np.linalg.norm(vista, axis=1)[:, None]
    medio = vista + luz
    medio /= np.linalg.norm(medio, axis=1)[:, None]
    nh = np.clip((n * medio).sum(axis=1), 0, 1)
    for mid, k, e in ((MAT_ALUMINIO, 0.55, 18), (MAT_METAL, 0.7, 40), (MAT_GOMA, 0.12, 8), (MAT_MADERA, 0.06, 6)):
        mm = mat == mid
        if mm.any():
            brillo[mm] = k * nh[mm] ** e
    col = lienzo.col[ys, xs] * f[:, None] + 255.0 * brillo[:, None]
    lienzo.col[ys, xs] = col


def _rect_redondeado_2d(x0: float, y0: float, x1: float, y1: float, r: float, por_esquina: int = 6):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(por_esquina + 1):
            a = math.radians(a0 + 90 * i / por_esquina)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _dentro_convexo(pol: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Máscara de los centros de píxel (xs × ys) dentro del polígono convexo `pol` (N×2)."""
    signos = []
    for k in range(len(pol)):
        (x0, y0), (x1, y1) = pol[k], pol[(k + 1) % len(pol)]
        signos.append((x1 - x0) * (ys - y0) - (y1 - y0) * (xs - x0))
    s = np.stack(np.broadcast_arrays(*signos))
    return (s >= 0).all(axis=0) | (s <= 0).all(axis=0)

