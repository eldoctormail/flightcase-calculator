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


def _punta(p: QPainter, punta: QPointF, dx: float, dy: float, largo: float = 4.4, ancho: float = 3.0) -> None:
    """Punta de flecha rellena con la punta en `punta`, apuntando en la dirección (dx, dy)."""
    l = math.hypot(dx, dy) or 1.0
    ux, uy = dx / l, dy / l
    bx, by = punta.x() - ux * largo, punta.y() - uy * largo
    tri = QPolygonF([punta, QPointF(bx - uy * ancho / 2, by + ux * ancho / 2),
                     QPointF(bx + uy * ancho / 2, by - ux * ancho / 2)])
    p.save()
    p.setBrush(p.pen().color())
    pen = QPen(p.pen())
    pen.setWidthF(0.8)
    p.setPen(pen)
    p.drawPolygon(tri)
    p.restore()


def _flecha(p: QPainter, punta: QPointF, angulo: float, largo: float = 4.0) -> None:
    """Punta rellena en `punta`, apuntando hacia `angulo` (grados, y hacia abajo)."""
    a = math.radians(angulo)
    _punta(p, punta, math.cos(a), math.sin(a), largo, largo * 0.75)


def _recta_flecha(p: QPainter, desde: QPointF, hasta: QPointF, largo: float = 4.2) -> None:
    """Recta que termina en una punta: la línea llega hasta la base de la punta, no la atraviesa."""
    dx, dy = hasta.x() - desde.x(), hasta.y() - desde.y()
    l = math.hypot(dx, dy) or 1.0
    p.drawLine(desde, QPointF(hasta.x() - dx / l * (largo - 0.6), hasta.y() - dy / l * (largo - 0.6)))
    _punta(p, hasta, dx, dy, largo, largo * 0.75)


def _arco_flecha(p: QPainter, cx: float, cy: float, rx: float, ry: float, desde: float, giro: float,
                 largo: float = 4.4) -> None:
    """Arco de elipse (ángulos en grados, antihorario como Qt) con una punta al final que sigue
    la tangente del arco; el arco termina en la base de la punta."""
    corte = math.degrees(largo * 0.85 / max(rx, ry))
    hasta = desde + giro
    trazo = giro - math.copysign(corte, giro)
    p.drawArc(QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry), int(desde * 16), int(trazo * 16))
    a = math.radians(hasta)
    punta = QPointF(cx + rx * math.cos(a), cy - ry * math.sin(a))
    sg = 1.0 if giro > 0 else -1.0
    tx, ty = -rx * math.sin(a) * sg, -ry * math.cos(a) * sg     # tangente, en el sentido del giro
    _punta(p, punta, tx, ty, largo, largo * 0.75)


def _mano(p: QPainter) -> None:
    """Mover (paneo): la cruz de cuatro flechas de los programas de CAD."""
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        _recta_flecha(p, QPointF(11 + dx * 1.5, 11 + dy * 1.5), QPointF(11 + dx * 9.2, 11 + dy * 9.2), 4.6)
    p.drawEllipse(QPointF(11, 11), 1.4, 1.4)


def _orbitar(p: QPainter) -> None:
    """Girar alrededor: un cubito con una órbita que le da la vuelta."""
    frente = QPolygonF([QPointF(8, 9.5), QPointF(13, 9.5), QPointF(13, 14.5), QPointF(8, 14.5)])
    p.drawPolygon(frente)
    p.drawPolyline(QPolygonF([QPointF(8, 9.5), QPointF(10, 7.5), QPointF(15, 7.5), QPointF(15, 12.5),
                              QPointF(13, 14.5)]))
    p.drawLine(QPointF(13, 9.5), QPointF(15, 7.5))
    _arco_flecha(p, 11, 11.5, 9.5, 5.2, 120, 270, 4.4)


def _zoom_arrastre(p: QPainter) -> None:
    """Zoom arrastrando: lupa con una flecha para arriba y otra para abajo."""
    p.drawEllipse(QPointF(8.0, 9.0), 5.0, 5.0)
    p.drawLine(QPointF(11.7, 12.7), QPointF(14.6, 15.6))
    _recta_flecha(p, QPointF(18.8, 11), QPointF(18.8, 2.4), 4.0)
    _recta_flecha(p, QPointF(18.8, 11), QPointF(18.8, 19.6), 4.0)


def _girar(sentido: int):
    def d(p: QPainter) -> None:
        if sentido < 0:      # a la izquierda (antihorario)
            _arco_flecha(p, 11, 11.5, 7.2, 7.2, -60, 290, 4.6)
        else:                # a la derecha (horario)
            _arco_flecha(p, 11, 11.5, 7.2, 7.2, 240, -290, 4.6)
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
    _recta_flecha(p, QPointF(11, 12), QPointF(4, 12), 3.8)
    _recta_flecha(p, QPointF(11, 12), QPointF(18, 12), 3.8)


def _regla(p: QPainter) -> None:
    """Medir: una regla en diagonal con sus marcas."""
    p.save()
    p.translate(11, 11)
    p.rotate(-35)
    p.drawRoundedRect(QRectF(-9.5, -3.6, 19, 7.2), 1.2, 1.2)
    for i, x in enumerate((-6.5, -3.5, -0.5, 2.5, 5.5)):
        p.drawLine(QPointF(x, -3.6), QPointF(x, -0.6 if i % 2 else 0.6))
    p.restore()


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
        boton("cotas", _cotas, "Acotar: medidas exteriores del case y alto de las tapas", canvas.set_mostrar_cotas, marcable=True).setChecked(
            canvas.show_dimensions)
        boton("medir", _regla, "Medir: clic en dos puntos del case (se engancha a las esquinas). Esc borra",
              canvas.set_modo_medir, marcable=True)
        boton("ejes", _ejes, "Mostrar los ejes", canvas.set_mostrar_ejes, marcable=True).setChecked(canvas.show_axes)
        fila.addStretch(1)
        canvas.projection_changed.connect(self._sincronizar_perspectiva)

    def _sincronizar_perspectiva(self, si: bool) -> None:
        b = self.botones["perspectiva"]
        b.blockSignals(True)
        b.setChecked(si)
        b.blockSignals(False)
