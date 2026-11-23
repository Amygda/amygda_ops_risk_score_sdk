"""Keep the fleet app running: one entry with the operating system.

The app's schedule only fires while the app is running. This registers the
app with the system's own service manager, so it starts when the user logs
in and is restarted if it stops:

- macOS: a launchd agent in ``~/Library/LaunchAgents``
- Linux: a systemd user service in ``~/.config/systemd/user``
- Windows: a Task Scheduler task that starts at log-on

``entry`` only describes what would be installed; ``install`` and ``remove``
do it. The API key is not part of the entry: the app reads it from a ``.env``
file beside the monitor. The entry's name and port are kept in the monitor's
``monitor.json`` (``service``), so later commands find it again.

``retire`` takes a whole monitor away: the entry, a running app, the
deployment and the folder.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional
from urllib.request import urlopen
from xml.sax.saxutils import escape

from amygda_ops_risk_score.monitor.project import BUNDLE
from amygda_ops_risk_score.monitor.project import CONFIG
from amygda_ops_risk_score.monitor.project import Monitor
from amygda_ops_risk_score.monitor.project import MonitorError

DEFAULT_PORT = 8050
LOG_FILE = "app.log"
PID_FILE = "app.pid"
SYSTEMS = ("Darwin", "Linux", "Windows")


def _slug(folder: Path) -> str:
    """A short name for the folder that differs for every monitor."""
    name = re.sub(r"[^a-z0-9]+", "-", folder.name.lower()).strip("-")[:30] or "monitor"
    return f"{name}-{hashlib.sha1(str(folder).encode()).hexdigest()[:6]}"


def _named(name: str) -> str:
    """A name the user chose, in the form every system accepts."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:40]
    if not slug:
        raise MonitorError(
            f'"{name}" can\'t be used as a name. Use letters and digits, for '
            'example "conveyor-fleet".'
        )
    return slug


def saved(folder) -> Dict[str, Any]:
    """The name and port this monitor's entry was installed with, if any."""
    try:
        config = json.loads((Path(folder).expanduser() / CONFIG).read_text())
    except (OSError, ValueError):
        return {}
    return config.get("service") or {}


def _save(folder: str, service: Optional[Dict[str, Any]]) -> None:
    path = Path(folder) / CONFIG
    config = json.loads(path.read_text())
    if service:
        config["service"] = service
    else:
        config.pop("service", None)
    path.write_text(json.dumps(config, indent=1, default=str))


def _command(folder: Path, port: int, python: str) -> List[str]:
    module = "amygda_ops_risk_score.monitor.cli"
    return [python, "-u", "-m", module, "app", str(folder), "--port", str(port)] + [
        "--no-open"
    ]


def _quote_windows(arg: str) -> str:
    return f'"{arg}"' if re.search(r"\s", arg) else arg


