"""Pestaña Taller: edición de parámetros, .scad de ida y vuelta y exportación."""

import pytest

from flightcase.taller.modelo import calcular
from flightcase.taller.scad import leer_proyecto


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(qapp):
    from flightcase.ui.widgets import TallerWidget
    return TallerWidget()


def test_editores_para_los_parametros_y_resultado_inicial(widget):
    assert {"int_ancho", "sistema", "manijas", "bandejas", "ruedas"} <= set(widget.editores)
    assert widget.resultado is not None
    assert widget.tabla_paneles.rowCount() == len(calcular().paneles)


def test_cambiar_un_parametro_recalcula(widget):
    ancho_antes = widget.resultado.valores["ext_ancho"]
    widget.editores["int_ancho"].widget.setValue(800)
    widget.recalcular()
    assert widget.resultado.valores["ext_ancho"] == pytest.approx(ancho_antes + 200)
    widget.editores["sistema"].widget.setCurrentText("hibrido")
    widget.recalcular()
    assert widget.resultado.info["sistema"] == ["hibrido"]


def test_lista_mal_escrita_no_rompe(widget):
    widget.editores["piezas_extra"].widget.setText('[["Base", 400, 300')
    widget.recalcular()
    assert "lista" in widget.lbl_avisos.text()
    widget.editores["piezas_extra"].widget.setText('[["Base", 400, 300, 18]]')
    widget.recalcular()
    assert widget.params["piezas_extra"] == [["Base", 400, 300, 18]]
    assert widget.resultado.extras


def test_guardar_y_abrir_scad(widget, tmp_path):
    widget.editores["int_ancho"].widget.setValue(482)
    widget.editores["manijas"].widget.setChecked(False)
    widget.editores["ruedas"].widget.setValue(4)
    ruta = tmp_path / "rack.scad"
    widget.guardar(str(ruta))
    leido = leer_proyecto(ruta)
    assert leido == {"int_ancho": 482, "manijas": False, "ruedas": 4}
    assert "flightcase();" in ruta.read_text(encoding="utf-8")

    widget.nuevo()
    assert widget.params["int_ancho"] == 600
    widget.abrir(str(ruta))
    assert widget.params["int_ancho"] == 482 and widget.params["ruedas"] == 4
    assert widget.lbl_archivo.text() == "rack.scad"


def test_abrir_conserva_parametros_sin_editor(widget, tmp_path):
    ruta = tmp_path / "color.scad"
    ruta.write_text('color_placa = "Black";\nint_prof = 500;\nflightcase();\n', encoding="utf-8")
    widget.abrir(str(ruta))
    assert 'color_placa' in widget.texto_proyecto() and "Black" in widget.texto_proyecto()


def test_exportar_paquete(widget, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail(a[2]))
    paq = widget.exportar(str(tmp_path / "salida"))
    assert (tmp_path / "salida" / "planos.pdf").exists()
    assert any(a.endswith(".dxf") for a in paq.archivos)


def test_pestana_taller_en_la_ventana(qapp):
    from flightcase.ui import FlightCaseMainWindow
    w = FlightCaseMainWindow(restore_settings=False, load_last_project=False)
    w.show()
    w.center_tabs.setCurrentWidget(w.taller_widget)
    assert not w.tabs.isVisible() and not w.config_container.isVisible()
    w.center_tabs.setCurrentWidget(w.schema_widget)
    assert w.tabs.isVisible() and w.config_container.isVisible()
    w.close()


def test_vista_3d_se_actualiza(widget):
    widget.editores["int_ancho"].widget.setValue(900)
    widget.recalcular()
    a, b = widget.vista_3d.mesh.bounding_box
    assert b.x - a.x >= widget.resultado.valores["ext_ancho"]


def test_exportar_step(widget, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail(a[2]))
    st = widget.exportar_step(str(tmp_path / "case.step"))
    assert st.cuerpos > 0 and (tmp_path / "case.step").read_text(encoding="ascii").startswith("ISO-10303-21;")


def test_taller_es_la_pestana_principal(qapp, tmp_path):
    from PySide6.QtGui import QKeySequence
    from flightcase.ui import FlightCaseMainWindow
    from flightcase.ui.app import icono_app
    assert not icono_app().isNull()
    w = FlightCaseMainWindow(restore_settings=False, load_last_project=False)
    assert w.center_tabs.currentWidget() is w.taller_widget and w.center_tabs.tabText(0) == "Taller"
    assert not w.windowIcon().isNull()
    atajos = {a.shortcut().toString(QKeySequence.PortableText): a.text() for a in w.file_menu.actions()
              if not a.shortcut().isEmpty()}
    assert "case" in atajos["Ctrl+S"] and "case" in atajos["Ctrl+O"] and "case" in atajos["Ctrl+N"]
    assert w.quick_menu.menuAction() in w.file_menu.actions()
    ruta = tmp_path / "mio.scad"
    w.taller_widget.guardar(str(ruta))
    w.taller_widget.editores["int_ancho"].widget.setValue(777)
    w._taller_guardar()                    # Ctrl+S guarda en el mismo archivo, sin preguntar
    assert "int_ancho = 777" in ruta.read_text(encoding="utf-8")
    w.close()
