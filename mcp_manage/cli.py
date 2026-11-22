"""명령줄 인터페이스: 상태 보기 / 등록 / 해지 / GUI.

    manage.py status    [--client LIST] [--json]
    manage.py install   [--client LIST] [--force] [--dry-run] [--name NAME]
    manage.py uninstall [--client LIST] [--force] [--dry-run] [--name NAME]
    manage.py gui
"""
from __future__ import annotations

import argparse
import json
import sys

from . import clients as C


def _targets(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    names = [n.strip().lower() for n in raw.split(",") if n.strip()]
    bad = [n for n in names if n not in C.CLIENTS]
    if bad:
        raise SystemExit(f"알 수 없는 클라이언트: {', '.join(bad)} (사용 가능: {', '.join(C.CLIENTS)})")
    return names


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="manage.py", allow_abbrev=False,
        description="Orange MCP 서버를 AI 클라이언트(Claude, Claude Desktop, Codex/ChatGPT, Antigravity)에 "
                    "등록하거나 해지합니다.")
    sub = p.add_subparsers(dest="cmd")

    def common(sp, mutating):
        sp.add_argument("--client", metavar="LIST",
                        help="대상 클라이언트(쉼표 구분: %s). 생략하면 설치된 모든 클라이언트." % ",".join(C.CLIENTS))
        sp.add_argument("--name", default="orange3", help="클라이언트에 등록되는 이름 (기본: orange3)")
        if mutating:
            sp.add_argument("--force", action="store_true",
                            help="이름만 같은 다른 설정도 교체/제거하고, 서버 파일 점검을 건너뜁니다")
            sp.add_argument("--dry-run", action="store_true", help="실제로 바꾸지 않고 할 일만 보여 줍니다")

    sp = sub.add_parser("status", aliases=["info"], help="클라이언트별 등록 현황")
    common(sp, False)
    sp.add_argument("--json", action="store_true", help="JSON 으로 출력")
    common_i = sub.add_parser("install", aliases=["register"], help="클라이언트에 등록")
    common(common_i, True)
    common_u = sub.add_parser("uninstall", aliases=["unregister", "remove"], help="클라이언트에서 해지")
    common(common_u, True)
    sub.add_parser("gui", help="등록/해지 창 열기")
    return p


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):  # 콘솔 코드페이지와 무관하게 한글이 깨지지 않게
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0
    if args.cmd == "gui":
        from . import gui
        return gui.main()
    try:
        spec = C.default_spec(args.name)
        only = _targets(args.client)
        if args.cmd in ("status", "info"):
            d = C.info(spec, only)
            print(json.dumps(d, indent=2, ensure_ascii=False) if args.json else C.render_info(d))
            return 0
        action = "install" if args.cmd in ("install", "register") else "uninstall"
        return C.run_action(spec, action, only, force=args.force, dry_run=args.dry_run)
    except C.ClientError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
