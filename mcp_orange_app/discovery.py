"""컴퓨터에 설치된 Orange(python.exe)를 찾는다. 읽기만 하고 아무것도 쓰지 않는다.

Orange 설치 파일은 레지스트리에 흔적을 남기지 않는 경우가 있어(포터블 형태) 폴더 스캔이 기본이다.
찾는 순서(= 우선순위):
  1. 환경변수 ORANGE_PYTHON
  2. config.json 에 저장된 선택
  3. exe(또는 저장소) 옆/위의 Orange 폴더
  4. 고정 드라이브 루트·사용자 폴더·Program Files 아래에서 이름에 'orange' 가 들어간 폴더(깊이 2)
  5. conda 계열(miniconda/anaconda/mambaforge)의 envs 아래 환경
"""
from __future__ import annotations

import os
import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from . import config, paths

_PY = "python.exe" if os.name == "nt" else "bin/python"
_ORANGE_NAME = re.compile(r"orange", re.I)
_CONDA_NAME = re.compile(r"(mini|ana)conda|mambaforge|miniforge|micromamba", re.I)


@dataclass(frozen=True)
class Candidate:
    python: Path
    source: str  # 어디서 찾았는지 (env / config / near-exe / scan / conda)

    @property
    def root(self) -> Path:
        return self.python.parent


def is_orange_python(py: Path) -> bool:
    """python.exe 옆에 Orange 패키지가 있는가 (실행하지 않고 파일로만 판정)."""
    if not py.is_file():
        return False
    base = py.parent
    for sp in (base / "Lib" / "site-packages", base.parent / "Lib" / "site-packages"):
        if (sp / "Orange").is_dir() and (sp / "orangecanvas").is_dir():
            return True
    return False


def _norm(p: Path) -> str:
    try:
        return os.path.normcase(str(p.resolve()))
    except OSError:
        return os.path.normcase(str(p))


def _children(d: Path) -> Iterator[Path]:
    try:
        for c in d.iterdir():
            try:
                if c.is_dir():
                    yield c
            except OSError:
                continue
    except OSError:
        return


def _py_in(d: Path) -> Iterator[Path]:
    """폴더 d 자체와 한 단계 아래에서 python.exe 후보를 낸다."""
    yield d / _PY
    for c in _children(d):
        yield c / _PY


def _scan_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            r = Path(letter + ":\\")
            try:
                if r.exists():
                    roots.append(r)
            except OSError:
                pass
        for var in ("USERPROFILE", "LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
            v = os.environ.get(var)
            if v:
                roots.append(Path(v))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local) / "Programs")
    else:
        roots.append(Path.home())
    seen, out = set(), []
    for r in roots:
        k = _norm(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _scan() -> Iterator[Candidate]:
    for root in _scan_roots():
        for child in _children(root):
            name = child.name
            if _ORANGE_NAME.search(name):
                for py in _py_in(child):
                    yield Candidate(py, "scan")
            if _CONDA_NAME.search(name):
                yield Candidate(child / _PY, "conda")
                for env in _children(child / "envs"):
                    yield Candidate(env / _PY, "conda")


def _near_exe() -> Iterator[Candidate]:
    base = paths.exe_dir()
    for d in (base, base.parent):
        yield Candidate(d / "Orange" / _PY, "near-exe")
        yield Candidate(d / _PY, "near-exe")


def raw_candidates(extra: Iterable[str] = ()) -> Iterator[Candidate]:
    for e in extra:
        yield Candidate(Path(e), "user")
    env = os.environ.get("ORANGE_PYTHON")
    if env:
        yield Candidate(Path(env), "env")
    saved = config.load().get("orange_python")
    if saved:
        yield Candidate(Path(saved), "config")
    yield from _near_exe()
    yield from _scan()


def find_orange_pythons(extra: Iterable[str] = (), scan: bool = True) -> list[Candidate]:
    """중복을 제거하고 Orange 로 보이는 것만 우선순위 순으로 돌려준다."""
    seen: set[str] = set()
    out: list[Candidate] = []
    gen: Iterator[Candidate]
    if scan:
        gen = raw_candidates(extra)
    else:
        gen = (c for c in raw_candidates(extra) if c.source != "scan" and c.source != "conda")
    for c in gen:
        k = _norm(c.python)
        if k in seen:
            continue
        seen.add(k)
        if is_orange_python(c.python):
            out.append(c)
    return out


def first_candidate() -> Optional[Candidate]:
    """스캔 없이 빠르게(환경변수·저장된 선택·exe 옆) 하나 고른다. 서버 시작 경로에서 쓴다."""
    for c in find_orange_pythons(scan=False):
        return c
    return None
