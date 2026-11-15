"""Hojas del interior para planos.pdf y pasos del interior para el instructivo.

flightcase.scad no tiene interiores (salvo bandejas y forro de espuma), así que esto no
viene del generador de OpenSCAD: dibuja con matplotlib, igual que generar.py, a partir de
lo que calcula flightcase/taller/interiores.py.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

COTA = "#1f4e9c"
MARCA = "#c0392b"
U_MM = 44.45


def fmt(v: float) -> str:
    return f"{float(v):.1f}".rstrip("0").rstrip(".")


def _coma(t: str) -> str:
    return re.sub(r"(\d)\.(\d)", r"\1,\2", t)


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _cota_h(ax, x1, x2, y, y_ref, txt=None, col=COTA, fs=8):
    ax.plot([x1, x1], [y_ref, y], color=col, lw=0.5)
    ax.plot([x2, x2], [y_ref, y], color=col, lw=0.5)
    ax.annotate("", xy=(x1, y), xytext=(x2, y),
                arrowprops=dict(arrowstyle="<|-|>", color=col, lw=0.8, shrinkA=0, shrinkB=0, mutation_scale=7))
    ax.text((x1 + x2) / 2, y, txt or fmt(abs(x2 - x1)), ha="center", va="bottom", fontsize=fs, color=col,
            bbox=dict(fc="white", ec="none", pad=0.4))


def _cota_v(ax, y1, y2, x, x_ref, txt=None, col=COTA, fs=8):
    ax.plot([x_ref, x], [y1, y1], color=col, lw=0.5)
    ax.plot([x_ref, x], [y2, y2], color=col, lw=0.5)
    ax.annotate("", xy=(x, y1), xytext=(x, y2),
                arrowprops=dict(arrowstyle="<|-|>", color=col, lw=0.8, shrinkA=0, shrinkB=0, mutation_scale=7))
    ax.text(x, (y1 + y2) / 2, txt or fmt(abs(y2 - y1)), ha="center", va="center", fontsize=fs, color=col,
            rotation=90, bbox=dict(fc="white", ec="none", pad=0.4))


def _guardar(fig, ruta: str) -> str:
    fig.savefig(ruta, dpi=200, bbox_inches="tight", facecolor="white")
    _plt().close(fig)
    return ruta


# ---------------------------------------------------------------------------
# Espuma: una figura por bloque, una vista por capa
# ---------------------------------------------------------------------------

_EJES_TXT = {"XY": ("ancho", "fondo", "vista desde arriba, el frente abajo"),
             "XZ": ("ancho", "alto", "vista desde el frente"),
             "YZ": ("fondo", "alto", "vista desde el costado")}


def dibujar_espuma(bl, ruta: str) -> str:
    from matplotlib import patches
    plt = _plt()
    capas = bl.capas
    n = len(capas)
    cols = 1 if n == 1 else (2 if n <= 4 else 3)
    filas = math.ceil(n / cols)
    w0, h0 = capas[0].ancho, capas[0].alto
    asp = h0 / max(w0, 1)
    fig, axs = plt.subplots(filas, cols, figsize=(5.2 * cols, 5.2 * asp * filas + 0.9 * filas), squeeze=False)
    for i, ax in enumerate(axs.flat):
        if i >= n:
            ax.axis("off")
            continue
        c = capas[i]
        ax.add_patch(patches.Rectangle((0, 0), c.ancho, c.alto, fc="#d9d9d9", ec="#333", lw=1.0))
        for cal in c.calados:
            x0, y0 = cal["cx"] - cal["w"] / 2, cal["cy"] - cal["h"] / 2
            pas = cal["tipo"] == "calado"
            estilo = dict(fc="white" if pas else "#f2f2f2", ec=MARCA if pas else COTA, lw=1.0,
                          hatch=None if pas else "///")
            if cal.get("puntos"):   # calado con forma: cada contorno, los de adentro en gris (islas)
                for k_, pts in enumerate(cal["puntos"]):
                    ax.add_patch(patches.Polygon(pts, closed=True, **(estilo if k_ == 0 else
                                                                         dict(estilo, fc="#d9d9d9"))))
            else:
                ax.add_patch(patches.Rectangle((x0, y0), cal["w"], cal["h"], **estilo))
            txt = f"{cal['equipo']}\n{fmt(cal['w'])} × {fmt(cal['h'])}"
            if not pas:
                txt += f"\nrebaje {fmt(cal['prof'])}"
            ax.text(cal["cx"], cal["cy"], _coma(txt), ha="center", va="center", fontsize=7,
                    color=MARCA if pas else COTA)
            # posición desde la esquina de abajo a la izquierda
            ax.text(x0 + 2, y0 + 2, _coma(f"{fmt(x0)}; {fmt(y0)}"), fontsize=6, color="#555", va="bottom")
        m = max(c.ancho, c.alto) * 0.07
        _cota_h(ax, 0, c.ancho, -m * 0.8, 0)
        _cota_v(ax, 0, c.alto, -m * 0.8, 0)
        ax.set_xlim(-m * 1.6, c.ancho + m * 0.3)
        ax.set_ylim(-m * 1.6, c.alto + m * 0.3)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(_coma(f"Capa {c.indice} · {fmt(c.esp)} mm"), fontsize=10, loc="left")
    fig.tight_layout()
    return _guardar(fig, ruta)


def texto_espuma(bl, I) -> str:
    c = bl.capas[0]
    ua, va, vista = _EJES_TXT.get(c.plano, ("ancho", "alto", ""))
    lado = "de abajo" if (bl.eje == 2 and bl.abre_arriba) else ("de atrás" if bl.eje == 1 else "del lado cerrado")
    if bl.eje == 2 and not bl.abre_arriba:
        lado = "de arriba (la tapa)"
    rebajes = sum(1 for cp in bl.capas for x in cp.calados if x["tipo"] == "rebaje")
    t = (f"{bl.nombre}: {len(bl.capas)} capas de {fmt(c.ancho)} × {fmt(c.alto)} mm ({ua} × {va}, {vista}). "
         f"La capa 1 es la {lado}; se pegan en orden. En rojo, calados pasantes; en azul rayado, rebajes "
         f"(fresar a la profundidad indicada desde la cara de la capa que mira a la abertura). "
         f"Las medidas chicas son la esquina del calado desde abajo a la izquierda. Holgura incluida. "
         f"DXF por capa en dxf/espuma/.")
    if rebajes:
        t += f" Hay {rebajes} rebaje(s): si el fondo de un equipo coincide con el borde de una capa, queda pasante y no hace falta fresar."
    return _coma(t)


# ---------------------------------------------------------------------------
# Rack de 19": vista de frente
# ---------------------------------------------------------------------------

def dibujar_rack(rk: Dict[str, Any], ruta: str) -> str:
    from matplotlib import patches
    plt = _plt()
    W, L, a0, A = rk["ancho"], rk["largo"], rk["desde"], rk["largo_util"]
    supl, ala = rk["suplemento"], rk["ala"]
    fig, ax = plt.subplots(figsize=(8.5, 8.5 * max(A, 300) / max(W, 300) * 0.55 + 1.5))
    ax.add_patch(patches.Rectangle((0, 0), W, A, fc="#f7f3ea", ec="#333", lw=1.2))
    # suplementos y rieles
    for x in (0, W - max(supl, 0)):
        if supl >= 1:
            ax.add_patch(patches.Rectangle((x, a0), supl, L, fc="#c9a26b", ec="#6b4a26", lw=0.6))
    for x in (supl, W - supl - ala):
        ax.add_patch(patches.Rectangle((x, a0), ala, L, fc="#b8bec6", ec="#555", lw=0.8))
    x_p = (W - 482.6) / 2
    for e in rk["equipos"]:
        y = a0 + (e["desde"] - 1) * U_MM
        h = e["u"] * U_MM
        ax.add_patch(patches.Rectangle((x_p, y + 0.4), 482.6, h - 0.8, fc="#3d4b5c", ec="black", lw=0.8))
        ax.text(W / 2, y + h / 2, _coma(f"{e['nombre']}  ·  {e['u']} U  ·  fondo {fmt(e['fondo'])}"),
                ha="center", va="center", color="white", fontsize=8)
    for hu in rk["huecos"]:
        y = a0 + (hu[0] - 1) * U_MM
        h = len(hu) * U_MM
        ax.add_patch(patches.Rectangle((x_p, y + 0.4), 482.6, h - 0.8, fc="white", ec="#888", lw=0.6, hatch="..."))
        ax.text(W / 2, y + h / 2, f"libre: {len(hu)} U (carátula ciega)", ha="center", va="center",
                fontsize=7.5, color="#555", bbox=dict(fc="white", ec="none", pad=0.5))
    for k in range(1, rk["u"] + 1):
        ax.text(-6, a0 + (k - 0.5) * U_MM, str(k), ha="right", va="center", fontsize=6.5, color="#555")
    m = max(W, A) * 0.06
    _cota_h(ax, 0, W, A + m * 0.5, A, f"interior {fmt(W)}")
    _cota_h(ax, x_p, x_p + 482.6, -m * 0.6, 0, "frente 19\" 482,6")
    _cota_v(ax, a0, a0 + L, W + m * 0.6, W, _coma(f"{rk['u']} U = {fmt(L)}"))
    if a0 > 1:
        _cota_v(ax, 0, a0, W + m * 0.6, W)
    if supl >= 1:
        _cota_h(ax, 0, supl, a0 + L + m * 0.25, a0 + L, _coma(fmt(supl)), fs=7)
    ax.set_xlim(-m * 1.2, W + m * 1.5)
    ax.set_ylim(-m * 1.4, A + m * 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    return _guardar(fig, ruta)


def texto_rack(rk: Dict[str, Any]) -> str:
    vista = ("Vista desde el frente, U1 abajo." if rk["frontal"] else
             "Vista desde arriba (rack de tapa superior), U1 adelante: la cota de la izquierda se mide desde el frente.")
    t = (f"{vista} Rieles de {rk['u']} U ({fmt(rk['largo'])} mm) con la cara a {fmt(rk['retiro'])} mm del plano de "
         f"cierre")
    if rk["desde"] > 1:
        t += f", empezando a {fmt(rk['desde'])} mm del " + ("piso interior" if rk["frontal"] else "frente interior")
    t += "."
    if rk["suplemento"] >= 1:
        t += (f" Suplemento de {fmt(rk['suplemento'])} mm entre cada costado y su riel, para que los agujeros de las "
              "orejas (465,1 entre centros) caigan sobre el ala del riel.")
    if rk["traseros"]:
        t += f" Rieles traseros con la cara a {fmt(rk['retiro'] + rk['dist_traseros'])} mm del cierre."
    t += (f" Fondo para equipos: {fmt(rk['fondo_cuerpo'] - rk['retiro'])} mm en el cuerpo"
          + (f" ({fmt(rk['fondo_util'] - rk['retiro'])} con la tapa trasera)" if rk["fondo_util"] > rk["fondo_cuerpo"] + 0.5 else "")
          + f"; dejar {fmt(rk['cables'])} mm detrás de cada equipo para conectores.")
    return _coma(t)


# ---------------------------------------------------------------------------
# Cajones: frentes vistos desde adelante y despiece
# ---------------------------------------------------------------------------

def dibujar_cajones(cajones: List[Dict[str, Any]], ruta: str) -> str:
    from matplotlib import patches
    plt = _plt()
    W = cajones[0]["ancho_util"]
    alto_max = max(c["z"] + c["alto"] for c in cajones)
    H = max(alto_max + 40, min(cajones[0]["alto_util"], alto_max * 1.4))
    fig, ax = plt.subplots(figsize=(8.5, 8.5 * H / W * 0.8 + 1.2))
    ax.add_patch(patches.Rectangle((0, 0), W, H, fc="#f7f3ea", ec="#333", lw=1.2))
    for c in cajones:
        x0 = (W - c["ancho"]) / 2 + c["holgura"]
        fw, fh = c["ancho"] - 2 * c["holgura"], c["alto"] - c["holgura"]
        ax.add_patch(patches.Rectangle((x0, c["z"]), fw, fh, fc="#e2c08f", ec="#6b4a26", lw=1.0))
        ax.add_patch(patches.FancyBboxPatch((W / 2 - 50, c["z"] + fh / 2 - 12), 100, 24,
                                            boxstyle="round,pad=0,rounding_size=8", fc="#555", ec="#333"))
        ax.text(x0 + 8, c["z"] + fh - 8, _coma(f"{c['nombre']}  ·  frente {fmt(fw)} × {fmt(fh)}"),
                fontsize=8, va="top")
        _cota_v(ax, c["z"], c["z"] + c["alto"], W + 25, W, fs=7)
    m = W * 0.06
    _cota_h(ax, 0, W, H + m * 0.4, H, f"interior {fmt(W)}")
    ax.set_xlim(-m, W + m * 1.4)
    ax.set_ylim(-m * 0.5, H + m * 1.1)
    ax.set_aspect("equal")
    ax.axis("off")
    return _guardar(fig, ruta)


def texto_cajones(cajones: List[Dict[str, Any]], num_pieza: Dict[str, int]) -> str:
    partes = []
    for c in cajones:
        piezas = ", ".join(f"P{num_pieza[n]}" for n in (f"{c['nombre']} {x}" for x in ("frente", "lateral", "trasera", "piso"))
                           if n in num_pieza)
        partes.append(f"{c['nombre']}: a {fmt(c['z'])} mm del piso, caja {fmt(c['caja_ancho'])} × {fmt(c['largo'])} × "
                      f"{fmt(c['h_caja'])} mm, corredera de {fmt(c['largo'])} mm" + (f" ({piezas})" if piezas else ""))
    c0 = cajones[0]
    t = ("Vista desde el frente con la tapa sacada. " + "; ".join(partes) + ". "
         f"Laterales y trasera van sobre el piso; la trasera entre los laterales. El frente se atornilla por "
         f"dentro a la caja, con {fmt(c0['holgura'])} mm de luz a los costados y arriba. Cada corredera ocupa "
         f"{fmt(c0['corredera'])} mm por lado; el frente queda a {fmt(c0['retiro'])} mm del plano de cierre.")
    return _coma(t)


# ---------------------------------------------------------------------------
# Hojas para planos.pdf
# ---------------------------------------------------------------------------

def vistas_planos(res, carpeta: str, piezas: List[Dict[str, Any]],
                  render_general: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """(título, png, texto) para el parámetro vistas_extra de generar_pdf."""
    I = res.valores.get("interiores")
    if I is None:
        return []
    os.makedirs(carpeta, exist_ok=True)
    num = {pz["nombre"]: pz["num"] for pz in piezas if pz.get("extra")}
    out: List[Tuple[str, str, str]] = []
    if render_general:
        eqs = [f"{e[1]} ({e[2]} mm{', ' + e[4] if e[4] else ''})" for e in I.elementos if e[0] in ("Equipo", "Rack")]
        texto = " ".join(I.resumen) + "."
        if eqs:
            texto += " Equipos: " + "; ".join(eqs) + "."
        out.append(("Interior", render_general, _coma(texto)))
    for i, bl in enumerate(I.espumas, 1):
        png = dibujar_espuma(bl, os.path.join(carpeta, f"interior_espuma{i}.png"))
        out.append((f"Interior: {bl.nombre.lower()} por capas", png, texto_espuma(bl, I)))
    if I.rack and I.rack.get("u"):
        png = dibujar_rack(I.rack, os.path.join(carpeta, "interior_rack.png"))
        out.append(("Interior: rack 19\"", png, texto_rack(I.rack)))
    if I.cajones:
        png = dibujar_cajones(I.cajones, os.path.join(carpeta, "interior_cajones.png"))
        out.append(("Interior: cajones", png, texto_cajones(I.cajones, num)))
    return out


# ---------------------------------------------------------------------------
# Pasos del instructivo
# ---------------------------------------------------------------------------

def pasos_instructivo(res, piezas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pasos de montaje del interior, con el formato de instructivo.armar_pasos."""
    I = res.valores.get("interiores")
    if I is None:
        return []
    v = res.valores
    abrir = round(0.8 * max(v["ext_ancho"], v["ext_prof"], v["ext_alto"]))
    num = {pz["nombre"]: pz["num"] for pz in piezas if pz.get("extra")}
    P = lambda nombre: f"P{num[nombre]}" if nombre in num else nombre.lower()
    camara = "0,0,0,62,0,28,0"
    pasos: List[Dict[str, Any]] = []
    rk = I.rack
    if rk and rk.get("u"):
        sup = "Suplemento de riel de rack"
        texto = [f"Piezas: {2 * (2 if rk['traseros'] else 1)} tramos de riel de {rk['u']} U ({fmt(rk['largo'])} mm)"
                 + (f", {2 * (2 if rk['traseros'] else 1)} suplementos {P(sup)} de {fmt(rk['suplemento'])} mm"
                    if rk["suplemento"] >= 1 else "") + ", tuercas enjauladas y tornillos M6."]
        k = 1
        if rk["suplemento"] >= 1:
            texto.append(f"{k}. Atornillá un suplemento a cada costado, con el canto a {fmt(rk['retiro'])} mm del "
                         "plano de cierre y a lo largo de los rieles.")
            k += 1
        texto.append(f"{k}. Atornillá los rieles " + ("sobre los suplementos" if rk["suplemento"] >= 1 else "a los costados")
                     + f", con la cara de las orejas a {fmt(rk['retiro'])} mm del plano de cierre"
                     + (f" y empezando a {fmt(rk['desde'])} mm del " + ("piso interior" if rk["frontal"] else "frente interior")
                        if rk["desde"] > 1 else "") + ". Medí la diagonal entre los agujeros: tienen que dar iguales.")
        k += 1
        if rk["traseros"]:
            texto.append(f"{k}. Colocá los rieles traseros con la cara a {fmt(rk['retiro'] + rk['dist_traseros'])} mm "
                         "del plano de cierre, mirando hacia adelante.")
            k += 1
        orden = ", ".join(f"{e['nombre']} en U{e['desde']}" + (f"–{e['hasta']}" if e["hasta"] > e["desde"] else "")
                          for e in sorted(rk["equipos"], key=lambda e: e["desde"]))
        if orden:
            texto.append(f"{k}. Calzá las tuercas enjauladas y montá los equipos de abajo hacia arriba: {orden}.")
            k += 1
        if rk["huecos"]:
            texto.append(f"{k}. Tapá las unidades libres con carátulas ciegas.")
        pasos.append(dict(titulo="Interior: rack 19\"", vista="int_rack", camara=camara,
                          defs={"paso": 99, "abrir_tapa": abrir, "resaltar_interior": "riel,suplemento"},
                          texto=texto))
    if I.cajones:
        for c in I.cajones:
            nm = c["nombre"]
            texto = [f"Piezas: frente {P(nm + ' frente')}, 2 laterales {P(nm + ' lateral')}, trasera "
                     f"{P(nm + ' trasera')}, piso {P(nm + ' piso')} y un par de correderas de {fmt(c['largo'])} mm.",
                     f"1. Armá la caja: laterales sobre el piso, la trasera entre ellos. Encolá y atornillá. "
                     f"Tiene que medir {fmt(c['caja_ancho'])} mm de ancho por fuera (± 0,5).",
                     f"2. Atornillá las correderas a los costados del case, a nivel, con el borde de abajo a "
                     f"{fmt(c['z'] + (c['alto'] - c['holgura'] - c['h_caja']) / 2 + (c['h_caja'] - min(45, c['h_caja'])) / 2)} "
                     f"mm del piso interior y retiradas {fmt(c['retiro'] + c['esp'])} mm del plano de cierre.",
                     "3. Montá la caja en las correderas y probá que corra entera sin rozar.",
                     f"4. Presentá el frente con {fmt(c['holgura'])} mm de luz a los costados y atornillalo por "
                     "dentro. Colocá el tirador."]
            pasos.append(dict(titulo=f"Interior: {nm.lower()}", vista=f"int_{nm.lower().replace(' ', '_').replace('ó', 'o')}",
                              camara=camara, defs={"paso": 99, "abrir_tapa": abrir, "resaltar_interior": "cajon,corredera"},
                              texto=texto))
    if I.espumas:
        texto = []
        for bl in I.espumas:
            texto.append(f"{bl.nombre}: {len(bl.capas)} capas ({', '.join(fmt(c.esp) for c in bl.capas)} mm). "
                         "Cortá cada capa con su DXF (dxf/espuma/) y fresá los rebajes.")
        texto += ["1. Pegá las capas en orden (la capa 1 del lado cerrado) con cola de contacto, alineando los calados.",
                  "2. Presentá cada equipo en su calado antes de pegar el bloque al case.",
                  "3. Pegá el bloque al case; la espuma de la tapa va pegada a la tapa."]
        pasos.append(dict(titulo="Interior: espuma", vista="int_espuma", camara=camara,
                          defs={"paso": 99, "abrir_tapa": abrir, "resaltar_interior": "espuma"}, texto=texto))
    for p in pasos:
        p["texto"] = [_coma(t) for t in p["texto"]]
    return pasos
