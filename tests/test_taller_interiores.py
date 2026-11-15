"""Interiores del taller: equipos, espuma con calados, cajones, rack de 19" y chequeos."""

import csv
import json
import os
from pathlib import Path

import pytest

from flightcase.taller import interiores as itr
from flightcase.taller.modelo import calcular
from flightcase.taller.produccion import exportar, largo_contornos
from flightcase.taller.scad import escribir_proyecto, leer_asignaciones

GOLDEN = sorted((Path(__file__).parent / "golden" / "taller").glob("*.json"))

# Rack de audio del taller (rack_audio.scad): frontal, dos tapas, 515 de ancho útil
RACK = dict(orientacion="frontal", tapas=2, int_ancho=515, int_prof=1100, int_alto_cuerpo=720,
            int_alto_tapa=105, placa_esp=10)
# Case vertical chico con espuma
VALIJA = dict(int_ancho=600, int_prof=400, int_alto_cuerpo=250, int_alto_tapa=80)


def _interior(params):
    res = calcular(params)
    return res, res.valores["interiores"]


def _avisos(I, texto):
    return [a for a in I.avisos if texto in a]


@pytest.mark.parametrize("caso", GOLDEN, ids=[g.stem for g in GOLDEN])
def test_sin_interiores_no_cambia_nada(caso):
    """Los proyectos de OpenSCAD no tienen interiores: el resultado sigue igual (los goldens
    se comparan en test_taller_golden) y no aparece nada nuevo."""
    res = calcular(json.loads(caso.read_text(encoding="utf-8"))["params"])
    assert res.valores["interiores"] is None
    assert res.valores["geo"]["interior"] is None


def test_espacio_util_por_orientacion():
    _, I = _interior(dict(VALIJA, equipos=[["Caja", 10, 10, 10]]))
    assert (I.cuerpo.med(0), I.cuerpo.med(1), I.cuerpo.med(2)) == pytest.approx((600, 400, 250))
    assert I.util.med(2) == pytest.approx(330)            # cuerpo + tapa
    _, I = _interior(dict(RACK, equipos=[["Caja", 10, 10, 10]]))
    assert (I.cuerpo.med(0), I.cuerpo.med(1), I.cuerpo.med(2)) == pytest.approx((515, 720, 1100))
    assert I.util.med(1) == pytest.approx(720 + 2 * 105)  # las dos tapas en profundidad
    _, I = _interior(dict(VALIJA, espuma_esp=10, equipos=[["Caja", 10, 10, 10]]))
    assert I.cuerpo.med(0) == pytest.approx(600)          # con forro, sigue siendo el espacio útil


def test_rack_19_en_el_rack_de_audio():
    _, I = _interior(dict(RACK, rack_u=12, rack_equipos=[["Consola", 3, 400, 8, 0, 30], ["Potencia", 2, 480, 15]]))
    r = I.rack
    assert r["largo"] == pytest.approx(12 * 44.45)
    # 515 de ancho: el ala de 15 no llega a los agujeros (465,1): suplemento por lado
    assert r["suplemento"] == pytest.approx((515 - 465.1) / 2 + 6 - 15)
    assert r["libres"] == 7
    nombres = {h[0]: h for h in I.herrajes}
    assert nombres["Perfil de rack negro 45U"][1] == 1          # 2 tramos de 12 U salen de una barra
    assert nombres['Carátula ciega 4 U 19"'][1] == 1 and nombres['Carátula ciega 3 U 19"'][1] == 1
    assert nombres["Tuerca enjaulada M6 para 2 mm"][1] == 8 + 4 + 4 + 4   # 3U, 2U, carátulas 4U y 3U
    assert any(e[0] == "Suplemento de riel de rack" and e[4] == 2 for e in I.extras)
    assert _avisos(I, "conviene sostenerlo atrás")             # la potencia pesa 15 kg
    _, I2 = _interior(dict(RACK, rack_u=12, rack_traseros=True, rack_equipos=[["Potencia", 2, 480, 15]]))
    assert not _avisos(I2, "conviene sostenerlo atrás")
    assert sum(1 for so in I2.solidos if so.tipo == "riel") == 4


def test_rack_que_no_entra():
    _, I = _interior(dict(RACK, int_ancho=480, rack_u=30, rack_equipos=[["Largo", 2, 900], ["Perillas", 1, 200, 2, 0, 200]]))
    assert _avisos(I, "un equipo de 19\" necesita")
    assert _avisos(I, "El rack de 30 U no entra")            # 1100 / 44,45 = 24 U
    assert _avisos(I, "Largo no entra de fondo")              # 900 > 20 + 825
    assert _avisos(I, "Lo que sobresale del frente de Perillas")
    _, I = _interior(dict(RACK, rack_u=4, rack_equipos=[["A", 2, 300, 1, 1], ["B", 2, 300, 1, 2]]))
    assert _avisos(I, "ocupan las mismas unidades")


