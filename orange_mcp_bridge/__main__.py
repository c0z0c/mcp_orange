"""Launcher: ``python -m orange_mcp_bridge`` starts Orange canvas with the bridge.

Orange's own sources are not modified; we subclass ``OMain`` and hook
``create_main_window``.
"""
import os
import sys
import logging

from Orange.canvas.__main__ import OMain

log = logging.getLogger("orange_mcp_bridge")


def _isolate_settings():
    """MCP_ORANGE_SETTINGS_DIR 이 있으면 Orange 의 설정/캐시/데이터 경로를 그 폴더로 돌린다.

    포터블 Orange 는 etc/orangerc.conf 로 설정(위젯 기본값, canvas 설정)을 *설치 폴더 안*에 저장한다.
    호환성 검사/테스트가 사용자의 설치본(또는 읽기 전용이어야 하는 테스트 설치본)을 건드리지 않게,
    Orange 의 경로 조회 함수만 바꿔 끼운다 (Orange 소스는 수정하지 않는다).
    """
    base = os.environ.get("MCP_ORANGE_SETTINGS_DIR")
    if not base:
        return
    from Orange.misc import environ
    mapping = {
        "widget_settings_dir": os.path.join(base, "config", "widgets"),
        "canvas_settings_dir": os.path.join(base, "config", "canvas"),
        "cache_dir": os.path.join(base, "cache"),
        "data_dir_base": os.path.join(base, "share"),
        "log_dir": os.path.join(base, "log"),
    }
    original = environ.get_path

    def get_path(name, default=None):
        return mapping.get(name) or original(name, default)

    environ.get_path = get_path
    log.info("settings isolated under %s", base)


class McpOMain(OMain):
    _bridge = None

    def argument_parser(self):
        parser = super().argument_parser()
        parser.add_argument(
            "--welcome", action="store_true",
            help="Show the 'Welcome to Orange' screen (hidden by default "
                 "when running with the MCP bridge)")
        return parser

    def show_welcome_screen(self, mainwindow):
        if self.options.welcome:
            super().show_welcome_screen(mainwindow)

    def create_main_window(self):
        window = super().create_main_window()
        try:
            from .server import start_bridge
            self._bridge = start_bridge()
        except Exception:  # never prevent Orange from starting
            log.exception("Failed to start MCP bridge")
        return window


def main(argv=None):
    _isolate_settings()
    return McpOMain().run(argv)


if __name__ == "__main__":
    sys.exit(main())
