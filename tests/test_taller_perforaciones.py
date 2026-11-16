"""Capa de perforaciones (remaches y tornillos) en los DXF por pieza y por placa."""

import copy
import math
import os

import pytest

from flightcase.taller import perforaciones as PF
from flightcase.taller import placas as P
from flightcase.taller.estilos import aplicar, estilos_incluidos
from flightcase.taller.modelo import CatalogoTaller, calcular, parametros_por_defecto
from flightcase.taller.produccion import datos, exportar, panel_dxf

CIERRE_EMB = "08-17373S"   # cierre mariposa embutido, calado 76 x 70, 8 remaches
MANIJA = "08-34082"        # asa retráctil embutida, calado 134 x 81, 6 remaches
RUEDA = "08-372151"


def _remaches_lista(res):
    h = next(h for h in res.herrajes if "emache" in h.nombre)
    return h.cantidad


def _circulos(texto):
    v = [x.strip() for x in texto.splitlines()]
    out = []
    for i in range(1, len(v)):
        if v[i] == "CIRCLE" and v[i - 1] == "0":
            campos, j = {}, i + 1
            while j + 1 < len(v) and v[j] != "0":
                campos[v[j]] = v[j + 1]
                j += 2
            out.append((campos["8"], float(campos["10"]), float(campos["20"]), 2 * float(campos["40"])))
    return out


def test_mismos_remaches_que_la_lista_de_materiales():
    """Con el case por defecto, los agujeros son los remaches de la lista (que suma un 10%)."""
    res = calcular()
    ag = PF.calcular(res)
    total = sum(len(l) for l in ag.values())
    assert total == pytest.approx(_remaches_lista(res) / 1.1, rel=0.03)
    origenes = {a.origen for l in ag.values() for a in l}
    assert {"perfil", "esquinero", "cierre", "manija"} <= origenes


@pytest.mark.parametrize("estilo", [e.id for e in estilos_incluidos()])
def test_agujeros_dentro_del_panel_y_fuera_de_los_calados(estilo):
    D = parametros_por_defecto()
    e = next(x for x in estilos_incluidos() if x.id == estilo)
    res = calcular(aplicar(dict(D), e, D))
    ag = PF.calcular(res)
    # la base de ruedas suelta sólo se remacha por el canto de la tabla: no tiene agujeros en las caras
    assert ag or res.valores.get("forma") == "tabla"
    for pid, lista in ag.items():
        p = res.panel(pid)
        cal = [c for c in res.calados if c.panel == pid and c.tipo != "rebaje"]
        for a in lista:
            assert a.d / 2 < a.x < p.ancho - a.d / 2 and a.d / 2 < a.y < p.alto - a.d / 2, (pid, a)
            for c in cal:
                assert not (abs(a.x - c.cx) < c.ancho / 2 and abs(a.y - c.cy) < c.alto / 2), (pid, a, c)
        for i, a in enumerate(lista):
            for b in lista[i + 1:]:
                assert math.hypot(a.x - b.x, a.y - b.y) >= PF.DISTANCIA_MINIMA


def test_paneles_iguales_tienen_los_mismos_agujeros():
    """Las piezas agrupadas (izquierda/derecha, frente/trasera) se cortan con un solo DXF:
    los agujeros de todas tienen que coincidir, dados vuelta si hace falta."""
    from flightcase.taller.planos import generar as gen
    D = parametros_por_defecto()
    for e in estilos_incluidos():
        d = datos(calcular(aplicar(dict(D), e, D)))
        for pz in gen.agrupar_piezas(d):
            w, h = pz["w"], pz["h"]

            def firma(pid, fx, fy):
                return sorted((round(w - x if fx else x), round(h - y if fy else y))
                              for _, x, y, _ in d["perforaciones"].get(pid, []))
            ref = firma(pz["ids"][0], 0, 0)
            for otro in pz["ids"][1:]:
                assert any(firma(otro, fx, fy) == ref for fx in (0, 1) for fy in (0, 1)), (e.id, pz["ids"])


def test_remaches_del_angulo_en_el_medio_del_ala():
    res = calcular()
    frente = PF.calcular(res)["cuerpo_frente"]
    ala = res.valores["geo"]["ala"]
    # el frente va de punta a punta: la fila vertical queda a medio ala del canto
    assert any(a.origen == "perfil" and a.x == pytest.approx(ala / 2) for a in frente)


def test_hibrido_no_queda_pegado_al_canto():
    """En el perfil híbrido el panel arranca hibrido_descuento adentro: el remache va en el
    medio de lo que el ala cubre del panel, no a medio ala de la arista."""
    piso = PF.calcular(calcular({"sistema": "hibrido"}))["piso"]
    filas = [a for a in piso if a.origen == "perfil"]
    assert min(min(a.x, a.y) for a in filas) >= 7


def test_cierres_embutidos_y_bisagras():
    base = PF.calcular(calcular())
    res = calcular({"ref_cierre": CIERRE_EMB, "bisagras": 2})
    ag = PF.calcular(res)
    n_cierres = len([m for m in res.marcas if m.tipo == "cierre" and res.panel(m.panel).grupo == "cuerpo"])
    cierres = sum(1 for l in ag.values() for a in l if a.origen == "cierre")
    assert cierres == 8 * n_cierres
    assert sum(1 for l in ag.values() for a in l if a.origen == "bisagra") == 2 * 6
    # el cierre embutido: los agujeros del cuerpo van a los costados del calado
    cal = next(c for c in res.calados if c.tipo == "cierre")
    lados = [a for a in ag[cal.panel] if a.origen == "cierre" and abs(a.y - cal.cy) <= cal.alto / 2 and abs(a.x - cal.cx) < 100]
    assert lados and all(abs(abs(a.x - cal.cx) - (cal.ancho / 2 + 6)) < 0.01 for a in lados)
    assert sum(len(l) for l in ag.values()) != sum(len(l) for l in base.values())


