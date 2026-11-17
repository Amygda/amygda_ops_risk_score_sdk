# Risk Score Dashboard (after Step 12)

Build this after Step 12 has finished, the results are downloaded and the "After Step 12" checks are done. It turns the run's outputs into one page the user can open in a browser and share: which assets need attention, when, and why.

Build the first version exactly as described here, so every user gets the same dashboard. Change it only when the user asks.

## Contents
- Offering it
- Inputs
- Output file
- Data blocks
- Values worked out in the page
- Page layout
- Visual rules
- Wording
- Variants by journey
- Parent and child assets
- Check before handing it over

---

## Offering it

Once Step 12's results have been shown, ask: *"Would you like a dashboard of these results? It's a single page you can open in a browser or share, with a fleet view, a ranking of assets, and a drill-down into each asset."*

If the user says yes, ask these questions in one round. Say what the default is for each:

| Question | Default |
|---|---|
| A short name for the fleet, e.g. "Conveyor fleet" or "Class 450 trains" | Taken from `asset_context` |
| Should all scored assets be included, or only some? | All |
| Are the assets parts of larger machines, e.g. carriages of a train? If yes, how do we know which parent each belongs to? (see "Parent and child assets") | No parents |
| Which alert bands should it use? | The watch and high levels already agreed after Step 12. If none were agreed, run "Checking alert bands against failures" (`validation.md`) now, propose the two levels and confirm them before building |
| Should any odd assets be left out? List assets with very few scored buckets (e.g. fewer than 5) or IDs that don't look like the rest (e.g. a test or placeholder ID) | Keep them |
| Are there known gaps to list on the page? | The gaps found in the validation checks during this run |

## Inputs

Read everything from the run's artifact folders. Don't recalculate any risk value (see `agent-execution.md` → "Scores come from the API only").

| File | Where it comes from | Used for |
|---|---|---|
| `risk_scores.parquet` | Step 12 | All risk values: `operational_risk`, `<system>_system_risk`, `<system>-<subsystem>_calibrated_risk` |
| `accepted_hierarchy.json` | Step 12 | System and subsystem names |
| `model_config.json` | Step 12 | Expert weights from labelling (`system_weights`, `subsystem_weights`) |
| `trained_weights.json` | Step 10 *(supervised)* | Learned weights |
| `supervised_training_report.json` | Step 10 *(supervised)* | AUC-ROC and average precision for expert (`baseline_*`) and learned (`supervised_*`) weights, `n_failures_used`, `n_positive_rows`, `n_total_rows`, `prediction_horizon`, `exclusion_after` |
| The failures file | The user *(supervised)* | Failure markers, plus checking whether alerts caught them |
| Alert bands and their reasons | "After Step 12" checks | Watch and high cut-offs |
| `weights_source` | Step 11 | Which weights the scores used |

## Output file

- Write one self-contained `.html` file to the Step 12 artifact folder, named `<fleet_name>_risk_dashboard.html` in lower case with underscores. It needs no server, and all data is inside the file.
- Put the data inside the page as CSV blocks: `<script type="text/csv" id="ds-<name>">…</script>`.
- Draw the charts with d3 v7.9.0. By default, load it from `https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js`; the page then needs internet access to draw. If the user needs it to open fully offline (e.g. on-premise), paste the library into the page. Use no other libraries.
- Build the page with a script that fills a template, and keep both next to the HTML so the dashboard can be rebuilt after the next scoring run.
- If your environment can publish or preview HTML pages, offer that as well. The file is still the deliverable.
- Keep the page under 10 MB. If the subsystem block would push it over, drop its rows where `calibrated_risk` is 0. The drivers chart still lists every subsystem, treating a missing row as 0.

## Data blocks

Use these names and columns. Round risk values to 1 decimal place.

