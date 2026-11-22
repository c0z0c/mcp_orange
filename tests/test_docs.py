import json, sys
from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
sys.path.insert(0, RELAY)
from bridge_client import call
fails = []
def check(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)

h = call("get_widget_help", widget="k-Means")
check(h["description"] and h["inputs"][0]["name"] == "Data", "core widget help: %s | in=%s" % (h["description"][:50], h["inputs"]))
check(h["offline_help"] is None and "note" in h, "core widget notes manual is online-only")
# 애드온 위젯은 설치된 경우에만 확인한다(없으면 깔끔한 오류로 건너뜀)
for label, name in (("educational", "Interactive k-Means"), ("text addon", "Word Cloud")):
    try:
        h = call("get_widget_help", widget=name)
        print("%s:" % label, h.get("offline_help_file"), (h.get("offline_help") or "")[:150].replace("\n", " "))
    except Exception as ex:  # noqa: BLE001
        check("no node or widget" in str(ex), "%s widget %r not installed -> clean error" % (label, name))
s = call("get_widget_source", widget="k-Means", max_chars=800)
check(s["total_chars"] > 3000 and s["next_offset"] == 800 and "class OWKMeans" in s["source"], "source paging ok (total %d)" % s["total_chars"])
s2 = call("get_widget_source", widget="k-Means", offset=s["next_offset"], max_chars=800)
check(s2["offset"] == 800 and s2["source"] != s["source"], "second page differs")
try:
    call("get_widget_source", widget="No Such Widget")
    check(False, "unknown widget should error")
except Exception as ex:
    check("no node or widget" in str(ex), "unknown widget error: %s" % ex)
print("\nFAILS:", fails or "none")
