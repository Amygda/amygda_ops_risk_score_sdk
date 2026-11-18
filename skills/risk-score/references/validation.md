# Validating each stage

Checks to run at the points SKILL.md names. Each one guards against output that looks fine but isn't. Run them, show the user the result, and decide with them before moving on.

## Contents
- Keyword coverage check (Step 3)
- How keyword assignment works (Steps 4–5)
- Feature frequency check (after Step 9, before Step 10)
- Predicting and auditing classification (Steps 7b–8)
- Threshold check (Step 10)
- Choosing weights (Steps 10–11)
- Sparse-log check (after Step 10 and Step 12)
- Checking alert bands against failures (after Step 12)

---

## Keyword coverage check (Step 3)

Step 3's keyword pool is the vocabulary everything later depends on. Classification in Step 8 assigns each log entry by matching its words against the keywords on each subsystem's list, and Step 3 locks as soon as Step 4 starts. So check the pool before moving on:

1. **Coverage:** for every distinct log entry, list the keywords it contains. Every entry that matters needs at least one *specific* keyword: a component, signal or fault name, not just "fault" or "error". Pay most attention to the entries tied to the user's failure modes.
2. **Noise:** list generic terms in the pool. These include verbs (check, read, return, release, require), status words (error, fault, alarm, warning), and phrases that appear in many entries (a status prefix, "see logs for details"). They can't be removed, and they cause misroutes and ties later, so watch them in Steps 4–5.
3. **Stemming:** `deep` extraction lemmatises. Look for keywords whose stem changes meaning, e.g. "bearing" → "bear", "data" → "datum", "coupling" → "couple". Matching still works, because the logs are stemmed the same way, but the hierarchy AI may misread the stem and file the entry under the wrong system.

Choosing the method:
- **Free-text logs:** start with `"deep"`.
- **Fixed-log (structured) data:** there is no reliable default. `"fast"` with the filter on can return too few, generic keywords. `"fast"` with the filter off can return phrase fragments and miss whole families of related entries. `"deep"` with `linguistic_filter=False` tends to give the broadest coverage, at the cost of the stemming caveat above. If coverage has gaps, re-run with another setting while Step 3 is still repeatable, and compare.
- **Heavy jargon not in a standard dictionary:** set `linguistic_filter=False`.

A simple word-overlap check (lower-case, strip punctuation and plural `s`) is enough to spot gaps. It will flag some false gaps caused by stemming, so read the flagged entries rather than trusting the count.

## How keyword assignment works (Steps 4–5)

- The hierarchy rows carry a `keywords` list per subsystem. **Step 8 classifies by these lists**, not by the subsystem names.
- `update_hierarchy` accepts names and confidences only. **After every update, the server re-assigns keywords from the Step 3 pool.** A `keywords=` override passed to `generate_hierarchy` does not survive an edit, and keywords can be dropped or duplicated.
- So prefer the extracted pool as-is, and steer with **subsystem names**. Names that describe one mechanism or signal attract the matching keywords. Broad names ("faults", "diagnostics", "commands", "general errors") attract generic terms and become catch-alls.
- After each update, read every subsystem's keyword list and check for:
  - the same keyword on subsystems in different systems;
  - generic terms on a real subsystem. A catch-all that collects several generic words can outscore the specific subsystem an entry belongs to;
  - stemmed words filed by a wrong meaning;
  - important entries that now match nothing.

  Fix by renaming, splitting, merging or removing subsystems, then update again. This is repeatable until Step 6.

## Predicting and auditing classification (Steps 7b–8)

**For fixed-log sessions, don't rely on `preview_classification` to predict Step 8.** The preview's per-entry labels can disagree with Step 8, which follows the subsystems' keyword lists: an entry can score high in the preview and still end up unclassified, or land in a different system.

Before Step 8, predict the final result from the hierarchy rows. For each entry, list the subsystems whose keywords it contains, and how many keywords match. As a rule of thumb, the subsystem with the most matching keywords tends to win. Treat that as a review heuristic, not a promise. Flag:
- **Ties:** equal matches on two or more subsystems. Step 8 picks one and records a confidence below 1.
- **Wins by generic terms:** a catch-all beating the specific subsystem.
- **Entries with no match:** these will be unclassified.

Show the user this prediction alongside the preview.

**After Step 8, always audit the zip:**

```python
import io, zipfile, pandas as pd
z = zipfile.ZipFile(zip_path)
dd = pd.read_parquet(io.BytesIO(z.read("labels/deduplicated_predictions.parquet")))   # one label per entry
ex = pd.read_parquet(io.BytesIO(z.read("labels/all_predictions_exploded.parquet")))   # every candidate label
logs = pd.read_csv(LOG_FILE)
missing = sorted(set(logs[LOG_COL]) - set(dd[LOG_COL]))           # unclassified entries
ties = dd[dd.confidence < 1][[LOG_COL, "system_name", "subsystem_name", "confidence"]]
rows_per_system = logs.merge(dd[[LOG_COL, "system_name"]], on=LOG_COL, how="left").system_name.fillna("(unclassified)").value_counts()
```

