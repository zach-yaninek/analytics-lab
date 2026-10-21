# TODOS: Association analysis (ticket fields ↔ last 10 telemetry codes before the ticket)

**Goal.** Measure how well a ticket's recorded issue (Trouble Code / Category / Sub Category, and later the
classifier's prediction from the ticket text) lines up with the **last 10 non-success telemetry codes generated
before the ticket was created**. Then use that to design and evaluate the zero-shot classifier.

**Settled inputs**
- **Clocks.** The case clock is US Eastern (IPA confirmed). Telemetry is UTC (verified on the full DB).
- **Windows.** One row per ticket × window, for all 6,113 device-matched tickets, in
  `verification/outputs/fu/fu_ticket_last10.csv`:
  - `corrected_guard0`, `corrected_guard30` and `corrected_guard60`: the 30-day lookback ending at ticket creation,
    or 30 or 60 minutes before it;
  - `control_minus35d`: the same machine, 35 days earlier. `control_clean` marks controls with no other ticket nearby.
- **Usable tickets.** Restrict to rows where `lookback_truncated` and `after_telemetry_end` are both false.
- **Code buckets.** The team's provisional lookup (`verify_with_db.LOOKUP`). It is not yet validated by IPA.

**First look** (quick, unverified: 3,259 unplanned tickets with a clean paired control). Share of tickets with ≥1
code of the bucket in the last-10 list, ticket window vs control window:

| Bucket | Ticket window | Control window |
|---|---|---|
| Electronics/software/comms | 20% | 13% |
| Door issue | 68% | 61% |
| Door issue, Electro/Mechanical tickets only | 78% | 68% |
| Mechanical fault | 55% | 52% |
| Stock-out | 46% | 45% |

Network tickets show no enrichment in any bucket. Having *some* code is near-universal: 90% of ticket windows and
89% of control windows.

---

## Work items

- [ ] **1. Target mapping (crosswalk).** Agree with the team, then IPA, how each Category (with its parent Trouble
  Code) maps to telemetry buckets, or to "no identifiable issue" or "not in telemetry".
  - *Inputs:* the 41 Categories (`verification/outputs/repro_clean_issue_mix.csv`) and the code dictionary
    (`verification/outputs/db/db_codes_buckets.csv`).
  - *Note:* no Category corresponds to Stock-out. Sub Category mostly records the repair action, not a fault subtype.
  - *Done when:* a versioned crosswalk CSV in the repo, with the rationale for each mapping.
- [ ] **2. Enrichment, ticket window vs paired control window.** For each bucket and each frequent code:
  - share of ticket windows with ≥1 occurrence in the last-10 list vs share of the same tickets' clean controls;
  - risk difference, lift and McNemar's paired test;
  - machine-clustered bootstrap confidence intervals, because a machine's tickets are not independent;
  - stratified by Trouble Code and Category.

  *Done when:* a table with intervals, reproduced by a second independent implementation.
- [ ] **3. Recency.** Lift by how long before the ticket the code appeared: 0–2 h, 2–6 h, 6–24 h, 1–7 d and 7–30 d.
  Use `last10_*_hours_before`. The most recent code is typically 2.4 h before the ticket.
  - Sensitivity: the 30 and 60-minute guard bands, which change the last-10 list for 10% and 15% of tickets.
  - *Done when:* we know whether the signal is concentrated in the final hours, which tells us how far back a
    classifier should look.
- [ ] **4. Category ↔ last-10 match rate.** Using the crosswalk from item 1: how often does the ticket's matching
  bucket appear among its last 10 codes, against the control window? Report precision and recall of "matching bucket
  present", overall and by Category.
- [ ] **5. Exclusions and sensitivities.** Report each result with and without:
  - monitoring-template tickets (`verification/flags.py`; 138 tickets);
  - tickets whose text quotes telemetry codes or systems (≥350 quote a code; `telemetry_mention`);
  - wrong-machine tickets (at least 39, about 52 on manual review);
  - planned, cancelled and duplicate tickets (`service_group`);
  - lookback-truncated windows;
  - repeat tickets whose windows overlap (23.6% have another ticket within 30 days). Use one ticket per episode, or
    cluster by machine.
- [ ] **6. Stratify by machine type.** Code support differs by family: scrubex-3, scrubex-7 and scrubex2.0-3 log
  almost no mechanical or electronics codes, while sd-49 logs about 100 per 1,000. Report enrichment per type, or for
  types that can emit the bucket.
- [ ] **7. Classifier evaluation design.**
  - **Reference labels:** an independent human-labelled set. Zac's pilot review template is still unlabelled. Redraw
    it from closed, unplanned, customer-reported tickets, stratified on the target buckets.
  - **Inputs vs reference:** never use the same field as both input and reference.
  - **Splits:** time-based (template drift from Dec 2025) and grouped by machine (no machine in both development and
    test).
  - **Text:** masked vs unmasked (quoted codes, system names, the `Device FW` line). Redact phone numbers and e-mail
    addresses (~300 tickets) before any text goes to a language model.
- [ ] **8. Adversarial verification.** Independent re-derivation plus skeptic review of every number before it goes
  into a doc or a sponsor update.
- [ ] **9. Open questions for IPA.**
  - Do technicians look at clearView error history when they assign the Category? If so, part of the association is
    built in.
  - Where is the Trouble Code entered at ticket creation stored? The export shows the final value: 63 of 64 open
    tickets have none.
  - A Field History Tracking export for Trouble Code, Category and Sub Category.
  - ~~Confirm that `devices.location_name` comes from the asset record, i.e. that it is the account.~~ Superseded
    on 21 Oct: IPA's installed-base list gives each machine's account directly (docs/06).

## Fleet exposure follow-ups (added 21 October)
- [x] **Customer-level and model-level rates on installed exposure**, and consistent outliers: `docs/06`,
  `verification/fleet_exposure.py`, charts `viz/fleet_exposure/`.
- [ ] **Run the database extract** (`python3 -I verification/fleet_db_extract.py --db <db>`, then zip and upload
  `verification/outputs/fleet/db/`). After that, re-running `verification/fleet_exposure.py` gives telemetry-type rates
  on installed exposure, networked vs non-networked rates and the full model × type crosswalk; chart `fx_05` switches
  basis by itself.
- [ ] **Stratify the association analysis by model as well as telemetry type** (item 6). Every ticketed machine
  already has its model (ticket model = list model on all 7,018 matched rows).
- [ ] **Measure how many of the 18 consistent-outlier customers chance alone would produce:** extend the stratified
  shuffle null (docs/06 §5) to the full rule (10 of 12 variants and both halves). Report separately the 8 with
  under 3 expected tickets in a half.
- [ ] **Re-run with IPA's answers on service channels** (docs/06 §8, asks 2–5): the Vogeltronix plan, the A-series,
  "Not Serviceable", and coverage dates.
- [ ] **Re-run with IPA's removal dates and parent accounts** when they arrive (docs/06 §8, asks 1 and 6).
- [ ] **Fold in IPA's field check** of the 18 consistent-outlier customers and 36 machines.
