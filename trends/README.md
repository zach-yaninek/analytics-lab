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

You need Python 3.11 or later. Open a terminal in the folder that holds `trends`, then create a virtual environment
(`.venv`) inside `trends`, activate it, and install the package into it.

**Windows** (Command Prompt):

```bat
cd trends
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python -m ipykernel install --user --name python3
ipa-trends selftest --quick
```

**macOS and Linux:**

```bash
cd trends
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -m ipykernel install --user --name python3
ipa-trends selftest --quick
```

- `pip install -e .` adds the `ipa-trends` command to the environment.
- `ipykernel install` makes the notebook's kernel (`python3`) run in this environment.
- `ipa-trends selftest --quick` runs the test suite on synthetic data (no IPA data needed). It takes several minutes.
- On Windows, if `python` is not found, use `py -m venv .venv`. In PowerShell, `.venv\Scripts\activate` runs a
  script that the execution policy often blocks: use Command Prompt instead.

**Activate the environment in every new terminal** before any `ipa-trends`, `pip` or `jupyter` command:
`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on macOS and Linux (run in the `trends` folder).
The prompt then starts with `(.venv)`. Every command below assumes it.

**Start Jupyter from the environment:** activate it, then run `jupyter lab` (or `jupyter notebook`) in the
`trends` folder; Jupyter opens in your browser, and `ticket_trends.ipynb` is in its file list. In VS Code, open the
`trends` folder and choose the `.venv` environment (or the `python3` kernel) when the notebook asks for a kernel.

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
2. Open `ticket_trends.ipynb` in Jupyter (`jupyter lab`, started from the activated environment) or VS Code. The
   first code cell holds the parameters; normally nothing changes. To switch cadence, edit one line:
   `RERUN_FREQUENCY = 'monthly'`.
3. **Restart & Run All** (Jupyter: Kernel menu; VS Code: Restart, then Run All). A plain Run All keeps the names
   left from earlier runs, so a name you have corrected would still stop the run. Within a few minutes the notebook
   shows:
   - the latest period and the fleet rate against its baseline;
   - flagged changes and install cohorts that stand out;
   - the charts;
   - data-quality notes, and when the next run is due (always after the export date; a period already due but with
     too many tickets still open is listed as needing a newer export).
4. Read the data-quality notes. A period that is too fresh is marked *provisional* and reported in the next run.
5. If "Ready to distribute" says yes, attach `data/output/latest/report.pdf` and paste
   `data/output/latest/email_summary.txt` into an email to the distribution list. A Power Automate flow can do this
   instead (see *Sharing*). After a back-run (`LATEST_PERIOD`), `latest/` is unchanged: send the files from the run
   folder the notebook names.
6. The dashboard picks up `latest/*.csv`. `data/output/runs/<run_id>/` keeps every run.

The same run without Jupyter (in a terminal with the environment activated):

```bash
ipa-trends run                                    # defaults, or:
ipa-trends run --params params/quarterly.yaml     # a copy of params/quarterly.example.yaml
ipa-trends run --set RERUN_FREQUENCY=monthly
ipa-trends run --engine notebook                  # runs the notebook headless, scans it, then publishes the run with it
```

**To keep an executed notebook, use `ipa-trends run --engine notebook`.** The notebook then only stages its run.
The command line scans the executed notebook, and only then publishes the run and saves the notebook as
`runs/<run_id>/executed_notebook.ipynb` of that run, never in `latest/`. `BASE_DIR` and every parameter set in the
parameter file or with `--set` are passed to the notebook. A back-run (`LATEST_PERIOD`) leaves `latest/` unchanged
with either engine, and the notebook and console say so.

papermill can run the notebook too, but the notebook then publishes its run itself, and the copy papermill writes is
not scanned. Write it outside `OUTPUT_DIR`, under a name git ignores, and do not share it:
`papermill ticket_trends.ipynb ticket_trends.executed.ipynb -p RERUN_FREQUENCY monthly` (or `-f params/monthly.yaml`).

## Changing the cadence

Change only `RERUN_FREQUENCY`.

- **Quarterly** (default) holds about three times the tickets per cell of monthly, so it can test more Categories
  and detect smaller changes.
- **Monthly** reacts faster but calls out only larger changes; each run writes the smallest detectable change per
  cell.
- **Fiscal year:** set `YEAR_START_MONTH` (10 for October).
- **Other lengths:** any whole number of months works, and periods are counted from a fixed anchor so their edges
  never move between runs.
- **Explicit periods** (a 4-4-5 calendar, say): set `PERIOD_EDGES` to the period edges. The wording then says
  'period' ('the previous four periods', 'Report (custom periods)'), and the baseline is the explicit periods that
  start in the `BASELINE_MONTHS` (12) before the latest one, and at least the one just before it.
  `RERUN_FREQUENCY` still names the run and keys the dashboard. Runs with explicit edges name no next run, and
  `ipa-trends next-runs` lists `RERUN_FREQUENCY`'s periods, not the explicit ones.

To see when runs are due:

```bash
ipa-trends next-runs                    # e.g. quarterly: due 15 Jan, 15 Apr, 15 Jul, 15 Oct (cron: 0 7 15 1,4,7,10 *)
ipa-trends next-runs --set RERUN_FREQUENCY=monthly
```

## Parameters

Set them in the notebook's parameters cell, in a YAML/JSON file (`--params`, or papermill `-f`), or one at a time
(`--set NAME=VALUE`, or papermill `-p`). Parameter names are written in capitals. A misspelt name, or a parameter
name in the wrong case (`rerun_frequency`, also as papermill `-p rerun_frequency monthly`), stops the run with E22
and the right spelling; papermill only warns about a name that is both misspelt and in lower case. In Jupyter a name
you have since corrected stays in memory until the kernel restarts, so use Restart & Run All. Relative paths are
read from the trends folder (or `BASE_DIR`, or the `IPA_TRENDS_HOME` environment variable). A relative `--params`
path is read from the current folder, then from the trends folder.

In a YAML parameter file, write a Windows path in single quotes or with forward slashes:
`OUTPUT_DIR: 'C:\Users\me\OneDrive - IPA\Trends\output'` or `OUTPUT_DIR: C:/Users/me/OneDrive - IPA/Trends/output`.
In double quotes a backslash starts an escape sequence: the file is then refused with E22, which gives the line and
column, or, for `\t` and `\n`, the path silently changes. Text holding a colon or `#` needs quotes too:
`REPORT_TITLE: 'IPA: quarterly trends'`. On the command line, `--set` keeps text as typed:
`--set "REPORT_TITLE=IPA: quarterly trends"`.

**Cadence**

| Parameter | Default | What it does |
|---|---|---|
| `RERUN_FREQUENCY` | `'quarterly'` | how often this is rerun, and the length of each period: 'quarterly', 'monthly', '2 months' |
| `YEAR_START_MONTH` | `1` | first month of the reporting year (10 for an October fiscal year) |
| `FISCAL_YEAR_NAMED_BY` | `'end'` | 'end': the year starting Oct 2026 is FY2027 |
| `ANCHOR_DATE` | `None` | 'YYYY-MM-DD' a date that starts a period, for unusual calendars |
| `PERIOD_EDGES` | `None` | explicit period edges ['YYYY-MM-DD', ...] in place of RERUN_FREQUENCY's periods (the wording then says 'period') |
| `LATEST_PERIOD` | `None` | report an earlier final period as the latest (a back-run): its label or start date ('2026 Q2', '2026-04-01'); never changes latest/ |
| `BASELINE_MONTHS` | `None` | months of baseline before the latest period (default: 12, or one period if longer) |
| `HISTORY_MONTHS` | `None` | months of history on the time charts, always with the baseline and latest period (default: 24, or three periods if longer) |
| `LABEL_LAG_DAYS` | `14` | days after a period ends before it counts as final (Categories are filled at close) |
| `MAX_OPEN_SHARE` | `0.02` | a period with more of its tickets still open stays provisional |
| `MAX_BLANK_CATEGORY_SHARE` | `0.05` | above this share of blank Categories (or twice the typical share), issue-level comparisons skip the period |
| `MAX_UNMAPPED_SHARE` | `0.05` | above this share of unmapped tickets, affected groups are not tested |

**Back-runs.** `LATEST_PERIOD` reports an earlier final period as if it were the latest; take its label or start date
(`period_key`) from `periods.csv`. The run goes to `runs/<run_id>/` only, so `latest/` and the dashboard keep the
regular run. A back-run names no next run (`next_run_after` is null), and with `--engine notebook` its executed
notebook is filed under its own run.

**`HISTORY_MONTHS`** limits only the time charts: every table keeps every period.

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
| `CATEGORY_ALIASES` | `{}` | {'new Category name': 'old Category name'}: for a renamed or split Category, so its series and tests continue |
| `REQUEST_TYPES_LOCAL` | `None` | CSV adding genuinely new Trouble Code x Category combinations to the request groups (not for a renamed or split Category) |
| `UNMAPPED_POLICY` | `'separate'` | 'separate': unmapped combinations form their own, never-tested group |
| `CASE_CLOCK_TZ` | `'America/New_York'` | time zone of the case times in the export (US Eastern for IPA) |
| `DATE_FORMAT` | `None` | e.g. '%m/%d/%Y %I:%M %p' when dates are stored as text (default: detected) |
| `BASE_DIR` | `None` | folder relative paths are read from (default: the trends folder) |
| `OUTPUT_DIR` | `'data/output'` | where runs are written (runs/<run_id>/ and latest/) |

**A renamed or split Category** (W04 or W27): map each new name to the old one in `CATEGORY_ALIASES`, so the series
and its tests continue. Adding the new names to `REQUEST_TYPES_LOCAL` instead would hold back the Category-level
tests of that Trouble Code's groups until the whole baseline uses the new names.

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
| `MIN_TYPE_MONTHS` | `100` | machine-months a model needs over 396 days for its own series (100 means 7.7 machines) |
| `MIN_CELL_MONTHS` | `100` | cells with fewer machine-months keep their rate, with meets_min_exposure False; the cohort map leaves them blank |
| `THIRD_PARTY_PLANS` | `['Vogeltronix']` | service plans whose service does not reach the case export (excluded) |
| `MISSING_INSTALL_DATE` | `'exclude'` | 'exclude' machines without an install date, or 'data_start' |

**Call-outs (conservative screening flags)**

| Parameter | Default | What it does |
|---|---|---|
| `Q_CUT` | `0.05` | false-discovery rate for a flag |
| `WATCH_Q` | `0.2` | false-discovery rate for the watch list (report only) |
| `MIN_CHANGE` | `0.2` | smallest change worth flagging (0.20 means 20%) |
| `MIN_CONTRAST` | `0.5` | smallest cohort difference worth calling out (0.50 means 50% higher) |
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
| `PRIVACY_ALLOW` | `[]` | names the privacy scan lets through although a real field holds them too (a model word that is also a city); never account names or numbers |

`PRIVACY_ALLOW` is only for genuine collisions found after a P01 (see *Privacy*).

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
| `changes.csv` | The latest period against its baseline, cell by cell: ratio, interval, q-value, status, reason when not tested, smallest detectable change, sentence. `baseline_labels`, `baseline_periods_used` and `baseline_set` ('all', or 'labels' for issue-level rows, which leave out periods with incomplete Category labels) name each row's own baseline; `sustained` and `previous_status` compare it with the period before. An untested cell's sentence gives its rate and the reason, never a change |
| `cohort_contrasts.csv` | Install cohorts over the last `CONTRAST_MONTHS` (12) months of final periods. Each row names its own window in `window_label` (issue-level rows leave out periods with incomplete Category labels). Columns: rate; ratios to the rest of the fleet, to newer and to older installs, and to machines of the same age in other cohorts (over the whole history); `position` (oldest, interior, newest, too_new, undated); status, basis and sentence (not-tested rows give only the rate and the reason) |
| `periods.csv` | The reporting grid: status and reason, open and blank-Category shares |
| `data_quality.csv` | Per-period counts: planned, cancelled, duplicate, open, unlisted, unmapped |
| `strata.csv` | Which models were pooled; cohort date ranges |
| `unmapped.csv` | Trouble Code × Category combinations missing from the reference |
| `report.html`, `report.pdf` | The report (the PDF is the attachment to send) |
| `email_summary.txt`, `.html` | Paste-ready email text, at most 15 lines |
| `charts/*.png` | Fleet trend, request groups, cohort profile, cohort × period map, changes, data quality. The time charts (fleet trend, request groups, cohort × period map, data quality) show the last `HISTORY_MONTHS` months. The changes chart shows the fleet and its request groups, then other flagged or watch-list cells, fleet-wide first, at most 15 rows, keeping one row for each flagged direction. Data quality marks the run's own blank-Category limit. Hollow markers and bars are periods that are not final yet |
| `manifest.json` | Parameters (absolute paths shortened to their last folder), input fingerprints, warnings, checks, privacy scan totals, `distribution_ready`, `next_run_after` (the next run's due date, after this export's date; null for back-runs and explicit `PERIOD_EDGES`) |
| `executed_notebook.ipynb` | Only in `runs/<run_id>/`, and only with `--engine notebook`: the executed notebook, after its privacy scan |

`OUTPUT_DIR` also holds `failed/<stamp>/error.txt` for each run that stopped (see *When something is wrong*) and,
for a moment while `latest/` is replaced, `latest.new/` or `latest.old/`.

## Sharing

Nothing is sent automatically, and no email credentials live in the code. Pick one:

- **A. By hand (recommended for the first cycles).** Review `report.html`, then email `report.pdf` with the text of
  `email_summary.txt`. Many Microsoft 365 tenants block .html attachments, so send the PDF.
- **B. Power Automate.** Keep `OUTPUT_DIR` in a OneDrive or SharePoint folder. A flow triggers when
  `latest/manifest.json` changes, reads `distribution_ready` and `run_id` (to avoid duplicates), and sends the PDF
  and summary to the list or posts them in Teams. Runs are staged outside `OUTPUT_DIR` and copied in only after
  every check and the privacy scan pass. `latest/` is then replaced as a whole: a complete copy (`latest.new/`) is
  renamed into place and the old one (`latest.old/`) removed, and `latest/manifest.json` is written last, as a new
  file. So the flow never sees a half-written run or a mix of two runs, and a back-run, which leaves `latest/`
  alone, does not trigger it. Because the folder is replaced, OneDrive or SharePoint version history for the files
  in `latest/` starts again with each run; `runs/<run_id>/` keeps every run. This has not yet been tried on
  SharePoint itself.
- **C. Dashboard.** Point Power BI at `latest/rates_final.csv` (and the other tables).

## Scheduling (optional)

The manual cycle above is the main process, because the Salesforce export is done by hand. To automate the run
itself, schedule it daily with `--only-if-new`: it skips the run until the inputs change. This works for any
frequency, including ones a calendar can't express, such as every 5 months.

A scheduled task starts in another folder and without the virtual environment, so call `ipa-trends` by its full
path inside `.venv`:

- **Windows:** in Task Scheduler, create a daily task whose action is *Start a program*, with
  - *Program/script*: `C:\path\to\trends\.venv\Scripts\ipa-trends.exe`
  - *Add arguments*: `run --params params\quarterly.yaml --only-if-new`
  - *Start in*: `C:\path\to\trends`

  A relative `--params` path is also looked for in the trends folder, so the file is found even if *Start in* is
  left empty (the task then starts in System32); a full path such as `C:\path\to\trends\params\quarterly.yaml` works
  too. To keep the console output, set *Program/script* to `cmd.exe` and *Add arguments* to
  `/c .venv\Scripts\ipa-trends.exe run --params params\quarterly.yaml --only-if-new >> run.log 2>&1`, with *Start in*
  as above. Keep the input and output folders on a local or network drive, not cloud-only OneDrive files.
- **macOS and Linux:** a crontab line such as

  ```bash
  0 7 * * * cd /path/to/trends && .venv/bin/ipa-trends run --params params/quarterly.yaml --only-if-new >> run.log 2>&1
  ```

A run that stops exits with a non-zero code (Task Scheduler shows it as the task's *Last Run Result*) and leaves
`OUTPUT_DIR/failed/<stamp>/error.txt` (see *When something is wrong*). Git ignores `run.log`, which can name local
folders.

## When something is wrong

**Exit codes:** 0 OK or skipped (`--only-if-new`); 1 a runtime check (C01) or the privacy scan (P01) failed; 2 an
input, parameter or output-folder problem (E01-E10, E20-E25, E30, E31); 3 unexpected (E99).
`ipa-trends run --engine notebook` exits with the code of the error the notebook stopped on.

**What a run that stops leaves.** It writes `OUTPUT_DIR/failed/<stamp>/error.txt` with the code, the stage, the exit
code and the package version (never the message or any cell value), and the console or notebook names the file.
This holds for every coded error once `OUTPUT_DIR` can be read from the parameters, with two exceptions: nothing is
written for E31, or when `OUTPUT_DIR` is inside a git repository that does not ignore it; the console says so
instead. (In the notebook, a misspelt parameter name stops it before the run starts, so only the notebook shows that
error.) With `--engine notebook`, the executed notebook is kept beside `error.txt` when its outputs pass the privacy
scan. When they cannot be scanned (for example, the inputs are missing), it stays in a private temporary folder
whose path is printed; delete it once you have looked at it. After a P01 it is deleted. Nothing reaches `latest/`
before every check and the privacy scan pass, and `latest/` is then replaced as a whole, so a run that stops leaves
it as it was. If `latest/` itself cannot be replaced (E30, a locked file), the message says what was and was not
updated.

**Unexpected errors.** An unexpected error's traceback goes to a private log on this computer, never to the console,
notebook or output folder. The log is a new file that only you can read, in the folder `ipa_trends_logs_<user>` of
the temporary folder, which only you can open (`<user>` is your user name on Windows, your user id elsewhere). If
the log cannot be written, E99 says so and still shows only the error's type.

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
| E22 | Unknown, misspelt or wrong-case parameter, an invalid value, or a parameter file that is missing or not valid YAML or JSON | The message gives the right name (`RERUN_FREQUENCY`, not `rerun_frequency`) or value, or the file's line and column. In the notebook, after correcting a name, use Restart & Run All |
| E24 | No reporting period overlaps the data | Check `PERIOD_EDGES` and the export dates |
| E25 | `LATEST_PERIOD` is not a final period of this run, or `BASELINE_MONTHS` is shorter than a period | Use a label or start date (`period_key`) from `periods.csv`; leave `BASELINE_MONTHS` empty or make it longer |
| E30 | `OUTPUT_DIR` could not be written: a file in `latest/` or `runs/<run_id>/` is open (Excel, OneDrive) or read-only, or the disk is full. `latest/` is replaced as a whole, so it normally still holds the previous run; the message says what was and was not updated (and, if `latest/` could not be put back, that the previous run is in `latest.old/`) | Close the file and run again |
| E31 | `OUTPUT_DIR` is inside a git repository and not ignored | Move it outside, or under `data/` |
| C01 | A runtime check failed (numbers would not add up) | Send the code and manifest to the MIT team |
| P01 | The privacy scan found a real identifier in an output (with `--engine notebook`, also in the executed notebook) | Send the field names (not the contents) to the MIT team; a model or Category word that equals a one-word city, location or note can be listed in `PRIVACY_ALLOW` |
| E99 | Unexpected error | Send the code and stage, not the private log |

| Warning | Meaning |
|---|---|
| W01 | Tickets outside `DATA_START`..`DATA_END` were left out |
| W03 | **Blocking.** A month has under 20% of the usual case rows (incomplete export?) |
| W04 | Trouble Code × Category combinations missing from the reference (see `unmapped.csv`); affected groups may go untested. For a renamed or split Category, map each new name to the old name in `CATEGORY_ALIASES` so its series continues; use `REQUEST_TYPES_LOCAL` only for genuinely new combinations |
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
| W26 | **Blocking.** None of the tickets opened in the 14 days before the export date is still open: the export may be filtered to closed cases (every case row counts, whatever `DATA_END` says; not judged with fewer than 30 such tickets) |
| W27 | A Category appeared in or disappeared from the latest period against the baseline: the Category-level tests of the groups it belongs to were held back, and the group totals were still tested. For a renamed or split Category, map each new name to the old one in `CATEGORY_ALIASES` |

## Privacy

- Outputs hold only period, model, family, install cohort, age and issue labels with counts and rates. They never
  hold account names, sites, serials, case numbers or pseudonyms.
- Real strings are read into memory for matching, the account bootstrap and the privacy scan.
- The scan checks every table, the manifest, chart text, the report and the email before anything is published.
  The executed-notebook scan applies only to `ipa-trends run --engine notebook`, which publishes nothing until the
  notebook's outputs pass it too. A notebook saved from Jupyter, or written by papermill, is not scanned: keep such
  copies out of shared folders. Any executed notebook also shows the run's full folder paths (its parameters cell
  holds `BASE_DIR`), which can include your user name; the manifest shortens such paths, the notebook does not.
- A one-word real string (a city, location or credentialing note) that equals a word the package writes itself, or a
  Trouble Code, Category or request group of the request-type reference or `REQUEST_TYPES_LOCAL`, is not counted on
  its own; account names and multi-word names are. Labels from the data (models, families, Categories outside the
  reference) never exempt anything, so a city typed into the Model column stops publication with P01. If a model or
  Category word genuinely equals such a string (a Location 'Remote' and the model LVD-Remote-2.0), list it in
  `PRIVACY_ALLOW`; an account name always counts, listed or not. The executed notebook is scanned with the same
  words.
- Keep `trends/data/` out of version control and restrict access to `OUTPUT_DIR`. `trends/.gitignore` ignores
  `data/`, spreadsheets and CSV files, parameter files other than the examples, executed notebooks (every `.ipynb`
  file but `ticket_trends.ipynb`), `.venv/` and log files.
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
python -I tests/test_units.py            # the unit tests alone (seconds)
python -I tests/test_parity.py           # MIT repository only
```

**Keep the copied definitions in step with `verification/`:**

```bash
python -I tests/sync_definitions.py
python -I tests/sync_definitions.py --write   # after changing verification/
```

**After changing the reconciliation targets:** `python -I tests/build_reference.py`.

**After changing a parameter, its comment in `config.COMMENTS`, or the notebook text in `tests/make_notebook.py`:**
`python -I tests/make_notebook.py`, to regenerate the notebook (a unit test checks that the committed notebook equals
the generated one). The parameter tables above copy `config.DEFAULTS` and `config.COMMENTS`; update them too.
