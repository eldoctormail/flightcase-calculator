"""Optimización de cortes en la placa.

Acomoda todas las piezas del case (por material) en placas enteras con el método MaxRects,
probando varias reglas de acomodo y órdenes de piezas, y se queda con el plan que usa menos
placas y deja el retazo más grande. Además escribe un DXF por placa, con cada pieza en su
lugar (contorno, calados, rebajes y marcas), listo para la router CNC o la escuadradora.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

Rect = Tuple[float, float, float, float]          # x, y, ancho, alto

REGLAS = ("lado_corto", "lado_largo", "area", "abajo_izquierda")
ORDENES: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    "area": lambda p: (p["w"] * p["h"], max(p["w"], p["h"])),
    "lado_mayor": lambda p: (max(p["w"], p["h"]), min(p["w"], p["h"])),
    "perimetro": lambda p: (p["w"] + p["h"], p["w"] * p["h"]),
    "ancho": lambda p: (p["w"], p["h"]),
    "alto": lambda p: (p["h"], p["w"]),
}


# ---------------------------------------------------------------------------
# MaxRects
# ---------------------------------------------------------------------------

def _puntaje(regla: str, fr: Rect, w: float, h: float) -> Tuple[float, float]:
    sobra_w, sobra_h = fr[2] - w, fr[3] - h
    if regla == "lado_corto":
        return min(sobra_w, sobra_h), max(sobra_w, sobra_h)
    if regla == "lado_largo":
        return max(sobra_w, sobra_h), min(sobra_w, sobra_h)
    if regla == "area":
        return fr[2] * fr[3] - w * h, min(sobra_w, sobra_h)
    return fr[1] + h, fr[0]                         # abajo a la izquierda


def _partir(libres: List[Rect], x: float, y: float, w: float, h: float) -> List[Rect]:
    nuevos = []
    for f in libres:
        fx, fy, fw, fh = f
        if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
            nuevos.append(f)
            continue
        if x > fx:
            nuevos.append((fx, fy, x - fx, fh))
        if x + w < fx + fw:
            nuevos.append((x + w, fy, fx + fw - x - w, fh))
        if y > fy:
            nuevos.append((fx, fy, fw, y - fy))
        if y + h < fy + fh:
            nuevos.append((fx, y + h, fw, fy + fh - y - h))
    nuevos = [f for f in nuevos if f[2] > 1 and f[3] > 1]
    limpios = []
    for i, a in enumerate(nuevos):
        contenido = any(i != j and a[0] >= b[0] - 1e-6 and a[1] >= b[1] - 1e-6 and
                        a[0] + a[2] <= b[0] + b[2] + 1e-6 and a[1] + a[3] <= b[1] + b[3] + 1e-6 and
                        (a != b or i > j) for j, b in enumerate(nuevos))
        if not contenido:
            limpios.append(a)
    return limpios


def _acomodar(pend: List[Dict[str, Any]], L: float, A: float, kerf: float, margen: float,
              rotar: bool, regla: str) -> List[Dict[str, Any]]:
    """Un plan con una regla y un orden fijos. Las piezas que no entran se descartan antes."""
    W, H = L - 2 * margen + kerf, A - 2 * margen + kerf     # el kerf del último corte cae en el margen
    placas: List[Dict[str, Any]] = []
    for p in pend:
        pw, ph = p["w"] + kerf, p["h"] + kerf
        mejor = None
        for pi, pl in enumerate(placas):
            for fr in pl["libres"]:
                for rot, (w, h) in ((False, (pw, ph)), (True, (ph, pw))):
                    if (rot and (not rotar or pw == ph)) or w > fr[2] + 1e-6 or h > fr[3] + 1e-6:
                        continue
                    pt = _puntaje(regla, fr, w, h)
                    if mejor is None or pt < mejor[0]:
                        mejor = (pt, pi, fr, rot, w, h)
        if mejor is None:
            placas.append(dict(libres=[(0.0, 0.0, W, H)], piezas=[]))
            rot = not (pw <= W + 1e-6 and ph <= H + 1e-6)
            w, h = (ph, pw) if rot else (pw, ph)
            mejor = ((0, 0), len(placas) - 1, (0.0, 0.0, W, H), rot, w, h)
        _, pi, fr, rot, w, h = mejor
        pl = placas[pi]
        pl["piezas"].append(dict(p, x=fr[0] + margen, y=fr[1] + margen, rot=rot,
                                 dw=p["h"] if rot else p["w"], dh=p["w"] if rot else p["h"]))
        pl["libres"] = _partir(pl["libres"], fr[0], fr[1], w, h)
    return placas


def _entra(p: Dict[str, Any], L: float, A: float, kerf: float, margen: float, rotar: bool) -> bool:
    W, H = L - 2 * margen + kerf, A - 2 * margen + kerf
    pw, ph = p["w"] + kerf, p["h"] + kerf
    return (pw <= W + 1e-6 and ph <= H + 1e-6) or (rotar and ph <= W + 1e-6 and pw <= H + 1e-6)


def retazo_mayor(pl: Dict[str, Any], kerf: float = 0.0) -> Rect:
    """El rectángulo libre más grande de la placa (en coordenadas de la placa), sin el kerf."""
    if not pl.get("libres"):
        return (0.0, 0.0, 0.0, 0.0)
    f = max(pl["libres"], key=lambda r: r[2] * r[3])
    m = pl.get("margen", 0.0)
    return (f[0] + m, f[1] + m, max(f[2] - kerf, 0.0), max(f[3] - kerf, 0.0))


def optimizar(sueltas: Iterable[Dict[str, Any]], L: float, A: float, kerf: float, margen: float,
              rotar: bool = True) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Acomoda las piezas sueltas (dicts con w y h, una por unidad) en placas de L x A.

    Prueba todas las reglas y órdenes y elige el plan con menos placas; a igualdad, el que deja
    el retazo libre más grande (más fácil de aprovechar en el próximo case). Devuelve
    (placas, no_entran). Cada placa: piezas (con x, y, rot, dw, dh), libres, L, A, margen,
    aprovechamiento (0-1)."""
    sueltas = list(sueltas)
    no_entran = [p for p in sueltas if not _entra(p, L, A, kerf, margen, rotar)]
    for p in no_entran:
        p["no_entra"] = True
    validas = [p for p in sueltas if not p.get("no_entra")]
    mejor, mejor_pt = None, None
    for orden in ORDENES.values():
        pend = sorted(validas, key=orden, reverse=True)
        for regla in REGLAS:
            plan = _acomodar(pend, L, A, kerf, margen, rotar, regla)
            libre = max((f[2] * f[3] for f in plan[-1]["libres"]), default=0.0) if plan else 0.0
            pt = (len(plan), -libre)
            if mejor_pt is None or pt < mejor_pt:
                mejor, mejor_pt = plan, pt
    placas = mejor or []
    for pl in placas:
        usado = sum(p["w"] * p["h"] for p in pl["piezas"])
        pl.update(L=L, A=A, margen=margen, kerf=kerf, aprovechamiento=usado / (L * A))
    return placas, no_entran


