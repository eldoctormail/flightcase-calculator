"""Estilos de case del taller y elección de herrajes del catálogo en el editor."""

import json
from pathlib import Path

import pytest

from flightcase.taller import estilos
from flightcase.taller.modelo import calcular, parametros_por_defecto

GOLDEN = Path(__file__).parent / "golden" / "taller"
D = parametros_por_defecto()
MEDIDAS = [{}, {"int_ancho": 560, "int_prof": 900, "int_alto_cuerpo": 500, "int_alto_tapa": 100}]


@pytest.fixture
def carpeta_datos(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(tmp_path))
    return tmp_path


def test_los_estilos_incluidos_tienen_parametros_conocidos():
    lista = estilos.estilos_incluidos()
    assert len(lista) >= 12
    assert len({e.id for e in lista}) == len(lista)
    for e in lista:
        for k in e.params:
            assert k.startswith("_") or k in D, (e.id, k)


@pytest.mark.parametrize("estilo", estilos.estilos_incluidos(), ids=lambda e: e.id)
@pytest.mark.parametrize("medidas", MEDIDAS, ids=["defecto", "grande"])
def test_cada_estilo_calcula_sin_errores(estilo, medidas):
    p = dict(D)
    p.update(medidas)
    q = estilos.aplicar(p, estilo, D)
    res = calcular(q)
    assert res.paneles
    assert q["orientacion"] == estilo.params["orientacion"]
    if not (estilo.params.get("_mitades") or estilo.params.get("_tapa_baja")):   # las medidas no cambian
        for k, v in medidas.items():
            assert q[k] == v


@pytest.mark.parametrize("proyecto", ["rack_dsnake", "anvil_tablero_absen", "anvil_acc_electricos"])
def test_base_de_ruedas_automatica_igual_a_la_del_taller(proyecto):
    p = dict(D)
    p.update(json.loads((GOLDEN / f"{proyecto}.json").read_text(encoding="utf-8"))["params"])
    assert estilos.base_ruedas_auto(p) == pytest.approx(p["base_ruedas"])


def test_un_estilo_no_deja_restos_del_anterior():
    p = estilos.aplicar(dict(D), estilos.buscar("baul_bisagras"), D)
    assert p["bisagras"] == 3
    p = estilos.aplicar(p, estilos.buscar("rack_dos_tapas"), D)
    assert p["bisagras"] == 0 and p["topes"] == 0 and p["tapas"] == 2
    p = estilos.aplicar(p, estilos.buscar("baul_tapa_suelta"), D)
    assert p["base_ruedas"] == [] and p["orientacion"] == "vertical" and p["cierres_frente_n"] == 0


def test_estilo_no_toca_interior_ni_herrajes_a_mano():
    p = dict(D)
    p.update({"equipos": [["Mixer", 400, 300, 120]], "herrajes_manuales": [["logo", "frente", 0, 0]],
              "ref_manija": "08-34082"})
    q = estilos.aplicar(p, estilos.buscar("rack_cubierta"), D)
    assert q["equipos"] == p["equipos"] and q["herrajes_manuales"] == p["herrajes_manuales"]
    assert q["ref_manija"] == "08-34082"
    assert q["acceso_tipo"] == "cubierta" and q["acceso_lateral"] == round(0.31 * D["int_prof"])


def test_clamshell_reparte_el_alto_en_mitades():
    p = dict(D)
    p.update({"int_alto_cuerpo": 250, "int_alto_tapa": 80})
    q = estilos.aplicar(p, estilos.buscar("clamshell"), D)
    assert q["int_alto_cuerpo"] + q["int_alto_tapa"] == 330
    assert q["int_alto_cuerpo"] == q["int_alto_tapa"] == 165


def test_estilos_propios_se_guardan_aplican_y_borran(carpeta_datos):
    p = dict(D)
    p.update({"orientacion": "frontal", "tapas": 2, "ref_manija": "08-34082", "placa_esp": 10, "int_ancho": 482})
    e = estilos.guardar_propio("Rack de la casa", p, D)
    assert (carpeta_datos / estilos.ARCHIVO_PROPIOS).is_file()
    assert "int_ancho" not in e.params and e.params["placa_esp"] == 10
    assert [x.id for x in estilos.estilos_propios()] == [e.id]

    otro = dict(D)
    otro.update({"int_ancho": 700, "bisagras": 3})
    q = estilos.aplicar(otro, estilos.buscar(e.id), D)
    assert q["orientacion"] == "frontal" and q["ref_manija"] == "08-34082" and q["placa_esp"] == 10
    assert q["int_ancho"] == 700 and q["bisagras"] == 0

    estilos.guardar_propio("Rack de la casa", otro, D)   # mismo nombre: lo reemplaza
    assert len(estilos.estilos_propios()) == 1
    assert estilos.borrar_propio(e.id) and estilos.estilos_propios() == []


