"""여러 Orange 버전에 대해 회귀 테스트를 돌리는 러너.

각 Orange 마다
  * 임시 MCP_ORANGE_HOME / MCP_ORANGE_SETTINGS_DIR 로 격리하고(설치 폴더·사용자 데이터를 건드리지 않음),
  * QT_QPA_PLATFORM=offscreen 으로 창 없이 띄우며,
  * test_relay 가 실제 릴레이(launch_orange, 호환성 검사, WMI 기동)로 Orange 를 띄운 뒤
    나머지 테스트가 그 인스턴스에 붙는다.
--verify-readonly 를 주면 실행 전후로 Orange 설치 폴더를 스냅샷 비교한다.

    .venv\\Scripts\\python.exe tests\\matrix.py [--orange PYTHON_EXE ...] [--tests a,b] [--verify-readonly]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _paths import ROOT, OUT  # noqa: F401  (relay/ 와 저장소 루트를 sys.path 에 추가)

import snapshot_tree

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

DEFAULT_ORANGES = [r"D:\Orange3-3.32.0\Orange\python.exe", r"D:\Orange3-3.40.0\Orange\python.exe"]
FIRST = ["test_relay"]          # 릴레이로 Orange 를 띄우는 테스트 (먼저)
THEN = ["scenario_iris", "test_controls", "test_select", "test_docs", "test_dialog", "test_autodismiss"]


def install_root(py: Path) -> Path:
    return py.parent.parent if py.parent.name.lower() == "orange" else py.parent


def kill_bridge(home: Path) -> None:
    try:
        pid = json.loads((home / "bridge.json").read_text(encoding="utf-8"))["pid"]
    except (OSError, ValueError, KeyError):
        return
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    time.sleep(2)


def run_test(name: str, env: dict, timeout: int) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-B", str(Path(ROOT) / "tests" / (name + ".py"))],
                           capture_output=True, env=env, timeout=timeout, stdin=subprocess.DEVNULL)
        out = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace")
        rc = p.returncode
    except subprocess.TimeoutExpired as ex:
        out = ((ex.stdout or b"") + b"\n" + (ex.stderr or b"")).decode("utf-8", "replace") + "\nTIMEOUT"
        rc = -1
    lines = out.splitlines()
    passed = sum(1 for ln in lines if ln.startswith("PASS "))
    failed = [ln for ln in lines if ln.startswith("FAIL ")]
    return {"test": name, "rc": rc, "pass": passed, "fail": failed, "secs": round(time.time() - t0),
            "tail": "\n".join(lines[-12:])}


DIALOG = ("test_dialog", "test_autodismiss")


EXE = None   # --exe 로 지정하면 test_relay 가 배포용 exe 를 MCP 서버로 쓴다


def make_env(py: str, home: Path, offscreen: bool) -> dict:
    env = dict(os.environ, MCP_ORANGE_HOME=str(home), MCP_ORANGE_SETTINGS_DIR=str(home / "settings"),
               ORANGE_MCP_DEBUG="1", ORANGE_PYTHON=py, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    if offscreen:
        env["QT_QPA_PLATFORM"] = "offscreen"
    else:
        env.pop("QT_QPA_PLATFORM", None)
    if EXE:
        env["MCP_ORANGE_EXE"] = EXE
    return env


def launch_direct(py: str, home: Path, offscreen: bool):
    """릴레이 없이 브리지 Orange 를 직접 띄운다(창 모드 가능). 응답할 때까지 기다린다."""
    from mcp_orange_app import launcher
    os.environ["MCP_ORANGE_HOME"] = str(home)
    extra = {"MCP_ORANGE_HOME": str(home), "MCP_ORANGE_SETTINGS_DIR": str(home / "settings"), "ORANGE_MCP_DEBUG": "1"}
    if offscreen:
        extra["QT_QPA_PLATFORM"] = "offscreen"
    plan = launcher.build_plan(py, extra_env=extra, logname="matrix_direct.log")
    env_backup = os.environ.pop("QT_QPA_PLATFORM", None) if not offscreen else None
    proc = launcher.spawn(plan, detach_from_job=False)
    import bridge_client as bc
    for _ in range(150):
        try:
            bc.call("ping", timeout=5)
            return proc
        except bc.BridgeError:
            if proc.poll() is not None:
                break
            time.sleep(1)
    raise RuntimeError("Orange 가 시작되지 않았습니다: " + plan.logfile)


def run_group(py, names, offscreen, timeout, via_relay, res, label=""):
    home = Path(tempfile.mkdtemp(prefix="mcp_orange_matrix_"))
    env = make_env(py, home, offscreen)
    try:
        if not via_relay:
            launch_direct(py, home, offscreen)
        for name in names:
            r = run_test(name, env, timeout)
            r["mode"] = ("offscreen" if offscreen else "windowed")
            print("  %-18s %s  (%d pass, %d fail, %ds)%s" % (
                name, "ok  " if r["rc"] == 0 and not r["fail"] else "FAIL", r["pass"], len(r["fail"]), r["secs"], label), flush=True)
            for ln in r["fail"][:5]:
                print("      " + ln)
            res["tests"].append(r)
    finally:
        kill_bridge(home)


def run_one(py: str, tests_first, tests_then, verify: bool, timeout: int) -> dict:
    from mcp_orange_app import probe as probe_mod
    pyp = Path(py)
    res = {"python": py, "tests": [], "readonly": None}
    snap_path = None
    if verify:
        snap_path = Path(tempfile.gettempdir()) / ("matrix_snap_%s.json" % re.sub(r"[^0-9A-Za-z]", "_", str(install_root(pyp))))
        snapshot_tree.main(["save", str(install_root(pyp)), str(snap_path)])
    pr = probe_mod.probe(py)
    qt5 = pr.qt.startswith("5.")
    res["qt"] = pr.qt
    # Qt5(5.12) 는 offscreen/minimal 플랫폼에서 QMessageBox 를 띄우면 죽는다(브리지와 무관) -> 대화상자 테스트만 창 모드로.
    windowed = [t for t in list(tests_first) + list(tests_then) if t in DIALOG] if qt5 else []
    offscreen_tests = [t for t in list(tests_first) + list(tests_then) if t not in windowed]
    first = [t for t in offscreen_tests if t in tests_first]
    rest = [t for t in offscreen_tests if t not in tests_first]
    print("  (Qt %s%s)" % (pr.qt, ", 대화상자 테스트는 창 모드" if windowed else ""), flush=True)
    home = Path(tempfile.mkdtemp(prefix="mcp_orange_matrix_"))
    env = make_env(py, home, True)
    try:
        for name in first + rest:
            r = run_test(name, env, timeout)
            r["mode"] = "offscreen"
            print("  %-18s %s  (%d pass, %d fail, %ds)" % (
                name, "ok  " if r["rc"] == 0 and not r["fail"] else "FAIL", r["pass"], len(r["fail"]), r["secs"]), flush=True)
            for ln in r["fail"][:5]:
                print("      " + ln)
            res["tests"].append(r)
    finally:
        kill_bridge(home)
    if windowed:
        run_group(py, windowed, False, timeout, False, res, "  [창 모드]")
    if verify:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = snapshot_tree.main(["diff", str(install_root(pyp)), str(snap_path)])
        res["readonly"] = {"unchanged": rc == 0, "detail": buf.getvalue().strip()}
        print("  install tree: " + buf.getvalue().strip().splitlines()[0], flush=True)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orange", action="append", help="Orange 의 python.exe (여러 번 지정 가능)")
    ap.add_argument("--tests", help="쉼표 구분: 실행할 테스트만 (기본: 전체)")
    ap.add_argument("--verify-readonly", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--exe", help="배포용 mcp_orange.exe 경로: 릴레이 테스트를 이 exe 로 수행")
    a = ap.parse_args()
    global EXE
    EXE = a.exe
    oranges = a.orange or [p for p in DEFAULT_ORANGES if os.path.isfile(p)]
    first, then = FIRST, THEN
    if a.tests:
        want = [t.strip() for t in a.tests.split(",")]
        first = [t for t in FIRST if t in want]
        then = [t for t in want if t not in FIRST]
    results = []
    for py in oranges:
        print("\n=== %s" % py, flush=True)
        results.append(run_one(py, first, then, a.verify_readonly, a.timeout))
    path = Path(OUT) / "matrix_result.json"
    path.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    bad = [(r["python"], t["test"]) for r in results for t in r["tests"] if t["rc"] != 0 or t["fail"]]
    ro_bad = [r["python"] for r in results if r["readonly"] and not r["readonly"]["unchanged"]]
    print("\n결과: %s" % path)
    print("실패: %s" % (bad or "없음"))
    if a.verify_readonly:
        print("설치 폴더 변경: %s" % (ro_bad or "없음"))
    return 1 if (bad or ro_bad) else 0


if __name__ == "__main__":
    sys.exit(main())
