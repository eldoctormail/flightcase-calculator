"""Ventana principal: el Taller, para armar cases a medida con las reglas propias."""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from datetime import datetime

from PySide6.QtCore import QEvent, QLockFile, QObject, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon, QKeySequence, QSurfaceFormat
from PySide6.QtWidgets import (QApplication, QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox,
                               QStatusBar, QWidget)

from ..paths import bundled_resource
from ..taller import recuperacion
from ..taller.scad import leer_proyecto
from .theme import DARK_THEME_QSS
from .widgets import TallerWidget

TITULO = "LBD Flightcase Maker"
MAX_RECIENTES = 8
AUTOGUARDADO_MINUTOS = (1, 3, 5, 10)
AUTOGUARDADO_POR_DEFECTO = 3
RECUPERACION_SEGUNDOS = 30          # cada cuánto se copia el case con cambios sin guardar


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
        self.taller_widget.case_nuevo.connect(self._case_nuevo_creado)
        self.taller_widget.pantalla_inicio = self.pantalla_inicio
        self.taller_widget.guardado.connect(self._guardado)
        self.lbl_autoguardado = QLabel()
        self.lbl_autoguardado.setStyleSheet("color:#8a93a3; padding-right:6px")
        self.status_bar.addPermanentWidget(self.lbl_autoguardado)
        self._init_recuperacion()
        self._init_menus()
        QApplication.instance().installEventFilter(self)
        if restore_settings:
            self._restore_settings(load_last_project)
        self._actualizar()

    # ------------------------------------------------- autoguardado/recuperación
    def _init_recuperacion(self) -> None:
        """Esta ventana tiene su copia de recuperación, marcada como «en uso» con un QLockFile
        (si la app se cuelga, el lock queda huérfano y al arrancar se ofrece recuperarla)."""
        self.sesion = recuperacion.Sesion()
        self._lock: Optional[QLockFile] = None
        try:
            recuperacion.carpeta().mkdir(parents=True, exist_ok=True)
            lock = QLockFile(self.sesion.lock)
            lock.setStaleLockTime(0)
            if lock.tryLock(0):
                self._lock = lock
        except OSError:
            pass
        self._foto_recuperacion: Optional[str] = None
        self._timer_recuperacion = QTimer(self)
        self._timer_recuperacion.setInterval(RECUPERACION_SEGUNDOS * 1000)
        self._timer_recuperacion.timeout.connect(self.copiar_para_recuperar)
        self._timer_recuperacion.start()
        self._timer_autoguardado = QTimer(self)
        self._timer_autoguardado.timeout.connect(self.autoguardar)
        self._programar_autoguardado()

    def minutos_autoguardado(self) -> int:
        v = _settings().value("autoguardadoMinutos", AUTOGUARDADO_POR_DEFECTO)
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return AUTOGUARDADO_POR_DEFECTO

    def poner_autoguardado(self, minutos: int) -> None:
        _settings().setValue("autoguardadoMinutos", int(minutos))
        self._programar_autoguardado()
        for a in getattr(self, "_acciones_autoguardado", {}).values():
            a.setChecked(a.data() == int(minutos))

    def _programar_autoguardado(self) -> None:
        m = self.minutos_autoguardado()
        if m:
            self._timer_autoguardado.start(m * 60_000)
        else:
            self._timer_autoguardado.stop()
        self._mostrar_autoguardado()

    def _mostrar_autoguardado(self, cuando: Optional[datetime] = None) -> None:
        m = self.minutos_autoguardado()
        if cuando is not None:
            self.lbl_autoguardado.setText(f"Guardado automáticamente a las {cuando:%H:%M}")
        elif not m:
            self.lbl_autoguardado.setText("Autoguardado desactivado")
        elif not self.taller_widget.ruta:
            self.lbl_autoguardado.setText("Sin guardar: el autoguardado empieza cuando le pongas nombre (Ctrl+S)")
        else:
            self.lbl_autoguardado.setText(f"Autoguardado cada {m} min")

    def _ocupado(self) -> bool:
        """Con un diálogo abierto (asistente, Mis cases, guardar...) no se autoguarda."""
        return QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None

    def autoguardar(self) -> bool:
        """Guarda el case en su archivo si tiene cambios. Los nuevos sin nombre no: esos van
        solo a la copia de recuperación."""
        t = self.taller_widget
        if not t.ruta or self._ocupado() or not t.hay_cambios():
            return False
        if t.guardar(t.ruta, automatico=True):
            return True
        self.lbl_autoguardado.setText("⚠ No se pudo autoguardar (¿el archivo está abierto en otro programa?)")
        return False

    def copiar_para_recuperar(self) -> bool:
        """Copia el case con los cambios sin guardar a la carpeta de recuperación."""
        t = self.taller_widget
        if not t.hay_cambios():
            if self._foto_recuperacion is not None:
                self.sesion.borrar()
                self._foto_recuperacion = None
            return False
        foto = t._foto()
        if foto == self._foto_recuperacion:
            return False
        if self.sesion.escribir(t.texto_proyecto(), t.ruta, t.params.get("_carpeta", "")):
            self._foto_recuperacion = foto
            return True
        return False

    def _guardado(self, automatico: bool) -> None:
        self.sesion.borrar()            # ya está en el archivo
        self._foto_recuperacion = None
        self._mostrar_autoguardado(datetime.now() if automatico else None)

    @staticmethod
    def _sigue_abierta(lock: str) -> bool:
        """True si otra ventana de la app tiene tomado ese lock (si el proceso murió, queda libre)."""
        if not os.path.exists(lock):
            return False
        lf = QLockFile(lock)
        lf.setStaleLockTime(0)
        if lf.tryLock(0):
            lf.unlock()                 # también borra el archivo del lock
            return False
        return True

    def pendientes_de_recuperar(self) -> List[recuperacion.Recuperable]:
        return recuperacion.pendientes(self._sigue_abierta, propia=self.sesion.id)

    def _preguntar_recuperar(self, r: recuperacion.Recuperable, quedan: int) -> str:
        """'recuperar', 'descartar' o 'despues'."""
        caja = QMessageBox(QMessageBox.Icon.Warning, "Recuperar case",
                           "La última vez la app se cerró sin guardar los cambios de "
                           f"«{r.nombre}».\nHay una copia de {r.fecha:%d/%m/%Y a las %H:%M}.", parent=self)
        caja.setInformativeText("Recuperar la pone en la ventana como cambios sin guardar: revisala y guardala."
                                + (f"\n(Hay {quedan} copia{'s' if quedan != 1 else ''} más para después.)" if quedan else ""))
        b_rec = caja.addButton("Recuperar", QMessageBox.ButtonRole.AcceptRole)
        b_desc = caja.addButton("Descartar", QMessageBox.ButtonRole.DestructiveRole)
        caja.addButton("Después", QMessageBox.ButtonRole.RejectRole)
        caja.setDefaultButton(b_rec)
        caja.exec()
        return {b_rec: "recuperar", b_desc: "descartar"}.get(caja.clickedButton(), "despues")

    def ofrecer_recuperacion(self) -> bool:
        """Al arrancar: si quedó una copia de un cierre inesperado, ofrece recuperarla. True si la cargó."""
        pendientes = self.pendientes_de_recuperar()
        if not pendientes:
            return False
        r = pendientes[0]
        quedan = len(pendientes) - 1
        respuesta = self._preguntar_recuperar(r, quedan)
        if respuesta == "descartar":
            recuperacion.borrar(r.id)
            return False
        if respuesta != "recuperar" or not self.taller_widget.confirmar_cambios("Recuperar case", "recuperar el otro"):
            return False
        try:
            self.taller_widget.cargar_con_cambios(r.scad, r.ruta, r.carpeta_case)
        except Exception as e:
            QMessageBox.warning(self, "Recuperar case", f"No se pudo leer la copia:\n{e}\n\nQuedó en {r.scad}")
            return False
        self.copiar_para_recuperar()     # ahora es la copia de esta sesión
        recuperacion.borrar(r.id)
        self._actualizar()
        self.status_bar.showMessage(f"Se recuperaron los cambios de «{r.nombre}». Guardalos con Ctrl+S.", 10000)
        return True

    def versiones(self, ruta: Optional[str] = None) -> bool:
        """Las versiones anteriores de un case (el abierto si no se dice). True si se restauró una."""
        from .widgets.versiones_widget import VersionesDialog
        t = self.taller_widget
        ruta = ruta or t.ruta
        if not ruta:
            QMessageBox.information(self, "Versiones anteriores",
                                    "Este case todavía no se guardó: las versiones aparecen cuando tiene archivo.")
            return False

        def restaurar(version: str) -> bool:
            if not t._es_el_abierto(ruta) and not t.abrir(ruta):
                return False
            t.cargar_con_cambios(version, ruta)
            return True

        dlg = VersionesDialog(self, ruta, restaurar, t._etiquetas, t.defectos)
        dlg.exec()
        if dlg.restaurada:
            nombre = os.path.basename(dlg.restaurada)[:16]
            self._actualizar()
            self.status_bar.showMessage(f"Versión del {nombre} en la ventana, sin guardar: Ctrl+S para quedártela "
                                        "(la actual queda entre las versiones).", 12000)
            return True
        return False

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
        self._accion(m, "&Nuevo case…", "Ctrl+N", self.pantalla_inicio,
                     "Pantalla de inicio: elegí un estilo de case o una plantilla y ponele nombre")
        self._accion(m, "Nuevo case con el a&sistente...", "Ctrl+Shift+N", self._asistente,
                     "Case nuevo paso a paso: estilo, equipos, medidas y terminaciones")
        self._accion(m, "&Mis cases...", "Ctrl+Shift+O", self.proyectos,
                     "Tus cases guardados con miniatura y medidas: buscar, abrir, duplicar, renombrar o borrar")
        self._accion(m, "&Abrir case (.scad)...", "Ctrl+O", self._taller_abrir, "Abrir un proyecto del taller")
        self.recent_menu = m.addMenu("Abrir &reciente")
        m.addSeparator()
        self._accion(m, "&Guardar case", "Ctrl+S", self._taller_guardar, "Guardar el proyecto del taller")
        self._accion(m, "Guardar case &como...", "Ctrl+Shift+S", self._taller_guardar_como, "Guardar en otro archivo")
        self.accion_versiones = self._accion(m, "&Versiones anteriores...", "Ctrl+Alt+V", lambda: self.versiones(),
                                             "Las copias fechadas que quedan cada vez que se guarda el case")
        self.menu_autoguardado = m.addMenu("A&utoguardado")
        grupo = QActionGroup(self)
        self._acciones_autoguardado = {}
        actual = self.minutos_autoguardado()
        for minutos in AUTOGUARDADO_MINUTOS + (0,):
            a = QAction(f"Cada {minutos} minuto{'s' if minutos != 1 else ''}" if minutos else "Desactivado", self)
            a.setCheckable(True)
            a.setData(minutos)
            a.setChecked(minutos == actual)
            a.triggered.connect(lambda _=False, n=minutos: self.poner_autoguardado(n))
            grupo.addAction(a)
            self.menu_autoguardado.addAction(a)
            self._acciones_autoguardado[minutos] = a
        m.addSeparator()
        self._accion(m, "Exportar &paquete del taller (planos, DXF, instructivo)...", "Ctrl+P", self._taller_exportar,
                     "DXF por pieza, listas de corte y materiales, planos.pdf e instructivo de montaje")
        self._accion(m, "Exportar p&lanos (PDF)...", "Ctrl+Shift+P", lambda: self.taller_widget.exportar_planos(),
                     "planos.pdf: resumen, vistas, cada pieza acotada, placas, perfiles y materiales")
        self._accion(m, "Exportar &hoja del case (PDF)...", "Ctrl+Alt+H", lambda: self.taller_widget.exportar_hoja(),
                     "Una hoja con la vista 3D como se ve ahora y las seis vistas de los lados, acotadas")
        self._accion(m, "Guardar &imagen de la vista 3D (PNG)...", "Ctrl+Alt+I",
                     lambda: self.taller_widget.guardar_imagen_3d(), "La vista 3D tal como se ve, con fondo transparente")
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
        self._accion(self.edit_menu, "Copiar &imagen de la vista 3D", "Ctrl+Shift+C", self.taller_widget.copiar_imagen_3d,
                     "Copia la vista 3D (sin fondo) para pegarla en otro programa")
        self.edit_menu.addSeparator()
        self._accion(self.edit_menu, "&Biblioteca de equipos...", "Ctrl+B", self.taller_widget.biblioteca,
                     "Tus equipos con sus medidas, para usarlos en la espuma o el rack de cualquier case")
        self._accion(self.edit_menu, "&Catálogo de herrajes y placas...", "Ctrl+K", lambda: self.taller_widget.editar_catalogo(),
                     "Las medidas reales de tus herrajes, perfiles y placas, con importar y exportar planilla CSV")
        self.taller_widget.historial_cambiado.connect(self._actualizar_historial)
        self._actualizar_historial()

        self.help_menu = barra.addMenu("A&yuda")
        a = self._accion(self.help_menu, f"&Acerca de {TITULO}...", None, self.acerca_de, "Autor y versión")
        a.setMenuRole(QAction.MenuRole.AboutRole)     # en Mac va al menú de la app
        from .actualizador import Actualizador
        self.actualizador = Actualizador(
            self, _settings, self._confirmar_para_actualizar)
        a = self._accion(self.help_menu, "&Buscar actualizaciones...", None, lambda: self.actualizador.buscar(),
                         "Ver si hay una versión nueva en GitHub e instalarla")
        a.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)   # en Mac, en el menú de la app
        self.accion_buscar_al_abrir = a = QAction("Buscar actualizaciones al &abrir", self, checkable=True)
        a.setChecked(self.actualizador.buscar_al_abrir)
        a.toggled.connect(lambda v: setattr(self.actualizador, "buscar_al_abrir", v))
        self.help_menu.addAction(a)

    def _confirmar_para_actualizar(self) -> bool:
        """Antes de cerrar para instalar una versión nueva (si ya se respondió, al cerrar no se vuelve a preguntar)."""
        self._ya_confirmado = self.taller_widget.confirmar_cambios("Actualizar", "cerrar para actualizar")
        if self._ya_confirmado:     # vale solo para el cierre que sigue enseguida (si la instalación falla, no)
            QTimer.singleShot(0, lambda: setattr(self, "_ya_confirmado", False))
        return self._ya_confirmado

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
                               ruta_actual=lambda: t.ruta, al_renombrar=t.renombrado, al_borrar=t.borrado,
                               versiones=self.versiones)

    def proyectos(self) -> None:
        """«Mis cases»: la lista de proyectos guardados."""
        self.dialogo_proyectos().exec()
        self._update_recent_files_menu()
        self._actualizar()

    def pantalla_inicio(self, al_abrir: bool = False) -> bool:
        """La pantalla de inicio: proyecto nuevo con estilo o plantilla, Mis cases, abrir o seguir.
        Al abrir la app, cancelarla deja el último case como estaba."""
        from .widgets.inicio_widget import PantallaInicio
        t = self.taller_widget
        if not al_abrir and not t.confirmar_cambios("Proyecto nuevo", "empezar otro"):
            return False
        s = _settings()
        dlg = PantallaInicio(self, recientes=self._get_recent_files(), ultimo=t.ruta if al_abrir else None,
                             mostrar_al_abrir=s.value("inicio/mostrar", True, type=bool))
        hecho = bool(dlg.exec())
        s.setValue("inicio/mostrar", dlg.chk_al_abrir.isChecked())
        if not hecho:
            return False
        if dlg.accion == "crear":
            t.crear(dlg.estilo.id if dlg.estilo else None, dlg.plantilla, dlg.nombre)
            self._actualizar()
            if t.ruta:
                self._add_recent_file(t.ruta)
            else:
                self._case_nuevo_creado()        # el aviso de la barra de estado, después de _actualizar
            return True
        elif dlg.accion == "proyectos":
            self.proyectos()
        elif dlg.accion == "abrir":
            self.abrir()
        elif dlg.accion == "asistente":
            self._asistente()
        self._actualizar()
        return True

    def al_abrir(self) -> None:
        """Al arrancar: primero lo que haya para recuperar; si no, la pantalla de inicio."""
        if self.ofrecer_recuperacion():
            return
        if _settings().value("inicio/mostrar", True, type=bool):
            self.pantalla_inicio(al_abrir=True)

    def _taller_nuevo(self) -> None:
        self.taller_widget.nuevo()

    def _case_nuevo_creado(self) -> None:
        """Al empezar un case nuevo se avisa en la barra de estado (si no, parece que no pasó nada)."""
        self._actualizar()
        self.status_bar.showMessage(
            "Case nuevo con las medidas por defecto: cambialas a la izquierda, o usá el asistente (Ctrl+Shift+N).",
            8000)
        QTimer.singleShot(8000, self._actualizar)

    def acerca_de(self) -> None:
        from ..version import AUTOR, version
        QMessageBox.about(
            self, f"Acerca de {TITULO}",
            f"<h3>{TITULO}</h3>"
            f"<p>Versión {version()}</p>"
            f"<p>Autor: {AUTOR}</p>"
            "<p>Cases a medida con las reglas del taller: planos, DXF, instructivo de montaje y STEP.</p>")

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
        self.accion_versiones.setEnabled(bool(self.taller_widget.ruta))
        if not self.lbl_autoguardado.text().startswith(("Guardado automáticamente", "⚠")) or not self.taller_widget.ruta:
            self._mostrar_autoguardado()
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
        if not getattr(self, "_ya_confirmado", False) and not self.taller_widget.confirmar_cambios("Salir", "salir"):
            event.ignore()
            return
        QApplication.instance().removeEventFilter(self)
        self._save_settings()
        self._timer_recuperacion.stop()
        self._timer_autoguardado.stop()
        self.sesion.borrar()                # se cerró bien: no hay nada que recuperar
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None
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
    QTimer.singleShot(300, window.al_abrir)    # recuperar si se cerró de golpe, o la pantalla de inicio

    from ..actualizaciones import es_app_instalada
    if es_app_instalada() and window.actualizador.buscar_al_abrir:   # desde el código no: la versión es otra
        QTimer.singleShot(3000, lambda: window.actualizador.buscar(silencioso=True))
    return app.exec()
