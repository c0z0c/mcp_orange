"""Add -> inspect -> remove every non-obsolete widget; report failures/gaps."""
import json, sys, time, collections
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call, BridgeError

OUT_FILE = OUT + r"\sweep_result.json"
call("clear_workflow")
widgets = call("list_widgets", limit=2000)["widgets"]
print("widgets:", len(widgets))
res = []
kinds = collections.Counter()
t_all = time.time()
for i, w in enumerate(widgets):
    rec = {"widget": w["widget"], "name": w["name"], "category": w["category"]}
    t0 = time.time()
    nid = None
    try:
        nid = call("add_node", widget=w["widget"], timeout=60)["id"]
        ins = call("inspect_widget", node=nid, timeout=60)
        rec["n_settings"] = len(ins["settings"])
        rec["n_controls"] = sum(1 for s in ins["settings"] if "control" in s)
        rec["no_control"] = [s["name"] for s in ins["settings"] if "control" not in s]
        rec["control_kinds"] = sorted({s["control"]["kind"] for s in ins["settings"] if "control" in s})
        rec["buttons"] = [b["text"] for b in ins["buttons"]]
        rec["messages"] = ins["messages"]
        for k in rec["control_kinds"]:
            kinds[k] += 1
        rec["ok"] = True
    except Exception as ex:
        rec["ok"] = False
        rec["error"] = str(ex)[:300]
    finally:
        if nid:
            try:
                call("remove_node", node=nid, timeout=60)
            except Exception as ex:
                rec["remove_error"] = str(ex)[:200]
    rec["t"] = round(time.time() - t0, 2)
    res.append(rec)
    if not rec["ok"]:
        print("FAIL", w["name"], rec["error"][:150])
    if i % 25 == 0:
        print(i, "...", round(time.time() - t_all), "s", flush=True)
json.dump(res, open(OUT_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
ok = [r for r in res if r["ok"]]
print("\nOK %d / %d" % (len(ok), len(res)))
print("control kinds (widgets using):", dict(kinds))
print("slowest:", sorted(((r["t"], r["name"]) for r in res), reverse=True)[:5])
unk = [(r["name"], len(r["no_control"])) for r in ok if r["no_control"]]
print("widgets with settings lacking a GUI control:", len(unk))
