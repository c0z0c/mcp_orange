"""Smoke test: build a small workflow through the bridge and screenshot it.
Run with the system python while Orange (run_orange.ps1) is up."""
import json
import sys
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, __file__.rsplit("\\tests", 1)[0] + "\\relay")
from bridge_client import call


def show(label, value):
    print("==", label)
    print(json.dumps(value, ensure_ascii=False, indent=1)[:1500])


show("ping", call("ping"))
show("widgets(k-means)", call("list_widgets", query="k-means"))
f = call("add_node", widget="File")
k = call("add_node", widget="k-Means")
d = call("add_node", widget="Data Table")
show("nodes", call("list_nodes"))
l1 = call("add_link", source=f["id"], sink=k["id"])
l2 = call("add_link", source=f["id"], sink=d["id"])
show("links", call("list_links"))
show("shot", call("screenshot", target="window", path=OUT + r"\shot_graph.png"))
