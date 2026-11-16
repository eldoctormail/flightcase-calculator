"""Vista 3D del taller: tapas que abren sobre su bisagra, cajones que salen, piezas ocultas,
y la interfaz nueva (barra lateral, panel «Vista», barra de datos y cubo de vistas)."""

import pytest

from flightcase.taller.geometria import malla_3d
from flightcase.taller.modelo import calcular
from flightcase.taller.vista import EstadoVista, VistaCase, tapas_del_case

RACK = dict(orientacion="frontal", tapas=2, int_ancho=515, int_prof=1100, int_alto_cuerpo=720,
            int_alto_tapa=105, placa_esp=10, cajones=[[200, 0], [200, 200]], rack_u=6, rack_desde=420)
VALIJA = dict(int_ancho=600, int_prof=400, int_alto_cuerpo=250, int_alto_tapa=80, espumas=[[0, 0, 120]])


def _vista(params):
    res = calcular(params)
    return res, VistaCase(malla_3d(res), res)


def _zmax(caras):
    return max(p.z for f in caras for p in f.vertices)


def test_tapas_segun_la_orientacion():
    assert [t.nombre for t in tapas_del_case(calcular(RACK))] == ["Tapa delantera", "Tapa trasera"]
    assert [t.nombre for t in tapas_del_case(calcular(VALIJA))] == ["Tapa"]
    hz = tapas_del_case(calcular(dict(VALIJA, orientacion="horizontal", tapas=2)))
    assert [(t.eje, t.signo) for t in hz] == [(0, -1), (0, 1)]


def test_cerrada_es_la_malla_original():
    res, v = _vista(VALIJA)
    m = v.aplicar(EstadoVista())
    assert len(m.faces) == len(v.malla.faces)
    assert m.bounding_box == v.malla.bounding_box
    assert {g.categoria for g in v.grupos} >= {"paneles", "perfiles", "herrajes", "espuma"}
    assert any(g.tapa == 1 for g in v.grupos) and any(g.tapa == 0 for g in v.grupos)


def test_tapa_abierta_gira_sobre_la_bisagra_de_atras():
    res, v = _vista(VALIJA)
    Z, Y = res.valores["ext_alto"], res.valores["ext_prof"]
    abierta = v.aplicar(EstadoVista(tapas=[1.0, 0.0]))
    cuerpo = [f for g in v.grupos if g.tapa == 0 for f in v.malla.faces[g.desde:g.hasta]]
    tapa = [f for f in abierta.faces if f not in set(cuerpo)]
    assert len(abierta.faces) == len(v.malla.faces)
    # la tapa queda parada atrás: sube por encima del case y no pasa hacia el frente
    assert _zmax(tapa) > Z + 200
    assert min(p.y for f in tapa for p in f.vertices) > Y - 150
    # el cuerpo no se movió y la cámara tampoco
    assert set(cuerpo) <= set(abierta.faces)
    assert abierta.bounding_box == v.malla.bounding_box


def test_tapa_delantera_de_un_rack_sube_hacia_adelante():
    res, v = _vista(RACK)
    abierta = v.aplicar(EstadoVista(tapas=[1.0, 0.0]))
    tapa1 = [f for g in v.grupos if g.tapa == 1 for f in v.malla.faces[g.desde:g.hasta]]
    nuevas = [f for f in abierta.faces if f not in set(v.malla.faces)]
    assert len(nuevas) == len(tapa1)
    # abierta queda arriba, como un alero hacia adelante (y < 0)
    assert min(p.y for f in nuevas for p in f.vertices) < -50
    assert min(p.z for f in nuevas for p in f.vertices) > res.valores["ext_prof"] - 150


def test_ocultar_tapas_partes_y_grupos():
    res, v = _vista(RACK)
    total = len(v.malla.faces)
    sin_tapa = v.aplicar(EstadoVista(tapas_ocultas=[True, False]))
    n_tapa1 = sum(g.hasta - g.desde for g in v.grupos if g.tapa == 1)
    assert len(sin_tapa.faces) == total - n_tapa1
    assert v.ocultas(EstadoVista(tapas_ocultas=[True, False])) == ["tapa delantera"]
    solo_cuerpo = v.aplicar(EstadoVista(seccion="cuerpo"))
    solo_tapas = v.aplicar(EstadoVista(seccion="tapas"))
    assert len(solo_cuerpo.faces) + len(solo_tapas.faces) == total
    sin_herrajes = v.aplicar(EstadoVista(ocultos={"herrajes", "perfiles"}))
    interior = {"Riel de rack", "Carátula ciega", "Cajón 1 (corredera)", "Cajón 2 (corredera)"}
    assert not any(f.color_group in ("herraje", "cierre", "remache", "profile", "aluminio")
                   for f in sin_herrajes.faces if f.label not in interior)   # el interior va aparte
    sin_cajones = v.aplicar(EstadoVista(ocultos={"cajones"}))
    assert not any(f.label.startswith("Cajón") for f in sin_cajones.faces)
    assert "Riel de rack" in {f.label for f in sin_cajones.faces}    # el rack es otra categoría


