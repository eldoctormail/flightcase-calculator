"""Interiores del case del taller: equipos, espuma con calados, cajones, rack de 19" y
chequeos de espacio libre.

flightcase.scad resuelve las bandejas y el forro de espuma (espuma_esp). Esto agrega lo
que el generador de OpenSCAD no tiene, con las mismas convenciones:

- Coordenadas del mundo: X = ancho, Y = profundidad (frente en Y = 0), Z = alto.
- Las posiciones de equipos, bloques de espuma y cajones se miden desde la esquina
  izquierda-delantera-inferior del espacio útil del cuerpo: x desde el costado izquierdo,
  y desde el frente del cuerpo (en un case frontal, desde el plano de cierre de la tapa
  delantera), z desde el piso interior. Si hay forro de espuma, el espacio útil es el de
  adentro del forro (las medidas interiores del proyecto ya son útiles).
- Un valor que falta (o "c") en x o y centra la pieza en el cuerpo.

Todo esto entra al resultado del taller como piezas adicionales (cortes de los cajones y
suplementos), herrajes y avisos, así que pasa solo a la lista de cortes, los DXF y el
presupuesto. La espuma sale además en DXF por capa (ver produccion.exportar).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .modelo import CatalogoTaller, fmt, s

# 19" (EIA-310 / IEC 60297)
U_MM = 44.45            # una unidad de rack
RACK_PANEL = 482.6      # ancho del frente del equipo, con orejas
RACK_AGUJEROS = 465.1   # distancia entre centros de los agujeros de las orejas
RACK_ABERTURA = 450.0   # ancho libre que necesita el cuerpo del equipo
RACK_OREJA = 3.0        # espesor de la oreja delante del riel
TOL = 1.0               # mm de superposición que se toleran antes de avisar

PARAMETROS = ("equipos", "espumas", "cajones", "rack_u", "rack_equipos")

_LATERALES = {0: (1, 2), 1: (0, 2), 2: (0, 1)}
_EJE = "XYZ"


def hay_interiores(P: Dict[str, Any]) -> bool:
    return bool(P.get("equipos") or P.get("espumas") or P.get("cajones") or (P.get("rack_u") or 0) > 0
                or P.get("rack_equipos"))


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _campo(fila: Sequence[Any], i: int) -> Optional[float]:
    return _num(fila[i]) if len(fila) > i else None


# ---------------------------------------------------------------------------
# Cajas alineadas a los ejes del mundo
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Caja:
    x0: float
    y0: float
    z0: float
    x1: float
    y1: float
    z1: float

    @staticmethod
    def de(p: Sequence[float], q: Sequence[float]) -> "Caja":
        return Caja(min(p[0], q[0]), min(p[1], q[1]), min(p[2], q[2]),
                    max(p[0], q[0]), max(p[1], q[1]), max(p[2], q[2]))

    @staticmethod
    def rangos(r: Sequence[Tuple[float, float]]) -> "Caja":
        return Caja(r[0][0], r[1][0], r[2][0], r[0][1], r[1][1], r[2][1])

    def lo(self, i: int) -> float:
        return (self.x0, self.y0, self.z0)[i]

    def hi(self, i: int) -> float:
        return (self.x1, self.y1, self.z1)[i]

    def med(self, i: int) -> float:
        return self.hi(i) - self.lo(i)

    def centro(self, i: int) -> float:
        return (self.lo(i) + self.hi(i)) / 2

    def solape(self, o: "Caja") -> List[float]:
        return [min(self.hi(i), o.hi(i)) - max(self.lo(i), o.lo(i)) for i in range(3)]

    def volumen(self) -> float:
        return max(self.med(0), 0) * max(self.med(1), 0) * max(self.med(2), 0)


@dataclass
class Solido:
    """Algo que ocupa lugar adentro del case (para los choques y la vista 3D)."""
    nombre: str
    tipo: str        # equipo, espuma, cajon, corredera, riel, suplemento, rack, caratula, bandeja
    caja: Caja
    grupo: str       # las partes de un mismo elemento no chocan entre sí
    fijo: bool = False


@dataclass
class CapaEspuma:
    bloque: int
    indice: int          # 1 = la capa del lado cerrado del bloque
    nombre: str
    ancho: float         # medidas de la capa en su plano (para el DXF)
    alto: float
    esp: float
    calados: List[Dict[str, Any]] = field(default_factory=list)   # tipo calado/rebaje, cx, cy, w, h, r, prof
    plano: str = "XY"    # ejes del mundo del dibujo (ancho, alto)


@dataclass
class BloqueEspuma:
    nombre: str
    caja: Caja
    eje: int             # eje de apilado de las capas (perpendicular a la cara abierta)
    abre_arriba: bool    # True: la cara abierta es la de coordenada mayor sobre `eje`
    bolsillos: List[Dict[str, Any]] = field(default_factory=list)   # u0,u1,v0,v1 (desde el borde) y fondo
    capas: List[CapaEspuma] = field(default_factory=list)


@dataclass
class ResultadoInteriores:
    solidos: List[Solido] = field(default_factory=list)
    espumas: List[BloqueEspuma] = field(default_factory=list)
    extras: List[list] = field(default_factory=list)       # [nombre, ancho, alto, esp, cant, material]
    herrajes: List[list] = field(default_factory=list)     # [nombre, cant, detalle, ref]
    avisos: List[str] = field(default_factory=list)
    elementos: List[List[str]] = field(default_factory=list)   # filas para la tabla "Interior"
    peso: Dict[str, float] = field(default_factory=dict)
    resumen: List[str] = field(default_factory=list)
    util: Optional[Caja] = None       # espacio útil total (cuerpo y tapas)
    cuerpo: Optional[Caja] = None     # espacio útil del cuerpo
    rack: Optional[Dict[str, Any]] = None
    eje_tapas: int = 2                # eje del mundo sobre el que abren las tapas
    signo_tapa: int = 1               # hacia dónde queda la tapa 1 sobre ese eje

    def en_tapa(self, c: Caja) -> int:
        """1 si la caja está en la tapa 1, -1 si está en la tapa 2 (o abajo), 0 si está en el cuerpo."""
        if self.cuerpo is None:
            return 0
        m, e = c.centro(self.eje_tapas), self.eje_tapas
        if m > self.cuerpo.hi(e) + TOL:
            return self.signo_tapa
        if m < self.cuerpo.lo(e) - TOL:
            return -self.signo_tapa
        return 0


# ---------------------------------------------------------------------------
# Espacio útil
# ---------------------------------------------------------------------------

def espacio_util(ctx: Dict[str, Any]) -> Tuple[Caja, Caja, int, int]:
    """(útil total, útil del cuerpo, eje de las tapas, signo hacia la tapa 1) en el mundo."""
    X, Y, Z = ctx["ext_ancho"], ctx["ext_prof"], ctx["ext_alto"]
    p, e = ctx["pared"], ctx["espuma"]
    hz, fr = ctx["horizontal"], ctx["frontal"]
    zc, zc2 = ctx["z_cierre"], ctx["z_cierre2"]
    if hz:
        mundo = lambda x, y, z: (Z - z, y, x)
    elif fr:
        mundo = lambda x, y, z: (x, Z - z, y)
    else:
        mundo = lambda x, y, z: (x, y, z)
    a, b = (p + e, p + e, p + e), (X - p - e, Y - p - e, Z - p - e)
    total = Caja.de(mundo(*a), mundo(*b))
    z0c = zc2 if ctx["dos_tapas"] else p + e
    cuerpo = Caja.de(mundo(a[0], a[1], z0c), mundo(b[0], b[1], zc))
    if hz:
        return total, cuerpo, 0, -1
    if fr:
        return total, cuerpo, 1, -1
    return total, cuerpo, 2, 1


def _plano_cierre(cuerpo: Caja, eje: int, signo: int) -> float:
    return cuerpo.hi(eje) if signo > 0 else cuerpo.lo(eje)


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

def calcular(P: Dict[str, Any], ctx: Dict[str, Any], cat: CatalogoTaller) -> ResultadoInteriores:
    R = ResultadoInteriores()
    total, cuerpo, eje_t, signo_t = espacio_util(ctx)
    R.util, R.cuerpo, R.eje_tapas, R.signo_tapa = total, cuerpo, eje_t, signo_t
    O = (cuerpo.x0, cuerpo.y0, total.z0)
    g = P.get
    A = R.avisos
    hz, fr = ctx["horizontal"], ctx["frontal"]
    dens_placa = float(g("densidad_placa", 650) or 650)

    def ubicar(i: int, medida: float, pos: Optional[float]) -> Tuple[float, float]:
        if pos is None:
            c = cuerpo.centro(i) if i != 2 else total.lo(2) + medida / 2
            return c - medida / 2, c + medida / 2
        return O[i] + pos, O[i] + pos + medida

    def txt_pos(c: Caja) -> str:
        return s("x ", round(c.x0 - O[0], 1), ", y ", round(c.y0 - O[1], 1), ", z ", round(c.z0 - O[2], 1))

    def txt_med(c: Caja) -> str:
        return s(round(c.med(0), 1), " x ", round(c.med(1), 1), " x ", round(c.med(2), 1))

    # ---- bandejas (las de flightcase.scad), para los choques ----
    for i, b in enumerate(ctx.get("bandejas", [])):
        esp = ctx["band_esp"](b)
        nombre = s("Bandeja ", i + 1) if len(ctx["bandejas"]) > 1 else "Bandeja"
        c = Caja.rangos([(cuerpo.centro(0) - b[0] / 2, cuerpo.centro(0) + b[0] / 2),
                         (cuerpo.centro(1) - b[1] / 2, cuerpo.centro(1) + b[1] / 2),
                         (ctx["pared"] + b[2] - esp, ctx["pared"] + b[2])])
        R.solidos.append(Solido(nombre, "bandeja", c, f"bandeja{i}", fijo=True))

    # ---- equipos sueltos ----
    peso_eq = 0.0
    equipos: List[Solido] = []
    for i, e in enumerate(g("equipos") or []):
        if not isinstance(e, (list, tuple)) or len(e) < 4:
            A.append(s("El equipo ", i + 1, " está mal cargado: van nombre, ancho, fondo y alto."))
            continue
        nombre = str(e[0]) if str(e[0]).strip() else s("Equipo ", i + 1)
        med = [_campo(e, 1), _campo(e, 2), _campo(e, 3)]
        if any(m is None or m <= 0 for m in med):
            A.append(s("El equipo ", nombre, " no tiene ancho, fondo y alto válidos."))
            continue
        peso = _campo(e, 4) or 0.0
        pos = [_campo(e, 5), _campo(e, 6), _campo(e, 7)]
        if pos[2] is None:
            pos[2] = 0.0
        c = Caja.rangos([ubicar(k, med[k], pos[k]) for k in range(3)])
        sol = Solido(nombre, "equipo", c, f"equipo{i}")
        equipos.append(sol)
        R.solidos.append(sol)
        peso_eq += peso
        R.elementos.append(["Equipo", nombre, txt_med(c), txt_pos(c), s(peso, " kg") if peso else ""])

    # ---- bloques de espuma con calados para los equipos ----
    plancha = float(g("espuma_plancha", 30) or 30)
    holg = float(g("espuma_holgura", 3) or 0)
    pared_min = float(g("espuma_pared_min", 15) or 0)
    fondo_min = float(g("espuma_fondo_min", 10) or 0)
    dens_esp = float(g("espuma_densidad", 30) or 0)
    medidas_pl = g("espuma_plancha_medidas") or [2000, 1000]
    mat_esp = str(g("espuma_material") or "Espuma de polietileno")
    ref_esp = str(g("ref_espuma_bloques") or "")
    if ref_esp and cat.existe(ref_esp):
        mat_esp = cat.nombre(ref_esp)
        plancha = float(cat.dato(ref_esp, "esp", plancha))
    elif ref_esp:
        A.append(s("La referencia ", ref_esp, " no está en el catálogo: revisá el número."))
    area_por_esp: Dict[float, float] = {}
    peso_esp = 0.0
    for i, f in enumerate(g("espumas") or []):
        if not isinstance(f, (list, tuple)):
            continue
        nombre = s("Espuma ", i + 1)
        rangos = []
        for k in range(3):
            m = _campo(f, k)
            p_ = _campo(f, 3 + k)
            if m is None or m <= 0:   # 0 = hasta el borde del cuerpo
                ini = O[k] + (p_ or 0.0)
                rangos.append((ini, cuerpo.hi(k)))
            elif p_ is None and k == eje_t and signo_t < 0:
                # sin posición: contra el fondo del cuerpo, del lado opuesto a la tapa delantera
                rangos.append((cuerpo.hi(k) - m, cuerpo.hi(k)))
            else:
                if k == 2 and p_ is None:
                    p_ = 0.0
                rangos.append(ubicar(k, m, p_))
        c = Caja.rangos(rangos)
        if min(c.med(k) for k in range(3)) <= 0:
            A.append(s("La ", nombre.lower(), " queda sin volumen: revisá medidas y posición."))
            continue
        # cara abierta: hacia la tapa más cercana (en el cuerpo, hacia la tapa 1)
        m_eje = c.centro(eje_t)
        if m_eje > cuerpo.hi(eje_t) + TOL:
            arriba = False
        elif m_eje < cuerpo.lo(eje_t) - TOL:
            arriba = True
        else:
            arriba = signo_t > 0
        bl = BloqueEspuma(nombre, c, eje_t, arriba)
        ua, va = _LATERALES[eje_t]
        L = c.med(eje_t)
        for eq in equipos:
            so = c.solape(eq.caja)
            if min(so) <= 0.5:
                continue
            u0 = max(eq.caja.lo(ua) - holg, c.lo(ua)) - c.lo(ua)
            u1 = min(eq.caja.hi(ua) + holg, c.hi(ua)) - c.lo(ua)
            v0 = max(eq.caja.lo(va) - holg, c.lo(va)) - c.lo(va)
            v1 = min(eq.caja.hi(va) + holg, c.hi(va)) - c.lo(va)
            fondo = (eq.caja.lo(eje_t) - c.lo(eje_t)) if arriba else (c.hi(eje_t) - eq.caja.hi(eje_t))
            fondo = max(0.0, fondo)
            bl.bolsillos.append(dict(equipo=eq.nombre, u0=u0, u1=u1, v0=v0, v1=v1, fondo=fondo))
            if fondo <= 0.01:
                A.append(s("El equipo ", eq.nombre, " atraviesa la ", nombre.lower(),
                           ": el calado queda pasante y el equipo apoya en lo que haya debajo."))
            elif fondo < fondo_min:
                A.append(s("Bajo el equipo ", eq.nombre, " quedan ", round(fondo, 1), " mm de espuma (mínimo ",
                           fondo_min, "): subí el equipo o agregá una capa."))
            bordes = [u0, c.med(ua) - u1, v0, c.med(va) - v1]
            if min(bordes) < pared_min - 0.01:
                A.append(s("El calado de ", eq.nombre, " queda a ", round(max(min(bordes), 0), 1),
                           " mm del borde de la ", nombre.lower(), " (mínimo ", pared_min, ")."))
        for a_i in range(len(bl.bolsillos)):
            for b_i in range(a_i + 1, len(bl.bolsillos)):
                p1, p2 = bl.bolsillos[a_i], bl.bolsillos[b_i]
                du = max(p1["u0"], p2["u0"]) - min(p1["u1"], p2["u1"])
                dv = max(p1["v0"], p2["v0"]) - min(p1["v1"], p2["v1"])
                sep = max(du, dv)
                if sep < 0:
                    A.append(s("Los calados de ", p1["equipo"], " y ", p2["equipo"], " se pisan en la ",
                               nombre.lower(), "."))
                elif sep < pared_min - 0.01:
                    A.append(s("Entre los calados de ", p1["equipo"], " y ", p2["equipo"], " quedan ",
                               round(sep, 1), " mm de espuma (mínimo ", pared_min, ")."))
        # capas, desde la cara cerrada hacia la abierta
        n = max(1, math.ceil(L / plancha - 1e-6))
        rebajes = []
        for j in range(n):
            d0 = j * plancha
            d1 = min(L, d0 + plancha)
            capa = CapaEspuma(i, j + 1, s(nombre, " capa ", j + 1), c.med(ua), c.med(va), round(d1 - d0, 2),
                              plano=_EJE[ua] + _EJE[va])
            for b_ in bl.bolsillos:
                if b_["fondo"] >= d1 - 0.01:
                    continue
                tipo = "calado" if b_["fondo"] <= d0 + 0.01 else "rebaje"
                prof = d1 - max(d0, b_["fondo"])
                capa.calados.append(dict(tipo=tipo, cx=(b_["u0"] + b_["u1"]) / 2, cy=(b_["v0"] + b_["v1"]) / 2,
                                         w=b_["u1"] - b_["u0"], h=b_["v1"] - b_["v0"], r=0.0, prof=round(prof, 2),
                                         equipo=b_["equipo"]))
                if tipo == "rebaje":
                    rebajes.append((b_["equipo"], j + 1, round(prof, 1)))
            bl.capas.append(capa)
            area_por_esp[capa.esp] = area_por_esp.get(capa.esp, 0.0) + capa.ancho * capa.alto / 1e6
        for eq_n, cj, pr in rebajes:
            A.append(s("El calado de ", eq_n, " termina dentro de la capa ", cj, " de la ", nombre.lower(),
                       ": esa capa lleva un rebaje de ", pr, " mm (fresado). Si el fondo coincide con una capa queda pasante."))
        resto = L - (n - 1) * plancha
        if n > 1 and abs(resto - plancha) > 0.5:
            A.append(s("La ", nombre.lower(), " mide ", round(L, 1), " mm: ", n - 1, " capas de ", plancha,
                       " y una de ", round(resto, 1), " mm."))
        vol = c.volumen() - sum((b_["u1"] - b_["u0"]) * (b_["v1"] - b_["v0"]) * (L - b_["fondo"])
                                for b_ in bl.bolsillos)
        peso_esp += max(vol, 0) / 1e9 * dens_esp
        R.espumas.append(bl)
        R.solidos.append(Solido(nombre, "espuma", c, f"espuma{i}"))
        R.elementos.append(["Espuma", nombre, txt_med(c), txt_pos(c),
                            s(n, " capa", "s" if n > 1 else "", ", ", len(bl.bolsillos), " calado",
                              "s" if len(bl.bolsillos) != 1 else "")])
    area_pl = float(medidas_pl[0]) * float(medidas_pl[1]) / 1e6
    for esp, area in sorted(area_por_esp.items(), reverse=True):
        R.herrajes.append([s(mat_esp, " ", esp, " mm"), math.ceil(area * 1.15 / area_pl - 1e-9),
                           s("planchas ", medidas_pl[0], "x", medidas_pl[1], " para ", round(area, 2),
                             " m² de capas (+15%)"), ref_esp])

    # ---- cajones con correderas (abren hacia el frente) ----
    caj = g("cajones") or []
    peso_caj = 0.0
    if caj:
        e = float(g("cajon_esp", 9) or 9)
        mat = str(g("cajon_material") or "") or s("Placa ", e, " mm")
        h = float(g("cajon_holgura", 3) or 0)
        ce_ = float(g("corredera_esp", 12.7) or 0)
        desc = float(g("cajon_desc_alto", 20) or 0)
        retiro = float(g("cajon_retiro", 5) or 0)
        largos = sorted(float(x) for x in (g("corredera_largos") or []) if _num(x))
        ref_corr = str(g("ref_corredera") or "")
        if not fr:
            A.append("Los cajones necesitan que el frente se abra: están pensados para cases frontales "
                     "(orientacion = \"frontal\"). En este case el frente es una pared fija.")
        fondo_disp = cuerpo.y1 - cuerpo.y0 - retiro - e - 10
        corr: Dict[float, int] = {}
        envolventes = []
        for i, cj in enumerate(caj):
            if not isinstance(cj, (list, tuple)) or len(cj) < 2:
                A.append(s("El cajón ", i + 1, " está mal cargado: van alto y altura desde el piso."))
                continue
            nombre = s("Cajón ", i + 1)
            alto, z = _campo(cj, 0), _campo(cj, 1)
            W = _campo(cj, 2) or cuerpo.med(0)
            largo = _campo(cj, 3) or 0.0
            if alto is None or alto <= 0 or z is None:
                A.append(s("El ", nombre.lower(), " no tiene alto o altura válidos."))
                continue
            if not largo:
                aptos = [l for l in largos if l <= fondo_disp + 0.01]
                if not aptos:
                    A.append(s("No hay corredera que entre en el fondo del cuerpo para el ", nombre.lower(),
                               " (hay ", round(fondo_disp, 1), " mm)."))
                    largo = max(fondo_disp, 0)
                else:
                    largo = aptos[-1]
            elif largo > fondo_disp + 0.01:
                A.append(s("La corredera de ", largo, " mm del ", nombre.lower(), " no entra: el cuerpo deja ",
                           round(fondo_disp, 1), " mm de fondo."))
            caja_ancho = W - 2 * ce_
            h_caja = alto - desc
            if W > cuerpo.med(0) + 0.01:
                A.append(s("El ", nombre.lower(), " (", W, " mm) es más ancho que el interior (",
                           round(cuerpo.med(0), 1), " mm)."))
            elif W < cuerpo.med(0) - 1:
                A.append(s("El ", nombre.lower(), " no ocupa todo el ancho: las correderas necesitan un costado ",
                           "o suplemento de ", round((cuerpo.med(0) - W) / 2, 1), " mm a cada lado."))
            if h_caja - e < 30:
                A.append(s("El ", nombre.lower(), " queda muy bajo: la caja tendría ", round(h_caja - e, 1), " mm de alto."))
            if caja_ancho - 2 * e <= 0 or largo <= 0:
                continue
            x0 = cuerpo.centro(0) - W / 2
            y0 = cuerpo.y0 + retiro
            z0 = total.z0 + z
            frente = Caja.rangos([(x0 + h, x0 + W - h), (y0, y0 + e), (z0, z0 + alto - h)])
            zc0 = z0 + (alto - h - h_caja) / 2
            caja = Caja.rangos([(x0 + ce_, x0 + W - ce_), (y0 + e, y0 + e + largo), (zc0, zc0 + h_caja)])
            grupo = f"cajon{i}"
            R.solidos.append(Solido(s(nombre, " (frente)"), "cajon", frente, grupo, fijo=True))
            R.solidos.append(Solido(nombre, "cajon", caja, grupo, fijo=True))
            alto_c = min(45.0, h_caja)
            for xa in (x0, x0 + W - ce_):
                R.solidos.append(Solido(s(nombre, " (corredera)"), "corredera",
                                        Caja.rangos([(xa, xa + ce_), (y0 + e, y0 + e + largo),
                                                     (zc0 + (h_caja - alto_c) / 2, zc0 + (h_caja + alto_c) / 2)]),
                                        grupo, fijo=True))
            envolventes.append((nombre, z0, z0 + alto))
            piezas = [
                (s(nombre, " frente"), W - 2 * h, alto - h, 1),
                (s(nombre, " lateral"), largo, h_caja - e, 2),
                (s(nombre, " trasera"), caja_ancho - 2 * e, h_caja - e, 1),
                (s(nombre, " piso"), caja_ancho, largo, 1),
            ]
            for nm, a_, b_, cant in piezas:
                R.extras.append([nm, round(a_, 2), round(b_, 2), e, cant, mat])
                peso_caj += a_ * b_ * e * cant / 1e9 * dens_placa
            corr[largo] = corr.get(largo, 0) + 1
            R.elementos.append(["Cajón", nombre, s(round(W, 1), " x ", largo, " x ", alto),
                                s("z ", z), s("caja ", round(caja_ancho, 1), " x ", largo, " x ", round(h_caja, 1),
                                  ", corredera ", largo)])
        for a_i in range(len(envolventes)):
            for b_i in range(a_i + 1, len(envolventes)):
                n1, a0, a1 = envolventes[a_i]
                n2, b0, b1 = envolventes[b_i]
                if min(a1, b1) - max(a0, b0) > 0.01:
                    A.append(s("El ", n1.lower(), " y el ", n2.lower(), " se pisan en altura."))
        for largo, n in sorted(corr.items()):
            R.herrajes.append([cat.nombre(ref_corr) if cat.existe(ref_corr) else s("Corredera telescópica ", largo, " mm (par)"),
                               n, s("extracción total, ", ce_, " mm por lado"), ref_corr])
        n_caj = sum(corr.values())
        if n_caj:
            R.herrajes.append(["Tirador embutido para cajón", n_caj, "uno por frente", ""])
            R.herrajes.append(["Tornillo para corredera", 16 * n_caj, "8 por corredera (4 al costado y 4 al cajón)", ""])

    # ---- rack de 19" ----
    rack_u = int(g("rack_u", 0) or 0)
    rack_eq = g("rack_equipos") or []
    peso_rack = 0.0
    if rack_eq and rack_u <= 0:
        rack_u = sum(int(_campo(r, 1) or 0) for r in rack_eq if isinstance(r, (list, tuple)))
        if rack_u:
            A.append(s("Hay equipos de rack pero rack_u = 0: se toman ", rack_u, " U (la suma de los equipos)."))
    if rack_u > 0:
        peso_rack = _rack(R, P, ctx, cat, total, cuerpo, rack_u, rack_eq)

    # ---- choques y espacio ----
    _choques(R, total, cuerpo, eje_t)

    R.peso = dict(equipos=round(peso_eq, 2), rack=round(peso_rack, 2), espuma=round(peso_esp, 2),
                  cajones=round(peso_caj, 2))
    R.peso["total"] = round(sum(R.peso.values()), 2)
    R.resumen.insert(0, s("Espacio útil del cuerpo: ", round(cuerpo.med(0), 1), " x ", round(cuerpo.med(1), 1), " x ",
                          round(cuerpo.med(2), 1), " mm"))
    if R.peso["total"] > 0:
        R.resumen.append(s("Peso del interior: ", R.peso["total"], " kg (equipos ", round(peso_eq + peso_rack, 2),
                           ", espuma ", R.peso["espuma"], ", cajones ", R.peso["cajones"], ")"))
    return R


def _rack(R: ResultadoInteriores, P: Dict[str, Any], ctx: Dict[str, Any], cat: CatalogoTaller,
          total: Caja, cuerpo: Caja, rack_u: int, rack_eq: list) -> float:
    """Rieles de 19", equipos de rack, carátulas ciegas y suplementos."""
    g = P.get
    A = R.avisos
    fr, hz = ctx["frontal"], ctx["horizontal"]
    if hz:
        A.append("El rack de 19\" se resuelve en cases frontales (rieles verticales, equipos de frente) o "
                 "verticales (rack de tapa superior). En un case acostado no se ubica.")
        return 0.0
    retiro = float(g("rack_retiro", 20) or 0)
    ala = float(g("riel_ala", 15) or 15)
    riel_fondo = float(g("riel_fondo", 20) or 20)
    riel_esp = float(g("riel_esp", 2) or 2)
    cables = float(g("rack_cables", 60) or 0)
    traseros = bool(g("rack_traseros", False))
    dist_tr = float(g("rack_dist_traseros", 0) or 0)
    desde = _num(g("rack_desde", -1))
    ref_riel = str(g("ref_riel") or "")
    W = cuerpo.med(0)
    X0 = cuerpo.x0
    if fr:   # rieles verticales: U a lo alto (Z), fondo hacia +Y desde el plano de cierre delantero
        a_lo, a_largo = total.z0, total.med(2)
        plano = cuerpo.y0
        d_max, d_cuerpo, d_tapa = total.y1 - plano, cuerpo.y1 - plano, plano - total.y0

        def caja(w0, w1, a0, a1, d0, d1):
            return Caja.rangos([(X0 + w0, X0 + w1), (plano + d0, plano + d1), (a_lo + a0, a_lo + a1)])
        txt_eje = "de abajo hacia arriba"
    else:    # tapa superior: rieles a lo largo de Y, fondo hacia abajo desde el plano de cierre
        a_lo, a_largo = cuerpo.y0, cuerpo.med(1)
        plano = cuerpo.z1
        d_max, d_cuerpo, d_tapa = plano - total.z0, plano - cuerpo.z0, total.z1 - plano

        def caja(w0, w1, a0, a1, d0, d1):
            return Caja.rangos([(X0 + w0, X0 + w1), (a_lo + a0, a_lo + a1), (plano - d1, plano - d0)])
        txt_eje = "desde el frente"
    max_u = int(math.floor(a_largo / U_MM + 1e-6))
    if rack_u > max_u:
        A.append(s("El rack de ", rack_u, " U no entra: el interior deja ", round(a_largo, 1), " mm (", max_u, " U)."))
    L = rack_u * U_MM
    a0 = (a_largo - L) / 2 if desde is None or desde < 0 else desde
    if a0 + L > a_largo + 0.01 and rack_u <= max_u:
        A.append(s("Los rieles se salen del interior: bajá rack_desde a ", round(a_largo - L, 1), " mm o menos."))
    # ancho: las orejas apoyan en el ala de los rieles
    if W < RACK_PANEL + 2:
        A.append(s("El interior mide ", round(W, 1), " mm de ancho: un equipo de 19\" necesita ", RACK_PANEL,
                   " mm más juego (≥ ", RACK_PANEL + 2, ")."))
    alcance = (W - RACK_AGUJEROS) / 2 + 6        # el ala tiene que pasar 6 mm el centro del agujero
    tope = (W - RACK_ABERTURA) / 2               # y no tapar los 450 mm del cuerpo del equipo
    supl = max(0.0, alcance - ala)
    if supl + ala > tope + 0.01:
        A.append(s("Con riel de ala ", ala, " mm el riel tapa la abertura de ", RACK_ABERTURA,
                   " mm del equipo: usá un riel más angosto."))
    if retiro < 0:
        A.append("rack_retiro negativo: los rieles quedarían fuera del cuerpo.")
    fondos_rieles = [retiro]
    if traseros:
        if dist_tr <= 0:
            dist_tr = d_cuerpo - retiro - riel_fondo - 5
        fondos_rieles.append(retiro + dist_tr)
        if retiro + dist_tr + riel_fondo > d_cuerpo + 0.01:
            A.append(s("Los rieles traseros quedan fuera del cuerpo: rack_dist_traseros máximo ",
                       round(d_cuerpo - retiro - riel_fondo, 1), " mm."))
    grupo = "rack"
    for k, d0 in enumerate(fondos_rieles):
        d_a, d_b = (d0, d0 + riel_fondo) if k == 0 else (d0 - riel_fondo, d0)
        for lado in (0, 1):
            w0 = supl if lado == 0 else W - supl - ala
            R.solidos.append(Solido("Riel de rack" + (" trasero" if k else ""), "riel",
                                    caja(w0, w0 + ala, a0, a0 + L, d_a, d_b), grupo, fijo=True))
            if supl >= 1:
                ws = 0 if lado == 0 else W - supl
                R.solidos.append(Solido("Suplemento de riel", "suplemento",
                                        caja(ws, ws + supl, a0, a0 + L, d_a, d_b + 20), grupo, fijo=True))
    n_rieles = 2 * len(fondos_rieles)
    if supl >= 1:
        e_s = round(supl, 1)
        R.extras.append(["Suplemento de riel de rack", riel_fondo + 20, round(L, 2), e_s, n_rieles,
                         s("Placa o listón ", e_s, " mm")])
    # equipos
    ocupado: List[Tuple[int, int, str]] = []
    siguiente = 1
    peso = 0.0
    fondo_max = 0.0
    tornillos = 0
    for i, r in enumerate(rack_eq):
        if not isinstance(r, (list, tuple)) or len(r) < 3:
            A.append(s("El equipo de rack ", i + 1, " está mal cargado: van nombre, U y fondo."))
            continue
        nombre = str(r[0]) if str(r[0]).strip() else s("Equipo de rack ", i + 1)
        u = int(_campo(r, 1) or 0)
        fondo = _campo(r, 2) or 0.0
        p_kg = _campo(r, 3) or 0.0
        u_desde = int(_campo(r, 4) or 0) or siguiente
        sal = _campo(r, 5) or 0.0
        if u <= 0 or fondo <= 0:
            A.append(s("El equipo de rack ", nombre, " no tiene U y fondo válidos."))
            continue
        u_hasta = u_desde + u - 1
        siguiente = max(siguiente, u_hasta + 1)
        if u_hasta > rack_u:
            A.append(s(nombre, " (U ", u_desde, " a ", u_hasta, ") se pasa del rack de ", rack_u, " U."))
        for (o0, o1, on) in ocupado:
            if min(o1, u_hasta) >= max(o0, u_desde):
                A.append(s(nombre, " y ", on, " ocupan las mismas unidades del rack."))
        ocupado.append((u_desde, u_hasta, nombre))
        if retiro + fondo + cables > d_max + 0.01:
            A.append(s(nombre, " no entra de fondo: necesita ", round(retiro + fondo + cables, 1),
                       " mm (retiro + fondo + ", cables, " de cables) y hay ", round(d_max, 1), " mm."))
        elif retiro + fondo > d_cuerpo + 0.01:
            A.append(s(nombre, " asoma ", round(retiro + fondo - d_cuerpo, 1),
                       " mm del cuerpo hacia la tapa trasera" if ctx["dos_tapas"] else " mm del cuerpo",
                       ": verificá que la tapa cierre."))
        if sal > retiro + d_tapa - 5:
            A.append(s("Lo que sobresale del frente de ", nombre, " (", sal, " mm) choca con la tapa: entran ",
                       round(retiro + d_tapa - 5, 1), " mm (rack_retiro + interior de la tapa)."))
        if not traseros and (p_kg > 10 or fondo > 450):
            A.append(s(nombre, " (", p_kg, " kg, ", fondo, " mm de fondo) conviene sostenerlo atrás: "
                       "activá rack_traseros o poné un soporte."))
        aa = a0 + (u_desde - 1) * U_MM
        hh = u * U_MM - 0.8
        R.solidos.append(Solido(s(nombre, " (frente)"), "rack", caja((W - RACK_PANEL) / 2, (W + RACK_PANEL) / 2,
                                                                       aa + 0.4, aa + 0.4 + hh, retiro - RACK_OREJA,
                                                                       retiro), f"rack_eq{i}"))
        R.solidos.append(Solido(nombre, "rack", caja((W - RACK_ABERTURA) / 2 + 2, (W + RACK_ABERTURA) / 2 - 2,
                                                     aa + 0.4, aa + 0.4 + hh, retiro, retiro + fondo), f"rack_eq{i}"))
        if sal > 0:
            R.solidos.append(Solido(s(nombre, " (perillas)"), "rack",
                                    caja(W / 2 - RACK_ABERTURA / 2 + 10, W / 2 + RACK_ABERTURA / 2 - 10,
                                         aa + hh * 0.25, aa + hh * 0.75, retiro - RACK_OREJA - sal, retiro - RACK_OREJA),
                                    f"rack_eq{i}"))
        peso += p_kg
        fondo_max = max(fondo_max, fondo)
        tornillos += 4 if u <= 2 else 8
        R.elementos.append(["Rack", nombre, s(u, " U x ", fondo, " mm"), s("U ", u_desde, "–", u_hasta),
                            s(p_kg, " kg") if p_kg else ""])
    # huecos: carátulas ciegas
    libres = [k for k in range(1, rack_u + 1) if not any(o0 <= k <= o1 for o0, o1, _ in ocupado)]
    huecos: List[List[int]] = []
    for k in libres:
        if huecos and huecos[-1][-1] == k - 1:
            huecos[-1].append(k)
        else:
            huecos.append([k])
    caratulas: Dict[int, int] = {}
    for h_ in huecos:
        n = len(h_)
        for tam in (4, 3, 2, 1):
            while n >= tam:
                caratulas[tam] = caratulas.get(tam, 0) + 1
                n -= tam
    for h_ in huecos:
        aa = a0 + (h_[0] - 1) * U_MM
        R.solidos.append(Solido("Carátula ciega", "caratula",
                                caja((W - RACK_PANEL) / 2, (W + RACK_PANEL) / 2, aa + 0.4, aa + len(h_) * U_MM - 0.4,
                                     retiro - 2, retiro), "rack_libre"))
    # herrajes
    bar = 45 * U_MM
    tramos = [L] * n_rieles
    barras, sobras = 0, []
    for t in tramos:
        for j, so in enumerate(sobras):
            if so >= t + 3:
                sobras[j] -= t + 3
                break
        else:
            barras += 1
            sobras.append(bar - t - 3)
    nom_riel = cat.nombre(ref_riel) if cat.existe(ref_riel) else "Perfil de rack 19\" 45U"
    if ref_riel and not cat.existe(ref_riel):
        A.append(s("La referencia ", ref_riel, " no está en el catálogo: revisá el número."))
    R.herrajes.append([nom_riel, barras, s("cortar ", n_rieles, " tramos de ", rack_u, " U (", round(L, 2), " mm)"),
                       ref_riel])
    R.herrajes.append(["Tornillo para fijar el riel al costado", n_rieles * (int(L // 100) + 2),
                       "cada 100 mm, que no atraviese el costado", ""])
    for tam, n in sorted(caratulas.items(), reverse=True):
        ref = {1: "04-8101", 2: "04-8102", 3: "04-8103", 4: "04-8104"}[tam]
        R.herrajes.append([cat.nombre(ref) if cat.existe(ref) else s("Carátula ciega ", tam, " U 19\""), n,
                           "para las unidades libres", ref if cat.existe(ref) else ""])
        tornillos += 4 * n
    if tornillos:
        ref_t = "08-5653" if riel_esp >= 1.75 else "08-5651"
        R.herrajes.append([cat.nombre(ref_t) if cat.existe(ref_t) else "Tuerca enjaulada M6", tornillos,
                           s("riel de ", riel_esp, " mm"), ref_t if cat.existe(ref_t) else ""])
        R.herrajes.append(["Tornillo M6x16 con arandela plástica", tornillos, "4 por equipo de 1-2 U, 8 desde 3 U", ""])
    R.rack = dict(u=rack_u, largo=L, desde=a0, retiro=retiro, suplemento=supl, ancho=W, fondo_util=d_max,
                  fondo_cuerpo=d_cuerpo, libres=len(libres))
    R.resumen.append(s("Rack 19\": ", rack_u, " U (", round(L, 1), " mm, U1 ", txt_eje, "), rieles a ", retiro,
                       " mm del cierre", s(", suplemento de ", round(supl, 1), " mm por lado") if supl >= 1 else "",
                       "; fondo para equipos: ", round(d_cuerpo - retiro, 1), " mm en el cuerpo",
                       s(", ", round(d_max - retiro, 1), " con la tapa trasera") if d_max > d_cuerpo + 0.5 else "",
                       "; ", len(libres), " U libres"))
    return peso


def _choques(R: ResultadoInteriores, total: Caja, cuerpo: Caja, eje_t: int) -> None:
    A = R.avisos
    lados = {0: ("a la izquierda", "a la derecha"), 1: ("adelante", "atrás"), 2: ("abajo", "arriba")}
    vistos = set()
    for so in R.solidos:
        lim = cuerpo if so.fijo else total
        for i in range(3):
            if so.fijo and i != eje_t:
                lim_lo, lim_hi = total.lo(i), total.hi(i)
            else:
                lim_lo, lim_hi = lim.lo(i), lim.hi(i)
            if so.tipo == "rack" or so.tipo == "caratula":   # los equipos de rack pueden ir a la tapa
                lim_lo, lim_hi = total.lo(i), total.hi(i)
            fuera_lo, fuera_hi = lim_lo - so.caja.lo(i), so.caja.hi(i) - lim_hi
            clave = (so.grupo, i)
            if clave in vistos:
                continue
            if fuera_lo > TOL or fuera_hi > TOL:
                vistos.add(clave)
                lado = lados[i][0] if fuera_lo > fuera_hi else lados[i][1]
                donde = "del cuerpo" if (so.fijo and i == eje_t) else "del interior"
                A.append(s(so.nombre, " se sale ", donde, " ", lado, " (", round(max(fuera_lo, fuera_hi), 1), " mm)."))
    sol = R.solidos
    pares = set()
    for a in range(len(sol)):
        for b in range(a + 1, len(sol)):
            p, q = sol[a], sol[b]
            if p.grupo == q.grupo or (p.grupo.startswith("rack") and q.grupo.startswith("rack")):
                continue
            if {p.tipo, q.tipo} == {"equipo", "espuma"}:
                continue   # el equipo va en su calado
            ov = p.caja.solape(q.caja)
            if min(ov) > TOL:
                clave = (p.grupo, q.grupo)
                if clave in pares:
                    continue
                pares.add(clave)
                A.append(s(_base(p.nombre), " choca con ", _base(q.nombre), " (se pisan ", round(ov[0], 1), " x ",
                           round(ov[1], 1), " x ", round(ov[2], 1), " mm)."))


def _base(nombre: str) -> str:
    return nombre.split(" (")[0]
