"""Print the tool list exactly as an AI client sees it (name, description, params)."""
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from _paths import ROOT, RELAY, OUT  # noqa: E402,F401

async def main():
    p = StdioServerParameters(command=sys.executable, args=[ROOT + r"\relay\mcp_orange.py"])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print("INSTRUCTIONS:", init.instructions, "\n")
            tools = (await s.list_tools()).tools
            total = 0
            for t in tools:
                props = t.inputSchema.get("properties", {})
                ps = ", ".join("%s%s" % (k, "*" if k in t.inputSchema.get("required", []) else "") for k in props)
                size = len(json.dumps({"d": t.description, "s": t.inputSchema}))
                total += size
                print("%-18s (%s)\n    %s" % (t.name, ps, " ".join((t.description or "").split())))
            print("\n%d tools, ~%d chars of schema+description in total" % (len(tools), total))

asyncio.run(main())
