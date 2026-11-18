# Running the pipeline as an agent

How to execute the SDK from an agent's tools (one shell command or script per step) so the user always sees progress, sessions survive between commands, and nothing sensitive leaks. Read this before Step 1.

## Contents
- Session persistence between commands
- Streaming progress to the user
- Keeping the API key out of output
- Session lifetime and the one-session-per-key rule
- When a call hangs
- Showing results without a notebook
- Scores come from the API only

---

## Session persistence between commands

Each tool call usually starts a fresh Python process, so the `Session` object does not survive. Save the `auth_id` to a file in `artifact_dir` the first time you open a session, and reconnect with `get_session` in every later command:

```python
from pathlib import Path
from amygda_ops_risk_score import OpsRiskClient, SessionConfig

def connect(artifact_dir, name, api_key):
    artifact_dir = Path(artifact_dir); artifact_dir.mkdir(parents=True, exist_ok=True)
    id_file = artifact_dir / "AUTH_ID"
    client = OpsRiskClient(); client.wait_until_ready()
    if id_file.exists():
        return client, client.get_session(auth_id=id_file.read_text().strip(), artifact_dir=str(artifact_dir))
    session = client.open_session(api_key=api_key, config=SessionConfig(name=name), artifact_dir=str(artifact_dir))
    id_file.write_text(session.auth_id)
    return client, session
```

Use separate `artifact_dir`s for labelling and risk scoring (they are different sessions). When a session is finished, deleted or expired, move or delete its `AUTH_ID` file so the next run opens a fresh one.

Read the API key from an environment variable or a `.env` file. Never ask the user to paste it into the chat.

## Streaming progress to the user

Steps take from 2 seconds to several minutes, and a user staring at a silent terminal assumes something broke. The SDK prints progress lines (`[extract_keywords] Scanning text... (40s elapsed)`), so make sure they reach the user:

- Run long steps in the background with unbuffered output written to a log file: `python -u step.py > artifact_dir/step.log 2>&1`.
- Watch that file and relay progress roughly every 30 seconds, plus a "still waiting on the server: N min" line each minute if nothing new appears.
- **Do not pipe output through `tail`, `head` or a plain `grep`.** They hold everything back until the command ends, so the user sees nothing. If you filter, use `grep --line-buffered` and an `awk` that calls `fflush()`.
- End each step script with a marker line such as `STEP3_DONE`, so whatever is watching knows when to stop.
- Progress lines use carriage returns. Convert them (`tr '\r' '\n'`) before reading the log.
- Before a step that has a gate (for example "stop if fewer than N days were scored"), print the gate result and exit non-zero on failure. Then a one-way door never runs on bad input.

## Keeping the API key out of output

`session.status()` returns the full `api_key`. Never print or log the raw status. Remove the key first:

```python
status = dict(session.status()); status.pop("api_key", None)
```

If a key does get printed, tell the user straight away and recommend they ask Amygda to rotate it.

## Session lifetime and the one-session-per-key rule

- **Sessions expire after about 4 hours** (`expires_at` in the status). That is less than the 6 hours stated elsewhere. Tell the user at the start, and plan Steps 1–8 (and then 9–12) as one sitting each. If a session expires mid-pipeline, the inputs and settings are still on disk: open a new session and re-run the completed steps in one script, then confirm the keyword list matches the previous run.
- **One active session per API key.** Delete sessions you abandon (`session.delete()`) instead of leaving them to expire.
- If `open_session()` returns `500 internal_error` right after a session expired, an expired session may still be holding the key's slot, and the client cannot clear it (`DELETE` on an expired session returns 404). Stop retrying and give the user the details for Amygda: the time, the endpoint, and the expired `auth_id`.

## When a call hangs

The first `extract_keywords(extraction_method="deep")` call has been seen to hang on the client for 10+ minutes, while the same call re-sent finished in about 2 seconds. If a step shows no progress line for 2 minutes and the server status still shows the previous result, kill the client process and re-send the call. Re-sending a repeatable step is safe.

Do not re-send a one-way door (Steps 8 and 12) this way without checking `session.status()` first. Step 8 can be retried safely only if the download failed (see Step 8 in SKILL.md).

## Showing results without a notebook

Plot helpers display through IPython and return `None`. Run from a script, they show nothing. Instead:

- Show results as tables in the chat (`get_top_keywords_table`, value counts, per-code mappings).
- For charts, build your own from the downloaded parquet files: an HTML page, or matplotlib saved to PNG with the `Agg` backend.
- Helpers that return data, such as `plot_detection_roc` (returns the threshold) and `plot_failure_detection_summary` (returns a DataFrame), still work from a script. Set `MPLBACKEND=Agg` to silence the display.

## Scores come from the API only

Every score, feature, threshold and weight you show the user comes from the API's own outputs (`risk_scores.parquet`, `training_fe.parquet`, `training_scores.parquet`, `calibration_thresholds.json`, the weight files). Don't rebuild or recompute scores locally, for example to blend weights or change windows. The internal calculation isn't documented and can change between SDK versions, so a local recalculation can drift from the real model without anyone noticing.

If the API can't produce what the user wants (a weight mix, a different window), say so, and note it as feedback for Amygda rather than working around it. Tables and charts built from the API's numbers are fine: that is presentation, not recalculation.
