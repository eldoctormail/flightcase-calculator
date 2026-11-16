"""Actualizaciones: busca una versión nueva en las Releases de GitHub, la descarga y la instala.

Sin Qt, para poder probarlo solo. La ventana (flightcase/ui/actualizador.py) lo usa así:

    nueva = buscar(version())             # None si ya está al día
    archivo = descargar(nueva, carpeta, progreso)
    preparar_instalacion(archivo)         # deja todo listo; la app se cierra y se instala sola

Cómo se instala, según el sistema:

* Windows: se corre el instalador de Inno Setup en modo silencioso (/SILENT, con barra de
  progreso) cuando la app ya se cerró, y al terminar vuelve a abrir la app (/RELANZAR=1).
  Windows pide permiso de administrador (UAC) porque se instala en Archivos de programa.
* macOS: se monta el .dmg, se copia la app nueva al lado de la actual y, cuando la app se
  cierra, se reemplaza y se vuelve a abrir. Si la app no está en una carpeta donde se pueda
  escribir (por ejemplo, se abrió desde el .dmg o desde Descargas sin moverla), se abre
  el .dmg para arrastrarla a mano.

Como las apps no están firmadas: lo que baja la propia app no lleva la marca de
«descargado de internet», así que ni SmartScreen ni Gatekeeper la frenan. Igual se le
quita la marca de cuarentena a la app nueva en macOS por las dudas.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

REPO = "eldoctormail/flightcase-calculator"
URL_ULTIMA = f"https://api.github.com/repos/{REPO}/releases/latest"
URL_RELEASES = f"https://github.com/{REPO}/releases"
NOMBRE_APP = "LBD Flightcase Maker"


class ErrorActualizacion(Exception):
    """Algo salió mal al buscar, bajar o instalar; el mensaje es para mostrarlo tal cual."""


@dataclass
class Novedad:
    version: str            # "0.4.0"
    notas: str              # texto de la Release (markdown)
    pagina: str             # página de la Release en GitHub
    archivo: str = ""       # nombre del instalador para este sistema ("" si no hay)
    url: str = ""
    tamano: int = 0         # bytes

    @property
    def instalable(self) -> bool:
        return bool(self.url)


# ----------------------------------------------------------------- versiones
def numeros(v: str) -> Tuple[int, ...]:
    """'v0.3.10' → (0, 3, 10). Lo que no es número se ignora ('0.4.0-beta' → (0, 4, 0))."""
    v = v.strip().lstrip("vV")
    partes = []
    for p in v.split("."):
        m = re.match(r"\d+", p)
        if not m:
            break
        partes.append(int(m.group()))
    while len(partes) > 1 and partes[-1] == 0:      # 0.3 == 0.3.0
        partes.pop()
    return tuple(partes)


def es_mas_nueva(candidata: str, actual: str) -> bool:
    c, a = numeros(candidata), numeros(actual)
    return bool(c) and (not a or c > a)


def es_app_instalada() -> bool:
    """True en la app empaquetada (PyInstaller); False al correr desde el código."""
    return bool(getattr(sys, "frozen", False))


# ------------------------------------------------------------------ elegir
def sufijo_instalador(sistema: str = sys.platform, maquina: Optional[str] = None) -> Optional[str]:
    """Final del nombre del instalador que sirve en esta computadora (None: no hay)."""
    if sistema == "win32":
        return "-Windows-Instalador.exe"
    if sistema == "darwin":
        maquina = (maquina or platform.machine()).lower()
        return "-macOS-AppleSilicon.dmg" if maquina in ("arm64", "aarch64") else "-macOS-Intel.dmg"
    return None


def novedad_desde_release(release: dict, sistema: str = sys.platform, maquina: Optional[str] = None) -> Novedad:
    n = Novedad(version=(release.get("tag_name") or "").strip().lstrip("vV"),
                notas=(release.get("body") or "").strip(),
                pagina=release.get("html_url") or URL_RELEASES)
    sufijo = sufijo_instalador(sistema, maquina)
    if sufijo:
        for a in release.get("assets") or []:
            if a.get("name", "").endswith(sufijo):
                n.archivo, n.url, n.tamano = a["name"], a["browser_download_url"], int(a.get("size") or 0)
                break
    return n


# ------------------------------------------------------------------ red
def _contexto_ssl() -> ssl.SSLContext:
    """En la app empaquetada de Mac, Python no ve los certificados del sistema: se usa certifi."""
    if not os.environ.get("SSL_CERT_FILE"):
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


def _abrir(url: str, timeout: float):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"{NOMBRE_APP.replace(' ', '')}-actualizador",
        "Accept": "application/vnd.github+json" if "api.github.com" in url else "*/*",
    })
    return urllib.request.urlopen(req, timeout=timeout, context=_contexto_ssl())


def buscar(version_actual: str, timeout: float = 10) -> Optional[Novedad]:
    """La última Release si es más nueva que version_actual; None si ya está al día."""
    try:
        with _abrir(URL_ULTIMA, timeout) as r:
            release = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise ErrorActualizacion(f"No se pudo consultar GitHub: {e}") from e
    if release.get("draft") or release.get("prerelease"):
        return None
    n = novedad_desde_release(release)
    return n if es_mas_nueva(n.version, version_actual) else None


def descargar(n: Novedad, carpeta: Optional[Path] = None,
              progreso: Optional[Callable[[int, int], bool]] = None, timeout: float = 30) -> Path:
    """Baja el instalador. progreso(bajado, total) devuelve False para cancelar."""
    if not n.instalable:
        raise ErrorActualizacion("Esta versión no trae instalador para esta computadora.")
    carpeta = Path(carpeta or tempfile.mkdtemp(prefix="lbd-actualizacion-"))
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / n.archivo
    parcial = destino.with_name(destino.name + ".parcial")
    try:
        with _abrir(n.url, timeout) as r, open(parcial, "wb") as f:
            total = int(r.headers.get("Content-Length") or n.tamano or 0)
            bajado = 0
            while True:
                bloque = r.read(256 * 1024)
                if not bloque:
                    break
                f.write(bloque)
                bajado += len(bloque)
                if progreso and progreso(bajado, total) is False:
                    raise ErrorActualizacion("Descarga cancelada.")
        if total and bajado != total:
            raise ErrorActualizacion(f"La descarga quedó incompleta ({bajado} de {total} bytes).")
        os.replace(parcial, destino)
        return destino
    except ErrorActualizacion:
        parcial.unlink(missing_ok=True)
        raise
    except Exception as e:
        parcial.unlink(missing_ok=True)
        raise ErrorActualizacion(f"No se pudo descargar {n.archivo}: {e}") from e


# ---------------------------------------------------------------- instalar
@dataclass
class Instalacion:
    """Lo que hay que lanzar justo antes de cerrar la app."""
    comando: list            # proceso que espera a que la app se cierre e instala
    manual: bool = False     # True: solo se abrió el .dmg, hay que arrastrar la app a mano
    mensaje: str = ""


def bundle_actual(ejecutable: str = sys.executable) -> Optional[Path]:
    """En Mac, la carpeta «LBD Flightcase Maker.app» que se está usando."""
    p = Path(ejecutable).resolve()
    for padre in p.parents:
        if padre.suffix == ".app":
            return padre
    return None


def _ps(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def comando_windows(instalador: Path, pid: int, app: str = sys.executable) -> list:
    """PowerShell oculto: espera a que se cierre la app y corre el instalador (pide UAC).

    Si no se da el permiso de administrador, vuelve a abrir la app de antes."""
    args = "'/SILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS','/RELANZAR=1'"
    script = (f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue; "
              f"try {{ Start-Process -FilePath {_ps(str(instalador))} -ArgumentList {args} -ErrorAction Stop }} "
              f"catch {{ Start-Process -FilePath {_ps(app)} }}")
    return ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script]


def guion_mac(nueva: Path, actual: Path, pid: int, punto_montaje: Optional[Path]) -> str:
    """Script de shell: espera a que se cierre la app, la reemplaza por la nueva y la abre."""
    q = shlex.quote
    vieja = actual.with_name(f".{actual.stem}-vieja.app")
    desmontar = f"hdiutil detach {q(str(punto_montaje))} -quiet || true\n" if punto_montaje else ""
    return (
        "#!/bin/sh\n"
        f"while kill -0 {pid} 2>/dev/null; do sleep 0.5; done\n"
        f"rm -rf {q(str(vieja))}\n"
        f"mv {q(str(actual))} {q(str(vieja))} && mv {q(str(nueva))} {q(str(actual))} "
        f"|| {{ [ -d {q(str(actual))} ] || mv {q(str(vieja))} {q(str(actual))}; }}\n"
        f"xattr -dr com.apple.quarantine {q(str(actual))} 2>/dev/null || true\n"
        f"rm -rf {q(str(vieja))} {q(str(nueva))}\n"
        f"{desmontar}"
        f"open {q(str(actual))}\n"
    )


def _montar_dmg(dmg: Path) -> Path:
    punto = Path(tempfile.mkdtemp(prefix="lbd-dmg-"))
    r = subprocess.run(["hdiutil", "attach", str(dmg), "-nobrowse", "-noautoopen", "-readonly",
                        "-mountpoint", str(punto)], capture_output=True, text=True)
    if r.returncode != 0:
        raise ErrorActualizacion(f"No se pudo abrir {dmg.name}: {r.stderr.strip() or r.stdout.strip()}")
    return punto


def _se_puede_reemplazar(app: Optional[Path]) -> bool:
    if app is None:
        return False
    s = str(app)
    if "/AppTranslocation/" in s or s.startswith("/Volumes/"):   # abierta desde el .dmg o sin mover
        return False
    return os.access(app.parent, os.W_OK)


def preparar_mac(dmg: Path, pid: int, app: Optional[Path] = None) -> Instalacion:
    app = app or bundle_actual()
    if not _se_puede_reemplazar(app):
        return Instalacion(["open", str(dmg)], manual=True, mensaje=(
            "Se abrió la versión nueva. Arrastrá «LBD Flightcase Maker» a la carpeta Aplicaciones "
            "y reemplazá la anterior.\n\nPara que la próxima vez se actualice sola, usá la app "
            "desde Aplicaciones (no desde el .dmg ni desde Descargas)."))
    punto = _montar_dmg(dmg)
    try:
        origen = next(punto.glob("*.app"))
    except StopIteration:
        subprocess.run(["hdiutil", "detach", str(punto), "-quiet"])
        raise ErrorActualizacion(f"{dmg.name} no tiene la app adentro.")
    nueva = app.with_name(f".{app.stem}-nueva.app")
    subprocess.run(["rm", "-rf", str(nueva)])
    r = subprocess.run(["ditto", str(origen), str(nueva)], capture_output=True, text=True)
    subprocess.run(["hdiutil", "detach", str(punto), "-quiet"])
    if r.returncode != 0:
        subprocess.run(["rm", "-rf", str(nueva)])
        raise ErrorActualizacion(f"No se pudo copiar la app nueva: {r.stderr.strip()}")
    guion = Path(tempfile.mkdtemp(prefix="lbd-act-")) / "actualizar.sh"
    guion.write_text(guion_mac(nueva, app, pid, None), encoding="utf-8")
    guion.chmod(0o755)
    return Instalacion(["/bin/sh", str(guion)])


def preparar_instalacion(archivo: Path, pid: Optional[int] = None) -> Instalacion:
    pid = pid or os.getpid()
    if sys.platform == "win32":
        return Instalacion(comando_windows(archivo, pid))
    if sys.platform == "darwin":
        return preparar_mac(archivo, pid)
    raise ErrorActualizacion("La instalación automática solo está disponible en Windows y Mac.")


def lanzar(inst: Instalacion) -> None:
    """Arranca el proceso que instala, separado de la app (sigue vivo cuando la app se cierra)."""
    if sys.platform == "win32":
        flags = 0x08000000 | 0x00000200      # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(inst.comando, creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(inst.comando, start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
