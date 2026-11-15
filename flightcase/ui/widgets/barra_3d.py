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
    camino = QPainterPath()
    for x, alto in ((6.5, 9.0), (9.5, 11.0), (12.5, 10.5), (15.5, 8.5)):   # dedos
        camino.addRoundedRect(QRectF(x - 1.4, 13 - alto, 2.8, alto + 2), 1.4, 1.4)
    camino.addRoundedRect(QRectF(5.1, 10, 11.8, 9.5), 3.5, 3.5)            # palma
    pulgar = QPainterPath()
    pulgar.moveTo(5.5, 14.5)
    pulgar.cubicTo(3.5, 12.5, 2.0, 13.5, 3.0, 15.0)
    pulgar.lineTo(6.5, 19.0)
    camino = camino.united(pulgar)
    p.drawPath(camino.simplified())


def _flecha(p: QPainter, punta: QPointF, angulo: float, largo: float = 4.0) -> None:
    for da in (150, -150):
        a = math.radians(angulo + da)
        p.drawLine(punta, QPointF(punta.x() + largo * math.cos(a), punta.y() + largo * math.sin(a)))


def _orbitar(p: QPainter) -> None:
    p.drawEllipse(QPointF(11, 11), 3, 3)
    rect = QRectF(3, 6, 16, 10)
    p.drawArc(rect, 200 * 16, 290 * 16)
    _flecha(p, QPointF(3.6, 13.5), 100)


def _zoom_arrastre(p: QPainter) -> None:
    p.drawLine(QPointF(11, 3), QPointF(11, 19))
    _flecha(p, QPointF(11, 3), -90)
    _flecha(p, QPointF(11, 19), 90)
    p.drawEllipse(QPointF(11, 11), 3, 3)


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
