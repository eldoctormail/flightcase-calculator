"""Copia de recuperación del case abierto, por si la app se cierra de golpe.

Mientras la app está abierta, cada tanto escribe el case con los cambios sin guardar en
la carpeta de datos del usuario (`recuperacion/<sesión>.scad`, más un `.json` con de qué
archivo es). Al cerrar bien la app se borra. Si al arrancar queda alguna de una sesión que
ya no está corriendo (se colgó, se cortó la luz, se apagó la compu), se ofrece recuperarla.

Que una sesión siga viva lo dice un QLockFile, que en la app lo maneja la ventana; acá
solo se leen y escriben los archivos.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from ..paths import user_data_dir

CARPETA = "recuperacion"


def carpeta() -> Path:
    return user_data_dir() / CARPETA


@dataclass
class Recuperable:
    id: str
    scad: str                   # la copia con los cambios
    ruta: Optional[str]         # el case del que es (None si nunca se guardó)
    carpeta_case: str           # para los logos y contornos con ruta relativa
    fecha: datetime             # cuándo se escribió la copia

    @property
    def nombre(self) -> str:
        return os.path.basename(self.ruta) if self.ruta else "un case nuevo sin guardar"

    def lock(self) -> str:
        return str(carpeta() / f"{self.id}.lock")


class Sesion:
    """La copia de recuperación de esta ventana."""

    def __init__(self, id: Optional[str] = None) -> None:
        self.id = id or f"{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}-{uuid.uuid4().hex[:6]}"

    @property
    def scad(self) -> Path:
        return carpeta() / f"{self.id}.scad"

    @property
    def meta(self) -> Path:
        return carpeta() / f"{self.id}.json"

    @property
    def lock(self) -> str:
        return str(carpeta() / f"{self.id}.lock")

    def escribir(self, texto: str, ruta: Optional[str], carpeta_case: str = "") -> bool:
        try:
            carpeta().mkdir(parents=True, exist_ok=True)
            for destino, contenido in ((self.scad, texto),
                                       (self.meta, json.dumps({"ruta": ruta or "", "carpeta": carpeta_case,
                                                               "fecha": datetime.now().isoformat(timespec="seconds")},
                                                              ensure_ascii=False))):
                tmp = destino.with_name(destino.name + ".tmp")
                tmp.write_text(contenido, encoding="utf-8")
                os.replace(tmp, destino)
            return True
        except OSError:
            return False

    def borrar(self) -> None:
        borrar(self.id)


def borrar(id: str) -> None:
    for ext in (".scad", ".json"):
        try:
            (carpeta() / f"{id}{ext}").unlink()
        except OSError:
            pass


def pendientes(sigue_abierta: Callable[[str], bool] = lambda lock: False,
               propia: Optional[str] = None) -> List[Recuperable]:
    """Las copias de sesiones que ya no están abiertas, de la más nueva a la más vieja.
    `sigue_abierta(ruta_del_lock)` dice si otra ventana de la app todavía la usa."""
    try:
        archivos = sorted(carpeta().glob("*.scad"))
    except OSError:
        return []
    salida: List[Recuperable] = []
    for scad in archivos:
        id = scad.stem
        if id == propia:
            continue
        try:
            meta = json.loads((carpeta() / f"{id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        try:
            fecha = datetime.fromisoformat(meta.get("fecha", ""))
        except (TypeError, ValueError):
            fecha = datetime.fromtimestamp(scad.stat().st_mtime)
        r = Recuperable(id=id, scad=str(scad), ruta=meta.get("ruta") or None,
                        carpeta_case=meta.get("carpeta") or "", fecha=fecha)
        if sigue_abierta(r.lock()):
            continue
        salida.append(r)
    salida.sort(key=lambda r: r.fecha, reverse=True)
    return salida
