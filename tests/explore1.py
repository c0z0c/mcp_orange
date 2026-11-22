import sys, json
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call

def X(code):
    r = call("debug_exec", code=code)
    print(r)

k = [n for n in call("list_nodes") if n["name"] == "k-Means"]
if not k:
    f = call("add_node", widget="File")
    k = [call("add_node", widget="k-Means")]
    call("add_link", source=f["id"], sink=k[0]["id"])
nid = k[0]["id"]
print("node", nid)
X(f"""
w = widget("{nid}")
h = w.settingsHandler
result = {{
 'cls': type(w).__name__,
 'handler': type(h).__name__,
 'known': {{n: type(s).__name__ for n, s in h.known_settings.items()}} if hasattr(h,'known_settings') else None,
 'handler_attrs': [a for a in dir(h) if 'setting' in a.lower()][:20],
}}
""")
X(f"""
w = widget("{nid}")
result = {{
 'controlled': {{k: [type(c).__name__ + ':' + type(getattr(c,'control',None)).__name__ for c in v] for k, v in w.controlled_attributes.items()}},
 'attrs': {{n: repr(getattr(w, n, None)) for n in ['k','smart_init','n_init','max_iterations','auto_commit','optimize_k','k_from','k_to','scoring']}},
}}
""")
X(f"""
w = widget("{nid}")
msgs = {{}}
for grp in ('Error','Warning','Information'):
    g = getattr(w, grp, None)
    msgs[grp] = (list(g.active) if g is not None else None, [a for a in dir(g) if not a.startswith('_')][:15] if g is not None else None)
result = msgs
""")
X(f"""
w = widget("{nid}")
result = {{
 'busy': [a for a in dir(w) if a in ('isBlocking','blockingStateChanged','isInvalidated','isReady','task','_task','__task')],
 'title': w.windowTitle(),
 'visible': w.isVisible(),
 'outputs': [o.name for o in type(w).get_signals('outputs')],
 'inputs': [i.name for i in type(w).get_signals('inputs')],
}}
""")
