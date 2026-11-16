"""Medida interior de placa a placa o de metal a metal (taller/medida_interior.py)."""

import pytest

from flightcase.taller.modelo import calcular, parametros_por_defecto

D = parametros_por_defecto()


def test_de_placa_a_placa_no_cambia_nada():
    a, b = calcular({}), calcular({"medida_interior": "placa"})
    assert (a.valores["ext_ancho"], a.valores["ext_prof"], a.valores["ext_alto"]) == \
        (b.valores["ext_ancho"], b.valores["ext_prof"], b.valores["ext_alto"])
    assert a.valores["medida_interior"] is None


def test_de_metal_a_metal_agranda_la_boca():
    a = calcular({})
    m = calcular({"medida_interior": "metal", "cierre_pata_int": 2})
    assert m.valores["ext_ancho"] == pytest.approx(a.valores["ext_ancho"] + 4)
    assert m.valores["ext_prof"] == pytest.approx(a.valores["ext_prof"] + 4)
    assert m.valores["ext_alto"] == pytest.approx(a.valores["ext_alto"])      # el aro no toca los altos
    mi = m.valores["medida_interior"]
    assert mi["pedido"]["int_ancho"] == D["int_ancho"] and mi["suma"]["int_ancho"] == 4


def test_hibrido_agranda_tambien_los_altos():
    a = calcular({"sistema": "hibrido"})
    m = calcular({"sistema": "hibrido", "medida_interior": "metal", "hibrido_pata_int": 1.5})
    assert m.valores["ext_ancho"] == pytest.approx(a.valores["ext_ancho"] + 3)
    assert m.valores["ext_alto"] == pytest.approx(a.valores["ext_alto"] + 3)


def test_dato_del_catalogo_manda(monkeypatch):
    from flightcase.taller import medida_interior as MI
    from flightcase.taller.modelo import catalogo_actual
    cat = catalogo_actual()
    monkeypatch.setattr(cat, "dato", lambda ref, k, d: 2.5 if k == "pata_int" and ref == "08-6203" else d)
    assert MI.patas(dict(D, sistema="hibrido", ref_hibrido="08-6203"), cat) == (2.5, 2.5)


def test_equipo_que_no_pasa_por_la_boca_avisa():
    eq = [["Consola", D["int_ancho"] - 1, 300, 100]]
    res = calcular({"equipos": eq})
    assert any("no pasa por la boca" in a for a in res.avisos)
    res = calcular({"equipos": eq, "medida_interior": "metal"})
    assert not any("no pasa por la boca" in a for a in res.avisos)
    # girado entra: no avisa
    assert not any("no pasa por la boca" in a for a in calcular({"equipos": [["Caja", 390, 596, 100]]}).avisos)


def test_formas_sin_perfiles_no_cambian():
    a = calcular({"forma": "tabla", "ruedas": 4})
    b = calcular({"forma": "tabla", "ruedas": 4, "medida_interior": "metal"})
    assert a.valores["ext_ancho"] == b.valores["ext_ancho"] and b.valores["medida_interior"] is None


def test_formas_con_perfil_de_cierre_agrandan():
    a = calcular({"forma": "slam"})
    b = calcular({"forma": "slam", "medida_interior": "metal"})
    assert b.valores["ext_ancho"] == pytest.approx(a.valores["ext_ancho"] + 3)
