"""Tipos de rueda: giratorias, fijas y con freno, cazoletas embutidas y base suelta (wheel board)."""

import pytest

from flightcase.taller.geometria import malla_3d
from flightcase.taller.modelo import CatalogoTaller, calcular

GRANDE = dict(int_ancho=800, int_prof=600, int_alto_cuerpo=500, ruedas=4, rueda_frenos=2)


def _herraje(r, texto):
    return [h for h in r.herrajes if texto in h.nombre]


def test_catalogo_trae_ruedas_y_cazoletas_nuevas():
    cat = CatalogoTaller()
    ruedas = [f for f in cat.filas if f["categoria"] == "rueda"]
    assert {f["datos"]["diametro"] for f in ruedas} >= {75, 80, 100, 125, 150}
    assert any(f["datos"].get("tipo") == "fija" for f in ruedas)
    assert any(f["datos"].get("freno") == 2 for f in ruedas)        # freno total
    assert len([f for f in cat.filas if f["categoria"] == "cazoleta"]) >= 2


def test_por_defecto_no_cambia_nada():
    r = calcular(dict(GRANDE))
    assert not {"ruedas_fijas", "cazoletas", "base_suelta"} & set(r.info)
    assert [m.texto for m in r.marcas if m.tipo == "rueda"] == ["freno", "freno", "placa rueda", "placa rueda"]


def test_ruedas_fijas_del_lado_opuesto_al_freno():
    r = calcular(dict(GRANDE, rueda_fijas=2, ref_rueda="08-372151", ref_rueda_freno="08-372191",
                      ref_rueda_fija="LBD-R100F"))
    marcas = [m for m in r.marcas if m.tipo == "rueda"]
    assert [m.texto for m in marcas] == ["freno", "freno", "fija", "fija"]
    assert max(m.x for m in marcas if m.texto == "freno") < min(m.x for m in marcas if m.texto == "fija")
    assert _herraje(r, "Rueda fija 100")[0].cantidad == 2
    assert not _herraje(r, "Rueda giratoria 100 mm azul (")       # no quedan giratorias sin freno
    assert r.info["ruedas_fijas"] == ["2"]
    assert not any("es fija" in a or "distinto alto" in a for a in r.avisos)
    m = malla_3d(r)
    assert sum(1 for s in m.solidos if s.nombre == "Rueda fija") > 0


def test_fijas_limitadas_por_los_frenos_y_avisos_de_tipo():
    r = calcular(dict(GRANDE, rueda_frenos=3, rueda_fijas=2))
    assert r.info["ruedas_fijas"] == ["1"]
    assert any("sólo pueden ser fijas 1" in a for a in r.avisos)
    r = calcular(dict(GRANDE, ref_rueda="LBD-R100F"))
    assert any("es fija" in a for a in r.avisos)
    r = calcular(dict(GRANDE, rueda_fijas=2, ref_rueda="08-372151", ref_rueda_freno="08-372191",
                      ref_rueda_fija="LBD-R150F"))
    assert any("distinto alto" in a for a in r.avisos)


def test_cazoletas_calan_el_piso_y_bajan_el_case():
    sin = calcular(dict(GRANDE, ref_rueda="08-372151", ref_rueda_freno="08-372191"))
    r = calcular(dict(GRANDE, cazoletas=True, ref_cazoleta="LBD-CZ100", ref_rueda="08-372151",
                      ref_rueda_freno="08-372191"))
    caz = [c for c in r.calados if c.tipo == "cazoleta"]
    assert len(caz) == 4 and all(c.panel == "piso" and (c.ancho, c.alto) == (170, 160) for c in caz)
    assert not [c for c in r.calados if c.tipo == "agujero"]        # los agujeros los trae la cazoleta
    assert float(r.info["ruedas"][1]) == float(sin.info["ruedas"][1]) - 35
    assert _herraje(r, "Cazoleta")[0].cantidad == 4
    rem = lambda x: next(h.cantidad for h in x.herrajes if "emache" in h.nombre)
    assert rem(r) > rem(sin)
    assert any("entran" in a and "dentro del case" in a for a in r.avisos)
    assert not any("se pisan" in a for a in r.avisos)
    m = malla_3d(r)
    assert sum(1 for s in m.solidos if s.nombre == "Cazoleta") >= 4 * 9


def test_cazoleta_chica_para_la_rueda_avisa():
    r = calcular(dict(GRANDE, cazoletas=True, ref_cazoleta="LBD-CZ100", ref_rueda="LBD-R125G",
                      ref_rueda_freno="LBD-R125GF"))
    assert any("no entra en la cazoleta" in a for a in r.avisos)


def test_cazoletas_no_van_con_base_de_ruedas():
    r = calcular(dict(GRANDE, cazoletas=True, base_ruedas=[700, 500, 18]))
    assert not [c for c in r.calados if c.tipo == "cazoleta"]
    assert any("no se usan cazoletas" in a for a in r.avisos)


def test_base_suelta_con_marco_y_sin_perforar_el_piso():
    r = calcular(dict(GRANDE, base_suelta=True, base_ruedas=[18]))
    ext_a, ext_p = r.valores["ext_ancho"], r.valores["ext_prof"]
    base = r.panel("base_ruedas")
    assert base is not None
    assert base.ancho == pytest.approx(ext_a + 2 * (4 + 1.5)) and base.alto == pytest.approx(ext_p + 2 * (4 + 1.5))
    assert not [c for c in r.calados if c.panel == "piso"]
    assert len([c for c in r.calados if c.panel == "base_ruedas" and c.tipo == "agujero"]) == 16
    marco = [p for p in r.perfiles if p.descripcion.startswith("Marco de la base")]
    assert [p.cantidad for p in marco] == [2, 2]
    assert _herraje(r, "cabeza fresada")[0].cantidad == 16
    assert _herraje(r, "marco de la base suelta")
    assert not _herraje(r, "fijar la base al piso")
    assert r.info["base_suelta"] == ["4", "30", "1.5"]
    # los bulones de las ruedas no chocan con el marco
    agujeros = [c for c in r.calados if c.panel == "base_ruedas"]
    assert min(min(c.cx, c.cy) - c.ancho / 2 for c in agujeros) >= 30 + 5 - 1e-6
    m = malla_3d(r)
    assert sum(1 for s in m.solidos if s.nombre == "Marco de la base") == 8


def test_base_suelta_solo_parado():
    r = calcular(dict(GRANDE, base_suelta=True, orientacion="frontal"))
    assert r.panel("base_ruedas") is None
    assert any("sólo se calcula para cases parados" in a for a in r.avisos)


def test_asistente_ofrece_tipos_de_rueda():
    from flightcase.ui.widgets.asistente import RUEDAS_ASISTENTE
    assert [c for c, *_ in RUEDAS_ASISTENTE] == ["no", "giratorias", "fijas", "cazoletas", "suelta"]