def test_rack_en_case_vertical_y_acostado():
    _, I = _interior(dict(VALIJA, int_ancho=490, int_prof=500, rack_u=6, rack_retiro=10))
    assert I.rack["fondo_cuerpo"] == pytest.approx(250)
    rieles = [so.caja for so in I.solidos if so.tipo == "riel"]
    assert all(c.med(1) == pytest.approx(6 * 44.45) for c in rieles)          # a lo largo de Y
    assert all(c.z1 == pytest.approx(I.cuerpo.z1 - 10) for c in rieles)      # bajo el plano de cierre
    _, I = _interior(dict(VALIJA, orientacion="horizontal", rack_u=4))
    assert _avisos(I, "En un case acostado no se ubica")


def test_espuma_con_calados_por_capa():
    _, I = _interior(dict(VALIJA, equipos=[["Mixer", 300, 250, 90, 4.5, 30, 30, 30],
                                           ["Micro", 200, 60, 60, 0.4, 380, 30, 40]],
                          espumas=[[0, 0, 120]]))
    bl = I.espumas[0]
    assert (bl.caja.med(0), bl.caja.med(1), bl.caja.med(2)) == pytest.approx((600, 400, 120))
    assert bl.abre_arriba and len(bl.capas) == 4
    mixer = [c for c in bl.capas[1].calados if c["equipo"] == "Mixer"][0]
    assert (mixer["w"], mixer["h"]) == pytest.approx((306, 256))               # + holgura 3 por lado
    assert mixer["cx"] == pytest.approx(30 - 3 + 153)
    assert not [c for c in bl.capas[0].calados]                                 # 30 mm de fondo bajo el mixer
    micro = {c.indice: c for c in bl.capas}
    assert [c["tipo"] for c in micro[2].calados if c["equipo"] == "Micro"] == ["rebaje"]
    assert [c["prof"] for c in micro[2].calados if c["equipo"] == "Micro"] == [pytest.approx(20)]
    assert _avisos(I, "lleva un rebaje de 20 mm")
    assert any(h[0] == "Espuma de polietileno 30 mm" for h in I.herrajes)
    assert I.peso["espuma"] > 0 and I.peso["equipos"] == pytest.approx(4.9)


def test_espuma_avisos_de_paredes_y_fondo():
    _, I = _interior(dict(VALIJA, equipos=[["A", 100, 100, 50, 0, 5, 50, 5], ["B", 100, 100, 50, 0, 114, 50, 5]],
                          espumas=[[0, 0, 60]]))
    assert _avisos(I, "del borde de la espuma 1")       # A queda a 2 mm del borde
    assert _avisos(I, "Entre los calados de A y B quedan 3 mm")   # 9 - 2 x 3 de holgura
    assert _avisos(I, "Bajo el equipo A quedan 5 mm")
    _, I = _interior(dict(VALIJA, equipos=[["A", 100, 100, 50]], espumas=[[0, 0, 60, None, None, 10]]))
    assert _avisos(I, "atraviesa la espuma 1")


def test_espuma_de_la_tapa_abre_hacia_el_cuerpo():
    _, I = _interior(dict(VALIJA, espumas=[[0, 0, 60, None, None, 260]], equipos=[["Alto", 100, 100, 280, 0, None, None, 0]]))
    bl = I.espumas[0]
    assert not bl.abre_arriba
    assert bl.bolsillos[0]["fondo"] == pytest.approx(bl.caja.z1 - (I.util.z0 + 280))


def test_cajones_con_correderas():
    _, I = _interior(dict(RACK, cajones=[[150, 0], [150, 150, 400, 350]]))
    piezas = {e[0]: e for e in I.extras}
    # cajón 1: todo el ancho (515), corredera más larga que entra en 720 - 5 - 9 - 10
    assert piezas["Cajón 1 frente"][1:3] == [515 - 6, 147]
    assert piezas["Cajón 1 lateral"][1:5] == [600, 121, 9, 2]
    assert piezas["Cajón 1 trasera"][1] == pytest.approx(515 - 2 * 12.7 - 18)
    assert piezas["Cajón 1 piso"][1:3] == [pytest.approx(515 - 25.4), 600]
    assert piezas["Cajón 2 lateral"][1] == 350
    assert _avisos(I, "cajón 2 no ocupa todo el ancho")
    corr = [h for h in I.herrajes if h[0].startswith("Corredera")]
    assert sorted((h[0], h[1]) for h in corr) == [("Corredera telescópica 350 mm (par)", 1),
                                                   ("Corredera telescópica 600 mm (par)", 1)]
    _, I = _interior(dict(RACK, cajones=[[150, 0], [150, 100]]))
    assert _avisos(I, "se pisan en altura")
    _, I = _interior(dict(VALIJA, cajones=[[100, 0]]))
    assert _avisos(I, "necesitan que el frente se abra")


