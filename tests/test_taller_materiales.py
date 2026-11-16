"""Material y espesor distinto por panel: medidas, ubicación, placas, listas, 3D y pestaña."""

import pytest

from flightcase.taller import placas as P
from flightcase.taller import produccion as PR
from flightcase.taller.geometria import malla_3d
from flightcase.taller.modelo import calcular
from flightcase.taller.planos import generar as gen


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _por_id(res):
    return {p.id: p for p in res.paneles}


def _calados(res, pid):
    return sorted((c.tipo, round(c.cx, 3), round(c.cy, 3)) for c in res.calados if c.panel == pid)


def test_sin_filas_no_cambia_nada():
    a, b = calcular(), calcular({"paneles_material": []})
    assert [(p.id, p.ancho, p.alto) for p in a.paneles] == [(p.id, p.ancho, p.alto) for p in b.paneles]
    assert a.panelmat == b.panelmat == []
    assert b.valores["materiales_paneles"] == {}


def test_panel_suelto_con_otra_placa_va_a_panelmat():
    res = calcular({"paneles_material": [["piso", "", 12, "Fenólico 12 mm"]]})
    assert ["piso", "Fenólico 12 mm", 12.0, 2440.0, 1220.0, ""] in res.panelmat
    # el piso va adentro de las paredes: sus medidas no dependen de su propio espesor
    assert (_por_id(res)["piso"].ancho, _por_id(res)["piso"].alto) == (600, 400)
    assert any("interior pierde 3 mm" in a for a in res.avisos)


def test_grupo_y_fila_posterior_corrige():
    res = calcular({"paneles_material": [["tapa", "", 6.5, ""], ["techo", "", 9, ""]]})
    mats = {m[0]: m for m in res.panelmat}
    assert set(mats) == {"tapa_frente", "tapa_trasera", "tapa_izq", "tapa_der"}   # techo volvió a la general
    assert mats["tapa_izq"][1] == "Placa 6.5 mm"


def test_laterales_se_acortan_contra_un_frente_mas_grueso_y_los_calados_no_se_mueven():
    base = calcular()
    res = calcular({"paneles_material": [["cuerpo_trasera", "", 12, ""]]})
    b, r = _por_id(base), _por_id(res)
    assert r["cuerpo_izq"].ancho == pytest.approx(b["cuerpo_izq"].ancho - 3)
    assert r["cuerpo_der"].ancho == pytest.approx(b["cuerpo_der"].ancho - 3)
    assert r["cuerpo_trasera"].ancho == b["cuerpo_trasera"].ancho
    # el izquierdo arranca atrás: su origen se corre 3 mm, los calados quedan en el mismo lugar del case
    assert _calados(res, "cuerpo_izq") == [(t, round(x - 3, 3), y) for t, x, y in _calados(base, "cuerpo_izq")]
    assert _calados(res, "cuerpo_der") == _calados(base, "cuerpo_der")
    col = {c["id"]: c for c in res.valores["geo"]["colocaciones"]}
    col0 = {c["id"]: c for c in base.valores["geo"]["colocaciones"]}
    assert col["cuerpo_izq"]["o"][1] == pytest.approx(col0["cuerpo_izq"]["o"][1] - 3)
    assert col["cuerpo_trasera"]["esp"] == 12 and col["cuerpo_frente"]["esp"] == 9


def test_extremos_que_cubren_acortan_las_paredes():
    p = {"extremos_cubren": True}
    base, res = calcular(p), calcular(dict(p, paneles_material=[["piso", "", 12, ""], ["techo", "", 6, ""]]))
    b, r = _por_id(base), _por_id(res)
    assert r["cuerpo_frente"].alto == pytest.approx(b["cuerpo_frente"].alto - 3)
    assert r["tapa_frente"].alto == pytest.approx(b["tapa_frente"].alto + 3)
    col = {c["id"]: c for c in res.valores["geo"]["colocaciones"]}
    col0 = {c["id"]: c for c in base.valores["geo"]["colocaciones"]}
    assert col["cuerpo_frente"]["o"][2] == pytest.approx(col0["cuerpo_frente"]["o"][2] + 3)


def test_hibrido_solo_cambia_el_espesor():
    p = {"sistema": "hibrido"}
    base, res = calcular(p), calcular(dict(p, paneles_material=[["cuerpo", "", 12, ""]]))
    assert [(x.ancho, x.alto) for x in base.paneles] == [(x.ancho, x.alto) for x in res.paneles]
    assert {m[0] for m in res.panelmat} >= {"piso", "cuerpo_frente", "cuerpo_izq"}


def test_panel_que_no_existe_avisa():
    res = calcular({"paneles_material": [["base2", "", 12, ""]]})
    assert res.panelmat == []
    assert any("base2" in a and "no es un panel" in a for a in res.avisos)


def test_placa_del_catalogo_da_medida_de_placa_y_va_a_la_lista():
    res = calcular({"paneles_material": [["techo", "05-001", 0, ""]]})
    m = {x[0]: x for x in res.panelmat}["techo"]
    assert m[1:] == ["Tablero abedul 2 caras revestidas 9,6 mm", 9.6, 2500, 1120, "05-001"]
    d = PR.datos(res)
    piezas = gen.agrupar_piezas(d)
    techo = next(pz for pz in piezas if "techo" in pz["ids"])
    assert techo["esp"] == 9.6 and techo["cant"] == 1
    placas, _ = P.armar_placas(d, piezas)
    abedul = [pl for pl in placas if pl["material"].startswith("Tablero abedul")]
    assert abedul and (abedul[0]["L"], abedul[0]["A"]) == (2500, 1120)
    filas = gen.lista_materiales(d, placas, {})
    assert any(f["ref"] == "05-001" and f["detalle"] == "2500 x 1120 mm" for f in filas)
    assert any(f["material"] == "Placa Fenólico 9 mm" for f in filas)
    assert gen.otros_materiales(d) == {"Tablero abedul 2 caras revestidas 9,6 mm": ["Techo (tapa)"]}


def test_mismo_nombre_otro_espesor_no_se_mezcla():
    res = calcular({"paneles_material": [["piso", "", 12, "Fenólico 9 mm"]]})
    assert {x[0]: x for x in res.panelmat}["piso"][1] == "Fenólico 9 mm (12 mm)"


def test_3d_usa_el_espesor_de_cada_panel():
    res = calcular({"paneles_material": [["techo", "", 15, ""]]})
    malla = malla_3d(res)
    zs = [v.z for f in malla.faces if f.label == "Techo (tapa)" for v in f.vertices]
    assert max(zs) - min(zs) == pytest.approx(15, abs=0.01)


def test_pestana_taller_tabla_de_material_por_panel(qapp):
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    w.set_params({"paneles_material": [["piso", "05-001", 0, ""]]})
    ed = w.editores["paneles_material"]
    assert ed.tabla.item(0, 0).text().startswith("piso — ")
    assert ed.tabla.item(0, 1).text().startswith("05-001 — ")
    assert ed.valor() == [["piso", "05-001", 0, ""]]
    assert "otra placa" in w.lbl_resumen.text()
    ops = dict(w._opciones_panel())
    assert ops["tapa"] == "Toda la tapa" and "techo" in ops and "base_ruedas" not in ops
