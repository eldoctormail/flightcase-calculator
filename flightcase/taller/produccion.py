"""Paquete de producción a partir de las reglas del taller, sin OpenSCAD.

Hace lo mismo que `generar.py` del generador de OpenSCAD (DXF por pieza, listas CSV y
planos.pdf), pero leyendo el resultado de `flightcase.taller.modelo.calcular` en lugar
de ejecutar OpenSCAD. Las funciones de agrupado, placas, barras, listas y PDF son las
mismas del generador (flightcase/taller/planos/generar.py).
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .modelo import ResultadoTaller, fmt
from .planos import generar as gen


# ---------------------------------------------------------------------------
# Resultado del modelo -> diccionario `d` de generar.py
# ---------------------------------------------------------------------------

def _linea(tipo: str, *campos: Any) -> str:
    return "@@" + "|".join([tipo] + [c if isinstance(c, str) else fmt(c) for c in campos])


def lineas_datos(res: ResultadoTaller) -> List[str]:
    """Las mismas líneas @@TIPO|... que imprime OpenSCAD con parte="datos"."""
    out = [_linea("INFO", k, *v) for k, v in res.info.items()]
    out += [_linea("PANEL", p.id, p.nombre, p.grupo, p.ancho, p.alto) for p in res.paneles]
    out += [_linea("CALADO", c.panel, c.tipo, c.cx, c.cy, c.ancho, c.alto, c.radio) for c in res.calados]
    out += [_linea("MARCA", m.panel, m.tipo, m.x, m.y, m.ancho, m.alto, m.texto) for m in res.marcas]
    out += [_linea("PERFIL", p.nombre, p.descripcion, p.largo, p.cantidad, p.corte, p.ref) for p in res.perfiles]
    out += [_linea("EXTRA", *e) for e in res.extras]
    out += [_linea("HERRAJE", h.nombre, h.cantidad, h.detalle, h.ref) for h in res.herrajes]
    out += [_linea("PANELMAT", *m) for m in res.panelmat]
    out += [_linea("BANDEJA", *b) for b in res.bandejas]
    out += [_linea("AVISO", a) for a in res.avisos]
    return out


def datos(res: ResultadoTaller) -> Dict[str, Any]:
    """Diccionario `d` con la forma que usan las funciones de generar.py. Los herrajes puestos
    a mano van además en d["manuales"] (por panel, en coordenadas del panel)."""
    d = gen.parsear_datos(lineas_datos(res))
    d["manuales"] = manuales_por_panel(res)
    d["peso"] = res.valores.get("peso")
    return d


def manuales_por_panel(res: ResultadoTaller) -> Dict[str, List[Dict[str, Any]]]:
    man = res.valores.get("manuales")
    out: Dict[str, List[Dict[str, Any]]] = {}
    if man is None:
        return out
    for c in man.colocados:
        if not c.panel or c.forma == "junta":
            continue
        out.setdefault(c.panel, []).append(dict(
            nombre=c.nombre, forma=c.forma, categoria=c.categoria, x=c.px, y=c.py, w=c.pw, h=c.ph,
            lineas=c.lineas_panel, modo=c.fila.modo if c.forma == "logo" else ""))
    return out


def trazos_manuales(manuales: List[Dict[str, Any]]) -> List[tuple]:
    """(capa, polilínea) para el DXF: contorno de cada herraje de superficie en MARCA y el dibujo
    de los logos (en GRABADO si se graba)."""
    out = []
    for hm in manuales:
        x0, y0, x1, y1 = hm["x"] - hm["w"] / 2, hm["y"] - hm["h"] / 2, hm["x"] + hm["w"] / 2, hm["y"] + hm["h"] / 2
        grabado = hm.get("modo") == "grabado"
        if hm["forma"] == "pie":
            r = hm["w"] / 2
            out.append(("MARCA", [(hm["x"] + r * math.cos(2 * math.pi * k / 36), hm["y"] + r * math.sin(2 * math.pi * k / 36))
                                  for k in range(37)]))
        elif hm["forma"] != "calado" and not grabado:
            out.append(("MARCA", [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]))
        for ln in hm.get("lineas", []):
            out.append(("GRABADO" if grabado else "MARCA", list(ln)))
    return out


# ---------------------------------------------------------------------------
# DXF (R12, líneas y arcos en mm, vista desde afuera como panel_2d de OpenSCAD)
# ---------------------------------------------------------------------------

def _n(v: float) -> str:
    return f"{round(v, 4):g}"


def _dxf_linea(capa: str, a, b) -> str:
    return f"  0\nLINE\n  8\n{capa}\n 10\n{_n(a[0])}\n 20\n{_n(a[1])}\n 11\n{_n(b[0])}\n 21\n{_n(b[1])}\n"


def _dxf_arco(capa: str, c, r: float, a0: float, a1: float) -> str:
    return (f"  0\nARC\n  8\n{capa}\n 10\n{_n(c[0])}\n 20\n{_n(c[1])}\n 40\n{_n(r)}\n"
            f" 50\n{_n(a0)}\n 51\n{_n(a1)}\n")


def _dxf_polilinea(capa: str, pts) -> str:
    """Polilínea cerrada (POLYLINE de R12, que lee cualquier CAM): un calado de espuma con forma."""
    vert = "".join(f"  0\nVERTEX\n  8\n{capa}\n 10\n{_n(x)}\n 20\n{_n(y)}\n 30\n0\n" for x, y in pts)
    return (f"  0\nPOLYLINE\n  8\n{capa}\n 66\n1\n 10\n0\n 20\n0\n 30\n0\n 70\n1\n" + vert +
            f"  0\nSEQEND\n  8\n{capa}\n")


def _rect_redondeado(capa: str, cx: float, cy: float, w: float, h: float, r: float) -> List[str]:
    """Rectángulo centrado con esquinas redondeadas (mismo recorte de radio que rect_redondeado)."""
    rr = min(r, w / 2 - 0.01, h / 2 - 0.01)
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    if rr <= 0:
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [_dxf_linea(capa, pts[i], pts[(i + 1) % 4]) for i in range(4)]
    return [
        _dxf_linea(capa, (x0 + rr, y0), (x1 - rr, y0)),
        _dxf_arco(capa, (x1 - rr, y0 + rr), rr, 270, 360),
        _dxf_linea(capa, (x1, y0 + rr), (x1, y1 - rr)),
        _dxf_arco(capa, (x1 - rr, y1 - rr), rr, 0, 90),
        _dxf_linea(capa, (x1 - rr, y1), (x0 + rr, y1)),
        _dxf_arco(capa, (x0 + rr, y1 - rr), rr, 90, 180),
        _dxf_linea(capa, (x0, y1 - rr), (x0, y0 + rr)),
        _dxf_arco(capa, (x0 + rr, y0 + rr), rr, 180, 270),
    ]


def panel_dxf(ancho: float, alto: float, calados: List[Dict[str, Any]] = (), trazos: List[tuple] = ()) -> str:
    """DXF de un panel: contorno y calados pasantes en la capa 0 (como OpenSCAD) y
    rebajes (no pasantes) en la capa REBAJE. `trazos` (capa, polilínea) agrega las marcas
    de los herrajes puestos a mano (capa MARCA) y los logos grabados (capa GRABADO)."""
    ent: List[str] = []
    esquinas = [(0, 0), (ancho, 0), (ancho, alto), (0, alto)]
    ent += [_dxf_linea("0", esquinas[i], esquinas[(i + 1) % 4]) for i in range(4)]
    for c in calados:
        capa = "REBAJE" if c["tipo"] == "rebaje" else "0"
        if c.get("puntos"):   # calado de espuma con forma (redondo, dedos, contorno)
            ent += [_dxf_polilinea(capa, pts) for pts in c["puntos"]]
            continue
        r = 0.0 if c["tipo"] == "rebaje" else c.get("r", 0.0)
        ent += _rect_redondeado(capa, c["cx"], c["cy"], c["w"], c["h"], r)
    capas = [("0", 7), ("REBAJE", 1)]
    for capa, pts in trazos:
        ent += [_dxf_linea(capa, pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        if capa not in [c[0] for c in capas]:
            capas.append((capa, 5 if capa == "MARCA" else 3))
    tabla = "".join(f"  0\nLAYER\n  2\n{c}\n 70\n0\n 62\n{col}\n  6\nCONTINUOUS\n" for c, col in capas)
    return (f"  0\nSECTION\n  2\nTABLES\n  0\nTABLE\n  2\nLAYER\n 70\n{len(capas)}\n" + tabla +
            "  0\nENDTAB\n  0\nENDSEC\n"
            "  0\nSECTION\n  2\nENTITIES\n" + "".join(ent) + "  0\nENDSEC\n  0\nEOF\n")


def largo_contornos(texto_dxf: str) -> float:
    """Suma de largos de LINE y ARC de un DXF (para comparar con el de OpenSCAD)."""
    v = [x.strip() for x in texto_dxf.splitlines()]
    total, i = 0.0, 0
    while i < len(v):
        if v[i] in ("LINE", "ARC") and i > 0 and v[i - 1] == "0":
            tipo, campos, j = v[i], {}, i + 1
            while j + 1 < len(v) and v[j] != "0":
                campos[v[j]] = float(v[j + 1]) if v[j] not in ("8",) else v[j + 1]
                j += 2
            if tipo == "LINE":
                total += math.hypot(campos["11"] - campos["10"], campos["21"] - campos["20"])
            else:
                total += campos["40"] * math.radians((campos["51"] - campos["50"]) % 360 or 360)
            i = j
        else:
            i += 1
    return total


# ---------------------------------------------------------------------------
# Paquete completo
# ---------------------------------------------------------------------------

@dataclass
class PaqueteTaller:
    carpeta: str
    archivos: List[str] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    piezas: List[Dict[str, Any]] = field(default_factory=list)
    placas: List[Dict[str, Any]] = field(default_factory=list)
    barras: Dict[str, Any] = field(default_factory=dict)


def _vistas_extra(d: Dict[str, Any], carpeta: str) -> list:
    """Dibujos 2D que generar.py agrega al PDF sin necesitar renders 3D."""
    from .planos.instructivo import fmt as fmt_i
    from .planos import detalle_junta
    vistas = []
    ci = d["info"].get("cierre", [])
    if len(ci) >= 9 and ci[0] == "1" and ci[1] and float(ci[7]) > 0:
        png_p = os.path.join(carpeta, "perfil_cierre.png")
        fc = lambda v: fmt_i(v).replace(".", ",")
        gen.dibujar_perfil_cierre(png_p, d["info"],
                                  vertical=d["info"].get("tipo", ["1", "vertical"])[1] == "vertical")
        aros = [p for p in d["perfiles"] if p["corte"] != "recto"]
        vistas.append((
            "Perfil híbrido", png_p,
            f"El mismo perfil va en el cuerpo y en la tapa, girado: el panel entra {fc(float(ci[7]))} mm en el canal "
            f"y entre cantos quedan {fc(float(ci[4]) + float(ci[5]))} mm. "
            + ("Aros a inglete 45°, medidos en la punta larga: los largos están en la hoja de perfiles; "
               "en el aro del cuerpo los lados verticales van partidos en la junta de la cubierta"
               if any(p["corte"] in ("45/recto", "45/45L") for p in aros) else
               "Aros a inglete 45°, medidos en la punta larga: "
               + "; ".join(f"{p['cant']} × {fc(p['largo'])} mm ({p['desc'].split(' (')[0].lower()})" for p in aros))
            + f". Cada lado lleva {fc(float(ci[6]))} mm más por esquina porque la pared del perfil sobresale de la cara."))
        jt = [p for p in d["perfiles"] if p["corte"] == "45L/45L"]
        if jt:
            png_d = os.path.join(carpeta, "detalle_union_junta.png")
            L5, L5c = fmt_i(jt[0]["largo"]), fmt_i(jt[0]["largo"] - 2 * float(ci[2]))
            detalle_junta.dibujar(png_d, L5=L5, L5c=L5c, solo_vistas=True)
            vistas.append((
                "Detalle: unión a inglete de la junta de la cubierta", png_d,
                " ".join(f"{k}. {n}" for k, n in enumerate(detalle_junta.notas(L5, L5c), 1))))
    return vistas


def colores_placa(d: Dict[str, Any]) -> Dict[str, str]:
    """Color de la placa y de la tapa (color_placa / color_tapa del .scad, nombres CSS como en
    OpenSCAD) para los renders del case terminado. Vacío o desconocido = madera."""
    from matplotlib.colors import to_hex
    out: Dict[str, str] = {}
    col = d["info"].get("color", [])
    for grupos, nombre in ((("base", "wall"), col[0] if col else ""), (("lid",), col[1] if len(col) > 1 else "")):
        try:
            hexa = to_hex(nombre.strip().lower()) if nombre.strip() else None
        except ValueError:
            hexa = None
        if hexa:
            out.update({g: hexa for g in grupos})
    return out


def _vista_cubierta(res: ResultadoTaller, d: Dict[str, Any], carpeta: str) -> list:
    """Hoja «Cubierta removible»: el case con la cubierta en U levantada, como la hacía generar.py."""
    if not d["paneles"].get("acceso_izq", {}).get("nombre", "").endswith("cubierta"):
        return []
    from .geometria import Opciones3D, malla_3d
    from .render import renderizar
    png = os.path.join(carpeta, "cubierta.png")
    if not renderizar(malla_3d(res, Opciones3D(cubierta_abierta=300, interior=False)), png,
                      "0,0,0,68,0,35,0", "1600,1200", colores_placa(d)):
        return []
    return [("Cubierta removible", png,
             "El techo y los laterales de arriba salen juntos como una cubierta en U; la bandeja "
             "queda fija en la parte de abajo. Para sacarla: abrir las tapas, soltar los cierres "
             "de las juntas laterales y levantar.")]


def _vistas_interior(res: ResultadoTaller, carpeta: str, piezas) -> list:
    """Hojas del interior (espuma por capas, rack, cajones) con una vista 3D con las tapas abiertas."""
    if res.valores.get("interiores") is None:
        return []
    from .geometria import Opciones3D, malla_3d
    from .planos import interior as pl_int
    from .render import renderizar
    v = res.valores
    png = os.path.join(carpeta, "interior.png")
    op = Opciones3D(abrir_tapa=round(0.8 * max(v["ext_ancho"], v["ext_prof"], v["ext_alto"])))
    try:
        ok = renderizar(malla_3d(res, op), png, "0,0,0,62,0,28,0", "1600,1200")
    except Exception:
        ok = False
    return pl_int.vistas_planos(res, carpeta, piezas, png if ok else None)


def _renderizador(res: ResultadoTaller):
    """Función render(salida_png, defs, camara, tam) que espera instructivo.py, hecha con
    la vista 3D propia en lugar de OpenSCAD."""
    from .geometria import Opciones3D, malla_3d
    from .render import renderizar

    def render(salida_png: str, defs: dict, camara: str, tam: str) -> bool:
        try:
            return renderizar(malla_3d(res, Opciones3D.desde_defs(defs)), salida_png, camara, tam)
        except Exception:
            return False
    return render


def _exportar_espuma(res: ResultadoTaller, carpeta: str, paq: "PaqueteTaller") -> None:
    """Un DXF por capa de cada bloque de espuma (calados en la capa 0, rebajes en REBAJE) y
    espuma.csv con el despiece."""
    interior = res.valores.get("interiores")
    if interior is None or not interior.espumas:
        return
    os.makedirs(os.path.join(carpeta, "dxf", "espuma"), exist_ok=True)
    filas = []
    for b, bl in enumerate(interior.espumas, 1):
        for capa in bl.capas:
            nombre = f"espuma{b}_capa{capa.indice}_{fmt(capa.esp)}mm.dxf"
            ruta = os.path.join(carpeta, "dxf", "espuma", nombre)
            with open(ruta, "w", encoding="utf-8", newline="\n") as f:
                f.write(panel_dxf(capa.ancho, capa.alto, capa.calados))
            paq.archivos.append(ruta)
            pas = [c for c in capa.calados if c["tipo"] == "calado"]
            reb = [c for c in capa.calados if c["tipo"] == "rebaje"]
            filas.append([bl.nombre, capa.indice, gen.num(capa.ancho), gen.num(capa.alto), gen.num(capa.esp),
                          ", ".join(f"{c['equipo']} {gen.num(c['w'])}x{gen.num(c['h'])}" for c in pas),
                          ", ".join(f"{c['equipo']} {gen.num(c['w'])}x{gen.num(c['h'])} prof. {gen.num(c['prof'])}"
                                    for c in reb),
                          "espuma/" + nombre])
    ruta = os.path.join(carpeta, "espuma.csv")
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Bloque", "Capa", "Ancho", "Alto", "Espesor", "Calados pasantes", "Rebajes", "Archivo"])
        w.writerows(filas)
    paq.archivos.append(ruta)


def exportar(res: ResultadoTaller, carpeta: str, rotar: bool = True, pdf: bool = True,
             render_png: Optional[str] = None, instructivo: bool = True, step: bool = True) -> PaqueteTaller:
    """Escribe dxf/*.dxf (una por pieza), dxf/placas/*.dxf (una por placa, con las piezas
    acomodadas), lista_cortes.csv, placas.csv, materiales.csv, case_3d.step, planos.pdf e
    instructivo_montaje.pdf en `carpeta`. `rotar` permite girar piezas en la placa (sin veta)."""
    os.makedirs(os.path.join(carpeta, "dxf"), exist_ok=True)
    d = datos(res)
    paq = PaqueteTaller(carpeta=carpeta, avisos=list(d["avisos"]))
    if not d["paneles"]:
        paq.avisos.append("El proyecto no tiene paneles.")
        return paq

    def escribir(nombre: str, texto: str) -> None:
        ruta = os.path.join(carpeta, "dxf", nombre)
        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)
        paq.archivos.append(ruta)

    piezas = gen.agrupar_piezas(d)
    N = gen.cantidad_cases(d)
    for pz in piezas:
        pz["dxf"] = f"{pz['num']:02d}_{pz['ids'][0]}_x{pz['cant']}.dxf"
        escribir(pz["dxf"], panel_dxf(pz["w"], pz["h"], pz["calados"],
                                      trazos_manuales(d["manuales"].get(pz["ids"][0], []))))
    forro = res.valores.get("forro")
    huecos_forro = {}
    if forro is not None:
        from . import forro as _fo
        huecos_forro = {j["nombre"]: j["huecos"] for j in _fo.juntar(forro)}
    n_forro = 0
    for i, e in enumerate(d["extras"]):
        num_p = len(piezas) + 1
        es_forro = e["nombre"] in huecos_forro
        if es_forro:
            n_forro += 1
        nombre = (f"{num_p:02d}_forro{n_forro}_x{e['cant']}.dxf" if es_forro
                  else f"{num_p:02d}_extra{i + 1}_x{e['cant']}.dxf")
        cal = huecos_forro.get(e["nombre"], [])
        escribir(nombre, panel_dxf(e["w"], e["h"], cal))
        piezas.append(dict(num=num_p, ids=[f"extra{i + 1}"], cant=e["cant"], nombre=e["nombre"],
                           w=e["w"], h=e["h"], calados=cal, marcas=[], dxf=nombre, extra=True,
                           material=e["material"], esp=e["esp"], forro=es_forro))

    _exportar_espuma(res, carpeta, paq)

    # Placas por material (optimizadas) y barras de perfil
    from . import placas as P
    placas, av = P.armar_placas(d, piezas, rotar=rotar, cantidad=N)
    paq.avisos += av
    trazos = {pz["num"]: trazos_manuales(d["manuales"].get(pz["ids"][0], [])) for pz in piezas if not pz.get("extra")}
    paq.archivos += P.escribir_dxf_placas(placas, piezas, os.path.join(carpeta, "dxf", "placas"), trazos)
    ruta = os.path.join(carpeta, "placas.csv")
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(P.filas_csv(placas, "dxf/placas/"))
    paq.archivos.append(ruta)
    barras = gen.cortar_barras([dict(p, cant=p["cant"] * N) for p in d["perfiles"]],
                               float(d["info"]["barra"][0]), float(d["info"]["barra"][1]))
    paq.piezas, paq.placas, paq.barras = piezas, placas, barras

    # CSV (mismo formato que generar.py: ';' y utf-8 con BOM para Excel)
    ruta = os.path.join(carpeta, "lista_cortes.csv")
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        tot = (lambda c: [c * N]) if N > 1 else (lambda c: [])
        w.writerow(["Tipo", "Pieza", "Descripción", "Largo/Ancho", "Alto", "Espesor",
                    "C/U" if N > 1 else "Cant."] + ([f"Total (x{N})"] if N > 1 else []) + ["Corte", "Archivo"])
        for pz in piezas:
            w.writerow(["Panel", f"P{pz['num']}", pz["nombre"], gen.num(pz["w"]), gen.num(pz["h"]),
                        gen.num(pz["esp"]) if "esp" in pz else gen.num(float(d["info"]["espesor"])), pz["cant"]]
                       + tot(pz["cant"]) + ["", pz["dxf"]])
        for p in d["perfiles"]:
            w.writerow(["Perfil", p["perfil"], p["desc"], gen.num(p["largo"]), "", "", p["cant"]]
                       + tot(p["cant"]) + [p["corte"], ""])
    paq.archivos.append(ruta)
    ruta = os.path.join(carpeta, "materiales.csv")
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Ref.", "Material", "Cantidad", "Detalle"])
        for fl in gen.lista_materiales(d, placas, barras):
            w.writerow([fl["ref"], fl["material"], fl["cant"], fl["detalle"]])
    paq.archivos.append(ruta)

    if step:    # modelo 3D para Fusion, SolidWorks o FreeCAD
        from .step import exportar_step
        nombre = os.path.basename(os.path.normpath(carpeta)).removeprefix("salida_") or "Flightcase"
        st = exportar_step(res, os.path.join(carpeta, "case_3d.step"), nombre)
        paq.archivos.append(st.ruta)
        paq.avisos += st.avisos

    if pdf:
        laminas, pasos = {}, []
        if instructivo or render_png is None:
            from .geometria import Opciones3D, malla_3d
            from .render import renderizar
            render = _renderizador(res)
            if render_png is None:
                render_png = os.path.join(carpeta, "render.png")
                if renderizar(malla_3d(res), render_png, "0,0,0,74,0,35,0", "1600,1200", colores_placa(d)):
                    paq.archivos.append(render_png)
                else:
                    render_png = None
            if instructivo:
                from .planos import instructivo as ins
                pasos = ins.armar_pasos(d, piezas)
                from .planos import interior as pl_int
                from . import forro as _fo
                p_int = _fo.pasos_instructivo(res, piezas) + pl_int.pasos_instructivo(res, piezas)
                from . import herrajes_manuales as hman
                p_int += hman.pasos_instructivo(res, piezas)
                if p_int:   # antes del paso final (el case terminado), si lo hay
                    fin = next((i for i, p in enumerate(pasos) if p.get("vista") == "final"), len(pasos))
                    pasos[fin:fin] = p_int
                laminas = ins.renderizar_laminas(render, d, piezas, os.path.join(carpeta, "montaje"), pasos)
                paq.archivos += sorted(set(laminas.values()))
        vistas = _vistas_extra(d, carpeta) + _vista_cubierta(res, d, carpeta) + _vistas_interior(res, carpeta, piezas)
        ruta = os.path.join(carpeta, "planos.pdf")
        gen.generar_pdf(ruta, d, piezas, placas, barras, render_png, None, laminas.get("explotado"), vistas)
        paq.archivos += [v[1] for v in vistas] + [ruta]
        if pasos:
            ruta = os.path.join(carpeta, "instructivo_montaje.pdf")
            from .planos import instructivo as ins
            ins.generar_instructivo(ruta, d, piezas, laminas, render_png, pasos)
            paq.archivos.append(ruta)
    return paq


def exportar_scad(scad: str, carpeta: str, rotar: bool = True, pdf: bool = True) -> PaqueteTaller:
    """El paquete de un proyecto .scad del generador del taller, sin OpenSCAD."""
    from .modelo import calcular
    from .scad import leer_proyecto
    params = leer_proyecto(scad)
    params["_carpeta"] = os.path.dirname(os.path.abspath(scad))   # logos y contornos con ruta relativa
    return exportar(calcular(params), carpeta, rotar=rotar, pdf=pdf)
