"""stdio MCP server that relays to the Orange canvas bridge.

Run by an MCP client as:  mcp_orange.exe --mcp-server   (development: python relay/mcp_orange.py)
Stateless: all state lives in the running Orange process, so several clients
(each with its own relay process) can control the same Orange instance.
Never print to stdout - it carries the MCP protocol.
"""
import sys
import time
from pathlib import Path
from typing import Annotated, Any, Optional

if not getattr(sys, "frozen", False):          # 개발 모드: 같은 저장소의 모듈을 찾는다
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from bridge_client import BridgeError, call  # noqa: E402
from mcp_orange_app import launcher  # noqa: E402

from mcp.server.fastmcp import FastMCP, Image  # noqa: E402
from pydantic import Field  # noqa: E402

Node = Annotated[str, Field(description="Node id such as 'n3' (from add_node / list_nodes)")]

mcp = FastMCP(
    "orange3",
    instructions=(
        "Drives a live Orange 3 canvas (the user can watch it).\n"
        "Flow: orange_status (launch_orange if needed) -> list_widgets -> "
        "add_node + add_link (+ load_file) -> wait_until_idle -> "
        "inspect_widget -> update_widget -> get_output / screenshot.\n"
        "Read 'messages' in results (widget errors/warnings). If a result "
        "shows new_errors, call get_errors: Orange error dialogs are closed "
        "automatically and never reported."))


def _call(cmd: str, **args: Any) -> Any:
    try:
        return call(cmd, **{k: v for k, v in args.items() if v is not None})
    except BridgeError as ex:
        raise ValueError(str(ex)) from None


# ------------------------------------------------------------------ lifecycle
@mcp.tool()
def orange_status() -> dict:
    """Check whether Orange is running. Returns version and workflow size."""
    try:
        return {"running": True, **call("ping")}
    except BridgeError as ex:
        return {"running": False, "detail": str(ex), "hint": "call launch_orange"}


@mcp.tool()
def launch_orange(show_welcome: bool = False, timeout_s: int = 120) -> dict:
    """Start Orange if it is not running (no welcome screen). Safe to repeat.
    Finds an installed Orange automatically and checks it is compatible first."""
    try:
        return {"already_running": True, **call("ping")}
    except BridgeError:
        pass
    try:
        target = launcher.resolve_target()
        plan = launcher.build_plan(target.python, show_welcome=show_welcome)
    except launcher.LaunchError as ex:
        raise ValueError(str(ex)) from None
    launcher.spawn(plan, detach_from_job=True)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(1.0)
        try:
            res = {"already_running": False, **call("ping"), "orange_python": target.python,
                   "compat": target.status}
            if target.status != "verified":
                res["warning"] = target.summary
            return res
        except BridgeError:
            continue
    raise ValueError("Orange did not start within %ds (log: %s)" % (timeout_s, plan.logfile))


# ------------------------------------------------------------------- catalogue
@mcp.tool()
def list_widgets(
        query: Annotated[Optional[str], Field(description="Substring of name/keywords, e.g. 'tree'")] = None,
        category: Annotated[Optional[str], Field(description="Category substring, e.g. 'Visualize'")] = None,
        limit: int = 40) -> dict:
    """Search the widget catalog. Returns widget name, category and the
    input/output channel names. Pass the name to add_node."""
    return _call("list_widgets", query=query, category=category, limit=limit)


@mcp.tool()
def get_widget_help(widget: Annotated[str, Field(description="Node id or widget name")],
                    max_chars: int = 6000) -> dict:
    """Widget description, typed inputs/outputs and, when bundled, its manual."""
    return _call("get_widget_help", widget=widget, max_chars=max_chars)


@mcp.tool()
def get_widget_source(widget: Annotated[str, Field(description="Node id or widget name")],
                      offset: int = 0, max_chars: int = 12000) -> dict:
    """Python source of a widget class, paged (next_offset). Last resort when
    inspect_widget and get_widget_help do not explain a behaviour."""
    return _call("get_widget_source", widget=widget, offset=offset,
                 max_chars=max_chars)


