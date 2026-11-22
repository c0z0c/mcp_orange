"""TCP (127.0.0.1) JSON-lines server. All commands run on the Qt GUI thread."""
import atexit
import json
import logging
import os
import secrets
import socketserver
import threading
import traceback
from concurrent.futures import Future

from AnyQt.QtCore import QObject, pyqtSignal, QCoreApplication

from . import commands, widget_ops, widget_docs, dialog_guard

log = logging.getLogger("orange_mcp_bridge")
ALL_COMMANDS = {**commands.COMMANDS, **widget_ops.COMMANDS,
                **widget_docs.COMMANDS, **dialog_guard.COMMANDS}

DISCOVERY_DIR = os.environ.get("MCP_ORANGE_HOME") or os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "mcp_orange")
DISCOVERY_FILE = os.path.join(DISCOVERY_DIR, "bridge.json")
CALL_TIMEOUT = 120.0


class GuiInvoker(QObject):
    """Runs callables on the thread this object lives in (the GUI thread)."""
    _job = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._job.connect(self._run)

    def _run(self, job):
        fn, fut = job
        if not fut.set_running_or_notify_cancel():
            return
        try:
            fut.set_result(fn())
        except BaseException as ex:  # noqa - report everything to the caller
            fut.set_exception(ex)

    def call(self, fn, timeout=CALL_TIMEOUT):
        fut = Future()
        self._job.emit((fn, fut))  # queued: receiver lives in GUI thread
        return fut.result(timeout)


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        server = self.server
        for raw in self.rfile:
            raw = raw.strip()
            if not raw:
                continue
            reply = {"id": None}
            try:
                req = json.loads(raw.decode("utf-8"))
                reply["id"] = req.get("id")
                if not secrets.compare_digest(
                        str(req.get("token", "")), server.token):
                    raise PermissionError("bad token")
                cmd = req["cmd"]
                args = req.get("args") or {}
                fn = ALL_COMMANDS.get(cmd)
                if fn is None:
                    raise KeyError("unknown command %r" % cmd)
                result = server.invoker.call(lambda: fn(**args))
                reply.update(ok=True, result=result)
            except BaseException as ex:  # noqa
                reply.update(ok=False, error="%s: %s" % (type(ex).__name__, ex),
                             trace=traceback.format_exc(limit=8))
            try:
                data = json.dumps(reply, ensure_ascii=False, default=str)
                self.wfile.write(data.encode("utf-8") + b"\n")
                self.wfile.flush()
            except OSError:
                return


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_bridge():
    app = QCoreApplication.instance()
    dialog_guard.install()  # GUI thread: auto-close error dialogs
    invoker = GuiInvoker()  # created on the GUI thread
    invoker.moveToThread(app.thread())
    srv = _Server(("127.0.0.1", 0), _Handler)
    srv.token = secrets.token_hex(16)
    srv.invoker = invoker
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, name="orange-mcp-bridge",
                     daemon=True).start()

    os.makedirs(DISCOVERY_DIR, exist_ok=True)
    with open(DISCOVERY_FILE, "w", encoding="utf-8") as f:
        json.dump({"port": port, "token": srv.token, "pid": os.getpid()}, f)

    def _cleanup():
        try:
            with open(DISCOVERY_FILE, encoding="utf-8") as f:
                if json.load(f).get("pid") == os.getpid():
                    os.remove(DISCOVERY_FILE)
        except Exception:
            pass
    atexit.register(_cleanup)
    log.info("MCP bridge listening on 127.0.0.1:%d", port)
    srv._keepalive = invoker  # keep the QObject alive
    return srv
