"""후보 Orange 의 python 으로 '브리지가 의존하는 내부 심볼'이 있는지 GUI 없이 점검한다.

점검 코드는 후보 Orange 의 python 안에서 실행된다(`python -s -B -c`). 그래서
  * Python 3.8 에서도 돌아가야 하고(새 문법 금지),
  * 후보 Orange 폴더에 아무것도 쓰지 않도록 -B(바이트코드 안 씀)와 offscreen Qt 를 쓴다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# 후보 python 안에서 실행되는 코드. 마지막 줄에 JSON 한 개를 출력한다.
PROBE_CODE = r'''
import sys, os, json, inspect, importlib
res = {"python": sys.version.split()[0], "versions": {}, "checks": []}
def add(name, ok, level, detail=""):
    res["checks"].append({"name": name, "ok": bool(ok), "level": level, "detail": str(detail)[:300]})
try:
    import importlib.metadata as md
except Exception:
    md = None
for dist in ("Orange3", "orange-canvas-core", "orange-widget-base", "AnyQt"):
    try:
        res["versions"][dist] = md.version(dist)
    except Exception:
        res["versions"][dist] = None
def imp(mod):
    try:
        return importlib.import_module(mod), None
    except BaseException as ex:
        return None, "%s: %s" % (type(ex).__name__, ex)
def member(mod, cls, attr, level, label=None):
    label = label or (cls + "." + attr if cls else attr)
    m, err = imp(mod)
    if m is None:
        add(label, False, level, err); return
    o = getattr(m, cls, None) if cls else m
    if o is None:
        add(label, False, level, "no %s in %s" % (cls, mod)); return
    add(label, hasattr(o, attr) if attr else True, level)
def source_has(mod, needle, level, label):
    m, err = imp(mod)
    if m is None:
        add(label, False, level, err); return
    try:
        add(label, needle in inspect.getsource(m), level)
    except Exception as ex:
        add(label, False, level, "%s: %s" % (type(ex).__name__, ex))

qt, err = imp("AnyQt.QtCore")
if qt is None:
    add("Qt (AnyQt)", False, "fatal", err)
else:
    res["qt"] = getattr(qt, "PYQT_VERSION_STR", None) or getattr(qt, "__version__", None)
    add("Qt (AnyQt)", True, "fatal")
for mod in ("Orange", "orangecanvas", "orangewidget"):
    m, err = imp(mod)
    add("import " + mod, m is not None, "fatal", err or "")

# 시작 훅 (orange_mcp_bridge/__main__.py)
for a in ("argument_parser", "create_main_window", "show_welcome_screen", "run"):
    member("Orange.canvas.__main__", "OMain", a, "fatal")
# 캔버스 창 API (commands.py / widget_ops.py)
for a in ("current_document", "load_scheme", "save_scheme_to"):
    member("orangecanvas.application.canvasmain", "CanvasMainWindow", a, "fatal")
member("orangewidget.workflow.widgetsscheme", "WidgetsScheme", "widget_for_node", "fatal")
member("orangecanvas.scheme.signalmanager", "SignalManager", "is_pending", "fatal")
member("orangecanvas.scheme.link", None, "possible_links", "fatal")
member("orangecanvas.registry", None, "global_registry", "fatal")
for a in ("Running", "Pending", "test_state_flags"):
    member("orangecanvas.scheme.node", "SchemeNode", a, "fatal")
# 비공개 구현 (get_output / 설정 주입)
source_has("orangecanvas.scheme.signalmanager", "__node_outputs", "fatal", "SignalManager private __node_outputs")
source_has("orangewidget.gui", "controlled_attributes", "fatal", "gui.controlled_attributes")
source_has("orangewidget.settings", "known_settings", "fatal", "SettingsHandler.known_settings")
# 있으면 좋은 것 (없으면 해당 기능만 제한)
member("orangewidget.workflow.errorreporting", "ErrorReporting", None, "warn", "ErrorReporting dialog class")
for a in ("select_by_indices", "select_by_rectangle", "unselect_all"):
    member("Orange.widgets.visualize.owscatterplotgraph", "OWScatterPlotBase", a, "warn")
for a in ("add_path", "load_data"):
    member("Orange.widgets.data.owfile", "OWFile", a, "warn")

# 브리지 소스가 이 python 의 문법으로 컴파일되는가 (예: 3.8 에서 3.9+ 문법)
bdir = os.environ.get("OMB_BRIDGE_DIR")
if bdir and os.path.isdir(bdir):
    bad = []
    for fn in sorted(os.listdir(bdir)):
        if fn.endswith(".py"):
            p = os.path.join(bdir, fn)
            try:
                with open(p, "rb") as f:
                    compile(f.read(), p, "exec", dont_inherit=True)
            except SyntaxError as ex:
                bad.append("%s:%s %s" % (fn, ex.lineno, ex.msg))
    add("bridge syntax on this Python", not bad, "fatal", "; ".join(bad))
print("@@PROBE@@" + json.dumps(res))
'''


@dataclass
class Check:
    name: str
    ok: bool
    level: str  # "fatal" | "warn"
    detail: str = ""


@dataclass
class ProbeResult:
    python_exe: str
    ran: bool = False                      # python 을 실제로 돌릴 수 있었나
    error: str = ""
    py_version: str = ""
    qt: str = ""
    versions: dict = field(default_factory=dict)   # 배포판 이름 -> 버전
    checks: list = field(default_factory=list)

    @property
    def orange_version(self) -> Optional[str]:
        return self.versions.get("Orange3")

    @property
    def fatal(self) -> list:
        return [c for c in self.checks if not c.ok and c.level == "fatal"]

    @property
    def warnings(self) -> list:
        return [c for c in self.checks if not c.ok and c.level == "warn"]

    def to_dict(self) -> dict[str, Any]:
        return {"python_exe": self.python_exe, "ran": self.ran, "error": self.error,
                "py_version": self.py_version, "qt": self.qt, "versions": self.versions,
                "checks": [c.__dict__ for c in self.checks]}


def _clean_env(bridge_dir: Optional[Path]) -> dict:
    env = dict(os.environ)
    for k in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"):
        env.pop(k, None)
    env.update(QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    if bridge_dir:
        env["OMB_BRIDGE_DIR"] = str(bridge_dir)
    return env


def probe(python_exe: "str | Path", bridge_dir: Optional[Path] = None, timeout: float = 120.0) -> ProbeResult:
    """python_exe 를 -s -B 로 돌려 PROBE_CODE 를 실행한다. 후보 폴더는 읽기만 한다."""
    r = ProbeResult(python_exe=str(python_exe))
    try:
        p = subprocess.run(
            [str(python_exe), "-s", "-B", "-c", PROBE_CODE],
            capture_output=True, timeout=timeout, env=_clean_env(bridge_dir), stdin=subprocess.DEVNULL,
            cwd=str(Path(python_exe).parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        r.error = "검사가 %d초 안에 끝나지 않았습니다" % timeout
        return r
    except OSError as e:
        r.error = "python 을 실행할 수 없습니다: %s" % e
        return r
    out = p.stdout.decode("utf-8", "replace")
    line = next((ln for ln in reversed(out.splitlines()) if ln.startswith("@@PROBE@@")), None)
    if line is None:
        tail = (p.stderr.decode("utf-8", "replace") or out).strip().splitlines()[-3:]
        r.error = "검사 결과를 받지 못했습니다 (exit %s): %s" % (p.returncode, " | ".join(tail))
        return r
    d = json.loads(line[len("@@PROBE@@"):])
    r.ran = True
    r.py_version = d.get("python", "")
    r.qt = d.get("qt") or ""
    r.versions = d.get("versions", {})
    r.checks = [Check(**c) for c in d.get("checks", [])]
    return r


if __name__ == "__main__":  # 수동 확인: python -m mcp_orange_app.probe <python.exe>
    from . import paths
    res = probe(sys.argv[1], paths.bridge_source_dir())
    print(json.dumps(res.to_dict(), indent=1, ensure_ascii=False))
