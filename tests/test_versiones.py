"""Autoguardado, recuperación tras un cierre inesperado y versiones fechadas de cada case."""

import os
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from flightcase.taller import recuperacion
from flightcase.taller import versiones as V


@pytest.fixture(autouse=True)
def clean_settings():
    s = QSettings("FlightcaseCalculator", "FlightcaseCalculator")
    s.clear()
    yield
    s.clear()


@pytest.fixture
def datos(tmp_path, monkeypatch):
    """Carpeta de datos propia (la de recuperación empieza vacía)."""
    d = tmp_path / "datos"
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(d))
    return d


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _scad(ruta, ancho):
    ruta.write_text(f"int_ancho = {ancho};\nflightcase();\n", encoding="utf-8")
    return str(ruta)


# ------------------------------------------------------------------ versiones
def test_respaldar_copia_lo_que_habia_como_mucho_cada_10_minutos(tmp_path):
    t0 = datetime(2026, 11, 16, 10, 0, 0)

    def guardado(ancho, minuto):          # el case como quedó guardado a esa hora
        ruta = _scad(tmp_path / "rack.scad", ancho)
        t = (t0 + timedelta(minutes=minuto)).timestamp()
        os.utime(ruta, (t, t))
        return ruta

    case = guardado(500, 0)
    primera = V.respaldar(case, ahora=t0 + timedelta(minutes=1))
    assert primera and os.path.basename(primera) == "2026-11-16 10.00.00.scad"
    assert os.path.dirname(primera) == os.path.join(str(tmp_path), ".versiones", "rack")
    assert V.respaldar(case, ahora=t0 + timedelta(minutes=30)) is None        # igual a la última
    guardado(510, 5)
    assert V.respaldar(case, ahora=t0 + timedelta(minutes=6)) is None         # muy seguido
    assert V.respaldar(case, ahora=t0 + timedelta(minutes=6), forzar=True)    # al abrirlo, siempre
    guardado(520, 16)
    assert V.respaldar(case, ahora=t0 + timedelta(minutes=17))
    vs = V.listar(case)
    assert [v.fecha.minute for v in vs] == [16, 5, 0]
    assert ["int_ancho = 520" in open(v.ruta, encoding="utf-8").read() for v in vs] == [True, False, False]
    assert V.respaldar(str(tmp_path / "no_existe.scad")) is None


def test_las_viejas_se_ralean():
    ahora = datetime(2026, 11, 16, 12, 0)
    vs = [V.Version(f"{i}.scad", ahora - timedelta(hours=i * 6)) for i in range(400)]   # 100 días, 4 por día
    quedan = V.a_conservar(vs, ahora)
    fechas = [v.fecha for v in quedan]
    recientes = [f for f in fechas if ahora - f < timedelta(days=2)]
    assert len(recientes) == 8                                       # todas las de dos días
    medio = [f for f in fechas if timedelta(days=2) <= ahora - f < timedelta(days=60)]
    assert len(medio) == len({f.date() for f in medio}) >= 57      # una por día
    viejas = [f for f in fechas if ahora - f >= timedelta(days=60)]
    assert len(viejas) == len({(f.year, f.month) for f in viejas})   # una por mes
    assert len(quedan) <= V.MAXIMO


def test_al_renombrar_y_borrar_las_versiones_siguen_al_case(tmp_path):
    from flightcase.taller import proyectos as P
    case = _scad(tmp_path / "viejo.scad", 500)
    V.respaldar(case)
    nueva = P.renombrar(case, "nuevo")
    assert not V.listar(case) and len(V.listar(nueva)) == 1
    mandadas = []
    V.a_la_papelera(nueva, lambda c: mandadas.append(c) or False)   # sin papelera: se borra
    assert mandadas and not V.listar(nueva) and not (tmp_path / ".versiones").exists()


def test_guardar_deja_version_de_lo_que_habia(qapp, tmp_path):
    from flightcase.ui.widgets import TallerWidget
    case = _scad(tmp_path / "rack.scad", 500)
    t = TallerWidget()
    t.abrir(case)
    t.editores["int_ancho"].poner(600)
    assert t.guardar(case)
    vs = V.listar(case)
    assert len(vs) == 1 and "int_ancho = 500" in open(vs[0].ruta, encoding="utf-8").read()
    t.editores["int_ancho"].poner(700)
    assert t.guardar(case) and len(V.listar(case)) == 1             # menos de 10 minutos después
    assert "int_ancho = 700" in open(case, encoding="utf-8").read()
    assert not os.path.exists(case + ".guardando")
    assert not t.guardar(None, automatico=True)                      # sin nombre no hay diálogo
    t.close()


