# Method: IPA service-ticket trends

This document states every definition the trend notebook uses, where it comes from, and how the statistics work.
It is written for IPA's analytics team and for anyone checking the numbers. `README.md` explains how to run it.

## 1. What is measured

**The rate.** Unplanned tickets per 100 installed machine-months:

> rate = 100 × unplanned tickets ÷ installed machine-months

It is computed for every reporting period, for every issue, and for each breakdown: install cohort, product family
and model (others are available).

| Term | Definition | Source in the analysis IPA saw |
|---|---|---|
| Unplanned ticket | Every case except planned work (Trouble Code *Preventative Maintenance* or *Installation*, or record type *Install Case*), cancelled requests and duplicate cases. No Trouble Found and monitoring tickets stay in. | Zac's `service_cases` view (`verification/common.py: CASE_VIEWS`), copied verbatim |
| Installed machine-month | One machine on IPA's equipment list for 30.4375 days (365.25 / 12) | `verification/fleet_exposure.py: machine_frame`, F2 |
| Population | Machines on the equipment list(s), except those on a third-party service plan (*Vogeltronix*, whose service does not reach the case export) and, by default, those with no install date | fleet_exposure F1 |
| Ticket's machine | The ticket's serial matched exactly (after trimming) to the equipment list; tickets on serials that are not listed drop out with their unknown exposure | fleet_exposure F1 |
| Account | The machine's account **on the equipment list**, so the numerator and the denominator use the same account | fleet_exposure F1 |
| Request group | One of 10 groups from Trouble Code × Category (Door, Mechanical, Electronics, Network, Software, Operator error, Other, No Trouble Found, Monitoring, Not categorised), from the frozen reference `request_types_v0.csv`; a monitoring-template ticket is in Monitoring whatever its Category | `verification/followups.py: assign_request_types`, docs/09 §3.3, copied verbatim |
| Category level | Categories under the seven component groups; Monitoring and blank-Category tickets are left out | followups Part A A1 rule (L708) |
| Monitoring template | Trouble Reported begins with the help desk's proactive-monitoring header | `verification/flags.py: monitoring_template`, copied verbatim |
| Age band | Years from install date to the midpoint of the machine's exposure in the period, cut at 1, 2, 4, 6, 8 and 10 | fleet_exposure `age_band` |
| Install cohort | The install date's bin; the width is a parameter (`INSTALL_COHORT_WIDTH`, one year by default), anchored like the periods; installs before `INSTALL_COHORT_START` are pooled | new; the follow-ups' cohorts (2016-18 … 2024-26) are reproduced with `INSTALL_COHORT_EDGES` |

The definitions are copied byte for byte (node by node) from the scripts that produced the numbers IPA has seen,
into `ipa_trends/definitions/`. In the MIT repository, `tests/sync_definitions.py` and `tests/test_parity.py` check
that the copies still equal their sources and that the engine reproduces their results machine by machine.

## 2. Reporting periods for a free frequency

`RERUN_FREQUENCY` is the only cadence setting. It is how often the notebook is rerun **and** the length of every
reporting period: any whole number of months, from 1 to 24. Quarterly is the default and monthly the alternative,
as proposed to IPA. Periods shorter than a month are refused: weekly cells hold too few tickets to tell a change
from noise.

**Edges.** Period edges are counted from a fixed anchor, so they do not move between runs: the 1st of
`YEAR_START_MONTH` (January by default; 10 for an October fiscal year), or `ANCHOR_DATE`. Each period is
[start, end), midnight to midnight on the case clock (US Eastern, as in the original analysis). `PERIOD_EDGES`
replaces the grid with explicit dates (4-4-5 calendars, reconciliation).

**Labels.** `Aug 2026`, `2026 Q2`, `FY2027 Q1`, `2026 H1`, `2026`, or a range such as `Jun-Aug 2026` for other
lengths. Tables carry the ISO start and end dates as keys.

**Statuses.** Each period gets one of four statuses.

| Status | Rule |
|---|---|
| partial | Starts before the export's first day; computed on the days it covers |
| in_progress | Ends after the export's last day; computed on the days it covers |
| provisional | Ended less than `LABEL_LAG_DAYS` (14) before the export was taken, or more than `MAX_OPEN_SHARE` (2%) of its tickets were still open |
| final | Everything else |

