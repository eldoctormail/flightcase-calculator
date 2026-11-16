"""Fórmulas: parámetros que se calculan a partir de otros (no está en flightcase.scad).

``formulas = [[nombre, expresión], ...]``. Si ``nombre`` es un parámetro del case, la fórmula
le pone el valor (y en la ventana ese campo queda calculado). Si no lo es, es una variable propia
que se puede usar en las otras fórmulas. Ejemplos::

    ["alto_equipo", "88"]
    ["int_alto_cuerpo", "alto_equipo + 2 * 15"]
    ["int_alto_tapa", "max(60, int_alto_cuerpo / 3)"]
    ["rack_u", "ceil(alto_equipo / 44.45)"]
    ["ruedas", "4 if int_ancho > 800 else 0"]

Se puede usar: números, los parámetros numéricos (y los de lista con [i], como rueda_placa[0]),
las variables propias, + - * / // % **, paréntesis, comparaciones, ``a if condición else b``,
``and``/``or``/``not`` y las funciones min, max, round, ceil, floor, abs y sqrt. El orden de
las filas no importa: se calculan según lo que usa cada una. Si una fórmula se usa a sí misma
(directa o indirectamente) o tiene un error, se avisa y no se aplica.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

FUNCIONES: Dict[str, Callable[..., float]] = {
    "min": min, "max": max, "round": round, "ceil": math.ceil, "floor": math.floor, "abs": abs, "sqrt": math.sqrt,
}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.Eq: operator.eq, ast.NotEq: operator.ne}
NOMBRE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ErrorFormula(ValueError):
    pass


@dataclass
class ResultadoFormulas:
    valores: Dict[str, Any] = field(default_factory=dict)        # parámetro del case -> valor calculado
    variables: Dict[str, float] = field(default_factory=dict)    # variables propias -> valor
    expresiones: Dict[str, str] = field(default_factory=dict)    # nombre -> expresión (las que se aplicaron)
    avisos: List[str] = field(default_factory=list)


def _normalizar(texto: str) -> str:
    """Admite coma decimal (2,5) y ^ como potencia."""
    t = re.sub(r"(?<=\d),(?=\d)", ".", str(texto))
    return t.replace("^", "**")


def _arbol(texto: str) -> ast.AST:
    try:
        return ast.parse(_normalizar(texto), mode="eval").body
    except SyntaxError as e:
        raise ErrorFormula(f"está mal escrita ({e.msg})") from None


def nombres_usados(nodo: ast.AST) -> Set[str]:
    out = set()
    for n in ast.walk(nodo):
        if isinstance(n, ast.Name) and n.id not in FUNCIONES:
            out.add(n.id)
    return out


def evaluar(nodo: ast.AST, valores: Dict[str, Any]) -> Any:
    """Evalúa el árbol con sólo lo permitido (sin atributos, sin llamadas a otras cosas)."""
    def ev(n: ast.AST) -> Any:
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, bool)):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in valores:
                raise ErrorFormula(f"«{n.id}» no es un parámetro ni una variable")
            v = valores[n.id]
            if isinstance(v, bool) or isinstance(v, (int, float, list)):
                return v
            raise ErrorFormula(f"«{n.id}» no es un número")
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(a, list) or isinstance(b, list):
                raise ErrorFormula("no se puede hacer cuentas con una lista: usá [0], [1]...")
            try:
                return _BIN[type(n.op)](a, b)
            except ZeroDivisionError:
                raise ErrorFormula("divide por cero") from None
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd, ast.Not)):
            v = ev(n.operand)
            return (not v) if isinstance(n.op, ast.Not) else (-v if isinstance(n.op, ast.USub) else +v)
        if isinstance(n, ast.BoolOp):
            vals = [ev(x) for x in n.values]
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.Compare) and all(type(o) in _CMP for o in n.ops):
            izq = ev(n.left)
            for op, der_n in zip(n.ops, n.comparators):
                der = ev(der_n)
                if not _CMP[type(op)](izq, der):
                    return False
                izq = der
            return True
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        if isinstance(n, ast.Subscript):
            lista, i = ev(n.value), ev(n.slice)
            if not isinstance(lista, list) or not isinstance(i, (int, float)) or int(i) != i:
                raise ErrorFormula("sólo se puede tomar un elemento de una lista con un número entero, como [0]")
            try:
                return lista[int(i)]
            except IndexError:
                raise ErrorFormula(f"la lista no tiene el elemento [{int(i)}]") from None
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCIONES and not n.keywords:
            try:
                return FUNCIONES[n.func.id](*[ev(a) for a in n.args])
            except (TypeError, ValueError) as e:
                raise ErrorFormula(f"{n.func.id}(): {e}") from None
        raise ErrorFormula("usa algo que no se puede en una fórmula")
    return ev(nodo)


def _filas(P: Dict[str, Any], R: ResultadoFormulas) -> List[Tuple[str, str]]:
    filas = P.get("formulas") or []
    if not isinstance(filas, list):
        R.avisos.append("formulas tiene que ser una lista de filas [nombre, expresión].")
        return []
    out, vistos = [], set()
    for i, f in enumerate(filas, 1):
        if not isinstance(f, (list, tuple)) or len(f) < 2 or not str(f[0]).strip():
            R.avisos.append(f"Fórmula {i}: va [nombre, expresión].")
            continue
        nombre, expr = str(f[0]).strip(), str(f[1]).strip()
        if not NOMBRE.match(nombre):
            R.avisos.append(f"Fórmula {i}: «{nombre}» no sirve de nombre (letras, números y _, sin espacios).")
            continue
        if not expr:
            continue
        if nombre in vistos:
            R.avisos.append(f"Fórmula {i}: «{nombre}» ya tiene otra fórmula; vale la primera.")
            continue
        vistos.add(nombre)
        out.append((nombre, expr))
    return out


def aplicar(P: Dict[str, Any], defectos: Optional[Dict[str, Any]] = None,
            enteros: Iterable[str] = ()) -> ResultadoFormulas:
    """Calcula las fórmulas de P["formulas"] y pone los valores en P (los parámetros del case).
    Los de ``enteros`` (cantidades) se redondean; las medidas quedan con hasta 4 decimales."""
    R = ResultadoFormulas()
    filas = _filas(P, R)
    if not filas:
        return R
    defectos = defectos if defectos is not None else P
    arboles: Dict[str, ast.AST] = {}
    for nombre, expr in filas:
        try:
            arboles[nombre] = _arbol(expr)
        except ErrorFormula as e:
            R.avisos.append(f"Fórmula de «{nombre}» ({expr}): {e}. No se aplica.")
    deps = {n: nombres_usados(a) & set(arboles) for n, a in arboles.items()}
    valores: Dict[str, Any] = {k: v for k, v in P.items() if isinstance(v, (int, float, list)) or isinstance(v, bool)}
    hechas: Set[str] = set()
    pendientes = dict(arboles)
    while pendientes:
        listas = [n for n in pendientes if deps[n] <= hechas]
        if not listas:
            ciclo = ", ".join(sorted(pendientes))
            R.avisos.append(f"Las fórmulas de {ciclo} se usan entre sí en círculo: no se aplican.")
            break
        for nombre in listas:
            arbol = pendientes.pop(nombre)
            expr = dict(filas)[nombre]
            try:
                v = evaluar(arbol, valores)
            except ErrorFormula as e:
                R.avisos.append(f"Fórmula de «{nombre}» ({expr}): {e}. No se aplica.")
                hechas.add(nombre)
                continue
            if isinstance(v, bool):
                v = int(v)
            if not isinstance(v, (int, float)) or (isinstance(v, float) and not math.isfinite(v)):
                R.avisos.append(f"Fórmula de «{nombre}» ({expr}): no da un número. No se aplica.")
                hechas.add(nombre)
                continue
            if nombre in defectos:
                anterior = defectos[nombre]
                if isinstance(anterior, bool):
                    v = bool(v)
                elif isinstance(anterior, (int, float)):
                    v = int(round(v)) if nombre in enteros else round(float(v), 4)
                    if isinstance(anterior, int) and float(v).is_integer():
                        v = int(v)
                else:
                    R.avisos.append(f"Fórmula de «{nombre}»: ese parámetro no es un número. No se aplica.")
                    hechas.add(nombre)
                    continue
                P[nombre] = v
                R.valores[nombre] = v
            else:
                v = round(float(v), 4)
                R.variables[nombre] = v
            valores[nombre] = v
            R.expresiones[nombre] = expr
            hechas.add(nombre)
    return R
