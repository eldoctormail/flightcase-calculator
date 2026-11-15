"""Exporta el case del taller a STEP (ISO 10303-21, AP214) para abrirlo en Fusion, SolidWorks o FreeCAD.

Se escribe directamente el texto STEP, sin librerías de CAD, para que los instaladores no
carguen con OpenCASCADE. Cada cuerpo de la vista 3D (geometria.malla_3d) sale como un sólido
cerrado de caras planas (MANIFOLD_SOLID_BREP): los paneles con sus calados pasantes, los aros
y ángulos de aluminio, los herrajes simplificados y el interior (equipos, espuma con sus
bolsillos, cajones, rack). Las piezas van en un ensamble, una pieza por nombre ("Frente
cuerpo", "Ángulo de arista"...), con el color de la vista 3D y las medidas en milímetros.
"""

from __future__ import annotations

import datetime as _dt
import math
import os

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .geometria import COLORES, Malla3D, Opciones3D, Solido3D, malla_3d
from .modelo import ResultadoTaller

Vec = Tuple[float, float, float]
Lazo = List[int]            # índices de vértices
Cara = List[Lazo]           # el primer lazo es el borde exterior, los demás son agujeros

TOL = 1e-4                  # mm: vértices más cerca que esto son el mismo


# ---------------------------------------------------------------- álgebra mínima

