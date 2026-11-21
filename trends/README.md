# IPA service-ticket trends (recurring notebook)

Reruns the service-ticket analysis on fresh exports. It reports **unplanned tickets per 100 installed
machine-months** by issue (request group and Category), for every reporting period, broken down by **install
cohort** (machines installed in different date ranges), product family and model. Each run:

- compares the latest complete period with the previous 12 months and calls out changes conservatively;
- lists install cohorts that stand out;
- writes a PDF report to attach, a self-contained HTML report, short email text and CSV tables for the Product
  Insights Dashboard.

**The rerun frequency is a free parameter.** `RERUN_FREQUENCY` is how often the notebook is rerun and the length of
each reporting period: `'quarterly'` (default), `'monthly'`, or any whole number of months (`'2 months'`, `'6
months'`, `'annual'`). Everything else follows from it: period edges, labels, baselines, wording and due dates.

`METHOD.md` gives every definition and the statistics. The definitions are copied verbatim from the analysis IPA
has already seen, and the engine reproduces its numbers (see *Reconciliation*).

## Who does what

| Who | What |
|---|---|
| IPA analyst (Product & Customer Service analytics) | Exports two files each cycle, runs the notebook, reviews the result and sends it |
| Distribution list | Reads `report.pdf` and the email summary; runs nothing |
| Product Insights Dashboard | Reads `data/output/latest/*.csv`, refreshed by each run |

## One-time setup (about 15 minutes)

You need Python 3.11 or later.

```bash
cd trends
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip install -r requirements.txt
.venv/bin/pip install -e .                       # adds the ipa-trends command
.venv/bin/python -m ipykernel install --user --name python3
ipa-trends selftest --quick                      # runs the test suite on synthetic data (no IPA data needed)
```

**Save the Salesforce report once** (a "Details Only" report of cases, all record types and **all statuses**,
exported as .xlsx by a user whose Salesforce time zone is **US Eastern**). It needs these columns:

- **Required:** Case Number, Account Name, Serial #, Date/Time Opened, Case Record Type, Status, Trouble Code,
  Trouble Code Category, Trouble Reported.
- **Recommended:** Trouble Code Sub Category, Trouble Closed Date/Time, Model #.
- The other columns of the usual export are ignored.

Filter on Date/Time Opened from at least 24 months before the latest period (15 months is the minimum for a full
baseline) up to the last complete day.

**The equipment list** is IPA's "Equipment list - Monthly Report". Required columns: Serial Number, Account Name,
Model, Product Family, Service Plan, Install Date. Recommended: Service Status, Shipping Country, Go Live Date.

**Before the first real run**, check the file layout without printing any values:

```bash
ipa-trends inspect
```

## Each cycle (quarterly or monthly; about 10 minutes of hands-on time)

1. About **two weeks after the period ends**, once late Category labels have settled, save into
   `trends/data/raw/`:
   - the case report, as `IPA_CaseHistory_<YYYY-MM-DD>.xlsx`;
   - that month's equipment list, as `IPA_Active_Equipment_list_<YYYY-MM-DD>.xlsx`. **Keep the earlier equipment
     lists in the folder**: they let the run account for machines that were removed.
2. Open `ticket_trends.ipynb` in Jupyter or VS Code. The first code cell holds the parameters; normally nothing
   changes. To switch cadence, edit one line: `RERUN_FREQUENCY = 'monthly'`.
3. **Run All.** Within a few minutes the notebook shows:
   - the latest period and the fleet rate against its baseline;
   - flagged changes and install cohorts that stand out;
   - the charts;
   - data-quality notes, and when the next run is due.
4. Read the data-quality notes. A period that is too fresh is marked *provisional* and reported in the next run.
5. If "Ready to distribute" says yes, attach `data/output/latest/report.pdf` and paste
   `data/output/latest/email_summary.txt` into an email to the distribution list. A Power Automate flow can do this
   instead (see *Sharing*).
6. The dashboard picks up `latest/*.csv`. `data/output/runs/<run_id>/` keeps every run.

The same run without Jupyter:

```bash
ipa-trends run                                    # defaults, or:
ipa-trends run --params params/quarterly.yaml     # a copy of params/quarterly.example.yaml
ipa-trends run --set RERUN_FREQUENCY=monthly
ipa-trends run --engine notebook                  # executes the notebook headless and saves it with the run
```

