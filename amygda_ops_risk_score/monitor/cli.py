"""``amygda-risk``: keep scoring new data with a deployed model.

    amygda-risk panels                                     # what the app can show
    amygda-risk design --spec my_app.json --model complete_model_x.zip --open
                                                           # see a layout first
    amygda-risk init fleet_monitor --model complete_model_x.zip --name fleet-v1
    amygda-risk design fleet_monitor --spec my_app.json    # choose what it shows
    amygda-risk app fleet_monitor                          # the live app, in a browser
    amygda-risk service fleet_monitor --install            # keep the app running
    amygda-risk run fleet_monitor --input new_logs.csv     # or drop files in inbox/
    amygda-risk score fleet_monitor --input other.csv      # one-off, changes nothing
    amygda-risk dashboard fleet_monitor
    amygda-risk status fleet_monitor
    amygda-risk alerts fleet_monitor                       # open alerts; --ack to close
    amygda-risk storage fleet_monitor --to sqlite          # files or one database file
    amygda-risk remove fleet_monitor                       # take a monitor away

The API key is read from AMYGDA_API_KEY (or --api-key-env), from the
environment or a .env file beside the monitor folder. It is never saved.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from amygda_ops_risk_score.monitor.project import CONFIG
from amygda_ops_risk_score.monitor.project import DEFAULT_KEY_ENV, Monitor, MonitorError
from amygda_ops_risk_score.monitor.spec import catalogue
from amygda_ops_risk_score.monitor.spec import describe_catalogue
from amygda_ops_risk_score.monitor.spec import SpecError


def _print_run(result) -> None:
    r = result.record
    if result.status == "failed":
        print(f"Run {result.run_id} FAILED: {r.get('reason')}")
        return
    if result.status == "no_new_data":
        print(
            f"Run {result.run_id}: no new data "
            f"({r.get('rows_read', 0):,} rows read, {r.get('rows_already_seen', 0):,} "
            "already seen)."
        )
    else:
        span = r.get("new_period") or {}
        data = f" from {span['start']} to {span['end']}" if span else ""
        print(
            f"Run {result.run_id}: {r['rows_new']:,} new logs{data}, "
            f"{r['periods_upserted']:,} periods scored for {r['assets_in_batch']} "
            "assets "
            f"({r.get('score_calls')} call(s)). Provisional periods: "
            f"{r['provisional_periods']}."
        )
        hot = [
            c for c in r.get("changes", []) if c["band_of_highest"] in ("watch", "high")
        ]
        for c in hot[:10]:
            print(
                f"  {c['band_of_highest'].upper():5} {c['asset_id']}: highest "
                f"{c['highest_this_run']:.1f} at {c['highest_this_run_at']}"
            )
        if len(hot) > 10:
            print(f"  ... and {len(hot) - 10} more at watch or high")
    for w in result.warnings:
        print(f"  ! {w}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="amygda-risk",
        description="Keep scoring new data with a deployed Amygda risk model.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a monitor folder and deploy a model")
    p.add_argument("folder")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--model", help="complete_model_<id>.zip (or a bundle) to deploy")
    src.add_argument("--deployment-id", help="use an existing deployment instead")
    p.add_argument("--name", help="deployment name (needed with --model)")
    # No longer needed; kept so existing commands still work.
    p.add_argument("--accept-storage", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--fleet-name", help='shown on the dashboard, e.g. "Conveyor fleet"')
    p.add_argument(
        "--watch",
        type=float,
        help="watch band cut-off (default: from the model's training scores)",
    )
    p.add_argument("--high", type=float, help="high band cut-off")
    p.add_argument(
        "--history", help="earlier logs to use as history (e.g. the training file)"
    )
    p.add_argument(
        "--date-format", help="timestamp format of your files (default: the model's)"
    )
    p.add_argument("--api-url", help="API to use (default: hosted)")
    p.add_argument(
        "--storage",
        choices=("files", "sqlite"),
        default="files",
        help="where scores, runs and alerts are kept: files (default) or "
        "sqlite (one database file, monitor.db)",
    )
    p.add_argument(
        "--api-key-env",
        default=DEFAULT_KEY_ENV,
        help=f"environment variable holding the API key (default {DEFAULT_KEY_ENV})",
    )

    c = sub.add_parser("panels", help="list the panels and tiles a dashboard can show")
    c.add_argument("--json", action="store_true", help="print the catalogue as JSON")
    c.add_argument(
        "--menu",
        action="store_true",
        help="print the panels as a pick list, group by group, in plain words",
    )

    g = sub.add_parser(
        "design",
        help="choose what the app shows and preview it; with --model, before "
        "anything is deployed or scored",
    )
    g.add_argument("folder", nargs="?", default=".")
    how = g.add_mutually_exclusive_group()
    how.add_argument("--spec", help="JSON file saying which tabs, panels and tiles")
    how.add_argument(
        "--reset", action="store_true", help="go back to the standard layout"
    )
    g.add_argument(
        "--model",
        help="complete_model_<id>.zip: preview the layout with the scores saved "
        "in it. Works before a monitor exists, and for one with no runs yet",
    )
    g.add_argument("--output", help="where to write a --model preview (.html)")
    g.add_argument("--watch", type=float, help="watch level for a --model preview")
    g.add_argument("--high", type=float, help="high level for a --model preview")
    g.add_argument(
        "--open", action="store_true", help="open the preview in your browser"
    )

    sv = sub.add_parser(
        "service",
        help="keep the app running: show, install or remove the system entry",
    )
    sv.add_argument("folder", nargs="?", default=".")
    sv.add_argument("--port", type=int, help="default 8050")
    sv.add_argument(
        "--name",
        help="your own name for the entry (letters and digits), instead of one "
        "made from the folder",
    )
    do = sv.add_mutually_exclusive_group()
    do.add_argument("--install", action="store_true", help="install it and start")
    do.add_argument("--remove", action="store_true", help="stop the app and remove it")

    rm = sub.add_parser(
        "remove",
        help="take a monitor away: stop its app, delete its deployment and "
        "its folder (shows what it would do; --yes does it)",
    )
    rm.add_argument("folder")
    rm.add_argument("--yes", action="store_true", help="do it; this can't be undone")
    rm.add_argument(
        "--keep-deployment",
        action="store_true",
        help="leave the deployed model on the Amygda API",
    )

    st = sub.add_parser(
        "storage", help="show where a monitor keeps its data, or move it"
    )
    st.add_argument("folder", nargs="?", default=".")
    st.add_argument(
        "--to",
        choices=("files", "sqlite"),
        help="move scores, runs and alerts to this kind of storage",
    )

    al = sub.add_parser("alerts", help="list alerts, or acknowledge them")
    al.add_argument("folder", nargs="?", default=".")
    al.add_argument("--all", action="store_true", help="include closed alerts")
    al.add_argument(
        "--ack", metavar="ID", help='acknowledge one alert by id, or "all" open ones'
    )

    a = sub.add_parser(
        "app",
        help="open the monitor as a live app: run, add files, schedule",
    )
    a.add_argument("folder", nargs="?", default=".")
    a.add_argument("--port", type=int, default=8050, help="default 8050")
    a.add_argument("--no-open", action="store_true", help="don't open a browser window")

    for name, helptext in (
        ("run", "score new data and update the monitor"),
        ("score", "one-off: score a file without changing the monitor"),
        ("dashboard", "rebuild the dashboard"),
        ("status", "show the monitor's state"),
    ):
        q = sub.add_parser(name, help=helptext)
        q.add_argument("folder", nargs="?", default=".")
        if name in ("run", "score"):
            q.add_argument(
                "--input",
                nargs="+",
                required=(name == "score"),
                help="file(s) of new logs"
                + (" (default: everything in inbox/)" if name == "run" else ""),
            )
        if name == "run":
            q.add_argument(
                "--no-dashboard",
                action="store_true",
                help="skip rebuilding the dashboard",
            )
            q.add_argument(
                "--scheduled",
                action="store_true",
                help=argparse.SUPPRESS,  # schedules are the app's; kept for old jobs
            )
        if name == "score":
            q.add_argument(
                "--output", help="folder for scores.parquet and the dashboard"
            )
        if name == "dashboard":
            q.add_argument(
                "--failures",
                help="CSV of asset_id, failure_date to mark on the dashboard",
            )

    args = parser.parse_args(argv)
    try:
        if getattr(args, "folder", None) and args.command != "app":
            # The key can live in a .env beside the monitor, as the app reads it.
            from amygda_ops_risk_score.app.server import load_env

            folder = Path(args.folder).expanduser().resolve()
            key_env = getattr(args, "api_key_env", None)
            if not key_env:
                try:
                    config = json.loads((folder / CONFIG).read_text())
                    key_env = config.get("api_key_env")
                except (OSError, ValueError):
                    pass
            load_env(folder, only=key_env or DEFAULT_KEY_ENV)
        if args.command == "init":
            bands = None
            if args.watch is not None or args.high is not None:
                if args.watch is None or args.high is None:
                    raise MonitorError("Give both --watch and --high, or neither.")
                bands = {
                    "watch": args.watch,
                    "high": args.high,
                    "basis": "Set when the monitor was created.",
                }
            mon = Monitor.init(
                args.folder,
                model=args.model,
                deployment_id=args.deployment_id,
                name=args.name,
                api_url=args.api_url,
                api_key_env=args.api_key_env,
                fleet_name=args.fleet_name,
                bands=bands,
                history=args.history,
                date_format=args.date_format,
                storage_kind=args.storage,
            )
            d = mon.deployment
            print(f"Monitor ready: {mon.path} ({mon.store.kind} storage)")
            print(
                f"  deployment {d['deployment_id']} ({d['name']}), scores every "
                f"{d['feature_frequency']}, "
                f"history kept: {mon.keep_history}"
            )
            print(
                f"  new files need columns: {d['asset_id_column']}, "
                f"{d['timestamp_column']}, {d['log_column']}"
            )
            for w in mon.model_warnings():
                print(f"  ! {w}")
            print(
                f"Next: amygda-risk app {args.folder}  (then add files on the page, "
                f"or drop them in {args.folder}/inbox/)"
            )
        elif args.command == "app":
            from amygda_ops_risk_score.app import serve

            serve(args.folder, port=args.port, open_browser=not args.no_open)
        elif args.command == "service":
            from amygda_ops_risk_score.app import service

            Monitor(args.folder)
            if args.install:
                e = service.install(args.folder, args.port, name=args.name)
                print(f"Installed {e['name']}. The app is at {e['url']}")
                print(f"  It starts when you log in. Output goes to {e['log']}")
                print(f"  To remove it: amygda-risk service {args.folder} --remove")
            elif args.remove:
                e = service.remove(args.folder)
                print(f"Removed {e['name']}. The app is stopped.")
            else:
                e = service.entry(args.folder, args.port, name=args.name)
                print(service.describe(e, installed=service.is_installed(e)))
                print("\nNothing was changed. Add --install to install it.")
        elif args.command == "remove":
            from amygda_ops_risk_score.app import service

            plan = service.retirement(args.folder)
            print(service.describe_retirement(plan, args.keep_deployment))
            if not args.yes:
                print("\nNothing was changed. Add --yes to do it.")
            else:
                done = service.retire(args.folder, args.keep_deployment)
                print(f"\nRemoved {done['folder']}.")
        elif args.command == "storage":
            mon = Monitor(args.folder)
            if args.to:
                moved = mon.set_storage(args.to)
                print(
                    f"Moved to {args.to} storage: {moved['scores']} score rows, "
                    f"{moved['runs']} runs, {moved['alerts']} alerts."
                )
            where = "monitor.db" if mon.store.kind == "sqlite" else "files"
            print(f"{mon.path} keeps its scores, runs and alerts in {where}.")
        elif args.command == "alerts":
            mon = Monitor(args.folder)
            if args.ack:
                n = mon.acknowledge_alerts(None if args.ack == "all" else args.ack)
                print(f"Acknowledged {n} alert{'' if n == 1 else 's'}.")
                if len(mon.scores):
                    mon.dashboard()
            found = mon.alerts(None if args.all else "open")
            if not found:
                print("No alerts." if args.all else "No open alerts.")
            for a in found:
                state = "" if a["status"] == "open" else f" [{a['status']}]"
                print(
                    f"{a['id']:>5}  {a['severity'].upper():5}  "
                    f"{a['raised_at'][:16].replace('T', ' ')}  {a['message']}{state}"
                )
        elif args.command == "panels":
            if args.menu:
                from amygda_ops_risk_score.monitor.spec import describe_menu, menu

                print(json.dumps(menu(), indent=1) if args.json else describe_menu())
            else:
                print(
                    json.dumps(catalogue(), indent=1)
                    if args.json
                    else describe_catalogue()
                )
        elif args.command == "design":
            from amygda_ops_risk_score.monitor.project import preview_from_model
            from amygda_ops_risk_score.monitor.spec import default_spec, load_spec

            is_monitor = (Path(args.folder).expanduser() / CONFIG).is_file()
            mon = Monitor(args.folder) if is_monitor or not args.model else None
            if (args.watch is None) != (args.high is None):
                raise MonitorError("Give both --watch and --high, or neither.")
            if mon is not None:
                if args.spec or args.reset:
                    print(f"Saved: {mon.set_spec(args.spec)}")
                spec = mon.spec()
            else:
                # No monitor yet: only look at the layout. Nothing is saved.
                spec = load_spec(args.spec) if args.spec else default_spec()
            print(
                "Tabs: "
                + "; ".join(
                    f"{t['title']} ({', '.join(p['type'] for p in t['panels'])})"
                    for t in spec["tabs"]
                )
            )
            shown = None
            if args.model:
                if args.output:
                    out = Path(args.output)
                elif mon is not None:
                    out = mon.path / "dashboard" / "preview.html"
                else:
                    stem = Path(args.spec).stem if args.spec else "layout"
                    base = Path(args.spec).resolve().parent if args.spec else Path.cwd()
                    out = base / f"{stem}_preview.html"
                bands = None
                if args.watch is not None:
                    bands = {"watch": args.watch, "high": args.high}
                shown = preview_from_model(
                    args.model,
                    out,
                    None if mon is not None else (args.spec or None),
                    bands=bands,
                    monitor=mon,
                )
                print(f"Preview (with the scores saved in the model): {shown}")
            elif len(mon.scores):
                shown = mon.dashboard(preview=True)
                print(f"Preview: {shown}")
            else:
                print(
                    "No scores yet, so there is nothing to preview. Add --model "
                    "<complete model zip> to preview with the model's own scores."
                )
            if shown and args.open:
                import webbrowser

                webbrowser.open(Path(shown).resolve().as_uri())
        elif args.command == "run":
            mon = Monitor(args.folder)
            if args.input is None and not mon.inbox_files():
                print(
                    f"No input given and {mon.path / 'inbox'} is empty. Nothing to do."
                )
                return 0
            try:
                result = mon.run(
                    args.input,
                    dashboard=not args.no_dashboard,
                    trigger="scheduled" if args.scheduled else "manual",
                )
            except Exception as exc:  # recorded in runs/ with a plain reason
                reason = getattr(exc, "monitor_reason", None) or str(exc)
                print(f"Run FAILED: {reason}", file=sys.stderr)
                print(f"  ({type(exc).__name__}: {exc})", file=sys.stderr)
                return 1
            _print_run(result)
            if result.status == "ok" and not args.no_dashboard:
                print(f"Dashboard: {mon.path / 'dashboard' / 'index.html'}")
        elif args.command == "score":
            mon = Monitor(args.folder)
            out = mon.score_once(args.input, args.output)
            print(f"Scored. Results and dashboard in {out}")
        elif args.command == "dashboard":
            mon = Monitor(args.folder)
            failures = None
            if args.failures:
                import pandas as pd

                failures = pd.read_csv(args.failures)
            print(f"Dashboard: {mon.dashboard(failures=failures)}")
        else:
            print(json.dumps(Monitor(args.folder).status(), indent=1, default=str))
    except (MonitorError, SpecError, ConnectionError, TimeoutError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # API and validation errors from the SDK
        from amygda_ops_risk_score.exceptions import OpsRiskSDKError

        if isinstance(exc, OpsRiskSDKError):
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
