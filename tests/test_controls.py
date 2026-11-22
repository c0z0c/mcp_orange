"""Dotted component settings, combos, list selection and the error-dialog flow."""
import json, sys, time
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call

fails = []
def check(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)

def idle(t=30):
    t0 = time.time()
    while time.time() - t0 < t:
        if not call("get_status")["busy"]: return True
        time.sleep(0.3)

call("clear_workflow")
f = call("add_node", widget="File")["id"]
call("load_file", node=f, path="iris")
sc = call("add_node", widget="Scatter Plot")["id"]
call("add_link", source=f, sink=sc)
idle()

ins = call("inspect_widget", node=sc)
S = {s["name"]: s for s in ins["settings"]}
check("graph.alpha_value" in S and S["graph.alpha_value"]["value"] is not None,
      "dotted setting visible with value: %s" % S.get("graph.alpha_value", {}).get("value"))
check(S["graph.alpha_value"].get("control", {}).get("kind") == "slider", "graph.alpha_value has slider control")
print("attr_x control:", S.get("attr_x", {}).get("control"))
r = call("set_setting", node=sc, name="graph.alpha_value", value=250)
check(r["new"] == 250, "alpha_value ->250 via dotted path (new=%s)" % r["new"])
r = call("set_setting", node=sc, name="graph.show_grid", value=True)
check(r["new"] is True, "show_grid on")
r = call("set_setting", node=sc, name="attr_x", value="petal length")
print("attr_x ->", r["new"], r["via"])
r = call("set_setting", node=sc, name="attr_y", value="petal width")
idle()
call("screenshot", target=sc, path=OUT + r"\shot_scatter2.png")

sel = call("add_node", widget="Select Columns")["id"]
call("add_link", source=f, sink=sel)
idle()
ins = call("inspect_widget", node=sel)
print("Select Columns settings:", [(s["name"], s.get("control", {}).get("kind")) for s in ins["settings"]])

try:
    nid = call("add_node", widget="NY Times")["id"]
    call("inspect_widget", node=nid)
except Exception as ex:
    print("expected failure:", str(ex)[:200])
time.sleep(1.0)
dl = call("list_dialogs")
print("dialogs:", json.dumps(dl, ensure_ascii=False)[:500])
if dl:
    a = call("answer_dialog")
    check("Don't Send" in a["action"], "error dialog answered with Don't Send: %s" % a)
    time.sleep(0.5)
    check(call("list_dialogs") == [], "no dialogs left")
else:
    print("(no dialog appeared)")
print("\nFAILS:", fails or "none")
