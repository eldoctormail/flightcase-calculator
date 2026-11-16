"""Modelos 3D (STEP) de los herrajes propios: lectura, triángulos, catálogo, vista 3D y STEP del case.

Los .step de tests/datos_step los hizo OpenCASCADE; los volúmenes de referencia son los que
da OpenCASCADE para cada pieza.
"""

import os
import re
from pathlib import Path

import numpy as np
import pytest

from flightcase.taller import catalogo as C
from flightcase.taller import modelos3d, step_leer

DATOS = Path(__file__).parent / "datos_step"
CAJA = str(DATOS / "caja_agujero_filete.step")      # 60 x 40 x 20, agujero Ø16, cuatro filetes
VOL_CAJA = 43757.345


@pytest.fixture(autouse=True)
def carpeta(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(tmp_path))
    modelos3d._memoria.clear()


def _vol_area(m):
    V, T = m.vertices, m.triangulos
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    return (float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6),
            float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2))


@pytest.mark.parametrize("archivo,volumen,caja,tol", [
    ("caja_agujero_filete.step", VOL_CAJA, ((0, 0, 0), (60, 40, 20)), 0.01),
    ("caja_pulgadas.step", VOL_CAJA, ((0, 0, 0), (60, 40, 20)), 0.01),       # escrito en pulgadas
    ("ensamble.step", 3 * VOL_CAJA, ((-60, -40, 0), (100, 60, 120)), 0.01),  # tres copias giradas
    ("cono.step", 3267.256, ((-10, -10, 0), (10, 10, 20)), 0.02),
    ("esfera.step", 14137.167, ((-15, -15, -15), (15, 15, 15)), 0.02),      # una cara, sin bordes
    ("toro.step", 9869.604, ((-25, -25, -5), (25, 25, 5)), 0.04),
])
def test_lee_las_piezas_como_opencascade(archivo, volumen, caja, tol):
    m = step_leer.leer(str(DATOS / archivo)).malla()
    vol, _area = _vol_area(m)
    assert vol == pytest.approx(volumen, rel=tol)      # positivo: los triángulos miran hacia afuera
    lo, hi = m.caja
    assert lo == pytest.approx(caja[0], abs=0.2) and hi == pytest.approx(caja[1], abs=0.2)
    assert not m.avisos


def test_ensamble_y_unidades():
    ens = step_leer.leer(str(DATOS / "ensamble.step")).malla()
    assert len(ens.solidos) == 3 and len({s for s, _m in ens.solidos}) == 1    # la misma pieza tres veces
    pulg = step_leer.leer(str(DATOS / "caja_pulgadas.step"))
    assert pulg.escala == pytest.approx(25.4)
    assert pulg.malla().escala == pytest.approx(25.4)


def test_aristas_sin_costuras():
    m = step_leer.leer(CAJA).malla()
    # 12 aristas de la caja + 2 círculos del agujero + las de los filetes; ninguna costura del cilindro
    assert 14 <= len(m.aristas) <= 30
    for a in m.aristas:
        assert a.shape[1] == 3 and len(a) >= 2


def test_triangular_con_agujero():
    borde = [(0, 0), (10, 0), (10, 10), (0, 10)]
    agujero = [(3, 3), (3, 7), (7, 7), (7, 3)]
    pts = borde + agujero
    tris = step_leer.triangular([borde, agujero])
    area = sum(abs((pts[b][0] - pts[a][0]) * (pts[c][1] - pts[a][1]) - (pts[b][1] - pts[a][1]) * (pts[c][0] - pts[a][0])) / 2
               for a, b, c in tris)
    assert area == pytest.approx(100 - 16)


def test_no_es_un_step(tmp_path):
    malo = tmp_path / "malo.step"
    malo.write_text("solid algo\nendsolid\n")
    with pytest.raises(step_leer.ErrorStep):
        step_leer.leer(str(malo))
    with pytest.raises(step_leer.ErrorStep):
        modelos3d.importar(str(malo), "MALO")
    assert not os.path.exists(os.path.join(modelos3d.carpeta(), "MALO.step"))   # no deja la copia


