"""Pestaña Taller: parámetros del generador del taller, resultado al instante y exportación."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from ...paths import bundled_resource
from ...taller.modelo import ResultadoTaller, calcular, fmt, parametros_por_defecto
from ...taller.scad import escribir_proyecto, leer_proyecto, literal, valor_literal

# Opciones fijas de los parámetros de texto que las tienen
OPCIONES: Dict[str, List[str]] = {
    "orientacion": ["vertical", "horizontal", "frontal"],
    "sistema": ["angulo", "hibrido"],
    "acceso_tipo": ["paneles", "cubierta"],
    "paredes_enteras": ["frente", "laterales"],
    "paredes_enteras_cuerpo": ["", "frente", "laterales"],
    "manijas_en": ["auto", "laterales", "frente"],
    "cierres_laterales": ["auto", "si", "no"],
}
# Números que sólo toman valores enteros
ENTEROS = {"tapas", "acceso_cierres_n", "cantidad_cases", "manijas_n", "cierres_frente_n",
           "cierres_lateral_n", "ruedas", "rueda_frenos", "bandeja_soportes", "encastre_remaches",
           "pies", "bisagras", "topes", "refuerzos", "refuerzo_remaches"}


def secciones_parametros() -> List[Dict[str, Any]]:
    """Secciones y ayuda de los parámetros (de taller_parametros_info.json)."""
    return json.loads(bundled_resource("taller_parametros_info.json").read_text(encoding="utf-8"))


class _Numero(QDoubleSpinBox):
    """Número sin ceros de más (600 en lugar de 600.00)."""

    def textFromValue(self, valor: float) -> str:  # noqa: N802 (nombre de Qt)
        return f"{valor:.{self.decimals()}f}".rstrip("0").rstrip(".") if self.decimals() else f"{valor:.0f}"


def _ayuda(texto: str) -> str:
    return f"<p style='white-space:pre-wrap'>{texto}</p>" if texto else ""


class _Editor:
    """Un control de edición por parámetro, según el tipo de su valor por defecto."""

    def __init__(self, nombre: str, defecto: Any, al_cambiar) -> None:
        self.nombre, self.defecto = nombre, defecto
        if isinstance(defecto, bool):
            w = QCheckBox()
            w.toggled.connect(al_cambiar)
        elif isinstance(defecto, (int, float)):
            w = _Numero()
            w.setRange(-100000, 100000)
            w.setDecimals(0 if nombre in ENTEROS else 2)
            w.setKeyboardTracking(False)
            w.valueChanged.connect(al_cambiar)
        elif isinstance(defecto, str) and nombre in OPCIONES:
            w = QComboBox()
            w.setEditable(True)
            w.addItems(OPCIONES[nombre])
            w.currentTextChanged.connect(al_cambiar)
        else:   # textos libres y listas (se escriben como en OpenSCAD)
            w = QLineEdit()
            if isinstance(defecto, list):
                w.setPlaceholderText("[]  (lista como en OpenSCAD)")
            w.editingFinished.connect(al_cambiar)
        self.widget = w

    def poner(self, valor: Any) -> None:
        w = self.widget
        w.blockSignals(True)
        try:
            if isinstance(w, QCheckBox):
                w.setChecked(bool(valor))
            elif isinstance(w, QDoubleSpinBox):
                w.setValue(float(valor))
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(valor))
            else:
                w.setText(valor if isinstance(valor, str) else literal(valor))
                w.setStyleSheet("")
        finally:
            w.blockSignals(False)

    def valor(self) -> Any:
        w = self.widget
        if isinstance(w, QCheckBox):
            return w.isChecked()
        if isinstance(w, QDoubleSpinBox):
            v = w.value()
            return int(round(v)) if self.nombre in ENTEROS or (isinstance(self.defecto, int) and v.is_integer()) else v
        if isinstance(w, QComboBox):
            return w.currentText()
        texto = w.text()
        if isinstance(self.defecto, list):
            try:
                v = valor_literal(texto or "[]")
                w.setStyleSheet("")
                return v
            except ValueError:
                w.setStyleSheet("background:#ffd6d6")
                raise
        return texto


class TallerWidget(QWidget):
    """Editor de un case con las reglas del taller (las del generador de OpenSCAD)."""

    resultado_cambiado = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.defectos = parametros_por_defecto()
        self.params: Dict[str, Any] = dict(self.defectos)
        self.ruta: Optional[str] = None
        self.resultado: Optional[ResultadoTaller] = None
        self.editores: Dict[str, _Editor] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.recalcular)
        self._init_ui()
        self._cargar_en_editores()
        self.recalcular()

    # ------------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        raiz = QVBoxLayout(self)
        barra = QHBoxLayout()
        self.lbl_archivo = QLabel("Proyecto nuevo")
        self.lbl_archivo.setStyleSheet("font-weight:600")
        barra.addWidget(self.lbl_archivo, 1)
        for texto, slot in (("Nuevo", self.nuevo), ("Abrir .scad…", self.abrir),
                            ("Guardar .scad…", self.guardar), ("Exportar paquete…", self.exportar)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            barra.addWidget(b)
        raiz.addLayout(barra)

        divisor = QSplitter(Qt.Horizontal, self)
        self.toolbox = QToolBox()
        for sec in secciones_parametros():
            pagina = QWidget()
            form = QFormLayout(pagina)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for p in sec["parametros"]:
                nombre = p["nombre"]
                if nombre not in self.defectos:
                    continue
                ed = _Editor(nombre, self.defectos[nombre], self._programar)
                ed.widget.setToolTip(_ayuda(p["ayuda"]))
                etiqueta = QLabel(nombre)
                etiqueta.setToolTip(_ayuda(p["ayuda"]))
                form.addRow(etiqueta, ed.widget)
                self.editores[nombre] = ed
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(pagina)
            self.toolbox.addItem(scroll, sec["seccion"])
        divisor.addWidget(self.toolbox)

        derecha = QWidget()
        dl = QVBoxLayout(derecha)
        dl.setContentsMargins(0, 0, 0, 0)
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setTextFormat(Qt.RichText)
        dl.addWidget(self.lbl_resumen)
        self.tabs = QTabWidget()
        self.tabla_paneles = self._tabla(["Pieza", "Ancho", "Alto", "Calados"])
        self.tabla_perfiles = self._tabla(["Perfil", "Descripción", "Largo", "Cant.", "Corte"])
        self.tabla_herrajes = self._tabla(["Herraje", "Cant.", "Detalle", "Ref."])
        self.tabs.addTab(self.tabla_paneles, "Paneles")
        self.tabs.addTab(self.tabla_perfiles, "Perfiles")
        self.tabs.addTab(self.tabla_herrajes, "Herrajes")
        dl.addWidget(self.tabs, 1)
        self.lbl_avisos = QLabel()
        self.lbl_avisos.setWordWrap(True)
        self.lbl_avisos.setStyleSheet("color:#a15c00")
        dl.addWidget(self.lbl_avisos)
        divisor.addWidget(derecha)
        divisor.setStretchFactor(0, 40)
        divisor.setStretchFactor(1, 60)
        raiz.addWidget(divisor, 1)

    @staticmethod
    def _tabla(columnas: List[str]) -> QTableWidget:
        t = QTableWidget(0, len(columnas))
        t.setHorizontalHeaderLabels(columnas)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        return t

    # -------------------------------------------------------------- estado
    def _cargar_en_editores(self) -> None:
        for nombre, ed in self.editores.items():
            ed.poner(self.params.get(nombre, self.defectos[nombre]))

    def _programar(self, *_args) -> None:
        self._timer.start()

    def _leer_editores(self) -> bool:
        ok = True
        for nombre, ed in self.editores.items():
            try:
                self.params[nombre] = ed.valor()
            except ValueError:
                ok = False
        return ok

    def set_params(self, params: Dict[str, Any], ruta: Optional[str] = None) -> None:
        self.params = dict(self.defectos)
        self.params.update(params)
        self.ruta = ruta
        self.lbl_archivo.setText(os.path.basename(ruta) if ruta else "Proyecto nuevo")
        self._cargar_en_editores()
        self.recalcular()

    def recalcular(self) -> None:
        if not self._leer_editores():
            self.lbl_avisos.setText("Hay una lista mal escrita (en rojo). Ejemplo: [[400, 300, 120]]")
            return
        try:
            res = calcular(self.params)
        except Exception as e:   # parámetros fuera de rango que el modelo no admite
            self.lbl_avisos.setText(f"No se pudo calcular con estos parámetros: {e}")
            return
        self.resultado = res
        self._mostrar(res)
        self.resultado_cambiado.emit(res)

    def _mostrar(self, res: ResultadoTaller) -> None:
        v = res.valores
        n_paneles = len(res.paneles)
        self.lbl_resumen.setText(
            f"<b>Exterior:</b> {fmt(v['ext_ancho'])} × {fmt(v['ext_prof'])} × {fmt(v['ext_alto'])} mm"
            f" &nbsp;·&nbsp; <b>Sistema:</b> {res.info['sistema'][0]}"
            f" &nbsp;·&nbsp; <b>Placa:</b> {v['placa_material']}"
            f" &nbsp;·&nbsp; {n_paneles} paneles, {sum(p.cantidad for p in res.perfiles)} tramos de perfil")
        calados: Dict[str, int] = {}
        for c in res.calados:
            calados[c.panel] = calados.get(c.panel, 0) + 1
        self._llenar(self.tabla_paneles, [[p.nombre, fmt(p.ancho), fmt(p.alto), str(calados.get(p.id, ""))]
                                          for p in res.paneles])
        self._llenar(self.tabla_perfiles, [[p.nombre, p.descripcion, fmt(p.largo), str(p.cantidad), p.corte]
                                           for p in res.perfiles])
        self._llenar(self.tabla_herrajes, [[h.nombre, str(h.cantidad), h.detalle, h.ref] for h in res.herrajes])
        self.lbl_avisos.setText("\n".join(f"⚠ {a}" for a in res.avisos))

    @staticmethod
    def _llenar(tabla: QTableWidget, filas: List[List[str]]) -> None:
        tabla.setRowCount(len(filas))
        for r, fila in enumerate(filas):
            for c, texto in enumerate(fila):
                item = QTableWidgetItem(texto)
                if c and texto.replace(".", "", 1).replace("-", "", 1).isdigit():
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                tabla.setItem(r, c, item)

    # ------------------------------------------------------------ archivos
    def nuevo(self) -> None:
        self.set_params({})

    def abrir(self, ruta: Optional[str] = None) -> None:
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto del taller", "",
                                                  "Proyecto OpenSCAD (*.scad)")
        if not ruta:
            return
        try:
            self.set_params(leer_proyecto(ruta), ruta)
        except Exception as e:
            QMessageBox.critical(self, "Abrir proyecto", f"No se pudo leer {os.path.basename(ruta)}:\n{e}")

    def texto_proyecto(self) -> str:
        self._leer_editores()
        titulo = os.path.splitext(os.path.basename(self.ruta))[0] if self.ruta else ""
        return escribir_proyecto(self.params, self.defectos, titulo)

    def guardar(self, ruta: Optional[str] = None) -> None:
        if not ruta:
            ruta, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto del taller",
                                                  self.ruta or "mi_case.scad", "Proyecto OpenSCAD (*.scad)")
        if not ruta:
            return
        if not ruta.lower().endswith(".scad"):
            ruta += ".scad"
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(self.texto_proyecto())
        self.ruta = ruta
        self.lbl_archivo.setText(os.path.basename(ruta))

    def exportar(self, carpeta: Optional[str] = None):
        from ...taller.produccion import exportar
        if self.resultado is None:
            return None
        if not carpeta:
            base = QFileDialog.getExistingDirectory(self, "Carpeta para el paquete del taller")
            if not base:
                return None
            nombre = os.path.splitext(os.path.basename(self.ruta))[0] if self.ruta else "case"
            carpeta = os.path.join(base, f"salida_{nombre}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            paq = exportar(self.resultado, carpeta)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Paquete del taller", f"No se pudo generar el paquete:\n{e}")
            return None
        QApplication.restoreOverrideCursor()
        avisos = ("\n\nAvisos:\n" + "\n".join(f"• {a}" for a in paq.avisos)) if paq.avisos else ""
        QMessageBox.information(self, "Paquete del taller",
                                f"Se generaron {len(paq.archivos)} archivos en:\n{carpeta}{avisos}")
        return paq
