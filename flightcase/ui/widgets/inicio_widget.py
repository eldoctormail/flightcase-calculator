"""Pantalla de inicio: empezar un proyecto nuevo eligiendo un estilo de case (por familia o
de la lista completa) o un case guardado como plantilla, con nombre, y la vista previa del
elegido a la derecha. También lleva a «Mis cases», a abrir un archivo o a seguir con el último."""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLayout, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from ...taller import estilos as _estilos
from ...taller import familias as _familias
from ...taller.estilos import Estilo
from .barra_3d import _icono

COLUMNAS = 3
ALTO_IMAGEN = 118


class _Flujo(QLayout):
    """Pone los widgets en fila y pasa a la siguiente cuando no entran (los chips)."""

    def __init__(self, parent: Optional[QWidget] = None, espacio: int = 5) -> None:
        super().__init__(parent)
        self._items = []
        self._esp = espacio
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, ancho: int) -> int:  # noqa: N802
        return self._acomodar(QRect(0, 0, ancho, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._acomodar(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _acomodar(self, rect: QRect, solo_medir: bool) -> int:
        x, y, alto_fila = rect.x(), rect.y(), 0
        for it in self._items:
            t = it.sizeHint()
            if x + t.width() > rect.right() + 1 and alto_fila > 0:
                x, y, alto_fila = rect.x(), y + alto_fila + self._esp, 0
            if not solo_medir:
                it.setGeometry(QRect(QPoint(x, y), t))
            x += t.width() + self._esp
            alto_fila = max(alto_fila, t.height())
        return y + alto_fila - rect.y()


class _Dibujante(QObject):
    """Dibuja miniaturas que faltan en un hilo aparte y avisa cuando están."""

    lista = Signal(str, str)          # clave, ruta del png

    def pedir(self, clave: str, dibujar: Callable[[], Optional[str]]) -> None:
        def correr() -> None:
            ruta = dibujar()
            if ruta:
                try:
                    self.lista.emit(clave, ruta)
                except RuntimeError:        # la pantalla ya se cerró: la miniatura queda para la próxima
                    pass
        QThreadPool.globalInstance().start(correr)


def _imagen(ruta: Optional[str], ancho: int, alto: int) -> QPixmap:
    pm = QPixmap(ruta) if ruta else QPixmap()
    if pm.isNull():
        return pm
    return pm.scaled(QSize(ancho, alto) * 2, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)


class _Tarjeta(QFrame):
    """Una tarjeta: imagen, nombre, texto y (en las familias) un chip por variante."""

    elegida = Signal(object)          # lo que representa la tarjeta (un Estilo o la ruta de un case)

    def __init__(self, titulo: str, texto: str, valor, variantes: Optional[List[Estilo]] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("tarjetaInicio")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("elegida", False)
        self.valor = valor
        self.variantes = variantes or []
        self.chips: Dict[str, QPushButton] = {}
        self._caja_chips: Optional[QWidget] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 10)
        lay.setSpacing(4)
        self.imagen = QLabel()
        self.imagen.setObjectName("imagenTarjeta")
        self.imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.imagen.setFixedHeight(ALTO_IMAGEN)
        lay.addWidget(self.imagen)
        self.marca = QLabel(self.imagen)
        self.marca.setObjectName("marcaElegida")
        self.marca.setPixmap(_icono("check").pixmap(14, 14))
        self.marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.marca.setFixedSize(22, 22)
        self.marca.hide()
        t = QLabel(titulo)
        t.setObjectName("tituloTarjeta")
        t.setWordWrap(True)
        lay.addWidget(t)
        d = QLabel(texto)
        d.setObjectName("textoTarjeta")
        d.setWordWrap(True)
        d.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(d)
        for w in (t, d):
            w.setContentsMargins(10, 0, 10, 0)
        if self.variantes:
            caja = QWidget()
            caja.setObjectName("chipsTarjeta")
            self._caja_chips = caja
            flujo = _Flujo(caja)
            caja.setContentsMargins(10, 4, 10, 0)
            for e in self.variantes:
                c = QPushButton(("★ " if e.propio else "") + _familias.nombre_corto(e))
                c.setObjectName("chipEstilo")
                c.setCheckable(True)
                c.setToolTip(f"<b>{e.nombre}</b><br>{e.descripcion}")
                c.setCursor(Qt.CursorShape.PointingHandCursor)
                c.clicked.connect(lambda _=False, est=e: self.elegida.emit(est))
                flujo.addWidget(c)
                self.chips[e.id] = c
            lay.addWidget(caja)
        lay.addStretch(1)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def poner_imagen(self, ruta: Optional[str]) -> None:
        pm = _imagen(ruta, 200, ALTO_IMAGEN - 8)
        if not pm.isNull():
            pm.setDevicePixelRatio(2)
            self.imagen.setPixmap(pm)

    def marcar(self, elegido) -> None:
        if isinstance(elegido, Estilo):
            mia = (isinstance(self.valor, Estilo) and self.valor.id == elegido.id) or \
                any(e.id == elegido.id for e in self.variantes)
        else:
            mia = isinstance(self.valor, str) and self.valor == elegido
        self.setProperty("elegida", mia)
        self.style().unpolish(self)
        self.style().polish(self)
        self.marca.setVisible(mia)
        self.marca.move(self.imagen.width() - 30, 8)
        for id_, c in self.chips.items():
            c.setChecked(mia and isinstance(elegido, Estilo) and elegido.id == id_)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self.marca.move(self.imagen.width() - 30, 8)
        c = self._caja_chips
        if c is not None:             # los chips pasan de fila: la tarjeta crece lo que haga falta
            m = c.contentsMargins()
            alto = c.layout().heightForWidth(max(10, self.width() - m.left() - m.right())) + m.top() + m.bottom()
            if c.minimumHeight() != alto:
                c.setMinimumHeight(alto)

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton and not self.property("elegida"):
            self.elegida.emit(self.variantes[0] if self.variantes else self.valor)
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        self.window().crear() if hasattr(self.window(), "crear") else None


class PantallaInicio(QDialog):
    """La pantalla de inicio. Al cerrar con exec() == Accepted, `accion` dice qué hacer:
    "crear" (con `estilo` o `plantilla`, y `nombre`), "proyectos", "abrir", "asistente" o "ultimo"."""

    def __init__(self, parent: Optional[QWidget] = None, recientes: Optional[List[str]] = None,
                 ultimo: Optional[str] = None, mostrar_al_abrir: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("pantallaInicio")
        self.setWindowTitle("Proyecto nuevo")
        self.resize(1240, 800)
        self.accion: Optional[str] = None
        self.estilo: Optional[Estilo] = None
        self.plantilla: Optional[str] = None
        self.ultimo = ultimo if ultimo and os.path.isfile(ultimo) else None
        self._recientes = [r for r in (recientes or []) if os.path.isfile(r)]
        self.tarjetas: Dict[str, List[_Tarjeta]] = {"familias": [], "todos": [], "plantillas": []}
        self._por_clave: Dict[str, List[_Tarjeta]] = {}
        self._dibujante = _Dibujante(self)
        self._dibujante.lista.connect(self._miniatura_lista)
        self.lista_estilos = _estilos.todos()
        self.familias = _familias.agrupar(self.lista_estilos)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._armar_nav())
        derecha = QVBoxLayout()
        derecha.setSpacing(0)
        fila = QHBoxLayout()
        fila.setSpacing(0)
        fila.addWidget(self._armar_centro(), 1)
        fila.addWidget(self._armar_vista_previa())
        derecha.addLayout(fila, 1)
        derecha.addWidget(self._armar_pie(mostrar_al_abrir))
        raiz.addLayout(derecha, 1)
        self.elegir(self.familias[0].estilos[0] if self.familias else None)
        self.txt_nombre.setFocus()

    # ------------------------------------------------------------------ armado
    def _armar_nav(self) -> QFrame:
        nav = QFrame()
        nav.setObjectName("navInicio")
        nav.setFixedWidth(220)
        lay = QVBoxLayout(nav)
        lay.setContentsMargins(14, 18, 14, 14)
        lay.setSpacing(4)
        marca = QLabel("<span style='color:#f5a524'>LBD</span><br>Flightcase Maker")
        marca.setObjectName("marcaInicio")
        lay.addWidget(marca)
        lay.addSpacing(18)
        self.botones_nav: Dict[str, QToolButton] = {}
        for clave, texto, icono in (("nuevo", "Proyecto nuevo", "file-plus"), ("proyectos", "Mis cases…", "folder"),
                                    ("abrir", "Abrir archivo…", "folder-open"),
                                    ("asistente", "Asistente…", "wand")):
            b = QToolButton()
            b.setObjectName("botonNavInicio")
            b.setText(texto)
            b.setIcon(_icono(icono))
            b.setIconSize(QSize(16, 16))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setCheckable(clave == "nuevo")
            b.setChecked(clave == "nuevo")
            if clave != "nuevo":
                b.clicked.connect(lambda _=False, c=clave: self._terminar(c))
            lay.addWidget(b)
            self.botones_nav[clave] = b
        lay.addStretch(1)
        if self.ultimo:
            t = QLabel("Seguir con")
            t.setObjectName("etiquetaCampo")
            lay.addWidget(t)
            b = QToolButton()
            b.setObjectName("botonNavInicio")
            b.setText(os.path.splitext(os.path.basename(self.ultimo))[0])
            b.setToolTip(self.ultimo)
            b.setIcon(_icono("history"))
            b.setIconSize(QSize(16, 16))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda: self._terminar("ultimo"))
            lay.addWidget(b)
            self.botones_nav["ultimo"] = b
        return nav

    def _armar_centro(self) -> QFrame:
        centro = QFrame()
        centro.setObjectName("centroInicio")
        lay = QVBoxLayout(centro)
        lay.setContentsMargins(26, 22, 26, 0)
        lay.setSpacing(6)
        t = QLabel("Empezar un proyecto nuevo")
        t.setObjectName("tituloInicio")
        lay.addWidget(t)
        s = QLabel("Elegí un estilo de case o una plantilla, ponele nombre y crealo.")
        s.setObjectName("subtituloInicio")
        lay.addWidget(s)
        lay.addSpacing(8)

        campo = QFrame()
        campo.setObjectName("campoNombre")
        campo.setMaximumWidth(420)
        fc = QHBoxLayout(campo)
        fc.setContentsMargins(10, 4, 10, 4)
        ico = QLabel()
        ico.setPixmap(_icono("cube").pixmap(16, 16))
        fc.addWidget(ico)
        col = QVBoxLayout()
        col.setSpacing(0)
        et = QLabel("Nombre del proyecto")
        et.setObjectName("etiquetaCampo")
        col.addWidget(et)
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setObjectName("nombreProyecto")
        self.txt_nombre.setPlaceholderText("Sin título")
        self.txt_nombre.setToolTip("Con nombre, el case se guarda enseguida en tu carpeta de cases y empieza "
                                   "el autoguardado. Sin nombre, queda sin guardar hasta Ctrl+S.")
        self.txt_nombre.returnPressed.connect(self.crear)
        col.addWidget(self.txt_nombre)
        fc.addLayout(col, 1)
        lay.addWidget(campo)
        lay.addSpacing(8)

        pestanas = QHBoxLayout()
        pestanas.setSpacing(6)
        self.grupo_pestanas = QButtonGroup(self)
        self.paginas = QStackedWidget()
        self.botones_pestana: Dict[str, QPushButton] = {}
        for i, (clave, texto, icono) in enumerate((("familias", "Estilos de case", "sparkles"),
                                                   ("todos", "Todos los estilos", "layout-grid"),
                                                   ("plantillas", "Plantillas", "template"))):
            b = QPushButton(texto)
            b.setObjectName("pestanaInicio")
            b.setIcon(_icono(icono))
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=i: self.paginas.setCurrentIndex(k))
            self.grupo_pestanas.addButton(b)
            pestanas.addWidget(b)
            self.botones_pestana[clave] = b
            self.paginas.addWidget(self._pagina(clave))
        self.botones_pestana["familias"].setChecked(True)
        pestanas.addStretch(1)
        lay.addLayout(pestanas)
        lay.addWidget(self.paginas, 1)
        return centro

    def _pagina(self, clave: str) -> QScrollArea:
        cont = QWidget()
        cont.setObjectName("paginaInicio")
        g = QGridLayout(cont)
        g.setContentsMargins(0, 8, 8, 16)
        g.setSpacing(10)
        if clave == "familias":
            items = [(f.nombre, f.descripcion, f, f.estilos) for f in self.familias]
        elif clave == "todos":
            items = [(("★ " if e.propio else "") + e.nombre, e.descripcion, e, None) for e in self.lista_estilos]
        else:
            items = [(os.path.splitext(os.path.basename(r))[0], self._texto_plantilla(r), r, None)
                     for r in self._recientes[:24]]
        for n, (titulo, texto, valor, variantes) in enumerate(items):
            t = _Tarjeta(titulo, texto, valor, variantes)
            t.elegida.connect(self.elegir)
            g.addWidget(t, n // COLUMNAS, n % COLUMNAS)
            self.tarjetas[clave].append(t)
            self._cargar_imagen(t, valor if not isinstance(valor, _familias.Familia) else valor.estilos[0])
        if not items:
            vacio = QLabel("Todavía no hay cases guardados. Cuando guardes uno, lo vas a poder usar como "
                           "plantilla: se copia todo (medidas, armado, interior y herrajes) en un proyecto nuevo.")
            vacio.setObjectName("subtituloInicio")
            vacio.setWordWrap(True)
            g.addWidget(vacio, 0, 0, 1, COLUMNAS)
        for c in range(COLUMNAS):
            g.setColumnStretch(c, 1)
        g.setRowStretch(g.rowCount(), 1)
        scroll = QScrollArea()
        scroll.setObjectName("scrollInicio")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(cont)
        return scroll

    @staticmethod
    def _texto_plantilla(ruta: str) -> str:
        from ...taller.proyectos import info_proyecto
        try:
            info = info_proyecto(ruta)
        except Exception:  # noqa: BLE001
            info = None
        if info is None or not info.medidas():
            return "Case guardado"
        return " · ".join(x for x in (info.medidas(), info.material) if x)

    def _armar_vista_previa(self) -> QFrame:
        caja = QFrame()
        caja.setObjectName("previaInicio")
        caja.setFixedWidth(330)
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(22, 26, 22, 18)
        lay.setSpacing(6)
        t = QLabel("Cases a medida, listos para el taller.")
        t.setObjectName("tituloPrevia")
        t.setWordWrap(True)
        lay.addWidget(t)
        s = QLabel("Diseñá, armá y prepará la fabricación con las reglas de tu taller.")
        s.setObjectName("subtituloInicio")
        s.setWordWrap(True)
        lay.addWidget(s)
        self.img_previa = QLabel()
        self.img_previa.setObjectName("imagenPrevia")
        self.img_previa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_previa.setMinimumHeight(250)
        lay.addWidget(self.img_previa, 1)
        self.lbl_familia = QLabel()
        self.lbl_familia.setObjectName("familiaPrevia")
        lay.addWidget(self.lbl_familia)
        self.lbl_nombre = QLabel()
        self.lbl_nombre.setObjectName("nombrePrevia")
        self.lbl_nombre.setWordWrap(True)
        lay.addWidget(self.lbl_nombre)
        self.lbl_descripcion = QLabel()
        self.lbl_descripcion.setObjectName("textoTarjeta")
        self.lbl_descripcion.setWordWrap(True)
        lay.addWidget(self.lbl_descripcion)
        linea = QFrame()
        linea.setObjectName("lineaPrevia")
        linea.setFixedHeight(1)
        lay.addSpacing(8)
        lay.addWidget(linea)
        lay.addSpacing(6)
        for icono, titulo, texto in (
                ("cube", "Diseño 3D al detalle", "Cada placa, perfil y herraje, al día mientras cambiás las medidas."),
                ("scissors", "Listo para el taller", "Lista de cortes, DXF por placa y planos del mismo modelo."),
                ("bolt", "Empezás más rápido", "Partís de un estilo o de un case tuyo, no de cero.")):
            fila = QHBoxLayout()
            fila.setSpacing(10)
            ic = QLabel()
            ic.setPixmap(_icono(icono).pixmap(16, 16))
            ic.setAlignment(Qt.AlignmentFlag.AlignTop)
            fila.addWidget(ic)
            col = QVBoxLayout()
            col.setSpacing(0)
            a = QLabel(titulo)
            a.setObjectName("tituloTarjeta")
            b = QLabel(texto)
            b.setObjectName("textoTarjeta")
            b.setWordWrap(True)
            col.addWidget(a)
            col.addWidget(b)
            fila.addLayout(col, 1)
            lay.addLayout(fila)
            lay.addSpacing(4)
        return caja

    def _armar_pie(self, mostrar_al_abrir: bool) -> QFrame:
        pie = QFrame()
        pie.setObjectName("pieInicio")
        lay = QHBoxLayout(pie)
        lay.setContentsMargins(26, 10, 22, 12)
        self.chk_al_abrir = QCheckBox("Mostrar esta pantalla al abrir la app")
        self.chk_al_abrir.setChecked(mostrar_al_abrir)
        lay.addWidget(self.chk_al_abrir)
        lay.addStretch(1)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        lay.addWidget(cancelar)
        self.btn_crear = QPushButton("Crear proyecto")
        self.btn_crear.setObjectName("principal")
        self.btn_crear.setIcon(_icono("arrow-right"))
        self.btn_crear.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.btn_crear.setDefault(True)
        self.btn_crear.clicked.connect(self.crear)
        lay.addWidget(self.btn_crear)
        return pie

    # ------------------------------------------------------------------ miniaturas
    def _cargar_imagen(self, t: _Tarjeta, valor) -> None:
        clave, ruta, dibujar = self._miniatura_de(valor)
        self._por_clave.setdefault(clave, []).append(t)
        if ruta:
            t.poner_imagen(ruta)
        elif dibujar is not None:
            self._dibujante.pedir(clave, dibujar)

    @staticmethod
    def _miniatura_de(valor) -> Tuple[str, Optional[str], Optional[Callable[[], Optional[str]]]]:
        if isinstance(valor, Estilo):
            return f"estilo:{valor.id}", _familias.miniatura(valor), lambda: _familias.dibujar_miniatura(valor)
        from ...taller import proyectos
        return f"case:{valor}", proyectos.miniatura_al_dia(valor), lambda: proyectos.generar_miniatura(valor)

    def _miniatura_lista(self, clave: str, ruta: str) -> None:
        for t in self._por_clave.get(clave, []):
            t.poner_imagen(ruta)
        if clave == self._clave_elegida():
            self._poner_previa(ruta)

    def _clave_elegida(self) -> str:
        return f"estilo:{self.estilo.id}" if self.estilo else f"case:{self.plantilla}"

    def _poner_previa(self, ruta: Optional[str]) -> None:
        pm = _imagen(ruta, 290, 250)
        if not pm.isNull():
            pm.setDevicePixelRatio(2)
        self.img_previa.setPixmap(pm)

    # ------------------------------------------------------------------ elegir y terminar
    def elegir(self, valor) -> None:
        """Elige un estilo o un case guardado (plantilla) y lo muestra a la derecha."""
        if valor is None:
            return
        self.estilo = valor if isinstance(valor, Estilo) else None
        self.plantilla = valor if isinstance(valor, str) else None
        for lista in self.tarjetas.values():
            for t in lista:
                t.marcar(valor)
        if self.estilo is not None:
            fam = _familias.familia_de(self.estilo, self.familias)
            self.lbl_familia.setText((fam.nombre if fam else "Estilo").upper())
            self.lbl_nombre.setText(self.estilo.nombre)
            self.lbl_descripcion.setText(self.estilo.descripcion)
            self._poner_previa(_familias.miniatura(self.estilo))
        else:
            self.lbl_familia.setText("PLANTILLA")
            self.lbl_nombre.setText(os.path.splitext(os.path.basename(self.plantilla))[0])
            self.lbl_descripcion.setText("Copia de este case (medidas, armado, interior y herrajes) en un "
                                         "proyecto nuevo. El original no cambia.")
            from ...taller.proyectos import miniatura_al_dia
            self._poner_previa(miniatura_al_dia(self.plantilla))

    @property
    def nombre(self) -> str:
        return self.txt_nombre.text().strip()

    def crear(self) -> None:
        if self.estilo is None and self.plantilla is None:
            return
        self._terminar("crear")

    def _terminar(self, accion: str) -> None:
        self.accion = accion
        self.accept()
