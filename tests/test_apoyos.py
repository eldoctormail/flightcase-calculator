"""Patines bajo el piso y patas de mesa."""

import pytest

from flightcase.taller.geometria import malla_3d
from flightcase.taller.modelo import calcular


def _sin(r):
    return [h.nombre for h in r.herrajes]


def test_sin_apoyos_no_cambia_nada():
    a, b = calcular(), calcular({"patines": 0, "patas_mesa": 0})
    assert len(a.herrajes) == len(b.herrajes) and a.extras == b.extras and a.valores["geo"]["apoyos"] is None


def test_patines_a_lo_largo_con_tornillos():
    r = calcular({"patines": 3, "int_ancho": 1000})
    v = r.valores
    pat = v["geo"]["apoyos"]["patines"]
    assert len(pat) == 3 and all(p[2] - p[0] > p[3] - p[1] for p in pat)     # a lo ancho (el lado largo)
    assert min(p[1] for p in pat) >= 20 and max(p[3] for p in pat) <= v["ext_prof"] - 20
    extra = next(e for e in r.extras if e[0] == "Patín")
    assert extra[4] == 3 and extra[3] == 45 and "Pino" in extra[5]
    torn = next(h for h in r.herrajes if h.nombre.startswith("Tornillo para madera"))
    agujeros = [c for c in r.calados if c.panel == "piso" and c.tipo == "agujero"]
    assert torn.cantidad == len(agujeros) and torn.cantidad >= 6
    assert len([m for m in r.marcas if m.tipo == "patin"]) == 3
    assert any(l.nombre.startswith("Pino") for l in v["peso"].lineas)
    r2 = calcular({"patines": 2, "patin_sentido": "largo", "ruedas": 4})
    pat2 = r2.valores["geo"]["apoyos"]["patines"]
    assert all(p[3] - p[1] > p[2] - p[0] for p in pat2)
    assert any("patines y también ruedas" in a for a in r2.avisos)


def test_patas_de_mesa_en_la_tapa_y_bajo_el_cuerpo():
    r = calcular({"patas_mesa": 4})
    soportes = [m for m in r.marcas if m.tipo == "pata"]
    assert len(soportes) == 4 and {m.panel for m in soportes} == {"techo"}
    assert "Pata de mesa" in _sin(r) and "Soporte de pata de mesa con rosca" in _sin(r)
    base = calcular()
    rem = lambda x: next(h for h in x.herrajes if h.nombre.startswith("Remache")).cantidad
    assert rem(r) >= rem(base) + 16
    assert r.info["patas_mesa"][0] == "tapa" and r.valores["peso"].total > base.valores["peso"].total + 5
    c = calcular({"patas_mesa": 4, "patas_en": "cuerpo", "pata_largo": 600})
    assert {m.panel for m in c.marcas if m.tipo == "pata"} == {"piso"}
    m = malla_3d(c)
    patas = [f for f in m.faces if f.label == "Pata de mesa"]
    assert patas and min(p.z for f in patas for p in f.vertices) == pytest.approx(-606, abs=1)
    assert calcular({"patas_mesa": 4, "orientacion": "frontal", "tapas": 2}).avisos[-1].startswith("Los patines")


def test_vista_oculta_patas_y_patines(qapp=None):
    from flightcase.taller.vista import EstadoVista, VistaCase
    r = calcular({"patas_mesa": 4, "patas_en": "cuerpo", "patines": 2})
    v = VistaCase(malla_3d(r), r)
    assert {"patas", "ruedas"} <= {g.categoria for g in v.grupos}
    sin = v.aplicar(EstadoVista(ocultos={"patas"}))
    assert not any(f.label == "Pata de mesa" for f in sin.faces) and any(f.label == "Patín" for f in sin.faces)
