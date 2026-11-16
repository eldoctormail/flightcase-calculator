"""Peso real del case: placas, perfiles, herrajes, espuma y equipos.

Cada cosa toma el peso del catálogo cuando el artículo lo tiene cargado:

- placas: ``densidad`` (kg/m³) o ``peso_hoja`` (kg de la hoja entera);
- perfiles: ``peso_m`` (gramos por metro);
- herrajes y accesorios: ``peso`` (gramos por unidad);
- espumas: ``densidad`` (kg/m³).

Lo que no tiene dato en el catálogo se estima (aluminio por la sección del ángulo, madera por
el tipo de placa, herrajes con valores típicos) y queda marcado «estimado», para que se sepa qué
conviene pesar y cargar. Los paneles se pesan con su medida real menos los calados que la
atraviesan. Los equipos pesan lo que se cargó en el interior.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ALUMINIO = 2.70        # g/cm³ = g por mm² de sección y metro de largo

# Densidad (kg/m³) por palabra del material o del tipo de placa. Valores típicos.
DENSIDADES_PLACA: List[Tuple[str, float]] = [
    ("alveolar", 450), ("polipropileno", 900), ("pp", 900), ("mdf", 750), ("fibrofácil", 750),
    ("fenólico", 700), ("fenolico", 700), ("fenol", 700), ("abedul", 680), ("birch", 680), ("multilaminado", 650), ("terciado", 600),
    ("contrachapado", 600), ("álamo", 450), ("alamo", 450), ("poplar", 450), ("pino", 500),
    ("osb", 620), ("aglomerado", 650), ("aluminio", 2700), ("acrílico", 1190), ("acrilico", 1190),
    ("policarbonato", 1200),
]

# Perfiles sin ángulo de catálogo: gramos por metro típicos.
PERFIL_GM = {"hibrido": 650.0, "tapa_m": 380.0, "tapa_h": 330.0, "angulo": 240.0}

# Herrajes sin peso en el catálogo: gramos típicos por unidad. Se busca por categoría del
# artículo o, si no hay ref, por palabras del nombre (en este orden).
HERRAJE_G_CATEGORIA = {
    "esquinero": 120.0, "escuadra": 30.0, "cierre": 300.0, "bisagra": 90.0, "tope": 60.0,
    "manija": 350.0, "cazoleta": 450.0, "plato": 250.0, "pie": 25.0, "remache": 1.2,
    "rueda_otra": 1000.0,
}
HERRAJE_G_NOMBRE: List[Tuple[str, float]] = [
    ("remache", 1.2), ("bulón", 25.0), ("bulon", 25.0), ("tornillo", 3.0), ("tuerca", 2.0), ("arandela", 1.0),
    ("esquinero bola", 140.0), ("esquinero", 90.0), ("cantonera", 90.0),
    ("cierre mariposa", 350.0), ("mariposa", 350.0), ("cierre", 200.0),
    ("bisagra", 90.0), ("tope", 60.0), ("compás", 60.0),
    ("manija embutida", 450.0), ("manija", 250.0), ("asa", 250.0), ("tirador", 80.0),
    ("cazoleta", 450.0), ("plato", 250.0), ("pie", 25.0), ("escuadra", 30.0),
    ("corredera", 900.0), ("riel", 700.0), ("perfil de rack", 700.0), ("rueda", 1200.0),
]


@dataclass
class LineaPeso:
    parte: str            # Placas, Perfiles, Herrajes, Espuma, Equipos
    nombre: str
    cantidad: float
    unidad: str           # "u", "m", "m²"
    unitario: float       # kg por unidad
    total: float          # kg
    origen: str           # "catálogo", "estimado" o "cargado"
    detalle: str = ""


@dataclass
class PesoCase:
    lineas: List[LineaPeso] = field(default_factory=list)
    partes: Dict[str, float] = field(default_factory=dict)
    vacio: float = 0.0           # el case solo (sin equipos)
    total: float = 0.0           # con equipos
    estimado: float = 0.0        # kg que salen de valores estimados
    sin_dato: List[str] = field(default_factory=list)   # refs o piezas a pesar

    def resumen(self) -> str:
        txt = f"{_kg(self.vacio)} kg vacío"
        if self.total > self.vacio + 0.005:
            txt += f", {_kg(self.total)} kg con equipos"
        return txt


PARTES = ("Placas", "Perfiles", "Herrajes", "Espuma", "Equipos")


def _kg(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def densidad_por_nombre(texto: str) -> Optional[float]:
    t = (texto or "").lower()
    for clave, d in DENSIDADES_PLACA:
        if re.search(r"(?<![a-zá-ú])" + re.escape(clave), t):
            return d
    return None


def densidad_placa(cat, ref: str, material: str, defecto: float) -> Tuple[float, str]:
    """(kg/m³, origen) de una placa: la del catálogo, la del tipo de material o `defecto`."""
    if cat is not None and cat.existe(ref):
        d = _num(cat.dato(ref, "densidad", None))
        if d:
            return d, "catálogo"
        ph = _num(cat.dato(ref, "peso_hoja", None))
        L, A, e = (_num(cat.dato(ref, k, None)) for k in ("largo", "ancho", "esp"))
        if ph and L and A and e:
            return ph / (L * A * e) * 1e9, "catálogo"
        por_tipo = densidad_por_nombre(str(cat.dato(ref, "tipo", "")) + " " + cat.nombre(ref))
        if por_tipo:
            return por_tipo, "estimado"
    return densidad_por_nombre(material) or defecto, "estimado"


_ANGULO = re.compile(r"(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)")


def gramos_metro_perfil(cat, ref: str, nombre: str) -> Tuple[float, str]:
    """(g/m, origen) de un perfil."""
    categoria = cat.categoria(ref) if cat is not None and cat.existe(ref) else ""
    if categoria:
        g = _num(cat.dato(ref, "peso_m", None))
        if g:
            return g, "catálogo"
        if categoria == "angulo":
            ala, e = _num(cat.dato(ref, "ala", None)), _num(cat.dato(ref, "esp", None))
            if ala and e:
                return (2 * ala - e) * e * ALUMINIO, "estimado"
    n = (nombre or "").lower()
    m = _ANGULO.search(n.replace(",", "."))
    if m and ("ángulo" in n or "angulo" in n or not categoria):
        a, b, e = (float(x) for x in m.groups())
        return (a + b - e) * e * ALUMINIO, "estimado"
    if not categoria:
        if "híbrido" in n or "hibrido" in n:
            categoria = "hibrido"
        elif "macho" in n:
            categoria = "tapa_m"
        elif "hembra" in n:
            categoria = "tapa_h"
        else:
            categoria = "angulo"
    return PERFIL_GM.get(categoria, PERFIL_GM["angulo"]), "estimado"


def gramos_herraje(cat, ref: str, nombre: str) -> Tuple[Optional[float], str]:
    """(g por unidad, origen) de un herraje; (None, "") si no hay cómo estimarlo."""
    categoria = cat.categoria(ref) if cat is not None and cat.existe(ref) else ""
    if categoria:
        g = _num(cat.dato(ref, "peso", None))
        if g:
            return g, "catálogo"
        if categoria == "rueda":
            d = _num(cat.dato(ref, "diametro", None)) or 100
            return 12.0 * d, "estimado"        # 100 mm ≈ 1,2 kg con la placa giratoria
        if categoria == "remache":
            d, l_ = _num(cat.dato(ref, "d", None)) or 4, _num(cat.dato(ref, "l", None)) or 12
            return round(0.0054 * d * d * l_, 2), "estimado"      # ≈ 1,2 g un 4x14 de aluminio
        if categoria == "manija":
            return (450.0 if cat.dato(ref, "tipo", "embutida") == "embutida" else 250.0), "estimado"
        if categoria == "cierre":
            return (350.0 if cat.dato(ref, "tipo", "superficie") == "embutido" else 200.0), "estimado"
        if categoria in HERRAJE_G_CATEGORIA:
            return HERRAJE_G_CATEGORIA[categoria], "estimado"
    n = (nombre or "").lower()
    m = re.search(r"rueda[^0-9]*(\d{2,3})(?:\s*mm|\b)", n)
    if m:
        return 12.0 * float(m.group(1)), "estimado"
    for clave, g in HERRAJE_G_NOMBRE:
        if clave in n:
            return g, "estimado"
    return None, ""


def _area_calado(c) -> float:
    if c.tipo.startswith("agujero"):
        return math.pi * (c.ancho / 2) * (c.alto / 2)
    r = min(max(c.radio or 0, 0), c.ancho / 2, c.alto / 2)
    return c.ancho * c.alto - (4 - math.pi) * r * r


def calcular(res, P: Dict[str, Any], cat) -> PesoCase:
    """Peso de un case (no del pedido entero) a partir del resultado del taller."""
    out = PesoCase()
    L = out.lineas
    v = res.valores
    P = P or {}
    defecto = float(P.get("densidad_placa", 650) or 650)
    ref_placa = str(P.get("ref_placa") or "")
    esp_general = float(v.get("placa_esp") or 9)
    mat_general = str(v.get("placa_material") or "")
    pmat = {m[0]: m for m in res.panelmat}

    # ---- placas: paneles (con su material) menos los calados que la atraviesan ----
    calado_area: Dict[str, float] = {}
    for c in res.calados:
        if "rebaje" in c.tipo:
            continue
        calado_area[c.panel] = calado_area.get(c.panel, 0.0) + _area_calado(c)
    grupos: Dict[Tuple[str, float, float, str], List[Any]] = {}
    for p in res.paneles:
        m = pmat.get(p.id)
        material, esp, ref = mat_general, esp_general, ref_placa
        if m:
            material = str(m[1] or material)
            esp = float(m[2] or esp)
            ref = str(m[5]) if len(m) > 5 and m[5] else ("" if material != mat_general else ref_placa)
        dens, origen = densidad_placa(cat, ref, material, defecto)
        bruta = p.ancho * p.alto
        if getattr(p, "contorno", None):      # trapecio del rack inclinado
            c = p.contorno
            bruta = abs(sum(c[i][0] * c[(i + 1) % len(c)][1] - c[(i + 1) % len(c)][0] * c[i][1]
                            for i in range(len(c)))) / 2
        area = max(bruta - calado_area.get(p.id, 0.0), 0.0) / 1e6
        clave = (material, esp, dens, origen)
        g = grupos.setdefault(clave, [0.0, 0])
        g[0] += area
        g[1] += 1
    for e in res.extras:
        try:
            nombre, a, b, esp, cant = str(e[0]), float(e[1]), float(e[2]), float(e[3]), float(e[4] or 1)
        except (TypeError, ValueError, IndexError):
            continue
        material = str(e[5]) if len(e) > 5 and e[5] else mat_general
        dens, origen = densidad_placa(cat, ref_placa if material == mat_general else "", material, defecto)
        clave = (material, esp, dens, origen)
        g = grupos.setdefault(clave, [0.0, 0])
        g[0] += a * b * cant / 1e6
        g[1] += int(cant)
    for (material, esp, dens, origen), (area, n) in grupos.items():
        kg_m2 = dens * esp / 1000
        nom = material if re.search(r"\b" + re.escape(_num_txt(esp)) + r"\s*mm", material.replace(".", ",")) else f"{material} ({_num_txt(esp)} mm)"
        L.append(LineaPeso("Placas", nom, round(area, 3), "m²", kg_m2,
                           area * kg_m2, origen, f"{n} pieza{'' if n == 1 else 's'}, {round(dens)} kg/m³"))

    # ---- perfiles ----
    por_perfil: Dict[Tuple[str, str], List[Any]] = {}
    for p in res.perfiles:
        k = (p.nombre, p.ref)
        por_perfil.setdefault(k, [0.0, 0])
        por_perfil[k][0] += p.largo * p.cantidad / 1000
        por_perfil[k][1] += p.cantidad
    for (nombre, ref), (metros, n) in por_perfil.items():
        gm, origen = gramos_metro_perfil(cat, ref, nombre)
        L.append(LineaPeso("Perfiles", nombre, round(metros, 3), "m", gm / 1000, metros * gm / 1000, origen,
                           f"{n} tramos, {round(gm)} g/m"))

    # ---- herrajes ----
    dens_forro = float(P.get("espuma_densidad", 30) or 30)
    for h in res.herrajes:
        if h.cantidad <= 0:
            continue
        es_espuma = (cat is not None and cat.categoria(h.ref) == "espuma") or h.nombre.lower().startswith("espuma")
        if es_espuma:      # forro de espuma de las paredes: va por m² y densidad, no por plancha
            esp = None
            if cat is not None and cat.existe(h.ref):
                esp = _num(cat.dato(h.ref, "esp", None))
            if esp is None:
                m = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", h.nombre)
                esp = float(m.group(1).replace(",", ".")) if m else float(P.get("espuma_esp", 0) or 0)
            m = re.search(r"para\s+(\d+(?:[.,]\d+)?)\s*m²", h.detalle or "")
            area = float(m.group(1).replace(",", ".")) if m else h.cantidad * 2.0
            dens, origen = dens_forro, "estimado"
            if cat is not None and cat.existe(h.ref) and _num(cat.dato(h.ref, "densidad", None)):
                dens, origen = float(cat.dato(h.ref, "densidad", 0)), "catálogo"
            kg_m2 = dens * (esp or 0) / 1000
            L.append(LineaPeso("Espuma", h.nombre, round(area, 3), "m²", kg_m2, area * kg_m2, origen,
                               f"forro de {_num_txt(esp or 0)} mm, {round(dens)} kg/m³"))
            continue
        g, origen = gramos_herraje(cat, h.ref, h.nombre)
        if g is None:
            out.sin_dato.append(h.ref or h.nombre)
            L.append(LineaPeso("Herrajes", h.nombre, h.cantidad, "u", 0.0, 0.0, "sin dato", h.ref))
            continue
        L.append(LineaPeso("Herrajes", h.nombre, h.cantidad, "u", g / 1000, h.cantidad * g / 1000, origen,
                           h.ref))

    # ---- interior: espuma y equipos ----
    interior = v.get("interiores")
    if interior is not None:
        pi = getattr(interior, "peso", {}) or {}
        if pi.get("espuma"):
            dens = float(P.get("espuma_densidad", 30) or 0)
            ref_e = str(P.get("ref_espuma_bloques") or "")
            origen = "estimado"
            if cat is not None and cat.existe(ref_e) and _num(cat.dato(ref_e, "densidad", None)):
                dens, origen = float(cat.dato(ref_e, "densidad", 0)), "catálogo"
            L.append(LineaPeso("Espuma", "Bloques de espuma del interior", 1, "u", pi["espuma"],
                               pi["espuma"], origen, f"{round(dens)} kg/m³" if dens else ""))
        eq = 0.0
        for e in P.get("equipos") or []:
            if isinstance(e, (list, tuple)) and len(e) > 4 and _num(e[4]):
                L.append(LineaPeso("Equipos", str(e[0]), 1, "u", float(e[4]), float(e[4]), "cargado"))
                eq += float(e[4])
        for r in P.get("rack_equipos") or []:
            if isinstance(r, (list, tuple)) and len(r) > 3 and _num(r[3]):
                L.append(LineaPeso("Equipos", str(r[0]), 1, "u", float(r[3]), float(r[3]), "cargado", "rack"))
                eq += float(r[3])

    L.sort(key=lambda x: PARTES.index(x.parte))
    for parte in PARTES:
        t = sum(x.total for x in L if x.parte == parte)
        if t > 0:
            out.partes[parte] = round(t, 2)
    out.total = round(sum(x.total for x in L), 2)
    out.vacio = round(out.total - out.partes.get("Equipos", 0.0), 2)
    out.estimado = round(sum(x.total for x in L if x.origen == "estimado"), 2)
    return out


def _num_txt(v: float) -> str:
    t = f"{v:.2f}".rstrip("0").rstrip(".")
    return t.replace(".", ",")


def filas_tabla(pc: PesoCase) -> List[List[str]]:
    """Filas para mostrar: Parte, Qué, Cantidad, Unitario, Total kg, De dónde sale."""
    out = []
    for x in pc.lineas:
        cant = _num_txt(x.cantidad) + ("" if x.unidad == "u" else f" {x.unidad}")
        if x.unidad == "u":
            unit = f"{_num_txt(x.unitario * 1000)} g" if x.unitario < 1 else f"{_num_txt(x.unitario)} kg"
        else:
            unit = f"{_num_txt(x.unitario)} kg/{x.unidad}"
        det = f" ({x.detalle})" if x.detalle else ""
        out.append([x.parte, x.nombre + det, cant, unit if x.unitario else "—", _num_txt(round(x.total, 2)),
                    x.origen])
    return out
