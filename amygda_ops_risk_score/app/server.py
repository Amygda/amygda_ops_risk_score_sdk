"""The fleet app's backend: one monitor folder, served on this machine.

Everything that scores or stores data is the monitor's own code
(``amygda_ops_risk_score.monitor``). This module adds a page, a few JSON
endpoints, one worker for runs and a scheduler. It uses only the standard
library.

Endpoints (state-changing ones need the ``X-Amygda-App: 1`` header, which a
page on another site can't send):

    GET    /                    the dashboard, with the app's controls
    GET    /api/state           running or idle, last run, inbox, schedule
    POST   /api/run             start a run on the files in the inbox
    PUT    /api/inbox/<name>    add a file (the request body is the file)
    DELETE /api/inbox/<name>    remove a waiting file
    POST   /api/schedule        set the schedule (JSON), or null for none
    POST   /api/schedule/pause  and /api/schedule/resume
    POST   /api/alerts/<id>/ack acknowledge an alert ("all" for every open one)
    POST   /api/alerts/rules    set what raises an alert (JSON: {"rules": [...]})
    POST   /api/layout          set the tabs, panels and header figures (JSON)
"""

from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from importlib import resources
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable, Dict, Optional
from urllib.parse import unquote

from amygda_ops_risk_score.app.schedule import describe
from amygda_ops_risk_score.app.schedule import next_run
from amygda_ops_risk_score.monitor import spec as app_spec
from amygda_ops_risk_score.monitor.project import DEFAULT_KEY_ENV
from amygda_ops_risk_score.monitor.project import INPUT_TYPES
from amygda_ops_risk_score.monitor.project import Monitor
from amygda_ops_risk_score.monitor.project import MonitorError

DEFAULT_PORT = 8050
HOST = "127.0.0.1"
MAX_UPLOAD_BYTES = 1024 ** 3
TICK_SECONDS = 20
HEADER = "X-Amygda-App"