def entry(
    folder,
    port: Optional[int] = None,
    system: Optional[str] = None,
    python: Optional[str] = None,
    home: Optional[Path] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """What keeping this monitor's app running takes on this system.

    ``name`` is the user's own name for the entry (letters and digits). Left
    out, it is the name the entry was installed with, or else one made from
    the folder. ``port`` likewise: the installed one, or else 8050.

    Returns ``system``, ``name``, ``kind`` (in plain words), ``path`` and
    ``text`` (the file to write; None on Windows), ``install`` and ``remove``
    (commands, as argument lists), ``url`` and ``log``. Nothing is changed.
    """
    folder = Path(folder).expanduser().resolve()
    system = system or platform.system()
    if system not in SYSTEMS:
        raise MonitorError(
            f"Keeping the app running isn't set up for {system}. Start it with "
            f"`amygda-risk app {folder}` from whatever starts programs there."
        )
    home = Path(home) if home else Path.home()
    kept = saved(folder)
    port = port or kept.get("port") or DEFAULT_PORT
    name = name or kept.get("name")
    slug = _named(name) if name else _slug(folder)
    command = _command(folder, port, python or sys.executable)
    log = folder / LOG_FILE
    out: Dict[str, Any] = {
        "system": system,
        "slug": slug,
        "chosen": bool(name),
        "folder": str(folder),
        "port": port,
        "url": f"http://127.0.0.1:{port}/",
        "log": str(log),
        "command": command,
    }
    if system == "Darwin":
        label = f"io.amygda.fleet-app.{slug}"
        path = home / "Library" / "LaunchAgents" / f"{label}.plist"
        args = "\n".join(f"    <string>{escape(a)}</string>" for a in command)
        text = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>WorkingDirectory</key><string>{escape(str(folder))}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>{escape(str(log))}</string>
  <key>StandardErrorPath</key><string>{escape(str(log))}</string>
</dict>
</plist>
"""
        domain = f"gui/{os.getuid() if hasattr(os, 'getuid') else 0}"
        out.update(
            name=label,
            kind="a launchd agent (starts when you log in, restarted if it stops)",
            path=str(path),
            text=text,
            install=[["launchctl", "bootstrap", domain, str(path)]],
            remove=[["launchctl", "bootout", f"{domain}/{label}"]],
        )
    elif system == "Linux":
        unit = f"amygda-fleet-app-{slug}.service"
        path = home / ".config" / "systemd" / "user" / unit
        run = " ".join(f'"{a}"' if re.search(r"\s", a) else a for a in command)
        text = f"""[Unit]
Description=Amygda fleet app ({folder.name})

[Service]
ExecStart={run}
WorkingDirectory={folder}
Restart=always
RestartSec=30
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""
        out.update(
            name=unit,
            kind="a systemd user service (starts when you log in, restarted if "
            "it stops)",
            path=str(path),
            text=text,
            install=[
                ["systemctl", "--user", "daemon-reload"],
                ["systemctl", "--user", "enable", "--now", unit],
            ],
            remove=[
                ["systemctl", "--user", "disable", "--now", unit],
            ],
        )
    else:
        task = f"Amygda fleet app {slug}"
        exe = Path(command[0])
        windowless = exe.with_name("pythonw.exe")
        command = [str(windowless if windowless.exists() else exe)] + command[1:]
        run = " ".join(_quote_windows(a) for a in command)
        out.update(
            name=task,
            kind="a Task Scheduler task (starts when you log on)",
            path=None,
            text=None,
            command=command,
            install=[
                ["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", task]
                + ["/TR", run],
                ["schtasks", "/Run", "/TN", task],
            ],
            remove=[
                ["schtasks", "/End", "/TN", task],
                ["schtasks", "/Delete", "/F", "/TN", task],
            ],
        )
    return out


def describe(e: Dict[str, Any], installed: Optional[bool] = None) -> str:
    """An entry in plain words, with the exact file or command."""
    lines = [f"Keeps the app for {e['folder']} running at {e['url']}"]
    lines.append(f"  as {e['kind']}, named {e['name']}")
    if installed is not None:
        lines.append(f"  installed: {'yes' if installed else 'no'}")
    if e["path"]:
        lines.append(f"  file: {e['path']}")
    lines.append(f"  runs: {' '.join(e['command'])}")
    lines.append(f"  output goes to: {e['log']}")
    if e["text"]:
        lines += ["", e["text"].rstrip()]
    return "\n".join(lines)


def _query(e: Dict[str, Any]) -> List[str]:
    if e["system"] == "Darwin":
        return ["launchctl", "print", e["remove"][0][2]]
    if e["system"] == "Linux":
        return ["systemctl", "--user", "is-enabled", e["name"]]
    return ["schtasks", "/Query", "/TN", e["name"]]


Runner = Callable[..., Any]


def _run(cmd: List[str], run: Runner):
    try:
        return run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise MonitorError(
            f"`{cmd[0]}` was not found, so the entry can't be managed from here."
        ) from None


def is_installed(e: Dict[str, Any], run: Runner = subprocess.run) -> bool:
    if e["path"] and not Path(e["path"]).exists():
        return False
    try:
        return _run(_query(e), run).returncode == 0
    except MonitorError:
        return False


def _taken_by(e: Dict[str, Any]) -> Optional[str]:
    """Another monitor's entry that already has this name, if there is one."""
    if not e["path"] or not Path(e["path"]).is_file():
        return None
    text = Path(e["path"]).read_text(errors="replace")
    return None if e["folder"] in text else e["path"]


def install(
    folder,
    port: Optional[int] = None,
    run: Runner = subprocess.run,
    name: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Register the app with the system and start it. Returns the entry.

    Installing again replaces the earlier entry (a new port or name, say)."""
    old = entry(folder, **kwargs)  # as it was installed, if it was
    e = entry(folder, port, name=name, **kwargs)
    Monitor(e["folder"])  # not a monitor folder: say so before touching anything
    if _taken_by(e):
        raise MonitorError(
            f'The name "{e["slug"]}" is already used by another monitor\'s app '
            f"({_taken_by(e)}). Choose another name."
        )
    for cmd in old["remove"]:  # replace an earlier entry; fine if there is none
        _run(cmd, run)
    if old["path"] and old["path"] != e["path"]:
        Path(old["path"]).unlink(missing_ok=True)
    if e["path"]:
        path = Path(e["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(e["text"])
    for cmd in e["install"]:
        done = _run(cmd, run)
        if done.returncode != 0:
            why = (done.stderr or done.stdout or "").strip()[:500]
            raise MonitorError(
                f"The entry could not be installed (`{' '.join(cmd[:3])} ...` "
                f"said: {why or 'nothing'})."
            )
    _save(e["folder"], {"name": e["slug"] if e["chosen"] else None, "port": e["port"]})
    return e


def remove(folder, run: Runner = subprocess.run, **kwargs) -> Dict[str, Any]:
    """Stop the app and take the entry out. Returns the entry."""
    e = entry(folder, **kwargs)
    for cmd in e["remove"]:
        _run(cmd, run)
    if e["path"]:
        Path(e["path"]).unlink(missing_ok=True)
    if (Path(e["folder"]) / CONFIG).is_file():
        _save(e["folder"], None)
    return e


# ---------------------------------------------------------------------------
# An app started by hand, and taking a whole monitor away
# ---------------------------------------------------------------------------


def note_running(folder: Path, port: int) -> Path:
    """Called by the app when it starts: leave its process id and port in the
    folder, so it can be found and stopped."""
    path = Path(folder) / PID_FILE
    path.write_text(json.dumps({"pid": os.getpid(), "port": port}))
    return path


def running_app(folder) -> Optional[Dict[str, Any]]:
    """The app serving this folder right now (``pid``, ``port``), or None.
    The app is asked which folder it serves, so a reused process id is never
    mistaken for it."""
    folder = Path(folder).expanduser().resolve()
    try:
        info = json.loads((folder / PID_FILE).read_text())
        url = f"http://127.0.0.1:{int(info['port'])}/api/state"
        with urlopen(url, timeout=3) as response:  # noqa: S310 - this machine
            state = json.loads(response.read())
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return info if state.get("folder") == str(folder) else None


def stop_app(folder) -> bool:
    """Stop an app that was started by hand for this folder. Returns whether
    one was running."""
    info = running_app(folder)
    if not info:
        return False
    try:
        os.kill(int(info["pid"]), signal.SIGTERM)
    except OSError:
        return False
    (Path(folder).expanduser().resolve() / PID_FILE).unlink(missing_ok=True)
    return True


def retirement(folder, run: Runner = subprocess.run, **kwargs) -> Dict[str, Any]:
    """What ``retire`` would take away for this monitor. Changes nothing."""
    mon = Monitor(folder)
    e = entry(mon.path, **kwargs)
    return {
        "folder": str(mon.path),
        "title": mon.title,
        "entry": e["name"] if is_installed(e, run) else None,
        "app_running": bool(running_app(mon.path)),
        "deployment_id": mon.deployment["deployment_id"],
        "deployment_name": mon.deployment.get("name"),
        # A deployment this monitor made is its own to delete; one it was
        # attached to (--deployment-id) may serve other monitors.
        "deployment_is_ours": (mon.path / BUNDLE).is_file(),
        "runs": len(mon.runs()),
        "periods": len(mon.scores),
    }


def describe_retirement(plan: Dict[str, Any], keep_deployment: bool = False) -> str:
    """A retirement plan in plain words."""
    lines = [f'Removing "{plan["title"]}" would:']
    if plan["entry"]:
        lines.append(
            f"  - stop the app and remove its start-up entry ({plan['entry']})"
        )
    elif plan["app_running"]:
        lines.append("  - stop the app, which is running now")
    dep = f"{plan['deployment_name']} ({plan['deployment_id']})"
    if keep_deployment:
        lines.append(f"  - keep the deployed model {dep}")
    elif plan["deployment_is_ours"]:
        lines.append(f"  - delete the deployed model {dep} from the Amygda API")
    else:
        lines.append(
            f"  - leave the deployed model {dep}: this monitor did not create it"
        )
    lines.append(
        f"  - delete the folder {plan['folder']}, with its {plan['periods']:,} "
        f"scores, {plan['runs']} run records, alerts and waiting files"
    )
    lines.append("None of this can be undone.")
    return "\n".join(lines)


def retire(
    folder,
    keep_deployment: bool = False,
    run: Runner = subprocess.run,
    monitor: Optional[Monitor] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Take a monitor away for good: stop its app, remove its start-up entry,
    delete its deployment and delete its folder. Returns what was done.

    The deployment is deleted first of the things that can fail, so a missing
    API key or an unreachable API leaves the folder as it was."""
    from amygda_ops_risk_score.exceptions import APIError

    mon = monitor or Monitor(folder)
    plan = retirement(mon.path, run=run, **kwargs)
    delete = plan["deployment_is_ours"] and not keep_deployment
    if delete:
        client, key = mon._client_and_key()  # no key: stop before anything changes
    remove(mon.path, run=run, **kwargs)
    stopped = stop_app(mon.path)
    deleted = False
    if delete:
        try:
            client.delete_deployment(key, plan["deployment_id"])
            deleted = True
        except APIError as exc:
            if exc.status_code != 404:  # 404: it was gone already
                raise MonitorError(
                    "The app is stopped, but the deployed model could not be "
                    f"deleted, so the folder was kept ({exc}). Try again, or pass "
                    "--keep-deployment."
                ) from None
    shutil.rmtree(mon.path)
    return dict(
        plan, deployment_deleted=deleted, app_stopped=stopped or bool(plan["entry"])
    )
