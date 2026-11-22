"""설정 마법사를 실제로 띄워 동작을 확인한다 (창이 잠깐 보인다). 데이터 폴더는 임시로 격리한다.
등록 패널은 건드리지 않는다(클라이언트 설정 변경 없음). Orange 는 읽기만 한다."""
import os
import sys
import tempfile

from _paths import ROOT, OUT  # noqa: F401

TMP = tempfile.mkdtemp(prefix="wizard_test_")
os.environ["MCP_ORANGE_HOME"] = TMP
os.environ["MCP_ORANGE_NO_UPDATE_CHECK"] = "1"   # 네트워크 호출 금지

from mcp_orange_app import compat, config, discovery  # noqa: E402

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


try:
    from mcp_orange_app import wizard
except ImportError as ex:   # tkinter 없는 환경
    print("SKIP wizard (tkinter 없음): %s" % ex)
    sys.exit(0)

if not discovery.find_orange_pythons(scan=False):
    print("SKIP wizard: Orange 가 근처에 없음")
    sys.exit(0)

w = wizard.Wizard()
state = {"ticks": 0}


def tick():
    state["ticks"] += 1
    if w._busy and state["ticks"] < 600:        # 검색/검사 끝날 때까지 (최대 60초)
        w.after(100, tick)
        return
    rows = [w.tree.item(i, "values") for i in w.tree.get_children()]
    check(len(rows) >= 1, "목록에 Orange %d 개 표시: %s" % (len(rows), [r[1] for r in rows]))
    check(any(r[0] == compat.LABEL[compat.VERIFIED] for r in rows), "검증된 조합이 '호환 (검증됨)'으로 표시됨")
    # 사용 가능한 첫 행을 골라 '이 Orange 사용' 실행
    first = next((i for i, t in w._targets.items() if t.status == compat.VERIFIED), None)
    check(first is not None, "검증된 Orange 행이 있음")
    gate_before = w._gate()[0]
    w.tree.selection_set(first)
    w.update()
    w.use_selected()
    saved = config.load().get("orange_python")
    check(saved and os.path.normcase(saved) == os.path.normcase(w._targets[first].python), "선택이 config.json 에 저장됨: %s" % saved)
    check(w._gate()[0], "선택 후 등록 게이트가 열림 (선택 전: %s)" % gate_before)
    w.destroy()


w.after(300, tick)
w.mainloop()
print("\nFAILS:", fails if fails else "none")
sys.exit(1 if fails else 0)
