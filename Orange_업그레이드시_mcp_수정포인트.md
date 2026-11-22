# Orange 업그레이드 시 mcp_orange 수정 포인트

mcp_orange는 **Orange 소스를 한 줄도 수정하지 않고**, Orange 내부 객체(`OMain`, 캔버스 윈도우,
시그널 매니저, 위젯 컨트롤 등)를 직접 호출하는 방식으로 동작한다.
그래서 Orange(또는 의존 라이브러리)가 올라가면 **내부 심볼 이름/동작이 바뀌어 깨질 수 있는 지점**이 정해져 있다.
이 문서는 그 지점을 위험도 순으로 기록한 체크리스트다.

---

## 0. 현재 기준선 (end-to-end 로 검증된 환경)

`tests\matrix.py` (전체 회귀: 릴레이 경유 launch_orange, 시나리오, 설정 주입, 선택, 문서, 오류창)를 통과한 조합만
`mcp_orange_app/compat.py` 의 `VERIFIED_COMBOS` 에 올라 있고, 설정 마법사/`--check` 에서 "호환 (검증됨)"으로 표시된다.

| 항목 | 3.40.0 (포터블) | 3.32.0 (포터블) |
|---|---|---|
| Orange3 | **3.40.0** | **3.32.0** |
| orange-canvas-core (`orangecanvas`) | 0.2.7 | 0.1.26 |
| orange-widget-base (`orangewidget`) | 4.27.0 | 4.16.1 |
| AnyQt / 실제 Qt 바인딩 | 0.2.1 / PyQt6 6.8.1 | 0.1.0 / PyQt5 5.12.3 |
| Orange 내장 Python | 3.12.10 | 3.8.8 |
| numpy | 1.26.4 | 1.24.4 |

| 릴레이/exe 쪽 | 버전 |
|---|---|
| 릴레이 Python (exe 빌드 / 개발 venv) | 3.14.6, `mcp` 1.30.0 (`requirements.txt`: `mcp>=1.28,<2`), PyInstaller 6.22.3 |

> 업그레이드 후 표를 새 버전으로 갱신할 것.
> 확인 명령: `mcp_orange.exe --check` (또는 `--check --json`). Orange 쪽 직접 확인은
> `<Orange>\python.exe -c "import Orange;print(Orange.__version__)"` 및 `-m pip list`.

---

## 1. 업그레이드 후 표준 절차

1. 새 Orange를 설치(또는 `ORANGE_PYTHON` 환경변수가 가리키는 곳, 또는 설정 마법사에서 선택).
2. `mcp_orange.exe --check` — 필수 내부 심볼 프로브. 실패 항목 이름이 아래 §2 의 수정 위치와 대응된다.
   통과하면 "미검증(필수 심볼은 있음)"으로 표시되며, **이 상태는 동작 보장이 아니다.**
3. `mcp_orange.exe --check --python <새 python.exe> --deep` — 창 없이(offscreen) 실제로 띄워 시나리오 22단계 실행.
4. `.venv\Scripts\python.exe tests\matrix.py --orange <새 python.exe> --verify-readonly` — 전체 회귀.
   `--verify-readonly` 는 설치 폴더가 실행 전후로 같은지 확인한다. 배포 exe 로 확인하려면 `--exe dist\mcp_orange.exe` 추가.
   FAIL 이 있으면 아래 표에서 해당 위치를 수정.
5. `tests\sweep_widgets.py` 로 설치된 **모든 위젯**을 추가/조사/삭제 → `tests\_out\sweep_result.json` 을 이전 결과와 비교.
6. `tests\show_tools.py` 로 AI 클라이언트에 보이는 도구 목록이 그대로인지 확인.
7. 전부 통과하면 `compat.py` 의 `VERIFIED_COMBOS` 에 `"<Orange3>": ("<canvas-core>", "<widget-base>")` 를 추가하고,
   이 문서 0번 표와 아래 "변경 이력"을 갱신한 뒤 exe 를 다시 빌드(`build\build_exe.ps1`).

> Qt 5 기반(3.32 등)에서 대화상자 테스트(`test_dialog`, `test_autodismiss`)는 offscreen 으로 돌리면 Orange 가 죽는다
> (Qt 5.12 의 `QMessageBox` 문제, 브리지와 무관). `matrix.py` 가 Qt5 에서는 이 두 테스트만 창 모드로 자동 전환한다.

---

## 2. 수정 포인트 (파일별, 위험도 순)

