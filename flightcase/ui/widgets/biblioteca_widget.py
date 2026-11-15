"""Ventana de la biblioteca de equipos: cargar, editar, buscar, importar/exportar y pasar al case."""

from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...taller import biblioteca as B

COLUMNAS = [("Nombre", "nombre"), ("Categoría", "categoria"), ("Ancho", "ancho"), ("Fondo", "fondo"),
            ("Alto", "alto"), ("Peso kg", "peso"), ("U rack", "u"), ("Forma en la espuma", "forma"),
            ("Radio", "radio"), ("Dedos", "dedos"), ("Sobresale", "sobresale"), ("Nota", "nota")]
AYUDAS = {
    "ancho": "De costado a costado (mm). En un equipo de rack, vacío = 482,6 (19\").",
    "fondo": "De adelante hacia atrás (mm).",
    "alto": "Alto (mm). En un equipo de rack, vacío = U × 44,45.",
    "u": "Unidades de rack. 0 o vacío = no es de rack.",
    "forma": "Calado en la espuma: vacío = rectángulo, «redondo», o la ruta de un .dxf / .svg con el contorno.",
    "radio": "Esquinas del calado en mm. Vacío = el radio general del case.",
    "dedos": "Huecos para sacar el equipo: 0, 1 (adelante) o 2 (los dos lados largos).",
    "sobresale": "Rack: perillas o manijas que sobresalen adelante de las orejas (mm).",
}


def _texto(campo: str, valor) -> str:
    if campo == "radio" and valor == -1:
        return ""
    if campo in ("u", "dedos", "ancho", "alto", "sobresale") and valor == 0:   # vacío = sin dato / el de rack
        return ""
    if isinstance(valor, float):
        return f"{valor:.2f}".rstrip("0").rstrip(".")
    return str(valor)


