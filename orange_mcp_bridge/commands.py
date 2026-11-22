"""Bridge commands. Every function here runs on the Qt GUI thread."""
import itertools
import os
import tempfile

from AnyQt.QtWidgets import QApplication

_counter = itertools.count(1)


# ----------------------------------------------------------------- helpers
def _window():
    from orangecanvas.application.canvasmain import CanvasMainWindow
    wins = [w for w in QApplication.topLevelWidgets()
            if isinstance(w, CanvasMainWindow) and w.isVisible()]
    if not wins:
        wins = [w for w in QApplication.topLevelWidgets()
                if isinstance(w, CanvasMainWindow)]
    if not wins:
        raise RuntimeError("no canvas window")
    active = QApplication.activeWindow()
    return active if active in wins else wins[0]


def _scheme():
    return _window().current_document().scheme()


def _id(obj, prefix):
    if not hasattr(obj, "_mcp_id"):
        obj._mcp_id = "%s%d" % (prefix, next(_counter))
    return obj._mcp_id


def _node(node_id):
    scheme = _scheme()
    for n in scheme.nodes:
        if _id(n, "n") == node_id or n.title == node_id:
            return n
    raise KeyError("no such node %r (use list_nodes)" % node_id)


def _channel(channels, name, kind):
    if name is None:
        return None
    for ch in channels:
        if name in (ch.name, getattr(ch, "id", None)):
            return ch
    raise KeyError("%s channel %r not found; available: %s"
                   % (kind, name, [c.name for c in channels]))


def _is_obsolete(desc):
    return ".obsolete." in desc.qualified_name or \
        (desc.category or "").lower() == "obsolete"


def _node_info(node):
    return {
        "id": _id(node, "n"),
        "title": node.title,
        "widget": node.description.qualified_name,
        "name": node.description.name,
        "position": list(node.position),
        "inputs": [c.name for c in node.input_channels()],
        "outputs": [c.name for c in node.output_channels()],
    }


def _link_info(link):
    return {
        "id": _id(link, "l"),
        "source": _id(link.source_node, "n"),
        "source_channel": link.source_channel.name,
        "sink": _id(link.sink_node, "n"),
        "sink_channel": link.sink_channel.name,
        "enabled": link.enabled,
    }


# ---------------------------------------------------------------- commands
def ping():
    import sys
    import Orange
    w = _window()
    scheme = w.current_document().scheme()
    return {"orange": Orange.__version__, "python": sys.version.split()[0],
            "workflow_title": scheme.title, "nodes": len(scheme.nodes),
            "links": len(scheme.links), "path": w.current_document().path()}


def list_widgets(query=None, category=None, limit=60):
    from orangecanvas.registry import global_registry
    reg = global_registry()
    q = (query or "").lower()
    out = []
    for d in reg.widgets():
        if _is_obsolete(d):
            continue
        cat = d.category or ""
        if category and category.lower() not in cat.lower():
            continue
        hay = " ".join([d.name, d.qualified_name, d.description or "",
                        " ".join(d.keywords or [])]).lower()
        if q and q not in hay:
            continue
        out.append({"widget": d.qualified_name, "name": d.name,
                    "category": cat,
                    "inputs": [i.name for i in d.inputs],
                    "outputs": [o.name for o in d.outputs]})
    total = len(out)
    return {"total": total, "returned": min(total, limit), "widgets": out[:limit]}


def list_nodes():
    return [_node_info(n) for n in _scheme().nodes]


def list_links():
    return [_link_info(l) for l in _scheme().links]


def add_node(widget, title=None, x=None, y=None):
    from orangecanvas.registry import global_registry
    reg = global_registry()
    desc = None
    try:
        desc = reg.widget(widget)
    except KeyError:
        matches = [d for d in reg.widgets()
                   if d.name.lower() == widget.lower()]
        current = [d for d in matches if not _is_obsolete(d)]
        matches = current or matches
        if len(matches) == 1:
            desc = matches[0]
        elif matches:
            raise KeyError("ambiguous widget name %r: %s"
                           % (widget, [m.qualified_name for m in matches]))
    if desc is None:
        raise KeyError("unknown widget %r (use list_widgets)" % widget)
    scheme = _scheme()
    if x is None or y is None:
        xs = [n.position[0] for n in scheme.nodes]
        x = (max(xs) + 180) if xs else 100
        y = scheme.nodes[-1].position[1] if scheme.nodes else 100
    node = scheme.new_node(desc, title=title, position=(float(x), float(y)))
    return _node_info(node)


def remove_node(node):
    n = _node(node)
    info = _node_info(n)
    _scheme().remove_node(n)
    return {"removed": info}


def add_link(source, sink, source_channel=None, sink_channel=None):
    from orangecanvas.scheme.link import possible_links
    scheme = _scheme()
    src, dst = _node(source), _node(sink)
    out_ch = _channel(src.output_channels(), source_channel, "output")
    in_ch = _channel(dst.input_channels(), sink_channel, "input")
    if out_ch is None or in_ch is None:
        cands = [(o, i) for o, i in possible_links(src, dst)
                 if (out_ch is None or o is out_ch)
                 and (in_ch is None or i is in_ch)]
        if not cands:
            raise ValueError(
                "no compatible channels between %s outputs %s and %s inputs %s"
                % (src.title, [c.name for c in src.output_channels()],
                   dst.title, [c.name for c in dst.input_channels()]))
        out_ch, in_ch = cands[0]
    link = scheme.new_link(src, out_ch, dst, in_ch)
    return _link_info(link)


def remove_link(link):
    scheme = _scheme()
    for l in scheme.links:
        if _id(l, "l") == link:
            info = _link_info(l)
            scheme.remove_link(l)
            return {"removed": info}
    raise KeyError("no such link %r (use list_links)" % link)


def screenshot(target="window", path=None):
    """Save a PNG of the canvas window ('window') or a node's widget window."""
    if path is None:
        fd, path = tempfile.mkstemp(prefix="orange_mcp_", suffix=".png")
        os.close(fd)
    if target == "window":
        pix = _window().grab()
    else:
        w = _scheme().widget_for_node(_node(target))
        pix = w.grab()
    if not pix.save(path, "PNG"):
        raise OSError("could not save screenshot to %s" % path)
    return {"path": path, "width": pix.width(), "height": pix.height()}


def debug_exec(code):
    """DEV ONLY. Executes Python in the Orange process. Disabled unless the
    environment variable ORANGE_MCP_DEBUG=1 was set when Orange started."""
    if os.environ.get("ORANGE_MCP_DEBUG") != "1":
        raise PermissionError("debug_exec is disabled")
    ns = {"scheme": _scheme(), "window": _window(), "node": _node,
          "widget": lambda nid: _scheme().widget_for_node(_node(nid)),
          "result": None}
    exec(code, ns)
    return repr(ns["result"])


COMMANDS = {f.__name__: f for f in (
    ping, list_widgets, list_nodes, list_links, add_node, remove_node,
    add_link, remove_link, screenshot, debug_exec,
)}
