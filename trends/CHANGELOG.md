# Changelog

Any change to a definition (the copies in `ipa_trends/definitions/`, the request-type reference, the exposure or
interval rules) bumps the method version and must be followed by `ipa-trends reconcile` on the original files.

## 1.0.0 (2026-11, not yet released)

First release for IPA's Product & Customer Service analytics team.
- Unplanned tickets per 100 installed machine-months by request group and Category, per reporting period, by
  install cohort, product family and model.
- The rerun frequency is a free parameter: any whole number of months (quarterly by default, monthly as the
  alternative).
- Conservative time-trend call-outs (crude rate ratios adjusted for business days; account bootstrap plus
  between-period variance; one Benjamini-Hochberg correction; a 20% practical threshold; survivorship check;
  data-quality gates) and install-cohort contrasts. A cohort must form a peak against newer and older installs, also
  checked against machines of the same age once 24 months of history exist. The newest cohort with enough expected
  tickets is compared with the rest of the fleet and with machines of the same age, and newer, still-filling cohorts
  are shown but not compared.
- Outputs: CSV tables with a stable dashboard key, PNG charts, a self-contained HTML report, a PDF report, email
  text and a manifest; a privacy scan of everything before publication.
- Reconciliation against the committed analysis (fleet, age, family, model, request-type, band, halves, monthly,
  install-cohort and install-year numbers).

### Changes from the independent review (before release)

Nothing had been released, so the version stays 1.0.0. No copied definition, request-type reference, exposure rule
or rate-interval rule (group_rates) changed, so the method version stays 1.0, `rates.csv` is unchanged and the
reconciliation targets are unchanged. The change-ratio intervals in `changes.csv` do change, through the τ² estimate
below.

These method rules changed (`METHOD.md` gives each in full):
- **Install cohorts** (§5): positions are chosen per issue. The newest cohort is the newest with at least 10 expected
  tickets for the issue; the cohorts after it are 'too new' (shown, never compared). A cohort whose newer installs
  would expect fewer than 40 tickets is compared like the newest one (rest of the fleet and same age), so a problem
  on last year's installs is not lost when this year's cohort becomes testable. An interior cohort's peak must
  also be at least 1.25× machines of the same age in other cohorts once the final history spans 24 months (before,
  the same-age ratio decided only for the newest cohort). Each row is worded over its own window.
- **Taxonomy gate** (§6): a Category that appeared or vanished between the baseline and the latest period holds back
  the Category-level tests of its groups, which stay tested (new warning W27, which names them; when the new names
  are unmapped, W04 covers it). W04's fix now points to
  `CATEGORY_ALIASES`; `REQUEST_TYPES_LOCAL` is for genuinely new combinations only.
- **Between-period variance τ²** (§6): residuals are winsorised at ±3 total standard deviations (sampling plus
  between-period), iterated, instead of ±3 sampling standard deviations; series broken by a Category that appeared or
  vanished are left out.
- **Cells with no tickets in the latest period** (§6): the published ratio is the continuity-corrected one, inside
  its interval; a cell with nothing expected has no ratio.
- **Baselines with incomplete Category labels** (§6): each change is worded from its own baseline ('three of the
  previous four quarters (those with complete Category labels)'), and `changes.csv` names each row's baseline
  periods (`baseline_labels`, `baseline_set`). An untested cell's sentence gives only its rate and the reason.
- **Explicit periods** (§2): with `PERIOD_EDGES` the wording says 'period', and the baseline counts the explicit
  periods that start in `BASELINE_MONTHS`.
- **Next runs** (§2) are counted from the export date, never on or before it; a period already due but still
  provisional is listed as needing a newer export; a back-run names no next run.
- **W26** (§7, closed-only export) looks at the tickets opened in the 14 days before the export date, over every case
  row whatever `DATA_END` says, and is not judged with fewer than 30 of them.
- **Privacy scan** (§11): only trusted words (the package's own and the request-type labels) exempt a one-word real
  string; labels from the data are scanned, so a city typed into the Model column stops publication. New parameter
  `PRIVACY_ALLOW` for genuine collisions (never an account name or an identifier, letters included). The
  executed-notebook scan uses the same words, and the notebook `--engine notebook` files (in `runs/` or beside a
  failure record) leaves out the injected parameter values.

Other changes:
- **Failure handling:** a run that stops leaves `OUTPUT_DIR/failed/<stamp>/error.txt` (code, stage, exit code),
  except inside a git repository that does not ignore `OUTPUT_DIR`; exit codes follow the error class (1 C01/P01,
  2 E01-E31, 3 E99); an unexpected error's traceback goes to a private log only you can read; `latest/` is replaced
  as a whole, so a locked file (E30) leaves it as it was. The tests simulate Windows file locks; the swap has not yet
  been tried on Windows or on a SharePoint-synced folder.
- **Notebook engine:** `ipa-trends run --engine notebook` passes `BASE_DIR` to the notebook, scans the executed
  notebook before publishing, files it under its own run, and exits with the code of the error the notebook stopped
  on. Back-runs leave `latest/` unchanged with either engine, and the notebook says so.
- **Parameters:** a name in the wrong case stops the run (E22) with the right spelling; a name left from an earlier
  Run All gets a Restart & Run All hint; a relative `--params` path is also looked for in the trends folder; a
  malformed YAML or JSON file is E22 with the line and column (was E99); `LATEST_PERIOD` accepts a start date;
  `--set` keeps text values as typed.
- **Report:** `HISTORY_MONTHS` now limits the time charts. `data_quality.png` uses the run's blank-Category limit.
  `changes.png` lists fleet-level flags first and keeps each flagged direction. 'Not flagged' replaces 'No clear
  change', and titles say when changes with intervals excluding no change could still be chance. The cohort rule text
  matches the rule above and says whether the run's history is long enough. Sustained watch items read 'also on the
  watch list last quarter'. The request-group definition and the Category scope are corrected.
- **Reconciliation:** `reconcile --deep` compares missing age bands (machines without exposure) as equal; the
  summary names the targets whose intervals were compared (R2, R3), and the docs say that `ag_install_pooled.csv`'s
  intervals were made with another rule and are not compared.
- **Docs:** setup and scheduling commands that work as written on Windows and on macOS and Linux; `.gitignore` covers
  executed notebooks, `.venv/` and logs.
