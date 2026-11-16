"""Panel «Vista» del Taller: qué parte del case mostrar, abrir u ocultar las tapas (con
animación sobre la bisagra), sacar los cajones, ocultar grupos de piezas y el aspecto."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

from ...taller.vista import CATEGORIAS, SECCIONES, EstadoVista, VistaCase


def _titulo(texto: str) -> QLabel:
    l = QLabel(texto)
    l.setObjectName("tituloSeccion")
    return l


class PanelVista(QWidget):
    """Controles de la vista 3D. Emite `cambiado` con el EstadoVista nuevo."""

    cambiado = Signal(object)
    tapas_cambiadas = Signal()   # cambió si una tapa está abierta u oculta (para la barra de arriba)
    DURACION_MS = 650            # lo que tarda en abrirse una tapa o salir un cajón

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.estado = EstadoVista()
        self._anims: Dict[str, QVariantAnimation] = {}
        self._tapas_nombres: List[str] = []
        self._n_cajones = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        lay.addWidget(_titulo("Mostrar"))
        fila = QHBoxLayout()
        fila.setSpacing(4)
        self.grupo_seccion = QButtonGroup(self)
        self.btn_seccion: Dict[str, QPushButton] = {}
        for clave, texto in SECCIONES:
            b = QPushButton(texto)
            b.setCheckable(True)
            b.setProperty("segmento", True)
            b.clicked.connect(lambda _=False, c=clave: self.poner_seccion(c))
            self.grupo_seccion.addButton(b)
            self.btn_seccion[clave] = b
            fila.addWidget(b)
        self.btn_seccion["todo"].setChecked(True)
        lay.addLayout(fila)

        lay.addWidget(_titulo("Tapas"))
        self.chk_interior = QCheckBox("Ver el interior (abre la primera tapa)")
        self.chk_interior.toggled.connect(lambda si: self.ver_interior(si))
        lay.addWidget(self.chk_interior)
        fila_t = QHBoxLayout()
        fila_t.setSpacing(4)
        self.btn_abrir_todas = QPushButton("Abrir todas")
        self.btn_abrir_todas.clicked.connect(lambda: self.abrir_todas(True))
        self.btn_cerrar_todas = QPushButton("Cerrar todas")
        self.btn_cerrar_todas.clicked.connect(lambda: self.abrir_todas(False))
        fila_t.addWidget(self.btn_abrir_todas)
        fila_t.addWidget(self.btn_cerrar_todas)
        lay.addLayout(fila_t)
        self.caja_tapas = QGridLayout()
        self.caja_tapas.setHorizontalSpacing(4)
        self.caja_tapas.setVerticalSpacing(4)
        lay.addLayout(self.caja_tapas)
        self.btn_abrir: List[QPushButton] = []
        self.btn_ocultar: List[QPushButton] = []

        self.lbl_cajones = _titulo("Cajones")
        lay.addWidget(self.lbl_cajones)
        fila_c = QHBoxLayout()
        fila_c.setSpacing(4)
        self.btn_sacar = QPushButton("Sacar todos")
        self.btn_sacar.clicked.connect(lambda: self.mover_cajones(1.0))
        self.btn_guardar = QPushButton("Guardar todos")
        self.btn_guardar.clicked.connect(lambda: self.mover_cajones(0.0))
        fila_c.addWidget(self.btn_sacar)
        fila_c.addWidget(self.btn_guardar)
        lay.addLayout(fila_c)
        self.caja_cajones = QVBoxLayout()
        self.caja_cajones.setSpacing(2)
        lay.addLayout(self.caja_cajones)
        self.sliders: List[QSlider] = []

        lay.addWidget(_titulo("Ocultar"))
        self.chk_ocultar: Dict[str, QCheckBox] = {}
        for clave, texto in CATEGORIAS:
            c = QCheckBox(texto)
            c.toggled.connect(lambda si, k=clave: self._ocultar(k, si))
            self.chk_ocultar[clave] = c
            lay.addWidget(c)

        lay.addWidget(_titulo("Aspecto"))
        self.chk_realista = QCheckBox("Colores de case real (placa y aluminio)")
        self.chk_realista.setChecked(True)
        self.chk_fondo = QCheckBox("Fondo claro")
        self.chk_piso = QCheckBox("Grilla del piso")
        self.chk_piso.setChecked(True)
        self.chk_cubo = QCheckBox("Cubo de vistas")
        self.chk_cubo.setChecked(True)
        for c in (self.chk_realista, self.chk_fondo, self.chk_piso, self.chk_cubo):
            lay.addWidget(c)
        lay.addStretch(1)
        self._mostrar_cajones()

    # ------------------------------------------------------------------ armado según el case
    @property
    def nombres_tapas(self) -> List[str]:
        return list(self._tapas_nombres)

    def set_vista_case(self, vista: VistaCase) -> None:
        """Arma los botones de las tapas y los deslizadores de los cajones de este case."""
        nombres = vista.nombres_tapas
        if nombres != self._tapas_nombres:
            self._tapas_nombres = nombres
            while self.caja_tapas.count():
                w = self.caja_tapas.takeAt(0).widget()
                if w is not None:
                    w.deleteLater()
            self.btn_abrir, self.btn_ocultar = [], []
            for i, nombre in enumerate(nombres):
                self.caja_tapas.addWidget(QLabel(nombre), i, 0)
                a = QPushButton("Abrir")
                a.setCheckable(True)
                a.setChecked(self.estado.tapas[i] > 0.5)
                a.clicked.connect(lambda si, k=i: self.abrir_tapa(k, si))
                o = QPushButton("Ocultar")
                o.setCheckable(True)
                o.setChecked(self.estado.tapas_ocultas[i])
                o.clicked.connect(lambda si, k=i: self.ocultar_tapa(k, si))
                self.caja_tapas.addWidget(a, i, 1)
                self.caja_tapas.addWidget(o, i, 2)
                self.btn_abrir.append(a)
                self.btn_ocultar.append(o)
            self._textos_tapas()
            self.tapas_cambiadas.emit()
        n = vista.cantidad_cajones
        if n != self._n_cajones:
            self._n_cajones = n
            while self.caja_cajones.count():
                w = self.caja_cajones.takeAt(0).widget()
                if w is not None:
                    w.deleteLater()
            self.sliders = []
            for i in range(n):
                self.caja_cajones.addWidget(QLabel(f"Cajón {i + 1}"))
                s = QSlider(Qt.Orientation.Horizontal)
                s.setRange(0, 100)
                s.setValue(round(100 * self.estado.cajones.get(i, 0.0)))
                s.valueChanged.connect(lambda val, k=i: self._cajon_movido(k, val))
                self.caja_cajones.addWidget(s)
                self.sliders.append(s)
            self.estado.cajones = {k: v for k, v in self.estado.cajones.items() if k < n}
            self._mostrar_cajones()

    def _mostrar_cajones(self) -> None:
        hay = self._n_cajones > 0
        for w in (self.lbl_cajones, self.btn_sacar, self.btn_guardar):
            w.setVisible(hay)

    def _textos_tapas(self) -> None:
        for i, b in enumerate(self.btn_abrir):
            b.setText("Cerrar" if b.isChecked() else "Abrir")
            b.setEnabled(not self.tapa_oculta(i))
        for b in self.btn_ocultar:
            b.setText("Mostrar" if b.isChecked() else "Ocultar")

    def tapa_abierta(self, i: int) -> bool:
        return i < len(self.btn_abrir) and self.btn_abrir[i].isChecked()

    def tapa_oculta(self, i: int) -> bool:
        return i < len(self.estado.tapas_ocultas) and self.estado.tapas_ocultas[i]

    # ------------------------------------------------------------------ acciones
    def _emitir(self) -> None:
        self.cambiado.emit(self.estado)

    def poner_seccion(self, clave: str) -> None:
        self.estado.seccion = clave
        self.btn_seccion[clave].setChecked(True)
        self._emitir()

    def _ocultar(self, clave: str, si: bool) -> None:
        (self.estado.ocultos.add if si else self.estado.ocultos.discard)(clave)
        self._emitir()

    def _animar(self, clave: str, desde: float, hasta: float, poner) -> None:
        """Lleva un valor de `desde` a `hasta` (al instante si el panel no está a la vista)."""
        vieja = self._anims.pop(clave, None)
        if vieja is not None:
            vieja.stop()
        if self.DURACION_MS <= 0 or not self.window().isVisible() or abs(hasta - desde) < 1e-6:
            poner(hasta)
            self._emitir()
            return
        an = QVariantAnimation(self)
        an.setStartValue(float(desde))
        an.setEndValue(float(hasta))
        an.setDuration(int(self.DURACION_MS * max(0.3, abs(hasta - desde))))
        an.setEasingCurve(QEasingCurve.Type.InOutCubic)
        an.valueChanged.connect(lambda v: (poner(float(v)), self._emitir()))
        an.finished.connect(lambda c=clave, a=an: self._anims.get(c) is a and self._anims.pop(c))
        self._anims[clave] = an
        an.start()

    def abrir_tapa(self, i: int, abrir: bool = True) -> None:
        if i >= len(self.estado.tapas):
            return
        if i == 0:
            self.chk_interior.blockSignals(True)
            self.chk_interior.setChecked(abrir)
            self.chk_interior.blockSignals(False)
        if abrir and self.estado.tapas_ocultas[i]:
            self.ocultar_tapa(i, False)
        if i < len(self.btn_abrir):
            self.btn_abrir[i].setChecked(abrir)
        self._textos_tapas()
        self.tapas_cambiadas.emit()

        def poner(v: float, k=i) -> None:
            self.estado.tapas[k] = v
        self._animar(f"tapa{i}", self.estado.tapas[i], 1.0 if abrir else 0.0, poner)

    def ocultar_tapa(self, i: int, ocultar: bool = True) -> None:
        if i >= len(self.estado.tapas_ocultas):
            return
        self.estado.tapas_ocultas[i] = ocultar
        if i < len(self.btn_ocultar):
            self.btn_ocultar[i].setChecked(ocultar)
        self._textos_tapas()
        self.tapas_cambiadas.emit()
        self._emitir()

    def abrir_todas(self, abrir: bool = True) -> None:
        for i in range(max(len(self._tapas_nombres), 1)):
            self.abrir_tapa(i, abrir)
        self.chk_interior.blockSignals(True)
        self.chk_interior.setChecked(abrir)
        self.chk_interior.blockSignals(False)

    def ver_interior(self, si: bool = True) -> None:
        """Abre (o cierra) la tapa 1: la de arriba en un case parado, la de adelante en uno frontal."""
        self.abrir_tapa(0, si)
        self.chk_interior.blockSignals(True)
        self.chk_interior.setChecked(si)
        self.chk_interior.blockSignals(False)

    def _cajon_movido(self, i: int, valor: int) -> None:
        anim = self._anims.pop(f"cajon{i}", None)
        if anim is not None:
            anim.stop()
        self.estado.cajones[i] = valor / 100.0
        self._emitir()

    def mover_cajones(self, hasta: float) -> None:
        for i, s in enumerate(self.sliders):
            def poner(v: float, k=i, sl=s) -> None:
                self.estado.cajones[k] = v
                sl.blockSignals(True)
                sl.setValue(round(v * 100))
                sl.blockSignals(False)
            self._animar(f"cajon{i}", self.estado.cajones.get(i, 0.0), hasta, poner)
