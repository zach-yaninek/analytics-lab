# Service Tickets & Telemetry: Executive Summary

*Roper IPA × MIT Analytics Lab. Updated 21 October 2026 (previous update 14 October; first issued for the IPA meeting
on 13 October 2026).*
*Team: Zachary Yaninek, Zachary Baylis, Varun Ram Narayanan, Nathanael Muller.*

> Repository version. Customer names are pseudonymised, following the repo convention; the Word memo given to IPA
> (`deliverables/IPA_Executive_Summary.docx`, not committed) uses real facility names. Supporting detail:
> - `docs/02`–`docs/06`. `docs/02`–`05` carry dated update notes.
> - Full-database results: `verification/outputs/db/db_summary.md` and `verification/outputs/fu/fu_summary.md`.
> - Fleet-exposure results: `verification/outputs/fleet/fx_summary.json` (`docs/06`).
> - Association study: `docs/07` (protocol, frozen before results) and `docs/08` (results).
> - IPA's follow-ups on slides 4 and 5: `docs/09` (protocol, frozen before results) and `docs/10` (results).
> - Charts: `viz/figures/`. Each finding below links its charts; "Charts by finding" at the end shows them in
>   order, with what to point at.

> **Update, 29 October 2026: IPA's follow-ups on slides 4 and 5** (`docs/09`, `docs/10`; slide charts `sl_18`–`sl_32`).
> - **Young machines' tickets (slide 4).**
>   - Machines under 4 years old have more tickets of almost every type, not different ones (8.0 against 4.8 per 100
>     machine-months).
>   - Within model, the mix shifts modestly but beyond chance (p < 0.001): Electronics is a larger share (mostly
>     Touchscreen, 1.85 times), and Mechanical a smaller one (mostly Packer).
>   - 80% of the 1,447 extra tickets are age within model, not model mix; Deposit Door and Touchscreen carry most of
>     them.
>   - No sign yet that they were fixed: the Touchscreen gap widened in the second half, and Deposit Door's held. IPA's
>     fix dates would turn this into a test.
> - **Repeat contacts (slide 5).**
>   - 31% of repeats are the same Category and 32% a different group; 28% involve a Monitoring ticket, No Trouble
>     Found or a blank Category.
>   - Quick follow-ups are more often the same problem: 46% within a day against 27% beyond six months.
>   - Every model repeats more than random timing would give (15.4% for the fleet against 23.6% observed), but once
>     ticket volume and timing are allowed for, no model or telemetry type stands out from the fleet.

> **Update, 22 October 2026: association study** (`docs/07`, `docs/08`; provisional).
> - **Primary result.** On average over the five code sets that could be tested, a ticket's Category agrees with the
>   telemetry codes logged in the final 7 days before it. Those codes appear before the ticket rather than in a
>   ticket-free stretch on the same machine 35 days earlier at 3.2 times the odds seen for tickets of other faults (95%
>   2.3 to 4.8; permutation p = 0.0005). Chart [as_01](../viz/figures/as_01_specificity_by_set.png).
> - **Verification.** This is the pre-specified primary test. Two blind clean-room builds reproduced it exactly, and a
>   skeptic review checked it (docs/08, "How this was checked").
> - **By code set** (descriptive; the estimates are imprecise). Clearly above 1 for the SAM, user-door and deposit-door
>   codes; borderline for the main door (lower end 1.01, permutation p 0.08). For Computer Board these data do not show
>   a specific match: its codes, mainly 25, rise at least as much before other faults' tickets. Chart
>   [as_01](../viz/figures/as_01_specificity_by_set.png).
> - **Timing.** The codes concentrate in the final hours: a ticket's own codes appear in its final 30 minutes for 23% of
>   tickets, against 2% of controls. Part of that may be the call itself; with the final 30 minutes dropped, they appear
>   within 6 hours before 45% of tickets against 13–14% of controls. Chart [as_02](../viz/figures/as_02_recency.png).
> - **Limits.** The Category results rest almost entirely on scrubex machines (chart
>   [as_07](../viz/figures/as_07_coverage.png)). If technicians read clearView when they set Category, part of the
>   agreement is built in (request 6 below). The results stay provisional until IPA's code definitions (crosswalk v1)
>   and a local run of the text-flag export; every sensitivity check run so far holds at 7 days (chart
>   [as_06](../viz/figures/as_06_robustness.png)).