# ----------------------------------------------------------------------- graph
@mcp.tool()
def list_nodes() -> list:
    """List workflow nodes: id, title, widget, input/output channel names."""
    return _call("list_nodes")


@mcp.tool()
def list_links() -> list:
    """List workflow links: id, source/sink node and channel."""
    return _call("list_links")


@mcp.tool()
def add_node(
        widget: Annotated[str, Field(description="Widget name, e.g. 'k-Means'")],
        title: Optional[str] = None,
        x: Optional[float] = None, y: Optional[float] = None) -> dict:
    """Add a widget. Returns the node id and its channel names. Position is
    optional (placed to the right of the last node)."""
    return _call("add_node", widget=widget, title=title, x=x, y=y)


@mcp.tool()
def remove_node(node: Node) -> dict:
    """Remove a node and its links."""
    return _call("remove_node", node=node)


@mcp.tool()
def add_link(
        source: Node, sink: Node,
        source_channel: Annotated[Optional[str], Field(description="Output name; auto if omitted")] = None,
        sink_channel: Annotated[Optional[str], Field(description="Input name; auto if omitted")] = None) -> dict:
    """Connect source output to sink input. Give the channels when more than
    one fits (e.g. Test and Score: 'Data' vs 'Learner')."""
    return _call("add_link", source=source, sink=sink,
                 source_channel=source_channel, sink_channel=sink_channel)


@mcp.tool()
def remove_link(link: Annotated[str, Field(description="Link id such as 'l4'")]) -> dict:
    """Remove a link."""
    return _call("remove_link", link=link)


# ------------------------------------------------------------- widget control
@mcp.tool()
def inspect_widget(node: Node, buttons: bool = True) -> dict:
    """Read a widget: settings (name, value, control kind with options or
    range), buttons, messages and busy state. Call before update_widget.
    Names with a dot (graph.alpha_value) are sub-component settings."""
    return _call("inspect_widget", node=node, buttons=buttons)


@mcp.tool()
def update_widget(
        node: Node,
        settings: Annotated[Optional[dict], Field(
            description="{name: value}. number/bool/text; option text or index "
                        "for combo and radio; list of item names/indices for lists")] = None,
        click_button: Annotated[Optional[str], Field(
            description="Button text to click after the settings, e.g. 'Apply'")] = None) -> dict:
    """Change settings through the widget's real controls, so Orange recomputes
    as for a user, then optionally click a button. Invalid values are rejected
    with the reason. Check 'messages' in the result."""
    return _call("update_widget", node=node, settings=settings,
                 click_button=click_button)


@mcp.tool()
def click_button(node: Node, button: Annotated[str, Field(description="Button text")]) -> dict:
    """Click one visible button of a widget."""
    return _call("click", node=node, button=button)


@mcp.tool()
def select_data(
        node: Node,
        rect: Annotated[Optional[list], Field(description="[x0, y0, x1, y1] in axis units (plots), e.g. [4.5, 2.0, 6.0, 3.5]")] = None,
        rows: Annotated[Optional[list], Field(description="Row indices (plots: data rows; tables: as displayed)")] = None,
        clear: bool = False) -> dict:
    """Select data as a user would (plots by rectangle or rows, tables by
    rows). The selection flows to the widget's 'Selected Data' output."""
    return _call("select_data", node=node, rect=rect, rows=rows, clear=clear)


@mcp.tool()
def load_file(
        node: Annotated[str, Field(description="Node id of a File widget")],
        path: Annotated[str, Field(description="File path or bundled dataset name: iris, titanic, heart_disease...")]) -> dict:
    """Load data into a File widget."""
    return _call("load_file", node=node, path=path)


# ------------------------------------------------------------- results/status
@mcp.tool()
def get_status(node: Optional[str] = None) -> dict:
    """Busy flag plus error/warning messages for one node or all nodes."""
    return _call("get_status", node=node)


