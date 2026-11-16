"""Ventana principal: el Taller, para armar cases a medida con las reglas propias."""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from PySide6.QtCore import QEvent, QObject, QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence, QSurfaceFormat
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMenu, QMessageBox, QStatusBar, QWidget

from ..paths import bundled_resource
from ..taller.scad import leer_proyecto
from .theme import DARK_THEME_QSS
from .widgets import TallerWidget

TITULO = "LBD Flightcase Maker"
MAX_RECIENTES = 8


def _settings() -> QSettings:
    return QSettings("FlightcaseCalculator", "FlightcaseCalculator")


class FlightCaseMainWindow(QMainWindow):
    """El Taller ocupa toda la ventana; el menú Archivo maneja los proyectos .scad."""

    def __init__(self, parent: Optional[QWidget] = None, restore_settings: bool = True,
                 load_last_project: bool = True):
        super().__init__(parent)
        self.setWindowIcon(icono_app())
        self.resize(1400, 900)
        self.taller_widget = TallerWidget(self)
        self.setCentralWidget(self.taller_widget)
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.taller_widget.resultado_cambiado.connect(self._estado_taller)
        self.taller_widget.ruta_cambiada.connect(self._ruta_cambiada)
        self.taller_widget.proyectos_pedidos.connect(self.proyectos)
        self._init_menus()
        QApplication.instance().installEventFilter(self)
        if restore_settings:
            self._restore_settings(load_last_project)
        self._actualizar()

    # ------------------------------------------------------------------ menús
    def _accion(self, menu: QMenu, texto: str, atajo: Optional[str], funcion, ayuda: str = "") -> QAction:
        a = QAction(texto, self)
        if atajo:
            a.setShortcut(atajo)
        if ayuda:
            a.setStatusTip(ayuda)
        a.triggered.connect(funcion)
        menu.addAction(a)
        return a

    def _init_menus(self) -> None:
        barra = self.menuBar()
        self.file_menu = barra.addMenu("&Archivo")
        m = self.file_menu
        self._accion(m, "&Nuevo case", "Ctrl+N", self._taller_nuevo, "Case nuevo con las reglas del taller")
        self._accion(m, "Nuevo case con el a&sistente...", "Ctrl+Shift+N", self._asistente,
                     "Case nuevo paso a paso: estilo, equipos, medidas y terminaciones")
        self._accion(m, "&Mis cases...", "Ctrl+Shift+O", self.proyectos,
                     "Tus cases guardados con miniatura y medidas: buscar, abrir, duplicar, renombrar o borrar")
        self._accion(m, "&Abrir case (.scad)...", "Ctrl+O", self._taller_abrir, "Abrir un proyecto del taller")
        self.recent_menu = m.addMenu("Abrir &reciente")
        m.addSeparator()
        self._accion(m, "&Guardar case", "Ctrl+S", self._taller_guardar, "Guardar el proyecto del taller")
        self._accion(m, "Guardar case &como...", "Ctrl+Shift+S", self._taller_guardar_como, "Guardar en otro archivo")
        m.addSeparator()
        self._accion(m, "Exportar &paquete del taller (planos, DXF, instructivo)...", "Ctrl+P", self._taller_exportar,
                     "DXF por pieza, listas de corte y materiales, planos.pdf e instructivo de montaje")
        self._accion(m, "Exportar p&lanos (PDF)...", "Ctrl+Shift+P", lambda: self.taller_widget.exportar_planos(),
                     "planos.pdf: resumen, vistas, cada pieza acotada, placas, perfiles y materiales")
        self._accion(m, "Exportar a &STEP (3D para CAD)...", "Ctrl+Alt+S", self._taller_step,
                     "El case armado para abrir en Fusion, SolidWorks o FreeCAD")
        self._accion(m, "Paquete del &taller desde un .scad sin abrirlo...", "Ctrl+T", self._export_taller_pack)
        m.addSeparator()
        self._accion(m, "&Salir", "Ctrl+Q", self.close)
        self._update_recent_files_menu()

        self.edit_menu = barra.addMenu("&Editar")
        self.accion_deshacer = self._accion(self.edit_menu, "&Deshacer", None, self.taller_widget.deshacer)
        self.accion_deshacer.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Undo))
        self.accion_rehacer = self._accion(self.edit_menu, "&Rehacer", None, self.taller_widget.rehacer)
        self.accion_rehacer.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Redo)
                                         + [QKeySequence("Ctrl+Y")])
        self.edit_menu.addSeparator()
        self._accion(self.edit_menu, "&Biblioteca de equipos...", "Ctrl+B", self.taller_widget.biblioteca,
                     "Tus equipos con sus medidas, para usarlos en la espuma o el rack de cualquier case")
        self._accion(self.edit_menu, "&Catálogo de herrajes y placas...", "Ctrl+K", lambda: self.taller_widget.editar_catalogo(),
                     "Las medidas reales de tus herrajes, perfiles y placas, con importar y exportar planilla CSV")
        self.taller_widget.historial_cambiado.connect(self._actualizar_historial)
        self._actualizar_historial()

    def _actualizar_historial(self) -> None:
        t = self.taller_widget
        for accion, texto, base in ((self.accion_deshacer, t.texto_deshacer(), "&Deshacer"),
                                    (self.accion_rehacer, t.texto_rehacer(), "&Rehacer")):
            accion.setText(f"{base}: {texto}" if texto else base)
        self.accion_deshacer.setEnabled(bool(t._deshacer))
        self.accion_rehacer.setEnabled(bool(t._rehacer))

    def eventFilter(self, obj, event) -> bool:
        """Ctrl+Z / Ctrl+Y deshacen el case aunque el cursor esté en un campo numérico
        (si no, el campo se queda con el atajo para deshacer su propio texto)."""
        if event.type() == QEvent.Type.ShortcutOverride and isinstance(obj, QWidget) \
                and self.taller_widget.isAncestorOf(obj):
            from PySide6.QtWidgets import QAbstractSpinBox
            w = obj
            while w is not None and not isinstance(w, QAbstractSpinBox):
                w = w.parentWidget()
            if w is not None and (event.matches(QKeySequence.StandardKey.Undo)
                                  or event.matches(QKeySequence.StandardKey.Redo)
                                  or QKeySequence(event.keyCombination()) == QKeySequence("Ctrl+Y")):
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------- recientes
    def _get_recent_files(self) -> List[str]:
        v = _settings().value("recientesScad")
        lista = [v] if isinstance(v, str) else list(v or [])
        return [r for r in lista if isinstance(r, str) and os.path.isfile(r)][:MAX_RECIENTES]

    def _add_recent_file(self, ruta: Optional[str]) -> None:
        if not ruta:
            return
        ruta = os.path.abspath(ruta)
        lista = [ruta] + [r for r in self._get_recent_files() if os.path.abspath(r) != ruta]
        _settings().setValue("recientesScad", lista[:MAX_RECIENTES])
        self._update_recent_files_menu()

    def _update_recent_files_menu(self) -> None:
        self.recent_menu.clear()
        recientes = self._get_recent_files()
        for i, ruta in enumerate(recientes, 1):
            a = QAction(f"&{i} {os.path.basename(ruta)}", self)
            a.setStatusTip(ruta)
            a.triggered.connect(lambda _=False, r=ruta: self.abrir(r))
            self.recent_menu.addAction(a)
        self.recent_menu.setEnabled(bool(recientes))

    # -------------------------------------------------------------- acciones
    def _ruta_cambiada(self, ruta: str) -> None:
        """Abrir o guardar, desde el menú o desde los botones del Taller."""
        if ruta:
            self._add_recent_file(ruta)
        self._actualizar()

    def abrir(self, ruta: Optional[str] = None) -> None:
        self.taller_widget.abrir(ruta)
        self._actualizar()

    def dialogo_proyectos(self):
        from .widgets.proyectos_widget import ProyectosDialog
        t = self.taller_widget
        return ProyectosDialog(self, recientes=self._get_recent_files, abrir=self.abrir,
                               ruta_actual=lambda: t.ruta, al_renombrar=t.renombrado, al_borrar=t.borrado)

    def proyectos(self) -> None:
        """«Mis cases»: la lista de proyectos guardados."""
        self.dialogo_proyectos().exec()
        self._update_recent_files_menu()
        self._actualizar()

    def _taller_nuevo(self) -> None:
        self.taller_widget.nuevo()
        self._actualizar()

    def _asistente(self) -> None:
        if self.taller_widget.asistente():
            self._actualizar()

    def _taller_abrir(self) -> None:
        self.abrir()

    def _taller_guardar(self) -> None:
        self.taller_widget.guardar(self.taller_widget.ruta)

    def _taller_guardar_como(self) -> None:
        self.taller_widget.guardar()

    def _taller_exportar(self) -> None:
        self.taller_widget.exportar()

    def _taller_step(self) -> None:
        self.taller_widget.exportar_step()

    def _export_taller_pack(self) -> None:
        """DXF, listas y planos.pdf de un proyecto .scad, sin abrirlo en la ventana."""
        from ..taller.produccion import exportar_scad
        scad, _ = QFileDialog.getOpenFileName(self, "Proyecto del taller (OpenSCAD)", "", "Proyecto OpenSCAD (*.scad)")
        if not scad:
            return
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para el paquete del taller")
        if not folder:
            return
        target = os.path.join(folder, f"salida_{os.path.splitext(os.path.basename(scad))[0]}")
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                paq = exportar_scad(scad, target)
            finally:
                QApplication.restoreOverrideCursor()
            avisos = ("\n\nAvisos:\n" + "\n".join(f"• {a}" for a in paq.avisos)) if paq.avisos else ""
            QMessageBox.information(self, "Paquete del taller",
                                    f"Se generaron {len(paq.archivos)} archivos en:\n{target}{avisos}")
        except Exception as e:
            QMessageBox.critical(self, "Paquete del taller", f"No se pudo generar el paquete:\n{e}")

    # --------------------------------------------------------- título/estado
    def _nombre(self) -> str:
        return os.path.basename(self.taller_widget.ruta) if self.taller_widget.ruta else "case nuevo"

    def _actualizar(self) -> None:
        self.setWindowTitle(f"{TITULO} — {self._nombre()}")
        self._estado_taller(self.taller_widget.resultado)

    def _estado_taller(self, res) -> None:
        if res is None:
            return
        v = res.valores
        avisos = f" | ⚠ {len(res.avisos)} aviso{'s' if len(res.avisos) != 1 else ''}" if res.avisos else ""
        self.status_bar.showMessage(
            f"{self._nombre()} | Exterior: {v['ext_ancho']:.0f}×{v['ext_prof']:.0f}×{v['ext_alto']:.0f} mm | "
            f"{len(res.paneles)} paneles | {v['placa_material']}{avisos}")

    # ----------------------------------------------------------- settings
    def _save_settings(self) -> None:
        s = _settings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("windowState", self.saveState())
        s.setValue("ultimoScad", self.taller_widget.ruta or "")

    def _restore_settings(self, load_last_project: bool = True) -> None:
        s = _settings()
        geom = s.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        state = s.value("windowState")
        if state:
            self.restoreState(state)
        ultimo = s.value("ultimoScad")
        if load_last_project and isinstance(ultimo, str) and ultimo and os.path.isfile(ultimo):
            try:
                self.taller_widget.set_params(leer_proyecto(ultimo), ultimo)
            except Exception:
                pass

    def closeEvent(self, event: QCloseEvent) -> None:
        QApplication.instance().removeEventFilter(self)
        self._save_settings()
        super().closeEvent(event)


