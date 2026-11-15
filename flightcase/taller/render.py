"""Imágenes PNG del case del taller sin OpenGL (para las láminas del instructivo).

Dibuja la malla de geometria.py con QPainter (algoritmo del pintor, caras ordenadas por
profundidad), con la misma convención de cámara que OpenSCAD
(`--camera=tx,ty,tz,rx,ry,rz,dist`: rx inclina desde arriba, rz gira alrededor de Z).
Funciona en cualquier equipo, sin placa de video ni OpenSCAD.
"""

from __future__ import annotations

import math
from typing import Dict, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPolygonF

from .geometria import Malla3D

COLORES: Dict[str, str] = {
    "base": "#d8c08e",      # cuerpo (neutro, como en las láminas de OpenSCAD)
    "lid": "#c4a46c",       # tapas
    "profile": "#b8c0c8",   # aluminio
    "herraje": "#5f6670",   # esquineros, cierres, manijas, ruedas
    "wall": "#9a7b4f",      # bandejas
    "resalte": "#ff9f1a",   # lo que se agrega en el paso
}
FONDO = "#ffffff"


def _norm(v: Sequence[float]) -> Tuple[float, float, float]:
    l = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / l, v[1] / l, v[2] / l)


def _camara(texto: str) -> Tuple[float, float]:
    """(rx, rz) en grados desde '0,0,0,62,0,32,0'."""
    c = [float(x) for x in texto.split(",")]
    return (c[3], c[5]) if len(c) >= 6 else (62.0, 32.0)


def renderizar(malla: Malla3D, ruta: str, camara: str = "0,0,0,62,0,32,0", tam: str = "1400,1050") -> bool:
    """Dibuja la malla y la guarda en `ruta` (PNG). Devuelve True si pudo."""
    if QGuiApplication.instance() is None:
        QGuiApplication([])
    w, h = (int(x) for x in tam.split(","))
    rx, rz = (math.radians(a) for a in _camara(camara))
    ojo = _norm((math.sin(rz) * math.sin(rx), -math.cos(rz) * math.sin(rx), math.cos(rx)))
    der = _norm((-ojo[1], ojo[0], 0.0)) if abs(ojo[2]) < 0.999 else (1.0, 0.0, 0.0)
    arriba = (ojo[1] * der[2] - ojo[2] * der[1], ojo[2] * der[0] - ojo[0] * der[2], ojo[0] * der[1] - ojo[1] * der[0])
    luz = _norm((0.45, -0.6, 0.75))

    def proy(p) -> Tuple[float, float, float]:
        return (p.x * der[0] + p.y * der[1] + p.z * der[2],
                p.x * arriba[0] + p.y * arriba[1] + p.z * arriba[2],
                p.x * ojo[0] + p.y * ojo[1] + p.z * ojo[2])

    caras = []
    for f in malla.faces:
        if sum(a * b for a, b in zip(f.normal, ojo)) <= 1e-6:
            continue   # cara de espaldas a la cámara
        pts = [proy(p) for p in f.vertices]
        prof = sum(p[2] for p in pts) / len(pts)
        caras.append((prof, pts, f))
    if not caras:
        return False
    xs = [p[0] for _, pts, _ in caras for p in pts]
    ys = [p[1] for _, pts, _ in caras for p in pts]
    margen = 0.06
    esc = min(w * (1 - 2 * margen) / max(max(xs) - min(xs), 1), h * (1 - 2 * margen) / max(max(ys) - min(ys), 1))
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    def pantalla(x: float, y: float) -> QPointF:
        return QPointF(w / 2 + (x - cx) * esc, h / 2 - (y - cy) * esc)

    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(FONDO))
    pin = QPainter(img)
    pin.setRenderHint(QPainter.Antialiasing)
    for _, pts, f in sorted(caras, key=lambda c: c[0]):
        base = QColor(COLORES.get(f.color_group, COLORES["base"]))
        luzf = 0.62 + 0.38 * max(0.0, sum(a * b for a, b in zip(f.normal, luz)))
        col = QColor(int(base.red() * luzf), int(base.green() * luzf), int(base.blue() * luzf))
        pin.setBrush(QBrush(col))
        pin.setPen(QPen(col.darker(160), 1.0))
        pin.drawPolygon(QPolygonF([pantalla(p[0], p[1]) for p in pts]))
    # contornos de calados sobre las caras visibles (sólo los de caras que miran a la cámara)
    pin.setPen(QPen(QColor("#3a3a3a"), 1.4))
    for s in malla.segments:
        a, b = proy(s.p1), proy(s.p2)
        pin.drawLine(pantalla(a[0], a[1]), pantalla(b[0], b[1])) if _segmento_visible(s, ojo, malla) else None
    # rótulos P1, P2... en los paneles que miran a la cámara
    fuente = QFont("Sans Serif", max(10, int(min(w, h) / 45)))
    fuente.setBold(True)
    pin.setFont(fuente)
    for r in malla.rotulos:
        if sum(a * b for a, b in zip(r.normal, ojo)) <= 0.15:
            continue
        x, y, _ = proy(r.centro)
        pt = pantalla(x, y)
        ancho = pin.fontMetrics().horizontalAdvance(r.texto) + 16
        alto = pin.fontMetrics().height() + 6
        caja = QRectF(pt.x() - ancho / 2, pt.y() - alto / 2, ancho, alto)
        pin.setPen(QPen(QColor("#222222"), 1.2))
        pin.setBrush(QBrush(QColor("#ffffff")))
        pin.drawRoundedRect(caja, 5, 5)
        pin.drawText(caja, Qt.AlignCenter, r.texto)
    pin.end()
    return img.save(ruta)


def _segmento_visible(seg, ojo, malla) -> bool:
    """Los calados se dibujan sólo si su panel mira a la cámara."""
    for f in malla.faces:
        if f.label and seg.label.startswith(f.label + ":") and not f.is_endgrain:
            if sum(a * b for a, b in zip(f.normal, ojo)) > 0 and _en_plano(seg, f):
                return True
    return False


def _en_plano(seg, f) -> bool:
    n = f.normal
    p0 = f.vertices[0]
    d = lambda p: (p.x - p0.x) * n[0] + (p.y - p0.y) * n[1] + (p.z - p0.z) * n[2]
    return abs(d(seg.p1)) < 1.0 and abs(d(seg.p2)) < 1.0
