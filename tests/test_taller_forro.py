"""Forro interior por cara: medidas, piezas, huecos, planchas, listas, 3D, instructivo y pestaña."""

import os

import pytest

from flightcase.taller import forro as FO
from flightcase.taller import produccion as PR
from flightcase.taller.geometria import malla_3d, Opciones3D
from flightcase.taller.modelo import calcular
from flightcase.taller.planos import generar as gen

MIXTO = {"forro": [["cuerpo", "alfombra", 0, ""], ["piso", "espuma", 20, ""], ["tapa", "espuma", 15, "08-019315"]]}


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _piezas(res):
    return {pz.nombre: pz for pz in res.valores["forro"].piezas}


def test_sin_forro_no_cambia_nada():
    a, b = calcular(), calcular({"forro": []})
    assert a.valores["ext_ancho"] == b.valores["ext_ancho"] and a.valores["ext_alto"] == b.valores["ext_alto"]
    assert a.extras == b.extras and a.panelmat == b.panelmat
    assert b.valores["forro"] is None and "forro" not in b.info


def test_cada_cara_hace_crecer_el_case_lo_que_mide_su_forro():
    base = calcular().valores
    v = calcular(MIXTO).valores
    assert v["ext_ancho"] == base["ext_ancho"] + 2 * 3
    assert v["ext_prof"] == base["ext_prof"] + 2 * 3
    assert v["ext_alto"] == base["ext_alto"] + 20 + 15     # piso y cara de la tapa; las paredes de la tapa no
    res = calcular(MIXTO)
    assert res.info["interior"][:2] == ["600", "400"]       # el interior sigue siendo el espacio útil


def test_piezas_y_como_apoyan():
    p = _piezas(calcular(MIXTO))
    assert (p["Forro piso (cuerpo)"].w, p["Forro piso (cuerpo)"].h, p["Forro piso (cuerpo)"].esp) == (606, 406, 20)
    # frente y trasera a todo el ancho, sobre el piso; los laterales entre ellos
    assert (p["Forro frente cuerpo"].w, p["Forro frente cuerpo"].h) == (606, 250)
    assert (p["Forro lateral izq. cuerpo"].w, p["Forro lateral izq. cuerpo"].h) == (400, 250)
    # tapa: el techo a todo el interior, las paredes debajo (espuma de 15 del catálogo)
    assert p["Forro techo (tapa)"].material == "Espuma plastazote (LD29) 15 mm"
    assert (p["Forro lateral izq. tapa"].w, p["Forro lateral izq. tapa"].h) == (406 - 30, 80)
    assert p["Forro frente cuerpo"].material == "Alfombra 3 mm"


def test_filas_en_orden_y_sin_forro():
    res = calcular({"forro": [["todo", "alfombra", 0, ""], ["tapa_paredes", "no", 0, ""], ["der", "espuma", 12, ""]]})
    F = res.valores["forro"]
    assert "tapa_paredes" not in F.caras
    assert F.caras["der"].esp == 12 and F.caras["izq"].esp == 3
    assert res.valores["ext_ancho"] == calcular().valores["ext_ancho"] + 3 + 12


def test_espuma_esp_es_la_base_de_todas_las_caras():
    res = calcular({"espuma_esp": 10, "forro": [["piso", "alfombra", 0, ""]]})
    F = res.valores["forro"]
    assert F.caras["izq"].material == "Espuma 10 mm" and F.caras["piso"].material == "Alfombra 3 mm"
    assert not any(h.nombre.startswith("Espuma ") for h in res.herrajes)    # ya no se estima por superficie


def test_caras_que_no_existen_avisan():
    res = calcular({"forro": [["base2", "alfombra", 0, ""], ["piso", "cuero", 0, ""]]})
    assert any("base2" in a for a in res.avisos) and any("cuero" in a for a in res.avisos)


def test_dos_tapas():
    res = calcular({"tapas": 2, "forro": [["todo", "alfombra", 0, ""]]})
    F = res.valores["forro"]
    assert "piso" not in F.caras and "base2" in F.caras and "tapa2_paredes" in F.caras
    assert res.valores["ext_alto"] == calcular({"tapas": 2}).valores["ext_alto"] + 2 * 3