# -------------------------------------------------------- ventana principal
def test_autoguardado_solo_con_cambios_y_con_nombre(qapp, tmp_path, datos):
    from flightcase.ui import FlightCaseMainWindow
    w = FlightCaseMainWindow(restore_settings=False)
    t = w.taller_widget
    assert w.minutos_autoguardado() == 3 and w._timer_autoguardado.interval() == 3 * 60_000
    assert "empieza cuando le pongas nombre" in w.lbl_autoguardado.text()
    t.editores["int_ancho"].poner(650)
    assert not w.autoguardar()                   # case nuevo: solo copia de recuperación
    assert w.copiar_para_recuperar() and w.sesion.scad.exists()
    assert not w.copiar_para_recuperar()         # sin cambios nuevos no reescribe

    case = _scad(tmp_path / "rack.scad", 500)
    t.guardar(case)
    assert not w.sesion.scad.exists()            # guardado: la copia de recuperación sobra
    assert not w.autoguardar()                   # sin cambios no toca el archivo
    t.editores["int_ancho"].poner(720)
    assert w.autoguardar()
    assert "int_ancho = 720" in open(case, encoding="utf-8").read()
    assert w.lbl_autoguardado.text().startswith("Guardado automáticamente a las")
    assert not t.hay_cambios()

    accion = w._acciones_autoguardado[0]
    accion.trigger()
    assert w.minutos_autoguardado() == 0 and not w._timer_autoguardado.isActive()
    assert w.lbl_autoguardado.text() == "Autoguardado desactivado"
    w._acciones_autoguardado[10].trigger()
    assert w._timer_autoguardado.interval() == 10 * 60_000
    w.close()


def test_cerrar_con_cambios_pregunta_y_al_cerrar_bien_no_queda_nada(qapp, tmp_path, datos, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from flightcase.ui import FlightCaseMainWindow
    w = FlightCaseMainWindow(restore_settings=False)
    w.show()
    w.taller_widget.editores["int_ancho"].poner(650)
    w.copiar_para_recuperar()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel)
    assert not w.close() and w.isVisible()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    assert w.close()
    assert list((datos / recuperacion.CARPETA).iterdir()) == []      # ni copia ni lock


CRASH = textwrap.dedent("""
    import os, sys
    from PySide6.QtWidgets import QApplication
    from flightcase.ui import FlightCaseMainWindow
    app = QApplication([])
    w = FlightCaseMainWindow(restore_settings=False)
    w.abrir(sys.argv[1])
    w.taller_widget.editores["int_ancho"].poner(777)
    assert w.copiar_para_recuperar()
    print(w.sesion.id, flush=True)
    os._exit(1)                                   # como si se cortara la luz
""")


def test_recupera_los_cambios_despues_de_un_cierre_de_golpe(qapp, tmp_path, datos, monkeypatch):
    from flightcase.ui import FlightCaseMainWindow
    case = _scad(tmp_path / "rack.scad", 500)
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=raiz)
    p = subprocess.run([sys.executable, "-c", CRASH, case], env=env, capture_output=True, text=True, timeout=120)
    assert p.returncode == 1, p.stderr
    id_muerta = p.stdout.strip().splitlines()[-1]
    assert (datos / recuperacion.CARPETA / f"{id_muerta}.lock").exists()   # el lock quedó huérfano

    otra = FlightCaseMainWindow(restore_settings=False)        # otra ventana abierta: la suya no se ofrece
    otra.taller_widget.editores["int_ancho"].poner(111)
    otra.copiar_para_recuperar()

    w = FlightCaseMainWindow(restore_settings=False)
    pendientes = w.pendientes_de_recuperar()
    assert [r.id for r in pendientes] == [id_muerta] and pendientes[0].ruta == case
    preguntas = []
    monkeypatch.setattr(w, "_preguntar_recuperar", lambda r, quedan: preguntas.append(r.nombre) or "recuperar")
    assert w.ofrecer_recuperacion()
    t = w.taller_widget
    assert preguntas == ["rack.scad"] and t.ruta == case and t.params["int_ancho"] == 777
    assert t.hay_cambios()                                      # el archivo sigue como estaba
    assert "int_ancho = 500" in open(case, encoding="utf-8").read()
    assert not (datos / recuperacion.CARPETA / f"{id_muerta}.scad").exists()
    assert w.sesion.scad.exists()                               # ahora es la copia de esta ventana
    assert not w.pendientes_de_recuperar()
    t.guardar(case)
    w.close()
    otra.taller_widget._foto_guardada = otra.taller_widget._foto()
    otra.close()


