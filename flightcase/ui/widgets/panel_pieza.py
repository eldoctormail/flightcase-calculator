"""Cuadro de la pieza elegida con un clic en la vista 3D: otro artículo, otro color o sacarla."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from ...taller.piezas import COLORES_NOMBRE, color_hex

OTRO_COLOR = "Otro color…"
ALCANCES = {
    "esquinero": [("esta", "Sólo esta"), ("tapa", "Las 4 de la tapa"), ("cuerpo", "Las 4 del otro lado"),
                  ("todas", "Las 8")],
    "arista": [("esta", "Sólo esta"), ("tapa", "Las de la tapa"), ("cuerpo", "Las del cuerpo"),
               ("todas", "Todas")],
}


class PanelPieza(QFrame):
    """Se muestra abajo de la vista 3D. Cada cambio se aplica enseguida (`cambiado`)."""

    cambiado = Signal()
    cerrado = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("panelPieza")
        self.pieza = ""
        self.tipo = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)
        arriba = QHBoxLayout()
        self.lbl_titulo = QLabel()
        self.lbl_titulo.setObjectName("tituloSeccion")
        arriba.addWidget(self.lbl_titulo, 1)
        self.btn_cerrar = QToolButton()
        self.btn_cerrar.setText("✕")
        self.btn_cerrar.setToolTip("Cerrar (Esc)")
        self.btn_cerrar.clicked.connect(self.cerrado.emit)
        arriba.addWidget(self.btn_cerrar)
        lay.addLayout(arriba)

        fila = QHBoxLayout()
        fila.setSpacing(8)
        self.lbl_modelo = QLabel("Modelo:")
        fila.addWidget(self.lbl_modelo)
        self.cmb_modelo = QComboBox()
        self.cmb_modelo.setMinimumWidth(240)
        self.cmb_modelo.activated.connect(lambda *_: self._avisar())
        fila.addWidget(self.cmb_modelo, 2)
        fila.addWidget(QLabel("Color:"))
        self.cmb_color = QComboBox()
        self.cmb_color.addItem("Igual que el resto", "")
        for nombre, h in COLORES_NOMBRE.items():
            self.cmb_color.addItem(_muestra(h), nombre.capitalize(), nombre)
        self.cmb_color.addItem(OTRO_COLOR, "otro")
        self.cmb_color.activated.connect(self._color_elegido)
        fila.addWidget(self.cmb_color, 1)
        self.chk_quitar = QCheckBox("Sin esta pieza")
        self.chk_quitar.toggled.connect(lambda *_: self._avisar())
        fila.addWidget(self.chk_quitar)
        lay.addLayout(fila)

        fila2 = QHBoxLayout()
        fila2.setSpacing(8)
        self.lbl_alcance = QLabel("Cambiar:")
        fila2.addWidget(self.lbl_alcance)
        self.cmb_alcance = QComboBox()
        self.cmb_alcance.setToolTip("A qué piezas se aplica lo que elijas arriba")
        fila2.addWidget(self.cmb_alcance)
        self.btn_restablecer = QPushButton("Volver a la de siempre")
        self.btn_restablecer.setToolTip("Saca el cambio de esta pieza (o de las elegidas en «Cambiar»)")
        self.btn_restablecer.clicked.connect(self._restablecer)
        fila2.addWidget(self.btn_restablecer)
        fila2.addStretch(1)
        self.lbl_nota = QLabel()
        self.lbl_nota.setObjectName("nota")
        self.lbl_nota.setWordWrap(True)
        fila2.addWidget(self.lbl_nota, 2)
        lay.addLayout(fila2)
        self._color_otro = ""
        self.restablecer_pedido = False
        self.setVisible(False)

    # ------------------------------------------------------------------
    def mostrar(self, pieza: str, tipo: str, titulo: str, modelos: list, ref: str, color: str, quitar: bool,
                puede_quitar: bool, nota: str = "") -> None:
        """modelos: [(ref, texto)] con ("", "Igual que el resto (…)") primero."""
        cambio_de_pieza = pieza != self.pieza
        self.pieza, self.tipo = pieza, tipo
        self.lbl_titulo.setText(titulo)
        for w in (self.cmb_modelo, self.cmb_color, self.chk_quitar, self.cmb_alcance):
            w.blockSignals(True)
        self.lbl_modelo.setText("Placa:" if tipo == "panel" else "Modelo:")
        self.cmb_modelo.clear()
        for r, texto in modelos:
            self.cmb_modelo.addItem(texto, r)
        i = self.cmb_modelo.findData(ref)
        if i < 0 and ref:
            self.cmb_modelo.addItem(ref, ref)
            i = self.cmb_modelo.count() - 1
        self.cmb_modelo.setCurrentIndex(max(i, 0))
        self._poner_color(color)
        self.chk_quitar.setChecked(bool(quitar))
        self.chk_quitar.setVisible(puede_quitar)
        alc = ALCANCES.get(tipo, [])
        actual = self.cmb_alcance.currentData()
        self.cmb_alcance.clear()
        for clave, texto in alc:
            self.cmb_alcance.addItem(texto, clave)
        if not cambio_de_pieza and actual:
            self.cmb_alcance.setCurrentIndex(max(self.cmb_alcance.findData(actual), 0))
        self.cmb_alcance.setVisible(bool(alc))
        self.lbl_alcance.setVisible(bool(alc))
        for w in (self.cmb_modelo, self.cmb_color, self.chk_quitar, self.cmb_alcance):
            w.blockSignals(False)
        self.lbl_nota.setText(nota)
        self.setVisible(True)

    def valores(self) -> Dict[str, Any]:
        return dict(ref=self.cmb_modelo.currentData() or "", color=self.color(), quitar=self.chk_quitar.isChecked()
                    and self.chk_quitar.isVisible(), alcance=self.cmb_alcance.currentData() or "esta")

    def color(self) -> str:
        d = self.cmb_color.currentData()
        if d == "otro":
            return self._color_otro
        return d or ""

    # ------------------------------------------------------------------
    def _poner_color(self, color: str) -> None:
        h = color_hex(color)
        nombre = next((n for n, v in COLORES_NOMBRE.items() if v == h), "")
        if not h:
            self.cmb_color.setCurrentIndex(0)
        elif nombre:
            self.cmb_color.setCurrentIndex(self.cmb_color.findData(nombre))
        else:
            self._color_otro = h
            i = self.cmb_color.findData("otro")
            self.cmb_color.setItemText(i, f"{OTRO_COLOR} ({h})")
            self.cmb_color.setItemIcon(i, _muestra(h))
            self.cmb_color.setCurrentIndex(i)

    def _color_elegido(self, i: int) -> None:
        if self.cmb_color.itemData(i) == "otro":
            c = QColorDialog.getColor(QColor(self._color_otro or "#888888"), self, "Color de la pieza")
            if not c.isValid():
                return
            self._color_otro = c.name()
            self.cmb_color.setItemText(i, f"{OTRO_COLOR} ({c.name()})")
            self.cmb_color.setItemIcon(i, _muestra(c.name()))
        self._avisar()

    def _restablecer(self) -> None:
        self.restablecer_pedido = True
        try:
            self.cambiado.emit()
        finally:
            self.restablecer_pedido = False

    def _avisar(self) -> None:
        self.cambiado.emit()

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() == Qt.Key.Key_Escape:
            self.cerrado.emit()
        else:
            super().keyPressEvent(ev)


def _muestra(hexa: str):
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(14, 14)
    pm.fill(QColor(hexa))
    return QIcon(pm)
