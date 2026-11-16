"""Copias fechadas de cada case, para volver a una versión anterior.

Antes de que un guardado (a mano o automático) pise el archivo, lo que había se copia a
`.versiones/<nombre del case>/AAAA-MM-DD HH.MM.SS.scad` (la fecha en que se había guardado
eso), junto al case. Así las copias
viajan con la carpeta (si la copiás a un pendrive o la tenés en Dropbox, van con ella)
y «Mis cases» no las lista, porque no entra en carpetas ocultas.

Para no juntar cientos de copias casi iguales se guarda como mucho una cada
`INTERVALO_MINUTOS`, salvo la primera de cada vez que se abre el case (así siempre queda
cómo estaba antes de empezar a tocarlo). Las viejas se van raleando: todas las de los
últimos dos días, una por día hasta los dos meses y una por mes después.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

CARPETA = ".versiones"
FORMATO = "%Y-%m-%d %H.%M.%S"
INTERVALO_MINUTOS = 10
TODAS_DIAS = 2            # se guardan todas las de los últimos días
DIARIAS_DIAS = 60         # después, una por día hasta acá; más viejas, una por mes
MAXIMO = 200


@dataclass
class Version:
    ruta: str              # el .scad de la copia
    fecha: datetime

    @property
    def tamano(self) -> int:
        try:
            return os.path.getsize(self.ruta)
        except OSError:
            return 0


def carpeta_versiones(ruta_case: str) -> str:
    ruta_case = os.path.abspath(ruta_case)
    nombre = os.path.splitext(os.path.basename(ruta_case))[0]
    return os.path.join(os.path.dirname(ruta_case), CARPETA, nombre)


def listar(ruta_case: str) -> List[Version]:
    """Las copias del case, de la más nueva a la más vieja."""
    carpeta = carpeta_versiones(ruta_case)
    versiones: List[Version] = []
    try:
        nombres = os.listdir(carpeta)
    except OSError:
        return versiones
    for n in nombres:
        base, ext = os.path.splitext(n)
        if ext.lower() != ".scad":
            continue
        try:
            fecha = datetime.strptime(base[:19], FORMATO)
        except ValueError:
            continue
        versiones.append(Version(os.path.join(carpeta, n), fecha))
    versiones.sort(key=lambda v: (v.fecha, v.ruta), reverse=True)
    return versiones


def _leer(ruta: str) -> Optional[bytes]:
    try:
        return Path(ruta).read_bytes()
    except OSError:
        return None


def _ocultar(carpeta: str) -> None:
    """En Windows las carpetas con punto no se ocultan solas."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(carpeta, 0x02)
        except Exception:
            pass


def respaldar(ruta_case: str, forzar: bool = False, ahora: Optional[datetime] = None) -> Optional[str]:
    """Copia el archivo como está ahora en el disco (antes de pisarlo). Devuelve la copia nueva,
    o None si no hacía falta: el archivo no existe, es igual a la última copia, o la última
    tiene menos de INTERVALO_MINUTOS (salvo `forzar`)."""
    contenido = _leer(ruta_case)
    if contenido is None:
        return None
    ahora = (ahora or datetime.now()).replace(microsecond=0)
    try:        # la copia lleva la fecha en que se guardó ese contenido, no la de ahora
        fecha = datetime.fromtimestamp(os.path.getmtime(ruta_case)).replace(microsecond=0)
    except OSError:
        fecha = ahora
    fecha = min(fecha, ahora)
    previas = listar(ruta_case)
    if previas:
        ultima = previas[0]
        if _leer(ultima.ruta) == contenido:
            return None
        if not forzar and fecha - ultima.fecha < timedelta(minutes=INTERVALO_MINUTOS):
            return None
    carpeta = carpeta_versiones(ruta_case)
    try:
        nueva_raiz = not os.path.isdir(os.path.dirname(carpeta))
        os.makedirs(carpeta, exist_ok=True)
        if nueva_raiz:
            _ocultar(os.path.dirname(carpeta))
        destino = os.path.join(carpeta, f"{fecha.strftime(FORMATO)}.scad")
        n = 2
        while os.path.exists(destino):
            destino = os.path.join(carpeta, f"{fecha.strftime(FORMATO)} ({n}).scad")
            n += 1
        tmp = destino + ".tmp"
        Path(tmp).write_bytes(contenido)
        os.replace(tmp, destino)
    except OSError:
        return None
    podar(ruta_case, ahora)
    return destino


def a_conservar(versiones: Iterable[Version], ahora: datetime) -> List[Version]:
    """Qué copias quedan después de ralear (de la más nueva a la más vieja)."""
    quedan: List[Version] = []
    vistos = set()
    for v in sorted(versiones, key=lambda v: v.fecha, reverse=True):
        edad = ahora - v.fecha
        if edad < timedelta(days=TODAS_DIAS):
            clave = None
        elif edad < timedelta(days=DIARIAS_DIAS):
            clave = ("dia", v.fecha.date())
        else:
            clave = ("mes", v.fecha.year, v.fecha.month)
        if clave is not None:
            if clave in vistos:        # ya está la más nueva de ese día o de ese mes
                continue
            vistos.add(clave)
        quedan.append(v)
    return quedan[:MAXIMO]


def podar(ruta_case: str, ahora: Optional[datetime] = None) -> int:
    """Borra las copias que sobran. Devuelve cuántas borró."""
    todas = listar(ruta_case)
    quedan = {v.ruta for v in a_conservar(todas, ahora or datetime.now())}
    borradas = 0
    for v in todas:
        if v.ruta not in quedan:
            try:
                os.remove(v.ruta)
                borradas += 1
            except OSError:
                pass
    return borradas


def mover(vieja: str, nueva: str) -> None:
    """Al renombrar el case, sus copias van con él."""
    origen, destino = carpeta_versiones(vieja), carpeta_versiones(nueva)
    if origen == destino or not os.path.isdir(origen):
        return
    if os.path.normcase(origen) == os.path.normcase(destino):    # solo cambiaron mayúsculas
        tmp = destino + ".renombrando"
        os.replace(origen, tmp)
        os.replace(tmp, destino)
        return
    if os.path.exists(destino):         # quedaron copias de otro case con ese nombre: se juntan
        for n in os.listdir(origen):
            if not os.path.exists(os.path.join(destino, n)):
                shutil.move(os.path.join(origen, n), os.path.join(destino, n))
        shutil.rmtree(origen, ignore_errors=True)
    else:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        os.replace(origen, destino)


def a_la_papelera(ruta_case: str, mandar=None) -> None:
    """Al borrar el case, sus copias también van a la papelera (`mandar(carpeta)` -> bool)."""
    carpeta = carpeta_versiones(ruta_case)
    if not os.path.isdir(carpeta):
        return
    if mandar is None or not mandar(carpeta):
        shutil.rmtree(carpeta, ignore_errors=True)
    raiz = os.path.dirname(carpeta)
    try:
        os.rmdir(raiz)                  # si era el último case con copias
    except OSError:
        pass
