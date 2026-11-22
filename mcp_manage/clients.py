"""AI 클라이언트(Claude, Claude Desktop, Codex/ChatGPT, Antigravity)의 MCP 서버 등록을 읽고 고친다.

표준 라이브러리만 쓴다.

* Claude          : `claude mcp add/remove --scope user` (설정 파일 ~/.claude.json 은 직접 고치지 않고 읽기만 한다)
* Codex / ChatGPT : `codex mcp add/remove` (설정 ~/.codex/config.toml 은 읽기만. ChatGPT 데스크톱 앱과 공유)
* Claude Desktop  : claude_desktop_config.json 을 직접 고친다 (Microsoft Store 판과 일반 설치판은 파일이 따로다)
* Antigravity     : ~/.gemini/config/mcp_config.json 을 직접 고친다

JSON 파일을 고칠 때는 다른 항목을 그대로 두고, 백업을 %LOCALAPPDATA%\\mcp_orange\\backup 에 파일마다 하나만 남기며,
임시 파일에 쓴 뒤 교체한다. 환경 변수(USERPROFILE/HOME, CLAUDE_CONFIG_DIR, CODEX_HOME, CLAUDE_DESKTOP_CONFIG,
LOCALAPPDATA, APPDATA)를 따르므로 테스트에서 임시 폴더를 가리킬 수 있다.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

CLIENTS = ("claude", "claude-desktop", "codex", "antigravity")
LABELS = {"claude": "Claude", "claude-desktop": "Claude Desktop",
          "codex": "Codex/ChatGPT", "antigravity": "Antigravity"}

ABSENT, SAME, STALE, FOREIGN = "absent", "same", "stale", "foreign"
STATE_TEXT = {
    ABSENT: "등록 안 됨",
    SAME: "등록됨",
    STALE: "등록됨 (경로가 다름 - 재등록 필요)",
    FOREIGN: "같은 이름의 다른 설정이 있음",
}


class ClientError(Exception):
    """클라이언트 설정을 읽거나 바꾸지 못했을 때."""


# ------------------------------------------------------------------ 값 객체
def _norm(p: str) -> str:
    if "\\" in p or "/" in p:
        try:
            return os.path.normcase(os.path.abspath(p))
        except (OSError, ValueError):
            return p.replace("/", "\\").lower()
    return p


@dataclass(frozen=True)
class Launch:
    """클라이언트가 MCP 서버를 띄울 때 쓰는 명령과 인자."""
    command: str
    args: tuple = ()

    def key(self) -> str:
        return _norm(self.command) + "\x01" + "\x01".join(_norm(a) for a in self.args)

    def display(self) -> str:
        return " ".join((self.command, *self.args)).strip()

    def dead(self) -> bool:
        """명령이 경로인데 그 파일이 없으면 True (죽은 항목)."""
        return ("\\" in self.command or "/" in self.command) and not os.path.isfile(self.command)


@dataclass
class ServerSpec:
    r"""등록할 서버 하나. 실행 명령은 두 가지 형태다.

    * 배포판:  mcp_orange.exe --mcp-server
    * 개발:    .venv\Scripts\python.exe relay\mcp_orange.py
    """
    name: str
    command: str
    args: tuple = ()

    def launch(self) -> Launch:
        return Launch(self.command, tuple(self.args))

    def _script(self) -> Optional[str]:
        for a in self.args:
            if a.lower().endswith(".py"):
                return a
        return None

    def is_ours(self, entry: Launch) -> bool:
        r"""등록된 항목이 이 서버를 가리키는지. 경로가 달라도(폴더를 옮김) mcp_orange.exe 나
        relay\mcp_orange.py 면 우리 것이다."""
        if Path(entry.command).stem.lower() == "mcp_orange":
            return True
        for a in entry.args:
            try:
                parts = os.path.normcase(os.path.abspath(a)).replace("/", "\\").split("\\")
            except (OSError, ValueError):
                continue
            if len(parts) >= 2 and parts[-1] == "mcp_orange.py" and parts[-2] == "relay":
                return True
        return False

    def problems(self) -> list[str]:
        """등록해도 클라이언트가 서버를 띄울 수 없는 이유들."""
        out = []
        script = self._script()
        if not os.path.isfile(self.command):
            out.append(f"실행 파일이 없습니다: {self.command}")
        elif script is not None:  # 개발 모드: python 에 mcp 패키지가 있는 venv 여야 한다
            site = Path(self.command).parents[1] / "Lib" / "site-packages"
            alt = Path(self.command).parents[1] / "lib"
            if not ((site / "mcp").is_dir() or any(alt.glob("python*/site-packages/mcp"))):
                out.append("relay 용 venv 에 mcp 패키지가 없습니다 (pip install -r relay\requirements.txt)")
        if script is not None and not os.path.isfile(script):
            out.append(f"relay 스크립트가 없습니다: {script}")
        return out


def default_spec(name: str = "orange3") -> ServerSpec:
    from mcp_orange_app import paths  # 지연 import: 등록 도구 자체는 앱 계층 없이도 import 된다
    command, args = paths.self_launch()
    return ServerSpec(name=name, command=command, args=tuple(args))


# ------------------------------------------------------- 훅 (테스트에서 바꿔 끼움)
which: Callable[[str], Optional[str]] = lambda n: shutil.which(n)


def _default_run(argv: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ClientError(f"{argv[0]} 실행 실패: 60초 안에 끝나지 않았습니다") from None
    except OSError as e:
        raise ClientError(f"{argv[0]} 실행 실패: {e}") from None
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


run_process: Callable[[list[str]], tuple[int, str]] = _default_run


# ----------------------------------------------------------------- 경로와 감지
def _env(name: str, fallback: str) -> str:
    return os.environ.get(name) or fallback


def home() -> str:
    return os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home())


def _local() -> str:
    return _env("LOCALAPPDATA", os.path.join(home(), "AppData", "Local"))


def _claude_file() -> str:
    return os.path.join(_env("CLAUDE_CONFIG_DIR", home()), ".claude.json")


def _codex_file() -> str:
    return os.path.join(_env("CODEX_HOME", os.path.join(home(), ".codex")), "config.toml")


def _agy_file() -> str:
    return os.path.join(home(), ".gemini", "config", "mcp_config.json")


def _glob(pattern: str) -> list[str]:
    try:
        return sorted(glob.glob(pattern))
    except OSError:
        return []


def _relocated_dir(pkg: str, legacy_dir: str) -> Optional[str]:
    """새 Store 판 Claude Desktop 은 사용자 데이터를 %LOCALAPPDATA%\\Claude-Data\\<패키지 소문자> 로 옮긴다."""
    names = []
    for marker in _glob(os.path.join(legacy_dir, ".user-data-left.*")):
        n = os.path.basename(marker)[len(".user-data-left."):]
        if n:
            names.append(n)
    names.append(os.path.basename(pkg).lower())
    for n in names:
        d = os.path.join(_local(), "Claude-Data", n)
        if os.path.isdir(d):
            return d
    return None


def _desktop_layout() -> tuple[list[str], list[str]]:
    """(Live: 앱이 실제로 읽는 설정 파일들, Orphans: 데이터가 옮겨 가 더는 읽히지 않는 옛 파일)."""
    over = os.environ.get("CLAUDE_DESKTOP_CONFIG")
    if over:
        return [over], []
    live, orphans = [], []
    for pkg in _glob(os.path.join(_local(), "Packages", "Claude_*")):
        legacy = os.path.join(pkg, "LocalCache", "Roaming", "Claude")
        moved = _relocated_dir(pkg, legacy)
        if moved:
            live.append(os.path.join(moved, "claude_desktop_config.json"))
            old = os.path.join(legacy, "claude_desktop_config.json")
            if os.path.isfile(old):
                orphans.append(old)
        elif os.path.isdir(legacy):
            live.append(os.path.join(legacy, "claude_desktop_config.json"))
    roaming = os.path.join(_env("APPDATA", os.path.join(home(), "AppData", "Roaming")), "Claude")
    plain = os.path.join(roaming, "claude_desktop_config.json")
    if not live or os.path.isfile(plain):
        live.append(plain)
    return live, orphans


def _json_files_of(client: str) -> list[str]:
    if client == "antigravity":
        return [_agy_file()]
    if client == "claude-desktop":
        return _desktop_layout()[0]
    return []


def _extra_cli_paths(client: str) -> list[str]:
    h = home()
    appdata = _env("APPDATA", os.path.join(h, "AppData", "Roaming"))
    local = _local()
    ext = os.path.join(h, ".vscode", "extensions")
    found: list[str] = []
    if client == "claude":
        found.append(os.path.join(h, ".local", "bin", "claude.exe"))
        found.append(os.path.join(appdata, "npm", "claude.cmd"))
        for d in reversed(_glob(os.path.join(ext, "anthropic.claude-code-*"))):
            found.append(os.path.join(d, "resources", "native-binary", "claude.exe"))
    else:
        found.append(os.path.join(appdata, "npm", "codex.cmd"))
        for d in _glob(os.path.join(local, "OpenAI", "Codex", "bin", "*")):
            found.append(os.path.join(d, "codex.exe"))
        for d in reversed(_glob(os.path.join(ext, "openai.chatgpt-*"))):
            for w in _glob(os.path.join(d, "bin", "windows-*")):
                found.append(os.path.join(w, "codex.exe"))
    return [p for p in found if os.path.isfile(p)]


def find_cli(client: str) -> Optional[str]:
    exe = which(client)
    if exe:
        return exe
    extra = _extra_cli_paths(client)
    return extra[0] if extra else None


def detect(client: str) -> bool:
    """클라이언트가 설치되어 있는지(CLI 가 있거나 설정 폴더가 있는지)."""
    if client == "claude":
        return find_cli("claude") is not None or os.path.isfile(_claude_file())
    if client == "codex":
        return find_cli("codex") is not None
    if client == "claude-desktop":
        return any(os.path.isdir(os.path.dirname(f)) for f in _json_files_of(client))
    gemini = os.path.join(home(), ".gemini")
    return (any(which(n) for n in ("agy", "antigravity"))
            or os.path.isdir(os.path.join(gemini, "antigravity"))
            or os.path.isfile(_agy_file()))


def stores(client: str) -> list[str]:
    """등록 저장소 목록. 설정 JSON 이 여러 개일 수 있는 Claude Desktop 은 파일마다 하나, 나머지는 [""]."""
    files = _json_files_of(client)
    return files or [""]


def store_label(client: str, store: str) -> str:
    if not store:
        return ""
    if client == "claude-desktop":
        low = store.lower()
        return "Microsoft Store 판" if ("\\packages\\" in low or "\\claude-data\\" in low) else "일반 설치판"
    return store


def who(client: str, store: str, store_count: int) -> str:
    label = LABELS[client]
    return f"{label} [{store_label(client, store)}]" if store_count > 1 else label


# ----------------------------------------------------------------------- 읽기
def _read_json(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ClientError(f"{path} 를 읽을 수 없습니다: {e}") from None
    return data if isinstance(data, dict) else {}


def _launch_of(entry: dict) -> Launch:
    cmd = entry.get("command")
    args = entry.get("args")
    return Launch(str(cmd) if cmd is not None else "",
                  tuple(str(a) for a in args) if isinstance(args, list) else ())


def _servers_of_json(data: dict) -> dict[str, Launch]:
    ms = data.get("mcpServers")
    if not isinstance(ms, dict):
        return {}
    return {k: _launch_of(v) for k, v in ms.items() if isinstance(v, dict)}


def _servers_of_toml(path: str) -> dict[str, Launch]:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ClientError(f"{path} 를 읽을 수 없습니다: {e}") from None
    ms = data.get("mcp_servers")
    if not isinstance(ms, dict):
        return {}
    return {k: _launch_of(v) for k, v in ms.items() if isinstance(v, dict)}


def read_all(client: str, store: str = "") -> dict[str, Launch]:
    """한 저장소에 등록된 모든 항목(이름 -> 실행 방법). 설정 파일이 깨졌으면 ClientError."""
    if client == "codex":
        p = _codex_file()
        return _servers_of_toml(p) if os.path.isfile(p) else {}
    if client == "claude":
        return _servers_of_json(_read_json(_claude_file()))
    return _servers_of_json(_read_json(store or _json_files_of(client)[0]))


def shadow_entries(client: str) -> list[tuple[str, str, Launch]]:
    """사용자 범위 밖의 등록(Claude 의 로컬/프로젝트 범위와 .mcp.json, Codex 의 프로젝트 .codex/config.toml).
    같은 이름이면 사용자 범위보다 우선하므로 알려 주는 용도다. 읽기 전용."""
    found: list[tuple[str, str, Launch]] = []
    if client == "codex":
        cfg = _codex_file()
        if not os.path.isfile(cfg):
            return found
        try:
            with open(cfg, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return found
        for m in re.finditer(r"""^\[projects\.(?:'([^']+)'|"([^"]+)")\]""", text, re.M):
            d = (m.group(1) or m.group(2)).replace("\\\\?\\", "")
            f2 = os.path.join(d, ".codex", "config.toml")
            try:
                if os.path.isfile(f2):
                    for k, v in _servers_of_toml(f2).items():
                        found.append((f"{f2} (프로젝트 범위)", k, v))
            except (ClientError, OSError, ValueError):
                continue
        return found
    if client != "claude":
        return found
    try:
        projects = _read_json(_claude_file()).get("projects")
        if not isinstance(projects, dict):
            return found
        for path, proj in projects.items():
            if isinstance(proj, dict):
                for k, v in _servers_of_json(proj).items():
                    found.append((f"{path} (로컬 범위)", k, v))
            try:
                mcp_json = os.path.join(path, ".mcp.json")
                if os.path.isfile(mcp_json):
                    for k, v in _servers_of_json(_read_json(mcp_json)).items():
                        found.append((f"{mcp_json} (프로젝트 범위)", k, v))
            except (ClientError, ValueError, OSError):
                continue
    except ClientError:
        pass
    return found


