import json, sys, time
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call
fails = []
def check(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)
def idle():
    while call("get_status")["busy"]: time.sleep(0.3)

call("clear_workflow")
f = call("add_node", widget="File")["id"]; call("load_file", node=f, path="iris")
sc = call("add_node", widget="Scatter Plot")["id"]; call("add_link", source=f, sink=sc)
tb = call("add_node", widget="Data Table")["id"]; call("add_link", source=f, sink=tb)
idle()
# Orange reuses the last settings of a closed widget as defaults: pin the axes
call("set_setting", node=sc, name="attr_x", value="sepal length")
call("set_setting", node=sc, name="attr_y", value="sepal width")
idle()
r = call("select_data", node=sc, rect=[5.0, 2.5, 6.0, 3.0]); idle()
out = call("get_output", node=sc, channel="Selected Data", rows=1)["Selected Data"]
check(r["selected"] == out["rows"] and out["rows"] > 10, "rect selection -> %s rows in 'Selected Data' (selected=%s)" % (out["rows"], r["selected"]))
r = call("select_data", node=sc, clear=True); idle()
out = call("get_output", node=sc, channel="Selected Data")["Selected Data"]
check(out["type"] is None, "clear -> no selected output (%s)" % out)
r = call("select_data", node=sc, rows=[0, 1, 2, 50]); idle()
out = call("get_output", node=sc, channel="Selected Data", rows=1)["Selected Data"]
check(out["rows"] == 4, "rows=[0,1,2,50] -> %s selected rows" % out["rows"])
# table
r = call("select_data", node=tb, rows=[10, 11, 12]); idle()
out = call("get_output", node=tb, channel="Selected Data", rows=3)["Selected Data"]
check(out["rows"] == 3, "table rows selection -> %s rows" % out["rows"])
print("\nFAILS:", fails or "none")
