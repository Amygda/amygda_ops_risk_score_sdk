# The Fleet App

Use this when the user wants to keep scoring new data with a model they are happy with. They get a small app on their own machine that shows the risk scores, takes new files, runs on a schedule and raises alerts. The user decides what it shows by answering questions. You write their answers into a spec; the SDK supplies the app. **You never write app code.**

This is the only way to keep scoring new data. Don't offer a script, a cron job or "scheduled scoring only" as an alternative: the app has the schedule.

It uses `deployment.md` for deploying the model and for the checks. Read that file too.

## Contents
- When to offer it
- What the user gets
- The questions
- From answers to a spec
- Starting layouts
- Steps
- Checking the app without a browser
- Checks before handing over
- Changing it later
- Removing a monitor
- Troubleshooting

---

## When to offer it

- **After Step 12 and the dashboard:** *"Would you like to keep watching this fleet as new data arrives? I can set up a small app on this machine: you choose what it shows, it scores new files on a schedule, and it raises alerts. It takes a few questions."*
- **When the user brings a `complete_model_<id>.zip`** and wants to monitor or keep scoring: do "Starting from an existing model zip" in `deployment.md`, then come here.
- **When the user already has a monitor folder** and wants a different layout, alerts or a schedule: go to "The questions", then step 4 onwards.

## What the user gets

Say this in your own words before the questions, so they know what they are choosing for:

- A page in their browser (`http://127.0.0.1:8050/`), on this machine only, with no login.
- Tabs and panels they chose: what changed, rankings, a heatmap, each asset in detail, alerts, run history.
- A bar at the top to **add files**, **run now**, and **set, pause or resume a schedule**.
- Alerts when something they care about happens, which they acknowledge with a click.
- Their logs and scores stay in a folder on this machine. Only the logs being scored are sent to the API, and they are not kept there.

**Setting it up scores nothing.** You deploy the model, create the folder and start the app. The app then waits for the user's data: they add files on the page or drop them in the folder. Don't score a file yourself, not even "so there is something to look at", unless the user asks you to load one.

## The questions

Three rounds, in this order: what the app shows, how it looks, then alerts and schedule. Use plain words, and say what you'll do if they have no preference. Never ask about ports, servers, processes, file formats or anything else technical: use the defaults in "Steps".

### Round 1: what the app shows

Do this in three steps, in this order: the panels, then who it is for, then your proposal. Don't ask about tabs or layout until the panels are chosen.

**Step 1: the panels, one group at a time.** Run `amygda-risk panels --menu` (`--menu --json` for the same as data). It prints five groups, each with a question, and under it the panels with a plain name and one line on what the user would see. Use its names and lines as they are; don't use the panel ids (`since_last_run`) with the user, and don't rely on lists in this file.

First offer the short cut: *"The app can show up to 15 panels in five groups. Shall I take you through them group by group so you can pick, or start with all of them and you tell me what to drop?"*

To go through them:
- **Ask one group per question, five questions in all.** Each group has at most four panels.
- **If you have a tool that asks the user a question with options to tick, use it:** one question per group, the group's question as the question, one option per panel with the plain name as its label and the line as its description, and more than one answer allowed.
- **Otherwise print the group as a short list, one panel per line**, each line starting with its letter, then the name in bold, then the line. End with *"Which of these? Letters, all or none."* and wait for the answer before showing the next group.
- **Never put several groups, or a group's panels, into one sentence or paragraph.** A user can't choose from a run of names separated by commas or dots.
- Say which you'd recommend when a group needs it: for the asset group, the first three work together, and the logs panel is what lets the user see the actual logs behind a score (for a fixed-log model, each code with the system it counts toward; for free-text, the log text itself). Tell them a dashboard file saved with the logs panel contains the log text; `weights` and `unmapped_codes` only appear when the model has them.
- A group answered "none" is left out. If every group is "none", say the page would be empty and ask again.

When the last group is answered, read the choice back as a short list (group, then the chosen names) and ask if it's right.

**Step 2: who it is for.** Only now ask about layout, and ask it through the person, not through tabs: *"Who will use it most?"* Give the three choices below, each with its line on what it means for them, so they can tell which fits. With a question tool, the bold name is the option's label and the line its description; otherwise print one choice per line.