# ---------------------------------------------------------------------------
# Todas las piezas del case, por material
# ---------------------------------------------------------------------------

def armar_placas(d: Dict[str, Any], piezas: List[Dict[str, Any]], rotar: bool = True,
                 cantidad: int = 1) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Placas de todo el pedido (`cantidad` cases), agrupadas por material. `piezas` es lo que
    devuelve agrupar_piezas (más los extras). Devuelve (placas, avisos)."""
    material_principal = d["info"]["material"]
    por_material: "OrderedDict[str, list]" = OrderedDict()
    for pz in piezas:
        corto = pz["nombre"] if pz.get("extra") else \
            d["paneles"][pz["ids"][0]]["nombre"].replace(" cuerpo", "").replace(" tapa", "")
        mat = pz.get("material", material_principal)
        for _ in range(pz["cant"] * cantidad):
            por_material.setdefault(mat, []).append(dict(num=pz["num"], w=pz["w"], h=pz["h"], nombre_corto=corto))
    from .planos.generar import medidas_placa
    pl = d["info"]["placa"]
    kerf, margen = float(pl[2]), float(pl[3])
    placas, avisos = [], []
    for mat, sueltas in por_material.items():
        L, A, _ref = medidas_placa(d, mat)
        pls, ne = optimizar(sueltas, L, A, kerf, margen, rotar=rotar)
        for p in pls:
            p["material"] = mat
        placas += pls
        avisos += [f"La pieza {p['num']} ({_f(p['w'])} x {_f(p['h'])}) no entra en la placa de "
                   f"{_f(L)} x {_f(A)}." for p in ne]
    return placas, avisos


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def resumen(placas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Por material: placas, aprovechamiento total y el retazo más grande que queda."""
    out: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for pl in placas:
        r = out.setdefault(pl["material"], dict(material=pl["material"], placas=0, area=0.0, usado=0.0,
                                                L=pl["L"], A=pl["A"], retazo=(0.0, 0.0, 0.0, 0.0)))
        r["placas"] += 1
        r["area"] += pl["L"] * pl["A"]
        r["usado"] += pl["aprovechamiento"] * pl["L"] * pl["A"]
        ret = retazo_mayor(pl, pl.get("kerf", 0.0))
        if ret[2] * ret[3] > r["retazo"][2] * r["retazo"][3]:
            r["retazo"] = ret
    for r in out.values():
        r["aprovechamiento"] = r["usado"] / r["area"] if r["area"] else 0.0
    return list(out.values())


