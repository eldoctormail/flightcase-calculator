"""Modelos 3D (STEP) de los herrajes propios del catálogo.

Un artículo del catálogo puede tener en ``datos``:

- ``modelo``: el archivo .step de la pieza. Al importarlo se copia a la carpeta de datos del
  usuario (``modelos_3d/``) y queda sólo el nombre; también puede ser una ruta completa.
- ``modelo_frente``: qué eje del modelo mira hacia afuera del case cuando la pieza está
  puesta: ``+Z`` (el que se usa si no se dice), ``-Z``, ``+X``, ``-X``, ``+Y`` o ``-Y``.
- ``modelo_adentro``: cuántos mm del modelo quedan metidos en la placa (un cierre embutido,
  un conector): 0 = la pieza apoya sobre la cara de afuera.

Los triángulos de cada modelo se guardan al lado del .step (``.malla.npz``) para no volver a
calcularlos cada vez que se abre la app.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..paths import user_resource
from . import step_leer

CARPETA = "modelos_3d"
FRENTES = ("+Z", "-Z", "+X", "-X", "+Y", "-Y")
VERSION_CACHE = 1
MAX_TRIANGULOS = 40000      # más que esto no hace falta para ver un herraje


def carpeta() -> str:
    return str(user_resource(CARPETA))


def ruta(nombre: str) -> str:
    """Ruta del archivo de un modelo (el nombre guardado en el catálogo)."""
    if not nombre:
        return ""
    if os.path.isabs(nombre):
        return nombre
    return os.path.join(carpeta(), nombre)


def _nombre_libre(base: str, datos: bytes) -> str:
    """Nombre para la copia: el de la pieza; si ya hay otro archivo distinto con ese nombre,
    se le agrega un pedacito del contenido."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "modelo"
    nombre = base + ".step"
    destino = os.path.join(carpeta(), nombre)
    if os.path.exists(destino):
        with open(destino, "rb") as f:
            if f.read() == datos:
                return nombre
        nombre = f"{base}_{hashlib.sha1(datos).hexdigest()[:6]}.step"
    return nombre


@dataclass
class Modelo:
    """Un modelo listo para ubicar: triángulos y aristas en mm, en las coordenadas del archivo."""
    ruta: str
    malla: step_leer.Malla

    @property
    def triangulos(self) -> int:
        return len(self.malla.triangulos)


_memoria: Dict[str, Tuple[Tuple[float, int], Modelo]] = {}


def _firma(r: str) -> Tuple[float, int]:
    st = os.stat(r)
    return (st.st_mtime, st.st_size)


def _guardar_cache(r: str, m: step_leer.Malla, firma: Tuple[float, int]) -> None:
    largos = np.array([len(a) for a in m.aristas], dtype=np.int64)
    aristas = np.vstack(m.aristas) if m.aristas else np.zeros((0, 3))
    sol_ids = np.array([s for s, _m in m.solidos], dtype=np.int64)
    sol_m = np.array([mm for _s, mm in m.solidos]).reshape(-1, 4, 4)
    try:
        with open(r + ".malla.npz", "wb") as f:
            np.savez_compressed(f, version=VERSION_CACHE, firma=np.array(firma, dtype=float),
                                v=m.vertices.astype(np.float32), t=m.triangulos.astype(np.int32),
                                aristas=aristas.astype(np.float32), largos=largos, sol_ids=sol_ids, sol_m=sol_m,
                                escala=m.escala, avisos=np.array(m.avisos, dtype=object))
    except OSError:
        pass


def _leer_cache(r: str, firma: Tuple[float, int]) -> Optional[step_leer.Malla]:
    try:
        with np.load(r + ".malla.npz", allow_pickle=True) as z:
            if int(z["version"]) != VERSION_CACHE or tuple(z["firma"]) != tuple(float(x) for x in firma):
                return None
            largos = z["largos"].tolist()
            ar = z["aristas"].astype(float)
            aristas, i = [], 0
            for n in largos:
                aristas.append(ar[i:i + n])
                i += n
            return step_leer.Malla(z["v"].astype(float), z["t"].astype(np.int64), aristas,
                                   [str(a) for a in z["avisos"]],
                                   list(zip(z["sol_ids"].tolist(), list(z["sol_m"]))), float(z["escala"]))
    except (OSError, KeyError, ValueError):
        return None


