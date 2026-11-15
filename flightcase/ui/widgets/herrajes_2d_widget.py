"""Pestaña «Herrajes a mano»: vista 2D de cada cara del case para agregar, mover, girar,
espejar y copiar herrajes, con guías en la junta de cierre de la tapa.

Las posiciones se guardan en el parámetro ``herrajes_manuales`` (ver
flightcase/taller/herrajes_manuales.py) y el resto (calados, DXF, lista, 3D, planos,
instructivo) sale del modelo del taller.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...taller import herrajes_manuales as hm
from ...taller.modelo import CatalogoTaller, ResultadoTaller, fmt

NOMBRE_CATEGORIA = {"manija": "Manija", "cierre": "Cierre", "bisagra": "Bisagra", "tope": "Tope", "pie": "Pie",
                    "rueda": "Rueda", "rueda_otra": "Rueda", "plato": "Plato de apilado", "escuadra": "Escuadra",
                    "extra": "Extra", "esquinero": "Esquinero", "rack": "Rack"}
PIEZA_PROPIA = "__propia__"

C_FONDO = QColor("#ffffff")
C_CUERPO = QColor("#ead6b0")
C_TAPA = QColor("#dcc79f")
C_BORDE = QColor("#5b4a32")
C_ALU = QColor(176, 184, 194, 150)
C_JUNTA = QColor("#c0392b")
C_AUTO = QColor("#6b7280")
C_MANUAL = QColor("#1f5fbf")
C_SEL = QColor("#e67e22")
C_GUIA = QColor("#d6336c")
C_COTA = QColor("#1f5fbf")


def _num(minimo: float, maximo: float, decimales: int = 1, sufijo: str = " mm") -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(minimo, maximo)
    w.setDecimals(decimales)
    w.setSuffix(sufijo)
    w.setKeyboardTracking(False)
    return w


class Lienzo2D(QWidget):
    """Dibujo de una cara: paneles, aluminio, juntas, herrajes automáticos (gris) y a mano (azul)."""

    seleccionado = Signal(int)             # índice de la fila (-1: ninguna)
    movido = Signal(int, float, float)     # al soltar: índice, x, y (vista)
    moviendo = Signal(int, float, float)   # mientras se arrastra
    doble_clic = Signal(float, float)      # en un lugar vacío: agregar ahí

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.cara: Optional[hm.Cara] = None
        self.auto: List[Dict[str, Any]] = []          # formas en la vista
        self.manuales: List[Dict[str, Any]] = []      # idx, rect, forma, lineas, nombre, aviso
        self.sel = -1
        self.iman = True
        self.paso = 1.0
        self._arrastre: Optional[Tuple[int, float, float]] = None   # idx, dx, dy
        self._mov: Optional[Tuple[float, float]] = None
        self._guias: List[Tuple[str, float]] = []

    # --------------------------------------------------------------- datos
    def set_datos(self, cara: Optional[hm.Cara], auto: List[Dict[str, Any]], manuales: List[Dict[str, Any]],
                  sel: int) -> None:
        self.cara, self.auto, self.manuales, self.sel = cara, auto, manuales, sel
        self._arrastre = None
        self._mov = None
        self._guias = []
        self.update()

    # --------------------------------------------------------- transformar
    def _escala(self) -> Tuple[float, float, float]:
        c = self.cara
        if c is None:
            return 1.0, 0.0, 0.0
        m = 46.0
        w, h = max(self.width() - 2 * m, 10), max(self.height() - 2 * m, 10)
        k = min(w / max(c.ancho, 1), h / max(c.alto, 1))
        ox = (self.width() - c.ancho * k) / 2
        oy = (self.height() + c.alto * k) / 2
        return k, ox, oy

    def a_pantalla(self, x: float, y: float) -> QPointF:
        k, ox, oy = self._escala()
        return QPointF(ox + x * k, oy - y * k)

    def a_mm(self, p: QPointF) -> Tuple[float, float]:
        k, ox, oy = self._escala()
        return (p.x() - ox) / k, (oy - p.y()) / k

    def _rect(self, r: Sequence[float]) -> QRectF:
        a, b = self.a_pantalla(r[0], r[3]), self.a_pantalla(r[2], r[1])
        return QRectF(a, b).normalized()

    # --------------------------------------------------------------- dibujo
    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), C_FONDO)
        c = self.cara
        if c is None:
            p.setPen(C_AUTO)
            p.drawText(self.rect(), Qt.AlignCenter, "Sin case calculado")
            return
        k, _, _ = self._escala()
        chico = QFont(self.font())
        chico.setPointSizeF(max(self.font().pointSizeF() - 1.5, 7))
        p.setFont(chico)
        # paneles
        for pc in c.paneles:
            r = self._rect(c.rect_a_vista(c.rect_panel(pc)))
            p.setPen(QPen(C_BORDE, 1))
            p.setBrush(C_TAPA if pc.grupo.startswith("tapa") else C_CUERPO)
            p.drawRect(r)
        # aluminio
        p.setPen(Qt.NoPen)
        p.setBrush(C_ALU)
        for a in c.aluminio:
            p.drawRect(self._rect(c.rect_a_vista(a)))
        p.setPen(QColor("#6b5838"))
        for pc in c.paneles:
            r = self._rect(c.rect_a_vista(c.rect_panel(pc)))
            p.drawText(r, Qt.AlignCenter, pc.nombre)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C_BORDE, 1.4))
        p.drawRect(self._rect((0, 0, c.ancho, c.alto)))
        # juntas de cierre
        for j in c.juntas:
            if j["horizontal"]:
                a, b = c.a_vista(0, j["fv"]), c.a_vista(c.W, j["fv"])
            else:
                a, b = c.a_vista(j["fu"], j["v0"]), c.a_vista(j["fu"], j["v1"])
            p.setPen(QPen(C_JUNTA, 1.3, Qt.DashLine))
            pa, pb = self.a_pantalla(*a), self.a_pantalla(*b)
            p.drawLine(pa, pb)
            p.setPen(C_JUNTA)
            izq = pa if pa.x() <= pb.x() else pb
            p.drawText(QPointF(min(pa.x(), pb.x()) + 4, min(pa.y(), pb.y()) - 4) if abs(pa.y() - pb.y()) < 1
                       else QPointF(izq.x() + 4, max(pa.y(), pb.y()) - 4), j["nombre"])
        # ejes de la cara
        p.setPen(QPen(QColor(150, 150, 150), 0.8, Qt.DotLine))
        p.drawLine(self.a_pantalla(c.ancho / 2, 0), self.a_pantalla(c.ancho / 2, c.alto))
        p.drawLine(self.a_pantalla(0, c.alto / 2), self.a_pantalla(c.ancho, c.alto / 2))
        # herrajes automáticos
        for f in self.auto:
            self._forma(p, f, C_AUTO, False)
        # herrajes a mano
        for f in self.manuales:
            if f["idx"] == self.sel:
                continue
            self._forma(p, self._movida(f), C_MANUAL, True)
        sel = next((f for f in self.manuales if f["idx"] == self.sel), None)
        if sel is not None:
            fs = self._movida(sel)
            self._forma(p, fs, C_SEL, True)
            self._cotas(p, fs)
        # guías del imán
        p.setPen(QPen(C_GUIA, 1, Qt.DashLine))
        for eje, v in self._guias:
            if eje == "x":
                p.drawLine(self.a_pantalla(v, -c.alto * 0.03), self.a_pantalla(v, c.alto * 1.03))
            else:
                p.drawLine(self.a_pantalla(-c.ancho * 0.03, v), self.a_pantalla(c.ancho * 1.03, v))
        # rótulo de la vista
        p.setPen(QColor("#555"))
        p.drawText(QRectF(6, 4, self.width() - 12, 18), Qt.AlignLeft,
                   f"{c.nombre}: vista desde afuera, {fmt(c.ancho)} × {fmt(c.alto)} mm")
        p.end()

    def _movida(self, f: Dict[str, Any]) -> Dict[str, Any]:
        if self._mov is None or f["idx"] != self.sel:
            return f
        dx, dy = self._mov[0] - f["x"], self._mov[1] - f["y"]
        r = f["rect"]
        return dict(f, x=self._mov[0], y=self._mov[1], rect=(r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy),
                    lineas=[[(a + dx, b + dy) for a, b in l] for l in f.get("lineas", [])])

    def _forma(self, p: QPainter, f: Dict[str, Any], color: QColor, manual: bool) -> None:
        r = self._rect(f["rect"])
        forma = f["forma"]
        relleno = QColor(color)
        relleno.setAlpha(45 if manual else 25)
        p.setBrush(relleno)
        p.setPen(QPen(color, 1.6 if manual else 1, Qt.SolidLine if forma in ("calado", "agujero") else Qt.DashLine))
        if forma in ("pie", "agujero"):
            p.drawEllipse(r)
        elif forma == "cruz":
            c = r.center()
            p.setPen(QPen(color, 1.4))
            p.drawLine(QPointF(c.x() - 6, c.y()), QPointF(c.x() + 6, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - 6), QPointF(c.x(), c.y() + 6))
        else:
            rad = min(f.get("radio", 0) * self._escala()[0], r.width() / 2, r.height() / 2)
            p.drawRoundedRect(r, rad, rad)
        if f.get("lineas"):
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(color, 1.1))
            for l in f["lineas"]:
                camino = QPainterPath(self.a_pantalla(*l[0]))
                for q in l[1:]:
                    camino.lineTo(self.a_pantalla(*q))
                p.drawPath(camino)
        if manual:
            for a in f.get("agujeros", []):
                p.setPen(QPen(color, 1))
                p.drawEllipse(self._rect(a))
            p.setPen(color if not f.get("aviso") else QColor("#b03a2e"))
            txt = ("⚠ " if f.get("aviso") else "") + f["nombre"]
            p.drawText(QRectF(r.left() - 60, r.top() - 17, r.width() + 120, 16), Qt.AlignHCenter | Qt.AlignBottom, txt)

    def _cotas(self, p: QPainter, f: Dict[str, Any]) -> None:
        """Distancias del centro a los bordes izquierdo y de abajo, y a la junta más cercana."""
        c = self.cara
        x, y = f["x"], f["y"]
        p.setPen(QPen(C_COTA, 1))
        a, b = self.a_pantalla(0, y), self.a_pantalla(x, y)
        p.drawLine(a, b)
        p.drawText(QPointF((a.x() + b.x()) / 2 - 14, a.y() - 4), fmt(round(x, 1)))
        a, b = self.a_pantalla(x, 0), self.a_pantalla(x, y)
        p.drawLine(a, b)
        p.drawText(QPointF(a.x() + 4, (a.y() + b.y()) / 2), fmt(round(y, 1)))
        d = distancia_junta(c, x, y)
        if d is not None and f["forma"] != "junta":
            dist, (jx, jy) = d
            a, b = self.a_pantalla(x, y), self.a_pantalla(jx, jy)
            p.setPen(QPen(C_JUNTA, 1, Qt.DotLine))
            p.drawLine(a, b)
            p.setPen(C_JUNTA)
            p.drawText(QPointF((a.x() + b.x()) / 2 + 4, (a.y() + b.y()) / 2 - 2), f"{fmt(round(dist, 1))} a la junta")

    # --------------------------------------------------------------- mouse
    def _en(self, x: float, y: float) -> int:
        candidatos = []
        for f in self.manuales:
            r = f["rect"]
            margen = 4 / self._escala()[0]
            if r[0] - margen <= x <= r[2] + margen and r[1] - margen <= y <= r[3] + margen:
                candidatos.append(((r[2] - r[0]) * (r[3] - r[1]), f["idx"]))
        return min(candidatos)[1] if candidatos else -1

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        self.setFocus()
        if self.cara is None or ev.button() != Qt.LeftButton:
            return
        x, y = self.a_mm(ev.position())
        idx = self._en(x, y)
        if idx != self.sel:
            self.sel = idx
            self.seleccionado.emit(idx)
        if idx >= 0:
            f = next(f for f in self.manuales if f["idx"] == idx)
            self._arrastre = (idx, f["x"] - x, f["y"] - y)
        self.update()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._arrastre is None:
            return
        idx, dx, dy = self._arrastre
        x, y = self.a_mm(ev.position())
        f = next((f for f in self.manuales if f["idx"] == idx), None)
        if f is None:
            return
        nx, ny = x + dx, y + dy
        if self.iman and not (ev.modifiers() & Qt.AltModifier):
            nx, ny, self._guias = self.imantar(f, nx, ny)
        else:
            self._guias = []
        self._mov = (nx, ny)
        self.moviendo.emit(idx, nx, ny)
        self.update()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if self._arrastre is not None and self._mov is not None:
            idx = self._arrastre[0]
            x, y = self._mov
            self._arrastre = None
            self._guias = []
            self.movido.emit(idx, x, y)
            return
        self._arrastre = None

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        if self.cara is None:
            return
        x, y = self.a_mm(ev.position())
        if self._en(x, y) < 0 and 0 <= x <= self.cara.ancho and 0 <= y <= self.cara.alto:
            self.doble_clic.emit(round(x / self.paso) * self.paso, round(y / self.paso) * self.paso)

    # ---------------------------------------------------------------- imán
    def imantar(self, f: Dict[str, Any], x: float, y: float) -> Tuple[float, float, List[Tuple[str, float]]]:
        """Acerca el centro (o un borde) a la guía más cercana: bordes y ejes de la cara, juntas
        de cierre y bordes del aluminio, y los centros de los otros herrajes."""
        c = self.cara
        tol = 8 / self._escala()[0]
        w, h = f["rect"][2] - f["rect"][0], f["rect"][3] - f["rect"][1]
        gx, gy = guias(c, [g for g in self.manuales if g["idx"] != f["idx"]] + self.auto)
        guias_v: List[Tuple[str, float]] = []

        def mejor(v: float, mitad: float, lista: List[float]) -> Tuple[float, Optional[float]]:
            opciones = []
            for g in lista:
                for off in (0.0, -mitad, mitad):   # centro, borde de abajo/izq., borde de arriba/der.
                    d = abs(v + off - g)
                    if d <= tol:
                        opciones.append((d, g - off, g))
            if not opciones:
                return v, None
            _, nv, g = min(opciones)
            return nv, g

        nx, g = mejor(x, w / 2, gx)
        if g is None:
            nx = round(x / self.paso) * self.paso
        else:
            guias_v.append(("x", g))
        ny, g = mejor(y, h / 2, gy)
        if g is None:
            ny = round(y / self.paso) * self.paso
        else:
            guias_v.append(("y", g))
        return nx, ny, guias_v

    # -------------------------------------------------------------- teclado
    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if self.sel < 0:
            return super().keyPressEvent(ev)
        paso = 10.0 if ev.modifiers() & Qt.ShiftModifier else max(self.paso, 1.0)
        mov = {Qt.Key_Left: (-paso, 0), Qt.Key_Right: (paso, 0), Qt.Key_Up: (0, paso), Qt.Key_Down: (0, -paso)}
        if ev.key() in mov:
            f = next((f for f in self.manuales if f["idx"] == self.sel), None)
            if f is not None:
                dx, dy = mov[ev.key()]
                self.movido.emit(self.sel, f["x"] + dx, f["y"] + dy)
            return
        super().keyPressEvent(ev)


def guias(c: hm.Cara, otros: Sequence[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    """Coordenadas (vista) donde se imanta un herraje: x y y por separado."""
    gx = [0.0, c.ancho / 2, c.ancho]
    gy = [0.0, c.alto / 2, c.alto]
    for a in c.aluminio:
        r = c.rect_a_vista(a)
        for v in (r[0], r[2]):
            if 0.5 < v < c.ancho - 0.5:
                gx.append(v)
        for v in (r[1], r[3]):
            if 0.5 < v < c.alto - 0.5:
                gy.append(v)
    for j in c.juntas:
        if j["horizontal"]:
            a, b = c.a_vista(0, j["fv"]), c.a_vista(c.W, j["fv"])
        else:
            a, b = c.a_vista(j["fu"], 0), c.a_vista(j["fu"], c.H)
        if abs(a[0] - b[0]) < 0.01:
            gx.append(a[0])
        else:
            gy.append(a[1])
    for o in otros:
        gx.append(o["x"])
        gy.append(o["y"])
    return gx, gy


def distancia_junta(c: Optional[hm.Cara], x: float, y: float) -> Optional[Tuple[float, Tuple[float, float]]]:
    """Distancia (vista) del punto a la junta de cierre más cercana y el pie de esa distancia."""
    if c is None:
        return None
    mejor = None
    fu, fv = c.a_cara(x, y)
    for j in c.juntas:
        if j["horizontal"]:
            d, pie = abs(fv - j["fv"]), c.a_vista(fu, j["fv"])
        else:
            d, pie = abs(fu - j["fu"]), c.a_vista(j["fu"], fv)
        if mejor is None or d < mejor[0]:
            mejor = (d, pie)
    return mejor


class HerrajesManualesWidget(QWidget):
    """Editor de ``herrajes_manuales`` sobre la vista 2D de cada cara."""

    cambiado = Signal(list)    # la lista nueva, para el parámetro herrajes_manuales

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.cat = CatalogoTaller()
        self.filas: List[hm.Fila] = []
        self.res: Optional[ResultadoTaller] = None
        self.caras: Dict[str, hm.Cara] = {}
        self.sel = -1
        self.carpeta = ""          # carpeta del .scad (para guardar el logo con ruta relativa)
        self._init_ui()

    # ------------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)

        f1 = QHBoxLayout()
        f1.addWidget(QLabel("Cara:"))
        self.cmb_cara = QComboBox()
        self.cmb_cara.currentIndexChanged.connect(lambda *_: self._refrescar(cambio_cara=True))
        f1.addWidget(self.cmb_cara)
        f1.addWidget(QLabel("Herraje:"))
        self.cmb_ref = QComboBox()
        self.cmb_ref.setMinimumContentsLength(14)
        self.cmb_ref.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        for fila in hm.catalogo_colocable(self.cat):
            self.cmb_ref.addItem(f"{NOMBRE_CATEGORIA.get(fila['categoria'], fila['categoria'])} · {fila['nombre']} "
                                 f"({fila['ref']})", fila["ref"])
        self.cmb_ref.addItem("Pieza propia (nombre y medida)…", PIEZA_PROPIA)
        f1.addWidget(self.cmb_ref, 1)
        self.btn_agregar = QPushButton("Agregar")
        self.btn_agregar.setToolTip("Agrega el herraje elegido en el centro de la cara (o hacé doble clic en la cara)")
        self.btn_agregar.clicked.connect(lambda: self.agregar())
        f1.addWidget(self.btn_agregar)
        self.btn_logo = QPushButton("Logo…")
        self.btn_logo.setToolTip("Placa de logo a partir de un dibujo .svg o .dxf")
        self.btn_logo.clicked.connect(lambda: self.agregar_logo())
        f1.addWidget(self.btn_logo)
        raiz.addLayout(f1)

        f2 = QHBoxLayout()
        self.sp_x, self.sp_y = _num(-10000, 10000), _num(-10000, 10000)
        self.sp_x.setToolTip("Centro, desde el borde izquierdo de la cara vista desde afuera")
        self.sp_y.setToolTip("Centro, desde el borde de abajo de la cara vista desde afuera")
        self.cmb_giro = QComboBox()
        self.cmb_giro.addItems(["0°", "90°", "180°", "270°"])
        self.chk_espejo = QCheckBox("Volteado")
        self.sp_ancho, self.sp_alto = _num(0, 5000), _num(0, 5000)
        self.sp_ancho.setToolTip("Ancho de la pieza (logos, extras y piezas propias)")
        self.sp_alto.setToolTip("Alto de la pieza (0 en un logo: según la proporción del dibujo)")
        self.cmb_modo = QComboBox()
        self.cmb_modo.addItems(["placa", "grabado"])
        self.cmb_modo.setToolTip("Logo: placa remachada o grabado sobre la madera (capa GRABADO del DXF)")
        f2b = QHBoxLayout()      # en dos filas, así entra en una pantalla de notebook
        for fila, etiqueta, w in ((f2, "X", self.sp_x), (f2, "Y", self.sp_y), (f2, "Giro", self.cmb_giro),
                                  (f2, "", self.chk_espejo), (f2b, "Ancho", self.sp_ancho), (f2b, "Alto", self.sp_alto),
                                  (f2b, "", self.cmb_modo)):
            if etiqueta:
                fila.addWidget(QLabel(etiqueta))
            fila.addWidget(w)
        f2.addStretch(1)
        f2b.addStretch(1)
        raiz.addLayout(f2)
        raiz.addLayout(f2b)
        self.sp_x.valueChanged.connect(self._editado)
        self.sp_y.valueChanged.connect(self._editado)
        self.cmb_giro.currentIndexChanged.connect(self._editado)
        self.chk_espejo.toggled.connect(self._editado)
        self.sp_ancho.valueChanged.connect(self._editado)
        self.sp_alto.valueChanged.connect(self._editado)
        self.cmb_modo.currentIndexChanged.connect(self._editado)

        f3 = QHBoxLayout()
        self.botones: Dict[str, QPushButton] = {}
        for clave, texto, ayuda, slot in (
                ("copiar", "Copiar", "Duplica el herraje al lado (Ctrl+D)", self.copiar),
                ("espejar", "Espejar", "Pone el mismo herraje, simétrico, en la cara de enfrente",
                 self.espejar),
                ("girar", "Girar", "Gira el herraje 90° (R)", self.girar),
                ("reemplazar", "Reemplazar", "Cambia el herraje por el elegido arriba, en el mismo lugar",
                 self.reemplazar),
                ("quitar", "Quitar", "Quita el herraje (Supr)", self.quitar)):
            b = QPushButton(texto)
            b.setToolTip(ayuda)
            b.clicked.connect(slot)
            f3.addWidget(b)
            self.botones[clave] = b
        f3.addStretch(1)
        self.chk_iman = QCheckBox("Imán")
        self.chk_iman.setChecked(True)
        self.chk_iman.setToolTip("Al arrastrar, se pega a la junta de cierre, al aluminio, a los ejes de la cara y a "
                                 "los otros herrajes (Alt lo suelta)")
        self.chk_iman.toggled.connect(lambda v: setattr(self.lienzo, "iman", v))
        f3.addWidget(self.chk_iman)
        f3.addWidget(QLabel("Paso"))
        self.sp_paso = _num(0.5, 100, 1)
        self.sp_paso.setValue(1)
        self.sp_paso.valueChanged.connect(lambda v: setattr(self.lienzo, "paso", v))
        f3.addWidget(self.sp_paso)
        raiz.addLayout(f3)

        self.lienzo = Lienzo2D(self)
        self.lienzo.seleccionado.connect(self._seleccionar)
        self.lienzo.movido.connect(self._movido)
        self.lienzo.moviendo.connect(self._moviendo)
        self.lienzo.doble_clic.connect(lambda x, y: self.agregar(x, y))
        raiz.addWidget(self.lienzo, 1)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        raiz.addWidget(self.lbl_info)

        for tecla, slot in (("Delete", self.quitar), ("Backspace", self.quitar), ("Ctrl+D", self.copiar),
                            ("R", self.girar)):
            atajo = QShortcut(QKeySequence(tecla), self.lienzo)
            atajo.setContext(Qt.WidgetShortcut)
            atajo.activated.connect(slot)
        self._mostrar_seleccion()

    # ------------------------------------------------------------ entrada
    def set_resultado(self, res: Optional[ResultadoTaller], filas: Sequence[Any], carpeta: str = "") -> None:
        """Lo llama la pestaña Taller después de cada cálculo."""
        self.res = res
        self.carpeta = carpeta
        nuevas = [hm.Fila.de(e) for e in (filas or [])]
        self.filas = [f for f in nuevas if f is not None]
        if len(self.filas) != len(nuevas):   # filas mal escritas a mano en el .scad: se descartan
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._emitir)
        if self.sel >= len(self.filas):
            self.sel = -1
        actual = self.cmb_cara.currentData()
        self.caras = {c.id: c for c in hm.caras(res)} if res is not None else {}
        self.cmb_cara.blockSignals(True)
        self.cmb_cara.clear()
        for cid in hm.CARAS:
            c = self.caras.get(cid)
            if c is not None:
                n = sum(1 for f in self.filas if f.cara == cid)
                self.cmb_cara.addItem(c.nombre + (f"  ({n})" if n else ""), cid)
        i = self.cmb_cara.findData(actual) if actual else 0
        self.cmb_cara.setCurrentIndex(max(i, 0))
        self.cmb_cara.blockSignals(False)
        self._refrescar()

    def cara_actual(self) -> Optional[hm.Cara]:
        return self.caras.get(self.cmb_cara.currentData())

    def set_cara(self, cid: str) -> None:
        i = self.cmb_cara.findData(cid)
        if i >= 0:
            self.cmb_cara.setCurrentIndex(i)

    # ------------------------------------------------------------ dibujo
    def _formas_auto(self, c: hm.Cara) -> List[Dict[str, Any]]:
        res = self.res
        man = res.valores.get("manuales")
        propias = {id(x) for x in (man.calados + man.marcas)} if man is not None else set()
        ids = {p.id: p for p in c.paneles}
        out = []

        def rect_vista(pc, x0, y0, x1, y1):
            a = c.a_vista(*c.panel_a_cara(pc, x0, y0))
            b = c.a_vista(*c.panel_a_cara(pc, x1, y1))
            return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

        for k in res.calados:
            pc = ids.get(k.panel)
            if pc is None or id(k) in propias or k.tipo == "rebaje":
                continue
            r = rect_vista(pc, k.cx - k.ancho / 2, k.cy - k.alto / 2, k.cx + k.ancho / 2, k.cy + k.alto / 2)
            out.append(dict(forma="agujero" if k.tipo == "agujero" else "calado", rect=r, radio=k.radio,
                            x=(r[0] + r[2]) / 2, y=(r[1] + r[3]) / 2, nombre=k.tipo))
        for m in res.marcas:
            pc = ids.get(m.panel)
            if pc is None or id(m) in propias:
                continue
            w, h = (m.ancho or 12), (m.alto or 12)
            if m.tipo in ("cierre", "bisagra", "cierre_acceso"):
                w = h = 12
            r = rect_vista(pc, m.x - w / 2, m.y - h / 2, m.x + w / 2, m.y + h / 2)
            forma = "pie" if m.tipo == "pie" else ("cruz" if w == 12 and h == 12 else "superficie")
            out.append(dict(forma=forma, rect=r, x=(r[0] + r[2]) / 2, y=(r[1] + r[3]) / 2, nombre=m.tipo))
        return out

    def _formas_manuales(self, c: hm.Cara) -> List[Dict[str, Any]]:
        man = self.res.valores.get("manuales") if self.res is not None else None
        if man is None:
            return []
        out = []
        for col in man.colocados:
            if col.cara != c.id:
                continue
            agujeros = []
            for k in col.calados:
                if k.tipo.startswith("agujero") and col.panel:
                    pc = c.panel(col.panel)
                    a = c.a_vista(*c.panel_a_cara(pc, k.cx - k.ancho / 2, k.cy - k.alto / 2))
                    b = c.a_vista(*c.panel_a_cara(pc, k.cx + k.ancho / 2, k.cy + k.alto / 2))
                    agujeros.append((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])))
            out.append(dict(idx=col.indice, x=col.x, y=col.y, rect=col.rect_vista, forma=col.forma,
                            lineas=col.lineas, nombre=col.nombre, aviso=" ".join(col.avisos), agujeros=agujeros,
                            radio=float(col.datos.get("radio", 0)) if col.forma == "calado" else 0))
        return out

    def _refrescar(self, cambio_cara: bool = False) -> None:
        c = self.cara_actual()
        if cambio_cara and self.sel >= 0 and (self.sel >= len(self.filas) or self.filas[self.sel].cara != (c.id if c else "")):
            self.sel = -1
        if c is None or self.res is None:
            self.lienzo.set_datos(None, [], [], -1)
        else:
            self.lienzo.set_datos(c, self._formas_auto(c), self._formas_manuales(c), self.sel)
        self._mostrar_seleccion()

    def _mostrar_seleccion(self) -> None:
        f = self.filas[self.sel] if 0 <= self.sel < len(self.filas) else None
        for w in (self.sp_x, self.sp_y, self.cmb_giro, self.chk_espejo, self.sp_ancho, self.sp_alto, self.cmb_modo):
            w.blockSignals(True)
        try:
            for b in self.botones.values():
                b.setEnabled(f is not None)
            for w in (self.sp_x, self.sp_y, self.cmb_giro, self.chk_espejo, self.sp_ancho, self.sp_alto, self.cmb_modo):
                w.setEnabled(f is not None)
            col = self._colocado(self.sel)
            if f is None:
                n = len([x for x in self.filas if x.cara == self.cmb_cara.currentData()])
                self.lbl_info.setText(
                    "Elegí un herraje y tocá «Agregar» (o doble clic en la cara). Arrastralo para moverlo: se pega a "
                    "la junta de cierre, al borde del aluminio y a los otros herrajes. Flechas: 1 mm (Mayús: 10 mm)."
                    + (f" En esta cara hay {n} a mano." if n else ""))
                return
            x, y = (col.x, col.y) if col is not None else (f.x, f.y)
            self.sp_x.setValue(x)
            self.sp_y.setValue(y)
            self.cmb_giro.setCurrentIndex(f.giro // 90)
            self.chk_espejo.setChecked(f.espejo)
            self.sp_ancho.setValue(f.ancho if f.ancho else (col.ancho if col is not None and f.giro % 180 == 0 else
                                                           (col.alto if col is not None else 0)))
            self.sp_alto.setValue(f.alto)
            self.cmb_modo.setCurrentText(f.modo)
            libre = col is not None and col.forma in ("logo", "superficie", "manija_sup")
            self.sp_ancho.setEnabled(libre)
            self.sp_alto.setEnabled(libre)
            self.cmb_modo.setEnabled(f.ref == "logo")
            self.chk_espejo.setEnabled(f.ref == "logo")
            if col is not None and col.forma == "junta":
                # se mueve sólo a lo largo de la junta (en un rack la junta se ve vertical)
                c = self.caras.get(f.cara)
                (self.sp_x if c is not None and c.giro % 2 else self.sp_y).setEnabled(False)
                self.cmb_giro.setEnabled(False)
            self.lbl_info.setText(self._texto_info(f, col, x, y))
        finally:
            for w in (self.sp_x, self.sp_y, self.cmb_giro, self.chk_espejo, self.sp_ancho, self.sp_alto, self.cmb_modo):
                w.blockSignals(False)

    def _texto_info(self, f: hm.Fila, col, x: float, y: float) -> str:
        c = self.cara_actual()
        partes = [f"<b>{col.nombre if col is not None else f.ref}</b>"]
        if c is not None:
            partes.append(f"centro a {fmt(round(x, 1))} mm de la izquierda y {fmt(round(y, 1))} mm de abajo "
                          f"(a {fmt(round(c.ancho - x, 1))} de la derecha, {fmt(round(c.alto - y, 1))} de arriba)")
            d = distancia_junta(c, x, y)
            if d is not None and (col is None or col.forma != "junta"):
                partes.append(f"a {fmt(round(d[0], 1))} mm de la junta de cierre")
        if col is not None and col.forma == "junta":
            partes.append("centrado en la junta de cierre (va en el cuerpo y en la tapa)")
        if col is not None and col.panel:
            nombre = next((p.nombre for p in self.res.paneles if p.id == col.panel), col.panel)
            partes.append(f"en {nombre}: {fmt(round(col.px, 1))}, {fmt(round(col.py, 1))} desde su esquina")
        txt = " · ".join(partes)
        if col is not None and col.avisos:
            txt += "<br><span style='color:#b03a2e'>⚠ " + "<br>⚠ ".join(col.avisos) + "</span>"
        return txt

    def _colocado(self, idx: int):
        man = self.res.valores.get("manuales") if self.res is not None else None
        if man is None or idx < 0:
            return None
        return next((c for c in man.colocados if c.indice == idx), None)

    # ----------------------------------------------------------- acciones
    def _emitir(self) -> None:
        self.cambiado.emit([f.lista() for f in self.filas])

    def _seleccionar(self, idx: int) -> None:
        self.sel = idx
        self._mostrar_seleccion()

    def _moviendo(self, idx: int, x: float, y: float) -> None:
        f = self.filas[idx] if 0 <= idx < len(self.filas) else None
        if f is not None:
            self.lbl_info.setText(self._texto_info(f, None, x, y))

    def _movido(self, idx: int, x: float, y: float) -> None:
        if 0 <= idx < len(self.filas):
            self.sel = idx
            self.filas[idx] = replace(self.filas[idx], x=round(x, 2), y=round(y, 2))
            self._emitir()

    def _editado(self, *_args) -> None:
        if not 0 <= self.sel < len(self.filas):
            return
        f = self.filas[self.sel]
        col = self._colocado(self.sel)
        libre = col is not None and col.forma in ("logo", "superficie", "manija_sup")
        self.filas[self.sel] = replace(
            f, x=round(self.sp_x.value(), 2), y=round(self.sp_y.value(), 2), giro=self.cmb_giro.currentIndex() * 90,
            espejo=self.chk_espejo.isChecked(), ancho=self.sp_ancho.value() if libre else f.ancho,
            alto=self.sp_alto.value() if libre else f.alto, modo=self.cmb_modo.currentText())
        self._emitir()

    def agregar(self, x: Optional[float] = None, y: Optional[float] = None, ref: Optional[str] = None) -> None:
        c = self.cara_actual()
        if c is None:
            return
        ref = ref or self.cmb_ref.currentData()
        ancho = alto = 0.0
        if ref == PIEZA_PROPIA:
            nombre, ok = QInputDialog.getText(self, "Pieza propia", "Nombre de la pieza (va a la lista de materiales):")
            if not ok or not nombre.strip():
                return
            ref, ancho, alto = nombre.strip(), 50.0, 50.0
        x = c.ancho / 2 if x is None else x
        y = c.alto / 2 if y is None else y
        self.filas.append(hm.Fila(ref, c.id, round(x, 2), round(y, 2), ancho=ancho, alto=alto))
        self.sel = len(self.filas) - 1
        self._emitir()

    def agregar_logo(self, ruta: Optional[str] = None, ancho: float = 150.0) -> None:
        c = self.cara_actual()
        if c is None:
            return
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Dibujo del logo", self.carpeta,
                                                  "Dibujos vectoriales (*.svg *.dxf)")
        if not ruta:
            return
        guardar = ruta
        if self.carpeta:
            try:
                rel = os.path.relpath(ruta, self.carpeta)
                if not rel.startswith(".."):
                    guardar = rel.replace(os.sep, "/")
            except ValueError:   # otra unidad en Windows
                pass
        self.filas.append(hm.Fila("logo", c.id, round(c.ancho / 2, 2), round(c.alto / 2, 2), ancho=ancho,
                                  archivo=guardar))
        self.sel = len(self.filas) - 1
        self._emitir()

    def copiar(self) -> None:
        if not 0 <= self.sel < len(self.filas):
            return
        f = self.filas[self.sel]
        c = self.caras.get(f.cara)
        col = self._colocado(self.sel)
        if col is not None and col.forma == "junta" and c is not None and c.giro % 2:
            paso = col.alto + 20     # junta vertical en la vista: se copia hacia arriba o abajo
            y = col.y + paso if col.y + paso < c.alto else col.y - paso
            self.filas.append(replace(f, x=round(col.x, 2), y=round(y, 2)))
        else:
            paso = (col.ancho if col is not None else 40) + 20
            x = f.x + paso if c is None or f.x + paso < c.ancho else f.x - paso
            self.filas.append(replace(f, x=round(x, 2)))
        self.sel = len(self.filas) - 1
        self._emitir()

    def espejar(self) -> None:
        if not 0 <= self.sel < len(self.filas):
            return
        f = self.filas[self.sel]
        c = self.caras.get(f.cara)
        if c is None:
            return
        nueva = hm.espejar(f, c)
        self.filas.append(nueva)
        self.sel = len(self.filas) - 1
        self._emitir()
        self.set_cara(nueva.cara)

    def girar(self) -> None:
        if 0 <= self.sel < len(self.filas):
            f = self.filas[self.sel]
            self.filas[self.sel] = replace(f, giro=(f.giro + 90) % 360)
            self._emitir()

    def reemplazar(self) -> None:
        ref = self.cmb_ref.currentData()
        if not 0 <= self.sel < len(self.filas) or ref == PIEZA_PROPIA:
            return
        f = self.filas[self.sel]
        self.filas[self.sel] = replace(f, ref=ref, ancho=0.0, alto=0.0, archivo="", modo="placa")
        self._emitir()

    def quitar(self) -> None:
        if 0 <= self.sel < len(self.filas):
            del self.filas[self.sel]
            self.sel = -1
            self._emitir()
