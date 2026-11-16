"""Estilos especiales: base de ruedas suelta, rack para mezcladora 2 y baúl para guitarras."""

import pytest

from flightcase.taller import estilos, formas
from flightcase.taller import perforaciones as PF
from flightcase.taller.geometria import Opciones3D, malla_3d
from flightcase.taller.modelo import calcular, parametros_por_defecto
from flightcase.taller.produccion import datos
from flightcase.taller.step import cuerpos


def _con(eid, **medidas):
    d = parametros_por_defecto()
    return estilos.aplicar(dict(d, **medidas), estilos.buscar(eid), d)


@pytest.mark.parametrize("eid", ["case_partido", "rack_mezcladora_2", "base_ruedas_suelta", "baul_guitarras"])
def test_especiales_completos(eid):
    res = calcular(_con(eid))
    m = malla_3d(res, Opciones3D())
    av = []
    assert all(c.cerrado for c in cuerpos(m, av)) and not av
    malla_3d(res, Opciones3D(abrir_tapa=200, explotar=50))
    PF.calcular(res)
    assert res.valores["peso"].total > 0


def test_base_de_ruedas_suelta():
    res = calcular(_con("base_ruedas_suelta", int_ancho=600, int_prof=400))
    assert [p.id for p in res.paneles] == ["tabla"]
    tabla = res.panel("tabla")
    assert (tabla.ancho, tabla.alto) == (604, 404)
    assert res.valores["ext_alto"] == 18 + 40
    assert sum(h.cantidad for h in res.herrajes if h.nombre.startswith("Rueda")) == 4
    assert not any(h.nombre.startswith("Esquinero") for h in res.herrajes)
    assert {p.descripcion.split(" (")[0] for p in res.perfiles} == {"Borde a lo ancho", "Borde a lo profundo"}
    assert not res.avisos
    pasos = formas.pasos_instructivo(datos(res), [])
    assert pasos[-1]["titulo"] == "Base terminada"


def test_rack_para_mezcladora_2_lleva_rack_adelante():
    res = calcular(_con("rack_mezcladora_2"))
    assert not res.avisos
    boca = [c for c in res.calados if c.panel == "cuerpo_frente" and c.tipo == "conector"]
    assert len(boca) == 1 and boca[0].alto == pytest.approx(3 * 44.45) and boca[0].ancho == 450
    assert any("rack de adelante" in h.detalle for h in res.herrajes)
    assert res.info["inclinado"][5] == "3"
    pasos = formas.pasos_instructivo(datos(res), [])
    assert any("Rack de adelante" in t for p in pasos for t in p["texto"])
    # si no entra bajo la pendiente, avisa
    p = _con("rack_mezcladora_2")
    p["incl_rack_frente"] = 8
    assert any("no entran bajo la pendiente" in a for a in calcular(p).avisos)


def test_baul_para_guitarras():
    p = _con("baul_guitarras", int_ancho=560, int_prof=1150, int_alto_cuerpo=420, int_alto_tapa=60)
    assert len(p["equipos"]) == 4 and len(p["espumas"]) == 5
    res = calcular(p)
    assert not [a for a in res.avisos if "calado" in a or "choca" in a or "se sale" in a]
    # con equipos propios no los pisa
    q = _con("baul_guitarras", equipos=[["Bajo", 120, 400, 1200]])
    assert q["equipos"] == [["Bajo", 120, 400, 1200]]
