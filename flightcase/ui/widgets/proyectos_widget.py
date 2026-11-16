"""Ventana «Mis cases»: los proyectos guardados con miniatura, medidas y fecha, para buscarlos,
abrirlos, duplicarlos, renombrarlos o borrarlos."""

from __future__ import annotations

import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...taller import proyectos as P

ICONO = QSize(216, 162)
CELDA = QSize(244, 250)
ORDENES = ("Más recientes", "Nombre (A-Z)", "Más grandes primero")
_RUTA = Qt.ItemDataRole.UserRole


def _settings() -> QSettings:
    return QSettings("FlightcaseCalculator", "FlightcaseCalculator")


def carpeta_proyectos() -> str:
    """Carpeta donde se guardan los cases (Documentos/LBD Flightcase Maker si no se eligió otra)."""
    v = _settings().value("carpetaProyectos")
    if isinstance(v, str) and v:
        return v
    return str(Path.home() / "Documents" / "LBD Flightcase Maker")


def poner_carpeta_proyectos(carpeta: str) -> None:
    _settings().setValue("carpetaProyectos", carpeta)


def _fecha(t: float) -> str:
    d = datetime.fromtimestamp(t)
    hoy = datetime.now().date()
    if d.date() == hoy:
        return f"hoy {d:%H:%M}"
    if (hoy - d.date()).days == 1:
        return f"ayer {d:%H:%M}"
    return f"{d:%d/%m/%Y %H:%M}"


def _icono_vacio(texto: str = "…") -> QIcon:
    pix = QPixmap(ICONO)
    pix.fill(QColor("#2b2f36"))
    p = QPainter(pix)
    p.setPen(QColor("#8a93a3"))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, texto)
    p.end()
    return _sin_tinte(pix)


def _sin_tinte(pix: QPixmap) -> QIcon:
    """Que el case elegido no se pinte de azul: se marca con el recuadro."""
    icono = QIcon(pix)
    icono.addPixmap(pix, QIcon.Mode.Selected)
    return icono


