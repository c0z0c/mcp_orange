"""호환성 판정. '검증 목록과 일치'와 '프로브 통과'를 구분해서 말한다 — 프로브는 동작 보장이 아니다."""
from __future__ import annotations

from dataclasses import dataclass

from .probe import ProbeResult

VERIFIED = "verified"          # 검증된 조합과 정확히 일치하고 프로브 통과
PROBE_OK = "probe_ok"          # 검증 목록엔 없지만 필요한 내부 심볼은 모두 있음 (사용자 확인 필요)
INCOMPATIBLE = "incompatible"  # 필수 심볼이 없거나 실행 불가
ERROR = "error"                # 검사 자체를 못 함 (python 실행 실패 등)

# 실제로 end-to-end 시나리오(tests/matrix.py)까지 통과시켜 본 조합.
# Orange3 버전 -> (orange-canvas-core, orange-widget-base)
VERIFIED_COMBOS = {
    "3.32.0": ("0.1.26", "4.16.1"),   # Python 3.8 / PyQt5 5.12 (포터블)
    "3.40.0": ("0.2.7", "4.27.0"),    # Python 3.12 / PyQt6 6.8 (포터블)
}

LABEL = {
    VERIFIED: "호환 (검증됨)",
    PROBE_OK: "미검증 (필수 심볼은 있음)",
    INCOMPATIBLE: "비호환",
    ERROR: "검사 실패",
}


@dataclass
class Verdict:
    status: str
    summary: str
    orange_version: str = ""

    @property
    def label(self) -> str:
        return LABEL[self.status]

    @property
    def usable(self) -> bool:
        return self.status in (VERIFIED, PROBE_OK)


def judge(res: ProbeResult) -> Verdict:
    if not res.ran:
        return Verdict(ERROR, res.error or "검사 실패")
    v = res.versions
    ov = v.get("Orange3") or ""
    if not ov:
        return Verdict(INCOMPATIBLE, "Orange3 패키지를 찾지 못했습니다 (이 python 은 Orange 가 아닙니다)", ov)
    if res.fatal:
        names = ", ".join(c.name for c in res.fatal[:4])
        more = "" if len(res.fatal) <= 4 else " 외 %d건" % (len(res.fatal) - 4)
        return Verdict(INCOMPATIBLE, "필수 항목 실패: %s%s" % (names, more), ov)
    combo = VERIFIED_COMBOS.get(ov)
    if combo and combo == (v.get("orange-canvas-core"), v.get("orange-widget-base")):
        extra = ""
        if res.warnings:
            extra = " (일부 기능 제한: %s)" % ", ".join(c.name for c in res.warnings[:3])
        return Verdict(VERIFIED, "Orange %s 는 검증된 조합입니다%s" % (ov, extra), ov)
    known = ", ".join(sorted(VERIFIED_COMBOS))
    return Verdict(
        PROBE_OK,
        "Orange %s 는 검증 목록(%s)에 없습니다. 필수 심볼은 모두 있지만 동작은 보장되지 않습니다" % (ov, known), ov)
