"""relay(stdio MCP 서버) 프로세스의 수명 관리.

AI 클라이언트는 대화(세션)가 끝나도 띄운 relay 를 내리지 않는 경우가 많아, 방치된 relay 가 계속 쌓인다.
relay 는 상태가 없으므로(모든 상태는 Orange 쪽에 있다) 언제 끝나도 잃는 것이 없다. 다음 세 가지 경우에 스스로 끝낸다.

relay 와 그것이 제어하는 Orange 는 종속 관계다. 제어 가능한 Orange 는 launch_orange 가 bridge 를 심어 띄운 것뿐이고,
사용자가 그 Orange 에서 직접 작업 중일 수 있다. 그래서 relay 는 살아 있는 Orange(bridge.json 의 pid)가 있는 동안
요청이 없어도 끝나지 않는다. 끝나는 경우는 다음 셋이다.

1. Orange 종료: 제어하던 Orange 가 사라졌다. 사용자가 대화 중에 Orange 를 닫고 "다시 켜줘"라고 할 수 있어서
   바로 끝내지 않고 유예(기본 120초)를 둔다. 유예 안에 요청이 오면 계속 산다.
2. 유휴: 제어하는 Orange 를 한 번도 보지 못한 relay(launch_orange 를 부르지 않은 채 방치된 것)가 일정 시간
   (기본 10분) 요청이 없다.
3. 클라이언트 종료: relay 를 띄운 클라이언트 프로세스가 사라졌다. 대화 상대가 없는 고아이므로 Orange 가 살아 있어도
   정리한다(Orange 는 영향 없음). 정상 경로(stdin EOF)가 안 먹는 경우의 안전망이다. 중간 런처만 먼저 끝나는
   구성도 있어서 같은 유예를 둔다.

Orange 자체는 절대 닫지 않는다(저장하지 않은 작업을 지킨다). 사용으로 치는 것은 ping 을 뺀 모든 MCP 요청이고,
도구 호출이 진행 중이면 유휴가 아니다.

환경변수
  MCP_ORANGE_IDLE_MINUTES       유휴 종료 분(기본 10, 0 이면 끔)
  MCP_ORANGE_IDLE_SECONDS       테스트용(초). 분보다 우선
  MCP_ORANGE_EXIT_GRACE_SECONDS Orange/클라이언트 종료 후 유예(기본 120, 0 이면 바로)
  MCP_ORANGE_NO_ORANGE_WATCH=1  Orange 종료 감시를 끈다
  MCP_ORANGE_NO_PARENT_WATCH=1  클라이언트 종료 감시를 끈다
  MCP_ORANGE_CLIENT_PID         감시할 클라이언트 PID 를 직접 지정(기본: 부모, onefile exe 면 그 부모)

표준 라이브러리만 쓴다. stdout 은 MCP 프로토콜이므로 메시지는 stderr 로만 낸다.
"""
from __future__ import annotations

import functools
import json
import os
import sys
import threading
import time
from typing import Callable, Optional

IDLE_MINUTES_ENV = "MCP_ORANGE_IDLE_MINUTES"
IDLE_SECONDS_ENV = "MCP_ORANGE_IDLE_SECONDS"
GRACE_ENV = "MCP_ORANGE_EXIT_GRACE_SECONDS"
NO_ORANGE_WATCH_ENV = "MCP_ORANGE_NO_ORANGE_WATCH"
NO_PARENT_WATCH_ENV = "MCP_ORANGE_NO_PARENT_WATCH"
CLIENT_PID_ENV = "MCP_ORANGE_CLIENT_PID"

DEFAULT_IDLE_MINUTES = 10.0
DEFAULT_GRACE_SECONDS = 120.0


# ------------------------------------------------------------------ 설정 읽기
def _float_env(name: str) -> Optional[float]:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return None


def idle_limit() -> Optional[float]:
    """유휴 종료까지의 시간(초). 꺼져 있으면 None."""
    s = _float_env(IDLE_SECONDS_ENV)
    if s is not None and s > 0:
        return s
    m = _float_env(IDLE_MINUTES_ENV)
    m = DEFAULT_IDLE_MINUTES if m is None or m < 0 else m
    return None if m == 0 else m * 60.0


