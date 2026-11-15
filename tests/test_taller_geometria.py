"""Vista 3D del taller: los paneles quedan dentro del case y no se pisan entre sí."""

import json
from pathlib import Path

import pytest

from flightcase.taller.geometria import malla_3d
from flightcase.taller.modelo import calcular

GOLDEN = sorted((Path(__file__).parent / "golden" / "taller").glob("*.json"))


def _caja(col, panel, t):
    """Caja alineada a los ejes (en coordenadas locales del case) que ocupa un panel."""
    pts = []
    for a in (0, panel.ancho):
        for b in (0, panel.alto):
            for c in (0, t):
                pts.append([col["o"][i] + a * col["u"][i] + b * col["v"][i] + c * col["n"][i] for i in range(3)])
    return [(min(p[i] for p in pts), max(p[i] for p in pts)) for i in range(3)]


@pytest.mark.parametrize("caso", GOLDEN, ids=[g.stem for g in GOLDEN])
def test_paneles_dentro_del_case_y_sin_superponerse(caso):
    res = calcular(json.loads(caso.read_text(encoding="utf-8"))["params"])
    geo, v = res.valores["geo"], res.valores
    paneles = {p.id: p for p in res.paneles}
    # todos los paneles del case (no la base de ruedas ni las bandejas) tienen ubicación
    ubicados = {c["id"] for c in geo["colocaciones"]}
    assert ubicados == {p for p in paneles if p != "base_ruedas" and not p.startswith("bandeja")}
    cajas = {c["id"]: _caja(c, paneles[c["id"]], geo["espesor"]) for c in geo["colocaciones"]}
    ext = (v["ext_ancho"], v["ext_prof"], v["ext_alto"])
    for pid, caja in cajas.items():
        for i in range(3):
            assert -0.01 <= caja[i][0] and caja[i][1] <= ext[i] + 0.01, (pid, caja, ext)
    if geo["hibrido"]:
        # con perfil híbrido las paredes se cruzan unos mm dentro del perfil de esquina
        # (igual que en flightcase.scad): sólo se controla que estén dentro del case
        return
    ids = sorted(cajas)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            pisa = all(min(cajas[a][k][1], cajas[b][k][1]) - max(cajas[a][k][0], cajas[b][k][0]) > 0.01
                       for k in range(3))
            assert not pisa, f"{a} y {b} se superponen"


def test_malla_tiene_paneles_perfiles_y_calados():
    res = calcular({"ruedas": 4, "bandejas": [[400, 300, 120]], "base_ruedas": []})
    m = malla_3d(res)
    grupos = {f.color_group for f in m.faces}
    assert {"base", "lid", "profile", "wall"} <= grupos
    assert any("manija" in s.label for s in m.segments)
    a, b = m.bounding_box
    v = res.valores
    assert b.x - a.x >= v["ext_ancho"] and b.z - a.z >= v["ext_alto"]


@pytest.mark.parametrize("orientacion", ["horizontal", "frontal"])
def test_orientaciones_acostadas_giran_el_case(orientacion):
    res = calcular({"orientacion": orientacion, "int_ancho": 600, "int_prof": 400,
                    "int_alto_cuerpo": 250, "int_alto_tapa": 80})
    a, b = malla_3d(res).bounding_box
    v = res.valores
    # el eje de las tapas (alto local) pasa a X en horizontal y a Y en frontal
    largo = b.x - a.x if orientacion == "horizontal" else b.y - a.y
    assert largo == pytest.approx(v["ext_alto"], abs=40)  # + esquineros y perfiles salientes
