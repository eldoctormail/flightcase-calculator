"""Formas de case que no son una caja: rack inclinado para consola, funda de rack y baúl plegable.

Estas reglas son de la app (no están en flightcase.scad). Usan los mismos materiales,
perfiles y herrajes del taller (placa, ángulo de arista, perfil de cierre macho/hembra,
esquineros, cierres mariposa, bisagras, manijas, ruedas y rieles de rack) y devuelven un
ResultadoTaller igual al de modelo.calcular, así que salen igual en la lista de cortes,
el DXF, las placas, los planos, el instructivo, la vista 3D y el STEP.

Ejes del mundo: X = ancho (frente), Y = profundidad (0 = frente), Z = alto (0 = abajo).
Cada panel se ubica con o (esquina de la cara exterior), u (ancho), v (alto) y n (normal
hacia adentro), como en modelo.py; los lados del rack inclinado son trapecios (contorno).

- inclinado: cuerpo en cuña (frente más bajo que la trasera) y tapa recta sobre el plano
  inclinado. El aro de cierre es un rectángulo en ese plano. Los rieles de rack van paralelos
  a la pendiente para atornillar la consola por las orejas.
- funda: tubo abierto adelante y atrás (piso, techo y laterales), con los bordes terminados
  en ángulo, esquineros en las 8 puntas y rieles de rack adelante y atrás. Medidas como un
  rack frontal: int_ancho = ancho, int_prof = alto, int_alto_cuerpo = profundidad.
- plegable: base gruesa con ruedas y cuatro paredes con bisagra de piano en el canto de
  abajo, que se pliegan hacia adentro (frente y trasera primero, después los laterales, que
  van sobre suplementos para quedar encima). La tapa va arriba como en un baúl.
- slam: caja cerrada donde una o dos caras (arriba, frente, trasera) son tapas planas, sin
  paredes de tapa: cada una apoya a ras en un marco de perfil slam que reemplaza a los ángulos
  de esa cara, gira sobre una bisagra de piano y cierra sola con cierres slam embutidos. Con
  dos hojas, la cara se abre como una puerta doble: una hoja se traba con pasadores y la otra
  cierra sobre ella. Las medidas son como las de una caja: el alto (o el fondo en un case
  parado) es el del cuerpo más el de la tapa, porque las tapas planas no tienen alto propio.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import materiales as _mat
from .modelo import (TRAMO_MINIMO, CatalogoTaller, Calado, Herraje, Marca, Panel, Perfil, ResultadoTaller,
                     _pos_n, fmt, round_os, s)

FORMAS = ("inclinado", "funda", "plegable", "slam", "tabla")
NOMBRES = {"inclinado": "Rack inclinado para consola (cuerpo en cuña, tapa sobre el plano inclinado)",
           "funda": "Funda de rack: abierta adelante y atrás, sin tapas",
           "plegable": "Baúl plegable: paredes con bisagra de piano que se pliegan sobre la base",
           "slam": "Tapas slam: tapas o puertas planas en un marco de perfil slam, con bisagra de piano y "
                   "cierres slam embutidos",
           "tabla": "Base de ruedas suelta (castor board): una tabla con ruedas y un borde de ángulo donde "
                    "apoyan uno o más cases"}

# pasos de la vista 3D y del instructivo de estas formas
F_CUERPO, F_AROS, F_ARISTAS, F_ESQ, F_TAPA, F_CIERRES, F_MANIJAS, F_RUEDAS = 1, 2, 3, 4, 5, 6, 7, 8

Vec = Tuple[float, float, float]


def es_forma(P: Dict[str, Any]) -> bool:
    return str(P.get("forma", "caja") or "caja") in FORMAS


def _sum(*vs: Sequence[float]) -> Vec:
    return tuple(sum(c) for c in zip(*vs))  # type: ignore[return-value]


def _mul(v: Sequence[float], k: float) -> Vec:
    return (v[0] * k, v[1] * k, v[2] * k)


def _neg(v: Sequence[float]) -> Vec:
    return (-v[0], -v[1], -v[2])


def n_cierres(L: float) -> int:
    return 1 if L <= 450 else (2 if L <= 1000 else 3)


# ---------------------------------------------------------------------------
# Valores efectivos (catálogo o parámetros), los mismos que usa modelo.calcular
# ---------------------------------------------------------------------------

def _efectivos(P: Dict[str, Any], cat: CatalogoTaller) -> SimpleNamespace:
    g, cd, ce = P.get, cat.dato, cat.existe
    E = SimpleNamespace()
    ref_placa = g("ref_placa")
    E.t = cd(ref_placa, "esp", g("placa_esp"))
    E.material = cat.nombre(ref_placa) if ce(ref_placa) else g("placa_material")
    E.placa_largo = cd(ref_placa, "largo", g("placa_largo"))
    E.placa_ancho = cd(ref_placa, "ancho", g("placa_ancho"))
    ref_ang, ref_esq = g("ref_angulo"), g("ref_esquinero")
    E.ala = cd(ref_ang, "ala", g("angulo_ala"))
    E.ae = cd(ref_ang, "esp", g("angulo_esp"))
    E.pata = cd(ref_esq, "pata", g("esq_pata"))
    paso = cd(ref_esq, "paso", 0)
    E.ed = g("esq_descuento") if not ce(ref_esq) else (15 if paso > 0 else E.pata + 2)
    E.esq_rem = cd(ref_esq, "remaches", 3)
    E.m_alto, E.m_sup = g("cierre_m_alto"), g("cierre_m_sup")
    E.h_alto, E.h_sup = g("cierre_h_alto"), g("cierre_h_sup")
    E.sal = g("cierre_saliente")
    hib = bool(g("cierre_hibrido"))
    E.perfil_arista = cat.nombre(ref_ang) if ce(ref_ang) else s("Ángulo ", E.ala, "x", E.ala, "x", E.ae)
    E.ref_arista = ref_ang
    rm, rh = g("ref_cierre_macho"), g("ref_cierre_hembra")
    E.macho = "Perfil híbrido" if hib else (cat.nombre(rm) if ce(rm) else "Cierre macho")
    E.hembra = E.macho if hib else (cat.nombre(rh) if ce(rh) else "Cierre hembra")
    E.ref_macho, E.ref_hembra = ("", "") if hib else (rm, rh)
    ref_man = g("ref_manija")
    E.man_emb = cd(ref_man, "tipo", "embutida") == "embutida"
    corte = cd(ref_man, "corte", [g("manija_corte_ancho"), g("manija_corte_alto")]) if ce(ref_man) \
        else [g("manija_corte_ancho"), g("manija_corte_alto")]
    E.man_w, E.man_h = corte[0], corte[1]
    E.man_r = cd(ref_man, "radio", g("manija_corte_radio"))
    E.man_rem = cd(ref_man, "remaches", 6)
    E.ref_manija = ref_man
    ref_cie = g("ref_cierre")
    E.cie_emb = cd(ref_cie, "tipo", "superficie") == "embutido"
    E.cie_corte = cd(ref_cie, "corte", [0, 0])
    E.cie_radio = cd(ref_cie, "radio", 8)
    E.cie_rem = cd(ref_cie, "remaches", 6)
    E.ref_cierre = ref_cie
    ref_r, ref_rf = g("ref_rueda"), g("ref_rueda_freno")
    geo_r = ref_rf if ref_rf != "" else ref_r
    E.rueda_d = cd(geo_r, "diametro", g("rueda_diametro"))
    E.rueda_alto = cd(geo_r, "alto", g("rueda_alto"))
    E.rueda_placa = cd(geo_r, "placa", g("rueda_placa"))
    E.rueda_aguj = cd(geo_r, "agujeros", g("rueda_agujeros"))
    E.rueda_aguj_d = 0 if g("rueda_agujero_d") == 0 else cd(geo_r, "agujero_d", g("rueda_agujero_d"))
    E.ref_rueda, E.ref_rueda_freno = ref_r, ref_rf
    E.pie_d = cd(g("ref_pie"), "diametro", g("pie_diametro"))
    E.pie_h = cd(g("ref_pie"), "alto", g("pie_alto"))
    # remache: el elegido o el más corto del catálogo que alcance (como modelo.calcular)
    general = _mat.MaterialPanel(E.material, E.t, E.placa_largo, E.placa_ancho, ref_placa if ce(ref_placa) else "")
    l_min = _mat.espesor_maximo(P, cat, general) + E.ae + 3
    rems = [f["ref"] for f in cat.filas if f["categoria"] == "remache"]
    cands_d = [r for r in rems if cd(r, "d", 0) == g("remache_d") and cd(r, "l", 0) >= l_min]
    cands = cands_d or [r for r in rems if cd(r, "l", 0) >= l_min]
    l_best = min([cd(r, "l", 999) for r in cands] + [999])
    if g("ref_remache") != "":
        E.remache_ref = g("ref_remache")
    elif g("usar_catalogo_remaches"):
        c_ = [r for r in cands if cd(r, "l", 0) == l_best]
        E.remache_ref = c_[0] if c_ else None
    else:
        E.remache_ref = None
    E.remache_d = cd(E.remache_ref or "", "d", g("remache_d"))
    return E


# ---------------------------------------------------------------------------
# Armado: junta paneles, perfiles, herrajes y las piezas de la vista 3D
# ---------------------------------------------------------------------------

class _Armado:
    def __init__(self, P: Dict[str, Any], cat: CatalogoTaller) -> None:
        self.P, self.cat, self.E = P, cat, _efectivos(P, cat)
        self.paneles: List[Panel] = []
        self.col: List[Dict[str, Any]] = []
        self.calados: List[Calado] = []
        self.marcas: List[Marca] = []
        self.perfiles: List[Perfil] = []
        self.H: List[list] = []
        self.A: List[str] = []
        self.extras: List[list] = []
        self.panelmat: List[list] = []
        # 3D
        self.aristas: List[Dict[str, Any]] = []     # ángulo en L: o (arista), a y b (normales de las caras), c, L
        self.bloques: List[Dict[str, Any]] = []     # perfiles de cierre, bisagras de piano: cajas o,u,v,n,a,b,c
        self.esquineros: List[Dict[str, Any]] = []
        self.herr: List[Dict[str, Any]] = []        # cierres, ganchos y bisagras en un marco o,u,v,n
        self.ruedas: List[Dict[str, Any]] = []
        self.pies: List[Vec] = []
        self.remaches = 0

    # -- piezas --
    def panel(self, pid: str, nombre: str, grupo: str, ancho: float, alto: float, o: Vec, u: Vec, v: Vec, n: Vec,
              contorno: Optional[List[Tuple[float, float]]] = None, esp: Optional[float] = None,
              mueve: Optional[str] = None, paso: Optional[int] = None) -> None:
        self.paneles.append(Panel(pid, nombre, grupo, round(ancho, 2), round(alto, 2),
                                  [(round(x, 2), round(y, 2)) for x, y in contorno] if contorno else None))
        self.col.append(dict(id=pid, o=o, u=u, v=v, n=n, grupo=grupo, esp=esp or self.E.t, mueve=mueve or grupo,
                             contorno=contorno, paso=paso or (F_TAPA if grupo == "tapa" else F_CUERPO)))

    def tramo(self, perfil: str, desc: str, largo: float, cant: int, corte: str, ref: str) -> None:
        if largo >= TRAMO_MINIMO and cant > 0:
            self.perfiles.append(Perfil(perfil, desc, round(largo, 2), cant, corte, ref))

    def arista(self, o: Vec, a: Vec, b: Vec, c: Vec, L: float, mueve: str = "cuerpo", paso: int = F_ARISTAS,
               solo_a: bool = False) -> None:
        """`solo_a`: el ángulo se remacha sólo a la cara de normal `a` (baúl plegable)."""
        if L >= TRAMO_MINIMO:
            self.aristas.append(dict(o=o, a=a, b=b, c=c, L=L, mueve=mueve, paso=paso, solo_a=solo_a))

    def bloque(self, o: Vec, u: Vec, v: Vec, n: Vec, a: float, b: float, c: float, color: str, etiqueta: str,
               mueve: str = "cuerpo", paso: int = F_AROS) -> None:
        if a > 0.01 and b > 0.01 and c > 0.01:
            self.bloques.append(dict(o=o, u=u, v=v, n=n, a=a, b=b, c=c, color=color, etiqueta=etiqueta,
                                     mueve=mueve, paso=paso))

    def esquinero(self, o: Vec, a: Vec, b: Vec, c: Vec, mueve: str = "cuerpo", paso: int = F_ESQ) -> None:
        self.esquineros.append(dict(o=o, a=a, b=b, c=c, mueve=mueve, paso=paso))

    def herraje3d(self, tipo: str, o: Vec, u: Vec, v: Vec, n: Vec, x: float, ys: Tuple[float, float],
                  mueve: str = "cuerpo", d: float = 1.0) -> None:
        self.herr.append(dict(tipo=tipo, o=o, u=u, v=v, n=n, x=x, ys=ys, mueve=mueve, d=d))

    # -- herrajes que se repiten --
    def aro(self, Q, X: float, S: float, desde: float, alto: float, color: str, mueve: str, etiqueta: str,
            partes: Optional[Dict[str, str]] = None, cortes_rectos: bool = False, paso: int = F_AROS) -> None:
        """Aro de cierre en el plano Q(x, s, h): rectángulo X x S, de `desde` a `desde + alto` sobre el plano.
        `partes` da a qué grupo de la vista va cada lado (baúl plegable: cada pared lleva el suyo)."""
        E = self.E
        sl, p = E.sal, E.t
        partes = partes or {}
        if cortes_rectos:   # frente y trasera entre los laterales: los laterales cubren las esquinas
            lados = (("frente", p, X - p, -sl, p), ("trasera", p, X - p, S - p, S + sl),
                     ("izq", -sl, p, -sl, S + sl), ("der", X - p, X + sl, -sl, S + sl))
        else:
            lados = (("frente", -sl, X + sl, -sl, p), ("trasera", -sl, X + sl, S - p, S + sl),
                     ("izq", -sl, p, p, S - p), ("der", X - p, X + sl, p, S - p))
        e1, e2, e3 = Q.e1, Q.e2, Q.e3
        for lado, x0, x1, s0, s1 in lados:
            self.bloque(Q(x0, s0, desde), e1, e2, e3, x1 - x0, s1 - s0, alto, color, etiqueta,
                        partes.get(lado, mueve), paso)

    def cierre(self, cara_o: Vec, u: Vec, v: Vec, n: Vec, x: float, mueve_cuerpo: str = "cuerpo") -> None:
        """Cierre mariposa en el cuerpo: `cara_o` en el plano de cierre sobre la cara exterior, v hacia la tapa."""
        b = self.E.m_alto - self.E.m_sup
        self.herraje3d("cierre", cara_o, u, v, n, x, (-b - 35, -b + 18), mueve_cuerpo)

    def gancho(self, cara_o: Vec, u: Vec, v: Vec, n: Vec, x: float, mueve: str = "tapa") -> None:
        """Contraparte en la tapa (el mismo marco que el cierre: v hacia la tapa)."""
        h = self.E.h_alto
        self.herraje3d("gancho", cara_o, u, v, n, x, (h - 14, h + 22), mueve)

    def ruedas_abajo(self, pid: str, ancho: float, alto: float, o: Vec, u: Vec, v: Vec, margen: float) -> None:
        """Cuatro ruedas bajo un panel horizontal (o = esquina de su cara de abajo)."""
        P, E = self.P, self.E
        if int(P.get("ruedas", 0) or 0) != 4:
            return
        frenos = max(0, min(4, int(P.get("rueda_frenos", 2) or 0)))
        pl = E.rueda_placa
        mx, my = margen + pl[0] / 2, margen + pl[1] / 2
        pos = [[mx if sx == 0 else ancho - mx, my if sy == 0 else alto - my] for sx in (0, 1) for sy in (0, 1)]
        for i, (cx, cy) in enumerate(pos):
            freno = i < frenos
            self.marcas.append(Marca(pid, "rueda", cx, cy, pl[0], pl[1], "freno" if freno else "placa rueda"))
            self.ruedas.append(dict(o=o, u=u, v=v, x=cx, y=cy, freno=freno))
            if E.rueda_aguj_d > 0:
                for ax in (-1, 1):
                    for ay in (-1, 1):
                        self.calados.append(Calado(pid, "agujero", cx + ax * E.rueda_aguj[0] / 2,
                                                   cy + ay * E.rueda_aguj[1] / 2, E.rueda_aguj_d, E.rueda_aguj_d,
                                                   E.rueda_aguj_d / 2))
        if 2 * mx + pl[0] > ancho + 0.01 or 2 * my + pl[1] > alto + 0.01:
            self.A.append("Las placas de rueda se superponen: el case es muy chico para 4 ruedas de esa placa.")
        cat, g = self.cat, P.get
        nom = lambda ref, d: cat.nombre(ref) if cat.existe(ref) else d
        if frenos:
            self.H.append([nom(E.ref_rueda_freno, s("Rueda giratoria Ø", E.rueda_d, " con freno")), frenos,
                           s("agujeros ", E.rueda_aguj[0], "x", E.rueda_aguj[1]), E.ref_rueda_freno])
        if 4 - frenos:
            self.H.append([nom(E.ref_rueda, s("Rueda giratoria Ø", E.rueda_d, " sin freno")), 4 - frenos,
                           s("agujeros ", E.rueda_aguj[0], "x", E.rueda_aguj[1]), E.ref_rueda])
        esp = next((m[2] for m in self.panelmat if m[0] == pid), E.t)
        self.H.append([s("Bulón M", math.floor(E.rueda_aguj_d - 0.5), " + arandela + tuerca autofrenante"), 16,
                       s("para agujero Ø", E.rueda_aguj_d, ", largo ≥ ", esp + 15, " mm"), ""])
        if int(g("rueda_fijas", 0) or 0) or g("cazoletas") or g("base_suelta") or len(g("base_ruedas") or []) >= 2:
            self.A.append("En esta forma de case las ruedas van atornilladas directo abajo: se ignoran ruedas fijas, "
                          "cazoletas y base de ruedas.")

    def pies_abajo(self, pid: str, ancho: float, alto: float, o: Vec, u: Vec, v: Vec, margen: float) -> None:
        P, E = self.P, self.E
        if int(P.get("pies", 0) or 0) != 4:
            return
        m = margen + E.pie_d / 2
        for sx in (0, 1):
            for sy in (0, 1):
                cx, cy = (m if sx == 0 else ancho - m), (m if sy == 0 else alto - m)
                self.marcas.append(Marca(pid, "pie", cx, cy, E.pie_d, E.pie_d, "pie"))
                self.pies.append(_sum(o, _mul(u, cx), _mul(v, cy)))
        ref = P.get("ref_pie", "")
        self.H.append([self.cat.nombre(ref) if self.cat.existe(ref) else "Pie de goma", 4,
                       s("Ø", E.pie_d, " x ", E.pie_h, " mm"), ref])
        if int(P.get("ruedas", 0) or 0) == 4:
            self.A.append("Elegiste ruedas y pies a la vez: van los dos abajo, verificá que no se crucen.")

    def manijas_en(self, pids: Sequence[str], centros: Dict[str, Tuple[float, float]], acostada: bool = False) -> None:
        """Manijas en esos paneles (centro de cada una en coordenadas del panel)."""
        P, E = self.P, self.E
        if not P.get("manijas"):
            return
        w, h = (E.man_h, E.man_w) if acostada else (E.man_w, E.man_h)
        for pid in pids:
            cx, cy = centros[pid]
            if E.man_emb:
                self.calados.append(Calado(pid, "manija", cx, cy, w, h, E.man_r))
            else:
                self.marcas.append(Marca(pid, "manija_sup", cx, cy, w, h, "asa de superficie"))
        cat = self.cat
        self.H.append([cat.nombre(E.ref_manija) if cat.existe(E.ref_manija) else "Manija embutida", len(pids),
                       s("calado ", E.man_w, "x", E.man_h) if E.man_emb else "de superficie", E.ref_manija])
        self.remaches += len(pids) * E.man_rem

    def calados_cierre(self) -> None:
        """Cierres embutidos: calado bajo cada marca de cierre del cuerpo."""
        E = self.E
        if not E.cie_emb:
            return
        grupos = {p.id: p.grupo for p in self.paneles}
        for m in list(self.marcas):
            if m.tipo == "cierre" and grupos.get(m.panel) != "tapa":
                self.calados.append(Calado(m.panel, "cierre", m.x, m.y - 2 - E.cie_corte[1] / 2,
                                           E.cie_corte[0], E.cie_corte[1], E.cie_radio))

    def _perforacion(self) -> Dict[str, Any]:
        """Datos para la capa de perforaciones de los DXF (perforaciones.py), como modelo.calcular."""
        P, E, cat = self.P, self.E, self.cat
        dr = lambda ref: dict(cat.fila(ref)["datos"]) if cat.existe(ref) else {}
        rb, rm = P.get("ref_bisagra", ""), E.ref_manija
        return dict(
            remache_d=E.remache_d, paso=P.get("remache_paso", 100), esq_remaches=E.esq_rem,
            cierre=dict(dr(E.ref_cierre), remaches=E.cie_rem, tipo="embutido" if E.cie_emb else "superficie",
                        corte=list(E.cie_corte)),
            bisagra=dict(dr(rb), remaches=cat.dato(rb, "remaches", 6)), piano=0,
            manija=dict(dr(rm), remaches=E.man_rem), cazoleta={}, plato={}, marco_ala=0,
            hibrido_ala=0, hibrido_descuento=0)

    # -- cierre del resultado --
    def remaches_de_perfiles(self) -> int:
        paso = self.P.get("remache_paso", 100)
        tr = lambda L: math.floor(max(L - 40, 0) / paso) + 1
        n = 0
        for p in self.perfiles:
            if p.ref == self.P.get("ref_riel") or p.descripcion.startswith("Riel"):
                continue
            filas = 1 if (p.corte != "recto" or "una fila" in p.descripcion) else 2
            n += filas * tr(p.largo) * p.cantidad
        return n

    def herrajes_comunes(self, n_esq: int, n_cierres_: int, cierre_det: str) -> None:
        P, E, cat = self.P, self.E, self.cat
        nom = lambda ref, d: cat.nombre(ref) if cat.existe(ref) else d
        ref_e = P.get("ref_esquinero", "")
        if n_esq:
            self.H.insert(0, [nom(ref_e, "Esquinero bola"), n_esq, s("pata ", E.pata, " mm"), ref_e])
        self.remaches += n_esq * E.esq_rem
        if n_cierres_:
            self.H.insert(1, [nom(E.ref_cierre, "Cierre mariposa"), n_cierres_,
                              cierre_det + (s(", embutido: calado ", E.cie_corte[0], "x", E.cie_corte[1])
                                            if E.cie_emb else ""), E.ref_cierre])
            self.remaches += n_cierres_ * E.cie_rem

    def avisos_comunes(self) -> None:
        P, cat, E = self.P, self.cat, self.E
        if P.get("sistema") == "hibrido":
            self.A.append("Esta forma de case se arma con ángulo de aluminio: se ignora el perfil híbrido.")
        if float(P.get("espuma_esp", 0) or 0) > 0 or P.get("ref_espuma"):
            self.A.append("La espuma de pared no se calcula en esta forma de case: las medidas son sin espuma.")
        if P.get("herrajes_manuales"):
            self.A.append("Los herrajes a mano todavía no se ubican en esta forma de case: quedan fuera del diseño.")
        if P.get("paneles_material"):
            self.A.append("El material por panel no se aplica en esta forma de case: todo va de la placa general.")
        if P.get("bandejas") or P.get("encastres") or float(P.get("acceso_lateral", 0) or 0) > 0:
            self.A.append("Bandejas, platos de apilado y tapas de acceso laterales no se resuelven en esta forma de "
                          "case: quedan fuera del diseño.")
        refs = [[P.get("ref_placa"), "placa"], [P.get("ref_angulo"), "angulo"], [P.get("ref_esquinero"), "esquinero"],
                [P.get("ref_cierre"), "cierre"], [P.get("ref_manija"), "manija"], [P.get("ref_rueda"), "rueda"],
                [P.get("ref_rueda_freno"), "rueda"], [P.get("ref_bisagra"), "bisagra"], [P.get("ref_pie"), "pie"],
                [P.get("ref_cierre_macho"), "tapa_m"], [P.get("ref_cierre_hembra"), "tapa_h"]]
        for r, tipo in refs:
            if r and not cat.existe(r):
                self.A.append(s("La referencia ", r, " no está en el catálogo: revisá el número."))
            elif r and cat.categoria(r) != tipo and not (tipo.startswith("tapa") and cat.categoria(r) == "hibrido"):
                self.A.append(s("La referencia ", r, " (", cat.nombre(r), ") no es del tipo esperado (", tipo, ")."))
        est = [r for r, tipo in refs if r and cat.existe(r) and not cat.verificado(r)
               and tipo in ("angulo", "esquinero", "cierre", "manija", "rueda")]
        if est:
            self.A.append("Medidas estimadas (no figuran en el catálogo) para " + ", ".join(dict.fromkeys(est))
                          + ": confirmalas con el herraje real antes de cortar o calar.")
        L_pl, A_pl = E.placa_largo - 2 * P.get("placa_margen", 10), E.placa_ancho - 2 * P.get("placa_margen", 10)
        for p in self.paneles:
            if p.id in [m[0] for m in self.panelmat]:
                continue
            if not ((p.ancho <= L_pl and p.alto <= A_pl) or (p.alto <= L_pl and p.ancho <= A_pl)):
                self.A.append(s("El panel ", p.nombre, " no entra en una placa de ", E.placa_largo, "x", E.placa_ancho, "."))
        barra, kerf = P.get("barra_largo", 6000), P.get("sierra_kerf", 3)
        for p in self.perfiles:
            if p.largo > barra - 2 * kerf:
                self.A.append(s("El tramo ", p.nombre, " de ", p.largo, " mm supera la barra."))
        for p in self.paneles:
            if p.ancho <= 0 or p.alto <= 0:
                self.A.append(s("El panel ", p.nombre, " da una medida negativa o cero: revisá las medidas interiores."))

    def resultado(self, forma: str, info_extra: Dict[str, List[str]], ext: Tuple[float, float, float, float],
                  inte: Tuple[float, float, float, float], mundo: Tuple[float, float, float], valores: Dict[str, Any],
                  geo: Dict[str, Any], interior=None, cierre_det: str = "", n_esq: int = 8) -> ResultadoTaller:
        P, E, cat = self.P, self.E, self.cat
        n_cie = len([m for m in self.marcas if m.tipo == "cierre" and
                     next((p.grupo for p in self.paneles if p.id == m.panel), "") != "tapa"])
        self.herrajes_comunes(n_esq, n_cie, cierre_det)
        if interior is not None:
            self.extras += [list(e) for e in interior.extras]
            self.H += [list(h) for h in interior.herrajes]
            self.A += interior.avisos
        for e in P.get("extras") or []:
            self.H.append([cat.nombre(e[0]) if cat.existe(e[0]) else e[0], e[1], "extra", e[0]])
        total = self.remaches + self.remaches_de_perfiles()
        self.H.append([cat.nombre(E.remache_ref) if E.remache_ref is not None else s("Remache pop Ø", P.get("remache_d")),
                       math.ceil(total * 1.1), s("estimado: paso ", P.get("remache_paso"), " mm, +10%"),
                       E.remache_ref if E.remache_ref is not None else ""])
        self.avisos_comunes()
        extras_p = [[e[0], e[1], e[2], e[3], e[4] if len(e) > 4 else 1, e[5] if len(e) > 5 else s("Placa ", e[3], " mm")]
                    for e in list(P.get("piezas_extra") or []) + self.extras]
        alto_r = (E.rueda_alto if int(P.get("ruedas", 0) or 0) == 4 else (E.pie_h if int(P.get("pies", 0) or 0) == 4 else 0))
        info = {
            "sistema": ["angulo"], "material": [E.material], "espesor": [fmt(E.t)],
            "color": [P.get("color_placa"), P.get("color_placa") if P.get("color_tapa") == "" else P.get("color_tapa")],
            "interior": [fmt(v) for v in inte], "exterior": [fmt(v) for v in ext], "espuma": ["0"],
            "tapa_abatible": ["0", fmt(P.get("topes", 0))],
            "tipo": ["1", "vertical", "0", fmt(ext[2]), fmt(ext[3])],
            "mundo": [fmt(round(v, 1)) for v in mundo],
            "barra": [fmt(P.get("barra_largo")), fmt(P.get("sierra_kerf"))],
            "montaje": [fmt(v) for v in (P.get("remache_paso"), E.remache_d, E.ed, 1 if P.get("manijas") else 0,
                                         P.get("rueda_frenos"), 0, n_cie, 1 if E.cie_emb else 0,
                                         sum(h[1] for h in self.H if h[0].lower().startswith("bisagra")),
                                         1 if int(P.get("pies", 0) or 0) == 4 else 0, 1 if E.man_emb else 0)],
            "encastres": ["0", "0"],
            "ruedas": [fmt(4 if int(P.get("ruedas", 0) or 0) == 4 else 0), fmt(alto_r), fmt(E.rueda_aguj_d),
                       fmt(E.rueda_aguj[0]), fmt(E.rueda_aguj[1])],
            "placa": [fmt(E.placa_largo), fmt(E.placa_ancho), fmt(P.get("placa_kerf")), fmt(P.get("placa_margen")),
                      P.get("ref_placa")],
            "cantidad": [fmt(P.get("cantidad_cases"))],
            "cierre": [fmt(1 if P.get("cierre_hibrido") else 0), P.get("ref_cierre_macho"), fmt(E.m_alto),
                       fmt(E.h_alto), fmt(E.m_sup), fmt(E.h_sup), fmt(E.sal), fmt(cat.dato(P.get("ref_cierre_macho"), "canal", 0)),
                       fmt(E.t)],
            "descuento": ["0"],
            "forma": [forma, NOMBRES[forma]],
        }
        info.update(info_extra)
        geo_base = dict(
            forma=forma, colocaciones=self.col, espesor=E.t, horizontal=False, frontal=False, dos_tapas=False,
            hibrido=False, cubierta=False, acceso=False, base=None, puertas=None, cierre_saliente=E.sal,
            ala_arista=E.ala, ala=E.ala, arista_esp=E.ae, esq_pata=E.pata, esq_descuento=E.ed,
            cierre_m_alto=E.m_alto, cierre_h_alto=E.h_alto, cierre_m_sup=E.m_sup, cierre_h_sup=E.h_sup, aristas=self.aristas, bloques=self.bloques,
            esquineros=self.esquineros, herrajes=self.herr, ruedas_abajo=self.ruedas, pies_abajo=self.pies,
            pie_d=E.pie_d, pie_h=E.pie_h, rueda_placa=list(E.rueda_placa), rueda_diametro=E.rueda_d,
            rueda_alto=E.rueda_alto if int(P.get("ruedas", 0) or 0) == 4 else 0, rueda_frenos=P.get("rueda_frenos", 2),
            rueda_dims={t_: [E.rueda_d, E.rueda_alto] for t_ in ("giratoria", "freno", "fija")},
            ruedas_tipos=["freno" if i < int(P.get("rueda_frenos", 2) or 0) else "giratoria" for i in range(4)],
            bandejas=[], interior=interior, ruedas=[], pies=[],
        )
        geo_base.update(geo)
        mats = {}
        val = {"pared": E.t, "placa_largo": E.placa_largo, "placa_ancho": E.placa_ancho, "placa_esp": E.t,
               "placa_material": E.material, "placa_kerf": P.get("placa_kerf"), "placa_margen": P.get("placa_margen"),
               "barra_largo": P.get("barra_largo"), "sierra_kerf": P.get("sierra_kerf"),
               "cantidad_cases": P.get("cantidad_cases"), "remache_ref": E.remache_ref, "materiales_paneles": mats,
               "geo": geo_base, "interiores": interior, "manuales": None, "forma": forma,
               "perforacion": self._perforacion()}
        val.update(valores)
        herrajes = [Herraje(*h) for h in self.H]
        return ResultadoTaller(info=info, paneles=self.paneles, calados=self.calados, marcas=self.marcas,
                               perfiles=self.perfiles, extras=extras_p, herrajes=herrajes, panelmat=self.panelmat,
                               bandejas=[], avisos=self.A, valores=val)


class _Plano:
    """Marco de un plano de cierre: Q(x, s, h) = p0 + x·e1 + s·e2 + h·e3 (e3 hacia la tapa)."""

    def __init__(self, p0: Vec, e1: Vec, e2: Vec, e3: Vec) -> None:
        self.p0, self.e1, self.e2, self.e3 = p0, e1, e2, e3

    def __call__(self, x: float, s_: float, h: float) -> Vec:
        return _sum(self.p0, _mul(self.e1, x), _mul(self.e2, s_), _mul(self.e3, h))


def _tapa(ar: _Armado, Q: _Plano, X: float, S: float, int_alto_tapa: float, bisagras_atras: int) -> Dict[str, float]:
    """Tapa recta sobre el plano de cierre Q (como la tapa de modelo.py con paredes_enteras "frente"):
    techo entre las paredes, frente y trasera enteros, laterales entre ellos. Agrega el aro hembra,
    las aristas, los esquineros y las marcas de los cierres en la tapa."""
    E, t = ar.E, ar.E.t
    e1, e2, e3 = Q.e1, Q.e2, Q.e3
    alto = int_alto_tapa + t
    hp = alto - E.h_sup
    ar.panel("techo", "Techo (tapa)", "tapa", X - 2 * t, S - 2 * t, Q(t, t, alto), e1, e2, _neg(e3))
    ar.panel("tapa_frente", "Frente tapa", "tapa", X, hp, Q(0, 0, E.h_sup), e1, e3, e2)
    ar.panel("tapa_trasera", "Trasera tapa", "tapa", X, hp, Q(X, S, E.h_sup), _neg(e1), e3, _neg(e2))
    ar.panel("tapa_izq", "Lateral izq. tapa", "tapa", S - 2 * t, hp, Q(0, S - t, E.h_sup), _neg(e2), e3, e1)
    ar.panel("tapa_der", "Lateral der. tapa", "tapa", S - 2 * t, hp, Q(X, t, E.h_sup), e2, e3, _neg(e1))
    ar.aro(Q, X, S, 0, E.h_alto, "profile_h", "tapa", "Perfil de cierre hembra", paso=F_TAPA)
    ed = E.ed
    for s0, sy in ((0.0, -1), (S, 1)):
        ar.arista(Q(ed, s0, alto), _mul(e2, sy), e3, e1, X - 2 * ed, "tapa", F_TAPA)
    for x0, sx in ((0.0, -1), (X, 1)):
        ar.arista(Q(x0, ed, alto), _mul(e1, sx), e3, e2, S - 2 * ed, "tapa", F_TAPA)
    for x0, sx in ((0.0, -1), (X, 1)):
        for s0, sy in ((0.0, -1), (S, 1)):
            ar.arista(Q(x0, s0, E.h_alto), _mul(e1, sx), _mul(e2, sy), e3, alto - E.h_alto - ed, "tapa", F_TAPA)
            ar.esquinero(Q(x0, s0, alto), _mul(e1, sx), _mul(e2, sy), e3, "tapa", F_TAPA)
    return dict(alto=alto, hp=hp, L_zt=alto - E.h_alto - ed)


def _perfiles_aro(ar: _Armado, X: float, S: float, desc_s: str, macho_recto: bool = False) -> None:
    E = ar.E
    if macho_recto:     # baúl plegable: cada pared lleva su tramo, sin inglete
        ar.tramo(E.macho, "Frente y trasera (entre los laterales)", X - 2 * E.t, 2, "recto", E.ref_macho)
        ar.tramo(E.macho, "Laterales (de punta a punta)", S + 2 * E.sal, 2, "recto", E.ref_macho)
    else:
        ar.tramo(E.macho, "Frente y trasera (punta larga)", X + 2 * E.sal, 2, "45/45", E.ref_macho)
        ar.tramo(E.macho, desc_s, S + 2 * E.sal, 2, "45/45", E.ref_macho)
    ar.tramo(E.hembra, "Frente y trasera (punta larga)", X + 2 * E.sal, 2, "45/45", E.ref_hembra)
    ar.tramo(E.hembra, desc_s, S + 2 * E.sal, 2, "45/45", E.ref_hembra)


def _cierres_tapa(ar: _Armado, Q: _Plano, X: float, S: float, cuerpo_ids: Dict[str, Tuple[str, Any, Any]],
                  bisagras: int, ref_bisagra: str, mueve_cuerpo: Dict[str, str]) -> str:
    """Cierres (y bisagras atrás) entre el cuerpo y la tapa. `cuerpo_ids[cara]` = (panel, f_x, f_y): la
    posición en ese panel de un punto a s (o x) del plano, a `b` mm bajo el plano."""
    P, E = ar.P, ar.E
    e1, e2, e3 = Q.e1, Q.e2, Q.e3
    margen = P.get("cierre_margen", 100)
    lat = P.get("cierres_laterales", "auto")
    lat_si = True if lat == "si" else (False if lat == "no" else S > 450)
    nf = int(P.get("cierres_frente_n", 0) or 0)
    nl = int(P.get("cierres_lateral_n", 0) or 0)
    xs = _pos_n(X, nf if nf > 0 else n_cierres(X), margen) if nf >= 0 else []
    ss = _pos_n(S, nl if nl > 0 else n_cierres(S), margen) if lat_si else []
    b = E.m_alto - E.m_sup
    yt = E.h_alto - E.h_sup
    caras = [("frente", xs), ("izq", ss), ("der", ss)]
    piano = ar.cat.existe(ref_bisagra) and ar.cat.dato(ref_bisagra, "largo", 0) > 0
    if bisagras <= 0:
        caras.append(("trasera", xs))
    for cara, lista in caras:
        pid, fx, fy = cuerpo_ids[cara]
        for q in lista:
            ar.marcas.append(Marca(pid, "cierre", fx(q), fy(q, b), 0, 0, "c1"))
            if cara == "frente":
                ar.marcas.append(Marca("tapa_frente", "cierre", q, yt, 0, 0, "c1"))
                o, u, n = Q(0, 0, 0), e1, e2
            elif cara == "trasera":
                ar.marcas.append(Marca("tapa_trasera", "cierre", X - q, yt, 0, 0, "c1"))
                o, u, n = Q(X, S, 0), _neg(e1), _neg(e2)
                q = X - q
            elif cara == "izq":
                ar.marcas.append(Marca("tapa_izq", "cierre", S - E.t - q, yt, 0, 0, "c1"))
                o, u, n = Q(0, S, 0), _neg(e2), e1
                q = S - q
            else:
                ar.marcas.append(Marca("tapa_der", "cierre", q - E.t, yt, 0, 0, "c1"))
                o, u, n = Q(X, 0, 0), e2, _neg(e1)
            ar.cierre(o, u, e3, n, q, mueve_cuerpo.get(cara, "cuerpo"))
            ar.gancho(o, u, e3, n, q)
    if bisagras > 0:
        pid, fx, fy = cuerpo_ids["trasera"]
        if piano:
            L = X - 2 * (E.pata + 10)
            ar.H.append([ar.cat.nombre(ref_bisagra), 1, s("cortar a ", L, " mm"), ref_bisagra])
            ar.remaches += 2 * (math.floor(L / 50) + 1)
            ar.bloque(Q(E.pata + 10, S + E.sal, -8), e1, e2, e3, L, 3, 16, "cierre", "Bisagra de piano", "cuerpo",
                      F_CIERRES)
        else:
            for q in _pos_n(X, bisagras, margen):
                ar.marcas.append(Marca(pid, "bisagra", fx(q), fy(q, b), 0, 0, "c1"))
                ar.marcas.append(Marca("tapa_trasera", "bisagra", X - q, yt, 0, 0, "c1"))
                ar.herraje3d("bisagra", Q(X, S, 0), _neg(e1), e3, _neg(e2), X - q, (-b - 35, -b + 14))
                ar.herraje3d("bisagra", Q(X, S, 0), _neg(e1), e3, _neg(e2), X - q, (yt + 14, yt - 22), "tapa", -1.0)
            nom = ar.cat.nombre(ref_bisagra) if ar.cat.existe(ref_bisagra) else "Bisagra"
            ar.H.append([nom, bisagras, "en la trasera", ref_bisagra])
            ar.remaches += ar.cat.dato(ref_bisagra, "remaches", 6) * bisagras
        topes = int(P.get("topes", 0) or 0)
        if topes:
            ref_t = P.get("ref_tope", "")
            ar.H.append([ar.cat.nombre(ref_t) if ar.cat.existe(ref_t) else "Tope de tapa", topes,
                         "sostiene la tapa abierta", ref_t])
            ar.remaches += ar.cat.dato(ref_t, "remaches", 8) * topes
    txt = ["frente"] + (["laterales"] if lat_si else []) + ([] if bisagras > 0 else ["trasera"])
    return " y ".join([", ".join(txt[:-1]), txt[-1]] if len(txt) > 1 else txt)


# ---------------------------------------------------------------------------
# Rack inclinado para consola
# ---------------------------------------------------------------------------

def _rack_inclinado(P: Dict[str, Any], cat: CatalogoTaller) -> ResultadoTaller:
    ar = _Armado(P, cat)
    E, t = ar.E, ar.E.t
    W, D = float(P["int_ancho"]), float(P["int_prof"])
    Hr = float(P["int_alto_cuerpo"])                 # alto interior atrás
    Hf = float(P.get("incl_alto_frente", 150))       # alto interior adelante
    X, Y = W + 2 * t, D + 2 * t
    zf, zr = Hf + t, Hr + t
    alfa = math.atan2(zr - zf, Y)
    ca, sa, ta = math.cos(alfa), math.sin(alfa), math.tan(alfa)
    S = Y / ca
    grados = round(math.degrees(alfa), 1)
    Q = _Plano((0.0, 0.0, zf), (1.0, 0.0, 0.0), (0.0, ca, sa), (0.0, -sa, ca))
    if Hr <= Hf:
        ar.A.append("En el rack inclinado la trasera tiene que ser más alta que el frente (int_alto_cuerpo es el alto "
                    "interior de atrás e incl_alto_frente el de adelante): con estas medidas no hay pendiente.")
    if abs(grados) > 30:
        ar.A.append(s("La pendiente da ", grados, "°: con más de 30° el perfil de cierre no abraza bien el canto "
                      "biselado del frente y de la trasera, y la consola queda muy parada. Revisá los altos."))

    def z_top(y: float) -> float:   # canto de arriba de las paredes (bajo el perfil macho)
        return zf + y * ta - E.m_sup / ca

    bisel = s(" (canto de arriba a ", abs(grados), "°)") if abs(grados) >= 0.5 else ""
    # ---- cuerpo ----
    ar.panel("piso", "Piso (cuerpo)", "cuerpo", X - 2 * t, Y - 2 * t, (t, t, 0.0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    h_fr_out, h_fr_in = z_top(0), z_top(t)
    h_tr_out, h_tr_in = z_top(Y), z_top(Y - t)
    ar.panel("cuerpo_frente", "Frente cuerpo" + bisel, "cuerpo", X, max(h_fr_out, h_fr_in), (0.0, 0.0, 0.0),
             (1, 0, 0), (0, 0, 1), (0, 1, 0))
    ar.panel("cuerpo_trasera", "Trasera cuerpo" + bisel, "cuerpo", X, max(h_tr_out, h_tr_in), (X, Y, 0.0),
             (-1, 0, 0), (0, 0, 1), (0, -1, 0))
    alto_lat = max(z_top(t), z_top(Y - t))
    ar.panel("cuerpo_izq", "Lateral izq. cuerpo (trapecio)", "cuerpo", D, alto_lat, (0.0, Y - t, 0.0), (0, -1, 0),
             (0, 0, 1), (1, 0, 0), contorno=[(0, 0), (D, 0), (D, z_top(t)), (0, z_top(Y - t))])
    ar.panel("cuerpo_der", "Lateral der. cuerpo (trapecio)", "cuerpo", D, alto_lat, (X, t, 0.0), (0, 1, 0),
             (0, 0, 1), (-1, 0, 0), contorno=[(0, 0), (D, 0), (D, z_top(Y - t)), (0, z_top(t))])
    # en la vista 3D el frente y la trasera se dibujan con el alto de su cara más baja
    for c in ar.col:
        if c["id"] == "cuerpo_frente":
            c["alto_3d"] = min(h_fr_out, h_fr_in)
        if c["id"] == "cuerpo_trasera":
            c["alto_3d"] = min(h_tr_out, h_tr_in)
    ar.aro(Q, X, S, -E.m_alto, E.m_alto, "profile", "cuerpo", "Perfil de cierre macho")
    # ---- tapa sobre el plano inclinado ----
    tp = _tapa(ar, Q, X, S, float(P["int_alto_tapa"]), int(P.get("bisagras", 0) or 0))
    # ---- aristas y esquineros del cuerpo ----
    ed = E.ed
    for y0, sy in ((0.0, -1), (Y, 1)):
        ar.arista((ed, y0, 0.0), (0, sy, 0), (0, 0, -1), (1, 0, 0), X - 2 * ed)
    for x0, sx in ((0.0, -1), (X, 1)):
        ar.arista((x0, ed, 0.0), (sx, 0, 0), (0, 0, -1), (0, 1, 0), Y - 2 * ed)
    L_f = zf - E.m_alto / ca - ed
    L_r = zr - E.m_alto / ca - ed
    for x0, sx in ((0.0, -1), (X, 1)):
        for y0, sy, L in ((0.0, -1, L_f), (Y, 1, L_r)):
            ar.arista((x0, y0, ed), (sx, 0, 0), (0, sy, 0), (0, 0, 1), L)
            ar.esquinero((x0, y0, 0.0), (sx, 0, 0), (0, sy, 0), (0, 0, -1))
    # ---- perfiles ----
    A_ = E.perfil_arista
    ar.tramo(A_, "Aristas a lo ancho (piso)", X - 2 * ed, 2, "recto", E.ref_arista)
    ar.tramo(A_, "Aristas a lo profundo (piso)", Y - 2 * ed, 2, "recto", E.ref_arista)
    corte_v = s(" (punta de arriba a ", abs(grados), "°)") if abs(grados) >= 0.5 else ""
    ar.tramo(A_, "Verticales del frente" + corte_v, L_f, 2, "recto", E.ref_arista)
    ar.tramo(A_, "Verticales de la trasera" + corte_v, L_r, 2, "recto", E.ref_arista)
    ar.tramo(A_, "Aristas a lo ancho (techo de la tapa)", X - 2 * ed, 2, "recto", E.ref_arista)
    ar.tramo(A_, "Aristas a lo largo de la pendiente (techo de la tapa)", S - 2 * ed, 2, "recto", E.ref_arista)
    ar.tramo(A_, "Verticales de la tapa (perpendiculares al plano)", tp["L_zt"], 4, "recto", E.ref_arista)
    _perfiles_aro(ar, X, S, "Lados de la pendiente (punta larga)")

    # ---- cierres: posiciones sobre cada pared del cuerpo ----
    def en_lado(izq: bool):
        def fx(q):     # q = distancia sobre la pendiente desde el frente
            y = q * ca
            return (Y - t - y) if izq else (y - t)

        def fy(q, b):
            return z_top(q * ca) - b
        return fx, fy
    ids = {"frente": ("cuerpo_frente", lambda q: q, lambda q, b: h_fr_out - b),
           "trasera": ("cuerpo_trasera", lambda q: X - q, lambda q, b: h_tr_out - b),
           "izq": ("cuerpo_izq",) + en_lado(True), "der": ("cuerpo_der",) + en_lado(False)}
    det = _cierres_tapa(ar, Q, X, S, ids, int(P.get("bisagras", 0) or 0), P.get("ref_bisagra", ""), {})
    ar.calados_cierre()
    # ---- manijas en los laterales, en la mitad del largo, bajo el canto inclinado ----
    xm = D / 2
    y_bajo = Y / 2 - (E.man_w / 2 if alfa > 0 else -E.man_w / 2)    # punta de la manija del lado más bajo
    zc_m = z_top(y_bajo) - P.get("manija_centro_desde_arriba", 80)
    if P.get("manijas") and zc_m + E.man_h / 2 > z_top(y_bajo) - (E.m_alto - E.m_sup) - 10:
        ar.A.append("La manija invade el perfil de cierre en el lado bajo de la pendiente: aumentá "
                    "manija_centro_desde_arriba.")
    ar.manijas_en(["cuerpo_izq", "cuerpo_der"], {"cuerpo_izq": (xm, zc_m), "cuerpo_der": (xm, zc_m)})
    if P.get("manijas") and zc_m - E.man_h / 2 < E.ala + 10:
        ar.A.append("La manija queda muy cerca del piso: el frente del rack inclinado es bajo para esa manija.")
    # ---- rack de 19" adelante, bajo la pendiente (rack para mezcladora 2) ----
    u_fr = int(P.get("incl_rack_frente", 0) or 0)
    if u_fr > 0:
        alto_r = u_fr * 44.45
        z0 = t + 5.0                                  # boca del rack: 5 mm sobre el piso
        tope = min(h_fr_out, h_fr_in) - (E.m_alto - E.m_sup) - 10
        if z0 + alto_r > tope:
            ar.A.append(s("Los ", u_fr, " U del rack de adelante no entran bajo la pendiente: el frente da lugar para ",
                          max(0, math.floor((tope - z0) / 44.45)), " U. Subí incl_alto_frente o bajá incl_rack_frente."))
        if W < 483:
            ar.A.append(s("El rack de adelante necesita ", 483, " mm de ancho interior (orejas de 19\"): hay ", W, " mm."))
        ar.calados.append(Calado("cuerpo_frente", "conector", X / 2, z0 + alto_r / 2, 450.0, alto_r, 3.0))
        for xr in (X / 2 - 241.5, X / 2 + 225.0):     # rieles detrás del frente, a los costados de la boca
            ar.bloque((xr, t, z0), (1, 0, 0), (0, 0, 1), (0, 1, 0), 16.5, alto_r, 15.0, "profile", "Riel de rack",
                      "cuerpo", F_AROS)
        ref_riel = str(P.get("ref_riel") or "")
        nom_riel = cat.nombre(ref_riel) if cat.existe(ref_riel) else "Perfil de rack 19\" 45U"
        ar.H.append([nom_riel, 1, s("cortar 2 tramos de ", u_fr, " U (", round(alto_r, 2), " mm) para el rack de adelante"),
                     ref_riel])
        ar.H.append(["Tornillo para fijar el riel al frente", 2 * (int(alto_r // 100) + 2),
                     "cada 100 mm, por fuera del frente, que no atraviese el riel", ""])
    # ---- ruedas y pies bajo el piso ----
    ar.ruedas_abajo("piso", X - 2 * t, Y - 2 * t, (t, t, 0.0), (1, 0, 0), (0, 1, 0), E.pata + P.get("rueda_margen", 10) - t)
    ar.pies_abajo("piso", X - 2 * t, Y - 2 * t, (t, t, 0.0), (1, 0, 0), (0, 1, 0), E.pata + P.get("rueda_margen", 10) - t)

    # ---- rieles de rack sobre la pendiente (interiores.py en el marco del plano) ----
    interior = None
    # fondo libre bajo el plano, medido perpendicular a la pendiente, en el canto interior del frente
    fondo_frente = -((t - 0) * -sa + (t - zf) * ca)
    if P.get("incl_rieles", True):
        from . import interiores as _int
        Pi = dict(P)
        for k_ in ("equipos", "espumas", "cajones", "bandejas"):
            Pi[k_] = []
        largo_util = S - 2 * t
        if int(P.get("rack_u", 0) or 0) <= 0 and not P.get("rack_equipos"):
            Pi["rack_u"] = int(math.floor(largo_util / _int.U_MM + 1e-6))
        Pi["rack_traseros"] = False
        zc_v = fondo_frente + t
        ctx = dict(horizontal=False, frontal=False, dos_tapas=False, ext_ancho=X, ext_prof=S,
                   ext_alto=zc_v + tp["alto"], pared=t, espuma=0.0, z_cierre=zc_v, z_cierre2=0.0, bandejas=[],
                   band_esp=lambda b: t)
        if Pi["rack_u"] > 0 or Pi.get("rack_equipos"):
            interior = _int.calcular(Pi, ctx, cat)
            interior.avisos = [a.replace("tapa trasera", "tapa") for a in interior.avisos]
            if interior.rack:
                interior.rack["inclinado"] = grados
                interior.resumen = [r.replace("rieles a", s("rieles paralelos a la pendiente de ", abs(grados), "°, a"))
                                    for r in interior.resumen]
        if P.get("equipos") or P.get("espumas") or P.get("cajones"):
            ar.A.append("En el rack inclinado sólo se ubica el rack de 19\" sobre la pendiente: equipos sueltos, "
                        "espuma y cajones quedan fuera del diseño.")
    marco_int = dict(p0=Q(0, 0, -(fondo_frente + t)), e1=Q.e1, e2=Q.e2, e3=Q.e3) if interior is not None else None

    pts = [(0, 0, 0), (X, Y, zr), Q(0, 0, tp["alto"]), Q(X, S, tp["alto"]), Q(0, -E.sal, 0)]
    mundo = (X, max(p[1] for p in pts) - min(p[1] for p in pts), max(p[2] for p in pts))
    info_extra = {"inclinado": [fmt(grados), fmt(round(S, 2)), fmt(round(zf, 2)), fmt(round(zr, 2)),
                                fmt(round(fondo_frente, 1)), fmt(max(0, u_fr))]}
    geo = dict(mover={"tapa": Q.e3}, marco_interior=marco_int, plano=dict(p0=Q.p0, e2=Q.e2, e3=Q.e3, S=S))
    valores = {"ext_ancho": X, "ext_prof": Y, "ext_alto": max(p[2] for p in pts), "incl_grados": grados,
               "incl_largo": S}
    return ar.resultado("inclinado", info_extra, (X, Y, zr, tp["alto"]), (W, D, Hr, float(P["int_alto_tapa"])),
                        mundo, valores, geo, interior, det)


# ---------------------------------------------------------------------------
# Funda de rack (sleeve)
# ---------------------------------------------------------------------------

def _funda(P: Dict[str, Any], cat: CatalogoTaller) -> ResultadoTaller:
    ar = _Armado(P, cat)
    E, t = ar.E, ar.E.t
    W, Hi, D = float(P["int_ancho"]), float(P["int_prof"]), float(P["int_alto_cuerpo"])
    X, Z = W + 2 * t, Hi + 2 * t
    ar.panel("piso", "Piso", "cuerpo", X, D, (0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    ar.panel("techo", "Techo", "cuerpo", X, D, (0.0, 0.0, Z), (1, 0, 0), (0, 1, 0), (0, 0, -1))
    ar.panel("cuerpo_izq", "Lateral izq.", "cuerpo", D, Hi, (0.0, D, t), (0, -1, 0), (0, 0, 1), (1, 0, 0))
    ar.panel("cuerpo_der", "Lateral der.", "cuerpo", D, Hi, (X, 0.0, t), (0, 1, 0), (0, 0, 1), (-1, 0, 0))
    ed = E.ed
    A_ = E.perfil_arista
    for x0, sx in ((0.0, -1), (X, 1)):
        for z0, sz in ((0.0, -1), (Z, 1)):
            ar.arista((x0, ed, z0), (sx, 0, 0), (0, 0, sz), (0, 1, 0), D - 2 * ed)
    for y0, sy in ((0.0, -1), (D, 1)):
        for z0, sz in ((0.0, -1), (Z, 1)):
            ar.arista((ed, y0, z0), (0, sy, 0), (0, 0, sz), (1, 0, 0), X - 2 * ed)
        for x0, sx in ((0.0, -1), (X, 1)):
            ar.arista((x0, y0, ed), (0, sy, 0), (sx, 0, 0), (0, 0, 1), Z - 2 * ed)
            for z0, sz in ((0.0, -1), (Z, 1)):
                ar.esquinero((x0, y0, z0), (sx, 0, 0), (0, sy, 0), (0, 0, sz))
    ar.tramo(A_, "Aristas a lo profundo", D - 2 * ed, 4, "recto", E.ref_arista)
    ar.tramo(A_, "Borde de las bocas, a lo ancho (tapa el canto del piso y del techo)", X - 2 * ed, 4, "recto",
             E.ref_arista)
    ar.tramo(A_, "Borde de las bocas, a lo alto (tapa el canto de los laterales)", Z - 2 * ed, 4, "recto",
             E.ref_arista)
    # manijas a los costados (asa acostada si la funda es baja)
    ar.manijas_en(["cuerpo_izq", "cuerpo_der"], {"cuerpo_izq": (D / 2, Hi / 2), "cuerpo_der": (D / 2, Hi / 2)},
                  acostada=False)
    if P.get("manijas") and E.man_h > Hi - 2 * (E.ala + 10):
        ar.A.append("La manija no entra en el lateral: la funda es muy baja para esa manija.")
    ar.pies_abajo("piso", X, D, (0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), E.pata + P.get("rueda_margen", 10))
    ar.ruedas_abajo("piso", X, D, (0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), E.pata + P.get("rueda_margen", 10))
    if int(P.get("tapas", 1) or 1) == 2 or int(P.get("bisagras", 0) or 0) > 0 or P.get("puertas"):
        ar.A.append("La funda no lleva tapas ni bisagras: va abierta adelante y atrás (para meterla en otro case o "
                    "usarla así en un estante).")
    # rieles adelante y atrás (interiores.py como un rack frontal sin tapas)
    from . import interiores as _int
    Pi = dict(P)
    interior = None
    if int(P.get("rack_u", 0) or 0) <= 0 and not P.get("rack_equipos"):
        Pi["rack_u"] = int(math.floor(Hi / _int.U_MM + 1e-6))
    ctx = dict(horizontal=False, frontal=True, dos_tapas=True, ext_ancho=X, ext_prof=Z, ext_alto=D, pared=t,
               espuma=0.0, z_cierre=D, z_cierre2=0.0, bandejas=[], band_esp=lambda b: t)
    if _int.hay_interiores(Pi):
        interior = _int.calcular(Pi, ctx, cat)
    mundo = (X + 2 * E.ae, D, Z)
    valores = {"ext_ancho": X, "ext_prof": Z, "ext_alto": D}
    return ar.resultado("funda", {}, (X, Z, D, 0), (W, Hi, D, 0), mundo, valores, dict(mover={}), interior, "")


# ---------------------------------------------------------------------------
# Baúl plegable
# ---------------------------------------------------------------------------

def _plegable(P: Dict[str, Any], cat: CatalogoTaller) -> ResultadoTaller:
    ar = _Armado(P, cat)
    E, t = ar.E, ar.E.t
    W, D = float(P["int_ancho"]), float(P["int_prof"])
    Hc = float(P["int_alto_cuerpo"])          # de la cara de arriba de la base al plano de cierre
    tb = float(P.get("pleg_base_esp", 18) or 18)
    X, Y = W + 2 * t, D + 2 * t
    zc = tb + Hc
    # entre niveles plegados: el espesor de la pared y, con cierres de superficie, lo que sobresalen
    holg = 0.0 if E.cie_emb else 12.0
    paso_n = t + holg
    h_libre = Hc - E.m_sup                      # alto de una pared apoyada en la base
    # frente y trasera: si no entran una al lado de la otra, la trasera va sobre un suplemento
    nivel_tr = 0.0 if 2 * h_libre <= D else paso_n
    h_fr, h_tr = h_libre, h_libre - nivel_tr
    n_fb = 1 if nivel_tr == 0 else 2
    nivel_izq = n_fb * paso_n
    h_izq = h_libre - nivel_izq
    nivel_der = nivel_izq if 2 * h_izq <= W else nivel_izq + paso_n
    h_der = h_libre - nivel_der
    alto_plegado = tb + nivel_der + t + holg
    # ---- base y paredes ----
    mat_base = P.get("pleg_base_material") or s("Placa ", tb, " mm")
    ar.panel("base", "Base (con las ruedas)", "cuerpo", X, Y, (0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), (0, 0, 1), esp=tb,
             mueve="cuerpo")
    ar.panelmat.append(["base", mat_base, tb])
    ar.panel("cuerpo_frente", "Pared del frente (se pliega 1.ª)", "cuerpo", X - 2 * t, h_fr, (t, 0.0, tb),
             (1, 0, 0), (0, 0, 1), (0, 1, 0), mueve="p_frente")
    ar.panel("cuerpo_trasera", "Pared trasera (se pliega 2.ª)" if n_fb == 2 else "Pared trasera (se pliega 1.ª)",
             "cuerpo", X - 2 * t, h_tr, (X - t, Y, tb + nivel_tr), (-1, 0, 0), (0, 0, 1), (0, -1, 0), mueve="p_trasera")
    ar.panel("cuerpo_izq", "Lateral izq. (se pliega después)", "cuerpo", Y, h_izq, (0.0, Y, tb + nivel_izq),
             (0, -1, 0), (0, 0, 1), (1, 0, 0), mueve="p_izq")
    ar.panel("cuerpo_der", "Lateral der. (se pliega último)", "cuerpo", Y, h_der, (X, 0.0, tb + nivel_der),
             (0, 1, 0), (0, 0, 1), (-1, 0, 0), mueve="p_der")
    # suplementos bajo las bisagras: tiras de la misma placa, paradas en el plano de la pared y
    # atornilladas a la base. La bisagra de piano va de la cara interior de la tira a la de la pared.
    sup = []
    if nivel_tr > 0:
        sup.append(("Suplemento bajo la pared trasera", X - 2 * t, nivel_tr, 1))
    if nivel_izq == nivel_der:
        sup.append(("Suplemento bajo los laterales", Y, nivel_izq, 2))
    else:
        sup.append(("Suplemento bajo el lateral izq.", Y, nivel_izq, 1))
        sup.append(("Suplemento bajo el lateral der.", Y, nivel_der, 1))
    for nombre, largo, alto, cant in sup:
        ar.extras.append([nombre, round(largo, 2), round(alto, 2), t, cant, E.material])
    if nivel_tr > 0:
        ar.bloque((t, Y - t, tb), (1, 0, 0), (0, 1, 0), (0, 0, 1), X - 2 * t, t, nivel_tr, "base", "Suplemento",
                  "cuerpo", F_CUERPO)
    ar.bloque((0.0, 0.0, tb), (1, 0, 0), (0, 1, 0), (0, 0, 1), t, Y, nivel_izq, "base", "Suplemento", "cuerpo",
              F_CUERPO)
    ar.bloque((X - t, 0.0, tb), (1, 0, 0), (0, 1, 0), (0, 0, 1), t, Y, nivel_der, "base", "Suplemento", "cuerpo",
              F_CUERPO)
    # ---- aro macho partido: cada pared lleva su tramo ----
    Q = _Plano((0.0, 0.0, zc), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    ar.aro(Q, X, Y, -E.m_alto, E.m_alto, "profile", "cuerpo", "Perfil de cierre macho",
           partes={"frente": "p_frente", "trasera": "p_trasera", "izq": "p_izq", "der": "p_der"}, cortes_rectos=True)
    tp = _tapa(ar, Q, X, Y, float(P["int_alto_tapa"]), 0)
    # ---- bisagras de piano en el canto de abajo de cada pared, del lado de adentro ----
    piano_ref = P.get("ref_bisagra", "") if cat.dato(P.get("ref_bisagra", ""), "largo", 0) > 0 else "08-2605"
    largos = [X - 2 * t - 20, X - 2 * t - 20, Y - 2 * t - 20, Y - 2 * t - 20]
    nom_p = cat.nombre(piano_ref) if cat.existe(piano_ref) else "Bisagra de piano"
    total_p = sum(largos)
    largo_barra = cat.dato(piano_ref, "largo", 1830) or 1830
    barras_p = 0
    sobras: List[float] = []
    for L in sorted(largos, reverse=True):
        for j, so in enumerate(sobras):
            if so >= L + 3:
                sobras[j] -= L + 3
                break
        else:
            barras_p += 1
            sobras.append(largo_barra - L - 3)
    ar.H.append([nom_p, barras_p, s("cortar 2 × ", round(largos[0], 1), " (frente y trasera) y 2 × ", round(largos[2], 1),
                                    " mm (laterales), una por pared en el canto de abajo, del lado de adentro"),
                 piano_ref])
    ar.H.append(["Tornillo para madera (suplementos y bisagra del frente a la base)", 2 * sum(math.floor(L / 100) + 1 for L in largos),
                 s("cada 100 mm, que no atraviesen la base de ", tb, " mm"), ""])
    ar.remaches += sum(math.floor(L / 50) + 1 for L in largos)
    for (o_, u_, L) in (((t + 10, t, tb), (1, 0, 0), largos[0]), ((t + 10, Y - t - 2, tb + nivel_tr - 15), (1, 0, 0), largos[1]),
                        ((t, t + 10, tb + nivel_izq - 15), (0, 1, 0), largos[2]),
                        ((X - t - 2, t + 10, tb + nivel_der - 15), (0, 1, 0), largos[3])):
        v_ = (0, 1, 0) if u_ == (1, 0, 0) else (1, 0, 0)
        ar.bloque(o_, u_, v_, (0, 0, 1), L, 2, 30, "cierre", "Bisagra de piano", "cuerpo", F_CIERRES)
    # ---- aristas: base, esquinas verticales (en los laterales) y tapa ----
    ed = E.ed
    for y0, sy in ((0.0, -1), (Y, 1)):
        ar.arista((ed, y0, 0.0), (0, sy, 0), (0, 0, -1), (1, 0, 0), X - 2 * ed)
    for x0, sx in ((0.0, -1), (X, 1)):
        ar.arista((x0, ed, 0.0), (sx, 0, 0), (0, 0, -1), (0, 1, 0), Y - 2 * ed)
        for y0, sy in ((0.0, -1), (Y, 1)):
            ar.esquinero((x0, y0, 0.0), (sx, 0, 0), (0, sy, 0), (0, 0, -1))
    z_ini = {0.0: tb + nivel_izq, X: tb + nivel_der}
    L_esq = {k_: zc - E.m_alto - (z0 + 5) for k_, z0 in z_ini.items()}
    for x0, sx, grupo in ((0.0, -1, "p_izq"), (X, 1, "p_der")):
        for y0, sy in ((0.0, -1), (Y, 1)):
            ar.arista((x0, y0, z_ini[x0] + 5), (sx, 0, 0), (0, sy, 0), (0, 0, 1), L_esq[x0], grupo, solo_a=True)
    A_ = E.perfil_arista
    ar.tramo(A_, "Aristas de la base a lo ancho", X - 2 * ed, 2, "recto", E.ref_arista)
    ar.tramo(A_, "Aristas de la base a lo profundo", Y - 2 * ed, 2, "recto", E.ref_arista)
    if abs(L_esq[0.0] - L_esq[X]) < 0.05:
        ar.tramo(A_, "Esquinas verticales (remachadas sólo al lateral, una fila)", L_esq[0.0], 4, "recto", E.ref_arista)
    else:
        ar.tramo(A_, "Esquinas verticales del lateral izq. (remachadas sólo al lateral, una fila)", L_esq[0.0], 2,
                 "recto", E.ref_arista)
        ar.tramo(A_, "Esquinas verticales del lateral der. (remachadas sólo al lateral, una fila)", L_esq[X], 2,
                 "recto", E.ref_arista)
    ar.tramo(A_, "Aristas a lo ancho (techo de la tapa)", X - 2 * ed, 2, "recto", E.ref_arista)
    ar.tramo(A_, "Aristas a lo profundo (techo de la tapa)", Y - 2 * ed, 2, "recto", E.ref_arista)
    ar.tramo(A_, "Verticales de la tapa", tp["L_zt"], 4, "recto", E.ref_arista)
    _perfiles_aro(ar, X, Y, "Laterales (punta larga)", macho_recto=True)
    # ---- cierres entre el cuerpo y la tapa ----
    b_ = lambda h_pared: (lambda q, b: h_pared - b)
    ids = {"frente": ("cuerpo_frente", lambda q: q - t, b_(h_fr)), "trasera": ("cuerpo_trasera", lambda q: X - t - q, b_(h_tr)),
           "izq": ("cuerpo_izq", lambda q: Y - q, b_(h_izq)), "der": ("cuerpo_der", lambda q: q, b_(h_der))}
    det = _cierres_tapa(ar, Q, X, Y, ids, 0, "", {"frente": "p_frente", "trasera": "p_trasera", "izq": "p_izq",
                                                  "der": "p_der"})
    # ---- cierres de las esquinas: traban frente y trasera contra el ángulo del lateral ----
    n_e = max(0, int(P.get("pleg_cierres_esquina", 2) or 0))
    x_c = E.ala - t + 25        # centro del cierre en la pared, pasando el ala del ángulo
    for pid, h, o_x0, o_x1, y_o, n_in, grupo in (("cuerpo_frente", h_fr, 0.0, X, 0.0, (0, 1, 0), "p_frente"),
                                                 ("cuerpo_trasera", h_tr, X, 0.0, Y, (0, -1, 0), "p_trasera")):
        z0 = tb + (nivel_tr if pid == "cuerpo_trasera" else 0.0)
        for zq in _pos_n(h, n_e, min(80.0, h / 4)) if n_e else []:
            w_p = X - 2 * t
            for lado in (0, 1):
                xl = x_c if lado == 0 else w_p - x_c
                ar.marcas.append(Marca(pid, "cierre_esquina", xl, zq, 0, 0, "esquina"))
                # en 3D: el cierre en la pared y el gancho sobre el ala del ángulo, cruzando la esquina
                xe = o_x0 if lado == 0 else o_x1
                dir_ = (1.0 if xe == 0.0 else -1.0, 0.0, 0.0)
                o_ = (xe + dir_[0] * E.ala, y_o, z0)
                ar.herraje3d("cierre", o_, (0, 0, 1), _neg(dir_), n_in, zq, (-60, -8), grupo)
                ar.herraje3d("gancho", o_, (0, 0, 1), _neg(dir_), n_in, zq, (-6, E.ala - 6),
                             "p_izq" if xe == 0.0 else "p_der")
    n_ce = 4 * n_e
    if n_ce:
        ar.H.append([cat.nombre(E.ref_cierre) if cat.existe(E.ref_cierre) else "Cierre mariposa", n_ce,
                     s(n_e, " por esquina vertical, acostado: el cierre en la pared y el gancho en el ala del ángulo del lateral"),
                     E.ref_cierre])
        ar.remaches += n_ce * E.cie_rem
    ar.calados_cierre()
    # ---- manijas en los laterales ----
    centros = {"cuerpo_izq": (Y / 2, h_izq - P.get("manija_centro_desde_arriba", 80)),
               "cuerpo_der": (Y / 2, h_der - P.get("manija_centro_desde_arriba", 80))}
    ar.manijas_en(["cuerpo_izq", "cuerpo_der"], centros)
    # ---- ruedas bajo la base ----
    ar.ruedas_abajo("base", X, Y, (0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), E.pata + P.get("rueda_margen", 10))
    ar.pies_abajo("base", X, Y, (0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), E.pata + P.get("rueda_margen", 10))
    # ---- avisos del plegado ----
    if h_fr > D - 5:
        ar.A.append(s("La pared del frente (", round(h_fr, 1), " mm) es más alta que el largo interior (", D,
                      " mm): no se puede plegar. Bajá el alto del cuerpo o hacé el case más largo."))
    if h_izq > W - 5:
        ar.A.append(s("Los laterales (", round(h_izq, 1), " mm) son más altos que el ancho interior (", W,
                      " mm): no se pueden plegar. Bajá el alto del cuerpo o hacé el case más ancho."))
    if h_der <= 0 or h_tr <= 0:
        ar.A.append("El cuerpo es muy bajo para los suplementos de las bisagras: subí int_alto_cuerpo.")
    if not E.cie_emb:
        ar.A.append(s("Con cierres de superficie, cada nivel de paredes plegadas deja ", holg,
                      " mm de luz para los cierres. Con cierres embutidos el plegado queda más bajo."))
    pliegue = [dict(mueve="p_frente", eje=(-1.0, 0.0, 0.0), centro=(0.0, t, tb)),
               dict(mueve="p_trasera", eje=(1.0, 0.0, 0.0), centro=(0.0, Y - t, tb + nivel_tr)),
               dict(mueve="p_izq", eje=(0.0, 1.0, 0.0), centro=(t, 0.0, tb + nivel_izq)),
               dict(mueve="p_der", eje=(0.0, -1.0, 0.0), centro=(X - t, 0.0, tb + nivel_der))]
    mundo = (X, Y, zc + tp["alto"])
    info_extra = {"plegable": [fmt(round(alto_plegado + tp["alto"], 1)), fmt(round(alto_plegado, 1)), fmt(tb),
                               fmt(n_fb), fmt(round(nivel_izq, 2)), fmt(round(nivel_der, 2))]}
    geo = dict(mover={"tapa": (0.0, 0.0, 1.0)}, pliegue=pliegue, alto_plegado=alto_plegado, z_cierre=zc)
    valores = {"ext_ancho": X, "ext_prof": Y, "ext_alto": zc + tp["alto"], "alto_plegado": alto_plegado + tp["alto"]}
    return ar.resultado("plegable", info_extra, (X, Y, zc, tp["alto"]), (W, D, Hc, float(P["int_alto_tapa"])),
                        mundo, valores, geo, None, det + "; más los de las esquinas", n_esq=8)


# ---------------------------------------------------------------------------
# Tapas slam (tapas y puertas planas en un marco de perfil slam)
# ---------------------------------------------------------------------------

CARAS_SLAM = {"arriba": ("techo",), "frente": ("frente",), "frente_trasera": ("frente", "trasera"),
              "arriba_frente": ("frente", "techo")}
NOMBRE_CARA = {"techo": "arriba", "frente": "adelante", "trasera": "atrás"}


def alto_total(P: Dict[str, Any]) -> float:
    """Cuerpo + tapa (+ segunda tapa): lo que la ventana muestra como alto interior."""
    tapa = float(P.get("int_alto_tapa", 0) or 0)
    total = float(P["int_alto_cuerpo"]) + tapa
    if int(P.get("tapas", 1) or 1) == 2:
        t2 = float(P.get("int_alto_tapa2", -1))
        total += tapa if t2 < 0 else t2
    return total


def _slam(P: Dict[str, Any], cat: CatalogoTaller) -> ResultadoTaller:
    ar = _Armado(P, cat)
    E, t = ar.E, ar.E.t
    g = P.get
    frontal = g("orientacion") == "frontal"
    W = float(P["int_ancho"])
    if frontal:     # como un rack parado: int_prof es el alto y el fondo es cuerpo + tapas
        Hi, D = float(P["int_prof"]), alto_total(P)
    else:
        D, Hi = float(P["int_prof"]), alto_total(P)
    X, Y, Z = W + 2 * t, D + 2 * t, Hi + 2 * t
    caras_txt = str(g("slam_caras", "arriba") or "arriba")
    if caras_txt not in CARAS_SLAM:
        ar.A.append(s("slam_caras «", caras_txt, "» no existe (", ", ".join(CARAS_SLAM), "): va arriba."))
        caras_txt = "arriba"
    abiertas = CARAS_SLAM[caras_txt]
    hojas = 2 if int(g("slam_hojas", 1) or 1) >= 2 else 1
    c = float(g("slam_borde", 20) or 20)          # ancho del marco slam a la vista
    ala = float(g("slam_ala", 25) or 25)           # ala del perfil sobre la pared de al lado
    gap = 3.0                                      # luz entre la tapa y el marco, y entre dos hojas
    if c < t + 5:
        ar.A.append(s("El marco slam de ", c, " mm es angosto para tapar el canto de la placa de ", t,
                      " mm: con menos de ", t + 5, " mm la tapa no tiene dónde apoyar."))
    modo = "lidmaker" if g("tapa_plana", "slam") == "lidmaker" else "slam"
    if modo == "lidmaker" and abiertas != ("techo",):
        ar.A.append("La tapa lidmaker va arriba, suelta y con cierres: en las otras caras queda como tapa slam.")
    basemaker = bool(g("basemaker", False))
    ya = t if "frente" in abiertas else 0.0
    yb = Y - t if "trasera" in abiertas else Y
    # ---- paredes del cuerpo (las caras abiertas no llevan pared: va la tapa plana) ----
    if basemaker:   # el piso va encastrado en un marco de perfil basemaker, a ras de los cantos
        ar.panel("piso", "Piso (en el marco basemaker)", "cuerpo", X - 2 * c, yb - ya - 2 * c, (c, ya + c, 0.0),
                 (1, 0, 0), (0, 1, 0), (0, 0, 1))
    else:
        ar.panel("piso", "Piso", "cuerpo", X, yb - ya, (0.0, ya, 0.0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    if "techo" not in abiertas:
        ar.panel("techo_fijo", "Techo", "cuerpo", X, yb - ya, (0.0, ya, Z), (1, 0, 0), (0, 1, 0), (0, 0, -1))
    if "frente" not in abiertas:
        ar.panel("cuerpo_frente", "Frente", "cuerpo", X, Z - 2 * t, (0.0, 0.0, t), (1, 0, 0), (0, 0, 1), (0, 1, 0))
    if "trasera" not in abiertas:
        ar.panel("cuerpo_trasera", "Trasera", "cuerpo", X, Z - 2 * t, (X, Y, t), (-1, 0, 0), (0, 0, 1), (0, -1, 0))
    ar.panel("cuerpo_izq", "Lateral izq.", "cuerpo", Y - 2 * t, Z - 2 * t, (0.0, Y - t, t), (0, -1, 0), (0, 0, 1),
             (1, 0, 0))
    ar.panel("cuerpo_der", "Lateral der.", "cuerpo", Y - 2 * t, Z - 2 * t, (X, t, t), (0, 1, 0), (0, 0, 1), (-1, 0, 0))
    # ---- marco de cada cara abierta: (o, u, v, n, A, B) de la cara exterior ----
    marcos = {"frente": ((0.0, 0.0, 0.0), (1, 0, 0), (0, 0, 1), (0, 1, 0), X, Z),
              "trasera": ((X, Y, 0.0), (-1, 0, 0), (0, 0, 1), (0, -1, 0), X, Z),
              "techo": ((0.0, 0.0, Z), (1, 0, 0), (0, 1, 0), (0, 0, -1), X, Y)}
    nom_perfil = cat.nombre(g("slam_perfil_ref")) if cat.existe(g("slam_perfil_ref", "")) else "Perfil slam"
    ref_perfil = g("slam_perfil_ref", "")
    ref_lm = g("lidmaker_ref", "")
    nom_lm = cat.nombre(ref_lm) if cat.existe(ref_lm) else "Perfil lidmaker"
    ref_bm = g("basemaker_ref", "")
    nom_bm = cat.nombre(ref_bm) if cat.existe(ref_bm) else "Perfil basemaker"
    ref_cie = g("ref_slam", "")
    cie = dict(cat.fila(ref_cie)["datos"]) if cat.existe(ref_cie) else {}
    cw, ch = (cie.get("corte") or [60, 40])
    cr = float(cie.get("radio", 3) or 0)
    ref_bis = g("ref_bisagra", "")
    piano_ref = ref_bis if cat.dato(ref_bis, "largo", 0) > 0 else "08-2605"
    lado = "der" if g("puerta_lado", "izq") == "der" else "izq"
    n_cie_tot, n_pasadores, piano_largos = 0, 0, []
    mueve_de = {}
    for i, cara in enumerate(abiertas):
        o, u, v, n, A, B = marcos[cara]
        fuera = _neg(n)
        Q = lambda a, b, h=0.0, o=o, u=u, v=v, n=n: _sum(o, _mul(u, a), _mul(v, b), _mul(n, h))
        grupo = "tapa" if i == 0 else "tapa2"
        mueve_de[cara] = grupo
        # el marco: cuatro tramos a inglete en el plano de la cara y el ala sobre la pared de al lado
        for a0, b0, aw, bh in ((0, 0, A, c), (0, B - c, A, c), (0, c, c, B - 2 * c), (A - c, c, c, B - 2 * c)):
            ar.bloque(Q(a0, b0), u, v, n, aw, bh, t, "profile", "Perfil slam", "cuerpo", F_AROS)
        for (a0, b0, du, dv, L, normal) in ((0, 0, 1, 0, A, _neg(v)), (0, B, 1, 0, A, v), (0, 0, 0, 1, B, _neg(u)),
                                            (A, 0, 0, 1, B, u)):
            eje = u if du else v
            ar.bloque(_sum(Q(a0, b0, 0), _mul(normal, 0.0)), eje, n, normal, L, ala, 1.5, "profile", "Perfil slam",
                      "cuerpo", F_AROS)
        nom_c = NOMBRE_CARA[cara]
        lm = modo == "lidmaker" and cara == "techo"
        np_, rp_ = (nom_lm, ref_lm) if lm else (nom_perfil, ref_perfil)
        ar.tramo(np_, s("Marco de la tapa de ", nom_c, ", lados largos (punta larga)"), max(A, B), 2, "45/45", rp_)
        ar.tramo(np_, s("Marco de la tapa de ", nom_c, ", lados cortos (punta larga)"), min(A, B), 2, "45/45", rp_)
        # la tapa (una o dos hojas), a ras del marco
        ancho_l = A - 2 * c - 2 * gap
        alto_l = B - 2 * c - 2 * gap
        n_h = hojas if (i == 0 or cara != "techo") else 1
        w_h = (ancho_l - gap * (n_h - 1)) / n_h
        # bisagra: en la trasera de la tapa de arriba; en las puertas, del lado elegido (dos hojas: en los dos)
        if lm:
            n_h, w_h = 1, ancho_l
        for k in range(n_h):
            a0 = c + gap + k * (w_h + gap)
            pid = s("tapa_", cara, "" if n_h == 1 else s("_", k + 1))
            nombre = s("Tapa de ", nom_c, "" if n_h == 1 else s(" (hoja ", k + 1, ")"))
            ar.panel(pid, nombre, "tapa", w_h, alto_l, Q(a0, c + gap), u, v, n, mueve=grupo, paso=F_TAPA)
            if lm:      # tapa lidmaker: suelta, la traban cierres mariposa en las paredes (más abajo)
                continue
            if cara == "techo":
                bis_borde, cie_borde = "b1", "b0"        # bisagra atrás, cierres adelante
            elif n_h == 2:
                bis_borde, cie_borde = ("a0", "a1") if k == 0 else ("a1", "a0")
            else:
                izq_es_a0 = cara == "frente"
                bis_borde = "a0" if (lado == "izq") == izq_es_a0 else "a1"
                cie_borde = "a1" if bis_borde == "a0" else "a0"
            # bisagra de piano a lo largo del borde
            if bis_borde in ("a0", "a1"):
                L = alto_l - 20
                ab = a0 if bis_borde == "a0" else a0 + w_h
                ar.bloque(Q(ab - 6, c + gap + 10, 0), v, u, fuera, L, 12, 3, "cierre", "Bisagra de piano", grupo,
                          F_CIERRES)
            else:
                L = w_h - 20
                ar.bloque(Q(a0 + 10, B - c - gap - 6, 0), u, v, fuera, L, 12, 3, "cierre", "Bisagra de piano", grupo,
                          F_CIERRES)
            piano_largos.append(L)
            # cierres slam embutidos en la tapa, junto al borde que cierra
            if n_h == 2 and k == 0:
                # la primera hoja se traba con dos pasadores embutidos (arriba y abajo) y lleva el perfil
                # de tope donde cierra la segunda
                n_pasadores += 2
                ar.tramo(nom_perfil, s("Tope entre las hojas de ", nom_c, " (en el canto de la hoja 1)"), alto_l, 1,
                         "recto", ref_perfil)
                ar.bloque(Q(a0 + w_h - 2, c + gap, 0), v, u, fuera, alto_l, gap + 4, 3, "profile", "Perfil slam",
                          grupo, F_AROS)
                continue
            largo_borde = alto_l if cie_borde in ("a0", "a1") else w_h
            n_c = n_cierres(largo_borde)
            for q in _pos_n(largo_borde, n_c, min(100.0, largo_borde / 4)):
                if cie_borde in ("a0", "a1"):     # borde vertical de la hoja: el cierre va parado
                    w_c, h_c = ch, cw
                    px, py = ((ch / 2 + 12) if cie_borde == "a0" else w_h - ch / 2 - 12), q
                else:
                    px, py = q, ch / 2 + 12
                    w_c, h_c = cw, ch
                ar.calados.append(Calado(pid, "cierre", px, py, w_c, h_c, cr))
                ar.marcas.append(Marca(pid, "cierre", px, py, w_c, h_c, "slam"))
                ar.bloque(Q(a0 + px - w_c / 2, c + gap + py - h_c / 2, -1.5), u, v, fuera, w_c, h_c, 1.5, "cierre",
                          "Cierre slam", grupo, F_CIERRES)
                n_cie_tot += 1
    if modo == "lidmaker" and "techo" in abiertas:
        # cierres mariposa en las paredes, bajo el marco lidmaker; el gancho va en el marco de la tapa
        margen = g("cierre_margen", 100)
        b_ = E.m_alto - E.m_sup
        lat = g("cierres_laterales", "auto")
        lat_si = True if lat == "si" else (False if lat == "no" else Y > 450)
        paredes = [("cuerpo_frente", X, (0.0, 0.0, Z), (1, 0, 0), (0, 1, 0), lambda q: q),
                   ("cuerpo_trasera", X, (X, Y, Z), (-1, 0, 0), (0, -1, 0), lambda q: q)]
        if lat_si:
            paredes += [("cuerpo_izq", Y, (0.0, Y, Z), (0, -1, 0), (1, 0, 0), lambda q: q - t),
                        ("cuerpo_der", Y, (X, 0.0, Z), (0, 1, 0), (-1, 0, 0), lambda q: q - t)]
        for pid, L, o_, u_, n_, fx in paredes:
            for q in _pos_n(L, n_cierres(L), margen):
                ar.marcas.append(Marca(pid, "cierre", fx(q), Z - 2 * t - c - b_, 0, 0, "c1"))
                ar.cierre(_sum(o_, (0.0, 0.0, -c)), u_, (0, 0, 1), n_, q)
                ar.gancho(_sum(o_, (0.0, 0.0, -c)), u_, (0, 0, 1), n_, q)
        ar.calados_cierre()
    if basemaker:
        o, u, v, n, A, B = (0.0, ya, 0.0), (1, 0, 0), (0, 1, 0), (0, 0, 1), X, yb - ya
        Qb = lambda a, b, h=0.0: _sum(o, _mul(u, a), _mul(v, b), _mul(n, h))
        for a0, b0, aw, bh in ((0, 0, A, c), (0, B - c, A, c), (0, c, c, B - 2 * c), (A - c, c, c, B - 2 * c)):
            ar.bloque(Qb(a0, b0), u, v, n, aw, bh, t, "profile", "Perfil basemaker", "cuerpo", F_AROS)
        ar.tramo(nom_bm, "Marco del piso, lados largos (punta larga)", max(A, B), 2, "45/45", ref_bm)
        ar.tramo(nom_bm, "Marco del piso, lados cortos (punta larga)", min(A, B), 2, "45/45", ref_bm)
    # ---- ángulos en las aristas que no son de una cara abierta, y esquineros ----
    ed = E.ed
    A_ = E.perfil_arista
    ab = set(abiertas) | ({"piso"} if basemaker else set())
    n_x = n_y = n_z = 0
    for y0, sy, cy in ((0.0, -1, "frente"), (Y, 1, "trasera")):
        for z0, sz, cz in ((0.0, -1, "piso"), (Z, 1, "techo")):
            if cy not in ab and cz not in ab:
                ar.arista((ed, y0, z0), (0, sy, 0), (0, 0, sz), (1, 0, 0), X - 2 * ed)
                n_x += 1
    for x0, sx in ((0.0, -1), (X, 1)):
        for z0, sz, cz in ((0.0, -1, "piso"), (Z, 1, "techo")):
            if cz not in ab:
                ar.arista((x0, ed, z0), (sx, 0, 0), (0, 0, sz), (0, 1, 0), Y - 2 * ed)
                n_y += 1
        for y0, sy, cy in ((0.0, -1, "frente"), (Y, 1, "trasera")):
            if cy not in ab:
                ar.arista((x0, y0, ed), (sx, 0, 0), (0, sy, 0), (0, 0, 1), Z - 2 * ed)
                n_z += 1
            for z0, sz in ((0.0, -1), (Z, 1)):
                ar.esquinero((x0, y0, z0), (sx, 0, 0), (0, sy, 0), (0, 0, sz))
    ar.tramo(A_, "Aristas a lo ancho", X - 2 * ed, n_x, "recto", E.ref_arista)
    ar.tramo(A_, "Aristas a lo profundo", Y - 2 * ed, n_y, "recto", E.ref_arista)
    ar.tramo(A_, "Aristas a lo alto", Z - 2 * ed, n_z, "recto", E.ref_arista)
    if len(abiertas) == 2 and "techo" in abiertas:
        ar.A.append("En la arista entre la tapa de arriba y la de adelante los dos marcos se tocan: ahí va un perfil "
                    "slam doble (o los dos tramos a inglete, uno sobre otro). Presentalos antes de remachar.")
    # ---- herrajes ----
    nom_p = cat.nombre(piano_ref) if cat.existe(piano_ref) else "Bisagra de piano"
    if piano_largos:
        ar.H.append([nom_p, len(piano_largos), "cortar a " + ", ".join(s(round(L, 1)) for L in piano_largos)
                     + " mm, una por hoja", piano_ref])
    ar.remaches += sum(2 * (math.floor(L / 50) + 1) for L in piano_largos)
    if n_cie_tot:
        ar.H.append([cat.nombre(ref_cie) if cat.existe(ref_cie) else "Cierre slam embutido", n_cie_tot,
                     s("embutido en la tapa: calado ", cw, "x", ch, "; el contragancho va en el marco"), ref_cie])
        ar.remaches += n_cie_tot * int(cie.get("remaches", 4) or 4)
    if n_pasadores:
        ar.H.append(["Pasador embutido (falleba) para puerta doble", n_pasadores,
                     "en la hoja 1, arriba y abajo: la traba al marco", ""])
        ar.remaches += n_pasadores * 4
    topes = int(g("topes", 0) or 0)
    if topes:
        ref_t = g("ref_tope", "")
        ar.H.append([cat.nombre(ref_t) if cat.existe(ref_t) else "Tope de tapa", topes, "sostiene la tapa abierta",
                     ref_t])
        ar.remaches += cat.dato(ref_t, "remaches", 8) * topes
    if int(g("bisagras", 0) or 0) > 0 and cat.dato(ref_bis, "largo", 0) <= 0:
        ar.A.append("Las tapas slam van con bisagra de piano a lo largo de la hoja: las bisagras sueltas no se usan.")
    # ---- manijas en los laterales, ruedas y pies ----
    hm = Z - 2 * t
    centros = {pid: ((Y - 2 * t) / 2, hm - g("manija_centro_desde_arriba", 80)) for pid in ("cuerpo_izq", "cuerpo_der")}
    ar.manijas_en(["cuerpo_izq", "cuerpo_der"], centros)
    margen = E.pata + g("rueda_margen", 10)
    if basemaker:
        ar.ruedas_abajo("piso", X - 2 * c, yb - ya - 2 * c, (c, ya + c, 0.0), (1, 0, 0), (0, 1, 0), max(margen - c, 5))
        ar.pies_abajo("piso", X - 2 * c, yb - ya - 2 * c, (c, ya + c, 0.0), (1, 0, 0), (0, 1, 0), max(margen - c, 5))
    else:
        ar.ruedas_abajo("piso", X, yb - ya, (0.0, ya, 0.0), (1, 0, 0), (0, 1, 0), margen)
        ar.pies_abajo("piso", X, yb - ya, (0.0, ya, 0.0), (1, 0, 0), (0, 1, 0), margen)
    # ---- interior ----
    from . import interiores as _int
    interior = None
    Pi = dict(P)
    if frontal and int(g("rack_u", 0) or 0) <= 0 and not g("rack_equipos") and g("slam_rack", False):
        Pi["rack_u"] = int(math.floor(Hi / _int.U_MM + 1e-6))
    if _int.hay_interiores(Pi):
        if frontal:
            ctx = dict(horizontal=False, frontal=True, dos_tapas="trasera" in abiertas, ext_ancho=X, ext_prof=Z,
                       ext_alto=Y, pared=t, espuma=0.0, z_cierre=Y, z_cierre2=0.0, bandejas=[], band_esp=lambda b: t)
        else:
            ctx = dict(horizontal=False, frontal=False, dos_tapas=False, ext_ancho=X, ext_prof=Y, ext_alto=Z, pared=t,
                       espuma=0.0, z_cierre=Z - t, z_cierre2=0.0, bandejas=[], band_esp=lambda b: t)
        interior = _int.calcular(Pi, ctx, cat)
    n_esq = 8
    dir_ = {"techo": (0.0, 0.0, 1.0), "frente": (0.0, -1.0, 0.0), "trasera": (0.0, 1.0, 0.0)}
    geo = dict(mover={"tapa": dir_[abiertas[0]]}, slam=dict(caras=list(abiertas), hojas=hojas),
               z_cierre=(Y if frontal else Z), z_cierre2=0.0)
    if frontal:
        valores = {"ext_ancho": X, "ext_prof": Z, "ext_alto": Y}
        ext, inte = (X, Z, Y, 0), (W, Hi, D, 0)
    else:
        valores = {"ext_ancho": X, "ext_prof": Y, "ext_alto": Z}
        ext, inte = (X, Y, Z, 0), (W, D, Hi, 0)
    info_extra = {"slam": [caras_txt, fmt(hojas), fmt(n_cie_tot), fmt(c), modo, fmt(1 if basemaker else 0)]}
    det = ", ".join(NOMBRE_CARA[cara] for cara in abiertas)
    res = ar.resultado("slam", info_extra, ext, inte, (X, Y, Z), valores, geo, interior,
                       s("tapas ", det), n_esq=n_esq)
    return res


# ---------------------------------------------------------------------------
# Base de ruedas suelta (castor board)
# ---------------------------------------------------------------------------

def _tabla(P: Dict[str, Any], cat: CatalogoTaller) -> ResultadoTaller:
    """Una tabla gruesa con cuatro ruedas abajo y un borde de ángulo alrededor, con el ala hacia arriba: los
    cases (o una pila) apoyan adentro del borde y viajan juntos. int_ancho x int_prof es la planta de lo que
    apoya; la tabla lleva 2 mm de luz por lado."""
    ar = _Armado(P, cat)
    E = ar.E
    g = P.get
    W, D = float(P["int_ancho"]), float(P["int_prof"])
    tb = float(g("tabla_esp", 18) or 18)
    borde = float(g("tabla_borde", 40) or 0)
    luz = 2.0
    X, Y = W + 2 * luz, D + 2 * luz
    mat = g("tabla_material") or s("Placa ", tb, " mm")
    ar.panel("tabla", "Tabla (con las ruedas)", "cuerpo", X, Y, (0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
             esp=tb)
    ar.panelmat.append(["tabla", mat, tb])
    # el borde: ángulo con un ala sobre el canto de la tabla y la otra hacia arriba (sobresale `borde`)
    alto_ala = tb + borde
    e_ang = 1.5
    for (o, u, n, L) in (((0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), X), ((X, Y, 0.0), (-1, 0, 0), (0, -1, 0), X),
                         ((0.0, Y, 0.0), (0, -1, 0), (1, 0, 0), Y), ((X, 0.0, 0.0), (0, 1, 0), (-1, 0, 0), Y)):
        ar.bloque(_sum(o, _mul(n, -e_ang)), u, (0, 0, 1), n, L, alto_ala, e_ang, "profile", "Borde de ángulo",
                  "cuerpo", F_ARISTAS)
    A_ = E.perfil_arista
    ar.tramo(A_, "Borde a lo ancho (ala hacia arriba)", X + 2 * e_ang, 2, "45/45", E.ref_arista)
    ar.tramo(A_, "Borde a lo profundo (ala hacia arriba)", Y + 2 * e_ang, 2, "45/45", E.ref_arista)
    if borde < 20:
        ar.A.append("Con menos de 20 mm de borde los cases se pueden correr de la tabla en una frenada.")
    if E.ala > alto_ala:
        ar.A.append(s("El ala del ángulo (", E.ala, " mm) es más alta que la tabla más el borde: subí tabla_borde."))
    if int(g("ruedas", 0) or 0) != 4:
        ar.A.append("La base de ruedas sin ruedas es sólo una tabla: poné ruedas = 4.")
    ar.ruedas_abajo("tabla", X, Y, (0.0, 0.0, 0.0), (1, 0, 0), (0, 1, 0), float(g("rueda_margen", 10) or 0))
    if g("manijas"):
        ar.A.append("La base de ruedas no lleva manijas: se empuja del case que va arriba.")
    Z = alto_ala
    mundo = (X + 2 * e_ang, Y + 2 * e_ang, Z)
    valores = {"ext_ancho": X + 2 * e_ang, "ext_prof": Y + 2 * e_ang, "ext_alto": Z}
    info_extra = {"tabla": [fmt(tb), fmt(borde), mat]}
    return ar.resultado("tabla", info_extra, (X, Y, Z, 0), (W, D, borde, 0), mundo, valores, dict(mover={}), None,
                        "", n_esq=0)


def calcular(P: Dict[str, Any], cat: CatalogoTaller) -> ResultadoTaller:
    forma = P.get("forma")
    if forma == "inclinado":
        res = _rack_inclinado(P, cat)
    elif forma == "funda":
        res = _funda(P, cat)
    elif forma == "slam":
        res = _slam(P, cat)
    elif forma == "tabla":
        res = _tabla(P, cat)
    else:
        res = _plegable(P, cat)
    from . import peso as _peso
    res.valores["peso"] = _peso.calcular(res, P, cat)
    return res


# ---------------------------------------------------------------------------
# Instructivo y hojas extra de los planos
# ---------------------------------------------------------------------------

def _f(v: float) -> str:
    return f"{float(v):.1f}".rstrip("0").rstrip(".").replace(".", ",")


def pasos_instructivo(d: Dict[str, Any], piezas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pasos de montaje (formato de instructivo.armar_pasos) para el rack inclinado, la funda y el plegable."""
    info = d["info"]
    forma = info["forma"][0]
    num = {pid: f"P{pz['num']}" for pz in piezas for pid in pz["ids"]}
    nom = lambda pid: f"{d['paneles'][pid]['nombre'].lower()} ({num.get(pid, '?')})" if pid in d["paneles"] else pid
    mont = info.get("montaje", ["100", "4"])
    mecha = float(mont[1]) + 0.1

    def per(desc: str) -> List[Dict[str, Any]]:
        return [p for p in d["perfiles"] if p["desc"].startswith(desc)]

    def tramos(lista: List[Dict[str, Any]]) -> str:
        return " y ".join(f"{p['cant']} × {_f(p['largo'])} mm" for p in lista)

    def her(prefijo: str) -> Optional[Dict[str, Any]]:
        return next((h for h in d["herrajes"] if h["nombre"].lower().startswith(prefijo)), None)

    camara = "0,0,0,62,0,32,0"
    pasos: List[Dict[str, Any]] = [dict(titulo="Verificar piezas y herramientas", vista=None, texto=[
        "Separá los paneles por número (P1, P2...) según la lista de esta hoja y marcá en cada uno la cara exterior.",
        "Controlá con cinta que cada panel mida lo indicado: un error de 1 mm se nota en todas las aristas.",
        f"Herramientas: sierra con disco para aluminio, remachadora, mecha de {_f(mecha)} mm, escuadra, falsa escuadra "
        "(para los ángulos que no son de 90°), cinta métrica y prensas.",
        "Cortá todos los perfiles antes de empezar, siguiendo la hoja de barras del PDF de planos."])]
    if forma == "slam":
        return pasos + _pasos_slam(d, info, nom, per, tramos, her, camara)
    if forma == "tabla":
        tb, borde, mat = info["tabla"]
        return pasos + [
            dict(titulo="Cortar la tabla", vista="f_cuerpo", camara=camara, defs={"paso": F_CUERPO},
                 texto=[f"Tabla: {nom('tabla')}, de {mat} ({_f(float(tb))} mm). Lijá los cantos y marcá la cara de "
                        "arriba."]),
            dict(titulo="Borde de ángulo", vista="f_esq", camara=camara, defs={"paso": F_ARISTAS},
                 texto=[f"Ángulo alrededor, a inglete 45° ({tramos(per('Borde'))}), con un ala sobre el canto de la "
                        f"tabla y la otra hacia arriba: sobresale {_f(float(borde))} mm y sujeta los cases.",
                        "Remachá el ala del canto a la tabla (o atornillala si la tabla es gruesa)."]),
            dict(titulo="Ruedas", vista="f_ruedas", camara="0,0,0,110,0,32,0", defs={"paso": F_RUEDAS},
                 texto=["Ruedas abajo, en las cuatro esquinas: bulones pasantes con arandela y tuerca autofrenante, "
                        "las ruedas con freno del mismo lado."]),
            dict(titulo="Base terminada", vista="final", texto=[
                "Apoyá el case arriba y probá que entre en el borde sin forzar y que no se mueva al empujar."])]
    if forma == "inclinado":
        g = info["inclinado"][0]
        pasos.append(dict(titulo="Armar el cuerpo en cuña", vista="f_cuerpo", camara=camara, defs={"paso": F_CUERPO},
                          texto=[f"El plano de cierre baja hacia el frente con una pendiente de {_f(float(g))}°.",
                                 f"Cortá el canto de arriba de {nom('cuerpo_frente')} y de {nom('cuerpo_trasera')} a "
                                 f"{_f(float(g))}° (sierra inclinada): en el frente la cara de afuera queda más baja; en "
                                 "la trasera, la de adentro. La medida del panel es la de la cara más alta.",
                                 f"Los laterales {nom('cuerpo_izq')} y {nom('cuerpo_der')} son trapecios: cortalos "
                                 "con su DXF o marcando los dos altos de los cantos.",
                                 f"Presentá {nom('piso')} entre las cuatro paredes, frente y trasera enteros y los "
                                 "laterales entre ellos. Controlá las diagonales del piso y que el canto inclinado de "
                                 "los laterales quede a ras con el bisel del frente y de la trasera."]
                          + ([f"Rack de adelante: calá en {nom('cuerpo_frente')} la boca de {info['inclinado'][5]} U "
                              "con su DXF y atornillá los dos rieles detrás del frente, a los costados de la boca, "
                              "antes de cerrar la caja."] if len(info["inclinado"]) > 5 and info["inclinado"][5] != "0"
                             else [])))
        pasos.append(dict(titulo="Colocar el aro macho sobre la pendiente", vista="f_aro", camara=camara,
                          defs={"paso": F_AROS},
                          texto=[f"El aro es un rectángulo en el plano inclinado: perfil macho a inglete 45° "
                                 f"({tramos(per('Frente y trasera') + per('Lados de la pendiente'))}, medidos en la "
                                 "punta larga; los primeros son los del macho).",
                                 "Armalo plano sobre la mesa, controlá las diagonales y calzalo sobre los cantos del "
                                 "cuerpo. Remachá cada 100 mm por la cara de afuera."]))
        pasos.append(dict(titulo="Aristas y esquineros del cuerpo", vista="f_esq", camara=camara, defs={"paso": F_ESQ},
                          texto=[f"Aristas del piso: {tramos(per('Aristas a lo ancho (piso)') + per('Aristas a lo profundo (piso)'))}.",
                                 f"Verticales: {tramos(per('Verticales del frente'))} adelante y "
                                 f"{tramos(per('Verticales de la trasera'))} atrás, con la punta de arriba cortada a "
                                 f"{_f(float(g))}° para que apoye bajo el aro.",
                                 "Esquineros en las cuatro puntas de abajo. Remachá las dos alas de cada ángulo."]))
    elif forma == "funda":
        pasos.append(dict(titulo="Armar el tubo", vista="f_cuerpo", camara=camara, defs={"paso": F_CUERPO},
                          texto=[f"Piso {nom('piso')} y techo {nom('techo')} van enteros; los laterales "
                                 f"{nom('cuerpo_izq')} entre ellos.",
                                 "Prensá el tubo en escuadra: medí las diagonales de las dos bocas, tienen que dar "
                                 "iguales (± 1 mm). Si los rieles no quedan paralelos, el equipo no entra."]))
        pasos.append(dict(titulo="Aristas, bordes de las bocas y esquineros", vista="f_esq", camara=camara,
                          defs={"paso": F_ESQ},
                          texto=[f"Aristas a lo profundo: {tramos(per('Aristas a lo profundo'))}.",
                                 f"Bordes de las bocas, en ángulo que tapa el canto de la placa: "
                                 f"{tramos(per('Borde de las bocas'))}.",
                                 "Esquineros en las ocho puntas. Remachá las dos alas de cada ángulo cada 100 mm."]))
    else:
        pl = info["plegable"]
        pasos.append(dict(titulo="Base y suplementos", vista="f_cuerpo", camara=camara, defs={"paso": F_CUERPO},
                          texto=[f"La base {nom('base')} es de {_f(float(pl[2]))} mm: las ruedas se atornillan en ella.",
                                 "Atornillá los suplementos (tiras de placa, ver la lista de piezas) parados en el borde "
                                 "de la base, bajo cada pared que no apoya directo: así cada pared, al plegarse, queda "
                                 "encima de la anterior.",
                                 "Las paredes se apoyan en la base (o en su suplemento) sin pegar ni atornillar: sólo "
                                 "las une la bisagra de piano."]))
        b = her("bisagra de piano")
        pasos.append(dict(titulo="Bisagras de piano y paredes", vista="f_aro", camara=camara, defs={"paso": F_AROS},
                          texto=[(f"{b['nota'][:1].upper()}{b['nota'][1:]}." if b else ""),
                                 f"Orden de plegado: {nom('cuerpo_frente')}, {nom('cuerpo_trasera')}, "
                                 f"{nom('cuerpo_izq')} y {nom('cuerpo_der')}. Antes de remachar nada, probá que cada "
                                 "pared baje plana sobre la anterior.",
                                 "El aro macho va partido: cada pared lleva su tramo, con corte recto. Los laterales "
                                 "llevan el tramo largo que cubre las esquinas."]))
        pasos.append(dict(titulo="Ángulos de las esquinas y cierres de esquina", vista="f_esq", camara=camara,
                          defs={"paso": F_CIERRES},
                          texto=[f"Los ángulos de las esquinas verticales "
                                 f"({tramos(per('Esquinas verticales'))}) se remachan sólo al lateral: el ala que "
                                 "apoya en el frente queda suelta, si no la pared no se pliega.",
                                 "Los cierres de las esquinas van acostados: el cuerpo del cierre en el frente (o la "
                                 "trasera) y el gancho en el ala del ángulo del lateral.",
                                 f"Plegado (paredes adentro y la tapa encima) mide {_f(float(pl[0]))} mm de alto."]))
    if forma != "funda":
        pasos.append(dict(titulo="Armar la tapa", vista="f_tapa", camara=camara, defs={"paso": F_TAPA},
                          texto=["La tapa se arma como la de un case común, sobre el aro hembra a inglete "
                                 f"({tramos([p for p in d['perfiles'] if p['perfil'] == d['perfiles'][-1]['perfil'] and p['corte'] == '45/45'])}).",
                                 f"Techo {nom('techo')} entre las cuatro paredes de la tapa; aristas, verticales y "
                                 "esquineros como en el cuerpo. Presentala cerrada sobre el cuerpo antes de remachar."]))
        c = her("cierre")
        pasos.append(dict(titulo="Cierres" + (" y bisagras" if her("bisagra") and forma != "plegable" else ""),
                          vista="f_cierres", camara=camara, defs={"paso": F_CIERRES},
                          texto=[f"Con la tapa cerrada, marcá cada cierre en las dos piezas a la vez ({c['nota']})."
                                 if c else "Marcá los cierres con la tapa cerrada.",
                                 "Remachá primero la base del cierre en el cuerpo y después el gancho en la tapa, con "
                                 "el cierre trabado: así queda justo."]))
    pasos.append(dict(titulo="Manijas" + (", ruedas y pies" if info.get("ruedas", ["0"])[0] == "4" or her("pie") else ""),
                      vista="f_ruedas", camara="0,0,0,110,0,32,0", defs={"paso": F_RUEDAS},
                      texto=["Las manijas embutidas entran por la cara de afuera; remachá el reborde."]
                      + (["Ruedas con freno del lado del frente. Bulones con arandela y tuerca autofrenante."]
                         if info.get("ruedas", ["0"])[0] == "4" else [])))
    pasos.append(dict(titulo="Case terminado", vista="final", texto=[
        "Revisá que todos los remaches estén firmes y que la tapa cierre sin forzar." if forma != "funda" else
        "Revisá que todos los remaches estén firmes y que los rieles queden paralelos.",
        *(["Para plegarlo: abrí los cierres de las esquinas, bajá el frente, la trasera y los laterales en ese orden "
           "y apoyá la tapa encima."] if forma == "plegable" else [])]))
    for p in pasos:
        p["texto"] = [t for t in p["texto"] if t]
    return pasos