def test_herrajes_a_mano():
    sin = PF.calcular(calcular({"manijas": False}))
    res = calcular({"manijas": False, "herrajes_manuales": [
        [MANIJA, "izq", 200, 120], [CIERRE_EMB, "frente", 300, 0], [RUEDA, "abajo", 150, 150],
        ["logo", "frente", 300, 120, 0, 0, 100, 50, "no_existe.svg"]]})
    ag = PF.calcular(res)
    nuevos = lambda pid, origen: [a for a in ag.get(pid, []) if a.origen == origen]
    assert len(nuevos("cuerpo_izq", "manija")) == 6
    assert len([a for l in ag.values() for a in l if a.origen == "cierre"]) == \
        len([a for l in sin.values() for a in l if a.origen == "cierre"]) + 8
    # placa de logo: 4 remaches en las esquinas; la rueda va con bulones (capa 0), sin remaches
    logo = nuevos("cuerpo_frente", "herraje")
    assert len(logo) == 4
    xs, ys = sorted({round(a.x) for a in logo}), sorted({round(a.y) for a in logo})
    assert len(xs) == len(ys) == 2 and xs[1] - xs[0] == 100 - 12 and ys[1] - ys[0] == 50 - 12
    assert not nuevos("piso", "herraje")


def test_perforaciones_propias_del_catalogo():
    filas = copy.deepcopy(CatalogoTaller().filas)
    for f in filas:
        if f["ref"] == CIERRE_EMB:
            f["datos"]["perforaciones"] = [[-50, -40], [50, -40], [0, 30]]
    cat = CatalogoTaller(filas)
    res = calcular({"ref_cierre": CIERRE_EMB}, cat)
    ag = PF.calcular(res)
    m = next(m for m in res.marcas if m.tipo == "cierre" and m.panel == "cuerpo_frente")
    linea = m.y + res.valores["geo"]["cierre_m_alto"]
    propios = sorted((a.x - m.x, round(a.y - linea, 2)) for a in ag["cuerpo_frente"]
                     if a.origen == "cierre" and abs(a.x - m.x) < 60)
    assert propios == [(-50, -40), (50, -40)]
    tapa = [a for a in ag["tapa_frente"] if a.origen == "cierre"]
    assert tapa and all(a.y == pytest.approx(30 - res.valores["geo"]["cierre_h_sup"]) for a in tapa)


def test_base_suelta_lleva_tornillos():
    ag = PF.calcular(calcular({"base_suelta": True, "ruedas": 4}))
    t = [a for a in ag["base_ruedas"] if a.capa == PF.CAPA_TORNILLOS]
    assert len(t) >= 8 and all(a.d == PF.TORNILLO_D for a in t)


def test_dxf_por_pieza_y_por_placa(tmp_path):
    paq = exportar(calcular(), str(tmp_path), pdf=False, step=False)
    piezas = [a for a in paq.archivos if a.endswith(".dxf") and os.sep + "dxf" + os.sep in a
              and "placas" not in a and "espuma" not in a]
    total = 0
    for pz in paq.piezas:
        ruta = next(a for a in piezas if os.path.basename(a) == pz["dxf"])
        texto = open(ruta, encoding="utf-8").read()
        circ = _circulos(texto)
        assert len(circ) == len(pz.get("agujeros", []))
        if circ:
            assert "\nPERFORACIONES\n" in texto.split("ENTITIES")[0]   # en la tabla de capas
        total += len(circ) * pz["cant"]
    assert total > 150
    # en las placas: los mismos agujeros, cada pieza en su lugar (girada o no)
    en_placas = 0
    for pl in paq.placas:
        texto = open(os.path.join(tmp_path, "dxf", "placas", pl["dxf"]), encoding="utf-8").read()
        circ = _circulos(texto)
        en_placas += len(circ)
        for _, x, y, _ in circ:
            assert any(p["x"] <= x <= p["x"] + p["dw"] and p["y"] <= y <= p["y"] + p["dh"] for p in pl["piezas"])
    assert en_placas == total


def test_placa_girada_mueve_los_agujeros():
    pieza = dict(num=1, w=600, h=300, calados=[])
    pl = dict(L=2440, A=1220, material="Fenólico", piezas=[dict(num=1, w=600, h=300, x=10, y=10, rot=True, dw=300, dh=600)])
    circ = _circulos(P.placa_dxf(pl, {1: pieza}, agujeros_por_num={1: [("PERFORACIONES", 100, 50, 4.1)]}))
    assert circ == [("PERFORACIONES", pytest.approx(10 + 300 - 50), pytest.approx(10 + 100), pytest.approx(4.1))]


def test_panel_dxf_sin_agujeros_no_cambia():
    assert "CIRCLE" not in panel_dxf(600, 400)
    assert "PERFORACIONES" not in panel_dxf(600, 400)
