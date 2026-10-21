# Service Tickets & Telemetry: Executive Summary

*Roper IPA × MIT Analytics Lab. Updated 21 October 2026 (previous update 14 October; first issued for the IPA meeting
on 13 October 2026).*
*Team: Zachary Yaninek, Zachary Baylis, Varun Ram Narayanan, Nathanael Muller.*

> Repository version. Customer names are pseudonymised, following the repo convention; the Word memo given to IPA
> (`deliverables/IPA_Executive_Summary.docx`, not committed) uses real facility names. Supporting detail:
> - `docs/02`–`docs/06`. `docs/02`–`05` carry dated update notes.
> - Full-database results: `verification/outputs/db/db_summary.md` and `verification/outputs/fu/fu_summary.md`.
> - Fleet-exposure results: `verification/outputs/fleet/fx_summary.json` (`docs/06`).
> - Association-analysis plan: `TODOS.md`.
> - Charts: `viz/figures/`.

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
2. **Service workload is concentrated by product and not by customer, and it mostly follows the installed base.**
   - Three model families (LVD-Remote-2.0, LVRR-WP-2.0, MV-2.0) account for 48% of tickets. That mostly reflects how
     many are installed: on the installed base they hold 42% of machine-months and 51% of unplanned tickets.
   - The ten busiest facilities account for only 11% of tickets. The two largest differ once their fleets are known:
     - Customer 171 (123 tickets) has about twice the unplanned tickets its 68 machines would generate at fleet
       rates;
     - Customer 029 (116 tickets, 107 machines) is in line with its fleet.
   - Deposit Door is the most common recorded issue: 1,124 tickets, 16% of unplanned service.
3. **New: adjusted for exposure and machine age, the main models are close to the fleet rate.**
   - **Fleet rate:** 6.2 unplanned tickets per 100 installed machine-months, about 0.74 per machine per year.
   - **LVD-Remote-2.0 and LVRR-WP-2.0:** 8.0 and 7.7 per 100. Most of that lead is their younger age; age for age
     they are 16% and 12% above the fleet.
   - **Clearly higher:** scrubBank 480 (2.6 times the fleet age for age) and alEx SD 2.0 (1.8 times).
   - **Almost no tickets:** the A-series.
   - **Age:** machines in their first four years generate about 8 per 100; machines over 10 years old, 2.5.
   - **Telemetry types (interim):** until the device list is joined to the installed base, they use telemetry-span
     exposure. scrubex2.0-2 and scrubex2.0-3 are at 7.9, against 7.0 for the telemetry fleet.
4. **The fleet rate depends on the denominator.** Unplanned tickets per 100 machine-months:
   - 6.2 on installed months, which include machines with no telemetry and quiet months;
   - 7.0 on telemetry-span months;
   - 7.11 on months with telemetry activity. That is Zac's measure, and it reproduces exactly on the full database.
5. **Most non-success telemetry is stock-outs and door events.** These shares also reproduce on the full database.
   - 6.7% of transactions are non-success: stock-outs 2.7%, door events 1.9%, mechanical and electronic fault codes
     0.75%.
   - Some machine types log almost no fault codes (scrubex-3: 17 in 9.7 M transactions), while another logs about
     100 per 1,000. That probably reflects which codes each family reports.
6. **New: customers differ in ticket rate, and the differences persist.** Each customer is compared with what its
   own machines would generate at fleet rates for their model and age.
   - **63 customers have more tickets than their fleet predicts, beyond chance.** Between them they have 1,732
     tickets, against 747 expected.
   - **The differences persist.** A customer's ratio in the first half of the period predicts its ratio in the
     second half: rank correlation 0.46, against 0.04 by chance.
   - **18 are consistent outliers:** flagged under at least 10 of 12 method variants and above expected in both
     halves. Together they have 737 tickets against 318 expected.
     - Nine have fewer than 10 machines.
     - In six of the larger ones, the excess is spread across the fleet. That points to the site (usage,
       environment, reporting), not one bad unit.
   - Only one is outside the normal spread between customers. This is a list for a field check, not a verdict.
7. **High-ticket machines hold up on installed exposure, as a continuum.**
   - Of the 113 machines flagged on 14 October, 106 are on the list and 93 stay flagged; 30 are consistent outliers.
   - On the whole list, 128 machines are flagged and 36 are consistent outliers.
   - A model that allows for the spread between machines still flags none.
   - Machines flagged on the first half alone fell from 12.6 to 2.9 times their expected tickets in the second
     half: regression to the mean, but a real excess remains.
8. **About one in four tickets is followed by another on the same machine within 30 days (23.6%).**
   - 40% of those follow-ups come within a week.
   - This measures repeat contact, not failed repairs.
   - Excluding the "Monitoring – Daily/Poll" tickets, the rate is 22.0%.
9. **The ticket and machine clocks are resolved.**
   - Case timestamps are US Eastern (confirmed by IPA). Telemetry timestamps are UTC (verified on the full
     database).
   - Our re-extraction converts ticket times to UTC (+4 h in summer, +5 h in winter) before matching.
   - On the original 30-ticket pilot, the correction changes the most recent code for 6 of the 26 tickets that have
     codes.
10. **A first look at how tickets relate to the telemetry just before them.**
    - **Dataset:** for each of the 6,113 device-matched tickets, we extracted the last 10 distinct non-success codes
      in the 30 days before it, on the corrected clock.
    - **Comparison:** 3,259 unplanned tickets have a clean comparison window on the same machine 35 days earlier.
      - Electronics codes (20% vs 13%) and door codes (68% vs 61%) are somewhat more common before tickets.
      - Mechanical and stock-out codes barely differ.
    - This is a first, unreviewed look, without confidence intervals.

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
| 3 | **Service channels.** Does Vogeltronix-plan service reach Salesforce? Is A-series service handled elsewhere? What does "Not Serviceable" mean? Do you have contract and warranty dates? | The 239 Vogeltronix machines had 3 tickets in a year, so we left them out. A-series machines have almost none. Coverage on the list is a snapshot. |
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
- **Installed machine-month** (findings 3 and 6): one month of a listed machine being installed, from its install
  date (or 1 August 2025) to 31 August 2026. The 239 machines on a third-party service plan are left out.
- **Expected tickets:** what the machines would generate at fleet rates for their model and age.
- **Flagged:** both of these hold:
  - 5 or more unplanned tickets;
  - more than expected beyond chance (Poisson test, Benjamini–Hochberg q < 0.05).

  This is a screening flag, not proof of a problem.
- **Consistent outlier:** both of these hold:
  - flagged under at least 10 of 12 method variants (three adjustments × tickets or 7-day episodes × with or without
    monitoring and No Trouble Found tickets);
  - above expected in both halves of the period.