위험도: 🔴 높음(내부 비공개 API/이름 규칙) · 🟡 중간(공개 API지만 시그니처/동작 변경 가능) · 🟢 낮음

### 🔴 2.1 시그널 매니저 비공개 속성 — `widget_ops.py` `get_output`

```python
sm._SignalManager__node_outputs.get(n, {})   # name-mangled private
state.outputs.values()                        # _OutputState.outputs
```
* `get_output` 이 노드의 마지막 출력값을 읽는 **유일한 방법**이 비공개 속성이다.
* 현재 위치: `orangecanvas/scheme/signalmanager.py` (`self.__node_outputs`, `_OutputState`).
* 깨지는 증상: `AttributeError: ... _SignalManager__node_outputs` 또는 항상 `no output (yet)`.
* 대응: 새 버전의 `SignalManager` 에서 노드별 출력 저장소 이름/구조를 다시 찾아 수정.
  공개 API(예: `signals_on_link`, `output_value` 류)가 생겼으면 그쪽으로 교체하는 것이 가장 좋다.
* 관련 테스트: `scenario_iris`, `test_relay`

### 🔴 2.2 컨트롤 ↔ 설정 매핑 — `widget_ops.py` `_controlled`, `inspect_widget`, `set_setting`

```python
obj.controlled_attributes          # orangewidget/gui.py : defaultdict(list)
cf[0].control                      # 콜백 객체(ControlledCallFront 류)의 .control
w.settingsHandler.known_settings   # orangewidget/settings.py
```
* 설정을 "진짜 Qt 컨트롤"로 바꾸기 위해 `controlled_attributes[name][0].control` 구조에 의존한다.
  이 구조가 바뀌면 모든 설정이 `setattr (no GUI control; callbacks NOT triggered)` 로 떨어져
  **GUI는 바뀌지만 재계산이 안 되는** 조용한 오류가 난다 (가장 위험한 실패 모드).
* `known_settings` 키 규칙: 서브컴포넌트는 `graph.alpha_value` 처럼 점(`.`)으로 구분 (`_resolve` 가 처리).
* 대응: `orangewidget/gui.py` 의 `ControlledAttributesDict` / `connectControl` 과
  `settings.py` 의 `SettingsHandler.known_settings` 를 확인.
* 관련 테스트: `test_controls`

### 🔴 2.3 Qt 컨트롤별 값 주입 로직 — `widget_ops.py` `_set_via_control`

Orange 가 각 컨트롤의 **어떤 시그널**을 듣는지에 맞춰 시그널을 수동 발생시킨다.
* `QComboBox` → `ctl.activated.emit(idx)` (Orange 가 `activated` 를 구독)
* `QSpinBox/QDoubleSpinBox` → `setValue` 후 값이 안 바뀌었으면 `editingFinished.emit()`
* `QLineEdit` → `setText` + `editingFinished` + `returnPressed`
  (숫자형 설정이면 `int()/float()` 변환을 **미리** 검사 — Orange 쪽 슬롯이 예외를 막지 않기 때문)
* 라디오 → `ctl.buttons`(`gui.radioButtons` 가 만드는 `buttons` 속성)의 `.click()`
* 리스트 → `selectionModel().select(...)`
* 대응: 위젯 콜백이 다른 시그널(`currentIndexChanged`, `textChanged` 등)로 바뀌면 여기서 같이 발생시키도록 수정.
  새 컨트롤 종류(예: 새 Qt 위젯 클래스)가 쓰이면 `_describe_control` 과 함께 분기 추가.
* 관련 테스트: `test_controls`

### 🔴 2.4 캔버스 윈도우 API — `commands.py`, `widget_ops.py`

| 호출 | 위치 | 용도 |
|---|---|---|
| `orangecanvas.application.canvasmain.CanvasMainWindow` | `_window`, `dialog_guard`, `_open_dialogs` | 캔버스 창 식별 |
| `win.current_document()` → `.scheme()`, `.path()`, `.setPath()`, `.setModified()` | 전반 | 현재 워크플로 |
| `win.load_scheme(filename)` | `open_workflow` | .ows 열기 |
| `win.save_scheme_to(scheme, filename)` | `save_workflow` | .ows 저장 |
| `scheme.new_node / remove_node / new_link / remove_link / clear` | `commands.py` | 그래프 편집 |
| `scheme.widget_for_node(node)` | 전반 | 노드 → 위젯 인스턴스 (`orangewidget/workflow/widgetsscheme.py`) |
| `scheme.signal_manager`, `sm.is_pending(node)` | `_state` | 계산 중 판정 |
| `orangecanvas.scheme.link.possible_links` | `add_link` | 채널 자동 선택 |
| `orangecanvas.registry.global_registry()` → `.widgets()`, `.widget(name)` | `list_widgets`, `add_node`, `widget_docs` | 위젯 카탈로그 |
| 위젯 `desc.qualified_name / name / category / inputs / outputs / keywords / help` | 전반 | 디스크립션 필드 |
| `SchemeNode.Running`, `SchemeNode.Pending`, `node.test_state_flags()` | `_state` | busy 판정 |
| `w.isBlocking()` | `_state` | busy 판정 |
| 위젯 메시지 그룹 `w.Error / Warning / Information` 의 `.active` | `_messages` | 오류/경고 텍스트 |

