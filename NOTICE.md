# NOTICE

## mcp_orange 라이선스
Copyright (C) 2026 mcp_orange contributors

이 프로그램은 자유 소프트웨어입니다. Free Software Foundation 이 발표한
**GNU General Public License 버전 3 또는 (선택에 따라) 그 이후 버전**의 조건에 따라
재배포하거나 수정할 수 있습니다. 전문은 [LICENSE](LICENSE) 를 참고하세요.

이 프로그램은 유용하기를 바라며 배포되지만 **어떠한 보증도 없습니다**. 상품성이나 특정 목적에의
적합성에 대한 묵시적 보증도 포함하지 않습니다.

SPDX-License-Identifier: GPL-3.0-or-later

### 왜 GPL 인가
`orange_mcp_bridge/` 는 Orange 프로세스 안에서 실행되며 Orange 의 `OMain` 을 상속하고 내부 객체를
직접 호출합니다. Orange3 는 GPL-3.0+ 이므로, 이 결합물은 GPL-3.0+ 로 배포합니다.
`relay/` 는 별도 프로세스이지만 같은 저장소에서 같은 라이선스로 배포합니다.

## 비공식 프로젝트 고지
mcp_orange 는 **Orange Data Mining / University of Ljubljana (Bioinformatics Laboratory) 와
관련이 없는 비공식·독립 프로젝트**입니다. 해당 기관의 보증이나 후원을 받지 않았습니다.
"Orange" 는 Orange3 프로젝트의 이름으로 이 문서에서는 호환 대상을 가리키는 용도로만 사용합니다.

## 이 저장소에 포함되지 않는 것 (별도 설치 필요)
이 저장소는 **Orange3 를 포함하지 않습니다.** Orange 소스 파일을 수정하거나 재배포하지 않습니다.
사용자는 공식 배포본을 직접 설치해야 합니다. 설치 방법은 [README.md](README.md) 를 보세요.

| 구성 요소 | 라이선스 | 출처 |
|---|---|---|
| Orange3 3.40.0, 3.32.0 (검증된 버전) | GPL-3.0+ | https://github.com/biolab/orange3 |
| orange-canvas-core 0.2.7 / 0.1.26 | GPL-3.0+ | https://github.com/biolab/orange-canvas-core |
| orange-widget-base 4.27.0 / 4.16.1 | GPL-3.0+ | https://github.com/biolab/orange-widget-base |
| PyQt6 / PyQt5 (Orange 번들) | GPL-3.0 / 상용 | https://www.riverbankcomputing.com/software/pyqt/ |

위 구성 요소의 저작권은 각 저작권자에게 있으며, 각자의 라이선스를 따릅니다.

## 배포 exe(`mcp_orange.exe`)에 포함된 구성요소
`mcp` Python SDK(MIT)와 그 의존 라이브러리, Python 인터프리터(PSF), Tcl/Tk 등이 exe 안에 들어 있습니다.
목록과 라이선스는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 에 있습니다.

## 소스 제공 (GPL)
`mcp_orange.exe` 의 대응 소스는 이 저장소의 같은 버전 태그입니다. 직접 빌드하려면 `build\build_exe.ps1` 을 쓰세요.

## 테스트용 Orange 설치본을 수정하지 않는 방식
호환성 검사와 테스트는 후보 Orange 폴더를 **읽기만** 합니다. 바이트코드를 쓰지 않도록 `python -s -B` 로 실행하고,
포터블 Orange 가 설치 폴더 안에 저장하는 설정(`Orange\config`)은 환경변수 `MCP_ORANGE_SETTINGS_DIR` 로 임시 폴더로 돌립니다
(브리지가 Orange 의 경로 조회 함수를 바꿔 끼우며 Orange 소스는 수정하지 않음). `tests\matrix.py --verify-readonly` 가
실행 전후 폴더 스냅샷을 비교해 변경이 없음을 확인합니다.
