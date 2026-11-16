"""Dibuja las miniaturas de los estilos incluidos para la pantalla de inicio.

    python tools/generar_miniaturas_estilos.py

Salen en flightcase/resources/estilos/<id>.png. Hay que correrlo al agregar o cambiar un estilo
en flightcase/resources/taller_estilos.json.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightcase.taller import estilos, familias  # noqa: E402


def main() -> int:
    errores = 0
    for e in estilos.estilos_incluidos():
        ruta = familias.dibujar_miniatura(e)
        print(("ok    " if ruta else "ERROR ") + e.id)
        errores += ruta is None
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
