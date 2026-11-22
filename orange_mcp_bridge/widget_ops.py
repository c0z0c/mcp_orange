"""Generic widget inspection / control. Runs on the Qt GUI thread."""
import os

from AnyQt.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QDialog, QDoubleSpinBox, QGroupBox, QLabel, QLineEdit, QMessageBox,
    QPushButton, QRadioButton, QSlider, QSpinBox,
)
from AnyQt.QtCore import QItemSelectionModel

from .commands import _scheme, _node, _id, _window, _node_info

# Persisted by Orange for window state only - noise for an AI.
_INTERNAL_SETTINGS = {"controlAreaVisible", "savedWidgetGeometry",
                      "__version__", "splitter_state"}
MAX_TEXT = 300


# ---------------------------------------------------------------- utilities
def _widget(node_id):
    node = _node(node_id)
    w = _scheme().widget_for_node(node)
    if w is None:
        raise RuntimeError(
            "widget for %s could not be created (its constructor failed, "
            "e.g. a needed add-on, backend or network access is missing). "
            "Check list_dialogs / get_status for an error dialog." % node_id)
    return node, w


def _resolve(w, name):
    """'graph.alpha_value' -> (w.graph, 'alpha_value')."""
    obj = w
    parts = name.split(".")
    for p in parts[:-1]:
        obj = getattr(obj, p)
    return obj, parts[-1]


def _controlled(obj, attr):
    cf = getattr(obj, "controlled_attributes", None)
    return cf.get(attr) if cf is not None else None


def _list_items(ctl, limit=60):
    model = ctl.model()
    if model is None:
        return []
    out = []
    for r in range(min(model.rowCount(), limit)):
        out.append(str(model.data(model.index(r, 0)) or ""))
    return out


def _jsonable(v, depth=0):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if depth < 3:
        if isinstance(v, (list, tuple, set)):
            items = [_jsonable(x, depth + 1) for x in list(v)[:50]]
            return items
        if isinstance(v, dict):
            return {str(k): _jsonable(x, depth + 1)
                    for k, x in list(v.items())[:50]}
    r = repr(v)
    return r if len(r) <= MAX_TEXT else r[:MAX_TEXT] + "..."


def _clean(text):
    return (text or "").replace("&", "").strip().rstrip(":").strip()


def _radio_buttons(ctl):
    btns = getattr(ctl, "buttons", None)
    if btns:
        return [b for b in btns if isinstance(b, QAbstractButton)]
    return None


def _describe_control(ctl):
    if isinstance(ctl, QCheckBox):
        return {"kind": "checkbox", "label": _clean(ctl.text())}
    if isinstance(ctl, (QSpinBox, QDoubleSpinBox)):
        return {"kind": "spin", "min": ctl.minimum(), "max": ctl.maximum()}
    if isinstance(ctl, QSlider):
        return {"kind": "slider", "min": ctl.minimum(), "max": ctl.maximum()}
    if isinstance(ctl, QComboBox):
        return {"kind": "combo",
                "options": [ctl.itemText(i) for i in range(ctl.count())][:60],
                "count": ctl.count()}
    if isinstance(ctl, QLineEdit):
        return {"kind": "text"}
    rb = _radio_buttons(ctl)
    if rb is not None:
        return {"kind": "radio", "options": [_clean(b.text()) for b in rb]}
    if isinstance(ctl, QAbstractItemView):
        return {"kind": "list", "items": _list_items(ctl),
                "count": ctl.model().rowCount() if ctl.model() else 0}
    return {"kind": type(ctl).__name__}


def _messages(w):
    out = {}
    for grp in ("Error", "Warning", "Information"):
        g = getattr(w, grp, None)
        active = [str(m) for m in getattr(g, "active", [])] if g else []
        if active:
            out[grp.lower()] = active
    return out


def _state(node, w):
    sm = _scheme().signal_manager
    busy = False
    reasons = []
    try:
        if w.isBlocking():
            busy = True
            reasons.append("blocking")
    except Exception:
        pass
    try:
        from orangecanvas.scheme.node import SchemeNode
        for flag, name in ((SchemeNode.Running, "running"),
                           (SchemeNode.Pending, "pending")):
            if node.test_state_flags(flag):
                busy = True
                reasons.append(name)
    except Exception:
        pass
    if getattr(sm, "is_pending", None) and sm.is_pending(node):
        busy = True
        reasons.append("signals-queued")
    return {"busy": busy, "reasons": reasons}


