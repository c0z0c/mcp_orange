r"""테스트 공용 경로. 하드코딩된 D:\ 경로 대신 이 파일 위치를 기준으로 한다."""
import os
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
RELAY = os.path.join(ROOT, "relay")
OUT = os.path.join(TESTS, "_out")          # 스크린샷/결과물 (git 제외)
os.makedirs(OUT, exist_ok=True)
for p in (RELAY, ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
