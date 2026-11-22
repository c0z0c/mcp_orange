r"""앱 계층(mcp_orange_app) 단위 테스트. Orange 는 필요 없다(일부는 근처에 Orange 가 있으면 추가 확인).
모든 데이터는 임시 MCP_ORANGE_HOME 에 쓰고 실제 클라이언트 설정은 건드리지 않는다."""
import os
import sys
import tempfile
from pathlib import Path

from _paths import ROOT  # noqa: F401

TMP = Path(tempfile.mkdtemp(prefix="app_test_"))
os.environ["MCP_ORANGE_HOME"] = str(TMP / "home")
os.environ.pop("ORANGE_PYTHON", None)

from mcp_orange_app import compat, config, discovery, launcher, main as app_main, paths, probe, version  # noqa: E402

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# ---- 진입점 플래그
for flag in ("--mcp-server", "--mcp_server", "-mcp_server"):
    check(flag in app_main.SERVER_FLAGS, "서버 모드 플래그 인식: " + flag)

# ---- 버전: version.txt + git 커밋 수
check(version.parse_base("0.5.0\n") == "0.5.0" and version.parse_base("﻿1.2.3") == "1.2.3", "version.txt 파싱(BOM/개행 허용)")
for bad in ("0.5", "1.2.3.4", "v1.2.3", ""):
    try:
        version.parse_base(bad)
        check(False, "잘못된 version.txt 거부: %r" % bad)
    except ValueError:
        check(True, "잘못된 version.txt 거부: %r" % bad)
vi = version.Info("0.5.0", 12, "1a2b3c4", False)
check(vi.full == "0.5.0.12" and vi.quad == (0, 5, 0, 12) and vi.display == "0.5.0.12+g1a2b3c4", "Info 표기: %s" % vi.display)
check(version.Info("0.5.0", 12, "1a2b3c4", True).display.endswith("+g1a2b3c4.dirty"), "커밋 안 한 변경은 .dirty")
check(version.Info("0.5.0", 0).display == "0.5.0.0", "커밋 없음/ git 없음 -> BUILD 0")
check(version.Info("0.5.0", 99999).quad[3] == 65535, "파일 버전 4번째 값은 65535 로 제한")
cur = version.collect()
check(cur.base == version.read_base(), "collect() 의 base == version.txt")
import subprocess as _sp  # noqa: E402
_n = _sp.run(["git", "rev-list", "--count", "HEAD"], cwd=str(paths.repo_root()), capture_output=True, text=True)
_exp = int(_n.stdout) if _n.returncode == 0 and _n.stdout.strip().isdigit() else 0
check(cur.build == _exp, "BUILD == git 커밋 수 (%d)" % _exp)
_bi = TMP / "bi.py"
version.write_buildinfo(_bi, version.Info("1.2.3", 7, "abc1234", True))
_ns = {}
exec(_bi.read_text(encoding="utf-8"), _ns)
check((_ns["BASE"], _ns["BUILD"], _ns["SHA"], _ns["DIRTY"]) == ("1.2.3", 7, "abc1234", True), "_buildinfo 기록 왕복")
check(app_main.__name__ and __import__("mcp_orange_app").__version__ == version.full(), "mcp_orange_app.__version__ == version.full()")

# ---- paths / config
check(paths.app_dir() == TMP / "home", "MCP_ORANGE_HOME 이 데이터 폴더를 바꿈")
config.save({"a": 1})
config.update(b=2)
check(config.load() == {"a": 1, "b": 2}, "config 저장/갱신 왕복")
(TMP / "home" / "config.json").write_text("{broken", encoding="utf-8")
check(config.load() == {}, "깨진 config 는 빈 설정으로 취급")
cmd, args = paths.self_launch()
check(cmd.lower().endswith(("python.exe", "python")) and args and args[0].endswith("mcp_orange.py"),
      "개발 모드의 등록 명령 = python + relay/mcp_orange.py: %s %s" % (cmd, args))


