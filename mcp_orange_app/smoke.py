"""격리된 Orange 를 offscreen 으로 띄워 브리지의 핵심 동작을 end-to-end 로 확인한다 (`--check --deep`).

* 사용자가 쓰는 Orange/bridge.json 과 섞이지 않도록 임시 MCP_ORANGE_HOME 을 쓴다.
* QT_QPA_PLATFORM=offscreen 이라 창이 뜨지 않는다.
* 후보 Orange 폴더에는 쓰지 않는다 (-B).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import launcher, paths


@dataclass
class Step:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class SmokeResult:
    python: str
    started: bool = False
    steps: list = field(default_factory=list)
    log_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.started and bool(self.steps) and all(s.ok for s in self.steps)

    def to_dict(self) -> dict:
        return {"python": self.python, "started": self.started, "ok": self.ok,
                "steps": [s.__dict__ for s in self.steps], "log_tail": self.log_tail}


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        proc.kill()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        pass


def run(python: str, startup_timeout: float = 150.0,
        say: Callable[[str], None] = lambda s: None) -> SmokeResult:
    res = SmokeResult(python=str(python))
    home = Path(tempfile.mkdtemp(prefix="mcp_orange_smoke_"))
    old_home = os.environ.get("MCP_ORANGE_HOME")
    os.environ["MCP_ORANGE_HOME"] = str(home)          # 이 프로세스의 bridge_client 도 같은 곳을 보게
    proc: Optional[subprocess.Popen] = None
    try:
        sys.path.insert(0, str(paths.repo_root() / "relay")) if not paths.frozen() else None
        import bridge_client as bc  # noqa: WPS433

        plan = launcher.build_plan(
            str(python), extra_env={"MCP_ORANGE_HOME": str(home), "QT_QPA_PLATFORM": "offscreen",
                                    "PYTHONIOENCODING": "utf-8",
                                    "MCP_ORANGE_SETTINGS_DIR": str(home / "settings")},
            logname="smoke_%d.log" % os.getpid())
        say("Orange 를 offscreen 으로 띄우는 중 ...")
        proc = launcher.spawn(plan, detach_from_job=False)
        t0 = time.time()
        ping = None
        while time.time() - t0 < startup_timeout:
            if proc.poll() is not None:
                break
            try:
                ping = bc.call("ping", timeout=10)
                break
            except bc.BridgeError:
                time.sleep(1.0)
        res.log_tail = _tail(plan.logfile)
        if ping is None:
            res.steps.append(Step("start", False, "브리지가 %d초 안에 응답하지 않음" % startup_timeout))
            return res
        res.started = True
        res.steps.append(Step("start", True, "%.0fs, %s" % (time.time() - t0, json.dumps(ping)[:120])))
        say("브리지 응답 확인. 시나리오 실행 ...")
        _scenario(bc, res, say)
        res.log_tail = _tail(plan.logfile)
        return res
    finally:
        if proc is not None:
            _kill_tree(proc)
        if old_home is None:
            os.environ.pop("MCP_ORANGE_HOME", None)
        else:
            os.environ["MCP_ORANGE_HOME"] = old_home
        shutil.rmtree(home, ignore_errors=True)


def _tail(path: str, n: int = 25) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


def _scenario(bc, res: SmokeResult, say) -> None:
    def step(name: str, fn: Callable[[], object]) -> object:
        try:
            out = fn()
            ok, detail = (out if isinstance(out, tuple) else (True, str(out) if out is not None else ""))
        except Exception as ex:  # noqa: BLE001 - 어떤 실패든 단계 실패로 기록
            ok, detail, out = False, "%s: %s" % (type(ex).__name__, str(ex)[:300]), None
        res.steps.append(Step(name, bool(ok), str(detail)[:300]))
        say(("  PASS " if ok else "  FAIL ") + name + ("" if ok else "  -> " + str(detail)[:160]))
        return out

    def idle(timeout=60):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not bc.call("get_status")["busy"]:
                return True
            time.sleep(0.3)
        return False

    ids = {}
    step("clear_workflow", lambda: bc.call("clear_workflow") and None)

    def widgets():
        r = bc.call("list_widgets", query="tree", limit=50)
        n = len(r["widgets"]) if isinstance(r, dict) and "widgets" in r else len(r)
        return n > 0, "%d matches for 'tree'" % n
    step("list_widgets", widgets)

    def add(widget, key):
        ids[key] = bc.call("add_node", widget=widget)["id"]
        return True, ids[key]
    step("add File", lambda: add("File", "file"))
    step("load_file iris", lambda: (bc.call("load_file", node=ids["file"], path="iris") or True, ""))
    step("idle after load", lambda: (idle(), ""))

    def out_rows():
        d = bc.call("get_output", node=ids["file"], rows=3)["Data"]
        return d["rows"] == 150, "rows=%s" % d["rows"]
    step("get_output File = 150 rows", out_rows)

    step("add k-Means", lambda: add("k-Means", "km"))
    step("link File -> k-Means", lambda: (bc.call("add_link", source=ids["file"], sink=ids["km"]) and True, ""))
    step("update_widget k=3 (Qt control path)", lambda: (
        lambda r: (True, json.dumps(r, ensure_ascii=False)[:160]))(
        bc.call("update_widget", node=ids["km"], settings={"optimize_k": "Fixed", "k": 3})))
    step("idle after k-Means", lambda: (idle(), ""))

    def clusters():
        d = bc.call("get_output", node=ids["km"], channel="Data", rows=150)["Data"]
        ci = d["head_columns"].index("Cluster")
        n = len({row[ci] for row in d["head"]})
        return n == 3, "clusters=%d (settings reached the algorithm)" % n
    step("k-Means -> 3 clusters", clusters)

    step("add Tree + Test and Score", lambda: (add("Tree", "tree") and add("Test and Score", "ts") and True, ""))
    step("link Test and Score", lambda: (
        bc.call("add_link", source=ids["file"], sink=ids["ts"], sink_channel="Data")
        and bc.call("add_link", source=ids["tree"], sink=ids["ts"], sink_channel="Learner") and True, ""))
    step("idle after Test and Score", lambda: (idle(90), ""))

    def evaluation():
        ev = bc.call("get_output", node=ids["ts"])
        return ev["Evaluation Results"]["type"] is not None, "Evaluation Results present"
    step("get_output Test and Score", evaluation)
    step("inspect_widget", lambda: (lambda r: (len(r.get("settings", [])) > 0, "%d settings" % len(r.get("settings", []))))(
        bc.call("inspect_widget", node=ids["km"])))
    step("add Scatter Plot + select_data", lambda: (add("Scatter Plot", "sc") and bc.call("add_link", source=ids["file"], sink=ids["sc"]) and idle(60) and
                                                    (lambda r: (True, json.dumps(r, ensure_ascii=False)[:120]))(
                                                        bc.call("select_data", node=ids["sc"], rows=[0, 1, 2]))))

    tmp = tempfile.mkdtemp(prefix="mcp_orange_ows_")
    ows = os.path.join(tmp, "smoke.ows")
    try:
        step("save_workflow", lambda: (bc.call("save_workflow", path=ows) and os.path.isfile(ows), ows))
        step("clear + open_workflow", lambda: (
            bc.call("clear_workflow") is not None and
            (lambda r: (r["nodes"] == len(ids), "nodes=%s" % r["nodes"]))(bc.call("open_workflow", path=ows))))
        step("idle after reload", lambda: (idle(90), ""))

        def png():
            p = os.path.join(tmp, "shot.png")
            bc.call("screenshot", target="window", path=p)
            return os.path.isfile(p) and os.path.getsize(p) > 1000, "%d bytes" % (os.path.getsize(p) if os.path.isfile(p) else 0)
        step("screenshot window", png)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    errs = bc.call("get_errors", clear=True, limit=5)
    hidden = errs.get("errors", []) if isinstance(errs, dict) else errs
    step("no hidden error dialogs", lambda: (not hidden, json.dumps(hidden, ensure_ascii=False)[:300]))
