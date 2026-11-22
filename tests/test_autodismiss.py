import json, sys, time
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call
fails = []
def check(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)

call("clear_workflow"); call("get_errors", clear=True)
f = call("add_node", widget="File")["id"]; call("load_file", node=f, path="iris")
km = call("add_node", widget="k-Means")["id"]; call("add_link", source=f, sink=km)
time.sleep(1)
base = call("get_errors")["total"]

# our own validation should refuse bad values before Orange sees them
for bad in ({"n_init": "abc"}, {"k": 9999}, {"k": "three"}):
    try:
        call("update_widget", node=km, settings=bad)
        check(False, "validation should reject %s" % bad)
    except Exception as ex:
        check("expects" in str(ex) or "outside" in str(ex), "rejected %s -> %s" % (bad, str(ex)[:90]))
check(call("get_errors")["total"] == base, "rejected values never reached Orange (no error dialog)")

# bypass validation (direct Qt) to prove the safety net: unhandled exception in a Qt slot
call("debug_exec", code="""
w = widget('%s')
w.controls.n_init.setText('abc')
""" % km)
time.sleep(1.5)
check(call("list_dialogs") == [], "no error dialog left open")
e = call("get_errors")
print(json.dumps(e, ensure_ascii=False, indent=1)[:1800])
check(e["total"] > base, "error dialog was caught and recorded (total %d -> %d)" % (base, e["total"]))
if e["errors"]:
    last = e["errors"][-1]
    check("Don't Send" in last["action"] or "don't send" in last["action"].lower(), "answered safely: %s" % last["action"])
    check(bool(last.get("exception") or last.get("traceback") or last.get("raw")), "details captured")
st = call("get_status")
print("status new_errors:", st.get("new_errors"))
# Orange still usable afterwards
r = call("update_widget", node=km, settings={"k": 3, "optimize_k": "Fixed"})
time.sleep(0.8)
out = call("get_output", node=km, channel="Data", rows=1)["Data"]
check(out["rows"] == 150, "workflow still works after the error (k-Means output %s rows)" % out["rows"])

# switch off -> dialogs stay (so a human could see them)
print(call("set_auto_dismiss", enabled=False))
call("debug_exec", code="""
from AnyQt.QtWidgets import QMessageBox
import builtins
d = QMessageBox(window); d.setIcon(QMessageBox.Icon.Critical)
d.setWindowTitle('Unexpected Error - Orange'); d.setText('x'); d.addButton("Don't Send", QMessageBox.ButtonRole.RejectRole)
d.setModal(False); d.show(); builtins._d = d
""")
time.sleep(1)
check(len(call("list_dialogs")) == 1, "with auto_dismiss off the dialog stays")
print(call("set_auto_dismiss", enabled=True))
time.sleep(1)
check(call("list_dialogs") == [], "re-enabled -> closed automatically")
print("\nFAILS:", fails or "none")
