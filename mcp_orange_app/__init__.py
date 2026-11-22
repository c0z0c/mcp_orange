"""mcp_orange 애플리케이션 계층: Orange 탐색, 호환성 검사, 실행, 설정 마법사.

표준 라이브러리만 쓴다(`mcp` SDK 는 --mcp-server 모드에서만, tkinter 는 GUI 에서만 지연 import).

버전은 version.txt + git 커밋 수로 정해진다 (자세한 규칙은 version.py). `__version__` 은 처음 쓸 때
계산한다 — 개발 모드에서 git 을 부르는 비용을 import 시점에 치르지 않기 위해서다.
"""


def __getattr__(name):
    if name == "__version__":
        from . import version
        return version.full()
    raise AttributeError(name)
