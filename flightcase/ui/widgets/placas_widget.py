"""Pestaña «Placas» del Taller: las piezas del case acomodadas en placas enteras."""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...taller import placas as P

COLORES = ["#e8c99b", "#cfe0c3", "#c9d9ee", "#f0c9c9", "#e3d1ee", "#f5e6a8", "#cde8e6"]
CLAVE_GIRAR = "taller/placasGirar"


def _settings() -> QSettings:
    return QSettings("FlightcaseCalculator", "FlightcaseCalculator")


def girar_permitido() -> bool:
    return _settings().value(CLAVE_GIRAR, True, type=bool)


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


class _Lienzo(QWidget):
    """Dibuja las placas una debajo de la otra, al ancho de la pestaña."""

    MARGEN, TITULO, ENTRE = 12, 22, 18

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.placas: List[Dict[str, Any]] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_placas(self, placas: List[Dict[str, Any]]) -> None:
        self.placas = placas
        self._ajustar_alto()
        self.update()

    def _escala(self) -> float:
        if not self.placas:
            return 1.0
        L = max(pl["L"] for pl in self.placas)
        return max(self.width() - 2 * self.MARGEN, 100) / L

    def _ajustar_alto(self) -> None:
        e = self._escala()
        alto = self.MARGEN + sum(self.TITULO + pl["A"] * e + self.ENTRE for pl in self.placas)
        self.setMinimumHeight(int(alto) + self.MARGEN)

    def resizeEvent(self, ev) -> None:   # noqa: N802 (Qt)
        super().resizeEvent(ev)
        self._ajustar_alto()

    def paintEvent(self, _ev) -> None:   # noqa: N802 (Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        e = self._escala()
        y = float(self.MARGEN)
        x0 = float(self.MARGEN)
        letra = QFont(self.font())
        for i, pl in enumerate(self.placas, 1):
            p.setPen(QColor("#e6e6e6"))
            letra.setBold(True)
            p.setFont(letra)
            p.drawText(QRectF(x0, y, self.width() - 2 * x0, self.TITULO), Qt.AlignmentFlag.AlignVCenter,
                       f"Placa {i} de {len(self.placas)} · {pl['material']} · {_f(pl['L'])} × {_f(pl['A'])} mm · "
                       f"aprovechamiento {round(100 * pl['aprovechamiento'])}%")
            letra.setBold(False)
            y += self.TITULO
            W, H = pl["L"] * e, pl["A"] * e
            yb = y + H                      # el y de la placa crece hacia arriba, como en el DXF
            p.setPen(QPen(QColor("#9a9a9a"), 1))
            p.setBrush(QColor("#f4f1ea"))
            p.drawRect(QRectF(x0, y, W, H))
            for pz in pl["piezas"]:
                r = QRectF(x0 + pz["x"] * e, yb - (pz["y"] + pz["dh"]) * e, pz["dw"] * e, pz["dh"] * e)
                p.setPen(QPen(QColor("#333333"), 1))
                p.setBrush(QColor(COLORES[(pz["num"] - 1) % len(COLORES)]))
                p.drawRect(r)
                texto = f"P{pz['num']}"
                if r.width() > 90 and r.height() > 34:
                    texto += f"  {pz.get('nombre_corto', '')}\n{_f(pz['w'])} × {_f(pz['h'])}" + \
                             ("  (girada)" if pz["rot"] else "")
                letra.setPointSizeF(8 if min(r.width(), r.height()) > 30 else 6.5)
                p.setFont(letra)
                p.setPen(QColor("#202020"))
                p.save()
                if r.height() > r.width() * 1.6 and r.width() < 60:     # pieza angosta y alta: texto vertical
                    p.translate(r.center())
                    p.rotate(-90)
                    p.drawText(QRectF(-r.height() / 2, -r.width() / 2, r.height(), r.width()),
                               Qt.AlignmentFlag.AlignCenter, texto)
                else:
                    p.drawText(r, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, texto)
                p.restore()
            ret = P.retazo_mayor(pl, pl.get("kerf", 0.0))
            if ret[2] * ret[3] > 0 and min(ret[2], ret[3]) > 50:
                r = QRectF(x0 + ret[0] * e, yb - (ret[1] + ret[3]) * e, ret[2] * e, ret[3] * e)
                p.setPen(QPen(QColor("#2f9e44"), 1.2, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(r.adjusted(2, 2, -2, -2))
                if r.width() > 80 and r.height() > 16:
                    letra.setPointSizeF(7.5)
                    p.setFont(letra)
                    p.setPen(QColor("#2b8a3e"))
                    p.drawText(r, Qt.AlignmentFlag.AlignCenter, f"retazo {_f(ret[2])} × {_f(ret[3])}")
            letra.setPointSizeF(self.font().pointSizeF())
            y += H + self.ENTRE
        p.end()


class PlacasWidget(QWidget):
    """Resumen de placas a comprar, dibujo de cada placa y DXF por placa."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._res = None
        self._pendiente = False
        self.placas: List[Dict[str, Any]] = []
        self.piezas: List[Dict[str, Any]] = []
        self.trazos: Dict[int, List[tuple]] = {}
        self.avisos: List[str] = []
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 0)
        fila = QHBoxLayout()
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setTextFormat(Qt.TextFormat.RichText)
        fila.addWidget(self.lbl, 1)
        self.chk_girar = QCheckBox("Girar piezas")
        self.chk_girar.setToolTip("Permite girar piezas 90° para aprovechar mejor la placa. "
                                  "Apagalo si la placa tiene veta o dibujo que hay que respetar.")
        self.chk_girar.setChecked(girar_permitido())
        self.chk_girar.toggled.connect(self._girar_cambiado)
        fila.addWidget(self.chk_girar)
        self.btn_dxf = QPushButton("Guardar DXF de las placas…")
        self.btn_dxf.setToolTip("Un DXF por placa con las piezas en su lugar (calados, rebajes y marcas) "
                                "y placas.csv con el resumen")
        self.btn_dxf.clicked.connect(lambda: self.guardar())
        fila.addWidget(self.btn_dxf)
        raiz.addLayout(fila)
        self.lienzo = _Lienzo()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.lienzo)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        raiz.addWidget(scroll, 1)

    # ------------------------------------------------------------------ datos
    def set_resultado(self, res) -> None:
        """Se calcula al mostrarse la pestaña (acomodar es rápido, pero no hace falta en cada tecla)."""
        self._res = res
        self._pendiente = True
        if self.isVisible():
            self.actualizar()

    def showEvent(self, ev) -> None:   # noqa: N802 (Qt)
        super().showEvent(ev)
        if self._pendiente:
            self.actualizar()

    def actualizar(self) -> None:
        self._pendiente = False
        if self._res is None:
            return
        from ...taller import produccion as PR
        from ...taller.planos import generar as gen
        try:
            d = PR.datos(self._res)
            piezas = gen.agrupar_piezas(d)
            for i, e in enumerate(d["extras"]):
                piezas.append(dict(num=len(piezas) + 1, ids=[f"extra{i + 1}"], cant=e["cant"], nombre=e["nombre"],
                                   w=e["w"], h=e["h"], calados=[], marcas=[], extra=True,
                                   material=e["material"], esp=e["esp"]))
            self.placas, self.avisos = P.armar_placas(d, piezas, rotar=self.chk_girar.isChecked(),
                                                      cantidad=gen.cantidad_cases(d))
            self.piezas = piezas
            self.trazos = {pz["num"]: PR.trazos_manuales(d["manuales"].get(pz["ids"][0], []))
                           for pz in piezas if not pz.get("extra")}
            n_cases = gen.cantidad_cases(d)
        except Exception as e:   # nunca debe impedir ver el resto del Taller
            self.placas, self.avisos, n_cases = [], [f"No se pudieron acomodar las piezas: {e}"], 1
        self.lienzo.set_placas(self.placas)
        partes = [f"<b>{r['placas']} {'placa' if r['placas'] == 1 else 'placas'} de {r['material']}</b> "
                  f"({_f(r['L'])} × {_f(r['A'])}) · aprovechamiento {round(100 * r['aprovechamiento'])}%"
                  + (f" · retazo más grande {_f(r['retazo'][2])} × {_f(r['retazo'][3])}"
                     if r["retazo"][2] * r["retazo"][3] > 0 else "")
                  for r in P.resumen(self.placas)]
        if n_cases > 1:
            partes.append(f"Para {n_cases} cases.")
        partes += [f"<span style='color:#d08a2b'>⚠ {a}</span>" for a in self.avisos]
        self.lbl.setText("<br>".join(partes) or "Sin piezas para acomodar.")
        self.btn_dxf.setEnabled(bool(self.placas))

    def _girar_cambiado(self, si: bool) -> None:
        _settings().setValue(CLAVE_GIRAR, si)
        if self._res is not None:
            self.actualizar()

    # -------------------------------------------------------------- archivos
    def guardar(self, carpeta: Optional[str] = None) -> List[str]:
        if self._pendiente or not self.placas:
            self.actualizar()
        if not self.placas:
            return []
        if not carpeta:
            carpeta = QFileDialog.getExistingDirectory(self, "Carpeta para los DXF de las placas")
            if not carpeta:
                return []
        rutas = P.escribir_dxf_placas(self.placas, self.piezas, os.path.join(carpeta, "placas"), self.trazos)
        ruta_csv = os.path.join(carpeta, "placas.csv")
        with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, delimiter=";").writerows(P.filas_csv(self.placas))
        rutas.append(ruta_csv)
        if self.isVisible():
            QMessageBox.information(self, "Placas", f"Se guardaron {len(rutas) - 1} DXF y placas.csv en:\n"
                                                    f"{os.path.join(carpeta, 'placas')}")
        return rutas
