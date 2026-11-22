import sys, json
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call

def X(code):
    print(call("debug_exec", code=code))

call("clear_workflow")
f = call("add_node", widget="File")
print(json.dumps(call("inspect_widget", node=f["id"]), indent=1)[:2500])
X(f"""
w = widget("{f['id']}")
result = [a for a in dir(w) if any(s in a.lower() for s in ('path','load','source','file','browse','reload')) and not a.startswith('__')][:60]
""")
X("""
import Orange, os
result = os.path.join(os.path.dirname(Orange.__file__), 'datasets')
""")