## Purpose
Our SQL pipeline links IPA's 13-month Salesforce case history to machine telemetry:
- 7,471 service tickets, August 2025 to August 2026;
- 118 million transactions from 7,183 devices.

Our priority is the data analysis: verify the data, understand where service tickets come from, and see how they
relate to the telemetry. The ticket classifier is a later, lower-priority step.

This update uses IPA's installed-base list (19 October: 9,294 active machines with account, model and install
date). With it we can, for the first time:
- adjust ticket rates for fleet exposure, by model and by customer;
- test which outliers are consistent.

## What we found
1. **Zac's arithmetic and SQL are correct and reproducible.**
   - Three independent implementations re-derived every case-export figure exactly.
   - The full-database re-run matches every value we compared from the original notebook (66 checks, including our
     own integrity checks).
   - One check fails in the committed run record. The cause was a sort-order bug in our comparison script, not in
     the notebook; once fixed, all 15 rows match.
   - **Charts:** none; the checks are tables (docs/02, `verification/outputs/db/db_summary.md`).
2. **Service workload is concentrated in a few models rather than a few customers, and it mostly follows the
   installed base.**
   - Three models (LVD-Remote-2.0, LVRR-WP-2.0, MV-2.0) account for 48% of all 7,471 tickets. That mostly reflects
     how many are installed: they hold 42% of installed machine-months and 51% of the 6,750 unplanned tickets on
     listed machines.
   - The ten busiest facilities account for only 11% of tickets. The two largest differ once their fleets are known:
     - Customer 171 (123 tickets in all) has 113 unplanned tickets on its 68 listed machines against 59 expected,
       about twice its fleet's rate. It is on the field-check list (finding 6); the reason is not yet known.
     - Customer 029 (116 tickets in all) has 114 against 102 expected on 107 machines, in line with its fleet.
   - Deposit Door is the most common recorded issue: 1,124 tickets, 16% of unplanned service.
   - **Charts:** [zac_03](../viz/figures/zac_03_model_workload.png) the three models' 48%;
     [fx_01](../viz/figures/fx_01_fleet_vs_ticket_share.png) 51% of tickets against 42% of machine-months;
     [zac_02](../viz/figures/zac_02_customer_workload.png) the ten busiest facilities;
     [fx_06](../viz/figures/fx_06_busiest_customers.png) Customers 171 and 029 against their fleets;
     [zac_04](../viz/figures/zac_04_issue_mix.png) Deposit Door.
3. **New: adjusted for exposure and machine age, the main models are close to the fleet rate.**
   - **Fleet rate:** 6.2 unplanned tickets per 100 installed machine-months, about 0.74 per machine per year.
   - **LVD-Remote-2.0 and LVRR-WP-2.0:** 8.0 and 7.7 per 100, 30% and 26% above the fleet. About half of that lead
     is their younger age: age for age they are 16% (95% interval 5–28%) and 12% (1–25%) above the fleet.
   - **Clearly higher:** scrubBank 480, 2.6 times the fleet age for age (1.8–3.8) and above it in both halves of the
     period. alEx SD 2.0 (1.8 times) and SD-64 (1.5 times) are above over the year, but not clearly in each half.
   - **Almost no tickets:** the A-series.
   - **Age:** machines under 4 years old generate about 8 per 100; machines 10 years or older, 2.5. Part of the
     oldest machines' low rate is that many are Not Serviceable.
   - **Telemetry types (interim):** until the device list is joined to the installed base, they use telemetry-span
     exposure. scrubex2.0-2 and scrubex2.0-3 are at 7.9, against 7.0 for the telemetry fleet.
   - **Charts:** [fx_02](../viz/figures/fx_02_rate_by_model.png) model rates, with the age-for-age ratios in its footer;
     [fx_09](../viz/figures/fx_09_model_persistence.png) the two halves; [fx_03](../viz/figures/fx_03_rate_by_age.png)
     age; [fx_04](../viz/figures/fx_04_rate_by_coverage.png) Not Serviceable;
     [fx_05](../viz/figures/fx_05_rate_by_telemetry_type.png) telemetry types.
