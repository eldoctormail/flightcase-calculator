# -*- mode: python ; coding: utf-8 -*-
# Empaquetado con PyInstaller para Windows y macOS.
#   pyinstaller packaging/flightcase.spec --noconfirm
import os
import sys
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
APP_NAME = "Flightcase Calculator"
VERSION = os.environ.get("APP_VERSION", "0.1.0")
ICONO = os.path.join(ROOT, "packaging", "icono")   # se regeneran con tools/generar_icono.py

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "flightcase", "resources"), os.path.join("flightcase", "resources"))],
    # PyOpenGL carga sus módulos de plataforma de forma dinámica
    hiddenimports=collect_submodules("OpenGL.platform") + collect_submodules("OpenGL.arrays")
    + ["matplotlib.backends.backend_agg", "matplotlib.backends.backend_pdf"],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    upx=False,
    icon=os.path.join(ICONO, "icono.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=os.path.join(ICONO, "icono.icns"),
        bundle_identifier="com.eldoctormail.flightcasecalculator",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Proyecto de flightcase",
                "CFBundleTypeExtensions": ["fcproj"],
                "CFBundleTypeRole": "Editor",
            }],
        },
    )
