"""Forma y capa DXF del calado de cada herraje, según su artículo del catálogo.

Del catálogo (ver catalogo.CON_CALADO):

- ``forma_corte``: rectangular (con el radio de siempre), redondo (círculo u óvalo del ancho x alto
  del calado) o dibujo: el contorno de ``corte_dibujo`` (.dxf o .svg) encajado en el calado sin
  deformarlo, girado 90° si el calado está parado y el dibujo acostado.
- ``capa_calado``: la capa del DXF del calado (vacío = 0, con el contorno de la pieza).

Devuelve, por panel, una entrada por calado (en el orden de ``res.calados``) con ``capa`` y
``puntos`` (polígonos, o None si va como rectángulo), lista para los dicts de produccion.datos.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

from .modelo import ResultadoTaller
from .perforaciones import capa_valida

CLAVE_DE_TIPO = {"cierre": "cierre", "manija": "manija", "cazoleta": "cazoleta", "encastre": "plato"}
PUNTOS_OVALO = 72


def _ovalo(cx: float, cy: float, w: float, h: float) -> List[Tuple[float, float]]:
    return [(round(cx + w / 2 * math.cos(2 * math.pi * k / PUNTOS_OVALO), 3),
             round(cy + h / 2 * math.sin(2 * math.pi * k / PUNTOS_OVALO), 3)) for k in range(PUNTOS_OVALO)]


CARPETA_DIBUJOS = "calados"


def carpeta_dibujos() -> str:
    from ..paths import user_resource
    return str(user_resource(CARPETA_DIBUJOS))


def ruta_dibujo(nombre: str) -> str:
    """El archivo del dibujo: un nombre suelto está en la carpeta de dibujos del usuario."""
    return nombre if os.path.isabs(nombre) else os.path.join(carpeta_dibujos(), nombre)


def importar_dibujo(origen: str, ref: str) -> str:
    """Copia el .dxf o .svg a la carpeta de dibujos (así no se pierde si movés el original) y
    lo lee para ver que tenga contornos. Devuelve el nombre para el catálogo; ValueError si no sirve."""
    import re
    import shutil
    from . import vectores
    ext = os.path.splitext(origen)[1].lower()
    if ext not in (".dxf", ".svg"):
        raise ValueError("el dibujo tiene que ser .dxf o .svg")
    lineas = vectores.leer(origen)
    if not any(len(l) >= 3 for l in lineas):
        raise ValueError("no tiene ningún contorno cerrado")
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", ref or os.path.splitext(os.path.basename(origen))[0]) or "calado"
    os.makedirs(carpeta_dibujos(), exist_ok=True)
    nombre = base + ext
    shutil.copyfile(origen, os.path.join(carpeta_dibujos(), nombre))
    return nombre


def _dibujo(archivo: str, cx: float, cy: float, w: float, h: float) -> Tuple[Optional[list], List[str]]:
    archivo = ruta_dibujo(archivo)
    from . import formas_espuma as FE
    from . import vectores
    nombre = os.path.basename(archivo)
    try:
        lineas = vectores.leer(archivo)
        xs = [p[0] for l in lineas for p in l]
        ys = [p[1] for l in lineas for p in l]
        bw, bh = (max(xs) - min(xs), max(ys) - min(ys)) if xs else (0.0, 0.0)
    except (OSError, ValueError) as e:
        return None, [f"No se pudo leer el dibujo del calado {nombre} ({e}): el calado va rectangular."]
    girar = bw > 0 and bh > 0 and (bw > bh) != (w > h) and abs(w - h) > 0.5
    ww, hh = (h, w) if girar else (w, h)
    grande = 4 * max(ww, hh) + 10
    polis, avisos = FE.contorno(grande / 2 - ww / 2, grande / 2 + ww / 2, grande / 2 - hh / 2, grande / 2 + hh / 2,
                                FE.Forma(tipo="contorno", archivo=archivo), grande, grande)
    avisos = [a.replace("del equipo", "del calado") for a in avisos]
    if not polis:
        return None, avisos
    out = []
    for pol in polis:
        pts = []
        for x, y in pol:
            u, v = x - grande / 2, y - grande / 2
            if girar:
                u, v = -v, u
            pts.append((round(cx + u, 3), round(cy + v, 3)))
        out.append(pts)
    return out, avisos


def estilos(res: ResultadoTaller) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    v = res.valores
    pf = v.get("perforacion") or {}
    manuales = v.get("manuales")
    man_de: Dict[int, Any] = {}
    if manuales is not None:
        for col in manuales.colocados:
            for c in col.calados:
                man_de[id(c)] = col
    out: Dict[str, List[Dict[str, Any]]] = {}
    avisos: List[str] = []
    for c in res.calados:
        col = man_de.get(id(c))
        if col is not None:
            datos = dict(col.datos or {})
        else:
            clave = CLAVE_DE_TIPO.get(c.tipo)
            datos = dict(pf.get(clave) or {}) if clave else {}
        estilo: Dict[str, Any] = {}
        if c.tipo != "rebaje" and not c.tipo.startswith("agujero"):
            if datos.get("capa_calado"):
                estilo["capa"] = capa_valida(datos["capa_calado"], "0")
            forma = str(datos.get("forma_corte") or ("dibujo" if datos.get("corte_dibujo") else "")).lower()
            if forma == "redondo":
                estilo["puntos"] = [_ovalo(c.cx, c.cy, c.ancho, c.alto)]
            elif forma == "dibujo":
                archivo = str(datos.get("corte_dibujo") or "")
                if not archivo:
                    avisos.append(f"El calado «{c.tipo}» tiene forma «dibujo» pero el catálogo no dice qué archivo: "
                                  "va rectangular.")
                else:
                    pts, av = _dibujo(archivo, c.cx, c.cy, c.ancho, c.alto)
                    avisos += [a for a in av if a not in avisos]
                    if pts:
                        estilo["puntos"] = pts
        out.setdefault(c.panel, []).append(estilo)
    return out, avisos


def aplicar(d: Dict[str, Any], res: ResultadoTaller) -> None:
    """Pone capa y puntos en los calados de `d` (los de produccion.datos, en el mismo orden)."""
    por_panel, avisos = estilos(res)
    for pid, lista in por_panel.items():
        cal = d["calados"].get(pid, [])
        for c, e in zip(cal, lista):
            c.update(e)
    for a in avisos:
        if a not in d["avisos"]:
            d["avisos"].append(a)
