"""Configuraciones guardadas por sección: los valores de una sola sección del Taller
(materiales, ruedas, espuma, cierres…) con un nombre, para cargarlos en otro case.

A diferencia de un estilo, que guarda todo el armado junto, una configuración guarda
sólo los parámetros de una sección y al cargarla no toca nada más del case.
Van a la carpeta de datos del usuario (taller_configuraciones.json).

Las medidas nunca se guardan. Las listas de contenido del case (equipos, cajones,
equipos del rack, bandejas, piezas extra…) sólo si se pide al guardar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..paths import bundled_resource, user_resource

ARCHIVO = "taller_configuraciones.json"

# Medidas del case: nunca forman parte de una configuración.
MEDIDAS = {"int_ancho", "int_prof", "int_alto_cuerpo", "int_alto_tapa", "int_alto_tapa2",
           "incl_alto_frente", "cantidad_cases"}

# Lo que se cargó en este case en particular: se guarda sólo si se pide.
CONTENIDO = {"equipos", "espumas", "cajones", "rack_u", "rack_equipos", "bandejas", "piezas_extra"}


@dataclass
class Configuracion:
    id: str
    nombre: str
    seccion: str
    params: Dict[str, Any] = field(default_factory=dict)


def secciones() -> Dict[str, List[str]]:
    """Título de cada sección que se puede guardar → nombres de sus parámetros (sin las medidas)."""
    filas = json.loads(bundled_resource("taller_parametros_info.json").read_text(encoding="utf-8"))
    res: Dict[str, List[str]] = {}
    for sec in filas[1:]:            # la primera es la de medidas interiores
        nombres = [p["nombre"] for p in sec["parametros"] if p["nombre"] not in MEDIDAS]
        if nombres:
            res[sec["seccion"]] = nombres
    return res


def claves_de(seccion: str, con_contenido: bool = False) -> List[str]:
    return [k for k in secciones().get(seccion, []) if con_contenido or k not in CONTENIDO]


def tiene_contenido(seccion: str, params: Dict[str, Any]) -> bool:
    """Si la sección tiene listas de contenido cargadas en este case (para ofrecer incluirlas)."""
    return any(params.get(k) for k in secciones().get(seccion, []) if k in CONTENIDO)


def todas() -> List[Configuracion]:
    ruta = user_resource(ARCHIVO)
    if not ruta.is_file():
        return []
    try:
        filas = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [Configuracion(f["id"], f["nombre"], f["seccion"], dict(f.get("params", {})))
            for f in filas if isinstance(f, dict) and {"id", "nombre", "seccion"} <= set(f)]


def de_seccion(seccion: str) -> List[Configuracion]:
    return sorted((c for c in todas() if c.seccion == seccion), key=lambda c: c.nombre.lower())


def _a_id(seccion: str, nombre: str) -> str:
    def limpio(t: str) -> str:
        return "".join(c.lower() if c.isalnum() else "_" for c in t).strip("_")
    return f"{limpio(seccion) or 'seccion'}__{limpio(nombre) or 'config'}"


def guardar(nombre: str, seccion: str, params: Dict[str, Any], con_contenido: bool = False) -> Configuracion:
    """Guarda (o reemplaza, si ya hay una con ese nombre en la sección) los valores de la sección."""
    if seccion not in secciones():
        raise ValueError(f"No se puede guardar la sección «{seccion}».")
    valores = {k: params[k] for k in claves_de(seccion, con_contenido) if k in params}
    conf = Configuracion(_a_id(seccion, nombre), nombre.strip(), seccion, valores)
    filas = [c for c in todas() if c.id != conf.id]
    filas.append(conf)
    _escribir(filas)
    return conf


def aplicar(params: Dict[str, Any], conf: Configuracion, defectos: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve los parámetros con la configuración cargada (no modifica los recibidos).

    Sólo cambian los parámetros de esa sección que la configuración trae; los que se
    agregaron a la app después de guardarla quedan como estaban."""
    validos = set(secciones().get(conf.seccion, [])) - MEDIDAS
    nuevo = dict(params)
    nuevo.update({k: v for k, v in conf.params.items() if k in validos and k in defectos})
    return nuevo


def borrar(id_conf: str) -> bool:
    filas = todas()
    quedan = [c for c in filas if c.id != id_conf]
    if len(quedan) == len(filas):
        return False
    _escribir(quedan)
    return True


def buscar(id_conf: str) -> Optional[Configuracion]:
    return next((c for c in todas() if c.id == id_conf), None)


def _escribir(filas: List[Configuracion]) -> None:
    ruta = user_resource(ARCHIVO)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = [{"id": c.id, "nombre": c.nombre, "seccion": c.seccion, "params": c.params} for c in filas]
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