class BibliotecaDialog(QDialog):
    """Lista editable de los equipos propios. Con `agregar` muestra el botón para pasar los
    elegidos al case (a la espuma o al rack)."""

    def __init__(self, parent: Optional[QWidget] = None, agregar: Optional[Callable[[List[B.EquipoBiblio]], None]] = None,
                 texto_agregar: str = "Agregar al case") -> None:
        super().__init__(parent)
        self.setWindowTitle("Biblioteca de equipos")
        self.resize(980, 520)
        self._agregar = agregar
        self.equipos: List[B.EquipoBiblio] = B.cargar()
        raiz = QVBoxLayout(self)
        ayuda = QLabel("Tus equipos con sus medidas, para usarlos en cualquier case. Los cambios se guardan solos. "
                       "Doble clic en una celda para editarla.")
        ayuda.setWordWrap(True)
        raiz.addWidget(ayuda)
        fila = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar por nombre o categoría…")
        self.buscar.textChanged.connect(self._filtrar)
        fila.addWidget(self.buscar, 1)
        raiz.addLayout(fila)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels([t for t, _ in COLUMNAS])
        for c, (_, campo) in enumerate(COLUMNAS):
            if campo in AYUDAS:
                self.tabla.horizontalHeaderItem(c).setToolTip(AYUDAS[campo])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.cellChanged.connect(self._celda_cambiada)
        self.tabla.itemSelectionChanged.connect(self._seleccion)
        raiz.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        for texto, slot in (("+ Nuevo", self.nuevo), ("− Quitar", self.quitar),
                            ("Importar planilla…", self.importar), ("Exportar planilla…", self.exportar)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            botones.addWidget(b)
        botones.addStretch(1)
        self.btn_agregar = QPushButton(texto_agregar)
        self.btn_agregar.setProperty("accent", "1")
        self.btn_agregar.clicked.connect(self._agregar_elegidos)
        self.btn_agregar.setVisible(agregar is not None)
        self.btn_agregar.setEnabled(False)
        botones.addWidget(self.btn_agregar)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.accept)
        botones.addWidget(cerrar)
        raiz.addLayout(botones)
        self.lbl_estado = QLabel()
        self.lbl_estado.setStyleSheet("color:#bbbbbb")
        raiz.addWidget(self.lbl_estado)
        self._llenar()

    # ------------------------------------------------------------------ tabla
    def _llenar(self) -> None:
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        for e in self.equipos:
            r = self.tabla.rowCount()
            self.tabla.insertRow(r)
            for c, (_, campo) in enumerate(COLUMNAS):
                item = QTableWidgetItem(_texto(campo, getattr(e, campo)))
                if c >= 2 and campo not in ("forma", "nota"):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabla.setItem(r, c, item)
        self.tabla.blockSignals(False)
        self.tabla.resizeColumnToContents(0)
        self.tabla.setColumnWidth(0, min(max(self.tabla.columnWidth(0), 160), 320))
        self._filtrar()
        self.lbl_estado.setText(f"{len(self.equipos)} equipos en la biblioteca." if self.equipos else
                                "La biblioteca está vacía: agregá equipos con «+ Nuevo», importá una planilla o "
                                "usá «Guardar en la biblioteca» desde las tablas de equipos del case.")

    def _filtrar(self, *_args) -> None:
        t = self.buscar.text().strip().lower()
        for r, e in enumerate(self.equipos):
            self.tabla.setRowHidden(r, bool(t) and t not in e.nombre.lower() and t not in e.categoria.lower())

    def _celda_cambiada(self, r: int, c: int) -> None:
        campo = COLUMNAS[c][1]
        item = self.tabla.item(r, c)
        texto = item.text().strip() if item else ""
        d = vars(self.equipos[r]).copy()
        defecto = {"radio": -1, "u": 0, "dedos": 0}.get(campo, 0)
        d[campo] = texto if texto or campo in ("forma", "nota", "categoria") else defecto
        try:
            self.equipos[r] = B.desde_dict(d)
        except ValueError:
            self.tabla.blockSignals(True)
            item.setText(_texto(campo, getattr(self.equipos[r], campo)))
            self.tabla.blockSignals(False)
            self.lbl_estado.setText(f"«{texto}» no es un valor válido para {COLUMNAS[c][0]}.")
            return
        self._guardar()

    def _seleccion(self) -> None:
        self.btn_agregar.setEnabled(bool(self.elegidos()))

    def elegidos(self) -> List[B.EquipoBiblio]:
        filas = sorted({i.row() for i in self.tabla.selectedIndexes()})
        return [self.equipos[r] for r in filas if 0 <= r < len(self.equipos)]

    def _guardar(self) -> None:
        B.guardar(self.equipos)

    # ---------------------------------------------------------------- acciones
    def nuevo(self) -> None:
        nombres = {e.nombre for e in self.equipos}
        n, nombre = 1, "Equipo nuevo"
        while nombre in nombres:
            n += 1
            nombre = f"Equipo nuevo {n}"
        self.equipos.append(B.EquipoBiblio(nombre))
        self._guardar()
        self._llenar()
        r = len(self.equipos) - 1
        self.tabla.setCurrentCell(r, 0)
        self.tabla.editItem(self.tabla.item(r, 0))

    def quitar(self) -> None:
        filas = sorted({i.row() for i in self.tabla.selectedIndexes()}, reverse=True)
        for r in filas:
            del self.equipos[r]
        if filas:
            self._guardar()
            self._llenar()

    def sumar(self, nuevos: List[B.EquipoBiblio]) -> List[str]:
        reemplazados = B.sumar(self.equipos, nuevos)
        self._guardar()
        self.equipos = B.cargar()
        self._llenar()
        return reemplazados

    def importar(self, ruta: Optional[str] = None) -> None:
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Importar equipos", "", "Planilla (*.csv);;Todos (*)")
        if not ruta:
            return
        try:
            with open(ruta, encoding="utf-8-sig") as f:
                nuevos = B.desde_csv(f.read())
        except (OSError, ValueError, UnicodeDecodeError) as e:
            QMessageBox.warning(self, "Importar equipos", f"No se pudo leer la planilla:\n{e}")
            return
        reemplazados = self.sumar(nuevos)
        extra = f" ({len(reemplazados)} ya estaban y se actualizaron)" if reemplazados else ""
        self.lbl_estado.setText(f"Se importaron {len(nuevos)} equipos{extra}.")

    def exportar(self, ruta: Optional[str] = None) -> None:
        if not ruta:
            ruta, _ = QFileDialog.getSaveFileName(self, "Exportar equipos", "equipos.csv", "Planilla (*.csv)")
        if not ruta:
            return
        with open(ruta, "w", encoding="utf-8-sig", newline="") as f:   # con BOM: Excel respeta los acentos
            f.write(B.a_csv(self.equipos))
        self.lbl_estado.setText(f"Se exportaron {len(self.equipos)} equipos a {ruta}.")

    def _agregar_elegidos(self) -> None:
        elegidos = self.elegidos()
        if elegidos and self._agregar is not None:
            self._agregar(elegidos)
            self.lbl_estado.setText(f"Se agregaron {len(elegidos)} equipos al case.")
