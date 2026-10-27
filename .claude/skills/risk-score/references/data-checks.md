# Step 0 — Check the data before Step 1

Profile the user's files before asking the upfront questions. Many problems that surface late in the pipeline are visible in the raw data, and several of them change which questions you ask. Report what you find in plain language, then ask.

## Contents
- What to check
- A profiling script
- How each finding changes the setup

---

## What to check

| Check | Why it matters |
|---|---|
| Rows, assets, date range, distinct log entries | Sets expectations; distinct entries become Step 1's `row_count` |
| **Days with logs per asset** (share of calendar days) | The model only scores time buckets that contain logs. With sparse logs, quiet days get no score, and rolling windows need checking (see validation.md) |
| **Message floods**: one entry repeated thousands of times in a burst | Collapsing repeats is optional and mostly speeds up processing. Note when the flood happened relative to failures, because it may be a real warning sign. Keep at least one entry per burst |
| **Routine vs fault entries**: normal-operation states, idle/standby, start-up and shutdown sequences, heartbeat or "OK" messages | Every classified entry adds to risk, so busy healthy periods can score high. Filtering routine entries is the user's decision, but it makes logs sparser. Keeping them instead means the hierarchy needs a place for them that isn't a fault subsystem |
| Timestamp format and resolution | Date-only data means daily buckets. For day-first dates, pass an explicit format (`"%d/%m/%Y"`), not `"infer"` |
| **Failure dates vs log range** | Failures before the logs start, or in the first few days, have no history to learn from. Failures after the training period belong to scoring, not training. Sample files can mix years |
| Gap between failures on the same asset | Drives the warning window (see Supervised Parameter Design Guidance). A gap of 0 days means a duplicate row |
| Asset IDs match between logs and failures | IDs often differ slightly between systems (a suffix, prefix or different case), and a maintenance file can include assets that aren't in the logs. Map the ones that belong and drop the rest, or supervised labels silently match nothing |
| Maintenance work orders: planned vs unplanned | Ask which ones count as failures; preventive maintenance usually doesn't |

## A profiling script

```python
import pandas as pd
logs = pd.read_csv(LOG_FILE)            # or pd.read_excel
ts = pd.to_datetime(logs[TIME_COL], dayfirst=True, errors="coerce")
print("rows", len(logs), "| assets", logs[ASSET_COL].nunique(), "| distinct entries", logs[LOG_COL].nunique(),
      "| range", ts.min(), "->", ts.max(), "| unparsed dates", ts.isna().sum())
days = ts.dt.normalize()
span = (days.max() - days.min()).days + 1
print("share of days with logs per asset:", (logs.assign(d=days).groupby(ASSET_COL).d.nunique() / span).round(2).to_dict())
top = logs[LOG_COL].value_counts()
print("top entries:\n", top.head(15))
print("largest share held by one entry:", round(top.iloc[0] / len(logs), 2))
f = pd.read_csv(FAILURES_FILE); fd = pd.to_datetime(f[FAILURE_DATE_COL], dayfirst=True)
print("failures by year:", fd.dt.year.value_counts().to_dict(), "| duplicates:", f.duplicated().sum())
print("failures before logs start / after logs end:", (fd < days.min()).sum(), (fd > days.max()).sum())
print("failure assets missing from logs:", sorted(set(f[ASSET_COL]) - set(logs[ASSET_COL])))
```

## How each finding changes the setup

- **Under about 80% of days have logs:** warn the user that quiet days won't be scored. Plan to check the rolling window after Step 10 (validation.md, "Sparse-log check").
- **Routine entries are a large share:** offer to remove them before Step 1, and list exactly which entries you would drop. If you remove them, re-check the share of days with logs, because it will fall.
- **One entry dominates:** offer to merge identical entries less than 60 seconds apart. Keep at least one per burst, because the burst itself may be the signal.
- **Composite log text:** if a status, severity or category column adds meaning, offer to combine it with the message (`"STATUS | message"`). Rows with an empty message then still carry text.
- **Routine entries kept:** plan for them in the hierarchy (Step 4–5). Give them their own system or subsystems, so they don't land in, or tie with, a fault subsystem.
- **Failures outside the log range or ID mismatches:** fix the failures file (filter, or map IDs) and save the prepared copies next to the originals. Never overwrite the user's files.
- **Very few failures** (under about 5 per asset with history before them): tell the user that supervised learning will have little to learn from, and that results will be optimistic. Offer unsupervised mode as the honest default.
