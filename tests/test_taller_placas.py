"""Optimización de cortes en la placa: acomodo, DXF por placa, paquete y pestaña Placas."""

import os
import random

import pytest

from flightcase.taller import placas as P
from flightcase.taller import produccion as PR
from flightcase.taller.modelo import calcular, parametros_por_defecto
from flightcase.taller.planos import generar as gen

L, A, KERF, MARGEN = 2440.0, 1220.0, 4.0, 10.0


def _sin_choques(placas, rotar=True):
    for pl in placas:
        ps = pl["piezas"]
        for p in ps:
            assert p["x"] >= MARGEN - 1e-6 and p["y"] >= MARGEN - 1e-6
            assert p["x"] + p["dw"] <= L - MARGEN + 1e-6 and p["y"] + p["dh"] <= A - MARGEN + 1e-6
            assert rotar or not p["rot"]
        for i, p in enumerate(ps):
            for q in ps[i + 1:]:
                assert (p["x"] + p["dw"] + KERF <= q["x"] + 1e-6 or q["x"] + q["dw"] + KERF <= p["x"] + 1e-6 or
                        p["y"] + p["dh"] + KERF <= q["y"] + 1e-6 or q["y"] + q["dh"] + KERF <= p["y"] + 1e-6)


@pytest.mark.parametrize("rotar", [True, False])
def test_acomoda_sin_choques_y_nunca_peor_que_antes(rotar):
    rnd = random.Random(7)
    mejoras = 0
    for _ in range(60):
        sueltas = [dict(num=i, w=rnd.randint(100, 1100), h=rnd.randint(80, 700)) for i in range(rnd.randint(4, 30))]
        nuevo, ne = P.optimizar([dict(s) for s in sueltas], L, A, KERF, MARGEN, rotar)
        viejo, _ = gen.acomodar_placas([dict(s) for s in sueltas], L, A, KERF, MARGEN, rotar)
        _sin_choques(nuevo, rotar)
        assert sum(len(pl["piezas"]) for pl in nuevo) + len(ne) == len(sueltas)
        assert len(nuevo) <= len(viejo)
        mejoras += len(nuevo) < len(viejo)
        for pl in nuevo:
            assert 0 < pl["aprovechamiento"] <= 1
    assert rotar is False or mejoras > 0


def test_pieza_que_no_entra_y_resumen():
    placas, ne = P.optimizar([dict(num=1, w=3000, h=200), dict(num=2, w=1000, h=500)], L, A, KERF, MARGEN)
    assert [p["num"] for p in ne] == [1] and len(placas) == 1
    r = P.resumen([dict(pl, material="Fenólico") for pl in placas])[0]
    assert r["placas"] == 1 and r["retazo"][2] * r["retazo"][3] > 1000 * 500
    # sin girar, una pieza que solo entra girada no entra
    _, ne = P.optimizar([dict(num=1, w=300, h=1500)], L, A, KERF, MARGEN, rotar=False)
    assert len(ne) == 1


def _entidades(texto):
    t = texto.split("\n")
    pares = [(t[i].strip(), t[i + 1]) for i in range(0, len(t) - 1, 2)]
    ents, cur = [], None
    for c, v in pares:
        if c == "0":
            cur = {"_": v}
            ents.append(cur)
        elif cur is not None:
            cur.setdefault(c, []).append(v)
    return ents


def test_dxf_de_placa_con_pieza_girada():
    pieza = dict(num=1, w=600, h=300, calados=[dict(tipo="calado", cx=100, cy=50, w=80, h=40, r=5),
                                               dict(tipo="rebaje", cx=500, cy=250, w=50, h=30)])
    pl = dict(L=L, A=A, material="Fenólico 9 mm",
              piezas=[dict(num=1, w=600, h=300, x=10, y=10, rot=True, dw=300, dh=600)])
    ents = _entidades(P.placa_dxf(pl, {1: pieza}, {1: [("MARCA", [(0, 0), (600, 300)])]}))
    capas = {e.get("8", [""])[0] for e in ents if e["_"] in ("LINE", "ARC", "TEXT")}
    assert {"PLACA", "0", "REBAJE", "MARCA", "TEXTO"} <= capas
    for e in ents:
        if e["_"] == "LINE" and e["8"][0] != "PLACA":
            for x, y in ((float(e["10"][0]), float(e["20"][0])), (float(e["11"][0]), float(e["21"][0]))):
                assert 10 - 1e-6 <= x <= 310 + 1e-6 and 10 - 1e-6 <= y <= 610 + 1e-6
    # el calado (100, 50) de la pieza girada 90° queda en (10 + 300 - 50, 10 + 100), con 40 x 80
    arcos = [e for e in ents if e["_"] == "ARC" and e["8"][0] == "0"]
    xs = [float(e["10"][0]) for e in arcos]
    ys = [float(e["20"][0]) for e in arcos]
    assert (min(xs) + max(xs)) / 2 == pytest.approx(260) and (min(ys) + max(ys)) / 2 == pytest.approx(110)
    assert max(xs) - min(xs) == pytest.approx(40 - 10) and max(ys) - min(ys) == pytest.approx(80 - 10)


def test_paquete_trae_dxf_por_placa_y_csv(tmp_path):
    p = dict(parametros_por_defecto(), cantidad_cases=3)
    paq = PR.exportar(calcular(p), str(tmp_path), pdf=False, step=False)
    dxf = sorted(os.listdir(tmp_path / "dxf" / "placas"))
    assert len(dxf) == len(paq.placas) >= 2 and all(n.isascii() for n in dxf)
    filas = (tmp_path / "placas.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(filas) == len(paq.placas) + 1 and "dxf/placas/" + dxf[0] in filas[1]
    # cada pieza del pedido está en alguna placa
    total = sum(pz["cant"] for pz in paq.piezas) * 3
    assert sum(len(pl["piezas"]) for pl in paq.placas) == total
    sin_girar = PR.exportar(calcular(p), str(tmp_path / "b"), rotar=False, pdf=False, step=False)
    assert not any(pz["rot"] for pl in sin_girar.placas for pz in pl["piezas"])


def test_pestana_placas(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from flightcase.ui.widgets import TallerWidget
    from flightcase.ui.widgets import placas_widget as PW
    monkeypatch.setattr(PW, "girar_permitido", lambda: True)
    monkeypatch.setattr(PW, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    w = TallerWidget()
    w.editores["cantidad_cases"].widget.setValue(2)
    w.recalcular()
    vp = w.vista_placas
    vp.actualizar()
    assert vp.placas and "placa" in vp.lbl.text() and "Para 2 cases" in vp.lbl.text()
    rutas = vp.guardar(str(tmp_path))
    assert len(rutas) == len(vp.placas) + 1 and all(os.path.isfile(r) for r in rutas)
    vp.chk_girar.setChecked(False)
    assert not any(pz["rot"] for pl in vp.placas for pz in pl["piezas"])