def _pasos_slam(d, info, nom, per, tramos, her, camara) -> List[Dict[str, Any]]:
    caras = CARAS_SLAM.get(info["slam"][0], ("techo",))
    hojas = int(float(info["slam"][1]))
    paredes = [pid for pid in ("piso", "techo_fijo", "cuerpo_frente", "cuerpo_trasera", "cuerpo_izq", "cuerpo_der")
               if pid in d["paneles"]]
    tapas = [pid for pid in d["paneles"] if pid.startswith("tapa_")]
    b, c, pa = her("bisagra de piano"), her("cierre slam"), her("pasador")
    lm = len(info["slam"]) > 4 and info["slam"][4] == "lidmaker" and "techo" in caras
    bm = len(info["slam"]) > 5 and info["slam"][5] == "1"
    mar = her("cierre mariposa")
    perfil = "perfil lidmaker" if lm else "perfil slam"
    pasos = [
        dict(titulo="Armar la caja", vista="f_cuerpo", camara=camara, defs={"paso": F_CUERPO},
             texto=["Es una caja cerrada salvo en " + " y ".join(NOMBRE_CARA[k] for k in caras) + ": ahí va la tapa plana.",
                    "Paredes: " + ", ".join(nom(p) for p in paredes) + ". Prensá la caja en escuadra y medí las "
                    "diagonales de cada boca abierta: tienen que dar iguales (± 1 mm) o la tapa no asienta."]),
        dict(titulo=("Marcos lidmaker" if lm else "Marcos slam") + (", basemaker" if bm else "")
             + ", aristas y esquineros", vista="f_esq", camara=camara, defs={"paso": F_ESQ},
             texto=[f"Marco de cada boca: {perfil} a inglete 45° ({tramos(per('Marco de la tapa'))}, medidos en la "
                    "punta larga). Armalo sobre la mesa, controlá las diagonales y remachalo sobre los cantos.",
                    (f"Piso: va encastrado en el marco de perfil basemaker ({tramos(per('Marco del piso'))}), a ras "
                     "de los cantos. Armá el marco en escuadra, calzá el piso y remachá las paredes sobre el ala."
                     if bm else ""),
                    f"El resto de las aristas lleva ángulo ({tramos(per('Aristas'))}) y las ocho puntas, esquineros."]),
        dict(titulo="Tapas planas" + ("" if lm and not b else " y bisagras de piano"), vista="f_tapa", camara=camara, defs={"paso": F_TAPA},
             texto=["Tapas: " + ", ".join(nom(p) for p in tapas) + ". Apoyan a ras dentro del marco, con 3 mm de luz "
                    "alrededor (y entre las hojas).",
                    (f"{b['nota'][:1].upper()}{b['nota'][1:]}: remachala primero en el marco y después en la tapa, con "
                     "la tapa calzada en su lugar." if b else "")]
             + ([f"Puerta doble: la hoja 1 lleva el tope donde cierra la hoja 2 ({tramos(per('Tope entre las hojas'))}) "
                 f"y {pa['cant'] if pa else 2} pasadores embutidos que la traban arriba y abajo."] if hojas == 2 else [])),
        (dict(titulo="Cierres mariposa", vista="f_cierres", camara=camara, defs={"paso": F_CIERRES},
              texto=[(f"{mar['cant']} cierres mariposa en las paredes, justo bajo el marco lidmaker; el gancho va en "
                      "el marco de la tapa." if mar else ""),
                     "Calá las paredes con su DXF, apoyá la tapa en su lugar y marcá el gancho con el cierre "
                     "tensado. La tapa sale entera: no lleva bisagras."]) if lm and not c else
         dict(titulo="Cierres slam", vista="f_cierres", camara=camara, defs={"paso": F_CIERRES},
             texto=[(f"{c['cant']} " + ("cierre slam embutido" if c["cant"] == 1 else "cierres slam embutidos")
                     + f" en las tapas ({c['nota']})." if c else ""),
                    "Calá la tapa con su DXF, presentá el cierre y, con la tapa cerrada, marcá el contragancho en el "
                    "marco. Probá que trabe solo al bajar la tapa antes de remachar."])),
        dict(titulo="Manijas" + (", ruedas y pies" if info.get("ruedas", ["0"])[0] == "4" or her("pie") else ""),
             vista="f_ruedas", camara="0,0,0,110,0,32,0", defs={"paso": F_RUEDAS},
             texto=["Las manijas embutidas entran por la cara de afuera; remachá el reborde."]
             + (["Ruedas con freno del lado del frente. Bulones con arandela y tuerca autofrenante."]
                if info.get("ruedas", ["0"])[0] == "4" else [])),
        dict(titulo="Case terminado", vista="final", texto=[
            "Revisá que todos los remaches estén firmes y que "
            + ("la tapa asiente pareja en el marco y los cierres la ajusten sin juego." if lm and not c else
               "cada tapa cierre sola al bajarla, sin forzar.")]),
    ]
    for p in pasos:
        p["texto"] = [t for t in p["texto"] if t]
    return pasos


