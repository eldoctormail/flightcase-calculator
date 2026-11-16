"""Hoja del case: una sola página A4 con la vista 3D y una vista 2D acotada de cada lado.

Pensada para mostrar o guardar el case de un vistazo (no para fabricar: para eso están los
planos). Las seis vistas laterales se dibujan con render.imagen() en vista paralela, todas a la
misma escala, y se acotan con la medida total que se ve en cada una (con herrajes y ruedas).
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtGui import QImage

from .geometria import Malla3D, Opciones3D, malla_3d
from .modelo import ResultadoTaller
from .render import ejes_camara, imagen

# nombre: (cámara de OpenSCAD, título). Las mismas que el cubo de vistas de la vista 3D.
VISTAS: Dict[str, Tuple[str, str]] = {
    "frente": ("0,0,0,90,0,0,0", "Frente"),
    "atras": ("0,0,0,90,0,180,0", "Atrás"),
    "izquierda": ("0,0,0,90,0,270,0", "Izquierda"),
    "derecha": ("0,0,0,90,0,90,0", "Derecha"),
    "arriba": ("0,0,0,0,0,0,0", "Arriba"),
    "abajo": ("0,0,0,180,0,0,0", "Abajo"),
}
PX_LADO_MAYOR = 900        # píxeles del lado más largo del case en las vistas 2D
CAMARA_3D = "0,0,0,62,0,32,0"
COTA = "#1f4e9c"


@dataclass
class VistaLado:
    nombre: str
    titulo: str
    img: QImage
    ancho: float          # medida total horizontal en esta vista (mm)
    alto: float           # medida total vertical (mm)
    extent: Tuple[float, float, float, float]   # izq, der, abajo, arriba de la imagen, en mm
    limites: Tuple[float, float, float, float]  # izq, der, abajo, arriba del case, en mm


def _vertices(malla: Malla3D) -> np.ndarray:
    return np.array([(p.x, p.y, p.z) for f in malla.faces for p in f.vertices], dtype=float)


def vistas_lados(malla: Malla3D, colores: Optional[Dict[str, str]] = None,
                 px_lado_mayor: int = PX_LADO_MAYOR) -> List[VistaLado]:
    """Las seis vistas del case, a la misma escala y centradas en el centro del case."""
    pts = _vertices(malla)
    if not len(pts):
        return []
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    centro = (lo + hi) / 2
    escala = px_lado_mayor / max(float((hi - lo).max()), 1.0)     # px por mm
    vistas = []
    for nombre, (camara, titulo) in VISTAS.items():
        _, der, arriba = ejes_camara(camara)
        u, v = (pts - centro) @ der, (pts - centro) @ arriba
        ancho, alto = float(u.max() - u.min()), float(v.max() - v.min())
        margen = 6 / escala
        semi_w, semi_h = max(abs(u.min()), abs(u.max())) + margen, max(abs(v.min()), abs(v.max())) + margen
        w, h = max(8, int(np.ceil(2 * semi_w * escala))), max(8, int(np.ceil(2 * semi_h * escala)))
        img = imagen(malla, camara, f"{w},{h}", colores, transparente=True, orto=escala, centro_vista=centro)
        if img is None:
            continue
        semi_w, semi_h = w / 2 / escala, h / 2 / escala
        vistas.append(VistaLado(nombre, titulo, img, ancho, alto, (-semi_w, semi_w, -semi_h, semi_h),
                                (float(u.min()), float(u.max()), float(v.min()), float(v.max()))))
    return vistas


def _a_numpy(img: QImage) -> np.ndarray:
    """RGBA en 0..1 para matplotlib."""
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w]
    return arr.astype(np.float32) / 255.0


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def datos_case(res: ResultadoTaller, malla: Malla3D) -> List[Tuple[str, str]]:
    """Filas del cuadro de datos de la hoja."""
    from .planos import generar as gen
    from .produccion import lineas_datos
    d = gen.parsear_datos(lineas_datos(res))
    info = d["info"]
    ext = [float(x) for x in info["exterior"]]
    mundo = [float(x) for x in info.get("mundo", [ext[0], ext[1], ext[2] + ext[3]])]
    inte = [float(x) for x in info["interior"]]
    pts = _vertices(malla)
    total = pts.max(axis=0) - pts.min(axis=0) if len(pts) else np.zeros(3)
    filas = [
        ("Exterior (ancho x prof. x alto)", f"{_fmt(mundo[0])} x {_fmt(mundo[1])} x {_fmt(mundo[2])} mm"),
        ("Interior (ancho x prof. x alto)", " x ".join(_fmt(x) for x in inte[:3]) + " mm"),
        ("Medida total (con herrajes y ruedas)", " x ".join(_fmt(round(x)) for x in total) + " mm"),
        ("Placa", str(info.get("material", ""))),
    ]
    colores = info.get("color")
    if isinstance(colores, list) and colores:
        filas.append(("Color", colores[0] if len(colores) < 2 or colores[0] == colores[1]
                      else f"cuerpo {colores[0]}, tapa {colores[1]}"))
    peso = res.valores.get("peso")
    if getattr(peso, "total", 0):
        texto = f"{peso.total:.1f} kg".replace(".", ",")
        if peso.total > peso.vacio + 0.05:
            texto += f" ({peso.vacio:.1f} kg vacío)".replace(".", ",")
        filas.append(("Peso aproximado", texto))
    return filas


def generar_hoja(res: ResultadoTaller, ruta: str, nombre: str = "case",
                 imagen_3d: Optional[QImage] = None, colores: Optional[Dict[str, str]] = None,
                 px_lado_mayor: int = PX_LADO_MAYOR) -> str:
    """Guarda la hoja en `ruta` (PDF). `imagen_3d` es la vista 3D tal como se ve en la app; si no
    viene, se dibuja una isométrica."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    malla = malla_3d(res, Opciones3D())
    if imagen_3d is None or imagen_3d.isNull():
        lado = int(px_lado_mayor * 1.6)
        imagen_3d = imagen(malla, CAMARA_3D, f"{lado},{lado * 3 // 4}", colores, transparente=True)
    vistas = vistas_lados(malla, colores, px_lado_mayor)
    filas = datos_case(res, malla)

    fig = plt.figure(figsize=(11.69, 8.27))
    fig.text(0.03, 0.955, nombre, fontsize=17, weight="bold", va="top")
    fig.text(0.97, 0.955, datetime.date.today().strftime("%d/%m/%Y"), fontsize=9, ha="right", va="top",
             color="#555")
    fig.text(0.03, 0.02, "Medidas en mm. Las vistas de los lados están todas a la misma escala y acotadas "
             "con la medida total (herrajes y ruedas incluidos).",
             fontsize=8, color="#777")

    # vista 3D grande a la izquierda
    ax = fig.add_axes((0.02, 0.30, 0.46, 0.60))
    ax.axis("off")
    if imagen_3d is not None and not imagen_3d.isNull():
        ax.imshow(_a_numpy(imagen_3d), interpolation="lanczos")
    ax.set_aspect("equal")

    # datos del case debajo
    y = 0.255
    for etiqueta, valor in filas:
        fig.text(0.04, y, etiqueta, fontsize=9, color="#555", va="top")
        fig.text(0.25, y, valor, fontsize=9, va="top", weight="bold")
        y -= 0.032

    # seis vistas acotadas a la derecha, todas a la misma escala
    if vistas:
        semi_w = max(v.extent[1] for v in vistas)
        semi_h = max(v.extent[3] for v in vistas)
        aire = 0.22 * max(semi_w, semi_h)          # lugar para las cotas
        x0, ancho_col, alto_fila = 0.50, 0.24, 0.29
        for i, v in enumerate(vistas):
            col, fila = i % 2, i // 2
            ax = fig.add_axes((x0 + col * ancho_col, 0.62 - fila * alto_fila, ancho_col - 0.01, alto_fila - 0.035))
            ax.axis("off")
            ax.imshow(_a_numpy(v.img), extent=v.extent, interpolation="lanczos")
            ax.set_xlim(-semi_w - aire, semi_w + aire * 0.4)
            ax.set_ylim(-semi_h - aire, semi_h + aire * 0.2)
            ax.set_aspect("equal")
            ax.set_title(v.titulo, fontsize=10, weight="bold", loc="center", pad=2)
            u0, u1, v0, v1 = v.limites
            sep = aire * 0.45
            # horizontal, abajo
            yc = v0 - sep
            ax.plot([u0, u0], [v0 - sep * 0.2, yc - sep * 0.15], color=COTA, lw=0.5)
            ax.plot([u1, u1], [v0 - sep * 0.2, yc - sep * 0.15], color=COTA, lw=0.5)
            ax.annotate("", xy=(u0, yc), xytext=(u1, yc),
                        arrowprops=dict(arrowstyle="<|-|>", color=COTA, lw=0.7, shrinkA=0, shrinkB=0,
                                        mutation_scale=6))
            ax.text((u0 + u1) / 2, yc, _fmt(round(v.ancho)), ha="center", va="center", fontsize=7.5,
                    color=COTA, bbox=dict(fc="white", ec="none", pad=0.6))
            # vertical, a la izquierda
            xc = u0 - sep
            ax.plot([u0 - sep * 0.2, xc - sep * 0.15], [v0, v0], color=COTA, lw=0.5)
            ax.plot([u0 - sep * 0.2, xc - sep * 0.15], [v1, v1], color=COTA, lw=0.5)
            ax.annotate("", xy=(xc, v0), xytext=(xc, v1),
                        arrowprops=dict(arrowstyle="<|-|>", color=COTA, lw=0.7, shrinkA=0, shrinkB=0,
                                        mutation_scale=6))
            ax.text(xc, (v0 + v1) / 2, _fmt(round(v.alto)), ha="center", va="center", fontsize=7.5,
                    color=COTA, rotation=90, bbox=dict(fc="white", ec="none", pad=0.6))

    carpeta = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    with PdfPages(ruta) as pdf:
        pdf.infodict()["Title"] = f"Hoja del case - {nombre}"
        pdf.savefig(fig, dpi=220)
    plt.close(fig)
    return ruta
