"""버전 = version.txt(MAJOR.MINOR.PATCH) + git 커밋 수(BUILD)  →  MAJOR.MINOR.PATCH.BUILD

* 개발(소스 실행): version.txt 와 `git rev-list --count HEAD` 로 그때그때 계산한다.
* 빌드(exe): build/mcp_orange.spec 이 같은 계산을 해 `_buildinfo.py` 로 굳히고(.gitignore 대상),
  exe 에는 git 이 없으므로 그 값을 쓴다. 같은 값이 exe 파일 속성(자세히 탭)의 버전 리소스에도 들어간다.

BUILD 는 '커밋한 만큼' 올라가므로, 릴리스는 **커밋한 뒤** 빌드한다. 커밋하지 않은 변경이 있으면
표시 문자열에 `+dirty` 가 붙는다 (예: 0.5.0.12+g1a2b3c4.dirty).
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_BASE_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Info:
    base: str            # version.txt 의 MAJOR.MINOR.PATCH
    build: int           # 커밋 수 (git 이 없거나 커밋이 없으면 0)
    sha: str = ""        # 짧은 커밋 해시 (없으면 빈 문자열)
    dirty: bool = False  # 커밋되지 않은 변경이 있음

    @property
    def full(self) -> str:
        """0.5.0.12 — 파일 버전과 같은 4자리."""
        return "%s.%d" % (self.base, self.build)

    @property
    def quad(self) -> tuple:
        return tuple(int(x) for x in self.base.split(".")) + (min(self.build, 65535),)

    @property
    def display(self) -> str:
        """사람이 보는 전체 표기. 0.5.0.12  /  0.5.0.12+g1a2b3c4  /  0.5.0.12+g1a2b3c4.dirty"""
        s = self.full
        if self.sha:
            s += "+g" + self.sha
        if self.dirty:
            s += ".dirty" if self.sha else "+dirty"
        return s


def parse_base(text: str) -> str:
    first = (text.lstrip("﻿").strip().splitlines() or [""])[0].strip()
    if not _BASE_RE.match(first):
        raise ValueError("version.txt 는 MAJOR.MINOR.PATCH 형식이어야 합니다 (예: 0.5.0): %r" % first)
    return first


def read_base() -> str:
    return parse_base((_root() / "version.txt").read_text(encoding="utf-8"))


def _git(*args: str) -> Optional[str]:
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        # git 출력은 UTF-8 이다. text=True 만 쓰면 로케일(한국어 Windows 는 cp949)로 읽다가 한글 경로에서 디코딩이 실패한다.
        r = subprocess.run(["git", *args], cwd=str(_root()), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15, **kw)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout is not None else None


def _own_repo() -> bool:
    """소스가 다른 저장소 안에 풀려 있을 때 엉뚱한 저장소의 커밋 수를 세지 않도록, 이 폴더가 저장소 루트일 때만 쓴다."""
    top = _git("rev-parse", "--show-toplevel")
    if not top:
        return False
    try:
        return Path(top).resolve() == _root().resolve()
    except OSError:
        return False


def collect(base: Optional[str] = None) -> Info:
    """version.txt 와 git 에서 지금 값을 계산한다 (캐시 없음, _buildinfo 를 보지 않음)."""
    base = base or read_base()
    if not _own_repo():
        return Info(base, 0)
    count = _git("rev-list", "--count", "HEAD")
    if not (count and count.isdigit()):
        return Info(base, 0)                         # 아직 커밋이 없음
    sha = _git("rev-parse", "--short=7", "HEAD") or ""
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return Info(base, int(count), sha, dirty)


def write_buildinfo(path: Path, info: Info) -> None:
    path.write_text(
        "# 자동 생성 (build/mcp_orange.spec) — 커밋하지 않는다.\n"
        "BASE = %r\nBUILD = %d\nSHA = %r\nDIRTY = %r\n" % (info.base, info.build, info.sha, info.dirty),
        encoding="utf-8")


@lru_cache(maxsize=None)
def info() -> Info:
    try:
        from . import _buildinfo as b          # exe 빌드가 만든 값
        return Info(b.BASE, int(b.BUILD), b.SHA, bool(b.DIRTY))
    except ImportError:
        pass
    try:
        return collect()
    except (OSError, ValueError):
        return Info("0.0.0", 0)


def full() -> str:
    return info().full


def display() -> str:
    return info().display