* 가장 큰 변경 가능성: `orange-canvas-core` 가 올라갈 때 `CanvasMainWindow` 의 메서드명/시그니처.
* 대응: `orangecanvas/application/canvasmain.py` 에서 `load_scheme`, `save_scheme_to`, `current_document` 를 재확인.
* 관련 테스트: `scenario_iris`, `smoke_graph`

### 🟡 2.5 시작 훅 — `orange_mcp_bridge/__main__.py`

```python
from Orange.canvas.__main__ import OMain
class McpOMain(OMain):
    def argument_parser(self)           # --welcome 옵션 추가
    def show_welcome_screen(self, mw)   # 기본 숨김
    def create_main_window(self)        # 윈도우 생성 직후 브리지 시작
McpOMain().run(argv)
```
* 프로브 항목: `OMain.argument_parser / create_main_window / show_welcome_screen / run`
* 의존 대상: `Orange/canvas/__main__.py` 의 `OMain`, 그 부모 `orangecanvas/main.py` 의 `Main`
  (`argument_parser`, `create_main_window`, `show_welcome_screen`, `run`).
* 깨지는 증상: Orange 는 뜨는데 `bridge.json` 이 안 생김, 또는 시작 시 `ImportError`/`TypeError`.
  (브리지 시작 실패는 `log.exception` 만 남기고 Orange 는 계속 뜸 — **`orange.err.log` 를 확인**)
* 대응: `OMain.run(argv)` 의 인자 형태 변화(현재 `run(self, argv)`), 훅 이름 변화 확인.
  `Main.run` 이 `create_main_window` 를 부르는 순서가 바뀌면 `start_bridge()` 위치 조정.
* 관련 테스트: `test_cold_launch`

### 🟡 2.6 에러 다이얼로그 자동 처리 — `dialog_guard.py`

```python
type(d).__name__ in ("ErrorReporting", "ErrorReportingDialog")   # 클래스명 비교
제목에 "unexpected error" / "error" 포함, QMessageBox Critical 아이콘
본문 정규식:  "Widget Name:\s*(.+)",  "Exception:\s*(.+)",  "Traceback"
버튼 라벨:    "don't send", "dont send", "cancel", "close", "no", "ok", "discard", "ignore"
```
* 현재 다이얼로그: `orangewidget/workflow/errorreporting.py` 의 `ErrorReporting`.
* **보안상 가장 중요**: 이 다이얼로그에서 **절대 "Send Report" 류 버튼을 누르면 안 된다.**
  버튼 문구/배치가 바뀌면 `_SAFE_BUTTONS` 매칭이 빗나가 `d.reject()` / `d.close()` 로 빠지는지 확인.
  새 버전에서 "Send" 가 안전 목록의 어떤 단어와도 겹치지 않는지 재검토.
* 상세 정보 정규식은 리포트 본문 포맷에 의존 → 포맷이 바뀌면 `widget/exception/traceback` 이 `None` 이 되고
  `raw` 에 원문이 들어간다 (기능은 유지, 정보만 거칠어짐).
* 관련 테스트: `test_autodismiss`, `test_dialog`

### 🟡 2.7 위젯 문서/소스 조회 — `widget_docs.py`

