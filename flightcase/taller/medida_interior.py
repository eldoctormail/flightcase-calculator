"""Medida interior de placa a placa o de metal a metal.

Los perfiles de cierre (macho/hembra) y el perfil híbrido abrazan el canto de la placa con una
pata por dentro: esa pata se come un poco del interior. Las medidas interiores del proyecto se
miden, como siempre, de placa a placa; con ``medida_interior = "metal"`` se miden entre las patas
de aluminio y el case crece lo necesario para que lo que entra justo pase por la boca.

- Perfil de cierre (sistema de ángulo): el aro está en el plano de cierre, así que sólo afecta
  el ancho y el largo (la boca).
- Perfil híbrido: va en todas las aristas, así que afecta también los altos (piso y techo).

El espesor de la pata sale del catálogo (dato ``pata_int`` del perfil) o de los parámetros
``cierre_pata_int`` / ``hibrido_pata_int``. Si los dos sistemas aplican, se usa el más grueso.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .modelo import CatalogoTaller, s

SIN_PERFILES = {"tabla"}           # formas sin perfil de cierre ni híbrido


def _dato(cat: CatalogoTaller, ref: str, defecto: float) -> float:
    if ref and cat.existe(ref):
        v = cat.dato(ref, "pata_int", None)
        if isinstance(v, (int, float)) and v >= 0:
            return float(v)
    return float(defecto or 0)


def patas(P: Dict[str, Any], cat: CatalogoTaller) -> Tuple[float, float]:
    """(pata del perfil de cierre en la boca, pata del híbrido en todas las aristas), en mm."""
    if P.get("forma") in SIN_PERFILES:
        return 0.0, 0.0
    g = P.get
    if g("sistema") == "hibrido":
        k = _dato(cat, str(g("ref_hibrido") or ""), g("hibrido_pata_int", 1.5))
        return k, k
    if P.get("forma") == "funda":     # la funda no tiene perfil de cierre
        return 0.0, 0.0
    refs = [str(g("ref_cierre_macho") or "")] + ([] if g("cierre_hibrido") else [str(g("ref_cierre_hembra") or "")])
    k = max(_dato(cat, r, g("cierre_pata_int", 1.5)) for r in refs)
    return k, 0.0


def ajustar(P: Dict[str, Any], cat: CatalogoTaller) -> Optional[Dict[str, Any]]:
    """Con medida_interior = "metal" agranda las medidas interiores (en P) para que, entre las patas
    de aluminio, quede lo que se pidió. Devuelve lo que sumó, o None si se mide de placa a placa."""
    if P.get("medida_interior", "placa") != "metal":
        return None
    boca, aristas = patas(P, cat)
    if max(boca, aristas) <= 0:
        return None
    k_xy = max(boca, aristas)
    suma = {"int_ancho": 2 * k_xy, "int_prof": 2 * k_xy, "int_alto_cuerpo": aristas, "int_alto_tapa": aristas}
    if float(P.get("int_alto_tapa2", -1)) >= 0:
        suma["int_alto_tapa2"] = aristas
    for k, v in suma.items():
        P[k] = round(float(P[k]) + v, 2)
    return {"patas": [boca, aristas], "suma": suma}


def boca_libre(P: Dict[str, Any], cat: CatalogoTaller) -> Tuple[str, str, float, float]:
    """Ejes del mundo de la boca (plano de cierre) y lo que queda libre entre las patas, de placa a placa."""
    boca, aristas = patas(P, cat)
    k = max(boca, aristas)
    W, D = float(P["int_ancho"]), float(P["int_prof"])
    o = P.get("orientacion")
    if o == "frontal":
        return "ancho", "alto", W - 2 * k, D - 2 * k
    if o == "horizontal":
        return "fondo", "alto", D - 2 * k, W - 2 * k
    return "ancho", "fondo", W - 2 * k, D - 2 * k


def avisos_paso(P: Dict[str, Any], cat: CatalogoTaller) -> List[str]:
    """De placa a placa: avisa si un equipo no pasa por la boca entre las patas de los perfiles."""
    if P.get("medida_interior", "placa") == "metal" or P.get("forma") in SIN_PERFILES:
        return []
    boca, aristas = patas(P, cat)
    if max(boca, aristas) <= 0:
        return []
    e1, e2, l1, l2 = boca_libre(P, cat)
    idx = {"ancho": 1, "fondo": 2, "alto": 3}
    A: List[str] = []
    for e in P.get("equipos") or []:
        if not isinstance(e, (list, tuple)) or len(e) < 4:
            continue
        try:
            m1, m2 = float(e[idx[e1]]), float(e[idx[e2]])
        except (TypeError, ValueError):
            continue
        entra = m1 <= l1 + 1e-6 and m2 <= l2 + 1e-6
        girado = m2 <= l1 + 1e-6 and m1 <= l2 + 1e-6
        if not (entra or girado):
            A.append(s("«", e[0], "» (", round(m1, 1), " x ", round(m2, 1), " mm) no pasa por la boca: entre las "
                       "patas de los perfiles quedan ", round(l1, 1), " x ", round(l2, 1), " mm. Medí el interior de "
                       "metal a metal (medida_interior = metal) o agrandá el case."))
    return A
