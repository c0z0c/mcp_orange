"""PyInstaller onefile 이 강제 종료로 남긴 임시 풀기 폴더(_MEI*) 정리.

MCP 클라이언트는 세션이 끝나면 서버 프로세스 트리를 Job Object 로 즉시 죽이는 경우가 있어, 부트로더가
정리하지 못한 폴더(약 40MB)가 쌓일 수 있다. 다른 인스턴스가 쓰는 폴더를 지우면 안 되므로
"폴더 이름 바꾸기"를 사용 중 판별에 쓴다: 로드된 DLL 이 폴더 안에 열려 있으면 Windows 는 이름 변경을 거부한다.
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
import tempfile
import threading


def cleanup_stale_extractions() -> int:
    """사용 중이 아닌 _MEI* 폴더를 지우고 지운 개수를 돌려준다. 어떤 실패도 조용히 무시한다."""
    if not getattr(sys, "frozen", False):
        return 0
    mine = os.path.normcase(os.path.abspath(getattr(sys, "_MEIPASS", "")))
    removed = 0
    try:
        for d in glob.glob(os.path.join(tempfile.gettempdir(), "_MEI*")):
            if not os.path.isdir(d) or os.path.normcase(os.path.abspath(d)) == mine:
                continue
            probe = d + "_del"
            try:
                os.rename(d, probe)          # 사용 중이면 PermissionError
            except OSError:
                continue
            shutil.rmtree(probe, ignore_errors=True)
            removed += 1
    except Exception:  # noqa: BLE001 - 정리는 부가 기능이므로 서버를 절대 막지 않는다
        pass
    return removed


def _cleanup_all() -> None:
    cleanup_stale_extractions()
    try:
        from . import update
        update.cleanup_leftovers()           # 이전 업그레이드가 남긴 mcp_orange_del.tmp
    except Exception:  # noqa: BLE001
        pass


def cleanup_in_background() -> None:
    if getattr(sys, "frozen", False):
        threading.Thread(target=_cleanup_all, name="mei-cleanup", daemon=True).start()
