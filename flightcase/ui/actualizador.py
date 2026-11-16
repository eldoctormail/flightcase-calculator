"""Avisa cuando hay una versión nueva y la instala con un clic (menú Ayuda → Buscar actualizaciones)."""

from __future__ import annotations

import html
from typing import Callable, Optional

from PySide6.QtCore import QObject, QSettings, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

from .. import actualizaciones as act
from ..version import version

CLAVE_AUTO = "actualizaciones/buscarAlAbrir"
CLAVE_OMITIDA = "actualizaciones/versionOmitida"


class _Hilo(QThread):
    """Corre una función fuera de la ventana para que no se congele."""
    listo = Signal(object)
    fallo = Signal(str)
    avance = Signal(int, int)

    def __init__(self, funcion: Callable, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.funcion = funcion

    def run(self) -> None:
        try:
            self.listo.emit(self.funcion(self))
        except Exception as e:      # noqa: BLE001 — el mensaje se muestra tal cual
            self.fallo.emit(str(e))


class Actualizador(QObject):
    """Busca, descarga e instala. La ventana le pasa cómo preguntar por los cambios sin guardar."""

    def __init__(self, ventana: QWidget, settings: Callable[[], QSettings],
                 confirmar_cierre: Callable[[], bool]):
        super().__init__(ventana)
        self.ventana = ventana
        self.settings = settings
        self.confirmar_cierre = confirmar_cierre
        self.sincronico = False      # en los tests: sin hilos
        self._hilos = []
        self.buscando = False

    # ------------------------------------------------------------ ajustes
    @property
    def buscar_al_abrir(self) -> bool:
        return str(self.settings().value(CLAVE_AUTO, "true")).lower() in ("true", "1")

    @buscar_al_abrir.setter
    def buscar_al_abrir(self, valor: bool) -> None:
        self.settings().setValue(CLAVE_AUTO, "true" if valor else "false")

    # -------------------------------------------------------------- hilos
    def _en_hilo(self, funcion, listo, fallo, avance=None) -> _Hilo:
        h = _Hilo(funcion, self)
        if self.sincronico:
            try:
                listo(funcion(h))
            except Exception as e:  # noqa: BLE001
                fallo(str(e))
            return h
        h.listo.connect(listo)
        h.fallo.connect(fallo)
        if avance:
            h.avance.connect(avance)
        h.finished.connect(lambda: self._hilos.remove(h) if h in self._hilos else None)
        self._hilos.append(h)
        h.start()
        return h

    # ------------------------------------------------------------- buscar
    def buscar(self, silencioso: bool = False) -> None:
        """silencioso: la búsqueda al abrir la app, que solo avisa si hay algo nuevo."""
        if self.buscando:
            return
        self.buscando = True
        actual = version()

        def listo(nueva) -> None:
            self.buscando = False
            if nueva is None:
                if not silencioso:
                    QMessageBox.information(self.ventana, "Actualizaciones",
                                            f"Ya tenés la última versión ({actual}).")
                return
            if silencioso and str(self.settings().value(CLAVE_OMITIDA, "")) == nueva.version:
                return
            self.ofrecer(nueva, actual, silencioso)

        def fallo(msj: str) -> None:
            self.buscando = False
            if not silencioso:      # sin internet al abrir la app no se molesta
                QMessageBox.warning(self.ventana, "Actualizaciones", msj)

        self._en_hilo(lambda _h: act.buscar(actual), listo, fallo)

    # ------------------------------------------------------------ ofrecer
    def preguntar(self, n: act.Novedad, actual: str, silencioso: bool) -> str:
        """'actualizar', 'pagina', 'omitir' o 'despues'."""
        caja = QMessageBox(self.ventana)
        caja.setWindowTitle("Hay una versión nueva")
        caja.setIcon(QMessageBox.Icon.Information)
        texto = (f"<h3>LBD Flightcase Maker {html.escape(n.version)}</h3>"
                 f"<p>Tenés la versión {html.escape(actual)}.</p>")
        if n.instalable and act.es_app_instalada():
            mb = f" ({n.tamano / 1e6:.0f} MB)" if n.tamano else ""
            texto += (f"<p>«Actualizar ahora» la descarga{mb}, cierra la app, la instala y la vuelve a abrir.</p>")
        else:
            texto += "<p>Descargala desde la página de la versión en GitHub.</p>"
        caja.setText(texto)
        if n.notas:
            caja.setDetailedText(n.notas)
        botones = {}
        if n.instalable and act.es_app_instalada():
            botones[caja.addButton("Actualizar ahora", QMessageBox.ButtonRole.AcceptRole)] = "actualizar"
        else:
            botones[caja.addButton("Abrir la página", QMessageBox.ButtonRole.AcceptRole)] = "pagina"
        if silencioso:
            botones[caja.addButton("Omitir esta versión", QMessageBox.ButtonRole.DestructiveRole)] = "omitir"
        despues = caja.addButton("Más tarde", QMessageBox.ButtonRole.RejectRole)
        botones[despues] = "despues"
        caja.setEscapeButton(despues)
        caja.exec()
        return botones.get(caja.clickedButton(), "despues")

    def ofrecer(self, n: act.Novedad, actual: str, silencioso: bool = False) -> None:
        r = self.preguntar(n, actual, silencioso)
        if r == "actualizar":
            self.actualizar(n)
        elif r == "pagina":
            QDesktopServices.openUrl(QUrl(n.pagina))
        elif r == "omitir":
            self.settings().setValue(CLAVE_OMITIDA, n.version)

    # --------------------------------------------------------- actualizar
    def actualizar(self, n: act.Novedad) -> None:
        progreso = QProgressDialog(f"Descargando la versión {n.version}…", "Cancelar", 0, 100, self.ventana)
        progreso.setWindowTitle("Actualizar")
        progreso.setMinimumDuration(0)
        progreso.setAutoClose(False)
        progreso.setAutoReset(False)
        progreso.setValue(0)

        cancelado = []

        def bajar(hilo: _Hilo):
            def avance(bajado: int, total: int) -> bool:
                hilo.avance.emit(bajado, total)
                return not cancelado
            return act.descargar(n, progreso=avance)

        def avance(bajado: int, total: int) -> None:
            if total:
                progreso.setValue(int(bajado * 100 / total))
                progreso.setLabelText(f"Descargando la versión {n.version}… "
                                      f"{bajado / 1e6:.0f} de {total / 1e6:.0f} MB")

        def listo(archivo) -> None:
            progreso.close()
            self.instalar(archivo)

        def fallo(msj: str) -> None:
            progreso.close()
            if not cancelado:
                QMessageBox.warning(self.ventana, "Actualizar",
                                    f"{msj}\n\nPodés bajarla a mano desde:\n{n.pagina}")

        progreso.canceled.connect(lambda: cancelado.append(True))
        self._en_hilo(bajar, listo, fallo, avance)

    def instalar(self, archivo) -> None:
        if not self.confirmar_cierre():         # canceló por los cambios sin guardar
            return
        try:
            inst = act.preparar_instalacion(archivo)
            act.lanzar(inst)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self.ventana, "Actualizar", f"No se pudo instalar: {e}")
            return
        if inst.manual:
            QMessageBox.information(self.ventana, "Actualizar", inst.mensaje)
            return
        self.salir()

    def salir(self) -> None:
        """Cierra la app para que el instalador pueda reemplazarla."""
        self.ventana.close()
        QApplication.instance().quit()
