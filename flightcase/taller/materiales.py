"""Material y espesor distinto por panel (no está en flightcase.scad).

El parámetro `paneles_material` es una lista de filas `[panel, placa, espesor, material]`:

- panel: el id de un panel ("techo", "cuerpo_izq"...) o un grupo entero ("cuerpo", "tapa",
  "tapa2"). Las filas se aplican en orden, así que una fila de un panel suelto puede corregir
  a la de su grupo.
- placa: referencia de una placa del catálogo (da material, espesor y medida de la placa
  entera). Vacío = sin catálogo.
- espesor: mm; 0 = el de la placa elegida o, sin placa, el de la placa general.
- material: nombre a mano; vacío = el de la placa elegida o "Placa <esp> mm".

Las medidas exteriores no cambian: el panel conserva la cara de afuera en su lugar y el
espesor de más (o de menos) se gana o se pierde hacia adentro. En el sistema de ángulo los
paneles que apoyan contra él se acortan (o alargan) esa diferencia y los calados y marcas
quedan en el mismo lugar del case. En el híbrido ningún panel toca a otro, así que sólo
cambia el espesor de la pieza.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

GRUPOS = {"cuerpo": "Todo el cuerpo", "tapa": "Toda la tapa", "tapa2": "Toda la segunda tapa"}
EXCLUIDOS_PREFIJO = ("base_ruedas", "bandeja")      # tienen su propio material


@dataclass
class MaterialPanel:
    material: str
    esp: float
    largo: float
    ancho: float
    ref: str = ""


def _num(v: Any, defecto: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return defecto


def filas(P: Dict[str, Any]) -> List[list]:
    out = []
    for f in P.get("paneles_material") or []:
        if isinstance(f, list) and f and isinstance(f[0], str) and f[0].strip():
            out.append(list(f) + [None] * (4 - len(f)))
    return out


def resolver_fila(fila: list, cat, general: MaterialPanel) -> MaterialPanel:
    """Material efectivo de una fila de `paneles_material`."""
    ref = str(fila[1] or "").strip()
    esp_fila = _num(fila[2])
    mat_fila = str(fila[3] or "").strip()
    con_cat = cat.existe(ref)
    esp = esp_fila if esp_fila > 0 else (cat.dato(ref, "esp", general.esp) if con_cat else general.esp)
    if mat_fila:
        mat = mat_fila
    elif con_cat:
        mat = cat.nombre(ref)
        if esp_fila > 0 and abs(esp_fila - cat.dato(ref, "esp", esp_fila)) > 0.01:
            mat = f"{mat} ({_f(esp)} mm)"
    elif abs(esp - general.esp) > 0.01:
        mat = f"Placa {_f(esp)} mm"
    else:
        mat = general.material
    if mat == general.material and abs(esp - general.esp) > 0.01:
        mat = f"{mat} ({_f(esp)} mm)"       # que no se mezcle con la placa general
    largo = cat.dato(ref, "largo", general.largo) if con_cat else general.largo
    ancho = cat.dato(ref, "ancho", general.ancho) if con_cat else general.ancho
    return MaterialPanel(mat, float(esp), float(largo), float(ancho), ref if con_cat else "")


def _f(v: float) -> str:
    return f"{float(v):.1f}".rstrip("0").rstrip(".")


def asignar(P: Dict[str, Any], cat, paneles: Iterable, general: MaterialPanel) -> Dict[str, MaterialPanel]:
    """Material de cada panel que no usa el general (panel id -> MaterialPanel)."""
    grupos: Dict[str, List[str]] = {}
    ids = []
    for p in paneles:
        if p.id.startswith(EXCLUIDOS_PREFIJO):
            continue
        ids.append(p.id)
        grupos.setdefault(p.grupo, []).append(p.id)
    out: Dict[str, MaterialPanel] = {}
    for fila in filas(P):
        clave = fila[0].strip()
        destino = grupos.get(clave, []) if clave in GRUPOS else ([clave] if clave in ids else [])
        m = resolver_fila(fila, cat, general)
        for pid in destino:
            out[pid] = m
    return {k: m for k, m in out.items()
            if m.material != general.material or abs(m.esp - general.esp) > 0.01}


def espesor_maximo(P: Dict[str, Any], cat, general: MaterialPanel) -> float:
    return max([general.esp] + [resolver_fila(f, cat, general).esp for f in filas(P)])


def claves_desconocidas(P: Dict[str, Any], paneles: Iterable) -> List[str]:
    ids = {p.id for p in paneles}
    return [f[0].strip() for f in filas(P) if f[0].strip() not in GRUPOS and f[0].strip() not in ids]


# ---------------------------------------------------------------------------
# Ajuste de cortes y ubicaciones por el espesor de los vecinos
# ---------------------------------------------------------------------------

def ajustar(paneles, colocaciones: List[dict], calados, marcas, esp_de, t: float, k: Dict[str, Any]) -> Dict[str, tuple]:
    """Corrige medidas y ubicación de los paneles cuando un vecino tiene otro espesor.

    `esp_de(pid)` da el espesor de cada panel y `k` trae las banderas de la construcción
    (hibrido, fe, fec, ce, dos_tapas, acceso). Devuelve, por panel, el corrimiento (du, dv)
    de su esquina local, que ya se descontó de sus calados y marcas."""
    for c in colocaciones:
        c["esp"] = esp_de(c["id"])
    if k["hibrido"]:
        return {}
    por_id = {p.id: p for p in paneles}
    col = {c["id"]: c for c in colocaciones}
    d = (lambda pid: esp_de(pid) - t if pid in por_id else 0.0)
    corr: Dict[str, List[float]] = {}     # pid -> [du, dv, dancho, dalto]

    def mover(pid, du=0.0, dv=0.0, dw=0.0, dh=0.0):
        if pid not in por_id:
            return
        c = corr.setdefault(pid, [0.0, 0.0, 0.0, 0.0])
        c[0] += du; c[1] += dv; c[2] += dw; c[3] += dh

    for pre, fe in (("cuerpo", k["fec"]), ("tapa", k["fe"]), ("tapa2", k["fe"])):
        fr, tr = f"{pre}_frente", f"{pre}_trasera"
        acc = pre == "cuerpo" and k["acceso"]
        # laterales: la pieza de adelante y la de atrás de cada costado (con acceso son dos)
        izq_del, izq_tr = f"{pre}_izq", ("acceso_izq" if acc else f"{pre}_izq")
        der_del, der_tr = f"{pre}_der", ("acceso_der" if acc else f"{pre}_der")
        if fe:   # frente y trasera de punta a punta: los laterales van entre ellos
            # izq arranca atrás (u = -Y), der arranca adelante (u = +Y)
            mover(izq_tr, du=d(tr), dw=-d(tr))
            mover(izq_del, dw=-d(fr))
            mover(der_del, du=d(fr), dw=-d(fr))
            mover(der_tr, dw=-d(tr))
        else:    # laterales enteros: frente y trasera entre ellos
            mover(fr, du=d(izq_del), dw=-d(izq_del) - d(der_del))
            mover(tr, du=d(der_tr), dw=-d(der_tr) - d(izq_tr))
        # alto de las paredes: con extremos que cubren, el piso / techo tapa sus cantos
        if k["ce"] > 0:
            paredes = [p.id for p in paneles if p.grupo == pre and p.id not in ("piso", "techo", "base2")
                       and not p.id.startswith(EXCLUIDOS_PREFIJO)]
            if pre == "cuerpo" and not k["dos_tapas"]:
                for pid in paredes:
                    mover(pid, dv=d("piso"), dh=-d("piso"))
            elif pre == "tapa":
                for pid in paredes:
                    mover(pid, dh=-d("techo"))
            elif pre == "tapa2":
                for pid in paredes:
                    mover(pid, dv=d("base2"), dh=-d("base2"))
    # piso, techo y fondo adentro de las paredes (sin extremos que cubren)
    if k["ce"] <= 0:
        for pid, pre in (("piso", "cuerpo"), ("techo", "tapa"), ("base2", "tapa2")):
            acc = pre == "cuerpo" and k["acceso"]
            izq = max(d(f"{pre}_izq"), d("acceso_izq") if acc else -1e9)
            der = max(d(f"{pre}_der"), d("acceso_der") if acc else -1e9)
            mover(pid, du=izq, dv=d(f"{pre}_frente"), dw=-izq - der, dh=-d(f"{pre}_frente") - d(f"{pre}_trasera"))

    desplaz: Dict[str, tuple] = {}
    for pid, (du, dv, dw, dh) in corr.items():
        if max(abs(du), abs(dv), abs(dw), abs(dh)) < 1e-9:
            continue
        p = por_id[pid]
        p.ancho += dw
        p.alto += dh
        c = col.get(pid)
        if c is not None:
            c["o"] = tuple(c["o"][i] + c["u"][i] * du + c["v"][i] * dv for i in range(3))
        for x in calados:
            if x.panel == pid:
                x.cx -= du; x.cy -= dv
        for m in marcas:
            if m.panel == pid:
                m.x -= du; m.y -= dv
        desplaz[pid] = (du, dv)
    return desplaz


def nombre_clave(clave: str, nombres: Dict[str, str]) -> str:
    return GRUPOS.get(clave) or nombres.get(clave, clave)


def lista_avisos(asignados: Dict[str, MaterialPanel], paneles, t: float, hib: bool, cat,
                 refs_perfil: List[str], general: MaterialPanel) -> List[str]:
    """Un aviso por espesor distinto (no uno por panel)."""
    out = []
    nombres = {p.id: p.nombre for p in paneles}
    por_esp: Dict[float, List[str]] = {}
    for pid, m in asignados.items():
        if abs(m.esp - t) >= 0.01:
            por_esp.setdefault(round(m.esp, 2), []).append(nombres.get(pid, pid))
    perf = [r for r in refs_perfil if cat.existe(r) and cat.dato(r, "placa", 0)]
    for esp, noms in por_esp.items():
        quien = noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " y " + noms[-1]
        verbo = "es" if len(noms) == 1 else "son"
        dif = esp - t
        if dif > 0:
            out.append(f"{quien} {verbo} de {_f(esp)} mm (la placa general es de {_f(t)}): las medidas de afuera "
                       f"no cambian, el interior pierde {_f(dif)} mm de ese lado.")
        for r in perf:
            if abs(cat.dato(r, "placa", esp) - esp) > 0.3:
                out.append(f"{quien} {verbo} de {_f(esp)} mm y el perfil {r} es para placa de "
                           f"{_f(cat.dato(r, 'placa', 0))} mm: verificá que entre en el canal.")
    return out


def opciones_panel(paneles) -> List[tuple]:
    """(clave, nombre) para elegir en la tabla: grupos primero, después cada panel."""
    grupos = []
    vistos = set()
    for p in paneles:
        if p.grupo in GRUPOS and p.grupo not in vistos:
            vistos.add(p.grupo)
            grupos.append((p.grupo, GRUPOS[p.grupo]))
    return grupos + [(p.id, p.nombre) for p in paneles if not p.id.startswith(EXCLUIDOS_PREFIJO)]


def sin_otro(asignados: Optional[Dict[str, MaterialPanel]]) -> bool:
    return not asignados
