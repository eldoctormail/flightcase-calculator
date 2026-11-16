"""Agujeros, forma y capa del calado de cada herraje desde el catálogo, y capas propias del DXF."""

import copy
import glob
import os

import pytest

from flightcase.taller import catalogo as C
from flightcase.taller import produccion as PR
from flightcase.taller.modelo import CatalogoTaller, calcular

MANIJA = "08-34082"


def _cat(**datos):
    filas = copy.deepcopy(C.incluido())
    for f in filas:
        if f["ref"] == MANIJA:
            f["datos"].update(datos)
    return CatalogoTaller(filas)


def _manijas(d):
    return [c for pid in d["calados"] for c in d["calados"][pid] if c["tipo"] == "manija"]


def test_puntos_se_escriben_y_se_leen():
    v = C.valor_texto("-20 x 15; 20 x 15; 0 x -30,5", "puntos")
    assert v == [[-20, 15], [20, 15], [0, -30.5]]
    assert C.texto_valor(v) == "-20 x 15; 20 x 15; 0 x -30,5"
    assert C.valor_texto(C.texto_valor(v), "puntos") == v
    assert C.valor_texto("[[1, 2], [3, 4]]", "puntos") == [[1, 2], [3, 4]]
    with pytest.raises(ValueError):
        C.valor_texto("hola", "puntos")
    assert C.tipo_medida("manija", "perforaciones") == "puntos"
    assert C.tipo_medida("tapa_m", "pata_int") == "num"


def test_agujeros_propios_con_su_diametro_y_capa():
    cat = _cat(perforaciones=[[-72, 0], [72, 0]], perforacion_d=5.2, capa_agujeros="mecha 5")
    d = PR.datos(calcular({"ref_manija": MANIJA}, cat))
    propios = [a for ags in d["perforaciones"].values() for a in ags if a[0] == "MECHA_5"]
    assert len(propios) == 4 and all(a[3] == 5.2 for a in propios)       # 2 por manija, una en cada lateral


def test_calado_redondo_y_en_su_capa():
    d = PR.datos(calcular({"ref_manija": MANIJA}, _cat(forma_corte="redondo", capa_calado="Fresado-6")))
    m = _manijas(d)
    assert m and all(c["capa"] == "FRESADO-6" and len(c["puntos"][0]) == 72 for c in m)
    c = m[0]
    xs = [p[0] for p in c["puntos"][0]]
    assert max(xs) - min(xs) == pytest.approx(c["w"], abs=0.01)
    texto = PR.panel_dxf(500, 400, m[:1])
    assert "\nFRESADO-6\n" in texto and "POLYLINE" in texto


def test_calado_con_dibujo(tmp_path):
    svg = tmp_path / "corte.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
                   '<polygon points="0,0 200,0 200,100 100,60 0,100"/></svg>')
    d = PR.datos(calcular({"ref_manija": MANIJA}, _cat(forma_corte="dibujo", corte_dibujo=str(svg))))
    m = _manijas(d)
    assert m and all(c.get("puntos") for c in m)
    c = m[0]
    xs = [p[0] for pol in c["puntos"] for p in pol]
    assert min(xs) >= c["cx"] - c["w"] / 2 - 0.1 and max(xs) <= c["cx"] + c["w"] / 2 + 0.1
    # sin archivo: rectangular y con aviso
    d = PR.datos(calcular({"ref_manija": MANIJA}, _cat(forma_corte="dibujo")))
    assert not any(c.get("puntos") for c in _manijas(d)) and any("dibujo" in a for a in d["avisos"])


def test_mapa_y_cambio_de_capas():
    mapa = PR.mapa_capas([["PERFORACIONES", "drill", 4], ["0", "cut", ""], ["marca", "", 2], [""], "x"])
    assert mapa == {"PERFORACIONES": ("DRILL", 4), "0": ("CUT", None), "MARCA": ("MARCA", 2)}
    texto = PR.panel_dxf(100, 50, [], agujeros=[("PERFORACIONES", 10, 10, 4.1)])
    nuevo = PR.aplicar_capas(texto, mapa)
    assert "\nDRILL\n" in nuevo and "\nPERFORACIONES\n" not in nuevo and "\nCUT\n" in nuevo
    assert " 62\n4\n" in nuevo
    assert PR.aplicar_capas(texto, {}) == texto
    # dos capas con el mismo nombre: una sola en la tabla
    junto = PR.aplicar_capas(texto, {"PERFORACIONES": ("0", None)})
    assert junto.count("  0\nLAYER\n  2\n0\n") == 1
    assert "TABLE\n  2\nLAYER\n 70\n2\n" in junto


def test_exportar_usa_las_capas_propias(tmp_path):
    res = calcular({"dxf_capas": [["PERFORACIONES", "DRILL", 4], ["0", "CUT", 1]]})
    PR.exportar(res, str(tmp_path), pdf=False, instructivo=False, step=False)
    piezas = glob.glob(os.path.join(tmp_path, "dxf", "*.dxf"))
    placas = glob.glob(os.path.join(tmp_path, "dxf", "placas", "*.dxf"))
    assert piezas and placas
    for f in piezas + placas:
        t = open(f, encoding="utf-8").read()
        assert "\nPERFORACIONES\n" not in t and "\nCUT\n" in t


def test_dibujo_se_copia_a_la_carpeta_del_usuario(tmp_path, monkeypatch):
    from flightcase.taller import calados_cnc
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(tmp_path / "datos"))
    svg = tmp_path / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect x="0" y="0" width="80" height="40"/></svg>')
    nombre = calados_cnc.importar_dibujo(str(svg), "LBD/1")
    assert nombre == "LBD_1.svg" and os.path.isfile(calados_cnc.ruta_dibujo(nombre))
    d = PR.datos(calcular({"ref_manija": MANIJA}, _cat(corte_dibujo=nombre)))
    assert all(c.get("puntos") for c in _manijas(d))
    with pytest.raises(ValueError):
        calados_cnc.importar_dibujo(str(tmp_path / "x.txt"), "x")