def test_descartar_la_recuperacion(qapp, tmp_path, datos, monkeypatch):
    from flightcase.ui import FlightCaseMainWindow
    s = recuperacion.Sesion("vieja")
    s.escribir("int_ancho = 333;\nflightcase();\n", None, str(tmp_path))
    w = FlightCaseMainWindow(restore_settings=False)
    monkeypatch.setattr(w, "_preguntar_recuperar", lambda r, quedan: "despues")
    assert not w.ofrecer_recuperacion() and s.scad.exists()          # «Después»: sigue ahí
    monkeypatch.setattr(w, "_preguntar_recuperar", lambda r, quedan: "descartar")
    assert not w.ofrecer_recuperacion() and not s.scad.exists()
    monkeypatch.setattr(w, "_preguntar_recuperar", lambda r, quedan: pytest.fail("no queda nada"))
    assert not w.ofrecer_recuperacion()
    w.close()


def test_recuperar_un_case_que_nunca_se_guardo(qapp, tmp_path, datos, monkeypatch):
    from flightcase.ui import FlightCaseMainWindow
    recuperacion.Sesion("vieja").escribir("int_ancho = 333;\nflightcase();\n", None, "")
    w = FlightCaseMainWindow(restore_settings=False)
    monkeypatch.setattr(w, "_preguntar_recuperar", lambda r, quedan: "recuperar")
    assert w.ofrecer_recuperacion()
    assert w.taller_widget.ruta is None and w.taller_widget.params["int_ancho"] == 333
    assert w.taller_widget.hay_cambios()
    w.taller_widget._foto_guardada = w.taller_widget._foto()
    w.close()


def test_restaurar_una_version_desde_el_menu_y_desde_mis_cases(qapp, tmp_path, datos, monkeypatch):
    from flightcase.ui import FlightCaseMainWindow
    from flightcase.ui.widgets import versiones_widget
    from flightcase.ui.widgets.proyectos_widget import poner_carpeta_proyectos
    poner_carpeta_proyectos(str(tmp_path))
    case = _scad(tmp_path / "rack.scad", 500)
    w = FlightCaseMainWindow(restore_settings=False)
    t = w.taller_widget
    assert not w.accion_versiones.isEnabled()
    w.abrir(case)
    assert w.accion_versiones.isEnabled()
    t.editores["int_ancho"].poner(640)
    t.guardar(case)                                           # queda la versión de 500

    vistos = []

    def exec_(dlg):
        vistos.append([dlg.lista.topLevelItem(i).text(2) for i in range(dlg.lista.topLevelItemCount())])
        dlg.restaurar_elegida()
        return 1
    monkeypatch.setattr(versiones_widget.VersionesDialog, "exec", exec_)
    assert w.versiones()
    assert vistos[0] and "500 → 640" in vistos[0][0]
    assert t.params["int_ancho"] == 500 and t.hay_cambios() and t.ruta == case
    assert "int_ancho = 640" in open(case, encoding="utf-8").read()     # el archivo no se tocó
    assert w.status_bar.currentMessage().startswith("Versión del")

    t.set_params({})                                           # otro case abierto: desde Mis cases
    dlg = w.dialogo_proyectos()
    assert dlg.btn_versiones.isVisible() or not dlg.isVisible()
    dlg.lista.setCurrentRow(0)
    dlg.ver_versiones()
    assert dlg.abierto == case and t.ruta == case and t.params["int_ancho"] == 500
    t._foto_guardada = t._foto()
    w.close()


def test_diferencias_en_castellano():
    from flightcase.ui.widgets.versiones_widget import diferencias
    et = {"int_ancho": "Ancho interior", "int_prof": "Profundidad interior", "a": "A", "b": "B"}
    assert diferencias({"int_ancho": 500}, {"int_ancho": 600.0}, et, {}) == ["Ancho interior: 500 → 600"]
    assert diferencias({}, {"int_prof": 300}, et, {"int_prof": 300}) == []
    largo = diferencias({"int_ancho": 1, "int_prof": 1, "a": 1, "b": 1, "c": [1]}, {"c": [2]}, et, {}, maximo=2)
    assert len(largo) == 3 and largo[-1] == "y 3 más"