def grace_seconds() -> float:
    g = _float_env(GRACE_ENV)
    return DEFAULT_GRACE_SECONDS if g is None or g < 0 else g


# -------------------------------------------------------------- 프로세스 확인
class Proc:
    """다른 프로세스의 종료를 확인하는 핸들. 핸들을 쥐고 있는 동안 PID 는 재사용되지 않는다."""

    def __init__(self, pid: int, handle):
        self.pid = pid
        self._h = handle          # None 이면 상태를 알 수 없음(권한 부족): 종료로 판단하지 않는다

    def exited(self) -> bool:
        if os.name == "nt":
            return self._h is not None and _k32.WaitForSingleObject(self._h, 0) == 0
        try:
            os.kill(self.pid, 0)
            return False
        except ProcessLookupError:
            return True
        except OSError:
            return False

    def created(self) -> Optional[int]:
        """생성 시각(FILETIME 정수). 알 수 없으면 None."""
        if os.name != "nt" or self._h is None:
            return None
        return _creation_time(self._h)

    def close(self) -> None:
        if os.name == "nt" and self._h is not None:
            _k32.CloseHandle(self._h)
        self._h = None


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _nt = ctypes.WinDLL("ntdll")
    _SYNCHRONIZE, _QUERY_LIMITED = 0x00100000, 0x1000
    _ERROR_INVALID_PARAMETER = 87

    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    _nt.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p,
                                              wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
    _nt.NtQueryInformationProcess.restype = wintypes.LONG

    class _Pbi(ctypes.Structure):
        _fields_ = [(n, ctypes.c_size_t) for n in
                    ("ExitStatus", "PebBase", "AffinityMask", "BasePriority", "UniqueProcessId", "ParentProcessId")]

    def _creation_time(h) -> Optional[int]:
        c, e, k, u = (wintypes.FILETIME() for _ in range(4))
        if not _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        return (c.dwHighDateTime << 32) | c.dwLowDateTime

    def _parent_pid_of(h) -> int:
        pbi = _Pbi()
        ok = _nt.NtQueryInformationProcess(h, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None) == 0
        return int(pbi.ParentProcessId) if ok else 0

    def _image_of(h) -> str:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(len(buf))
        return buf.value if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""

    def _is_launcher_stub(parent_h) -> bool:
        """부모가 실제 클라이언트가 아니라 이 서버를 대신 띄운 런처인가.
        - PyInstaller onefile exe: 부트로더(같은 exe)가 실제 서버의 부모이고 서버가 끝나야 끝난다.
        - Windows venv: .venv\\Scripts\\python.exe 스텁이 base 인터프리터를 자식으로 띄운다.
        어느 쪽이든 스텁은 클라이언트가 죽어도 서버와 함께 남으므로 그 위의 프로세스를 봐야 한다."""
        parent = os.path.normcase(_image_of(parent_h))
        own = os.path.normcase(_image_of(_k32.GetCurrentProcess()))
        if not parent or not own:
            return False
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return parent == own
        if sys.prefix != sys.base_prefix:
            return parent == os.path.normcase(sys.executable) and own != parent
        return False


def open_proc(pid: int) -> Optional[Proc]:
    """pid 프로세스의 감시 핸들. 그런 프로세스가 없으면 None. 권한이 없어 열 수 없으면 '살아 있음'으로 둔다."""
    if pid <= 0:
        return None
    if os.name != "nt":
        p = Proc(pid, None)
        return None if p.exited() else p
    h = _k32.OpenProcess(_SYNCHRONIZE | _QUERY_LIMITED, False, pid)
    if not h:
        return None if ctypes.get_last_error() == _ERROR_INVALID_PARAMETER else Proc(pid, None)
    return Proc(pid, h)