# ---- compat.judge
def fake(versions, fatal=(), warn=(), ran=True, error=""):
    r = probe.ProbeResult(python_exe="x", ran=ran, error=error, versions=versions)
    r.checks = [probe.Check(n, False, "fatal") for n in fatal] + [probe.Check(n, False, "warn") for n in warn]
    return r


v = compat.judge(fake({"Orange3": "3.40.0", "orange-canvas-core": "0.2.7", "orange-widget-base": "4.27.0"}))
check(v.status == compat.VERIFIED and v.usable, "검증된 조합 -> VERIFIED")
v = compat.judge(fake({"Orange3": "3.32.0", "orange-canvas-core": "0.1.26", "orange-widget-base": "4.16.1"}))
check(v.status == compat.VERIFIED, "3.32.0 조합도 VERIFIED")
v = compat.judge(fake({"Orange3": "3.99.0", "orange-canvas-core": "9", "orange-widget-base": "9"}))
check(v.status == compat.PROBE_OK and v.usable and "검증 목록" in v.summary, "모르는 버전 + 프로브 통과 -> PROBE_OK(사용 가능, 경고)")
v = compat.judge(fake({"Orange3": "3.40.0", "orange-canvas-core": "0.2.7", "orange-widget-base": "4.27.0"}, fatal=["CanvasMainWindow.load_scheme"]))
check(v.status == compat.INCOMPATIBLE and not v.usable and "load_scheme" in v.summary, "필수 심볼 실패 -> INCOMPATIBLE")
v = compat.judge(fake({"Orange3": "3.40.0", "orange-canvas-core": "0.2.7", "orange-widget-base": "4.27.0"}, warn=["OWFile.add_path"]))
check(v.status == compat.VERIFIED and "일부 기능 제한" in v.summary, "경고만 실패 -> VERIFIED + 제한 안내")
v = compat.judge(fake({}, ran=False, error="boom"))
check(v.status == compat.ERROR and not v.usable, "실행 실패 -> ERROR")
v = compat.judge(fake({"Orange3": None}))
check(v.status == compat.INCOMPATIBLE and "Orange3" in v.summary, "Orange 가 아닌 python -> INCOMPATIBLE")

# ---- probe: Orange 가 아닌 python 은 비호환으로 판정
res = probe.probe(sys.executable)
check(res.ran and compat.judge(res).status == compat.INCOMPATIBLE, "일반 python -> 실행은 되지만 INCOMPATIBLE")
res = probe.probe(TMP / "nope" / "python.exe")
check(not res.ran and compat.judge(res).status == compat.ERROR, "없는 python -> ERROR")

# ---- discovery
fake_root = TMP / "Orange3-9.9.9" / "Orange"
(fake_root / "Lib" / "site-packages" / "Orange").mkdir(parents=True)
(fake_root / "Lib" / "site-packages" / "orangecanvas").mkdir(parents=True)
(fake_root / "python.exe").write_bytes(b"")
check(discovery.is_orange_python(fake_root / "python.exe"), "Orange 패키지가 있는 python 을 Orange 로 인식")
check(not discovery.is_orange_python(Path(sys.executable)), "일반 python 은 Orange 아님")
os.environ["ORANGE_PYTHON"] = str(fake_root / "python.exe")
found = discovery.find_orange_pythons(scan=False)
check(found and found[0].source == "env", "ORANGE_PYTHON 이 최우선 후보")
os.environ["ORANGE_PYTHON"] = sys.executable
try:
    launcher.resolve_target()
    check(False, "잘못된 ORANGE_PYTHON 은 오류여야 함")
except launcher.LaunchError as ex:
    check("ORANGE_PYTHON" in str(ex), "잘못된 ORANGE_PYTHON -> 다른 Orange 로 대체하지 않고 오류")
os.environ.pop("ORANGE_PYTHON")

