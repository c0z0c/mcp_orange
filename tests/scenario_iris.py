"""Scenario: a moderately complex workflow on iris, built and driven through the bridge.
Needs Orange running via scripts\\restart.ps1. Run with the system python."""
import json
import sys
import time
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call, BridgeError

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def wait_idle(timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not call("get_status")["busy"]:
            return True
        time.sleep(0.3)
    return False


def add(widget, x, y, title=None):
    return call("add_node", widget=widget, x=x, y=y, title=title)["id"]


call("clear_workflow")
file_ = add("File", 60, 200)
call("load_file", node=file_, path="iris")
check(wait_idle(), "idle after loading iris")
out = call("get_output", node=file_, rows=3)["Data"]
check(out["rows"] == 150, "File output has 150 rows (got %s)" % out.get("rows"))
check(len(out["attributes"]) == 4, "iris has 4 attributes")

# k-Means branch
km = add("k-Means", 260, 80)
tbl = add("Data Table", 460, 80)
call("add_link", source=file_, sink=km)
call("add_link", source=km, sink=tbl, source_channel="Data")
check(wait_idle(), "idle after k-Means linked")
ins = call("inspect_widget", node=km)
names = {s["name"]: s for s in ins["settings"]}
print("k-Means settings:", {k: (v["value"], v.get("control", {}).get("kind")) for k, v in names.items()})
check("k" in names and names["k"]["control"]["kind"] == "spin", "k-Means exposes 'k' as spin")
r = call("update_widget", node=km, settings={"optimize_k": "Fixed", "k": 4})
print("update:", json.dumps(r, ensure_ascii=False)[:600])
check(wait_idle(), "idle after k=4")
kout = call("get_output", node=km, channel="Data", rows=150)["Data"]
cols = kout["head_columns"]
check("Cluster" in cols, "k-Means output has Cluster column (cols=%s)" % cols[-3:])
if "Cluster" in cols:
    ci = cols.index("Cluster")
    clusters = {row[ci] for row in kout["head"]}
    check(len(clusters) == 4, "exactly 4 clusters (got %s)" % sorted(clusters))
r = call("update_widget", node=km, settings={"k": 2})
check(wait_idle(), "idle after k=2")
kout = call("get_output", node=km, channel="Data", rows=150)["Data"]
ci = kout["head_columns"].index("Cluster")
check(len({row[ci] for row in kout["head"]}) == 2, "k=2 -> 2 clusters (callback chain works)")

# Learners -> Test & Score
lr = add("Logistic Regression", 260, 200)
tree = add("Tree", 260, 280)
knn = add("kNN", 260, 360)
ts = add("Test and Score", 460, 280)
call("add_link", source=file_, sink=ts, sink_channel="Data")
for l in (lr, tree, knn):
    call("add_link", source=l, sink=ts, sink_channel="Learner")
check(wait_idle(60), "idle after Test and Score")
st = call("get_status", node=ts)["nodes"][0]
print("Test&Score status:", st)
check(not st.get("messages", {}).get("error"), "Test and Score has no errors")

# PCA -> Scatter Plot, Sampler -> Box Plot
pca = add("PCA", 260, 460)
sc = add("Scatter Plot", 460, 460)
call("add_link", source=file_, sink=pca)
call("add_link", source=pca, sink=sc, source_channel="Transformed Data")
smp = add("Data Sampler", 260, 560)
bp = add("Box Plot", 460, 560)
call("add_link", source=file_, sink=smp)
call("add_link", source=smp, sink=bp, source_channel="Data Sample")
check(wait_idle(60), "idle at the end")

st = call("get_status")
for n in st["nodes"]:
    print(" ", n["id"], n["title"], "busy=%s" % n.get("busy"), n.get("messages", ""))
check(len(call("list_nodes")) == 11, "11 nodes")
check(len(call("list_links")) == 10, "10 links (got %d)" % len(call("list_links")))
ev = call("get_output", node=ts)
print("Test&Score outputs:", json.dumps(ev, ensure_ascii=False)[:500])
check(ev["Evaluation Results"]["type"] is not None, "Test and Score produced Evaluation Results")
print(call("screenshot", target=sc, path=OUT + r"\shot_scatter.png"))

# save / reload round trip
p = OUT + r"\scenario_iris.ows"
call("save_workflow", path=p)
call("clear_workflow")
check(len(call("list_nodes")) == 0, "cleared")
o = call("open_workflow", path=p)
check(o["nodes"] == 11, "reloaded 11 nodes from .ows (got %s)" % o["nodes"])
wait_idle(60)
ins = call("inspect_widget", node=[n for n in call("list_nodes") if n["name"] == "k-Means"][0]["id"])
k_after = [s for s in ins["settings"] if s["name"] == "k"][0]["value"]
check(k_after == 2, "k=2 persisted through save/load (got %s)" % k_after)
print(call("screenshot", target="window", path=OUT + r"\shot_scenario.png"))
print("\nFAILS:", fails if fails else "none")
sys.exit(1 if fails else 0)
