"""등록/해지 창 (tkinter). CLI 와 같은 clients.py 로직을 쓴다."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import clients as C

_MARK = {C.SAME: "● 등록됨", C.STALE: "▲ 경로 다름", C.FOREIGN: "▲ 다른 설정", C.ABSENT: "○ 등록 안 됨"}


class Panel(ttk.Frame):
    """클라이언트 등록/해지 패널. 단독 창(App)이나 설정 마법사 안에 넣을 수 있다.

    gate: 등록(install) 직전에 호출되는 함수. (허용 여부, 사유) 를 돌려주며, 거부되면 --force 가 꺼져 있는 한
    등록하지 않는다 (예: 호환되는 Orange 가 선택되지 않았을 때).
    """

    def __init__(self, master, gate=None) -> None:
        super().__init__(master)
        self.gate = gate
        self.spec = C.default_spec()
        self._log_q: queue.Queue = queue.Queue()
        self._busy = False
        self._rows: dict[str, C.StoreStatus] = {}

        self.dry = tk.BooleanVar(value=False)
        self.force = tk.BooleanVar(value=False)
        self.name_var = tk.StringVar(value=self.spec.name)

        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="등록 이름").pack(side="left")
        ent = ttk.Entry(top, textvariable=self.name_var, width=14)
        ent.pack(side="left", padx=(6, 12))
        ent.bind("<FocusOut>", lambda _e: self.refresh())
        ent.bind("<Return>", lambda _e: self.refresh())
        self.server_lbl = ttk.Label(top, text="", foreground="#555")
        self.server_lbl.pack(side="left", fill="x", expand=True)

        mid = ttk.Frame(self, padding=(12, 4))
        mid.pack(fill="both", expand=True)
        cols = ("state", "current")
        self.tree = ttk.Treeview(mid, columns=cols, show="tree headings", selectmode="extended", height=7)
        self.tree.heading("#0", text="클라이언트")
        self.tree.heading("state", text="상태")
        self.tree.heading("current", text="등록된 실행 명령")
        self.tree.column("#0", width=230, stretch=False)
        self.tree.column("state", width=190, stretch=False)
        self.tree.column("current", width=380)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        bar = ttk.Frame(self, padding=(12, 6))
        bar.pack(fill="x")
        self.buttons = [
            ttk.Button(bar, text="선택 등록", command=lambda: self.act("install", True)),
            ttk.Button(bar, text="선택 해지", command=lambda: self.act("uninstall", True)),
            ttk.Button(bar, text="전체 등록", command=lambda: self.act("install", False)),
            ttk.Button(bar, text="전체 해지", command=lambda: self.act("uninstall", False)),
            ttk.Button(bar, text="새로고침", command=self.refresh),
        ]
        for b in self.buttons:
            b.pack(side="left", padx=(0, 6))
        ttk.Checkbutton(bar, text="미리보기(dry-run)", variable=self.dry).pack(side="left", padx=(14, 6))
        ttk.Checkbutton(bar, text="강제(--force)", variable=self.force).pack(side="left")

        logf = ttk.Frame(self, padding=(12, 0, 12, 12))
        logf.pack(fill="both", expand=True)
        self.log = tk.Text(logf, height=9, wrap="word", state="disabled", font=("Consolas", 9))
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="left", fill="y")

        self.refresh()
        self.after(100, self._pump)

    # ----------------------------------------------------------------- 도우미
    def _spec(self) -> C.ServerSpec:
        self.spec = C.default_spec(self.name_var.get().strip() or "orange3")
        return self.spec

    def say(self, msg: str) -> None:
        self._log_q.put(msg)

    def _pump(self) -> None:
        try:
            while True:
                msg = self._log_q.get_nowait()
                if msg is None:
                    self._set_busy(False)
                    self.refresh()
                    continue
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for b in self.buttons:
            b.configure(state="disabled" if busy else "normal")

    # ------------------------------------------------------------------ 갱신
    def refresh(self) -> None:
        spec = self._spec()
        probs = spec.problems()
        self.server_lbl.configure(
            text=("서버: " + spec.launch().display()) if not probs else "⚠ " + probs[0],
            foreground="#555" if not probs else "#b00020")
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        for st in C.all_status(spec):
            if not st.installed:
                state, cur = "설치되어 있지 않음", ""
            elif st.error:
                state, cur = "오류", st.error
            else:
                state = _MARK[st.state] + (f" (+중복 {len(st.dups)})" if st.dups else "")
                cur = (st.current.display() + (" [파일 없음]" if st.current.dead() else "")) if st.current else ""
            iid = self.tree.insert("", "end", text=st.label, values=(state, cur))
            self._rows[iid] = st

    # ------------------------------------------------------------------ 동작
    def act(self, action: str, selected: bool) -> None:
        if self._busy:
            return
        if selected:
            sel = self.tree.selection()
            if not sel:
                messagebox.showinfo("선택", "표에서 클라이언트를 먼저 선택하세요.", parent=self)
                return
            targets = sorted({self._rows[i].client for i in sel if self._rows[i].installed},
                             key=C.CLIENTS.index)
            if not targets:
                messagebox.showinfo("선택", "선택한 클라이언트가 설치되어 있지 않습니다.", parent=self)
                return
        else:
            targets = None  # 설치된 모든 클라이언트
        spec = self._spec()
        dry, force = self.dry.get(), self.force.get()
        if action == "install" and self.gate is not None and not force:
            ok, why = self.gate()
            if not ok:
                messagebox.showwarning("등록할 수 없음", why, parent=self)
                return
        if action == "uninstall" and not dry:
            names = ", ".join(C.LABELS[t] for t in targets) if targets else "설치된 모든 클라이언트"
            if not messagebox.askyesno("해지 확인", f"'{spec.name}' 등록을 {names} 에서 제거할까요?", parent=self):
                return
        self._set_busy(True)
        self.say("-" * 56)

        def work() -> None:
            try:
                C.run_action(spec, action, targets, force=force, dry_run=dry, say=self.say)
            except Exception as e:  # noqa: BLE001 - 창이 멈추지 않게 모두 로그로
                self.say(f"실패: {type(e).__name__}: {e}")
            finally:
                self._log_q.put(None)

        threading.Thread(target=work, daemon=True).start()


class App(tk.Tk):
    """등록/해지 전용 단독 창 (manage.py gui)."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Orange MCP 등록 관리")
        self.geometry("860x560")
        self.minsize(720, 440)
        Panel(self).pack(fill="both", expand=True)


def main() -> int:
    App().mainloop()
    return 0
