"""Estilos con reglas propias: rack con puertas, rack inclinado, funda de rack y baúl plegable."""

import math

import pytest

from flightcase.taller import estilos
from flightcase.taller.geometria import Opciones3D, malla_3d
from flightcase.taller.modelo import calcular, parametros_por_defecto
from flightcase.taller.produccion import datos, panel_dxf
from flightcase.taller.planos import generar as gen
from flightcase.taller.step import cuerpos

MEDIDAS = {
    "rack_puertas": dict(int_ancho=490, int_prof=12 * 44.45 + 10, int_alto_cuerpo=450, int_alto_tapa=60, rack_u=12),
    "rack_inclinado": dict(int_ancho=560, int_prof=500, int_alto_cuerpo=380, incl_alto_frente=150, int_alto_tapa=120),
    "funda_rack": dict(int_ancho=485, int_prof=8 * 44.45 + 4, int_alto_cuerpo=450),
    "baul_plegable": dict(int_ancho=1100, int_prof=700, int_alto_cuerpo=600, int_alto_tapa=100),
}


def _con_estilo(eid):
    d = parametros_por_defecto()
    p = dict(d)
    p.update(MEDIDAS[eid])
    return estilos.aplicar(p, estilos.buscar(eid), d)


@pytest.mark.parametrize("eid", list(MEDIDAS))
def test_estilo_completo_3d_y_step(eid):
    res = calcular(_con_estilo(eid))
    assert res.paneles and res.perfiles and res.herrajes
    m = malla_3d(res, Opciones3D())
    av = []
    cs = cuerpos(m, av)
    assert cs and all(c.cerrado for c in cs)
    assert not av
    # abierta y explotada no fallan
    malla_3d(res, Opciones3D(abrir_tapa=300, explotar=100))


def test_otro_estilo_vuelve_a_caja():
    p = _con_estilo("baul_plegable")
    d = parametros_por_defecto()
    q = estilos.aplicar(p, estilos.buscar("baul_tapa_suelta"), d)
    assert q["forma"] == "caja" and not q["puertas"]


def test_rack_con_puertas():
    res = calcular(_con_estilo("rack_puertas"))
    bis = [m for m in res.marcas if m.tipo == "bisagra"]
    assert {m.panel for m in bis} == {"cuerpo_izq", "tapa_izq", "tapa2_izq"}
    assert len([m for m in bis if m.panel == "tapa_izq"]) == 3
    cie = {m.panel for m in res.marcas if m.tipo == "cierre"}
    assert cie <= {"cuerpo_der", "tapa_der", "tapa2_der"}
    h = next(h for h in res.herrajes if h.ref == "08-2251")
    assert h.cantidad == 6 and "por puerta" in h.detalle
    assert res.info["puertas"][0] == "izq"


def test_puertas_fuera_de_rack_avisa():
    res = calcular(dict(puertas=True, bisagras=2))
    assert any("orientación frontal" in a for a in res.avisos)
    assert "puertas" not in res.info


def test_rack_inclinado():
    p = _con_estilo("rack_inclinado")
    res = calcular(p)
    t = res.valores["pared"]
    zf, zr, Y = 150 + t, 380 + t, 500 + 2 * t
    alfa = math.degrees(math.atan2(zr - zf, Y))
    assert float(res.info["inclinado"][0]) == pytest.approx(round(alfa, 1))
    izq = res.panel("cuerpo_izq")
    assert izq.contorno and len(izq.contorno) == 4
    altos = sorted(y for _, y in izq.contorno if y > 0)
    assert altos[1] - altos[0] == pytest.approx((Y - 2 * t) * math.tan(math.radians(alfa)), abs=0.05)
    # la tapa mide lo mismo que el plano inclinado
    S = Y / math.cos(math.atan2(zr - zf, Y))
    assert res.panel("tapa_izq").ancho == pytest.approx(S - 2 * t, abs=0.01)
    # rieles: las U que entran sobre la pendiente
    assert res.valores["interiores"].rack["u"] == math.floor((S - 2 * t) / 44.45)
    # el trapecio llega al DXF y a los planos
    d = datos(res)
    assert d["paneles"]["cuerpo_izq"]["contorno"]
    pz = next(pz for pz in gen.agrupar_piezas(d) if "cuerpo_izq" in pz["ids"])
    assert "cuerpo_der" in pz["ids"] and pz["contorno"]
    dxf = panel_dxf(pz["w"], pz["h"], pz["calados"], contorno=pz["contorno"])
    assert dxf.count("LINE\n  8\n0\n") >= 4


def test_funda_de_rack():
    res = calcular(_con_estilo("funda_rack"))
    assert {p.id for p in res.paneles} == {"piso", "techo", "cuerpo_izq", "cuerpo_der"}
    assert not [m for m in res.marcas if m.tipo == "cierre"]
    rk = res.valores["interiores"].rack
    assert rk["u"] == 8 and rk["traseros"]
    assert sum(p.cantidad for p in res.perfiles) == 12


def test_baul_plegable():
    res = calcular(_con_estilo("baul_plegable"))
    alto = {p.id: p.alto for p in res.paneles}
    # cada pared que se pliega después va más arriba (suplemento) y es más baja
    assert alto["cuerpo_frente"] > alto["cuerpo_trasera"] > alto["cuerpo_izq"] > alto["cuerpo_der"]
    assert any(e[0].startswith("Suplemento") for e in res.extras)
    assert float(res.info["plegable"][0]) < res.valores["ext_alto"] / 2
    assert any(h.ref == "08-2605" for h in res.herrajes)
    m = malla_3d(res, Opciones3D(vista_parte="plegado"))
    alto_pleg = m.bounding_box[1].z - m.bounding_box[0].z
    assert alto_pleg < res.valores["ext_alto"] * 0.6


def test_plegable_que_no_pliega_avisa():
    p = _con_estilo("baul_plegable")
    p["int_prof"] = 400
    res = calcular(p)
    assert any("no se puede plegar" in a for a in res.avisos)
