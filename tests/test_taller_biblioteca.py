"""Biblioteca de equipos y asistente de case nuevo."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from flightcase.taller import biblioteca as B
from flightcase.taller.modelo import calcular, parametros_por_defecto

CONSOLA = B.EquipoBiblio("Consola", "Mezcla", ancho=400, fondo=300, alto=100, peso=5.5)
MICRO = B.EquipoBiblio("Micro SM58", "Micrófonos", ancho=60, fondo=200, alto=60, forma="redondo", dedos=1)
POTENCIA = B.EquipoBiblio("Potencia", "Rack", u=2, fondo=350, peso=12, sobresale=20)


@pytest.fixture(autouse=True)
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(tmp_path))
    QApplication.instance() or QApplication([])


def test_guardar_cargar_y_reemplazar():
    assert B.cargar() == []
    lista = [CONSOLA, MICRO]
    B.guardar(lista)
    assert {e.nombre for e in B.cargar()} == {"Consola", "Micro SM58"}
    lista = B.cargar()
    reemplazados = B.sumar(lista, [B.EquipoBiblio("consola", ancho=410, fondo=300, alto=100), POTENCIA])
    assert reemplazados == ["consola"] and len(lista) == 3
    B.guardar(lista)
    assert next(e for e in B.cargar() if e.nombre == "consola").ancho == 410


def test_planilla_ida_y_vuelta():
    texto = B.a_csv([CONSOLA, MICRO, POTENCIA])
    assert texto.splitlines()[1] == "Consola;Mezcla;400;300;100;5,5;0;;-1;0;0;"
    assert B.desde_csv(texto) == [CONSOLA, MICRO, POTENCIA]
    # una planilla hecha a mano: otro orden, coma como separador, columnas que faltan
    assert B.desde_csv("alto,nombre,ancho,fondo\n50,Pedal,120,80\n,,,\n") == [
        B.EquipoBiblio("Pedal", ancho=120, fondo=80, alto=50)]
    with pytest.raises(ValueError):
        B.desde_csv("Ancho;Fondo\n1;2\n")


def test_filas_de_las_tablas():
    assert CONSOLA.fila_equipos() == ["Consola", 400, 300, 100, 5.5, "c", "c", 0, "", -1, 0]
    assert POTENCIA.fila_equipos()[1:4] == [482.6, 350, pytest.approx(88.9)]
    assert POTENCIA.fila_rack() == ["Potencia", 2, 350, 12, 0, 20]
    assert B.desde_fila_equipos(MICRO.fila_equipos()) == B.EquipoBiblio(
        "Micro SM58", ancho=60, fondo=200, alto=60, forma="redondo", dedos=1)
    assert B.desde_fila_rack(POTENCIA.fila_rack()).u == 2


def test_acomodar_en_espuma_sin_choques():
    d = parametros_por_defecto()
    sug = B.acomodar_en_espuma([CONSOLA, MICRO, POTENCIA], d["espuma_holgura"], d["espuma_pared_min"],
                               d["espuma_fondo_min"], plancha=d["espuma_plancha"])
    assert sug["int_alto_cuerpo"] % d["espuma_plancha"] == 0
    p = dict(sug, espumas=[[0, 0, 0]])
    avisos = calcular(p).avisos
    assert not [a for a in avisos if "choca" in a or "se sale" in a or "no entra" in a], avisos


def test_tabla_de_equipos_desde_y_hacia_la_biblioteca(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from flightcase.ui.widgets import TallerWidget
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    w = TallerWidget()
    ed = w.editores["equipos"]
    ed.agregar_filas([CONSOLA.fila_equipos(), MICRO.fila_equipos()])
    w.recalcular()
    assert [e[0] for e in w.params["equipos"]] == ["Consola", "Micro SM58"]
    assert ed.guardar_en_biblioteca([1]) == 1
    assert [e.nombre for e in B.cargar()] == ["Micro SM58"]
    rack = w.editores["rack_equipos"]
    rack.agregar_filas([POTENCIA.fila_rack()])
    assert rack.guardar_en_biblioteca() == 1
    assert next(e for e in B.cargar() if e.nombre == "Potencia").u == 2


def test_ventana_de_la_biblioteca(tmp_path):
    from flightcase.ui.widgets.biblioteca_widget import BibliotecaDialog
    B.guardar([CONSOLA, POTENCIA])
    agregados = []
    dlg = BibliotecaDialog(agregar=agregados.extend)
    assert dlg.tabla.rowCount() == 2 and not dlg.btn_agregar.isEnabled()
    dlg.nuevo()
    dlg.tabla.item(2, 0).setText("Pedalera")
    dlg.tabla.item(2, 2).setText("600,5")
    assert any(e.nombre == "Pedalera" and e.ancho == 600.5 for e in B.cargar())
    dlg.tabla.item(2, 2).setText("ancho")             # no es un número: queda como estaba
    assert next(e for e in B.cargar() if e.nombre == "Pedalera").ancho == 600.5
    dlg.buscar.setText("rack")
    assert [dlg.tabla.isRowHidden(r) for r in range(3)] == [True, False, True]
    dlg.buscar.clear()
    dlg.tabla.selectRow(0)
    dlg.btn_agregar.click()
    assert [e.nombre for e in agregados] == [dlg.equipos[0].nombre]
    dlg.exportar(str(tmp_path / "eq.csv"))
    B.guardar([])
    dlg2 = BibliotecaDialog()
    dlg2.importar(str(tmp_path / "eq.csv"))
    assert len(B.cargar()) == 3


def _asistente(estilo, modo, nombres, exterior=None):
    from flightcase.ui.widgets.asistente import AsistenteCase
    a = AsistenteCase()
    a.pagina_estilo.seleccionar(estilo)
    a.pagina_interior.opciones[modo].setChecked(True)
    a.pagina_interior.elegir(nombres)
    a.pagina_interior._sugerir_u()
    a.pagina_medidas.initializePage()
    a.pagina_terminaciones.initializePage()
    if exterior:
        a.pagina_medidas.rb_exterior.setChecked(True)
        for sp, v in zip((a.pagina_medidas.sp_ancho, a.pagina_medidas.sp_largo, a.pagina_medidas.sp_alto), exterior):
            sp.setValue(v)
    return a


def test_asistente_espuma_con_equipos():
    B.guardar([CONSOLA, MICRO, POTENCIA])
    a = _asistente("baul_tapa_suelta", "espuma", ["Consola", "Micro SM58"])
    p = a.armar_params()
    assert [e[0] for e in p["equipos"]] == ["Consola", "Micro SM58"] and p["espumas"] == [[0, 0, 0]]
    assert p["int_ancho"] > 400 + 60 and p["ruedas"] == 4
    a.pagina_resumen.initializePage()
    assert "Exterior:" in a.pagina_resumen.lbl.text()


def test_asistente_rack_y_medidas_exteriores():
    B.guardar([CONSOLA, POTENCIA, B.EquipoBiblio("Mixer rack", u=3, fondo=420)])
    a = _asistente("rack_una_tapa", "rack", ["Potencia", "Mixer rack"])
    assert a.pagina_interior.sp_u.value() == 5
    p = a.armar_params()
    assert p["rack_u"] == 5 and len(p["rack_equipos"]) == 2 and p["orientacion"] == "frontal"
    assert p["int_alto_cuerpo"] >= 420 + p["rack_retiro"]
    assert not [x for x in calcular(p).avisos if "19\"" in x]
    a = _asistente("baul_bisagras", "vacio", [], exterior=(800, 500, 600))
    p = a.armar_params()
    v = calcular(p).valores
    assert (v["ext_ancho"], v["ext_prof"], v["ext_alto"]) == pytest.approx((800, 500, 600), abs=0.2)
    assert p["bisagras"] > 0


def test_asistente_abre_el_case_en_el_taller(monkeypatch):
    from flightcase.ui.widgets import TallerWidget
    from flightcase.ui.widgets import asistente as A
    w = TallerWidget()
    w.editores["int_ancho"].widget.setValue(777)
    w.recalcular()
    monkeypatch.setattr(A.AsistenteCase, "exec", lambda self: (setattr(self, "params", self.armar_params()), 1)[1])
    assert w.asistente()
    assert w.ruta is None and w.params["int_ancho"] != 777 and not w._deshacer