def test_choques_y_piezas_fuera_del_interior():
    _, I = _interior(dict(VALIJA, bandejas=[[600, 400, 120, 9]], equipos=[["Caja", 200, 200, 150]]))
    assert _avisos(I, "Bandeja choca con Caja")
    _, I = _interior(dict(VALIJA, equipos=[["Grande", 700, 100, 50]]))
    assert _avisos(I, "Grande se sale del interior")
    _, I = _interior(dict(VALIJA, equipos=[["Alto", 100, 100, 320]]))
    assert not _avisos(I, "se sale")                      # entra en la tapa (250 + 80)
    _, I = _interior(dict(RACK, rack_u=6, rack_desde=0, cajones=[[150, 0]]))
    assert _avisos(I, "Cajón 1 choca con")


def test_interiores_entran_en_la_lista_y_el_resultado():
    res, I = _interior(dict(RACK, rack_u=12, rack_equipos=[["Consola", 3, 400]], cajones=[[150, 0]]))
    assert I.extras and all(e in res.extras for e in I.extras)
    assert any(h.nombre.startswith("Corredera telescópica") for h in res.herrajes)
    assert all(a in res.avisos for a in I.avisos)


def test_bandeja_de_un_case_frontal_de_una_tapa_queda_en_el_cuerpo():
    res = calcular(dict(RACK, tapas=1, bandejas=[[515, 600, 500, 15]]))
    b = res.valores["geo"]["bandejas"][0]
    v = res.valores
    # el cuerpo de un case frontal de una tapa va de la tapa (adelante) al piso (atrás)
    assert v["ext_alto"] - v["geo"]["ext_alto_cuerpo"] < b["cy"] < v["ext_alto"]


def test_vista_3d_del_interior():
    from flightcase.taller.geometria import Opciones3D, malla_3d
    res = calcular(dict(VALIJA, equipos=[["Mixer", 300, 250, 90, 4.5, 30, 30, 30]],
                        espumas=[[0, 0, 120], [0, 0, 60, None, None, 250]]))
    m = malla_3d(res)
    grupos = {f.color_group for f in m.faces}
    assert {"equipo", "espuma"} <= grupos
    tapa = [f for f in m.faces if f.label == "Espuma 2"]
    z_cerrado = max(p.z for f in tapa for p in f.vertices)
    m2 = malla_3d(res, Opciones3D(abrir_tapa=400))
    z_abierto = max(p.z for f in m2.faces if f.label == "Espuma 2" for p in f.vertices)
    assert z_abierto == pytest.approx(z_cerrado + 400)       # la espuma de la tapa sube con la tapa
    cuerpo = max(p.z for f in m2.faces if f.label == "Espuma 1" for p in f.vertices)
    assert cuerpo == pytest.approx(max(p.z for f in m.faces if f.label == "Espuma 1" for p in f.vertices))
    # en las láminas del instructivo (paso < 99) no se dibuja el interior
    assert not {f for f in malla_3d(res, Opciones3D(paso=4)).faces if f.color_group == "espuma"}


def test_paquete_con_espuma_y_cajones(tmp_path):
    # case frontal: la espuma abre hacia la tapa delantera y las capas se apilan en profundidad
    # (sin posición, el bloque va contra el fondo del cuerpo)
    res = calcular(dict(RACK, equipos=[["Micro", 200, 60, 60, 0.4, "c", 640, 500]], espumas=[[0, 120, 0]],
                        cajones=[[150, 0]]))
    paq = exportar(res, str(tmp_path), pdf=False)
    dxfs = sorted(os.listdir(tmp_path / "dxf" / "espuma"))
    I = res.valores["interiores"]
    assert len(dxfs) == len(I.espumas[0].capas) == 4
    capa = I.espumas[0].capas[-1]
    texto = (tmp_path / "dxf" / "espuma" / dxfs[-1]).read_text(encoding="utf-8")
    c = capa.calados[0]
    assert largo_contornos(texto) == pytest.approx(2 * (capa.ancho + capa.alto) + 2 * (c["w"] + c["h"]))
    with open(tmp_path / "espuma.csv", encoding="utf-8-sig") as f:
        filas = list(csv.reader(f, delimiter=";"))
    assert filas[0][0] == "Bloque" and len(filas) == 5
    assert "prof. 10" in filas[1][6]            # 20 mm de espuma detrás del micro: rebaje en la capa 1
    with open(tmp_path / "lista_cortes.csv", encoding="utf-8-sig") as f:
        cortes = f.read()
    assert "Cajón 1 lateral" in cortes and "Cajón 1 piso" in cortes
    assert str(tmp_path / "espuma.csv") in paq.archivos