4. **The fleet rate depends on the denominator.** Unplanned tickets per 100 machine-months:
   - 6.2 on installed months (August 2025 to August 2026), which include machines with no telemetry and quiet
     months;
   - 7.0 on telemetry-span months (August 2025 to July 2026);
   - 7.11 on months with telemetry activity (August 2025 to July 2026). That is Zac's measure, and it reproduces
     exactly on the full database.
   - **Charts:** [fx_02](../viz/figures/fx_02_rate_by_model.png) 6.2;
     [fx_05](../viz/figures/fx_05_rate_by_telemetry_type.png) 7.0; [zac_06](../viz/figures/zac_06_monthly_rates.png)
     7.11 and its monthly range.
5. **Most non-success telemetry is stock-outs and door events.** These shares also reproduce on the full database.
   - 6.7% of transactions are non-success: stock-outs 2.7%, door events 1.9%, mechanical and electronic fault codes
     0.75%.
   - Some machine types log almost no fault codes (scrubex-3: 17 in 9.7 M transactions), while another logs about
     100 per 1,000. That probably reflects which codes each family reports.
   - **Charts:** none; the transaction mix is a table (docs/02).
6. **New: customers differ in ticket rate, and the differences tend to last.** Each customer is compared with what
   its own machines would generate at fleet rates for their model and age.
   - **63 customers have more tickets than their fleet predicts, beyond chance.** Between them they have 1,732
     tickets, against 747 expected.
   - **The differences tend to last.** Customers that ran high in the first half of the period tended to run high in
     the second. The rank correlation is 0.46, against 0.04 when the halves are shuffled between customers.
   - **Individual flags can still be chance.** The pattern holds for customers as a group; about 6 of the 15
     customers clearly above expected in both halves would be expected by chance.
   - **18 are consistent outliers:** flagged under at least 10 of 12 method variants and above expected beyond
     chance in each half. Together they have 737 tickets against 318 expected.
     - Nine have fewer than 10 machines, where one or two machines may drive the count.
     - In six of the larger ones, the extra tickets are spread across many machines. That fits something
       site-wide (use, environment, coverage or how readily staff call) better than one bad unit.
   - Only one is unusual even after allowing for the normal spread between customers. This is a list for a field
     check, not a verdict.
   - **Charts:** [fx_07](../viz/figures/fx_07_customer_funnel.png) the 63 flagged and the one outside the normal spread;
     [fx_10](../viz/figures/fx_10_customer_persistence.png) the two halves;
     [fx_12](../viz/figures/fx_12_outlier_drivers.png) what drives each consistent outlier.
7. **High-ticket machines hold up on installed exposure, as a continuum.**
   - Of the 113 machines flagged on 14 October, 106 are on the list and 93 stay flagged; 30 are consistent outliers.
   - On the whole list, 128 machines are flagged and 36 are consistent outliers.
   - Allowing for how much machines normally differ, none stands out as a separate group of defective units (2 did
     on 14 October).
   - The 70 machines picked out on the first half alone ran at 12.6 times their expected tickets then and 2.9 times
     in the second half. Picking machines on their worst months exaggerates how far out they are, but they stay
     well above expected.
   - **Chart:** [fx_11](../viz/figures/fx_11_machine_persistence.png) the continuum; the 12.6 and 2.9 times are in its
     footer. The counts in the first three bullets are not drawn (docs/06).
