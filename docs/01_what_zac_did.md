# What Zac did: walkthrough of the IPA Service Ticket SQL Analysis notebook

*Source:* `data/raw/IPA_Service_Ticket_SQL_Analysis.ipynb` (41 cells: 22 code, 19 markdown), with a plain-text dump in
`data/derived/notebook_dump.md`. This document describes the notebook. It does not judge whether the methods are
correct; other review documents cover that. Quoted numbers are Zac's printed outputs unless marked *(computed here)*.
Identifiers are the notebook's own pseudonyms (`Customer NNN`, `T#####`, `M#####`, `Host NNN`).

---

## 1. Overview

The notebook is titled "IPA Service Ticket Analysis — MIT A-Lab · 10 October 2026" (its manifest also records
`created: 2026-10-10`). It ran on Google Colab (Python 3.12.14). The code cells carry execution counts 1–22 in order,
so it was run top to bottom in one session. Its purpose is a midterm-ready descriptive analysis of IPA's service
workload, plus a check of whether a ticket can be linked to its machine's telemetry codes. It has three inputs: (1) the
Salesforce case export `IPA_CaseHistory_Aug 2025-Aug2026.xlsx` (only the sheet `ipa_repair cases` is read; the
`Summary` sheet is ignored), (2) the 17 GB telemetry SQLite database `ipa_transaction_events_202508_202608.db` (tables
`transaction_events`, `devices`, `transaction_codes`), and (3) a code-to-bucket lookup typed into the code, taken from
the team sheet "ALab (1), Classifying Failure Codes". It builds a pseudonymised working database
(`ipa_sql_outputs/analysis.sqlite`), answers 11 sub-questions in Parts 1–5, runs 14 reconciliation checks (Part 6.1),
and prints 7 candidate midterm findings and 5 open items. Every query result is saved as a CSV; it also saves 10 PNG
charts, a manifest, a blank pilot-review template and a findings text file.

---

## 2. Data pipeline (cells 1–9)

### 2.1 Sources and checksums (cells 1–2)
Cell 1 imports the libraries, sets the plot style and `SEED = 15072`, and creates the output folder `ipa_sql_outputs/`.
Cell 2 signs in to Google Drive, downloads the originals, and checks each one's SHA-256 before use:

| File | SHA-256 Zac expects | Notes |
|---|---|---|
| `IPA_CaseHistory_Aug 2025-Aug2026.xlsx` | `8ffdc2482ee1…084ff8` | The copy in this repo hashes to `f060f5810dc8…19646f`, which differs (see §6) |
| `ipa_transaction_events_202508_202608.db.gz` | `072be66f6e79…1f6b5a` | Download needs ≥20 GiB free disk |
| `ipa_transaction_events_202508_202608.db` (decompressed) | `7aa5d423bb38…2244d0` | Decompression needs ≥17 GiB free disk |

The printed result is "Verified original" for the workbook and the archive, followed by "Original workbook and full
atomic database verified; ready for read-only analysis."

### 2.2 Opening the database read-only (cell 4)
The source DB is opened with a SQLite URI `?mode=ro`, then `PRAGMA query_only=ON` and `PRAGMA cache_size=-200000`
(about 200 MB) are set. The file's size and `mtime_ns` are recorded at the start. Cell 8 compares them again at the end
and writes the result to the manifest as `source_database_unchanged`. All derived tables go to a separate SQLite file,
`ipa_sql_outputs/analysis.sqlite`.

### 2.3 Pseudonymisation (cell 4)
Every label comes from a deterministic sort. Python `sorted()` puts the distinct cleaned real values in ascending
string order, and each value gets a 1-based index. `clean()` strips whitespace and turns blank or `None` into `None`.
No salt or randomness is used. Anyone holding the raw files can therefore rebuild the map, and the labels keep the
sort order of the real identifiers.

| Label | Built from | Format | Count |
|---|---|---|---|
| `case_id` | cleaned `Case Number` (all rows) | `T00001`… | 7,471 |
| `customer` | distinct cleaned `Account Name` | `Customer 001`… | 845 |
| `machine_id` | **union** of `devices.external_device_id` and cleaned ticket `Serial #` | `M00001`… | not printed; 7,183 + 3,773 − 3,041 = 7,915 *(computed here from printed counts)* |
| `host` | distinct non-null `devices.clearview_url` (not stripped) | `Host 001`… | not printed |

The machine label depends on the telemetry device dictionary as well as the tickets. Without the DB,
`verification/common.py` gives ticket serials `S#####` labels, which do not match Zac's `M#####` numbers. The
`Customer` and `T` labels depend only on the workbook and do match. The identity maps stay in memory; a code comment
says "saved outputs use pseudonyms".

