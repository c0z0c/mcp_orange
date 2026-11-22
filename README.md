# mcp_orange

AI(MCP 클라이언트)가 **Orange 3** 캔버스를 직접 조작해 워크플로를 구성·실행하는 MCP 브리지

- 사용자는 캔버스에서 AI 작업을 실시간 확인
- **Orange 소스 무수정** (외부 프로세스 + 브리지 주입 방식)

> **비공식 프로젝트**: Orange Data Mining / University of Ljubljana 와 무관
> - Orange3 미포함 (별도 설치 필요) — 상세: [NOTICE.md](NOTICE.md)
> - 라이선스: **GPL-3.0-or-later** ([LICENSE](LICENSE)), 무보증

```
AI 클라이언트 --stdio--> mcp_orange.exe --mcp-server --127.0.0.1+토큰--> orange_mcp_bridge (Orange 내부)
```

## 빠른 시작 (Windows)

1. **Orange 3 설치**: [지원 버전](#지원-버전과-orange-다운로드)의 공식 링크 사용
2. **mcp_orange.exe 다운로드**: [Releases](https://github.com/c0z0c/mcp_orange/releases)
3. **exe 더블클릭** → 설정 마법사 실행
   - Orange 자동 탐색 + 호환성 검사 (수 초)
   - 호환 Orange 선택 → **이 Orange 사용**
   - AI 클라이언트(Claude, Claude Desktop, Codex/ChatGPT, Antigravity) 선택 → **등록**
4. AI 에 요청 (예: "iris 로 k-Means 돌려줘") — `launch_orange` 로 Orange 자동 기동

> **미서명 exe**: 최초 실행 시 SmartScreen/Defender 검사로 수 초~수십 초 지연 가능
> - "추가 정보 → 실행" 선택
> - 신뢰가 어려우면 소스 직접 빌드 ([개발](#개발))

## 명령줄

단일 exe, 인자별 동작

| 실행 | 동작 |
|---|---|
| `mcp_orange.exe` | 설정 마법사 (GUI) |
| `mcp_orange.exe --mcp-server` | AI 클라이언트용 stdio MCP 서버 (별칭 `-mcp_server`, 출력 없음) |
| `mcp_orange.exe --check` | Orange 탐색 + 호환성 검사 (`--python` `--no-scan` `--json`) |
| `mcp_orange.exe --check --deep` | 검사 + 창 없이 실기동 시나리오 실행 (20~60초) |
| `mcp_orange.exe --register` | 호환 확인 후 클라이언트 등록 (`--client` `--dry-run` `--force`) |
| `mcp_orange.exe --unregister` / `--status` | 등록 해지 / 현황 조회 |
| `mcp_orange.exe --version` | 버전 출력 |
| `mcp_orange.exe --update` | 최신 릴리스 확인 → 확인 후 업그레이드 (`--yes` 로 확인 생략) |

수동 등록 시 설정:
```json
{ "mcpServers": { "orange3": { "command": "C:\\경로\\mcp_orange.exe", "args": ["--mcp-server"] } } }
```
- 지원 클라이언트: `claude`, `claude-desktop`, `codex`(ChatGPT 데스크톱 공유), `antigravity`
- 등록 이름 기본값: `orange3` (`--name` 으로 변경)

## 지원 버전과 Orange 다운로드

`tests\matrix.py` 전체 회귀를 **통과한 조합**
- Orange 내부 API 의존 → 목록 외 버전은 **미검증** (동작 비보증)

| Orange3 | canvas-core / widget-base | Python / Qt | 공식 다운로드 |
|---|---|---|---|
| **3.40.0** | 0.2.7 / 4.27.0 | 3.12 / PyQt6 6.8 | [설치 파일 (x86_64)](https://download.biolab.si/download/files/Orange3-3.40.0-x86_64.exe) · [소스 zip](https://download.biolab.si/download/files/Orange3-3.40.0.zip) · [릴리스](https://github.com/biolab/orange3/releases/tag/3.40.0) |
| **3.32.0** | 0.1.26 / 4.16.1 | 3.8 / PyQt5 5.12 | [설치 파일 (Miniconda)](https://download.biolab.si/download/files/Orange3-3.32.0-Miniconda-x86_64.exe) · [소스 zip](https://download.biolab.si/download/files/Orange3-3.32.0.zip) · [릴리스](https://github.com/biolab/orange3/releases/tag/3.32.0) |

- 최신판: <https://orangedatamining.com/download/> (목록 초과 버전은 미검증)
- 신규 버전 점검 절차: [Orange_업그레이드시_mcp_수정포인트.md](Orange_업그레이드시_mcp_수정포인트.md)

### Orange 탐색 순서
1. `ORANGE_PYTHON` 환경변수
2. 마법사에서 저장한 선택
3. exe 옆 `Orange\python.exe`
4. 드라이브 루트·사용자 폴더·Program Files 하위 (이름에 `orange` 포함, 깊이 2)
5. conda 환경

- 미발견 시 마법사 **찾아보기...** 로 `python.exe` 직접 지정
- 탐색·검사는 Orange 폴더 **읽기 전용**

### 호환성 판정
| 표시 | 의미 |
|---|---|
| 호환 (검증됨) | 검증 조합과 일치 + 필수 내부 항목 충족 |
| 미검증 | 목록 외 버전, 필수 심볼은 존재 (사용 전 확인 질문) |
| 비호환 | 필수 항목 누락 또는 Orange 아님 → 등록·기동 거부 (`--force` 로만 우회) |
| 검사 실패 | python 실행 불가 등 |

## 업그레이드
- **자동 확인**: 설정 마법사 시작 시 [GitHub Releases](https://github.com/c0z0c/mcp_orange/releases) 최신 버전을 백그라운드 조회
  - 새 버전이 있으면 **사용자 확인 후** 교체·재시작 (거부 시 아무 변화 없음)
  - 오프라인·조회 실패는 조용히 무시
- **수동**: `mcp_orange.exe --update` (`--yes` 로 확인 생략)
- **안전장치**
  - 다운로드 주소는 이 저장소의 릴리스만 허용, HTTPS 필수
  - 크기·실행 파일 형식 확인 후에만 교체, 실패 시 기존 exe 유지
  - 실행 중인 exe 는 이름 변경 방식으로 교체 → 이전 파일(`mcp_orange_del.tmp`)은 다음 실행 시 삭제
  - 업그레이드를 승인하면 **이전 exe 로 실행 중인 서버(AI 클라이언트가 띄운 `--mcp-server`)를 강제 종료**해 파일 잠금을 푼다 (확인창에 안내). 클라이언트가 다음 호출 때 새 버전으로 다시 시작하며 Orange 는 종료되지 않는다. 그래도 남은 파일은 실행 중인 서버가 30초마다 다시 지운다
- **제외**: `--mcp-server` 모드는 확인하지 않음 (stdout 이 MCP 프로토콜, 사용자 질의 불가)
- **끄기**: 환경변수 `MCP_ORANGE_NO_UPDATE_CHECK=1`
- 쓰기 권한이 없는 폴더(예: Program Files)에 둔 exe 는 교체 실패 → 안내 후 기존 exe 유지

## 동작 특성
- **설정 변경**: 위젯의 실제 Qt 컨트롤 경유 → Orange 콜백·재계산 정상 수행
  - 잘못된 값(숫자칸 문자, 범위 초과)은 사전 거부
- **오류 창**: "Unexpected Error" 는 *Don't Send* 로 자동 종료, 내용은 `get_errors` 로 조회
  - **오류 리포트 외부 전송 없음**, `set_auto_dismiss(false)` 로 해제 가능
- **개인정보**: `recent_*` 설정(파일 이력)은 노출 차단
- **세션 종료**: AI 세션이 끝나도 Orange 유지 (미저장 작업 보호). Orange 는 relay 가 닫지 않는다
- **relay 수명 (Orange 에 종속)**: 클라이언트가 내리지 않아 방치된 `mcp_orange.exe --mcp-server` 가 쌓이지 않도록 스스로 종료
  - 제어하는 Orange 가 **살아 있는 동안은 요청이 없어도 종료하지 않음** (사용자가 그 Orange 에서 직접 작업 중일 수 있음)
  - 그 Orange 가 종료되면 유예(기본 120초) 후 종료. 유예 안에 요청이 오면 계속 실행 (Orange 를 닫고 "다시 켜줘" 하는 경우)
  - Orange 를 한 번도 제어하지 않은 relay(`launch_orange` 없이 방치)는 10분 무요청 시 종료
  - relay 를 띄운 클라이언트 프로세스가 사라진 경우(고아)는 Orange 가 살아 있어도 유예 후 정리 (Orange 에는 영향 없음)
  - 종료돼도 클라이언트가 다음 호출 때 다시 띄우는 것이 전제. `initialize` 응답의 instructions 로 AI 에게 알림
  - 환경변수: `MCP_ORANGE_IDLE_MINUTES`(기본 10, 0=끔), `MCP_ORANGE_EXIT_GRACE_SECONDS`(기본 120, 0=즉시),
    `MCP_ORANGE_NO_ORANGE_WATCH=1`, `MCP_ORANGE_NO_PARENT_WATCH=1`, `MCP_ORANGE_CLIENT_PID`(감시할 클라이언트 PID 직접 지정)
- **로컬 보안**: `127.0.0.1` 임의 포트 + 임의 토큰
  - 토큰 파일 `%LOCALAPPDATA%\mcp_orange\bridge.json` 은 동일 계정 프로세스가 읽기 가능 → 계정 내부는 신뢰 경계 없음
- **데이터 폴더**: `%LOCALAPPDATA%\mcp_orange\`
  - `config.json`(선택 Orange·검사 결과), `bridge\`(브리지 사본), `logs\`
- **포터블 Orange 설정**: 위젯 기본값을 설치 폴더(`Orange\config`)에 저장
  - `--deep` 및 테스트는 임시 폴더로 격리 → 설치본 무변경
  - 일반 사용 시에는 Orange 기본 동작 유지

## 개발

개발용 venv 필요 (`mcp>=1.28,<2`)
```
python -m venv .venv
.venv\Scripts\pip install -r relay\requirements.txt
```
- `.venv\Scripts\python.exe app_main.py --check`: 소스 모드 실행 (exe 와 동일 기능)
- `build\build_exe.ps1`: `dist\mcp_orange.exe` 빌드 (PyInstaller, 전용 venv `build\.venv`) + `SHA256SUMS.txt` 생성
- `build\release.ps1 -Message "변경 요약"`: **릴리스 자동화** (`-DryRun` 미리보기) — README 히스토리 추가 → 커밋 → exe 빌드 → 태그 → push → [GitHub Releases](https://github.com/c0z0c/mcp_orange/releases) 업로드
  - 조건: master 브랜치, `gh auth login` 완료
  - 별도 `Release vX` 커밋이 남지 않도록 변경 전체와 README 히스토리를 **커밋 하나**로 묶는다 (이미 커밋만 하고 push 전이면 그 커밋에 합침, 이미 push 된 커밋일 때만 `Release vX` 커밋을 따로 만듦)
- `manage.cmd status|install|uninstall`: 개발 모드 클라이언트 등록
- 테스트
  - `tests\test_app.py`, `test_manage.py`, `test_wizard.py`: Orange 불필요
  - `tests\matrix.py [--orange <python.exe> ...] [--exe dist\mcp_orange.exe] [--verify-readonly]`: **Orange 버전별 전체 회귀**
    - 임시 데이터 폴더 + 설정 격리 + offscreen 기동
    - `--verify-readonly`: 실행 전후 설치 폴더 스냅샷 비교
  - `tests\test_lifecycle.py`: relay 수명 규칙(유휴/Orange 종속/유예/고아) 검증. Orange 불필요, 임시 `MCP_ORANGE_HOME` 사용
  - `tests\test_exe_cleanup.py`: 강제 종료 잔여 `_MEI*` 임시 폴더 정리 검증
  - `tests\run_all.ps1`: 개발용 Orange 대상 기존 회귀 묶음

### 버전
확인 위치
- `mcp_orange.exe --version`
- 설정 마법사 제목줄
- MCP `initialize` 응답의 `serverInfo.version`
- exe **속성 → 자세히** 탭 (파일·제품 버전, 설명, 저작권)

## 참고 문서
- [아키텍처_구조.md](아키텍처_구조.md): LLM · MCP · Orange 연결 구조와 동작
- [Orange_업그레이드시_mcp_수정포인트.md](Orange_업그레이드시_mcp_수정포인트.md): Orange 업그레이드 시 점검 항목

## 버전 히스토리

`build\release.ps1` 이 릴리스 때 자동 추가 (최신순, 변경 내용 = 직전 태그 이후 커밋 제목, 해당 커밋에 함께 포함). 전체 이력: `git log`

| 버전 | 날짜 | 변경 |
|---|---|---|
| 0.6.1.6 | 2026-11-22 | 업그레이드 이슈 수정 |
| 0.5.0.5 | 2026-11-22 | mcp 메모리 관리 최적화: relay 수명을 Orange에 종속(유휴·고아 자동 종료) |
| 0.5.0.4 | 2026-11-22 | 아이콘 추가 |
| 0.5.0.2 | 2026-11-22 | Initial commit: mcp_orange |
