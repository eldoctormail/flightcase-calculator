"""Peso real del case (flightcase/taller/peso.py)."""

import json

import pytest

from flightcase.taller import catalogo as C
from flightcase.taller import modelo as m
from flightcase.taller import peso


@pytest.fixture
def P():
    return m.parametros_por_defecto()


def _cat_con(cambios):
    filas = [dict(f) for f in C.incluido()]
    for f in filas:
        if f["ref"] in cambios:
            f["datos"] = {**f["datos"], **cambios[f["ref"]]}
    return m.CatalogoTaller(filas)


def test_case_por_defecto_tiene_peso_razonable(P):
    pc = m.calcular(P).valores["peso"]
    # 618 x 418 x 348 de fenólico 9 mm: unos 13 kg
    assert 9 < pc.vacio < 18
    assert set(pc.partes) == {"Placas", "Perfiles", "Herrajes"}
    assert pc.total == pc.vacio
    assert abs(sum(pc.partes.values()) - pc.total) < 0.05


def test_placas_por_area_espesor_y_densidad(P):
    P["ref_placa"] = "LBD-FEN9"
    cat = _cat_con({"LBD-FEN9": {"densidad": 1000}})
    res = m.calcular(P, cat)
    pc = res.valores["peso"]
    area = sum(p.ancho * p.alto for p in res.paneles) / 1e6
    calados = sum(peso._area_calado(c) for c in res.calados if "rebaje" not in c.tipo) / 1e6
    placas = [x for x in pc.lineas if x.parte == "Placas"]
    assert len(placas) == 1 and placas[0].origen == "catálogo"
    assert placas[0].total == pytest.approx((area - calados) * 9 * 1.0, rel=1e-6)


def test_peso_hoja_del_catalogo(P):
    P["ref_placa"] = "LBD-FEN9"
    cat = _cat_con({"LBD-FEN9": {"peso_hoja": 2.44 * 1.22 * 9 * 0.8}})     # 800 kg/m³
    pc = m.calcular(P, cat).valores["peso"]
    lin = next(x for x in pc.lineas if x.parte == "Placas")
    assert lin.unitario == pytest.approx(0.8 * 9)


def test_densidad_estimada_por_material():
    assert peso.densidad_por_nombre("Fenólico 9 mm") == 700
    assert peso.densidad_por_nombre("MDF 9 mm") == 750
    assert peso.densidad_por_nombre("Polipropileno alveolar 4 mm") == 450
    assert peso.densidad_por_nombre("Cartón") is None


def test_angulo_por_seccion_y_catalogo():
    cat = m.catalogo_actual()
    g, origen = peso.gramos_metro_perfil(cat, "08-6105", "")
    assert origen == "estimado" and g == pytest.approx((60 - 1.5) * 1.5 * 2.7)
    g, origen = peso.gramos_metro_perfil(None, "", "Ángulo 30x30x1.5")
    assert g == pytest.approx((60 - 1.5) * 1.5 * 2.7)
    cat = _cat_con({"08-6105": {"peso_m": 300}})
    assert peso.gramos_metro_perfil(cat, "08-6105", "") == (300, "catálogo")


def test_herrajes_con_peso_del_catalogo(P):
    P["ref_remache"] = "04-042"
    cat = _cat_con({"04-042": {"peso": 2}})
    res = m.calcular(P, cat)
    h = next(h for h in res.herrajes if h.ref == "04-042")
    lin = next(x for x in res.valores["peso"].lineas if x.nombre == h.nombre)
    assert lin.origen == "catálogo" and lin.total == pytest.approx(h.cantidad * 0.002)


def test_herraje_desconocido_queda_sin_dato():
    g, origen = peso.gramos_herraje(None, "", "Cosa rara")
    assert g is None
    assert peso.gramos_herraje(None, "", "Rueda giratoria Ø125 con freno")[0] == 1500


def test_equipos_y_espuma_suman_aparte(P):
    P["equipos"] = [["Mixer", 300, 200, 80, 6.5]]
    P["espuma_bloques"] = 1
    pc = m.calcular(P).valores["peso"]
    assert pc.partes["Equipos"] == 6.5
    assert pc.total == pytest.approx(pc.vacio + 6.5, abs=0.01)
    assert "con equipos" in pc.resumen()


def test_forro_de_espuma_por_area(P):
    P["espuma_esp"] = 10
    res = m.calcular(P)
    lin = [x for x in res.valores["peso"].lineas if x.parte == "Espuma"]
    assert lin and lin[0].unidad == "m²"
    assert lin[0].unitario == pytest.approx(30 * 10 / 1000)


def test_catalogo_tiene_campos_de_peso():
    claves = {c: [k for k, *_ in med] for c, _, med in C.CATEGORIAS}
    assert "densidad" in claves["placa"] and "peso_hoja" in claves["placa"]
    assert "peso_m" in claves["angulo"] and "peso_m" in claves["hibrido"]
    for c in ("esquinero", "cierre", "manija", "rueda", "remache", "rack", "extra"):
        assert "peso" in claves[c]


def test_planilla_csv_lleva_el_peso():
    filas = [{"ref": "X1", "categoria": "cierre", "nombre": "Cierre", "datos": {"peso": 320}, "verificado": True}]
    txt = C.a_csv(filas)
    assert "peso" in txt.splitlines()[0]
    vuelta, avisos = C.desde_csv(txt)
    assert vuelta[0]["datos"]["peso"] == 320 and not avisos


def test_filas_tabla():
    pc = m.calcular().valores["peso"]
    filas = peso.filas_tabla(pc)
    assert all(len(f) == 6 for f in filas)
    assert any(f[0] == "Placas" for f in filas)
