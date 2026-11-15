"""Formas de los calados de espuma: esquinas redondeadas, redondos, huecos para los dedos y
contornos traídos de un dibujo (DXF o SVG).

Un calado se describe en el plano del bloque de espuma (u, v en mm desde la esquina del
bloque) por su rectángulo envolvente: el del equipo más la holgura. La forma se arma con
QPainterPath (unión con los huecos para los dedos y recorte al bloque) y sale como uno o
más polígonos cerrados, en sentido antihorario y sin repetir el primer punto.

Si el calado es un rectángulo de esquinas vivas sin dedos, ``contorno`` devuelve None y
todo sigue como antes (DXF con LINE, 3D por grilla).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Punto = Tuple[float, float]
Poligono = List[Punto]

FORMAS = ("rect", "redondo")      # además: ruta a un .dxf o .svg
TRAMOS_CIRCULO = 48               # tramos de un círculo completo en el DXF


@dataclass
class Forma:
    tipo: str = "rect"            # rect, redondo o contorno
    archivo: str = ""             # para contorno
    radio: float = 0.0            # esquinas del rectángulo (y del contorno no se usa)
    dedos: int = 0                # 0, 1 (del lado delantero / de abajo) o 2 (los dos lados largos)
    dedo_ancho: float = 30.0
    dedo_largo: float = 25.0      # cuánto entra el hueco en la espuma fuera del calado

    def es_simple(self) -> bool:
        return self.tipo == "rect" and self.radio <= 0.01 and self.dedos <= 0


def forma_de_texto(texto: str) -> Tuple[str, str]:
    """("rect" | "redondo" | "contorno", archivo) a partir de lo cargado en la tabla."""
    t = (texto or "").strip()
    if not t or t.lower() in ("rect", "rectangulo", "rectángulo"):
        return "rect", ""
    if t.lower() in ("redondo", "circulo", "círculo", "elipse"):
        return "redondo", ""
    if t.lower().endswith((".dxf", ".svg")):
        return "contorno", t
    raise ValueError(t)


def _qt():
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QPainterPath, QPolygonF
    return QPainterPath, QPolygonF, QPointF, QRectF


def _area(p: Sequence[Punto]) -> float:
    return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))) / 2


def area(polis: Sequence[Sequence[Punto]]) -> float:
    """Área calada: los contornos que quedan dentro de otro (huecos, islas) restan y suman
    según cuántos los rodean."""
    total = 0.0
    for i, p in enumerate(polis):
        prof = sum(1 for j, q in enumerate(polis) if j != i and dentro([q], *p[0]))
        total += abs(_area(p)) * (-1 if prof % 2 else 1)
    return max(total, 0.0)


def _ruta_contorno(archivo: str, carpeta: str) -> str:
    return archivo if os.path.isabs(archivo) or not carpeta else os.path.join(carpeta, archivo)


def _camino_dibujo(archivo: str, carpeta: str, u0: float, u1: float, v0: float, v1: float):
    """El dibujo encajado en el rectángulo (sin deformarlo), como camino relleno."""
    from . import vectores
    QPainterPath, QPolygonF, QPointF, _ = _qt()
    lineas = vectores.leer(_ruta_contorno(archivo, carpeta))
    lineas, _, _ = vectores.encajar(lineas, u1 - u0, v1 - v0)
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    camino = QPainterPath()
    for l in lineas:
        if len(l) < 3:
            continue
        sub = QPainterPath()
        sub.addPolygon(QPolygonF([QPointF(cu + x, cv + y) for x, y in l]))
        sub.closeSubpath()
        camino = camino.united(sub)
    return camino


def contorno(u0: float, u1: float, v0: float, v1: float, forma: Forma, ancho: float, alto: float,
             carpeta: str = "") -> Tuple[Optional[List[Poligono]], List[str]]:
    """Polígonos del calado (o None si es un rectángulo simple) y avisos."""
    if forma.es_simple():
        return None, []
    QPainterPath, QPolygonF, QPointF, QRectF = _qt()
    avisos: List[str] = []
    w, h = u1 - u0, v1 - v0
    camino = QPainterPath()
    if forma.tipo == "redondo":
        camino.addEllipse(QRectF(u0, v0, w, h))
    elif forma.tipo == "contorno":
        try:
            camino = _camino_dibujo(forma.archivo, carpeta, u0, u1, v0, v1)
        except (OSError, ValueError) as e:
            avisos.append(f"No se pudo leer el contorno {os.path.basename(forma.archivo)} ({e}): "
                          "el calado va rectangular.")
            camino = QPainterPath()
        if camino.isEmpty():
            camino.addRect(QRectF(u0, v0, w, h))
        else:
            b = camino.boundingRect()
            if b.width() < w * 0.98 or b.height() < h * 0.98:
                avisos.append(f"El contorno {os.path.basename(forma.archivo)} no tiene la proporción del equipo: "
                              f"queda de {b.width():.0f} x {b.height():.0f} mm dentro de {w:.0f} x {h:.0f}.")
    else:
        r = max(0.0, min(forma.radio, w / 2, h / 2))
        camino.addRoundedRect(QRectF(u0, v0, w, h), r, r)

    if forma.dedos > 0:
        da, dl = max(forma.dedo_ancho, 1.0), max(forma.dedo_largo, 1.0)
        largo_en_u = w >= h          # lados largos: los de v constante si el calado es más ancho que alto
        lados = [-1] if forma.dedos == 1 else [-1, 1]
        for lado in lados:
            if largo_en_u:
                cu, cv = (u0 + u1) / 2, (v0 if lado < 0 else v1)
                rect = QRectF(cu - da / 2, cv - dl, da, 2 * dl)
            else:
                cu, cv = (u0 if lado < 0 else u1), (v0 + v1) / 2
                rect = QRectF(cu - dl, cv - da / 2, 2 * dl, da)
            hueco = QPainterPath()
            hueco.addRoundedRect(rect, da / 2, da / 2)
            camino = camino.united(hueco)

    bloque = QPainterPath()
    bloque.addRect(QRectF(0, 0, ancho, alto))
    camino = camino.intersected(bloque).simplified()
    polis: List[Poligono] = []
    for pol in camino.toSubpathPolygons():
        pts = [(round(p.x(), 3), round(p.y(), 3)) for p in pol]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        limpio: Poligono = []
        for p in pts:
            if not limpio or abs(p[0] - limpio[-1][0]) > 1e-3 or abs(p[1] - limpio[-1][1]) > 1e-3:
                limpio.append(p)
        if len(limpio) >= 3 and abs(_area(limpio)) > 1.0:
            polis.append(limpio)
    return (polis or None), avisos


def dentro(polis: Sequence[Sequence[Punto]], u: float, v: float) -> bool:
    """Punto dentro de la forma (regla par-impar, así los agujeros internos quedan afuera)."""
    adentro = False
    for p in polis:
        n = len(p)
        for i in range(n):
            (x1, y1), (x2, y2) = p[i], p[(i + 1) % n]
            if (y1 > v) != (y2 > v) and u < x1 + (v - y1) * (x2 - x1) / (y2 - y1):
                adentro = not adentro
    return adentro


def simplificar(p: Sequence[Punto], tol: float) -> Poligono:
    """Douglas-Peucker sobre un polígono cerrado (para la vista 3D por grilla)."""
    if len(p) <= 4:
        return list(p)

    def dp(pts: List[Punto]) -> List[Punto]:
        if len(pts) < 3:
            return pts
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        L = math.hypot(x2 - x1, y2 - y1) or 1e-9
        dmax, imax = 0.0, 0
        for i in range(1, len(pts) - 1):
            d = abs((x2 - x1) * (y1 - pts[i][1]) - (x1 - pts[i][0]) * (y2 - y1)) / L
            if d > dmax:
                dmax, imax = d, i
        if dmax <= tol:
            return [pts[0], pts[-1]]
        return dp(pts[:imax + 1])[:-1] + dp(pts[imax:])

    # partir en el punto más lejano al primero para no perder la forma
    lejos = max(range(len(p)), key=lambda i: math.hypot(p[i][0] - p[0][0], p[i][1] - p[0][1]))
    a = dp(list(p[:lejos + 1]))
    b = dp(list(p[lejos:]) + [p[0]])
    out = a[:-1] + b[:-1]
    return out if len(out) >= 3 else list(p)
