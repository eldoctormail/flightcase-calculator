"""Lista de proyectos guardados (.scad): medidas, fecha, miniatura, duplicar y renombrar.

Las medidas y las miniaturas se guardan en la carpeta de datos del usuario y se
recalculan solo cuando cambia la fecha del archivo, así abrir la lista es rápido
aunque haya muchos cases.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..paths import user_data_dir, user_resource

INDICE = "proyectos.json"
CARPETA_MINIATURAS = "miniaturas"
TAM_MINIATURA = "360,270"
CAMARA_MINIATURA = "0,0,0,62,0,30,0"
PROFUNDIDAD_BUSQUEDA = 2          # la carpeta de proyectos y dos niveles de subcarpetas


@dataclass
class InfoProyecto:
    ruta: str
    fecha: float                              # última modificación (epoch)
    ancho: Optional[float] = None             # medidas exteriores en mm
    prof: Optional[float] = None
    alto: Optional[float] = None
    material: str = ""                        # placa de los paneles
    error: str = ""                           # si no se pudo leer o calcular

    @property
    def nombre(self) -> str:
        return os.path.splitext(os.path.basename(self.ruta))[0]

    @property
    def carpeta(self) -> str:
        return os.path.dirname(self.ruta)

    def medidas(self) -> str:
        if self.ancho is None:
            return ""
        return f"{self.ancho:.0f} × {self.prof:.0f} × {self.alto:.0f} mm"

    def coincide(self, texto: str) -> bool:
        """Búsqueda sin distinguir mayúsculas ni acentos, por nombre, carpeta, material o medidas."""
        palabras = _normalizar(texto).split()
        donde = _normalizar(" ".join((self.nombre, os.path.basename(self.carpeta), self.material, self.medidas())))
        return all(p in donde for p in palabras)


def _normalizar(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# ------------------------------------------------------------------ índice
def _leer_indice() -> Dict[str, dict]:
    try:
        datos = json.loads(user_resource(INDICE).read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_indice(indice: Dict[str, dict]) -> None:
    ruta = user_resource(INDICE)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, ruta)
    except OSError:
        pass


def _clave(ruta: str) -> str:
    return os.path.normcase(os.path.abspath(ruta))


def _calcular_info(ruta: str, fecha: float) -> InfoProyecto:
    from .modelo import calcular
    from .scad import leer_proyecto
    info = InfoProyecto(ruta=ruta, fecha=fecha)
    try:
        params = leer_proyecto(ruta)
        params["_carpeta"] = os.path.dirname(os.path.abspath(ruta))
        v = calcular(params).valores
        info.ancho, info.prof, info.alto = (float(v["ext_ancho"]), float(v["ext_prof"]), float(v["ext_alto"]))
        info.material = str(v.get("placa_material", "") or "")
    except Exception as e:                       # un .scad que no es del taller o está roto
        info.error = str(e) or type(e).__name__
    return info


def info_proyecto(ruta: str, indice: Optional[Dict[str, dict]] = None) -> Optional[InfoProyecto]:
    """Datos de un proyecto, del índice si el archivo no cambió. None si ya no existe."""
    try:
        fecha = os.path.getmtime(ruta)
    except OSError:
        return None
    propio = indice is None
    indice = _leer_indice() if propio else indice
    k = _clave(ruta)
    d = indice.get(k)
    if isinstance(d, dict) and d.get("fecha") == fecha:
        info = InfoProyecto(ruta=os.path.abspath(ruta), fecha=fecha, ancho=d.get("ancho"), prof=d.get("prof"),
                            alto=d.get("alto"), material=d.get("material", ""),
                            error=d.get("error", ""))
    else:
        info = _calcular_info(os.path.abspath(ruta), fecha)
        indice[k] = {"fecha": fecha, "ancho": info.ancho, "prof": info.prof, "alto": info.alto,
                     "material": info.material, "error": info.error}
        if propio:
            _guardar_indice(indice)
    return info


def buscar_scad(carpeta: str, profundidad: int = PROFUNDIDAD_BUSQUEDA) -> List[str]:
    """Los .scad de la carpeta y sus subcarpetas (sin entrar en salidas del taller ni carpetas ocultas)."""
    encontrados: List[str] = []
    if not carpeta or not os.path.isdir(carpeta):
        return encontrados
    base = os.path.abspath(carpeta).rstrip(os.sep).count(os.sep)
    for raiz, dirs, archivos in os.walk(carpeta):
        nivel = os.path.abspath(raiz).rstrip(os.sep).count(os.sep) - base
        dirs[:] = [d for d in dirs if not d.startswith((".", "salida_", "flightcase_gen", "__"))]
        if nivel >= profundidad:
            dirs[:] = []
        encontrados += [os.path.join(raiz, a) for a in archivos if a.lower().endswith(".scad")]
    return encontrados


def listar(carpetas: Iterable[str], recientes: Iterable[str] = ()) -> List[InfoProyecto]:
    """Proyectos de las carpetas más los recientes, sin repetir, del más nuevo al más viejo.
    Los archivos de la librería de OpenSCAD (sin `flightcase();`) no se listan."""
    rutas: Dict[str, str] = {}
    for r in recientes:
        if os.path.isfile(r):
            rutas.setdefault(_clave(r), os.path.abspath(r))
    for c in carpetas:
        for r in buscar_scad(c):
            if _es_proyecto(r):
                rutas.setdefault(_clave(r), os.path.abspath(r))
    indice = _leer_indice()
    antes = dict(indice)
    infos = [i for i in (info_proyecto(r, indice) for r in rutas.values()) if i is not None]
    if indice != antes:
        _guardar_indice(indice)
    infos.sort(key=lambda i: i.fecha, reverse=True)
    return infos


def _es_proyecto(ruta: str) -> bool:
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            texto = f.read(200_000)
    except OSError:
        return False
    return "flightcase(" in texto and "module flightcase" not in texto


# -------------------------------------------------------------- miniaturas
def ruta_miniatura(ruta: str) -> Path:
    h = hashlib.sha1(_clave(ruta).encode("utf-8")).hexdigest()[:16]
    return user_data_dir() / CARPETA_MINIATURAS / f"{h}.png"


def miniatura_al_dia(ruta: str) -> Optional[str]:
    """La miniatura si existe y es más nueva que el proyecto."""
    png = ruta_miniatura(ruta)
    try:
        if png.stat().st_mtime >= os.path.getmtime(ruta):
            return str(png)
    except OSError:
        pass
    return None


def generar_miniatura(ruta: str) -> Optional[str]:
    """Dibuja el case cerrado en perspectiva (como el render del instructivo, más chico).
    Se puede llamar desde un hilo aparte."""
    from .geometria import malla_3d
    from .modelo import calcular
    from .render import renderizar
    from .scad import leer_proyecto
    png = ruta_miniatura(ruta)
    try:
        params = leer_proyecto(ruta)
        params["_carpeta"] = os.path.dirname(os.path.abspath(ruta))
        png.parent.mkdir(parents=True, exist_ok=True)
        tmp = png.with_name(png.stem + f".{os.getpid()}.{id(params)}.png")
        if renderizar(malla_3d(calcular(params)), str(tmp), CAMARA_MINIATURA, TAM_MINIATURA):
            os.replace(tmp, png)
            return str(png)
    except Exception:
        pass
    return None


def olvidar(ruta: str) -> None:
    """Saca un proyecto del índice y borra su miniatura (al borrarlo o renombrarlo)."""
    indice = _leer_indice()
    if indice.pop(_clave(ruta), None) is not None:
        _guardar_indice(indice)
    try:
        ruta_miniatura(ruta).unlink()
    except OSError:
        pass


def _mover_cache(vieja: str, nueva: str) -> None:
    indice = _leer_indice()
    d = indice.pop(_clave(vieja), None)
    if d is not None:
        try:
            d["fecha"] = os.path.getmtime(nueva)
            indice[_clave(nueva)] = d
        except OSError:
            pass
        _guardar_indice(indice)
    try:
        os.replace(ruta_miniatura(vieja), ruta_miniatura(nueva))
    except OSError:
        pass


# ------------------------------------------------- duplicar / renombrar
_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def nombre_valido(nombre: str) -> str:
    """El nombre sin extensión y sin caracteres que Windows o macOS no aceptan."""
    nombre = nombre.strip()
    if nombre.lower().endswith(".scad"):
        nombre = nombre[:-5].strip()
    nombre = _INVALIDOS.sub("-", nombre).strip(". ")
    if not nombre:
        raise ValueError("El nombre no puede quedar vacío.")
    return nombre


def _con_titulo(texto: str, titulo: str) -> str:
    """Cambia el comentario del título (primera línea) que escribe escribir_proyecto."""
    lineas = texto.split("\n")
    if lineas and lineas[0].startswith("// ") and len(lineas) > 1 and "LBD Flightcase Maker" in lineas[1]:
        lineas[0] = f"// {titulo}"
        return "\n".join(lineas)
    return texto


def nombre_libre(carpeta: str, base: str) -> str:
    """`base.scad`, o `base 2.scad`, `base 3.scad`... el primero que no exista."""
    ruta = os.path.join(carpeta, f"{base}.scad")
    n = 2
    while os.path.exists(ruta):
        ruta = os.path.join(carpeta, f"{base} {n}.scad")
        n += 1
    return ruta


def duplicar(ruta: str, nombre: Optional[str] = None) -> str:
    """Copia el proyecto en la misma carpeta (los logos y contornos con ruta relativa siguen
    funcionando). Devuelve la ruta nueva."""
    carpeta = os.path.dirname(os.path.abspath(ruta))
    base = nombre_valido(nombre) if nombre else f"{os.path.splitext(os.path.basename(ruta))[0]} (copia)"
    nueva = nombre_libre(carpeta, base)
    texto = Path(ruta).read_text(encoding="utf-8")
    Path(nueva).write_text(_con_titulo(texto, os.path.splitext(os.path.basename(nueva))[0]), encoding="utf-8")
    return nueva


def renombrar(ruta: str, nombre: str) -> str:
    """Cambia el nombre del archivo (en la misma carpeta). Devuelve la ruta nueva."""
    carpeta = os.path.dirname(os.path.abspath(ruta))
    nuevo = nombre_valido(nombre)
    nueva = os.path.join(carpeta, f"{nuevo}.scad")
    if os.path.abspath(nueva) == os.path.abspath(ruta):
        return os.path.abspath(ruta)
    solo_mayusculas = os.path.normcase(nueva) == os.path.normcase(os.path.abspath(ruta))
    if os.path.exists(nueva) and not solo_mayusculas:
        raise FileExistsError(f"Ya hay un proyecto llamado «{nuevo}» en esa carpeta.")
    texto = Path(ruta).read_text(encoding="utf-8")
    os.replace(ruta, nueva)
    nuevo_texto = _con_titulo(texto, nuevo)
    if nuevo_texto != texto:
        Path(nueva).write_text(nuevo_texto, encoding="utf-8")
    _mover_cache(ruta, nueva)
    from . import versiones
    try:
        versiones.mover(ruta, nueva)        # las versiones anteriores siguen al case
    except OSError:
        pass
    return nueva
