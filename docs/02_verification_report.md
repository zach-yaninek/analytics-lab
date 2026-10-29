# Verification of Zac's IPA service-ticket SQL analysis

*Scope:* Zac Baylis's notebook `IPA_Service_Ticket_SQL_Analysis.ipynb` (10 Oct 2026); what it does is described in
`docs/01_what_zac_did.md`. Two companion documents cover the topics the user asked about in depth: customer-to-fleet
ownership (`docs/03_customer_fleet_ownership.md`) and timestamp semantics (`docs/04_timestamp_semantics.md`).
*Inputs available here:* the case-history workbook, the notebook with its printed outputs, and the project plan.
The 17 GB telemetry database was **not** available, so telemetry results were checked by logic review and
cross-table consistency only; `verification/verify_with_db.py` re-runs them once the DB is uploaded.
*[Updated 14 Oct: the DB has since been run; see the Update below.]*

> **Update, 14 October 2026.** This report was written on 12 October, before the full-database run and IPA's
> answers at the 13 October meeting. The original text below is kept as the dated record; superseded statements are
> marked *[Updated 14 Oct]*. What changed:
> - **Full-database re-run done** (`verify_with_db.py`; record in `verification/outputs/db/db_summary.md`). It made 66
>   checks against Zac's printed values, plus our own integrity checks. 65 pass in the committed record. The one
>   FAIL (`pilot_last_codes_head`) was a sort-order bug in our comparison script, fixed in commit 1db0943; re-sorted,
>   all 15 rows match. `db_summary.md` predates that fix.
>   - Reproduced: linkage 81.82% (6,113 tickets, 3,041 machines), the 16 / 31 / 83 mapping summary, the
>     machine-type and monthly rates, and the bucket totals.
> - **Telemetry clock: UTC** (verified on the full database). The evidence:
>   - hour-of-day profiles shift by zone as UTC predicts;
>   - no zone shows a DST gap or doubled hour;
>   - `event_time_offset` is 0 in all but 1 of the 1.5 million sampled rows, and `event_time_utc` follows the
>     transaction time by a median of about 36 s;
>   - the 155 rows where the two columns differ are −4 or −5 h shifts on devices with no linked ticket.
>
>   Sources: `db/db_summary.md` steps 5–8 and `fu/fu_summary.md` F5.
> - **Case clock: US Eastern**, confirmed by IPA on 13 October.
> - **Pilot at the corrected anchor** (+4 h EDT / +5 h EST). The rank-1 code is unchanged for 20 of the 26 pilot
>   tickets with codes. 11 tickets have codes in the 4–5 h that Zac's windows missed (`fu/fu_summary.md` F3).
> - **Customer attribution:** the device location name attributes 86% of devices to one account each, pending IPA
>   confirmation (see the update in `docs/03`).
> - **Field timing:** IPA says Trouble Code is entered at intake and may change by close, and that Category and Sub
>   Category are set near close (see the update in `docs/04`).
> - **Classifier:** IPA chose retrospective linking, and it is now lower priority than the data analysis
>   (`docs/executive_summary.md`).

---

## 1. Bottom line

1. **The arithmetic and SQL are correct.** Every number Zac printed that comes from the case export was reproduced
   **exactly** by three independent implementations. No arithmetic, join or SQL error was found anywhere in the
   notebook.
2. **His telemetry tables are internally consistent.** 85 cross-table identities pass: bucket sums, cohort and
   exclusion totals, the monthly and type tables, and the pilot tables. A second reviewer re-derived about 80 of
   them independently and found no discrepancy. The tables still cannot be *re-run* until the DB is available.
   *[Updated 14 Oct: re-run on the full database; they reproduce (see the Update).]*
