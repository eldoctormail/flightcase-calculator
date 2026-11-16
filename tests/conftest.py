"""Configuración común de los tests."""

import os
import tempfile

# Los tests nunca escriben en la carpeta de datos real del usuario.
os.environ.setdefault("FLIGHTCASE_DATA_DIR", tempfile.mkdtemp(prefix="flightcase-tests-"))


import pytest


@pytest.fixture(autouse=True)
def _sin_dialogos_que_bloqueen(monkeypatch):
    """Un QMessageBox.question sin respuesta prevista colgaría los tests: falla enseguida."""
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:
        return

    def _pregunta(*args, **kwargs):
        raise AssertionError(f"QMessageBox.question sin respuesta en el test: {args[1:3]}")
    monkeypatch.setattr(QMessageBox, "question", _pregunta)