def test_importar_copia_y_guarda_los_triangulos(monkeypatch):
    nombre, mod = modelos3d.importar(CAJA, "MI/PIEZA 1")
    assert nombre == "MI_PIEZA_1.step"
    assert os.path.exists(modelos3d.ruta(nombre)) and os.path.exists(modelos3d.ruta(nombre) + ".malla.npz")
    assert modelos3d.medidas(mod.malla) == pytest.approx((60, 40, 20))
    assert modelos3d.medidas(mod.malla, "-Y") == pytest.approx((60, 20, 40))
    # importar otra vez el mismo archivo no hace otra copia
    assert modelos3d.importar(CAJA, "MI/PIEZA 1")[0] == nombre
    # la segunda vez se lee de la copia guardada, sin volver a leer el STEP
    modelos3d._memoria.clear()
    monkeypatch.setattr(step_leer, "leer", lambda *_a: (_ for _ in ()).throw(AssertionError("leyó el STEP")))
    otra = modelos3d.cargar(nombre)
    assert np.allclose(otra.malla.vertices, mod.malla.vertices, atol=1e-3)
    assert len(otra.malla.aristas) == len(mod.malla.aristas) and otra.malla.solidos[0][0] == mod.malla.solidos[0][0]


def test_orientacion_apoya_sobre_la_cara():
    m = step_leer.leer(CAJA).malla()
    for frente in modelos3d.FRENTES:
        R = modelos3d.ejes_frente(frente)
        assert np.linalg.det(R) == pytest.approx(1)          # sin espejar
        M = modelos3d.orientacion(m, frente, adentro=3)
        q = m.vertices @ M[:3, :3].T + M[:3, 3]
        assert q[:, 2].min() == pytest.approx(-3)
        assert (q[:, 0].min() + q[:, 0].max()) == pytest.approx(0, abs=1e-9)


# ---------------------------------------------------------------------------
# En el case
# ---------------------------------------------------------------------------

def _con_modelo(ref="MI-PIEZA", archivo=CAJA, **datos):
    nombre, _mod = modelos3d.importar(archivo, ref)
    filas = C.filas_actuales() + [{"ref": ref, "categoria": "extra", "nombre": "Mi pieza" if ref == "MI-PIEZA" else ref,
                                   "datos": dict(modelo=nombre, **datos), "verificado": True}]
    C.guardar(filas)
    return nombre


@pytest.mark.parametrize("orientacion", ["vertical", "horizontal", "frontal"])
def test_herraje_con_modelo_en_la_vista_3d(orientacion):
    from flightcase.taller.geometria import malla_3d
    from flightcase.taller.modelo import calcular
    _con_modelo()
    r = calcular({"orientacion": orientacion, "herrajes_manuales": [["MI-PIEZA", "frente", 200, 150, 90]]})
    c = r.valores["manuales"].colocados[0]
    assert c.modelo == "MI-PIEZA.step"
    assert sorted((c.pw, c.ph)) == pytest.approx([40, 60])      # mide lo que mide el modelo
    m = malla_3d(r)
    tri = [f for f in m.faces if not f.contorno]
    assert len(tri) == len(modelos3d.cargar("MI-PIEZA.step").malla.triangulos)
    assert all(f.label == "Mi pieza" for f in tri)
    assert any(s.style == "arista" for s in m.segments)
    assert len(m.modelos) == 1
    # el modelo queda apoyado sobre la cara de afuera del frente, centrado donde se puso
    P = np.array([(p.x, p.y, p.z) for f in tri for p in f.vertices])
    tam = sorted(P.max(axis=0) - P.min(axis=0))
    assert tam == pytest.approx([20, 40, 60], abs=0.01)
    # y no queda además la caja simplificada
    assert not any(f.label == "Mi pieza" and f.contorno for f in m.faces)


def test_sin_archivo_avisa_y_dibuja_simplificado():
    from flightcase.taller.geometria import malla_3d
    from flightcase.taller.modelo import calcular
    nombre = _con_modelo()
    os.remove(modelos3d.ruta(nombre))
    modelos3d._memoria.clear()
    r = calcular({"herrajes_manuales": [["MI-PIEZA", "frente", 200, 150]]})
    assert any("modelo 3D" in a for a in r.valores["manuales"].avisos)
    m = malla_3d(r)
    assert any(f.label == "Mi pieza" for f in m.faces) and not m.modelos