def client_target() -> "tuple[Optional[Proc], bool]":
    """감시할 클라이언트. (핸들, 이미 사라졌는가). 감시할 수 없으면 (None, False).

    CLIENT_PID 가 있으면 그것, 없으면 부모 프로세스다. 부모가 런처 스텁(PyInstaller onefile 부트로더, Windows venv 의
    python.exe)이면 그 위의 프로세스를 본다: 스텁은 클라이언트가 죽어도 서버와 함께 남기 때문이다.
    대상이 이 프로세스보다 늦게 만들어졌으면 PID 재사용이므로 감시하지 않는다.
    """
    if os.environ.get(NO_PARENT_WATCH_ENV) == "1":
        return None, False
    explicit = _float_env(CLIENT_PID_ENV)
    if explicit and explicit > 0:
        pid = int(explicit)
    elif os.name == "nt":
        pid = _parent_pid_of(_k32.GetCurrentProcess())
        for _ in range(2):                       # 런처 스텁을 건너뛰어 실제 클라이언트를 찾는다
            if pid <= 0:
                break
            stub = open_proc(pid)
            if stub is None:
                return None, True
            is_stub = stub._h is not None and _is_launcher_stub(stub._h)
            up = _parent_pid_of(stub._h) if is_stub else 0
            stub.close()
            if not is_stub:
                break
            pid = up
    else:
        pid = os.getppid()
    if pid <= 0 or pid == os.getpid():
        return None, False
    proc = open_proc(pid)
    if proc is None:
        return None, True            # 시작할 때 이미 사라졌다: 고아
    mine = _creation_time(_k32.GetCurrentProcess()) if os.name == "nt" else None
    theirs = proc.created()
    if mine is not None and theirs is not None and theirs > mine:
        proc.close()
        return None, False           # PID 재사용
    return proc, False


# ------------------------------------------------------------------- 본체
def _default_exit(reason: str) -> None:
    try:
        sys.stderr.write("[mcp_orange] %s; exiting (the client restarts it on the next call).\n" % reason)
        sys.stderr.flush()
    finally:
        os._exit(0)


