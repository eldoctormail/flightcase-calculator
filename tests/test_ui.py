"""Ventana principal: solo el Taller."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def clean_settings():
    s = QSettings("FlightcaseCalculator", "FlightcaseCalculator")
    s.clear()
    s.sync()
    yield
    s.clear()
    s.sync()


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _scad(tmp_path, nombre, ancho):
    ruta = tmp_path / nombre
    ruta.write_text(f"int_ancho = {ancho};\nflightcase();\n", encoding="utf-8")
    return str(ruta)


def test_ventana_y_barra_de_estado(qapp):
    from flightcase.ui import FlightCaseMainWindow
    from flightcase.ui.widgets import TallerWidget
    w = FlightCaseMainWindow(restore_settings=False)
    assert isinstance(w.centralWidget(), TallerWidget)
    assert "case nuevo" in w.windowTitle()
    assert "Exterior:" in w.status_bar.currentMessage() and "paneles" in w.status_bar.currentMessage()
    w.close()


def test_vuelve_a_abrir_el_ultimo_scad(qapp, tmp_path):
    from flightcase.ui import FlightCaseMainWindow
    ruta = _scad(tmp_path, "rack.scad", 482)
    w1 = FlightCaseMainWindow()
    w1.abrir(ruta)
    w1.close()                              # guarda la sesión
    w2 = FlightCaseMainWindow()
    assert w2.taller_widget.ruta == ruta and w2.taller_widget.params["int_ancho"] == 482
    assert "rack.scad" in w2.windowTitle()
    w2.close()
    w3 = FlightCaseMainWindow(load_last_project=False)
    assert w3.taller_widget.ruta is None
    w3.close()


def test_menu_de_recientes(qapp, tmp_path):
    from flightcase.ui import FlightCaseMainWindow
    w = FlightCaseMainWindow(restore_settings=False)
    assert not w.recent_menu.isEnabled()
    rutas = [_scad(tmp_path, f"c{i}.scad", 400 + i) for i in range(10)]
    for r in rutas:
        w.abrir(r)
    acciones = w.recent_menu.actions()
    assert len(acciones) == 8 and acciones[0].text() == "&1 c9.scad"
    acciones[3].trigger()                   # c6
    assert w.taller_widget.params["int_ancho"] == 406
    assert w.recent_menu.actions()[0].text() == "&1 c6.scad"
    w._taller_nuevo()
    assert w.taller_widget.ruta is None and "case nuevo" in w.windowTitle()
    w.close()


def test_vista_3d_del_taller(qapp):
    from flightcase.ui.widgets import Schema3DCanvas
    from flightcase.taller.geometria import Opciones3D, malla_3d
    from flightcase.taller.modelo import calcular
    canvas = Schema3DCanvas()
    canvas.set_mesh(malla_3d(calcular({}), Opciones3D()))
    assert canvas.mesh.faces
    canvas.close()


def test_case_desde_medidas_exteriores(qapp):
    import json
    from pathlib import Path
    from flightcase.taller.modelo import calcular, interior_para_exterior
    from flightcase.ui.widgets import TallerWidget
    for caso in ("rack_dsnake", "anvil_absen"):
        p = json.loads((Path(__file__).parent / "golden" / "taller" / f"{caso}.json").read_text(encoding="utf-8"))["params"]
        p.update(interior_para_exterior(p, 700, 400, 800))
        v = calcular(p).valores
        assert (v["ext_ancho"], v["ext_prof"], v["ext_alto"]) == pytest.approx((700, 400, 800), abs=0.1)
    with pytest.raises(ValueError):
        interior_para_exterior({}, 15, 400, 800)
    w = TallerWidget()
    alto_tapa = w.params["int_alto_tapa"]
    w.poner_exterior(800, 500, 600)
    v = w.resultado.valores
    assert (v["ext_ancho"], v["ext_prof"], v["ext_alto"]) == pytest.approx((800, 500, 600), abs=0.1)
    assert w.params["int_alto_tapa"] == alto_tapa                       # la tapa queda igual
    assert w.editores["int_ancho"].valor() == w.params["int_ancho"]
    assert [round(s.value()) for s in w.ext_spins] == [800, 500, 600]


def test_botones_de_la_vista_3d(qapp):
    from PySide6.QtCore import QPointF, Qt
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    c, b = w.vista_3d, w.barra_3d.botones
    b["acercar"].click()
    assert c.zoom_factor == pytest.approx(1.25)
    b["alejar"].click()
    b["alejar"].click()
    assert c.zoom_factor == pytest.approx(0.8)
    b["mover"].setChecked(True)
    assert c.modo_raton == "mover" and c.cursor().shape() == Qt.CursorShape.OpenHandCursor
    assert not b["orbitar"].isChecked()
    c.mover(30, -10)
    assert (c.pan_offset_x, c.pan_offset_y) == (30, -10)
    b["encuadrar"].click()
    assert (c.zoom_factor, c.pan_offset_x, c.pan_offset_y) == (1.0, 0.0, 0.0)
    b["girar_izq"].click()
    assert c.azimuth_deg == pytest.approx(135)
    c.set_vista("frente")
    assert (c.azimuth_deg, c.elevation_deg) == (0.0, 0.0)
    b["perspectiva"].setChecked(True)
    assert c.is_perspective
    b["cotas"].setChecked(False)
    assert not c.show_dimensions
    c.resize(400, 300)
    c.zoom(2.0, QPointF(300, 150))       # el punto bajo el mouse queda quieto
    assert (c.pan_offset_x, c.pan_offset_y) == pytest.approx((-100, 0))


def test_medidas_interiores_y_exteriores_enganchadas(qapp):
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    tapa = w.params["int_alto_tapa"]
    w.editores["int_alto_tapa"].widget.setValue(tapa + 40)       # la tapa cambia, el alto total no
    w.recalcular()
    assert w.params["int_alto_cuerpo"] + w.params["int_alto_tapa"] == pytest.approx(w.sp_alto_interior.value())
    w.sp_alto_interior.setValue(500)
    w.recalcular()
    assert w.params["int_alto_cuerpo"] == pytest.approx(500 - tapa - 40)
    assert w.ext_spins[2].value() == pytest.approx(w.resultado.valores["ext_alto"])
    w.editores["int_ancho"].widget.setValue(700)                 # interior -> exterior
    w.recalcular()
    assert w.ext_spins[0].value() == pytest.approx(w.resultado.valores["ext_ancho"]) and w.ext_spins[0].value() > 700
    w.ext_spins[1].setValue(600)                                 # exterior -> interior
    assert w.resultado.valores["ext_prof"] == pytest.approx(600, abs=0.1)
    assert w.editores["int_prof"].valor() == w.params["int_prof"] < 600
