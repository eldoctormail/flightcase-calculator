"""Familias de estilos de case para la pantalla de inicio, y la miniatura de cada estilo.

Las miniaturas de los estilos incluidos vienen hechas (resources/estilos/<id>.png, se rehacen
con ``python tools/generar_miniaturas_estilos.py``). Las de los estilos propios se dibujan la
primera vez y quedan en la carpeta de datos del usuario.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..paths import bundled_resource, user_resource
from .estilos import Estilo

TAM = "480,360"
CAMARA = "0,0,0,62,0,30,0"
NEGRO = {"base": "#26282d", "wall": "#26282d", "lid": "#26282d"}   # como la placa negra de la mayoría

FAMILIAS = (
    ("estandar", "Estándar", "Baúles de gira con tapa suelta, baja, 50/50 o abisagrada, plegables y cases de mano.",
     ("baul_tapa_suelta", "baul_tapa_baja", "baul_50_50", "baul_bisagras", "baul_base_ruedas", "baul_plegable",
      "case_mano_pies", "tapa_piano", "hibrido_liviano")),
    ("broadcast", "Broadcast", "Cases de producción parados, con rieles de rack y acceso por arriba a los cables.",
     ("broadcast_produccion", "broadcast_trasera_cerrada", "broadcast_trasera_cerrada_2")),
    ("clamshell", "Clamshell", "Dos mitades que se abren como un libro, hacia arriba o hacia los costados, "
     "o una tapa en cada extremo.", ("clamshell", "clamshell_izq_der", "dos_tapas_vertical", "acostado_dos_tapas")),
    ("frontal", "Apertura frontal", "Cases parados que se abren de frente: tapa adelante, puertas o bandejas.",
     ("apertura_frontal", "bandejas_euro")),
    ("racks", "Racks", "Racks 19\" medidos en unidades: tapa adelante, adelante y atrás, puertas, tapas de acceso, "
     "cubierta, inclinado para consola o funda abierta.",
     ("rack_una_tapa", "rack_dos_tapas", "rack_puertas", "rack_acceso_paneles", "rack_cubierta", "rack_inclinado",
      "funda_rack")),
    ("slam", "Tapas slam", "Tapas que cierran solas al bajarlas, con cierres slam embutidos.", ()),
    ("especiales", "Especiales", "Armados para un uso puntual.", ()),
)

# Nombre corto de cada estilo en los chips de su familia (sin repetir lo que ya dice la familia)
CORTOS = {
    "baul_tapa_suelta": "Baúl", "baul_tapa_baja": "Tapa baja", "baul_50_50": "50/50",
    "baul_bisagras": "Tapa abisagrada", "baul_base_ruedas": "Base de ruedas",
    "baul_plegable": "Plegable", "case_mano_pies": "De mano con pies", "tapa_piano": "Bisagra de piano",
    "hibrido_liviano": "Perfil híbrido",
    "broadcast_produccion": "De producción", "broadcast_trasera_cerrada": "Trasera cerrada",
    "broadcast_trasera_cerrada_2": "Trasera cerrada 2",
    "clamshell": "Clamshell", "clamshell_izq_der": "Izquierda/derecha", "dos_tapas_vertical": "Tapa arriba y abajo",
    "acostado_dos_tapas": "Acostado, tapas a los lados",
    "apertura_frontal": "Tapa adelante", "bandejas_euro": "Bandejas euro",
    "rack_una_tapa": "Tapa adelante", "rack_dos_tapas": "Adelante y atrás", "rack_puertas": "Con puertas",
    "funda_rack": "Funda (sleeve)", "rack_acceso_paneles": "Tapas de acceso", "rack_cubierta": "Cubierta entera",
    "rack_inclinado": "Para mezcladora",
}


def nombre_corto(estilo: Estilo) -> str:
    return CORTOS.get(estilo.id, estilo.nombre)


@dataclass
class Familia:
    clave: str
    nombre: str
    descripcion: str
    estilos: List[Estilo] = field(default_factory=list)


def agrupar(estilos: List[Estilo]) -> List[Familia]:
    """Las familias con sus estilos en orden. Un estilo incluido que no está en ninguna va a
    «Otros»; los propios, a «Mis estilos»."""
    por_id = {e.id: e for e in estilos}
    usados = set()
    out = []
    for clave, nombre, desc, ids in FAMILIAS:
        f = Familia(clave, nombre, desc, [por_id[i] for i in ids if i in por_id])
        usados.update(e.id for e in f.estilos)
        if f.estilos:
            out.append(f)
    otros = [e for e in estilos if e.id not in usados and not e.propio]
    if otros:
        out.append(Familia("otros", "Otros", "Más armados del taller.", otros))
    propios = [e for e in estilos if e.propio]
    if propios:
        out.append(Familia("propios", "Mis estilos", "Los armados que guardaste con «Guardar como estilo».", propios))
    return out


def familia_de(estilo: Estilo, familias: List[Familia]) -> Optional[Familia]:
    return next((f for f in familias if any(e.id == estilo.id for e in f.estilos)), None)


def _clave_propio(estilo: Estilo) -> str:
    texto = json.dumps(estilo.params, sort_keys=True, default=str)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]


def ruta_miniatura(estilo: Estilo) -> Path:
    if not estilo.propio:
        return bundled_resource(f"estilos/{estilo.id}.png")
    return user_resource(f"miniaturas_estilos/{estilo.id}-{_clave_propio(estilo)}.png")


def miniatura(estilo: Estilo) -> Optional[str]:
    """La miniatura si ya está hecha (sin dibujar nada)."""
    ruta = ruta_miniatura(estilo)
    return str(ruta) if ruta.is_file() else None


def dibujar_miniatura(estilo: Estilo, ruta: Optional[Path] = None) -> Optional[str]:
    """Dibuja el estilo con las medidas por defecto, cerrado y en placa negra. Se puede llamar
    desde un hilo aparte."""
    from .estilos import aplicar
    from .geometria import malla_3d
    from .modelo import calcular, parametros_por_defecto
    from .render import renderizar
    ruta = Path(ruta or ruta_miniatura(estilo))
    try:
        d = parametros_por_defecto()
        params = aplicar(dict(d), estilo, d)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_name(ruta.stem + f".{os.getpid()}.{id(params)}.png")
        if renderizar(malla_3d(calcular(params)), str(tmp), CAMARA, TAM, NEGRO, transparente=True):
            os.replace(tmp, ruta)
            return str(ruta)
    except Exception:
        pass
    return None
