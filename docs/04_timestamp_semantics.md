# Timestamp semantics and field-update timing

This document addresses Zac's open item 6.3: *"Confirm timestamp semantics and field update timing before final
ticket-to-code matching. The pilot is conditional on unverified clock assumptions."*

**Sources**
- Scripts: `verification/timestamp_semantics.py` (first wave) and `verification/flags.py` (canonical monitoring flag).
- Second-wave adversarial re-derivations: claims K3a–K3g and K4a–K4h in `data/derived/workflowB_result.json`. Each
  number below was recomputed by at least two independent scripts unless marked otherwise.
- Outputs: `verification/outputs/ts_*.csv`. All are pseudonymous.

**Status tags.** **[verified]** means re-derived from the case export. **[Zac]** is a value printed in Zac's notebook.
**[inferred]** is reasoning or documentation, not confirmed by IPA. **[pending DB / IPA]** means it cannot be
settled with the data in hand.

> **Update, 14 October 2026.** This document was written on 12 October, before the full-database run and IPA's
> answers at the 13 October meeting. The original text below is kept as the dated record; superseded statements are
> marked *[Updated 14 Oct]*. What changed:
> - **Case clock: US Eastern**, confirmed by IPA on 13 October.
> - **Telemetry clock: UTC**, verified on the full database. The evidence:
>   - hour-of-day profiles shift by zone as UTC predicts;
>   - no zone shows a DST gap or doubled hour;
>   - `event_time_offset` is 0 in all but 1 of the 1.5 million sampled rows;
>   - the 155 rows where the two columns differ are −4 or −5 h shifts on devices with no linked ticket.
>
>   Sources: `verification/outputs/db/db_summary.md` steps 5–8 and `verification/outputs/fu/fu_summary.md` F5.
> - **Window rule.** Add +4 h (EDT) or +5 h (EST) to `opened_at` to put a ticket on the telemetry clock. Applied to
>   the 6,113 device-matched tickets, that is +4 h for 4,151 and +5 h for 1,962 (`fu/fu_summary.md` F1).
> - **Zac's pilot at the corrected anchor** (`fu/fu_summary.md` F3, `fu_pilot_equal_clock_vs_corrected.csv`):
>   - the rank-1 code is unchanged for 20 of the 26 tickets with codes;
>   - the last-10 distinct list is unchanged for 19 of 26;
>   - 11 tickets have codes in the 4–5 h that the original windows missed.
> - **Field timing (IPA, 13 October):**
>   - Trouble Code is entered at intake but may be updated by close. The export holds only the final value: 1 of 64
>     open tickets has one, which is why we read it as filled by closure. Where the intake value is kept is an open
>     question for IPA.
>   - Category and Sub Category are set near the end of the ticket's life.
> - **Classifier:** IPA chose the retrospective linker (§5), and it is now lower priority than the data analysis.
>   Ticket text may be processed with a language model; we still remove contact details.

---

## 1. Bottom line

| Question | Answer | Status |
|---|---|---|
| Is `Date/Time Opened` hospital-local time? | **No.** Every ticket is on one shared clock. | verified |
| Is it UTC (or any fixed offset)? | **No.** The clock observes daylight saving time. | verified |
| Which zone is the shared clock? | **US Eastern** (America/New_York) is the working assumption. Central is not fully excluded. *[Updated 14 Oct: US Eastern.]* | ~~inferred; IPA to confirm~~ confirmed by IPA (13 Oct) |
| Is `Trouble Closed Date/Time` on the same clock? | Yes. No negative durations; close-within-1-h shares are equal across zones. | verified |
| What clock are the telemetry timestamps on? | **Unknown.** `transaction_time_local` and `transaction_time_utc` hold the same value in all but 155 of 118,047,569 rows. *[Updated 14 Oct: **UTC**.]* | ~~Zac; pending DB / IPA~~ verified on the full DB (14 Oct) |
| How far off can Zac's pilot anchor be? | Between −2 h and +5 h for the 30 pilot tickets, depending on the telemetry clock. That is well inside his ±12 h band. *[Updated 14 Oct: 4–5 h early; corrected, the rank-1 code is unchanged for 20 of 26.]* | verified (arithmetic); settled 14 Oct |
| When are Trouble Code / Category filled in? | **By closure.** 1 of 64 open tickets has them, against 461 of 461 tickets closed in the same month. *[Updated 14 Oct: IPA says Trouble Code is entered at intake and may change by close, so the export holds only the final value; Category and Sub Category are set near close.]* | verified (export); IPA answer 13 Oct |
| Are Resolution and Notes written at intake? | **No.** They are written during the ticket's life (44% of open tickets already have a resolution). | verified |

