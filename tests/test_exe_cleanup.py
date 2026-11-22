r"""dist\mcp_orange.exe 가 강제 종료로 남은 _MEI 폴더만 치우고, 실행 중인 인스턴스의 폴더는 건드리지 않는지 확인.
dist\mcp_orange.exe 가 있어야 한다 (build\build_exe.ps1)."""
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

from _paths import ROOT  # noqa: F401

EXE = os.path.join(ROOT, "dist", "mcp_orange.exe")
if not os.path.isfile(EXE):
    print("SKIP: %s 없음" % EXE)
    sys.exit(0)

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


INIT = (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}) + "\n").encode()
TMP = tempfile.gettempdir()


def meis():
    return set(glob.glob(os.path.join(TMP, "_MEI*")))


def start():
    p = subprocess.Popen([EXE, "--mcp-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p.stdin.write(INIT)
    p.stdin.flush()
    p.stdout.readline()
    return p


base = meis()
a = start()                                   # 실행 중인 인스턴스 A
a_dirs = meis() - base
check(len(a_dirs) == 1, "A 가 풀기 폴더 1개를 만듦")

b = start()                                   # B 를 만들고 강제로 트리 종료 -> 폴더 누수
b_dirs = meis() - base - a_dirs
subprocess.run(["taskkill", "/PID", str(b.pid), "/T", "/F"], capture_output=True)
time.sleep(2)
check(all(os.path.isdir(d) for d in b_dirs) and len(b_dirs) == 1, "B 강제 종료 -> 폴더가 남음(누수 재현): %s" % [os.path.basename(d) for d in b_dirs])

c = start()                                   # C 시작 -> 백그라운드 정리 실행
time.sleep(4)
now = meis() - base
check(not any(os.path.exists(d) for d in b_dirs), "C 시작 후 B 의 남은 폴더가 정리됨")
check(all(os.path.isdir(d) for d in a_dirs), "실행 중인 A 의 폴더는 그대로")
a.stdin.write((json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n").encode())
a.stdin.flush()
reply = json.loads(a.stdout.readline())
check(reply.get("id") == 9 and "error" not in reply, "A 가 여전히 응답함: %s" % str(reply)[:80])

for p in (a, c):
    p.stdin.close()
    p.wait(15)
time.sleep(1)
check(not (meis() - base), "정상 종료 후엔 남는 폴더 없음")
print("\nFAILS:", fails if fails else "none")
sys.exit(1 if fails else 0)