# ---------------------------------------------------------------------------
# DXF por placa
# ---------------------------------------------------------------------------

def _transformar(x0: float, y0: float, alto: float, rot: bool):
    """Punto de la pieza (u, v) -> punto en la placa. Girada = 90° antihorario."""
    if rot:
        return lambda u, v: (x0 + alto - v, y0 + u)
    return lambda u, v: (x0 + u, y0 + v)


def _texto(capa: str, x: float, y: float, alto: float, texto: str, angulo: float = 0.0) -> str:
    from .produccion import _n
    texto = texto.replace("\n", " ")
    return (f"  0\nTEXT\n  8\n{capa}\n 10\n{_n(x)}\n 20\n{_n(y)}\n 30\n0\n 40\n{_n(alto)}\n  1\n{texto}\n"
            f" 50\n{_n(angulo)}\n 72\n1\n 73\n2\n 11\n{_n(x)}\n 21\n{_n(y)}\n 31\n0\n")


def placa_dxf(pl: Dict[str, Any], piezas_por_num: Dict[int, Dict[str, Any]],
              trazos_por_num: Optional[Dict[int, List[tuple]]] = None, rotulos: bool = True) -> str:
    """DXF de una placa: el borde de la placa en la capa PLACA, cada pieza en su lugar con el
    contorno y los calados pasantes en la capa 0, rebajes en REBAJE, marcas de herrajes en MARCA,
    logos en GRABADO y el número de pieza en TEXTO (para apagar en el CAM)."""
    from .produccion import _dxf_linea, _dxf_polilinea, _rect_redondeado
    trazos_por_num = trazos_por_num or {}
    ent: List[str] = []
    L, A = pl["L"], pl["A"]
    borde = [(0, 0), (L, 0), (L, A), (0, A)]
    ent += [_dxf_linea("PLACA", borde[i], borde[(i + 1) % 4]) for i in range(4)]
    capas = [("PLACA", 8), ("0", 7), ("REBAJE", 1)]
    for p in pl["piezas"]:
        pz = piezas_por_num.get(p["num"], {})
        w, h, rot = p["w"], p["h"], p["rot"]
        t = _transformar(p["x"], p["y"], h, rot)
        esq = [t(0, 0), t(w, 0), t(w, h), t(0, h)]
        ent += [_dxf_linea("0", esq[i], esq[(i + 1) % 4]) for i in range(4)]
        for c in pz.get("calados", []):
            capa = "REBAJE" if c["tipo"] == "rebaje" else "0"
            if c.get("puntos"):
                ent += [_dxf_polilinea(capa, [t(*q) for q in pts]) for pts in c["puntos"]]
                continue
            r = 0.0 if c["tipo"] == "rebaje" else c.get("r", 0.0)
            cx, cy = t(c["cx"], c["cy"])
            cw, ch = (c["h"], c["w"]) if rot else (c["w"], c["h"])
            ent += _rect_redondeado(capa, cx, cy, cw, ch, r)
        for capa, pts in trazos_por_num.get(p["num"], []):
            q = [t(*a) for a in pts]
            ent += [_dxf_linea(capa, q[i], q[i + 1]) for i in range(len(q) - 1)]
            if capa not in [c[0] for c in capas]:
                capas.append((capa, 5 if capa == "MARCA" else 3))
        if rotulos:
            cx, cy = p["x"] + p["dw"] / 2, p["y"] + p["dh"] / 2
            alto_txt = max(min(25.0, min(p["dw"], p["dh"]) / 4), 4.0)
            ent.append(_texto("TEXTO", cx, cy, alto_txt, f"P{p['num']}",
                              90.0 if p["dh"] > p["dw"] * 1.3 else 0.0))
    if rotulos:
        capas.append(("TEXTO", 4))
    tabla = "".join(f"  0\nLAYER\n  2\n{c}\n 70\n0\n 62\n{col}\n  6\nCONTINUOUS\n" for c, col in capas)
    return (f"  0\nSECTION\n  2\nTABLES\n  0\nTABLE\n  2\nLAYER\n 70\n{len(capas)}\n" + tabla +
            "  0\nENDTAB\n  0\nENDSEC\n"
            "  0\nSECTION\n  2\nENTITIES\n" + "".join(ent) + "  0\nENDSEC\n  0\nEOF\n")