# ---------------------------------------------------------------- editor


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(qapp, carpeta_datos):
    from flightcase.ui.widgets import TallerWidget
    return TallerWidget()


def test_editor_aplica_estilo_y_guarda_uno_propio(widget):
    widget.editores["int_ancho"].widget.setValue(700)
    widget.aplicar_estilo("rack_dos_tapas")
    assert widget.resultado.info["tipo"][:2] == ["2", "frontal"]
    assert widget.params["int_ancho"] == 700
    assert widget.editores["orientacion"].widget.currentText() == "frontal"
    assert widget.lbl_estilo.text()

    id_propio = widget.guardar_estilo("Mi rack")
    assert widget.cmb_estilo.currentData() == id_propio and widget.btn_borrar_estilo.isEnabled()
    widget.nuevo(preguntar=False)          # descarta el estilo aplicado sin guardar
    assert widget.params["orientacion"] == "vertical" and widget.cmb_estilo.currentIndex() == 0
    widget.aplicar_estilo(id_propio)
    assert widget.params["orientacion"] == "frontal" and widget.params["tapas"] == 2
    widget.borrar_estilo(confirmar=False)
    assert widget.cmb_estilo.findData(id_propio) == -1


def test_herrajes_se_eligen_del_catalogo(widget):
    ed = widget.editores["ref_manija"]
    w = ed.widget
    refs = [w.itemData(i) for i in range(w.count())]
    assert refs[0] == "" and "08-34082" in refs and "08-372151" not in refs   # sólo manijas
    w.setCurrentIndex(refs.index("08-34082"))
    widget.recalcular()
    assert widget.params["ref_manija"] == "08-34082"
    assert "Asa retráctil" in w.currentText()
    assert any(h.ref == "08-34082" for h in widget.resultado.herrajes)

    w.setEditText("99-NOEXISTE")   # un número que no está igual se acepta (y avisa)
    widget.recalcular()
    assert widget.params["ref_manija"] == "99-NOEXISTE"
    w.setCurrentIndex(0)
    widget.recalcular()
    assert widget.params["ref_manija"] == ""


def test_accesorios_extra_en_tabla(widget):
    ed = widget.editores["extras"]
    ed.poner([["08-5740A", 4]])
    assert ed.tabla.item(0, 0).text().startswith("08-5740A — Punto de anclaje")
    widget.recalcular()
    assert widget.params["extras"] == [["08-5740A", 4]]
    assert any(h.ref == "08-5740A" and h.cantidad == 4 for h in widget.resultado.herrajes)

    from PySide6.QtWidgets import QTableWidgetItem
    ed.tabla.insertRow(1)
    ed.tabla.setItem(1, 0, QTableWidgetItem("08-3476031"))   # sin cantidad: va 1
    widget.recalcular()
    assert widget.params["extras"] == [["08-5740A", 4], ["08-3476031", 1]]


def test_tapa_baja_y_bandejas_euro():
    por_id = {e.id: e for e in estilos.estilos_incluidos()}
    p = dict(D, int_alto_cuerpo=500, int_alto_tapa=100)
    q = estilos.aplicar(p, por_id["baul_tapa_baja"], D)
    assert (q["int_alto_cuerpo"], q["int_alto_tapa"]) == (550, 50)        # el total no cambia
    p = dict(D, int_prof=700, cajones=[])
    q = estilos.aplicar(p, por_id["bandejas_euro"], D)
    assert q["cajones"] == [[116.0, 0.0], [116.0, 120.0], [116.0, 240.0], [116.0, 360.0], [116.0, 480.0]]
    assert estilos.aplicar(dict(p, cajones=[[200, 0]]), por_id["bandejas_euro"], D)["cajones"] == [[200, 0]]


def test_rack_de_audio_nuevo_sale_igual_al_del_generador():
    """El estilo «Rack de audio» en un proyecto nuevo da exactamente el rack_audio.scad de Javier."""
    from test_taller_golden import _filas
    golden = json.loads((GOLDEN / "rack_audio.json").read_text(encoding="utf-8"))
    q = estilos.aplicar(dict(D), estilos.buscar("rack_audio"), D, con_medidas=True)
    esperado = dict(D)
    esperado.update(golden["params"])
    for k, v in golden["params"].items():
        assert q[k] == v, k
    assert _filas(calcular(q)) == _filas(calcular(esperado))


def test_rack_de_audio_en_el_taller_respeta_las_medidas_del_proyecto():
    p = dict(D)
    p.update(MEDIDAS[1])
    q = estilos.aplicar(p, estilos.buscar("rack_audio"), D)
    for k, v in MEDIDAS[1].items():
        assert q[k] == v
    assert q["acceso_tipo"] == "cubierta" and q["ref_cierre_macho"] == "08-6203"
    assert q["base_ruedas"] == estilos.base_ruedas_auto(q) and q["acceso_lateral"] == round(0.31 * 900)
