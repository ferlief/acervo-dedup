# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one folder, two binaries.

  acervo-dedup-gui.exe   windowed  double-click target, opens the interface
  acervo-dedup.exe       console   the engine; the window drives it and reads
                                   its stdout for the live log

They share one MERGE'd dependency tree, so the folder holds a single copy of
Python, PyYAML and the WebView2 glue instead of two.

onedir, not onefile, on purpose: the window spawns the CLI binary once per
scan, and a onefile build would re-extract the whole bundle to a temp folder
on every spawn - seconds of latency and a disk write, per run, for nothing.
"""

from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, MERGE, PYZ
from PyInstaller.building.build_main import Analysis

RAIZ = Path(SPECPATH).parent
ESTATICOS = RAIZ / "src" / "acervo_dedup" / "gui" / "static"

COMUM = dict(
    pathex=[str(RAIZ / "src")],
    # The interface's HTML/CSS/JS is data, not code: without this the frozen
    # build serves 404 for every asset.
    datas=[(str(ESTATICOS), "acervo_dedup/gui/static")],
    hiddenimports=["acervo_dedup.gui", "acervo_dedup.gui.desktop"],
    excludes=["tkinter", "unittest", "pydoc_data"],
    noarchive=False,
)

a_cli = Analysis([str(RAIZ / "packaging" / "entry_cli.py")], **COMUM)
a_gui = Analysis([str(RAIZ / "packaging" / "entry_gui.py")], **COMUM)

MERGE((a_cli, "entry_cli", "acervo-dedup"), (a_gui, "entry_gui", "acervo-dedup-gui"))

pyz_cli = PYZ(a_cli.pure)
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="acervo-dedup",
    console=True,
    strip=False,
    upx=False,
)

pyz_gui = PYZ(a_gui.pure)
exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="acervo-dedup-gui",
    console=False,
    strip=False,
    upx=False,
)

COLLECT(
    exe_cli,
    a_cli.binaries,
    a_cli.datas,
    exe_gui,
    a_gui.binaries,
    a_gui.datas,
    strip=False,
    upx=False,
    name="acervo-dedup",
)
