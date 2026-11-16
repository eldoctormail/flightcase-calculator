"""Versión de la app: la del instalador (escrita en _version.py al compilar) o la de pyproject.toml."""

from __future__ import annotations

from pathlib import Path

AUTOR = "Javier Amigo"


def version() -> str:
    try:
        from ._version import VERSION   # lo escribe el workflow de instaladores
        return VERSION
    except ImportError:
        pass
    try:
        import tomllib
        with open(Path(__file__).resolve().parent.parent / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        pass
    try:
        from importlib.metadata import version as _v
        return _v("flightcase-calculator")
    except Exception:
        return "desconocida"