---

## 2. The case clock

### 2.1 One shared clock, not hospital-local [verified]
**Decisive test: creation order.** Salesforce case numbers are assigned in creation order. Sorted by case number,
the 7,471 opening times **never go backwards: 0 of 7,470 consecutive steps** (173 steps are ties at minute
precision). If each ticket showed its hospital's local time, a Pacific ticket created a few minutes after an
Eastern one would display about 3 hours earlier. Simulating that gives **more than 1,200 backward steps** (1,205–1,312
depending on the zone map). Every Pacific ticket sits in time between its Eastern case-number neighbours.

**Corroborating test: westward shift.** On weekdays, tickets from western hospitals open later on the export clock
than tickets from Eastern hospitals:
- Central: about **+1 h** (0.9 to 1.25 h across estimators).
- Pacific: about **+2 h** (1.85 to 2.5 h).

This shift survives every robustness check:
- hospital-clustered bootstrap intervals;
- stratifying by record type, weekday, model and case owner;
- alternative state→zone maps.

The record-type mix works *against* the shift, so it is not a mix artefact. Pacific shifts less than its full 3 h,
probably because desk hours cut off the Pacific afternoon. This truncation explanation is plausible but not
demonstrated, so the observed shifts must not be used as conversion offsets. Mountain (n≈160) mixes New Mexico
(about +4.8 h) and Colorado (about +0.6 h), and its cluster interval spans roughly 0.75–3.1 h, so it is not quoted
as evidence.

**Weaker controls.** The first wave also cited a 07:00 opening floor in every zone, early Pacific tickets, flat
close hours and monitoring tickets. A second-wave reviewer showed that the first three do not discriminate between
hypotheses on their own. The monitoring control is small (n=39 non-Eastern). The creation-order test above
supersedes them all.

### 2.2 The clock observes daylight saving time [verified]
- For Eastern hospitals, weekday opening hours do not move between standard-time and daylight-time months. The
  median difference is about +0.06 h, with a 95% CI of roughly ±0.3 h once tickets are clustered by hospital. A UTC
  or fixed-offset export would show +1 h.
- The help desk's first tickets of the day appear at about 07:00 on the export clock in both seasons:

  | Season | Weekday tickets before 06:00 / in 06h / 07h / 08h |
  |---|---|
  | DST months | 0 / 1 / 406 / 600 |
  | Standard months | 2 / 0 / 191 / 295 |

- Only 3 weekday tickets in the whole year were opened before 07:00.
- The spring-change window shows a +0.6 to +0.8 h mid-day shift. The fall window does not, and the 07:00 edge does
  not move in either. We read this as seasonal behaviour, not a clock change, and disclose it.
- The Arizona (no-DST) difference-in-differences test is underpowered (n = 51) and inconclusive.

### 2.3 Which zone? US Eastern, provisionally [inferred; IPA to confirm] *[Updated 14 Oct: confirmed by IPA]*
Relative tests cannot identify the absolute zone. Three facts favour US Eastern:
1. **The file's own creation stamp.** `docProps/core.xml` records `created = 2026-09-01T12:35:45Z`. The latest close
   in the export is `2026-09-01 08:05` on the export clock (9 closes that morning, 07:06–08:05).
   - On Eastern daylight time (UTC−4), that last close is 12:05Z, 31 minutes before the file was created.
   - On Central (UTC−5) it would be 13:05Z, after the file existed, which is impossible.

   This assumes the stamp is the true write time. The local copy was later re-saved in Excel on 2026-10-10, but
   re-saving keeps `created`.
2. IPA's headquarters, including its support division, is in Duluth, Georgia, which is on Eastern time.
3. All 14,854 open and close values have zero seconds and carry no zone. That fits a Salesforce **report** export,
   which Salesforce shows in the exporting user's time zone, rather than an API or Data Loader extract (UTC with
   seconds). Salesforce documents UTC storage, display in the viewer's zone, and UTC for API/Data Loader. The time
   zone of a report *export* is not officially documented, so this point is an inference.

The 73% Eastern customer share and the US-holiday pattern say nothing about which zone the exporting user had set,
so they are **not** used as evidence.

**Working rule.** Localise `opened_at` and `closed_at` as `America/New_York` with `zoneinfo`, never a fixed offset.
Carry ±1 h sensitivity until IPA confirms the exporting user's time-zone setting, or re-exports about 10 cases with
CreatedDate in UTC.

