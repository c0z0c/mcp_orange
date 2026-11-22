"""Source and help lookup for widgets (by node id or widget name)."""
import inspect
import os
import re
import sys
from html.parser import HTMLParser

from .commands import _scheme, _node

_help_index = None


def _description(widget):
    """Resolve a node id ('n3') or a widget name/qualified name to
    (WidgetDescription, class)."""
    from orangecanvas.registry import global_registry
    reg = global_registry()
    try:
        node = _node(widget)
        desc = node.description
    except KeyError:
        try:
            desc = reg.widget(widget)
        except KeyError:
            m = [d for d in reg.widgets() if d.name.lower() == widget.lower()
                 and ".obsolete." not in d.qualified_name]
            if not m:
                raise KeyError("no node or widget %r" % widget)
            desc = m[0]
    import importlib
    mod, _, cls = desc.qualified_name.rpartition(".")
    return desc, getattr(importlib.import_module(mod), cls)


def get_widget_source(widget, offset=0, max_chars=12000):
    desc, cls = _description(widget)
    src = inspect.getsource(cls)
    chunk = src[offset:offset + max_chars]
    return {"widget": desc.qualified_name,
            "file": inspect.getsourcefile(cls),
            "total_chars": len(src), "offset": offset,
            "returned_chars": len(chunk),
            "next_offset": (offset + max_chars
                            if offset + max_chars < len(src) else None),
            "source": chunk}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip, self.h1 = [], 0, None
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "head"):
            self.skip += 1
        if tag == "h1":
            self._in_h1 = True
        if tag in ("p", "li", "br", "h1", "h2", "h3", "tr", "div"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "head"):
            self.skip = max(0, self.skip - 1)
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        if self.skip:
            return
        if self._in_h1 and self.h1 is None:
            self.h1 = data.strip(" \n¶")
        self.parts.append(data)

    def text(self):
        t = "".join(self.parts)
        t = re.sub(r"[ \t]+", " ", t)
        return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _build_help_index():
    global _help_index
    if _help_index is not None:
        return _help_index
    idx = {}
    root = os.path.join(sys.prefix, "help")
    for dirpath, _, files in os.walk(root):
        if os.sep + "widgets" not in dirpath + os.sep:
            continue
        for fn in files:
            if not fn.endswith(".html"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    parser = _Text()
                    parser.feed(f.read(6000))
                if parser.h1:
                    idx.setdefault(_norm(parser.h1), p)
            except OSError:
                pass
    _help_index = idx
    return idx


def get_widget_help(widget, max_chars=6000):
    desc, cls = _description(widget)
    out = {
        "widget": desc.qualified_name, "name": desc.name,
        "category": desc.category,
        "description": desc.description,
        "keywords": list(desc.keywords or []),
        "inputs": [{"name": i.name, "types": [getattr(t, "__name__", str(t))
                                                for t in i.types]}
                   for i in desc.inputs],
        "outputs": [{"name": o.name, "types": [getattr(t, "__name__", str(t))
                                                 for t in o.types]}
                    for o in desc.outputs],
        "class_doc": inspect.getdoc(cls),
        "online_help": desc.help,
    }
    path = _build_help_index().get(_norm(desc.name))
    if path:
        with open(path, encoding="utf-8", errors="replace") as f:
            p = _Text()
            p.feed(f.read())
        text = p.text()
        out["offline_help_file"] = path
        out["offline_help"] = text[:max_chars]
        out["offline_help_truncated"] = len(text) > max_chars
    else:
        out["offline_help"] = None
        out["note"] = ("no bundled manual page for this widget "
                       "(core Orange docs are online only); "
                       "use inspect_widget / get_widget_source")
    return out


COMMANDS = {f.__name__: f for f in (get_widget_source, get_widget_help)}
