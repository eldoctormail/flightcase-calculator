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


def test_deshacer_y_rehacer(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from flightcase.ui import FlightCaseMainWindow
    w = FlightCaseMainWindow(restore_settings=False)
    t = w.taller_widget
    assert not w.accion_deshacer.isEnabled() and not t.btn_deshacer.isEnabled()
    t.editores["int_ancho"].widget.setValue(700)
    t.recalcular()
    t.editores["rack_u"].widget.setValue(4)
    t.recalcular()
    t.herrajes.cambiado.emit([["08-41076", "frente", 100, 100, 0, False, 0, 0, "", "placa"]])
    assert w.accion_deshacer.text() == "&Deshacer: Herrajes a mano"
    t.deshacer()
    assert t.params["herrajes_manuales"] == [] and t.params["rack_u"] == 4
    assert w.accion_rehacer.text() == "&Rehacer: Herrajes a mano"
    w.accion_deshacer.trigger()
    assert t.params["rack_u"] == 0 and t.editores["rack_u"].valor() == 0
    t.deshacer()
    assert t.params["int_ancho"] == 600 and not w.accion_deshacer.isEnabled()
    t.rehacer()
    t.rehacer()
    assert (t.params["int_ancho"], t.params["rack_u"]) == (700, 4)
    t.editores["int_prof"].widget.setValue(333)    # un cambio nuevo borra lo que se podía rehacer
    t.recalcular()
    assert not w.accion_rehacer.isEnabled()
    # Ctrl+Z con el cursor en un campo: deshace el case (y lo escrito cuenta como cambio)
    w.show()
    campo = t.editores["int_alto_tapa"].widget
    campo.setFocus()
    campo.lineEdit().selectAll()
    QTest.keyClicks(campo.lineEdit(), "120")
    QTest.keyClick(campo.lineEdit(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert t.params["int_alto_tapa"] == 80 and t.params["int_prof"] == 333
    t.set_params({})                               # otro proyecto: historial nuevo
    assert not w.accion_deshacer.isEnabled() and not w.accion_rehacer.isEnabled()
    w.close()


def test_nuevo_pregunta_si_hay_cambios_y_avisa(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from flightcase.ui.app import FlightCaseMainWindow
    w = FlightCaseMainWindow(restore_settings=False)
    t = w.taller_widget
    assert not t.hay_cambios()
    t.set_params({"int_ancho": 900}, str(tmp_path / "x.scad"))
    assert not t.hay_cambios()
    t.editores["int_ancho"].poner(700)
    assert t.hay_cambios()
    nuevo = next(a for a in w.file_menu.actions() if a.text() == "&Nuevo case")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel)
    nuevo.trigger()
    assert t.params["int_ancho"] == 700                       # canceló: sigue el case de antes
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Save)
    nuevo.trigger()
    assert "int_ancho = 700" in (tmp_path / "x.scad").read_text(encoding="utf-8")   # lo guardó antes
    assert t.ruta is None and t.lbl_archivo.text() == "Proyecto nuevo"
    assert t.params["int_ancho"] == t.defectos["int_ancho"]
    assert w.status_bar.currentMessage().startswith("Case nuevo")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("no había cambios"))
    nuevo.trigger()                                              # sin cambios no pregunta
    w.close()


def test_acerca_de(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from flightcase.ui.app import FlightCaseMainWindow
    from flightcase.version import version
    visto = []
    monkeypatch.setattr(QMessageBox, "about", lambda parent, titulo, texto: visto.append(texto))
    w = FlightCaseMainWindow(restore_settings=False)
    accion = next(a for a in w.help_menu.actions() if "Acerca de" in a.text())
    accion.trigger()
    assert "Javier Amigo" in visto[0] and f"Versión {version()}" in visto[0]
    assert version() not in ("", "desconocida")
    w.close()
