"""Pestaña Taller: parámetros del generador del taller, resultado al instante y exportación."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
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
    QSizePolicy,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...paths import bundled_resource
from ...taller import estilos
from ...taller.modelo import ENTEROS, CatalogoTaller, ResultadoTaller, calcular, catalogo_actual, fmt, parametros_por_defecto
from ...taller.scad import escribir_proyecto, leer_proyecto, literal, valor_literal

# Opciones fijas de los parámetros de texto que las tienen
OPCIONES: Dict[str, List[str]] = {
    "orientacion": ["vertical", "horizontal", "frontal"],
    "forma": ["caja", "inclinado", "funda", "plegable", "slam", "tabla"],
    "slam_caras": ["arriba", "frente", "frente_trasera", "arriba_frente"],
    "tapa_plana": ["slam", "lidmaker"],
    "puerta_lado": ["izq", "der"],
    "patin_sentido": ["auto", "ancho", "largo"],
    "patas_en": ["tapa", "cuerpo"],
    "sistema": ["angulo", "hibrido"],
    "acceso_tipo": ["paneles", "cubierta"],
    "paredes_enteras": ["frente", "laterales"],
    "paredes_enteras_cuerpo": ["", "frente", "laterales"],
    "manijas_en": ["auto", "laterales", "frente"],
    "cierres_laterales": ["auto", "si", "no"],
}
# Números que sólo toman valores enteros


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
    "formulas": [("Medida o variable", "texto", None), ("Fórmula", "texto", None)],
    "paneles_material": [("Panel o grupo", "panel", None), ("Placa del catálogo", "placa", ""),
                         ("Espesor", "num", 0), ("Material", "texto", "")],
    "forro": [("Cara o grupo", "cara", None), ("Material", "forro_tipo", "alfombra"), ("Espesor", "num", 0),
              ("Artículo del catálogo", "forro_ref", "")],
}

# Tablas cuyas filas se completan con los valores por defecto de las columnas vacías
COMPLETAR = {"extras", "paneles_material", "forro"}

# Herrajes que se eligen del catálogo: categorías que se ofrecen en la lista (None = todas)
REF_CATEGORIAS: Dict[str, Optional[tuple]] = {
    "ref_placa": ("placa",), "ref_angulo": ("angulo",), "ref_hibrido": ("hibrido",),
    "ref_cierre_macho": ("tapa_m", "hibrido"), "ref_cierre_hembra": ("tapa_h", "hibrido"),
    "ref_esquinero": ("esquinero",), "ref_cierre": ("cierre",), "ref_manija": ("manija",),
    "ref_rueda": ("rueda",), "ref_rueda_freno": ("rueda",), "ref_rueda_fija": ("rueda",),
    "ref_cazoleta": ("cazoleta",), "ref_plato": ("plato",),
    "ref_remache": ("remache",), "ref_pie": ("pie",), "ref_bisagra": ("bisagra",), "ref_tope": ("tope",),
    "ref_espuma": ("espuma",), "ref_espuma_bloques": ("espuma",), "ref_escuadra": ("escuadra",),
    "ref_riel": ("rack",), "ref_corredera": None,
}
SEPARADOR_REF = " — "


def catalogo() -> CatalogoTaller:
    """El catálogo en uso, con los cambios del usuario (Editar → Catálogo)."""
    return catalogo_actual()


def etiqueta_ref(ref: str) -> str:
    """«ref — nombre» para mostrar un artículo; el ref solo si no está en el catálogo."""
    cat = catalogo()
    return f"{ref}{SEPARADOR_REF}{cat.nombre(ref)}" if cat.existe(ref) else ref


def ref_de_texto(texto: str) -> str:
    return texto.split(SEPARADOR_REF, 1)[0].strip()


def _ayuda_articulo(fila: Dict[str, Any]) -> str:
    from ...taller import catalogo as C
    datos = C.resumen_datos(fila)
    extra = "".join(f"\n{t}: {fila[k]}" for k, t in (("proveedor", "Proveedor"), ("nota", "Nota")) if fila.get(k))
    if fila.get("origen") in ("propio", "modificado"):
        extra += "\nDe tu catálogo" + (" (cambiado)" if fila["origen"] == "modificado" else "")
    nota = "" if fila.get("verificado", True) else "\nMedidas estimadas: verificalas con la pieza."
    return f"{fila['nombre']} ({C.NOMBRES.get(fila['categoria'], fila['categoria'])})" + \
        (f"\n{datos}" if datos else "") + extra + nota


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


def _settings():
    from PySide6.QtCore import QSettings
    return QSettings("FlightcaseCalculator", "FlightcaseCalculator")


def _con_codigo(ayuda: str, nombre: str) -> str:
    """La ayuda con el nombre del parámetro en el .scad, para quien edite el archivo a mano."""
    return f"{ayuda}\n\nEn el .scad: {nombre}" if ayuda else f"En el .scad: {nombre}"


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

    def __init__(self, parent=None, categorias: Optional[tuple] = None) -> None:
        super().__init__(parent)
        self.categorias = categorias

    def createEditor(self, parent, option, index):  # noqa: N802 (nombre de Qt)
        w = QComboBox(parent)
        w.setEditable(True)
        w.setMaxVisibleItems(20)
        _llenar_combo_catalogo(w, self.categorias, vacio=self.categorias is not None)
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


def etiqueta_panel(clave: str, opciones: List[tuple]) -> str:
    """«id — nombre» de un panel o grupo del case; la clave sola si no está en el case."""
    nombre = dict(opciones).get(clave)
    return f"{clave}{SEPARADOR_REF}{nombre}" if nombre else clave


class _DelegadoPanel(QStyledItemDelegate):
    """Celda que se edita eligiendo un panel (o un grupo de paneles) del case calculado."""

    def __init__(self, parent, opciones) -> None:
        super().__init__(parent)
        self.opciones = opciones          # función: [(clave, nombre)] del último cálculo

    def createEditor(self, parent, option, index):  # noqa: N802 (nombre de Qt)
        w = QComboBox(parent)
        w.setEditable(True)
        w.setMaxVisibleItems(24)
        for clave, nombre in self.opciones():
            w.addItem(f"{clave}{SEPARADOR_REF}{nombre}", clave)
        return w

    def setEditorData(self, editor, index):  # noqa: N802
        clave = ref_de_texto(index.data() or "")
        i = editor.findData(clave)
        if i >= 0:
            editor.setCurrentIndex(i)
        else:
            editor.setEditText(clave)

    def setModelData(self, editor, model, index):  # noqa: N802
        model.setData(index, etiqueta_panel(ref_de_texto(editor.currentText()), self.opciones()))


class _DelegadoOpciones(QStyledItemDelegate):
    """Celda que se elige de una lista fija (se puede escribir otro valor)."""

    def __init__(self, parent, opciones: List[str]) -> None:
        super().__init__(parent)
        self.opciones = opciones

    def createEditor(self, parent, option, index):  # noqa: N802 (nombre de Qt)
        w = QComboBox(parent)
        w.setEditable(True)
        w.addItems(self.opciones)
        return w

    def setEditorData(self, editor, index):  # noqa: N802
        editor.setEditText(index.data() or "")

    def setModelData(self, editor, model, index):  # noqa: N802
        model.setData(index, editor.currentText().strip())


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

    def __init__(self, nombre: str, defecto: Any, al_cambiar, opciones_panel=None, opciones_cara=None) -> None:
        self.nombre, self.defecto = nombre, defecto
        self.columnas = TABLAS[nombre]
        self.opciones_panel = opciones_panel or (lambda: [])
        self.opciones_cara = opciones_cara or (lambda: [])
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
            delegado = {"ref": lambda: _DelegadoArticulo(self.tabla),
                        "placa": lambda: _DelegadoArticulo(self.tabla, ("placa",)),
                        "forma": lambda: _DelegadoForma(self.tabla),
                        "panel": lambda: _DelegadoPanel(self.tabla, self.opciones_panel),
                        "cara": lambda: _DelegadoPanel(self.tabla, self.opciones_cara),
                        "forro_tipo": lambda: _DelegadoOpciones(self.tabla, ["alfombra", "espuma", "no"]),
                        "forro_ref": lambda: _DelegadoArticulo(self.tabla, ("espuma", "alfombra"))}.get(tipo)
            if delegado:
                d = delegado()
                self._delegados = getattr(self, "_delegados", []) + [d]   # Qt no se queda con la referencia
                self.tabla.setItemDelegateForColumn(c, d)
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
        if nombre in ("equipos", "rack_equipos"):   # biblioteca de equipos propios
            b = QPushButton("Desde la biblioteca…")
            b.setToolTip("Elegí equipos guardados en tu biblioteca y agregalos a esta tabla")
            b.clicked.connect(self.desde_biblioteca)
            botones.addWidget(b)
            b = QPushButton("Guardar en la biblioteca")
            b.setToolTip("Guarda las filas elegidas (o todas) en tu biblioteca de equipos, para usarlas en otros cases")
            b.clicked.connect(lambda: self.guardar_en_biblioteca())
            botones.addWidget(b)
        botones.addStretch(1)
        lay.addLayout(botones)
        self.widget = w

    # ------------------------------------------------------- biblioteca
    def agregar_filas(self, filas: List[List[Any]]) -> None:
        self.tabla.blockSignals(True)
        try:
            for fila in filas:
                self._poner_fila(self.tabla.rowCount(), fila)
        finally:
            self.tabla.blockSignals(False)
        self._al_cambiar()

    def desde_biblioteca(self) -> None:
        from .biblioteca_widget import BibliotecaDialog
        rack = self.nombre == "rack_equipos"
        dlg = BibliotecaDialog(self.widget, agregar=lambda eqs: self.agregar_filas(
            [e.fila_rack() if rack else e.fila_equipos() for e in eqs]),
            texto_agregar="Agregar al rack" if rack else "Agregar a los equipos")
        dlg.exec()

    def guardar_en_biblioteca(self, filas_elegidas: Optional[List[int]] = None) -> int:
        from ...taller import biblioteca as B
        try:
            filas = self.valor()
        except ValueError:
            QMessageBox.warning(self.widget, "Biblioteca de equipos", "Hay celdas obligatorias vacías en la tabla.")
            return 0
        elegidas = filas_elegidas if filas_elegidas is not None else sorted({i.row() for i in self.tabla.selectedIndexes()})
        if elegidas:
            filas = [f for i, f in enumerate(filas) if i in elegidas]
        nuevos = []
        for f in filas:
            try:
                nuevos.append(B.desde_fila_rack(f) if self.nombre == "rack_equipos" else B.desde_fila_equipos(f))
            except (ValueError, TypeError):
                continue
        if not nuevos:
            return 0
        lista = B.cargar()
        reemplazados = B.sumar(lista, nuevos)
        B.guardar(lista)
        extra = f"\n({len(reemplazados)} ya estaban y se actualizaron)" if reemplazados else ""
        QMessageBox.information(self.widget, "Biblioteca de equipos",
                                f"Se guardaron {len(nuevos)} equipos en la biblioteca.{extra}")
        return len(nuevos)

    def refrescar_etiquetas(self) -> None:
        """«ref — nombre» de nuevo, con los nombres del catálogo actual."""
        self.tabla.blockSignals(True)
        try:
            for c, (_, tipo, _r) in enumerate(self.columnas):
                if tipo not in ("ref", "placa"):
                    continue
                for r in range(self.tabla.rowCount()):
                    it = self.tabla.item(r, c)
                    if it and it.text().strip():
                        it.setText(etiqueta_ref(ref_de_texto(it.text())))
        finally:
            self.tabla.blockSignals(False)

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
                self._poner_fila(self.tabla.rowCount(), fila)
        finally:
            self.tabla.blockSignals(False)

    def _poner_fila(self, r: int, fila: Any) -> None:
        self.tabla.insertRow(r)
        celdas = fila if isinstance(fila, list) else [fila]
        for c, v in enumerate(celdas[:len(self.columnas)]):
            vacio = v == "c" or (v == -1 and self.columnas[c][2] == -1)   # relleno que se muestra vacío
            texto = "" if vacio else (fmt(v) if isinstance(v, (int, float)) else str(v))
            if self.columnas[c][1] in ("ref", "placa", "forro_ref"):
                texto = etiqueta_ref(texto)
            elif self.columnas[c][1] == "panel":
                texto = etiqueta_panel(texto, self.opciones_panel())
            elif self.columnas[c][1] == "cara":
                texto = etiqueta_panel(texto, self.opciones_cara())
            self.tabla.setItem(r, c, QTableWidgetItem(texto))

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
                    elif tipo in ("ref", "placa", "panel", "cara", "forro_ref"):
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
    ruta_cambiada = Signal(str)          # se abrió o se guardó un .scad (vacío = case nuevo)
    proyectos_pedidos = Signal()         # botón «Mis cases…»
    historial_cambiado = Signal()          # cambió lo que se puede deshacer o rehacer
    pantalla_inicio = None                 # la ventana pone acá su pantalla de inicio (botón «Nuevo…»)
    case_nuevo = Signal()                  # se empezó un case nuevo (botón o menú «Nuevo»)
    guardado = Signal(bool)                # se escribió el .scad (True = autoguardado)

    MAX_HISTORIAL = 200

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
        self._deshacer: List[str] = []       # fotos del case (JSON) antes de cada cambio
        self._rehacer: List[str] = []
        self._foto_actual: Optional[str] = None
        self._respaldados: set = set()        # cases con copia fechada desde que se abrieron
        self._etiquetas = {p["nombre"]: p.get("etiqueta") or p["nombre"]
                           for sec in secciones_parametros() for p in sec["parametros"]}
        self._etiquetas.update(int_alto_cuerpo="Alto interior", herrajes_manuales="Herrajes a mano")
        self._init_ui()
        self._cargar_en_editores()
        self.recalcular()
        self._leer_editores()
        self._foto_guardada = self._foto()

    # ------------------------------------------------------------------ UI
    # Grupos de la barra lateral: clave, texto, y qué secciones de parámetros entran
    # (por el comienzo del título). Las que no entran en ninguno van a «Accesorios».
    GRUPOS_LATERAL = (
        ("medidas", "Medidas", ("Fórmulas",)),
        ("armado", "Armado", ("Tipo de case", "Placa", "Sistema de armado", "Corte y compra")),
        ("herrajes", "Herrajes", ("Esquineros", "Perfil de cierre", "Manijas", "Cierres", "Encastres",
                                  "Herrajes del catálogo")),
        ("ruedas", "Ruedas", ("Ruedas",)),
        ("interior", "Interior", ("Interior", "Bandejas", "Forro")),
        ("accesorios", "Accesorios", ()),
        ("vista", "Vista", ()),
    )

    def _grupo_de(self, n_sec: int, titulo: str) -> str:
        if n_sec == 0:
            return "medidas"
        for clave, _, prefijos in self.GRUPOS_LATERAL:
            if any(titulo.startswith(p) for p in prefijos):
                return clave
        return "accesorios"

    def _init_ui(self) -> None:
        from .iconos import DIBUJOS, icono
        from .panel_vista import PanelVista
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # ---- cabecera: nombre, archivo, deshacer/rehacer y acciones
        cabecera = QFrame()
        cabecera.setObjectName("cabecera")
        barra = QHBoxLayout(cabecera)
        barra.setContentsMargins(10, 6, 10, 6)
        barra.setSpacing(6)
        marca = QLabel("<span style='color:#f5a524;font-weight:800'>LBD</span>&nbsp;"
                       "<span style='font-weight:600'>Flightcase Maker</span>")
        marca.setObjectName("marca")
        barra.addWidget(marca)
        self.lbl_archivo = QLabel("Proyecto nuevo")
        self.lbl_archivo.setObjectName("archivo")
        barra.addWidget(self.lbl_archivo, 1)
        self.btn_deshacer = QPushButton("Deshacer")
        self.btn_deshacer.setIcon(icono(DIBUJOS["deshacer"]))
        self.btn_deshacer.clicked.connect(self.deshacer)
        self.btn_rehacer = QPushButton("Rehacer")
        self.btn_rehacer.setIcon(icono(DIBUJOS["rehacer"]))
        self.btn_rehacer.clicked.connect(self.rehacer)
        barra.addWidget(self.btn_deshacer)
        barra.addWidget(self.btn_rehacer)
        barra.addSpacing(12)
        for texto, slot in (("Mis cases…", self.proyectos_pedidos.emit),
                            ("Nuevo…", lambda: (self.pantalla_inicio or self.nuevo)()), ("Asistente…", lambda: self.asistente()),
                            ("Catálogo…", lambda: self.editar_catalogo()),
                            ("Abrir .scad…", self.abrir),
                            ("Guardar .scad…", self.guardar), ("Planos PDF…", lambda: self.exportar_planos()),
                            ("Exportar STEP…", self.exportar_step),
                            ("Exportar paquete…", self.exportar)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            if texto == "Exportar paquete…":       # la acción principal, resaltada
                b.setObjectName("principal")
                b.setIcon(icono(DIBUJOS["exportar"], "#ffffff"))
            barra.addWidget(b)
        raiz.addWidget(cabecera)

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        raiz.addLayout(cuerpo, 1)

        # ---- barra lateral de íconos
        lateral = QFrame()
        lateral.setObjectName("lateral")
        ll = QVBoxLayout(lateral)
        ll.setContentsMargins(4, 6, 4, 6)
        ll.setSpacing(2)
        self.botones_lateral: Dict[str, QToolButton] = {}
        self.grupo_lateral = QButtonGroup(self)
        self.grupo_lateral.setExclusive(True)

        def boton_lateral(clave: str, texto: str, marcable: bool = True) -> QToolButton:
            b = QToolButton()
            b.setObjectName("botonLateral")
            b.setText(texto)
            b.setIcon(icono(DIBUJOS[clave]))
            b.setIconSize(QSize(22, 22))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setCheckable(marcable)
            b.setFixedWidth(66)
            return b
        for clave, texto, _ in self.GRUPOS_LATERAL:
            b = boton_lateral(clave, texto)
            b.clicked.connect(lambda _=False, c=clave: self.mostrar_grupo(c))
            self.grupo_lateral.addButton(b)
            self.botones_lateral[clave] = b
            ll.addWidget(b)
        ll.addStretch(1)
        self.btn_panel = boton_lateral("panel", "Panel")
        self.btn_panel.setChecked(True)
        self.btn_panel.setToolTip("Mostrar u ocultar el panel de la izquierda (más lugar para la vista 3D)")
        self.btn_panel.toggled.connect(self._mostrar_panel)
        ll.addWidget(self.btn_panel)
        cuerpo.addWidget(lateral)

        divisor = QSplitter(Qt.Horizontal, self)
        divisor.setObjectName("divisorTaller")
        divisor.setHandleWidth(3)
        cuerpo.addWidget(divisor, 1)

        # ---- panel izquierdo: una página por grupo, con sus secciones una abajo de otra
        self.panel_izq = QFrame()
        self.panel_izq.setObjectName("panelIzq")
        self.panel_izq.setMinimumWidth(300)
        pl = QVBoxLayout(self.panel_izq)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        self.lbl_grupo = QLabel()
        self.lbl_grupo.setObjectName("tituloPanel")
        pl.addWidget(self.lbl_grupo)
        if True:   # estilo de case: arriba del panel, a mano en todos los grupos (menos en Vista)
            self.caja_estilo = caja_estilo = QFrame()
            caja_estilo.setObjectName("cajaEstilo")
            fe = QVBoxLayout(caja_estilo)
            fe.setContentsMargins(10, 4, 10, 6)
            fe.setSpacing(4)
            fila_estilo = QHBoxLayout()
            fila_estilo.addWidget(QLabel("Estilo:"))
            self.cmb_estilo = QComboBox()
            self.cmb_estilo.setMinimumWidth(160)
            self.cmb_estilo.setToolTip("Aplica una forma de armado (tapas, accesos, bisagras, ruedas…) "
                                       "sin tocar las medidas ni el interior.")
            self.cmb_estilo.activated.connect(self._estilo_elegido)
            fila_estilo.addWidget(self.cmb_estilo, 1)
            fe.addLayout(fila_estilo)
            fila_b = QHBoxLayout()
            self.btn_guardar_estilo = QPushButton("Guardar como estilo…")
            self.btn_guardar_estilo.setToolTip("Guarda cómo está armado este case (sin medidas ni interior) "
                                               "para usarlo en otros proyectos.")
            self.btn_guardar_estilo.clicked.connect(lambda: self.guardar_estilo())
            fila_b.addWidget(self.btn_guardar_estilo)
            self.btn_borrar_estilo = QPushButton("Borrar estilo")
            self.btn_borrar_estilo.clicked.connect(lambda: self.borrar_estilo())
            fila_b.addWidget(self.btn_borrar_estilo)
            fe.addLayout(fila_b)
            self.lbl_estilo = QLabel()     # descripción del estilo (completa en el tooltip)
            self.lbl_estilo.setObjectName("nota")
            self.lbl_estilo.setWordWrap(True)
            self.lbl_estilo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            fe.addWidget(self.lbl_estilo)
            pl.addWidget(caja_estilo)
        self.toolbox = QStackedWidget()      # páginas del panel (el nombre viene del QToolBox de antes)
        self.toolbox.setObjectName("paginas")
        pl.addWidget(self.toolbox, 1)
        self._cargar_estilos()

        paginas: Dict[str, QVBoxLayout] = {}
        self._paginas: Dict[str, int] = {}
        self.secciones_de_grupo: Dict[str, List[str]] = {c: [] for c, _, _ in self.GRUPOS_LATERAL}
        for clave, _, _ in self.GRUPOS_LATERAL:
            pagina = QWidget()
            pagina.setObjectName("pagina")
            lay = QVBoxLayout(pagina)
            lay.setContentsMargins(10, 4, 10, 10)
            lay.setSpacing(4)
            paginas[clave] = lay
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(pagina)
            self._paginas[clave] = self.toolbox.addWidget(scroll)
        for n_sec, sec in enumerate(secciones_parametros()):
            titulo = "Medidas" if n_sec == 0 else sec["seccion"]
            grupo = self._grupo_de(n_sec, titulo)
            self.secciones_de_grupo[grupo].append(titulo)
            if n_sec:                 # la de medidas ya lleva el título de la página
                cab = QLabel(titulo)
                cab.setObjectName("tituloSeccion")
                cab.setWordWrap(True)
                paginas[grupo].addWidget(cab)
            caja = QWidget()
            form = QFormLayout(caja)
            form.setContentsMargins(0, 0, 0, 6)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)   # nombre largo: el campo pasa abajo
            if n_sec == 0:
                self._seccion_medidas(form, sec)
            for p in ([] if n_sec == 0 else sec["parametros"]):
                nombre = p["nombre"]
                if nombre not in self.defectos:
                    continue
                etiqueta = QLabel(p.get("etiqueta") or nombre)
                etiqueta.setToolTip(_ayuda(_con_codigo(p["ayuda"], nombre)))
                if nombre in TABLAS:
                    ed = _EditorTabla(nombre, self.defectos[nombre], self._programar, self._opciones_panel,
                                      self._opciones_cara)
                    ed.widget.setToolTip(_ayuda(_con_codigo(p["ayuda"], nombre)))
                    form.addRow(etiqueta)
                    form.addRow(ed.widget)
                    if nombre == "formulas":      # lo que dio cada fórmula, debajo de la tabla
                        self.lbl_formulas = QLabel()
                        self.lbl_formulas.setObjectName("notaMedidas")
                        self.lbl_formulas.setWordWrap(True)
                        self.lbl_formulas.setTextFormat(Qt.RichText)
                        form.addRow(self.lbl_formulas)
                else:
                    ed = _Editor(nombre, self.defectos[nombre], self._programar)
                    ed.widget.setToolTip(_ayuda(_con_codigo(p["ayuda"], nombre)))
                    form.addRow(etiqueta, ed.widget)
                self.editores[nombre] = ed
            paginas[grupo].addWidget(caja)
        self.panel_vista = PanelVista()
        paginas["vista"].setContentsMargins(0, 0, 0, 0)
        paginas["vista"].addWidget(self.panel_vista)
        for clave, lay in paginas.items():
            lay.addStretch(1)
            if not self.secciones_de_grupo[clave] and clave not in ("vista",):
                self.botones_lateral[clave].setVisible(False)
        divisor.addWidget(self.panel_izq)

        # ---- derecha: resumen, pestañas (vista 3D, herrajes a mano, tablas) y avisos
        derecha = QWidget()
        derecha.setObjectName("derecha")
        dl = QVBoxLayout(derecha)
        dl.setContentsMargins(6, 6, 6, 4)
        dl.setSpacing(4)
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setWordWrap(True)
        self.lbl_resumen.setTextFormat(Qt.RichText)
        self.lbl_resumen.setObjectName("resumen")
        dl.addWidget(self.lbl_resumen)
        self.tabs = QTabWidget()
        from .schema_3d_widget import Schema3DCanvas
        pagina_3d = QWidget()
        l3d = QVBoxLayout(pagina_3d)
        l3d.setContentsMargins(0, 0, 0, 0)
        l3d.setSpacing(0)
        from .barra_3d import BarraVista3D
        self.vista_3d = Schema3DCanvas(self)
        self.vista_3d.setMinimumHeight(260)
        self.barra_3d = BarraVista3D(self.vista_3d, self)
        self.chk_interior = self.panel_vista.chk_interior
        self.barra_tapas = QHBoxLayout()            # Abrir/Ocultar de cada tapa, a mano sobre la vista
        self.barra_tapas.setSpacing(2)
        self.barra_3d.layout().addLayout(self.barra_tapas)
        l3d.addWidget(self.barra_3d)
        l3d.addWidget(self.vista_3d, 1)
        self.barra_datos = QFrame()
        self.barra_datos.setObjectName("barraDatos")
        bd = QHBoxLayout(self.barra_datos)
        bd.setContentsMargins(10, 4, 10, 4)
        bd.setSpacing(18)
        self.datos: Dict[str, QLabel] = {}
        for clave, titulo in (("medida", "Medida exterior"), ("paneles", "Paneles"), ("perfiles", "Perfiles"),
                              ("herrajes", "Herrajes"), ("peso", "Peso estimado")):
            caja = QWidget()
            cl = QVBoxLayout(caja)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0)
            t = QLabel(titulo)
            t.setObjectName("datoTitulo")
            v = QLabel("–")
            v.setObjectName("datoValor")
            cl.addWidget(t)
            cl.addWidget(v)
            self.datos[clave] = v
            bd.addWidget(caja)
        bd.addStretch(1)
        self.lbl_oculto = QLabel()
        self.lbl_oculto.setObjectName("chip")
        bd.addWidget(self.lbl_oculto)
        self.btn_avisos = QPushButton()
        self.btn_avisos.setObjectName("chipAviso")
        self.btn_avisos.setCheckable(True)
        self.btn_avisos.setChecked(True)
        self.btn_avisos.setToolTip("Mostrar u ocultar los avisos debajo de la vista")
        self.btn_avisos.toggled.connect(lambda si: self.lbl_avisos.setVisible(si))
        bd.addWidget(self.btn_avisos)
        l3d.addWidget(self.barra_datos)
        self.tabs.addTab(pagina_3d, "Vista 3D")
        from .herrajes_2d_widget import HerrajesManualesWidget
        self.herrajes = HerrajesManualesWidget(self)
        self.herrajes.cambiado.connect(self._herrajes_cambiados)
        self.tabs.addTab(self.herrajes, "Herrajes a mano")
        self.tabla_paneles = self._tabla(["Pieza", "Ancho", "Alto", "Placa", "Calados"])
        self.tabla_perfiles = self._tabla(["Perfil", "Descripción", "Largo", "Cant.", "Corte"])
        self.tabla_herrajes = self._tabla(["Herraje", "Cant.", "Detalle", "Ref."])
        self.tabs.addTab(self.tabla_paneles, "Paneles")
        from .placas_widget import PlacasWidget
        self.vista_placas = PlacasWidget(self)
        self.tabs.addTab(self.vista_placas, "Placas")
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
        pagina_peso = QWidget()
        lp = QVBoxLayout(pagina_peso)
        lp.setContentsMargins(0, 0, 0, 0)
        self.lbl_peso = QLabel()
        self.lbl_peso.setWordWrap(True)
        self.lbl_peso.setTextFormat(Qt.RichText)
        lp.addWidget(self.lbl_peso)
        self.tabla_peso = self._tabla(["Parte", "Qué", "Cantidad", "Peso unitario", "Total kg", "De dónde sale"])
        lp.addWidget(self.tabla_peso, 1)
        self.tabs.addTab(pagina_peso, "Peso")
        dl.addWidget(self.tabs, 1)
        self.lbl_avisos = QLabel()
        self.lbl_avisos.setWordWrap(True)
        self.lbl_avisos.setObjectName("avisos")
        dl.addWidget(self.lbl_avisos)
        divisor.addWidget(derecha)
        divisor.setStretchFactor(0, 30)
        divisor.setStretchFactor(1, 70)
        divisor.setSizes([420, 980])   # que entren los nombres de los herrajes elegidos

        # ---- la vista: el panel maneja tapas, cajones y qué se oculta; el lienzo, el aspecto
        self._vista_case = None
        self.panel_vista.cambiado.connect(self._aplicar_vista)
        self.panel_vista.tapas_cambiadas.connect(self._barra_tapas)
        self.panel_vista.chk_realista.toggled.connect(self.vista_3d.set_realista)
        self.panel_vista.chk_fondo.toggled.connect(self.vista_3d.set_fondo_claro)
        self.panel_vista.chk_piso.toggled.connect(self.vista_3d.set_mostrar_piso)
        self.panel_vista.chk_cubo.toggled.connect(lambda si: (setattr(self.vista_3d, "mostrar_cubo", si),
                                                              self.vista_3d.update()))
        self.mostrar_grupo("medidas")

    def mostrar_grupo(self, clave: str) -> None:
        """Muestra en el panel de la izquierda las secciones de ese grupo de la barra lateral."""
        self.toolbox.setCurrentIndex(self._paginas[clave])
        self.botones_lateral[clave].setChecked(True)
        texto = dict((c, t) for c, t, _ in self.GRUPOS_LATERAL)[clave]
        self.lbl_grupo.setText(texto)
        self.caja_estilo.setVisible(clave != "vista")
        if not self.btn_panel.isChecked():
            self.btn_panel.setChecked(True)

    def grupo_actual(self) -> str:
        i = self.toolbox.currentIndex()
        return next(c for c, n in self._paginas.items() if n == i)

    def _mostrar_panel(self, si: bool) -> None:
        self.panel_izq.setVisible(si)

    def _barra_tapas(self) -> None:
        """Botones «Abrir / Ocultar» de cada tapa arriba de la vista 3D (como en el panel Vista)."""
        while self.barra_tapas.count():
            w = self.barra_tapas.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        pv = self.panel_vista
        for i, nombre in enumerate(pv.nombres_tapas):
            n = nombre.lower()
            abierta, oculta = pv.tapa_abierta(i), pv.tapa_oculta(i)
            a = QPushButton(("Cerrar " if abierta else "Abrir ") + n)
            a.setObjectName("botonTapa")
            a.setCheckable(True)
            a.setChecked(abierta)
            a.clicked.connect(lambda si, k=i: pv.abrir_tapa(k, si))
            a.setEnabled(not oculta)
            o = QPushButton(("Mostrar " if oculta else "Ocultar ") + n)
            o.setObjectName("botonTapa")
            o.setCheckable(True)
            o.setChecked(oculta)
            o.clicked.connect(lambda si, k=i: pv.ocultar_tapa(k, si))
            self.barra_tapas.addWidget(a)
            self.barra_tapas.addWidget(o)

    def _aplicar_vista(self, *_args) -> None:
        if self._vista_case is None:
            return
        estado = self.panel_vista.estado
        self.vista_3d.set_mesh(self._vista_case.aplicar(estado))
        ocultas = self._vista_case.ocultas(estado)
        self.lbl_oculto.setText(("Oculto: " + ", ".join(ocultas)) if ocultas else "")
        self.lbl_oculto.setVisible(bool(ocultas))

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
        self.lbl_estilo.setToolTip(e.descripcion if e else "")
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
    @staticmethod
    def _con_mm(w: QWidget) -> QWidget:
        """El control con "mm" a la derecha."""
        caja = QWidget()
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(6)
        fila.addWidget(w, 1)
        fila.addWidget(QLabel("mm"))
        return caja

    MEDIDAS = (("ancho", "Ancho"), ("largo", "Largo"), ("alto", "Alto"), ("cuerpo", "Alto de cuerpo"),
               ("tapa", "Alto de tapa"))

    def _seccion_medidas(self, form: QFormLayout, sec: Dict[str, Any]) -> None:
        """Medidas del case, interiores o exteriores a elección: Ancho y Largo, el Alto total con
        candado, y el alto del cuerpo y de la tapa. Las interiores son las que se guardan en el .scad;
        al cargar exteriores se recalculan con las paredes, el aluminio y la espuma de este armado."""
        ayudas = {p["nombre"]: p["ayuda"] for p in sec["parametros"]}
        caja = QWidget()
        g = QGridLayout(caja)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(3)

        def subtitulo(texto: str, fila: int) -> None:
            l = QLabel(texto)
            l.setObjectName("subtituloMedidas")
            g.addWidget(l, fila, 0, 1, 2)

        def etiqueta(texto: str) -> QLabel:
            l = QLabel(texto)
            l.setObjectName("etiquetaCampo")
            return l

        subtitulo("Medición", 0)
        g.addWidget(etiqueta("Medidas tomadas por"), 1, 0, 1, 2)
        self.cmb_medicion = QComboBox()
        self.cmb_medicion.setObjectName("medicion")
        self.cmb_medicion.addItem("Interiores", "interior")
        self.cmb_medicion.addItem("Exteriores (sin ruedas)", "exterior")
        self.cmb_medicion.setToolTip(_ayuda(
            "Interiores: el hueco útil, lo que entra adentro del case.\n"
            "Exteriores: lo que ocupa el case por fuera, sin ruedas. Al cargarlas se calculan las "
            "interiores con las paredes, el aluminio y la espuma de este armado."))
        self.cmb_medicion.currentIndexChanged.connect(lambda *_: self._medicion_cambiada())
        g.addWidget(self.cmb_medicion, 2, 0, 1, 2)

        subtitulo("Dimensiones", 3)
        self.medidas: Dict[str, QDoubleSpinBox] = {}
        self.etiquetas_medidas: Dict[str, QLabel] = {}
        lugar = {"ancho": (4, 0, 1), "largo": (4, 1, 1), "alto": (6, 0, 2), "cuerpo": (8, 0, 1), "tapa": (8, 1, 1)}
        for clave, texto in self.MEDIDAS:
            sp = _Numero()
            sp.setRange(0, 10000)
            sp.setDecimals(1)
            sp.setKeyboardTracking(False)
            sp.setObjectName("medida")
            sp.valueChanged.connect(lambda val, c=clave: self._medida_editada(c, val))
            fila, col, ancho = lugar[clave]
            et = etiqueta(texto)
            g.addWidget(et, fila, col, 1, ancho)
            self.etiquetas_medidas[clave] = et
            if clave == "alto":
                linea = QHBoxLayout()
                linea.setSpacing(6)
                linea.addWidget(sp, 1)
                linea.addWidget(QLabel("mm"))
                self.btn_candado = QToolButton()
                self.btn_candado.setObjectName("candado")
                self.btn_candado.setCheckable(True)
                self.btn_candado.setChecked(True)
                self.btn_candado.setIconSize(QSize(18, 18))
                self.btn_candado.toggled.connect(lambda *_: self._poner_icono_candado())
                linea.addWidget(self.btn_candado)
                g.addLayout(linea, fila + 1, col, 1, ancho)
                self._poner_icono_candado()
            else:
                g.addWidget(self._con_mm(sp), fila + 1, col, 1, ancho)
            self.medidas[clave] = sp
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        self.lbl_medidas_nota = QLabel()
        self.lbl_medidas_nota.setObjectName("notaMedidas")
        self.lbl_medidas_nota.setWordWrap(True)
        g.addWidget(self.lbl_medidas_nota, 10, 0, 1, 2)
        form.addRow(caja)

        # los parámetros del .scad (siempre interiores) quedan como editores ocultos
        for nombre in ("int_ancho", "int_prof", "int_alto_cuerpo", "int_alto_tapa"):
            ed = _Editor(nombre, self.defectos[nombre], self._programar)
            ed.widget.setToolTip(_ayuda(_con_codigo(ayudas.get(nombre, ""), nombre)))
            ed.widget.setVisible(False)
            self.editores[nombre] = ed
            form.addRow(ed.widget)
        self.medidas["ancho"].setToolTip(_ayuda(_con_codigo(ayudas.get("int_ancho", ""), "int_ancho")))
        self.medidas["largo"].setToolTip(_ayuda(_con_codigo(ayudas.get("int_prof", ""), "int_prof")))
        self.medidas["alto"].setToolTip(_ayuda("Alto total: el cuerpo más la tapa (y la segunda tapa si la hay). "
                                               "Al cambiarlo, la tapa queda igual y el cuerpo toma la diferencia."))
        self.medidas["cuerpo"].setToolTip(_ayuda(_con_codigo(
            "Alto del cuerpo, del piso al cierre de la tapa (entre los dos cierres si el case tiene dos tapas).",
            "int_alto_cuerpo")))
        self.medidas["tapa"].setToolTip(_ayuda(_con_codigo(ayudas.get("int_alto_tapa", ""), "int_alto_tapa")))
        try:
            medicion = _settings().value("taller/medicion", "interior")
        except Exception:  # noqa: BLE001
            medicion = "interior"
        self.cmb_medicion.blockSignals(True)
        self.cmb_medicion.setCurrentIndex(1 if medicion == "exterior" else 0)
        self.cmb_medicion.blockSignals(False)
        self._etiquetas_medicion()

    # ---- medidas: interiores o exteriores
    @property
    def medicion(self) -> str:
        """"interior" o "exterior": cómo se muestran y se cargan las medidas."""
        return self.cmb_medicion.currentData()

    def set_medicion(self, medicion: str) -> None:
        self.cmb_medicion.setCurrentIndex(1 if medicion == "exterior" else 0)

    def _medicion_cambiada(self) -> None:
        try:
            _settings().setValue("taller/medicion", self.medicion)
        except Exception:  # noqa: BLE001
            pass
        self._etiquetas_medicion()
        self._mostrar_exterior()

    def _etiquetas_medicion(self) -> None:
        tapas = int(self.params.get("tapas", 1)) == 2
        self.etiquetas_medidas["cuerpo"].setText("Alto de cuerpo" + (" (entre cierres)" if tapas else ""))
        self.etiquetas_medidas["tapa"].setText("Alto de tapa" + (" 1" if tapas else ""))

    def _poner_icono_candado(self) -> None:
        from .barra_3d import _icono
        fijo = self.btn_candado.isChecked()
        self.btn_candado.setIcon(_icono("lock" if fijo else "lock-open"))
        self.btn_candado.setToolTip(
            "Alto fijo: al cambiar el cuerpo o la tapa, el otro se ajusta y el alto total queda igual."
            if fijo else "Alto libre: al cambiar el cuerpo o la tapa, el alto total crece o se achica.")

    def _valores_medidas(self) -> Dict[str, float]:
        """Lo que muestran los cinco campos según la medición elegida."""
        p = self.params
        cuerpo, tapa = float(p["int_alto_cuerpo"]), float(p["int_alto_tapa"])
        interior = {"ancho": float(p["int_ancho"]), "largo": float(p["int_prof"]),
                    "alto": cuerpo + self._alto_tapas(), "cuerpo": cuerpo, "tapa": tapa}
        if self.medicion != "exterior" or self.resultado is None:
            return interior
        v, geo = self.resultado.valores, self.resultado.valores["geo"]
        Z, zc1, zc2 = v["ext_alto"], geo["z_cierre"], geo["z_cierre2"]
        return {"ancho": v["ext_ancho"], "largo": v["ext_prof"], "alto": Z,
                "cuerpo": zc1 - (zc2 if geo.get("dos_tapas") else 0.0), "tapa": Z - zc1}

    def _poner_tapas(self, total_tapas: float) -> bool:
        """Pone la tapa para que las tapas sumen `total_tapas` (con la segunda igual si la copia)."""
        dos = int(self.params.get("tapas", 1)) == 2
        t2 = float(self.params.get("int_alto_tapa2", -1))
        tapa = total_tapas / 2 if dos and t2 < 0 else total_tapas - (t2 if dos else 0.0)
        if tapa <= 0:
            self.lbl_avisos.setText("La tapa no puede quedar sin alto: achicá el cuerpo o soltá el candado del alto.")
            return False
        self.editores["int_alto_tapa"].poner(round(tapa, 2))
        self.params["int_alto_tapa"] = round(tapa, 2)
        return True

    def _medida_editada(self, clave: str, valor: float) -> None:
        if self.resultado is None:
            return
        self._leer_editores()
        antes = self._valores_medidas()
        delta = valor - antes[clave]
        if abs(delta) < 0.005:
            return
        ok = True
        if self.medicion == "exterior" and clave in ("ancho", "largo", "alto"):
            quiero = [antes["ancho"], antes["largo"], antes["alto"]]
            quiero[("ancho", "largo", "alto").index(clave)] = valor
            self.poner_exterior(*quiero)
            return
        if clave in ("ancho", "largo"):
            nombre = "int_ancho" if clave == "ancho" else "int_prof"
            self.editores[nombre].poner(round(float(self.params[nombre]) + delta, 2))
        elif clave == "alto":
            ok = self._poner_cuerpo(float(self.params["int_alto_cuerpo"]) + delta)
        elif clave == "cuerpo":
            total = float(self.params["int_alto_cuerpo"]) + self._alto_tapas()
            cuerpo = float(self.params["int_alto_cuerpo"]) + delta
            if self.btn_candado.isChecked():
                ok = self._poner_tapas(total - cuerpo)
            ok = ok and self._poner_cuerpo(cuerpo)
        elif clave == "tapa":
            total = float(self.params["int_alto_cuerpo"]) + self._alto_tapas()
            ok = self._poner_tapas(self._alto_tapas() + delta * (2 if self._tapa2_copia() else 1))
            if ok and self.btn_candado.isChecked():
                ok = self._poner_cuerpo(total - self._alto_tapas())
        if not ok:
            self._mostrar_exterior()
            return
        self.recalcular()

    def _tapa2_copia(self) -> bool:
        return int(self.params.get("tapas", 1)) == 2 and float(self.params.get("int_alto_tapa2", -1)) < 0

    def _opciones_cara(self) -> List[tuple]:
        """Caras y grupos del forro interior, con los nombres de este case."""
        if self.resultado is not None and self.resultado.valores.get("forro_opciones"):
            return self.resultado.valores["forro_opciones"]
        from ...taller.forro import opciones
        return opciones(False, lambda c: c)

    def _opciones_panel(self) -> List[tuple]:
        from ...taller.materiales import opciones_panel
        return opciones_panel(self.resultado.paneles) if self.resultado is not None else []

    def _alto_tapas(self) -> float:
        """Alto interior de la tapa, más el de la segunda tapa si el case tiene dos."""
        tapa = float(self.editores["int_alto_tapa"].valor())
        if int(self.params.get("tapas", 1)) == 2:
            t2 = float(self.params.get("int_alto_tapa2", -1))
            tapa += tapa if t2 < 0 else t2
        return tapa

    def _poner_cuerpo(self, cuerpo: float) -> bool:
        if cuerpo <= 0:
            self.lbl_avisos.setText("El cuerpo no puede quedar sin alto: agrandá el alto total o achicá la tapa.")
            return False
        self.editores["int_alto_cuerpo"].poner(round(cuerpo, 2))
        self.params["int_alto_cuerpo"] = round(cuerpo, 2)
        return True

    def _mostrar_exterior(self) -> None:
        """Pone en los campos las medidas (interiores o exteriores) del case calculado."""
        if self.resultado is None:
            return
        self._etiquetas_medicion()
        for clave, valor in self._valores_medidas().items():
            sp = self.medidas[clave]
            if not sp.hasFocus():
                sp.blockSignals(True)
                sp.setValue(valor)
                sp.blockSignals(False)
        v = self.resultado.valores
        if self.medicion == "exterior":
            p = self.params
            alto = float(p["int_alto_cuerpo"]) + self._alto_tapas()
            nota = (f"Por dentro: {fmt(p['int_ancho'])} × {fmt(p['int_prof'])} × {fmt(alto)} mm "
                    f"(cuerpo {fmt(p['int_alto_cuerpo'])} + tapa {fmt(p['int_alto_tapa'])}).")
        else:
            nota = (f"Por fuera: {fmt(v['ext_ancho'])} × {fmt(v['ext_prof'])} × {fmt(v['ext_alto'])} mm, "
                    "sin ruedas.")
        self.lbl_medidas_nota.setText(nota)

    def poner_exterior(self, ancho: float, prof: float, alto: float) -> None:
        """Ajusta las medidas interiores para que el case tenga estas medidas exteriores."""
        from ...taller.modelo import interior_para_exterior
        self._leer_editores()
        try:
            interior = interior_para_exterior(self.params, ancho, prof, alto)
        except ValueError as e:
            self.lbl_avisos.setText(str(e))
            self._mostrar_exterior()
            return
        for clave, valor in interior.items():
            self.params[clave] = valor
            if clave in self.editores:
                self.editores[clave].poner(valor)
        self.recalcular()

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
        self.ruta_cambiada.emit(ruta or "")
        self.cmb_estilo.setCurrentIndex(0)
        self._mostrar_estilo()
        self._cargar_en_editores()
        self._deshacer.clear()               # otro proyecto: el historial empieza de cero
        self._rehacer.clear()
        self._foto_actual = None
        self.recalcular()
        self._leer_editores()
        self._foto_guardada = self._foto()   # recién abierto (o nuevo): sin cambios
        self._respaldados.clear()            # la primera vez que se guarde, queda copia de cómo estaba

    # ------------------------------------------------------------ historial
    def _foto(self) -> str:
        datos = {k: v for k, v in self.params.items() if not k.startswith("_")}
        return json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)

    def _registrar_cambio(self) -> None:
        foto = self._foto()
        if self._foto_actual is not None and foto != self._foto_actual:
            self._deshacer.append(self._foto_actual)
            del self._deshacer[:-self.MAX_HISTORIAL]
            self._rehacer.clear()
        if foto != self._foto_actual:
            self._foto_actual = foto
            self._avisar_historial()

    def _describir(self, a: Optional[str], b: Optional[str]) -> str:
        """Qué cambió entre dos fotos, con los nombres en castellano."""
        if not a or not b:
            return ""
        pa, pb = json.loads(a), json.loads(b)
        claves = sorted(k for k in set(pa) | set(pb) if pa.get(k) != pb.get(k))
        if not claves:
            return ""
        nombres = [self._etiquetas.get(k, k) for k in claves]
        return nombres[0] if len(nombres) == 1 else f"{nombres[0]} y {len(nombres) - 1} más"

    def texto_deshacer(self) -> str:
        return self._describir(self._deshacer[-1], self._foto_actual) if self._deshacer else ""

    def texto_rehacer(self) -> str:
        return self._describir(self._foto_actual, self._rehacer[-1]) if self._rehacer else ""

    def _avisar_historial(self) -> None:
        for boton, pila, texto, accion in ((self.btn_deshacer, self._deshacer, self.texto_deshacer(), "Deshacer"),
                                           (self.btn_rehacer, self._rehacer, self.texto_rehacer(), "Rehacer")):
            boton.setEnabled(bool(pila))
            boton.setToolTip(f"{accion}: {texto}" if texto else accion)
        self.historial_cambiado.emit()

    def _confirmar_edicion(self) -> None:
        """Si hay un número a medio escribir, que cuente como cambio antes de deshacer."""
        foco = QApplication.focusWidget()
        while foco is not None and not isinstance(foco, QDoubleSpinBox):
            foco = foco.parentWidget()
        if isinstance(foco, QDoubleSpinBox) and self.isAncestorOf(foco):
            foco.interpretText()
        if self._timer.isActive():
            self._timer.stop()
            self.recalcular()

    def deshacer(self) -> None:
        self._confirmar_edicion()
        if not self._deshacer:
            return
        self._rehacer.append(self._foto_actual)
        self._restaurar(self._deshacer.pop())

    def rehacer(self) -> None:
        self._confirmar_edicion()
        if not self._rehacer:
            return
        self._deshacer.append(self._foto_actual)
        self._restaurar(self._rehacer.pop())

    def _restaurar(self, foto: str) -> None:
        carpeta = self.params.get("_carpeta", "")
        self.params = dict(self.defectos)
        self.params.update(json.loads(foto))
        self.params["_carpeta"] = carpeta
        self._foto_actual = foto
        self._cargar_en_editores()
        self.recalcular()
        self._avisar_historial()

    def recalcular(self) -> None:
        if not self._leer_editores():
            self.lbl_avisos.setText("Hay un dato mal cargado (en rojo): una lista mal escrita, un número que no se entiende o una celda obligatoria vacía.")
            return
        self._registrar_cambio()
        try:
            res = calcular(self.params)
        except Exception as e:   # parámetros fuera de rango que el modelo no admite
            self.lbl_avisos.setText(f"No se pudo calcular con estos parámetros: {e}")
            return
        self.resultado = res
        self._marcar_formulas(res.valores.get("formulas"))
        self._mostrar(res)
        self._mostrar_exterior()
        self.resultado_cambiado.emit(res)

    # campo de Medidas -> parámetro que mueve (el alto total mueve el cuerpo)
    MEDIDA_PARAMETRO = {"ancho": "int_ancho", "largo": "int_prof", "alto": "int_alto_cuerpo",
                        "cuerpo": "int_alto_cuerpo", "tapa": "int_alto_tapa"}

    def _marcar_formulas(self, fx) -> None:
        """Los parámetros que salen de una fórmula muestran el valor calculado y no se editan a mano."""
        calculados = dict(fx.valores) if fx is not None else {}
        expresiones = fx.expresiones if fx is not None else {}
        antes = getattr(self, "_por_formula", {})
        for nombre, valor in calculados.items():
            self.params[nombre] = valor
            ed = self.editores.get(nombre)
            if ed is None:
                continue
            if nombre not in antes:
                antes[nombre] = ed.widget.toolTip()
            ed.poner(valor)
            ed.widget.setEnabled(False)
            ed.widget.setToolTip(_ayuda(f"Calculado con la fórmula: {nombre} = {expresiones.get(nombre, '')}\n"
                                        "Para cambiarlo a mano, borrá esa fórmula (Medidas → Fórmulas)."))
        for nombre in [n for n in antes if n not in calculados]:
            ed = self.editores.get(nombre)
            if ed is not None:
                ed.widget.setEnabled(True)
                ed.widget.setToolTip(antes[nombre])
            del antes[nombre]
        self._por_formula = antes
        if hasattr(self, "medidas"):
            if not hasattr(self, "_ayuda_medidas"):
                self._ayuda_medidas = {c: sp.toolTip() for c, sp in self.medidas.items()}
            for clave, sp in self.medidas.items():
                nombre = self.MEDIDA_PARAMETRO[clave]
                bloqueado = nombre in calculados
                sp.setEnabled(not bloqueado)
                sp.setToolTip(_ayuda(f"Calculado con la fórmula: {nombre} = {expresiones.get(nombre, '')}")
                              if bloqueado else self._ayuda_medidas[clave])
        if getattr(self, "lbl_formulas", None) is not None:
            todo = {**calculados, **(fx.variables if fx is not None else {})}
            self.lbl_formulas.setText(" &nbsp;·&nbsp; ".join(f"<b>{n}</b> = {fmt(v)}" for n, v in todo.items()))

    def _mostrar(self, res: ResultadoTaller) -> None:
        v = res.valores
        n_paneles = len(res.paneles)
        self.lbl_resumen.setText(
            f"<b>Exterior:</b> {fmt(v['ext_ancho'])} × {fmt(v['ext_prof'])} × {fmt(v['ext_alto'])} mm"
            f" &nbsp;·&nbsp; <b>Sistema:</b> {res.info['sistema'][0]}"
            f" &nbsp;·&nbsp; <b>Placa:</b> {v['placa_material']}"
            + (f" (+ {len(otros)} paneles en otra placa)" if (otros := v.get("materiales_paneles") or {}) else "") +
            f" &nbsp;·&nbsp; {n_paneles} paneles, {sum(p.cantidad for p in res.perfiles)} tramos de perfil"
            + (f" &nbsp;·&nbsp; <b>Forro:</b> {len(fo.piezas)} piezas" if (fo := v.get("forro")) is not None and fo.piezas else "")
            + (f" &nbsp;·&nbsp; <b>Peso:</b> {pc.resumen()}" if (pc := v.get("peso")) else ""))
        self._mostrar_peso(v.get("peso"))
        calados: Dict[str, int] = {}
        for c in res.calados:
            calados[c.panel] = calados.get(c.panel, 0) + 1
        mat = {m[0]: f"{m[1]}" for m in res.panelmat}
        self._llenar(self.tabla_paneles, [[p.nombre, fmt(p.ancho), fmt(p.alto), mat.get(p.id, v["placa_material"]),
                                           str(calados.get(p.id, ""))] for p in res.paneles])
        for nombre_t, ops in (("paneles_material", self._opciones_panel), ("forro", self._opciones_cara)):
            ed = self.editores.get(nombre_t)
            if isinstance(ed, _EditorTabla):      # nombres de los paneles (o caras) ya calculados
                ops = ops()
                ed.tabla.blockSignals(True)
                for r in range(ed.tabla.rowCount()):
                    it = ed.tabla.item(r, 0)
                    if it and it.text().strip():
                        it.setText(etiqueta_panel(ref_de_texto(it.text()), ops))
                ed.tabla.blockSignals(False)
        self._llenar(self.tabla_perfiles, [[p.nombre, p.descripcion, fmt(p.largo), str(p.cantidad), p.corte]
                                           for p in res.perfiles])
        self._llenar(self.tabla_herrajes, [[h.nombre, str(h.cantidad), h.detalle, h.ref] for h in res.herrajes])
        self.lbl_avisos.setText("\n".join(f"⚠ {a}" for a in res.avisos))
        interior = v.get("interiores")
        forro = v.get("forro")
        txt_forro = ("<b>Forro:</b> " + "; ".join(res.info.get("forro", []))) if forro is not None and forro.piezas else ""
        if interior is not None:
            self.lbl_interior.setText("<br>".join(interior.resumen + ([txt_forro] if txt_forro else [])))
            self._llenar(self.tabla_interior, interior.elementos)
        elif txt_forro:
            self.lbl_interior.setText(txt_forro)
            self._llenar(self.tabla_interior, [])
        else:
            self.lbl_interior.setText("Sin interior cargado. Agregá equipos, espuma, cajones o un rack "
                                      "en las secciones «Interior» de la izquierda.")
            self._llenar(self.tabla_interior, [])
        hay_interior = interior is not None or bool(txt_forro)
        abrir_interior = hay_interior and not self._habia_interior     # recién cargado: mostrarlo
        self._habia_interior = hay_interior
        self._mostrar_datos(res)
        self.herrajes.set_resultado(res, self.params.get("herrajes_manuales", []), self.params.get("_carpeta", ""))
        self.vista_placas.set_resultado(res)
        self._actualizar_3d()
        if abrir_interior:
            self.panel_vista.ver_interior(True)

    def _mostrar_peso(self, pc) -> None:
        from ...taller import peso as _peso
        if pc is None:
            self.lbl_peso.setText("")
            self._llenar(self.tabla_peso, [])
            return
        kg = _peso._kg
        partes = " &nbsp;·&nbsp; ".join(f"{p}: {kg(t)} kg" for p, t in pc.partes.items())
        txt = f"<b>Case vacío: {kg(pc.vacio)} kg</b>"
        if pc.total > pc.vacio + 0.005:
            txt += f" &nbsp;·&nbsp; <b>Con equipos: {kg(pc.total)} kg</b>"
        txt += f"<br>{partes}"
        if pc.estimado > 0.005:
            txt += (f"<br><span style='color:#a15c00'>{kg(pc.estimado)} kg salen de valores estimados. "
                    "Para el peso real, cargá la densidad de la placa, los g/m de los perfiles y el peso de "
                    "cada herraje en el catálogo (Ctrl+K).</span>")
        if pc.sin_dato:
            txt += ("<br><span style='color:#a15c00'>Sin peso (no suman): "
                    + ", ".join(dict.fromkeys(pc.sin_dato)) + ".</span>")
        self.lbl_peso.setText(txt)
        self._llenar(self.tabla_peso, _peso.filas_tabla(pc))

    def _actualizar_3d(self, *_args) -> None:
        res = self.resultado
        if res is None:
            return
        try:
            from ...taller.geometria import malla_3d
            from ...taller.produccion import colores_placa
            from ...taller.vista import VistaCase
            # la malla se arma con las tapas cerradas; abrirlas o sacar cajones sólo la mueve
            self._vista_case = VistaCase(malla_3d(res), res)
            self.panel_vista.set_vista_case(self._vista_case)
            try:
                self.vista_3d.set_colores_placa(colores_placa({"info": res.info}))
            except Exception:
                self.vista_3d.set_colores_placa({})
            self._aplicar_vista()
        except Exception as e:   # la vista 3D nunca debe impedir ver el resultado
            self.lbl_avisos.setText(self.lbl_avisos.text() + f"\n(No se pudo armar la vista 3D: {e})")

    def _mostrar_datos(self, res: ResultadoTaller) -> None:
        """Barra de datos debajo de la vista 3D: medida, piezas, peso y avisos."""
        v = res.valores
        self.datos["medida"].setText(f"{fmt(v['ext_ancho'])} × {fmt(v['ext_prof'])} × {fmt(v['ext_alto'])} mm")
        self.datos["paneles"].setText(str(len(res.paneles)))
        self.datos["perfiles"].setText(f"{sum(p.cantidad for p in res.perfiles)} tramos")
        self.datos["herrajes"].setText(str(sum(h.cantidad for h in res.herrajes if isinstance(h.cantidad, (int, float)))))
        peso = v.get("peso")              # PesoCase (cuando está el cálculo de peso real)
        peso = getattr(peso, "total", peso)
        self.datos["peso"].setText(f"{fmt(round(float(peso), 1))} kg" if isinstance(peso, (int, float)) and peso else "–")
        self.datos["peso"].parentWidget().setVisible(self.datos["peso"].text() != "–")
        n = len(res.avisos)
        self.btn_avisos.setText(f"⚠ {n} para revisar" if n else "✓ Sin avisos")
        self.btn_avisos.setProperty("hay", bool(n))
        self.btn_avisos.style().unpolish(self.btn_avisos)
        self.btn_avisos.style().polish(self.btn_avisos)

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
    def asistente(self) -> bool:
        """Case nuevo paso a paso. Devuelve True si se terminó."""
        from .asistente import AsistenteCase
        dlg = AsistenteCase(self)
        if dlg.exec() and dlg.params is not None:
            self.set_params(dlg.params)
            return True
        return False

    def biblioteca(self) -> None:
        from .biblioteca_widget import BibliotecaDialog
        BibliotecaDialog(self).exec()

    def editar_catalogo(self, categoria: str = "") -> None:
        from .catalogo_widget import CatalogoDialog
        dlg = CatalogoDialog(self, categoria)
        dlg.exec()
        if dlg.cambiado:
            self.catalogo_cambiado()

    def catalogo_cambiado(self) -> None:
        """Se editó el catálogo: listas de herrajes y placas al día y el case recalculado."""
        for nombre, ed in self.editores.items():
            if isinstance(ed, _Editor) and isinstance(ed.widget, QComboBox) and nombre in REF_CATEGORIAS:
                valor = ed.valor()
                w = ed.widget
                w.blockSignals(True)
                w.clear()
                _llenar_combo_catalogo(w, REF_CATEGORIAS[nombre], vacio=True)
                w.blockSignals(False)
                ed.poner(valor)
            elif isinstance(ed, _EditorTabla):
                ed.refrescar_etiquetas()
        self.herrajes.catalogo_cambiado()
        self.recalcular()

        self.set_params({})
    def hay_cambios(self) -> bool:
        """True si el case cambió desde que se abrió, se guardó o se empezó."""
        self._leer_editores()
        return self._foto() != getattr(self, "_foto_guardada", None)

    def confirmar_cambios(self, titulo: str, antes_de: str) -> bool:
        """Si hay cambios sin guardar pregunta Guardar/Descartar/Cancelar. False = canceló."""
        if not self.hay_cambios():
            return True
        r = QMessageBox.question(
            self, titulo, f"«{self.lbl_archivo.text()}» tiene cambios sin guardar.\n¿Guardarlos antes de {antes_de}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            self.guardar(self.ruta)
            if self.hay_cambios():      # canceló el diálogo de guardar
                return False
        return True

    def nuevo(self, preguntar: bool = True) -> bool:
        """Empieza un case con las medidas por defecto; si hay cambios sin guardar, pregunta antes."""
        if preguntar and not self.confirmar_cambios("Case nuevo", "empezar uno nuevo"):
            return False
        self.set_params({})
        self.case_nuevo.emit()
        return True

    def crear(self, id_estilo: Optional[str] = None, plantilla: Optional[str] = None, nombre: str = "",
              carpeta: Optional[str] = None) -> bool:
        """Proyecto nuevo desde la pantalla de inicio: con un estilo sobre las medidas por defecto,
        o copia de un case guardado (`plantilla`). Con nombre se guarda enseguida en la carpeta de
        cases (o en `carpeta`), sin pisar otro archivo."""
        if plantilla:
            try:
                params = leer_proyecto(plantilla)
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, "Proyecto nuevo", f"No se pudo leer {os.path.basename(plantilla)}:\n{e}")
                return False
            params["_carpeta"] = os.path.dirname(os.path.abspath(plantilla))   # logos y archivos a mano
            self.set_params(params)
        else:
            self.set_params({})
            if id_estilo:
                self.aplicar_estilo(id_estilo)
        self._foto_guardada = self._foto()        # recién empezado: sin cambios
        if nombre:
            from ...taller.proyectos import nombre_libre, nombre_valido
            from .proyectos_widget import carpeta_proyectos
            carpeta = carpeta or carpeta_proyectos()
            try:
                os.makedirs(carpeta, exist_ok=True)
                ruta = nombre_libre(carpeta, nombre_valido(nombre))
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Proyecto nuevo", f"No se pudo guardar «{nombre}»: {e}\n"
                                    "El case quedó abierto sin guardar (Ctrl+S).")
                return True
            self.guardar(ruta)
        else:
            self.case_nuevo.emit()
        return True

    def _es_el_abierto(self, ruta: Optional[str]) -> bool:
        return bool(ruta and self.ruta) and \
            os.path.normcase(os.path.abspath(ruta)) == os.path.normcase(os.path.abspath(self.ruta))

    def abrir(self, ruta: Optional[str] = None, preguntar: bool = True) -> bool:
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto del taller", "",
                                                  "Proyecto OpenSCAD (*.scad)")
        if not ruta:
            return False
        if preguntar and not self._es_el_abierto(ruta) and not self.confirmar_cambios("Abrir case", "abrir otro"):
            return False
        try:
            self.set_params(leer_proyecto(ruta), ruta)
        except Exception as e:
            QMessageBox.critical(self, "Abrir proyecto", f"No se pudo leer {os.path.basename(ruta)}:\n{e}")
            return False
        return True

    def cargar_con_cambios(self, scad: str, ruta: Optional[str], carpeta: str = "") -> None:
        """Pone en la ventana el contenido de `scad` (una versión anterior o una copia de
        recuperación) como cambios sin guardar del case `ruta`: hasta que se guarde, el
        archivo queda como estaba."""
        params = leer_proyecto(scad)
        if ruta and not os.path.isfile(ruta):
            carpeta, ruta = carpeta or os.path.dirname(os.path.abspath(ruta)), None
        self.set_params(params, ruta)
        if not ruta and carpeta:
            self.params["_carpeta"] = carpeta
            self.recalcular()
        self._foto_guardada = None

    def texto_proyecto(self) -> str:
        self._leer_editores()
        titulo = os.path.splitext(os.path.basename(self.ruta))[0] if self.ruta else ""
        return escribir_proyecto(self.params, self.defectos, titulo)

    def guardar(self, ruta: Optional[str] = None, automatico: bool = False) -> bool:
        """Escribe el .scad. Antes, lo que había en el archivo queda como versión fechada
        (ver taller/versiones.py). `automatico`: sin diálogos (el autoguardado)."""
        if not ruta:
            if automatico:
                return False
            ruta, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto del taller",
                                                  self.ruta or self._ruta_sugerida(), "Proyecto OpenSCAD (*.scad)")
        if not ruta:
            return False
        if not ruta.lower().endswith(".scad"):
            ruta += ".scad"
        from ...taller import versiones
        carpeta_antes = self.params.get("_carpeta", "")
        self._mudar_logos(os.path.dirname(os.path.abspath(ruta)))
        texto = self.texto_proyecto()
        clave = os.path.normcase(os.path.abspath(ruta))
        try:
            versiones.respaldar(ruta, forzar=clave not in self._respaldados)
            tmp = ruta + ".guardando"
            with open(tmp, "w", encoding="utf-8") as f:     # si se corta a la mitad, el case no queda roto
                f.write(texto)
            os.replace(tmp, ruta)
        except OSError as e:
            self.params["_carpeta"] = carpeta_antes
            if not automatico:
                QMessageBox.critical(self, "Guardar case", f"No se pudo guardar {os.path.basename(ruta)}:\n{e}")
            return False
        self._respaldados.add(clave)
        self.herrajes.carpeta = self.params["_carpeta"]
        self.ruta = ruta
        self.lbl_archivo.setText(os.path.basename(ruta))
        self._foto_guardada = self._foto()
        self.ruta_cambiada.emit(ruta)
        self.guardado.emit(automatico)
        return True

    @staticmethod
    def _ruta_sugerida() -> str:
        """Un case nuevo se guarda por defecto en la carpeta de cases (la de «Mis cases»)."""
        from ...taller.proyectos import nombre_libre
        from .proyectos_widget import carpeta_proyectos
        carpeta = carpeta_proyectos()
        try:
            os.makedirs(carpeta, exist_ok=True)
        except OSError:
            return "mi_case.scad"
        return nombre_libre(carpeta, "mi_case")

    def renombrado(self, vieja: str, nueva: str) -> None:
        """El archivo abierto cambió de nombre desde «Mis cases»."""
        if self.ruta and os.path.normcase(os.path.abspath(self.ruta)) == os.path.normcase(os.path.abspath(vieja)):
            self.ruta = nueva
            self.lbl_archivo.setText(os.path.basename(nueva))
            self.ruta_cambiada.emit(nueva)

    def borrado(self, ruta: str) -> None:
        """El archivo abierto se mandó a la papelera: el case queda en la ventana, sin guardar."""
        if self.ruta and os.path.normcase(os.path.abspath(self.ruta)) == os.path.normcase(os.path.abspath(ruta)):
            self.ruta = None
            self.lbl_archivo.setText("Proyecto nuevo (el archivo se borró)")
            self.ruta_cambiada.emit("")

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
            from .placas_widget import girar_permitido
            paq = exportar(self.resultado, carpeta, rotar=girar_permitido())
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Paquete del taller", f"No se pudo generar el paquete:\n{e}")
            return None
        QApplication.restoreOverrideCursor()
        avisos = ("\n\nAvisos:\n" + "\n".join(f"• {a}" for a in paq.avisos)) if paq.avisos else ""
        QMessageBox.information(self, "Paquete del taller",
                                f"Se generaron {len(paq.archivos)} archivos en:\n{carpeta}{avisos}")
        return paq

    def exportar_planos(self, ruta: Optional[str] = None) -> Optional[str]:
        """Sólo planos.pdf (resumen, vistas 3D, cada pieza acotada, placas, perfiles y materiales),
        sin el resto del paquete."""
        import shutil
        import tempfile
        from ...taller.produccion import exportar
        from .placas_widget import girar_permitido
        if self.resultado is None:
            return None
        nombre = os.path.splitext(os.path.basename(self.ruta))[0] if self.ruta else "case"
        if not ruta:
            ruta, _ = QFileDialog.getSaveFileName(self, "Exportar planos", f"Planos - {nombre}.pdf", "PDF (*.pdf)")
            if not ruta:
                return None
            if not ruta.lower().endswith(".pdf"):
                ruta += ".pdf"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                exportar(self.resultado, os.path.join(tmp, f"salida_{nombre}"), rotar=girar_permitido(), step=False)
                shutil.copyfile(os.path.join(tmp, f"salida_{nombre}", "planos.pdf"), ruta)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Exportar planos", f"No se pudieron generar los planos:\n{e}")
            return None
        QApplication.restoreOverrideCursor()
        if self.isVisible():
            QMessageBox.information(self, "Exportar planos", f"Se guardaron los planos en:\n{ruta}")
        return ruta

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
