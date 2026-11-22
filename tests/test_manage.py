"""mcp_manage (등록/해지) 테스트. Orange 가 필요 없고, 실제 클라이언트 설정은 건드리지 않는다
(모든 경로를 임시 폴더로 돌리고 claude/codex CLI 는 가짜로 바꾼다)."""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="mcp_manage_test_"))
for k, v in {"USERPROFILE": TMP / "home", "HOME": TMP / "home", "LOCALAPPDATA": TMP / "local",
             "APPDATA": TMP / "roaming", "CLAUDE_CONFIG_DIR": TMP / "home",
             "CODEX_HOME": TMP / "home" / ".codex"}.items():
    os.environ[k] = str(v)
os.environ.pop("CLAUDE_DESKTOP_CONFIG", None)

from mcp_manage import clients as C  # noqa: E402
from mcp_manage import cli  # noqa: E402

failed = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))
    if not cond:
        failed.append(name)


def make_root(base: Path) -> C.ServerSpec:
    (base / ".venv" / "Scripts").mkdir(parents=True)
    (base / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    (base / ".venv" / "Lib" / "site-packages" / "mcp").mkdir(parents=True)
    (base / "relay").mkdir()
    (base / "relay" / "mcp_orange.py").write_text("")
    return C.ServerSpec("orange3", str(base / ".venv" / "Scripts" / "python.exe"),
                        (str(base / "relay" / "mcp_orange.py"),))


spec = make_root(TMP / "proj")
lines = []
say = lines.append

# --- 가짜 CLI -------------------------------------------------------------------
calls = []
fake_cfg = {"claude": {}, "codex": {}}


def fake_run(argv):
    calls.append(argv)
    client = Path(argv[0]).stem
    verb, name = argv[2], None
    if verb == "add":
        name = argv[argv.index("--") - 1]
        fake_cfg[client][name] = C.Launch(argv[argv.index("--") + 1], tuple(argv[argv.index("--") + 2:]))
    elif verb == "remove":
        fake_cfg[client].pop(argv[-1], None)
    return 0, ""


C.which = lambda n: f"C:\\fake\\{n}.exe" if n in ("claude", "codex") else None
C.run_process = fake_run
orig_read_all = C.read_all


def read_all_fake(client, store=""):
    if client in fake_cfg:
        return dict(fake_cfg[client])
    return orig_read_all(client, store)


C.read_all = read_all_fake

# 1. JSON 클라이언트(Antigravity): 다른 항목 보존 --------------------------------------
agy = Path(C._agy_file())
agy.parent.mkdir(parents=True)
agy.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x", "args": ["1"]}}}))
rc = C.run_action(spec, "install", ["antigravity"], say=say)
d = json.loads(agy.read_text(encoding="utf-8"))
check("agy install rc=0", rc == 0, lines)
check("agy entry written", d["mcpServers"]["orange3"] == {"command": spec.command, "args": [spec.args[0]]}, d)
check("agy other server kept", d["mcpServers"]["other"] == {"command": "x", "args": ["1"]}, d)
check("agy other key kept", d.get("theme") == "dark", d)
check("agy backup made", Path(C.backup_file(str(agy))).is_file())
check("agy no BOM / tmp left", not agy.read_bytes().startswith(b"\xef\xbb\xbf") and not Path(str(agy) + ".tmp").exists())

lines.clear()
rc = C.run_action(spec, "install", ["antigravity"], say=say)
check("install twice is a no-op", rc == 0 and any("건너뜀" in l for l in lines), lines)

# 2. 경로가 달라진 우리 항목은 교체 ------------------------------------------------------
old = make_root(TMP / "old_proj")
d = json.loads(agy.read_text(encoding="utf-8"))
d["mcpServers"]["orange3"] = {"command": old.command, "args": [old.args[0]]}
agy.write_text(json.dumps(d))
st = C.analyze(spec, "antigravity", "", 1)
check("stale state detected", st.state == C.STALE, st.state)
lines.clear()
rc = C.run_action(spec, "install", ["antigravity"], say=say)
d = json.loads(agy.read_text(encoding="utf-8"))
check("stale path replaced without --force", rc == 0 and d["mcpServers"]["orange3"]["args"] == [spec.args[0]], (rc, d, lines))

# 3. 이름만 같은 남의 설정은 --force 없이 건드리지 않음 --------------------------------------
d["mcpServers"]["orange3"] = {"command": "node", "args": ["theirs.js"]}
agy.write_text(json.dumps(d))
lines.clear()
rc = C.run_action(spec, "install", ["antigravity"], say=say)
check("foreign refused (rc=1)", rc == 1, lines)
check("foreign untouched", json.loads(agy.read_text())["mcpServers"]["orange3"]["command"] == "node")
lines.clear()
rc = C.run_action(spec, "uninstall", ["antigravity"], say=say)
check("foreign uninstall refused", rc == 1 and json.loads(agy.read_text())["mcpServers"]["orange3"]["command"] == "node", lines)
rc = C.run_action(spec, "install", ["antigravity"], force=True, say=say)
check("--force replaces foreign", rc == 0 and json.loads(agy.read_text())["mcpServers"]["orange3"]["command"] == spec.command)

# 4. dry-run 은 파일을 바꾸지 않음 / 중복(다른 이름의 우리 것) 정리 ----------------------------------
d = json.loads(agy.read_text())
d["mcpServers"]["orange"] = {"command": old.command, "args": [old.args[0]]}
agy.write_text(json.dumps(d))
before = agy.read_text()
lines.clear()
C.run_action(spec, "install", ["antigravity"], dry_run=True, say=say)
check("dry-run changes nothing", agy.read_text() == before and any("dry-run" in l for l in lines), lines)
lines.clear()
C.run_action(spec, "install", ["antigravity"], say=say)
d = json.loads(agy.read_text())
check("duplicate removed", "orange" not in d["mcpServers"] and "orange3" in d["mcpServers"], d)

# 5. 해지: 우리 것만 지우고 남의 것은 보존 ---------------------------------------------------
rc = C.run_action(spec, "uninstall", ["antigravity"], say=say)
d = json.loads(agy.read_text())
check("uninstall removes ours only", rc == 0 and "orange3" not in d["mcpServers"] and "other" in d["mcpServers"], d)
lines.clear()
rc = C.run_action(spec, "uninstall", ["antigravity"], say=say)
check("uninstall when absent is a no-op", rc == 0 and any("등록되어 있지 않습니다" in l for l in lines), lines)

# 6. Claude Desktop: Store 판 + 일반 설치판 두 저장소 ---------------------------------------------
pkg = TMP / "local" / "Packages" / "Claude_abc123" / "LocalCache" / "Roaming" / "Claude"
pkg.mkdir(parents=True)
plain_dir = TMP / "roaming" / "Claude"
plain_dir.mkdir(parents=True)
(plain_dir / "claude_desktop_config.json").write_text(json.dumps({"mcpServers": {}, "x": 1}))
check("two stores found", len(C.stores("claude-desktop")) == 2, C.stores("claude-desktop"))
lines.clear()
rc = C.run_action(spec, "install", ["claude-desktop"], say=say)
files = C.stores("claude-desktop")
ok = all("orange3" in json.loads(Path(f).read_text())["mcpServers"] for f in files)
check("desktop registered in both stores", rc == 0 and ok, lines)
check("desktop labels distinguish stores", any("Store" in l for l in lines) and any("일반" in l for l in lines), lines)
check("desktop other key kept", json.loads((plain_dir / "claude_desktop_config.json").read_text())["x"] == 1)
rc = C.run_action(spec, "uninstall", ["claude-desktop"], say=say)
check("desktop removed from both", rc == 0 and not any(
    "orange3" in json.loads(Path(f).read_text())["mcpServers"] for f in files))

# 데이터가 Claude-Data 로 옮겨 간 Store 판은 새 위치를 쓴다
moved = TMP / "local" / "Claude-Data" / "claude_abc123"
moved.mkdir(parents=True)
(pkg / ".user-data-left.claude_abc123").write_text("")
live = C._desktop_layout()[0]
check("relocated store dir used", any(str(moved) in f for f in live) and not any(str(pkg) in f for f in live), live)

# 7. CLI 로 등록하는 클라이언트(Claude, Codex) --------------------------------------------------
calls.clear()
lines.clear()
rc = C.run_action(spec, "install", ["claude", "codex"], say=say)
check("claude add argv", any(c[1:5] == ["mcp", "add", "--scope", "user"] and c[5] == "orange3"
                             and c[6] == "--" and c[7:] == [spec.command, spec.args[0]]
                             for c in calls if "claude" in c[0]), calls)
check("codex add argv (no --scope)", any(c[1:4] == ["mcp", "add", "orange3"] and "--scope" not in c
                                         for c in calls if "codex" in c[0]), calls)
check("cli install rc=0", rc == 0, lines)
calls.clear()
C.run_action(spec, "install", ["claude"], say=say)
check("claude install again does not re-add", not calls, calls)
rc = C.run_action(spec, "uninstall", ["claude", "codex"], say=say)
check("cli uninstall calls remove", sum(1 for c in calls if c[2] == "remove") == 2 and rc == 0, calls)
check("fake configs emptied", not fake_cfg["claude"] and not fake_cfg["codex"], fake_cfg)

# 8. Codex config.toml 읽기와 프로젝트 범위 알림 -------------------------------------------------
C.read_all = orig_read_all
proj = TMP / "somewhere"
(proj / ".codex").mkdir(parents=True)
(proj / ".codex" / "config.toml").write_text(
    f'[mcp_servers.orange3]\ncommand = "{spec.command.replace(chr(92), "/")}"\nargs = ["{spec.args[0].replace(chr(92), "/")}"]\n')
cfg = Path(C._codex_file())
cfg.parent.mkdir(parents=True, exist_ok=True)
cfg.write_text(f"model = 'x'\n[projects.'{proj}']\ntrust_level = 'trusted'\n"
               "[mcp_servers.keep]\ncommand = 'k'\nargs = [\n  'a',\n  'b',\n]\n")
got = C.read_all("codex")
check("toml multi-line args parsed", got.get("keep") == C.Launch("k", ("a", "b")), got)
sh = C.shadow_entries("codex")
check("codex project-scope shadow reported", any(n == "orange3" for _w, n, _l in sh), sh)
buf = []
C.warn_shadow(spec, "codex", buf.append)
check("shadow warning printed", any("주의" in b for b in buf), buf)

# 9. 서버 파일이 없으면 등록 거부, --force 면 진행 ----------------------------------------------------
bad = C.ServerSpec("orange3", str(TMP / "none" / "python.exe"), (str(TMP / "none" / "relay" / "mcp_orange.py"),))
lines.clear()
rc = C.run_action(bad, "install", ["antigravity"], say=say)
check("missing server files refuse install", rc == 1 and "orange3" not in json.loads(agy.read_text())["mcpServers"], lines)
check("problems() lists reasons", len(bad.problems()) >= 2, bad.problems())

# 10. 깨진 JSON 은 덮어쓰지 않고 오류 -----------------------------------------------------------------
agy.write_text("{ not json")
lines.clear()
rc = C.run_action(spec, "install", ["antigravity"], say=say)
check("broken json not overwritten", rc == 1 and agy.read_text() == "{ not json" and any("실패" in l for l in lines), lines)

# 11. CLI 진입점 -------------------------------------------------------------------------------------
agy.write_text("{}")
out = io.StringIO()
real = sys.stdout
sys.stdout = out
try:
    rc1 = cli.main(["status", "--json", "--client", "antigravity"])
finally:
    sys.stdout = real
j = json.loads(out.getvalue())
check("status --json", rc1 == 0 and j["clients"][0]["state"] == "absent", out.getvalue())
try:
    cli.main(["install", "--client", "nope"])
    check("unknown client rejected", False)
except SystemExit as e:
    check("unknown client rejected", "알 수 없는 클라이언트" in str(e))

print(f"\n{'ALL PASSED' if not failed else 'FAILED: ' + ', '.join(failed)}")
sys.exit(1 if failed else 0)