# ---- 자동 선택 우선순위: 검증됨 > 미검증, 그 안에서는 최신 버전
T = launcher.Target
cands = [T("a", compat.PROBE_OK, "", "3.99.0"), T("b", compat.VERIFIED, "", "3.32.0"), T("c", compat.VERIFIED, "", "3.40.0")]
check(max(cands, key=launcher._rank).python == "c", "검증된 것 중 최신(3.40.0)을 고름")
check(max(cands[:2], key=launcher._rank).python == "b", "미검증 최신(3.99)보다 검증된 구버전(3.32)을 우선")
check(launcher._version_key("3.9.0") < launcher._version_key("3.40.0"), "버전은 숫자로 비교(3.9 < 3.40)")

# ---- persist=False 는 설정에 아무것도 쓰지 않는다 (드라이런이 사용자 설정을 바꾸지 않게)
cfgfile = paths.config_file()
cfgfile.unlink(missing_ok=True)
os.environ["ORANGE_PYTHON"] = str(fake_root / "python.exe")      # 실행 불가능한 가짜 Orange
try:
    launcher.resolve_target(persist=False)
except launcher.LaunchError:
    pass
check(not cfgfile.exists(), "resolve_target(persist=False) 는 config.json 을 만들지 않음")
os.environ.pop("ORANGE_PYTHON")

# ---- 브리지 배포
r1 = launcher.deploy_bridge()
r2 = launcher.deploy_bridge()
check(r1 == r2 and (r1 / "orange_mcp_bridge" / "server.py").is_file(), "브리지 배포는 멱등이고 server.py 를 포함")
names = sorted(p.name for p in r1.iterdir())
check(names == [".ok", "orange_mcp_bridge"], "배포 폴더에는 브리지 패키지만 있음(-P 없이 -m 으로 실행해도 안전): %s" % names)
plan = launcher.build_plan(sys.executable)
check(plan.argv[1:5] == ["-s", "-B", "-m", "orange_mcp_bridge"] and plan.cwd == str(r1)
      and plan.env["PYTHONPATH"] == str(r1), "실행 계획: -s -B -m orange_mcp_bridge, cwd/PYTHONPATH=배포 폴더")
check("-P" not in plan.argv, "Python 3.8 호환: -P 를 쓰지 않음")
os.environ["MCP_ORANGE_SETTINGS_DIR"] = "X"
check(launcher.build_plan(sys.executable).env.get("MCP_ORANGE_SETTINGS_DIR") == "X", "격리 환경변수를 Orange 로 전달")
os.environ.pop("MCP_ORANGE_SETTINGS_DIR")

# ---- 브리지 소스는 구버전 Python 문법을 지킨다 (3.8 에서 컴파일돼야 함)
import ast  # noqa: E402
for f in sorted((ROOT_P := Path(ROOT) / "orange_mcp_bridge").glob("*.py")):
    try:
        ast.parse(f.read_text(encoding="utf-8"), feature_version=(3, 8))
        ok = True
    except SyntaxError as ex:
        ok = False
        print("   ", f.name, ex)
    check(ok, "Python 3.8 문법: " + f.name)

# ---- 새 버전 확인/업그레이드 (네트워크 없이: update._open 을 가짜로 바꾼다)
import io  # noqa: E402
import json  # noqa: E402
import urllib.error  # noqa: E402
from mcp_orange_app import update  # noqa: E402

check(update.parse_version("v0.5.0.3") == (0, 5, 0, 3) and update.parse_version("1.2.3") == (1, 2, 3, 0), "태그 파싱 (v 접두, 3자리는 BUILD 0)")
check(update.parse_version("0.5.0.10") > update.parse_version("0.5.0.9"), "버전은 숫자로 비교 (10 > 9)")
for bad in ("latest", "1.2", "1.2.x"):
    try:
        update.parse_version(bad)
        check(False, "잘못된 태그 거부: " + bad)
    except ValueError:
        check(True, "잘못된 태그 거부: " + bad)

PAYLOAD = b"MZ" + b"x" * 5000
URL = update.DOWNLOAD_PREFIX + "v9.0.0.1/mcp_orange.exe"


class FakeRes(io.BytesIO):
    def __init__(self, data, url="https://github.com/x"):
        super().__init__(data)
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def release(tag="v9.0.0.1", url=URL, name="mcp_orange.exe"):
    return json.dumps({"tag_name": tag, "html_url": "https://github.com/page",
                       "assets": [{"name": name, "browser_download_url": url, "size": len(PAYLOAD)}]}).encode()