# ----------------------------------------------------------------------- 쓰기
def backup_file(path: str) -> str:
    """설정 파일 백업 위치: %LOCALAPPDATA%\\mcp_orange\\backup\\<파일>.<경로 해시>.bak (파일마다 하나, 덮어씀)."""
    h = hashlib.sha1(os.path.abspath(path).lower().encode("utf-8")).hexdigest()[:8]
    return os.path.join(_local(), "mcp_orange", "backup", f"{os.path.basename(path)}.{h}.bak")


def _backup(path: str) -> None:
    try:
        dest = backup_file(path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
    except OSError:
        pass  # 백업은 선택 사항


def _replace_with_retry(tmp: str, path: str) -> None:
    # 클라이언트가 설정 변경을 감지해 잠깐 파일을 잡으면 교체가 실패하므로 풀릴 때까지 다시 시도한다.
    for i in range(1, 21):
        try:
            os.replace(tmp, path)
            return
        except OSError:
            if i == 20:
                raise
            time.sleep(0.15)


def _json_write(path: str, mutate: Callable[[dict], None]) -> None:
    """JSON 설정을 백업 후 원자적으로 고친다. mutate 는 mcpServers 사전을 제자리에서 바꾼다."""
    data = _read_json(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    mutate(servers)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        _backup(path)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        _replace_with_retry(tmp, path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ClientError(
            f"{path} 를 고칠 수 없습니다: {e} / 다른 프로그램이 파일을 사용 중일 수 있습니다. "
            "해당 클라이언트를 종료하고 다시 시도하세요") from None


def _clean_desktop_orphans(name: str) -> None:
    """옮겨 가서 더는 읽히지 않는 옛 Store 판 설정 파일에서 우리가 예전에 써 둔 항목을 지운다."""
    for f in _desktop_layout()[1]:
        try:
            if name in read_all("claude-desktop", f):
                _json_write(f, lambda s: s.pop(name, None))
        except ClientError:
            pass


def _cli_path(client: str) -> str:
    p = find_cli(client)
    if not p:
        raise ClientError(f"{client} CLI 를 찾을 수 없습니다(PATH 포함).")
    return p


def add(client: str, name: str, launch: Launch, store: Optional[str] = None) -> None:
    """서버를 등록한다. 같은 이름이 있으면 덮어쓴다. store 를 주면 그 저장소에만, 아니면 모든 저장소에 쓴다."""
    files = _json_files_of(client)
    if files:
        entry = {"command": launch.command, "args": list(launch.args)}
        for f in ([store] if store else files):
            _json_write(f, lambda s: s.__setitem__(name, dict(entry)))
        if client == "claude-desktop":
            _clean_desktop_orphans(name)
        return
    if any(name in read_all(client, s) for s in stores(client)):
        remove(client, name)
    argv = [_cli_path(client), "mcp", "add"]
    if client == "claude":
        argv += ["--scope", "user"]
    argv += [name, "--", launch.command, *launch.args]
    code, out = run_process(argv)
    if code != 0:
        raise ClientError(f"{client} mcp add 실패: {out}")


def remove(client: str, name: str, store: Optional[str] = None) -> None:
    """서버 등록을 제거한다. store 를 주면 그 저장소에서만, 아니면 모든 저장소에서. 없는 파일은 만들지 않는다."""
    files = _json_files_of(client)
    if files:
        for f in ([store] if store else files):
            if name in read_all(client, f):
                _json_write(f, lambda s: s.pop(name, None))
        if client == "claude-desktop":
            _clean_desktop_orphans(name)
        return
    argv = [_cli_path(client), "mcp", "remove"]
    if client == "claude":
        argv += ["--scope", "user"]
    argv.append(name)
    code, out = run_process(argv)
    if code != 0:
        raise ClientError(f"{client} mcp remove 실패: {out}")


# ------------------------------------------------------------------- 상태 판정
@dataclass
class StoreStatus:
    client: str
    store: str
    label: str                      # "Claude" 또는 "Claude Desktop [Microsoft Store 판]"
    installed: bool
    state: str = ABSENT             # ABSENT | SAME | STALE | FOREIGN
    current: Optional[Launch] = None
    dups: list = field(default_factory=list)       # [(이름, Launch)] 다른 이름으로 중복 등록된 우리 항목
    error: str = ""


def analyze(spec: ServerSpec, client: str, store: str, store_count: int) -> StoreStatus:
    """한 저장소의 등록 상태. 항목을 이름이 아니라 내용(is_ours)으로 판정한다."""
    st = StoreStatus(client, store, who(client, store, store_count), detect(client))
    if not st.installed:
        return st
    try:
        allv = read_all(client, store)
    except ClientError as e:
        st.error = str(e)
        return st
    cur = allv.get(spec.name)
    st.current = cur
    if cur is not None:
        if cur.key() == spec.launch().key():
            st.state = SAME
        elif spec.is_ours(cur):
            st.state = STALE
        else:
            st.state = FOREIGN
    st.dups = [(k, v) for k, v in allv.items() if k != spec.name and spec.is_ours(v)]
    return st


def all_status(spec: ServerSpec, only: Optional[list[str]] = None) -> list[StoreStatus]:
    out = []
    for client in (only or CLIENTS):
        ss = stores(client)
        out += [analyze(spec, client, s, len(ss)) for s in ss]
    return out


def _dead(l: Launch) -> str:
    return " [파일 없음]" if l.dead() else ""


# ----------------------------------------------------------- 등록 / 해지 동작
def install_store(spec: ServerSpec, st: StoreStatus, *, force: bool = False, dry_run: bool = False,
                  say: Callable[[str], None] = print) -> int:
    """한 저장소에 등록한다.
    우리 것이 없음 -> 추가 / 같음 -> 건너뜀 / 우리 것인데 경로가 다름 -> 교체 /
    다른 이름의 우리 것 -> 중복으로 보고 제거 / 이름만 같은 남의 것 -> --force 일 때만 교체."""
    who_ = st.label
    if st.state == FOREIGN and not force:
        say(f"  {who_}: '{spec.name}' 이(가) 이 서버가 아닌 다른 설정으로 이미 있습니다: {st.current.display()}")
        say("          교체하려면 강제(--force)로 다시 실행하세요.")
        return 1
    if st.state == SAME and not st.dups:
        say(f"  {who_}: 이미 등록되어 있습니다 (건너뜀)")
        return 0
    store = st.store or None
    if st.state == SAME:
        say(f"  {who_}: 이미 등록되어 있습니다")
    else:
        verb = "등록" if st.current is None else "교체"
        detail = "" if st.current is None else f" (기존: {st.current.display()}{_dead(st.current)})"
        if dry_run:
            say(f"  {who_}: [dry-run] {verb}할 예정{detail}")
        else:
            add(st.client, spec.name, spec.launch(), store)
            say(f"  {who_}: {verb} 완료{detail}")
    for k, v in st.dups:
        if dry_run:
            say(f"  {who_}: [dry-run] 중복 항목 '{k}' 제거할 예정 ({v.display()}{_dead(v)})")
        else:
            remove(st.client, k, store)
            say(f"  {who_}: 중복 항목 '{k}' 제거 완료 ({v.display()}{_dead(v)})")
    return 0


def uninstall_store(spec: ServerSpec, st: StoreStatus, *, force: bool = False, dry_run: bool = False,
                    say: Callable[[str], None] = print) -> int:
    """한 저장소에서 해지한다. 우리 것(다른 이름 포함)은 지우고, 이름만 같은 남의 것은 --force 일 때만 지운다."""
    who_ = st.label
    allv = read_all(st.client, st.store)
    cur = allv.get(spec.name)
    foreign = cur is not None and not spec.is_ours(cur)
    targets = [k for k, v in allv.items() if spec.is_ours(v)]
    if foreign and force:
        targets.append(spec.name)
    if not targets and not foreign:
        say(f"  {who_}: 등록되어 있지 않습니다 (건너뜀)")
        return 0
    store = st.store or None
    for name in targets:
        l = allv[name]
        label = "" if name == spec.name else f"'{name}' "
        if dry_run:
            say(f"  {who_}: [dry-run] {label}제거할 예정 ({l.display()}{_dead(l)})")
        else:
            remove(st.client, name, store)
            say(f"  {who_}: {label}제거 완료")
    if foreign and not force:
        say(f"  {who_}: '{spec.name}' 은(는) 이 서버가 아닌 다른 설정입니다: {cur.display()}")
        say("          그래도 제거하려면 강제(--force)로 다시 실행하세요.")
        return 1
    return 0


def warn_shadow(spec: ServerSpec, client: str, say: Callable[[str], None] = print) -> None:
    for where, name, l in shadow_entries(client):
        if name == spec.name or spec.is_ours(l):
            say(f"  {LABELS[client]}: 주의 - 사용자 범위 밖에 '{name}' 등록이 있어 우선 적용될 수 있습니다: "
                f"{where}: {l.display()}{_dead(l)}")
            say(f"          자동으로 고치지 않습니다. " + (
                f"위 파일에서 [mcp_servers.{name}] 항목을 직접 지우세요." if client == "codex"
                else f"해당 프로젝트 폴더에서 claude mcp remove {name} 으로 정리하세요."))


def run_action(spec: ServerSpec, action: str, clients: Optional[list[str]] = None, *,
               force: bool = False, dry_run: bool = False,
               say: Callable[[str], None] = print) -> int:
    """action: 'install' | 'uninstall'. clients 가 None 이면 설치된 모든 클라이언트. 종료 코드(0 성공)."""
    if action == "install" and not force:
        probs = spec.problems()
        if probs:
            for p in probs:
                say(f"등록하지 않습니다: {p}")
            say("그래도 등록하려면 강제(--force)로 실행하세요.")
            return 1
    targets = list(clients) if clients else [c for c in CLIENTS if detect(c)]
    if not targets:
        say("설치된 AI 클라이언트(Claude, Claude Desktop, Codex, Antigravity)가 없습니다.")
        return 1
    fn = install_store if action == "install" else uninstall_store
    title = "클라이언트에 등록" if action == "install" else "클라이언트에서 제거"
    say(f"{spec.name}: {title}" + (" (dry-run)" if dry_run else ""))
    code = 0
    for client in targets:
        if not detect(client):
            say(f"  {LABELS[client]}: 설치되어 있지 않습니다 (건너뜀)")
            continue
        try:
            ss = stores(client)
            for s in ss:
                st = analyze(spec, client, s, len(ss))
                if st.error:
                    raise ClientError(st.error)
                code |= fn(spec, st, force=force, dry_run=dry_run, say=say)
            warn_shadow(spec, client, say)
        except ClientError as e:
            say(f"  {LABELS[client]}: 실패 - {e}")
            code |= 1
    return code


def info(spec: ServerSpec, only: Optional[list[str]] = None) -> dict:
    """등록 현황을 JSON 으로 낼 수 있는 사전으로 모은다."""
    rows = []
    for st in all_status(spec, only):
        rows.append({
            "client": st.client, "label": st.label, "store": st.store or None,
            "installed": st.installed,
            "state": st.state if st.installed else "not-installed",
            "state_text": STATE_TEXT[st.state] if st.installed else "클라이언트가 설치되어 있지 않음",
            "current": st.current.display() if st.current else None,
            "dead": bool(st.current and st.current.dead()),
            "duplicates": [k for k, _ in st.dups],
            "error": st.error or None,
        })
    shadows = []
    for c in (only or CLIENTS):
        for where, name, l in shadow_entries(c):
            if name == spec.name or spec.is_ours(l):
                shadows.append({"client": c, "where": where, "name": name, "command": l.display()})
    return {"name": spec.name, "command": spec.launch().display(),
            "problems": spec.problems(), "clients": rows, "shadows": shadows,
            "python": sys.version.split()[0]}


def render_info(d: dict) -> str:
    lines = [f"MCP 서버 '{d['name']}'", f"  실행: {d['command']}"]
    for p in d["problems"]:
        lines.append(f"  ! {p}")
    lines.append("")
    lines.append("클라이언트별 등록 현황")
    for r in d["clients"]:
        mark = {"same": "[v]", "stale": "[!]", "foreign": "[!]", "absent": "[ ]"}.get(r["state"], "[-]")
        lines.append(f"  {mark} {r['label']}: {r['state_text']}")
        if r["current"] and r["state"] != "absent":
            lines.append(f"        {r['current']}{' [파일 없음]' if r['dead'] else ''}")
        if r["duplicates"]:
            lines.append(f"        중복 등록된 다른 이름: {', '.join(r['duplicates'])}")
        if r["error"]:
            lines.append(f"        오류: {r['error']}")
    for s in d["shadows"]:
        lines.append(f"  주의: {s['client']} 사용자 범위 밖 등록 '{s['name']}' - {s['where']}: {s['command']}")
    return "\n".join(lines)
