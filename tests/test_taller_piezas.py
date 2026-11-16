"""Piezas sueltas: cambiar un esquinero, un ángulo o un panel solo (piezas.py)."""

import numpy as np
import pytest

from flightcase.taller import piezas as PZ
from flightcase.taller.geometria import malla_3d
from flightcase.taller.modelo import calcular
from flightcase.taller.perforaciones import calcular as perforaciones

ARRIBA = ["esq_001", "esq_011", "esq_101", "esq_111"]


def _esq(res, ref):
    return sum(h.cantidad for h in res.herrajes if h.ref == ref and h.detalle.startswith("pata"))


def test_sin_cambios_queda_igual():
    res = calcular()
    assert [(p.descripcion, p.largo, p.cantidad) for p in res.perfiles if p.corte == "recto"] == [
        ("Aristas a lo ancho (piso y techo)", 568, 4), ("Aristas a lo profundo (piso y techo)", 368, 4),
        ("Verticales cuerpo", 214, 4), ("Verticales tapa", 44, 4)]
    assert [h.cantidad for h in res.herrajes if h.nombre == "Esquinero bola"] == [8]
    ids = [i for i, _ in PZ.opciones(res)]
    assert len([i for i in ids if i.startswith("esq_")]) == 8
    assert len([i for i in ids if i.startswith("ar_")]) == 16


def test_esquineros_apilables_solo_arriba():
    base = calcular()
    res = calcular({"piezas": [[p, "08-4018", "negro", 0] for p in ARRIBA]})
    assert _esq(res, "08-4018") == 4
    assert [h.cantidad for h in res.herrajes if h.nombre == "Esquinero bola"] == [4]
    fila = next(h for h in res.herrajes if h.ref == "08-4018")
    assert "negro" in fila.detalle and "arriba" in fila.detalle
    # los ángulos de arriba se acortan hasta el esquinero nuevo (pata 50 + 2), los de abajo no
    largos = sorted((p.descripcion, p.largo, p.cantidad) for p in res.perfiles if p.descripcion.startswith("Aristas a lo ancho"))
    assert largos == [("Aristas a lo ancho (piso y techo)", 514, 2), ("Aristas a lo ancho (piso y techo)", 568, 2)]
    # remaches: cambian las patas y los tramos
    rem = lambda r: next(h.cantidad for h in r.herrajes if "Remache" in h.nombre)
    assert rem(res) != rem(base)
    # vista 3D: las caras del esquinero llevan su id y el color
    m = malla_3d(res)
    caras = [f for f in m.faces if f.pieza == "esq_001"]
    assert caras and any(f.color == PZ.COLORES_NOMBRE["negro"] for f in caras)
    assert any(s.pieza == "esq_001" and s.color_hex for s in m.solidos)


def test_un_angulo_de_otro_perfil_y_otro_sin_poner():
    res = calcular({"piezas": [["ar_x_01", "08-6209", "rojo", 0], ["ar_zc_00", "", "", 1]]})
    otro = [p for p in res.perfiles if p.ref == "08-6209"]
    assert len(otro) == 1 and otro[0].cantidad == 1 and "rojo" in otro[0].descripcion
    assert next(p.cantidad for p in res.perfiles if p.descripcion == "Verticales cuerpo") == 3
    ar = {a["id"]: a for a in res.valores["geo"]["aristas_case"]}
    assert ar["ar_x_01"]["ala"] == 20 and ar["ar_zc_00"]["quitar"]
    assert not [f for f in malla_3d(res).faces if f.pieza == "ar_zc_00"]


def test_perforaciones_siguen_a_cada_pieza():
    base = perforaciones(calcular())
    res = perforaciones(calcular({"piezas": [["ar_zc_00", "", "", 1]]}))
    # sin el ángulo vertical de adelante a la izquierda, el frente y el lateral izquierdo pierden su fila
    for pid in ("cuerpo_frente", "cuerpo_izq"):
        assert len([a for a in res[pid] if a.origen == "perfil"]) < len([a for a in base[pid] if a.origen == "perfil"])
    assert len([a for a in res["cuerpo_der"] if a.origen == "perfil"]) == \
        len([a for a in base["cuerpo_der"] if a.origen == "perfil"])