def test_cajon_sale_hacia_el_frente():
    res, v = _vista(RACK)
    assert v.cantidad_cajones == 2
    largo = res.valores["interiores"].cajones[0]["largo"]
    antes = {f.label: min(p.y for p in f.vertices) for f in v.malla.faces if f.label == "Cajón 1 (frente)"}
    afuera = v.aplicar(EstadoVista(cajones={0: 1.0}))
    despues = min(p.y for f in afuera.faces if f.label == "Cajón 1 (frente)" for p in f.vertices)
    assert despues == pytest.approx(antes["Cajón 1 (frente)"] - 0.9 * largo)
    # el otro cajón no se movió
    c2 = [f for f in afuera.faces if f.label == "Cajón 2 (frente)"]
    assert c2 and all(f in set(v.malla.faces) for f in c2)


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_barra_lateral_y_panel_vista(qapp):
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    assert w.grupo_actual() == "medidas"
    assert "Ruedas" in w.secciones_de_grupo["ruedas"]
    assert any(s.startswith("Interior") for s in w.secciones_de_grupo["interior"])
    assert all(w.secciones_de_grupo[c] for c in ("medidas", "armado", "herrajes", "ruedas", "interior"))
    w.botones_lateral["vista"].click()
    assert w.grupo_actual() == "vista" and w.lbl_grupo.text() == "Vista"
    w.btn_panel.setChecked(False)
    assert w.panel_izq.isHidden()
    w.mostrar_grupo("ruedas")             # elegir un grupo vuelve a mostrar el panel
    assert not w.panel_izq.isHidden()
    assert w.datos["paneles"].text() == str(len(w.resultado.paneles))
    assert "×" in w.datos["medida"].text()


def test_panel_vista_abre_oculta_y_saca_cajones(qapp):
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    w.set_params(dict(RACK))
    pv = w.panel_vista
    assert pv.nombres_tapas == ["Tapa delantera", "Tapa trasera"]
    assert len(pv.sliders) == 2 and not pv.btn_sacar.isHidden()
    assert w.chk_interior.isChecked()          # con interior, se abre la tapa delantera
    assert pv.estado.tapas == [1.0, 0.0]
    cerrada = len(w.vista_3d.mesh.faces)
    pv.ocultar_tapa(0, True)
    assert len(w.vista_3d.mesh.faces) < cerrada
    assert "tapa delantera" in w.lbl_oculto.text() and not pv.btn_abrir[0].isEnabled()
    pv.mover_cajones(1.0)
    assert pv.estado.cajones == {0: 1.0, 1: 1.0} and pv.sliders[0].value() == 100
    pv.chk_ocultar["paneles"].setChecked(True)
    assert not any(f.color_group in ("base", "lid") for f in w.vista_3d.mesh.faces)
    pv.abrir_todas(False)
    assert pv.estado.tapas == [0.0, 0.0] and not w.chk_interior.isChecked()
    # botones sobre la vista 3D, uno para abrir y otro para ocultar cada tapa
    textos = [w.barra_tapas.itemAt(i).widget().text() for i in range(w.barra_tapas.count())]
    assert textos == ["Abrir tapa delantera", "Mostrar tapa delantera", "Abrir tapa trasera", "Ocultar tapa trasera"]
    pv.chk_fondo.setChecked(True)
    assert w.vista_3d.fondo_claro


def test_cubo_de_vistas(qapp):
    from PySide6.QtCore import QPointF
    from flightcase.ui.widgets.schema_3d_widget import Schema3DCanvas
    c = Schema3DCanvas()
    c.resize(600, 400)
    caras = {vista: poly for poly, vista, _, _ in c._armar_cubo()}
    assert set(caras) == {"frente", "derecha", "arriba"}       # desde la isométrica
    centro = caras["frente"].boundingRect().center()
    assert c.vista_en_cubo(centro) == "frente"
    assert c.vista_en_cubo(QPointF(10, 390)) is None
    c.set_vista("frente")
    assert {v for _, v, _, _ in c._armar_cubo()} == {"frente"}