### 2.4 Derived working tables (cells 4, 6, 8)

| Table | Rows (cell 9) | Contents |
|---|---|---|
| `cases` | 7,471 | `case_id, customer, machine_id`; `opened_at`, `closed_at` (formatted `YYYY-MM-DD HH:MM:SS`, no time zone); `model, product, record_type, status, trouble_code, category, subcategory`; for each of Trouble Reported, Trouble Resolution and Administrative Notes, only a `_present` flag (0/1) and a `_length`. Free text, city/state/zip, country, Dispatch # and Case Owner are not carried over. |
| `devices` | 7,183 | `machine_id, device_status, machine_type_raw, machine_type` (lower-cased and stripped; `'Unknown'` if blank), `host`, `shared_internal_host` (1 if the URL, minus any trailing `/`, equals IPA's single hard-coded shared production clearView host). Device IDs are asserted unique. |
| `codes` | 49 | All columns of `transaction_codes` (including `transaction_code`, `transaction_description`), plus `bucket` and `provisional_fault` |
| `telemetry_month_code` | 418,188 | One row per (machine, `substr(transaction_date_local,1,7)` month, code), with `n`, `first_date`, `last_date`, `clocks_differ` (local time string ≠ UTC string), `missing_time` (UTC time or local date null) |
| `source_code_totals` | 49 | An independent `COUNT(*) … GROUP BY transaction_code` on the raw events |
| `pilot_selection` | 30 | `case_id, stratum` |
| `pilot_events` | 4,736 | Every non-`00` event (`case_id, transaction_time_utc, transaction_code`) in each pilot machine's buffered extraction range |
| `pilot_window_counts` | 90 | 30 tickets × 3 offsets: `all_events`, `non_success_events` in the 30-day window |

Cell 6 is a full-table scan (`NOT INDEXED`) fetched in chunks of 25,000 rows. It took from 2.0 s to 450.5 s and asserts
two things: every telemetry device ID is in the serial map, and `SUM(n)` equals the independent code totals. It then
adds indexes. Cell 9 prints "Atomic transactions represented: 118,047,569". Its line "Shared data checksum verified" is
a hard-coded print statement, not a computed check.

Fields loaded but never used later: `closed_at`, case `status`, `product`, `device_status`, the Administrative Notes
flag and length, `machine_type_raw`, and `issue_path` (defined in the `case_base` view). `SEED` is defined in cell 1,
but cell 8 hashes with the literal string `'15072'`.

### 2.5 Provisional code taxonomy (cell 4)
These are the team's provisional buckets ("provisional team taxonomy, not IPA validation", per the manifest). The 100
two-digit codes `00`–`99` each fall in exactly one bucket *(checked here)*. Any code in `transaction_codes` outside
those 100 strings is labelled **Malformed**.

| Bucket | # | Codes |
|---|---|---|
| Success | 1 | 00 |
| User behavior | 9 | 04 07 10 19 21 50 60 61 78 |
| Stock-out | 4 | 03 22 51 77 |
| Operational status | 13 | 53 55 68 69 70 71 72 73 74 75 76 82 83 |
| **Mechanical fault** | 13 | 02 11 14 16 17 18 31 32 33 34 35 66 67 |
| **Electronics/software/comms** | 10 | 05 06 08 09 13 23 24 25 52 54 |
| Door issue | 24 | 12 15 20 26 27 30 41 42 43 44 45 46 47 48 56 57 58 59 62 63 65 79 80 81 |
| Incomplete transaction | 1 | 01 |
| Undefined | 25 | 28 29 36 37 38 39 40 49 64, 84–99 |

**`provisional_fault`** is 1 when the bucket is Mechanical fault or Electronics/software/comms (the two bold rows,
23 codes) and 0 otherwise. Zac calls it the "narrow fault-code measure". Door issue is deliberately left out ("its
cause is ambiguous"). Code 05 stays in its bucket, with a sensitivity figure that excludes it.

### 2.6 The 30-ticket pilot (cell 8)
1. **Eligible:** any `cases` row (not only unplanned ones) whose `machine_id` is in `devices` and whose
   `opened_at` falls between `'2025-09-02'` and `'2026-07-31 23:59:59'` (string comparison). 2 Sep 2025 minus the
   32-day buffer is 1 Aug 2025 *(computed here)*.
2. **Stratum** = `trouble_code`, with missing codes set to `'Missing'`.
3. **Order key** = `sha256('15072' + case_id)` as a hex string. `within_stratum` = 0-based rank of that key inside the
   stratum.
4. **Rotation:** sort by (`within_stratum`, order key) and take the first 30. This takes the top-hashed ticket from each
   stratum, then the second from each, and so on.
   *(Computed here from the Excel:* the export has 11 trouble-code strata in the date window. Looking up the 30 printed
   pilot IDs gives 3 tickets each from 9 strata, 2 from Preventative Maintenance and 1 from Canopy. By service group
   that is 20 "Other recorded issue", 5 "Planned work", 3 "Missing trouble code" and 2 "No Trouble Found".)
5. **Extraction:** for each ticket, the query `pilot_extraction.sql` pulls the machine's events with
   `transaction_date_local` from (open date − 32 d) to (open date + 2 d). For offsets −12, 0 and +12 h it counts events
   with `transaction_time_utc` in `[anchor − 30 d, anchor)`, where anchor = `opened_at` + offset. This treats the
   case clock as equal to UTC (the "equal-clock assumption").
6. A `private` frame holding the pilot's raw rows is built in memory, with empty `reviewed_issue/matching_codes/reviewer`
   columns. The notebook does not write it to disk ("do not export private text automatically").

### 2.7 Artefacts written to `ipa_sql_outputs/`
- **27 CSVs**, one per `q()` query: record_quality, linkage, telemetry_date_coverage, field_completeness,
  hierarchy_ambiguity, service_groups, customer_workload, model_workload, issue_mix, customer_issue_mix,
  model_issue_mix, telemetry_buckets, code_totals, model_type_mapping, customer_host_audit, mapping_summary,
  comparison_cohort, ticket_cohort_exclusions, machine_type_rates, monthly_comparison, case_monthly, repeat_summary,
  repeat_by_model, pilot_candidate_coverage, pilot_scenario_summary, pilot_last_distinct_codes, pilot_last_three_events.
  The SQL text is kept in an in-memory `queries` dict that is never saved.
- **10 PNGs:** `01_missing_fields`, `02_customer_workload`, `03_model_workload`, `04_issue_mix`,
  `05_machine_type_rates`, `06_monthly_rates`, `07_repeat_contact`, `08_customer_concentration`,
  `09_model_issue_heatmap`, `10_repeat_composition`.
- **Other files:** `analysis.sqlite`, `source_aggregation.sql`, `pilot_extraction.sql`, `manifest.json`,
  `pilot_review_template.csv`, `midterm_findings.txt`.
  - `manifest.json` records the creation date, DB name, size and mtime, the workbook name and SHA-256, row counts
    (cases, devices, codes, telemetry), both SQL strings, the bucket source and `source_database_unchanged`.
  - `pilot_review_template.csv` holds the 30 pilot tickets with model, trouble code, category and subcategory, plus
    `reviewed_issue`, `matching_codes`, `reviewer` and `review_status`, all set to `'Pending'`.

### 2.8 SQL views used by later sections
| View | Defined in | Definition |
|---|---|---|
| `case_base` | cell 15 | `cases` + `month = substr(opened_at,1,7)` + `service_group` (precedence: Planned work → Cancelled request → Duplicate case → No Trouble Found → Missing trouble code → Other recorded issue) |
| `service_cases` | cell 15 | `case_base` minus Planned work, Cancelled request and Duplicate case ("unplanned service", 7,186 rows) |
| `machine_month` | cell 27 | Telemetry per machine-month for `'2025-08' ≤ month < '2026-08'`: transactions, fault transactions, door transactions |
| `comparison_month` | cell 27 | `machine_month` INNER JOIN `devices`, LEFT JOIN unplanned-ticket counts by (machine, ticket month); missing ticket counts set to 0 |
| `repeat_cases` | cell 31 | `service_cases` with `LEAD()` next opening and next category per machine, kept only where `opened_at < '2026-08-02'` |

**Planned work** means `trouble_code` is Preventative Maintenance or Installation, or `record_type` is Install Case.
**Cancelled request**, **Duplicate case** and **No Trouble Found** are values of `category`.

---

## 3. Section by section

Each heading is Zac's question. Under it: **Data** (source), **Method** (plain English, with formulas, filters and
windows), **Result** (printed numbers) and **Caveats** (Zac's own stated limits, quoted where possible).

### 1.1 What is the unit of analysis? (cell 11)
- **Data:** Excel + telemetry device dictionary (+ `telemetry_month_code` for coverage).
- **Method:** One case is one distinct `case_id`; one device is one `external_device_id`. Matching is exact on the
  whitespace-stripped serial (`cases LEFT JOIN devices USING(machine_id)`). Match % = 100 × matched cases ÷ all cases.
- **Result:** 7,471 cases (7,471 distinct), 845 customers, 3,773 ticket machines, 31 models; opened 2025-08-01 07:22
  to 2026-08-31 17:45. Linkage: 6,113 matched cases (**81.82%**) on 3,041 machines; "1,358 tickets have no exact
  device-dictionary match". Telemetry: 2025-08-01 to 2026-08-28, 118,047,569 transactions, 6,951 transacting machines.
- **Caveats:** "Matching an identifier establishes a possible link, not the presence of telemetry near the ticket
  date." The unmatched tickets "remain in the case-only summaries".

### 1.2 Which fields are available? (cell 13)
- **Data:** Excel.
- **Method:** Missing % = 100 × missing ÷ 7,471 (a blank counts as missing). The hierarchy audit lists
  (trouble_code, subcategory) pairs with more than one distinct `category`.
- **Result:** Missing: Trouble Reported 0, Model # 0, Trouble Code 101 (1.35%), Category 330 (4.42%),
  **Sub Category 2,315 (30.99%)**, Trouble Resolution 641 (8.58%). Six code/subcategory pairs span more than one
  category; the largest is Electronics / Replacement across 5 categories (292 cases).
- **Caveats:** A field present in the export may not have been filled in when the ticket opened. "Field entry/update
  times must be confirmed before using these fields in a model intended for ticket-opening decisions."

### 1.3 Separate service outcomes (cell 15)
- **Data:** Excel.
- **Method:** Assign each case to exactly one `service_group` using the precedence in §2.8. Planned, cancelled and
  duplicate cases are excluded from "unplanned service". No Trouble Found and missing-code tickets stay in.
- **Result:** Other recorded issue 6,508 (87.11%), No Trouble Found 577 (7.72%), Cancelled request 247 (3.31%),
  Missing trouble code 101 (1.35%), Planned work 23 (0.31%), Duplicate case 15 (0.20%). That leaves **7,186**
  unplanned tickets.
- **Caveats:** "'Other recorded issue' is not a confirmed machine fault." Full workload tables (Part 2.1) keep all cases.

### 2.1 Where are tickets concentrated? (cells 17–18)
- **Data:** Excel (all 7,471 cases).
- **Method:** Count cases and distinct ticket machines per customer and per model. Share = 100·N_g/N. The
  cumulative-share curve ranks customers by ticket count.
- **Result:**
  - Top customers: Customer 171 (123), 029 (116), 641 (92), 529 (91), 054 (78), 479 (71), 308 (70), 062 (68),
    602 (64), 489 (61). **The top 10 hold 11.2%**, and the chart shows that 126 customer labels account for 50%.
  - Top models: LVD-Remote-2.0 1,426, LVRR-WP-2.0 1,244, MV-2.0 936, LVD-Remote 724, LVRR-WP 589, alEx LC-D 575,
    MV 456, LC-30 305, alEx SD 2.0 158, alEx MC-D 143. **The top 3 hold 48.3%.**
- **Caveats:** "Affected machines" means machines that appear in tickets, "not an installed-fleet denominator".
  "Ticket counts measure workload, not customer failure rates." Counts "cannot establish that a larger customer or
  more widely installed model is less reliable."

### 2.2 What issues are recorded? (cells 20–21)
- **Data:** Excel, `service_cases` (N = 7,186).
- **Method:** Count `category` values, with missing kept as `[Missing]`, as a share of unplanned tickets. Full
  customer×category and model×category tables are saved as CSV. The heatmap shows the 8 highest-volume models × top 7
  categories + "Other", as row percentages.
- **Result:** Deposit Door 1,124 (15.64%), Computer Board 679 (9.45%), SAM 588, No Trouble Found 577, Main Door 568,
  Touchscreen 562, User Door 515, Curtain 510, [Missing] 325, Packer 227. Heatmap rows (unplanned n): LVD-Remote-2.0
  1,393, LVRR-WP-2.0 1,211, MV-2.0 897, LVD-Remote 695, alEx LC-D 558, LVRR-WP 554, MV 427, LC-30 298.
- **Caveats:** "A category describes what was recorded, not necessarily the underlying cause." The heatmap is "Not
  exposure-adjusted."

### 3.1 How should non-success transactions be interpreted? (cell 23)
- **Data:** `telemetry_month_code` LEFT JOIN `codes`.
- **Method:** Sum transactions by bucket and by code. The non-success share is the share of codes other than `00`. The
  fault-code rate = 1,000 × (Mechanical + Electronics/software/comms transactions) ÷ all transactions. A sensitivity
  version removes code 05.
- **Result:**
  - Success 110,166,059 (93.32%), Stock-out 3,236,592 (2.74%), Door issue 2,212,968 (1.87%), Mechanical fault
    844,284 (0.72%), User behavior 796,042, Incomplete 473,188, Operational status 268,236,
    Electronics/software/comms 45,235, Undefined 4,959, Malformed 6.
  - Non-success: 7,881,510 / 118,047,569 = **6.68%**.
  - Narrow fault codes: 889,519 = **7.54 per 1,000**, or **7.43** without code 05.
- **Caveats:** "The taxonomy is provisional." The rate "counts transaction outcomes, not distinct breakdowns, failed
  machines or downtime. Repeated codes may describe the same incident. Unknown codes are retained."

### 3.2 Can customer and model labels be mapped to the fleet? (cell 25)
- **Data:** Excel + `devices` (only exactly matched tickets).
- **Method:** For each case model, count the distinct telemetry `machine_type` values; for each customer, count the
  distinct hosts; for each host, count the distinct customers.
- **Result:** 16 case models span more than one telemetry type; 31 customers span more than one host; 83 hosts are
  linked to more than one customer. In the first 15 mapping rows, for example, LVD-Remote-2.0 → scrubex2.0-2 (1,227
  cases, 608 machines), plus Unknown (13), scrubex2.0-3 (3) and sd2.0-49 (1). `customer_host_audit` is saved to CSV
  but not displayed.
- **Caveats:** "Customer-specific exposure rates are therefore not reported without a verified customer-to-fleet
  mapping." Fleet comparisons use `machine_type`, which is "normalised only for letter case and whitespace".

### 3.3 How do rates vary across observed machine types? (cell 27)
- **Data:** Excel (`service_cases`) + telemetry (`comparison_month`).
- **Method:** Window Aug 2025 to Jul 2026. A **transaction-active machine-month** is a machine with at least 1
  transaction that month (zero-ticket months included). Tickets are counted by `substr(opened_at,1,7)`; telemetry is
  aggregated first, then ticket counts are joined on. The main cohort excludes the shared internal host and machines
  with no host. R_g = 100 × unplanned tickets in active machine-months ÷ active machine-months; F_g = 1,000 ×
  fault-code transactions ÷ all transactions. Chart screen: ≥100 active machine-months, ≥20 tickets and type ≠
  Unknown, with the top 10 by R_g plotted. The overall rate uses all types.
- **Result (cohort):**
  - All active machine-months: 70,057 machine-months, 4,933 tickets, 109,344,700 transactions, 65,847 with zero tickets.
  - Known non-shared hosts: **69,155** machine-months, **4,916** tickets, 108,944,603 transactions, 64,961 with zero tickets.
- **Result (where the 6,664 unplanned tickets in the window went):** included 4,916; no device match 1,203; no
  transactions in the ticket month 479; missing host 48; shared/internal host 18. These sum to 6,664, the same as the
  Aug 2025 to Jul 2026 unplanned total in `case_monthly` *(computed here)*.
- **Result (rates):** the overall rate is "4,916 tickets / 69,155 active machine-months × 100 = **7.11**". The table
  lists the 15 types that pass the screen:

| Type | Machines | Active MM | Tickets | R (per 100 MM) | F (per 1,000 tx) |
|---|---|---|---|---|---|
| sbsx-51 | 31 | 319 | 66 | 20.69 | 5.57 |
| sd-49 | 53 | 584 | 53 | 9.08 | 99.75 |
| scrubex-7 | 116 | 1,352 | 111 | 8.21 | 0.00 |
| scrubex2.0-2 | 1,172 | 12,329 | 999 | 8.10 | 13.14 |
| scrubex2.0-3 | 1,072 | 11,141 | 894 | 8.02 | 0.12 |
| alex2.0-3 | 470 | 5,011 | 397 | 7.92 | 5.43 |
| alex2.0-1 | 329 | 3,571 | 266 | 7.45 | 2.44 |
| scrubex2.0-4 | 913 | 9,442 | 684 | 7.24 | 4.89 |
| scrubex-2 | 520 | 5,873 | 397 | 6.76 | 14.03 |
| mlc-1 | 444 | 5,087 | 334 | 6.57 | 20.97 |
| scrubex-1 | 112 | 1,246 | 79 | 6.34 | 12.19 |
| scrubex2.0-5 | 153 | 1,606 | 89 | 5.54 | 4.76 |
| scrubex-4 | 366 | 4,143 | 204 | 4.92 | 5.19 |
| scrubex-3 | 494 | 5,484 | 246 | 4.49 | 0.00 |
| scrubex-5 | 82 | 938 | 37 | 3.94 | 7.36 |

  The 15 listed types account for 4,856 tickets and 68,126 machine-months. The other 60 tickets and 1,029
  machine-months belong to types that are screened out or Unknown *(computed here)*.
- **Caveats:** "ratios of totals, not averages of machine-level rates"; an active month "is an observation unit, not
  30 days of confirmed uptime; offline months are absent"; the rates describe "this selected observed cohort", and the
  source "includes only recently reporting US/Canada machines and omits some retired machines" (selection bias); the
  screens are "descriptive stability screens, not significance tests"; no adjustment for age, customer mix or
  reporting; "a zero narrow-fault-code count does not establish an absence of failures."

### 3.4 Do patterns change over time? (cell 29)
- **Data:** the same comparison cohort (telemetry + Excel), plus the case-only `case_monthly` table (Excel).
- **Method:** R and F computed per month for the cohort in §3.3. August 2026 is left out of the cohort series because
  its "telemetry is incomplete"; `case_monthly` keeps all 13 months.
- **Result:**

| Month | All tickets | Unplanned | Cohort MM | Cohort tickets | R | F |
|---|---|---|---|---|---|---|
| 2025-08 | 567 | 552 | 5,420 | 360 | 6.64 | 6.82 |
| 2025-09 | 581 | 550 | 5,605 | 414 | 7.39 | 7.10 |
| 2025-10 | 663 | 629 | 5,677 | 472 | 8.31 | 7.52 |
| 2025-11 | 504 | 477 | 5,675 | 353 | 6.22 | 8.03 |
| 2025-12 | 596 | 570 | 5,718 | 436 | 7.63 | 8.13 |
| 2026-01 | 601 | 586 | 5,739 | 449 | 7.82 | 8.08 |
| 2026-02 | 552 | 534 | 5,763 | 379 | 6.58 | 8.15 |
| 2026-03 | 613 | 601 | 5,903 | 440 | 7.45 | 7.78 |
| 2026-04 | 557 | 542 | 5,968 | 408 | 6.84 | 7.69 |
| 2026-05 | 515 | 485 | 5,952 | 354 | 5.95 | 7.18 |
| 2026-06 | 632 | 604 | 5,903 | 442 | 7.49 | 6.95 |
| 2026-07 | 549 | 534 | 5,832 | 409 | 7.01 | 7.23 |
| 2026-08 | 541 | 522 | — | — | — | — |

  "Monthly ticket rates range from 5.95 to 8.31 per 100 active machine-months."
- **Caveats:** "The series does not establish a directional or seasonal effect." Machine mix, reporting and source
  selection can move the series, and "a single annual cycle does not establish seasonality".

### 4.1 How often is another ticket opened within 30 days? (cells 31–32)
- **Data:** Excel, `service_cases`.
- **Method:** For each machine, order tickets by (`opened_at`, `case_id`) and use `LEAD` to get the next opening.
  Repeat if 0 ≤ gap (Julian days) ≤ 30; same-category repeat also requires a non-missing `category` equal to the next
  ticket's. Denominator: index tickets opened before 2026-08-02 (full 30-day follow-up; the next ticket may fall in
  August). P30 = 100 × repeats ÷ eligible index tickets.
- **Result:** 6,665 eligible tickets on 3,495 machines; 1,574 repeats (**23.62%**), of which 515 are same-category
  (**7.73%**); 0 simultaneous (gap = 0) follow-ups. Breakdown chart: no repeat 5,091 (76.4%), repeat with a different
  or missing category 1,059 (15.9%), same category 515 (7.7%). By model (top 10 by volume): LVD-Remote-2.0 23.21%,
  LVRR-WP-2.0 24.07%, MV-2.0 22.07%, LVD-Remote 20.46%, alEx LC-D 30.42%, LVRR-WP 22.78%, MV 23.13%, LC-30 14.79%,
  alEx SD 2.0 30.83%, scrubBank 480 36.92% (130 eligible).
- **Caveats:** a per-ticket measure, so busy machines count repeatedly; "It measures repeat contact, not repair
  failure"; cases opened at the same time can be counted, and truncated history does not identify the first-ever
  incident; the follow-up is "same serial, not necessarily same underlying fault".

### 5.1 Are recent codes available for review? (cell 34; selection in cell 8, see §2.6)
- **Data:** Excel + `pilot_events` / `pilot_window_counts` (telemetry).
- **Method:** SQL rebuilds each window `[opened_at + offset − 30 d, opened_at + offset)`, counts non-success events and
  distinct codes, and joins the Python-computed `all_events`. Each ticket-offset is labelled "No transactions
  observed", "Only success transactions observed" or "Candidate codes available". For offset 0 only, it lists each
  ticket's up to 10 most recent distinct non-success codes (last seen, occurrences, description, bucket) and counts
  distinct codes and buckets in the last 3 non-success events. Timestamp ties are broken by code order.
- **Result:** At each offset (−12, 0, +12 h), 26 of 30 tickets have transactions and 26 have non-success events; the
  4 with none are T01629, T03959, T05506 and T05683. At offset 0 the printed per-ticket table sums to 4,060
  non-success events and 39,118 total events *(computed here)*, with 0–867 non-success events per ticket. "Among 26
  pilot tickets with at least three non-success events, 25 have repeated codes within the last three events." The
  first 15 rows of the recent-code list are shown (3 tickets × 5 codes); e.g. T00705's most recent is code 43 "User
  Door 3 is Open" (Door issue).
- **Caveats:** "a deliberately varied feasibility sample, not a representative sample"; the case export has no time
  zone, so the ±12 h runs are "sensitivity scenarios, not confirmed conversions"; "Candidate availability means a code
  can be reviewed. It does not mean the code explains the service issue."; "The pilot does not yet apply a
  previous-repair cutoff"; "no verified within-second event order"; the step "does not determine semantic matches,
  silent failures or whether the last three codes are sufficient", and "Broad failure buckets are not equivalent to
  diagnostic issue groups". Next step: manual review against the narratives and confirming timestamp semantics with
  IPA; the template "is intentionally unlabelled".

---

## 4. Validation checks in 6.1 (cell 37)

Zac's scope statement: "These checks verify arithmetic and construction; they cannot validate source labels, time
zones or fleet completeness." Each check is an `assert` and printed "Pass". The table below describes what each check
compares.

| # | Check | What it compares | What it shows | What it does not show |
|---|---|---|---|---|
| 1 | Distinct case identifiers | `cases.case_id` is unique | One row per Case Number | Whether separate cases describe the same incident (15 are labelled Duplicate) |
| 2 | Distinct device identifiers | `devices.machine_id` is unique (also asserted in cell 4) | Joins to `devices` cannot multiply rows | That an exact serial match is the same physical machine; why 1,358 tickets do not match |
| 3 | No lost or multiplied case rows | Row count of the `linkage` left join = 7,471 | The join preserves the case count (follows from #2) | Match quality |
| 4 | Service groups reconcile | Σ service_group counts = 7,471 | The groups partition all cases | Whether the precedence rules or labels are right; a `CASE … ELSE` always partitions |
| 5 | Telemetry codes reconcile to independent raw SQL | Per-code Σ `n` in `telemetry_month_code` equals `source_code_totals` (pandas `Series.equals`) | The chunked aggregation lost or duplicated no rows for any code | Anything about the source table itself, since both queries read it |
| 6 | All source transactions represented | Σ `n` = `manifest['telemetry_rows']` | Internal consistency | Independent evidence: `telemetry_rows` is itself `SUM(n)` from the same table (the independent comparison is #5 and the cell 6 assert) |
| 7 | No missing transaction dates | Σ `missing_time` = 0 | No null UTC time or local date | That local/UTC semantics are right; nulls in `transaction_time_local` |
| 8 | Every aggregate machine is in dictionary | Telemetry `machine_id` ⊆ `devices` | The inner join in `comparison_month` drops no telemetry | Dictionary coverage of ticket serials |
| 9 | Provisional-window counts reconcile | SQL `non_success_events` (cell 34) = Python counts (cell 8) for all 90 ticket-offsets | Two implementations of the window logic agree | Whether the time-zone assumption is right; `all_events` is not cross-checked (the SQL table takes it from the Python table) |
| 10 | Rate numerator reconciles | Σ tickets in `machine_type_rates` = "Included in comparison" (4,916) | The machine-month route and the case-level route agree | Whether the exposure denominator is valid |
| 11 | Workload totals reconcile | Σ customer cases = Σ model cases = 7,471 | Group-bys over the same table cover every row | Correctness of labels; this holds by construction |
| 12 | Independent repeat-contact calculation | pandas `shift(-1)` gap count = 1,574 | The SQL `LEAD` logic agrees with a pandas version using the same filters | Same-category count and denominator (not compared); validity of the definition |
| 13 | Independent missing-subcategory count | pandas `isna()` = 2,315 | The SQL count is right on the same table | Anything about the source export |
| 14 | Original database preserved | `source_database_unchanged` (same size and mtime before and after cell 8) | The read-only extraction left the file's metadata unchanged | A content hash after the run (SHA-256 is checked only in cell 2, before analysis) |

After the checks the cell prints "Rows with unequal supplied local and UTC clock strings: 155". This is Σ
`clocks_differ`, so it counts source transactions, not aggregate rows. It is followed by "Equality of supplied clocks
does not establish the case timezone or validate the intended local-time semantics."

---

## 5. Zac's printed findings and open items (verbatim)

**6.2 Midterm findings** (cell 39; also written to `midterm_findings.txt`):

1. The case export contains 7,471 distinct tickets across 845 customer labels and 31 model labels.
2. Exact serial matching links 6,113 tickets (81.8%) to the device dictionary; this is identifier coverage, not diagnostic matching accuracy.
3. The top three model labels account for 48.3% of tickets. This is a workload concentration, not a reliability ranking.
4. Within the restricted comparison cohort, 4,916 unplanned tickets occur across 69,155 transaction-active machine-months, or 7.11 per 100 active machine-months. Offline periods are not measured by this denominator.
5. Trouble Code Sub Category is missing in 2,315 tickets (31.0%). Missing detail limits fine-grained classification.
6. Among 6,665 unplanned tickets with complete follow-up, 1,574 (23.6%) are followed by another ticket on the same machine within 30 days. This does not establish a failed repair.
7. Non-success transactions account for 6.68% of transactions; the team's provisional narrow fault buckets account for 0.75%. The two definitions answer different questions.

**6.3 What remains unresolved** (cell 40):

- Verify customer-to-fleet ownership before reporting customer-specific exposure rates. The observed case/host crosswalk is not a complete ownership register.
- Confirm timestamp semantics and field update timing before final ticket-to-code matching. The pilot is conditional on unverified clock assumptions.
- Confirm the provisional code buckets, particularly ambiguous door outcomes and code 05. Keep unknown and malformed codes visible.
- Complete independent review of the pilot and a held-out evaluation set before reporting classifier accuracy or “last three codes” coverage.
- Interpret repeat tickets and differences across machine types as descriptive patterns. Age, usage mix, reporting behaviour and source selection may explain part of the differences.

---

## 6. Reproducibility from the Excel alone

The Excel-side values were re-derived with `verification/01_excel_reproducibility.py` (output:
`verification/outputs/01_excel_reproducibility.csv`). All 47 Excel-side values compared match Zac's printed numbers.
The one mismatch is the workbook SHA-256 (`f060f58…` here vs `8ffdc24…` in cell 2).

**Reproduction note:** under pandas 3, blank workbook cells come back as `NaN`, and the original `clean(NaN)` returned the string
`'nan'` rather than `None`. That turns the 101 missing trouble codes (and missing categories and subcategories) into a
literal `'nan'`. `verification/common.py` now converts `NaN` to `None` on load (and `clean()` is NaN-safe), so the table matches Zac's Colab run.

| Section | Excel alone? | Why | Re-derived here |
|---|---|---|---|
| Pipeline: `cases` | yes | Built entirely from the sheet. `T`/`Customer` labels are identical; machine labels differ (`S#####` vs `M#####`) because the serial map also uses device IDs, but counts are unaffected | 7,471 rows, 845 customers, 3,773 machines |
| Pipeline: `devices`, `codes`, telemetry, pilot tables | no | Need the SQLite DB | — |
| 1.1 Unit of analysis | partly | `record_quality` is Excel-only; `linkage` needs `devices`; date coverage needs `transaction_events` | 7/7 record-quality values match |
| 1.2 Fields | yes | Case columns only | 6 missing counts + 6 ambiguity rows match |
| 1.3 Service outcomes | yes | Case columns only | 6 groups + 7,186 match |
| 2.1 Workload | yes | Case columns only | Top-10 customers and models, 11.2%, 48.3%, 126 labels match |
| 2.2 Issue mix | yes | `service_cases` only | Top-10 categories and heatmap n match |
| 3.1 Telemetry buckets | no | `transaction_events` + `transaction_codes` | Taxonomy structure only (100 codes, no overlaps) |
| 3.2 Fleet mapping | no | Needs `devices.machine_type` and clearView hosts | — |
| 3.3 Type rates | no | Denominator is telemetry machine-months; exclusions need `devices`. Only the 6,664 in-window unplanned total is Excel-derivable | 6,664 total matches the sum of the exclusion rows |
| 3.4 Monthly | partly | `case_monthly` is Excel-only; cohort rates need telemetry | 13/13 months × 2 columns match |
| 4.1 Repeats | yes | `service_cases` + `LEAD`; partitions do not depend on label numbering | All 7 summary values + top-10 models match |
| 5.1 Pilot | no | Eligibility requires a device match; windows need `transaction_events`. The 30 printed IDs can be looked up in the Excel (strata in §2.6) | Strata of printed IDs only |
| 6.1 Checks | partly | #1, #4, #11, #12, #13 are Excel-only; #2, #3, #5–#10, #14 need the DB | #1, #11, #12, #13 re-run and pass; #4 implied by matching groups |
| 6.2 Findings | partly | Findings 1, 3, 5, 6 are Excel-only; 2, 4, 7 need telemetry | 1, 3, 5, 6 match |