- **Someone checking each morning.** *"The page opens on what changed since the last run and any open alerts, with the ranking under it. The figures at the top are about today: open alerts and the assets at watch or high right now. Assets are ordered by their latest score. Best when someone acts on it daily."*
- **An engineer looking into assets.** *"The page opens on one asset in detail: its risk over time, each system, and what drove a period. The model and run panels are shown in full. The figures at the top are the highest risk reached and data quality. Assets are ordered by the highest risk they reached. Best for working out why an asset is risky."*
- **A manager glancing weekly.** *"The page opens on the whole fleet: the heatmap and the ranking, with each panel's explanation written out under its title. The figures at the top are totals for the period. Assets are ordered by their average risk. Best for seeing the overall picture, not the detail."*

Say that this only arranges the panels they chose: nothing is added or removed, and they can change the arrangement when they see the proposal. The answer decides:

| Who | Opens on | Order and detail | Header figures | `rank_by` |
|---|---|---|---|---|
| Checks each morning | The tab with `since_last_run` and `alerts` | What changed first, then the ranking; model and run panels on later tabs | `open_alerts`, `assets_high_now`, `assets_watch_now`, `last_run` | `latest` |
| Engineer | The asset tab | Asset panels first; model and run panels in full | `highest`, `assets_high`, `at_watch`, `unmatched`, `provisional` | `peak` |
| Manager, weekly | The fleet tab | `heatmap` and `ranking` first; notes written under each title (`notes: inline`) | `assets_high`, `median`, `highest`, `assets_scored` | `mean` |

Put the chosen panels into tabs by their groups (a group with one or two panels can share a tab with a related group), in the order the table gives. The asset panels must share one tab. Take the header figures and `rank_by` from the table too; don't ask about them separately.

