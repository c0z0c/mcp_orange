import json, sys, time
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call

fails = []
def check(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)

call("set_auto_dismiss", enabled=False)  # the guard would close our fake error dialog
# a non-blocking dialog shaped like Orange's "Unexpected Error" report dialog
call("debug_exec", code="""
from AnyQt.QtWidgets import QMessageBox
import builtins
d = QMessageBox(window)
d.setWindowTitle('Unexpected Error - Orange')
d.setText('The program encountered an unexpected error.')
d.addButton('Send Report (Thanks!)', QMessageBox.ButtonRole.AcceptRole)
d.addButton("Don't Send", QMessageBox.ButtonRole.RejectRole)
d.setModal(False)
d.show()
builtins._mcp_test_dialog = d
""")
time.sleep(0.5)
dl = call("list_dialogs")
print(json.dumps(dl, ensure_ascii=False))
check(len(dl) == 1 and "Don't Send" in dl[0]["buttons"], "dialog is listed with its buttons")
st = call("get_status")
check(bool(st.get("dialogs")), "get_status reports the open dialog")
a = call("answer_dialog")
check(a["action"] == "clicked \"Don't Send\"" or "Don't Send" in a["action"], "default answer is Don't Send: %s" % a)
time.sleep(0.5)
check(call("list_dialogs") == [], "dialog gone")
call("debug_exec", code="import builtins; del builtins._mcp_test_dialog")
call("set_auto_dismiss", enabled=True)
print("\nFAILS:", fails or "none")