### 2.4 Close timestamps
- **[verified]** A close time exists on exactly the 7,384 `Trouble Closed` tickets. It is missing on all 87 others:
  64 `Dispatch` (open), 11 `Ricoh-Closed`, 7 `Closed` and 5 `Case Closed`.
- **[verified]** Every close is at or after its opening. 16 durations are exactly zero, and the median duration is
  about 67 h (closed tickets only).
- **[verified]** Close minutes cluster: 2.3× more same-minute sharing than opening times.
- **[inferred]** That clustering suggests administrative close-out by the desk rather than repair completion. Do not
  use `closed_at` as the end of an incident window until IPA confirms what it records.
- **[verified]** One close value is stored as text (`11/21/2025 7:11 AM`, case T02209). It parses correctly.

---

## 3. The telemetry clock [pending DB / IPA] *[Updated 14 Oct: UTC, verified on the full database; see the Update at
the top]*

**[Zac]** In Zac's run, `transaction_time_local` and `transaction_time_utc` are identical strings for all but 155
of 118,047,569 events. They record **one clock under two labels**. That clock could be true UTC with a mislabelled
"local" column, machine-local time with a mislabelled "UTC" column, or a fixed clearView-server zone. Some of the
155 may also be NULLs rather than real differences. Zac's month aggregation uses `transaction_date_local` and his
pilot windows use `transaction_time_utc`; while the two agree, those are consistent with each other.

**Decisive tests** are implemented in `verification/verify_with_db.py`, steps 5–7. They run as soon as the DB is
available, and were validated on synthetic fixtures with planted answers.

| Test | Machine-local clock | UTC clock | Fixed ET server clock |
|---|---|---|---|
| 1. Ingestion lag (receipt minus transaction time) by hospital zone, if a receipt-time column exists | ≈+4/+5 h ET, +7/+8 h PT | ≈0 everywhere | ≈+4/+5 h everywhere |
| 2. Hour-of-day profile of `00` transactions by hospital zone and DST period | zones align; no seasonal move | Pacific +3 h vs Eastern; 1 h seasonal move | Pacific +3 h; no seasonal move |
| 3. 2026-03-08 02:00–02:59 and 2025-11-02 01:00–01:59 | empty hour (spring) and doubled hour (fall) in DST zones | neither | neither in local hours |
| 4. The 155 differing rows | offsets of −4/−5 h (ET) or −7/−8 h (PT) indicate where the UTC column was really converted | – | – |

**No need to wait for the full re-scan to re-rank the pilot.** Zac's `analysis.sqlite` → `pilot_events` table already
holds every non-success event from 32 days before to 2 days after each pilot anchor. Once the clock is known, the
last-codes and last-three tables can be recomputed at the corrected offset from that table alone. All-event counts
at new offsets still need the source DB, because `00` events were not saved.

---

## 4. What this means for ticket-to-telemetry windows (Zac's pilot)

**Hours to add to `opened_at`** to put it on the telemetry clock, assuming an Eastern case clock. Under a Central
case clock, add 1 h to every entry. *[Updated 14 Oct: with an Eastern case clock and UTC telemetry, the rule is
+4 h (EDT) / +5 h (EST).]*

| Hospital zone | Telemetry = UTC | Telemetry = machine-local | Telemetry = ET server |
|---|---|---|---|
| Eastern | +4 (EDT) / +5 (EST) | 0 | 0 |
| Central | +4 / +5 | −1 | 0 |
| Mountain | +4 / +5 | −2 | 0 |
| Arizona (no DST) | +4 / +5 | −3 (summer) / −2 (winter) | 0 |
| Pacific | +4 / +5 | −3 | 0 |
| Hawaii | +4 / +5 | −6 (summer) / −5 (winter) | 0 |
| Newfoundland | +4 / +5 | +1.5 | 0 |

**Pilot sample.** 27 Eastern, 2 Central and 1 Arizona ticket (the Arizona one in winter); 23 fall in daylight
time and 7 in standard time. The required correction therefore lies between **−2 h and +5 h**.

What that means for each pilot result:
- **"26 of 30 tickets have candidate codes" is very likely unchanged.** Every corrected window shares at least 29.79
  of its 30 days with Zac's window. The 4 zero tickets have no events anywhere in their extraction range.
  - Bracketing by ±12 h does not *guarantee* this, so we say "very likely".
  - The result also says less than it seems. At every offset, "has non-success codes" equals "the machine
    transacted": 26 = 26. Non-success codes, mostly stock-outs, appear whenever a machine is used, and there is no
    control window. So 26/30 shows the machines were active, not that their codes explain the tickets.
