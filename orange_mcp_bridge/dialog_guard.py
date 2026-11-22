"""Auto-dismiss Orange's error dialogs and keep a record of what they said.

A modal "Unexpected Error" box blocks the GUI for whoever drives Orange; the
bridge closes it (never sending the report), stores the details so the AI can
read what went wrong, and lets work continue. Runs on the GUI thread.
"""
import collections
import re
import time

from AnyQt.QtCore import QTimer
from AnyQt.QtWidgets import (
    QAbstractButton, QApplication, QDialog, QLabel, QMessageBox,
    QPlainTextEdit, QTextEdit,
)

POLL_MS = 250
_errors = collections.deque(maxlen=100)
_state = {"enabled": True, "dismissed_total": 0, "read_upto": 0,
          "timer": None, "scan_all_message_boxes": False}
# Never answer with anything that would submit data.
_SAFE_BUTTONS = ("don't send", "dont send", "cancel", "close", "no", "ok",
                 "discard", "ignore")


def _clean(t):
    return (t or "").replace("&", "").strip().rstrip(":").strip().lower()


def _is_error_dialog(d):
    title = (d.windowTitle() or "").lower()
    if "unexpected error" in title or "error" in title.split(" - ")[0]:
        return True
    if type(d).__name__ in ("ErrorReporting", "ErrorReportingDialog"):
        return True
    if isinstance(d, QMessageBox):
        if d.icon() == QMessageBox.Icon.Critical:
            return True
        return _state["scan_all_message_boxes"]
    return False


def _details(d):
    texts = [" ".join(l.text().split()) for l in d.findChildren(QLabel)
             if l.text() and l.isVisibleTo(d)]
    body = []
    for e in d.findChildren(QTextEdit) + d.findChildren(QPlainTextEdit):
        body.append(e.toPlainText())
    if isinstance(d, QMessageBox):
        texts = [d.text(), d.informativeText()] + texts
        if d.detailedText():
            body.append(d.detailedText())
    body_txt = "\n".join(b for b in body if b)
    widget = None
    m = re.search(r"Widget Name:\s*(.+)", body_txt)
    if m:
        widget = m.group(1).strip()
    exc = None
    m = re.search(r"Exception:\s*(.+)", body_txt)
    if m:
        exc = m.group(1).strip()
    tb = None
    i = body_txt.find("Traceback")
    if i >= 0:
        tb = body_txt[i:i + 4000]
    return {"title": d.windowTitle(),
            "text": [t for t in texts if t][:4],
            "widget": widget, "exception": exc, "traceback": tb,
            "raw": None if tb or exc else body_txt[:1500] or None}


def _dismiss(d):
    btns = [b for b in d.findChildren(QAbstractButton) if b.isVisibleTo(d)]
    labels = [_clean(b.text()) for b in btns]
    for pref in _SAFE_BUTTONS:
        if pref in labels:
            btns[labels.index(pref)].click()
            return "clicked %r" % pref
    d.reject() if isinstance(d, QDialog) else d.close()
    return "closed"


def _tick():
    if not _state["enabled"]:
        return
    from orangecanvas.application.canvasmain import CanvasMainWindow
    for w in QApplication.topLevelWidgets():
        if (isinstance(w, QDialog) and w.isVisible()
                and not isinstance(w, CanvasMainWindow)
                and _is_error_dialog(w)):
            info = _details(w)
            info["time"] = time.strftime("%H:%M:%S")
            info["action"] = _dismiss(w)
            _errors.append(info)
            _state["dismissed_total"] += 1


def install():
    if _state["timer"] is not None:
        return
    t = QTimer()
    t.setInterval(POLL_MS)
    t.timeout.connect(_tick)
    t.start()
    _state["timer"] = t  # keep alive


# --- commands -------------------------------------------------------------
def get_errors(clear=False, limit=10):
    """Error dialogs that were auto-dismissed (newest last)."""
    items = list(_errors)[-limit:]
    new = _state["dismissed_total"] - _state["read_upto"]
    _state["read_upto"] = _state["dismissed_total"]
    res = {"auto_dismiss": _state["enabled"], "total": _state["dismissed_total"],
           "new_since_last_read": new, "errors": items}
    if clear:
        _errors.clear()
    return res


def set_auto_dismiss(enabled=True, all_message_boxes=False):
    """enabled: close Orange error dialogs automatically (never sending
    reports). all_message_boxes: also auto-close ordinary message boxes."""
    _state["enabled"] = bool(enabled)
    _state["scan_all_message_boxes"] = bool(all_message_boxes)
    return {"auto_dismiss": _state["enabled"],
            "all_message_boxes": _state["scan_all_message_boxes"]}


def pending_error_count():
    return _state["dismissed_total"] - _state["read_upto"]


COMMANDS = {f.__name__: f for f in (get_errors, set_auto_dismiss)}