def icono_app() -> QIcon:
    """Ícono de la app (packaging/icono/icono.svg, generado con tools/generar_icono.py)."""
    return QIcon(str(bundled_resource("icono.png")))


def run_app() -> int:
    """Arranca la aplicación."""
    gl_format = QSurfaceFormat()        # antialiasing 4x en la vista 3D
    gl_format.setSamples(4)
    gl_format.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(gl_format)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME_QSS)
    app.setApplicationName(TITULO)
    app.setWindowIcon(icono_app())
    if sys.platform == "win32":   # que la barra de tareas muestre nuestro ícono y no el de Python
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("eldoctormail.FlightcaseCalculator")
        except Exception:
            pass
    window = FlightCaseMainWindow()

    for arg in sys.argv[1:]:            # doble clic en un .scad
        if arg.lower().endswith(".scad") and os.path.isfile(arg):
            window.abrir(arg)
            break

    class _FileOpenFilter(QObject):     # macOS entrega los archivos del Finder como QFileOpenEvent
        def eventFilter(self, obj, event):
            if event.type() == QEvent.FileOpen and event.file().lower().endswith(".scad"):
                window.abrir(event.file())
                return True
            return False

    file_filter = _FileOpenFilter(app)
    app.installEventFilter(file_filter)
    window.show()
    return app.exec()