def _nombre_archivo(i: int, material: str) -> str:
    import unicodedata
    sin_tildes = unicodedata.normalize("NFKD", material).encode("ascii", "ignore").decode()
    limpio = "".join(ch if ch.isalnum() else "_" for ch in sin_tildes).strip("_")
    while "__" in limpio:
        limpio = limpio.replace("__", "_")
    return f"placa_{i:02d}_{limpio or 'placa'}.dxf"


def escribir_dxf_placas(placas: List[Dict[str, Any]], piezas: List[Dict[str, Any]], carpeta: str,
                        trazos_por_num: Optional[Dict[int, List[tuple]]] = None) -> List[str]:
    """Un DXF por placa en `carpeta`. Devuelve las rutas."""
    os.makedirs(carpeta, exist_ok=True)
    por_num = {pz["num"]: pz for pz in piezas}
    rutas = []
    for i, pl in enumerate(placas, 1):
        ruta = os.path.join(carpeta, _nombre_archivo(i, pl["material"]))
        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(placa_dxf(pl, por_num, trazos_por_num))
        pl["dxf"] = os.path.basename(ruta)
        rutas.append(ruta)
    return rutas


def filas_csv(placas: List[Dict[str, Any]], carpeta_dxf: str = "placas/") -> List[List[str]]:
    """Filas para placas.csv: una por placa. `carpeta_dxf`: dónde quedan los DXF, relativo al CSV."""
    def n(v: float) -> str:
        return _f(v).replace(".", ",")
    filas = [["Placa", "Material", "Medidas", "Piezas", "Aprovechamiento", "Retazo libre más grande", "Archivo"]]
    for i, pl in enumerate(placas, 1):
        cuenta: "OrderedDict[str, int]" = OrderedDict()
        for p in pl["piezas"]:
            k = f"P{p['num']}"
            cuenta[k] = cuenta.get(k, 0) + 1
        ret = retazo_mayor(pl, pl.get("kerf", 0.0))
        filas.append([str(i), pl["material"], f"{n(pl['L'])} x {n(pl['A'])}",
                      ", ".join(f"{k} x{c}" if c > 1 else k for k, c in cuenta.items()),
                      f"{round(100 * pl['aprovechamiento'])}%",
                      f"{n(ret[2])} x {n(ret[3])}" if ret[2] * ret[3] > 0 else "",
                      carpeta_dxf + pl.get("dxf", "")])
    return filas