8. **About one in four tickets is followed by another on the same machine within 30 days (23.6%).**
   - 40% of those follow-ups come within a week.
   - This measures repeat contact, not failed repairs.
   - Excluding the "Monitoring – Daily/Poll" tickets, the rate is 22.0%.
   - **Chart:** [zac_10](../viz/figures/zac_10_repeat_composition.png) the 23.6% and what repeats are made of. The 40%
     and 22.0% are not drawn.
9. **The ticket and machine clocks are resolved.**
   - Case timestamps are US Eastern (confirmed by IPA). Telemetry timestamps are UTC (verified on the full
     database).
   - Our re-extraction converts ticket times to UTC (+4 h in summer, +5 h in winter) before matching.
   - On the original 30-ticket pilot, the correction changes the most recent code for 6 of the 26 tickets that have
     codes.
   - **Charts:** none.
10. **A first look at how tickets relate to the telemetry just before them.**
    - **Dataset:** for each of the 6,113 device-matched tickets, we extracted the last 10 distinct non-success codes
      in the 30 days before it, on the corrected clock.
    - **Comparison:** 3,259 unplanned tickets have a clean comparison window on the same machine 35 days earlier.
      - Electronics codes (20% vs 13%) and door codes (68% vs 61%) are somewhat more common before tickets.
      - Mechanical and stock-out codes barely differ.
    - This is a first, unreviewed look, without confidence intervals.
    - **Superseded by the association study** (update above; docs/08). Its reviewed version of this comparison is chart
      [as_04](../viz/figures/as_04_bucket_enrichment.png): the final 7 days on 2,911 tickets, with intervals. There
      mechanical codes are also more common before tickets (40% vs 36%).

**Answered by IPA:**
- **Installed base:** the active list arrived on 19 October.
- **On 13 October:**
  - The case clock is US Eastern.
  - Trouble Code is entered at intake and may change by close; Category and Sub Category are set near close.
  - The classifier is for retrospective linking and comes after the data analysis.
  - Ticket text may be processed with a language model (contact details removed).
  - IPA's code definitions are being sent.

## What we need from IPA

| # | Request | Why we need it |
|---|---|---|
| 1 | **Machines removed or replaced during August 2025 to August 2026, with removal dates, and parent accounts.** | The list holds active machines only. 433 unplanned tickets sit on 226 serials that are not on it, mostly older models, so their rates are understated. Parent accounts give health-system rates. |
| 2 | **A field check of the 18 consistent-outlier customers and 36 consistent-outlier machines** (list available on request). | Only IPA can tell whether the signal reflects heavy use, site practice, reporting habits or problem units. |
| 3 | **Service channels.** Does Vogeltronix-plan service reach Salesforce? Is A-series service handled elsewhere? What does "Not Serviceable" mean? Do you have contract and warranty dates? | The 239 Vogeltronix machines had 3 unplanned tickets in 13 months, so we left them out. A-series machines have almost none. Coverage on the list is a snapshot. |
| 4 | IPA's code definitions (being sent), and which codes each machine family or firmware version can emit. | They replace our provisional buckets for the association analysis and the fault-code comparison by type. |
| 5 | **How "Monitoring – Daily/Poll" tickets are created, and whether they count as customer demand.** | There are 138 of them, involved in 11% of repeat contacts. If telemetry alerts create them, matching them back to telemetry is circular. |
| 6 | **Whether technicians look at clearView error history when they assign Category and Sub Category; where the intake Trouble Code is kept; a Field History Tracking export.** | If technicians use clearView, part of the ticket-to-telemetry association is built in. The export holds only the final Trouble Code. |
| 7 | Whether the close time is stamped automatically, and whether a ticket opened within hours of the previous one closing is a re-open or rollover. | It decides whether to count tickets or episodes. |

