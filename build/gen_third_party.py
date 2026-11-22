"""빌드 venv 에 설치된 패키지의 라이선스 메타데이터로 THIRD_PARTY_NOTICES.md 를 만든다.

    build\\.venv\\Scripts\\python.exe build\\gen_third_party.py
exe 에 들어가는 것은 relay/requirements.txt 의 의존 트리(mcp 와 그 하위)다. PyInstaller 자체는 빌드 도구이며
부트로더만 exe 에 들어간다(GPL-2.0 + 예외: 결과물에 GPL 이 전염되지 않음).
"""
import importlib.metadata as md
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_ONLY = {"pip", "setuptools", "wheel", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile",
              "packaging", "pywin32-ctypes"}


def req_names(dist, seen):
    for r in dist.requires or []:
        m = re.match(r"[A-Za-z0-9_.\-]+", r)
        if not m or 'extra ==' in r:
            continue
        n = m.group(0).lower().replace("_", "-")
        if n in seen:
            continue
        seen.add(n)
        try:
            req_names(md.distribution(n), seen)
        except md.PackageNotFoundError:
            pass


def license_of(d):
    meta = d.metadata
    lic = meta.get("License-Expression") or ""
    if not lic:
        cls = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
        lic = ", ".join(cls)
    if not lic:
        raw = (meta.get("License") or "").strip().splitlines()
        lic = raw[0][:80] if raw else "(메타데이터에 없음)"
    return lic


seen = set()
for top in ("mcp",):
    seen.add(top)
    req_names(md.distribution(top), seen)
rows = []
for n in sorted(seen):
    if n in BUILD_ONLY:
        continue
    try:
        d = md.distribution(n)
    except md.PackageNotFoundError:
        continue
    home = d.metadata.get("Home-page") or (d.metadata.get_all("Project-URL") or [""])[0].split(",")[-1].strip()
    rows.append((d.metadata["Name"], d.version, license_of(d), home))

out = ["# 제3자 구성요소 (배포 exe 에 포함)", "",
       "`mcp_orange.exe` 는 아래 오픈소스 구성요소를 포함합니다. 저작권과 라이선스는 각 저작권자에게 있으며,",
       "정확한 전문은 각 프로젝트의 배포본/저장소를 보세요. 이 목록은 `build/gen_third_party.py` 가 빌드 환경의",
       "패키지 메타데이터로 생성했습니다.", "",
       "| 패키지 | 버전 | 라이선스(메타데이터 기준) | 홈 |", "|---|---|---|---|"]
out += ["| %s | %s | %s | %s |" % r for r in rows]
out += ["", "이 밖에 exe 에는 다음이 들어 있습니다.", "",
        "* **Python** (PSF License) 인터프리터와 표준 라이브러리, **Tcl/Tk**(tkinter, BSD 계열), **OpenSSL**(Apache-2.0)",
        "* **PyInstaller 부트로더** (GPL-2.0 + 부트로더 예외 — 이 예외로 결과물의 라이선스는 제한되지 않음)",
        "", "mcp_orange 자체는 GPL-3.0-or-later 입니다 ([LICENSE](LICENSE), [NOTICE.md](NOTICE.md))."]
(ROOT / "THIRD_PARTY_NOTICES.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("wrote THIRD_PARTY_NOTICES.md with %d packages (python %s)" % (len(rows), sys.version.split()[0]))
