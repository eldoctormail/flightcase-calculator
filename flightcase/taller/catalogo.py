"""Catálogo editable de herrajes, perfiles y placas.

El catálogo que viene con la app (resources/catalogo_fr.json) es de solo lectura. Lo que el
usuario cambia se guarda aparte, en su carpeta de datos (catalogo_propio.json):

- ``articulos``: filas propias. Una fila con la ref de un artículo incluido lo reemplaza
  (medidas del proveedor real); una ref nueva es un artículo nuevo.
- ``ocultos``: refs de artículos incluidos que el usuario quitó.

Así una versión nueva de la app puede traer artículos nuevos sin pisar lo que cargó el
usuario. Cada fila es ``{ref, categoria, nombre, datos, verificado}`` y, opcionales,
``proveedor`` y ``nota``.

El catálogo también se pasa a y desde una planilla CSV (separador ; y coma decimal, como la
abre Excel en castellano): una fila por artículo y una columna por medida.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..paths import bundled_resource, user_resource

ARCHIVO = "catalogo_propio.json"
CAMPOS_FIJOS = ("ref", "categoria", "nombre", "datos", "verificado", "proveedor", "nota")

# Categorías en el orden en que se muestran: (clave, nombre, medidas). Cada medida es
# (clave en datos, título, tipo, ayuda). Tipos: "num", "par" (dos números, «ancho x alto»),
# "texto" o una tupla con las opciones. Sólo son las medidas que usan las reglas del taller:
# un artículo puede tener otras (se muestran y se exportan igual).
CATEGORIAS: List[Tuple[str, str, List[Tuple[str, str, Any, str]]]] = [
    ("placa", "Placas", [
        ("tipo", "Tipo", "texto", "Fenólico, abedul, MDF, polipropileno… (sólo para vos: el material es el nombre)."),
        ("esp", "Espesor", "num", "Espesor real de la placa en mm (medilo: un fenólico «9 mm» suele dar 9,2)."),
        ("largo", "Largo hoja", "num", "Largo de la hoja entera en mm (el optimizador de cortes usa esta medida)."),
        ("ancho", "Ancho hoja", "num", "Ancho de la hoja entera en mm."),
        ("densidad", "Densidad", "num", "kg/m³ de la placa, para el peso del case (fenólico ≈ 700, abedul ≈ 680, MDF ≈ 750)."),
        ("peso_hoja", "Peso hoja (kg)", "num", "Si el proveedor da el peso de la hoja entera en kg, ponelo acá en vez de la densidad."),
    ]),
    ("angulo", "Perfiles ángulo", [
        ("ala", "Ala", "num", "Ala del ángulo de aluminio en mm (30 = 30x30)."),
        ("esp", "Espesor", "num", "Espesor de la chapa del ángulo en mm."),
        ("peso_m", "Peso (g/m)", "num", "Gramos por metro de perfil, para el peso total del case (vacío = se estima)."),
    ]),
    ("hibrido", "Perfiles híbridos", [
        ("placa", "Para placa", "num", "Espesor de placa para el que está hecho el canal (mm)."),
        ("canal", "Canal", "num", "Profundidad del canal (mm)."),
        ("junta", "Junta", "num", "Alto de la junta macho/hembra (mm)."),
        ("ala_corta", "Ala corta", "num", "mm"),
        ("ala_larga", "Ala larga", "num", "mm"),
        ("pared", "Pared", "num", "Espesor de pared del aluminio (mm)."),
        ("peso_m", "Peso (g/m)", "num", "Gramos por metro de perfil, para el peso total del case (vacío = se estima)."),
    ]),
    ("tapa_m", "Perfil de tapa macho", [
        ("placa", "Para placa", "num", "Espesor de placa para el que está hecho (mm)."),
        ("canal", "Canal", "num", "Profundidad del canal (mm)."),
        ("peso_m", "Peso (g/m)", "num", "Gramos por metro de perfil, para el peso total del case (vacío = se estima)."),
    ]),
    ("tapa_h", "Perfil de tapa hembra", [
        ("placa", "Para placa", "num", "Espesor de placa para el que está hecho (mm)."),
        ("peso_m", "Peso (g/m)", "num", "Gramos por metro de perfil, para el peso total del case (vacío = se estima)."),
    ]),
    ("esquinero", "Esquineros", [
        ("pata", "Pata", "num", "Largo de cada pata desde la esquina (mm): cuánto se descuenta del perfil."),
        ("paso", "Paso de perfil", "num", "Paso para el perfil en mm (0 = sin paso)."),
        ("remaches", "Remaches", "num", "Remaches por esquinero."),
    ]),
    ("escuadra", "Escuadras", []),
    ("cierre", "Cierres", [
        ("tipo", "Tipo", ("superficie", "embutido"), "Superficie (se remacha encima) o embutido (mariposa: lleva calado)."),
        ("corte", "Calado", "par", "Calado en la placa, ancho x alto en mm (sólo embutidos)."),
        ("radio", "Radio", "num", "Radio de las esquinas del calado (mm)."),
        ("prof", "Profundidad", "num", "Profundidad de la cazoleta del cierre (mm)."),
        ("remaches", "Remaches", "num", "Remaches por cierre."),
    ]),
    ("bisagra", "Bisagras", [
        ("largo", "Largo", "num", "Bisagra de piano: largo del tramo (mm). Vacío = bisagra común."),
        ("remaches", "Remaches", "num", "Remaches por bisagra."),
    ]),
    ("tope", "Topes de tapa", [
        ("remaches", "Remaches", "num", "Remaches por tope."),
    ]),
    ("manija", "Manijas", [
        ("tipo", "Tipo", ("embutida", "superficie"), "Embutida (lleva calado) o de superficie."),
        ("exterior", "Exterior", "par", "Medida de afuera, ancho x alto en mm."),
        ("corte", "Calado", "par", "Calado en la placa, ancho x alto en mm (sólo embutidas)."),
        ("radio", "Radio", "num", "Radio de las esquinas del calado (mm)."),
        ("remaches", "Remaches", "num", "Remaches por manija."),
    ]),
    ("rueda", "Ruedas", [
        ("tipo", "Tipo", ("giratoria", "fija"), "Giratoria o fija."),
        ("diametro", "Diámetro", "num", "Diámetro de la rueda (mm)."),
        ("alto", "Alto total", "num", "Alto desde el piso hasta la placa de montaje (mm)."),
        ("placa", "Placa", "par", "Placa de montaje, largo x ancho en mm."),
        ("agujeros", "Agujeros", "par", "Distancia entre agujeros de la placa, largo x ancho en mm."),
        ("agujero_d", "Ø agujero", "num", "Diámetro de los agujeros de la placa (mm)."),
        ("freno", "Freno", "num", "0 = sin freno, 1 = freno de rueda, 2 = freno total (traba el giro)."),
    ]),
    ("rueda_otra", "Otras ruedas", []),
    ("cazoleta", "Cazoletas de rueda", [
        ("exterior", "Exterior", "par", "Medida de afuera del ala, ancho x largo en mm."),
        ("corte", "Calado", "par", "Calado en el piso, ancho x largo en mm."),
        ("radio", "Radio", "num", "Radio de las esquinas del calado (mm)."),
        ("prof", "Profundidad", "num", "Cuánto se mete hacia adentro (mm)."),
        ("remaches", "Remaches", "num", "Remaches por cazoleta."),
        ("placa_max", "Placa máx.", "par", "Placa de rueda más grande que entra, largo x ancho en mm."),
    ]),
    ("plato", "Platos de apilado", [
        ("exterior", "Exterior", "par", "Medida de afuera, ancho x largo en mm."),
        ("corte", "Calado", "par", "Calado en la tapa, ancho x largo en mm."),
        ("radio", "Radio", "num", "Radio de las esquinas del calado (mm)."),
        ("prof", "Profundidad", "num", "mm"),
        ("remaches", "Remaches", "num", "Remaches por plato."),
    ]),
    ("pie", "Pies", [
        ("diametro", "Diámetro", "num", "mm"),
        ("alto", "Alto", "num", "mm"),
    ]),
    ("remache", "Remaches", [
        ("d", "Diámetro", "num", "Diámetro del remache (mm)."),
        ("l", "Largo", "num", "Largo del remache (mm)."),
    ]),
    ("espuma", "Espumas", [
        ("esp", "Espesor", "num", "Espesor de la plancha (mm)."),
        ("densidad", "Densidad", "num", "kg/m³ de la espuma, para el peso del case (plastazote LD29 ≈ 29)."),
    ]),
    ("rack", "Rack", []),
    ("conector", "Conectores y energía", [
        ("forma", "Forma del calado", ("redondo", "rectangular"), "Redondo (conectores D: XLR, powerCON, etherCON…) o rectangular (IEC, pasacables)."),
        ("corte", "Calado", "par", "Calado en la placa, ancho x alto en mm (en uno redondo, el diámetro en los dos)."),
        ("radio", "Radio", "num", "Radio de las esquinas del calado rectangular (mm)."),
        ("brida", "Brida", "par", "Medida de la brida o tapa que queda por fuera, ancho x alto en mm."),
        ("tornillos", "Tornillos", "par", "Distancia entre los agujeros de los tornillos, ancho x alto en mm (vacío = sin tornillos, a presión)."),
        ("tornillos_n", "Cantidad de tornillos", "num", "2 (en diagonal, como los conectores D) o 4 (en las cuatro esquinas)."),
        ("tornillo_d", "Ø agujero tornillo", "num", "Diámetro del agujero para el tornillo (mm)."),
        ("fondo", "Fondo", "num", "Cuánto entra el conector hacia adentro del case, desde la cara de afuera (mm)."),
    ]),
    ("extra", "Accesorios", []),
]
_CON_PESO = ("esquinero", "escuadra", "cierre", "bisagra", "tope", "manija", "rueda", "rueda_otra", "cazoleta",
             "plato", "pie", "remache", "rack", "conector", "extra")
for _c, _n, _m in CATEGORIAS:
    if _c in _CON_PESO:
        _m.append(("peso", "Peso (g)", "num", "Peso de una unidad en gramos, para el peso total del case (pesala o sacala de la ficha del proveedor)."))
NOMBRES = {c: n for c, n, _ in CATEGORIAS}
MEDIDAS = {c: m for c, _, m in CATEGORIAS}

COLUMNAS_CSV = [("Ref", "ref"), ("Categoría", "categoria"), ("Nombre", "nombre"), ("Proveedor", "proveedor"),
                ("Verificado", "verificado"), ("Nota", "nota")]


# ---------------------------------------------------------------------------
# Leer y guardar
# ---------------------------------------------------------------------------

def incluido() -> List[Dict[str, Any]]:
    """El catálogo que viene con la app."""
    return json.loads(bundled_resource("catalogo_fr.json").read_text(encoding="utf-8"))


def _limpia(f: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fila válida (con ref, categoría y nombre) o None."""
    if not isinstance(f, dict):
        return None
    ref = str(f.get("ref") or "").strip()
    cat = str(f.get("categoria") or "").strip()
    if not ref or not cat:
        return None
    out = {"ref": ref, "categoria": cat, "nombre": str(f.get("nombre") or ref).strip(),
           "datos": dict(f.get("datos") or {}) if isinstance(f.get("datos"), dict) else {},
           "verificado": bool(f.get("verificado", True))}
    for k in ("proveedor", "nota"):
        if str(f.get(k) or "").strip():
            out[k] = str(f[k]).strip()
    return out