| Block | Columns | Contents |
|---|---|---|
| `ds-daily` | `asset_id, date, operational_risk, <system>…` | One row per asset per scored bucket. The system columns are the `<system>_system_risk` columns, renamed to the system name. For a sub-daily model use `period_start` (ISO `YYYY-MM-DDTHH:MM`) in place of `date`. |
| `ds-subsys` | `asset_id, date, system, subsystem, calibrated_risk` | Long form of the `_calibrated_risk` columns (split the column name on the first `-`). |
| `ds-failures` | `asset_id, failure_date` | Every failure in the file, ISO dates. Leave the block empty if unsupervised. |
| `ds-bands` | `band, cutoff, basis` | Rows `watch` and `high`. Add a row `sdk_tuner` if `plot_detection_roc` was run. `basis` is one plain sentence on how the cut-off was chosen. |
| `ds-eval` | `metric, expert_weights, learned_weights` | Rows `AUC-ROC` and `Average precision` *(supervised only)*. |
| `ds-facts` | `failures_used, pre_failure_buckets, training_buckets, warning_window, exclusion` | From the training report *(supervised only)*. |
| `ds-weights` | `system, subsystem, expert_weight, learned_weight` | One `(system)` row per system holding the system weight, then its subsystems. Leave `learned_weight` empty if unsupervised. |
| `ds-hierarchy` | `asset_id, parent_id, parent_label` | Only when assets have parents. |
| `ds-meta` | JSON (`<script type="application/json">`) | `fleet_name`, `period_label`, `journey` (e.g. "fixed-log, supervised"), `weights_used` (`expert` or `learned`), `prediction_horizon`, `part_word` and `parent_word` (e.g. "carriage", "train"; omit without parents), `made_on`, and `known_gaps` (a list of sentences). |

## Values worked out in the page

Work these out in the page's script from the blocks above. They summarise the API's scores and never replace them.

- **Asset summary**, one row per asset:
  - mean, 90th percentile and peak `operational_risk`, and the date of the peak; if the peak is tied, take the first date and show "first of N";
  - buckets scored, buckets at watch or above, and buckets at high or above;
  - failures before the scored period, inside it, and within one `prediction_horizon` after its end (their warning windows overlap the scored data).

  Sort by mean, highest first.
- **Fleet figures**: assets scored, buckets scored, fleet median, which assets reached high on any bucket, the highest peak among the other assets, the overall peak with its asset and date, buckets at watch and at high, and the first and last dates.
- **Failure check** *(supervised)*: one row per failure inside the scored period or within one `prediction_horizon` after its end. Mark the latter "after the period". Each row has:
  - the highest risk in the `prediction_horizon` before the failure;
  - the first bucket at watch and the first at high within 2 × `prediction_horizon` before it;
  - days of high warning, which is the failure date minus the first high date, or 0 if there was none.

  Count only scored buckets.
- **Weight shares**: for each subsystem, system weight × subsystem weight, for the expert and the learned weights.

## Page layout

Keep this order. Each section has an `id` so it can be linked to.

1. **Header (`overview`)**
   - Title: `<Fleet name> risk, <period>`. Write the period as a full quarter ("Q1 2024") only when it covers the whole quarter. Otherwise use the month or month range ("Sep 2025", "Jul–Aug 2025").
   - One takeaway sentence built from the fleet figures, e.g. *"ASS-003, ASS-007 and ASS-011 reached the high band (40+) on 46 asset-days this quarter, while no other asset peaked above 39.6. Each had repeat failures in 2023 and failed again this quarter."*
     - If more than 3 assets reached high, name the 3 with the most high buckets and add "and N others".
     - The failure clause names the assets that failed in the period (or just after it). Say "each" only if it is true of every named asset, and leave the clause out if nothing failed.
2. **Four tiles**
   - Assets that reached high, listing which ones and out of how many.
   - Fleet median risk, with the date range.
   - Highest risk, with its asset and date.
   - Buckets at watch, with how many of those were high and out of how many scored.
3. **Fleet (`fleet`)**
   - **Heatmap**: one row per asset, ordered as in the ranking, and one cell per date.
     - Mark recorded failures with a 2px outline in the foreground colour; a red fill would vanish on red cells. Outline the selected asset's whole row, not a single cell.
     - Leave days with no logs empty. Give every scored cell, including 0, a faint edge so it can't be mistaken for an empty day.
     - Clicking a cell opens that asset and day in the asset section. Empty days aren't clickable.
     - Add a legend running from 0 to the high band.
     - Note under the title, with this run's bands in place of 35 and 40: *"Grey is normal, amber is watch (35+), red is high (40+). Outlined cells are days a failure was recorded. Blank cells are days with no logs."*
   - **Ranking table**: Asset (with a Watch or High tag for the highest band reached), Average risk (with an in-cell bar scaled 0–100), 90th percentile, Peak, Peak day, buckets at watch, buckets at high, failures before the period, failures in the period, failures just after.
     - Colour the risk cells with the heatmap's scale. Clicking a row opens that asset.
