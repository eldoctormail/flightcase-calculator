"""Catálogo editable de herrajes y placas, con planilla CSV."""

import copy

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from flightcase.taller import catalogo as C
from flightcase.taller.modelo import CatalogoTaller, calcular, catalogo_actual


@pytest.fixture(autouse=True)
def datos(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(tmp_path))
    QApplication.instance() or QApplication([])


def _fila(ref, categoria, nombre, **datos):
    return {"ref": ref, "categoria": categoria, "nombre": nombre, "datos": datos, "verificado": True}


def test_sin_cambios_es_el_de_la_app():
    filas = C.filas_actuales()
    assert [f["ref"] for f in filas] == list(dict.fromkeys(f["ref"] for f in C.incluido()))
    assert {f["origen"] for f in filas} == {"incluido"}
    assert C.diferencias(filas) == ([], [])
    # todas las categorías del catálogo de la app tienen nombre en la ventana
    assert {f["categoria"] for f in filas} <= set(C.NOMBRES)
    assert len([f for f in filas if f["categoria"] == "placa"]) >= 5


def test_guardar_cambios_propios_y_ocultos():
    filas = copy.deepcopy(C.filas_actuales())
    filas = [f for f in filas if f["ref"] != "08-4018"]                         # quitado
    rueda = next(f for f in filas if f["ref"] == "LBD-R100F")
    rueda["datos"]["alto"] = 131                                                 # cambiado
    filas.append(_fila("PROV-FEN9", "placa", "Fenólico 9,2 mm Maderera X", esp=9.2, largo=2500, ancho=1250))
    C.guardar(filas)
    propios, ocultos = C.cargar_propio()
    assert [f["ref"] for f in propios] == ["LBD-R100F", "PROV-FEN9"] and ocultos == ["08-4018"]

    cat = catalogo_actual()
    assert not cat.existe("08-4018")
    assert cat.dato("LBD-R100F", "alto", 0) == 131 and cat.propio("LBD-R100F")
    assert cat.fila("PROV-FEN9")["origen"] == "propio"
    assert not cat.propio("08-4112")
    assert catalogo_actual() is cat                       # no se vuelve a leer si no cambió
    assert CatalogoTaller().dato("PROV-FEN9", "esp", 0) == 9.2

    # el taller usa la placa propia: espesor, material y medida de la hoja
    r = calcular({"ref_placa": "PROV-FEN9"})
    v = r.valores
    assert (v["placa_esp"], v["placa_largo"], v["placa_ancho"]) == (9.2, 2500, 1250)
    assert r.info["material"] == ["Fenólico 9,2 mm Maderera X"]

    # restaurar todo: vuelve a ser el de la app
    C.guardar(C.incluido())
    assert C.cargar_propio() == ([], [])
    assert catalogo_actual().dato("LBD-R100F", "alto", 0) == 125


def test_rueda_propia_sin_confirmar_avisa():
    filas = copy.deepcopy(C.filas_actuales())
    filas.append({**_fila("MIA-100", "rueda", "Rueda de mi proveedor", diametro=110, alto=140,
                          placa=[110, 90], agujeros=[85, 65], agujero_d=9), "verificado": False})
    C.guardar(filas)
    r = calcular({"ruedas": 4, "rueda_frenos": 0, "ref_rueda": "MIA-100"})
    assert r.valores["geo"]["rueda_diametro"] == 110
    assert any("sin confirmar" in a and "MIA-100" in a for a in r.avisos)
    assert not any("adamhall" in a and "MIA-100" in a for a in r.avisos)


def test_valores_de_las_medidas():
    assert C.valor_texto("9,6", "num") == 9.6
    assert C.valor_texto("100 x 85", "par") == [100, 85]
    assert C.valor_texto("100x85") == [100, 85]
    assert C.valor_texto("[100, 85]") == [100, 85]
    assert C.valor_texto("100,85", "par") == [100, 85]
    assert C.valor_texto("Embutido", ("superficie", "embutido")) == "embutido"
    assert C.valor_texto("", "num") is None
    assert C.valor_texto("giratoria") == "giratoria"
    for malo, tipo in (("nueve", "num"), ("100", "par"), ("rara", ("superficie", "embutido"))):
        with pytest.raises(ValueError):
            C.valor_texto(malo, tipo)
    assert C.texto_valor(9.6) == "9,6" and C.texto_valor([100, 85]) == "100 x 85"


def test_planilla_ida_y_vuelta():
    filas = [f for f in copy.deepcopy(C.filas_actuales()) if f["categoria"] in ("placa", "rueda", "cierre")]
    texto = C.a_csv(filas)
    encabezado = texto.splitlines()[0].split(";")
    assert encabezado[:6] == ["Ref", "Categoría", "Nombre", "Proveedor", "Verificado", "Nota"]
    assert {"esp", "largo", "ancho", "diametro", "placa", "corte"} <= set(encabezado)
    leidas, avisos = C.desde_csv(texto)
    assert avisos == []
    sin_origen = [{k: v for k, v in f.items() if k != "origen"} for f in filas]
    assert leidas == sin_origen