## Next steps
**Done since 14 October:**
- installed-base exposure for models, ages and coverage;
- customer-level rates;
- the consistent-outlier analysis;
- the database extract script that joins telemetry devices to the installed base.

**Next, in priority order:**
1. **Association analysis** between ticket fields and the last 10 codes: enrichment against paired control windows
   with confidence intervals, recency, and a category-to-code crosswalk once IPA's code definitions arrive.
2. **Telemetry-type rates on installed exposure:** run `verification/fleet_db_extract.py` on the database. This also
   gives networked vs non-networked rates.
3. **Consistent outliers:** fold in IPA's field check, then re-run with removal dates and parent accounts.
4. **Fault-code comparison by machine type**, once we have IPA's code definitions.
5. **Ticket classifier** (retrospective linking): lower priority, after the data analysis.

*Definitions.*
- **Unplanned tickets** exclude preventive maintenance and installations, cancelled requests and duplicate cases.
- **Installed machine-month** (findings 2, 3, 6 and 7): one month of a listed machine being installed, from its install
  date (or 1 August 2025) to 31 August 2026. The 239 machines on a third-party service plan are left out: their
  service rarely reaches the case export.
- **Expected tickets:** what the machines would generate at fleet rates for their model and age.
- **Flagged:** both of these hold:
  - 5 or more unplanned tickets;
  - more than expected beyond chance (Poisson test, Benjamini–Hochberg q < 0.05).

  This is a screening flag, not proof of a problem.
- **Halves of the period** (findings 6 and 7): a split in time, not a random split of the data.
  - **The split:** 1 August 2025 to 14 February 2026, and 15 February to 31 August 2026. That is about 6.5 months
    each, with 3,334 and 3,416 unplanned tickets.
  - **How each half is counted:** each machine counts only the installed months inside a half. Expected tickets are
    refitted within each half, so fleet-wide differences between the halves, such as season, cancel out. Only a
    customer's or machine's standing relative to the fleet is compared.
  - **What the halves test:** whether customers and machines that run high in one half also run high in the other.
    - Rank correlation: 0.46, against 0.04 when the halves are shuffled between customers.
    - Customers picked out on one half were significant in the other 43% and 38% of the time, against 17% and 13%
      after shuffling.
  - **Caveats:**
    - each half has about half the data, and 8 of the 18 consistent outliers have under 3 expected tickets in a half;
    - the halves cover different seasons;
    - most tickets on machines no longer listed fall in the first half.
- **The 12 method variants:** every combination of three choices (3 × 2 × 2), each with the same flag rule.
  - **Adjustment:** model only; model + machine age (the main analysis); or model + age + service status. Checks that
    a flag does not depend on one adjustment, and whether a contract or warranty mix explains it.
  - **Count:** tickets, or 7-day episodes (a ticket within 7 days of the previous one on the same machine is merged
    into it). A burst of follow-ups or rollovers on one problem then counts once.
  - **Tickets included:** all unplanned, or without the "Monitoring – Daily/Poll" and No Trouble Found tickets.
    Monitoring tickets may be raised by IPA's own telemetry alerts, and No Trouble Found tickets are not faults.
  - **Flags across the variants:**
    - customers: 29 to 79, with 63 in the main variant;
    - machines: 53 to 151, with 128 in the main variant.
- **Consistent outlier:** both of these hold:
  - flagged in at least 10 of the 12 method variants;
  - above expected beyond chance in each half of the period (Poisson p < 0.05 in each).

  That gives 18 customers and 36 machines. Detail is in docs/06 §2 and §5.

## Charts by finding
*For presenting: the charts for each finding above, in order. Each chart's title states its finding; the notes say
what to point at and where a chart's numbers differ from the text. Customer charts use pseudonyms; the real-name
variants of zac_02, fx_06, fx_07, fx_10 and fx_12 are drawn locally to `deliverables/` and are not committed.*

