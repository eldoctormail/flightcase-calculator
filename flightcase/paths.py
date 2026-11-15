"""Rutas de recursos incluidos y de datos editables del usuario.

En la app instalada la carpeta de recursos es de solo lectura (dentro del .app o de
Archivos de programa), así que lo que el usuario guarda va a su
carpeta de datos (por ejemplo, los estilos de case propios).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "FlightcaseCalculator"
RESOURCES_DIR = Path(__file__).resolve().parent / "resources"


def user_data_dir() -> Path:
    """Carpeta de datos del usuario (se puede forzar con FLIGHTCASE_DATA_DIR)."""
    override = os.environ.get("FLIGHTCASE_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_DIR_NAME


def bundled_resource(name: str) -> Path:
    return RESOURCES_DIR / name


def user_resource(name: str) -> Path:
    return user_data_dir() / name