With papermill: `papermill ticket_trends.ipynb out.ipynb -p RERUN_FREQUENCY monthly` (or `-f params/monthly.yaml`).

## Changing the cadence

Change only `RERUN_FREQUENCY`.

- **Quarterly** (default) holds about three times the tickets per cell of monthly, so it can test more Categories
  and detect smaller changes.
- **Monthly** reacts faster but calls out only larger changes; each run writes the smallest detectable change per
  cell.
- **Fiscal year:** set `YEAR_START_MONTH` (10 for October).
- **Other lengths:** any whole number of months works, and periods are counted from a fixed anchor so their edges
  never move between runs.

To see when runs are due:

```bash
ipa-trends next-runs                    # e.g. quarterly: due 15 Jan, 15 Apr, 15 Jul, 15 Oct (cron: 0 7 15 1,4,7,10 *)
ipa-trends next-runs --set RERUN_FREQUENCY=monthly
```

## Parameters

Set them in the notebook's parameters cell, in a YAML/JSON file (`--params`, or papermill `-f`), or one at a time
(`--set NAME=VALUE`, or papermill `-p`). A misspelt name stops the run with a "did you mean" suggestion. Relative
paths are read from the trends folder (or `BASE_DIR`, or the `IPA_TRENDS_HOME` environment variable).

**Cadence**

| Parameter | Default | What it does |
|---|---|---|
| `RERUN_FREQUENCY` | `'quarterly'` | how often this is rerun = length of each period: 'quarterly', 'monthly', '2 months'... |
| `YEAR_START_MONTH` | `1` | first month of the reporting year (10 for an October fiscal year) |
| `FISCAL_YEAR_NAMED_BY` | `'end'` | 'end': the year starting Oct 2026 is FY2027 |
| `ANCHOR_DATE` | `None` | 'YYYY-MM-DD' a date that starts a period, for unusual calendars |
| `PERIOD_EDGES` | `None` | explicit period edges ['YYYY-MM-DD', ...] (overrides RERUN_FREQUENCY) |
| `LATEST_PERIOD` | `None` | report an earlier final period as the latest (back-runs); never overwrites latest/ |
| `BASELINE_MONTHS` | `None` | months of baseline before the latest period (default: 12, or one period if longer) |
| `HISTORY_MONTHS` | `None` | months of history in the charts (default: 24, or three periods if longer) |
| `LABEL_LAG_DAYS` | `14` | days after a period ends before it counts as final (Categories are filled at close) |
| `MAX_OPEN_SHARE` | `0.02` | a period with more of its tickets still open stays provisional |
| `MAX_BLANK_CATEGORY_SHARE` | `0.05` | above this share of blank Categories (or twice the typical share), issue-level comparisons skip the period |
| `MAX_UNMAPPED_SHARE` | `0.05` | above this share of unmapped tickets, affected groups are not tested |

**Inputs (relative paths are read from the trends folder)**

