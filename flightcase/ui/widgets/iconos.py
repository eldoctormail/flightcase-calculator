"""Íconos de la barra lateral del Taller, dibujados con QPainter (iguales en Windows y Mac)."""

from __future__ import annotations

import math
from typing import Callable, Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

LADO = 24


def icono(dibujar: Callable[[QPainter], None], color: str = "#c9d3e6", activo: str = "#ffffff") -> QIcon:
    """Ícono con su versión normal y la del botón marcado (más clara)."""
    ic = QIcon()
    for col, estado in ((color, QIcon.State.Off), (activo, QIcon.State.On)):
        for escala in (1, 2):
            pm = QPixmap(LADO * escala, LADO * escala)
            pm.setDevicePixelRatio(escala)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(col), 1.7)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            dibujar(p)
            p.end()
            ic.addPixmap(pm, QIcon.Mode.Normal, estado)
    return ic


def _medidas(p: QPainter) -> None:
    p.drawRect(QRectF(4, 9, 16, 11))
    p.drawLine(QPointF(4, 4), QPointF(20, 4))
    for x in (4, 20):
        p.drawLine(QPointF(x, 2.5), QPointF(x, 5.5))
    for x in (8, 12, 16):
        p.drawLine(QPointF(x, 9), QPointF(x, 12))


def _case(p: QPainter) -> None:
    p.drawPolygon(QPolygonF([QPointF(3, 9), QPointF(12, 5), QPointF(21, 9), QPointF(12, 13)]))
    p.drawPolyline(QPolygonF([QPointF(3, 9), QPointF(3, 17), QPointF(12, 21), QPointF(21, 17), QPointF(21, 9)]))
    p.drawLine(QPointF(12, 13), QPointF(12, 21))
    p.drawLine(QPointF(3, 12), QPointF(12, 16))
    p.drawLine(QPointF(12, 16), QPointF(21, 12))


def _herrajes(p: QPainter) -> None:
    # cierre mariposa: placa con la palanca
    p.drawRoundedRect(QRectF(5, 3, 14, 10), 2, 2)
    p.drawEllipse(QPointF(12, 8), 2.2, 2.2)
    p.drawLine(QPointF(9, 13), QPointF(9, 18))
    p.drawLine(QPointF(15, 13), QPointF(15, 18))
    p.drawArc(QRectF(9, 15, 6, 6), 180 * 16, 180 * 16)


def _ruedas(p: QPainter) -> None:
    p.drawLine(QPointF(5, 4), QPointF(19, 4))
    p.drawLine(QPointF(12, 4), QPointF(12, 8))
    p.drawPolyline(QPolygonF([QPointF(8, 8), QPointF(16, 8), QPointF(15, 12)]))
    p.drawEllipse(QPointF(12, 15), 5.5, 5.5)
    p.drawEllipse(QPointF(12, 15), 1.5, 1.5)


def _interior(p: QPainter) -> None:
    p.drawRect(QRectF(4, 3, 16, 18))
    p.drawLine(QPointF(4, 9), QPointF(20, 9))
    p.drawLine(QPointF(4, 15), QPointF(20, 15))
    for y in (6, 12, 18):
        p.drawLine(QPointF(10, y), QPointF(14, y))


def _accesorios(p: QPainter) -> None:
    for i in range(6):
        a = math.radians(i * 60)
        p.drawLine(QPointF(12 + 5 * math.cos(a), 12 + 5 * math.sin(a)),
                   QPointF(12 + 8.5 * math.cos(a), 12 + 8.5 * math.sin(a)))
    p.drawEllipse(QPointF(12, 12), 5, 5)
    p.drawEllipse(QPointF(12, 12), 1.8, 1.8)


def _vista(p: QPainter) -> None:
    p.drawArc(QRectF(2, 5, 20, 16), 20 * 16, 140 * 16)
    p.drawArc(QRectF(2, 3, 20, 16), 200 * 16, 140 * 16)
    p.drawEllipse(QPointF(12, 12), 3.5, 3.5)


def _panel(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
    p.drawLine(QPointF(9, 4), QPointF(9, 20))


def _deshacer(p: QPainter) -> None:
    p.drawArc(QRectF(5, 6, 14, 12), 90 * 16, -200 * 16)
    p.drawLine(QPointF(12, 6), QPointF(8, 6))
    p.drawLine(QPointF(8, 6), QPointF(10.5, 3.5))
    p.drawLine(QPointF(8, 6), QPointF(10.5, 8.5))


def _rehacer(p: QPainter) -> None:
    p.drawArc(QRectF(5, 6, 14, 12), 90 * 16, 200 * 16)
    p.drawLine(QPointF(12, 6), QPointF(16, 6))
    p.drawLine(QPointF(16, 6), QPointF(13.5, 3.5))
    p.drawLine(QPointF(16, 6), QPointF(13.5, 8.5))


def _exportar(p: QPainter) -> None:
    p.drawPolyline(QPolygonF([QPointF(4, 13), QPointF(4, 20), QPointF(20, 20), QPointF(20, 13)]))
    p.drawLine(QPointF(12, 3), QPointF(12, 15))
    p.drawLine(QPointF(12, 3), QPointF(8, 7))
    p.drawLine(QPointF(12, 3), QPointF(16, 7))


DIBUJOS: Dict[str, Callable[[QPainter], None]] = {
    "medidas": _medidas, "armado": _case, "herrajes": _herrajes, "ruedas": _ruedas, "interior": _interior,
    "accesorios": _accesorios, "vista": _vista, "panel": _panel, "deshacer": _deshacer, "rehacer": _rehacer,
    "exportar": _exportar,
}