def test_huecos_de_manijas_y_platos():
    res = calcular(dict(MIXTO, encastres=True))
    p = _piezas(res)
    assert len(p["Forro techo (tapa)"].huecos) == 4                   # platos de apilado
    lat = p["Forro lateral izq. cuerpo"].huecos
    assert len(lat) == 1 and (lat[0]["w"], lat[0]["h"]) == (170, 100)   # manija embutida
    assert not p["Forro frente cuerpo"].huecos
    # izquierdo y derecho, vistos desde adentro, tienen el hueco en el mismo lugar: es la misma pieza
    j = {x["nombre"]: x for x in FO.juntar(res.valores["forro"])}
    assert j["Forro lateral izq. cuerpo / Forro lateral der. cuerpo"]["cant"] == 2
    # en 3D la lámina se parte alrededor del hueco
    techo = next(f for f in res.valores["geo"]["forro"] if f["nombre"] == "Forro techo (tapa)")
    assert len(techo["celdas"]) > 1


def test_extras_planchas_y_compra():
    res = calcular(MIXTO)
    mats = {e[5] for e in res.extras}
    assert {"Alfombra 3 mm", "Espuma 20 mm", "Espuma plastazote (LD29) 15 mm"} <= mats
    filas = {f[1]: f for f in res.panelmat if len(f) > 6 and f[6] == "forro"}
    assert filas["Alfombra 3 mm"][3:5] == [2000.0, 1500.0] and filas["Espuma 20 mm"][3:5] == [2000.0, 1000.0]
    assert any(h.nombre.startswith("Adhesivo de contacto") for h in res.herrajes)
    d = PR.datos(res)
    assert gen.medidas_placa(d, "Alfombra 3 mm")[:2] == (2000.0, 1500.0)


def test_3d_tiene_el_forro_y_se_mueve_con_la_tapa():
    res = calcular(MIXTO)
    cerrado = [f for f in malla_3d(res).faces if f.color_group.startswith("forro_")]
    assert cerrado and {f.color_group for f in cerrado} == {"forro_alfombra", "forro_espuma"}
    abierto = malla_3d(res, Opciones3D(abrir_tapa=300))
    z_techo = max(p.z for f in abierto.faces if f.label == "Forro techo (tapa)" for p in f.vertices)
    assert z_techo == pytest.approx(res.valores["ext_alto"] - res.valores["pared"] + 300)
    sin = malla_3d(res, Opciones3D(interior=False))
    assert not any(f.color_group.startswith("forro_") for f in sin.faces)


def test_exportar(tmp_path):
    res = calcular(dict(MIXTO, encastres=True))
    paq = PR.exportar(res, str(tmp_path), pdf=False, step=False)
    dxf = sorted(os.listdir(tmp_path / "dxf"))
    forros = [n for n in dxf if "_forro" in n]
    assert len(forros) == 6
    techo = next(pz for pz in paq.piezas if pz["nombre"] == "Forro techo (tapa)")
    assert len(techo["calados"]) == 4
    assert {pl["material"] for pl in paq.placas} >= {"Alfombra 3 mm", "Espuma 20 mm"}
    mats = (tmp_path / "materiales.csv").read_text(encoding="utf-8-sig")
    assert "Forro: Alfombra 3 mm" in mats and "planchas de 2000 x 1500 mm" in mats


def test_paso_del_instructivo():
    res = calcular(MIXTO)
    piezas = [dict(nombre=j["nombre"], num=i, forro=True) for i, j in enumerate(FO.juntar(res.valores["forro"]), 7)]
    pasos = FO.pasos_instructivo(res, piezas)
    assert len(pasos) == 1 and pasos[0]["defs"]["resaltar_interior"] == "forro"
    assert any("P7" in t for t in pasos[0]["texto"])


def test_interiores_usan_el_espacio_de_adentro_del_forro():
    res = calcular(dict(MIXTO, equipos=[["Caja", 100, 100, 100]]))
    I = res.valores["interiores"]
    p = res.valores["pared"]
    assert I.util.x0 == pytest.approx(p + 3) and I.util.z0 == pytest.approx(p + 20)


def test_pestana_tabla_forro(qapp):
    from flightcase.ui.widgets.taller_widget import TallerWidget
    w = TallerWidget()
    ed = w.editores["forro"]
    ed.poner([["piso", "espuma", 20, ""]])
    assert ed.valor() == [["piso", "espuma", 20, ""]]
    w.params["forro"] = ed.valor()
    claves = [c for c, _ in w._opciones_cara()]
    assert "techo" in claves and "tapa_paredes" in claves and "cuerpo" in claves
