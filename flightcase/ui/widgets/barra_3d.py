"""Barra de navegación de la vista 3D: zoom, mano para mover, girar, vistas y encuadrar.

Los íconos se dibujan acá con QPainter, así se ven igual en Windows y en Mac.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QToolButton, QWidget

from .schema_3d_widget import Schema3DCanvas

LADO = 22
COLOR = QColor(235, 235, 235)


def _icono(dibujar: Callable[[QPainter], None]) -> QIcon:
    icono = QIcon()
    for escala in (1, 2):
        pm = QPixmap(LADO * escala, LADO * escala)
        pm.setDevicePixelRatio(escala)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(COLOR, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        dibujar(p)
        p.end()
        icono.addPixmap(pm)
    return icono


def _lupa(signo: str):
    def d(p: QPainter) -> None:
        p.drawEllipse(QPointF(9.5, 9.5), 6, 6)
        p.drawLine(QPointF(14, 14), QPointF(19.5, 19.5))
        p.drawLine(QPointF(6.5, 9.5), QPointF(12.5, 9.5))
        if signo == "+":
            p.drawLine(QPointF(9.5, 6.5), QPointF(9.5, 12.5))
    return d


def _mano(p: QPainter) -> None:
    """Puño agarrando (como el cursor de «arrastrar»): los cuatro nudillos arriba, la palma
    y el pulgar doblado por delante; alrededor, flechas chicas de mover."""
    camino = QPainterPath()
    for x in (6.9, 10.0, 13.1, 16.2):                                        # dedos doblados
        camino.addRoundedRect(QRectF(x - 1.45, 6.2, 2.9, 6.0), 1.45, 1.45)
    camino.addRoundedRect(QRectF(5.45, 10.0, 12.2, 8.4), 3.4, 3.4)          # palma
    p.drawPath(camino.simplified())
    pulgar = QPainterPath()                                                  # pulgar doblado
    pulgar.moveTo(5.6, 13.0)
    pulgar.cubicTo(8.0, 12.2, 10.6, 12.6, 12.0, 14.6)
    p.drawPath(pulgar)
    pen = p.pen()
    fina = QPen(pen)
    fina.setWidthF(pen.widthF() * 0.8)
    p.setPen(fina)
    for punta, ang in ((QPointF(11.5, 2.4), -90), (QPointF(11.5, 21.2), 90),
                       (QPointF(1.6, 14.2), 180), (QPointF(21.4, 14.2), 0)):
        _flecha(p, punta, ang, 2.0)
    p.setPen(pen)


def _flecha(p: QPainter, punta: QPointF, angulo: float, largo: float = 4.0) -> None:
    for da in (150, -150):
        a = math.radians(angulo + da)
        p.drawLine(punta, QPointF(punta.x() + largo * math.cos(a), punta.y() + largo * math.sin(a)))


def _orbitar(p: QPainter) -> None:
    """Girar alrededor: un cubito con una flecha que le da la vuelta."""
    frente = QPolygonF([QPointF(8, 9.5), QPointF(13, 9.5), QPointF(13, 14.5), QPointF(8, 14.5)])
    p.drawPolygon(frente)
    p.drawPolyline(QPolygonF([QPointF(8, 9.5), QPointF(10, 7.5), QPointF(15, 7.5), QPointF(15, 12.5),
                              QPointF(13, 14.5)]))
    p.drawLine(QPointF(13, 9.5), QPointF(15, 7.5))
    p.drawArc(QRectF(2, 4, 18, 15), 200 * 16, 300 * 16)
    _flecha(p, QPointF(3.2, 14.6), 115, 3.6)


def _zoom_arrastre(p: QPainter) -> None:
    """Zoom arrastrando: lupa con una flecha para arriba y otra para abajo."""
    p.drawEllipse(QPointF(8.5, 9.5), 5.2, 5.2)
    p.drawLine(QPointF(12.3, 13.3), QPointF(15.5, 16.5))
    p.drawLine(QPointF(19, 3.5), QPointF(19, 18.5))
    _flecha(p, QPointF(19, 3.5), -90, 3.2)
    _flecha(p, QPointF(19, 18.5), 90, 3.2)


def _girar(sentido: int):
    def d(p: QPainter) -> None:
        rect = QRectF(4, 4, 14, 14)
        if sentido < 0:
            p.drawArc(rect, 30 * 16, 260 * 16)
            _flecha(p, QPointF(17.1, 7.5), -40)
        else:
            p.drawArc(rect, 150 * 16, -260 * 16)
            _flecha(p, QPointF(4.9, 7.5), -140)
    return d


def _encuadrar(p: QPainter) -> None:
    for x, y, dx, dy in ((3, 3, 1, 1), (19, 3, -1, 1), (3, 19, 1, -1), (19, 19, -1, -1)):
        p.drawLine(QPointF(x, y), QPointF(x + 5 * dx, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + 5 * dy))
    p.drawRect(QRectF(8, 8, 6, 6))


def _cubo(p: QPainter) -> None:
    frente = QPolygonF([QPointF(4, 8), QPointF(14, 8), QPointF(14, 18), QPointF(4, 18)])
    p.drawPolygon(frente)
    p.drawPolyline(QPolygonF([QPointF(4, 8), QPointF(8, 4), QPointF(18, 4), QPointF(18, 14), QPointF(14, 18)]))
    p.drawLine(QPointF(14, 8), QPointF(18, 4))


def _perspectiva(p: QPainter) -> None:
    p.drawPolygon(QPolygonF([QPointF(7, 5), QPointF(15, 5), QPointF(19, 18), QPointF(3, 18)]))
    p.drawLine(QPointF(11, 5), QPointF(11, 18))


def _cotas(p: QPainter) -> None:
    p.drawLine(QPointF(3, 7), QPointF(3, 17))
    p.drawLine(QPointF(19, 7), QPointF(19, 17))
    p.drawLine(QPointF(4, 12), QPointF(18, 12))
    _flecha(p, QPointF(4, 12), 180, 3.5)
    _flecha(p, QPointF(18, 12), 0, 3.5)


def _ejes(p: QPainter) -> None:
    o = QPointF(6, 16)
    for fin, color in ((QPointF(19, 16), "#f87171"), (QPointF(6, 3), "#60a5fa"), (QPointF(15, 9), "#4ade80")):
        p.setPen(QPen(QColor(color), 1.8))
        p.drawLine(o, fin)


class BarraVista3D(QFrame):
    """Botones para manejar la vista 3D sin depender solo del mouse."""

    def __init__(self, canvas: Schema3DCanvas, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("barra3d")
        self.canvas = canvas
        self.botones: Dict[str, QToolButton] = {}
        fila = QHBoxLayout(self)
        fila.setContentsMargins(4, 2, 4, 2)
        fila.setSpacing(2)

        def boton(clave: str, icono, ayuda: str, accion=None, marcable: bool = False) -> QToolButton:
            b = QToolButton(self)
            b.setIcon(_icono(icono))
            b.setIconSize(QSize(LADO, LADO))
            b.setToolTip(ayuda)
            b.setCheckable(marcable)
            b.setAutoRaise(True)
            if accion is not None:
                (b.toggled if marcable else b.clicked).connect(accion)
            self.botones[clave] = b
            fila.addWidget(b)
            return b

        def separador() -> None:
            linea = QFrame(self)
            linea.setFrameShape(QFrame.Shape.VLine)
            linea.setStyleSheet("color: rgba(255,255,255,60); background: transparent")
            fila.addWidget(linea)

        boton("acercar", _lupa("+"), "Acercar (+ o rueda del mouse)", canvas.acercar)
        boton("alejar", _lupa("-"), "Alejar (- o rueda del mouse)", canvas.alejar)
        separador()
        # qué hace el botón izquierdo del mouse
        for clave, icono, ayuda in (
            ("orbitar", _orbitar, "Girar alrededor del case al arrastrar (flechas del teclado: de a 5°)"),
            ("mover", _mano, "Mano: mover la imagen al arrastrar (también con el botón derecho o Mayús + flechas)"),
            ("zoom", _zoom_arrastre, "Zoom al arrastrar hacia arriba o abajo"),
        ):
            b = boton(clave, icono, ayuda, marcable=True)
            b.toggled.connect(lambda si, c=clave: si and canvas.set_modo_raton(c))
        self.grupo_modo = [self.botones[c] for c in ("orbitar", "mover", "zoom")]
        for b in self.grupo_modo:
            b.setAutoExclusive(True)
        self.botones[canvas.modo_raton].setChecked(True)
        separador()
        boton("girar_izq", _girar(-1), "Girar 90° a la izquierda", lambda: canvas.girar(90))
        boton("girar_der", _girar(1), "Girar 90° a la derecha", lambda: canvas.girar(-90))
        vistas = boton("vistas", _cubo, "Vistas: isométrica, frente, atrás, lados, arriba, abajo")
        menu = QMenu(vistas)
        for clave, texto in (("iso", "Isométrica"), ("frente", "Frente"), ("atras", "Atrás"),
                             ("izquierda", "Izquierda"), ("derecha", "Derecha"), ("arriba", "Arriba"),
                             ("abajo", "Abajo")):
            a = QAction(texto, menu)
            a.triggered.connect(lambda _=False, c=clave: canvas.set_vista(c))
            menu.addAction(a)
        vistas.setMenu(menu)
        vistas.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        boton("encuadrar", _encuadrar, "Encuadrar: el case entero en la ventana (Inicio, F o doble clic)",
              canvas.encuadrar)
        separador()
        boton("perspectiva", _perspectiva, "Perspectiva (apagado: vista paralela, sin deformar)",
              canvas.set_perspective, marcable=True).setChecked(canvas.is_perspective)
        boton("cotas", _cotas, "Mostrar las cotas", canvas.set_mostrar_cotas, marcable=True).setChecked(
            canvas.show_dimensions)
        boton("ejes", _ejes, "Mostrar los ejes", canvas.set_mostrar_ejes, marcable=True).setChecked(canvas.show_axes)
        fila.addStretch(1)
        canvas.projection_changed.connect(self._sincronizar_perspectiva)

    def _sincronizar_perspectiva(self, si: bool) -> None:
        b = self.botones["perspectiva"]
        b.blockSignals(True)
        b.setChecked(si)
        b.blockSignals(False)
