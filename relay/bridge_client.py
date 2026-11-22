"""Tiny stdlib client for the Orange bridge (used by the MCP relay and tests)."""
import json
import os
import socket
import itertools



def discovery_file():
    """호출 시점에 계산한다(테스트가 MCP_ORANGE_HOME 으로 격리된 Orange 를 가리킬 수 있게)."""
    return os.path.join(
        os.environ.get("MCP_ORANGE_HOME")
        or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "mcp_orange"),
        "bridge.json")


DISCOVERY_FILE = discovery_file()
_ids = itertools.count(1)


class BridgeError(RuntimeError):
    pass


def _discover():
    try:
        with open(discovery_file(), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise BridgeError(
            "Orange bridge not running (no %s). Call launch_orange." % discovery_file())


def call(cmd, timeout=130.0, **args):
    info = _discover()
    try:
        sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=5)
    except OSError as ex:
        raise BridgeError("Orange bridge unreachable (stale discovery file?): %s" % ex)
    with sock:
        sock.settimeout(timeout)
        req = {"id": next(_ids), "token": info["token"], "cmd": cmd, "args": args}
        sock.sendall(json.dumps(req).encode("utf-8") + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                raise BridgeError("bridge closed the connection")
            buf += chunk
    reply = json.loads(buf.decode("utf-8"))
    if not reply.get("ok"):
        raise BridgeError(reply.get("error", "unknown error"))
    return reply["result"]
