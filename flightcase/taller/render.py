"""Imágenes PNG del case del taller sin OpenGL (para las láminas del instructivo).

Rasteriza la malla de geometria.py con un z-buffer en numpy (cada píxel guarda la pieza
más cercana, así nada se dibuja delante de lo que no corresponde), con supermuestreo para
bordes suaves y contornos sacados del propio z-buffer. Usa la convención de cámara de
OpenSCAD (`--camera=tx,ty,tz,rx,ry,rz,dist`: rx inclina desde arriba, rz gira alrededor
de Z). Funciona en cualquier equipo, sin placa de video ni OpenSCAD.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QImage, QPainter, QPen

from .geometria import Malla3D

COLORES: Dict[str, str] = {
    "base": "#d8c08e",      # cuerpo (neutro, como en las láminas de OpenSCAD)
    "lid": "#c4a46c",       # tapas
    "profile": "#b0c4de",   # aluminio (aro macho, aristas)
    "profile_h": "#708090", # aro hembra de las tapas
    "rueda": "#262626",
    "rueda_freno": "#7a1f1f",
    "herraje": "#5f6670",   # esquineros, cierres, manijas, ruedas
    "wall": "#9a7b4f",      # bandejas
    "resalte": "#ff9f1a",   # lo que se agrega en el paso
    "calado": "#3c342a",    # huecos de los paneles
}
FONDO = (255, 255, 255)
SUPER = 2          # supermuestreo (antialias)


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
        gana = dentro & (z > zona + 0.05)   # empate (caras coplanares): gana la primera, sin parpadeo
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
                salto = np.abs(np.where(ambos, za - zb, 0.0)) > 3.0
            e = distinto & (~ambos | dobla | otro_color | salto)
            borde[: self.h - dy, : self.w - dx] |= e
            borde[dy:, dx:] |= e
        for _ in range(grosor - 1):
            b2 = borde.copy()
            b2[1:, :] |= borde[:-1, :]
            b2[:, 1:] |= borde[:, :-1]
            borde = b2
        self.col[borde] = self.col[borde] * 0.45


def renderizar(malla: Malla3D, ruta: str, camara: str = "0,0,0,62,0,32,0", tam: str = "1400,1050") -> bool:
    """Dibuja la malla y la guarda en `ruta` (PNG). Devuelve True si pudo."""
    if QGuiApplication.instance() is None:
        QGuiApplication([])
    w, h = (int(x) for x in tam.split(","))
    W, H = w * SUPER, h * SUPER
    rx, rz = (math.radians(a) for a in _camara(camara))
    ojo = np.array(_norm((math.sin(rz) * math.sin(rx), -math.cos(rz) * math.sin(rx), math.cos(rx))))
    der = np.array(_norm((-ojo[1], ojo[0], 0.0)) if abs(ojo[2]) < 0.999 else (1.0, 0.0, 0.0))
    arriba = np.cross(ojo, der)
    luz = np.array(_norm((0.45, -0.6, 0.75)))
    base = np.stack([der, arriba, ojo], axis=1)          # punto · base = (x, y, prof)

    caras = [f for f in malla.faces if len(f.vertices) >= 3]
    if not caras:
        return False
    todos = np.array([(p.x, p.y, p.z) for f in caras for p in f.vertices]) @ base
    margen = 0.06
    ancho = max(todos[:, 0].max() - todos[:, 0].min(), 1)
    alto = max(todos[:, 1].max() - todos[:, 1].min(), 1)
    esc = min(W * (1 - 2 * margen) / ancho, H * (1 - 2 * margen) / alto)
    cx = (todos[:, 0].max() + todos[:, 0].min()) / 2
    cy = (todos[:, 1].max() + todos[:, 1].min()) / 2

    def pantalla(pts: np.ndarray) -> np.ndarray:
        q = pts @ base
        return np.stack([W / 2 + (q[:, 0] - cx) * esc, H / 2 - (q[:, 1] - cy) * esc, q[:, 2]], axis=1)

    lienzo = _Lienzo(W, H)
    grupos = {g: i for i, g in enumerate(COLORES)}
    normales: List[Tuple[float, float, float]] = []
    colores_id: List[int] = []

    def poligono(pts3: np.ndarray, normal: np.ndarray, grupo: str, sesgo: float = 0.0,
                 agujeros: Sequence[np.ndarray] = ()) -> None:
        ident = len(normales)
        normales.append(tuple(normal))
        gi = grupos.get(grupo, 0)
        colores_id.append(gi)
        luzf = 0.62 + 0.38 * max(0.0, float(normal @ luz))
        color = _rgb(COLORES.get(grupo, COLORES["base"])) * luzf
        s = pantalla(pts3)
        for i in range(1, len(s) - 1):
            lienzo.triangulo(s[[0, i, i + 1]], color, ident, gi, sesgo, agujeros)

    # calados: 4 segmentos seguidos con la misma etiqueta ("Panel: tipo"); son agujeros pasantes
    # en las dos caras grandes del panel, así se ve lo que hay detrás como en OpenSCAD
    calados: Dict[str, List[np.ndarray]] = {}
    por_etiqueta: Dict[str, list] = {}
    for s in malla.segments:
        por_etiqueta.setdefault(s.label, []).append(s)
    for etiqueta, segs in por_etiqueta.items():
        if ":" not in etiqueta:
            continue
        panel = etiqueta.split(":")[0]
        for i in range(0, len(segs) - 3, 4):
            calados.setdefault(panel, []).append(np.array([(sg.p1.x, sg.p1.y, sg.p1.z) for sg in segs[i:i + 4]]))

    for f in caras:
        n = np.array(_norm(f.normal))
        if n @ ojo <= 1e-6:
            continue       # de espaldas: la tapa otra cara más cercana
        pts = np.array([(p.x, p.y, p.z) for p in f.vertices])
        agujeros = []
        if f.label in calados and not f.is_endgrain:
            for q in calados[f.label]:
                plano = q - np.outer((q - pts[0]) @ n, n)      # el calado llevado al plano de esta cara
                agujeros.append(pantalla(plano)[:, :2])
        poligono(pts, n, f.color_group, agujeros=agujeros)

    lienzo.contornos(np.array(normales + [(0, 0, 1)]), np.array(colores_id + [-1]), grosor=SUPER)

    rgb = np.ascontiguousarray(np.clip(lienzo.col, 0, 255).astype(np.uint8))
    img = QImage(rgb.data, W, H, 3 * W, QImage.Format_RGB888).copy()

    # rótulos: sólo si en su centro no hay nada más cerca que el propio panel
    pin = QPainter(img)
    pin.setRenderHint(QPainter.Antialiasing)
    pin.setRenderHint(QPainter.TextAntialiasing)
    for r in malla.rotulos:
        n = np.array(_norm(r.normal))
        if n @ ojo <= 0.15:
            continue
        x, y, z = pantalla(np.array([[r.centro.x, r.centro.y, r.centro.z]]))[0]
        px, py = int(x), int(y)
        if not (0 <= px < W and 0 <= py < H) or lienzo.z[py, px] > z + 2.0:
            continue
        fuente = QFont("Sans Serif")
        fuente.setBold(True)
        fuente.setPixelSize(max(9 * SUPER, int(r.tam * esc * 0.8)))
        pin.setFont(fuente)
        ancho_t = pin.fontMetrics().horizontalAdvance(r.texto) + fuente.pixelSize() * 0.8
        alto_t = fuente.pixelSize() * 1.5
        caja = QRectF(x - ancho_t / 2, y - alto_t / 2, ancho_t, alto_t)
        pin.setPen(QPen(QColor("#222222"), 1.2 * SUPER))
        pin.setBrush(QBrush(QColor("#ffffff")))
        pin.drawRoundedRect(caja, alto_t * 0.2, alto_t * 0.2)
        pin.drawText(caja, Qt.AlignCenter, r.texto)
    pin.end()
    return img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(ruta)


def _dentro_convexo(pol: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Máscara de los centros de píxel (xs × ys) dentro del polígono convexo `pol` (N×2)."""
    signos = []
    for k in range(len(pol)):
        (x0, y0), (x1, y1) = pol[k], pol[(k + 1) % len(pol)]
        signos.append((x1 - x0) * (ys - y0) - (y1 - y0) * (xs - x0))
    s = np.stack(np.broadcast_arrays(*signos))
    return (s >= 0).all(axis=0) | (s <= 0).all(axis=0)

