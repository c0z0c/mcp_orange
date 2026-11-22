"""Orange must NOT be running. launch_orange via relay, then screenshot."""
import asyncio, base64, os, sys, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from _paths import ROOT, RELAY, OUT  # noqa: E402,F401


async def main():
    params = StdioServerParameters(command=sys.executable, args=[ROOT + r"\relay\mcp_orange.py"],
                                   env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print((await s.call_tool("orange_status", {})).structuredContent)
            t0 = time.time()
            res = await s.call_tool("launch_orange", {"timeout_s": 150})
            print("launch:", res.structuredContent, "%.0fs" % (time.time() - t0))
            shot = await s.call_tool("screenshot", {"target": "window"})
            for c in shot.content:
                if c.type == "image":
                    open(OUT + r"\shot_cold.png", "wb").write(base64.b64decode(c.data))
            print((await s.call_tool("orange_status", {})).structuredContent)

asyncio.run(main())