3. **His main caution on customer-to-fleet ownership is right.** No field links devices to customer accounts, ticket
   serials reach only 42% of telemetry devices, and `Account Name` is a facility. Customer-specific exposure rates
   are not supportable from the data as delivered (`docs/03`). *[Updated 14 Oct: the device location name, in the
   DB, attributes 86% of devices to one account; rates look feasible pending IPA's confirmation (`docs/03`).]*
4. **His flagged timestamp issue is real, and half of it is now settled.**
   - Case times are on one shared, daylight-saving clock, most likely US Eastern. They are not hospital-local and
     not UTC.
   - The telemetry clock is still unknown. *[Updated 14 Oct: UTC, verified on the full database; the case clock is
     US Eastern, confirmed by IPA.]*
   - Trouble Code and Category are filled by closure, and Resolution and Notes are written during the ticket's life
     (`docs/04`). *[Updated 14 Oct: IPA says Trouble Code is entered at intake and may change by close; the export
     holds only the final value.]*
5. **The issues found are about definitions and interpretation, not errors.** The most consequential:
   - the 30-ticket pilot sample design, and what its 26/30 result does and does not show;
   - how sensitive the repeat-contact and fleet-rate headlines are to definitions;
   - help-desk monitoring tickets and telemetry-quoting ticket text, which matter for the classifier;
   - fault-code comparability across machine types.

   None changes a printed number. Several change how a number should be worded for the sponsor.

---

## 2. How this was verified

- **Wave 1.** Nine independent agents worked from the raw files:
  - an inventory of the notebook;
  - a faithful SQL reproduction, which ports his queries verbatim and checks them character-for-character;
  - a clean-room pandas reproduction from his method text only, without reading his code;
  - a case-logic audit and a telemetry-consistency audit;
  - a customer-to-fleet analysis;
  - a case-timestamp and field-timing analysis;
  - web research on Salesforce date handling, IPA and clearView;
  - a DB verification script, self-tested on synthetic databases with planted answers.
- **Wave 2.** Ten adversarial reviewers re-derived each material claim with their own code and tried to refute it.
  A completeness critic then reconciled the reviewers' verdicts and number conflicts. Every number in this report and
  in the IPA memo survived that step. Claims that did not survive are listed in §6.
- **Code.** All code is in `verification/`, with pseudonymous outputs in `verification/outputs/`. Each script runs
  end-to-end with `python3 -I verification/<script>.py`.

| Script | Purpose | Result |
|---|---|---|
| `reproduce_sql.py` | Zac's SQL verbatim on the rebuilt case table | 25 claims match; 1 differs (workbook hash); 3 need the DB; 1 partial (pilot selection, consistent) |
| `reproduce_cleanroom.py` | pandas re-derivation from his method text | 220 of 223 cell-level comparisons match; 0 mismatches; 3 not comparable |
| `01_excel_reproducibility.py` | third check, notebook-section order | 47 of 47 Excel-side values match |
| `audit_case_logic.py` | definitional sensitivity, case side | see §4 |
| `audit_telemetry_consistency.py` | 85 identities among his printed telemetry tables | 85 pass, 0 fail |
| `customer_fleet_audit.py` | ownership and coverage | `docs/03` |
| `timestamp_semantics.py`, `flags.py` | case clock, field timing, monitoring flag | `docs/04` |
| `verify_with_db.py` (+ `tests/`) | everything that needs the DB | ready; fixture self-test passes |

---

## 3. Reproduction of headline numbers

| Zac's result | Zac | Re-derived here | Status |
|---|---|---|---|
| Tickets / accounts / ticket serials / models | 7,471 / 845 / 3,773 / 31 | identical | ✔ |
| Missing: Trouble Code / Category / Sub Category / Resolution | 101 / 330 / 2,315 / 641 | identical | ✔ |
| Service groups (Other / NTF / Cancelled / Missing code / Planned / Duplicate) | 6,508 / 577 / 247 / 101 / 23 / 15 | identical; 7,186 unplanned | ✔ |
| Top-10 accounts' share; top-3 models' share | 11.2%; 48.3% | identical (126 accounts reach 50%) | ✔ |
| Top category among unplanned tickets | Deposit Door 1,124 (15.6%) | identical; IPA's own Summary sheet agrees once its scope (all tickets, excluding NTF and missing) is matched | ✔ |
| Monthly ticket counts (13 months) | table | identical | ✔ |
| 30-day repeat contact | 1,574 / 6,665 = 23.62%; same-category 7.73% | identical | ✔ |
| Pilot selection (30 tickets) | 30 ids | consistent with his rule (eligibility needs the DB) | ✔ (partial) |
| Exact-serial linkage | 6,113 tickets (81.82%), 3,041 machines | needs DB | pending → ✔ DB (14 Oct) |
| Telemetry totals and buckets | 118,047,569; 6.68% non-success; 7.54 per 1,000 narrow faults | internally consistent | pending → ✔ DB (14 Oct) |
| Cohort rate | 4,916 / 69,155 = 7.11 per 100 active machine-months | consistent: exclusions sum to the 6,664 unplanned Aug-25–Jul-26 tickets re-derived from the workbook | pending → ✔ DB (14 Oct) |
| Mapping summary | 16 / 31 / 83 | logic reviewed (§4, F6) | pending → ✔ DB (14 Oct) |

**Workbook provenance.** The local workbook hashes to `f060f58…`, not the `8ffdc24…` Zac verified. Its metadata
shows it was re-saved in Excel on 2026-10-10, the same day as the notebook; the export itself was created on
2026-09-01. Every Excel-derived value reproduces, so the difference does not affect his results. Zac should still
confirm which copy is canonical, because free-text columns were not compared cell by cell.

---

## 4. Findings on methods and interpretation

Severity reflects the effect on conclusions or on the team's next deliverables, not on Zac's arithmetic.

| # | Finding | Severity | Recommendation |
|---|---|---|---|
| F1 | **The pilot sample is not a test of ticket-to-code matching yet.** Round-robin allocation over 11 trouble-code strata gives groups holding 0.2% of tickets 9 of the 30 picks. Only 17 of 30 are unplanned recorded-issue tickets without a monitoring template: 5 are planned work, 5 are monitoring templates, 2 are NTF and 1 lacks a code. "Candidate codes available" equals "the machine transacted" (26 = 26 at every offset), because non-success codes, mostly stock-outs, appear whenever a machine is used, and there is no control window. Last-codes were computed only at the uncorrected anchor. Zac himself calls the sample "deliberately varied, not representative". | medium | Redraw from closed, unplanned, customer-reported tickets with resolution text; stratify on the classifier's target buckets; add a control window; recompute last-codes once the telemetry clock is known. |
| F2 | **The repeat-contact headline depends on the definition.** 23.6% is correct as defined (any later unplanned ticket on the same serial within 30 days). Alternatives: 22.0% with monitoring-template tickets removed; 20.7% (1,248 / 6,035) for closed, non-NTF, non-template tickets; 22.7% after merging follow-ups under 24 h. 40% of repeats happen within 7 days (median gap 9.9 days), and the export cannot say whether those continue one incident. Random timing of the same tickets would give about 14.8%, so the observed clustering is real. Model differences in repeat rate are almost entirely explained by tickets per ticketed machine (observed/expected 0.92–1.18 for every large model except LC-30, 0.67), so they are not model-specific repeat risk. *[29 Oct: re-derived with committed code in docs/10 (`verification/outputs/followups/rp_null.csv`, `rp_by_model.csv`). 14.8% is what one common window for every machine gives (14.84%). On each machine's own months, from install, it is 15.4% (observed ÷ expected 1.53). Relative to the fleet, the 12 models with 100+ eligible tickets run from 0.73 (LC-30) to 1.16 (LVD-Remote), and none differs after Benjamini–Hochberg. The conclusion stands.]* | medium | Report 23.6% with the 22.0% sensitivity and the 7-day share. Do not present the repeat-by-model chart as reliability. Ask IPA whether a revisit gets a new case number. |
| F3 | **The fleet ticket rate depends on what an "active month" is.** 528 device-matched unplanned tickets fall in machine-months with no transactions: 479 on cohort hosts, plus 49 hidden by the CASE order in the exclusion table. These are dropped from both numerator and denominator. Without install and decommission dates, a rate per *installed* machine-month for this cohort lies anywhere from about 6.5 to 7.8 per 100. The direction of bias in 7.11 is unknown. (The first wave said "biased down"; that was refuted.) August 2025 keeps an unusually small share of its tickets in the cohort (65% vs 74%). | medium | Present 7.11 as "per transaction-active machine-month" with the 6.5–7.8 range. Report the 528 by type and month. Reorder the CASE so host and silence are reported independently. Ask IPA what a silent month means. |
| F4 | **Telemetry fault-code rates are not comparable across machine types.** Three types holding about a quarter of cohort tickets log almost no narrow-fault codes: scrubex-7 0, scrubex-3 17 in 9.7 M, scrubex2.0-3 0.12 per 1,000. sd-49 logs 99.75 per 1,000. That spread more plausibly reflects which codes each family can emit than reliability. | medium (project objective 1) | Do not rank types by fault codes per 1,000 until IPA confirms code support by family or firmware. Use machine type as a classifier stratifier. |
| F5 | **Help-desk monitoring tickets and telemetry-quoting text.** 138 tickets (1.8%) are "Monitoring – Daily/Poll" templates. 85% of them follow another ticket on the same machine within 14 days, and they are involved in 11% of repeats. 10.4% of Trouble Reported texts mention clearView or clariFy, and at least 4.7% quote a numeric error code. | medium (classifier) | Flag them (`verification/flags.py`). Evaluate any ticket-to-code matching with and without them, and with and without masking. Confirm their origin with IPA. |
| F6 | **The mapping counts (cell 25) include artefacts.** `Unknown` counts as a machine type: at least 2 of the 16 models qualify only through it. IPA's shared internal host is counted like a customer instance. URLs are not normalised. So the counts overstate genuine mismatches within the matched set. They are still not upper bounds on true cross-instance ownership, because 19% of serials are unmatched and NULL hosts are ignored. | low | Recount with `shared_internal_host = 0`, known types only, and normalised URLs (`verify_with_db.py` step 3). |
| F7 | **"Missing trouble code" mostly means "not closed out yet".** 84 of the 101 are not in `Trouble Closed` status, and 79 were opened in August 2026. Only 17 of the 7,384 closed tickets (0.2%) lack a code. Status is never used in the notebook. | low | Describe missing codes as about 0.2% of closed tickets. Report open and non-standard statuses separately, and never use them as labelled classifier data. |
| F8 | **"Sub Category missing in 31%" overstates the gap.** The field is never used for Network codes and is blank on 95% of Miscellaneous codes. For Electro/Mechanical + Electronics it is blank on 9.4%, falling from about 20% (Aug–Oct 2025) to 4–9% a month. It mostly records the *repair action*, not a fault subtype. | low | Reword finding 5. Use Category, which has a strict single-parent hierarchy and is missing on 3.3% of closed tickets, as the main label level. |
| F9 | **The validation checks show construction, not correctness.** Of the 14 passing checks, 8 restate an earlier assert or hold by construction, 3 are weak re-implementations of the same definition, and 3 add real assurance. None tests the month, clock, host-flag or bucket choices. In a synthetic test, a 20-day month misassignment still passes. | low | Relabel them "construction checks". Add the cross-table identities from `audit_telemetry_consistency.py`. |
| F10 | **Minor points.** Same-category repeat uses only the *next* ticket (8.8% if any same-category ticket within 30 days counts, vs 7.7%). The pilot hash keys on the pseudonym, so any change to the export reshuffles the sample. A few tied orderings sit outside the displayed top-10s. Install Case tickets with repair codes (14) are counted as planned work. | info | State the definitions explicitly. Store the pilot list. |

### 4.1 Checked and found sound
These need no change:
- service-group precedence (no ticket meets two rules);
- the 30-day right-censoring cut (`< 2026-08-02` is exactly right; follow-up is complete through 31 Aug);
- aggregate-then-join construction for rates;
- the bucket taxonomy plumbing (each of codes 00–99 sits in exactly one bucket; bucket totals sum to 118,047,569);
- pilot extraction buffers and window edges (correct for any clock offset within ±14 h);
- the read-only handling of the source DB;
- no near-duplicate account names. The 8 serials that appear under two accounts do not affect any printed result.

---

## 5. What is still pending, and how it will be resolved *[status updated 14 Oct]*

| Item | Needs | Where | Status (14 Oct) |
|---|---|---|---|
| Linkage 81.82%, mapping 16/31/83, machine-type and monthly rates, bucket totals | the DB | `verify_with_db.py` steps 1–4 compare against Zac's printed values | Done: all reproduce (`db/db_summary.md`) |
| Host-as-customer-system feasibility | the DB, plus IPA's instance-to-organisation list | `verify_with_db.py` step 3, `customer_fleet_audit.py --db` (checks D1–D8) | Done at account level: host is not a facility key (single-account hosts hold 59.6% of the fleet); the system-level test still needs IPA's instance-to-organisation list. The device location name is the better route (`docs/03` update) |
| Telemetry clock (UTC, machine-local or server) | the DB, or IPA | `verify_with_db.py` steps 5–7: DST gap and doubled hour, hour profiles by zone, ingestion lag, the 155 rows | Done: UTC |
| Absolute case-clock zone (Eastern vs Central) | IPA (exporting user's Salesforce time zone) | `docs/04` §2.3 | Done: US Eastern (IPA, 13 Oct) |
| Code buckets, code support by family, door codes, code 05 | IPA | memo asks | In progress: IPA is sending its code definitions |
| Pilot re-ranking at the corrected anchor | the telemetry clock | Zac's `analysis.sqlite` → `pilot_events` suffices | Done: rank-1 code unchanged for 20 of 26 (`fu/fu_summary.md` F3) |

---

## 6. Corrections to our own first-wave claims (for transparency)

The adversarial wave changed these first-wave statements. Only the corrected versions are used anywhere else.

- "Elevated model repeat rates rest on a few chronic machines": **refuted.** Random timing concentrates repeats at
  least as much, and equal-fraction trimming leaves scrubBank 480 still well above the large models.
- "7.11 is biased down; about 7.75 is the corrected rate": **refuted.** The add-back keeps only silent months that
  contain a ticket, so it is an upper bound. The direction is unknown, and the range is about 6.5–7.8.
- Monitoring-template counts of 132 / 135 / 140: **reconciled to 138** under one documented rule (`flags.py`).
  Repeat effect: 22.0% with templates removed, not 22.1%.
- Wrong-machine tickets: "39 (0.52%)" is a floor; a broader manual review finds about 52 (0.7%).
- "The data cannot tell Eastern from Central": the file's creation stamp favours Eastern (conditional). Two of the
  originally cited reasons, the customer mix and the holiday pattern, are not evidence and were dropped.
- "Mountain matches the +2 h offset": a coincidence of mixing New Mexico and Colorado. Dropped.
- Case-clock evidence: the creation-order test (0 of 7,470 backward steps) replaces the weaker desk-edge and
  close-time arguments.
- "Model # is 1:1 with serial": corrected to "each serial carries a single model number".
- Field guidance: split into an at-open predictor list and a retrospective linker list (`docs/04` §5). The project
  plan's classifier is retrospective.