def vistas_planos(res: ResultadoTaller, carpeta: str) -> List[Tuple[str, str, str]]:
    """Hojas extra de planos.pdf: el baúl plegado y el rack inclinado de costado."""
    import os
    from .geometria import Opciones3D, malla_3d
    from .render import renderizar
    forma = res.valores.get("forma")
    out = []
    if forma == "plegable":
        png = os.path.join(carpeta, "plegado.png")
        pl = res.info["plegable"]
        if renderizar(malla_3d(res, Opciones3D(vista_parte="plegado", interior=False)), png, "0,0,0,66,0,30,0",
                      "1600,1200"):
            out.append(("Plegado", png,
                        f"Vacío, las paredes se pliegan hacia adentro sobre la base (frente, trasera y laterales, en ese "
                        f"orden) y la tapa va encima: queda de {_f(float(pl[0]))} mm de alto en lugar de "
                        f"{_f(res.valores['ext_alto'])} mm (sin ruedas)."))
    if forma == "inclinado":
        png = os.path.join(carpeta, "inclinado_costado.png")
        inc = res.info["inclinado"]
        if renderizar(malla_3d(res, Opciones3D(abrir_tapa=0)), png, "0,0,0,90,0,90,0", "1600,1200"):
            out.append(("Rack inclinado de costado", png,
                        f"Pendiente de {_f(float(inc[0]))}°: el plano de cierre mide {_f(float(inc[1]))} mm de largo; "
                        f"el cuerpo tiene {_f(float(inc[2]))} mm de alto adelante y {_f(float(inc[3]))} mm atrás "
                        f"(exteriores, hasta el plano de cierre). Bajo los rieles quedan {_f(float(inc[4]))} mm de fondo "
                        "en el frente, medidos perpendicular a la pendiente."))
    return out