Only final periods are compared or used as baselines.

- **When the export was taken.** `EXTRACTED_AT` defaults to the workbook's *created* date, then to the file's
  modification date. It is never inferred from the last ticket, so a report filtered to the quarter's end still
  makes that quarter final.
- **Open tickets.** Tickets whose Status is not one of Trouble Closed, Ricoh-Closed, Closed or Case Closed count as
  open.

The 14-day lag comes from docs/04 §5.2: Trouble Code and Category are filled in near close, and in the reference
export 54 of the 122 tickets opened in the last 7 days were still open and unlabelled.

**Labels complete enough.** Some tickets are genuinely never categorised: 0.5–3.4% a month in the reference export
after its first two months. The gate therefore looks for labels missing beyond the usual level. A period is left
out of issue-level baselines, and of tests when it is the latest period, when more of its unplanned tickets have a
blank Category than `MAX_BLANK_CATEGORY_SHARE` (5%) or twice the typical (median) share, whichever is higher. In the
reference export, Category was blank on 16.2% of tickets in Aug 2025 and 9.0% in Sep 2025, so both are left out.

## 3. Exposure per period

This is fleet_exposure's rule, generalised from the whole period and its two halves to any grid.

- **Start.** max(first day of the data, min(install date, first ticket)). A ticket before the listed install date
  starts the exposure, because the list's install date is the install at the current account.
- **End.** The day after the data for machines on the newest equipment list. For a machine that drops off a later
  list, the end is midway between its last listing and its first absence, or the day after its last ticket if that
  is later.
- **Machine-months.** Machine-months in a period are whole days ÷ 30.4375 inside it. Edges fall at midnight, so a
  machine's months summed over the periods equal its whole-window months exactly; every run checks this.
- **Age band in a period.** Taken at the midpoint of the machine's exposure in that period.

**The equipment ledger.** IPA's equipment list is a monthly report of the machines active on its date. Machines
removed earlier are missing, so their tickets drop out. The share of tickets on unlisted serials falls from 11% in
Aug 2025 to 1% in Aug 2026, which would build a false upward trend into older periods. Every snapshot kept in the
input folder therefore enters a ledger, so a removed machine keeps its exposure up to its removal. With one
snapshot this is exactly the original rule. Each period's unlisted share is reported in `data_quality.csv`.

**Runtime checks.** Every run stops, publishing nothing, if any of these fails:

- months add up over periods;
- every ticket falls in exactly one period;
- breakdowns add up to the fleet;
- request groups add up to all tickets;
- a group's non-Monitoring tickets equal its Categories plus its blank-Category tickets;
- tickets on listed, third-party and missing-install machines add up.

## 4. Rates and intervals

Every cell goes through the copied `fleet_exposure.group_rates`, so its 95% interval follows the committed rule.

- The default is an account cluster bootstrap: accounts are resampled with replacement, 2,000 draws, seed 15072,
  in the account order of the original pseudonyms. Tickets cluster within accounts, so this is the interval to
  read.
- A cell in fewer than 10 accounts, or with no tickets, takes the wider of the bootstrap and Byar's Poisson
  interval.

**Pooling small models.** A model gets its own series when it averages at least 7.7 installed machines over the
data window, or over the latest final period. That is 100 machine-months over the original 396-day window, as in
fleet_exposure. The second condition means a fast-growing new model is not hidden. The rest are pooled into
"Other models"; `strata.csv` lists them.

**Small cells.** A cell with fewer than `MIN_CELL_MONTHS` (100) machine-months is kept but drawn hollow.

## 5. Install cohorts (the primary lens)

The cohort view is how the Touchscreen problem was found: 2022-23 installs had 1.54 Touchscreen tickets per 100
machine-months, 3.9 times the 2024-26 rate (`verification/outputs/followups/ag_install_pooled.csv`). The decisive
feature was a **peak**: those cohorts sat above both older and newer installs.

**What each run shows**

- **The cohort profile:** rates by install cohort over the last `CONTRAST_MONTHS` (12) of final periods.
- **The cohort × period map:** how each install-date range's rate moves at the chosen frequency.
- **Four comparisons for every cohort × issue:**
  - the **crude ratio**: the cohort's rate over the rest of the fleet's rate;
  - **newer / older**: the cohort's rate over the rate of every cohort installed after it, and before it;
  - the **same-age ratio**: the cohort against machines of the same age band in other cohorts, over the whole
    final history (bands where the other cohorts have fewer than 100 machine-months are left out of both sides).

  Each gets a paired account-bootstrap interval and p-value.

