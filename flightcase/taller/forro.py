"""Forro interior por cara: alfombra o espuma pegada en cada cara de adentro del case (no
está en flightcase.scad).

El parámetro `forro` es una lista de filas `[cara, material, espesor, ref]`:

- cara: una cara del cuerpo ("piso", "frente", "trasera", "izq", "der"), de la tapa
  ("techo" = la cara de la tapa, "tapa_paredes" = sus cuatro paredes), de la segunda tapa
  ("base2", "tapa2_paredes") o un grupo ("cuerpo", "paredes", "tapa", "tapa2", "todo").
  Las filas se aplican en orden: una fila de una cara corrige a la de su grupo.
- material: "alfombra", "espuma" o "no" (sin forro en esa cara).
- espesor: mm; 0 = el del artículo del catálogo o, sin artículo, el por defecto
  (forro_alfombra_esp para la alfombra, espuma_esp o 10 para la espuma).
- ref: artículo del catálogo (categoría espuma o alfombra), opcional: da el nombre, el
  espesor y la medida de la plancha.

Como con espuma_esp, las medidas interiores del proyecto son el espacio útil: el case crece
lo que mide el forro de cada cara. Las paredes de la tapa no cambian el exterior (la tapa
tiene las mismas medidas de afuera que el cuerpo), sólo achican el lugar adentro de la tapa.

Cómo se arma (y así se cortan las piezas): primero el piso a todo el interior, después el
frente y la trasera a todo el ancho, apoyados en el piso, y por último los laterales entre
ellos. En la tapa, el techo a todo el interior y las paredes debajo de él.

Si sólo está espuma_esp (sin filas), el case se calcula como en flightcase.scad: espuma en
todas las caras y las planchas estimadas por superficie.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

CARAS_CUERPO = ("piso", "frente", "trasera", "izq", "der")
CARAS_TAPA = ("techo", "tapa_paredes")
CARAS_TAPA2 = ("base2", "tapa2_paredes")
CARAS = CARAS_CUERPO + CARAS_TAPA + CARAS_TAPA2
GRUPOS: Dict[str, Tuple[str, ...]] = {
    "todo": CARAS, "cuerpo": CARAS_CUERPO, "paredes": ("frente", "trasera", "izq", "der"),
    "tapa": CARAS_TAPA, "tapa2": CARAS_TAPA2,
}
NOMBRE_GRUPO = {"todo": "Todo el interior", "cuerpo": "Todo el cuerpo", "paredes": "Paredes del cuerpo",
                "tapa": "Toda la tapa", "tapa2": "Toda la segunda tapa"}
TIPOS = ("alfombra", "espuma", "no")
SIN_FORRO = ("no", "nada", "sin", "ninguno", "-")

ALFOMBRA_ESP = 3.0
ESPUMA_ESP = 10.0
ALFOMBRA_PLANCHA = (2000.0, 1500.0)    # trozo de rollo
ESPUMA_PLANCHA = (2000.0, 1000.0)


@dataclass
class CaraForro:
    tipo: str          # alfombra o espuma
    esp: float
    material: str      # nombre que sale en la lista de cortes y en la compra
    ref: str
    largo: float       # plancha entera
    ancho: float


@dataclass
class PiezaForro:
    cara: str
    nombre: str
    tipo: str
    material: str
    esp: float
    w: float
    h: float
    grupo: str                                     # cuerpo, tapa o tapa2 (para mover con la tapa)
    caja: Tuple[float, float, float, float, float, float]   # x0, y0, z0, x1, y1, z1 (case parado, sin ubicar)
    vista: str = ""                                # cómo se dibuja (ver VISTAS)
    huecos: List[Dict[str, Any]] = field(default_factory=list)   # calados del DXF: tipo, cx, cy, w, h, r
    huecos_3d: List[Tuple[int, float, float, int, float, float]] = field(default_factory=list)  # eje, desde, hasta (x2)


# Ejes de cada pieza en su dibujo, vista desde adentro del case: (eje, signo) del ancho y del alto
VISTAS: Dict[str, Tuple[Tuple[int, int], Tuple[int, int]]] = {
    "frente": ((0, -1), (2, 1)), "trasera": ((0, 1), (2, 1)), "izq": ((1, 1), (2, 1)), "der": ((1, -1), (2, 1)),
    "piso": ((0, 1), (1, 1)), "techo": ((0, -1), (1, 1)),
}
# Calados de los paneles que meten el herraje hacia adentro: el forro lleva el mismo hueco
HUECOS = ("manija", "manija a mano", "cierre", "cazoleta", "encastre")


@dataclass
class Forro:
    caras: Dict[str, CaraForro] = field(default_factory=dict)
    avisos: List[str] = field(default_factory=list)
    piezas: List[PiezaForro] = field(default_factory=list)

    def esp(self, cara: str) -> float:
        c = self.caras.get(cara)
        return c.esp if c else 0.0


def celdas(caja: Tuple[float, ...], huecos_3d) -> List[Tuple[float, ...]]:
    """La lámina partida en cajas que dejan libres los huecos (para la vista 3D y el STEP)."""
    if not huecos_3d:
        return [tuple(caja)]
    eu, ev = huecos_3d[0][0], huecos_3d[0][3]
    lo, hi = caja[:3], caja[3:]
    cu = sorted({lo[eu], hi[eu]} | {h[k] for h in huecos_3d for k in (1, 2)})
    cv = sorted({lo[ev], hi[ev]} | {h[k] for h in huecos_3d for k in (4, 5)})
    out = []
    for a0, a1 in zip(cu, cu[1:]):
        for b0, b1 in zip(cv, cv[1:]):
            mu, mv = (a0 + a1) / 2, (b0 + b1) / 2
            if any(h[1] <= mu <= h[2] and h[4] <= mv <= h[5] for h in huecos_3d):
                continue
            c0, c1 = list(lo), list(hi)
            c0[eu], c1[eu], c0[ev], c1[ev] = a0, a1, b0, b1
            out.append(tuple(c0) + tuple(c1))
    return out


def hay_forro(P: Dict[str, Any]) -> bool:
    return any(isinstance(f, (list, tuple)) and f and str(f[0] or "").strip() for f in (P.get("forro") or []))


def _num(v: Any, defecto: float = 0.0) -> float:
    if isinstance(v, bool):
        return defecto
    try:
        return float(v)
    except (TypeError, ValueError):
        return defecto


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def caras_validas(dos_tapas: bool) -> Tuple[str, ...]:
    return tuple(c for c in CARAS if (c not in CARAS_TAPA2 if not dos_tapas else c != "piso"))


def resolver(P: Dict[str, Any], cat, dos_tapas: bool, espuma_def: float = 0.0, ref_espuma: str = "") -> Forro:
    """Forro efectivo de cada cara: espuma_esp en todas (si hay) y después las filas en orden."""
    g = P.get
    F = Forro()
    validas = caras_validas(dos_tapas)
    esp_alf = _num(g("forro_alfombra_esp"), ALFOMBRA_ESP) or ALFOMBRA_ESP
    planchas = {"alfombra": tuple(g("forro_alfombra_plancha") or ALFOMBRA_PLANCHA),
                "espuma": tuple(g("forro_espuma_plancha") or ESPUMA_PLANCHA)}

    def armar(tipo: str, esp: float, ref: str) -> CaraForro:
        con_cat = bool(ref) and cat.existe(ref)
        if esp <= 0:
            esp = _num(cat.dato(ref, "esp", 0)) if con_cat else 0
        if esp <= 0:
            esp = esp_alf if tipo == "alfombra" else (espuma_def if espuma_def > 0 else ESPUMA_ESP)
        nombre = cat.nombre(ref) if con_cat else f"{tipo.capitalize()} {_f(esp)} mm"
        if con_cat and _num(cat.dato(ref, "esp", 0)) not in (0, esp):
            nombre = f"{nombre} ({_f(esp)} mm)"
        L, A = planchas[tipo][0], planchas[tipo][1]
        if con_cat:
            L, A = _num(cat.dato(ref, "largo", L), L), _num(cat.dato(ref, "ancho", A), A)
        return CaraForro(tipo, esp, nombre, ref if con_cat else "", float(L), float(A))

    if espuma_def > 0:
        base = armar("espuma", espuma_def, ref_espuma)
        F.caras = {c: base for c in validas}
    for fila in g("forro") or []:
        if not isinstance(fila, (list, tuple)) or not fila or not str(fila[0] or "").strip():
            continue
        fila = list(fila) + [None] * (4 - len(fila))
        clave = str(fila[0]).strip()
        if clave in GRUPOS:
            caras = [c for c in GRUPOS[clave] if c in validas]
        elif clave in validas:
            caras = [clave]
        else:
            F.avisos.append(f"Forro interior: «{clave}» no es una cara de este case; esa fila no se usa.")
            continue
        tipo = str(fila[1] or "").strip().lower()
        ref = str(fila[3] or "").strip()
        if tipo in SIN_FORRO:
            for c in caras:
                F.caras.pop(c, None)
            continue
        if tipo not in ("alfombra", "espuma"):
            if ref and cat.existe(ref):
                tipo = "alfombra" if cat.categoria(ref) == "alfombra" else "espuma"
            else:
                F.avisos.append(f"Forro interior: el material «{fila[1]}» no se entiende (va alfombra, espuma o no); "
                                f"la fila de «{clave}» no se usa.")
                continue
        esp = _num(fila[2])
        if esp < 0:
            esp = 0
        cf = armar(tipo, esp, ref)
        for c in caras:
            F.caras[c] = cf
    return F


def calcular_piezas(F: Forro, geo: Dict[str, Any], nombre_panel: Callable[[str], str]) -> None:
    """Piezas de forro de cada cara, con su lugar en el case (coordenadas del case parado).

    geo: X, Y (exterior), pared, z_cierre, z_cierre2, ext_alto, dos_tapas."""
    X, Y, p = geo["X"], geo["Y"], geo["pared"]
    zc, zc2, Z, dos = geo["z_cierre"], geo["z_cierre2"], geo["ext_alto"], geo["dos_tapas"]
    x0, x1, y0, y1 = p, X - p, p, Y - p
    W, D = x1 - x0, y1 - y0
    e = F.esp
    out: List[PiezaForro] = []

    def pieza(cara: str, pid: str, grupo: str, caja, w: float, h: float, cf: Optional[CaraForro] = None) -> None:
        cf = cf or F.caras[cara]
        if w <= 0 or h <= 0:
            F.avisos.append(f"Forro interior: no queda lugar para el forro de {nombre_panel(pid).lower()}.")
            return
        lado = pid.split("_")[-1] if "_" in pid else ("techo" if pid == "techo" else "piso")
        out.append(PiezaForro(cara, f"Forro {nombre_panel(pid).lower()}", cf.tipo, cf.material, cf.esp,
                              round(w, 2), round(h, 2), grupo, tuple(round(v, 3) for v in caja), lado))

    def paredes(pre: str, grupo: str, za: float, zb: float, ef: float, et: float, ei: float, ed: float,
                cfs: Dict[str, Optional[CaraForro]], clave: Dict[str, str]) -> None:
        H = zb - za
        if cfs["frente"]:
            pieza(clave["frente"], f"{pre}_frente", grupo, (x0, y0, za, x1, y0 + ef, zb), W, H, cfs["frente"])
        if cfs["trasera"]:
            pieza(clave["trasera"], f"{pre}_trasera", grupo, (x0, y1 - et, za, x1, y1, zb), W, H, cfs["trasera"])
        if cfs["izq"]:
            pieza(clave["izq"], f"{pre}_izq", grupo, (x0, y0 + ef, za, x0 + ei, y1 - et, zb), D - ef - et, H, cfs["izq"])
        if cfs["der"]:
            pieza(clave["der"], f"{pre}_der", grupo, (x1 - ed, y0 + ef, za, x1, y1 - et, zb), D - ef - et, H, cfs["der"])

    # cuerpo
    z_piso = zc2 if dos else p
    if not dos and "piso" in F.caras:
        pieza("piso", "piso", "cuerpo", (x0, y0, p, x1, y1, p + e("piso")), W, D)
    za = z_piso + (0 if dos else e("piso"))
    paredes("cuerpo", "cuerpo", za, zc, e("frente"), e("trasera"), e("izq"), e("der"),
            {k: F.caras.get(k) for k in ("frente", "trasera", "izq", "der")},
            {k: k for k in ("frente", "trasera", "izq", "der")})
    # tapa (y segunda tapa): la cara a todo el interior y las paredes debajo
    tapas = [("techo", "tapa_paredes", "tapa", zc, Z - p, True)]
    if dos:
        tapas.append(("base2", "tapa2_paredes", "tapa2", p, zc2, False))
    for cara, par, grupo, za, zb, arriba in tapas:
        ec = e(cara)
        if cara in F.caras:
            pieza(cara, cara, grupo, (x0, y0, zb - ec, x1, y1, zb) if arriba else (x0, y0, za, x1, y1, za + ec), W, D)
        cp = F.caras.get(par)
        if cp:
            ep = cp.esp
            paredes(grupo, grupo, za if arriba else za + ec, zb - ec if arriba else zb, ep, ep, ep, ep,
                    {k: cp for k in ("frente", "trasera", "izq", "der")}, {k: par for k in ("frente", "trasera", "izq", "der")})
    F.piezas = out


def agregar_huecos(F: Forro, calados, colocaciones: List[Dict[str, Any]], pared: float) -> None:
    """Huecos en el forro donde un herraje embutido (manija, cierre, cazoleta, plato) entra en el case.

    Cada calado del panel se lleva al plano del forro que está pegado a ese panel."""
    col = {c["id"]: c for c in colocaciones}
    for c in calados:
        if c.tipo not in HUECOS or c.panel not in col:
            continue
        cl = col[c.panel]
        o, u, v, n = cl["o"], cl["u"], cl["v"], cl["n"]
        a = next(i for i in range(3) if abs(n[i]) > 0.5)
        centro = [o[i] + u[i] * c.cx + v[i] * c.cy for i in range(3)]
        med = [abs(u[i]) * c.ancho + abs(v[i]) * c.alto for i in range(3)]
        for pz in F.piezas:
            lo, hi = pz.caja[:3], pz.caja[3:]
            if hi[a] - lo[a] > pz.esp + 0.01 or abs(hi[a] - lo[a] - pz.esp) > 0.01:
                continue   # la pieza no es una lámina perpendicular a la normal del panel
            cerca = lo[a] if n[a] > 0 else hi[a]
            if abs(cerca - o[a]) > pared + 1.0:
                continue
            (eu, su), (ev, sv) = VISTAS[pz.vista]
            if eu == a or ev == a:
                continue
            u0, u1 = centro[eu] - med[eu] / 2, centro[eu] + med[eu] / 2
            v0, v1 = centro[ev] - med[ev] / 2, centro[ev] + med[ev] / 2
            if u1 <= lo[eu] or u0 >= hi[eu] or v1 <= lo[ev] or v0 >= hi[ev]:
                continue
            u0, u1, v0, v1 = max(u0, lo[eu]), min(u1, hi[eu]), max(v0, lo[ev]), min(v1, hi[ev])
            pz.huecos_3d.append((eu, u0, u1, ev, v0, v1))
            cu = (u0 + u1) / 2 - lo[eu] if su > 0 else hi[eu] - (u0 + u1) / 2
            cv = (v0 + v1) / 2 - lo[ev] if sv > 0 else hi[ev] - (v0 + v1) / 2
            tipo = "cazoleta de rueda" if c.tipo == "cazoleta" else c.tipo
            pz.huecos.append(dict(tipo=tipo, cx=round(cu, 2), cy=round(cv, 2), w=round(u1 - u0, 2),
                                  h=round(v1 - v0, 2), r=float(getattr(c, "radio", 0) or 0)))


def _firma(pz: PiezaForro) -> tuple:
    return (round(pz.w, 1), round(pz.h, 1), pz.esp, pz.material,
            tuple(sorted((h["cx"], h["cy"], h["w"], h["h"]) for h in pz.huecos)))


def juntar(F: Forro) -> List[Dict[str, Any]]:
    """Piezas iguales (misma medida, material y huecos) juntas: nombre, w, h, esp, cant, material, huecos."""
    juntas: Dict[tuple, Dict[str, Any]] = {}
    for pz in F.piezas:
        k = _firma(pz)
        if k in juntas:
            j = juntas[k]
            j["cant"] += 1
            j["piezas"].append(pz)
            if pz.nombre not in j["nombre"].split(" / "):
                j["nombre"] += " / " + pz.nombre
        else:
            juntas[k] = dict(nombre=pz.nombre, w=pz.w, h=pz.h, esp=pz.esp, cant=1, material=pz.material,
                             tipo=pz.tipo, huecos=list(pz.huecos), piezas=[pz])
    return list(juntas.values())


def extras(F: Forro) -> List[list]:
    """Las piezas juntas con el formato de piezas_extra: [nombre, ancho, alto, esp, cant, material]."""
    return [[j["nombre"], j["w"], j["h"], j["esp"], j["cant"], j["material"]] for j in juntar(F)]


def materiales(F: Forro) -> Dict[str, CaraForro]:
    out: Dict[str, CaraForro] = {}
    for c in F.caras.values():
        out.setdefault(c.material, c)
    return out


def superficie(F: Forro) -> float:
    """m² de forro (para el adhesivo)."""
    return sum(pz.w * pz.h for pz in F.piezas) / 1e6


def panelmat(F: Forro) -> List[list]:
    """Filas PANELMAT con la medida de la plancha de cada material del forro (para acomodar las piezas)."""
    return [[f"forro{i}", m, c.esp, c.largo, c.ancho, c.ref, "forro"] for i, (m, c) in enumerate(materiales(F).items(), 1)]


def resumen_caras(F: Forro, nombre_cara: Callable[[str], str]) -> List[str]:
    """«Piso: Alfombra 3 mm», una por cara con forro, en el orden de CARAS."""
    return [f"{nombre_cara(c)}: {F.caras[c].material}" for c in CARAS if c in F.caras]


def chequear(F: Forro, P: Dict[str, Any], acceso: bool) -> None:
    A = F.avisos
    for pz in F.piezas:
        L, An = next(((c.largo, c.ancho) for c in F.caras.values() if c.material == pz.material), (0, 0))
        if L and not (max(pz.w, pz.h) <= max(L, An) and min(pz.w, pz.h) <= min(L, An)):
            A.append(f"Forro interior: la pieza {pz.nombre.lower()} ({_f(pz.w)} x {_f(pz.h)}) no entra en una "
                     f"plancha de {_f(L)} x {_f(An)}: va en dos partes con la unión a tope.")
    if acceso and ("izq" in F.caras or "der" in F.caras):
        A.append("Forro interior: con tapa de acceso lateral, cortá el forro del lateral en la junta de la tapa de acceso.")


def opciones(dos_tapas: bool, nombre_cara: Callable[[str], str]) -> List[Tuple[str, str]]:
    """(clave, nombre) de las caras y grupos que se pueden forrar, para la tabla de la app."""
    grupos = [g for g in GRUPOS if g != "tapa2" or dos_tapas]
    return [(g, NOMBRE_GRUPO[g]) for g in grupos] + [(c, nombre_cara(c)) for c in caras_validas(dos_tapas)]


def planchas_estimadas(F: Forro) -> Dict[str, int]:
    """Planchas por material estimadas por superficie (+20 %), para cuando no se acomodan."""
    out: Dict[str, int] = {}
    for m, c in materiales(F).items():
        area = sum(pz.w * pz.h for pz in F.piezas if pz.material == m)
        out[m] = max(1, math.ceil(area * 1.2 / (c.largo * c.ancho))) if area else 0
    return out


def pasos_instructivo(res, piezas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Paso de montaje del forro, con el formato de instructivo.armar_pasos."""
    F = res.valores.get("forro")
    if F is None or not F.piezas:
        return []
    v = res.valores
    num = {pz["nombre"]: pz["num"] for pz in piezas if pz.get("forro")}
    juntas = juntar(F)

    def lista(caras: Tuple[str, ...]) -> str:
        out = []
        for j in juntas:
            if any(pz.cara in caras for pz in j["piezas"]) and j["nombre"] in num:
                out.append(f"P{num[j['nombre']]}" + (f" (x{j['cant']})" if j["cant"] > 1 else ""))
        return ", ".join(out)

    texto = [f"Piezas: el forro cortado ({', '.join(sorted(materiales(F)))}) y adhesivo de contacto para "
             f"{_f(superficie(F)).replace('.', ',')} m²."]
    k = 1
    for caras, txt in ((("piso", "techo", "base2"), "Pegá primero el forro del piso y el de la cara de cada tapa, a todo el interior."),
                       (("frente", "trasera"), "Después el frente y la trasera, a todo el ancho y apoyados en el piso."),
                       (("izq", "der"), "Por último los laterales, entre el frente y la trasera."),
                       (("tapa_paredes", "tapa2_paredes"), "En la tapa, las paredes van debajo del forro del techo, "
                                                           "frente y trasera primero y los laterales entre ellos.")):
        l = lista(caras)
        if l:
            texto.append(f"{k}. {txt} ({l})")
            k += 1
    texto.append(f"{k}. Pasá adhesivo a las dos caras, dejá orear lo que diga el envase y apoyá desde el centro "
                 "hacia los bordes. Recortá con trincheta lo que sobre en los cantos y en los huecos de los herrajes.")
    abrir = round(0.8 * max(v["ext_ancho"], v["ext_prof"], v["ext_alto"]))
    return [dict(titulo="Interior: forro", vista="int_forro", camara="0,0,0,62,0,28,0",
                 defs={"paso": 99, "abrir_tapa": abrir, "resaltar_interior": "forro"}, texto=texto)]
