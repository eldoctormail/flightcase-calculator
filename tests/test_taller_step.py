"""Exportación del case del taller a STEP: sólidos cerrados, medidas y archivo bien formado."""

import json
import math
import re
from pathlib import Path

import pytest

from flightcase.taller.geometria import malla_3d
from flightcase.taller.modelo import calcular
from flightcase.taller.step import cuerpo_de_solido, cuerpos, exportar_step, texto_step

GOLDEN = sorted((Path(__file__).parent / "golden" / "taller").glob("*.json"))
VALIJA = dict(int_ancho=600, int_prof=400, int_alto_cuerpo=250, int_alto_tapa=80)
RACK = dict(orientacion="frontal", tapas=2, int_ancho=515, int_prof=1100, int_alto_cuerpo=720,
            int_alto_tapa=105, placa_esp=10)
CON_INTERIOR = {
    "valija_espuma": dict(VALIJA, equipos=[["Mixer", 300, 250, 90, 4.5, 30, 30, 30],
                                           ["Micro", 200, 60, 60, 0.4, 380, 30, 40]],
                          espumas=[[0, 0, 120], [0, 0, 60, None, None, 250]]),
    "rack_cajon_y_rack": dict(RACK, equipos=[["Micro", 200, 60, 60, 0.4, "c", 640, 500]], espumas=[[0, 120, 0]],
                              cajones=[[150, 0]], rack_u=6),
}
CASOS = [json.loads(g.read_text(encoding="utf-8"))["params"] for g in GOLDEN] + list(CON_INTERIOR.values())
IDS = [g.stem for g in GOLDEN] + list(CON_INTERIOR)


def _area(pts):
    """Área de un polígono plano en 3D."""
    nx = ny = nz = 0.0
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        nx += p.y * q.z - p.z * q.y
        ny += p.z * q.x - p.x * q.z
        nz += p.x * q.y - p.y * q.x
    return math.sqrt(nx * nx + ny * ny + nz * nz) / 2


@pytest.mark.parametrize("params", CASOS, ids=IDS)
def test_todos_los_cuerpos_son_solidos_cerrados(params):
    res = calcular(params)
    malla = malla_3d(res)
    avisos = []
    lista = cuerpos(malla, avisos)
    assert len(lista) == len(malla.solidos)
    assert all(c.cerrado for c in lista), [c.nombre for c in lista if not c.cerrado]
    assert all(c.volumen() > 0 for c in lista)
    assert not avisos
    # el conjunto ocupa lo mismo que la vista 3D
    a, b = malla.bounding_box
    xs = [p for c in lista for p in c.vertices]
    for i, (lo, hi) in enumerate(((a.x, b.x), (a.y, b.y), (a.z, b.z))):
        assert min(p[i] for p in xs) == pytest.approx(lo) and max(p[i] for p in xs) == pytest.approx(hi)


@pytest.mark.parametrize("params", CASOS[:3] + [CON_INTERIOR["rack_cajon_y_rack"]])
def test_paneles_con_sus_calados_pasantes(params):
    res = calcular(params)
    malla = malla_3d(res)
    t = res.valores["geo"]["espesor"]
    paneles = {p.nombre: p for p in res.paneles}
    perforados = 0
    for so in malla.solidos:
        if so.nombre not in paneles or so.color not in ("base", "lid"):
            continue
        p = paneles[so.nombre]
        c = cuerpo_de_solido(malla, so)
        huecos = sum(_area(ag) for ag in so.agujeros)
        assert c.volumen() == pytest.approx((p.ancho * p.alto - huecos) * t, rel=1e-6), so.nombre
        assert sum(len(cara) - 1 for cara in c.caras) == 2 * len(so.agujeros)   # en las dos caras
        perforados += bool(so.agujeros)
    assert perforados


def test_espuma_con_bolsillos():
    res = calcular(CON_INTERIOR["valija_espuma"])
    malla = malla_3d(res)
    I = res.valores["interiores"]
    for bl in I.espumas:
        so = next(s for s in malla.solidos if s.nombre == bl.nombre)
        c = cuerpo_de_solido(malla, so)
        ua, va = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[bl.eje]
        L = bl.caja.med(bl.eje)
        lleno = bl.caja.med(ua) * bl.caja.med(va) * L
        hueco = sum((b["u1"] - b["u0"]) * (b["v1"] - b["v0"]) * (L - min(L, b["fondo"])) for b in bl.bolsillos)
        assert c.cerrado and c.volumen() == pytest.approx(lleno - hueco, rel=1e-6)
    assert any(bl.bolsillos for bl in I.espumas)


def test_archivo_step_bien_formado(tmp_path):
    res = calcular(CON_INTERIOR["valija_espuma"])
    ruta = tmp_path / "valija.step"
    st = exportar_step(res, str(ruta))
    texto = ruta.read_text(encoding="ascii")
    assert texto.startswith("ISO-10303-21;") and texto.rstrip().endswith("END-ISO-10303-21;")
    assert "AUTOMOTIVE_DESIGN" in texto and "SI_UNIT(.MILLI.,.METRE.)" in texto
    definidos = set(int(n) for n in re.findall(r"^#(\d+)=", texto, re.M))
    usados = set(int(n) for n in re.findall(r"#(\d+)", texto))
    assert usados <= definidos
    assert texto.count("MANIFOLD_SOLID_BREP(") == st.cuerpos
    assert texto.count("NEXT_ASSEMBLY_USAGE_OCCURRENCE(") == st.piezas
    assert "SHELL_BASED_SURFACE_MODEL" not in texto
    # nombres con acentos en la codificación de STEP
    assert "'\\X2\\00C1\\X0\\ngulo de arista'" in texto
    assert "COLOUR_RGB('espuma'" in texto


def test_texto_step_de_un_cubo():
    from flightcase.taller.step import Cuerpo
    V = [(x, y, z) for x in (0, 10) for y in (0, 10) for z in (0, 10)]
    caras = [[[0, 2, 6, 4]], [[1, 5, 7, 3]], [[0, 4, 5, 1]], [[2, 3, 7, 6]], [[0, 1, 3, 2]], [[4, 6, 7, 5]]]
    c = Cuerpo("Cubo", "base", V, caras)
    assert abs(c.volumen()) == pytest.approx(1000)
    texto = texto_step([c], "Prueba")
    assert texto.count("ADVANCED_FACE(") == 6 and texto.count("EDGE_CURVE(") == 12
    assert texto.count("VERTEX_POINT(") == 8


def test_paquete_del_taller_trae_el_step(tmp_path):
    from flightcase.taller.produccion import exportar
    paq = exportar(calcular(VALIJA), str(tmp_path / "salida_valija"), pdf=False)
    ruta = tmp_path / "salida_valija" / "case_3d.step"
    assert str(ruta) in paq.archivos
    assert "PRODUCT('valija'" in ruta.read_text(encoding="ascii")


def test_lo_abre_opencascade(tmp_path):
    """Si está OpenCASCADE (el motor de FreeCAD) se lee el archivo y se validan los sólidos."""
    pytest.importorskip("OCP")
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    res = calcular(CON_INTERIOR["rack_cajon_y_rack"])
    ruta = tmp_path / "rack.step"
    st = exportar_step(res, str(ruta))
    r = STEPControl_Reader()
    assert r.ReadFile(str(ruta)) == IFSelect_RetDone
    r.TransferRoots()
    forma = r.OneShape()
    assert BRepCheck_Analyzer(forma).IsValid()
    ex, n = TopExp_Explorer(forma, TopAbs_SOLID), 0
    while ex.More():
        n += 1
        ex.Next()
    assert n == st.cuerpos
