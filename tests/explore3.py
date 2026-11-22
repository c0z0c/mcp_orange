import json, sys, time
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call
def X(code): print(call("debug_exec", code=code))
def idle():
    while call("get_status")["busy"]: time.sleep(0.3)

call("clear_workflow")
f = call("add_node", widget="File")["id"]; call("load_file", node=f, path="iris")
sc = call("add_node", widget="Scatter Plot")["id"]; call("add_link", source=f, sink=sc); idle()
tb = call("add_node", widget="Data Table")["id"]; call("add_link", source=f, sink=tb); idle()
X(f"""
w = widget("{sc}")
g = w.graph
result = {{'graph': type(g).__name__, 'sel_methods': [a for a in dir(g) if 'select' in a.lower()][:25],
 'view': type(g.plot_widget).__name__, 'sig': [a for a in dir(w) if 'select' in a.lower()][:20]}}
""")
X(f"""
w = widget("{tb}")
result = {{'tbl_sel': [a for a in dir(w) if 'select' in a.lower()][:30], 'views': type(w.tabs.currentWidget()).__name__ if hasattr(w,'tabs') else None}}
""")
# try rectangle selection in data coords on the scatter plot
X(f"""
from AnyQt.QtCore import QRectF
w = widget("{sc}")
g = w.graph
import numpy as np
vr = g.view_box.viewRect()
result = {{'viewrect': (vr.left(), vr.top(), vr.width(), vr.height()), 'n_sel_before': 0 if w.selection is None else len(w.selection)}}
""")