def _resta(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _punto(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cruz(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _largo(a: Sequence[float]) -> float:
    return math.sqrt(_punto(a, a))


def _unit(a: Sequence[float]) -> Vec:
    l = _largo(a) or 1.0
    return (a[0] / l, a[1] / l, a[2] / l)


def _newell(pts: Sequence[Sequence[float]]) -> Vec:
    """Normal (sin normalizar, de largo = 2·área) de un polígono plano según su sentido de giro."""
    nx = ny = nz = 0.0
    for i, p in enumerate(pts):
        q = pts[(i + 1) % len(pts)]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    return (nx, ny, nz)


# ---------------------------------------------------------------- de la malla a un B-rep

@dataclass
class Cuerpo:
    """Sólido listo para escribir: vértices y caras (lazos de índices) bien orientadas."""
    nombre: str
    color: str
    vertices: List[Vec]
    caras: List[Cara]
    cerrado: bool = True

    def volumen(self) -> float:
        V = self.vertices
        tot = 0.0
        for cara in self.caras:
            for lazo in cara:
                p0 = V[lazo[0]]
                for i in range(1, len(lazo) - 1):
                    tot += _punto(p0, _cruz(V[lazo[i]], V[lazo[i + 1]]))
        return tot / 6.0


class _Vertices:
    """Une vértices repetidos (con tolerancia) dentro de un cuerpo."""

    def __init__(self) -> None:
        self.lista: List[Vec] = []
        self._grilla: Dict[Tuple[int, int, int], List[int]] = {}

    def indice(self, p: Sequence[float]) -> int:
        c = tuple(int(math.floor(x / TOL)) for x in p)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for i in self._grilla.get((c[0] + dx, c[1] + dy, c[2] + dz), ()):
                        q = self.lista[i]
                        if abs(q[0] - p[0]) <= TOL and abs(q[1] - p[1]) <= TOL and abs(q[2] - p[2]) <= TOL:
                            return i
        self.lista.append((float(p[0]), float(p[1]), float(p[2])))
        self._grilla.setdefault(c, []).append(len(self.lista) - 1)  # type: ignore[arg-type]
        return len(self.lista) - 1


def _limpiar(lazo: Lazo) -> Lazo:
    """Saca vértices repetidos seguidos (aristas de largo cero)."""
    out: Lazo = []
    for i in lazo:
        if not out or out[-1] != i:
            out.append(i)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _es_plana(pts: Sequence[Vec]) -> bool:
    n = _newell(pts)
    if _largo(n) < 1e-9:
        return False
    n = _unit(n)
    d0 = _punto(n, pts[0])
    return all(abs(_punto(n, p) - d0) < 1e-3 for p in pts)


def _agujeros_del_panel(V: _Vertices, caras: List[Cara], agujeros: List[List[Vec]],
                        nombre: str, avisos: List[str]) -> None:
    """Perfora una caja (6 caras) con los calados pasantes, que están sobre una de sus caras."""
    pts = V.lista
    validos: List[Tuple[int, int, List[Vec]]] = []
    for ag in agujeros:
        if len(ag) < 3:
            continue
        # la cara de la caja que contiene el calado, y la opuesta
        f_out = next((i for i, c in enumerate(caras)
                      if all(abs(_punto(_unit(_newell([pts[j] for j in c[0]])), _resta(p, pts[c[0][0]]))) < 0.05
                             for p in ag)), None)
        if f_out is None:
            avisos.append(f"{nombre}: un calado no está sobre la cara del panel; no se perforó en el STEP.")
            continue
        n_out = _unit(_newell([pts[j] for j in caras[f_out][0]]))
        f_in = next((i for i, c in enumerate(caras) if i != f_out and
                     _punto(_unit(_newell([pts[j] for j in c[0]])), n_out) < -0.999), None)
        if f_in is None:
            continue
        # adentro de la cara, sin tocar el borde ni otros calados (en el plano de la cara)
        ref = pts[caras[f_out][0][0]]
        e1 = _unit(_resta(pts[caras[f_out][0][1]], ref))
        e2 = _cruz(n_out, e1)
        plano = lambda p: (_punto(_resta(p, ref), e1), _punto(_resta(p, ref), e2))
        borde = [plano(pts[j]) for j in caras[f_out][0]]
        bx0, bx1 = min(b[0] for b in borde), max(b[0] for b in borde)
        by0, by1 = min(b[1] for b in borde), max(b[1] for b in borde)
        p2 = [plano(p) for p in ag]
        x0, x1, y0, y1 = min(p[0] for p in p2), max(p[0] for p in p2), min(p[1] for p in p2), max(p[1] for p in p2)
        if not (bx0 + 0.05 < x0 and x1 < bx1 - 0.05 and by0 + 0.05 < y0 and y1 < by1 - 0.05):
            avisos.append(f"{nombre}: un calado toca el borde del panel; no se perforó en el STEP.")
            continue
        if any(not (x1 < o[0] or o[1] < x0 or y1 < o[2] or o[3] < y0) for o in
               [(min(q[0] for q in pp), max(q[0] for q in pp), min(q[1] for q in pp), max(q[1] for q in pp))
                for _, _, pp in [(a, b, [plano(p) for p in c]) for a, b, c in validos]]):
            avisos.append(f"{nombre}: dos calados se pisan; se perforó sólo el primero en el STEP.")
            continue
        validos.append((f_out, f_in, ag))

    for f_out, f_in, ag in validos:
        n_out = _unit(_newell([pts[j] for j in caras[f_out][0]]))
        t = _punto(_resta(pts[caras[f_in][0][0]], pts[caras[f_out][0][0]]), n_out)
        afuera = [V.indice(p) for p in ag]
        adentro = [V.indice((p[0] + n_out[0] * t, p[1] + n_out[1] * t, p[2] + n_out[2] * t)) for p in ag]
        # el agujero gira al revés que el borde de su cara
        sentido = _punto(_newell([pts[j] for j in afuera]), _newell([pts[j] for j in caras[f_out][0]]))
        caras[f_out].append(list(reversed(afuera)) if sentido > 0 else afuera)
        sentido = _punto(_newell([pts[j] for j in adentro]), _newell([pts[j] for j in caras[f_in][0]]))
        caras[f_in].append(list(reversed(adentro)) if sentido > 0 else adentro)
        n = len(ag)
        for i in range(n):
            j = (i + 1) % n
            caras.append([[afuera[i], afuera[j], adentro[j], adentro[i]]])


def _orientar(cuerpo: Cuerpo) -> None:
    """Da vuelta las caras para que todas giren igual (normal hacia afuera) y marca si cierra."""
    usos: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for f, cara in enumerate(cuerpo.caras):
        for lazo in cara:
            for i, a in enumerate(lazo):
                b = lazo[(i + 1) % len(lazo)]
                usos.setdefault((min(a, b), max(a, b)), []).append((f, 1 if a < b else -1))
    vuelta = [0] * len(cuerpo.caras)       # 0 sin ver, 1 igual, -1 al revés
    vecinos: Dict[int, List[Tuple[int, int, int]]] = {}
    for lista in usos.values():
        if len(lista) == 2:
            (f, s), (g, r) = lista
            vecinos.setdefault(f, []).append((g, s, r))
            vecinos.setdefault(g, []).append((f, r, s))
    for inicio in range(len(cuerpo.caras)):
        if vuelta[inicio]:
            continue
        vuelta[inicio] = 1
        pila = [inicio]
        while pila:
            f = pila.pop()
            for g, s, r in vecinos.get(f, ()):
                # la arista compartida tiene que recorrerse en sentidos opuestos
                quiero = -vuelta[f] * s * r
                if not vuelta[g]:
                    vuelta[g] = quiero
                    pila.append(g)
    cuerpo.caras = [cara if vuelta[f] == 1 else [list(reversed(l)) for l in cara]
                    for f, cara in enumerate(cuerpo.caras)]
    if cuerpo.volumen() < 0:
        cuerpo.caras = [[list(reversed(l)) for l in cara] for cara in cuerpo.caras]
    # cerrado: cada arista la usan dos lazos, una vez en cada sentido
    cuenta: Dict[Tuple[int, int], int] = {}
    for cara in cuerpo.caras:
        for lazo in cara:
            for i, a in enumerate(lazo):
                b = lazo[(i + 1) % len(lazo)]
                cuenta[(a, b)] = cuenta.get((a, b), 0) + 1
    cuerpo.cerrado = all(c == 1 and cuenta.get((b, a), 0) == 1 for (a, b), c in cuenta.items())


def cuerpo_de_solido(malla: Malla3D, so: Solido3D, avisos: Optional[List[str]] = None) -> Optional[Cuerpo]:
    """Arma el B-rep de un sólido de la malla (une vértices, perfora calados, orienta caras)."""
    avisos = avisos if avisos is not None else []
    V = _Vertices()
    caras: List[Cara] = []
    for f in malla.faces[so.desde:so.hasta]:
        lazo = _limpiar([V.indice((p.x, p.y, p.z)) for p in f.vertices])
        if len(lazo) < 3:
            continue
        pts = [V.lista[i] for i in lazo]
        if _es_plana(pts):
            caras.append([lazo])
        else:    # cara alabeada: en triángulos
            for i in range(1, len(lazo) - 1):
                tri = [lazo[0], lazo[i], lazo[i + 1]]
                if _largo(_newell([V.lista[j] for j in tri])) > 1e-9:
                    caras.append([tri])
    if len(caras) < 4:
        return None
    if so.agujeros:
        _agujeros_del_panel(V, caras, [[(p.x, p.y, p.z) for p in ag] for ag in so.agujeros], so.nombre, avisos)
    cuerpo = Cuerpo(so.nombre or "Pieza", so.color, V.lista, caras)
    _orientar(cuerpo)
    return cuerpo


def cuerpos(malla: Malla3D, avisos: Optional[List[str]] = None) -> List[Cuerpo]:
    out = []
    for so in malla.solidos:
        c = cuerpo_de_solido(malla, so, avisos)
        if c is not None:
            out.append(c)
    return out


# ---------------------------------------------------------------- texto STEP

def _txt(s: str) -> str:
    """Cadena STEP: comillas dobladas y lo que no es ASCII como \\X2\\....\\X0\\."""
    out, buf = [], []
    for ch in s:
        if 32 <= ord(ch) < 127:
            if buf:
                out.append("\\X2\\" + "".join(f"{ord(c):04X}" for c in buf) + "\\X0\\")
                buf = []
            out.append("''" if ch == "'" else "\\\\" if ch == "\\" else ch)
        elif ord(ch) <= 0xFFFF:
            buf.append(ch)
    if buf:
        out.append("\\X2\\" + "".join(f"{ord(c):04X}" for c in buf) + "\\X0\\")
    return "'" + "".join(out) + "'"


def _num(x: float, dec: int = 6) -> str:
    s = f"{x:.{dec}f}".rstrip("0")
    if s in ("-0.", "-."):
        s = "0."
    return s if not s.endswith(".") or len(s) > 1 else "0."


def _vec(v: Sequence[float], dec: int = 6) -> str:
    return "(" + ",".join(_num(c, dec) for c in v) + ")"


_CATEGORIAS = ({"base", "lid", "wall", "base_ruedas", "resalte"}, {"profile", "profile_h", "aluminio"}, set(),
               {"equipo", "rack_frente", "espuma", "cajon"})


def _categoria(color: str) -> int:
    """0 madera, 1 aluminio, 2 herrajes, 3 interior (para ordenar las piezas del ensamble)."""
    return next((i for i, c in enumerate(_CATEGORIAS) if color in c), 2)


def _rgb(hexa: str) -> Vec:
    h = hexa.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


class _Escritor:
    def __init__(self) -> None:
        self.lineas: List[str] = []
        self._dir: Dict[Vec, int] = {}

    def __call__(self, texto: str) -> int:
        self.lineas.append(texto)
        return len(self.lineas)

    def ref(self, n: int) -> str:
        return f"#{n}"

    def refs(self, ns: Iterable[int]) -> str:
        return "(" + ",".join(f"#{n}" for n in ns) + ")"

    def direccion(self, v: Sequence[float]) -> int:
        clave = tuple(round(c, 9) for c in v)
        if clave not in self._dir:
            self._dir[clave] = self(f"DIRECTION('',{_vec(v, 9)})")  # type: ignore[index]
        return self._dir[clave]  # type: ignore[index]

    def texto(self) -> str:
        return "\n".join(f"#{i + 1}={l};" for i, l in enumerate(self.lineas))


def _solido(w: _Escritor, c: Cuerpo) -> int:
    """MANIFOLD_SOLID_BREP (o un SHELL_BASED_SURFACE_MODEL si no cierra) del cuerpo."""
    V = c.vertices
    vp = {}
    usados = sorted({i for cara in c.caras for lazo in cara for i in lazo})
    for i in usados:
        cp = w(f"CARTESIAN_POINT('',{_vec(V[i])})")
        vp[i] = (cp, w(f"VERTEX_POINT('',#{cp})"))
    aristas: Dict[Tuple[int, int], int] = {}

    def arista(a: int, b: int) -> Tuple[int, bool]:
        clave = (min(a, b), max(a, b))
        if clave not in aristas:
            p, q = clave
            d = _resta(V[q], V[p])
            ve = w(f"VECTOR('',#{w.direccion(_unit(d))},{_num(_largo(d))})")
            ln = w(f"LINE('',#{vp[p][0]},#{ve})")
            aristas[clave] = w(f"EDGE_CURVE('',#{vp[p][1]},#{vp[q][1]},#{ln},.T.)")
        return aristas[clave], a < b

    caras_ids = []
    for cara in c.caras:
        borde = [V[i] for i in cara[0]]
        n = _unit(_newell(borde))
        e = _unit(_resta(borde[1], borde[0]))
        e = _unit(_resta(e, tuple(n[k] * _punto(e, n) for k in range(3))))
        ax = w(f"AXIS2_PLACEMENT_3D('',#{w(f'CARTESIAN_POINT({chr(39)}{chr(39)},{_vec(borde[0])})')},"
               f"#{w.direccion(n)},#{w.direccion(e)})")
        plano = w(f"PLANE('',#{ax})")
        limites = []
        for k, lazo in enumerate(cara):
            oes = []
            for i, a in enumerate(lazo):
                ec, sentido = arista(a, lazo[(i + 1) % len(lazo)])
                oes.append(w(f"ORIENTED_EDGE('',*,*,#{ec},{'.T.' if sentido else '.F.'})"))
            el = w(f"EDGE_LOOP('',{w.refs(oes)})")
            limites.append(w(f"{'FACE_OUTER_BOUND' if k == 0 else 'FACE_BOUND'}('',#{el},.T.)"))
        caras_ids.append(w(f"ADVANCED_FACE('',{w.refs(limites)},#{plano},.T.)"))
    if c.cerrado:
        cs = w(f"CLOSED_SHELL('',{w.refs(caras_ids)})")
        return w(f"MANIFOLD_SOLID_BREP({_txt(c.nombre)},#{cs})")
    os_ = w(f"OPEN_SHELL('',{w.refs(caras_ids)})")
    return w(f"SHELL_BASED_SURFACE_MODEL({_txt(c.nombre)},({w.ref(os_)}))")


def texto_step(lista: Sequence[Cuerpo], titulo: str = "Flightcase", archivo: str = "case.step") -> str:
    """Archivo STEP AP214 con un ensamble: una pieza por nombre, cada una con sus cuerpos y colores."""
    w = _Escritor()
    # unidades: milímetros
    mm = w("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
    rad = w("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
    sr = w("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
    unc = w(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-03),#{mm},'distance_accuracy_value','confusion accuracy')")
    ctx = w(f"( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{unc})) "
            f"GLOBAL_UNIT_ASSIGNED_CONTEXT((#{mm},#{rad},#{sr})) REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY') )")
    ac = w("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
    w(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#{ac})")
    pc = w(f"PRODUCT_CONTEXT('',#{ac},'mechanical')")
    pdc = w(f"PRODUCT_DEFINITION_CONTEXT('part definition',#{ac},'design')")
    origen = w("CARTESIAN_POINT('',(0.,0.,0.))")
    z, x = w.direccion((0, 0, 1)), w.direccion((1, 0, 0))

    def ejes() -> int:
        return w(f"AXIS2_PLACEMENT_3D('',#{origen},#{z},#{x})")

    def producto(nombre: str) -> int:
        p = w(f"PRODUCT({_txt(nombre)},{_txt(nombre)},'',(#{pc}))")
        w(f"PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#{p}))")
        pf = w(f"PRODUCT_DEFINITION_FORMATION('','',#{p})")
        return w(f"PRODUCT_DEFINITION('design','',#{pf},#{pdc})")

    # el ensamble
    pd_raiz = producto(titulo)
    ejes_raiz = ejes()
    hijos_ejes: List[int] = []
    rep_raiz_idx = w("")         # se completa al final, cuando se conocen los ejes de los hijos
    w(f"SHAPE_DEFINITION_REPRESENTATION(#{w(f'PRODUCT_DEFINITION_SHAPE({chr(39)}{chr(39)},{chr(39)}{chr(39)},#{pd_raiz})')},#{rep_raiz_idx})")

    # piezas agrupadas por nombre, en el orden en que aparecen
    grupos: Dict[str, List[Cuerpo]] = {}
    for c in lista:
        grupos.setdefault(c.nombre, []).append(c)
    # madera primero, después aluminio, herrajes e interior
    orden = list(grupos)
    grupos = {n: grupos[n] for n in sorted(orden, key=lambda n: (_categoria(grupos[n][0].color), orden.index(n)))}
    estilos: List[int] = []
    colores: Dict[str, int] = {}

    def estilo(color: str) -> int:
        if color not in colores:
            r, g, b = _rgb(COLORES.get(color, COLORES["base"]))
            col = w(f"COLOUR_RGB('{color}',{_num(r, 4)},{_num(g, 4)},{_num(b, 4)})")
            fas = w(f"FILL_AREA_STYLE('',(#{w(f'FILL_AREA_STYLE_COLOUR({chr(39)}{chr(39)},#{col})')}))")
            sss = w(f"SURFACE_SIDE_STYLE('',(#{w(f'SURFACE_STYLE_FILL_AREA(#{fas})')}))")
            colores[color] = w(f"PRESENTATION_STYLE_ASSIGNMENT((#{w(f'SURFACE_STYLE_USAGE(.BOTH.,#{sss})')}))")
        return colores[color]

    for i, (nombre, cs) in enumerate(grupos.items()):
        pd = producto(nombre)
        items = [_solido(w, c) for c in cs]
        for it, c in zip(items, cs):
            estilos.append(w(f"STYLED_ITEM('color',(#{estilo(c.color)}),#{it})"))
        ej = ejes()
        tipo = "ADVANCED_BREP_SHAPE_REPRESENTATION" if all(c.cerrado for c in cs) else "SHAPE_REPRESENTATION"
        rep = w(f"{tipo}({_txt(nombre)},{w.refs(items + [ej])},#{ctx})")
        w(f"SHAPE_DEFINITION_REPRESENTATION(#{w(f'PRODUCT_DEFINITION_SHAPE({chr(39)}{chr(39)},{chr(39)}{chr(39)},#{pd})')},#{rep})")
        # ubicado en el ensamble sin moverlo (las coordenadas ya son las del case)
        en_raiz = ejes()
        hijos_ejes.append(en_raiz)
        nauo = w(f"NEXT_ASSEMBLY_USAGE_OCCURRENCE('{i + 1}',{_txt(nombre)},'',#{pd_raiz},#{pd},$)")
        pds = w(f"PRODUCT_DEFINITION_SHAPE('','',#{nauo})")
        idt = w(f"ITEM_DEFINED_TRANSFORMATION('','',#{ej},#{en_raiz})")
        rr = w(f"( REPRESENTATION_RELATIONSHIP('','',#{rep},#{rep_raiz_idx}) "
               f"REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(#{idt}) SHAPE_REPRESENTATION_RELATIONSHIP() )")
        w(f"CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(#{rr},#{pds})")
    w.lineas[rep_raiz_idx - 1] = f"SHAPE_REPRESENTATION({_txt(titulo)},{w.refs([ejes_raiz] + hijos_ejes)},#{ctx})"
    if estilos:
        w(f"MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION('',{w.refs(estilos)},#{ctx})")

    ahora = _dt.datetime.now().replace(microsecond=0).isoformat()
    cabecera = (
        "ISO-10303-21;\nHEADER;\n"
        f"FILE_DESCRIPTION(({_txt('Flightcase ' + titulo)}),'2;1');\n"
        f"FILE_NAME({_txt(archivo)},'{ahora}',(''),(''),'Flightcase Calculator','Flightcase Calculator','');\n"
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\nENDSEC;\nDATA;\n"
    )
    return cabecera + w.texto() + "\nENDSEC;\nEND-ISO-10303-21;\n"


@dataclass
class ResultadoStep:
    ruta: str
    piezas: int
    cuerpos: int
    avisos: List[str] = field(default_factory=list)


def exportar_step(res: ResultadoTaller, ruta: str, titulo: Optional[str] = None,
                  interior: bool = True) -> ResultadoStep:
    """Escribe el case armado (tapas cerradas, con el interior) en `ruta` (.step)."""
    malla = malla_3d(res, Opciones3D(interior=interior))
    avisos: List[str] = []
    lista = cuerpos(malla, avisos)
    abiertos = sorted({c.nombre for c in lista if not c.cerrado})
    if abiertos:
        avisos.append("Quedaron como superficies (no sólidos): " + ", ".join(abiertos))
    titulo = titulo or os.path.splitext(os.path.basename(ruta))[0] or "Flightcase"
    texto = texto_step(lista, titulo, os.path.basename(ruta))
    with open(ruta, "w", encoding="ascii", newline="\n") as f:
        f.write(texto)
    return ResultadoStep(ruta, len({c.nombre for c in lista}), len(lista), avisos)
