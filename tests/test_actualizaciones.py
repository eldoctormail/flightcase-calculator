"""Buscar, descargar e instalar versiones nuevas (sin red: GitHub se simula)."""

import io
import json
from pathlib import Path

import pytest

from flightcase import actualizaciones as act

RELEASE = {
    "tag_name": "v0.4.0", "body": "## Novedades\n* Actualización automática", "draft": False,
    "prerelease": False, "html_url": "https://github.com/eldoctormail/flightcase-calculator/releases/tag/v0.4.0",
    "assets": [
        {"name": "LBDFlightcaseMaker-0.4.0-macOS-AppleSilicon.dmg", "size": 72, "browser_download_url": "https://x/arm.dmg"},
        {"name": "LBDFlightcaseMaker-0.4.0-macOS-Intel.dmg", "size": 79, "browser_download_url": "https://x/intel.dmg"},
        {"name": "LBDFlightcaseMaker-0.4.0-Windows-Instalador.exe", "size": 58, "browser_download_url": "https://x/win.exe"},
    ],
}


class _Respuesta(io.BytesIO):
    def __init__(self, datos: bytes):
        super().__init__(datos)
        self.headers = {"Content-Length": str(len(datos))}


def test_comparar_versiones():
    assert act.numeros("v0.3.10") == (0, 3, 10) and act.numeros("V1.2") == (1, 2)
    assert act.es_mas_nueva("0.4.0", "0.3.0")
    assert act.es_mas_nueva("v0.3.10", "0.3.9")          # 10 > 9 aunque como texto sea menor
    assert not act.es_mas_nueva("0.3.0", "0.3")          # iguales
    assert not act.es_mas_nueva("0.2.5", "0.3.0")
    assert act.es_mas_nueva("0.4.0", "desconocida")


@pytest.mark.parametrize("sistema, maquina, url", [
    ("win32", "AMD64", "https://x/win.exe"),
    ("darwin", "arm64", "https://x/arm.dmg"),
    ("darwin", "x86_64", "https://x/intel.dmg"),
    ("linux", "x86_64", ""),
])
def test_elige_el_instalador_de_cada_computadora(sistema, maquina, url):
    n = act.novedad_desde_release(RELEASE, sistema, maquina)
    assert n.version == "0.4.0" and n.url == url and n.instalable == bool(url)
    assert n.notas.startswith("## Novedades")


def test_buscar(monkeypatch):
    monkeypatch.setattr(act, "_abrir", lambda url, timeout: _Respuesta(json.dumps(RELEASE).encode()))
    assert act.buscar("0.3.0").version == "0.4.0"
    assert act.buscar("0.4.0") is None                     # al día
    monkeypatch.setattr(act, "_abrir", lambda url, timeout: _Respuesta(json.dumps({**RELEASE, "prerelease": True}).encode()))
    assert act.buscar("0.3.0") is None                     # las de prueba no se ofrecen

    def sin_red(url, timeout):
        raise OSError("sin conexión")
    monkeypatch.setattr(act, "_abrir", sin_red)
    with pytest.raises(act.ErrorActualizacion, match="No se pudo consultar GitHub"):
        act.buscar("0.3.0")


def test_descargar_con_progreso_y_cancelar(monkeypatch, tmp_path):
    datos = b"x" * 600_000
    monkeypatch.setattr(act, "_abrir", lambda url, timeout: _Respuesta(datos))
    n = act.Novedad("0.4.0", "", "", "LBD-0.4.0-Windows-Instalador.exe", "https://x/win.exe", len(datos))
    vistos = []
    archivo = act.descargar(n, tmp_path, lambda b, t: vistos.append((b, t)))
    assert archivo.read_bytes() == datos and vistos[-1] == (len(datos), len(datos))

    with pytest.raises(act.ErrorActualizacion, match="cancelada"):
        act.descargar(n, tmp_path / "otra", lambda b, t: False)
    assert not list((tmp_path / "otra").iterdir())         # no queda el archivo a medias


def test_comando_windows_espera_e_instala_en_silencio():
    cmd = act.comando_windows(Path(r"C:\Temp\LBD Flightcase's\inst.exe"), 4321, r"C:\Program Files\LBD\app.exe")
    assert cmd[0] == "powershell" and "Hidden" in cmd
    script = cmd[-1]
    assert script.startswith("Wait-Process -Id 4321")
    assert "'C:\\Temp\\LBD Flightcase''s\\inst.exe'" in script     # comillas de PowerShell
    assert "'/SILENT'" in script and "'/RELANZAR=1'" in script
    assert "catch { Start-Process -FilePath 'C:\\Program Files\\LBD\\app.exe' }" in script


