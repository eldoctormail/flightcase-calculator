"""Fórmulas: medidas calculadas a partir de otras (formulas.py)."""

import pytest

from flightcase.taller import formulas
from flightcase.taller.modelo import calcular, parametros_por_defecto
from flightcase.taller.scad import leer_proyecto


def test_formulas_ponen_parametros_y_variables():
    P = parametros_por_defecto()
    P["formulas"] = [["int_alto_tapa", "max(60, int_alto_cuerpo / 3)"],   # el orden no importa
                     ["int_alto_cuerpo", "alto_equipo + 2 * 15"],
                     ["alto_equipo", "88,5"],                             # coma decimal
                     ["ruedas", "4 if int_ancho > 500 else 0"],
                     ["unidades", "ceil(alto_equipo / 44.45)"]]
    R = formulas.aplicar(P, parametros_por_defecto(), {"ruedas"})
    assert not R.avisos
    assert R.variables == {"alto_equipo": 88.5, "unidades": 2}
    assert P["int_alto_cuerpo"] == pytest.approx(118.5)
    assert P["int_alto_tapa"] == 60
    assert P["ruedas"] == 4 and isinstance(P["ruedas"], int)


def test_formulas_con_error_o_en_circulo_avisan_y_no_se_aplican():
    P = parametros_por_defecto()
    ancho = P["int_ancho"]
    P["formulas"] = [["a", "b + 1"], ["b", "a * 2"], ["int_ancho", "__import__('os')"],
                     ["int_prof", "1 / 0"], ["mal nombre", "3"], ["int_alto_tapa", "rueda_placa[0] + 10"]]
    R = formulas.aplicar(P, parametros_por_defecto(), {"ruedas"})
    texto = " ".join(R.avisos)
    assert "círculo" in texto and "divide por cero" in texto and "no sirve de nombre" in texto
    assert P["int_ancho"] == ancho and "int_ancho" not in R.valores
    assert R.valores["int_alto_tapa"] == pytest.approx(P["rueda_placa"][0] + 10)


def test_no_evalua_cosas_peligrosas():
    for expr in ("__import__('os').system('x')", "().__class__", "open('a')", "[x for x in (1,)]", "'texto'"):
        with pytest.raises(formulas.ErrorFormula):
            formulas.evaluar(formulas._arbol(expr), {})


def test_el_modelo_aplica_las_formulas():
    base = calcular()
    res = calcular({"formulas": [["int_ancho", "int_prof + 100"]]})
    assert res.valores["formulas"].valores == {"int_ancho": 500}
    assert res.valores["ext_ancho"] == pytest.approx(base.valores["ext_ancho"] - 100)
    res = calcular({"formulas": [["int_ancho", "nada + 1"]]})
    assert any("nada" in a for a in res.avisos)


def test_ventana_bloquea_los_campos_calculados(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    w.editores["formulas"].poner([["int_alto_tapa", "int_alto_cuerpo / 2"], ["x", "3"]])
    w.recalcular()
    assert w.params["int_alto_tapa"] == pytest.approx(w.params["int_alto_cuerpo"] / 2)
    assert not w.editores["int_alto_tapa"].widget.isEnabled()
    assert not w.medidas["tapa"].isEnabled() and w.medidas["ancho"].isEnabled()
    assert "x</b> = 3" in w.lbl_formulas.text()
    ruta = tmp_path / "f.scad"
    assert w.guardar(str(ruta))
    assert leer_proyecto(ruta)["formulas"] == [["int_alto_tapa", "int_alto_cuerpo / 2"], ["x", "3"]]
    w.editores["formulas"].poner([])
    w.recalcular()
    assert w.editores["int_alto_tapa"].widget.isEnabled() and w.medidas["tapa"].isEnabled()