def cargar_propio() -> Tuple[List[Dict[str, Any]], List[str]]:
    """(artículos propios, refs incluidas ocultas) guardados por el usuario."""
    ruta = user_resource(ARCHIVO)
    if not ruta.is_file():
        return [], []
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], []
    if not isinstance(d, dict):
        return [], []
    arts = [f for f in (_limpia(x) for x in d.get("articulos") or []) if f]
    ocultos = [str(r) for r in d.get("ocultos") or [] if str(r).strip()]
    return arts, ocultos


def combinar(base: List[Dict[str, Any]], propios: Iterable[Dict[str, Any]],
             ocultos: Iterable[str]) -> List[Dict[str, Any]]:
    """El catálogo que usa la app: el incluido, con los propios encima y sin los ocultos.
    Cada fila lleva ``origen``: "incluido", "modificado" o "propio"."""
    ocultos = set(ocultos)
    propios = list(propios)
    por_ref = {f["ref"]: f for f in propios}
    out, vistos = [], set()
    for f in base:
        r = f["ref"]
        if r in vistos:
            continue
        vistos.add(r)
        if r in por_ref:
            out.append({**copy.deepcopy(por_ref[r]), "origen": "modificado"})
        elif r not in ocultos:
            out.append({**copy.deepcopy(f), "origen": "incluido"})
    for f in propios:
        if f["ref"] not in vistos:
            vistos.add(f["ref"])
            out.append({**copy.deepcopy(f), "origen": "propio"})
    return out


