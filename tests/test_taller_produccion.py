"""El paquete del taller hecho en Python sale igual que el de generar.py con OpenSCAD.

Los archivos de tests/golden/taller_paquete/<caso> son la salida de generar.py
(--sin-render) sobre los proyectos del taller: las listas CSV tal cual y el largo total
de los contornos de cada DXF.
"""

import json
from pathlib import Path

import pytest

from flightcase.application import ExportTallerPackFromScadUseCase
from flightcase.taller.modelo import calcular
from flightcase.taller.produccion import exportar, largo_contornos, panel_dxf

GOLDEN = Path(__file__).parent / "golden"
CASOS = sorted(p.name for p in (GOLDEN / "taller_paquete").iterdir() if p.is_dir())


def _params(caso):
    return json.loads((GOLDEN / "taller" / f"{caso}.json").read_text(encoding="utf-8"))["params"]


@pytest.mark.parametrize("caso", CASOS)
def test_paquete_igual_que_generar_py(caso, tmp_path):
    esperado = GOLDEN / "taller_paquete" / caso
    paq = exportar(calcular(_params(caso)), str(tmp_path), pdf=False)
    for nombre in ("lista_cortes.csv", "materiales.csv"):
        assert (tmp_path / nombre).read_bytes() == (esperado / nombre).read_bytes(), nombre
    largos = json.loads((esperado / "largos_dxf.json").read_text(encoding="utf-8"))
    assert sorted(p.name for p in (tmp_path / "dxf").iterdir()) == sorted(largos)
    for nombre, largo_os in largos.items():
        # OpenSCAD aproxima las esquinas redondeadas con polígonos de 32 lados
        largo = largo_contornos((tmp_path / "dxf" / nombre).read_text(encoding="utf-8"))
        assert largo == pytest.approx(largo_os, rel=2e-3), nombre
    assert len(paq.archivos) == len(largos) + 2


def test_dxf_panel_con_calados_y_rebaje():
    txt = panel_dxf(600, 400, [
        dict(tipo="manija", cx=300, cy=200, w=120, h=60, r=10),
        dict(tipo="rebaje", cx=100, cy=100, w=50, h=50, r=5),
    ])
    assert txt.rstrip().endswith("EOF")
    assert txt.count("\nARC\n") == 4                      # sólo la manija lleva radios
    assert txt.count("\nLINE\n") == 4 + 4 + 4             # contorno, manija, rebaje
    assert txt.count("\nREBAJE\n") == 4 + 1              # 4 líneas + la definición de la capa
    assert largo_contornos(txt) == pytest.approx(2000 + (2 * (100 + 40) + 2 * 3.14159265 * 10) + 200, rel=1e-6)


def test_planos_pdf_desde_scad(tmp_path):
    scad = tmp_path / "caja.scad"
    scad.write_text(
        'include <flightcase_gen/flightcase.scad>\n'
        'int_ancho = 500;\nint_prof = 300;\nint_alto_cuerpo = 200; // cuerpo\nint_alto_tapa = 60;\n'
        'flightcase();\n', encoding="utf-8")
    paq = ExportTallerPackFromScadUseCase.execute(str(scad), str(tmp_path / "salida"))
    pdf = tmp_path / "salida" / "planos.pdf"
    assert pdf.read_bytes()[:4] == b"%PDF"
    assert any(a.endswith(".dxf") for a in paq.archivos)
    frente = next(p for p in paq.piezas if "cuerpo_frente" in p["ids"])
    assert frente["w"] > 500  # el panel toma las medidas del .scad, no las de por defecto


def test_menu_paquete_del_taller(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from flightcase.ui import FlightCaseMainWindow

    QApplication.instance() or QApplication([])
    scad = tmp_path / "rack.scad"
    scad.write_text("int_ancho = 482;\nflightcase();\n", encoding="utf-8")
    window = FlightCaseMainWindow(restore_settings=False, load_last_project=False)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(scad), ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    mensajes = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: mensajes.append(a[2]))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail(a[2]))
    window._export_taller_pack()
    assert (tmp_path / "salida_rack" / "planos.pdf").exists()
    assert mensajes and "salida_rack" in mensajes[0]
