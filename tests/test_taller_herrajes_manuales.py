"""Herrajes puestos a mano sobre las caras del case (herrajes_manuales)."""

import os

import pytest

from flightcase.taller import herrajes_manuales as hm
from flightcase.taller import vectores
from flightcase.taller.modelo import calcular
from flightcase.taller.produccion import datos, exportar, panel_dxf, trazos_manuales
from flightcase.taller.scad import escribir_proyecto, leer_asignaciones

MANIJA = "08-34082"        # asa retráctil embutida, calado 134 x 81
CIERRE = "08-17373S"       # cierre mariposa embutido, calado 76 x 70
RUEDA = "08-372151"
PIE = "08-4907"

LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
<g transform="translate(10,10)"><path d="M0 0 L60 0 L60 80 Z M80 0 C120 0 120 80 80 80 Z"/>
<circle cx="150" cy="40" r="30"/><rect x="0" y="85" width="180" height="5"/></g></svg>"""


def _man(r):
    return r.valores["manuales"]


# ---------------------------------------------------------------------------
# Caras
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("orientacion", ["vertical", "horizontal", "frontal"])
@pytest.mark.parametrize("tapas", [1, 2])
def test_caras_ida_y_vuelta(orientacion, tapas):
    r = calcular({"orientacion": orientacion, "tapas": tapas, "acceso_lateral": 150 if orientacion == "frontal" else 0})
    caras = hm.caras(r)
    assert [c.id for c in caras] == list(hm.CARAS)
    ids = {p.id for c in caras for p in c.paneles}
    assert ids == {p.id for p in r.paneles if p.id != "base_ruedas" and not p.id.startswith("bandeja")}
    for c in caras:
        assert {c.ancho, c.alto} == {c.W, c.H}
        for x, y in ((10, 20), (c.ancho - 5, 3), (c.ancho / 2, c.alto - 1)):
            assert c.a_vista(*c.a_cara(x, y)) == pytest.approx((x, y))
        for p in c.paneles:
            rp = c.rect_panel(p)
            assert 0 <= rp[0] and rp[2] <= c.W + 0.01 and 0 <= rp[1] and rp[3] <= c.H + 0.01
            fu, fv = c.panel_a_cara(p, 12, 34)
            assert c.cara_a_panel(p, fu, fv) == pytest.approx((12, 34))


def test_vista_derecha_en_un_rack():
    """En un case frontal el lateral se ve parado: alto de la vista = alto del case en uso."""
    r = calcular({"orientacion": "frontal"})
    izq = next(c for c in hm.caras(r) if c.id == "izq")
    assert izq.alto == pytest.approx(r.valores["ext_prof"])      # int_prof es el ALTO en frontal
    assert izq.nombre == "Lateral izq."
    assert any(j["horizontal"] for j in izq.juntas)


def test_sin_herrajes_manuales_no_cambia_nada():
    a, b = calcular(), calcular({"herrajes_manuales": []})
    assert a.calados == b.calados and a.marcas == b.marcas and a.herrajes == b.herrajes
    assert b.valores["manuales"] is None


# ---------------------------------------------------------------------------
# Resolución
# ---------------------------------------------------------------------------

def test_manija_embutida_girada():
    base = calcular({"manijas": False})
    r = calcular({"manijas": False, "herrajes_manuales": [[MANIJA, "frente", 200, 120, 90]]})
    (c,) = _man(r).colocados
    assert c.panel == "cuerpo_frente" and c.forma == "calado"
    assert (c.ancho, c.alto) == (81, 134)
    (k,) = [k for k in r.calados if k.tipo == "manija a mano"]
    assert (k.panel, k.ancho, k.alto) == ("cuerpo_frente", 81, 134)
    cara = next(x for x in hm.caras(r) if x.id == "frente")
    assert cara.a_vista(*cara.panel_a_cara(cara.panel("cuerpo_frente"), k.cx, k.cy)) == pytest.approx((200, 120))
    h = next(h for h in r.herrajes if h.ref == MANIJA)
    assert h.cantidad == 1 and "a mano" in h.detalle
    rem = lambda res: next(h for h in res.herrajes if h.nombre.startswith("Remache")).cantidad
    assert rem(r) > rem(base)


def test_cierre_se_centra_en_la_junta_como_los_automaticos():
    r = calcular({"cierres_frente_n": 2, "herrajes_manuales": [[CIERRE, "frente", 300, 30]]})
    auto = [m for m in r.marcas if m.tipo == "cierre" and m.panel == "cuerpo_frente"]
    (c,) = _man(r).colocados
    assert c.forma == "junta"
    m_cuerpo, m_tapa = c.marcas
    assert (m_cuerpo.panel, m_tapa.panel) == ("cuerpo_frente", "tapa_frente")
    assert m_cuerpo.y == pytest.approx(auto[0].y)
    tapa = [m for m in r.marcas if m.tipo == "cierre" and m.panel == "tapa_frente"]
    assert m_tapa.y == pytest.approx(tapa[0].y)
    cara = next(x for x in hm.caras(r) if x.id == "frente")
    assert c.y == pytest.approx(r.valores["geo"]["z_cierre"])           # la y pedida se ignora
    assert any(k.tipo == "cierre a mano" for k in r.calados)              # cierre embutido: calado en el cuerpo
    assert cara.juntas[0]["fv"] == pytest.approx(c.y)


def test_cierre_en_la_segunda_tapa():
    r = calcular({"tapas": 2, "herrajes_manuales": [[CIERRE, "der", 150, 5]]})
    (c,) = _man(r).colocados
    assert {m.panel for m in c.marcas} == {"cuerpo_der", "tapa2_der"}
    assert all(m.texto == "c2" for m in c.marcas)


def test_frontal_la_manija_horizontal_en_la_vista_queda_horizontal_en_el_mundo():
    r = calcular({"orientacion": "frontal", "manijas": False, "herrajes_manuales": [[MANIJA, "der", 150, 200]]})
    (c,) = _man(r).colocados
    assert (c.ancho, c.alto) == (134, 81)
    # en el panel, el ancho de la vista corre por el eje v (profundidad del case)
    assert (c.pw, c.ph) == (81, 134)


def test_avisos_aluminio_fuera_y_choques():
    r = calcular({"herrajes_manuales": [
        [MANIJA, "frente", 20, 100],            # sobre el ángulo de la arista
        [PIE, "frente", 300, 1000],              # fuera de la cara
        [MANIJA, "izq", 209, 125],               # encima de la manija automática del lateral
        ["xx", "costado", 0, 0],                 # cara que no existe
        ["mal"]]})
    txt = " ".join(r.avisos)
    assert "pisa el aluminio" in txt
    assert "queda fuera de los paneles" in txt
    assert "se pisan" in txt
    assert "no existe" in txt
    assert "mal escrita" in txt


def test_rueda_pie_y_pieza_propia():
    r = calcular({"herrajes_manuales": [[RUEDA, "abajo", 120, 120], [PIE, "abajo", 400, 300],
                                        ["Placa de identificación", "trasera", 300, 120, 0, 0, 80, 40]]})
    agujeros = [k for k in r.calados if k.tipo == "agujero a mano"]
    assert len(agujeros) == 4 and {k.panel for k in agujeros} == {"piso"}
    assert any(h.nombre.startswith("Bulón") and h.detalle == "ruedas puestas a mano" for h in r.herrajes)
    propia = next(h for h in r.herrajes if h.nombre == "Placa de identificación")
    assert propia.ref == "" and propia.cantidad == 1
    c = _man(r).colocados[2]
    assert (c.pw, c.ph) == (80, 40) and c.panel == "cuerpo_trasera"


# ---------------------------------------------------------------------------
# Logos
# ---------------------------------------------------------------------------

def test_logo_svg_y_dxf(tmp_path):
    (tmp_path / "logo.svg").write_text(LOGO, encoding="utf-8")
    lineas = vectores.leer(str(tmp_path / "logo.svg"))
    assert len(lineas) == 4
    x0, y0, x1, y1 = vectores.caja(lineas)
    assert (x1 - x0, y1 - y0) == pytest.approx((180, 90), abs=0.5)
    r = calcular({"_carpeta": str(tmp_path), "herrajes_manuales": [
        ["logo", "frente", 300, 120, 0, 1, 160, 0, "logo.svg"],
        ["logo", "izq", 200, 120, 90, 0, 100, 0, "logo.svg", "grabado"]]})
    placa, grabado = _man(r).colocados
    assert (placa.ancho, placa.alto) == pytest.approx((160, 80))
    assert (grabado.ancho, grabado.alto) == pytest.approx((50, 100))     # girado 90°
    lx = [p[0] for l in placa.lineas for p in l]
    assert min(lx) >= 300 - 80 - 0.01 and max(lx) <= 300 + 80 + 0.01
    assert any(h.nombre == "Placa de logo logo.svg" for h in r.herrajes)
    d = datos(r)
    trazos = trazos_manuales(d["manuales"]["cuerpo_izq"])
    assert {c for c, _ in trazos} == {"GRABADO"}
    texto = panel_dxf(400, 300, [], trazos)
    assert "GRABADO" in texto and texto.count("\nLINE\n") > 4
    assert vectores.leer_dxf(texto)            # el DXF se vuelve a leer


def test_logo_que_no_se_puede_leer():
    r = calcular({"herrajes_manuales": [["logo", "frente", 300, 120, 0, 0, 100, 50, "no_existe.svg"]]})
    assert any("no se pudo leer" in a for a in r.avisos)
    (c,) = _man(r).colocados
    assert (c.ancho, c.alto) == (100, 50)


def test_dxf_de_logo_con_arcos(tmp_path):
    from flightcase.taller.produccion import _dxf_arco, _dxf_linea
    ent = _dxf_linea("0", (0, 0), (100, 0)) + _dxf_arco("0", (50, 0), 50, 0, 180)
    texto = "  0\nSECTION\n  2\nENTITIES\n" + ent + "  0\nENDSEC\n  0\nEOF\n"
    (tmp_path / "a.dxf").write_text(texto)
    lineas = vectores.leer(str(tmp_path / "a.dxf"))
    assert vectores.caja(lineas) == pytest.approx((0, 0, 100, 50), abs=0.5)


# ---------------------------------------------------------------------------
# Edición, .scad, paquete, 3D
# ---------------------------------------------------------------------------

def test_espejar_y_fila():
    r = calcular()
    frente = next(c for c in hm.caras(r) if c.id == "frente")
    f = hm.Fila(MANIJA, "frente", 100, 120, 90)
    g = hm.espejar(f, frente)
    assert (g.cara, g.x, g.y, g.giro, g.espejo) == ("trasera", frente.ancho - 100, 120, 270, False)
    assert hm.Fila(MANIJA, "izq", 10, 20.5).lista() == [MANIJA, "izq", 10, 20.5]
    assert hm.Fila("logo", "izq", 10, 20, 0, True, 100, 0, "a.svg").lista() == ["logo", "izq", 10, 20, 0, 1, 100, 0, "a.svg"]
    assert hm.Fila.de([MANIJA, "izq", 10, 20, 450]).giro == 90


def test_scad_ida_y_vuelta():
    filas = [[MANIJA, "frente", 200, 120, 90], ["logo", "izq", 200, 120, 0, 1, 100, 0, "logos/a.svg", "grabado"]]
    texto = escribir_proyecto({"int_ancho": 500, "herrajes_manuales": filas, "_carpeta": "/x"},
                              {"int_ancho": 600, "herrajes_manuales": []})
    assert "_carpeta" not in texto
    assert leer_asignaciones(texto) == {"int_ancho": 500, "herrajes_manuales": filas}


def test_paquete_y_3d(tmp_path):
    from flightcase.taller.geometria import Opciones3D, malla_3d
    params = {"manijas": False, "herrajes_manuales": [
        [MANIJA, "izq", 200, 120], [CIERRE, "frente", 150, 0], [PIE, "abajo", 300, 200],
        ["08-34331", "der", 200, 120, 90], ["Chapa", "trasera", 300, 120, 0, 0, 80, 40]]}
    r = calcular(params)
    sin = calcular({"manijas": False})
    assert len(malla_3d(r).faces) > len(malla_3d(sin).faces)
    resaltada = malla_3d(r, Opciones3D(resaltar_manuales=True))
    assert any(f.color_group == "resalte" for f in resaltada.faces)
    paq = exportar(r, str(tmp_path), pdf=False)
    dxf_izq = next(a for a in paq.archivos if "cuerpo_izq" in a)
    with open(dxf_izq, encoding="utf-8") as f:
        assert f.read().count("ARC") >= 4            # el calado de la manija, con radios
    dxf_tr = next(a for a in paq.archivos if "cuerpo_trasera" in a)
    with open(dxf_tr, encoding="utf-8") as f:
        assert "MARCA" in f.read()
    with open(os.path.join(str(tmp_path), "materiales.csv"), encoding="utf-8-sig") as f:
        mat = f.read()
    assert MANIJA in mat and "Chapa" in mat
    from flightcase.taller.planos import generar as gen
    pasos = hm.pasos_instructivo(r, gen.agrupar_piezas(datos(r)))
    assert pasos and pasos[0]["titulo"] == "Colocar los herrajes a mano"
    assert len(pasos[0]["texto"]) == 1 + 5


# ---------------------------------------------------------------------------
# Pestaña
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_pestana_herrajes_a_mano(qapp, tmp_path):
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    h = w.herrajes
    h.set_cara("frente")
    i = h.cmb_ref.findData(MANIJA)
    h.cmb_ref.setCurrentIndex(i)
    h.agregar(150, 120)
    assert w.params["herrajes_manuales"] == [[MANIJA, "frente", 150, 120]]
    assert any(k.tipo == "manija a mano" for k in w.resultado.calados)
    h.lienzo.movido.emit(0, 180.4, 130)
    assert w.params["herrajes_manuales"][0][2:4] == [180.4, 130]
    h.girar()
    assert w.params["herrajes_manuales"][0][4] == 90
    h.copiar()
    assert len(w.params["herrajes_manuales"]) == 2 and h.sel == 1
    h.espejar()
    assert w.params["herrajes_manuales"][2][1] == "trasera" and h.cmb_cara.currentData() == "trasera"
    h.quitar()
    assert len(w.params["herrajes_manuales"]) == 2
    (tmp_path / "logo.svg").write_text(LOGO, encoding="utf-8")
    ruta = tmp_path / "case.scad"
    w.guardar(str(ruta))
    h.agregar_logo(str(tmp_path / "logo.svg"))
    assert w.params["herrajes_manuales"][-1][8] == "logo.svg"      # relativo al .scad
    assert _man(w.resultado).colocados[-1].lineas
    w.guardar(str(ruta))
    w.nuevo()
    assert w.params["herrajes_manuales"] == []
    w.abrir(str(ruta))
    assert len(w.params["herrajes_manuales"]) == 3
    assert not [a for a in w.resultado.avisos if "logo" in a.lower()]


def test_iman_pega_a_la_junta(qapp):
    from flightcase.ui.widgets.herrajes_2d_widget import Lienzo2D
    r = calcular({"herrajes_manuales": [[PIE, "frente", 300, 100]]})
    cara = next(c for c in hm.caras(r) if c.id == "frente")
    L = Lienzo2D()
    L.resize(800, 500)
    col = _man(r).colocados[0]
    f = dict(idx=0, x=col.x, y=col.y, rect=col.rect_vista, forma=col.forma, nombre=col.nombre)
    L.set_datos(cara, [], [f], 0)
    banda = cara.juntas[0]["banda"]
    # el borde de arriba del pie se acerca al borde de abajo de la banda del perfil de cierre
    x, y, g = L.imantar(f, 300.3, banda[0] - col.alto / 2 - 1.2)
    assert y == pytest.approx(banda[0] - col.alto / 2) and ("y", pytest.approx(banda[0])) in g
    assert x == 300 or x == pytest.approx(cara.ancho / 2)
