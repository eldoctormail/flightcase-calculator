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
