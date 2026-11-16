"""Asistente de case nuevo: estilo, interior (equipos de la biblioteca), medidas y terminaciones,
paso a paso y sin recorrer todas las secciones del Taller."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ...taller import biblioteca as B
from ...taller import estilos
from ...taller.modelo import calcular, fmt, interior_para_exterior, parametros_por_defecto

U_MM = B.U_MM
ANCHO_RACK = 490.0          # 19" (482,6) más juego y rieles


def _mm(minimo: float = 1, maximo: float = 5000, valor: float = 0) -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setRange(minimo, maximo)
    sp.setDecimals(1)
    sp.setSuffix(" mm")
    sp.setValue(valor)
    return sp


class _PaginaEstilo(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("1. ¿Qué tipo de case?")
        self.setSubTitle("La forma de armado: tapas, bisagras, ruedas y accesorios. Después se puede cambiar.")
        lay = QVBoxLayout(self)
        self.lista = QListWidget()
        for e in estilos.todos():
            item = QListWidgetItem(e.nombre + ("  (propio)" if e.propio else ""))
            item.setData(Qt.UserRole, e.id)
            item.setToolTip(e.descripcion)
            self.lista.addItem(item)
        self.lista.setCurrentRow(0)
        self.lista.currentRowChanged.connect(self._mostrar)
        lay.addWidget(self.lista, 1)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet("font-style:italic")
        lay.addWidget(self.lbl)
        self._mostrar()

    def _mostrar(self, *_args) -> None:
        e = self.estilo()
        self.lbl.setText(e.descripcion if e else "")

    def estilo(self) -> Optional[estilos.Estilo]:
        item = self.lista.currentItem()
        return estilos.buscar(item.data(Qt.UserRole)) if item else None

    def seleccionar(self, id_estilo: str) -> None:
        for i in range(self.lista.count()):
            if self.lista.item(i).data(Qt.UserRole) == id_estilo:
                self.lista.setCurrentRow(i)


class _PaginaInterior(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("2. ¿Qué va adentro?")
        self.setSubTitle("Elegí equipos de tu biblioteca. Con «Abrir la biblioteca…» podés cargar equipos nuevos.")
        lay = QVBoxLayout(self)
        self.grupo = QButtonGroup(self)
        self.opciones: Dict[str, QRadioButton] = {}
        for clave, texto in (("vacio", "Vacío (o lo cargo después)"),
                             ("espuma", "Espuma con calados para mis equipos"),
                             ("rack", "Rack 19\" con mis equipos de rack")):
            rb = QRadioButton(texto)
            self.grupo.addButton(rb)
            self.opciones[clave] = rb
            rb.toggled.connect(self._refrescar)
            lay.addWidget(rb)
        self.lista = QListWidget()
        lay.addWidget(self.lista, 1)
        fila = QHBoxLayout()
        self.btn_bib = QPushButton("Abrir la biblioteca…")
        self.btn_bib.clicked.connect(self._abrir_biblioteca)
        fila.addWidget(self.btn_bib)
        fila.addStretch(1)
        self.lbl_u = QLabel("Unidades de rack:")
        self.sp_u = QSpinBox()
        self.sp_u.setRange(1, 60)
        self.sp_u.setToolTip("Por defecto, la suma de los equipos elegidos. Subilo para dejar lugar libre.")
        fila.addWidget(self.lbl_u)
        fila.addWidget(self.sp_u)
        lay.addLayout(fila)
        self.chk_medidas = QCheckBox("Calcular las medidas del case a partir de los equipos")
        self.chk_medidas.setChecked(True)
        lay.addWidget(self.chk_medidas)
        self.lbl_vacia = QLabel()
        self.lbl_vacia.setWordWrap(True)
        self.lbl_vacia.setStyleSheet("color:#bbbbbb")
        lay.addWidget(self.lbl_vacia)
        self._u_tocado = False
        self.sp_u.valueChanged.connect(lambda *_: setattr(self, "_u_tocado", True))
        self.lista.itemChanged.connect(self._sugerir_u)
        self.opciones["vacio"].setChecked(True)
        self._u_tocado = False

    def modo(self) -> str:
        return next(k for k, rb in self.opciones.items() if rb.isChecked())

    def _refrescar(self, *_args) -> None:
        modo = self.modo()
        rack = modo == "rack"
        elegidos = {e.nombre for e in self.elegidos()}
        self.lista.blockSignals(True)
        self.lista.clear()
        equipos = [e for e in B.cargar() if (e.es_rack if rack else True)] if modo != "vacio" else []
        for e in equipos:
            medidas = (f"{e.u} U, fondo {fmt(e.fondo)} mm" if rack else
                       f"{fmt(e.fila_equipos()[1])} × {fmt(e.fondo)} × {fmt(e.fila_equipos()[3])} mm")
            item = QListWidgetItem(f"{e.nombre}  —  {medidas}" + (f"  ({e.categoria})" if e.categoria else ""))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if e.nombre in elegidos else Qt.Unchecked)
            item.setData(Qt.UserRole, e)
            self.lista.addItem(item)
        self.lista.blockSignals(False)
        for w in (self.lista, self.btn_bib, self.chk_medidas):
            w.setVisible(modo != "vacio")
        self.lbl_u.setVisible(rack)
        self.sp_u.setVisible(rack)
        if modo != "vacio" and not equipos:
            self.lbl_vacia.setText("No hay equipos " + ("de rack (con U) " if rack else "") +
                                   "en tu biblioteca todavía. Abrila para cargarlos.")
        else:
            self.lbl_vacia.setText("")
        self._sugerir_u()

    def _sugerir_u(self, *_args) -> None:
        if self.modo() == "rack" and not self._u_tocado:
            self.sp_u.blockSignals(True)
            self.sp_u.setValue(max(1, sum(e.u for e in self.elegidos())))
            self.sp_u.blockSignals(False)

    def elegidos(self) -> List[B.EquipoBiblio]:
        out = []
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            if item.checkState() == Qt.Checked:
                out.append(item.data(Qt.UserRole))
        return out

    def elegir(self, nombres: List[str]) -> None:
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole).nombre in nombres else Qt.Unchecked)

    def _abrir_biblioteca(self) -> None:
        from .biblioteca_widget import BibliotecaDialog
        BibliotecaDialog(self).exec()
        self._refrescar()


class _PaginaMedidas(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("3. Medidas")
        self.setSubTitle("Interiores (el espacio útil) o exteriores (lo que mide el case por fuera, sin ruedas).")
        lay = QVBoxLayout(self)
        fila = QHBoxLayout()
        self.rb_interior = QRadioButton("Medidas interiores")
        self.rb_exterior = QRadioButton("Medidas exteriores")
        self.rb_interior.setChecked(True)
        for rb in (self.rb_interior, self.rb_exterior):
            rb.toggled.connect(self._etiquetas)
            fila.addWidget(rb)
        fila.addStretch(1)
        lay.addLayout(fila)
        form = QFormLayout()
        d = parametros_por_defecto()
        self.sp_ancho = _mm(valor=d["int_ancho"])
        self.sp_largo = _mm(valor=d["int_prof"])
        self.sp_alto = _mm(valor=d["int_alto_cuerpo"] + d["int_alto_tapa"])
        self.sp_tapa = _mm(valor=d["int_alto_tapa"])
        self.lbl_ancho, self.lbl_largo, self.lbl_alto = QLabel(), QLabel(), QLabel()
        form.addRow(self.lbl_ancho, self.sp_ancho)
        form.addRow(self.lbl_largo, self.sp_largo)
        form.addRow(self.lbl_alto, self.sp_alto)
        form.addRow(QLabel("Alto de tapa (interior)"), self.sp_tapa)
        lay.addLayout(form)
        self.lbl_nota = QLabel()
        self.lbl_nota.setWordWrap(True)
        self.lbl_nota.setStyleSheet("color:#bbbbbb")
        lay.addWidget(self.lbl_nota)
        lay.addStretch(1)
        self._etiquetas()

    def _etiquetas(self, *_args) -> None:
        cual = "exterior" if self.rb_exterior.isChecked() else "interior"
        self.lbl_ancho.setText(f"Ancho {cual}")
        self.lbl_largo.setText(f"Largo {cual}")
        self.lbl_alto.setText(f"Alto {cual}" + (" (total, con la tapa)" if cual == "interior" else ""))

    def initializePage(self) -> None:   # noqa: N802 (nombre de Qt)
        sug = self.wizard().medidas_sugeridas()
        if sug:
            self.rb_interior.setChecked(True)
            self.sp_ancho.setValue(sug["int_ancho"])
            self.sp_largo.setValue(sug["int_prof"])
            self.sp_alto.setValue(sug["int_alto_cuerpo"] + self.sp_tapa.value())
            self.lbl_nota.setText(sug.get("nota", "Medidas calculadas a partir de los equipos elegidos."))
        else:
            self.lbl_nota.setText("")


# Ruedas que ofrece el asistente: clave, texto y explicación
RUEDAS_ASISTENTE = [
    ("no", "Sin ruedas", "El case va sin ruedas."),
    ("giratorias", "4 giratorias (2 con freno)", "Lo más común: las 4 giran y 2 tienen freno."),
    ("fijas", "2 giratorias con freno + 2 fijas", "Como un carro: adelante giran y frenan, atrás van fijas y el case va derecho."),
    ("cazoletas", "4 giratorias en cazoleta (más bajo)",
     "Cada rueda va embutida en una cazoleta de acero en el piso: el case queda más bajo."),
    ("suelta", "Base suelta con ruedas (wheel board)",
     "Una tabla con ruedas y un marco de ángulo donde se apoya el case; el piso no se perfora."),
]


class _PaginaTerminaciones(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("4. Terminaciones")
        self.setSubTitle("Lo más común. El resto se ajusta después en las secciones del Taller.")
        form = QFormLayout(self)
        d = parametros_por_defecto()
        self.sp_placa = _mm(3, 30, d["placa_esp"])
        form.addRow("Espesor de la placa", self.sp_placa)
        self.cmb_ruedas = QComboBox()
        for clave, texto, ayuda in RUEDAS_ASISTENTE:
            self.cmb_ruedas.addItem(texto, clave)
            self.cmb_ruedas.setItemData(self.cmb_ruedas.count() - 1, ayuda, Qt.ToolTipRole)
        form.addRow("Ruedas", self.cmb_ruedas)
        self.chk_manijas = QCheckBox("Manijas embutidas")
        self.chk_manijas.setChecked(bool(d["manijas"]))
        form.addRow("Manijas", self.chk_manijas)
        self.sp_forro = _mm(0, 50, d["espuma_esp"])
        self.sp_forro.setToolTip("Espuma pegada en todas las caras interiores. 0 = sin forro.")
        form.addRow("Forro de espuma", self.sp_forro)

    def initializePage(self) -> None:   # noqa: N802
        e = self.wizard().pagina_estilo.estilo()
        p = estilos.aplicar(parametros_por_defecto(), e, parametros_por_defecto()) if e else parametros_por_defecto()
        self.cmb_ruedas.setCurrentIndex(self.cmb_ruedas.findData("giratorias" if int(p.get("ruedas", 0)) > 0 else "no"))

    def ruedas(self) -> str:
        return self.cmb_ruedas.currentData() or "no"
        self.chk_manijas.setChecked(bool(p.get("manijas", True)))
        self.sp_placa.setValue(float(p.get("placa_esp", 9)))


class _PaginaResumen(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("5. Listo")
        self.setSubTitle("Así queda el case. Al tocar «Terminar» se abre en el Taller para seguir ajustándolo.")
        lay = QVBoxLayout(self)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setTextFormat(Qt.RichText)
        lay.addWidget(self.lbl)
        lay.addStretch(1)

    def initializePage(self) -> None:   # noqa: N802
        try:
            p = self.wizard().armar_params()
            res = calcular(p)
        except Exception as e:  # medidas que el modelo no admite
            self.lbl.setText(f"No se pudo armar el case con estos datos: {e}")
            return
        v = res.valores
        e = self.wizard().pagina_estilo.estilo()
        avisos = "".join(f"<li>{a}</li>" for a in list(dict.fromkeys(res.avisos))[:8])
        self.lbl.setText(
            f"<b>{e.nombre if e else 'Case'}</b><br>"
            f"Exterior: {fmt(v['ext_ancho'])} × {fmt(v['ext_prof'])} × {fmt(v['ext_alto'])} mm<br>"
            f"Interior: {fmt(p['int_ancho'])} × {fmt(p['int_prof'])} mm, cuerpo {fmt(p['int_alto_cuerpo'])} mm "
            f"+ tapa {fmt(p['int_alto_tapa'])} mm<br>"
            f"{len(res.paneles)} paneles · {len(p.get('equipos') or [])} equipos en la espuma · "
            f"{len(p.get('rack_equipos') or [])} equipos de rack"
            + (f"<br><br>Avisos para revisar después:<ul>{avisos}</ul>" if avisos else ""))


class AsistenteCase(QWizard):
    """Arma los parámetros de un case nuevo. `params` queda con el resultado al terminar."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Asistente de case nuevo")
        self.setWizardStyle(QWizard.ClassicStyle)
        self.resize(720, 560)
        self.setButtonText(QWizard.NextButton, "Siguiente >")
        self.setButtonText(QWizard.BackButton, "< Atrás")
        self.setButtonText(QWizard.FinishButton, "Terminar")
        self.setButtonText(QWizard.CancelButton, "Cancelar")
        self.pagina_estilo = _PaginaEstilo()
        self.pagina_interior = _PaginaInterior()
        self.pagina_medidas = _PaginaMedidas()
        self.pagina_terminaciones = _PaginaTerminaciones()
        self.pagina_resumen = _PaginaResumen()
        for p in (self.pagina_estilo, self.pagina_interior, self.pagina_medidas, self.pagina_terminaciones,
                  self.pagina_resumen):
            self.addPage(p)
        self.params: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ lógica
    def _orientacion(self) -> str:
        e = self.pagina_estilo.estilo()
        return (e.params.get("orientacion") if e else None) or "vertical"

    def medidas_sugeridas(self) -> Optional[Dict[str, Any]]:
        pi = self.pagina_interior
        elegidos = pi.elegidos()
        if pi.modo() == "vacio" or not elegidos or not pi.chk_medidas.isChecked():
            return None
        d = parametros_por_defecto()
        if pi.modo() == "rack":
            fondo = max(e.fondo + e.sobresale for e in elegidos)
            return {"int_ancho": ANCHO_RACK, "int_prof": round(pi.sp_u.value() * U_MM + 10, 1),
                    "int_alto_cuerpo": round(fondo + d["rack_retiro"] + d["rack_cables"], 1),
                    "nota": f"Ancho para 19\", alto para {pi.sp_u.value()} U y profundidad para el equipo más "
                            "largo, con lugar para cables atrás y perillas adelante."}
        sug = B.acomodar_en_espuma(elegidos, d["espuma_holgura"], d["espuma_pared_min"], d["espuma_fondo_min"],
                                   plancha=d["espuma_plancha"])
        if self._orientacion() != "vertical":
            sug["nota"] = ("Medidas calculadas con los equipos uno al lado del otro, como en un case vertical: "
                           "revisá la ubicación en la tabla de equipos.")
        return sug

    def armar_params(self) -> Dict[str, Any]:
        defectos = parametros_por_defecto()
        p: Dict[str, Any] = dict(defectos)
        pm, pt, pi = self.pagina_medidas, self.pagina_terminaciones, self.pagina_interior
        tapa = pm.sp_tapa.value()
        p["int_alto_tapa"] = tapa
        p["placa_esp"] = pt.sp_placa.value()
        p["espuma_esp"] = pt.sp_forro.value()
        elegidos = pi.elegidos()
        if pi.modo() == "espuma" and elegidos:
            sug = self.medidas_sugeridas() or B.acomodar_en_espuma(
                elegidos, defectos["espuma_holgura"], defectos["espuma_pared_min"], defectos["espuma_fondo_min"])
            p["equipos"] = sug["equipos"]
            p["espumas"] = [[0, 0, 0]]          # un bloque que llena el cuerpo
        elif pi.modo() == "rack" and elegidos:
            p["rack_u"] = pi.sp_u.value()
            p["rack_equipos"] = [e.fila_rack() for e in elegidos]
        exterior = pm.rb_exterior.isChecked()
        ancho, largo, alto = pm.sp_ancho.value(), pm.sp_largo.value(), pm.sp_alto.value()
        if not exterior:
            if alto <= tapa:
                raise ValueError("el alto interior tiene que ser mayor que el alto de tapa")
            p.update(int_ancho=ancho, int_prof=largo, int_alto_cuerpo=round(alto - tapa, 1))
        e = self.pagina_estilo.estilo()

        def con_estilo(q: Dict[str, Any]) -> Dict[str, Any]:
            q = estilos.aplicar(q, e, defectos) if e else q
            q["placa_esp"] = pt.sp_placa.value()          # lo elegido en el asistente manda sobre el estilo
            q["espuma_esp"] = pt.sp_forro.value()
            r = pt.ruedas()
            q["ruedas"] = 0 if r == "no" else 4
            q["rueda_fijas"] = 2 if r == "fijas" else 0
            q["cazoletas"] = r == "cazoletas"
            q["base_suelta"] = r == "suelta"
            if r in ("no", "cazoletas", "suelta"):
                q["base_ruedas"] = []
            q["manijas"] = pt.chk_manijas.isChecked()
            return q

        p = con_estilo(p)
        if exterior:
            p.update(interior_para_exterior(p, ancho, largo, alto))
            p = con_estilo(p)                           # base de ruedas automática con las medidas finales
        return p

    def accept(self) -> None:
        try:
            self.params = self.armar_params()
        except ValueError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Asistente de case nuevo", str(e))
            return
        super().accept()