4. **Asset detail (`asset`)**
   - The heading names the selected asset. A drop-down lists assets as `<asset> · avg <mean>`.
   - Default: the top-ranked asset, on its peak day. Picking another asset selects its peak day too.
   - **Operational risk over time**: a line chart from 0 to 100.
     - Dashed reference lines at watch and high, and a solid red line labelled "failed <date>" at each failure.
     - Break the line over days with no logs; don't connect across them.
     - Hovering shows the overall and per-system values. Clicking a day selects it.
   - **Risk by system**: small multiples, one row per system on a 0–100 scale, sharing the time axis.
     - Show the selected day's value at the right of each row. Mark the selected day and any failures with lines.
   - **What drove the selected day**: horizontal bars of `calibrated_risk` for every subsystem on that day.
     - Sort highest first, colour by system, and show values.
     - Note: *"100 means activity at or above the subsystem's calibrated threshold."*
5. **About the model (`model`)**
   - **Failure check table** *(supervised)*: asset, failure date, highest risk in the warning window before it, first watch bucket, first high bucket, days of high warning.
     - Above the table, a note giving the band cut-offs, the SDK tuner's cut-off if there is one, and how many failures the bands were judged on. Warn if that is fewer than 5.
   - **Ranking quality** *(supervised)*: the evaluation table, expert against learned, with which weights were used marked.
     - Note giving how many failures and pre-failure buckets it was measured on.
     - Always say the figures are optimistic, because the training report evaluates on the data the model was trained on.
   - **Expert vs learned weights** *(supervised)*: a dot plot of each subsystem's share of the score.
     - An open marker for expert, a filled marker for learned, joined by a line. Group the rows by system.
     - If a system's learned weight is 0, all its subsystems get a 0% share. Say in the note that the model gave that system no weight.
   - **Known gaps**: a bulleted list, as agreed with the user.
     - Typical entries:
       - unclassified log codes and codes counting toward the wrong subsystem (from the Step 8 audit, if available);
       - subsystems and systems given zero weight;
       - scores existing only for buckets with logs;
       - in-sample evaluation;
       - bands based on fewer than 5 failures.
     - If something couldn't be checked with the files available, say so rather than leaving it out.
6. **Footer**: one line naming the data period, the journey (fixed-log or free-text, supervised or unsupervised), which weights were used, and the date the page was made. Add *"All data is embedded in this file."*

## Visual rules

- **Colour tokens**: define all colours as CSS variables on `:root`.
  - Add a dark-mode set under `prefers-color-scheme: dark`, repeated under `:root[data-theme="dark"]`. A `:root[data-theme="light"]` override must force light mode.
  - The page needs an explicit background.
- **Risk colour scale** (heatmap, ranking and failure check): a single scale with stops at 0 (the card colour), 20 (muted grey), watch (amber) and high (red), clamped above high. The scale follows the run's bands; never use fixed 33/66 bands.
- **System colours**: give each system its own categorical colour, in `accepted_hierarchy.json` order, and use it everywhere that system appears.
- **Markers**: in line charts, failures are solid red lines and the selected day is a line in the foreground colour. In the heatmap, failures are outlined as above.
- **Names**: show system and subsystem names with underscores replaced by spaces.
- **Numbers**: tabular figures; risk to 1 decimal place; weight shares as percentages.
- **Interaction**: every chart has a hover tooltip with exact values. The asset and day selection is shared across all the charts on the page and isn't saved anywhere.
- **Layout**: works at phone width with no sideways scrolling; tables scroll inside their own card.

## Wording

- Plain language for an operations reader. Say "risk", "watch", "high", "failure"; avoid "quantile", "calibration", "positive rows" outside the model section. The exception is the drivers note's "calibrated threshold".
- Every chart gets a one- or two-sentence note saying how to read it.
- Never use the word "notebook".
- Use dates without times for daily models. For sub-daily models, write times as `Mar 4 14:00`.