# --------------------------------------------------------------- inspection
def inspect_widget(node, buttons=True):
    n, w = _widget(node)
    handler = w.settingsHandler
    controlled = w.controlled_attributes
    settings = []
    for name, setting in handler.known_settings.items():
        if name in _INTERNAL_SETTINGS or name.startswith("_"):
            continue
        try:
            obj, attr = _resolve(w, name)
        except AttributeError:
            obj, attr = w, name
        val = getattr(obj, attr, None)
        if name.startswith("recent") and isinstance(val, (list, tuple)):
            shown = "<%d entries hidden: may contain private paths>" % len(val)
        else:
            shown = _jsonable(val)
        entry = {"name": name, "value": shown,
                 "type": type(val).__name__,
                 "setting": type(setting).__name__}
        cf = _controlled(obj, attr)
        if cf:
            ctl = getattr(cf[0], "control", None)
            if ctl is not None:
                entry["control"] = _describe_control(ctl)
        settings.append(entry)
    info = {
        "node": _node_info(n),
        "class": "%s.%s" % (type(w).__module__, type(w).__name__),
        "settings": settings,
        "messages": _messages(w),
        "state": _state(n, w),
        "inputs": [c.name for c in n.input_channels()],
        "outputs": [c.name for c in n.output_channels()],
    }
    if buttons:
        info["buttons"] = _list_buttons(w)
    return info