def test_planilla_de_un_proveedor():
    actuales = copy.deepcopy(C.filas_actuales())
    texto = ("Código;Categoría;Descripción;esp;largo;ancho;Proveedor\n"
             "MX-18;Placas;Fenólico 18 mm;18,3;2440;1220;Maderera X\n"
             "LBD-FEN9;;;9,2;;;Maderera X\n"                 # sólo corrige el espesor de uno que ya está
             "MX-?;Tornillos;Algo;1;;;\n"                    # categoría que no existe
             "MX-12;placa;Fenólico 12;doce;;;\n"            # medida que no se entiende
             ";;;;;;\n")
    nuevas, avisos = C.desde_csv(texto, actuales)
    por_ref = {f["ref"]: f for f in nuevas}
    assert set(por_ref) == {"MX-18", "LBD-FEN9", "MX-12"}
    assert por_ref["MX-18"]["categoria"] == "placa" and por_ref["MX-18"]["datos"] == {"esp": 18.3, "largo": 2440,
                                                                                       "ancho": 1220}
    assert por_ref["MX-18"]["proveedor"] == "Maderera X" and por_ref["MX-18"]["verificado"]
    fen9 = por_ref["LBD-FEN9"]
    assert fen9["datos"]["esp"] == 9.2 and fen9["datos"]["largo"] == 2440 and fen9["nombre"].startswith("Fenólico 9")
    assert "esp" not in por_ref["MX-12"]["datos"]
    assert len(avisos) == 2 and "Tornillos" in avisos[0] and "doce" in avisos[1]
    agregadas, actualizadas = C.sumar(actuales, nuevas)
    assert (agregadas, actualizadas) == (2, 1)
    with pytest.raises(ValueError):
        C.desde_csv("Nombre;esp\nAlgo;3\n")


def test_ventana_del_catalogo(tmp_path, monkeypatch):
    from flightcase.ui.widgets.catalogo_widget import CatalogoDialog
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg = CatalogoDialog(categoria="placa")
    titulos = [dlg.tabla.horizontalHeaderItem(c).text() for c in range(dlg.tabla.columnCount())]
    assert titulos[:6] == ["Ref", "Nombre", "Tipo", "Espesor", "Largo hoja", "Ancho hoja"]
    n = dlg.tabla.rowCount()
    f = dlg.nuevo()
    assert dlg.tabla.rowCount() == n + 1 and f["categoria"] == "placa"
    r = n
    col = {t: c for c, t in enumerate(titulos)}
    dlg.tabla.item(r, col["Ref"]).setText("MIA-9")
    dlg.tabla.item(r, col["Espesor"]).setText("9,4")
    dlg.tabla.item(r, col["Largo hoja"]).setText("nueve")             # no es un número: queda como estaba
    assert catalogo_actual().dato("MIA-9", "esp", 0) == 9.4
    assert catalogo_actual().dato("MIA-9", "largo", 0) == 2440
    dlg.tabla.item(r, col["Ref"]).setText("LBD-FEN9")                 # repetida: no se acepta
    assert catalogo_actual().existe("MIA-9")

    # cambiar uno de la app y restaurarlo
    r0 = next(i for i in range(dlg.tabla.rowCount()) if dlg.tabla.item(i, 0).text() == "LBD-FEN12")
    dlg.tabla.item(r0, col["Espesor"]).setText("12,2")
    assert catalogo_actual().propio("LBD-FEN12")
    assert dlg.tabla.item(r0, col["Origen"]).text() == "cambiado"
    dlg.tabla.selectRow(r0)
    dlg.restaurar()
    assert not catalogo_actual().propio("LBD-FEN12")

    # quitar uno de la app y recuperarlo
    r0 = next(i for i in range(dlg.tabla.rowCount()) if dlg.tabla.item(i, 0).text() == "LBD-MDF9")
    dlg.tabla.selectRow(r0)
    dlg.quitar()
    assert not catalogo_actual().existe("LBD-MDF9")
    dlg.recuperar_quitados()
    assert catalogo_actual().existe("LBD-MDF9")

    # sin confirmar
    r = next(i for i in range(dlg.tabla.rowCount()) if dlg.tabla.item(i, 0).text() == "MIA-9")
    dlg.tabla.item(r, col["Verif."]).setCheckState(Qt.Unchecked)
    assert not catalogo_actual().verificado("MIA-9")

    # exportar lo que se ve e importarlo en otro catálogo
    dlg.buscar.setText("MIA")
    dlg.exportar(str(tmp_path / "mias.csv"))
    texto = (tmp_path / "mias.csv").read_text(encoding="utf-8-sig")
    assert len(texto.splitlines()) == 2 and texto.splitlines()[1].startswith("MIA-9;placa;")
    C.guardar(C.incluido())
    dlg2 = CatalogoDialog()
    assert dlg2.categoria == "" and dlg2.tabla.horizontalHeaderItem(1).text() == "Categoría"
    dlg2.importar(str(tmp_path / "mias.csv"))
    assert catalogo_actual().dato("MIA-9", "esp", 0) == 9.4 and dlg2.cambiado


def test_el_taller_se_entera_de_los_cambios():
    from flightcase.ui.widgets.taller_widget import TallerWidget
    t = TallerWidget()
    combo = t.editores["ref_placa"].widget
    assert combo.findData("MIA-15") < 0
    filas = copy.deepcopy(C.filas_actuales()) + [_fila("MIA-15", "placa", "Fenólico 15 de mi proveedor", esp=15.2,
                                        largo=2440, ancho=1220)]
    C.guardar(filas)
    t.catalogo_cambiado()
    assert combo.findData("MIA-15") >= 0
    t.editores["ref_placa"].poner("MIA-15")
    t.recalcular()
    assert t.resultado.valores["placa_esp"] == 15.2
    assert t.herrajes.cat.existe("MIA-15")