def test_color_de_un_panel_y_placa_desde_piezas():
    res = calcular({"piezas": [["techo", "", "azul", 0]]})
    assert res.valores["geo"]["colores_paneles"] == {"techo": PZ.COLORES_NOMBRE["azul"]}
    assert all(f.color == PZ.COLORES_NOMBRE["azul"] for f in malla_3d(res).faces if f.pieza == "techo")


def test_filas_poner_y_cambios():
    filas = PZ.poner([], PZ.Cambio("esq_000", "08-4018"))
    filas = PZ.poner(filas, PZ.Cambio("esq_000", "", "rojo"))
    assert filas == [["esq_000", "", "rojo", 0]]
    assert PZ.poner(filas, PZ.Cambio("esq_000")) == []
    assert PZ.color_hex("ROJO") == PZ.COLORES_NOMBRE["rojo"] and PZ.color_hex("#abc") == "#aabbcc"
    assert PZ.color_hex("cualquiera") == ""


def test_avisos_de_piezas():
    res = calcular({"piezas": [["esq_000", "08-6105", "", 0], ["ar_x_00", "08-4018", "", 0], ["nada", "", "rojo", 0]]})
    txt = "\n".join(res.avisos)
    assert "no es un esquinero" in txt and "no es un ángulo" in txt and "«nada»" in txt


def test_dos_tapas_y_acostado():
    for extra in ({"tapas": 2}, {"orientacion": "horizontal"}):
        res = calcular(dict(extra, piezas=[["esq_000", "08-4018", "", 0]]))
        assert _esq(res, "08-4018") == 1
        assert malla_3d(res).faces


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_clic_elige_la_pieza_de_adelante(qapp):
    """pieza_en() del lienzo: la cara más cercana bajo el mouse (con matrices armadas a mano)."""
    from PySide6.QtCore import QPointF
    from flightcase.ui.widgets.schema_3d_widget import Schema3DCanvas
    from flightcase.taller.malla import Point3D, PolygonFace3D, WireframeMesh3D

    def cuadrado(z, pieza):
        v = tuple(Point3D(x, y, z) for x, y in ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)))
        return PolygonFace3D(v, (0, 0, 1), pieza=pieza)

    c = Schema3DCanvas()
    c.resize(200, 200)
    c.set_mesh(WireframeMesh3D(faces=[cuadrado(-0.5, "atras"), cuadrado(0.5, "adelante")]))
    # mirando desde +z: la profundidad de pantalla es -z
    mv = np.diag([1.0, 1.0, -1.0, 1.0])
    c._matrices = (mv, np.eye(4))
    assert c.pieza_en(QPointF(100, 100)) == "adelante"
    assert c.pieza_en(QPointF(2, 2)) == ""


def test_cuadro_de_la_pieza_cambia_el_proyecto(qapp):
    from flightcase.ui.widgets.taller_widget import TallerWidget
    w = TallerWidget()
    w.elegir_pieza("esq_001")
    pp = w.panel_pieza
    assert not pp.isHidden() and "arriba" in pp.lbl_titulo.text()
    pp.cmb_modelo.setCurrentIndex(pp.cmb_modelo.findData("08-4018"))
    pp.cmb_alcance.setCurrentIndex(pp.cmb_alcance.findData("tapa"))
    pp.cmb_color.setCurrentIndex(pp.cmb_color.findData("negro"))
    pp.cambiado.emit()
    assert sorted(f[0] for f in w.params["piezas"]) == ARRIBA
    assert _esq(w.resultado, "08-4018") == 4
    assert w.editores["piezas"].valor() == w.params["piezas"]      # queda en la tabla (y en el .scad)
    # un panel: la placa va a «Material por panel» y el color a las piezas
    w.elegir_pieza("techo")
    assert pp.lbl_modelo.text() == "Placa:"
    pp.cmb_color.setCurrentIndex(pp.cmb_color.findData("rojo"))
    pp.cambiado.emit()
    assert ["techo", "", "rojo", 0] in w.params["piezas"]
    # volver a la de siempre: sólo esa pieza
    w.elegir_pieza("esq_001")
    pp._restablecer()
    assert "esq_001" not in [f[0] for f in w.params["piezas"]]
    w.elegir_pieza("")
    assert pp.isHidden()