def _list_buttons(w, limit=40):
    out = []
    for b in w.findChildren(QAbstractButton):
        if isinstance(b, (QRadioButton, QCheckBox)):
            continue  # reachable as settings
        text = _clean(b.text())
        if not text or not b.isVisibleTo(w):
            continue
        out.append({"text": text, "enabled": b.isEnabled(),
                    "checkable": b.isCheckable(),
                    "checked": b.isChecked() if b.isCheckable() else None})
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ control
def _set_via_control(w, name, ctl, value):
    """Drive the real Qt control so Orange's own callbacks run."""
    if isinstance(ctl, QCheckBox):
        ctl.setChecked(bool(value))
        return "checkbox.setChecked"
    if isinstance(ctl, (QSpinBox, QDoubleSpinBox)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("%s expects a number, got %r" % (name, value))
        if not ctl.minimum() <= value <= ctl.maximum():
            raise ValueError("%s=%r is outside the allowed range %s..%s" % (
                name, value, ctl.minimum(), ctl.maximum()))
        ctl.setValue(value)
        if getattr(w, name, None) != value:
            ctl.editingFinished.emit()
        return "spin.setValue"
    if isinstance(ctl, QSlider):
        ctl.setValue(int(value))
        return "slider.setValue"
    if isinstance(ctl, QComboBox):
        if isinstance(value, str):
            idx = ctl.findText(value)
            if idx < 0:
                idx = next((i for i in range(ctl.count())
                            if _clean(ctl.itemText(i)).lower()
                            == value.lower()), -1)
            if idx < 0:
                raise ValueError("%r not in options %s" % (
                    value, [ctl.itemText(i) for i in range(ctl.count())]))
        else:
            idx = int(value)
        ctl.setCurrentIndex(idx)
        ctl.activated.emit(idx)  # Orange listens to `activated`
        return "combo.setCurrentIndex+activated"
    if isinstance(ctl, QLineEdit):
        current = getattr(w, name, None)
        if isinstance(current, (int, float)) and not isinstance(current, bool):
            try:  # Orange converts with int()/float() in an unguarded slot
                (int if isinstance(current, int) else float)(str(value))
            except ValueError:
                raise ValueError(
                    "%s expects a %s, got %r" % (
                        name, type(current).__name__, value)) from None
        ctl.setText(str(value))
        ctl.editingFinished.emit()
        ctl.returnPressed.emit()
        return "lineedit.setText+returnPressed"
    rb = _radio_buttons(ctl)
    if rb is not None:
        if isinstance(value, str):
            labels = [_clean(b.text()).lower() for b in rb]
            if value.lower() not in labels:
                raise ValueError("%r not in options %s" % (value, labels))
            idx = labels.index(value.lower())
        else:
            idx = int(value)
        rb[idx].click()
        return "radio.click"
    if isinstance(ctl, QAbstractItemView):
        model, sel = ctl.model(), ctl.selectionModel()
        items = _list_items(ctl, limit=100000)
        want = value if isinstance(value, (list, tuple)) else [value]
        rows = []
        for v in want:
            if isinstance(v, int):
                rows.append(v)
            elif v in items:
                rows.append(items.index(v))
            else:
                raise ValueError("%r not in list items %s" % (v, items[:30]))
        sel.clearSelection()
        for r in rows:
            sel.select(model.index(r, 0), QItemSelectionModel.SelectionFlag.Select)
        return "list.select(%d rows)" % len(rows)
    raise TypeError("unsupported control %s" % type(ctl).__name__)


def set_setting(node, name, value):
    n, w = _widget(node)
    if name not in w.settingsHandler.known_settings:
        raise KeyError("unknown setting %r; known: %s" % (
            name, sorted(set(w.settingsHandler.known_settings)
                         - _INTERNAL_SETTINGS)))
    obj, attr = _resolve(w, name)
    old = getattr(obj, attr, None)
    cf = _controlled(obj, attr)
    ctl = getattr(cf[0], "control", None) if cf else None
    if ctl is not None:
        via = _set_via_control(obj, attr, ctl, value)
    else:
        setattr(obj, attr, value)
        via = "setattr (no GUI control; callbacks NOT triggered)"
    new = getattr(obj, attr, None)
    return {"name": name, "old": _jsonable(old), "new": _jsonable(new),
            "via": via, "messages": _messages(w)}


def click(node, button):
    n, w = _widget(node)
    want = _clean(button).lower()
    cands = [b for b in w.findChildren(QAbstractButton)
             if _clean(b.text()).lower() == want and b.isVisibleTo(w)]
    if not cands:
        raise KeyError("no button %r; available: %s" % (
            button, [b["text"] for b in _list_buttons(w)]))
    cands = [b for b in cands if b.isEnabled()] or cands
    b = cands[0]
    if not b.isEnabled():
        raise RuntimeError("button %r is disabled" % button)
    b.click()
    return {"clicked": _clean(b.text()), "messages": _messages(w)}


def update_widget(node, settings=None, click_button=None):
    results = [set_setting(node, k, v) for k, v in (settings or {}).items()]
    out = {"settings": results}
    if click_button:
        out["click"] = click(node, click_button)
    n, w = _widget(node)
    out["messages"] = _messages(w)
    out["state"] = _state(n, w)
    from . import dialog_guard
    if dialog_guard.pending_error_count():
        out["new_errors"] = dialog_guard.pending_error_count()
        out["hint"] = "an error dialog was auto-closed; call get_errors"
    return out


# ----------------------------------------------------------------- dialogs
# Never submit error reports: prefer the harmless button.
_DISMISS_PREFERENCE = ("don't send", "dont send", "cancel", "close", "no",
                       "ok", "discard", "ignore")


def _open_dialogs():
    from orangecanvas.application.canvasmain import CanvasMainWindow
    out = []
    for w in QApplication.topLevelWidgets():
        if isinstance(w, CanvasMainWindow) or not w.isVisible():
            continue
        if isinstance(w, QDialog):
            out.append(w)
    return out


def _dialog_info(d, idx):
    if isinstance(d, QMessageBox):
        texts = [t for t in (d.text(), d.informativeText()) if t]
    else:
        texts = [_clean_full(l.text()) for l in d.findChildren(QLabel)
                 if l.text() and l.isVisibleTo(d)][:6]
    btns = [_clean(b.text()) for b in d.findChildren(QAbstractButton)
            if b.isVisibleTo(d) and _clean(b.text())]
    return {"index": idx, "title": d.windowTitle(),
            "class": type(d).__name__, "text": texts[:6],
            "buttons": btns, "modal": d.isModal()}


def _clean_full(t):
    return " ".join((t or "").split())[:300]


def list_dialogs():
    return [_dialog_info(d, i) for i, d in enumerate(_open_dialogs())]


def answer_dialog(button=None, index=0):
    """Click `button` in an open dialog, or dismiss it harmlessly
    (error-report dialogs are answered with 'Don't Send')."""
    dlgs = _open_dialogs()
    if not dlgs:
        raise RuntimeError("no open dialog")
    d = dlgs[index]
    info = _dialog_info(d, index)
    btns = [b for b in d.findChildren(QAbstractButton) if b.isVisibleTo(d)]
    labels = [_clean(b.text()).lower() for b in btns]
    pick = None
    if button:
        want = _clean(button).lower()
        if want in labels:
            pick = btns[labels.index(want)]
        else:
            raise KeyError("no button %r; available %s" % (button, info["buttons"]))
    else:
        for pref in _DISMISS_PREFERENCE:
            if pref in labels:
                pick = btns[labels.index(pref)]
                break
    if pick is not None:
        pick.click()
        how = "clicked %r" % _clean(pick.text())
    else:
        d.close()
        how = "closed"
    return {"dialog": info["title"], "action": how}


# ------------------------------------------------------------------- status
def get_status(node=None):
    scheme = _scheme()
    nodes = [_node(node)] if node else list(scheme.nodes)
    res = []
    for n in nodes:
        w = scheme.widget_for_node(n)
        item = {"id": _id(n, "n"), "title": n.title}
        if w is not None:
            item.update(_state(n, w))
            item["messages"] = _messages(w)
        else:
            item["busy"] = False
            item["note"] = "widget not created"
        res.append(item)
    from . import dialog_guard
    dialogs = [_dialog_info(d, i) for i, d in enumerate(_open_dialogs())]
    out = {"busy": any(r.get("busy") for r in res), "nodes": res}
    n_err = dialog_guard.pending_error_count()
    if n_err:
        out["new_errors"] = n_err  # auto-dismissed error dialogs: get_errors
    if dialogs:
        out["dialogs"] = dialogs  # an open dialog may be blocking work
    return out


# ------------------------------------------------------------------- output
def _var_info(v):
    d = {"name": v.name, "type": type(v).__name__}
    vals = getattr(v, "values", None)
    if vals:
        d["values"] = list(vals)[:10]
    return d


def _summarize(v, rows):
    from Orange.data import Table
    if isinstance(v, Table):
        dom = v.domain
        cols = list(dom.variables) + list(dom.metas)
        head = [[str(inst[c]) for c in cols[:30]] for inst in v[:rows]]
        return {"type": "Table", "rows": len(v),
                "attributes": [_var_info(a) for a in dom.attributes][:60],
                "class_vars": [_var_info(a) for a in dom.class_vars],
                "metas": [_var_info(a) for a in dom.metas][:30],
                "head_columns": [c.name for c in cols[:30]], "head": head}
    shape = getattr(v, "shape", None)
    return {"type": type(v).__name__,
            "shape": list(shape) if shape is not None else None,
            "repr": _jsonable(repr(v))}


def get_output(node, channel=None, rows=8):
    n = _node(node)
    sm = _scheme().signal_manager
    outs = sm._SignalManager__node_outputs.get(n, {})
    res = {}
    for ch in n.output_channels():
        if channel and channel not in (ch.name, getattr(ch, "id", None)):
            continue
        state = outs.get(ch)
        values = list(state.outputs.values()) if state is not None else []
        values = [v for v in values if v is not None]
        res[ch.name] = (_summarize(values[0], rows) if values
                        else {"type": None, "note": "no output (yet)"})
    if channel and not res:
        raise KeyError("no output channel %r; outputs: %s"
                       % (channel, [c.name for c in n.output_channels()]))
    return res


# ---------------------------------------------------------------- selection
def select_data(node, rect=None, rows=None, clear=False):
    """Select data in a widget.
    rect=[x0, y0, x1, y1] in data coordinates (scatter-plot-like widgets);
    rows=[...] row indices (plots: data rows; tables: rows as displayed);
    clear=True drops the selection first."""
    from AnyQt.QtCore import QRectF
    from AnyQt.QtWidgets import QAbstractItemView, QComboBox
    import numpy as np
    n, w = _widget(node)
    g = getattr(w, "graph", None)
    if g is not None and hasattr(g, "select_by_indices"):
        if clear and hasattr(g, "unselect_all"):
            g.unselect_all()
        if rect is not None:
            x0, y0, x1, y1 = [float(v) for v in rect]
            g.select_by_rectangle(QRectF(min(x0, x1), min(y0, y1),
                                         abs(x1 - x0), abs(y1 - y0)))
        elif rows is not None:
            g.select_by_indices(np.asarray(rows, dtype=int))
        elif not clear:
            raise ValueError("give rect=[x0,y0,x1,y1], rows=[...] or clear=true")
        sel = getattr(w, "selection", None)
        # widget.selection holds (row index, group) pairs
        count = len(sel) if sel is not None else 0
        return {"via": "plot", "selected": count, "messages": _messages(w)}
    # table-like widgets: drive the item view's selection model
    views = [v for v in w.findChildren(QAbstractItemView)
             if v.model() is not None and v.model().rowCount() > 0
             and v.selectionModel() is not None
             and not isinstance(v.parent(), QComboBox)
             and v.selectionMode() != QAbstractItemView.SelectionMode.NoSelection]
    if not views:
        raise TypeError("%s has no selectable plot or table" % n.title)
    view = max(views, key=lambda v: v.model().rowCount())
    sel = view.selectionModel()
    if clear or rows is not None:
        sel.clearSelection()
    if rows is not None:
        from AnyQt.QtCore import QItemSelection
        model = view.model()
        cols = model.columnCount() - 1
        s = QItemSelection()
        for r in rows:
            s.select(model.index(int(r), 0), model.index(int(r), cols))
        sel.select(s, QItemSelectionModel.SelectionFlag.Select)
    elif rect is not None:
        raise TypeError("rect selection needs a plot widget")
    return {"via": "table view", "selected": len(sel.selectedRows()),
            "messages": _messages(w)}


# ------------------------------------------------------------ File helper
def load_file(node, path):
    """Point a File widget at `path` (or a bundled dataset name like 'iris')."""
    n, w = _widget(node)
    if not hasattr(w, "add_path") or not hasattr(w, "load_data"):
        raise TypeError("%s is not a File-like widget" % n.title)
    if not os.path.isfile(path):
        import Orange
        ds = os.path.join(os.path.dirname(Orange.__file__), "datasets")
        for ext in ("", ".tab", ".csv", ".xlsx"):
            cand = os.path.join(ds, path + ext)
            if os.path.isfile(cand):
                path = cand
                break
        else:
            raise FileNotFoundError(path)
    path = os.path.abspath(path)
    w.add_path(path)
    w.source = w.LOCAL_FILE
    w.load_data()
    return {"loaded": os.path.basename(path), "messages": _messages(w)}


# ----------------------------------------------------------------- workflow
def open_workflow(path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    win = _window()
    win.load_scheme(path)
    scheme = win.current_document().scheme()
    return {"path": path, "title": scheme.title, "nodes": len(scheme.nodes),
            "links": len(scheme.links)}


def save_workflow(path=None):
    win = _window()
    doc = win.current_document()
    scheme = doc.scheme()
    if path is None:
        path = doc.path()
        if not path:
            raise ValueError("workflow has no path yet; pass path")
    path = os.path.abspath(path)
    if not win.save_scheme_to(scheme, path):
        raise OSError("could not save workflow to %s" % path)
    doc.setPath(path)
    doc.setModified(False)
    return {"path": path, "nodes": len(scheme.nodes), "links": len(scheme.links)}


def clear_workflow():
    scheme = _scheme()
    n = len(scheme.nodes)
    scheme.clear()
    win = _window()
    doc = win.current_document()
    doc.setPath("")
    return {"removed_nodes": n}


COMMANDS = {f.__name__: f for f in (
    inspect_widget, set_setting, click, update_widget, get_status, get_output,
    open_workflow, save_workflow, clear_workflow, load_file,
    list_dialogs, answer_dialog, select_data,
)}
