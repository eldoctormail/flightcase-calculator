"""Ventana «Versiones anteriores»: las copias fechadas de un case, para volver a una."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...taller import versiones as V

_RUTA = Qt.ItemDataRole.UserRole


def _fecha(d: datetime) -> str:
    hoy = datetime.now().date()
    if d.date() == hoy:
        return f"hoy {d:%H:%M}"
    if (hoy - d.date()).days == 1:
        return f"ayer {d:%H:%M}"
    return f"{d:%d/%m/%Y %H:%M}"


def _leer(ruta: str) -> Optional[Dict[str, Any]]:
    from ...taller.scad import leer_proyecto
    try:
        return leer_proyecto(ruta)
    except Exception:
        return None


def _medidas(params: Optional[Dict[str, Any]], carpeta: str) -> str:
    if params is None:
        return "no se pudo leer"
    from ...taller.modelo import calcular
    try:
        v = calcular(dict(params, _carpeta=carpeta)).valores
        return f"{v['ext_ancho']:.0f} × {v['ext_prof']:.0f} × {v['ext_alto']:.0f} mm"
    except Exception:
        return "no se pudo calcular"


def _texto(valor: Any) -> str:
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, (int, float, str)):
        t = str(valor)
        return t if len(t) <= 24 else t[:23] + "…"
    return ""


def diferencias(antes: Dict[str, Any], ahora: Dict[str, Any], etiquetas: Dict[str, str],
                defectos: Dict[str, Any], maximo: int = 3) -> List[str]:
    """Qué cambia de `antes` a `ahora`, con los nombres en castellano («Ancho interior: 600 → 700»)."""
    claves = sorted(k for k in set(antes) | set(ahora)
                    if not k.startswith("_") and antes.get(k, defectos.get(k)) != ahora.get(k, defectos.get(k)))
    salida = []
    for k in claves:
        a, b = antes.get(k, defectos.get(k)), ahora.get(k, defectos.get(k))
        nombre = etiquetas.get(k, k)
        ta, tb = _texto(a), _texto(b)
        salida.append(f"{nombre}: {ta} → {tb}" if ta and tb else nombre)
    if len(salida) > maximo:
        salida = salida[:maximo] + [f"y {len(salida) - maximo} más"]
    return salida


class VersionesDialog(QDialog):
    """`restaurar(ruta_version)` pone esa versión en la ventana del Taller."""

    def __init__(self, parent: Optional[QWidget], ruta_case: str,
                 restaurar: Optional[Callable[[str], None]] = None,
                 etiquetas: Optional[Dict[str, str]] = None,
                 defectos: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(parent)
        self.ruta_case = ruta_case
        self._restaurar = restaurar
        self._etiquetas = etiquetas or {}
        self._defectos = defectos or {}
        self.restaurada: Optional[str] = None
        nombre = os.path.basename(ruta_case)
        self.setWindowTitle(f"Versiones anteriores de {nombre}")
        self.resize(900, 520)

        raiz = QVBoxLayout(self)
        ayuda = QLabel(
            f"Cada vez que se guarda «{nombre}» (a mano o con el autoguardado), lo que había antes queda "
            f"copiado acá con su fecha: una copia cada {V.INTERVALO_MINUTOS} minutos como mucho, y siempre la de "
            "cómo estaba al abrirlo. Se guardan todas las de los últimos dos días, una por día hasta los dos "
            "meses y una por mes después.\n"
            "Restaurar pone esa versión en la ventana sin tocar el archivo: si te sirve, guardala (Ctrl+S) "
            "y la que está ahora también queda entre las versiones.")
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color:#a9b1bd")
        raiz.addWidget(ayuda)

        self.lista = QTreeWidget()
        self.lista.setHeaderLabels(["Fecha", "Medidas exteriores", "Diferencias con el archivo actual (esa versión → ahora)"])
        self.lista.setRootIsDecorated(False)
        self.lista.setAlternatingRowColors(True)
        self.lista.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.lista.itemDoubleClicked.connect(lambda *_: self.restaurar_elegida())
        self.lista.currentItemChanged.connect(lambda *_: self._botones())
        raiz.addWidget(self.lista, 1)

        self.lbl_vacio = QLabel("Todavía no hay versiones anteriores: aparecen desde la segunda vez que se guarda el case.")
        self.lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vacio.setStyleSheet("color:#8a93a3; padding:24px")
        raiz.addWidget(self.lbl_vacio)

        fila = QHBoxLayout()
        self.btn_restaurar = QPushButton("Restaurar en la ventana")
        self.btn_restaurar.setDefault(True)
        self.btn_restaurar.clicked.connect(self.restaurar_elegida)
        fila.addWidget(self.btn_restaurar)
        self.btn_carpeta = QPushButton("Abrir la carpeta de versiones")
        self.btn_carpeta.clicked.connect(self.abrir_carpeta)
        fila.addWidget(self.btn_carpeta)
        fila.addStretch(1)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.reject)
        fila.addWidget(cerrar)
        raiz.addLayout(fila)
        self.recargar()

    def recargar(self) -> None:
        self.lista.clear()
        carpeta = os.path.dirname(os.path.abspath(self.ruta_case))
        actual = _leer(self.ruta_case) or {}
        for v in V.listar(self.ruta_case):
            params = _leer(v.ruta)
            cambios = diferencias(params, actual, self._etiquetas, self._defectos) if params is not None else []
            it = QTreeWidgetItem([_fecha(v.fecha), _medidas(params, carpeta),
                                  "; ".join(cambios) if cambios else "igual al guardado ahora"])
            it.setData(0, _RUTA, v.ruta)
            it.setToolTip(0, f"{v.fecha:%d/%m/%Y %H:%M:%S}\n{v.ruta}")
            it.setToolTip(2, "\n".join(diferencias(params, actual, self._etiquetas, self._defectos, maximo=40))
                          if params is not None else "")
            self.lista.addTopLevelItem(it)
        for c in (0, 1):
            self.lista.resizeColumnToContents(c)
        if self.lista.topLevelItemCount():
            self.lista.setCurrentItem(self.lista.topLevelItem(0))
        vacio = not self.lista.topLevelItemCount()
        self.lista.setVisible(not vacio)
        self.lbl_vacio.setVisible(vacio)
        self.btn_carpeta.setEnabled(os.path.isdir(V.carpeta_versiones(self.ruta_case)))
        self._botones()

    def _botones(self) -> None:
        self.btn_restaurar.setEnabled(self.version_elegida() is not None)

    def version_elegida(self) -> Optional[str]:
        it = self.lista.currentItem()
        return it.data(0, _RUTA) if it is not None else None

    def restaurar_elegida(self) -> None:
        ruta = self.version_elegida()
        if not ruta:
            return
        if self._restaurar:
            try:
                if self._restaurar(ruta) is False:     # canceló (p. ej. al preguntar por cambios sin guardar)
                    return
            except Exception as e:
                QMessageBox.warning(self, "Restaurar versión", f"No se pudo leer esa versión:\n{e}")
                return
        self.restaurada = ruta
        self.accept()

    def abrir_carpeta(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(V.carpeta_versiones(self.ruta_case)))