def test_step_del_case_lleva_el_modelo_entero(tmp_path):
    from flightcase.taller.modelo import calcular
    from flightcase.taller.step import exportar_step
    _con_modelo()
    _con_modelo("PULG", str(DATOS / "caja_pulgadas.step"), modelo_frente="-Y")
    r = calcular({"herrajes_manuales": [["MI-PIEZA", "frente", 200, 150], ["MI-PIEZA", "arriba", 200, 150],
                                        ["PULG", "izq", 200, 150]]})
    res = exportar_step(r, str(tmp_path / "case.step"))
    assert not res.avisos
    texto = (tmp_path / "case.step").read_text(encoding="ascii")
    # las caras curvas del modelo van como son (cilindro del agujero, filetes), no en triángulos
    assert texto.count("CYLINDRICAL_SURFACE(") >= 3
    assert texto.count("PRODUCT('Mi pieza'") == 2 and texto.count("PRODUCT('PULG'") == 1
    assert "CONVERSION_BASED_UNIT('UNIDAD'" in texto      # el de pulgadas lleva su unidad
    # todas las referencias apuntan a entidades que existen
    ids = set(re.findall(r"^#(\d+)=", texto, re.M))
    usadas = set(re.findall(r"#(\d+)", re.sub(r"'(?:[^']|'')*'", "", texto)))
    assert usadas <= ids


def test_espejado_va_como_superficies(tmp_path):
    from flightcase.taller.geometria import malla_3d
    from flightcase.taller.modelo import calcular
    _con_modelo()
    r = calcular({"herrajes_manuales": [["MI-PIEZA", "frente", 200, 150, 0, 1]]})
    m = malla_3d(r)
    assert not m.modelos and any(s.nombre == "Mi pieza" for s in m.solidos)


def test_lo_abre_opencascade_con_el_modelo(tmp_path):
    pytest.importorskip("OCP")
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.GProp import GProp_GProps
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    from flightcase.taller.geometria import malla_3d
    from flightcase.taller.modelo import calcular
    from flightcase.taller.step import exportar_step
    _con_modelo()
    _con_modelo("PULG", str(DATOS / "caja_pulgadas.step"), modelo_frente="-Y", modelo_adentro=5)
    r = calcular({"orientacion": "horizontal", "herrajes_manuales": [["MI-PIEZA", "frente", 200, 150, 90],
                                                                     ["PULG", "izq", 200, 150]]})
    exportar_step(r, str(tmp_path / "case.step"))
    vista = {}
    for f in malla_3d(r).faces:
        if not f.contorno:
            vista.setdefault(f.label, []).extend((p.x, p.y, p.z) for p in f.vertices)
    rd = STEPControl_Reader()
    rd.ReadFile(str(tmp_path / "case.step"))
    rd.TransferRoots()
    ex = TopExp_Explorer(rd.OneShape(), TopAbs_SOLID)
    cajas = []
    while ex.More():
        p = GProp_GProps()
        BRepGProp.VolumeProperties_s(ex.Current(), p)
        if abs(p.Mass() - VOL_CAJA) < 1:          # el volumen exacto: no son triángulos
            b = Bnd_Box()
            BRepBndLib.Add_s(ex.Current(), b, True)
            c1, c2 = b.CornerMin(), b.CornerMax()
            cajas.append((c1.X(), c1.Y(), c1.Z(), c2.X(), c2.Y(), c2.Z()))
        ex.Next()
    assert len(cajas) == 2
    for nombre in ("Mi pieza", "PULG"):          # en el mismo lugar que en la vista 3D
        P = np.array(vista[nombre])
        esperado = tuple(P.min(axis=0)) + tuple(P.max(axis=0))
        assert any(np.allclose(c, esperado, atol=0.05) for c in cajas)


def test_boton_del_catalogo(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from flightcase.ui.widgets.catalogo_widget import CatalogoDialog
    d = CatalogoDialog(categoria="extra")
    f = d.nuevo("extra")
    texto = d.modelo_3d(CAJA)
    assert texto and "60.0 x 40.0 mm" in texto
    fila = next(x for x in C.filas_actuales() if x["ref"] == f["ref"])
    assert fila["datos"]["modelo"].endswith(".step")
    assert os.path.exists(modelos3d.ruta(fila["datos"]["modelo"]))
    # las columnas del modelo están en la tabla de la categoría
    assert {"modelo", "modelo_frente", "modelo_adentro"} <= {c[1] for c in d._columnas}
    d.close()