def fake_open(api, blob=PAYLOAD, final_url="https://objects.example/x"):
    return lambda u: FakeRes(api if u == update.LATEST_API else blob, final_url)


_orig = update._open
update._open = fake_open(release())
info = update.check(current="0.5.0.2")
check(info.newer and info.version == "9.0.0.1" and info.url == URL, "새 버전 감지")
check(not update.check(current="9.0.0.1").newer and not update.check(current="9.0.0.7").newer, "같거나 높으면 업데이트 없음")
update._open = fake_open(release(url="https://evil.example/mcp_orange.exe"))
check(not update.check(current="0.5.0.2").newer, "다른 도메인의 다운로드 주소는 거부")
update._open = fake_open(release(name="other.exe"))
check(not update.check(current="0.5.0.2").newer, "mcp_orange.exe 가 아닌 자산은 무시")
update._open = fake_open(b"not json")
try:
    update.check()
    check(False, "깨진 응답은 UpdateError")
except update.UpdateError:
    check(True, "깨진 응답은 UpdateError")


def boom(_u):
    raise urllib.error.URLError("offline")


update._open = boom
try:
    update.check()
    check(False, "오프라인은 UpdateError")
except update.UpdateError as ex:
    check("확인하지 못했습니다" in str(ex), "오프라인은 UpdateError")

# 교체: 성공
fake_exe = TMP / "bin" / "mcp_orange.exe"
fake_exe.parent.mkdir()
fake_exe.write_bytes(b"MZ-old")
update._open = fake_open(release())
good = update.check(current="0.5.0.2")
update.install(good, exe=fake_exe)
check(fake_exe.read_bytes() == PAYLOAD, "업그레이드: 새 파일로 교체")
check((fake_exe.parent / update.OLD_NAME).read_bytes() == b"MZ-old" and not (fake_exe.parent / update.NEW_NAME).exists(),
      "이전 exe 는 _del.tmp 로 보관, 임시 파일 없음")
# 남은 _del.tmp 정리: 이전 exe 로 뜬 프로세스가 쓰는 동안(잠김)은 못 지우고, 풀리면 지운다
import threading  # noqa: E402
import time  # noqa: E402
from mcp_orange_app import housekeeping  # noqa: E402

lk_dir = TMP / "locked"
lk_dir.mkdir()
lk_exe = lk_dir / "mcp_orange.exe"
lk_exe.write_bytes(b"MZ-new")
lk_old = lk_dir / update.OLD_NAME
lk_old.write_bytes(b"MZ-old")
_saved = (getattr(sys, "frozen", None), sys.executable, housekeeping.cleanup_stale_extractions, housekeeping.RETRY_SECONDS)
sys.frozen, sys.executable = True, str(lk_exe)
housekeeping.cleanup_stale_extractions = lambda: 0          # 실제 %TEMP%\_MEI* 는 건드리지 않는다
housekeeping.RETRY_SECONDS = 0.2
try:
    holder = open(lk_old, "rb")                               # 이전 exe 를 실행 중인 프로세스 흉내(삭제 거부)
    update.cleanup_leftovers(wait=0)
    check(lk_old.exists() and update.leftovers_exist(), "이전 프로세스가 쓰는 동안 _del.tmp 는 남고 예외도 없다")
    t = threading.Thread(target=housekeeping._cleanup_all, daemon=True)
    t.start()
    time.sleep(0.6)
    check(t.is_alive() and lk_old.exists(), "잠겨 있는 동안 정리 스레드는 계속 재시도한다")
    holder.close()                                            # 이전 프로세스 종료
    t.join(5)
    check(not t.is_alive() and not lk_old.exists(), "잠금이 풀리면 _del.tmp 를 지우고 스레드가 끝난다")
    lk_old.write_bytes(b"MZ-old")
    update.cleanup_leftovers(wait=0)
    check(not lk_old.exists() and not update.leftovers_exist(), "wait=0 이어도 잠기지 않았으면 바로 지운다")