## Variants by journey

| Situation | Change |
|---|---|
| Unsupervised | Leave out the failure markers, the failure-check table, the ranking-quality table and the learned weights. Show the weights used as a single bar chart. Base the bands on the score distribution and say so in `basis`. Leave out the failure clause in the takeaway. |
| Supervised, scored with expert weights | Keep the weight comparison, but mark expert as the weights used. |
| Free-text | In the drivers card, add a short list of the logs from `classified_logs.parquet` behind the top subsystem on the selected day, at most 10. |
| Sub-daily model | Heatmap and ranking use each asset's highest value per day, and the notes say so. The trend and system charts plot every bucket. The drivers chart works on the selected bucket. |
| More than 40 rows in the heatmap (assets, or parents when there are parents) | The heatmap shows the 25 highest-ranked rows, plus any row with a failure in the failure check. Say so in its note. The ranking table still lists every row. |

## Parent and child assets

Some fleets are machines made of parts, such as a train with 2–5 carriages, where each carriage is an `asset_id` with its own scores. Check whether that applies.

**Getting the mapping.** In order of preference:
1. A column in the log file holding the parent ID (e.g. `train_id`).
2. A mapping file from the user with `asset_id, parent_id`.
3. A pattern in the IDs, e.g. `T12-C3` → `T12`.

For any of these, show the user a summary before building: how many parents there are, the smallest and largest number of children, any parent with a single child, and any child IDs that don't look like the rest. Get it confirmed. For a pattern, show the whole mapping.

Assets without a parent stay as their own row. Store the result as `ds-hierarchy`.

If the systems in `accepted_hierarchy.json` don't fit the kind of machine the user describes, say so before building, e.g. baggage-scanner systems on a "train" fleet.

**Rolling up.** A parent's risk on a day is the **highest** risk among its children that day, and the page records which child that was. Use the highest so that one failing carriage isn't hidden by healthy ones. Label every parent value "worst carriage" (or the user's word for the part).

Don't sum or average risks into a new score. The children's own values remain the API's scores.

**Layout changes:**
- **Tiles and takeaway** count parents ("trains") first, then the children involved, e.g. *"Trains T03 and T07 reached high on 12 days, driven by carriages T03-C2 and T07-C4."*
  - The median tile uses carriage buckets, labelled as such. A median of daily maxima overstates typical risk.
  - The fourth tile counts parent-days at watch and high, then the carriage-day figures.
  - With many parents, follow the takeaway rule above: name the top 3 parents and the carriages that drove them.
- **Heatmap**:
  - One row per parent, coloured by the worst child.
  - Clicking a parent's label expands its children's rows underneath; clicking a cell opens the parent and day.
  - The tooltip names the child that drove the cell.
- **Ranking**: parents ranked on their rolled-up values, each expandable to its children.
  - Add a column "Worst carriage" naming the child with the highest average.
  - Show the carriage that set the parent's peak next to "Peak day". It can differ from the worst carriage.
- **Asset detail**: pick a parent, then show:
  - Operational risk over time with one line per child, in a neutral grey scale. The worst child on the selected day is in the foreground colour, with the others muted, and its name is in the legend.
  - A child selector that controls "Risk by system" and "What drove the selected day".
    - It resets to the worst child on the selected day whenever the parent or day changes from the heatmap, ranking or trend chart.
    - A child picked by hand stays selected until the parent changes.
    - Clicking a child's heatmap cell selects that child.
  - Hovering the trend chart lists each child's overall risk on that day, highest first.
- **Failures**:
  - A failure recorded against a child marks that child and its parent.
  - A failure recorded against the parent marks only the parent. The failure check then uses the parent's rolled-up value, and the note says so.

## Check before handing it over

- Open the page and look at it, using a browser or screenshot tool if you have one. Confirm:
  - every section has rendered,
  - there are no console errors,
  - it works in both light and dark mode.
- Compare at least three numbers with `risk_scores.parquet`: the overall peak with its asset and date, one asset's mean, and the number of buckets at high.
- Check the takeaway sentence and the tiles against the ranking table.
- Then give the user the file path. Summarise in two or three sentences what the dashboard shows, and ask whether they want any changes.
