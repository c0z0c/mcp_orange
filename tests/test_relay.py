"""End-to-end through the real stdio MCP relay (mcp SDK client)."""
import asyncio
import json
import os
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from _paths import ROOT, RELAY, OUT  # noqa: E402,F401
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def data(res):
    """Structured tool result -> python object."""
    assert not res.isError, res.content[0].text if res.content else res
    if res.structuredContent is not None:
        sc = res.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) and list(sc) == ["result"] else sc
    return json.loads(res.content[0].text)


async def main():
    exe = os.environ.get("MCP_ORANGE_EXE")      # 설정되면 배포용 exe 를 MCP 서버로 사용
    print("server:", exe + " --mcp-server" if exe else "python relay/mcp_orange.py")
    params = StdioServerParameters(
        command=exe or sys.executable,
        args=["--mcp-server"] if exe else [ROOT + r"\relay\mcp_orange.py"],
        env=dict(os.environ))   # MCP_ORANGE_HOME 등 격리 변수를 릴레이에 전달
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = [t.name for t in tools.tools]
            print("tools:", names)
            check(len(names) >= 18, "relay exposes %d tools" % len(names))

            st = data(await s.call_tool("orange_status", {}))
            print("status:", st)
            if not st["running"]:
                t0 = time.time()
                la = data(await s.call_tool("launch_orange", {"timeout_s": 150}))
                check(la.get("already_running") is False,
                      "launch_orange started Orange in %.0fs" % (time.time() - t0))
            else:
                print("(Orange already running)")

            await s.call_tool("clear_workflow", {})
            f = data(await s.call_tool("add_node", {"widget": "File"}))
            await s.call_tool("load_file", {"node": f["id"], "path": "heart_disease"})
            k = data(await s.call_tool("add_node", {"widget": "Tree"}))
            ts = data(await s.call_tool("add_node", {"widget": "Test and Score"}))
            await s.call_tool("add_link", {"source": f["id"], "sink": ts["id"], "sink_channel": "Data"})
            await s.call_tool("add_link", {"source": k["id"], "sink": ts["id"], "sink_channel": "Learner"})
            idle = data(await s.call_tool("wait_until_idle", {"timeout_s": 60}))
            check(idle["idle"], "wait_until_idle -> %s" % idle)
            out = data(await s.call_tool("get_output", {"node": f["id"], "rows": 2}))
            print("heart_disease:", out["Data"]["rows"], "rows,", len(out["Data"]["attributes"]), "attrs")
            check(out["Data"]["rows"] == 303, "heart_disease has 303 rows")

            bad = await s.call_tool("update_widget", {"node": k["id"], "settings": {"nope": 1}})
            check(bad.isError and "unknown setting" in bad.content[0].text,
                  "bad setting -> clear error: " + (bad.content[0].text[:100] if bad.content else ""))

            shot = await s.call_tool("screenshot", {"target": "window"})
            kinds = [c.type for c in shot.content]
            check("image" in kinds, "screenshot returns an image content (%s)" % kinds)
            for c in shot.content:
                if c.type == "image":
                    import base64
                    open(OUT + r"\shot_relay.png", "wb").write(base64.b64decode(c.data))


asyncio.run(main())
print("\nFAILS:", fails if fails else "none")
sys.exit(1 if fails else 0)