finally:
    if _saved[0] is None:
        del sys.frozen
    else:
        sys.frozen = _saved[0]
    sys.executable, housekeeping.cleanup_stale_extractions, housekeeping.RETRY_SECONDS = _saved[1:]
# 업그레이드 승인 = 옛 exe 로 실행 중인 다른 프로세스(AI 클라이언트가 띄운 서버)를 강제 종료한다
if sys.platform == "win32":
    import shutil  # noqa: E402
    kill_dir = TMP / "killold"
    kill_dir.mkdir()
    kill_exe = kill_dir / "mcp_orange.exe"
    shutil.copy(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "PING.EXE"), kill_exe)
    olds = [_sp.Popen([str(kill_exe), "-n", "120", "127.0.0.1"], stdout=_sp.DEVNULL) for _ in range(2)]
    other = _sp.Popen([sys.executable, "-c", "import time; time.sleep(60)"])      # 다른 exe 는 건드리면 안 된다
    time.sleep(0.5)
    try:
        update._open = fake_open(release())
        n = update.install(update.check(current="0.5.0.2"), exe=kill_exe)
        time.sleep(0.3)
        check(n == 2 and all(p.poll() is not None for p in olds), "업그레이드: 옛 exe 로 실행 중인 프로세스를 모두 종료 (%s개)" % n)
        check(other.poll() is None, "업그레이드: 다른 프로그램은 종료하지 않는다")
        check(kill_exe.read_bytes() == PAYLOAD, "업그레이드: 새 exe 로 교체됨")
        (kill_dir / update.OLD_NAME).unlink()
        check(not (kill_dir / update.OLD_NAME).exists(), "옛 프로세스가 끝나 _del.tmp 의 잠금이 풀려 삭제된다")
        # 실행 중인 서버가 없으면 종료할 것도 없다
        update._open = fake_open(release())
        check(update.install(update.check(current="0.5.0.2"), exe=kill_exe) == 0, "실행 중인 옛 프로세스가 없으면 0개")
    finally:
        for p in olds + [other]:
            if p.poll() is None:
                p.kill()
# 교체: 크기 불일치(잘린 다운로드) -> 원본 유지
fake_exe.write_bytes(b"MZ-keep")
update._open = fake_open(release(), blob=b"MZ" + b"x" * 100)
try:
    update.install(good, exe=fake_exe)
    check(False, "크기 불일치는 거부")
except update.UpdateError as ex:
    check("크기" in str(ex) and fake_exe.read_bytes() == b"MZ-keep", "크기 불일치 -> 거부, 기존 exe 그대로")
check(not (fake_exe.parent / update.NEW_NAME).exists(), "실패해도 임시 파일은 남지 않음")
# 교체: 실행 파일이 아닌 내용 / http 리다이렉트
update._open = fake_open(release(), blob=b"<html>")
try:
    update.install(good, exe=fake_exe)
    check(False, "비실행 파일 거부")
except update.UpdateError:
    check(fake_exe.read_bytes() == b"MZ-keep", "MZ 헤더가 아니면 거부, 기존 exe 그대로")
update._open = fake_open(release(), final_url="http://insecure.example/x")
try:
    update.install(good, exe=fake_exe)
    check(False, "http 리다이렉트 거부")
except update.UpdateError:
    check(fake_exe.read_bytes() == b"MZ-keep", "https 가 아닌 최종 주소는 거부")
try:
    update.install(update.UpdateInfo(version="1"))
    check(False, "받을 게 없으면 오류")
except update.UpdateError:
    check(True, "받을 업데이트가 없으면 오류")
try:
    update.install(good)       # 소스(비 frozen) 실행에서는 자기 자신을 교체하지 않는다
    check(False, "소스 실행에서는 교체 거부")
except update.UpdateError:
    check(True, "소스 실행에서는 교체 거부")
update._open = _orig

print("\nFAILS:", fails if fails else "none")
sys.exit(1 if fails else 0)
