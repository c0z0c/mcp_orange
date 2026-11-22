"""relay 수명 관리(mcp_orange_app/lifecycle.py) 검증. Orange 불필요, 설치된 Orange·사용자 데이터 폴더를 건드리지 않는다.

1부: 가짜 시계 + 더미 프로세스로 규칙 검증 (유휴 / Orange 종속 / 유예 / 고아)
2부: 실제 relay 프로세스(stdio)로 종단 검증. bridge.json 은 임시 MCP_ORANGE_HOME 에 만든다.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

from _paths import ROOT, RELAY  # noqa: E402,F401
from mcp_orange_app import lifecycle as lc  # noqa: E402

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def dummy():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])


def kill(p):
    p.kill()
    p.wait()


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def write_bridge(path, pid):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"port": 1, "token": "x", "pid": pid}, f)


def make(tmp, clock, **kw):
    exits = []
    disc = os.path.join(tmp, "bridge.json")
    obj = lc.Lifecycle(discovery=lambda: disc, clock=clock, exit_fn=exits.append, **kw)
    return obj, exits, disc


def part1():
    tmp = tempfile.mkdtemp(prefix="lc_unit_")
    procs = []
    try:
        # 유휴: 제어하는 Orange 를 본 적 없으면 유휴 한도 후 종료
        clk = Clock()
        o, _, disc = make(tmp, clk, idle=600, grace=120)
        clk.t += 599
        check(o.check() is None, "no Orange: not yet idle at 599s")
        clk.t += 2
        check("idle" in (o.check() or ""), "no Orange: exits after idle limit")

        # 진행 중인 도구 호출은 유휴가 아니다
        clk = Clock()
        o, _, disc = make(tmp, clk, idle=600, grace=120)
        o.begin()
        clk.t += 5000
        check(o.check() is None, "busy tool call is never idle")
        o.end()
        check(o.check() is None, "idle clock restarts when the call ends")

        # 죽은 pid 가 적힌 낡은 bridge.json 은 Orange 로 치지 않는다
        d = dummy()
        d_pid = d.pid
        kill(d)
        write_bridge(disc, d_pid)
        clk = Clock()
        o, _, disc = make(tmp, clk, idle=600, grace=120)
        o.poll()
        clk.t += 700
        check("idle" in (o.check() or ""), "stale bridge.json (dead pid) does not hold the relay")

        # 살아 있는 Orange 가 있으면 요청이 없어도 끝나지 않는다(사용자가 직접 작업 중일 수 있다)
        orange = dummy()
        procs.append(orange)
        write_bridge(disc, orange.pid)
        clk = Clock()
        o, _, disc = make(tmp, clk, idle=600, grace=120)
        o.poll()
        clk.t += 100000
        o.poll()
        check(o.check() is None, "live Orange: relay is never idle-closed")

        # 정상 종료로 bridge.json 이 지워져도 보고 있던 Orange 를 계속 감시한다
        os.remove(disc)
        o.poll()
        check(o.check() is None, "bridge.json removed but Orange still alive: still held")

        # Orange 종료 -> 유예 후 종료, 유예 안의 요청은 유예를 다시 시작
        kill(orange)
        o.poll()
        check(o.check() is None, "Orange just closed: grace not elapsed")
        clk.t += 100
        o.touch()                      # 사용자가 "다시 켜줘" 라고 해서 요청이 왔다
        clk.t += 100
        check(o.check() is None, "request during grace restarts the grace")
        clk.t += 21
        check("Orange" in (o.check() or ""), "exits grace seconds after the last request once Orange is gone")

        # 새 Orange(launch_orange) 가 뜨면 새 pid 를 감시한다
        o2 = dummy()
        procs.append(o2)
        write_bridge(disc, o2.pid)
        clk.t += 1
        o.poll()
        check(o.check() is None, "new Orange pid replaces the dead one")
        clk.t += 100000
        check(o.check() is None, "relaunched Orange holds the relay")
        kill(o2)

        # 유예 0 이면 Orange 종료 즉시
        o3 = dummy()
        procs.append(o3)
        write_bridge(disc, o3.pid)
        clk = Clock()
        o, _, disc = make(tmp, clk, idle=600, grace=0)
        o.poll()
        kill(o3)
        o.poll()
        check("Orange" in (o.check() or ""), "grace 0: exits as soon as Orange is gone")

        # 클라이언트가 사라지면 Orange 가 살아 있어도 유예 후 종료(고아 정리)
        orange = dummy()
        client = dummy()
        procs += [orange, client]
        write_bridge(disc, orange.pid)
        clk = Clock()
        o, _, disc = make(tmp, clk, idle=600, grace=120, client=lc.open_proc(client.pid))
        o.poll()
        clk.t += 5000
        check(o.check() is None, "client alive + Orange alive: held")
        kill(client)
        o.poll()
        clk.t += 119
        check(o.check() is None, "client gone: grace not elapsed")
        clk.t += 2
        check("client" in (o.check() or ""), "client gone: exits after grace even though Orange is alive")
        kill(orange)

        # 시작할 때 이미 고아
        clk = Clock()
        o, _, disc = make(tmp, clk, idle=None, grace=120, client_gone=True)
        clk.t += 121
        check("client" in (o.check() or ""), "already-orphaned at start: exits after grace")

        # 모두 꺼진 설정
        clk = Clock()
        o, _, disc = make(tmp, clk, idle=None, grace=120, watch_orange=False)
        clk.t += 10 ** 7
        check(o.check() is None, "idle disabled + nothing to watch: never exits")
    finally:
        for p in procs:
            if p.poll() is None:
                kill(p)


# ------------------------------------------------------------------ 2부: 실제 relay
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "lifecycle-test", "version": "0"}}}


def spawn_relay(home, stdin, **env):
    e = dict(os.environ, MCP_ORANGE_HOME=home, MCP_ORANGE_NO_UPDATE_CHECK="1")
    for k in list(e):
        if k.startswith("MCP_ORANGE_") and k not in ("MCP_ORANGE_HOME", "MCP_ORANGE_NO_UPDATE_CHECK"):
            del e[k]
    e.update({k: str(v) for k, v in env.items()})
    return subprocess.Popen([sys.executable, "-s", "-B", os.path.join(RELAY, "mcp_orange.py")],
                            stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e)


def handshake(p):
    p.stdin.write((json.dumps(INIT) + "\n").encode())
    p.stdin.flush()
    reply = json.loads(p.stdout.readline())
    p.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode())
    p.stdin.flush()
    return reply["result"]


def wait_exit(p, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if p.poll() is not None:
            return time.time() - t0
        time.sleep(0.1)
    return None


def part2():
    procs = []
    try:
        # E1: Orange 없이 방치 -> 유휴 종료, 안내 문구가 initialize 에 실린다
        home = tempfile.mkdtemp(prefix="lc_e2e1_")
        r = spawn_relay(home, subprocess.PIPE, MCP_ORANGE_IDLE_SECONDS=3)
        procs.append(r)
        res = handshake(r)
        check("tied to the Orange" in (res.get("instructions") or ""), "initialize instructions carry the lifetime note")
        check("Drives a live Orange 3 canvas" in (res.get("instructions") or ""), "original instructions are kept")
        t = wait_exit(r, 15)
        check(t is not None and r.returncode == 0, "E1 idle relay exits by itself (rc=0, %s s)" % (None if t is None else round(t, 1)))

        # E2: 살아 있는 Orange 가 있으면 유휴여도 유지, Orange 가 닫히면 유예 후 종료
        home = tempfile.mkdtemp(prefix="lc_e2e2_")
        orange = dummy()
        procs.append(orange)
        write_bridge(os.path.join(home, "bridge.json"), orange.pid)
        r = spawn_relay(home, subprocess.PIPE, MCP_ORANGE_IDLE_SECONDS=2, MCP_ORANGE_EXIT_GRACE_SECONDS=2)
        procs.append(r)
        handshake(r)
        check(wait_exit(r, 7) is None, "E2 relay stays up while its Orange is alive (idle limit 2s, waited 7s)")
        kill(orange)
        t = wait_exit(r, 15)
        check(t is not None and 1.0 <= t, "E2 relay exits after its Orange is gone + grace (%s s)" % (None if t is None else round(t, 1)))

        # E3: 클라이언트(부모)가 사라지면 유예 후 종료. stdin 은 테스트가 쥐고 있어 EOF 가 오지 않는다
        home = tempfile.mkdtemp(prefix="lc_e2e3_")
        relay_py = os.path.join(RELAY, "mcp_orange.py")
        # 클라이언트 역할의 mid 는 venv 스텁 없이 base 인터프리터로 직접 띄우고(kill 하면 그 프로세스 하나만 죽는다),
        # relay 는 venv python 으로 띄운다: 실제 구성 '클라이언트 -> 런처 스텁 -> relay' 와 같다
        base_py = getattr(sys, "_base_executable", sys.executable)
        mid_code = ("import subprocess,os;"
                    "p=subprocess.Popen([%r,'-s','-B',%r],env=os.environ);"
                    "print(p.pid,flush=True);p.wait()" % (sys.executable, relay_py))
        env = dict(os.environ, MCP_ORANGE_HOME=home, MCP_ORANGE_EXIT_GRACE_SECONDS="2",
                   MCP_ORANGE_IDLE_MINUTES="0", MCP_ORANGE_NO_UPDATE_CHECK="1")
        env.pop("MCP_ORANGE_CLIENT_PID", None)
        env.pop("MCP_ORANGE_NO_PARENT_WATCH", None)
        mid = subprocess.Popen([base_py, "-s", "-B", "-c", mid_code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, env=env)
        procs.append(mid)
        child = lc.open_proc(int(mid.stdout.readline()))
        check(child is not None, "E3 relay started under a client process")
        time.sleep(4)
        check(child is not None and not child.exited(), "E3 relay stays up while its client is alive")
        kill(mid)
        t0 = time.time()
        while child is not None and not child.exited() and time.time() - t0 < 15:
            time.sleep(0.2)
        check(child is not None and child.exited(), "E3 orphaned relay exits after its client is gone (%.1f s)" % (time.time() - t0))
    finally:
        for p in procs:
            if p.poll() is None:
                kill(p)


if __name__ == "__main__":
    part1()
    part2()
    print("\n%d failure(s)" % len(fails))
    sys.exit(1 if fails else 0)
