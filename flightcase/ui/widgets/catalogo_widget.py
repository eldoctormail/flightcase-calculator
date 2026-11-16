"""Ventana del catálogo de herrajes, perfiles y placas: editar las medidas, cargar los artículos
de tus proveedores y pasar todo a y desde una planilla CSV."""

from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...taller import catalogo as C

TODAS = ""
ORIGEN_TEXTO = {"incluido": "de la app", "modificado": "cambiado", "propio": "tuyo"}
ORIGEN_COLOR = {"modificado": "#c77d1a", "propio": "#2f7fd8"}


class _DelegadoOpciones(QStyledItemDelegate):
    """Celda con opciones fijas (tipo de cierre, de manija, de rueda)."""

    def __init__(self, parent, opciones_de) -> None:
        super().__init__(parent)
        self.opciones_de = opciones_de      # función: columna -> tupla de opciones o None

    def createEditor(self, parent, option, index):  # noqa: N802 (nombre de Qt)
        ops = self.opciones_de(index.column())
        if not ops:
            return super().createEditor(parent, option, index)
        w = QComboBox(parent)
        w.addItems([""] + list(ops))
        return w

    def setEditorData(self, editor, index):  # noqa: N802
        if isinstance(editor, QComboBox):
            editor.setCurrentText(index.data() or "")
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):  # noqa: N802
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentText())
        else:
            super().setModelData(editor, model, index)


