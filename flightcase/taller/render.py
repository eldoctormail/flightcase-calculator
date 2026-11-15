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
    "profile": "#b0c4de",   # aluminio (aro macho, aristas)
    "profile_h": "#708090", # aro hembra de las tapas
    "rueda": "#222222",
    "rueda_freno": "#7a1f1f",
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

    # calados (agujeros) agrupados por panel: 4 segmentos seguidos con la misma etiqueta
    calados_por_cara: Dict[int, list] = {}
    grupos: Dict[str, list] = {}
    for s in malla.segments:
        grupos.setdefault(s.label, []).append(s)
    for etiqueta, segs in grupos.items():
        for i in range(0, len(segs) - 3, 4):
            cuatro = segs[i:i + 4]
            cara = _cara_de(cuatro[0], malla)
            if cara is not None:
                calados_por_cara.setdefault(id(cara), []).append(cuatro)

    # rótulos: se ordenan junto con las caras, así los tapa lo que esté delante
    elementos = [(prof, 0, pts, f) for prof, pts, f in caras]
    for r in malla.rotulos:
        if sum(a * b for a, b in zip(r.normal, ojo)) > 0.15:
            x, y, z = proy(r.centro)
            elementos.append((z + 0.01, 1, (x, y), r))

    for prof, tipo, datos, obj in sorted(elementos, key=lambda e: e[0]):
        if tipo == 0:
            base = QColor(COLORES.get(obj.color_group, COLORES["base"]))
            luzf = 0.62 + 0.38 * max(0.0, sum(a * b for a, b in zip(obj.normal, luz)))
            col = QColor(int(base.red() * luzf), int(base.green() * luzf), int(base.blue() * luzf))
            pin.setBrush(QBrush(col))
            pin.setPen(QPen(col.darker(160), 1.0))
            pin.drawPolygon(QPolygonF([pantalla(p[0], p[1]) for p in datos]))
            for cuatro in calados_por_cara.get(id(obj), []):
                pin.setPen(QPen(QColor("#2a2a2a"), 1.2))
                pin.setBrush(QBrush(QColor(60, 52, 40)))
                pin.drawPolygon(QPolygonF([pantalla(*proy(sg.p1)[:2]) for sg in cuatro]))
        else:
            pt = pantalla(*datos)
            fuente = QFont("Sans Serif")
            fuente.setBold(True)
            fuente.setPixelSize(max(9, int(obj.tam * esc)))
            pin.setFont(fuente)
            ancho = pin.fontMetrics().horizontalAdvance(obj.texto) + fuente.pixelSize() * 0.8
            alto = fuente.pixelSize() * 1.6
            caja = QRectF(pt.x() - ancho / 2, pt.y() - alto / 2, ancho, alto)
            pin.setPen(QPen(QColor("#222222"), 1.2))
            pin.setBrush(QBrush(QColor("#ffffff")))
            pin.drawRoundedRect(caja, alto * 0.2, alto * 0.2)
            pin.drawText(caja, Qt.AlignCenter, obj.texto)
    pin.end()
    return img.save(ruta)


def _cara_de(seg, malla):
    """Cara exterior del panel sobre la que está dibujado un calado (o None)."""
    for f in malla.faces:
        if f.label and seg.label.startswith(f.label + ":") and not f.is_endgrain and _en_plano(seg, f):
            return f
    return None


def _en_plano(seg, f) -> bool:
    n = f.normal
    p0 = f.vertices[0]
    d = lambda p: (p.x - p0.x) * n[0] + (p.y - p0.y) * n[1] + (p.z - p0.z) * n[2]
    return abs(d(seg.p1)) < 1.0 and abs(d(seg.p2)) < 1.0
