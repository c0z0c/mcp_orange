import json, sys, time
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call
def X(code): print(call("debug_exec", code=code))
def idle():
    while call("get_status")["busy"]: time.sleep(0.3)
nodes = {n["name"]: n["id"] for n in call("list_nodes")}
sc, tb = nodes["Scatter Plot"], nodes["Data Table"]
X(f"""
from AnyQt.QtCore import QRectF
w = widget("{sc}")
g = w.graph
g.select_by_rectangle(QRectF(5.0, 2.5, 1.0, 0.5))
result = {{'sel_after_rect': None if w.selection is None else len(w.selection), 'attr': [a for a in ('selection_changed',) if hasattr(g,a)]}}
""")
idle(); time.sleep(0.5)
print(json.dumps(call("get_output", node=sc, rows=2), ensure_ascii=False)[:350])
X(f"""
w = widget("{sc}")
import inspect
result = inspect.getsource(type(w.graph).select_by_rectangle)[:600] + '\\n----\\n' + inspect.getsource(type(w.graph).select_by_indices)[:500]
""")
# table
X(f"""
from AnyQt.QtWidgets import QTableView, QAbstractItemView
w = widget("{tb}")
views = w.findChildren(QTableView)
result = [(type(v).__name__, v.isVisible(), v.model().rowCount() if v.model() else None) for v in views]
""")