| Parameter | Default | What it does |
|---|---|---|
| `CASE_EXPORTS` | `'data/raw/IPA_CaseHistory_*.xlsx'` | case report(s) from Salesforce (.xlsx); the newest match is used |
| `CASE_SHEET` | `'ipa_repair cases'` | sheet holding the cases (if missing and only one other sheet exists, that one is read) |
| `EQUIPMENT_LISTS` | `'data/raw/IPA_Active_Equipment_list_*.xlsx'` | every equipment-list snapshot (Monthly Report); keep them all |
| `EQUIPMENT_SHEET` | `'Equipment list - Monthly Report'` | sheet holding the equipment list |
| `EQUIPMENT_LIST_DATES` | `{}` | {'file name': 'YYYY-MM-DD'} for lists whose file name has no date |
| `EXTRACTED_AT` | `None` | 'YYYY-MM-DD' the case report was exported (default: the workbook's created date) |
| `DATA_START` | `None` | 'YYYY-MM-DD' first day the export covers (default: the first ticket's day) |
| `DATA_END` | `None` | 'YYYY-MM-DD' last day the export covers (default: the last ticket's day) |
| `COLUMN_ALIASES` | `{}` | {'renamed header': 'expected header'} if IPA renames a column |
| `CATEGORY_ALIASES` | `{}` | {'new Category name': 'old Category name'} so a renamed Category keeps its series |
| `REQUEST_TYPES_LOCAL` | `None` | CSV adding new Trouble Code x Category combinations to the request groups |
| `UNMAPPED_POLICY` | `'separate'` | 'separate': unmapped combinations form their own, never-tested group |
| `CASE_CLOCK_TZ` | `'America/New_York'` | time zone of the case times in the export (US Eastern for IPA) |
| `DATE_FORMAT` | `None` | e.g. '%m/%d/%Y %I:%M %p' when dates are stored as text (default: detected) |
| `BASE_DIR` | `None` | folder relative paths are read from (default: the trends folder) |
| `OUTPUT_DIR` | `'data/output'` | where runs are written (runs/<run_id>/ and latest/) |

**Breakdowns**

| Parameter | Default | What it does |
|---|---|---|
| `STRATIFY_BY` | `['install_cohort', 'family', 'model']` | breakdowns: 'install_cohort', 'family', 'model', 'age_group', 'service_status', ... |
| `CATEGORY_DIMS` | `['fleet', 'install_cohort']` | breakdowns that also get Category-level rates |
| `INSTALL_COHORT_WIDTH` | `'1 year'` | width of install cohorts: '1 year', '6 months', 'quarterly'... |
| `INSTALL_COHORT_START` | `'2016-01-01'` | first cohort start; earlier installs are pooled ('Before 2016') |
| `INSTALL_COHORT_EDGES` | `None` | explicit cohort edges ['2016-01-01', '2019-01-01', ...] (overrides the width) |
| `MODEL_FILTER` | `None` | only these models (reconciliation) |
| `POOL_SMALL_STRATA` | `True` | pool models with too few machines into one "Other models" series |
| `MIN_TYPE_MONTHS` | `100` | machine-months a model needs over 396 days for its own series (100 = 7.7 machines) |
| `MIN_CELL_MONTHS` | `100` | cells with fewer machine-months are shown hollow |
| `THIRD_PARTY_PLANS` | `['Vogeltronix']` | service plans whose service does not reach the case export (excluded) |
| `MISSING_INSTALL_DATE` | `'exclude'` | 'exclude' machines without an install date, or 'data_start' |

**Call-outs (conservative screening flags)**

| Parameter | Default | What it does |
|---|---|---|
| `Q_CUT` | `0.05` | false-discovery rate for a flag |
| `WATCH_Q` | `0.2` | false-discovery rate for the watch list (report only) |
| `MIN_CHANGE` | `0.2` | smallest change worth flagging (0.20 = 20%) |
| `MIN_CONTRAST` | `0.5` | smallest cohort difference worth calling out (0.50 = 50% higher) |
| `CONTRAST_MONTHS` | `12` | months of final periods in the install-cohort comparison |
| `MIN_EXPECTED` | `10` | fewest expected tickets in the latest period for a test |
| `MIN_BASELINE_TICKETS` | `20` | fewest baseline tickets for a test |
| `MIN_ACCOUNTS` | `10` | fewest accounts with baseline tickets for a test |
| `TAU2_FLOOR` | `0.001` | smallest between-period variance assumed (log scale) |
| `N_BOOT` | `2000` | bootstrap draws (2000 as in the analysis IPA saw) |
| `SEED` | `15072` | random seed (15072 as in the analysis IPA saw) |
| `COHORT_MAP_ISSUES` | `'auto'` | 'auto' or a list of issue names for the cohort charts |

**Outputs**

| Parameter | Default | What it does |
|---|---|---|
| `MAKE_CHARTS` | `'auto'` | 'auto': charts when matplotlib is installed |
| `MAKE_REPORT` | `True` | write report.html, report.pdf and the email text |
| `REPORT_TITLE` | `'IPA service-ticket trends'` | title of the report and email |

## Outputs (`data/output/latest/` and `data/output/runs/<run_id>/`)

**Every table row carries** `schema_version`, `run_id`, `rerun_frequency`, `method_version` and
`definitions_hash`.

**The dashboard key** is (`rerun_frequency`, `period_start`, `stratum_dim`, `stratum_key`, `issue_level`,
`issue_group`, `issue`). Every run restates past periods (labels arrive late, lists change), so **replace, never
append**. Column types are in `schema.json`.

| File | What it holds |
|---|---|
| `rates_final.csv` | The dashboard feed: final periods only, every breakdown × issue (tickets, machine-months, average installed machines, rate per 100, 95% interval) |
| `rates.csv` | The same for every period, with its status (partial, in progress and provisional periods included) |
| `changes.csv` | The latest period against its baseline, cell by cell: ratio, interval, q-value, status, reason when not tested, smallest detectable change, sentence |
| `cohort_contrasts.csv` | Install cohorts over the last 12 months: rate; ratios to the rest of the fleet, to newer and to older installs, and to earlier installs at the same age; status, sentence |
| `periods.csv` | The reporting grid: status and reason, open and blank-Category shares |
| `data_quality.csv` | Per-period counts: planned, cancelled, duplicate, open, unlisted, unmapped |
| `strata.csv` | Which models were pooled; cohort date ranges |
| `unmapped.csv` | Trouble Code × Category combinations missing from the reference |
| `report.html`, `report.pdf` | The report (the PDF is the attachment to send) |
| `email_summary.txt`, `.html` | Paste-ready email text, at most 15 lines |
| `charts/*.png` | Fleet trend, request groups, cohort profile, cohort × period map, changes, data quality |
| `manifest.json` | Parameters, input fingerprints, warnings, checks, privacy scan totals, `distribution_ready`, `next_run_after` |

## Sharing

Nothing is sent automatically, and no email credentials live in the code. Pick one:

- **A. By hand (recommended for the first cycles).** Review `report.html`, then email `report.pdf` with the text of
  `email_summary.txt`. Many Microsoft 365 tenants block .html attachments, so send the PDF.
- **B. Power Automate.** Keep `OUTPUT_DIR` in a OneDrive or SharePoint folder. A flow triggers when
  `latest/manifest.json` changes, reads `distribution_ready` and `run_id` (to avoid duplicates), and sends the PDF
  and summary to the list or posts them in Teams. Runs are staged outside `OUTPUT_DIR` and copied in only after
  every check and the privacy scan pass, so the flow never sees a half-written run.
- **C. Dashboard.** Point Power BI at `latest/rates_final.csv` (and the other tables).

## Scheduling (optional)

The manual cycle above is the main process, because the Salesforce export is done by hand. To automate the run
itself, schedule it daily with `--only-if-new`: it skips the run until the inputs change. This works for any
frequency, including ones a calendar can't express, such as every 5 months.

```bash
ipa-trends run --params params/quarterly.yaml --only-if-new
```

- **Windows:** use Task Scheduler. Keep the input and output folders on a local or network drive, not cloud-only
  OneDrive files.
- **Linux/macOS:** use cron, for example `0 7 * * *`.

## When something is wrong

**Exit codes:** 0 OK or skipped; 1 a runtime check or the privacy scan failed; 2 an input or parameter problem;
3 unexpected.

An unexpected error's traceback goes to a private log on the computer, never to the console, notebook or output
folder. A failed run writes only `failed/<stamp>/error.txt` (code and stage).

| Code | Meaning | Fix |
|---|---|---|
| E01 | No input file matches, it is not .xlsx, or it cannot be opened (old .xls, encrypted, still downloading) | Save as .xlsx in `data/raw/`; check `CASE_EXPORTS` / `EQUIPMENT_LISTS` |
| E02 | The named sheet is missing and the workbook has several other sheets | Set `CASE_SHEET` / `EQUIPMENT_SHEET` |
| E03 | No header row in the first 10 rows, a required column is missing, or two columns read as the same | The message gives the closest header and a ready `COLUMN_ALIASES` line |
| E04 | The same Case Number twice with different contents | Export again |
| E05 | Dates that cannot be read, or a column mixing month-first and day-first text dates | Fix the cells or set `DATE_FORMAT` |
| E06 | A serial listed twice in one equipment list | Remove the duplicate rows |
| E07 | `request_types_v0.csv` was edited | Restore it; put additions in `REQUEST_TYPES_LOCAL` |
| E08 | A `REQUEST_TYPES_LOCAL` file is missing, malformed, or redefines a reference row | Local rows may only add new combinations |
| E09 | An equipment list's date is unknown, or two lists share a date | Put the date in the file name or set `EQUIPMENT_LIST_DATES` |
| E10 | Over 0.5% of rows have no Case Number or Serial # | Check the export's columns |
| E20 | `RERUN_FREQUENCY` / `INSTALL_COHORT_WIDTH` not recognised (weeks, pandas aliases, out of range) | Use `'quarterly'`, `'monthly'` or `'N months'` |
| E21 | `ANCHOR_DATE` after the 28th | Choose day 1 to 28 |
| E22 | Unknown or invalid parameter | The message suggests the right name or value |
| E24 | No reporting period overlaps the data | Check `PERIOD_EDGES` and the export dates |
| E25 | `LATEST_PERIOD` is not a final period, or `BASELINE_MONTHS` is shorter than a period | Use a label from `periods.csv` |
| E30 | A file in `latest/` is locked (open in Excel, OneDrive) | Close it and run again |
| E31 | `OUTPUT_DIR` is inside a git repository and not ignored | Move it outside, or under `data/` |
| C01 | A runtime check failed (numbers would not add up) | Send the code and manifest to the MIT team |
| P01 | The privacy scan found a real identifier in an output | Send the field names (not the contents) to the MIT team |
| E99 | Unexpected error | Send the code and stage, not the private log |

| Warning | Meaning |
|---|---|
| W01 | Tickets outside `DATA_START`..`DATA_END` were left out |
| W03 | **Blocking.** A month has under 20% of the usual case rows (incomplete export?) |
| W04 | Trouble Code × Category combinations missing from the reference (see `unmapped.csv`); affected groups may go untested |
| W07 | The newest equipment list is much older or newer than the case data |
| W08 | Machines without (readable) install dates were left out |
| W09 | Unknown Status (treated as open) or Case Record Type values. **Blocking** at 10 or more record-type tickets, which could be planned work |
| W10 | Rows without a Case Number, Serial # or Account Name |
| W11 | No monitoring-template tickets in the latest period (template wording changed?) |
| W12 | Many weekday tickets before 06:00: the export may not be on US Eastern time |
| W13 | Dates stored as text (read with one detected format) |
| W14 | Between-period variation could not be estimated; a conservative default is used |
| W15 | No final period yet, or not enough baseline periods: nothing is compared |
| W16 | Identical duplicate rows were dropped |
| W17 | Serials that would match the list only if case or leading zeros were ignored |
| W18 | The named sheet was missing; the only other sheet was read |
| W19 | Several case exports match; the newest was used |
| W20 | Report title or footer rows were skipped |
| W21 | Opened times in the repeated daylight-saving hour (non-Eastern exports) |
| W22 | Machines without Account Name, Model or Product Family were grouped as such |
| W23 | Machines dropped off a later equipment list; their exposure ends midway |
| W24 | The export date is before the last ticket; the last ticket date was used |
| W25 | Tickets fall outside `PERIOD_EDGES` |
| W26 | **Blocking.** No recent ticket is still open: the export may be filtered to closed cases |

## Privacy

- Outputs hold only period, model, family, install cohort, age and issue labels with counts and rates. They never
  hold account names, sites, serials, case numbers or pseudonyms.
- Real strings are read into memory for matching, the account bootstrap and the privacy scan.
- The scan checks every table, the manifest, chart text, the report, the email and any executed notebook before
  anything is published.
- Keep `trends/data/` out of version control (`trends/.gitignore` does this) and restrict access to `OUTPUT_DIR`.
- Commit `ticket_trends.ipynb` only without outputs.

## For the MIT team

**Reconcile** with the numbers IPA has seen, on the original two files. The output is counts only and safe to paste
back:

```bash
ipa-trends reconcile --params params/reconcile_2025-08_2026-08.yaml [--deep]
```

**Tests:**

```bash
python -I tests/run_tests.py
python -I tests/test_parity.py           # MIT repository only
```

**Keep the copied definitions in step with `verification/`:**

```bash
python -I tests/sync_definitions.py
python -I tests/sync_definitions.py --write   # after changing verification/
```

**After changing the reconciliation targets:** `python -I tests/build_reference.py`.

**After changing a parameter:** `python -I tests/make_notebook.py`, to regenerate the notebook's parameters cell.