**Step 3: propose.** Show the layout as a short table (tab → what's on it, top to bottom, by plain name) plus the header figures in words, and ask if it's right. A proposal is easier to correct than a blank page. Change it as they say: a panel moved, a tab renamed, a figure swapped (`amygda-risk panels` lists the header figures).

### Round 2: the name and how it looks

**The name.** Ask: *"What should this app be called?"* (for example "Conveyor fleet risk"). Use the user's answer everywhere, and don't make up another name from the data or from the examples in this file:

| Where | Form | Example for "Conveyor fleet risk" |
|---|---|---|
| The top of the page (`title` in the spec) | As the user wrote it | `Conveyor fleet risk` |
| `--fleet-name` at step 3 | As the user wrote it | `"Conveyor fleet risk"` |
| The folder and the spec file | Lower case, underscores | `conveyor_fleet_risk_monitor/`, `conveyor_fleet_risk_app.json` |
| The deployment name (`--name`) | Lower case, hyphens, `-v1` | `conveyor-fleet-risk-v1` |
| The start-up entry (`--name` at step 5) | Lower case, hyphens | `conveyor-fleet-risk` |

If the user wants a different name for one of these, use theirs.

| Ask | Default |
|---|---|
| Light, dark, or follow each viewer's device? | Follow the device |
| Do you have a brand colour? (a hex code like `#0b6e4f`, or tell me the colour and I'll pick one) | No brand colour |
| Do you have a logo file to put at the top? (png, jpg, svg; up to 300 KB) | No logo |

If they have no preferences, say you'll use the defaults and move on. Amber and red can't be changed: they always mean watch and high. The colour must be written as `#rrggbb`; it is used for a thin bar across the top and the line under the open tab. If the user names a colour ("a dark green"), pick a hex yourself, avoid ambers and reds, and have them confirm it when they see the page.

### Round 3: alerts, schedule and where the data is kept

| Ask | Default |
|---|---|
| What should raise an alert? Offer in plain words: an asset reaches **high** (or watch) · an asset's score **jumps** by N points in one run · an asset **goes quiet** for N days while others report · a **run fails** · too many new logs **match nothing** (the data may have changed) | An asset reaching high, and a failed run |
| How often should it check for new files? (every few hours, every day at a time, or every week on a day) | Every day at 06:00 |
| Should the app start by itself whenever you log in to this computer, so the checks always happen? | Yes |
| Keep the scores and history as **ordinary files**, or in **one database file**? Say: "Both live in the same folder on this machine and work the same. Pick the database if you'd like to query the scores from other tools, or want a single file to back up. You can switch later." | Files |

Plus, if not already answered, the questions in `deployment.md` ("Questions to ask"): the alert bands and the history file.

Notes for the alert question:
- **Turn the user's words into rules, and say back what you chose.** "When something gets bad" is `enters_band`; "suddenly gets worse" is `rises_by`; "stops working" can mean a run failing (`run_failed`) or an asset going quiet (`no_data`): include both unless they say which.
- **Check that a band rule can fire.** Compare the watch and high levels with the scores the user has (Step 12's, or `risk_score/risk_scores.parquet` in the model zip): the highest `operational_risk` against each level. If nothing has reached high, say so and add watch. If nothing has reached watch either, say that plainly: *"No asset has come near these levels, so the band alerts will stay silent unless something changes a lot. The jump rule is the one that will speak up."* Offer to revisit the levels (the defaults are only a starting point), and always include a jump rule, so a silent Alerts tab isn't mistaken for a healthy fleet.
- **Size the jump rule from the data.** A run compares each asset's latest score with its latest score before the run, so the size depends on how often new files arrive. Ask how often a new file is expected (daily, weekly). Then, in the scores the user has, take each asset's last `operational_risk` per day (or per week), difference it, and pick N so that it would have fired a handful of times over the period, not every run. Weekly files move more per run than daily ones: don't reuse a daily number for weekly files.
- **Severity labels.** Every alert carries `HIGH` or `WATCH`. For `enters_band` it is the level reached. For the others it is only how urgent the alert is: `run_failed` is `HIGH`; `rises_by`, `no_data` and `unmatched_above` are `WATCH`. Tell the user a `WATCH` on a jump alert does not mean the asset reached the watch level.
- Alerts show in the app. They are not emailed or sent anywhere; say so if the user expects that.
- Tell the user what they will see: each alert says what happened and when, clicking one about an asset opens that asset at that time, and the app's **Settings** tab has **Alert settings**, where they can switch each kind of alert on or off and change its level or number themselves. Changes apply from the next run.

## From answers to a spec

The spec is one JSON file. Write it next to where the monitor folder will be, as `<name>_app.json` (the name from Round 2, lower case with underscores). The monitor keeps its own copy as `app.json`. Everything is optional; what you leave out gets the default.

```json
{
  "title": "Conveyor fleet risk",
  "rank_by": "peak",
  "theme": {"mode": "auto", "accent": "#0b6e4f", "logo": "logo.png"},
  "header": {"tiles": ["open_alerts", "assets_high_now", "highest", "last_run"]},
  "alerts": {"rules": [
    {"type": "enters_band", "band": "high"},
    {"type": "rises_by", "points": 8},
    {"type": "run_failed", "runs": 1}
  ]},
  "schedule": {"every": "day", "at": "06:00"},
  "tabs": [
    {"title": "Fleet", "panels": ["since_last_run", "fleet_systems", {"type": "ranking", "top": 10}]},
    {"title": "Alerts", "panels": ["alerts"]},
    {"title": "Assets", "panels": ["asset_trend", "asset_systems", "asset_drivers"]},
    {"title": "Health", "panels": ["run_table", "known_gaps"]}
  ]
}
```

| Answer | Goes into |
|---|---|
| What they want first, and on which tab | `tabs`: each has a `title` and `panels`, top to bottom. The first tab opens first (or set `default_tab`) |
| A panel with a setting ("only the top 10", "only assets that were flagged") | An object instead of a name: `{"type": "ranking", "top": 10}`, `{"type": "since_last_run", "only_flagged": true}`. `amygda-risk panels` lists each panel's settings. `"width": "half"` puts two panels side by side; `"title"` renames one |
| Figures at the top | `header.tiles`: up to 6 |
| "Worst" means… | `rank_by` |
| The name | `title`: shown at the top exactly as written |
| Look | `theme.mode` (`auto`, `light`, `dark`), `theme.accent`, `theme.logo` (a path, relative to the spec file; it is copied into the monitor folder) |
| Alert rules | `alerts.rules`: each a `type` and one setting. `enters_band` (`band`: `watch` or `high`; watch also covers high), `rises_by` (`points`), `no_data` (`days`), `run_failed` (`runs`), `unmatched_above` (`percent`). `"rules": []` turns alerts off |
| How often | `schedule`: `{"every": "hours", "hours": 6}` (1, 2, 3, 4, 6, 8 or 12), `{"every": "day", "at": "06:00"}` or `{"every": "week", "weekday": "mon", "at": "06:00"}`. Local time |
| Explanations on the page | `notes`: `tooltip` (an info mark by each title, the default), `inline` or `off` |

Rules the check enforces: each panel appears once; the `asset_*` panels go on the same tab; up to 8 tabs; up to 6 tiles. If the user wants alerts, include the `alerts` panel on some tab (and the `open_alerts` tile), or they will have nowhere to see them.

Check a spec without touching anything:

```python
import json
from amygda_ops_risk_score.monitor import validate_spec, SpecError
try:
    validate_spec(json.load(open("<spec file>")))
except SpecError as e:
    print(e)      # says what is wrong in plain words, with a suggestion for a misspelt name
```

## Starting layouts

When the user says "you choose", start from the nearest of these and adjust.

**Daily check** (someone looks each morning and acts on what changed):
- Fleet: `since_last_run`, `fleet_systems`, `ranking` (top 10) · Alerts: `alerts` · Assets: `asset_trend`, `asset_systems`, `asset_drivers`, `asset_logs` · Health: `run_health`, `run_table`
- Tiles: `open_alerts`, `assets_high_now`, `assets_watch_now`, `last_run` · `rank_by`: `latest`

**Engineer** (digs into why an asset is risky):
- Assets: `asset_trend`, `asset_systems`, `asset_drivers`, `asset_logs` · Fleet: `heatmap`, `fleet_systems`, `ranking` · Alerts: `alerts` · Model: `bands`, `weights`, `unmapped_codes`, `known_gaps` · Runs: `run_health`, `run_warnings`, `run_table`
- Tiles: `highest`, `assets_high`, `at_watch`, `unmatched`, `provisional` · `rank_by`: `peak`

**Weekly overview** (a manager wants the picture, not the detail):
- Overview: `heatmap`, `ranking` (columns `mean`, `peak`, `at_watch`, `at_high`; top 15) · Alerts: `alerts` (with `include_closed`) · Assets: `asset_trend`, `asset_systems`
- Tiles: `assets_high`, `median`, `highest`, `assets_scored` · `rank_by`: `mean` · `notes`: `inline`

Leaving `tabs` out altogether gives the standard layout: Fleet, Asset detail, Alerts, Model, Runs.

## Steps

Run these yourself, one at a time (see `agent-execution.md`, "Running the monitor"). Defaults you don't ask about: port 8050; the folder `<project>/<name>_monitor`.

1. **Show the layout before deploying anything.** One command builds the page from the scores saved in the model zip (the `complete_model_<id>.zip` from Step 12, or the one the user brought) and opens it in the user's own browser:
   ```bash
   amygda-risk design --spec <spec file> --model <complete_model.zip> --open [--watch <w> --high <h>]
   ```
   It deploys nothing, sends nothing and saves only the page (`<spec name>_preview.html`, beside the spec). Give `--watch` and `--high` when levels were agreed. Panels that need a run (what changed, alerts, run history) show as "pending" cards, so the user sees where they will be. Ask what to change, edit the spec, run it again, and repeat until they are happy.

   Let the command open the page (`--open`). Don't try to load the file in a browser tool or pane of your own: many can't open local files.

2. **The API key.** The commands and the app read the key from a file named `.env` in the monitor folder or the folder above it, with a line `AMYGDA_API_KEY=...`. If the user's `.env` already uses another name (the examples use `AMYGDA_SDK_API_KEY`), keep it and pass `--api-key-env <NAME>` at step 3. If there is no `.env`, ask the user to create one in the project folder and add the line themselves. **Never write, print or echo the key.**

3. **Create the monitor**, as in `deployment.md` ("Steps"), with the name from Round 2 and the storage answer:
   ```bash
   amygda-risk init <folder> --model <complete_model.zip> --name <name-v1> \
       --history <training_file> --fleet-name "<name>" \
       [--watch <w> --high <h>] [--storage sqlite] [--api-key-env <NAME>]
   ```
   Then run `helpers.check_deployment` (`deployment.md`, "Checks before handing over"). It checks the deployed model against the scores saved in the zip; it adds nothing to the monitor. Skip this step for an existing monitor.

4. **Apply the layout:**
   ```bash
   amygda-risk design <folder> --spec <spec file>
   ```
   It checks the spec, saves it in the folder and reports a problem in plain words. Fix the spec and run it again. To look at it again before any data has been scored, add `--model <complete_model.zip> --open`.

5. **Start the app.** Use the answer to "should it start by itself when you log in" from Round 3. If you haven't asked, ask now, in these words and no more technical: *"Should the app start by itself whenever you log in to this computer? That way the daily check always happens. You can turn this off at any time."* Don't mention launchd, agents, services, plists or file paths unless the user asks how it works; then show `amygda-risk service <folder>`, which prints the exact entry and changes nothing.

   On a yes:
   ```bash
   amygda-risk service <folder> --name <name> --install
   ```
   `--name` is the user's name for the app from Round 2 (lower case, hyphens). If they ask for a different name here, use theirs.

   On a no, start it for now in the background (the command does not return, and without `--no-open` it opens a browser window):
   ```bash
   nohup amygda-risk app <folder> --port 8050 --no-open > <folder>/app.log 2>&1 &
   ```
   Tell them plainly: it runs until this computer restarts or they log out, and the scheduled checks only happen while it is running. They can start it themselves any time with `amygda-risk app <folder>`.

6. **Open the app** at `http://127.0.0.1:8050/`. It says it is set up and waiting for data: that is the right state to hand over. Walk the user through the bar at the top: the status line and next scheduled check, **Add files**, **Run now** and the **Schedule** button (change, pause, resume). Tell them the tabs fill in after the first run, and that a **Settings** tab then appears on the right, where they can change the alert settings and rearrange the tabs and panels themselves. If they have a file ready, let them add it and press **Run now** themselves; don't do it for them.

7. **Hand over** with the checks below.

**Only if the user asks you to load data** (for example a backlog of older files): `amygda-risk run <folder> --input <file>`, as in `deployment.md` ("Loading older files"). Report each run as "Reading a run" there describes.

## Checking the app without a browser

The page's buttons call these on `http://127.0.0.1:8050`. Use them to check the app yourself; anything other than a GET needs the header `X-Amygda-App: 1` (without it: 403, "Requests must come from the app's own page").

| Button | Call |
|---|---|
| (status line) | `GET /api/state`: `key_present`, `schedule_text`, `next_run`, `inbox`, `running`, `last_run`, `last_action`, `open_alerts`, `problem` |
| Add files | `PUT /api/inbox/<file name>` with the file as the body (`curl -T <file> -H "X-Amygda-App: 1" ...`) |
| Run now | `POST /api/run`, then poll `/api/state` until `running` is null and read `last_action` |
| Schedule | `POST /api/schedule` with the schedule as JSON; `POST /api/schedule/pause`, `/api/schedule/resume` |
| Acknowledge | `POST /api/alerts/<id>/ack` (`all` for every open alert) |
| Save alert settings | `POST /api/alerts/rules` with `{"rules": [...]}`, the same rules as `alerts.rules` in the spec |
| Save layout | `POST /api/layout` with `{"tabs": [...], "tiles": [...]}`, as `tabs` and `header.tiles` in the spec |

Prefer having the user press the buttons, and read `/api/state` afterwards. Don't add files or start runs through these calls unless the user asked you to load data.

## Checks before handing over

- Everything in `deployment.md` ("Checks before handing over").
- **The app answers and has its key:** `curl -s http://127.0.0.1:8050/api/state` returns JSON with `"key_present": true`, the `title` the user chose, the `schedule_text` they asked for and a `next_run` time. If `key_present` is false, the `.env` isn't where the app looks, or the variable name differs (step 2).
- **Nothing was scored during setup:** `"has_scores": false` and `"last_run": null`, unless the user added a file themselves or asked you to load one.
- **The alert rules can fire** (Round 3 notes), and the Alerts tab is on the page.
- **`amygda-risk service <folder>`** says `installed: yes`, if they chose to have it start by itself.
- Tell the user, briefly: the address to bookmark; that new files go in through **Add files** or into `<folder>/inbox/`; that alerts appear on the Alerts tab and are not sent anywhere; that the machine must be on and logged in for scheduled runs (a run missed while it was off is made when the app next starts); and how to stop it (`amygda-risk service <folder> --remove` if it starts by itself; otherwise it stops when the machine restarts or they log out).

## Changing it later

| The user wants | Do |
|---|---|
| A different layout, look or alert rules, through you | Start from the monitor's own copy, `<folder>/app.json`: the user may have changed the tabs and panels, the alert settings or the schedule in the app since you wrote the spec file. Copy it over the spec file, make the change there, and run `amygda-risk design <folder> --spec <file>`. The open page notices within a few seconds and loads again by itself; there is nothing to restart. New alert rules are checked from the next run |
| A different alert level or number, by themselves | **Settings** tab in the app → Alert settings |
| To rearrange the page themselves | **Settings** tab in the app → Tabs and panels: tick or untick a tab or a panel to show or hide it, drag tabs and panels into a new order, drag a panel onto another tab, and drag unused panels in from "Not on the page". They can also rename, add and delete tabs and choose the figures at the top. Saving loads the new layout. A tab or panel that is unticked stays in `app.json` with `"hidden": true`: keep it when you edit the layout, and don't treat it as a mistake |
| The standard layout back | `amygda-risk design <folder> --reset` |
| A different schedule, or to pause it | The **Schedule** button in the app |
| To see or close alerts without the app | `amygda-risk alerts <folder>` (`--all` for closed ones, `--ack <id>` or `--ack all`) |
| Files or database | `amygda-risk storage <folder> --to sqlite` (or `files`), with the app stopped: `service --remove` first, `--install` after. `amygda-risk storage <folder>` says which it uses |
| A different port, or another name for the start-up entry | `amygda-risk service <folder> --port <n> --name <name> --install` replaces the entry |
| To stop the app but keep everything | `amygda-risk service <folder> --remove`. The folder, scores and deployment stay |
| To get rid of the monitor altogether | "Removing a monitor" below |
| Different watch and high levels | `bands` in `monitor.json` (`deployment.md`) |

With database storage, the scores are in `<folder>/monitor.db`: table `scores` (one row per asset and period: `asset_id`, `period_start`, `operational_risk`, a column per system and subsystem score, `provisional`), `runs` and `alerts`. Any SQLite tool can read it. Tell the user to read it only; the monitor rewrites it.

## Removing a monitor

One command takes a monitor away: it stops the app, removes the start-up entry, deletes the deployed model from the API and deletes the folder with its scores and history.

```bash
amygda-risk remove <folder>          # says what it would do; changes nothing
amygda-risk remove <folder> --yes    # does it
```

Run it without `--yes` first and show the user what it lists. **Ask, and run it with `--yes` only on a clear yes: none of it can be undone.** `--keep-deployment` leaves the deployed model on the API (for example when another machine scores with it). A deployment the monitor was only attached to (`init --deployment-id`) is never deleted. Never remove a monitor folder by hand, and never delete a deployment through the Python client when this command can do it.

## Troubleshooting

| What happens | Cause | What to do |
|---|---|---|
| The page says "No API key" or Run now is refused | The app can't find the key | Step 2: a `.env` in the monitor folder or the one above, with the variable named in `monitor.json` (`api_key_env`). Then restart: `service --install` again |
| "Port 8050 can't be used" | Another app (or this one, already running) has the port | `amygda-risk service <folder>` shows whether it is installed. Otherwise pick another port |
| The page doesn't load | The app isn't running | `amygda-risk service <folder>`; read `<folder>/app.log` |
| "The dashboard could not be built" on the page | A spec problem | `amygda-risk design <folder> --spec <file>` reports it |
| A scheduled time passed and nothing ran | The inbox was empty (nothing to do, no run is recorded), the schedule is paused, or the machine was off | Check the status line in the app. A missed check is made when the app next starts |
| The Alerts tab is always empty | No rule can fire with these levels | Round 3 notes: compare the levels with the scores, add a watch or jump rule |
| The page only says it is waiting for data | Nothing has been scored yet | Expected after setup. It fills in after the user's first run |
| A panel the user chose is missing | It has no data yet (run panels before the first run; `unmapped_codes` for a free-text model; the logs panel until the monitor has kept some logs) | It appears once the data exists. A monitor made before the logs panel existed shows the logs it still has, about twice the model's rolling window, and builds up from its next run |
| "The name ... is already used by another monitor's app" | Two monitors were given the same start-up name | Ask the user for another name, or remove the old monitor first |
| "Another run is in progress" when changing storage | The app or a run holds the folder | Stop the app first |
| The entry can't be installed | The system refused, or isn't macOS, Linux or Windows | Show the user the message. Start the app by hand with `amygda-risk app <folder>` in the meantime |
| Linux: the app stops when the user logs out | User services end with the session | The user can run `loginctl enable-linger $USER` (it needs their say-so) |

Run failures, unmatched logs and the other monitor messages: `deployment.md` ("Troubleshooting").