class CatalogoDialog(QDialog):
    """Catálogo editable. Los cambios se guardan solos en la carpeta de datos del usuario;
    `cambiado` queda en True si se tocó algo (para recalcular el case al cerrar)."""

    def __init__(self, parent: Optional[QWidget] = None, categoria: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Catálogo de herrajes y placas")
        self.resize(1180, 620)
        self.cambiado = False
        self.filas: List[Dict[str, Any]] = copy.deepcopy(C.filas_actuales())
        self.categoria = categoria if categoria in C.NOMBRES else TODAS
        self._columnas: List[tuple] = []        # (clase, clave, título, tipo)
        self._indices: List[int] = []           # fila de la tabla -> índice en self.filas

        raiz = QVBoxLayout(self)
        ayuda = QLabel("Cargá las medidas reales de los herrajes y placas que comprás. Lo que cambies acá lo usan "
                       "todas las listas del taller (placa, ruedas, cierres, material por panel…). Los cambios se "
                       "guardan solos; lo que viene con la app no se pisa y se puede restaurar.")
        ayuda.setWordWrap(True)
        raiz.addWidget(ayuda)

        divisor = QSplitter(Qt.Horizontal)
        self.lista_cat = QListWidget()
        self.lista_cat.setMaximumWidth(230)
        self.lista_cat.currentRowChanged.connect(self._cat_elegida)
        divisor.addWidget(self.lista_cat)

        derecha = QWidget()
        dl = QVBoxLayout(derecha)
        dl.setContentsMargins(0, 0, 0, 0)
        fila = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar por ref, nombre, proveedor o nota…")
        self.buscar.textChanged.connect(self._filtrar)
        fila.addWidget(self.buscar, 1)
        self.chk_mios = QCheckBox("Sólo los míos")
        self.chk_mios.setToolTip("Mostrar sólo los artículos que cargaste o cambiaste")
        self.chk_mios.toggled.connect(self._filtrar)
        fila.addWidget(self.chk_mios)
        dl.addLayout(fila)

        self.tabla = QTableWidget(0, 0)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.cellChanged.connect(self._celda_cambiada)
        self._delegado = _DelegadoOpciones(self.tabla, self._opciones_columna)
        self.tabla.setItemDelegate(self._delegado)
        dl.addWidget(self.tabla, 1)
        divisor.addWidget(derecha)
        divisor.setStretchFactor(1, 1)
        raiz.addWidget(divisor, 1)

        botones = QHBoxLayout()
        for texto, slot, ayuda_b in (
                ("+ Nuevo", self.nuevo, "Artículo nuevo en la categoría elegida"),
                ("Duplicar", self.duplicar, "Copia del artículo elegido, para cargar uno parecido de otro proveedor"),
                ("− Quitar", self.quitar, "Saca los artículos elegidos de las listas"),
                ("Restaurar original", self.restaurar, "Vuelve los artículos elegidos a como vienen con la app"),
                ("Recuperar quitados…", self.recuperar_quitados, "Vuelve a poner los artículos de la app que quitaste"),
                ("Importar planilla…", self.importar, "Agrega o actualiza artículos desde un CSV (por ref)"),
                ("Exportar planilla…", self.exportar, "Guarda en un CSV los artículos que se ven en la tabla")):
            b = QPushButton(texto)
            b.setToolTip(ayuda_b)
            b.clicked.connect(lambda _=False, s=slot: s())
            botones.addWidget(b)
        botones.addStretch(1)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.accept)
        botones.addWidget(cerrar)
        raiz.addLayout(botones)
        self.lbl_estado = QLabel()
        self.lbl_estado.setStyleSheet("color:#999999")
        self.lbl_estado.setWordWrap(True)
        raiz.addWidget(self.lbl_estado)

        self._llenar_categorias()
        self._llenar()

    # -------------------------------------------------------------- categorías
    def _llenar_categorias(self) -> None:
        cuenta: Dict[str, int] = {}
        for f in self.filas:
            cuenta[f["categoria"]] = cuenta.get(f["categoria"], 0) + 1
        self.lista_cat.blockSignals(True)
        self.lista_cat.clear()
        it = QListWidgetItem(f"Todas ({len(self.filas)})")
        it.setData(Qt.UserRole, TODAS)
        self.lista_cat.addItem(it)
        for cat, nombre, _m in C.CATEGORIAS:
            it = QListWidgetItem(f"{nombre} ({cuenta.get(cat, 0)})")
            it.setData(Qt.UserRole, cat)
            self.lista_cat.addItem(it)
        for cat in sorted(set(cuenta) - set(C.NOMBRES)):
            it = QListWidgetItem(f"{cat} ({cuenta[cat]})")
            it.setData(Qt.UserRole, cat)
            self.lista_cat.addItem(it)
        for i in range(self.lista_cat.count()):
            if self.lista_cat.item(i).data(Qt.UserRole) == self.categoria:
                self.lista_cat.setCurrentRow(i)
        self.lista_cat.blockSignals(False)

    def _cat_elegida(self, i: int) -> None:
        it = self.lista_cat.item(i)
        self.categoria = it.data(Qt.UserRole) if it else TODAS
        self._llenar()

    # ------------------------------------------------------------------ tabla
    def _armar_columnas(self, filas: List[Dict[str, Any]]) -> None:
        cols: List[tuple] = [("fijo", "ref", "Ref", None)]
        if self.categoria == TODAS:
            cols.append(("fijo", "categoria", "Categoría", None))
        cols.append(("fijo", "nombre", "Nombre", None))
        if self.categoria == TODAS:
            cols.append(("resumen", "", "Medidas", None))
        else:
            titulos = {k: (t, tipo, a) for k, t, tipo, a in C.MEDIDAS.get(self.categoria, [])}
            for k in C.claves_medidas(filas, self.categoria):
                t, tipo, _a = titulos.get(k, (k, None, ""))
                cols.append(("dato", k, t, tipo))
        cols += [("fijo", "proveedor", "Proveedor", None), ("fijo", "verificado", "Verif.", None),
                 ("fijo", "nota", "Nota", None), ("origen", "", "Origen", None)]
        self._columnas = cols
        self.tabla.setColumnCount(len(cols))
        self.tabla.setHorizontalHeaderLabels([c[2] for c in cols])
        ayudas = {k: a for k, _t, _tipo, a in C.MEDIDAS.get(self.categoria, [])}
        ayudas_fijas = {"ref": "Código del artículo (el de tu proveedor). Es lo que queda guardado en el case.",
                        "verificado": "Tildado = medidas confirmadas con la pieza. Sin tildar, el taller avisa "
                                      "que hay que medirla antes de cortar.",
                        "proveedor": "Dónde lo comprás (sólo para vos)."}
        for c, (clase, clave, _t, tipo) in enumerate(cols):
            texto = ayudas.get(clave, "") if clase == "dato" else ayudas_fijas.get(clave, "")
            if clase == "resumen":
                texto = "Elegí una categoría a la izquierda para editar las medidas."
            if isinstance(tipo, tuple):
                texto += f"\nOpciones: {', '.join(tipo)}."
            elif tipo == "par":
                texto += "\nDos medidas: 100 x 85."
            self.tabla.horizontalHeaderItem(c).setToolTip(texto.strip())

    def _llenar(self) -> None:
        if self.categoria == TODAS:
            self._indices = list(range(len(self.filas)))
        else:
            self._indices = [i for i, f in enumerate(self.filas) if f["categoria"] == self.categoria]
        self._armar_columnas([self.filas[i] for i in self._indices])
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(0)
        for r, i in enumerate(self._indices):
            self.tabla.insertRow(r)
            self._poner_fila(r, self.filas[i])
        self.tabla.blockSignals(False)
        self.tabla.resizeColumnsToContents()
        for c, (clase, clave, _t, _tipo) in enumerate(self._columnas):
            if clave == "nombre" or clase == "resumen":
                self.tabla.setColumnWidth(c, min(max(self.tabla.columnWidth(c), 160), 380))
        self._filtrar()
        self._estado()

    def _poner_fila(self, r: int, f: Dict[str, Any]) -> None:
        origen = f.get("origen", "propio")
        color = QBrush(QColor(ORIGEN_COLOR[origen])) if origen in ORIGEN_COLOR else None
        for c, (clase, clave, _t, tipo) in enumerate(self._columnas):
            if clase == "fijo" and clave == "verificado":
                it = QTableWidgetItem("")
                it.setFlags((it.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                it.setCheckState(Qt.Checked if f.get("verificado", True) else Qt.Unchecked)
            elif clase == "fijo" and clave == "categoria":
                it = QTableWidgetItem(C.NOMBRES.get(f["categoria"], f["categoria"]))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            elif clase == "fijo":
                it = QTableWidgetItem(str(f.get(clave, "") or ""))
            elif clase == "dato":
                v = f.get("datos", {}).get(clave)
                it = QTableWidgetItem(C.texto_valor(v))
                if tipo in ("num", "par") or (tipo is None and isinstance(v, (int, float, list))):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            elif clase == "resumen":
                it = QTableWidgetItem(C.resumen_datos(f))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            else:
                it = QTableWidgetItem(ORIGEN_TEXTO.get(origen, origen))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if color:
                    it.setForeground(color)
            if clave == "ref" and color:
                it.setForeground(color)
            self.tabla.setItem(r, c, it)

    def _opciones_columna(self, c: int):
        if 0 <= c < len(self._columnas):
            tipo = self._columnas[c][3]
            return tipo if isinstance(tipo, tuple) else None
        return None

    def _filtrar(self, *_args) -> None:
        t = self.buscar.text().strip().lower()
        mios = self.chk_mios.isChecked()
        for r, i in enumerate(self._indices):
            f = self.filas[i]
            texto = " ".join(str(f.get(k, "")) for k in ("ref", "nombre", "proveedor", "nota")).lower()
            oculto = (bool(t) and t not in texto) or (mios and f.get("origen") == "incluido")
            self.tabla.setRowHidden(r, oculto)

    def _estado(self, texto: str = "") -> None:
        mios = sum(1 for f in self.filas if f.get("origen") in ("propio", "modificado"))
        base = f"{len(self.filas)} artículos, {mios} tuyos o cambiados."
        self.lbl_estado.setText(f"{texto}  ·  {base}" if texto else base)

    def _celda_cambiada(self, r: int, c: int) -> None:
        if not (0 <= r < len(self._indices)):
            return
        i = self._indices[r]
        f = copy.deepcopy(self.filas[i])
        clase, clave, titulo, tipo = self._columnas[c]
        it = self.tabla.item(r, c)
        texto = it.text().strip() if it else ""
        error = ""
        if clase == "fijo" and clave == "verificado":
            f["verificado"] = it.checkState() == Qt.Checked
        elif clase == "fijo" and clave == "ref":
            if not texto:
                error = "La ref no puede quedar vacía."
            elif any(g["ref"] == texto for j, g in enumerate(self.filas) if j != i):
                error = f"Ya hay un artículo con la ref {texto}."
            else:
                f["ref"] = texto
        elif clase == "fijo":
            if clave == "nombre" and not texto:
                error = "El nombre no puede quedar vacío."
            elif texto:
                f[clave] = texto
            else:
                f.pop(clave, None)
        elif clase == "dato":
            try:
                v = C.valor_texto(texto, tipo)
            except ValueError as e:
                error = f"{titulo}: {e}."
            else:
                if v is None:
                    f["datos"].pop(clave, None)
                else:
                    f["datos"][clave] = v
        if error:
            self.tabla.blockSignals(True)
            self._poner_fila(r, self.filas[i])
            self.tabla.blockSignals(False)
            self._estado(error)
            return
        self.filas[i] = f
        self._guardar([f])
        self.tabla.blockSignals(True)
        self._poner_fila(r, f)
        self.tabla.blockSignals(False)
        self._estado()

    def _guardar(self, tocadas: Optional[List[Dict[str, Any]]] = None) -> None:
        C.marcar_origen(tocadas if tocadas is not None else self.filas)
        C.guardar(self.filas)
        self.cambiado = True

    def _elegidas(self) -> List[int]:
        return [self._indices[r] for r in sorted({x.row() for x in self.tabla.selectedIndexes()})
                if 0 <= r < len(self._indices) and not self.tabla.isRowHidden(r)]

    def _seleccionar(self, i: int, columna: str = "ref") -> None:
        if i in self._indices:
            r = self._indices.index(i)
            c = next((k for k, col in enumerate(self._columnas) if col[1] == columna), 0)
            self.tabla.setCurrentCell(r, c)
            self.tabla.scrollToItem(self.tabla.item(r, c))

    def _rehacer(self, elegir: Optional[int] = None) -> None:
        self._llenar_categorias()
        self._llenar()
        if elegir is not None:
            self._seleccionar(elegir)

    # ---------------------------------------------------------------- acciones
    def nuevo(self, categoria: Optional[str] = None) -> Optional[Dict[str, Any]]:
        cat = categoria or self.categoria
        if not cat:
            nombres = [n for _c, n, _m in C.CATEGORIAS]
            elegido, ok = QInputDialog.getItem(self, "Artículo nuevo", "Categoría:", nombres, 0, False)
            if not ok:
                return None
            cat = next(c for c, n, _m in C.CATEGORIAS if n == elegido)
        f = {"ref": C.ref_libre(self.filas, "NUEVO"), "categoria": cat,
             "nombre": f"{C.NOMBRES.get(cat, cat).rstrip('s')} nuevo", "datos": {}, "verificado": True,
             "origen": "propio"}
        if cat == "placa":
            f["datos"] = {"esp": 9, "largo": 2440, "ancho": 1220}
            f["nombre"] = "Placa nueva 9 mm"
        self.filas.append(f)
        self._guardar([f])
        self._rehacer(len(self.filas) - 1)
        if self.tabla.currentItem() is not None:
            self.tabla.editItem(self.tabla.currentItem())
        self._estado("Escribí la ref de tu proveedor y las medidas.")
        return f

    def duplicar(self) -> None:
        elegidas = self._elegidas()
        if not elegidas:
            self._estado("Elegí el artículo que querés duplicar.")
            return
        ultimo = None
        for i in elegidas:
            f = copy.deepcopy(self.filas[i])
            f["ref"] = C.ref_libre(self.filas, f["ref"])
            f["origen"] = "propio"
            self.filas.append(f)
            ultimo = len(self.filas) - 1
        self._guardar(self.filas[-len(elegidas):])
        self._rehacer(ultimo)
        self._estado("Cambiá la ref y las medidas de la copia.")

    def quitar(self) -> None:
        elegidas = self._elegidas()
        if not elegidas:
            return
        de_la_app = sum(1 for i in elegidas if self.filas[i].get("origen") != "propio")
        if len(elegidas) > 1 or de_la_app == 0:
            nombres = ", ".join(self.filas[i]["ref"] for i in elegidas[:6]) + ("…" if len(elegidas) > 6 else "")
            if QMessageBox.question(self, "Quitar del catálogo", f"¿Quitar {len(elegidas)} artículo(s)? ({nombres})"
                                    + ("\nLos de la app se pueden recuperar después." if de_la_app else "")
                                    ) != QMessageBox.Yes:
                return
        for i in sorted(elegidas, reverse=True):
            del self.filas[i]
        self._guardar([])
        self._rehacer()
        self._estado(f"Se quitaron {len(elegidas)} artículos.")

    def restaurar(self) -> None:
        elegidas = [i for i in self._elegidas() if self.filas[i].get("origen") == "modificado"]
        if not elegidas:
            self._estado("Elegí artículos cambiados (en naranja) para volverlos a como vienen con la app.")
            return
        for i in elegidas:
            orig = C.original(self.filas[i]["ref"])
            if orig:
                self.filas[i] = orig
        self._guardar([])
        self._rehacer()
        self._estado(f"Se restauraron {len(elegidas)} artículos.")

    def recuperar_quitados(self) -> None:
        quitados = C.ocultos_incluidos(self.filas)
        if not quitados:
            self._estado("No quitaste ningún artículo de los que vienen con la app.")
            return
        if QMessageBox.question(self, "Recuperar artículos",
                                f"¿Volver a poner {len(quitados)} artículo(s) de la app que quitaste?") != QMessageBox.Yes:
            return
        self.filas += quitados
        self._guardar([])
        self._rehacer()
        self._estado(f"Se recuperaron {len(quitados)} artículos.")

    def importar(self, ruta: Optional[str] = None) -> None:
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Importar catálogo", "", "Planilla (*.csv *.txt);;Todos (*)")
        if not ruta:
            return
        try:
            with open(ruta, encoding="utf-8-sig") as fh:
                texto = fh.read()
        except UnicodeDecodeError:
            with open(ruta, encoding="cp1252") as fh:      # CSV guardado por Excel en Windows
                texto = fh.read()
        except OSError as e:
            QMessageBox.warning(self, "Importar catálogo", f"No se pudo leer la planilla:\n{e}")
            return
        try:
            nuevas, avisos = C.desde_csv(texto, self.filas)
        except ValueError as e:
            QMessageBox.warning(self, "Importar catálogo", f"No se pudo leer la planilla:\n{e}")
            return
        agregadas, actualizadas = C.sumar(self.filas, nuevas)
        self._guardar()
        self._rehacer()
        msg = f"Se importaron {agregadas + actualizadas} artículos ({agregadas} nuevos, {actualizadas} actualizados)."
        self._estado(msg)
        if avisos:
            QMessageBox.information(self, "Importar catálogo", msg + "\n\n" + "\n".join(avisos[:30])
                                    + (f"\n… y {len(avisos) - 30} avisos más." if len(avisos) > 30 else ""))
        self.ultimo_aviso = avisos

    def exportar(self, ruta: Optional[str] = None) -> None:
        filas = [self.filas[i] for r, i in enumerate(self._indices) if not self.tabla.isRowHidden(r)]
        if not ruta:
            sugerido = f"catalogo_{self.categoria or 'completo'}.csv"
            ruta, _ = QFileDialog.getSaveFileName(self, "Exportar catálogo", sugerido, "Planilla (*.csv)")
        if not ruta:
            return
        with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:   # con BOM: Excel respeta los acentos
            fh.write(C.a_csv(filas))
        self._estado(f"Se exportaron {len(filas)} artículos a {os.path.basename(ruta)}.")
