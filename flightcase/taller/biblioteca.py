"""Biblioteca de equipos: los equipos propios (consolas, potencias, micrófonos, racks...) con
sus medidas, guardados una vez y reusados en la espuma o el rack de cualquier case.

Se guarda en la carpeta de datos del usuario (biblioteca_equipos.json) y se puede pasar a y
desde una planilla CSV (separador ; y coma decimal, como la abre Excel en castellano).
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Iterable, List, Optional

from ..paths import user_resource

ARCHIVO = "biblioteca_equipos.json"
U_MM = 44.45                  # una unidad de rack
ANCHO_19 = 482.6              # frente de un equipo de 19"


@dataclass
class EquipoBiblio:
    nombre: str
    categoria: str = ""
    ancho: float = 0.0        # de costado a costado
    fondo: float = 0.0        # de adelante hacia atrás
    alto: float = 0.0
    peso: float = 0.0         # kg
    u: int = 0                # unidades de rack (0 = no va en rack)
    forma: str = ""           # forma del calado en la espuma: "", "redondo" o ruta a un .dxf / .svg
    radio: float = -1.0       # radio de las esquinas del calado (-1 = el general del case)
    dedos: int = 0            # huecos para los dedos: 0, 1 o 2
    sobresale: float = 0.0    # rack: cuánto sobresale adelante de las orejas (perillas, manijas)
    nota: str = ""

    @property
    def es_rack(self) -> bool:
        return self.u > 0

    def fila_equipos(self, x: Any = "c", y: Any = "c", z: Any = 0) -> List[Any]:
        """Fila para la tabla de equipos del interior (espuma)."""
        ancho = self.ancho or (ANCHO_19 if self.es_rack else 0)
        alto = self.alto or (self.u * U_MM if self.es_rack else 0)
        return [self.nombre, ancho, self.fondo, alto, self.peso, x, y, z, self.forma, self.radio, self.dedos]

    def fila_rack(self) -> List[Any]:
        """Fila para la tabla de equipos de rack."""
        return [self.nombre, max(self.u, 1), self.fondo, self.peso, 0, self.sobresale]


COLUMNAS_CSV = [("Nombre", "nombre"), ("Categoría", "categoria"), ("Ancho", "ancho"), ("Fondo", "fondo"),
                ("Alto", "alto"), ("Peso kg", "peso"), ("U", "u"), ("Forma en la espuma", "forma"),
                ("Radio", "radio"), ("Dedos", "dedos"), ("Sobresale adelante", "sobresale"), ("Nota", "nota")]
_NUMERICOS = {f.name: f.type for f in fields(EquipoBiblio) if f.type in ("float", "int")}


def _num(valor: Any, entero: bool = False) -> Any:
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".") or "0"
    n = float(valor)
    return int(round(n)) if entero else n


def desde_dict(d: Dict[str, Any]) -> EquipoBiblio:
    datos: Dict[str, Any] = {}
    for f in fields(EquipoBiblio):
        if f.name not in d or d[f.name] is None or d[f.name] == "":
            continue
        v = d[f.name]
        if f.name in _NUMERICOS:
            v = _num(v, _NUMERICOS[f.name] == "int")
        else:
            v = str(v).strip()
        datos[f.name] = v
    if not datos.get("nombre"):
        raise ValueError("un equipo sin nombre")
    return EquipoBiblio(**datos)


def desde_fila_equipos(fila: List[Any]) -> EquipoBiblio:
    """De una fila de la tabla de equipos del interior."""
    f = list(fila) + [None] * 11
    return desde_dict(dict(nombre=f[0], ancho=f[1], fondo=f[2], alto=f[3], peso=f[4], forma=f[8],
                           radio=f[9] if f[9] is not None else -1, dedos=f[10]))


def desde_fila_rack(fila: List[Any]) -> EquipoBiblio:
    """De una fila de la tabla de equipos de rack."""
    f = list(fila) + [None] * 6
    u = int(_num(f[1] or 1, True))
    return desde_dict(dict(nombre=f[0], u=u, ancho=ANCHO_19, alto=round(u * U_MM, 2), fondo=f[2], peso=f[3],
                           sobresale=f[5], categoria="Rack 19\""))


def cargar() -> List[EquipoBiblio]:
    ruta = user_resource(ARCHIVO)
    if not ruta.is_file():
        return []
    try:
        filas = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for d in filas if isinstance(filas, list) else []:
        try:
            out.append(desde_dict(d))
        except (TypeError, ValueError):
            continue
    return out


def guardar(equipos: Iterable[EquipoBiblio]) -> None:
    ruta = user_resource(ARCHIVO)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = [asdict(e) for e in sorted(equipos, key=lambda e: (e.categoria.lower(), e.nombre.lower()))]
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def sumar(biblioteca: List[EquipoBiblio], nuevos: Iterable[EquipoBiblio]) -> List[str]:
    """Agrega (o reemplaza, si ya hay uno con el mismo nombre) y devuelve los reemplazados."""
    reemplazados = []
    for n in nuevos:
        for i, e in enumerate(biblioteca):
            if e.nombre.strip().lower() == n.nombre.strip().lower():
                biblioteca[i] = n
                reemplazados.append(n.nombre)
                break
        else:
            biblioteca.append(n)
    return reemplazados


def _texto_num(v: Any) -> str:
    if isinstance(v, (int, float)):
        t = f"{v:.2f}".rstrip("0").rstrip(".")
        return t.replace(".", ",")
    return str(v)


def a_csv(equipos: Iterable[EquipoBiblio]) -> str:
    salida = io.StringIO()
    w = csv.writer(salida, delimiter=";", lineterminator="\n")
    w.writerow([t for t, _ in COLUMNAS_CSV])
    for e in equipos:
        d = asdict(e)
        w.writerow([_texto_num(d[c]) for _, c in COLUMNAS_CSV])
    return salida.getvalue()


def desde_csv(texto: str) -> List[EquipoBiblio]:
    """Lee una planilla con encabezados (los de a_csv, sin importar mayúsculas ni el orden)."""
    texto = texto.lstrip("﻿")
    primera = texto.splitlines()[0] if texto.strip() else ""
    delim = ";" if primera.count(";") >= primera.count(",") else ","
    lector = csv.reader(io.StringIO(texto), delimiter=delim)
    filas = list(lector)
    if not filas:
        return []
    por_titulo = {t.lower(): c for t, c in COLUMNAS_CSV}
    por_titulo.update({c: c for _, c in COLUMNAS_CSV})
    columnas: List[Optional[str]] = [por_titulo.get(h.strip().lower()) for h in filas[0]]
    if "nombre" not in columnas:
        raise ValueError("la planilla no tiene la columna Nombre")
    out = []
    for fila in filas[1:]:
        d = {c: v for c, v in zip(columnas, fila) if c}
        if not (d.get("nombre") or "").strip():
            continue
        out.append(desde_dict(d))
    return out


def acomodar_en_espuma(equipos: List[EquipoBiblio], holgura: float, pared: float, fondo_min: float,
                       separacion: Optional[float] = None, plancha: float = 0.0) -> Dict[str, Any]:
    """Pone los equipos uno al lado del otro (de izquierda a derecha) en un bloque de espuma y
    devuelve las medidas interiores que hacen falta y las filas de la tabla de equipos.

    ancho = paredes + equipos con su holgura + espuma entre ellos; fondo = el equipo más
    profundo; alto del cuerpo = el equipo más alto + espuma de fondo, redondeado a planchas
    enteras si se indica su espesor."""
    sep = pared if separacion is None else separacion
    x = pared + holgura
    filas, prof, alto = [], 0.0, 0.0
    for i, e in enumerate(equipos):
        f = e.fila_equipos()
        ancho, fondo, h = f[1], f[2], f[3]
        if i:
            x += sep + 2 * holgura
        f[5], f[7] = round(x, 1), round(fondo_min, 1)
        filas.append(f)
        x += ancho
        prof, alto = max(prof, fondo), max(alto, h)
    return {
        "int_ancho": round(x + holgura + pared, 1),
        "int_prof": round(prof + 2 * (holgura + pared), 1),
        "int_alto_cuerpo": round(math.ceil((alto + fondo_min) / plancha - 1e-6) * plancha if plancha > 0
                                 else alto + fondo_min, 1),
        "equipos": filas,
    }
