"""설정 마법사 (tkinter): 1) Orange 를 찾아 호환성을 확인하고 고른다  2) AI 클라이언트에 등록한다.

mcp_orange.exe 를 인자 없이 실행(더블클릭)하면 이 창이 뜬다.
"""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from mcp_manage import clients as C
from mcp_manage import gui as manage_gui

from . import version, compat, config, discovery, launcher, paths, update

_COLOR = {compat.VERIFIED: "#0b7a0b", compat.PROBE_OK: "#9a6700", compat.INCOMPATIBLE: "#b00020", compat.ERROR: "#b00020"}


def _hide_own_console() -> None:
    """더블클릭으로 실행돼 콘솔 창이 따로 생긴 경우에만 숨긴다 (터미널에서 실행했다면 그대로 둔다)."""
    if not paths.frozen() or sys.platform != "win32":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        pids = (ctypes.c_uint * 8)()
        n = k.GetConsoleProcessList(pids, 8)
        if 0 < n <= 2:   # onefile 은 부트로더 + 자식, 이 둘뿐이면 우리가 만든 콘솔
            hwnd = k.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:  # noqa: BLE001 - 콘솔 숨김은 부가 기능
        pass


class Wizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Orange MCP 설정 — mcp_orange %s" % version.display())
        self.geometry("980x780")
        self.minsize(820, 640)
        self._set_icon()
        self._q: queue.Queue = queue.Queue()
        self._targets: dict[str, launcher.Target] = {}      # tree iid -> 검사 결과
        self._selected: Optional[launcher.Target] = None
        self._busy = False

        # ---- 1. Orange
        box = ttk.LabelFrame(self, text=" 1. Orange 연결 ", padding=10)
        box.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(
            box, foreground="#555", wraplength=900, justify="left",
            text="컴퓨터에 설치된 Orange 3 를 찾아 이 도구와 호환되는지 검사합니다. "
                 "검사는 Orange 폴더를 읽기만 하며 아무것도 수정하지 않습니다.").pack(anchor="w")
        cols = ("status", "version", "python", "path")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", selectmode="browse", height=5)
        for c, t, w in (("status", "호환성", 190), ("version", "Orange", 70), ("python", "Python", 70), ("path", "위치", 520)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, stretch=(c == "path"))
        self.tree.pack(fill="x", pady=(8, 4))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        for st, col in _COLOR.items():
            self.tree.tag_configure(st, foreground=col)

        bar = ttk.Frame(box)
        bar.pack(fill="x")
        self.btn_scan = ttk.Button(bar, text="다시 검색", command=self.scan)
        self.btn_browse = ttk.Button(bar, text="찾아보기...", command=self.browse)
        self.btn_deep = ttk.Button(bar, text="정밀 검사 (창 없이 실제 실행)", command=self.deep)
        self.btn_use = ttk.Button(bar, text="이 Orange 사용", command=self.use_selected)
        for b in (self.btn_scan, self.btn_browse, self.btn_deep, self.btn_use):
            b.pack(side="left", padx=(0, 6))
        self.sel_lbl = ttk.Label(box, text="", foreground="#555", wraplength=900, justify="left")
        self.sel_lbl.pack(anchor="w", pady=(6, 0))
        self.detail = ttk.Label(box, text="", foreground="#555", wraplength=900, justify="left")
        self.detail.pack(anchor="w")

        # ---- 2. 등록 (기존 등록 패널 재사용)
        reg = ttk.LabelFrame(self, text=" 2. AI 클라이언트에 등록 ", padding=2)
        reg.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.panel = manage_gui.Panel(reg, gate=self._gate)
        self.panel.pack(fill="both", expand=True)

        self._show_saved()
        self.after(100, self._pump)
        self.after(200, self.scan)
        self.after(1500, self._check_update)

    def _set_icon(self) -> None:
        """창 제목줄/작업 표시줄 아이콘. 없거나 실패해도 동작에는 영향 없다."""
        ico = paths.repo_root() / ("mcp_orange.ico" if paths.frozen() else "build/mcp_orange.ico")
        try:
            self.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 상태
    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._busy = busy
        for b in (self.btn_scan, self.btn_browse, self.btn_deep, self.btn_use):
            b.configure(state="disabled" if busy else "normal")
        if text:
            self.detail.configure(text=text)

    def _pump(self) -> None:
        try:
            while True:
                fn = self._q.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _post(self, fn) -> None:
        self._q.put(fn)

    def _show_saved(self) -> None:
        saved = config.load().get("orange_python")
        self._selected = None
        if saved:
            t = launcher.cached_check(saved)
            if t and t.usable:
                self._selected = t
        self._refresh_selected()

    def _refresh_selected(self) -> None:
        if self._selected:
            t = self._selected
            self.sel_lbl.configure(
                text="사용할 Orange: %s  [%s %s]" % (t.python, t.orange_version, compat.LABEL[t.status]),
                foreground=_COLOR[t.status])
        else:
            self.sel_lbl.configure(text="사용할 Orange 가 아직 선택되지 않았습니다. 목록에서 고르고 '이 Orange 사용'을 누르세요.",
                                   foreground="#b00020")
        self.panel.refresh()

    def _gate(self):
        if self._selected is None:
            return False, "먼저 위에서 호환되는 Orange 를 선택하세요. (또는 '강제'를 켜면 건너뜁니다)"
        return True, ""

    # ------------------------------------------------------------ 새 버전
    def _check_update(self) -> None:
        """시작 후 백그라운드로 최신 릴리스를 확인한다. 오프라인 등 실패는 조용히 무시한다."""
        if update.disabled() or not paths.frozen():
            return

        def work() -> None:
            try:
                info = update.check()
            except update.UpdateError:
                return
            if info.newer:
                self._post(lambda: self._ask_update(info))

        threading.Thread(target=work, daemon=True).start()

    def _ask_update(self, info: "update.UpdateInfo") -> None:
        if not messagebox.askyesno(
                "새 버전", "새 버전 %s 이(가) 있습니다. (현재 %s)\n\n지금 업그레이드하고 다시 시작할까요?\n\n"
                "AI 클라이언트가 실행 중인 이전 버전 mcp_orange 서버는 교체 후 종료됩니다 "
                "(클라이언트가 다음 호출 때 새 버전으로 다시 시작합니다. Orange 는 종료되지 않습니다)."
                % (info.version, version.full()), parent=self):
            return
        self._set_busy(True, "새 버전을 받는 중입니다 ...")

        def work() -> None:
            try:
                update.install(info)
            except update.UpdateError as e:
                msg = str(e)
                self._post(lambda: (self._set_busy(False, msg), messagebox.showerror("업그레이드 실패", msg, parent=self)))
                return
            self._post(self._restart)

        threading.Thread(target=work, daemon=True).start()

    def _restart(self) -> None:
        update.relaunch()
        self.destroy()

    # ------------------------------------------------------------ 검색/검사
    def scan(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Orange 를 찾고 호환성을 검사하는 중입니다 ...")
        self.tree.delete(*self.tree.get_children())
        self._targets.clear()

        def work() -> None:
            try:
                cands = discovery.find_orange_pythons()
                with ThreadPoolExecutor(max_workers=min(4, max(1, len(cands)))) as ex:
                    res = list(ex.map(lambda c: launcher.check(c.python, save=True), cands))
                self._post(lambda: self._fill(res))
            except Exception as e:  # noqa: BLE001
                msg = "검색 실패: %s" % e
                self._post(lambda: self._set_busy(False, msg))

        threading.Thread(target=work, daemon=True).start()

    def _fill(self, results: list) -> None:
        # 사용 우선순위(검증됨 > 미검증, 최신 버전 우선) 순으로 보여 준다 — 맨 위가 미리 선택되는 항목
        results = sorted(results, key=lambda t: launcher._rank(t) if t.usable else (-1, ()), reverse=True)
        for t in results:
            self._add_row(t)
        self._set_busy(False, "Orange %d 개를 찾았습니다." % len(results) if results
                       else "Orange 를 찾지 못했습니다. '찾아보기...'로 Orange 의 python.exe 를 직접 지정하세요.")
        # 저장된 선택이 목록에 있으면 그 행을, 없으면 첫 번째 사용 가능한 행을 미리 선택
        saved = config.load().get("orange_python")
        pick = next((i for i, t in self._targets.items() if saved and Path(t.python) == Path(saved)), None) \
            or next((i for i, t in self._targets.items() if t.usable), None)
        if pick:
            self.tree.selection_set(pick)

    def _add_row(self, t: launcher.Target) -> str:
        iid = self.tree.insert("", "end", values=(compat.LABEL.get(t.status, t.status), t.orange_version or "?",
                                                  t.py_version or "?", t.python), tags=(t.status,))
        self._targets[iid] = t
        return iid

    def browse(self) -> None:
        f = filedialog.askopenfilename(parent=self, title="Orange 의 python.exe 선택",
                                       filetypes=[("python.exe", "python.exe"), ("모든 파일", "*.*")])
        if not f or self._busy:
            return
        self._set_busy(True, "검사 중 ...")

        def work() -> None:
            t = launcher.check(f, save=True)
            self._post(lambda: (self._add_row(t), self._set_busy(False, "%s: %s" % (compat.LABEL[t.status], t.summary))))

        threading.Thread(target=work, daemon=True).start()

    def _current(self) -> Optional[launcher.Target]:
        sel = self.tree.selection()
        return self._targets.get(sel[0]) if sel else None

    def _on_select(self) -> None:
        t = self._current()
        if not t:
            return
        lines = [t.summary]
        lines += ["  - 실패: %s %s" % (c["name"], c["detail"]) for c in t.checks[:5]]
        self.detail.configure(text="\n".join(lines))

    def deep(self) -> None:
        t = self._current()
        if not t or not t.usable:
            messagebox.showinfo("정밀 검사", "사용 가능한(호환/미검증) Orange 를 목록에서 먼저 선택하세요.", parent=self)
            return
        if self._busy:
            return
        self._set_busy(True, "정밀 검사 중 (창 없이 Orange 를 실제로 띄웁니다. 20~60초) ...")

        def work() -> None:
            from . import smoke
            r = smoke.run(t.python)
            failed = [s for s in r.steps if not s.ok]
            msg = ("정밀 검사 통과 (%d 단계)" % len(r.steps)) if r.ok else \
                  "정밀 검사 실패: " + "; ".join("%s (%s)" % (s.name, s.detail[:80]) for s in failed[:3])
            self._post(lambda: (self._set_busy(False, msg), messagebox.showinfo("정밀 검사", msg, parent=self)))

        threading.Thread(target=work, daemon=True).start()

    def use_selected(self) -> None:
        t = self._current()
        if t is None:
            messagebox.showinfo("선택", "목록에서 Orange 를 먼저 고르세요.", parent=self)
            return
        if not t.usable:
            messagebox.showwarning("사용할 수 없음", "%s\n\n%s" % (compat.LABEL[t.status], t.summary), parent=self)
            return
        if t.status == compat.PROBE_OK and not messagebox.askyesno(
                "미검증 버전", "%s\n\n그래도 이 Orange 를 사용할까요?" % t.summary, parent=self):
            return
        config.update(orange_python=t.python)
        self._selected = t
        self._refresh_selected()


def main() -> int:
    from . import housekeeping
    housekeeping.cleanup_in_background()
    _hide_own_console()
    Wizard().mainloop()
    return 0