class AppError(Exception):
    """Something the person using the app can fix. Shown to them as is."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def load_env(folder: Path, only: Optional[str] = None) -> Optional[Path]:
    """Read ``KEY=value`` lines from a ``.env`` beside the monitor (its folder,
    the folder above, or the current one), without replacing anything already
    set. The app is often started by the system, with no shell to set the key.
    ``only`` reads that one variable and leaves the rest of the file alone.
    """
    for candidate in (folder / ".env", folder.parent / ".env", Path.cwd() / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.replace("export ", "", 1).strip()
            value = value.strip().strip("'\"")
            if name and name not in os.environ and only in (None, name):
                os.environ[name] = value
        return candidate
    return None


def _asset(name: str) -> bytes:
    return resources.files("amygda_ops_risk_score.app").joinpath(name).read_bytes()


# The light and dark switch for the page shown before there is a dashboard.
# It uses the same saved choice as the dashboard's own button.
_THEME_HEAD = (
    "<script>try{var t=localStorage.getItem('amygda-theme');"
    "if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}"
    "catch(e){}</script>"
)
_THEME_BUTTON = """<script>(function(){
var r=document.documentElement,b=document.getElementById('theme-toggle');
function dark(){
  if(r.dataset.theme)return r.dataset.theme==='dark';
  return matchMedia('(prefers-color-scheme: dark)').matches}
function draw(){b.textContent=dark()?'\\u2600 Light mode':'\\u263e Dark mode'}
b.onclick=function(){
  var n=dark()?'light':'dark';r.dataset.theme=n;
  try{localStorage.setItem('amygda-theme',n)}catch(e){}
  draw()};
draw()})()</script>"""


def _shell(title: str, message: str) -> str:
    """A page for when there is no dashboard to show yet, in the same style."""
    template = (
        resources.files("amygda_ops_risk_score.monitor")
        .joinpath("template.html")
        .read_text()
    )
    style = re.search(r"<style>.*?</style>", template, re.S).group(0)
    esc = lambda s: (  # noqa: E731
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title>{style}{_THEME_HEAD}</head><body><main>"
        f'<div class="brand"><div class="titlebar"><h1>{esc(title)}</h1>'
        '<button class="btn" id="theme-toggle" type="button"></button></div></div>'
        f'<p class="lede">{esc(message)}</p>'
        f"</main>{_THEME_BUTTON}</body></html>"
    )


class FleetApp:
    """One monitor folder as an app: its page, runs, inbox and schedule.

    Args:
        folder: The monitor folder.
        open_monitor: Returns a ``Monitor`` for the folder (tests pass one
            with their own client). Default: ``Monitor(folder)``.
    """

    def __init__(self, folder, open_monitor: Optional[Callable[[], Monitor]] = None):
        self.path = Path(folder).expanduser().resolve()
        self._open = open_monitor or (lambda: Monitor(self.path))
        mon = self._open()  # fails early if this isn't a monitor folder
        self.fleet_name = mon.config["fleet_name"]
        self.title = mon.title
        self.key_env = mon.config.get("api_key_env", DEFAULT_KEY_ENV)
        self._needs_key = open_monitor is None
        self._lock = threading.Lock()
        self._running: Optional[Dict[str, Any]] = None
        self._last: Optional[Dict[str, Any]] = None
        self._note: Optional[str] = None
        self._page_lock = threading.Lock()
        self._page_key: Optional[str] = None
        self._stop = threading.Event()
        saved = self._read_state().get("last_check")
        # A check missed while the app was off is made when it starts again.
        self._last_check = datetime.fromisoformat(saved) if saved else datetime.now()

    # ------------------------------------------------------------------ #
    # State
    # ------------------------------------------------------------------ #

    def _read_state(self) -> Dict[str, Any]:
        return self._open().store.state("app")

    def _set_last_check(self, when: datetime) -> None:
        self._last_check = when
        self._open().store.save_state(
            {"last_check": when.isoformat(timespec="seconds")}, "app"
        )

    def _spec(self) -> Dict[str, Any]:
        return self._open().spec()

    def _version(self) -> str:
        """Changes whenever the page would: new scores, a run, a new layout."""
        parts = [self._open().store.version()]
        for rel in (app_spec.SPEC_FILE, "monitor.json"):
            p = self.path / rel
            parts.append(str(p.stat().st_mtime_ns) if p.exists() else "-")
        return ".".join(parts)

    def _last_run(self) -> Optional[Dict[str, Any]]:
        r = self._open().store.last_run()
        if not r:
            return None
        keys = ("run_id", "status", "trigger", "started_at", "finished_at")
        return {k: r.get(k) for k in keys + ("reason", "rows_new")}

    def key_present(self) -> bool:
        return not self._needs_key or bool(os.environ.get(self.key_env))

    def state(self) -> Dict[str, Any]:
        mon = self._open()
        schedule, problem = None, None
        try:
            schedule = mon.spec()["schedule"]
        except app_spec.SpecError as exc:
            problem = f"{app_spec.SPEC_FILE} has a problem: {exc}"
        nxt = next_run(schedule, max(self._last_check, datetime.now()))
        with self._lock:
            running, last, note = self._running, self._last, self._note
        self.title = mon.title  # a new layout can rename the page
        return {
            "fleet_name": self.fleet_name,
            "title": self.title,
            "folder": str(self.path),
            "running": running,
            "last_action": last,
            "note": note,
            "problem": problem,
            "last_run": self._last_run(),
            "has_scores": mon.store.has_scores(),
            "storage": mon.store.kind,
            "inbox": [
                {"name": p.name, "size": p.stat().st_size} for p in mon.inbox_files()
            ],
            "schedule": schedule,
            "schedule_text": describe(schedule),
            "next_run": nxt.isoformat(timespec="seconds") if nxt else None,
            "key_present": self.key_present(),
            "key_env": self.key_env,
            "open_alerts": len(mon.alerts("open")),
            "version": self._version(),
            "file_types": list(INPUT_TYPES),
        }

    # ------------------------------------------------------------------ #
    # Page
    # ------------------------------------------------------------------ #

    def page(self) -> str:
        """The dashboard with the app's controls added, rebuilt when stale."""
        extra = '<link rel="stylesheet" href="/app.css"><script src="/app.js"></script>'
        out = self.path / "dashboard" / "app.html"
        with self._page_lock:
            if not self._open().store.has_scores():
                html = _shell(
                    self._open().title,
                    "Everything is set up and waiting for data. Add a file of "
                    "logs and press Run now, or leave files in the inbox for "
                    "the next scheduled check. The page fills in after the "
                    "first run.",
                )
            else:
                key = self._version()
                try:
                    if key != self._page_key or not out.exists():
                        failures = None
                        if (self.path / "failures.csv").is_file():
                            import pandas as pd

                            failures = pd.read_csv(self.path / "failures.csv")
                        self._open().dashboard(output=out, failures=failures)
                        self._page_key = key
                    html = out.read_text()
                except Exception as exc:  # a bad spec must not take the app down
                    html = _shell(
                        self.title,
                        f"The dashboard could not be built: {exc}",
                    )
        # The page draws its alert settings as a form when it is in the app.
        html = html.replace("<head>", "<head><script>window.AMYGDA_APP=1</script>", 1)
        return html.replace("</body>", extra + "</body>")

    # ------------------------------------------------------------------ #
    # Runs
    # ------------------------------------------------------------------ #

    def start_run(self, trigger: str = "manual") -> Dict[str, Any]:
        """Start a run on the inbox in the background. One run at a time."""
        if not self._open().inbox_files():
            raise AppError("There are no files waiting. Add a file first.", 409)
        if not self.key_present():
            raise AppError(
                f"No API key: set {self.key_env} (for example in a .env file "
                "beside the monitor folder) and start the app again.",
                409,
            )
        with self._lock:
            if self._running:
                raise AppError("A run is already in progress.", 409)
            self._running = {
                "trigger": trigger,
                "started_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._note = None
        threading.Thread(target=self._do_run, args=(trigger,), daemon=True).start()
        return self._running

    def _do_run(self, trigger: str) -> None:
        last: Dict[str, Any]
        try:
            result = self._open().run(None, trigger=trigger)
            r = result.record
            if result.status == "ok":
                text = (
                    f"Scored {r.get('rows_new', 0):,} new logs for "
                    f"{r.get('assets_in_batch', 0)} assets."
                )
            else:
                text = "Nothing new: every row had been scored already."
            last = {"status": result.status, "message": text}
            if result.warnings:
                last["warnings"] = list(result.warnings)
        except BaseException as exc:  # noqa: BLE001 - recorded by the monitor
            last = {
                "status": "failed",
                "message": getattr(exc, "monitor_reason", None) or str(exc),
            }
        last["trigger"] = trigger
        last["finished_at"] = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._last = last
            self._running = None

    def wait(self, timeout: float = 600.0) -> None:
        """Block until no run is in progress (for scripts and tests)."""
        end = datetime.now().timestamp() + timeout
        while self._running and datetime.now().timestamp() < end:
            self._stop.wait(0.05)

    # ------------------------------------------------------------------ #
    # Inbox
    # ------------------------------------------------------------------ #

    def _inbox_path(self, name: str) -> Path:
        clean = Path(unquote(name)).name.strip()
        if not clean or clean.startswith("."):
            raise AppError("That file name can't be used.")
        if not clean.lower().endswith(INPUT_TYPES):
            raise AppError(
                f'"{clean}" can\'t be read. Use a {", ".join(INPUT_TYPES)} file.'
            )
        return self.path / "inbox" / clean

    def add_file(self, name: str, stream, length: int) -> Dict[str, Any]:
        """Save an uploaded file into the inbox. A waiting file with the same
        name is replaced."""
        dest = self._inbox_path(name)
        if length <= 0:
            raise AppError("The file is empty.")
        if length > MAX_UPLOAD_BYTES:
            raise AppError("The file is over 1 GB. Split it into smaller files.", 413)
        dest.parent.mkdir(exist_ok=True)
        replaced = dest.exists()
        part = dest.with_name(dest.name + ".part")
        left = length
        with open(part, "wb") as fh:
            while left > 0:
                chunk = stream.read(min(left, 1024 * 1024))
                if not chunk:
                    break
                fh.write(chunk)
                left -= len(chunk)
        if left:
            part.unlink(missing_ok=True)
            raise AppError("The upload stopped before the whole file arrived.")
        part.replace(dest)
        return {"name": dest.name, "size": length, "replaced": replaced}

    def remove_file(self, name: str) -> None:
        dest = self._inbox_path(name)
        if not dest.is_file():
            raise AppError("That file is no longer waiting.", 404)
        dest.unlink()

    # ------------------------------------------------------------------ #
    # Schedule
    # ------------------------------------------------------------------ #

    def set_schedule(self, schedule: Optional[Dict[str, Any]]) -> Optional[Dict]:
        """Save the schedule in ``app.json``. It counts from now, so a time
        earlier today doesn't fire at once."""
        mon = self._open()
        spec = mon.spec()
        spec["schedule"] = app_spec.validate_schedule(schedule)
        app_spec.save_spec(spec, self.path / app_spec.SPEC_FILE)
        self._set_last_check(datetime.now())
        return spec["schedule"]

    def set_alert_rules(self, body: Any) -> list:
        """Save what raises an alert in ``app.json``. The rules are checked
        first; they apply from the next run."""
        from amygda_ops_risk_score.monitor.alerts import validate_rules

        rules = body.get("rules") if isinstance(body, dict) else None
        if not isinstance(rules, list):
            raise AppError('Send {"rules": [...]}.')
        mon = self._open()
        spec = mon.spec()
        spec["alerts"] = validate_rules({"rules": rules}, error=AppError)
        app_spec.save_spec(spec, self.path / app_spec.SPEC_FILE)
        return spec["alerts"]["rules"]

    def set_layout(self, body: Any) -> Dict[str, Any]:
        """Save which tabs and panels the page shows, and optionally the
        figures at the top, in ``app.json``. Everything else in the layout
        (look, alert rules, schedule) is kept. The layout is checked first."""
        if not isinstance(body, dict) or not isinstance(body.get("tabs"), list):
            raise AppError('Send {"tabs": [...]}.')
        spec = self._open().spec()
        spec["tabs"] = body["tabs"]
        if isinstance(body.get("tiles"), list):
            spec["header"] = dict(spec["header"], tiles=body["tiles"])
        spec["default_tab"] = None  # the first tab opens first
        saved = app_spec.validate_spec(spec)
        app_spec.save_spec(saved, self.path / app_spec.SPEC_FILE)
        return {"tabs": [t["title"] for t in saved["tabs"]]}

    def acknowledge(self, which: str) -> int:
        """Acknowledge one alert by id, or every open one with "all"."""
        return self._open().acknowledge_alerts(None if which == "all" else which)

    def pause(self, paused: bool) -> Optional[Dict]:
        schedule = self._spec()["schedule"]
        if not schedule:
            raise AppError("There is no schedule to pause. Set one first.", 409)
        return self.set_schedule(dict(schedule, paused=paused))

    def tick(self, now: Optional[datetime] = None) -> Optional[str]:
        """One scheduler check. Returns what it did: "run", "nothing", or None
        when no run was due."""
        now = now or datetime.now()
        try:
            schedule = self._spec()["schedule"]
        except app_spec.SpecError:
            return None
        due = next_run(schedule, self._last_check)
        if due is None:
            # No schedule, or paused: time that passes now is never caught up.
            self._last_check = now
            return None
        if due > now:
            return None
        self._set_last_check(now)
        when = f"{due:%b} {due.day}, {due:%H:%M}"
        try:
            self.start_run("scheduled")
            return "run"
        except AppError as exc:
            with self._lock:
                if "no files" in str(exc):
                    self._note = f"Scheduled check for {when}: no new files."
                else:
                    self._note = f"Scheduled run for {when} did not start: {exc}"
            return "nothing"

    def _scheduler(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - never let the scheduler die
                pass

    # ------------------------------------------------------------------ #
    # Serving
    # ------------------------------------------------------------------ #

    def server(self, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
        app = self

        class Handler(_Handler):
            fleet_app = app

        try:
            httpd = ThreadingHTTPServer((HOST, port), Handler)
        except OSError as exc:
            raise MonitorError(
                f"Port {port} can't be used ({exc.strerror or exc}). "
                "Pass another with --port."
            )
        httpd.daemon_threads = True
        return httpd

    def start_scheduler(self) -> None:
        threading.Thread(target=self._scheduler, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


_STATIC = {
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}


class _Handler(BaseHTTPRequestHandler):
    fleet_app: FleetApp
    server_version = "AmygdaFleetApp"

    def log_message(self, *args) -> None:  # keep the terminal quiet
        pass

    # -- helpers --------------------------------------------------------- #

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj, default=str).encode(), "application/json")

    def _local(self) -> bool:
        """Only answer requests addressed to this machine by name. This stops
        another site reaching the app through a hostname it controls."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def _guard(self) -> bool:
        if not self._local():
            self._json({"error": "This app only answers on this machine."}, 403)
            return False
        if self.command in ("GET", "HEAD"):
            return True
        origin = self.headers.get("Origin")
        if self.headers.get(HEADER) != "1" or (
            origin and origin.split("//")[-1] != self.headers.get("Host")
        ):
            self._json({"error": "Requests must come from the app's own page."}, 403)
            return False
        return True

    def _body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return None
        if length > 64 * 1024:
            raise AppError("The request is too large.", 413)
        try:
            return json.loads(self.rfile.read(length))
        except ValueError:
            raise AppError("The request is not valid JSON.")

    def _handle(self, fn: Callable[[], Any]) -> None:
        try:
            self._json(fn())
        except AppError as exc:
            self._json({"error": str(exc)}, exc.status)
        except (MonitorError, app_spec.SpecError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # -- routes ---------------------------------------------------------- #

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard():
            return
        path = self.path.split("?", 1)[0]
        app = self.fleet_app
        if path == "/":
            self._send(200, app.page().encode(), "text/html; charset=utf-8")
        elif path in _STATIC:
            name, kind = _STATIC[path]
            self._send(200, _asset(name), kind)
        elif path == "/api/state":
            self._handle(app.state)
        else:
            self._json({"error": "Not found."}, 404)

    do_HEAD = do_GET  # noqa: N815

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard():
            return
        path = self.path.split("?", 1)[0]
        app = self.fleet_app
        if path == "/api/run":
            self._handle(lambda: {"running": app.start_run("manual")})
        elif path == "/api/schedule":
            self._handle(lambda: {"schedule": app.set_schedule(self._body())})
        elif path == "/api/schedule/pause":
            self._handle(lambda: {"schedule": app.pause(True)})
        elif path == "/api/schedule/resume":
            self._handle(lambda: {"schedule": app.pause(False)})
        elif path == "/api/layout":
            self._handle(lambda: app.set_layout(self._body()))
        elif path == "/api/alerts/rules":
            self._handle(lambda: {"rules": app.set_alert_rules(self._body())})
        elif path.startswith("/api/alerts/") and path.endswith("/ack"):
            which = unquote(path.removeprefix("/api/alerts/").removesuffix("/ack"))
            self._handle(lambda: {"acknowledged": app.acknowledge(which)})
        else:
            self._json({"error": "Not found."}, 404)

    def do_PUT(self) -> None:  # noqa: N802
        if not self._guard():
            return
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/inbox/"):
            self._json({"error": "Not found."}, 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        name = path.removeprefix("/api/inbox/")
        self._handle(lambda: self.fleet_app.add_file(name, self.rfile, length))

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._guard():
            return
        path = self.path.split("?", 1)[0]
        if not path.startswith("/api/inbox/"):
            self._json({"error": "Not found."}, 404)
            return
        name = path.removeprefix("/api/inbox/")
        self._handle(lambda: self.fleet_app.remove_file(name) or {"removed": True})


def serve(folder, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    """Run the app for a monitor folder until interrupted (Ctrl+C)."""
    from amygda_ops_risk_score.app.service import note_running

    folder = Path(folder).expanduser().resolve()
    load_env(folder)
    app = FleetApp(folder)
    httpd = app.server(port)
    app.start_scheduler()
    url = f"http://{HOST}:{httpd.server_address[1]}/"
    pid_file = note_running(folder, httpd.server_address[1])
    print(f"{app.title}: {url}")
    print(f"  schedule: {describe(app._spec()['schedule'])}")
    if not app.key_present():
        print(f"  ! No API key in {app.key_env}: runs will not start until it is set.")
    print("  Press Ctrl+C to stop. The schedule only runs while this is running.")
    if open_browser:
        import webbrowser

        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        app.stop()
        httpd.server_close()
        pid_file.unlink(missing_ok=True)
