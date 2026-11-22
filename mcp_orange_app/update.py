"""새 버전 확인과 자체 교체 (GitHub Releases).

흐름: 최신 릴리스 조회 -> 새 버전이면 호출한 쪽이 사용자에게 확인 -> 동의하면 exe 를 내려받아
크기·형식 확인 -> 실행 중인 exe 를 이름만 바꿔 치우고(Windows 는 실행 중인 exe 의 이름 변경을 허용)
새 파일을 그 자리에 둔다. 이전 파일은 다음 시작 때 지운다. 실패하면 원래대로 되돌린다.

MCP 서버 모드(--mcp-server)에서는 확인하지 않는다: stdout 이 프로토콜이고 사용자에게 물을 수 없다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import version

REPO = "c0z0c/mcp_orange"
ASSET = "mcp_orange.exe"
LATEST_API = "https://api.github.com/repos/%s/releases/latest" % REPO
DOWNLOAD_PREFIX = "https://github.com/%s/releases/download/" % REPO
NEW_NAME = "mcp_orange_new.tmp"
OLD_NAME = "mcp_orange_del.tmp"


class UpdateError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 실패 사유."""


@dataclass
class UpdateInfo:
    version: str = ""        # 최신 릴리스 (예 "0.5.0.3")
    newer: bool = False      # 실행 중인 버전보다 새 것이고 받을 파일이 있음
    url: str = ""
    size: int = 0
    page: str = ""


def disabled() -> bool:
    """MCP_ORANGE_NO_UPDATE_CHECK 가 있으면 시작 시 확인을 건너뛴다 (테스트·오프라인용)."""
    return bool(os.environ.get("MCP_ORANGE_NO_UPDATE_CHECK"))


def parse_version(text: str) -> tuple:
    """'v0.5.0.3' -> (0, 5, 0, 3). 3자리면 BUILD 0 으로 채운다."""
    parts = text.strip().lstrip("vV").split(".")
    if not 3 <= len(parts) <= 4 or not all(p.isdigit() for p in parts):
        raise ValueError("해석할 수 없는 버전: %r" % text)
    return tuple(int(p) for p in parts) + (0,) * (4 - len(parts))


def _open(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "mcp_orange/" + version.full(), "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=15)


def check(current: Optional[str] = None) -> UpdateInfo:
    """최신 릴리스를 조회한다. 네트워크 호출이므로 화면 스레드에서 부르지 않는다. 실패하면 UpdateError."""
    try:
        with _open(LATEST_API) as res:
            data = json.loads(res.read().decode("utf-8"))
        latest = parse_version(str(data.get("tag_name", "")))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("공개된 릴리스가 아직 없습니다.") from e
        raise UpdateError("최신 버전을 확인하지 못했습니다: %s" % e) from e
    except (OSError, ValueError) as e:       # URLError/타임아웃(OSError), JSON/버전 오류(ValueError)
        raise UpdateError("최신 버전을 확인하지 못했습니다: %s" % e) from e
    ver = ".".join(map(str, latest))
    info = UpdateInfo(version=ver, page=str(data.get("html_url", "")))
    if latest <= parse_version(current or version.full()):
        return info
    for a in data.get("assets") or []:
        url = str(a.get("browser_download_url", ""))
        if a.get("name") == ASSET and url.startswith(DOWNLOAD_PREFIX):
            info.newer, info.url, info.size = True, url, int(a.get("size") or 0)
            break
    return info


def _download(info: UpdateInfo, dest: Path) -> None:
    with _open(info.url) as res, open(dest, "wb") as out:
        if not res.geturl().startswith("https://"):
            raise UpdateError("안전하지 않은 다운로드 경로입니다.")
        first = True
        while True:
            chunk = res.read(1 << 20)
            if not chunk:
                break
            if first and chunk[:2] != b"MZ":
                raise UpdateError("받은 파일이 실행 파일이 아닙니다.")
            first = False
            out.write(chunk)
    if info.size and dest.stat().st_size != info.size:
        raise UpdateError("받은 파일 크기가 다릅니다.")


def install(info: UpdateInfo, exe: Optional[Path] = None) -> None:
    """새 exe 를 받아 확인하고 실행 중인 exe 를 교체한다. 실패하면 원래대로 되돌리고 UpdateError."""
    if not info.newer:
        raise UpdateError("받을 업데이트가 없습니다.")
    if exe is None:
        if not getattr(sys, "frozen", False):
            raise UpdateError("exe 로 실행 중일 때만 교체할 수 있습니다. 릴리스 페이지에서 받으세요: " + info.page)
        exe = Path(sys.executable)
    fresh, old = exe.with_name(NEW_NAME), exe.with_name(OLD_NAME)
    try:
        _download(info, fresh)
        old.unlink(missing_ok=True)
        os.replace(exe, old)
        try:
            os.replace(fresh, exe)
        except OSError:
            os.replace(old, exe)
            raise
    except UpdateError:
        raise
    except OSError as e:
        raise UpdateError("업그레이드 실패 (쓰기 권한이 없거나 네트워크 오류): %s" % e) from e
    finally:
        fresh.unlink(missing_ok=True)


def relaunch() -> None:
    """교체된 exe 를 새 프로세스로 실행한다 (현재 프로세스는 호출한 쪽이 종료)."""
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")   # onefile 자식이 부모의 임시 폴더를 재사용하지 않게
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if sys.platform == "win32" else 0
    subprocess.Popen([sys.executable], env=env, creationflags=flags, close_fds=True)


def cleanup_leftovers(wait: float = 5.0) -> None:
    """이전 업그레이드가 남긴 파일을 지운다. 이전 프로세스가 끝나기를 잠시 기다린다."""
    if not getattr(sys, "frozen", False):
        return
    exe = Path(sys.executable)
    old = exe.with_name(OLD_NAME)
    deadline = time.monotonic() + wait
    while old.exists() and time.monotonic() < deadline:
        try:
            old.unlink()
        except OSError:
            time.sleep(0.25)
    try:
        exe.with_name(NEW_NAME).unlink(missing_ok=True)
    except OSError:
        pass
