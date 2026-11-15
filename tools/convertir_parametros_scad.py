#!/usr/bin/env python3
"""Lee la cabecera de flightcase.scad y escribe la ayuda de cada parámetro.

    python tools/convertir_parametros_scad.py ruta/a/flightcase_gen/flightcase.scad

Genera flightcase/resources/taller_parametros_info.json: una lista de secciones
[{"seccion": "...", "parametros": [{"nombre", "ayuda"}]}] en el orden del archivo,
que usa la pestaña Taller de la app. Las secciones de vista/colores quedan afuera.
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "flightcase" / "resources" / "taller_parametros_info.json"
OMITIR_SECCIONES = {"Vista", "Colores (solo para el modelo 3D y los planos)"}
OMITIR = {"cubierta_abierta", "resaltar_cubierta", "vista_parte", "resaltar_que"}


def convertir(texto):
    secciones, actual, previos = [], None, []
    for linea in texto.splitlines():
        s = linea.strip()
        m = re.match(r"/\*\s*\[(.+?)\]\s*\*/", s)
        if m:
            actual = {"seccion": m.group(1), "parametros": []}
            secciones.append(actual)
            previos = []
            continue
        if actual is None:
            continue
        if s.startswith("module ") or s.startswith("function "):
            break
        if s.startswith("//"):
            previos.append(s.lstrip("/").strip())
            continue
        m = re.match(r"([A-Za-z_]\w*)\s*=\s*(.*?);\s*(?://\s*(.*))?$", s)
        if m:
            ayuda = " ".join(previos + ([m.group(3).strip()] if m.group(3) else []))
            actual["parametros"].append({"nombre": m.group(1), "ayuda": ayuda})
        previos = [] if s else previos
    return [s for s in secciones if s["seccion"] not in OMITIR_SECCIONES and
            not s.update(parametros=[p for p in s["parametros"] if p["nombre"] not in OMITIR])
            and s["parametros"]]


if __name__ == "__main__":
    datos = convertir(Path(sys.argv[1]).read_text(encoding="utf-8"))
    # los nombres en castellano ("etiqueta") se cargan a mano: se conservan al regenerar
    previas = ({p["nombre"]: p["etiqueta"] for s in json.loads(SALIDA.read_text(encoding="utf-8"))
                for p in s["parametros"] if p.get("etiqueta")} if SALIDA.is_file() else {})
    for s in datos:
        for p in s["parametros"]:
            if p["nombre"] in previas:
                p["etiqueta"] = previas[p["nombre"]]
    SALIDA.write_text(json.dumps(datos, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{sum(len(s['parametros']) for s in datos)} parámetros en {len(datos)} secciones -> {SALIDA}")