Report:
- the unclassified entries, with their row counts;
- tied entries, with the label they got and the alternatives;
- rows per system;
- any entry tied to a failure mode that landed in the wrong system.

If the result is poor and the dataset is small, redoing labelling is usually cheap, because Steps 1–8 are mostly automatic. Offer it, with an estimate based on how long this run took.

## Feature frequency check (after Step 9, before Step 10)

`feature_frequency="auto"` picks the finest bucket width the timestamps support. That is not always a width the data can fill. Before training, check how many buckets would actually contain logs. Only buckets with logs get features and scores:

1. Read the chosen width, `timestamp_resolution` and `typical_event_gap` from Step 9's result, and tell the user what was picked and why.
2. From the raw log, count the buckets of that width that contain at least one entry, per asset, and divide by the buckets in each asset's time span. This is a count of the user's data, not a recalculation of any score.
3. If only a small share of buckets contain logs (as a rule of thumb, under about 20%), the width is probably too fine. Scores will swing with individual bursts, most of the time will have no score, and supervised training gets "pre-failure" buckets that look like any busy period. Suggest a coarser width (e.g. `"1h"`, `"4h"`, `"1D"`) and show the share at each.
4. Also consider the failure records: if failure times are only known to the day, sub-daily buckets add little to the labels.

Step 9 is repeatable until Step 10 starts, so re-run it with the new width before training. Once training has run, changing the width means a new risk-score session.

## Threshold check (Step 10)

Don't judge thresholds by eye. From `training_fe.parquet` (column `<system>-<subsystem>_risk_feature`), compute per subsystem the threshold, mean, max and **share of time buckets at or above the threshold**:

- 🟢 Flagged on a small share of buckets (roughly 1–15%): usable.
- 🔴 Flagged on a large share (30% or more): the threshold sits at or near the mean, and "elevated" is the normal state.
- 🔴 Threshold near the maximum: unreachably high, so the subsystem will rarely or never trigger. Consider lowering `quantile_for_thresholds`.
- ⚪ Max 0: the subsystem never fires, usually a sign of a labelling problem upstream.

If the feature values are mostly small whole numbers, they are too coarse for a quantile to separate well:
- `flag` features are 0/1 per code, so thresholds tend to land at the lowest non-zero value. Prefer `sum` for fixed-log data.
- With few logs, a quantile can land on the mean whatever its value. Changing `quantile_for_thresholds` cannot fix that; a longer window or a coarser `feature_frequency` can.
- Step 9's settings lock once Step 10 runs. To try other settings, open a new risk-score session and import the labelling zip again.

## Choosing weights (Steps 10–11)

Show the training report's AUC-ROC **and average precision** for expert vs learned weights. Average precision is the better guide when pre-failure buckets are rare. Then look at `trained_weights.json`:

- **With few positive buckets (`n_positive_rows` small, e.g. under about 30), learned weights can drop whole systems or key subsystems to 0.** That can include the subsystems tied to the user's own failure modes. It fits the training data, but may not be a believable picture of the equipment; ask the user.
- The training report's scores are measured on the training data itself, so they flatter the learned weights.
- Step 11 accepts only `"labelling"` or `"supervised"`. Don't default to supervised because the run was supervised; choose with the user from this evidence.
- If neither weight set is acceptable, say so. The API can't score with a mix of the two, so don't build one locally. The options are: use the expert weights, retrain with settings that give more positives (a longer warning window, or more failures), or raise it with Amygda.

## Sparse-log check (after Step 10 and Step 12)

The model only scores time buckets that contain logs, and empty buckets get no row. On sparse logs:

1. **Count scored buckets vs calendar buckets.** Quiet periods are missing, not low. Say so when presenting results.
2. **Check that the rolling window is time-based.** Earlier SDK versions windowed over the last N rows with logs, so a burst could be carried into scores weeks later. SDK 5.0.0 documents windows as durations (`"7D"`), but check it without recalculating anything:
   - Pick a scored bucket that follows a quiet stretch longer than the window.
   - Look up, in the raw log, whether any entries mapped to a subsystem (`logs_by_system_subsystem.json`) fall inside that bucket's window.
   - If none do, but the server's feature for that subsystem in `training_fe.parquet` or `risk_scores.parquet` is above 0, the window is reaching back past its time span.

   If you find that, don't correct the scores locally. Tell the user which buckets are affected (scores there are carried over from earlier activity), and note it as feedback for Amygda.

Adding placeholder rows for quiet periods does not help: rows that match no keyword are dropped before features are built.

## Checking alert bands against failures (after Step 12)

The 33/66 colour bands in the helpers are fixed and rarely match a given model's score range. Pick bands from the data:

- Look at the scores in the run-up to each failure (the warning window and a little before) and on ordinary days. Choose a watch level that catches the build-ups, and a high level that fires rarely outside them. Show how many buckets each would flag.
- Separate post-failure repair periods from warnings. Scores can stay high while equipment is being fixed; those are neither false alarms nor warnings.
- **`helpers.plot_detection_roc` picks its cut-off on the training data.** Treat it as optimistic: a cut-off fitted in-sample can sit above the scores that later failures actually reach.
- Check the failures file for failures inside the scored period, and use them as the real test.