- **"Last three codes" and "last five codes" are not verified.** They were computed only at the uncorrected anchor.
  - Under UTC telemetry, Zac's anchor is 4–5 h early, so the hours just before the call are cut off.
  - Under machine-local telemetry, the 3 non-Eastern tickets are 1–2 h late, so events after the call leak in.
  - Zac's ±12 h scenarios printed only whether any events existed.
- **Desk troubleshooting events.** For first-call-resolution (FCR) tickets, events in the 30–60 minutes before the
  call may come from the desk walking the user through resets. Flag a guard band.

---

## 5. Field-update timing and what it means for the classifier

*[Updated 14 Oct: IPA chose the retrospective linker, and the classifier is now lower priority than the data
analysis. IPA's field-timing answer, above, explains the 1-of-64 pattern: the export holds the final Trouble Code,
not the intake value.]*

**Open versus closed.** 64 tickets were open (`Dispatch`) at export, and all were opened in August 2026. The fair
comparison is therefore with the 461 tickets opened in August 2026 and already closed. In the table, "open" is n=64
and "closed" is the 7,407 other tickets. *[verified]*

| Field | Filled: open | Filled: closed | When it is written | At-open predictor | Retrospective linker |
|---|---|---|---|---|---|
| Trouble Reported | 100% | 100% | at intake (repair verbs in 1.2% vs 41.5% in Resolution) | ✔ (mask quoted codes as an ablation) | ✔ |
| Model #, Product Name | 100% | 100% | asset lookup (one model per serial) | ✔ | ✔ |
| Case Record Type | 100% | 100% | intake; no sign of later re-typing | ✔ (adds little beyond model) | ✔ |
| Trouble Code | 1.6% (1/64) | 99.5% (Aug-2026 closed: 461/461) | by closure | ✘ (label only) | ✔ input; but it cannot also be the accuracy reference |
| Category | 1.6% | 96.4% (99.3%) | by closure | ✘ | ✔ (same caveat) |
| Sub Category | 1.6% | 69.6% (72.7%) | by closure; mostly records the *repair action* | ✘ | ✔ as resolution information |
| Trouble Resolution | 43.8% (28/64) | 91.8% | during the ticket, as a running log | ✘ (leaks outcome) | ✔ (probably the most informative input) |
| Administrative Notes | 59.4% | 64.2% | during and after the ticket (≈90% of dated notes have an entry after opening; 2–6% after closure) | ✘ | ✔ after PII redaction |
| Dispatch # | 93.8% | – | within hours on repair-type tickets; never on General/Install Case | ✘ (process proxy) | ✔ |
| Case Owner | – | – | owner *at export*; tracks staffing changes | ✘ | ✘ (use only to stratify label-noise audits) |
| `closed_at`, Status | – | – | at closure | ✘ | anchor / filter only |

**Two classifier use cases need different field lists.** The project plan's classifier "associates a customer
service ticket with one of the past 10 error code buckets ... no identifiable issue, or an issue not represented in
the telemetry". "No identifiable issue" is a post-visit outcome, so this is a **retrospective linker**:
- Resolution and the trouble-code fields are legitimate inputs.
- The main risk is **circularity**: telemetry-derived text, and evaluation labels drawn from the same text.

An **at-open triage predictor** would be restricted to the ✔ fields in the at-open column. The 10/13
feature-selection deliverable should give both lists, and the team should confirm with IPA which use matters.

**Three other points to settle:**
- **The "10 buckets".** Zac's telemetry-bucket table has exactly 10 rows (including Success and Malformed), and
  Trouble Code also has exactly 10 values. The team should state in writing that the classifier's classes are the
  telemetry buckets.
- **Evaluation needs independent labels.** A zero-shot classifier has no training labels. If Category or Trouble
  Code are inputs, a Category→bucket crosswalk cannot also be the accuracy reference. An independent human-labelled
  evaluation set is needed; Zac's pilot review template is still unlabelled.
- **No Stock-out class in the tickets.** No Category corresponds to the telemetry Stock-out bucket, and only 6
  Trouble Reported texts mention stock-outs.

