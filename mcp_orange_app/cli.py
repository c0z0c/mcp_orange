"""명령줄: --check / --register / --unregister / --status / --gui / --version"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from . import version, compat, config, discovery, launcher, paths


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):  # 콘솔 코드페이지와 무관하게 한글이 깨지지 않게
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcp_orange", allow_abbrev=False,
        description="AI(MCP 클라이언트)가 Orange 3 를 조작하게 해 주는 도구. 인자 없이 실행하면 설정 창이 열립니다.")
    act = p.add_mutually_exclusive_group()
    act.add_argument("--mcp-server", "--mcp_server", "-mcp_server", dest="mcp_server", action="store_true",
                     help="stdio MCP 서버로 실행 (AI 클라이언트가 호출하는 모드)")
    act.add_argument("--check", action="store_true", help="설치된 Orange 를 찾아 호환성을 검사")
    act.add_argument("--register", action="store_true", help="호환 확인 후 AI 클라이언트에 등록")
    act.add_argument("--unregister", action="store_true", help="AI 클라이언트에서 등록 해지")
    act.add_argument("--status", action="store_true", help="클라이언트별 등록 현황")
    act.add_argument("--gui", action="store_true", help="설정 창 열기 (인자 없이 실행해도 같음)")
    act.add_argument("--update", action="store_true", help="새 버전을 확인하고, 있으면 확인 후 업그레이드")
    act.add_argument("--version", action="store_true")

    p.add_argument("--python", metavar="PYTHON_EXE", help="--check: 이 Orange 의 python.exe 만 검사")
    p.add_argument("--no-scan", action="store_true", help="--check: 드라이브 스캔 없이 빠른 후보만")
    p.add_argument("--deep", action="store_true",
                   help="--check: Orange 를 창 없이(offscreen) 실제로 띄워 시나리오까지 실행 (수 분 걸릴 수 있음)")
    p.add_argument("--select", action="store_true", help="--check: 검사한 것 중 사용 가능한 첫 Orange 를 사용 대상으로 저장")
    p.add_argument("--json", action="store_true", help="JSON 으로 출력")
    p.add_argument("--client", metavar="LIST", help="대상 클라이언트(쉼표 구분)")
    p.add_argument("--name", default="orange3", help="클라이언트에 등록되는 이름 (기본: orange3)")
    p.add_argument("--force", action="store_true", help="--register/--unregister: 비호환·다른 설정이어도 진행")
    p.add_argument("--yes", "-y", action="store_true", help="--update: 확인 질문 없이 업그레이드")
    p.add_argument("--dry-run", action="store_true", help="--register/--unregister: 실제로 바꾸지 않고 할 일만 표시")
    return p


# ------------------------------------------------------------------ --check
def _check_one(c: discovery.Candidate) -> launcher.Target:
    return launcher.check(c.python, save=True)


def cmd_check(args) -> int:
    if args.python:
        cands = [discovery.Candidate(Path(args.python), "user")]
    else:
        cands = discovery.find_orange_pythons(scan=not args.no_scan)
    if not cands:
        msg = "Orange 를 찾지 못했습니다. --python <python.exe> 로 직접 지정하세요."
        print(json.dumps({"found": []}, ensure_ascii=False) if args.json else msg)
        return 1
    with ThreadPoolExecutor(max_workers=min(4, len(cands))) as ex:
        targets = list(ex.map(_check_one, cands))
    # 사용 우선순위(검증됨 > 미검증, 최신 버전 우선) 순으로 보여 준다 — 맨 위가 자동 선택 대상
    order = sorted(range(len(cands)), key=lambda i: launcher._rank(targets[i]) if targets[i].usable else (-1, ()), reverse=True)
    cands = [cands[i] for i in order]
    targets = [targets[i] for i in order]

    deep = {}
    if args.deep:
        from . import smoke
        for t in targets:
            if t.usable:
                say = (lambda s: None) if args.json else (lambda s: print(s, flush=True))
                if not args.json:
                    print("\n[deep] %s" % t.python)
                deep[t.python] = smoke.run(t.python, say=say).to_dict()

    chosen: Optional[launcher.Target] = targets[0] if targets and targets[0].usable else None
    if args.select and chosen:
        config.update(orange_python=chosen.python)

    if args.json:
        print(json.dumps([{"python": t.python, "source": c.source, "status": t.status, "summary": t.summary,
                           "orange_version": t.orange_version, "python_version": t.py_version,
                           "failed_checks": t.checks, "deep": deep.get(t.python)}
                          for c, t in zip(cands, targets)], indent=2, ensure_ascii=False))
    else:
        print("\n발견한 Orange %d 개:" % len(targets))
        for c, t in zip(cands, targets):
            print("  [%s] %s  (Orange %s, Python %s, 출처: %s)" % (
                compat.LABEL.get(t.status, t.status), t.python, t.orange_version or "?", t.py_version or "?", c.source))
            print("      %s" % t.summary)
            for f in t.checks[:6]:
                print("      - 실패: %s %s" % (f["name"], f["detail"]))
        if args.select and chosen:
            print("\n사용 대상으로 저장: %s" % chosen.python)
        elif not args.select and chosen:
            print("\n(사용 대상으로 저장하려면 --select 를 붙이세요. 등록할 때 자동으로 저장되기도 합니다.)")
    if args.deep:
        bad = [p for p, d in deep.items() if not d["ok"]]
        if bad:
            return 2
    return 0 if any(t.usable for t in targets) else 1


# --------------------------------------------------------- 등록 / 해지 / 현황
def cmd_manage(args) -> int:
    from mcp_manage import clients as C
    from mcp_manage.cli import _targets
    spec = C.default_spec(args.name)
    only = _targets(args.client)
    if args.status:
        d = C.info(spec, only)
        d["orange"] = config.load().get("orange_python")
        print(json.dumps(d, indent=2, ensure_ascii=False) if args.json else C.render_info(d))
        return 0
    if args.register:
        try:
            t = launcher.resolve_target(persist=not args.dry_run)
        except launcher.LaunchError as ex:
            if not args.force:
                print("등록하지 않았습니다.\n%s" % ex, file=sys.stderr)
                return 1
            print("경고(--force): %s" % ex, file=sys.stderr)
        else:
            print("Orange: %s\n  %s [%s]\n  %s" % (t.python, compat.LABEL[t.status], t.orange_version, t.summary))
            if not args.dry_run:
                config.update(orange_python=t.python)
        return C.run_action(spec, "install", only, force=args.force, dry_run=args.dry_run)
    return C.run_action(spec, "uninstall", only, force=args.force, dry_run=args.dry_run)


# ------------------------------------------------------------------ --update
def cmd_update(args) -> int:
    from . import update
    info = update.check()
    print("현재 %s / 최신 %s" % (version.full(), info.version))
    if not info.newer:
        print("최신 버전입니다.")
        return 0
    print("새 버전이 있습니다: %s" % info.page)
    if not paths.frozen():
        print("소스로 실행 중이라 자동 교체는 하지 않습니다. 위 페이지에서 받으세요.")
        return 0
    if not args.yes:
        try:
            print("실행 중인 이전 버전 mcp_orange 서버(AI 클라이언트가 띄운 것)는 교체 후 종료됩니다. Orange 는 종료되지 않습니다.")
            if input("업그레이드할까요? (y/N) ").strip().lower() != "y":
                return 0
        except EOFError:
            return 0
    killed = update.install(info)
    if killed:
        print("실행 중이던 이전 버전 서버 %d개를 종료했습니다 (클라이언트가 다음 호출 때 다시 시작합니다)." % killed)
    print("업그레이드 완료. 다시 실행하면 %s 입니다." % info.version)
    return 0


def main(argv: "list[str] | None" = None) -> int:
    _utf8()
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        parser.error("알 수 없는 인자: %s" % " ".join(unknown))
    try:
        if args.version:
            print("mcp_orange %s" % version.display())
            return 0
        if args.update:
            return cmd_update(args)
        if args.gui:
            from . import wizard
            return wizard.main()
        if args.check:
            return cmd_check(args)
        if args.register or args.unregister or args.status:
            return cmd_manage(args)
    except Exception as e:  # noqa: BLE001
        from mcp_manage import clients as C
        from .update import UpdateError
        if isinstance(e, (C.ClientError, UpdateError)):
            print("오류: %s" % e, file=sys.stderr)
            return 1
        raise
    parser.print_help()
    return 0
