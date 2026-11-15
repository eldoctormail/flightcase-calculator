"""Calados de espuma con forma: esquinas redondeadas, redondos, dedos y contornos de dibujo."""

import math

import pytest

from flightcase.taller import formas_espuma as F
from flightcase.taller.modelo import calcular
from flightcase.taller.produccion import panel_dxf

VALIJA = dict(int_ancho=600, int_prof=400, int_alto_cuerpo=250, int_alto_tapa=80)
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60" viewBox="0 0 100 60">'
       '<path d="M0 0 H100 V40 L70 60 H30 L0 40 Z"/></svg>')


def _bloque(**p):
    res = calcular(dict(VALIJA, espumas=[[0, 0, 120]], **p))
    I = res.valores["interiores"]
    return res, I.espumas[0]


def _calado(bl, equipo, capa=-1):
    return [c for c in bl.capas[capa].calados if c["equipo"] == equipo][0]


def test_rectangulo_simple_queda_como_antes():
    assert F.contorno(0, 100, 0, 50, F.Forma(), 300, 200) == (None, [])
    _, bl = _bloque(equipos=[["Caja", 100, 100, 60]])
    assert "puntos" not in _calado(bl, "Caja") and "contorno" not in bl.bolsillos[0]


def test_areas_de_las_formas():
    pol, _ = F.contorno(20, 220, 30, 130, F.Forma(radio=10), 300, 200)
    assert F.area(pol) == pytest.approx(200 * 100 - (4 - math.pi) * 100, rel=2e-3)
    pol, _ = F.contorno(20, 220, 30, 130, F.Forma("redondo"), 300, 200)
    assert F.area(pol) == pytest.approx(math.pi * 100 * 50, rel=2e-3)
    pol, _ = F.contorno(20, 220, 30, 130, F.Forma(dedos=2, dedo_ancho=30, dedo_largo=25), 300, 200)
    hueco = 30 * 10 + math.pi * 15 ** 2 / 2          # lo que el hueco asoma fuera del calado
    assert F.area(pol) == pytest.approx(20000 + 2 * hueco, rel=5e-3)


def test_dedos_en_los_lados_largos_y_recortados_al_bloque():
    pol, _ = F.contorno(50, 250, 40, 100, F.Forma(dedos=2), 300, 200)
    vs = [y for p in pol for _, y in p]
    us = [x for p in pol for x, _ in p]
    assert min(vs) == pytest.approx(15) and max(vs) == pytest.approx(125)   # 25 mm fuera de cada lado largo
    assert min(us) == pytest.approx(50) and max(us) == pytest.approx(250)
    pol, _ = F.contorno(0, 300, 0, 200, F.Forma(dedos=2), 300, 200)          # ocupa todo: no se sale
    assert F.area(pol) == pytest.approx(300 * 200)
    pol, _ = F.contorno(50, 110, 20, 180, F.Forma(dedos=1), 300, 200)        # más alto que ancho: dedo al costado
    assert min(x for p in pol for x, _ in p) == pytest.approx(25)


def test_contorno_desde_svg(tmp_path):
    (tmp_path / "pedal.svg").write_text(SVG, encoding="utf-8")
    _, bl = _bloque(equipos=[["Pedal", 200, 120, 60, 0, None, None, 70, "pedal.svg"]], _carpeta=str(tmp_path))
    c = _calado(bl, "Pedal")
    assert c["puntos"] and c["tipo"] == "calado"
    # trapecio de 100 x 60 encajado en 206 x 126 (con holgura): sin las dos esquinas de abajo
    assert F.area(c["puntos"]) < 206 * 126 * 0.95


def test_contorno_que_no_existe_avisa_y_va_rectangular(tmp_path):
    res, bl = _bloque(equipos=[["Pedal", 200, 120, 60, 0, None, None, 70, "no_esta.dxf"]], _carpeta=str(tmp_path))
    assert any("No se pudo leer el contorno no_esta.dxf" in a for a in res.avisos)
    assert F.area(_calado(bl, "Pedal")["puntos"]) == pytest.approx(206 * 126)


def test_forma_mal_escrita_avisa():
    res, bl = _bloque(equipos=[["Caja", 100, 100, 60, 0, None, None, 60, "triangulo"]])
    assert any("no se entiende" in a for a in res.avisos)
    assert "puntos" not in _calado(bl, "Caja")


def test_radio_global_y_por_equipo():
    _, bl = _bloque(espuma_radio=8, equipos=[["A", 100, 100, 60, 0, 100], ["B", 100, 100, 60, 0, 400, None, 60, "", 0]])
    assert "puntos" in _calado(bl, "A") and "puntos" not in _calado(bl, "B")


def test_peso_de_la_espuma_descuenta_la_forma():
    _, bl_r = _bloque(equipos=[["Micro", 100, 100, 120]])
    res_r = calcular(dict(VALIJA, espumas=[[0, 0, 120]], equipos=[["Micro", 100, 100, 120]]))
    res_c = calcular(dict(VALIJA, espumas=[[0, 0, 120]], equipos=[["Micro", 100, 100, 120, 0, None, None, 0, "redondo"]]))
    assert res_c.valores["interiores"].peso["espuma"] > res_r.valores["interiores"].peso["espuma"]


def test_dxf_lleva_polilinea_cerrada_en_su_capa():
    _, bl = _bloque(equipos=[["Micro", 60, 60, 100, 0, None, None, 40, "redondo", -1, 1]])
    capas = {c.indice: c for c in bl.capas}
    assert _calado(bl, "Micro", 1)["tipo"] == "rebaje"                  # capa 2: el fondo cae a 40 mm
    txt = panel_dxf(capas[2].ancho, capas[2].alto, capas[2].calados)
    assert "POLYLINE" in txt and "SEQEND" in txt and "\n  8\nREBAJE\n" in txt
    txt = panel_dxf(capas[4].ancho, capas[4].alto, capas[4].calados)   # capa de arriba: pasante
    n_vert = txt.count("\nVERTEX\n")
    assert n_vert == len(_calado(bl, "Micro", 3)["puntos"][0])


def test_vista_3d_con_formas():
    from flightcase.taller.geometria import Opciones3D, malla_3d
    res, _ = _bloque(espuma_radio=6, equipos=[["Mixer", 300, 200, 60, 0, None, None, 60, "", -1, 2],
                                              ["Micro", 60, 60, 100, 0, 480, 60, 20, "redondo"]])
    m = malla_3d(res, Opciones3D())
    espuma = [f for f in m.faces if f.color_group == "espuma"]
    assert 0 < len(espuma) < 20000


def test_tabla_de_equipos_con_forma(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(tmp_path))
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    ed = w.editores["equipos"]
    ed.poner([["Micro", 60, 60, 100, 0, "c", "c", 0, "redondo", -1, 2]])
    assert ed.tabla.item(0, 8).text() == "redondo" and ed.tabla.item(0, 9).text() == ""
    w.editores["espumas"].poner([[0, 0, 120]])
    w.recalcular()
    assert w.params["equipos"] == [["Micro", 60, 60, 100, 0, "c", "c", 0, "redondo", -1, 2]]
    bl = w.resultado.valores["interiores"].espumas[0]
    assert "contorno" in bl.bolsillos[0]