### 5.1 Telemetry-derived text [verified]
- **Monitoring templates.** 138 tickets (1.8%) open with the help desk's `Monitor(ing) … Daily/Poll` header. This is
  the canonical rule in `verification/flags.py`; the first-wave counts of 132, 135 and 140 used different regexes,
  and the script reconciles them.
  - 117 of the 138 (85%) follow another ticket on the same machine within 14 days, against 14% of other tickets.
  - Every one of those prior tickets is a regular ticket.
  - So they look like **post-incident watches**, not independent fault detections.
- **Mentions of telemetry systems.** 775 tickets (10.4%) mention clearView or clariFy, or are templates, in Trouble
  Reported; across all three text fields it is 1,033 (13.8%). At least 350 tickets (4.7%) quote a numeric error
  code, mostly door (156) and mechanical (93) codes.
  - For an at-open predictor, a quoted code is known at intake.
  - For a retrospective linker, it is genuine evidence.
  - Either way, report results **with and without masking**, and keep evaluation labels independent of that text.
- **Contact details.** Roughly 300 tickets contain phone numbers or e-mail addresses in free text. Redact them
  before any text goes to an external language model, and confirm with IPA that processing is permitted.

### 5.2 Drift over the year [verified]
- A system-added `Device FW: x.y.z` line appears from **2025-12-12**, on 41–63% of tickets each month after that.
  Parse it into a firmware field rather than only stripping it.
- "FCR" rises gradually, from 13–25% of tickets per month in Aug–Dec 2025 to 61–66% in Apr–Aug 2026.
- clariFy mentions rise from under 1% to 10–21% of tickets; clearView mentions fall to about 0.
- Labelling also changed:
  - Category was missing on 16.2% (Aug 2025) and 9.0% (Sep 2025) of tickets, then 0.5–3.4%.
  - Hardware Sub Category was missing on about 20% in Aug–Oct 2025, then 4–9% a month.
  - Zac's "31% sub-category missing" is therefore partly an early-period and not-applicable artefact. It is 9.4%
    for Electro/Mechanical + Electronics tickets.
- **Consequence.** Develop prompts and thresholds on an earlier period, evaluate on a later held-out period, and
  report results by period. End any test window at least two weeks before 2026-08-31: 54 of the 122 tickets opened
  in the last 7 days are still open and unlabelled.

---

## 6. Questions for IPA (and why each matters) *[answers added 14 Oct]*

| # | Ask | Why we need it | Answer (13 Oct) |
|---|---|---|---|
| 1 | Which time zone is set on the Salesforce user who exported the case-history report on 1 Sep 2026? Is "Date/Time Opened" the case creation time? Ideally, re-export about 10 cases with CreatedDate in UTC. | The data prove one shared, daylight-saving clock but cannot pin it down. Eastern vs Central leaves 1 h of uncertainty on every ticket-to-telemetry window. | US Eastern (IPA, 13 Oct). |
| 2 | Telemetry: are `transaction_time_utc` / `transaction_time_local` true UTC, each machine's local clock (with automatic DST?), or the clearView server's zone? Is the stored time the event time or the receipt time? What are the 155 rows where they differ? | The two columns are identical, so their labels don't tell us. A wrong guess moves each ticket's look-back window by up to 5 h and changes which codes count as "the last ones before the call". | Settled from the data: UTC, verified on the full database (14 Oct). The 155 rows are −4/−5 h shifts on unlinked devices. |
| 3 | When are Trouble Code / Category / Sub Category, Case Record Type, Case Owner and Dispatch # set? Is the close time stamped automatically on the status change? Field History Tracking would answer this. | It decides which fields a classifier may legitimately use, and whether close time can mark the end of an incident. | Partly answered: Trouble Code at intake (may change); Category and Sub Category near close. Field History export, close-time stamping, and where the intake Trouble Code is kept still open. |
| 4 | How are "Monitoring – Daily / Poll" tickets created, and should they count as customer demand? | They make up 1.8% of tickets and 11% of 30-day repeats. If telemetry alerts trigger them, matching them back to telemetry is circular. | Not yet asked. |
| 5 | How does IPA want to use a ticket classifier: triage at intake, or linking closed tickets to telemetry for engineering insight? May ticket free text (with contact details redacted) be processed by a language model? | The intended use decides the feature list (due 10/13) and the evaluation design. | Retrospective linking, lower priority than the data analysis; LLM processing of ticket text approved. |
| 6 | What do the statuses `Ricoh-Closed`, `Closed` and `Case Closed` mean? Is Sub Category meant to be not applicable for Network and Miscellaneous codes? | These 23 tickets have no close time and mostly no code; we need to know whether to count them as completed work. Sub Category's "31% missing" may simply mean not applicable. | Open. |