* 오프라인 도움말 경로: `sys.prefix\help\...\widgets\*.html` (HTML `<h1>` 를 위젯명과 정규화 비교).
  Orange 의 도움말 번들 위치/구조가 바뀌면 `_build_help_index` 의 `root` 와 `"widgets"` 경로 필터 수정.
  (현재 `Orange\help\` 아래에 애드온 문서만 있고 **코어 문서는 온라인 전용** → `note` 필드로 안내함)
* 위젯 클래스 해석: `desc.qualified_name` 을 `rpartition(".")` 해서 `importlib` 로 import.
* 관련 테스트: `test_docs`

### 🟡 2.8 선택(Select) 기능 — `widget_ops.py` `select_data`

```python
w.graph.select_by_indices(np.ndarray)      # Orange/widgets/visualize/owscatterplotgraph.py
w.graph.select_by_rectangle(QRectF)
w.graph.unselect_all()
w.selection                                 # (행 인덱스, 그룹) 쌍
```
* 산점도 계열 `OWScatterPlotBase` 의 메서드명에 의존. 이름이 바뀌면 plot 경로가 `table view` 폴백으로 빠져
  "no selectable plot or table" 오류가 날 수 있다.
* 표(table) 계열은 `QAbstractItemView` 를 휴리스틱으로 찾음 (가장 행이 많은 뷰 선택).
* 관련 테스트: `test_select`

### 🟡 2.9 File 위젯 도우미 — `widget_ops.py` `load_file`

```python
w.add_path(path)      # orangewidget/utils/filedialogs.py : RecentPathsWComboMixin.add_path
w.source = w.LOCAL_FILE
w.load_data()         # Orange/widgets/data/owfile.py : OWFile.load_data
```
* 번들 데이터셋 폴더: `Orange\datasets\` (`.tab/.csv/.xlsx`).
* `OWFile` 의 `source`/`LOCAL_FILE`/`load_data`/`add_path` 가 바뀌면 수정.
* 관련 테스트: `scenario_iris`

### 🟢 2.10 `recent_*` 설정 숨김 — `widget_ops.py` `inspect_widget`

* 이름이 `recent` 로 시작하는 리스트 설정은 **개인 경로 노출 방지**를 위해 건수만 표시. 새 위젯이
  다른 이름(예: `history_*`, `last_*`)으로 파일 이력을 저장하면 노출될 수 있으므로 `sweep_widgets` 결과에서 점검.
* `_INTERNAL_SETTINGS` = `controlAreaVisible, savedWidgetGeometry, __version__, splitter_state`
  새 내부 설정이 생기면 여기에 추가 (소음 제거 목적).

### 🟢 2.11 스크린샷 — `commands.py` `screenshot`

* `QWidget.grab()` + `QPixmap.save(path, "PNG")`. Qt 바인딩이 바뀌어도(PyQt5↔6) AnyQt 가 흡수.
  단, 열거형은 Qt6 스타일(`QMessageBox.Icon.Critical`, `QItemSelectionModel.SelectionFlag.Select`,
  `QAbstractItemView.SelectionMode.NoSelection`)로 작성되어 있음 → **Qt5 로 되돌아가면** 일부는 AnyQt 가 처리하지만 확인 필요.

---

## 3. Orange 외부 의존 (Orange 업그레이드와 함께 점검)

### 3.1 Python 버전 / 실행 방식
* 브리지는 **Orange 내장 Python(3.8 ~ 3.12 에서 검증)** 에서 실행, **표준 라이브러리 + Qt(AnyQt)만** 사용.
  그래서 브리지 소스는 **Python 3.8 문법**을 지켜야 한다(`tests\test_app.py` 가 `ast.parse(feature_version=(3, 8))` 로 검사,
  프로브도 후보 Python 으로 직접 컴파일해 본다).
* 실행은 `<Orange python> -s -B -m orange_mcp_bridge`, **cwd 와 `PYTHONPATH` 는 배포 폴더**
  (`%LOCALAPPDATA%\mcp_orange\bridge\<해시>\`, 브리지 패키지만 들어 있음). `-P` 는 3.11+ 전용이라 쓰지 않는다 —
  배포 폴더가 깨끗해서 `-m` 이 cwd 를 sys.path 에 넣어도 오염이 없다. `-B` 는 후보 Orange 폴더에 바이트코드를 쓰지 않기 위해서.

### 3.2 Orange 설치 경로 가정 (경로가 바뀌면 수정)
| 위치 | 하드코딩된 값 |
|---|---|
| `mcp_orange_app\discovery.py` | 탐색 순서: `ORANGE_PYTHON` → config.json → exe 옆(`Orange\python.exe`) → 드라이브 루트/사용자 폴더/Program Files 의 이름에 `orange` 가 든 폴더(깊이 2) → conda envs. 설치 방식이 바뀌어 `python.exe` 위치/`Lib\site-packages\Orange` 구조가 달라지면 `is_orange_python` 수정 |
| `mcp_orange_app\launcher.py` | `_spawn_via_wmi` 가 PowerShell `Invoke-CimMethod` 사용 (Windows 전용) |
| `run_orange.ps1` | 개발용: `"$root\..\Orange\python.exe"` (배포 exe 는 쓰지 않음) |

> **클라이언트 등록은 `mcp_orange.exe --register`(또는 마법사)로 갱신한다.** exe 를 옮긴 뒤 새 위치에서 다시
> 등록하면 옛 경로로 남은 항목을 "경로 다름"으로 인식해 새 경로로 교체한다. 개발 모드(소스)에서는 `manage.cmd` 를 쓴다. 이 도구(`mcp_manage/`)는 Orange 내부 API 에 의존하지 않으므로
> Orange 업그레이드 자체로는 수정할 일이 없다. 대신 **AI 클라이언트 쪽 설정 위치/CLI 문법**이 바뀌면
> `mcp_manage/clients.py` 의 경로 함수(`_claude_file`, `_codex_file`, `_agy_file`, `_desktop_layout`)와
> `add()/remove()` 의 CLI 인자를 고친다 (`tests\test_manage.py` 로 검증).

### 3.3 `mcp` 라이브러리 (릴레이, venv)
* `from mcp.server.fastmcp import FastMCP, Image`, `@mcp.tool()`, `mcp.run()` 사용.
  `mcp` 2.x 에서 import 경로가 바뀔 수 있어 `requirements.txt` 를 `>=1.28,<2` 로 고정해 둠.
* 변경 시 `tests\show_tools.py` 로 도구 스키마 확인.

### 3.4 통신 규약
* 브리지: `127.0.0.1` 임의 포트 + 토큰, 디스커버리 파일 `%LOCALAPPDATA%\mcp_orange\bridge.json`
  (`{"port","token","pid"}`). JSON-lines, 명령은 모두 **Qt GUI 스레드**에서 실행(`GuiInvoker`).
* 릴레이와 브리지는 같은 `mcp_orange` 폴더의 코드를 쓰므로 **명령 이름/인자를 바꾸면 양쪽을 같이** 수정:
  `ALL_COMMANDS`(서버) ↔ `relay/mcp_orange.py` 의 `_call("<cmd>")`.
  (예: 도구 `click_button` 은 브리지 명령 `click` 을 호출)

---

## 4. 증상 → 원인 빠른 찾기

| 증상 | 가능한 원인 | 볼 곳 |
|---|---|---|
| `orange_status` 가 계속 `running:false` | 브리지 미기동 (`create_main_window` 훅 변경 등) | `orange.err.log`, §2.5 |
| 설정을 바꿨는데 결과가 안 변함 | `controlled_attributes` 구조 변경 → setattr 폴백 | 응답의 `via` 값, §2.2 |
| 콤보/라디오 값이 안 먹음 | 위젯이 다른 시그널을 구독 | §2.3 |
| `get_output` 이 항상 `no output (yet)` / AttributeError | 시그널 매니저 비공개 속성 변경 | §2.1 |
| `open_workflow`/`save_workflow` 실패 | `CanvasMainWindow` 메서드 변경 | §2.4 |
| 오류 창이 자동으로 안 닫힘 / 정보가 비어 있음 | `ErrorReporting` 클래스/문구 변경 | §2.6 |
| `get_widget_help` 가 `offline_help: null` | 도움말 번들 구조 변경 (코어 문서는 원래 온라인 전용) | §2.7 |
| `select_data` 오류 | 그래프 선택 메서드 이름 변경 | §2.8 |
| `launch_orange` 가 `Orange python not found` | 설치 경로 변경 | §3.2 |
| 도구 목록이 비거나 import 오류 | `mcp` 버전 | §3.3 |

---

## 5. 변경 이력 (업그레이드할 때마다 아래에 추가)

| 날짜 | Orange | canvas-core | widget-base | 수정한 곳 / 메모 |
|---|---|---|---|---|
| 2026-11-21 | 3.40.0 | 0.2.7 | 4.27.0 | 기준선 기록 (최초 작성). 수정 없음. |
| 2026-11-22 | 3.32.0 | 0.1.26 | 4.16.1 | 2번째 검증 대상 추가(Python 3.8, PyQt5 5.12). 코드 수정: `-P` 제거(3.11+ 전용 → `-s -B -m` + 깨끗한 cwd), 브리지 Python 3.8 문법 유지. matrix 전부 통과. Qt5 헤드리스에서 QMessageBox 가 프로세스를 죽이는 문제는 Qt 자체의 제약이라 테스트만 창 모드로 전환. |
