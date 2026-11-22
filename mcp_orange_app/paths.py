"""경로 규칙. 테스트에서는 환경변수 MCP_ORANGE_HOME 으로 데이터 폴더를 통째로 바꿀 수 있다."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def frozen() -> bool:
    """PyInstaller 로 묶인 exe 로 실행 중인가."""
    return bool(getattr(sys, "frozen", False))


def repo_root() -> Path:
    """소스 체크아웃의 루트 (개발 모드) 또는 exe 가 풀린 리소스 루트 (frozen)."""
    if frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def exe_dir() -> Path:
    """exe(또는 개발 모드의 저장소 루트)가 있는 폴더 — 옆에 Orange 폴더가 있는지 찾는 기준."""
    return Path(sys.executable).resolve().parent if frozen() else repo_root()


def app_dir() -> Path:
    """사용자별 데이터 폴더. 브리지의 bridge.json 도 여기에 만들어진다."""
    env = os.environ.get("MCP_ORANGE_HOME")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "mcp_orange"


def config_file() -> Path:
    return app_dir() / "config.json"


def log_dir() -> Path:
    return app_dir() / "logs"


def bridge_runtime_dir() -> Path:
    """브리지 소스를 풀어 두는 곳. Orange 가 릴레이보다 오래 살 수 있으므로 임시 폴더를 쓰지 않는다."""
    return app_dir() / "bridge"


def bridge_source_dir() -> Path:
    """배포용 브리지 패키지(orange_mcp_bridge)의 원본 위치."""
    return repo_root() / "orange_mcp_bridge"


def self_launch() -> tuple[str, tuple[str, ...]]:
    """AI 클라이언트에 등록할 '이 서버를 실행하는 명령'.

    frozen: (mcp_orange.exe, ("--mcp-server",))
    개발:   (.venv python, (relay/mcp_orange.py,))
    """
    if frozen():
        return str(Path(sys.executable).resolve()), ("--mcp-server",)
    root = repo_root()
    venv = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    py = venv if venv.is_file() else Path(sys.executable)
    return str(py), (str(root / "relay" / "mcp_orange.py"),)