### Association study (update, 22 October)
![A ticket's own codes show up before it rather than in its control at 3.2x the odds seen for other faults' tickets](../viz/figures/as_01_specificity_by_set.png)

*Point at:* the pooled 3.2x row on top (95% 2.3 to 4.8); then the per-set rows. Main Door's interval only just clears 1;
Computer Board's (0.5x) includes 1. Per-set rows are descriptive; only the pooled test decides.

![A ticket's own codes appear in its final 30 minutes for 23% of tickets, against 2% of controls](../viz/figures/as_02_recency.png)

*Point at:* 23% against 2% at 30 minutes, and how the gap narrows to 68% against 50% at 7 days. The footer gives the
6-hour figure with the final 30 minutes dropped (45% against 13–14%).

![H1 and the per-set results rest on 1,439 of 2,911 tickets, 97% of them on scrubex machines](../viz/figures/as_07_coverage.png)

*Point at:* 1,439 of the 2,911 tickets can be checked, 97% of them on scrubex machines; the footer lists the alEx and
mlc tickets that cannot.

![At 7 days the main result holds in every sensitivity variant run so far: the pooled specificity ratio stays between 2.3x and 3.5x](../viz/figures/as_06_robustness.png)

*Point at:* every interval stays above 1 at 7 days. Footer: the one 30-day check that reaches 1, and the pending
text-flag check (S2), which bears on request 6 (clearView).

### 1. Verification
No chart: the checks are tables (docs/02, `verification/outputs/db/db_summary.md`).

### 2. Where the workload comes from
![Top 3 of 31 models hold 48.3% of all tickets; LVD-Remote-2.0 alone has 19.1%](../viz/figures/zac_03_model_workload.png)

*Point at:* the three blue bars, 48.3% of all 7,471 tickets (all tickets, including planned and cancelled).

![The three busiest models' 51% of tickets mostly reflects their 42% of installed machine-months](../viz/figures/fx_01_fleet_vs_ticket_share.png)

*Point at:* the three bold rows: 42% of installed machine-months (gray) against 51% of unplanned tickets on listed
machines (blue).

![No customer dominates: the top 10 of 845 with tickets hold 11.2% of tickets](../viz/figures/zac_02_customer_workload.png)

*Point at:* the top 10 hold 11.2%; Customer 171 has 123 tickets and Customer 029 116 (all tickets).

![10 of the 15 customers with the most tickets are flagged, 6 consistently; the top one (by 1 ticket) is in line with its fleet](../viz/figures/fx_06_busiest_customers.png)

*Point at:* Customer 171, 113 against 59 expected (blue: a consistent outlier); Customer 029, 114 against 102, in line
with its fleet. On unplanned tickets on listed machines 029 is the busiest by one ticket, hence the title.

![Deposit Door leads with 15.6% of unplanned tickets, 1.7× the next category](../viz/figures/zac_04_issue_mix.png)

*Point at:* Deposit Door, 1,124 of 7,186 unplanned tickets (15.6%).

### 3. Model rates, adjusted for exposure and age
![5 of 27 models run above the fleet ticket rate beyond the noise, led by scrubBank 480 at 2.7×](../viz/figures/fx_02_rate_by_model.png)

*Point at:* the fleet line at 6.2; LVD-Remote-2.0 at 8.0 and LVRR-WP-2.0 at 7.7. The title's 2.7× for scrubBank 480 is
the crude ratio; the finding's 2.6 age for age is in the footer (2.58×), with 1.16×, 1.12×, alEx SD 2.0 1.82× and SD-64
1.55×. The fifth blue model, alEx LC-D, is 1.05× age for age. The finding's intervals are not drawn (docs/06).

![Allowing for age, only scrubBank 480 is clearly above the fleet in both halves; A-LC and A-MC are clearly below](../viz/figures/fx_09_model_persistence.png)

*Point at:* scrubBank 480 above the fleet in both halves (2.65, then 2.56); alEx SD 2.0 and SD-64 not clearly in each
half.

![Machines under 1 year old have 3.3× the ticket rate of machines 10 years or older](../viz/figures/fx_03_rate_by_age.png)

*Point at:* about 8 per 100 under 4 years, 2.5 at 10 years or older.

![Under Warranty machines have 1.7× the fleet's ticket rate, Not Serviceable 0.24×](../viz/figures/fx_04_rate_by_coverage.png)

*Point at:* Not Serviceable at 0.24× the fleet, part of why the oldest machines run low.

![3 of 15 telemetry types run above the telemetry fleet's ticket rate, led by sbsx-51 at 2.9×; 3 run below](../viz/figures/fx_05_rate_by_telemetry_type.png)

*Point at:* scrubex2.0-2 and scrubex2.0-3 at 7.9 against 7.0 (interim, telemetry-span exposure). The title leads with
sbsx-51, which the finding does not discuss.

### 4. The fleet rate depends on the denominator
fx_02 shows 6.2 (installed months) and fx_05 shows 7.0 (telemetry-span months), both above. The ticket counts differ
too: 6,750, 4,996 and 4,916.

![No clear trend or seasonality in the monthly ticket rate: 5.95 to 8.31](../viz/figures/zac_06_monthly_rates.png)

*Point at:* 7.11 on months with telemetry activity, Zac's measure, and its monthly range of 5.95 to 8.31.

### 5. The telemetry transaction mix
No chart: the non-success mix is a table (docs/02). The htm_06 charts show a different measure (non-success
events before tickets, by the 14 October machine groups).

### 6. Customers against their fleets
![63 customers are flagged, but only 1 lies outside the normal spread between customers](../viz/figures/fx_07_customer_funnel.png)

*Point at:* the 63 flagged; only one, a 3-machine site, lies outside the 99.8% funnel limit. 32 are above the 95% limit.

![Customers that run high tend to stay high: rank correlation 0.46 between halves, 0.04 when the halves are shuffled](../viz/figures/fx_10_customer_persistence.png)

*Point at:* rank correlation 0.46 between halves against 0.04 when shuffled. The 15 clearly above in both halves are
among the 311 customers with at least 3 expected tickets in each half, so 8 of the 18 consistent outliers are not drawn.

![9 of 18 consistent outliers have under 10 machines; 6 of the other 9 have their excess spread across their fleets](../viz/figures/fx_12_outlier_drivers.png)

*Point at:* 9 of the 18 have under 10 machines; in 6 of the other 9 the excess is spread across the fleet. The 1,732
against 747 tickets are not drawn.

### 7. High-ticket machines
![Machines with 3+ first-half tickets had 2.6× their expected second-half tickets; their sites alone would give 1.5×](../viz/figures/fx_11_machine_persistence.png)

*Point at:* second-half ratios rise with first-half tickets: a continuum. The title's 2.6× is for the 272 machines with
3 or more first-half tickets; the finding's 12.6 then 2.9 times (70 machines flagged on the first half) is in the
footer. The 106, 93, 30, 128 and 36 counts are not drawn. Do not use htm_03 for this finding: it is the 14 October cut,
and its "93" is a different group.

### 8. Repeat contact
![23.6% of unplanned tickets have a 30-day repeat; 7.7% a same-category one](../viz/figures/zac_10_repeat_composition.png)

*Point at:* 23.6% of unplanned tickets have a 30-day repeat. The 40% within a week and the 22.0% without monitoring
tickets are not drawn; htm_05's 7-day follow-up rates are a different measure.

### 9. Clocks
No chart.

### 10. First look at the telemetry before tickets
![Electronics codes appear before 13% of tickets against 5% of controls; stock-out codes, the negative control, do not rise](../viz/figures/as_04_bucket_enrichment.png)

*Point at:* the reviewed version of this comparison (final 7 days, 2,911 tickets, with intervals). Its numbers differ
from the first look by design; mechanical codes are clearly more common before tickets here.
