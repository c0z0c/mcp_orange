# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: mcp_orange.exe (onefile, console).
#   build\build_exe.ps1 로 빌드한다.
#
# 브리지(orange_mcp_bridge)는 exe 안에서 실행되지 않는다 — Orange 자신의 Python 이 실행한다.
# 그래서 import 분석 대상이 아니라 '데이터 파일'로만 넣고, 실행 시 %LOCALAPPDATA%\mcp_orange\bridge 로 푼다.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))

# ---- 버전: version.txt + git 커밋 수 -> exe 안(_buildinfo)과 파일 속성(버전 리소스) 양쪽에 넣는다
from mcp_orange_app import version as _ver

_info = _ver.collect()
_ver.write_buildinfo(ROOT / "mcp_orange_app" / "_buildinfo.py", _info)
print("mcp_orange version:", _info.display)

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo)

_vi = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_info.quad, prodvers=_info.quad, mask=0x3F, flags=0x0,
                      OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "c0z0c"),
            StringStruct("FileDescription", "mcp_orange - Orange 3 MCP bridge"),
            StringStruct("FileVersion", _info.full),
            StringStruct("InternalName", "mcp_orange"),
            StringStruct("LegalCopyright", "Copyright (C) 2026 c0z0c. GPL-3.0-or-later"),
            StringStruct("OriginalFilename", "mcp_orange.exe"),
            StringStruct("ProductName", "mcp_orange"),
            StringStruct("ProductVersion", _info.display),
            StringStruct("Comments", "https://github.com/c0z0c/mcp_orange"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ])
_vi_file = Path(SPECPATH) / "work" / "version_info.txt"
_vi_file.parent.mkdir(parents=True, exist_ok=True)
_vi_file.write_text(str(_vi), encoding="utf-8")

bridge_files = [(str(p), "orange_mcp_bridge")
                for p in sorted((ROOT / "orange_mcp_bridge").glob("*.py"))]

a = Analysis(
    [str(ROOT / "app_main.py")],
    pathex=[str(ROOT), str(ROOT / "relay")],
    binaries=[],
    datas=bridge_files,
    # --mcp-server 에서 지연 import 하는 모듈들(정적 분석이 놓칠 수 있음)
    hiddenimports=["mcp_orange", "bridge_client", "mcp_orange_app.wizard", "mcp_orange_app.smoke",
                   "mcp_manage.gui", "mcp_manage.cli", "mcp_orange_app._buildinfo"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["unittest", "pydoc", "test", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
# onefile 은 실행할 때마다 모든 파일을 풀기 때문에 파일 수가 곧 시작 지연이다.
# Tcl 의 시간대 DB(tzdata, 600여 개 파일)는 우리 GUI 가 쓰지 않으므로 뺀다.
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").startswith("_tcl_data/tzdata")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mcp_orange",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 는 백신 오탐을 늘린다
    console=True,        # stdio MCP 서버에 필요. 더블클릭 시엔 GUI 가 뜨고 콘솔은 스스로 숨긴다.
    disable_windowed_traceback=False,
    version=str(_vi_file),
)