**When a cohort stands out (higher)**

| Cohort | Rule |
|---|---|
| Interior (has older and newer installs) | At least 1 + `MIN_CONTRAST` (1.5×) the rest of the fleet, **and** at least 1.25× both the newer and the older installs |
| Newest | At least 1.5× both the rest of the fleet and earlier installs observed at the same age |
| Oldest, pooled ('Before …'), or 'Unknown' | Shown but never called out |

In addition, all of the cohort's comparisons must be beyond chance together. The call-out's p-value is the largest
of their p-values (an intersection-union test), and one Benjamini–Hochberg correction runs over every cohort × issue
cell (q below 0.05). At least 10 tickets must be expected, and the window's Category labels must be complete.
'Lower' is the mirror image.

**Why this rule**

- **Why a peak.** A steady age effect cannot produce a peak, whether rates rise or fall with machine age: a cohort
  in the middle of such a trend lies between its newer and older neighbours. Two neighbouring cohorts can both stand
  out, because each is compared with all newer and all older installs.
- **Why not the same-age ratio alone.** Within one year of data, machines of the same age come from neighbouring
  install years (docs/10). A two-year block such as 2022-23 is then its own comparison: on the synthetic fixture the
  same-age ratios of the planted 2022 and 2023 cohorts were only 1.5 and 1.2, against crude ratios of 2.8 and 2.7.
  The same-age ratio is therefore reported for context and decides only for the newest cohort.
- **What it achieves.** On the synthetic fixture, exactly the planted Touchscreen cohorts (and their Electronics
  group) stand out. With no planted effect, nothing does.

*Persisting* marks a cohort that also stood out in the window ending one period earlier.

## 6. Time-trend call-outs (conservative flags)

Each cell compares the latest final period L with the pooled final baseline B: the periods in the 12 months
before L, or one period if periods are longer.

**The ratio**

- E_L = rate_B × machine-months_L × f_L ÷ f̄_B
- ratio = O_L ÷ E_L

This is the **crude** rate ratio. It is not standardised for age or model mix; the cohort, family and model
breakdowns show the mix instead. The only adjustment is the **business-day factor** f: a weekend or US-federal-
holiday day is weighted by its ticket rate relative to a business day, estimated from the baseline's fleet tickets.
f̄_B weights the baseline periods by the cell's machine-months. Without it, a month with 23 business days would
look 15% busier than one with 20. Published rates are not adjusted, and the unadjusted ratio is written too.

**The variance:** Var(log ratio) = V_boot + τ² (1 + 1/K).

- **V_boot** comes from the paired account bootstrap: the same draws reweight L and B. A ½-ticket continuity
  correction is used.
- **τ²** is the between-period variance beyond sampling noise, estimated by DerSimonian–Laird and pooled within a
  family ("head": all tickets and request groups; "category").
  - It is estimated on the final periods before L at the run's own length when there are at least 6 of them,
    otherwise on monthly periods, unscaled (conservative for longer periods).
  - Standardised residuals are winsorised at ±3, so a one-month spike cannot inflate it.
  - It is floored at `TAU2_FLOOR`.
  - The latest period never enters its own yardstick.
- **K** is the number of baseline periods.

**When a cell is tested.** All of these must hold:

- L is final, and the baseline has at least half its periods;
- at least 10 tickets are expected;
- the baseline has at least 20 tickets from at least 10 accounts;
- the issue is a real issue, not *Not categorised* or *Unmapped*;
- the data-quality gates pass, applied **equally to L and B**:
  - Category labels are complete enough;
  - there is no taxonomy change. If Trouble Code × Category combinations missing from the reference reach more
    than 5% of a Trouble Code's tickets in L (a split or renamed Category), the groups that Trouble Code maps to
    are not tested. When the Trouble Code fixes the group (Electronics, Network, Software, Operator Error), only
    that group's Category-level tests are suspended.

**One Benjamini–Hochberg correction** runs over every tested cell in the run.

**Statuses**