@mcp.tool()
def wait_until_idle(timeout_s: float = 60.0) -> dict:
    """Wait until no widget is computing. Use after loading data, linking or
    changing settings of heavy widgets. Returns nodes that report problems."""
    t0 = time.time()
    while True:
        st = _call("get_status")
        if not st["busy"]:
            res = {"idle": True, "waited_s": round(time.time() - t0, 1),
                   "problems": [n for n in st["nodes"] if n.get("messages")]}
            if st.get("dialogs"):
                res["open_dialogs"] = st["dialogs"]
            if st.get("new_errors"):
                res["new_errors"] = st["new_errors"]
                res["hint"] = "call get_errors"
            return res
        if time.time() - t0 > timeout_s:
            return {"idle": False, "waited_s": round(time.time() - t0, 1),
                    "busy_nodes": [n["id"] for n in st["nodes"] if n.get("busy")]}
        time.sleep(0.3)


@mcp.tool()
def get_output(
        node: Node,
        channel: Annotated[Optional[str], Field(description="Output name; all outputs if omitted")] = None,
        rows: int = 8) -> dict:
    """Latest output of a node, as data. Tables: row count, columns, first
    `rows` rows. Other objects (models, plots, ...): type and short repr only.
    What a plot or visual widget draws is not in the data: use screenshot.
    Call wait_until_idle first, otherwise the output may be stale or empty."""
    return _call("get_output", node=node, channel=channel, rows=rows)


@mcp.tool()
def screenshot(target: Annotated[str, Field(description="'window' for the canvas, or a node id for that widget")] = "window") -> list:
    """PNG image of the canvas board (target='window': node/link layout) or of
    one widget window (target=node id such as 'n3': plot, table, results).
    Call wait_until_idle first so the image shows the finished result. Returns
    the image plus its size and the PNG file path. The widget is rendered
    directly; there is no tool to open or show its window, and a widget that
    was never shown may render with an unfinished layout. For exact values
    use get_output / inspect_widget instead of reading them off the image."""
    r = _call("screenshot", target=target)
    return [Image(path=r["path"]), "%dx%d, saved at %s"
            % (r["width"], r["height"], r["path"])]


# ----------------------------------------------------------- errors / dialogs
@mcp.tool()
def get_errors(clear: bool = False, limit: int = 10) -> dict:
    """Error dialogs Orange raised (auto-closed, never reported): widget,
    exception, traceback. Call when a result shows new_errors or looks wrong."""
    return _call("get_errors", clear=clear, limit=limit)


@mcp.tool()
def set_auto_dismiss(enabled: bool = True, all_message_boxes: bool = False) -> dict:
    """Auto-close Orange error dialogs (default on). all_message_boxes=true
    also closes ordinary message boxes."""
    return _call("set_auto_dismiss", enabled=enabled,
                 all_message_boxes=all_message_boxes)


@mcp.tool()
def list_dialogs() -> list:
    """Open dialogs (title, text, buttons). Non-error dialogs stay open until
    answered."""
    return _call("list_dialogs")


@mcp.tool()
def answer_dialog(
        button: Annotated[Optional[str], Field(description="Button text; omit for the safe default")] = None,
        index: int = 0) -> dict:
    """Click a button in an open dialog. Default: a harmless one (e.g.
    "Don't Send"); reports are never submitted."""
    return _call("answer_dialog", button=button, index=index)


# ------------------------------------------------------------------- workflow
@mcp.tool()
def open_workflow(path: Annotated[str, Field(description="Path to an .ows file")]) -> dict:
    """Load an .ows workflow, replacing the current one."""
    return _call("open_workflow", path=path)


@mcp.tool()
def save_workflow(path: Annotated[Optional[str], Field(description="Target .ows; omit to save to the current file")] = None) -> dict:
    """Save the workflow to an .ows file."""
    return _call("save_workflow", path=path)


@mcp.tool()
def clear_workflow() -> dict:
    """Remove all nodes and links."""
    return _call("clear_workflow")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
