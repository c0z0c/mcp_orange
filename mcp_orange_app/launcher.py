"""Orange 를 브리지와 함께 띄운다. (relay 의 launch_orange 와 --check/--smoke 가 공유)

* 브리지 소스(orange_mcp_bridge)를 %LOCALAPPDATA%\\mcp_orange\\bridge\\<해시> 에 풀어 거기서 실행한다.
  exe 가 임시 폴더에서 풀리는 PyInstaller onefile 이어도, Orange 가 릴레이보다 오래 살아도 안전하다.
  이 폴더에는 브리지 패키지만 있으므로 `-P` 없이 `-m` 으로 실행해도 sys.path 오염이 없다
  (그래서 `-P` 가 없는 Python 3.8 기반 Orange 3.32 에서도 같은 방식으로 뜬다).
* 후보 Orange 폴더에는 아무것도 쓰지 않도록 `-B` 를 준다.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import compat, config, discovery, paths, probe as probe_mod


class LaunchError(ValueError):
    """사용자에게 그대로 보여 줄 수 있는 실패 사유."""


# ---------------------------------------------------------------- 브리지 배포
def _tree_stamp(src: Path) -> str:
    h = hashlib.sha1(b"bridge-v1")      # 배포 폴더 이름은 소스 내용으로만 결정된다 (커밋마다 다시 풀 필요 없음)
    for p in sorted(src.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(str(p.relative_to(src)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def deploy_bridge() -> Path:
    """브리지 패키지를 데이터 폴더로 복사하고, 그 *부모* 폴더(PYTHONPATH 이자 cwd)를 돌려준다."""
    src = paths.bridge_source_dir()
    if not src.is_dir():
        raise LaunchError("브리지 소스를 찾을 수 없습니다: %s" % src)
    stamp = _tree_stamp(src)
    root = paths.bridge_runtime_dir() / stamp
    dst = root / "orange_mcp_bridge"
    if not (root / ".ok").is_file():
        tmp = root.with_name(stamp + ".tmp%d" % os.getpid())
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(src, tmp / "orange_mcp_bridge", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".mypy_cache"))
        (tmp / ".ok").write_text(stamp)
        try:
            os.replace(tmp, root)          # 원자적으로 공개. 동시에 다른 릴레이가 먼저 했으면 실패 -> 그 결과를 쓴다
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            if not (root / ".ok").is_file():
                raise
        _prune_old(paths.bridge_runtime_dir(), keep=stamp)
    assert dst.is_dir()
    return root


def _prune_old(base: Path, keep: str) -> None:
    """예전 해시 폴더 정리(사용 중이면 지워지지 않으므로 조용히 무시)."""
    try:
        for d in base.iterdir():
            if d.is_dir() and d.name != keep:
                shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass


# ---------------------------------------------------------------- 대상 선택 + 호환성
@dataclass
class Target:
    python: str
    status: str
    summary: str
    orange_version: str = ""
    py_version: str = ""
    checks: list = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.status in (compat.VERIFIED, compat.PROBE_OK)


def _fingerprint(py: Path) -> str:
    try:
        st = py.stat()
        return "%d:%d" % (st.st_size, int(st.st_mtime))
    except OSError:
        return ""


def check(python: "str | Path", save: bool = True, select: bool = False) -> Target:
    """python 을 프로브하고 판정한다. save 면 결과를 config 에 남기고, select 면 사용 대상으로 고른다."""
    py = Path(python)
    res = probe_mod.probe(py, paths.bridge_source_dir())
    v = compat.judge(res)
    t = Target(str(py), v.status, v.summary, v.orange_version, res.py_version,
               [c.__dict__ for c in res.checks if not c.ok])
    if save:
        cfg = config.load()
        results = cfg.get("results", {})
        results[os.path.normcase(str(py))] = {
            "status": t.status, "summary": t.summary, "orange_version": t.orange_version,
            "py_version": t.py_version, "fingerprint": _fingerprint(py),
            "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "failed": t.checks}
        cfg["results"] = results
        if select:
            cfg["orange_python"] = str(py)
        config.save(cfg)
    return t


def cached_check(python: "str | Path") -> Optional[Target]:
    """같은 python(크기·수정시각 동일)을 이미 검사했다면 그 결과."""
    py = Path(python)
    r = config.load().get("results", {}).get(os.path.normcase(str(py)))
    if not r or r.get("fingerprint") != _fingerprint(py):
        return None
    return Target(str(py), r["status"], r["summary"], r.get("orange_version", ""),
                  r.get("py_version", ""), r.get("failed", []))


def _version_key(v: str) -> tuple:
    out = []
    for part in (v or "").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def _rank(t: "Target") -> tuple:
    """자동 선택 우선순위: 검증됨 > 미검증, 그 안에서는 최신 Orange 버전 우선."""
    return (1 if t.status == compat.VERIFIED else 0, _version_key(t.orange_version))


def _check_all(cands, persist: bool) -> list:
    from concurrent.futures import ThreadPoolExecutor

    def one(c):
        return cached_check(c.python) or check(c.python, save=persist)
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(cands)))) as ex:
        return list(ex.map(one, cands))


def resolve_target(allow_probe: bool = True, persist: bool = True) -> Target:
    """사용할 Orange 를 고르고(환경변수 > 저장된 선택 > exe 옆 > 스캔 후 최적), 호환성을 확인한다.

    persist=False 면 config.json 에 아무것도 쓰지 않는다(드라이런 등).
    스캔으로 여러 개를 찾으면 사용 가능한 것 중 '검증됨 우선, 최신 버전 우선'으로 고른다.
    """
    explicit = os.environ.get("ORANGE_PYTHON")
    if explicit and not discovery.is_orange_python(Path(explicit)):
        # 사용자가 명시한 경로가 틀렸으면 다른 Orange 로 조용히 대체하지 않고 알려 준다
        raise LaunchError("환경변수 ORANGE_PYTHON 이 Orange 의 python.exe 가 아닙니다: %s" % explicit)
    cand = discovery.first_candidate()
    if cand is not None:
        t = cached_check(cand.python)
        if t is None:
            if not allow_probe:
                raise LaunchError("아직 호환성 검사를 하지 않았습니다: %s" % cand.python)
            t = check(cand.python, save=persist, select=(persist and cand.source != "env"))
    else:
        cands = discovery.find_orange_pythons()                 # 전체 스캔
        if not cands:
            raise LaunchError(
                "Orange 를 찾을 수 없습니다. mcp_orange.exe 를 인자 없이 실행해 Orange 를 선택하거나, "
                "환경변수 ORANGE_PYTHON 에 Orange 의 python.exe 경로를 지정하세요.")
        if not allow_probe and any(cached_check(c.python) is None for c in cands):
            raise LaunchError("아직 호환성 검사를 하지 않았습니다.")
        results = _check_all(cands, persist)
        usable = [r for r in results if r.usable]
        t = max(usable, key=_rank) if usable else results[0]
        if persist and t.usable:
            config.update(orange_python=t.python)
    if not t.usable:
        raise LaunchError("이 Orange 는 사용할 수 없습니다 (%s): %s\n  경로: %s" % (
            compat.LABEL.get(t.status, t.status), t.summary, t.python))
    return t


# ---------------------------------------------------------------- 실행
# 릴레이 환경에서 Orange 로 그대로 넘기는 변수: 데이터 폴더 격리, 설정 격리, 헤드리스, 개발용 debug_exec.
PASS_THROUGH_ENV = ("MCP_ORANGE_HOME", "MCP_ORANGE_SETTINGS_DIR", "QT_QPA_PLATFORM", "ORANGE_MCP_DEBUG")


@dataclass
class Plan:
    argv: list
    cwd: str
    env: dict          # PYTHONPATH 등 추가 환경변수
    logfile: str


def build_plan(python: str, show_welcome: bool = False, extra_env: Optional[dict] = None,
               logname: str = "orange.relay.log", extra_args: Optional[list] = None) -> Plan:
    root = deploy_bridge()
    paths.log_dir().mkdir(parents=True, exist_ok=True)
    argv = [python, "-s", "-B", "-m", "orange_mcp_bridge"]
    if show_welcome:
        argv.append("--welcome")
    argv += list(extra_args or [])
    env = {"PYTHONPATH": str(root)}
    # WMI 로 띄운 프로세스는 우리 환경변수를 물려받지 못하므로, 필요한 것만 명시적으로 전달한다.
    for k in PASS_THROUGH_ENV:
        if k in os.environ:
            env[k] = os.environ[k]
    env.update(extra_env or {})
    return Plan(argv, str(root), env, str(paths.log_dir() / logname))


def _wmi_cmdline(plan: Plan) -> str:
    q = lambda s: '"%s"' % s  # noqa: E731
    sets = "".join('set "%s=%s"&& ' % (k, v) for k, v in plan.env.items())
    cmd = " ".join(q(a) if (os.sep in a or " " in a) else a for a in plan.argv)
    return 'cmd.exe /d /s /c "%s%s > %s 2>&1"' % (sets, cmd, q(plan.logfile))


def _spawn_via_wmi(plan: Plan) -> bool:
    ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
          "-Arguments @{CommandLine=$env:OM_CMD; CurrentDirectory=$env:OM_CWD}; "
          "exit $r.ReturnValue")
    env = dict(os.environ, OM_CMD=_wmi_cmdline(plan), OM_CWD=plan.cwd)
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            env=env, capture_output=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def spawn(plan: Plan, detach_from_job: bool = True) -> Optional[subprocess.Popen]:
    """Orange 를 띄운다.

    detach_from_job=True (MCP 서버): MCP 클라이언트는 Job Object 로 릴레이의 프로세스 트리를 통째로 죽이므로
      일반 자식이면 세션 종료와 함께 Orange 가 죽어 저장 안 한 작업을 잃는다. WMI 로 만든 프로세스는
      그 Job 밖(사용자의 대화형 세션)에 생기므로 살아남는다. WMI 가 안 되면 분리된 일반 프로세스로 폴백.
    False (검사/테스트): 환경변수를 그대로 물려받는 일반 자식 프로세스 (Popen 을 돌려준다).
    """
    env = dict(os.environ)
    env.update(plan.env)
    if sys.platform == "win32" and detach_from_job:
        if _spawn_via_wmi(plan):
            return None
    log = open(plan.logfile, "wb")
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if detach_from_job else 0
    kw = {"creationflags": flags} if sys.platform == "win32" else {"start_new_session": detach_from_job}
    return subprocess.Popen(plan.argv, env=env, cwd=plan.cwd, stdout=log, stderr=log,
                            stdin=subprocess.DEVNULL, **kw)
