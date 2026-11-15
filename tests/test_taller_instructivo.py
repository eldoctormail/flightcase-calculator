"""Instructivo de montaje del taller: láminas sin OpenSCAD y PDF completo."""

import json
from pathlib import Path

import pytest

from flightcase.taller.geometria import P_CUERPO, P_ESQ, Opciones3D, malla_3d
from flightcase.taller.modelo import calcular
from flightcase.taller.produccion import exportar
from flightcase.taller.render import renderizar

GOLDEN = Path(__file__).parent / "golden" / "taller"


def _params(caso):
    return json.loads((GOLDEN / f"{caso}.json").read_text(encoding="utf-8"))["params"]


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_opciones_desde_los_defs_del_instructivo():
    op = Opciones3D.desde_defs({"paso": 3, "explotar": 120, "etiquetas": '[["piso","P1"],["techo","P4"]]'})
    assert op.paso == 3 and op.explotar == 120 and op.etiquetas == {"piso": "P1", "techo": "P4"}


def test_pasos_muestran_hasta_el_paso_y_resaltan_lo_nuevo():
    res = calcular({"ruedas": 4})
    hasta_cuerpo = malla_3d(res, Opciones3D(paso=P_CUERPO))
    assert any(f.color_group == "resalte" for f in hasta_cuerpo.faces)
    assert not any(f.label == "Esquinero" for f in hasta_cuerpo.faces)
    assert not any(f.color_group == "lid" for f in hasta_cuerpo.faces)    # la tapa es el paso siguiente
    esquineros = malla_3d(res, Opciones3D(paso=P_ESQ))
    assert all(f.color_group == "resalte" for f in esquineros.faces if f.label == "Esquinero")
    completo = malla_3d(res)
    assert not any(f.color_group == "resalte" for f in completo.faces)


def test_explotar_separa_la_tapa():
    res = calcular()
    alto = lambda m: m.bounding_box[1].z - m.bounding_box[0].z
    assert alto(malla_3d(res, Opciones3D(explotar=100))) > alto(malla_3d(res)) + 200


def test_render_png(qapp, tmp_path):
    from PySide6.QtGui import QImage
    res = calcular()
    ruta = tmp_path / "vista.png"
    assert renderizar(malla_3d(res, Opciones3D(etiquetas={"cuerpo_frente": "P2"})), str(ruta), tam="400,300")
    img = QImage(str(ruta))
    assert (img.width(), img.height()) == (400, 300)
    no_blancos = sum(1 for x in range(0, 400, 8) for y in range(0, 300, 8) if img.pixelColor(x, y).name() != "#ffffff")
    assert no_blancos > 200


@pytest.mark.parametrize("caso", ["mi_case", "rack_audio"])
def test_paquete_con_instructivo(qapp, tmp_path, caso):
    paq = exportar(calcular(_params(caso)), str(tmp_path))
    pdf = tmp_path / "instructivo_montaje.pdf"
    assert pdf.read_bytes()[:4] == b"%PDF" and pdf.stat().st_size > 50_000
    assert (tmp_path / "montaje" / "explotado.png").exists()
    assert (tmp_path / "render.png").exists()
    assert str(pdf) in paq.archivos
