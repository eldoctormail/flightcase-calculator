"""Genera los íconos de la app a partir de packaging/icono/icono.svg.

    python tools/generar_icono.py

Salen:
- packaging/icono/icono.ico   (Windows: 16 a 256 px, en PNG dentro del .ico)
- packaging/icono/icono.icns  (macOS: 16 a 1024 px)
- flightcase/resources/icono.png (256 px, ícono de la ventana)

No hace falta nada fuera de PySide6: el .ico y el .icns se arman a mano con PNG adentro.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SVG = RAIZ / "packaging" / "icono" / "icono.svg"


def png(renderer: QSvgRenderer, lado: int) -> bytes:
    img = QImage(lado, lado, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(p)
    p.end()
    datos = QByteArray()
    buf = QBuffer(datos)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(datos)


def ico(imagenes: dict) -> bytes:
    lados = sorted(imagenes)
    cabecera = struct.pack("<HHH", 0, 1, len(lados))
    pos = 6 + 16 * len(lados)
    entradas, cuerpo = b"", b""
    for lado in lados:
        d = imagenes[lado]
        b = 0 if lado >= 256 else lado
        entradas += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(d), pos)
        cuerpo += d
        pos += len(d)
    return cabecera + entradas + cuerpo


def icns(imagenes: dict) -> bytes:
    tipos = [(b"icp4", 16), (b"icp5", 32), (b"icp6", 64), (b"ic07", 128), (b"ic08", 256), (b"ic09", 512),
             (b"ic10", 1024), (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512)]
    cuerpo = b"".join(t + struct.pack(">I", len(imagenes[l]) + 8) + imagenes[l] for t, l in tipos)
    return b"icns" + struct.pack(">I", len(cuerpo) + 8) + cuerpo


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841 (QPainter necesita la app)
    r = QSvgRenderer(str(SVG))
    if not r.isValid():
        print(f"No se pudo leer {SVG}")
        return 1
    imgs = {l: png(r, l) for l in (16, 24, 32, 48, 64, 128, 256, 512, 1024)}
    (RAIZ / "packaging" / "icono" / "icono.ico").write_bytes(ico({l: imgs[l] for l in (16, 24, 32, 48, 64, 128, 256)}))
    (RAIZ / "packaging" / "icono" / "icono.icns").write_bytes(icns(imgs))
    (RAIZ / "flightcase" / "resources" / "icono.png").write_bytes(imgs[256])
    print("Íconos generados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
