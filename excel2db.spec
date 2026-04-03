# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

# Collect all app submodules so PyInstaller finds them
hiddenimports = (
    collect_submodules("app")
    + collect_submodules("app.routes")
    + collect_submodules("app.services")
    + collect_submodules("app.models")
    + ["uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
       "uvicorn.protocols", "uvicorn.protocols.http",
       "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
       "uvicorn.protocols.websockets",
       "uvicorn.protocols.websockets.auto",
       "uvicorn.lifespan", "uvicorn.lifespan.on",
       "multipart", "multipart.multipart"]
)

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("app/templates", "app/templates"),
        ("app/static", "app/static"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Excel2DB",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)
