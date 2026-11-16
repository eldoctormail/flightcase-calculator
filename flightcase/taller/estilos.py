"""Estilos de case: configuraciones listas para aplicar sobre las medidas del proyecto.

Un estilo cambia cómo se arma el case (orientación, tapas, accesos, bisagras, ruedas...)
y no toca las medidas interiores, el interior cargado ni los herrajes puestos a mano.
Los estilos incluidos están en resources/taller_estilos.json; los que guarda el usuario
van a su carpeta de datos (taller_estilos_propios.json).

Claves especiales de un estilo (empiezan con "_", no son parámetros del .scad):
- ``_base_ruedas: "auto"``: base de ruedas bajo el cuerpo, 10 mm más chica que el piso.
- ``_mitades: true``: reparte el alto interior total en cuerpo y tapa iguales.
- ``_acceso: fracción``: tapa de acceso lateral de esa fracción del alto del case.
- ``_tapa_baja: mm``: la tapa queda de ese alto interior y el resto pasa al cuerpo (el total no cambia).
- ``_guitarras: n``: n guitarras paradas entre tabiques de espuma, si el proyecto todavía
  no tiene equipos ni espumas.
- ``_cajones: mm``: llena el alto interior con cajones (bandejas con correderas) de ese paso,
  si el proyecto todavía no tiene cajones.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..paths import bundled_resource, user_resource

ARCHIVO_PROPIOS = "taller_estilos_propios.json"

# Lo que un estilo incluido vuelve a su valor por defecto antes de aplicarse, para que
# no queden restos del estilo anterior (por ejemplo, bisagras en un rack de dos tapas).
CLAVES_ESTILO = (
    "forma", "slam_caras", "slam_hojas", "slam_rack", "tapa_plana", "basemaker", "incl_rack_frente", "tabla_borde", "puertas", "puerta_lado", "incl_rieles", "pleg_base_esp", "pleg_base_material", "pleg_cierres_esquina",
    "tapas", "int_alto_tapa2", "orientacion", "descuento_entre",
    "acceso_lateral", "acceso_junta", "acceso_cierres_n", "acceso_tipo",
    "paredes_enteras", "paredes_enteras_cuerpo", "extremos_cubren",
    "manijas", "manijas_en", "manijas_n", "manija_sep", "manija_pos",
    "cierres_laterales", "cierres_frente_n", "cierres_lateral_n",
    "ruedas", "rueda_frenos", "rueda_fijas", "base_ruedas", "base_suelta", "cazoletas", "encastres",
    "pies", "ref_pie", "bisagras", "ref_bisagra", "topes", "ref_tope", "refuerzos", "sistema",
)

# Lo que un estilo propio no guarda: medidas, interior, herrajes a mano y la vista.
NO_GUARDAR = {
    "int_ancho", "int_prof", "int_alto_cuerpo", "int_alto_tapa", "incl_alto_frente", "cantidad_cases",
    "piezas_extra", "bandejas", "equipos", "espumas", "cajones", "rack_u", "rack_equipos",
    "herrajes_manuales", "etiquetas",
    "parte", "panel_id", "rect_w", "rect_h", "abrir_tapa", "angulo_tapa", "mostrar_perfiles",
    "explotar", "paso", "vista_parte", "resaltar_que", "resaltar_cubierta", "cubierta_abierta",
    "color_resalte",
}

BASE_RETIRO = 10.0   # la base de ruedas queda 5 mm adentro del piso de cada lado
BASE_ESPESOR = 18


@dataclass
class Estilo:
    id: str
    nombre: str
    descripcion: str
    params: Dict[str, Any] = field(default_factory=dict)
    propio: bool = False


def estilos_incluidos() -> List[Estilo]:
    filas = json.loads(bundled_resource("taller_estilos.json").read_text(encoding="utf-8"))
    return [Estilo(f["id"], f["nombre"], f.get("descripcion", ""), dict(f.get("params", {}))) for f in filas]


def estilos_propios() -> List[Estilo]:
    ruta = user_resource(ARCHIVO_PROPIOS)
    if not ruta.is_file():
        return []
    try:
        filas = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [Estilo(f["id"], f["nombre"], f.get("descripcion", ""), dict(f.get("params", {})), True)
            for f in filas if isinstance(f, dict) and "id" in f and "nombre" in f]


def todos() -> List[Estilo]:
    return estilos_incluidos() + estilos_propios()


def _alto_case(p: Dict[str, Any]) -> float:
    """Alto interior del lado donde va la tapa de acceso (depende de la orientación)."""
    o = p.get("orientacion")
    if o == "frontal":
        return float(p["int_prof"])
    if o == "horizontal":
        return float(p["int_ancho"])
    return float(p["int_alto_cuerpo"])


def base_ruedas_auto(p: Dict[str, Any]) -> List[float]:
    """Base de ruedas bajo el cuerpo: la planta exterior del cuerpo menos BASE_RETIRO en cada sentido.

    Medidas en el orden de base_ruedas: a lo ancho y a lo alto del plano del piso.
    """
    from .modelo import calcular

    sin_base = dict(p)
    sin_base["base_ruedas"] = []
    res = calcular(sin_base)
    v = res.valores
    o = p.get("orientacion")
    if o == "vertical":
        ancho, largo = v["ext_ancho"], v["ext_prof"]
    else:   # parado o acostado: el piso es una pared del cuerpo y la base cubre el largo del cuerpo
        ancho = v["ext_prof"] if o == "horizontal" else v["ext_ancho"]
        largo = float(res.info["tipo"][3])
    return [round(ancho - BASE_RETIRO, 1), round(largo - BASE_RETIRO, 1), BASE_ESPESOR]


def _guitarras(p: Dict[str, Any], n: int) -> Tuple[List[list], List[list]]:
    """Guitarras paradas una al lado de la otra, separadas por tabiques de espuma de todo el alto y el fondo.
    Las medidas de cada guitarra salen del case (ancho repartido, fondo y alto del cuerpo): se ajustan después
    en la tabla de equipos."""
    W = float(p["int_ancho"])
    D = float(p["int_alto_cuerpo"]) if p.get("orientacion") == "frontal" else float(p["int_prof"])
    H = _alto_case(p)
    sep = 30.0                                       # tabique de espuma entre guitarras y contra los costados
    hueco = (W - (n + 1) * sep) / n
    gw = max(20.0, hueco - 10)
    espumas = [[sep, 0, 0, round(i * (hueco + sep), 1)] for i in range(n + 1)]
    equipos = [[f"Guitarra {i + 1}", round(gw, 1), round(max(50.0, D - 20), 1), round(max(50.0, H - 20), 1), 4,
                round(sep + i * (hueco + sep) + 5, 1)] for i in range(n)]
    return equipos, espumas


def aplicar(params: Dict[str, Any], estilo: Estilo, defectos: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve los parámetros con el estilo aplicado (no modifica los recibidos)."""
    nuevo = dict(params)
    claves = [k for k in defectos if k not in NO_GUARDAR] if estilo.propio else CLAVES_ESTILO
    for k in claves:
        if k in defectos:
            nuevo[k] = defectos[k]
    nuevo.update({k: v for k, v in estilo.params.items() if not k.startswith("_")})

    if estilo.params.get("_mitades"):
        total = float(nuevo["int_alto_cuerpo"]) + float(nuevo["int_alto_tapa"])
        mitad = round(total / 2)
        nuevo["int_alto_cuerpo"], nuevo["int_alto_tapa"] = mitad, total - mitad
    baja = estilo.params.get("_tapa_baja")
    if baja:
        total = float(nuevo["int_alto_cuerpo"]) + float(nuevo["int_alto_tapa"])
        tapa = min(float(baja), total / 3)
        nuevo["int_alto_cuerpo"], nuevo["int_alto_tapa"] = round(total - tapa), round(tapa)
    paso = estilo.params.get("_cajones")
    if paso and not nuevo.get("cajones"):
        n = max(1, int(_alto_case(nuevo) // float(paso)))
        nuevo["cajones"] = [[float(paso) - 4, i * float(paso)] for i in range(n)]
    n_g = int(estilo.params.get("_guitarras", 0) or 0)
    if n_g and not nuevo.get("equipos") and not nuevo.get("espumas"):
        nuevo["equipos"], nuevo["espumas"] = _guitarras(nuevo, n_g)
    frac = estilo.params.get("_acceso")
    if frac:
        nuevo["acceso_lateral"] = round(float(frac) * _alto_case(nuevo))
    if estilo.params.get("_base_ruedas") == "auto":
        nuevo["base_ruedas"] = base_ruedas_auto(nuevo)
    return nuevo


def _a_id(nombre: str) -> str:
    limpio = "".join(c.lower() if c.isalnum() else "_" for c in nombre).strip("_")
    return "propio_" + (limpio or "estilo")


def guardar_propio(nombre: str, params: Dict[str, Any], defectos: Dict[str, Any],
                   descripcion: str = "") -> Estilo:
    """Guarda (o reemplaza, si ya hay uno con ese nombre) un estilo con lo que difiere de los valores por defecto."""
    valores = {k: v for k, v in params.items()
               if k in defectos and k not in NO_GUARDAR and not k.startswith("_") and v != defectos[k]}
    estilo = Estilo(_a_id(nombre), nombre.strip(), descripcion or "Estilo guardado por vos.", valores, True)
    filas = [e for e in estilos_propios() if e.id != estilo.id]
    filas.append(estilo)
    _escribir_propios(filas)
    return estilo


def borrar_propio(id_estilo: str) -> bool:
    filas = estilos_propios()
    quedan = [e for e in filas if e.id != id_estilo]
    if len(quedan) == len(filas):
        return False
    _escribir_propios(quedan)
    return True


def _escribir_propios(filas: List[Estilo]) -> None:
    ruta = user_resource(ARCHIVO_PROPIOS)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = [{"id": e.id, "nombre": e.nombre, "descripcion": e.descripcion, "params": e.params} for e in filas]
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def buscar(id_estilo: str) -> Optional[Estilo]:
    return next((e for e in todos() if e.id == id_estilo), None)