def test_guion_mac_reemplaza_la_app_y_la_abre():
    app = Path("/Applications/LBD Flightcase Maker.app")
    nueva = Path("/Applications/.LBD Flightcase Maker-nueva.app")
    g = act.guion_mac(nueva, app, 99, None)
    assert "while kill -0 99" in g
    assert "mv '/Applications/LBD Flightcase Maker.app' '/Applications/.LBD Flightcase Maker-vieja.app'" in g
    assert "xattr -dr com.apple.quarantine" in g
    assert g.rstrip().endswith("open '/Applications/LBD Flightcase Maker.app'")


def test_mac_abierta_desde_el_dmg_se_actualiza_a_mano(tmp_path):
    dmg = tmp_path / "LBD.dmg"
    for app in (Path("/Volumes/LBD Flightcase Maker/LBD Flightcase Maker.app"),
                Path("/private/var/folders/x/AppTranslocation/ABC/d/LBD Flightcase Maker.app")):
        inst = act.preparar_mac(dmg, 1, app)
        assert inst.manual and inst.comando == ["open", str(dmg)] and "Aplicaciones" in inst.mensaje


def test_bundle_actual():
    assert act.bundle_actual("/Applications/LBD Flightcase Maker.app/Contents/MacOS/LBD Flightcase Maker") \
        == Path("/Applications/LBD Flightcase Maker.app")
    assert act.bundle_actual("/usr/bin/python3") is None


# ------------------------------------------------------------------ ventana
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ventana(qapp, monkeypatch):
    from PySide6.QtCore import QSettings
    from flightcase.ui import actualizador as ui
    from flightcase.ui.app import FlightCaseMainWindow
    w = FlightCaseMainWindow(restore_settings=False)
    w.actualizador.sincronico = True
    s = QSettings("FlightcaseCalculatorTests", "actualizaciones")
    s.clear()
    w.actualizador.settings = lambda: s
    monkeypatch.setattr(ui, "version", lambda: "0.3.0")
    yield w
    w.close()


def test_menu_y_aviso(ventana, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from flightcase.ui import actualizador as ui
    textos = [a.text() for a in ventana.help_menu.actions()]
    assert "&Buscar actualizaciones..." in textos
    assert ventana.accion_buscar_al_abrir.isChecked()
    ventana.accion_buscar_al_abrir.setChecked(False)
    assert not ventana.actualizador.buscar_al_abrir

    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda p, t, m: avisos.append(m))
    monkeypatch.setattr(ui.act, "buscar", lambda v: None)
    ventana.actualizador.buscar()
    assert avisos == ["Ya tenés la última versión (0.3.0)."]
    ventana.actualizador.buscar(silencioso=True)             # al abrir, si no hay nada, no avisa
    assert len(avisos) == 1

    n = act.novedad_desde_release(RELEASE, "win32")
    monkeypatch.setattr(ui.act, "buscar", lambda v: n)
    ofrecidas = []
    monkeypatch.setattr(ventana.actualizador, "preguntar", lambda n, a, s: ofrecidas.append(n.version) or "omitir")
    ventana.actualizador.buscar(silencioso=True)
    assert ofrecidas == ["0.4.0"]
    ventana.actualizador.buscar(silencioso=True)             # la omitió: no se la ofrece de nuevo al abrir
    assert ofrecidas == ["0.4.0"]
    ventana.actualizador.buscar()                            # desde el menú, sí
    assert ofrecidas == ["0.4.0", "0.4.0"]


def test_sin_internet_al_abrir_no_molesta(ventana, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from flightcase.ui import actualizador as ui

    def falla(v):
        raise act.ErrorActualizacion("No se pudo consultar GitHub: sin red")
    monkeypatch.setattr(ui.act, "buscar", falla)
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda p, t, m: avisos.append(m))
    ventana.actualizador.buscar(silencioso=True)
    assert avisos == []
    ventana.actualizador.buscar()
    assert avisos and "sin red" in avisos[0]


def test_actualizar_descarga_guarda_cambios_e_instala(ventana, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    from flightcase.ui import actualizador as ui
    t = ventana.taller_widget
    t.set_params({"int_ancho": 900}, str(tmp_path / "x.scad"))
    t.editores["int_ancho"].poner(700)
    instalador = tmp_path / "inst.exe"
    monkeypatch.setattr(ui.act, "descargar", lambda n, progreso=None: instalador)
    lanzados, cerrada = [], []
    monkeypatch.setattr(ui.act, "preparar_instalacion", lambda a: act.Instalacion(["instalar", str(a)]))
    monkeypatch.setattr(ui.act, "lanzar", lambda inst: lanzados.append(inst.comando))
    monkeypatch.setattr(ventana.actualizador, "salir", lambda: cerrada.append(1))
    n = act.novedad_desde_release(RELEASE, "win32")

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel)
    ventana.actualizador.actualizar(n)
    assert lanzados == [] and not cerrada                    # canceló: no se cierra ni instala

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Save)
    ventana.actualizador.actualizar(n)
    assert "int_ancho = 700" in (tmp_path / "x.scad").read_text(encoding="utf-8")
    assert lanzados == [["instalar", str(instalador)]] and cerrada == [1]
