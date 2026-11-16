"""El tema oscuro tiene que leerse entero: con un error de sintaxis Qt descarta toda la hoja de estilo."""

from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QLabel


def test_la_hoja_de_estilo_se_lee_sin_errores():
    from flightcase.ui.theme import DARK_THEME_QSS
    app = QApplication.instance() or QApplication([])
    assert DARK_THEME_QSS.count("{") == DARK_THEME_QSS.count("}")
    mensajes = []
    anterior = qInstallMessageHandler(lambda _tipo, _ctx, texto: mensajes.append(texto))
    try:
        app.setStyleSheet(DARK_THEME_QSS)
        etiqueta = QLabel("x")
        etiqueta.show()
        app.processEvents()
        etiqueta.hide()
    finally:
        qInstallMessageHandler(anterior)
    assert not [m for m in mensajes if "stylesheet" in m.lower()], mensajes


def test_selector_interiores_exteriores_muestra_las_dos_opciones():
    """Con la hoja de estilo, el desplegable de Medición se abría encima del combo y recortado:
    «Exteriores» quedaba tapado y no se podía elegir."""
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from flightcase.ui.theme import DARK_THEME_QSS
    from flightcase.ui.widgets import TallerWidget
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(DARK_THEME_QSS)
    try:
        w = TallerWidget()
        w.resize(1200, 700)
        w.show()
        app.processEvents()
        c = w.cmb_medicion
        c.showPopup()
        app.processEvents()
        v = c.view()
        ultima = v.visualRect(c.model().index(c.count() - 1, 0))
        assert v.viewport().rect().contains(ultima), (ultima, v.viewport().rect())
        assert v.window().mapToGlobal(v.window().rect().topLeft()).y() >= c.mapToGlobal(c.rect().bottomLeft()).y() - 2
        QTest.qWait(600)
        QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, ultima.center())
        app.processEvents()
        assert c.currentData() == "exterior"
        w.set_medicion("interior")
        w.close()
    finally:
        app.setStyleSheet("")
