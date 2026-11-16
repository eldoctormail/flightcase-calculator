"""Configuraciones guardadas por sección: se guardan sólo los valores de una sección
y al cargarlas en otro case no cambia nada más."""

import pytest

from flightcase.taller import configuraciones as cf
from flightcase.taller.modelo import calcular, parametros_por_defecto

D = parametros_por_defecto()


@pytest.fixture(autouse=True)
def carpeta_datos(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(tmp_path))
    return tmp_path


def test_las_secciones_no_incluyen_medidas_y_sus_parametros_existen():
    secs = cf.secciones()
    assert "Ruedas" in secs and "Placa" in secs and "Interior: equipos y espuma" in secs
    assert "Medidas interiores" not in secs
    for nombres in secs.values():
        assert not set(nombres) & cf.MEDIDAS
        for k in nombres:
            assert k in D, k


def test_guardar_y_cargar_ruedas_en_otro_case():
    p = dict(D, ruedas=4, rueda_diametro=125, rueda_frenos=2, placa_esp=9, int_ancho=777)
    c = cf.guardar("Ruedas 125 con freno", "Ruedas", p)
    assert c.params["rueda_diametro"] == 125
    assert set(c.params) <= set(cf.secciones()["Ruedas"])
    assert "placa_esp" not in c.params

    otro = dict(D, int_ancho=500, placa_esp=7, ruedas=0)
    q = cf.aplicar(otro, cf.buscar(c.id), D)
    assert q["ruedas"] == 4 and q["rueda_diametro"] == 125 and q["rueda_frenos"] == 2
    assert q["int_ancho"] == 500 and q["placa_esp"] == 7          # el resto no se toca
    assert otro["ruedas"] == 0                                    # no modifica lo recibido
    assert calcular(q).paneles


def test_mismo_nombre_reemplaza_solo_en_su_seccion():
    cf.guardar("Mi favorita", "Ruedas", dict(D, rueda_diametro=100))
    cf.guardar("Mi favorita", "Placa", dict(D, placa_esp=12))
    cf.guardar("Mi favorita", "Ruedas", dict(D, rueda_diametro=150))
    ruedas = cf.de_seccion("Ruedas")
    assert len(ruedas) == 1 and ruedas[0].params["rueda_diametro"] == 150
    assert len(cf.de_seccion("Placa")) == 1


def test_las_listas_del_case_solo_si_se_piden():
    p = dict(D, equipos=[["Consola", 400, 300, 100, 5, 0, 0, 0, "", -1, 0]], espuma_densidad=30)
    assert cf.tiene_contenido("Interior: equipos y espuma", p)
    sin = cf.guardar("Espuma 30", "Interior: equipos y espuma", p)
    assert "equipos" not in sin.params and sin.params["espuma_densidad"] == 30
    con = cf.guardar("Espuma con consola", "Interior: equipos y espuma", p, con_contenido=True)
    assert con.params["equipos"] == p["equipos"]
    q = cf.aplicar(dict(D), sin, D)
    assert q["equipos"] == D["equipos"]


def test_valores_viejos_o_ajenos_a_la_seccion_se_ignoran():
    c = cf.Configuracion("x", "x", "Ruedas", {"rueda_diametro": 80, "placa_esp": 3, "int_ancho": 1, "no_existe": 5})
    q = cf.aplicar(dict(D), c, D)
    assert q["rueda_diametro"] == 80
    assert q["placa_esp"] == D["placa_esp"] and q["int_ancho"] == D["int_ancho"] and "no_existe" not in q


def test_borrar_y_seccion_desconocida():
    c = cf.guardar("Borrame", "Placa", dict(D))
    assert cf.borrar(c.id) and cf.buscar(c.id) is None
    assert not cf.borrar(c.id)
    with pytest.raises(ValueError):
        cf.guardar("x", "Medidas interiores", dict(D))


def test_archivo_roto_no_rompe(carpeta_datos):
    (carpeta_datos / cf.ARCHIVO).write_text("{no es json", encoding="utf-8")
    assert cf.todas() == []


# ------------------------------------------------------------------ en el Taller
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_boton_por_seccion_guardar_cargar_y_deshacer(qapp):
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    assert {"Ruedas", "Placa", "Interior: equipos y espuma"} <= set(w.botones_config)
    w.editores["rueda_diametro"].poner(125)
    w.editores["placa_esp"].poner(12)
    w.recalcular()
    id_c = w.guardar_configuracion("Ruedas", "Ruedas grandes", con_contenido=False)

    w.set_params({})                                  # otro case
    w.editores["placa_esp"].poner(7)
    w.recalcular()
    assert w.cargar_configuracion(id_c)
    assert w.params["rueda_diametro"] == 125 and w.editores["rueda_diametro"].valor() == 125
    assert w.params["placa_esp"] == 7
    w.deshacer()
    assert w.params["rueda_diametro"] == D["rueda_diametro"]

    menu = w.botones_config["Ruedas"].menu()
    w._llenar_menu_config(menu, "Ruedas")
    textos = [a.text() for a in menu.actions()]
    assert "Cargar «Ruedas grandes»" in textos
    assert w.borrar_configuracion(id_c, confirmar=False)
    w._llenar_menu_config(menu, "Ruedas")
    assert "No hay configuraciones guardadas" in [a.text() for a in menu.actions()]
