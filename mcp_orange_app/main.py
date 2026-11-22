"""mcp_orange.exe 의 진입점.

    mcp_orange.exe                  인자 없음 → 설정 마법사(GUI)
    mcp_orange.exe --mcp-server     AI 클라이언트가 실행하는 stdio MCP 서버 (별칭: -mcp_server)
    mcp_orange.exe --check ...      Orange 탐색 + 호환성 검사
    mcp_orange.exe --register ...   호환 확인 후 AI 클라이언트에 등록 (--unregister, --status)

--mcp-server 경로는 stdout 이 MCP 프로토콜이므로 어떤 것도 출력하지 않고, 그 모드에서 필요 없는
모듈(argparse 이외 CLI, tkinter)은 import 하지 않는다.
"""
from __future__ import annotations

import sys

SERVER_FLAGS = {"--mcp-server", "--mcp_server", "-mcp_server", "-mcp-server"}


def _run_server() -> int:
    from . import housekeeping, paths
    housekeeping.cleanup_in_background()
    if not paths.frozen():
        sys.path.insert(0, str(paths.repo_root() / "relay"))
        sys.path.insert(1, str(paths.repo_root()))
    import mcp_orange as server  # relay/mcp_orange.py (FastMCP stdio 서버)
    try:   # initialize 응답의 serverInfo.version 에 mcp_orange 버전을 싣는다
        from . import version
        server.mcp._mcp_server.version = version.full()
    except Exception:  # noqa: BLE001 - 표시용일 뿐
        pass
    server.main()
    return 0


def main(argv: "list[str] | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in SERVER_FLAGS for a in argv):
        return _run_server()
    if not argv:
        from . import wizard
        return wizard.main()
    from . import cli
    return cli.main(argv)