def test_scad_de_ida_y_vuelta_con_interiores():
    P = dict(equipos=[["Mixer", 300, 250, 90, 4.5, "c", 30, 0]], espumas=[[0, 0, 120]], cajones=[[150, 0]],
             rack_u=8, rack_equipos=[["Consola", 3, 400]])
    leido = leer_asignaciones(escribir_proyecto(P))
    assert {k: leido[k] for k in P} == P
    assert itr.hay_interiores(leido)


def test_tablas_del_editor(qapp):
    from PySide6.QtWidgets import QTableWidgetItem
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    assert not w.chk_interior.isChecked()
    ed = w.editores["equipos"]
    ed._agregar()
    for c, v in enumerate(["Mixer", "300", "250", "90", "", "", "30,5"]):
        ed.tabla.setItem(0, c, QTableWidgetItem(v))
    w.recalcular()
    assert w.params["equipos"] == [["Mixer", 300, 250, 90, 0, "c", 30.5]]
    assert w.chk_interior.isChecked()            # al cargar el primer interior se abre la vista
    assert w.tabla_interior.rowCount() == 1
    ed.tabla.setItem(0, 2, QTableWidgetItem(""))  # fondo obligatorio
    w.recalcular()
    assert "mal cargado" in w.lbl_avisos.text()
    w.set_params(dict(bandejas=[[400, 300, 120, 15, "Fenólico 15 mm"]]))
    assert w.editores["bandejas"].tabla.rowCount() == 1
    assert w.editores["bandejas"].valor() == [[400, 300, 120, 15, "Fenólico 15 mm"]]


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_hojas_del_interior_para_planos(tmp_path, qapp):
    from flightcase.taller.planos import interior as pl
    res = calcular(dict(RACK, rack_u=12, rack_desde=420, rack_equipos=[["Consola", 3, 420, 8]],
                        cajones=[[200, 0], [200, 200]], equipos=[["Micro", 200, 60, 60, 0.4, "c", 640, 500]],
                        espumas=[[0, 120, 0]]))
    piezas = [dict(nombre="Cajón 1 frente", num=8, extra=True), dict(nombre="Cajón 1 lateral", num=9, extra=True)]
    vistas = pl.vistas_planos(res, str(tmp_path), piezas)
    titulos = [v[0] for v in vistas]
    assert titulos == ["Interior: espuma 1 por capas", "Interior: rack 19\"", "Interior: cajones"]
    assert all(os.path.getsize(v[1]) > 1000 for v in vistas)
    assert "Suplemento de 15,9 mm" in vistas[1][2] and "420 mm del piso interior" in vistas[1][2]
    assert "(P8, P9)" in vistas[2][2]
    assert "rebaje" in vistas[0][2]


def test_pasos_del_interior_en_el_instructivo():
    from flightcase.taller.planos import interior as pl
    res = calcular(dict(RACK, rack_u=12, rack_traseros=True, rack_equipos=[["Consola", 3, 420], ["Potencia", 2, 480]],
                        cajones=[[200, 0]], equipos=[["Micro", 200, 60, 60]], espumas=[[0, 120, 0]]))
    pasos = pl.pasos_instructivo(res, [dict(nombre="Cajón 1 frente", num=8, extra=True)])
    assert [p["titulo"] for p in pasos] == ["Interior: rack 19\"", "Interior: cajón 1", "Interior: espuma"]
    rack = " ".join(pasos[0]["texto"])
    assert "Consola en U1–3, Potencia en U4–5" in rack and "rieles traseros" in rack and "533,4" in rack
    assert "frente P8" in pasos[1]["texto"][0]
    assert all(p["defs"]["paso"] == 99 and p["defs"]["abrir_tapa"] > 0 for p in pasos)
    assert pl.pasos_instructivo(calcular(), []) == []


def test_lamina_resalta_el_interior():
    from flightcase.taller.geometria import Opciones3D, malla_3d
    res = calcular(dict(RACK, rack_u=6))
    m = malla_3d(res, Opciones3D.desde_defs({"paso": 99, "abrir_tapa": 800, "resaltar_interior": "riel"}))
    assert any(f.color_group == "resalte" and f.label.startswith("Riel") for f in m.faces)


def test_paquete_con_interior_suma_hojas(tmp_path):
    res = calcular(dict(RACK, rack_u=8, rack_equipos=[["Consola", 3, 420]]))
    paq = exportar(res, str(tmp_path), instructivo=False)
    assert str(tmp_path / "interior_rack.png") in paq.archivos
    assert str(tmp_path / "interior.png") in paq.archivos