def cargar(nombre: str) -> Modelo:
    """El modelo del archivo (de la memoria, de la copia guardada o leyendo el STEP)."""
    r = ruta(nombre)
    if not r or not os.path.exists(r):
        raise step_leer.ErrorStep(f"no está el archivo {os.path.basename(nombre) or '(sin nombre)'}")
    firma = _firma(r)
    guardado = _memoria.get(r)
    if guardado and guardado[0] == firma:
        return guardado[1]
    malla = _leer_cache(r, firma)
    if malla is None:
        ms = step_leer.leer(r)
        malla = ms.malla()
        if len(malla.triangulos) > MAX_TRIANGULOS:     # muy detallado: más grueso
            ms = step_leer.leer(r)
            lo, hi = malla.caja
            malla = ms.malla(tol_mm=float(np.linalg.norm(hi - lo)) / 80.0)
        _guardar_cache(r, malla, firma)
    mod = Modelo(r, malla)
    _memoria[r] = (firma, mod)
    return mod


def importar(origen: str, ref: str) -> Tuple[str, Modelo]:
    """Copia el .step a la carpeta de modelos y lo lee. Devuelve (nombre para el catálogo, modelo).
    Lanza ErrorStep si no se puede leer (y no deja la copia)."""
    with open(origen, "rb") as f:
        datos = f.read()
    os.makedirs(carpeta(), exist_ok=True)
    nombre = _nombre_libre(ref or os.path.splitext(os.path.basename(origen))[0], datos)
    destino = os.path.join(carpeta(), nombre)
    nuevo = not os.path.exists(destino)
    if nuevo:
        shutil.copyfile(origen, destino)
    try:
        return nombre, cargar(nombre)
    except (step_leer.ErrorStep, ValueError, IndexError, KeyError, TypeError, RecursionError) as e:
        if nuevo:
            for x in (destino, destino + ".malla.npz"):
                try:
                    os.remove(x)
                except OSError:
                    pass
        if isinstance(e, step_leer.ErrorStep):
            raise
        raise step_leer.ErrorStep(f"no se pudo leer el modelo ({e.__class__.__name__}: {e})") from e


# ---------------------------------------------------------------------------
# Orientación sobre la cara
# ---------------------------------------------------------------------------

def ejes_frente(frente: str) -> np.ndarray:
    """Matriz 3x3 cuyas filas son los ejes del modelo que van a lo ancho, a lo alto y hacia
    afuera de la cara (a, b, c)."""
    frente = frente if frente in FRENTES else "+Z"
    s = -1.0 if frente[0] == "-" else 1.0
    eje = {"X": 0, "Y": 1, "Z": 2}[frente[1]]
    afuera = np.zeros(3)
    afuera[eje] = s
    arriba = np.array([0.0, 1.0, 0.0]) if eje == 2 else np.array([0.0, 0.0, 1.0])
    ancho = np.cross(arriba, afuera)
    return np.array([ancho, arriba, afuera])


def orientacion(m: step_leer.Malla, frente: str = "+Z", adentro: float = 0.0) -> np.ndarray:
    """Matriz 4x4 de las coordenadas del modelo (mm) a las de la pieza puesta: centrada a lo
    ancho y a lo alto, apoyada en c = 0 (menos lo que entra en la placa)."""
    R = ejes_frente(frente)
    q = m.vertices @ R.T
    lo, hi = q.min(axis=0), q.max(axis=0)
    t = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2] - float(adentro or 0)])
    M = np.eye(4)
    M[:3, :3], M[:3, 3] = R, t
    return M


def medidas(m: step_leer.Malla, frente: str = "+Z") -> Tuple[float, float, float]:
    """(ancho, alto, fondo) de la pieza puesta, en mm."""
    q = m.vertices @ ejes_frente(frente).T
    d = q.max(axis=0) - q.min(axis=0)
    return float(d[0]), float(d[1]), float(d[2])


def del_articulo(datos: dict) -> Optional[Tuple[Modelo, np.ndarray, Tuple[float, float, float]]]:
    """(modelo, orientación, medidas) del modelo de un artículo, o None si no tiene o no se lee."""
    nombre = datos.get("modelo") if isinstance(datos, dict) else None
    if not nombre or not isinstance(nombre, str):
        return None
    mod = cargar(nombre)
    frente = str(datos.get("modelo_frente") or "+Z").upper()
    try:
        adentro = float(datos.get("modelo_adentro") or 0)
    except (TypeError, ValueError):
        adentro = 0.0
    return mod, orientacion(mod.malla, frente, adentro), medidas(mod.malla, frente)


def resumen(m: Modelo, frente: str = "+Z") -> str:
    a, b, c = medidas(m.malla, frente)
    return (f"{os.path.basename(m.ruta)}: {a:.1f} x {b:.1f} mm, {c:.1f} mm de alto, "
            f"{len(m.malla.solidos)} sólido(s), {m.triangulos} triángulos")


def avisos(m: Modelo) -> List[str]:
    return list(m.malla.avisos)