class Lifecycle:
    def __init__(self, discovery: Optional[Callable[[], str]] = None, idle: Optional[float] = None,
                 grace: Optional[float] = None, watch_orange: bool = True,
                 client: Optional[Proc] = None, client_gone: bool = False,
                 clock: Callable[[], float] = time.monotonic,
                 exit_fn: Callable[[str], None] = _default_exit):
        self.discovery, self.idle, self.grace = discovery, idle, grace_seconds() if grace is None else grace
        self.watch_orange, self._clock, self._exit = watch_orange, clock, exit_fn
        self._lock = threading.Lock()
        self._last = clock()
        self._busy = 0
        self._orange: Optional[Proc] = None
        self._orange_gone_at: Optional[float] = None
        self._client = client
        self._client_gone_at: Optional[float] = self._last if client_gone else None

    # 사용 기록
    def touch(self) -> None:
        with self._lock:
            self._last = self._clock()

    def begin(self) -> None:
        with self._lock:
            self._busy += 1
            self._last = self._clock()

    def end(self) -> None:
        with self._lock:
            self._busy -= 1
            self._last = self._clock()

    # 감시
    def _orange_pid(self) -> int:
        if self.discovery is None:
            return 0
        try:
            with open(self.discovery(), encoding="utf-8") as f:
                return int(json.load(f).get("pid") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            return 0

    def poll(self) -> None:
        """Orange/클라이언트 상태를 한 번 확인한다."""
        now = self._clock()
        with self._lock:
            if self.watch_orange and self.discovery:
                pid = self._orange_pid()
                # bridge.json 이 지워져도(정상 종료 시 Orange 가 지운다) 보고 있던 핸들은 유지한다.
                # 다른 pid 가 나타났을 때만(launch_orange 로 새로 뜬 Orange) 감시 대상을 바꾼다.
                if pid and (self._orange is None or pid != self._orange.pid):
                    new = open_proc(pid)
                    if new is not None and new.exited():
                        new.close()
                        new = None
                    if new is not None:
                        if self._orange is not None:
                            self._orange.close()
                        self._orange, self._orange_gone_at = new, None
                if self._orange is not None and self._orange_gone_at is None and self._orange.exited():
                    self._orange_gone_at = now
            if self._client is not None and self._client_gone_at is None and self._client.exited():
                self._client_gone_at = now

    def check(self) -> Optional[str]:
        """끝내야 하면 이유를, 아니면 None."""
        now = self._clock()
        with self._lock:
            if self._busy > 0:
                return None
            quiet = now - self._last
            # relay 의 수명은 제어하는 Orange 에 종속된다: 살아 있는 Orange 가 있으면(사용자가 직접 작업 중일 수 있다)
            # 요청이 없어도 유휴로 끝내지 않는다. 유휴 종료는 제어하는 Orange 를 한 번도 보지 못한 relay 에만 적용된다.
            # Orange 가 사라진 뒤에는 아래 유예 규칙이 끝낸다.
            if self.idle is not None and self._orange is None and quiet >= self.idle:
                return "idle for %.1f min" % (quiet / 60)
            for name, gone_at in (("the Orange it controlled", self._orange_gone_at),
                                  ("the client process", self._client_gone_at)):
                if gone_at is not None and now - max(self._last, gone_at) >= self.grace:
                    return "%s is gone" % name
        return None

    def poll_interval(self) -> float:
        smallest = min([x for x in (self.idle, self.grace) if x is not None] or [8.0])
        return min(2.0, max(0.1, smallest / 4))

    def start(self) -> None:
        def loop():
            while True:
                time.sleep(self.poll_interval())
                try:
                    self.poll()
                    reason = self.check()
                except Exception:  # noqa: BLE001 - 감시 실패가 서버를 죽이면 안 된다
                    continue
                if reason:
                    self._exit(reason)
        threading.Thread(target=loop, name="mcp-orange-lifecycle", daemon=True).start()

    # MCP 요청 훅
    def instructions_note(self) -> str:
        parts = []
        if self.idle is not None:
            parts.append("after about %d minutes without any request if no Orange it controls is running"
                         % max(1, round(self.idle / 60)))
        if self.watch_orange:
            parts.append("about %d seconds after the Orange it controls is closed" % round(self.grace))
        if not parts:
            return ""
        return ("\n\nThis server's lifetime is tied to the Orange it controls: while that Orange is running the "
                "server stays up, even if the user is working in Orange and sends no requests. It exits by itself "
                + " or ".join(parts) + ", and the client normally starts it again on the next call. Use your "
                "judgement: if a call fails because the connection closed, retry it once; if orange_status then "
                "reports Orange is not running, call launch_orange. The Orange window itself is never closed by "
                "this. If retrying still fails, tell the user to reconnect the MCP server. You do not need to keep "
                "it alive.")

    def hook(self, lowlevel_server) -> None:
        """ping 을 뺀 모든 요청 핸들러를 감싸 사용 기록과 진행 중 표시를 한다."""
        from mcp import types
        handlers = lowlevel_server.request_handlers
        for req_type, handler in list(handlers.items()):
            if req_type is types.PingRequest:
                continue
            handlers[req_type] = self._wrap(handler)
        note = self.instructions_note()
        if note:
            lowlevel_server.instructions = (lowlevel_server.instructions or "") + note

    def _wrap(self, handler):
        @functools.wraps(handler)
        async def wrapped(req):
            self.begin()
            try:
                return await handler(req)
            finally:
                self.end()
        return wrapped


def install(lowlevel_server, discovery: Callable[[], str]) -> Optional[Lifecycle]:
    """relay 에 수명 관리를 붙이고 감시 스레드를 시작한다. 모두 꺼져 있으면 None."""
    client, gone = (None, False) if os.environ.get(NO_PARENT_WATCH_ENV) == "1" else client_target()
    lc = Lifecycle(discovery=discovery, idle=idle_limit(),
                   watch_orange=os.environ.get(NO_ORANGE_WATCH_ENV) != "1",
                   client=client, client_gone=gone)
    lc.hook(lowlevel_server)
    lc.start()
    return lc
