"""Piezas sueltas: cambiar un esquinero, un ángulo o un panel solo (no está en flightcase.scad).

El parámetro `piezas` es una lista de filas `[pieza, artículo, color, sin_pieza]`:

- pieza: el id de una pieza del case. Esquineros "esq_XYZ" y ángulos de arista "ar_x_YZ",
  "ar_y_XZ", "ar_zc_XY" (vertical del cuerpo), "ar_zt_XY" (de la tapa) y "ar_zt2_XY" (de la
  segunda tapa), donde cada letra es 0 o 1 según la punta del case en ese eje (coordenadas
  del case: X a lo ancho, Y a lo profundo con 0 adelante, Z a lo alto con 0 en el piso).
  Un panel va por su id ("techo", "cuerpo_frente"...).
- artículo: referencia del catálogo que reemplaza a la general en esa pieza (un esquinero
  apilable sólo arriba, otro ángulo en una arista). En un panel, una placa del catálogo (se
  pasa a `paneles_material`). Vacío = la de todo el case.
- color: nombre ("negro", "rojo"...) o "#rrggbb". Vacío = el de siempre. Va a la vista 3D,
  al STEP y a la descripción de la lista de corte.
- sin_pieza: 1 = esa pieza no va (un ángulo que no se pone, una punta sin esquinero).

Cada fila reemplaza a una anterior de la misma pieza. Las medidas que cambian (el largo de los
ángulos que llegan a un esquinero más grande o más chico, los remaches, las perforaciones) salen
de acá, así que la lista de corte, los DXF, los planos, el peso y el STEP quedan iguales a la vista.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

Vec = Tuple[float, float, float]

COLORES_NOMBRE: Dict[str, str] = {
    "negro": "#1c1c1c", "blanco": "#f0f0f0", "rojo": "#c62828", "azul": "#1e5aa8", "verde": "#2e7d32",
    "amarillo": "#f2c200", "naranja": "#ef7d00", "gris": "#7d7d7d", "dorado": "#c9a227", "plata": "#c0c0c0",
}
TRAMO_MINIMO = 30.0


def color_hex(texto: Any) -> str:
    """"#rrggbb" de un color escrito por nombre o en hexadecimal; "" si no se entiende."""
    t = str(texto or "").strip().lower()
    if not t:
        return ""
    if t in COLORES_NOMBRE:
        return COLORES_NOMBRE[t]
    if re.fullmatch(r"#?[0-9a-f]{6}", t):
        return "#" + t.lstrip("#")
    if re.fullmatch(r"#?[0-9a-f]{3}", t):
        h = t.lstrip("#")
        return "#" + "".join(c * 2 for c in h)
    return ""


def nombre_color(texto: Any) -> str:
    """Cómo se escribe el color en las listas: el nombre si es uno conocido."""
    t = str(texto or "").strip()
    h = color_hex(t)
    if not h:
        return ""
    for n, v in COLORES_NOMBRE.items():
        if v == h:
            return n
    return t if not t.startswith("#") else h


@dataclass
class Cambio:
    pieza: str
    ref: str = ""
    color: str = ""          # como lo escribió el usuario
    quitar: bool = False

    @property
    def hex(self) -> str:
        return color_hex(self.color)

    def fila(self) -> list:
        return [self.pieza, self.ref, self.color, 1 if self.quitar else 0]


def _verdad(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "si", "sí", "true", "x")
    try:
        return float(v or 0) != 0
    except (TypeError, ValueError):
        return False


def cambios(P: Dict[str, Any]) -> Dict[str, Cambio]:
    """Las filas de `piezas`, por id (la última de cada pieza gana)."""
    out: Dict[str, Cambio] = {}
    for f in P.get("piezas") or []:
        if not isinstance(f, list) or not f or not isinstance(f[0], str) or not f[0].strip():
            continue
        f = list(f) + [None] * (4 - len(f))
        c = Cambio(f[0].strip(), str(f[1] or "").strip(), str(f[2] or "").strip(), _verdad(f[3]))
        if c.ref or c.color or c.quitar:
            out[c.pieza] = c
        else:
            out.pop(c.pieza, None)       # una fila vacía vuelve la pieza a la de siempre
    return out


def poner(filas: Sequence[Any], cambio: Cambio) -> List[list]:
    """`piezas` con ese cambio (reemplaza la fila de esa pieza; sin nada = la saca)."""
    out = [list(f) for f in filas or [] if not (isinstance(f, list) and f and str(f[0]).strip() == cambio.pieza)]
    if cambio.ref or cambio.color or cambio.quitar:
        out.append(cambio.fila())
    return out


# ---------------------------------------------------------------------------
# Nombres para mostrar (según cómo queda el case en el mundo: parado, acostado o al frente)
# ---------------------------------------------------------------------------

def ubicador(horizontal: bool, frontal: bool, Z: float) -> Callable[[Vec], Vec]:
    if horizontal:
        return lambda p: (Z - p[2], p[1], p[0])
    if frontal:
        return lambda p: (p[0], Z - p[2], p[1])
    return lambda p: p


def _lados(p: Vec, centro: Vec, ejes: Iterable[int]) -> List[str]:
    palabras = (("izquierda", "derecha"), ("adelante", "atrás"), ("abajo", "arriba"))
    orden = sorted(ejes, key=lambda i: (2, 1, 0).index(i))       # arriba/abajo, adelante/atrás, izq/der
    return [palabras[i][1 if p[i] > centro[i] else 0] for i in orden]


# ---------------------------------------------------------------------------
# Esquineros y ángulos de arista de un case común (no las formas)
# ---------------------------------------------------------------------------

@dataclass
class General:
    """Lo de todo el case, con lo que se compara cada pieza."""
    ref_esq: str
    nombre_esq: str
    pata: float
    remaches_esq: int
    descuento: float
    ref_ar: str
    nombre_ar: str
    ala: float
    esp: float
    hibrido: bool


def _bits(*vs: float) -> str:
    return "".join("1" if v > 0 else "0" for v in vs)


def armar(geo: Dict[str, Any], X: float, Y: float, Z: float, gen: General, P: Dict[str, Any], cat,
          nombres_ar: Dict[str, str]) -> Tuple[List[dict], List[dict], List[str]]:
    """(esquineros, aristas, avisos) del case, cada uno con lo que le cambia su fila de `piezas`.

    `geo` trae las medidas del case (z_cierre, cierre_m_alto, dos_tapas, L_x...). `nombres_ar`:
    la descripción de cada tipo de arista para la lista de corte ("x", "y", "zc", "zt", "zt2")."""
    cmb = cambios(P)
    avisos: List[str] = []
    ub = ubicador(geo["horizontal"], geo["frontal"], Z)
    w0, w1 = ub((0, 0, 0)), ub((X, Y, Z))
    centro = tuple((a + b) / 2 for a, b in zip(w0, w1))
    dos = geo["dos_tapas"]
    ed = gen.descuento

    # ---- esquineros ----
    esq: List[dict] = []
    por_id: Dict[str, dict] = {}
    for z in (0.0, Z):
        for x in (0.0, X):
            for y in (0.0, Y):
                pid = "esq_" + _bits(x, y, z)
                c = cmb.get(pid)
                d = dict(id=pid, o=(x, y, z), a=(1 if x > 0 else -1, 0, 0), b=(0, 1 if y > 0 else -1, 0),
                         c=(0, 0, 1 if z > 0 else -1), grupo=("tapa" if z > 0 else ("tapa2" if dos else "cuerpo")),
                         ref=gen.ref_esq, nombre=gen.nombre_esq, pata=gen.pata, remaches=gen.remaches_esq,
                         descuento=ed, color="", quitar=False, cambiada=False)
                wp = ub((x, y, z))
                d["etiqueta"] = "Esquinero " + " ".join(_lados(wp, centro, (0, 1, 2)))
                if c is not None:
                    d["cambiada"] = True
                    if c.ref and c.ref != gen.ref_esq:
                        if cat.existe(c.ref) and cat.categoria(c.ref) == "esquinero":
                            pata = float(cat.dato(c.ref, "pata", gen.pata))
                            paso = float(cat.dato(c.ref, "paso", 0) or 0)
                            d.update(ref=c.ref, nombre=cat.nombre(c.ref), pata=pata,
                                     remaches=int(cat.dato(c.ref, "remaches", 3)),
                                     descuento=15.0 if paso > 0 else pata + 2)
                            if pata > gen.pata + 0.01:
                                avisos.append(f"{d['etiqueta']}: el {c.ref} tiene pata de {_f(pata)} mm (el resto, "
                                              f"{_f(gen.pata)} mm). Verificá que no pise ruedas, manijas ni cierres.")
                            if paso > 0 and not gen.hibrido and abs(paso - gen.ala) > 2:
                                avisos.append(f"{d['etiqueta']}: el {c.ref} tiene paso de perfil de {_f(paso)} mm y "
                                              f"el ángulo es de {_f(gen.ala)} mm: no calzan.")
                        else:
                            avisos.append(f"{d['etiqueta']}: «{c.ref}» no es un esquinero del catálogo; queda el de siempre.")
                    d["color"] = c.hex
                    if c.quitar:
                        d["quitar"] = True
                        d["descuento"] = ed
                        avisos.append(f"{d['etiqueta']}: sin esquinero. Los ángulos llegan igual que con "
                                      "esquinero: tapá la punta o cortalos a inglete.")
                esq.append(d)
                por_id[pid] = d

    def desc(x: float, y: float, z: float) -> float:
        return por_id["esq_" + _bits(x, y, z)]["descuento"]

    # ---- ángulos (o perfiles híbridos) de las aristas ----
    ar: List[dict] = []
    zc1, zc2 = geo["z_cierre"], geo["z_cierre2"]
    m_alto, h_alto = geo["cierre_m_alto"], geo["cierre_h_alto"]

    def agregar(pid: str, tipo: str, o: Vec, a: Vec, b: Vec, c: Vec, L: float, grupo: str,
                L_base: float = 0.0) -> None:
        d = dict(id=pid, tipo=tipo, o=o, a=a, b=b, c=c, L=L, grupo=grupo, ref=gen.ref_ar, nombre=gen.nombre_ar,
                 ala=gen.ala, esp=gen.esp, color="", quitar=False, cambiada=False, descripcion=nombres_ar[tipo])
        medio = tuple(o[i] + c[i] * L / 2 for i in range(3))
        eje = max(range(3), key=lambda i: abs(ub(tuple(c))[i] - ub((0, 0, 0))[i]))
        quien = {"zc": " (cuerpo)", "zt": " (tapa)", "zt2": " (segunda tapa)"}.get(tipo, "")
        d["etiqueta"] = ("Ángulo " if not gen.hibrido else "Perfil ") + \
            " ".join(_lados(ub(medio), centro, [i for i in range(3) if i != eje])) + quien
        k = cmb.get(pid)
        if k is not None:
            d["cambiada"] = True
            if k.ref and k.ref != gen.ref_ar:
                if gen.hibrido:
                    avisos.append(f"{d['etiqueta']}: en el sistema híbrido el perfil no se cambia por arista; "
                                  "sólo el color.")
                elif cat.existe(k.ref) and cat.categoria(k.ref) == "angulo":
                    d.update(ref=k.ref, nombre=cat.nombre(k.ref), ala=float(cat.dato(k.ref, "ala", gen.ala)),
                             esp=float(cat.dato(k.ref, "esp", gen.esp)))
                else:
                    avisos.append(f"{d['etiqueta']}: «{k.ref}» no es un ángulo del catálogo; queda el de siempre.")
            d["color"] = k.hex
            if k.quitar:
                if gen.hibrido:
                    avisos.append(f"{d['etiqueta']}: en el sistema híbrido los paneles van encastrados en el "
                                  "perfil; no se puede sacar.")
                else:
                    d["quitar"] = True
        if L >= TRAMO_MINIMO:
            ar.append(d)
        elif L_base >= TRAMO_MINIMO and not d["quitar"]:
            avisos.append(f"{d['etiqueta']}: con el esquinero de esa punta el tramo daría {_f(L)} mm y se omite; "
                          "verificá que la pata del esquinero no pise el perfil de cierre.")

    for z in (0.0, Z):
        g = "tapa" if z > 0 else ("tapa2" if dos else "cuerpo")
        sz = 1 if z > 0 else -1
        for y in (0.0, Y):
            sy = 1 if y > 0 else -1
            d0, d1 = desc(0.0, y, z), desc(X, y, z)
            agregar("ar_x_" + _bits(y, z), "x", (d0, y, z), (0, sy, 0), (0, 0, sz), (1, 0, 0), X - d0 - d1, g,
                    X - 2 * ed)
        for x in (0.0, X):
            sx = 1 if x > 0 else -1
            d0, d1 = desc(x, 0.0, z), desc(x, Y, z)
            agregar("ar_y_" + _bits(x, z), "y", (x, d0, z), (sx, 0, 0), (0, 0, sz), (0, 1, 0), Y - d0 - d1, g,
                    Y - 2 * ed)
    for x in (0.0, X):
        sx = 1 if x > 0 else -1
        for y in (0.0, Y):
            sy = 1 if y > 0 else -1
            xy = _bits(x, y)
            if dos:
                agregar("ar_zc_" + xy, "zc", (x, y, zc2 + m_alto), (sx, 0, 0), (0, sy, 0), (0, 0, 1), geo["L_zc"], "cuerpo")
                db = desc(x, y, 0.0)
                agregar("ar_zt2_" + xy, "zt2", (x, y, db), (sx, 0, 0), (0, sy, 0), (0, 0, 1),
                        geo["L_zt2"] + ed - db, "tapa2", geo["L_zt2"])
            else:
                db = desc(x, y, 0.0)
                agregar("ar_zc_" + xy, "zc", (x, y, db), (sx, 0, 0), (0, sy, 0), (0, 0, 1), geo["L_zc"] + ed - db,
                        "cuerpo", geo["L_zc"])
            dt = desc(x, y, Z)
            agregar("ar_zt_" + xy, "zt", (x, y, zc1 + h_alto), (sx, 0, 0), (0, sy, 0), (0, 0, 1),
                    geo["L_zt"] + ed - dt, "tapa", geo["L_zt"])

    conocidas = set(por_id) | {"ar_x_" + _bits(a, b) for a in (0, 1) for b in (0, 1)} | \
        {"ar_y_" + _bits(a, b) for a in (0, 1) for b in (0, 1)} | \
        {f"ar_{t}_" + _bits(a, b) for t in ("zc", "zt", "zt2") for a in (0, 1) for b in (0, 1)}
    paneles = {c["id"] for c in geo.get("colocaciones", [])}
    for pid in cmb:
        if pid not in conocidas and pid not in paneles:
            avisos.append(f"Piezas sueltas: «{pid}» no es una pieza de este case.")
    return esq, ar, _juntar(avisos)


def _juntar(avisos: List[str]) -> List[str]:
    """Un aviso por problema, con las piezas a las que les pasa ("Esquinero A, B: ...")."""
    grupos: Dict[str, List[str]] = {}
    for a in avisos:
        quien, _, resto = a.partition(": ")
        grupos.setdefault(resto, []).append(quien)
    out = []
    for resto, quienes in grupos.items():
        if len(quienes) == 1:
            out.append(f"{quienes[0]}: {resto}")
        else:
            palabra = quienes[0].split(" ", 1)[0]
            lugares = [q.split(" ", 1)[1] if q.startswith(palabra + " ") else q for q in quienes]
            out.append(f"{palabra}{'es' if palabra.endswith('l') else 's'} {', '.join(lugares)}: {resto}")
    return out


def _f(v: float) -> str:
    return f"{float(v):.1f}".rstrip("0").rstrip(".")


def filas_perfiles(aristas: Sequence[dict]) -> List[list]:
    """Filas de la lista de corte de los ángulos: [nombre, descripción, largo, cantidad, "recto", ref],
    agrupadas por tipo de arista (en el mismo orden que siempre) y por perfil, largo y color."""
    out: List[list] = []
    for tipo in ("x", "y", "zc", "zt", "zt2"):
        grupo: Dict[tuple, list] = {}
        for a in aristas:
            if a["tipo"] != tipo or a["quitar"]:
                continue
            desc = a["descripcion"] + (f", {nombre_color(a['color'])}" if a["color"] else "")
            clave = (a["nombre"], desc, round(a["L"], 3), a["ref"])
            if clave in grupo:
                grupo[clave][3] += 1
            else:
                grupo[clave] = [a["nombre"], desc, a["L"], 1, "recto", a["ref"]]
        out.extend(grupo.values())
    return out


def filas_esquineros(esquineros: Sequence[dict]) -> List[list]:
    """Filas de herrajes de los esquineros: [nombre, cantidad, detalle, ref]."""
    grupo: Dict[tuple, list] = {}
    for e in esquineros:
        if e["quitar"]:
            continue
        det = f"pata {_f(e['pata'])} mm" + (f", {nombre_color(e['color'])}" if e["color"] else "")
        clave = (e["nombre"], det, e["ref"])
        if clave in grupo:
            grupo[clave][1] += 1
        else:
            grupo[clave] = [e["nombre"], 1, det, e["ref"]]
    filas = list(grupo.values())
    if len(filas) > 1:        # dónde va cada uno
        donde: Dict[tuple, List[str]] = {}
        for e in esquineros:
            if not e["quitar"]:
                det = f"pata {_f(e['pata'])} mm" + (f", {nombre_color(e['color'])}" if e["color"] else "")
                donde.setdefault((e["nombre"], det, e["ref"]), []).append(e)
        for f in filas:
            es = donde[(f[0], f[2], f[3])]
            if 0 < len(es) < 8 and all(e["cambiada"] for e in es):
                f[2] += "; " + ", ".join(e["etiqueta"].replace("Esquinero ", "") for e in es)
    return filas


def remaches_esquineros(esquineros: Sequence[dict]) -> int:
    return sum(int(e["remaches"]) for e in esquineros if not e["quitar"])


# ---------------------------------------------------------------------------
# Lista de piezas para elegir (tabla y clic en el 3D)
# ---------------------------------------------------------------------------

def opciones(res) -> List[Tuple[str, str]]:
    """[(id, nombre)] de las piezas que se pueden cambiar en este case."""
    geo = res.valores.get("geo") or {}
    out: List[Tuple[str, str]] = []
    for e in geo.get("esquineros_case") or []:
        out.append((e["id"], e["etiqueta"]))
    for a in geo.get("aristas_case") or []:
        out.append((a["id"], a["etiqueta"]))
    for p in res.paneles:
        if not p.id.startswith(("base_ruedas", "bandeja")):
            out.append((p.id, f"Panel: {p.nombre}"))
    return out


def tipo_de(pid: str) -> str:
    """"esquinero", "arista" o "panel"."""
    if pid.startswith("esq_"):
        return "esquinero"
    if pid.startswith("ar_"):
        return "arista"
    return "panel"


def iguales(pid: str, cual: str, res) -> List[str]:
    """Las piezas del mismo tipo para «aplicar a…»: cual = "tapa", "cuerpo" o "todas"."""
    geo = res.valores.get("geo") or {}
    t = tipo_de(pid)
    lista = geo.get("esquineros_case") if t == "esquinero" else (geo.get("aristas_case") if t == "arista" else None)
    if not lista:
        return [pid]
    if cual == "todas":
        return [e["id"] for e in lista]
    grupos = {"tapa": ("tapa",), "cuerpo": ("cuerpo", "tapa2")}.get(cual, ())
    return [e["id"] for e in lista if e["grupo"] in grupos] or [pid]
