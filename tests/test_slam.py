"""Tapas slam: tapas y puertas planas en marco de perfil slam (formas.py, forma = slam)."""

import pytest

from flightcase.taller import estilos, formas
from flightcase.taller.geometria import Opciones3D, malla_3d
from flightcase.taller.modelo import calcular, parametros_por_defecto
from flightcase.taller.produccion import datos
from flightcase.taller.step import cuerpos

SLAM = ["baul_slam_hd", "tapa_slam_doble", "tapa_slam_adelante", "tapas_slam_adelante_atras", "rack_slam"]
RACK = dict(int_ancho=485, int_prof=12 * 44.45 + 4, int_alto_cuerpo=500, int_alto_tapa=0)


def _con(eid, **medidas):
    d = parametros_por_defecto()
    p = dict(d, **medidas)
    return estilos.aplicar(p, estilos.buscar(eid), d)


@pytest.mark.parametrize("eid", SLAM)
def test_estilos_slam_completos(eid):
    est = estilos.buscar(eid)
    res = calcular(_con(eid, **(RACK if est.params["orientacion"] == "frontal" else {})))
    assert res.valores["forma"] == "slam" and not res.avisos
    tapas = [p for p in res.paneles if p.grupo == "tapa"]
    assert len(tapas) == {"tapa_slam_doble": 2, "tapas_slam_adelante_atras": 2, "rack_slam": 2}.get(eid, 1)
    nombres = {h.nombre: h.cantidad for h in res.herrajes}
    assert any(n.startswith("Cierre slam") for n in nombres) and any("piano" in n.lower() for n in nombres)
    assert any(p.nombre == "Perfil slam (marco de tapa plana)" for p in res.perfiles)
    m = malla_3d(res, Opciones3D())
    av = []
    assert all(c.cerrado for c in cuerpos(m, av)) and not av
    malla_3d(res, Opciones3D(abrir_tapa=200, explotar=50))
    pasos = formas.pasos_instructivo(datos(res), [])
    assert [p["titulo"] for p in pasos][-1] == "Case terminado"


def test_medidas_de_una_caja_con_tapa_plana():
    res = calcular(_con("baul_slam_hd", int_ancho=600, int_prof=400, int_alto_cuerpo=250, int_alto_tapa=80))
    t = res.valores["pared"]
    assert res.valores["ext_alto"] == pytest.approx(250 + 80 + 2 * t)     # cuerpo + tapa, sin paredes de tapa
    techo = next(p for p in res.paneles if p.id == "tapa_techo")
    assert techo.ancho == pytest.approx(600 + 2 * t - 2 * 20 - 6)          # marco de 20 y 3 mm de luz
    assert not any(p.id.startswith("tapa_") and p.id != "tapa_techo" for p in res.paneles)


def test_rack_slam_lleva_rieles_a_todo_el_alto():
    res = calcular(_con("rack_slam", **RACK))
    assert res.valores["interiores"] is not None and res.valores["interiores"].rack
    assert any("Riel" in h.nombre or "riel" in h.nombre for h in res.herrajes) or \
        any("Riel" in p.nombre or p.descripcion.startswith("Riel") for p in res.perfiles)


def test_puerta_doble_traba_con_pasadores():
    res = calcular(_con("tapa_slam_doble"))
    nombres = {h.nombre: h.cantidad for h in res.herrajes}
    assert nombres["Pasador embutido (falleba) para puerta doble"] == 2
    assert any(p.descripcion.startswith("Tope entre las hojas") for p in res.perfiles)


def test_caras_que_no_existen_avisan():
    res = calcular(dict(parametros_por_defecto(), forma="slam", slam_caras="abajo"))
    assert any("slam_caras" in a for a in res.avisos)


FRONTALES = ["apertura_frontal_puerta_doble", "puertas_dobles_y_tapa", "tapa_adelante_y_arriba"]


@pytest.mark.parametrize("eid", FRONTALES + ["tapa_lidmaker", "piso_basemaker", "lidmaker_basemaker"])
def test_estilos_de_tapa_plana_completos(eid):
    est = estilos.buscar(eid)
    res = calcular(_con(eid))
    assert res.valores["forma"] == "slam"
    m = malla_3d(res, Opciones3D())
    av = []
    assert all(c.cerrado for c in cuerpos(m, av)) and not av
    malla_3d(res, Opciones3D(abrir_tapa=200, explotar=50))
    pasos = formas.pasos_instructivo(datos(res), [])
    assert pasos[-1]["titulo"] == "Case terminado"
    hojas = est.params.get("slam_hojas", 1)
    tapas = [p for p in res.paneles if p.id.startswith("tapa_")]
    assert len(tapas) == hojas + (1 if est.params["slam_caras"] == "arriba_frente" else 0)


def test_tapa_lidmaker_es_suelta_con_cierres_mariposa():
    res = calcular(_con("tapa_lidmaker"))
    nombres = {h.nombre: h.cantidad for h in res.herrajes}
    assert not any("piano" in n.lower() or n.startswith("Cierre slam") for n in nombres)
    assert nombres["Cierre mariposa"] >= 4
    assert any(p.nombre.lower().startswith("perfil lindmaker") or "lidmaker" in p.nombre.lower() for p in res.perfiles)
    assert {m.panel for m in res.marcas if m.tipo == "cierre"} <= {"cuerpo_frente", "cuerpo_trasera",
                                                                     "cuerpo_izq", "cuerpo_der"}
    assert res.info["slam"][4] == "lidmaker"


def test_piso_basemaker_encastrado_en_su_marco():
    res = calcular(_con("piso_basemaker"))
    t, c = res.valores["pared"], 20
    piso = res.panel("piso")
    assert piso.ancho == pytest.approx(res.valores["ext_ancho"] - 2 * c)
    assert any(p.descripcion.startswith("Marco del piso") for p in res.perfiles)
    assert not any(p.descripcion.startswith("Aristas") and "piso" in p.descripcion.lower() for p in res.perfiles)
    assert res.info["slam"][5] == "1" and t > 0
