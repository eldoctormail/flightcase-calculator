"""Patines bajo el piso y patas de mesa (no están en flightcase.scad).

Patines (``patines`` = 2 o 3): listones de madera atornillados bajo el piso, a lo largo del
lado más largo (o del que se elija), para levantar el case con zorra o autoelevador y que no
apoye la placa en el piso. Van retirados de los esquineros. Salen en la lista de corte (piezas
extra con su material), con los tornillos y su marca en el piso.

Patas de mesa (``patas_mesa`` = 4): cuatro patas de tubo que se enroscan en soportes:
- ``patas_en = "tapa"``: los soportes van por dentro del techo de la tapa. Se saca la tapa, se le
  ponen las patas y se da vuelta: el techo queda como tablero de la mesa.
- ``patas_en = "cuerpo"``: los soportes van bajo el piso y el case entero queda parado sobre
  las patas (una consola o un rack a la altura de trabajo).

Sólo para cases parados (orientación vertical): en uno frontal o acostado avisa y no pone nada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SENTIDOS = ("auto", "ancho", "largo")
PATAS_EN = ("tapa", "cuerpo")
ESP_SOPORTE = 6.0          # alto de la placa del soporte de la pata (para el 3D)
REMACHES_SOPORTE = 4
PASO_TORNILLOS = 300.0     # un tornillo cada tanto a lo largo del patín


@dataclass
class ResultadoApoyos:
    extras: List[list] = field(default_factory=list)          # [nombre, largo, ancho, esp, cant, material]
    herrajes: List[Tuple[str, int, str, str]] = field(default_factory=list)
    marcas: List[Any] = field(default_factory=list)
    calados: List[Any] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    info: Dict[str, List[str]] = field(default_factory=dict)
    remaches: int = 0
    alto_patines: float = 0.0
    geo: Dict[str, Any] = field(default_factory=dict)


def _f(P: Dict[str, Any], clave: str, defecto: float) -> float:
    try:
        return float(P.get(clave, defecto))
    except (TypeError, ValueError):
        return defecto


def s(*partes: Any) -> str:
    from .modelo import s as _s
    return _s(*partes)


def _mm(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _repartir(L: float, n: int, ancho: float, margen: float) -> List[float]:
    """Inicio de cada una de `n` piezas de `ancho` repartidas en L, la primera y la última a `margen` del borde."""
    if n <= 1:
        return [(L - ancho) / 2]
    paso = (L - 2 * margen - ancho) / (n - 1)
    return [margen + i * paso for i in range(n)]


def calcular(P: Dict[str, Any], X: float, Y: float, Z: float, *, vertical: bool, panel_base: str,
             panel_techo: Optional[str], ox: float, oy: float, margen: float, placa_esp: float,
             hay_ruedas: bool, hay_pies: bool, hay_base: bool) -> ResultadoApoyos:
    """X, Y, Z: medidas exteriores. `ox`, `oy`: dónde empieza el panel del piso (y del techo)
    respecto del borde exterior. `margen`: lo que hay que dejar libre en cada esquina (esquineros)."""
    from .modelo import Calado, Marca, s
    R = ResultadoApoyos()
    n_pat = int(_f(P, "patines", 0))
    n_patas = int(_f(P, "patas_mesa", 0))
    if not n_pat and not n_patas:
        return R
    if not vertical:
        R.avisos.append("Los patines y las patas de mesa son para cases parados (orientación vertical): "
                        "en este case no se ponen.")
        return R

    # ---- patines ----
    if n_pat:
        if n_pat not in (2, 3):
            R.avisos.append(s("patines tiene que ser 0, 2 o 3 (puse ", n_pat, "): no se ponen."))
        else:
            ancho = max(_f(P, "patin_ancho", 70), 10)
            alto = max(_f(P, "patin_alto", 45), 5)
            material = str(P.get("patin_material") or "Pino")
            retiro = _f(P, "patin_retiro", -1)
            retiro = margen if retiro < 0 else retiro
            sentido = str(P.get("patin_sentido") or "auto")
            if sentido not in SENTIDOS:
                R.avisos.append(s("patin_sentido «", sentido, "» no existe (", ", ".join(SENTIDOS), "): uso auto."))
                sentido = "auto"
            a_lo_ancho = (X >= Y) if sentido == "auto" else sentido == "ancho"
            largo_case, cruzado = (X, Y) if a_lo_ancho else (Y, X)
            largo = largo_case - 2 * retiro
            if largo < 100 or cruzado < n_pat * ancho + 2 * retiro:
                R.avisos.append("Los patines no entran bajo el piso de este case: achicá el ancho o el retiro.")
            else:
                n_torn = max(2, math.ceil(largo / PASO_TORNILLOS) + 1)
                largo_torn = 5 * math.ceil((placa_esp + 0.7 * alto) / 5)
                cajas = []
                for x0 in _repartir(cruzado, n_pat, ancho, retiro):
                    if a_lo_ancho:
                        caja = (retiro, x0, retiro + largo, x0 + ancho)
                    else:
                        caja = (x0, retiro, x0 + ancho, retiro + largo)
                    cajas.append(caja + (alto,))
                    cx, cy = (caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2
                    R.marcas.append(Marca(panel_base, "patin", cx - ox, cy - oy, caja[2] - caja[0], caja[3] - caja[1],
                                          "patín"))
                    for t in range(n_torn):     # tornillos de adentro hacia el patín, en la línea del medio
                        d = 40 + t * (largo - 80) / (n_torn - 1)
                        px, py = (caja[0] + d, cy) if a_lo_ancho else (cx, caja[1] + d)
                        R.calados.append(Calado(panel_base, "agujero", px - ox, py - oy, 5.0, 5.0, 2.5))
                R.extras.append(["Patín", round(largo, 1), round(ancho, 1), round(alto, 1), n_pat,
                                 s(material, " ", _mm(ancho), "×", _mm(alto), " mm")])
                R.herrajes.append(("Tornillo para madera Ø5", n_pat * n_torn,
                                   s(largo_torn, " mm, de adentro del piso hacia el patín (", n_torn, " por patín)"), ""))
                R.alto_patines = alto
                R.info["patines"] = [str(n_pat), _mm(ancho), _mm(alto), _mm(largo), "ancho" if a_lo_ancho else "largo"]
                R.geo["patines"] = [list(c) for c in cajas]
                if hay_ruedas or hay_pies or hay_base:
                    R.avisos.append("Elegiste patines y también ruedas, pies o base de ruedas: van todos bajo el "
                                    "piso, revisá que no se crucen.")

    # ---- patas de mesa ----
    if n_patas:
        if n_patas != 4:
            R.avisos.append(s("patas_mesa tiene que ser 0 o 4 (puse ", n_patas, "): no se ponen."))
            return R
        en = str(P.get("patas_en") or "tapa")
        if en not in PATAS_EN:
            R.avisos.append(s("patas_en «", en, "» no existe (tapa o cuerpo): uso tapa."))
            en = "tapa"
        if en == "tapa" and not panel_techo:
            R.avisos.append("Este case no tiene techo de tapa: las patas de mesa van bajo el cuerpo.")
            en = "cuerpo"
        largo = max(_f(P, "pata_largo", 700), 50)
        lado = max(_f(P, "pata_lado", 40), 10)
        soporte = max(_f(P, "pata_soporte", 70), lado)
        retiro = _f(P, "pata_retiro", -1)
        retiro = margen if retiro < 0 else retiro
        if 2 * (retiro + soporte) > min(X, Y):
            R.avisos.append("Los soportes de las patas de mesa no entran: el case es muy chico para patas.")
            return R
        c = retiro + soporte / 2
        if en == "tapa":      # por dentro del techo: el retiro se cuenta desde la cara interior de la pared
            c = max(c, max(ox, oy) + soporte / 2 + 5)
        centros = [[c if sx == 0 else X - c, c if sy == 0 else Y - c] for sx in (0, 1) for sy in (0, 1)]
        panel = panel_techo if en == "tapa" else panel_base
        for cx, cy in centros:
            R.marcas.append(Marca(panel, "pata", cx - ox, cy - oy, soporte, soporte,
                                  "soporte de pata (por dentro)" if en == "tapa" else "soporte de pata"))
        R.herrajes.append(("Pata de mesa", 4, s("tubo cuadrado ", _mm(lado), "×", _mm(lado), ", largo ", _mm(largo),
                                                " mm, con espárrago para enroscar"), ""))
        R.herrajes.append(("Soporte de pata de mesa con rosca", 4,
                           s("placa ", _mm(soporte), "×", _mm(soporte), " mm, ", REMACHES_SOPORTE, " remaches c/u, ",
                             "por dentro del techo de la tapa" if en == "tapa" else "bajo el piso"), ""))
        R.remaches += 4 * REMACHES_SOPORTE
        alto_mesa = largo + ESP_SOPORTE + (placa_esp if en == "tapa" else Z)
        R.info["patas_mesa"] = [en, _mm(largo), _mm(lado), _mm(alto_mesa)]
        R.geo["patas"] = dict(en=en, centros=centros, largo=largo, lado=lado, soporte=soporte, esp=ESP_SOPORTE)
        if en == "cuerpo" and R.geo.get("patines"):
            R.avisos.append("Pusiste patines y patas de mesa bajo el cuerpo a la vez: van los dos bajo el piso.")
        if en == "cuerpo" and (hay_ruedas or hay_pies or hay_base):
            R.avisos.append("Las patas de mesa bajo el cuerpo se cruzan con las ruedas, los pies o la base: "
                            "sacá esas o poné las patas en la tapa.")
    return R
