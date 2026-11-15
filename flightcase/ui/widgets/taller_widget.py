"""Pestaña Taller: parámetros del generador del taller, resultado al instante y exportación."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from ...paths import bundled_resource
from ...taller import estilos
from ...taller.modelo import CatalogoTaller, ResultadoTaller, calcular, fmt, parametros_por_defecto
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


# Listas que se cargan en una tabla: columnas (título, "texto" o "num", valor si queda un hueco
# antes de otra columna cargada: "c" = centrado, None = obligatoria)
TABLAS: Dict[str, List[tuple]] = {
    "bandejas": [("Ancho", "num", None), ("Fondo", "num", None), ("Altura (cara de arriba)", "num", None),
                 ("Espesor", "num", None), ("Material", "texto", None)],
    "equipos": [("Nombre", "texto", ""), ("Ancho", "num", None), ("Fondo", "num", None), ("Alto", "num", None),
                ("Peso kg", "num", 0), ("X", "num", "c"), ("Y", "num", "c"), ("Z", "num", 0),
                ("Forma en la espuma", "forma", ""), ("Radio", "num", -1), ("Dedos", "num", 0)],
    "espumas": [("Ancho", "num", 0), ("Fondo", "num", 0), ("Alto", "num", 0), ("X", "num", "c"), ("Y", "num", "c"),
                ("Z", "num", 0)],
    "cajones": [("Alto del frente", "num", None), ("Altura desde el piso", "num", None), ("Ancho", "num", 0),
                ("Largo corredera", "num", 0)],
    "rack_equipos": [("Nombre", "texto", ""), ("U", "num", None), ("Fondo", "num", None), ("Peso kg", "num", 0),
                     ("Desde U", "num", 0), ("Sobresale adelante", "num", 0)],
    "extras": [("Artículo del catálogo", "ref", None), ("Cantidad", "num", 1)],
}

# Tablas cuyas filas se completan con los valores por defecto de las columnas vacías
COMPLETAR = {"extras"}

# Herrajes que se eligen del catálogo: categorías que se ofrecen en la lista (None = todas)
REF_CATEGORIAS: Dict[str, Optional[tuple]] = {
    "ref_placa": ("placa",), "ref_angulo": ("angulo",), "ref_hibrido": ("hibrido",),
    "ref_cierre_macho": ("tapa_m", "hibrido"), "ref_cierre_hembra": ("tapa_h", "hibrido"),
    "ref_esquinero": ("esquinero",), "ref_cierre": ("cierre",), "ref_manija": ("manija",),
    "ref_rueda": ("rueda",), "ref_rueda_freno": ("rueda",), "ref_plato": ("plato",),
    "ref_remache": ("remache",), "ref_pie": ("pie",), "ref_bisagra": ("bisagra",), "ref_tope": ("tope",),
    "ref_espuma": ("espuma",), "ref_espuma_bloques": ("espuma",), "ref_escuadra": ("escuadra",),
    "ref_riel": ("rack",), "ref_corredera": None,
}
SEPARADOR_REF = " — "
_catalogo: Optional[CatalogoTaller] = None


def catalogo() -> CatalogoTaller:
    global _catalogo
    if _catalogo is None:
        _catalogo = CatalogoTaller()
    return _catalogo


def etiqueta_ref(ref: str) -> str:
    """«ref — nombre» para mostrar un artículo; el ref solo si no está en el catálogo."""
    cat = catalogo()
    return f"{ref}{SEPARADOR_REF}{cat.nombre(ref)}" if cat.existe(ref) else ref


def ref_de_texto(texto: str) -> str:
    return texto.split(SEPARADOR_REF, 1)[0].strip()


def _ayuda_articulo(fila: Dict[str, Any]) -> str:
    datos = ", ".join(f"{k}: {fmt(v) if not isinstance(v, str) else v}" for k, v in fila.get("datos", {}).items())
    nota = "" if fila.get("verificado", True) else "\nMedidas estimadas: verificalas con la pieza."
    return f"{fila['nombre']} ({fila['categoria']})" + (f"\n{datos}" if datos else "") + nota


def _llenar_combo_catalogo(w: QComboBox, categorias: Optional[tuple], vacio: bool) -> None:
    """Carga los artículos del catálogo (de esas categorías) en un combo editable con búsqueda."""
    w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    w.setMinimumContentsLength(18)
    w.view().setMinimumWidth(420)
    if vacio:
        w.addItem("", "")
    filas = catalogo().filas
    orden = list(categorias) if categorias else sorted({f["categoria"] for f in filas})
    for cat in orden:
        for f in filas:
            if f["categoria"] == cat:
                w.addItem(f"{f['ref']}{SEPARADOR_REF}{f['nombre']}" + ("" if f.get("verificado", True) else " *"),
                          f["ref"])
                w.setItemData(w.count() - 1, _ayuda_articulo(f), Qt.ToolTipRole)
    comp = QCompleter(w.model(), w)
    comp.setFilterMode(Qt.MatchContains)
    comp.setCaseSensitivity(Qt.CaseInsensitive)
    w.setCompleter(comp)


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
        elif isinstance(defecto, str) and nombre in REF_CATEGORIAS:
            w = QComboBox()
            w.setEditable(True)
            w.setMaxVisibleItems(20)
            _llenar_combo_catalogo(w, REF_CATEGORIAS[nombre], vacio=True)
            w.lineEdit().setPlaceholderText("sin elegir (usa las medidas)")
            w.currentTextChanged.connect(al_cambiar)
            w.activated.connect(lambda *_: w.lineEdit().setCursorPosition(0))
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
            elif isinstance(w, QComboBox) and self.nombre in REF_CATEGORIAS:
                i = w.findData(str(valor))
                if i >= 0:
                    w.setCurrentIndex(i)
                else:
                    w.setEditText(str(valor))
                w.lineEdit().setCursorPosition(0)
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
        if isinstance(w, QComboBox) and self.nombre in REF_CATEGORIAS:
            return ref_de_texto(w.currentText())
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


def _a_numero(texto: str) -> float:
    v = float(texto.strip().replace(",", "."))
    return int(v) if v.is_integer() else v


class _DelegadoArticulo(QStyledItemDelegate):
    """Celda que se edita eligiendo un artículo del catálogo (con búsqueda por texto)."""

    def createEditor(self, parent, option, index):  # noqa: N802 (nombre de Qt)
        w = QComboBox(parent)
        w.setEditable(True)
        w.setMaxVisibleItems(20)
        _llenar_combo_catalogo(w, None, vacio=False)
        return w

    def setEditorData(self, editor, index):  # noqa: N802
        ref = ref_de_texto(index.data() or "")
        i = editor.findData(ref)
        if i >= 0:
            editor.setCurrentIndex(i)
        else:
            editor.setEditText(ref)

    def setModelData(self, editor, model, index):  # noqa: N802
        model.setData(index, etiqueta_ref(ref_de_texto(editor.currentText())))


class _DelegadoForma(QStyledItemDelegate):
    """Forma del calado de espuma: rect, redondo o un dibujo (.dxf / .svg) elegido del disco."""

    ELEGIR = "Elegir dibujo (.dxf / .svg)…"

    def createEditor(self, parent, option, index):  # noqa: N802 (nombre de Qt)
        w = QComboBox(parent)
        w.setEditable(True)
        w.addItems(["rect", "redondo", self.ELEGIR])
        w.activated.connect(lambda i, w=w: self._elegir(w) if w.itemText(i) == self.ELEGIR else None)
        return w

    def _elegir(self, w: QComboBox) -> None:
        ruta, _ = QFileDialog.getOpenFileName(w, "Contorno del equipo", "", "Dibujos (*.dxf *.svg)")
        w.setEditText(ruta or "")

    def setEditorData(self, editor, index):  # noqa: N802
        editor.setEditText(index.data() or "")

    def setModelData(self, editor, model, index):  # noqa: N802
        t = editor.currentText().strip()
        model.setData(index, "" if t == self.ELEGIR else t)


class _EditorTabla:
    """Editor de una lista de listas (bandejas, equipos, cajones...) como tabla con filas."""

    def __init__(self, nombre: str, defecto: Any, al_cambiar) -> None:
        self.nombre, self.defecto = nombre, defecto
        self.columnas = TABLAS[nombre]
        self._al_cambiar = al_cambiar
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tabla = QTableWidget(0, len(self.columnas))
        self.tabla.setHorizontalHeaderLabels([c[0] for c in self.columnas])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.setMinimumHeight(140)
        for c, (_, tipo, _r) in enumerate(self.columnas):
            if tipo in ("ref", "forma"):
                self._delegado = _DelegadoArticulo(self.tabla) if tipo == "ref" else _DelegadoForma(self.tabla)
                self.tabla.setItemDelegateForColumn(c, self._delegado)
            if tipo == "forma":   # una ruta larga no tapa las columnas de al lado
                self.tabla.horizontalHeader().setSectionResizeMode(c, QHeaderView.Interactive)
                self.tabla.setColumnWidth(c, 150)
                self.tabla.setTextElideMode(Qt.ElideLeft)
        self.tabla.cellChanged.connect(lambda *_: self._al_cambiar())
        lay.addWidget(self.tabla)
        botones = QHBoxLayout()
        for texto, slot in (("+ Agregar", self._agregar), ("− Quitar", self._quitar)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            botones.addWidget(b)
        botones.addStretch(1)
        lay.addLayout(botones)
        self.widget = w

    def _agregar(self) -> None:
        self.tabla.insertRow(self.tabla.rowCount())

    def _quitar(self) -> None:
        filas = sorted({i.row() for i in self.tabla.selectedIndexes()} or {self.tabla.rowCount() - 1}, reverse=True)
        for f in filas:
            if f >= 0:
                self.tabla.removeRow(f)
        self._al_cambiar()

    def poner(self, valor: Any) -> None:
        filas = valor if isinstance(valor, list) else []
        self.tabla.blockSignals(True)
        try:
            self.tabla.setRowCount(0)
            for fila in filas:
                r = self.tabla.rowCount()
                self.tabla.insertRow(r)
                celdas = fila if isinstance(fila, list) else [fila]
                for c, v in enumerate(celdas[:len(self.columnas)]):
                    vacio = v == "c" or (v == -1 and self.columnas[c][2] == -1)   # relleno que se muestra vacío
                    texto = "" if vacio else (fmt(v) if isinstance(v, (int, float)) else str(v))
                    if self.columnas[c][1] == "ref":
                        texto = etiqueta_ref(texto)
                    self.tabla.setItem(r, c, QTableWidgetItem(texto))
        finally:
            self.tabla.blockSignals(False)

    def valor(self) -> Any:
        out, error = [], False
        self.tabla.blockSignals(True)
        try:
            for r in range(self.tabla.rowCount()):
                celdas: List[Any] = []
                for c, (_, tipo, _r) in enumerate(self.columnas):
                    item = self.tabla.item(r, c)
                    texto = item.text().strip() if item else ""
                    if item:
                        item.setBackground(QBrush())
                    if not texto:
                        celdas.append(None)
                    elif tipo == "num":
                        try:
                            celdas.append(_a_numero(texto))
                        except ValueError:
                            item.setBackground(QColor("#ffd6d6"))
                            error = True
                            celdas.append(None)
                    elif tipo == "ref":
                        celdas.append(ref_de_texto(texto))
                    else:
                        celdas.append(texto)
                while celdas and celdas[-1] is None:
                    celdas.pop()
                if not celdas:
                    continue
                if self.nombre in COMPLETAR:   # filas que el modelo lee enteras
                    celdas += [None] * (len(self.columnas) - len(celdas))
                for c, v in enumerate(celdas):
                    if v is None:
                        relleno = self.columnas[c][2]
                        if relleno is None:
                            error = True
                            item = self.tabla.item(r, c)
                            if item is None:
                                item = QTableWidgetItem("")
                                self.tabla.setItem(r, c, item)
                            item.setBackground(QColor("#ffd6d6"))
                        celdas[c] = relleno
                out.append(celdas)
        finally:
            self.tabla.blockSignals(False)
        if error:
            raise ValueError(f"tabla {self.nombre} incompleta")
        return out


class TallerWidget(QWidget):
    """Editor de un case con las reglas del taller (las del generador de OpenSCAD)."""

    resultado_cambiado = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.defectos = parametros_por_defecto()
        self.params: Dict[str, Any] = dict(self.defectos)
        self.ruta: Optional[str] = None
        self.resultado: Optional[ResultadoTaller] = None
        self.editores: Dict[str, Any] = {}
        self._habia_interior = False
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
                            ("Guardar .scad…", self.guardar), ("Exportar paquete…", self.exportar),
                            ("Exportar STEP…", self.exportar_step)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            barra.addWidget(b)
        raiz.addLayout(barra)

        fila_estilo = QHBoxLayout()
        fila_estilo.addWidget(QLabel("Estilo de case:"))
        self.cmb_estilo = QComboBox()
        self.cmb_estilo.setMinimumWidth(280)
        self.cmb_estilo.setToolTip("Aplica una forma de armado (tapas, accesos, bisagras, ruedas…) "
                                   "sin tocar las medidas ni el interior.")
        self.cmb_estilo.activated.connect(self._estilo_elegido)
        self.cmb_estilo.setMaximumWidth(460)
        fila_estilo.addWidget(self.cmb_estilo)
        self.btn_guardar_estilo = QPushButton("Guardar como estilo…")
        self.btn_guardar_estilo.setToolTip("Guarda cómo está armado este case (sin medidas ni interior) "
                                           "para usarlo en otros proyectos.")
        self.btn_guardar_estilo.clicked.connect(lambda: self.guardar_estilo())
        fila_estilo.addWidget(self.btn_guardar_estilo)
        self.btn_borrar_estilo = QPushButton("Borrar estilo")
        self.btn_borrar_estilo.clicked.connect(lambda: self.borrar_estilo())
        fila_estilo.addWidget(self.btn_borrar_estilo)
        fila_estilo.addStretch(1)
        raiz.addLayout(fila_estilo)
        self.lbl_estilo = QLabel()
        self.lbl_estilo.setWordWrap(True)
        self.lbl_estilo.setStyleSheet("font-style:italic")
        raiz.addWidget(self.lbl_estilo)
        self._cargar_estilos()

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
                etiqueta = QLabel(nombre)
                etiqueta.setToolTip(_ayuda(p["ayuda"]))
                if nombre in TABLAS:
                    ed = _EditorTabla(nombre, self.defectos[nombre], self._programar)
                    ed.widget.setToolTip(_ayuda(p["ayuda"]))
                    form.addRow(etiqueta)
                    form.addRow(ed.widget)
                else:
                    ed = _Editor(nombre, self.defectos[nombre], self._programar)
                    ed.widget.setToolTip(_ayuda(p["ayuda"]))
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
        from .schema_3d_widget import Schema3DCanvas
        pagina_3d = QWidget()
        l3d = QVBoxLayout(pagina_3d)
        l3d.setContentsMargins(0, 0, 0, 0)
        self.chk_interior = QCheckBox("Ver el interior (tapas abiertas)")
        self.chk_interior.toggled.connect(self._actualizar_3d)
        l3d.addWidget(self.chk_interior)
        self.vista_3d = Schema3DCanvas(self)
        self.vista_3d.setMinimumHeight(260)
        l3d.addWidget(self.vista_3d, 1)
        self.tabs.addTab(pagina_3d, "Vista 3D")
        from .herrajes_2d_widget import HerrajesManualesWidget
        self.herrajes = HerrajesManualesWidget(self)
        self.herrajes.cambiado.connect(self._herrajes_cambiados)
        self.tabs.addTab(self.herrajes, "Herrajes a mano")
        self.tabla_paneles = self._tabla(["Pieza", "Ancho", "Alto", "Calados"])
        self.tabla_perfiles = self._tabla(["Perfil", "Descripción", "Largo", "Cant.", "Corte"])
        self.tabla_herrajes = self._tabla(["Herraje", "Cant.", "Detalle", "Ref."])
        self.tabs.addTab(self.tabla_paneles, "Paneles")
        self.tabs.addTab(self.tabla_perfiles, "Perfiles")
        self.tabs.addTab(self.tabla_herrajes, "Herrajes")
        pagina_int = QWidget()
        li = QVBoxLayout(pagina_int)
        li.setContentsMargins(0, 0, 0, 0)
        self.lbl_interior = QLabel()
        self.lbl_interior.setWordWrap(True)
        li.addWidget(self.lbl_interior)
        self.tabla_interior = self._tabla(["Tipo", "Nombre", "Medidas", "Posición", "Nota"])
        li.addWidget(self.tabla_interior, 1)
        self.tabs.addTab(pagina_int, "Interior")
        dl.addWidget(self.tabs, 1)
        self.lbl_avisos = QLabel()
        self.lbl_avisos.setWordWrap(True)
        self.lbl_avisos.setStyleSheet("color:#a15c00")
        dl.addWidget(self.lbl_avisos)
        divisor.addWidget(derecha)
        divisor.setStretchFactor(0, 40)
        divisor.setStretchFactor(1, 60)
        divisor.setSizes([480, 900])   # que entren los nombres de los herrajes elegidos
        raiz.addWidget(divisor, 1)

    # ------------------------------------------------------------- estilos
    def _cargar_estilos(self, elegir: str = "") -> None:
        self.cmb_estilo.blockSignals(True)
        self.cmb_estilo.clear()
        self.cmb_estilo.addItem("Elegí un estilo para aplicarlo…", "")
        lista = estilos.todos()
        for e in lista:
            self.cmb_estilo.addItem(("★ " if e.propio else "") + e.nombre, e.id)
            self.cmb_estilo.setItemData(self.cmb_estilo.count() - 1, e.descripcion, Qt.ToolTipRole)
        i = self.cmb_estilo.findData(elegir) if elegir else 0
        self.cmb_estilo.setCurrentIndex(max(i, 0))
        self.cmb_estilo.blockSignals(False)
        self._estilos = {e.id: e for e in lista}
        self._mostrar_estilo()

    def _mostrar_estilo(self) -> None:
        e = self._estilos.get(self.cmb_estilo.currentData() or "")
        self.lbl_estilo.setText(e.descripcion if e else "")
        self.btn_borrar_estilo.setEnabled(bool(e and e.propio))

    def _estilo_elegido(self, _indice: int) -> None:
        id_estilo = self.cmb_estilo.currentData()
        if id_estilo:
            self.aplicar_estilo(id_estilo)
        self._mostrar_estilo()

    def aplicar_estilo(self, id_estilo: str) -> None:
        """Aplica un estilo sobre las medidas e interior actuales."""
        e = self._estilos.get(id_estilo) or estilos.buscar(id_estilo)
        if e is None:
            return
        self._leer_editores()
        try:
            self.params = estilos.aplicar(self.params, e, self.defectos)
        except Exception as ex:   # base automática con medidas que el modelo no admite
            self.lbl_avisos.setText(f"No se pudo aplicar el estilo «{e.nombre}»: {ex}")
            return
        i = self.cmb_estilo.findData(id_estilo)
        if i >= 0:
            self.cmb_estilo.setCurrentIndex(i)
        self._cargar_en_editores()
        self.recalcular()
        self._mostrar_estilo()

    def guardar_estilo(self, nombre: Optional[str] = None) -> Optional[str]:
        if nombre is None:
            nombre, ok = QInputDialog.getText(self, "Guardar como estilo",
                                              "Nombre del estilo (guarda cómo está armado, sin medidas ni interior):")
            if not ok:
                return None
        if not nombre.strip():
            return None
        self._leer_editores()
        e = estilos.guardar_propio(nombre, self.params, self.defectos)
        self._cargar_estilos(e.id)
        return e.id

    def borrar_estilo(self, confirmar: bool = True) -> None:
        e = self._estilos.get(self.cmb_estilo.currentData() or "")
        if not e or not e.propio:
            return
        if confirmar and QMessageBox.question(self, "Borrar estilo", f"¿Borrar el estilo «{e.nombre}»?") != QMessageBox.Yes:
            return
        estilos.borrar_propio(e.id)
        self._cargar_estilos()

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

    def _herrajes_cambiados(self, filas: List[Any]) -> None:
        self.params["herrajes_manuales"] = filas
        self.recalcular()

    def set_params(self, params: Dict[str, Any], ruta: Optional[str] = None) -> None:
        self.params = dict(self.defectos)
        self.params.update(params)
        self.params["_carpeta"] = os.path.dirname(os.path.abspath(ruta)) if ruta else ""
        self.ruta = ruta
        self.lbl_archivo.setText(os.path.basename(ruta) if ruta else "Proyecto nuevo")
        self.cmb_estilo.setCurrentIndex(0)
        self._mostrar_estilo()
        self._cargar_en_editores()
        self.recalcular()

    def recalcular(self) -> None:
        if not self._leer_editores():
            self.lbl_avisos.setText("Hay un dato mal cargado (en rojo): una lista mal escrita, un número que no se entiende o una celda obligatoria vacía.")
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
        interior = v.get("interiores")
        if interior is not None:
            self.lbl_interior.setText("<br>".join(interior.resumen))
            self._llenar(self.tabla_interior, interior.elementos)
            if not self._habia_interior:
                self.chk_interior.blockSignals(True)
                self.chk_interior.setChecked(True)   # recién cargado: mostrarlo
                self.chk_interior.blockSignals(False)
        else:
            self.lbl_interior.setText("Sin interior cargado. Agregá equipos, espuma, cajones o un rack "
                                      "en las secciones «Interior» de la izquierda.")
            self._llenar(self.tabla_interior, [])
        self._habia_interior = interior is not None
        self.herrajes.set_resultado(res, self.params.get("herrajes_manuales", []), self.params.get("_carpeta", ""))
        self._actualizar_3d()

    def _actualizar_3d(self, *_args) -> None:
        res = self.resultado
        if res is None:
            return
        try:
            from ...taller.geometria import Opciones3D, malla_3d
            abrir = self.chk_interior.isChecked()
            v = res.valores
            op = Opciones3D(abrir_tapa=0.8 * max(v["ext_ancho"], v["ext_prof"], v["ext_alto"]) if abrir else 0.0)
            self.vista_3d.set_mesh(malla_3d(res, op))
        except Exception as e:   # la vista 3D nunca debe impedir ver el resultado
            self.lbl_avisos.setText(self.lbl_avisos.text() + f"\n(No se pudo armar la vista 3D: {e})")

    @staticmethod
    def _llenar(tabla: QTableWidget, filas: List[List[str]]) -> None:
        tabla.setRowCount(len(filas))
        for r, fila in enumerate(filas):
            for c, texto in enumerate(fila):
                item = QTableWidgetItem(texto)
                if c and texto.removeprefix("-").replace(".", "", 1).isdigit():   # números, no refs (08-41076)
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
        self._mudar_logos(os.path.dirname(os.path.abspath(ruta)))
        self.herrajes.carpeta = self.params["_carpeta"]
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(self.texto_proyecto())
        self.ruta = ruta
        self.lbl_archivo.setText(os.path.basename(ruta))

    def _mudar_logos(self, carpeta: str) -> None:
        """Al guardar en otra carpeta, los logos con ruta relativa siguen apuntando al mismo archivo."""
        vieja = self.params.get("_carpeta", "")
        filas = []
        for e in self.params.get("herrajes_manuales") or []:
            if isinstance(e, list) and len(e) > 8 and isinstance(e[8], str) and e[8]:
                absoluta = e[8] if os.path.isabs(e[8]) else os.path.abspath(os.path.join(vieja or carpeta, e[8]))
                try:
                    rel = os.path.relpath(absoluta, carpeta)
                except ValueError:
                    rel = absoluta
                e = list(e)
                e[8] = absoluta if rel.startswith("..") else rel.replace(os.sep, "/")
            filas.append(e)
        if filas:
            self.params["herrajes_manuales"] = filas
        equipos = []
        for e in self.params.get("equipos") or []:   # contornos de espuma (.dxf / .svg) con ruta relativa
            if (isinstance(e, list) and len(e) > 8 and isinstance(e[8], str)
                    and e[8].lower().endswith((".dxf", ".svg"))):
                absoluta = e[8] if os.path.isabs(e[8]) else os.path.abspath(os.path.join(vieja or carpeta, e[8]))
                try:
                    rel = os.path.relpath(absoluta, carpeta)
                except ValueError:
                    rel = absoluta
                e = list(e)
                e[8] = absoluta if rel.startswith("..") else rel.replace(os.sep, "/")
            equipos.append(e)
        if equipos:
            self.params["equipos"] = equipos
        self.params["_carpeta"] = carpeta

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

    def exportar_step(self, ruta: Optional[str] = None):
        """Modelo 3D del case armado (.step) para abrir en Fusion, SolidWorks o FreeCAD."""
        from ...taller.step import exportar_step
        if self.resultado is None:
            return None
        nombre = os.path.splitext(os.path.basename(self.ruta))[0] if self.ruta else "case"
        if not ruta:
            ruta, _ = QFileDialog.getSaveFileName(self, "Exportar el case a STEP", f"{nombre}.step",
                                                  "Modelo 3D STEP (*.step *.stp)")
            if not ruta:
                return None
            if not ruta.lower().endswith((".step", ".stp")):
                ruta += ".step"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            st = exportar_step(self.resultado, ruta, nombre)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Exportar STEP", f"No se pudo exportar el STEP:\n{e}")
            return None
        QApplication.restoreOverrideCursor()
        avisos = ("\n\nAvisos:\n" + "\n".join(f"• {a}" for a in st.avisos)) if st.avisos else ""
        QMessageBox.information(self, "Exportar STEP",
                                f"Se exportó el case armado ({st.piezas} piezas, {st.cuerpos} cuerpos) a:\n{ruta}{avisos}")
        return st
