"""«Mis cases»: lista de proyectos guardados, miniaturas, duplicar, renombrar y borrar."""

import os
import time

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from flightcase.taller import proyectos as P


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def limpio():
    s = QSettings("FlightcaseCalculator", "FlightcaseCalculator")
    s.clear()
    yield
    s.clear()


def _guardar(carpeta, nombre, ancho, titulo=True):
    from flightcase.taller.scad import escribir_proyecto
    ruta = os.path.join(carpeta, f"{nombre}.scad")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(escribir_proyecto({"int_ancho": ancho}, None, nombre if titulo else ""))
    return ruta


def test_listar_con_medidas_fecha_y_sin_repetir(tmp_path):
    a = _guardar(tmp_path, "Rack audio", 482)
    sub = tmp_path / "clientes"
    sub.mkdir()
    _guardar(sub, "Case luces", 700)
    (tmp_path / "salida_rack").mkdir()                     # paquetes exportados: no se miran
    _guardar(tmp_path / "salida_rack", "copia", 300)
    (tmp_path / "libreria.scad").write_text("module flightcase() {}\n", encoding="utf-8")
    t = time.time()
    os.utime(a, (t - 100, t - 100))
    infos = P.listar([str(tmp_path)], recientes=[a])
    assert [i.nombre for i in infos] == ["Case luces", "Rack audio"]     # el más nuevo primero
    assert infos[1].ancho == pytest.approx(P.listar([], [a])[0].ancho)
    ancho_ext = infos[1].ancho
    assert ancho_ext > 482 and "×" in infos[1].medidas() and infos[1].material
    assert infos[0].coincide("LUCES") and infos[0].coincide("clientes") and not infos[0].coincide("rack")
    assert infos[1].coincide("rack audio")


def test_indice_no_recalcula_si_no_cambio(tmp_path, monkeypatch):
    a = _guardar(tmp_path, "uno", 500)
    P.listar([str(tmp_path)])
    llamadas = []
    original = P._calcular_info
    monkeypatch.setattr(P, "_calcular_info", lambda r, f: llamadas.append(r) or original(r, f))
    P.listar([str(tmp_path)])
    assert llamadas == []
    _guardar(tmp_path, "uno", 600)
    os.utime(a, (time.time() + 5, time.time() + 5))
    assert P.listar([str(tmp_path)])[0].ancho > 600 and llamadas == [a]


def test_scad_con_una_linea_rota_se_lista_igual(tmp_path):
    (tmp_path / "raro.scad").write_text("int_ancho = [1, 2;\nflightcase();\n", encoding="utf-8")
    info = P.listar([str(tmp_path)])[0]
    assert info.nombre == "raro"          # la línea rota se ignora y se lista igual


def test_duplicar_y_renombrar(tmp_path):
    a = _guardar(tmp_path, "Rack", 482)
    c1 = P.duplicar(a)
    c2 = P.duplicar(a)
    assert os.path.basename(c1) == "Rack (copia).scad" and os.path.basename(c2) == "Rack (copia) 2.scad"
    assert open(c1, encoding="utf-8").readline().strip() == "// Rack (copia)"
    assert "int_ancho = 482;" in open(c1, encoding="utf-8").read()
    n = P.renombrar(c1, "Rack 4U: escenario")
    assert os.path.basename(n) == "Rack 4U- escenario.scad" and not os.path.exists(c1)
    assert open(n, encoding="utf-8").readline().strip() == "// Rack 4U- escenario"
    with pytest.raises(FileExistsError):
        P.renombrar(n, "Rack")
    with pytest.raises(ValueError):
        P.renombrar(n, "  .scad")


def test_miniatura(qapp, tmp_path):
    a = _guardar(tmp_path, "mini", 400)
    assert P.miniatura_al_dia(a) is None
    png = P.generar_miniatura(a)
    assert png and os.path.getsize(png) > 1000 and P.miniatura_al_dia(a) == png
    os.utime(a, (time.time() + 10, time.time() + 10))      # el case cambió: hay que dibujarla de nuevo
    assert P.miniatura_al_dia(a) is None
    P.olvidar(a)
    assert not os.path.exists(png)


def test_dialogo_mis_cases(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from flightcase.ui import FlightCaseMainWindow
    from flightcase.ui.widgets.proyectos_widget import poner_carpeta_proyectos
    poner_carpeta_proyectos(str(tmp_path))
    a = _guardar(tmp_path, "Anvil Absen", 520)
    b = _guardar(tmp_path, "Rack audio", 482)
    os.utime(a, (time.time() - 50, time.time() - 50))
    w = FlightCaseMainWindow(restore_settings=False)
    dlg = w.dialogo_proyectos()
    dlg.esperar_miniaturas()
    assert dlg.lista.count() == 2 and dlg.lista.item(0).text().startswith("Rack audio")
    assert not dlg.lista.item(0).icon().isNull()

    dlg.buscar.setText("absen")
    assert dlg.ruta_elegida() == a and dlg.lbl_total.text() == "1 de 2"
    dlg.buscar.setText("")

    dlg.lista.setCurrentRow(0)
    dlg.abrir_elegido()                                     # abre en el Taller y queda entre los recientes
    assert w.taller_widget.ruta == b and w.taller_widget.params["int_ancho"] == 482
    assert w._get_recent_files() == [b]

    dlg = w.dialogo_proyectos()
    dlg.lista.setCurrentRow(0)
    assert "(abierto)" in dlg.lista.currentItem().text()
    nueva = dlg.renombrar("Rack sonido")                    # el case abierto sigue al archivo
    assert w.taller_widget.ruta == nueva and "Rack sonido" in w.windowTitle()
    assert w._get_recent_files() == [nueva]

    copia = dlg.duplicar()
    assert os.path.basename(copia) == "Rack sonido (copia).scad" and dlg.ruta_elegida() == copia
    assert dlg.lista.count() == 3

    dlg.lista.setCurrentItem(dlg._items[nueva])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    assert dlg.borrar()
    assert not os.path.exists(nueva) and dlg.lista.count() == 2
    assert w.taller_widget.ruta is None and w.taller_widget.params["int_ancho"] == 482
    dlg.reject()
    w.close()


def test_guardar_case_nuevo_sugiere_la_carpeta_de_cases(qapp, tmp_path):
    from flightcase.ui.widgets import TallerWidget
    from flightcase.ui.widgets.proyectos_widget import poner_carpeta_proyectos
    carpeta = tmp_path / "Mis cases"
    poner_carpeta_proyectos(str(carpeta))
    t = TallerWidget()
    assert t._ruta_sugerida() == str(carpeta / "mi_case.scad") and carpeta.is_dir()
    (carpeta / "mi_case.scad").write_text("", encoding="utf-8")
    assert t._ruta_sugerida() == str(carpeta / "mi_case 2.scad")
    t.close()


def test_botones_del_taller_tambien_anotan_recientes(qapp, tmp_path):
    from flightcase.ui import FlightCaseMainWindow
    w = FlightCaseMainWindow(restore_settings=False)
    ruta = str(tmp_path / "desde_boton.scad")
    w.taller_widget.guardar(ruta)                          # el botón «Guardar .scad…» del Taller
    assert w._get_recent_files() == [ruta] and "desde_boton" in w.windowTitle()
    w.close()