| Status | Rule |
|---|---|
| higher / lower | q < 0.05 and the ratio is at least 20% away from 1. An increase must also survive the **survivorship check**: putting back the tickets on serials missing from the equipment list, with their least possible exposure (fleet_exposure's bound), must still leave the interval above 1 and the increase at least 20%. Otherwise it becomes a watch item, with the reason given. |
| watch_higher / watch_lower | q < 0.20 and at least 20% away from 1 (report only) |
| no_clear_change | Tested; neither of the above |
| not_tested | With the reason |

**Sustained** marks a change also flagged, or on watch, in the same direction for the previous period against its
own baseline.

A lasting step is flagged when it starts. In later runs, the trailing baseline gradually takes in the higher level,
so the flag fades while the trend charts and `rates.csv` keep showing the new level. On the synthetic fixture, a
Deposit Door rise starting in July is flagged in the quarterly run for Q3. At monthly cadence it would be flagged
for July; September, whose baseline already includes July and August, is not.

**Wording.** Nouns follow the cadence ("the previous four quarters", "beyond normal month-to-month variation").
The word "significant" is never used. A flag is a screening flag for follow-up, not proof of a problem. Each run
also writes every cell's smallest detectable change (80% power, before the correction): monthly cells need larger
changes than quarterly ones.

## 7. Data-quality warnings

Warnings are written to `manifest.json` and shown in the report. **Blocking** warnings set
`distribution_ready = false`, because the numbers may be wrong:

- W03: a month with under 20% of the usual case rows;
- W09: 10 or more tickets with an unknown record type;
- W26: no open tickets among recent ones (an export filtered to closed cases).

`README.md` lists every code with its fix.

## 8. What the numbers do not show

- **Mix.** Crude rates combine reliability with fleet age and model mix. Read the cohort, family and model
  breakdowns and the same-age contrast before attributing a change to reliability.
- **One equipment list.** Until several monthly lists accumulate, the equipment list is a single snapshot. Older
  periods then miss removed machines, and the survivorship check and the unlisted share are the guards.
- **Restated history.** Categories are filled near close, and lists change, so each run restates past periods.
  Dashboards should replace, never append.
- **Snapshot attributes.** Service status, plan and account are taken from the newest list for all periods.
- **New data, new numbers.** IPA's runs use newer exports. The Aug 2025–Aug 2026 numbers then move slightly away
  from those in the executive summary (6.16 per 100), as late labels arrive and the list changes.
- **Monthly runs.** A quarterly cell holds about three times the tickets of a monthly one, so monthly runs can
  test fewer Categories, and a change must be larger to be called out. Weekly runs are not supported.

## 9. Reconciliation

`ipa-trends reconcile` runs the engine on the original two files (case export Aug 2025–Aug 2026; equipment list of
19 Oct 2026). It checks the engine against the aggregates committed under `verification/outputs/`:

- the fleet totals, third-party and unlisted counts (`fx_summary.json`);
- rates and intervals by age band, family and model (`fx_age_rates.csv`, `fx_family_rates.csv`,
  `fx_model_rates.csv`);
- under-4 and 4+ rates by request group and Category, with intervals (`ag_type_rates.csv`);
- rates by age band (`ag_band_rates.csv`);
- the two halves;
- monthly ticket and unlisted counts;
- the definitions' fingerprints (request-type hash, 138 monitoring templates, 0 unmapped tickets);
- the install-cohort and install-year rates on the 15 support models (`ag_install_pooled.csv`).

Counts must match exactly. Machine-months, rates and intervals must match to a relative 1e-8. The output holds
counts and labels only.

## 10. Verification

`tests/run_tests.py` runs everything on synthetic data:

- hand-computed unit tests;
- every cadence, with the invariant that all cadences add up to the same totals;
- planted effects that must be flagged: a 2026 Q3 Deposit Door rise, an alEx Computer Board fall, and a
  Touchscreen ×3 on 2022-23 installs;
- a null fixture for false alarms;
- publishing: byte-identical reruns, and a planted leak that must stop publication;
- export-drift variants: title rows, a renamed header, a split Category, a renamed Trouble Code, a duplicate case,
  dates stored as text, mixed date formats, a Central-time export, a closed-only export, a report filtered to the
  quarter end, a one-month spike, removed machines and blank fields;
- the notebook run headless.

`tests/test_parity.py` (MIT repository) runs the engine against `verification/`.
