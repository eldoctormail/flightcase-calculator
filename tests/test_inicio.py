"""Pantalla de inicio: familias de estilos, elegir un estilo o una plantilla y crear el proyecto."""

import os

import pytest

from flightcase.taller import estilos, familias


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_familias_cubren_todos_los_estilos():
    incluidos = estilos.estilos_incluidos()
    grupos = familias.agrupar(incluidos)
    ids = [e.id for f in grupos for e in f.estilos]
    assert sorted(ids) == sorted(e.id for e in incluidos) and len(ids) == len(set(ids))
    assert all(f.clave != "otros" for f in grupos)            # ninguno quedó suelto
    for e in incluidos:                                        # cada uno con su miniatura hecha
        assert familias.miniatura(e), e.id
        assert familias.nombre_corto(e) != e.nombre
    propio = estilos.Estilo("mio", "Mi baúl", "", {"ruedas": 4}, propio=True)
    assert familias.agrupar(incluidos + [propio])[-1].nombre == "Mis estilos"
    assert familias.ruta_miniatura(propio).name.startswith("mio-")


def test_elegir_estilo_con_chips_y_plantilla(qapp, tmp_path):
    from flightcase.ui.widgets.inicio_widget import PantallaInicio
    case = tmp_path / "Bateria.scad"
    case.write_text("int_ancho = 900;\n", encoding="utf-8")
    d = PantallaInicio(recientes=[str(case), str(tmp_path / "no-existe.scad")])
    assert d.estilo.id == "baul_tapa_suelta"                   # primera familia, primer estilo
    racks = next(t for t in d.tarjetas["familias"] if t.valor.clave == "racks")
    racks.chips["rack_puertas"].click()
    assert d.estilo.id == "rack_puertas" and racks.property("elegida")
    assert racks.chips["rack_puertas"].isChecked() and not racks.chips["rack_una_tapa"].isChecked()
    assert d.lbl_familia.text() == 'RACKS 19"' and "puertas" in d.lbl_nombre.text()
    todos = {t.valor.id: t for t in d.tarjetas["todos"]}
    assert todos["rack_puertas"].property("elegida") and len(todos) == len(d.lista_estilos)
    assert [t.valor for t in d.tarjetas["plantillas"]] == [str(case)]    # sólo los que existen
    d.elegir(str(case))
    assert d.estilo is None and d.plantilla == str(case) and d.lbl_familia.text() == "PLANTILLA"
    d.txt_nombre.setText("  Nuevo rack ")
    d.crear()
    assert d.accion == "crear" and d.nombre == "Nuevo rack" and d.result()


def test_crear_proyecto_con_estilo_y_nombre(qapp, tmp_path):
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    assert w.crear("rack_dos_tapas")
    assert w.params["orientacion"] == "frontal" and w.ruta is None and not w.hay_cambios()
    assert w.crear("baul_bisagras", nombre="Luces: LED", carpeta=str(tmp_path))
    assert w.ruta == os.path.join(str(tmp_path), "Luces- LED.scad") and os.path.isfile(w.ruta)
    assert w.crear("baul_bisagras", nombre="Luces: LED", carpeta=str(tmp_path))
    assert w.ruta.endswith("Luces- LED 2.scad")                 # no pisa el que ya estaba
    w.editores["int_ancho"].poner(777)
    w.guardar(w.ruta)
    assert w.crear(plantilla=w.ruta)                            # copia sin ruta: el original no cambia
    assert w.params["int_ancho"] == 777 and w.ruta is None