def _icono(png: str) -> QIcon:
    pix = QPixmap(png)
    if pix.isNull():
        return _icono_vacio("sin vista")
    lienzo = QPixmap(ICONO)            # fondo claro para que el case se vea bien en el tema oscuro
    lienzo.fill(QColor("#f4f5f7"))
    esc = pix.scaled(ICONO, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    p = QPainter(lienzo)
    p.drawPixmap((ICONO.width() - esc.width()) // 2, (ICONO.height() - esc.height()) // 2, esc)
    p.end()
    return _sin_tinte(lienzo)


class ProyectosDialog(QDialog):
    """`recientes` da la lista de recientes de la ventana; `abrir(ruta)` abre un case en el Taller;
    `ruta_actual()` es el case abierto (para no borrarlo sin avisar y seguirlo si se renombra);
    `al_renombrar(vieja, nueva)` avisa a la ventana."""

    def __init__(self, parent: Optional[QWidget] = None, recientes: Callable[[], List[str]] = lambda: [],
                 abrir: Optional[Callable[[str], None]] = None,
                 ruta_actual: Callable[[], Optional[str]] = lambda: None,
                 al_renombrar: Optional[Callable[[str, str], None]] = None,
                 al_borrar: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mis cases")
        self.resize(1120, 720)
        self._recientes = recientes
        self._abrir = abrir
        self._ruta_actual = ruta_actual
        self._al_renombrar = al_renombrar
        self._al_borrar = al_borrar
        self.infos: List[P.InfoProyecto] = []
        self.abierto: Optional[str] = None
        self._items: Dict[str, QListWidgetItem] = {}
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._pendientes: Dict[str, Future] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._revisar_miniaturas)
        self._init_ui()
        self.recargar()

    # ------------------------------------------------------------------ interfaz
    def _init_ui(self) -> None:
        raiz = QVBoxLayout(self)
        fila = QHBoxLayout()
        self.buscar = QLineEdit()
        self.buscar.setPlaceholderText("Buscar por nombre, carpeta, medidas o material…")
        self.buscar.setClearButtonEnabled(True)
        self.buscar.textChanged.connect(self._filtrar)
        fila.addWidget(self.buscar, 1)
        fila.addWidget(QLabel("Ordenar:"))
        self.orden = QComboBox()
        self.orden.addItems(ORDENES)
        self.orden.currentIndexChanged.connect(lambda _i: self._llenar())
        fila.addWidget(self.orden)
        raiz.addLayout(fila)

        fila_c = QHBoxLayout()
        self.lbl_carpeta = QLabel()
        self.lbl_carpeta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fila_c.addWidget(self.lbl_carpeta, 1)
        b = QPushButton("Cambiar carpeta…")
        b.setToolTip("La carpeta donde guardás tus cases. También se listan sus subcarpetas y los abiertos hace poco.")
        b.clicked.connect(self.elegir_carpeta)
        fila_c.addWidget(b)
        raiz.addLayout(fila_c)

        self.lista = QListWidget()
        self.lista.setViewMode(QListWidget.ViewMode.IconMode)
        self.lista.setIconSize(ICONO)
        self.lista.setGridSize(CELDA)
        self.lista.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.lista.setMovement(QListWidget.Movement.Static)
        self.lista.setWordWrap(True)
        self.lista.setUniformItemSizes(True)
        self.lista.setSpacing(6)
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lista.setStyleSheet("QListWidget::item { border: 2px solid transparent; border-radius: 6px; padding: 4px; }"
                                 "QListWidget::item:selected { background: #2f4a6b; color: white;"
                                 " border: 2px solid #5b9bd5; }")
        self.lista.itemActivated.connect(lambda _it: self.abrir_elegido())
        self.lista.currentItemChanged.connect(lambda *_: self._botones())
        self.lista.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        raiz.addWidget(self.lista, 1)

        self.lbl_vacio = QLabel()
        self.lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio.setWordWrap(True)
        self.lbl_vacio.setStyleSheet("color:#8a93a3; padding:24px")
        raiz.addWidget(self.lbl_vacio)

        botones = QHBoxLayout()
        self.btn_abrir = QPushButton("Abrir")
        self.btn_abrir.setDefault(True)
        self.btn_abrir.clicked.connect(self.abrir_elegido)
        self.btn_duplicar = QPushButton("Duplicar")
        self.btn_duplicar.setToolTip("Copia el case en la misma carpeta, para hacer una variante sin tocar el original.")
        self.btn_duplicar.clicked.connect(lambda: self.duplicar())
        self.btn_renombrar = QPushButton("Renombrar…")
        self.btn_renombrar.clicked.connect(lambda: self.renombrar())
        self.btn_borrar = QPushButton("Borrar")
        self.btn_borrar.setToolTip("Manda el archivo .scad a la papelera.")
        self.btn_borrar.clicked.connect(lambda: self.borrar())
        self.btn_mostrar = QPushButton("Mostrar en la carpeta")
        self.btn_mostrar.clicked.connect(self.mostrar_en_carpeta)
        for w in (self.btn_abrir, self.btn_duplicar, self.btn_renombrar, self.btn_borrar, self.btn_mostrar):
            botones.addWidget(w)
        botones.addStretch(1)
        self.lbl_total = QLabel()
        botones.addWidget(self.lbl_total)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.reject)
        botones.addWidget(cerrar)
        raiz.addLayout(botones)

        QShortcut(QKeySequence.StandardKey.Find, self, activated=self.buscar.setFocus)
        QShortcut(QKeySequence("F2"), self, activated=lambda: self.renombrar())
        QShortcut(QKeySequence.StandardKey.Delete, self.lista, activated=lambda: self.borrar())
        QShortcut(QKeySequence("Ctrl+D"), self, activated=lambda: self.duplicar())

    def _menu(self, pos) -> None:
        if self.lista.itemAt(pos) is None:
            return
        m = QMenu(self)
        m.addAction("Abrir", self.abrir_elegido)
        m.addAction("Duplicar", lambda: self.duplicar())
        m.addAction("Renombrar…", lambda: self.renombrar())
        m.addAction("Mostrar en la carpeta", self.mostrar_en_carpeta)
        m.addSeparator()
        m.addAction("Borrar", lambda: self.borrar())
        m.exec(self.lista.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------- datos
    def recargar(self, elegir: Optional[str] = None) -> None:
        carpeta = carpeta_proyectos()
        existe = os.path.isdir(carpeta)
        self.lbl_carpeta.setText(f"Carpeta de cases: {carpeta}" + ("" if existe else " (todavía no existe)"))
        self.infos = P.listar([carpeta], self._recientes())
        self._llenar(elegir)

    def _ordenados(self) -> List[P.InfoProyecto]:
        orden = self.orden.currentIndex()
        if orden == 1:
            return sorted(self.infos, key=lambda i: P._normalizar(i.nombre))
        if orden == 2:
            return sorted(self.infos, key=lambda i: -((i.ancho or 0) * (i.prof or 0) * (i.alto or 0)))
        return list(self.infos)

    def _llenar(self, elegir: Optional[str] = None) -> None:
        elegir = elegir or self.ruta_elegida()
        self.lista.clear()
        self._items.clear()
        actual = self._ruta_actual()
        actual = os.path.normcase(os.path.abspath(actual)) if actual else None
        for info in self._ordenados():
            lineas = [info.nombre, info.medidas() or "no se pudo leer", _fecha(info.fecha)]
            if actual == os.path.normcase(info.ruta):
                lineas[0] += "  (abierto)"
            it = QListWidgetItem("\n".join(lineas))
            it.setData(_RUTA, info.ruta)
            it.setToolTip(f"{info.ruta}\n{info.material}" + (f"\n⚠ {info.error}" if info.error else ""))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            png = P.miniatura_al_dia(info.ruta)
            if png:
                it.setIcon(_icono(png))
            elif info.error:
                it.setIcon(_icono_vacio("no es un case del taller"))
            else:
                it.setIcon(_icono_vacio("dibujando…"))
                self._pedir_miniatura(info.ruta)
            self.lista.addItem(it)
            self._items[info.ruta] = it
            if elegir and os.path.normcase(info.ruta) == os.path.normcase(os.path.abspath(elegir)):
                self.lista.setCurrentItem(it)
        if self.lista.currentItem() is None and self.lista.count():
            self.lista.setCurrentRow(0)
        self._filtrar(self.buscar.text())

    def _filtrar(self, texto: str) -> None:
        visibles = 0
        por_ruta = {i.ruta: i for i in self.infos}
        for n in range(self.lista.count()):
            it = self.lista.item(n)
            ok = por_ruta[it.data(_RUTA)].coincide(texto)
            it.setHidden(not ok)
            visibles += ok
        cur = self.lista.currentItem()
        if cur is None or cur.isHidden():
            primero = next((self.lista.item(n) for n in range(self.lista.count())
                            if not self.lista.item(n).isHidden()), None)
            self.lista.setCurrentItem(primero)
        total = len(self.infos)
        self.lbl_total.setText(f"{visibles} de {total}" if texto.strip() else f"{total} case{'s' if total != 1 else ''}")
        if not total:
            self.lbl_vacio.setText("Todavía no hay cases guardados. Los que guardes en la carpeta de cases "
                                   "(o abras desde cualquier lado) van a aparecer acá.")
        elif not visibles:
            self.lbl_vacio.setText(f"Ningún case coincide con «{texto.strip()}».")
        self.lbl_vacio.setVisible(not visibles)
        self._botones()

    def _botones(self) -> None:
        hay = self.ruta_elegida() is not None
        for b in (self.btn_abrir, self.btn_duplicar, self.btn_renombrar, self.btn_borrar, self.btn_mostrar):
            b.setEnabled(hay)

    def ruta_elegida(self) -> Optional[str]:
        it = self.lista.currentItem()
        return it.data(_RUTA) if it is not None and not it.isHidden() else None

    # -------------------------------------------------------------- miniaturas
    def _pedir_miniatura(self, ruta: str) -> None:
        if ruta not in self._pendientes:
            self._pendientes[ruta] = self._pool.submit(P.generar_miniatura, ruta)
            self._timer.start()

    def _revisar_miniaturas(self) -> None:
        for ruta, fut in list(self._pendientes.items()):
            if not fut.done():
                continue
            del self._pendientes[ruta]
            png = fut.result() if not fut.cancelled() and fut.exception() is None else None
            it = self._items.get(ruta)
            if it is not None:
                it.setIcon(_icono(png) if png else _icono_vacio("sin vista"))
        if not self._pendientes:
            self._timer.stop()

    def esperar_miniaturas(self, segundos: float = 30) -> None:
        """Para los tests y la captura: espera a que se dibujen todas."""
        for fut in list(self._pendientes.values()):
            try:
                fut.result(timeout=segundos)
            except Exception:
                pass
        self._revisar_miniaturas()

    def done(self, r: int) -> None:  # noqa: D401
        self._timer.stop()
        for fut in self._pendientes.values():
            fut.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)
        super().done(r)

    # ----------------------------------------------------------------- acciones
    def abrir_elegido(self) -> None:
        ruta = self.ruta_elegida()
        if not ruta:
            return
        self.abierto = ruta
        if self._abrir:
            self._abrir(ruta)
        self.accept()

    def duplicar(self, nombre: Optional[str] = None) -> Optional[str]:
        ruta = self.ruta_elegida()
        if not ruta:
            return None
        try:
            nueva = P.duplicar(ruta, nombre)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Duplicar", f"No se pudo duplicar:\n{e}")
            return None
        if os.path.normcase(os.path.dirname(nueva)) != os.path.normcase(os.path.abspath(carpeta_proyectos())):
            self._recordar(nueva)
        self.recargar(elegir=nueva)
        return nueva

    def _recordar(self, ruta: str) -> None:
        """Un case fuera de la carpeta de cases se lista por estar entre los recientes."""
        actuales = self._recientes()
        recientes = [ruta] + [r for r in actuales if r != ruta]
        _settings().setValue("recientesScad", recientes[:8])

    def renombrar(self, nombre: Optional[str] = None) -> Optional[str]:
        ruta = self.ruta_elegida()
        if not ruta:
            return None
        if nombre is None:
            viejo = os.path.splitext(os.path.basename(ruta))[0]
            nombre, ok = QInputDialog.getText(self, "Renombrar case", "Nombre nuevo:", QLineEdit.EchoMode.Normal, viejo)
            if not ok or nombre.strip() == viejo:
                return None
        try:
            nueva = P.renombrar(ruta, nombre)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Renombrar", str(e))
            return None
        recientes = [nueva if os.path.normcase(r) == os.path.normcase(ruta) else r for r in self._recientes()]
        _settings().setValue("recientesScad", recientes)
        if self._al_renombrar:
            self._al_renombrar(ruta, nueva)
        self.recargar(elegir=nueva)
        return nueva

    def borrar(self, confirmar: bool = True) -> bool:
        ruta = self.ruta_elegida()
        if not ruta:
            return False
        nombre = os.path.basename(ruta)
        actual = self._ruta_actual()
        abierto = bool(actual) and os.path.normcase(os.path.abspath(actual)) == os.path.normcase(ruta)
        if confirmar:
            extra = "\n\nEs el case que tenés abierto: queda en la ventana como case sin guardar." if abierto else ""
            r = QMessageBox.question(self, "Borrar case", f"¿Mandar «{nombre}» a la papelera?{extra}",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return False
        from PySide6.QtCore import QFile
        if not QFile.moveToTrash(ruta):
            try:
                os.remove(ruta)
            except OSError as e:
                QMessageBox.warning(self, "Borrar case", f"No se pudo borrar {nombre}:\n{e}")
                return False
        P.olvidar(ruta)
        _settings().setValue("recientesScad",
                             [r for r in self._recientes() if os.path.normcase(r) != os.path.normcase(ruta)])
        if abierto and self._al_borrar:
            self._al_borrar(ruta)
        self.recargar()
        return True

    def mostrar_en_carpeta(self) -> None:
        ruta = self.ruta_elegida()
        if not ruta:
            return
        import subprocess
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", ruta])
                return
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(ruta)])
                return
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(ruta)))

    def elegir_carpeta(self) -> None:
        inicial = carpeta_proyectos()
        carpeta = QFileDialog.getExistingDirectory(self, "Carpeta de cases",
                                                   inicial if os.path.isdir(inicial) else str(Path.home()))
        if carpeta:
            poner_carpeta_proyectos(carpeta)
            self.recargar()
