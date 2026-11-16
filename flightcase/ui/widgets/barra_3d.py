"""Barra de navegación de la vista 3D: zoom, mano para mover, girar, vistas y encuadrar.

Los íconos se dibujan acá con QPainter, así se ven igual en Windows y en Mac.
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QToolButton, QWidget

from .schema_3d_widget import Schema3DCanvas

LADO = 22
COLOR = QColor(235, 235, 235)


def _svg(nombre: str, escala: int) -> QPixmap:
    """Un ícono del set Tabler (MIT, resources/iconos) pintado del color de la barra."""
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer
    from ...paths import bundled_resource
    texto = bundled_resource(f"iconos/{nombre}.svg").read_text(encoding="utf-8")
    texto = texto.replace("currentColor", COLOR.name()).replace('stroke-width="2"', 'stroke-width="1.75"')
    pm = QPixmap(LADO * escala, LADO * escala)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(texto.encode())).render(p, QRectF(0, 0, LADO * escala, LADO * escala))
    p.end()
    pm.setDevicePixelRatio(escala)
    return pm


def _icono(dibujar) -> QIcon:
    """`dibujar` es el nombre de un SVG del set o una función que pinta con QPainter."""
    icono = QIcon()
    if isinstance(dibujar, str):
        for escala in (1, 2):
            icono.addPixmap(_svg(dibujar, escala))
        return icono
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

        boton("acercar", "zoom-in", "Acercar (+ o rueda del mouse)", canvas.acercar)
        boton("alejar", "zoom-out", "Alejar (- o rueda del mouse)", canvas.alejar)
        separador()
        # qué hace el botón izquierdo del mouse
        for clave, icono, ayuda in (
            ("orbitar", "rotate-3d", "Girar alrededor del case al arrastrar (flechas del teclado: de a 5°)"),
            ("mover", "hand-stop", "Mano: mover la imagen al arrastrar (también con el botón derecho o Mayús + flechas)"),
            ("zoom", "zoom-scan", "Zoom al arrastrar hacia arriba o abajo"),
        ):
            b = boton(clave, icono, ayuda, marcable=True)
            b.toggled.connect(lambda si, c=clave: si and canvas.set_modo_raton(c))
        self.grupo_modo = [self.botones[c] for c in ("orbitar", "mover", "zoom")]
        for b in self.grupo_modo:
            b.setAutoExclusive(True)
        self.botones[canvas.modo_raton].setChecked(True)
        separador()
        boton("girar_izq", "rotate", "Girar 90° a la izquierda", lambda: canvas.girar(90))
        boton("girar_der", "rotate-clockwise", "Girar 90° a la derecha", lambda: canvas.girar(-90))
        vistas = boton("vistas", "box", "Vistas: isométrica, frente, atrás, lados, arriba, abajo")
        menu = QMenu(vistas)
        for clave, texto in (("iso", "Isométrica"), ("frente", "Frente"), ("atras", "Atrás"),
                             ("izquierda", "Izquierda"), ("derecha", "Derecha"), ("arriba", "Arriba"),
                             ("abajo", "Abajo")):
            a = QAction(texto, menu)
            a.triggered.connect(lambda _=False, c=clave: canvas.set_vista(c))
            menu.addAction(a)
        vistas.setMenu(menu)
        vistas.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        boton("encuadrar", "focus-centered", "Encuadrar: el case entero en la ventana (Inicio, F o doble clic)",
              canvas.encuadrar)
        separador()
        boton("perspectiva", "perspective", "Perspectiva (apagado: vista paralela, sin deformar)",
              canvas.set_perspective, marcable=True).setChecked(canvas.is_perspective)
        boton("cotas", "dimensions", "Acotar: medidas exteriores del case y alto de las tapas", canvas.set_mostrar_cotas, marcable=True).setChecked(
            canvas.show_dimensions)
        boton("medir", "ruler-measure", "Medir: clic en dos puntos del case (se engancha a las esquinas). Esc borra",
              canvas.set_modo_medir, marcable=True)
        boton("ejes", _ejes, "Mostrar los ejes", canvas.set_mostrar_ejes, marcable=True).setChecked(canvas.show_axes)
        fila.addStretch(1)
        canvas.projection_changed.connect(self._sincronizar_perspectiva)

    def _sincronizar_perspectiva(self, si: bool) -> None:
        b = self.botones["perspectiva"]
        b.blockSignals(True)
        b.setChecked(si)
        b.blockSignals(False)