_cache: Dict[str, Any] = {"firma": None, "filas": None}


def _firma() -> Any:
    try:
        st = user_resource(ARCHIVO).stat()
        return (str(user_resource(ARCHIVO)), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(user_resource(ARCHIVO)), None)


def filas_actuales() -> List[Dict[str, Any]]:
    """Catálogo combinado; se vuelve a leer sólo si cambió catalogo_propio.json."""
    firma = _firma()
    if _cache["firma"] != firma or _cache["filas"] is None:
        arts, ocultos = cargar_propio()
        _cache["filas"] = combinar(incluido(), arts, ocultos)
        _cache["firma"] = firma
    return _cache["filas"]


def _igual(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return all(a.get(k) == b.get(k) for k in CAMPOS_FIJOS if k not in ("proveedor", "nota")) and \
        all((a.get(k) or "") == (b.get(k) or "") for k in ("proveedor", "nota"))


def diferencias(filas: Iterable[Dict[str, Any]],
                base: Optional[List[Dict[str, Any]]] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    """(propios, ocultos) que hacen falta guardar para que el catálogo quede como `filas`."""
    base = incluido() if base is None else base
    por_ref = {}
    for f in base:
        por_ref.setdefault(f["ref"], f)
    propios, refs = [], set()
    for f in filas:
        f = _limpia(f)
        if not f or f["ref"] in refs:
            continue
        refs.add(f["ref"])
        orig = por_ref.get(f["ref"])
        if orig is None or not _igual(f, orig):
            propios.append(f)
    ocultos = [r for r in por_ref if r not in refs]
    return propios, ocultos


def guardar(filas: Iterable[Dict[str, Any]]) -> None:
    """Guarda el catálogo completo (sólo lo que difiere del incluido)."""
    propios, ocultos = diferencias(filas)
    ruta = user_resource(ARCHIVO)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"articulos": propios, "ocultos": ocultos}, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    _cache["firma"] = None


def marcar_origen(filas: List[Dict[str, Any]], base: Optional[List[Dict[str, Any]]] = None) -> None:
    """Pone a cada fila su ``origen`` comparándola con el catálogo incluido."""
    base = incluido() if base is None else base
    por_ref = {}
    for f in base:
        por_ref.setdefault(f["ref"], f)
    for f in filas:
        orig = por_ref.get(f["ref"])
        f["origen"] = "propio" if orig is None else ("incluido" if _igual(f, orig) else "modificado")


def ocultos_incluidos(filas: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Artículos que vienen con la app y no están en `filas` (los que el usuario quitó)."""
    refs = {f["ref"] for f in filas}
    out, vistos = [], set()
    for f in incluido():
        if f["ref"] not in refs and f["ref"] not in vistos:
            vistos.add(f["ref"])
            out.append({**f, "origen": "incluido"})
    return out


def ref_libre(filas: Iterable[Dict[str, Any]], base: str) -> str:
    refs = {f["ref"] for f in filas}
    if base not in refs:
        return base
    n = 2
    while f"{base}-{n}" in refs:
        n += 1
    return f"{base}-{n}"


def original(ref: str) -> Optional[Dict[str, Any]]:
    """La fila tal como viene con la app (para «Restaurar»)."""
    f = next((x for x in incluido() if x["ref"] == ref), None)
    return {**f, "origen": "incluido"} if f else None


# ---------------------------------------------------------------------------
# Valores de las medidas (texto <-> dato)
# ---------------------------------------------------------------------------

def _num(t: str) -> float:
    v = float(t.strip().replace(",", "."))
    return int(v) if v.is_integer() else v


def texto_valor(v: Any) -> str:
    """Medida para mostrar o exportar: 9,6 · 100 x 85 · embutido."""
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, (int, float)):
        t = f"{v:.3f}".rstrip("0").rstrip(".")
        return t.replace(".", ",")
    if isinstance(v, (list, tuple)):
        return " x ".join(texto_valor(x) for x in v)
    return "" if v is None else str(v)


_SEP_PAR = re.compile(r"\s*[x×X*;]\s*|,\s+|\s+")


def valor_texto(t: str, tipo: Any = None) -> Any:
    """Medida escrita a mano o leída de la planilla. Vacío = None (sin dato).
    Error (ValueError) si no se entiende para ese tipo."""
    t = str(t or "").strip()
    if not t:
        return None
    if isinstance(tipo, tuple):
        if t.lower() not in tipo:
            raise ValueError(f"«{t}» no es una opción ({', '.join(tipo)})")
        return t.lower()
    if tipo == "texto":
        return t
    s_ = t.strip("[]() ")
    partes = [p for p in _SEP_PAR.split(s_) if p]
    if tipo == "par" and len(partes) == 1 and s_.count(",") == 1:     # «100,85» en una lista
        partes = s_.split(",")
    if tipo == "par" or len(partes) > 1:
        try:
            nums = [_num(p) for p in partes]
        except ValueError:
            if tipo in ("par", "num"):
                raise ValueError(f"«{t}» no son dos medidas (escribí por ejemplo 100 x 85)")
            return t
        if tipo == "par" and len(nums) != 2:
            raise ValueError(f"«{t}» no son dos medidas (escribí por ejemplo 100 x 85)")
        return nums
    try:
        return _num(t)
    except ValueError:
        if tipo == "num":
            raise ValueError(f"«{t}» no es un número")
        return t


def tipo_medida(categoria: str, clave: str) -> Any:
    for k, _t, tipo, _a in MEDIDAS.get(categoria, []):
        if k == clave:
            return tipo
    return None


def claves_medidas(filas: Iterable[Dict[str, Any]], categoria: Optional[str] = None) -> List[str]:
    """Las medidas de esas filas: primero las conocidas de la categoría, después las demás."""
    filas = list(filas)
    orden: List[str] = []
    cats = [categoria] if categoria else [c for c, _, _ in CATEGORIAS]
    for c in cats:
        for k, *_ in MEDIDAS.get(c, []):
            if k not in orden and (categoria or any(k in f.get("datos", {}) for f in filas)):
                orden.append(k)
    for f in filas:
        for k in f.get("datos", {}):
            if k not in orden:
                orden.append(k)
    return orden


def resumen_datos(f: Dict[str, Any]) -> str:
    titulos = {k: t for k, t, *_ in MEDIDAS.get(f.get("categoria", ""), [])}
    return ", ".join(f"{titulos.get(k, k)}: {texto_valor(v)}" for k, v in f.get("datos", {}).items())


# ---------------------------------------------------------------------------
# Planilla CSV
# ---------------------------------------------------------------------------

def a_csv(filas: Iterable[Dict[str, Any]]) -> str:
    """Una fila por artículo; las medidas, una columna cada una con su clave (esp, largo, placa…)."""
    filas = list(filas)
    medidas = claves_medidas(filas)
    salida = io.StringIO()
    w = csv.writer(salida, delimiter=";", lineterminator="\n")
    w.writerow([t for t, _ in COLUMNAS_CSV] + medidas)
    for f in filas:
        fila = []
        for _, c in COLUMNAS_CSV:
            v = f.get(c, "")
            fila.append(("sí" if v else "no") if c == "verificado" else str(v or ""))
        fila += [texto_valor(f.get("datos", {}).get(k)) for k in medidas]
        w.writerow(fila)
    return salida.getvalue()


_SI = {"si", "sí", "s", "yes", "y", "true", "verdadero", "1", "x"}
_NO = {"no", "n", "false", "falso", "0", ""}
_ALIAS_CATEGORIA = {n.lower(): c for c, n, _ in CATEGORIAS}
_ALIAS_CATEGORIA.update({"placas": "placa", "herraje": "extra", "accesorio": "extra", "perfil": "angulo",
                         "angulos": "angulo", "ángulo": "angulo", "híbrido": "hibrido", "cantonera": "esquinero",
                         "cantoneras": "esquinero", "asa": "manija", "asas": "manija", "cierre": "cierre",
                         "ruedas": "rueda", "tablero": "placa", "tableros": "placa"})


def categoria_de_texto(t: str) -> str:
    """Clave de categoría a partir de la clave o del nombre (Placas, ruedas…); "" si no existe."""
    t = str(t or "").strip().lower()
    for cand in (t, t.rstrip("s"), t[:-2] if t.endswith("es") else t):
        if cand in NOMBRES:
            return cand
        if cand in _ALIAS_CATEGORIA:
            return _ALIAS_CATEGORIA[cand]
    return ""


def desde_csv(texto: str, actuales: Optional[List[Dict[str, Any]]] = None
              ) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Lee una planilla (con los encabezados de a_csv, sin importar mayúsculas ni el orden).

    Devuelve (filas, avisos). Si la ref ya está en `actuales`, la fila parte de ese artículo y
    las celdas vacías no cambian nada (así alcanza una planilla con ref y las medidas nuevas).
    Las columnas que no son fijas son medidas (esp, largo, placa…)."""
    texto = texto.lstrip("﻿")
    primera = texto.splitlines()[0] if texto.strip() else ""
    delim = ";" if primera.count(";") >= primera.count(",") else ("\t" if "\t" in primera else ",")
    filas = list(csv.reader(io.StringIO(texto), delimiter=delim))
    if not filas:
        return [], []
    por_titulo = {t.lower(): c for t, c in COLUMNAS_CSV}
    por_titulo.update({c: c for _, c in COLUMNAS_CSV})
    por_titulo.update({"categoria": "categoria", "referencia": "ref", "código": "ref", "codigo": "ref",
                       "descripción": "nombre", "descripcion": "nombre", "verificada": "verificado"})
    cols: List[Tuple[str, str]] = []
    for h in filas[0]:
        h = h.strip()
        cols.append(("fijo", por_titulo[h.lower()]) if h.lower() in por_titulo else ("dato", h))
    if ("fijo", "ref") not in cols:
        raise ValueError("la planilla no tiene la columna Ref")
    previas = {f["ref"]: f for f in actuales or []}
    out, avisos, vistas = [], [], set()
    for n, fila in enumerate(filas[1:], start=2):
        celdas = {}
        for (clase, clave), v in zip(cols, fila):
            celdas[(clase, clave)] = v.strip()
        ref = celdas.get(("fijo", "ref"), "")
        if not ref:
            continue
        if ref in vistas:
            avisos.append(f"Fila {n}: la ref {ref} está repetida; quedó la primera.")
            continue
        prev = previas.get(ref)
        f = copy.deepcopy(prev) if prev else {"ref": ref, "categoria": "", "nombre": "", "datos": {},
                                              "verificado": True}
        f.pop("origen", None)
        if celdas.get(("fijo", "categoria")):
            cat = categoria_de_texto(celdas[("fijo", "categoria")])
            if not cat:
                avisos.append(f"Fila {n} ({ref}): la categoría «{celdas[('fijo', 'categoria')]}» no existe; "
                              "no se importó.")
                continue
            f["categoria"] = cat
        if not f["categoria"]:
            avisos.append(f"Fila {n} ({ref}): falta la categoría; no se importó.")
            continue
        for k in ("nombre", "proveedor", "nota"):
            if celdas.get(("fijo", k)):
                f[k] = celdas[("fijo", k)]
        if not f.get("nombre"):
            f["nombre"] = ref
        ver = celdas.get(("fijo", "verificado"))
        if ver is not None and ver != "":
            if ver.lower() in _SI:
                f["verificado"] = True
            elif ver.lower() in _NO:
                f["verificado"] = False
        else:
            f["verificado"] = True     # medidas del proveedor real
        malas = []
        for (clase, clave), v in celdas.items():
            if clase != "dato" or not clave or v == "":
                continue
            try:
                f["datos"][clave] = valor_texto(v, tipo_medida(f["categoria"], clave))
            except ValueError as e:
                malas.append(f"{clave}: {e}")
        if malas:
            avisos.append(f"Fila {n} ({ref}): " + "; ".join(malas) + ". Esas medidas no se cambiaron.")
        vistas.add(ref)
        out.append(f)
    return out, avisos


def sumar(filas: List[Dict[str, Any]], nuevas: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
    """Agrega o reemplaza (por ref). Devuelve (agregadas, actualizadas)."""
    idx = {f["ref"]: i for i, f in enumerate(filas)}
    agregadas = actualizadas = 0
    for n in nuevas:
        if n["ref"] in idx:
            origen = filas[idx[n["ref"]]].get("origen", "propio")
            filas[idx[n["ref"]]] = {**n, "origen": "propio" if origen == "propio" else "modificado"}
            actualizadas += 1
        else:
            idx[n["ref"]] = len(filas)
            filas.append({**n, "origen": "propio"})
            agregadas += 1
    return agregadas, actualizadas
