"""Paneles de conexión y energía: conectores puestos a mano sobre una cara."""

import os

import pytest

from flightcase.taller import herrajes_manuales as hm
from flightcase.taller.modelo import calcular, catalogo_actual
from flightcase.taller.produccion import exportar


def _conectores(*filas):
    return calcular({"herrajes_manuales": [list(f) for f in filas]})


def test_conector_d_calado_y_tornillos_en_diagonal():
    r = _conectores(["CON-NAC3-IN", "frente", 150, 100])
    man = r.valores["manuales"]
    col = man.colocados[0]
    assert col.forma == "conector" and (col.pw, col.ph) == (26, 31)
    cal = [k for k in col.calados if k.tipo == "conector a mano"]
    tor = [k for k in col.calados if k.tipo == "agujero a mano"]
    assert len(cal) == 1 and cal[0].ancho == 24 and cal[0].radio == 12     # redondo Ø24
    assert len(tor) == 2 and {round(k.ancho, 1) for k in tor} == {3.2}
    (a, b) = sorted(tor, key=lambda k: k.cx)
    assert b.cx - a.cx == pytest.approx(19) and a.cy - b.cy == pytest.approx(24)   # en diagonal
    assert not man.avisos
    nombres = {h.nombre: h.cantidad for h in r.herrajes}
    assert nombres["powerCON entrada (azul), conector D"] == 1
    assert nombres["Tornillo M3 x 12 + tuerca para conector"] == 2


def test_rectangular_y_cuatro_tornillos_girado():
    r = _conectores(["CON-IEC-C14", "frente", 150, 100], ["CON-SCHUKO", "frente", 300, 100, 90])
    iec, schuko = r.valores["manuales"].colocados
    assert [(k.ancho, k.alto) for k in iec.calados] == [(27.5, 20)]          # a presión: sin tornillos
    assert len([k for k in schuko.calados if k.tipo.startswith("agujero")]) == 4


def test_conectores_pegados_no_avisan_pero_encimados_si():
    pegados = _conectores(["CON-XLR3-H", "frente", 150, 100], ["CON-XLR3-H", "frente", 182, 100])
    assert not pegados.valores["manuales"].avisos
    encimados = _conectores(["CON-XLR3-H", "frente", 150, 100], ["CON-XLR3-H", "frente", 165, 100])
    assert any("se pisan" in a for a in encimados.valores["manuales"].avisos)


def test_fila_de_conectores_centrada():
    from flightcase.ui.widgets.herrajes_2d_widget import fila_de_conectores
    cat = catalogo_actual()
    fila = fila_de_conectores(cat, ["CON-NAC3-IN", "CON-NAC3-OUT", "CON-XLR3-H"], 300, 100, separacion=6)
    xs = [x for _, x, _ in fila]
    assert xs == pytest.approx([268, 300, 332]) and {y for _, _, y in fila} == {100}
    col = fila_de_conectores(cat, ["CON-NAC3-IN", "CON-NAC3-OUT"], 300, 100, separacion=4, vertical=True)
    assert [y for _, _, y in col] == pytest.approx([117.5, 82.5])


def test_dxf_3d_y_peso(tmp_path):
    from flightcase.taller.geometria import malla_3d
    r = _conectores(["CON-TRUE1-IN", "frente", 150, 100], ["CON-PASACABLES", "frente", 300, 120])
    sin = calcular()
    m = malla_3d(r)
    assert sum(1 for s in m.solidos if s.nombre.startswith("powerCON TRUE1")) == 3   # brida, frente y cuerpo
    assert r.valores["peso"].vacio > sin.valores["peso"].vacio
    paq = exportar(r, str(tmp_path), pdf=False)
    dxf = next(a for a in paq.archivos if "cuerpo_frente" in a and a.endswith(".dxf"))
    with open(dxf, encoding="utf-8") as f:
        assert f.read().count("ARC") >= 4 * 3 + 4     # calado redondo, 2 tornillos y el pasacables
    with open(os.path.join(str(tmp_path), "materiales.csv"), encoding="utf-8-sig") as f:
        assert "CON-TRUE1-IN" in f.read()


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_boton_panel_de_conexiones(qapp):
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    h = w.herrajes
    h.set_cara("frente")
    assert h.panel_conexiones(["CON-NAC3-IN", "CON-NAC3-OUT", "CON-ETHERCON", "CON-XLR3-H"]) == 4
    filas = w.params["herrajes_manuales"]
    assert [f[0] for f in filas] == ["CON-NAC3-IN", "CON-NAC3-OUT", "CON-ETHERCON", "CON-XLR3-H"]
    assert {f[1] for f in filas} == {"frente"}
    assert sum(1 for k in w.resultado.calados if k.tipo == "conector a mano") == 4
    assert any(c["categoria"] == "conector" for c in hm.catalogo_colocable(catalogo_actual()))
