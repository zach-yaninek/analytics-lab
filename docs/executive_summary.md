# Service Tickets & Telemetry: Executive Summary

*Roper IPA × MIT Analytics Lab. Updated 14 October 2026; first issued for the IPA meeting on 13 October 2026.*
*Team: Zachary Yaninek, Zachary Baylis, Varun Ram Narayanan, Nathanael Muller.*

> Repository version. Customer names are pseudonymised, following the repo convention; the Word memo given to IPA
> (`deliverables/IPA_Executive_Summary.docx`, not committed) uses real facility names. Supporting detail:
> - `docs/02`–`docs/05`. Note that `docs/02`–`04` predate the full-database run.
> - Full-database results: `verification/outputs/db/db_summary.md` and `verification/outputs/fu/fu_summary.md`.
> - Association-analysis plan: `TODOS.md`.
> - Charts: `viz/figures/`.

## Purpose
Our SQL pipeline links IPA's 13-month Salesforce case history to machine telemetry:
- 7,471 service tickets, August 2025 to August 2026;
- 118 million transactions from 7,183 devices.

Our priority is the data analysis: verify the data, understand where service tickets come from, and see how they
relate to the telemetry. The ticket classifier is a later, lower-priority step.

This update adds:
- the full-database re-run;
- IPA's answers from the 13 October meeting;
- a location-based customer mapping;
- three new analyses: machines with an outsized share of tickets, ticket rates by machine type adjusted for exposure,
  and a first look at the telemetry just before each ticket.

## What we found
1. **Zac's arithmetic and SQL are correct and reproducible.**
   - Three independent implementations re-derived every case-export figure exactly.
   - The full-database re-run matches every value we compared from the original notebook (66 checks, including our
     own integrity checks).
   - One check fails in the committed run record. The cause was a sort-order bug in our comparison script, not in
     the notebook; once fixed, all 15 rows match.
2. **Service workload is concentrated by product and not by customer.**
   - Three model families (LVD-Remote-2.0, LVRR-WP-2.0, MV-2.0) account for 48% of tickets. That mostly reflects how
     many of them are installed (finding 3).
   - The ten busiest facilities account for only 11%; the largest is Customer 171 with 123 tickets.
   - Deposit Door is the most common recorded issue: 1,124 tickets, 16% of unplanned service.
3. **New: adjusted for exposure, the busiest machine types are only modestly above the fleet rate.**
   - The three telemetry types with the most tickets (scrubex2.0-2, scrubex2.0-3, scrubex2.0-4) generate 52% of
     unplanned device-matched tickets, but they also make up 48% of machine-months.
   - Their rates are 8.5, 8.2 and 7.6 tickets per 100 machine-months, against 7.5 for the fleet on the same measure
     (+12%, +9% and +0%). The first two are above the fleet rate even allowing for chance. Their lead in raw counts
     is mostly fleet size.
   - The 7.5 differs from finding 4's 7.1 because it counts every month between a machine's first and last
     transaction.
   - Among types with at least 100 machine-months, the highest rate is sbsx-51's: 21.9 per 100 machine-months,
     2.9 times the fleet, on 33 devices.
   - Model is recorded only on tickets, so rates by model cannot be computed. For the three leading models,
     telemetry type is a near one-to-one stand-in.
4. **The fleet ticket rate is about 7 per 100 machine-months.** There were 4,916 unplanned tickets over 69,155
   machine-months with telemetry activity, giving 7.11.
   - The figure reproduces exactly on the full database.
   - Depending on how months without transactions are treated, the rate is 6.5–7.8. That range reflects the
     definition, not uncertainty in the count.
5. **Most non-success telemetry is stock-outs and door events.** These shares also reproduce on the full database.
   - 6.7% of transactions are non-success: stock-outs 2.7%, door events 1.9%, mechanical and electronic fault codes
     0.75%.
   - Some machine types log almost no fault codes (scrubex-3: 17 in 9.7 M transactions), while another logs about
     100 per 1,000. That probably reflects which codes each family reports.
6. **New: a small group of machines generates an outsized share of tickets, more than chance explains.**
   - The top 5% of telemetry devices (332, counting machines with no tickets) hold 33% of tickets. Chance alone,
     given machine type and months in service, gives 22%.
   - 113 machines are flagged (see the definitions). About 70 of them stay flagged in at least 9 of the 10 method
     variants we tried; that count is provisional and not yet reproduced.
   - The flagged machines are spread across 82 facilities, 62 of which have just one.
   - On 67 of the 113, one category makes up half or more of the tickets, against about 38 expected for those
     models.
   - **It is a continuum, not a distinct set of defective units.** Ticket rates vary widely even between machines of
     the same type at the same facility. A model that allows for that spread flags only 2 machines.
   - About a quarter of the excess is facility-level. Merging tickets less than 7 days apart removes about half of
     the excess among machines with 6 or more tickets.
   - Telemetry shows no stronger warning before their tickets than before other machines' tickets. However, only 163
     of their tickets (21%) have a clean comparison window a month earlier.
7. **About one in four tickets is followed by another on the same machine within 30 days (23.6%).**
   - 40% of those follow-ups come within a week.
   - This measures repeat contact, not failed repairs.
   - Excluding the "Monitoring – Daily/Poll" tickets, the rate is 22.0%.
8. **Updated: customer-level rates look feasible for most of the fleet, pending IPA's confirmation.**
   - The telemetry device list carries a location name that matches the ticket's account for 99% of ticketed
     devices.
   - That attributes 6,171 of the 7,183 devices (86%, including some in the warehouse or offline) to 666 accounts,
     including machines that never had a ticket.
   - Caveats: it is a current snapshot, accounts are facilities rather than health systems, and IPA should confirm
     that the field comes from the asset record.
   - No customer-level rate has been computed yet.
9. **Updated: the ticket and machine clocks are resolved.**
   - Case timestamps are US Eastern (confirmed by IPA). Telemetry timestamps are UTC (verified on the full
     database).
   - Our re-extraction converts ticket times to UTC (+4 h in summer, +5 h in winter) before matching.
   - The original notebook's look-back windows were 4–5 hours early. On its 30-ticket pilot, the correction changes
     the most recent code for 6 of the 26 tickets that have codes.
10. **New: a first look at how tickets relate to the telemetry just before them.**
    - **Dataset:** for each of the 6,113 device-matched tickets, we extracted the last 10 distinct non-success codes
      in the 30 days before it, on the corrected clock.
    - **Timing:** where there is one, the most recent code comes a median 2.4 hours before the ticket (tickets with
      a full 30-day look-back).
    - **Comparison:** 3,259 unplanned tickets have a clean comparison window on the same machine 35 days earlier.
      For them, some code is present in 90% of ticket windows and 89% of comparison windows.
      - Electronics codes (20% vs 13%) and door codes (68% vs 61%) are somewhat more common before tickets.
      - Mechanical and stock-out codes barely differ (55% vs 52%; 46% vs 45%).
    - This is a first, unreviewed look, without confidence intervals.
    - **Field timing (IPA):** Category and Sub Category are set near close, so they describe the outcome, which is
      what a backward-looking comparison needs. Two questions remain:
      - do technicians consult clearView when they assign them?
      - where is the Trouble Code entered at intake kept?

**Answered by IPA on 13 October:**
- The case clock is US Eastern.
- Trouble Code is entered at intake and may change by close; Category and Sub Category are set near close. The
  export holds only the final Trouble Code: 1 of 64 open tickets has one. This updates our 13 October reading that
  trouble codes are completed at closure.
- The classifier is for retrospective linking and comes after the data analysis.
- Ticket text may be processed with a language model. We will still remove contact details.
- IPA's code definitions are being sent.

## What we need from IPA

| # | Request | Why we need it |
|---|---|---|
| 1 | An installed-base mapping: parent-account IDs on the case export and the organization each clearView instance serves. Ideally, the asset list: serial, account, parent account, install, and removal dates. | Location names now attribute 86% of devices to facilities, but rates by health system need parent accounts. Install and removal dates would fix the months in service of new or retired machines; 22 of the 113 flagged machines have under 12 months. |
| 2 | **Confirmation that the device location name comes from the asset record, and how current it is.** | Customer-level rates for 86% of the fleet rest on it. |
| 3 | IPA's code definitions (being sent), and which codes each machine family or firmware version can emit. | Fault-code rates range from about 0 to about 100 per 1,000 transactions across machine types. The definitions replace our provisional buckets for the association analysis and for comparing types fairly (project objective 1). |
| 4 | **How "Monitoring – Daily/Poll" tickets are created, and whether they count as customer demand.** | There are 138 of them (1.8%), and they are involved in 11% of repeat contacts. 26 of the 113 flagged machines are flagged only because of them. If telemetry alerts trigger them, matching them back to telemetry is circular. |
| 5 | **A field check of the 113 flagged machines** (list available on request): known problem units, heavy-use sites, or sites that report more? | Only IPA can tell whether the statistical signal matches what the service team sees. |
| 6 | **Whether technicians look at clearView error history when they assign Category and Sub Category; where the Trouble Code entered at intake is kept; and a Field History Tracking export for Trouble Code, Category, and Sub Category.** | If technicians use clearView, part of the ticket-to-telemetry association is built in. Only 1 of 64 open tickets in the export has a Trouble Code, so the intake value is not in the export. The history export shows how fields change between intake and close. |
| 7 | Why 732 ticket serials (18% of tickets) are missing from the telemetry device list (serial format, non-networked or retired machines?), and what a month with no transactions means. | These tickets drop out of every telemetry analysis. 528 tickets fall in months with no transactions; how those months are treated moves the fleet rate anywhere from 6.5 to 7.8. |
| 8 | Whether the close time is stamped automatically when the status changes, and whether a ticket opened within hours of the previous one closing is a re-open or rollover rather than a new visit. | It decides whether to count tickets or episodes. Much of the tail of high-ticket machines is repeat contact. |

## Next steps
**Done since the 13 October memo:**
- the full-database re-run;
- the high-ticket-machine analysis;
- ticket rates by machine type;
- the location-based customer mapping;
- the clock correction;
- the last-10-codes dataset.

**Next, in priority order:**
1. **Association analysis** between ticket fields and the last 10 codes: enrichment against paired control windows
   with confidence intervals, recency, and a category-to-code crosswalk once IPA's code definitions arrive.
2. **Customer-level rates** for the 86% of the fleet with a location-based account, once IPA confirms the field.
3. **High-ticket machines:** fold in IPA's field check, reproduce the robust core, then re-run with install and
   removal dates.
4. **Fault-code comparison by machine type**, once we have IPA's code definitions and which codes each family can
   emit.
5. **Ticket classifier** (retrospective linking): lower priority, after the data analysis. It will reuse the
   last-10-codes dataset and the ticket text. The classifier milestones in the 13 October memo (10/13–10/23) are
   paused, in line with IPA's priorities.

*Definitions.*
- **Unplanned tickets** exclude preventive maintenance and installations, cancelled requests and duplicate cases.
- **Machine-month with telemetry activity** (finding 4) means a month in which a machine recorded at least one
  transaction (August 2025 to July 2026; IPA's internal clearView instance excluded).
- **Machine-month** (findings 3 and 6) counts every month from a machine's first to its last transaction, quiet
  months included.
- **Flagged** (finding 6; 113 machines): a machine is flagged when both of these hold:
  - it has 5 or more unplanned tickets (the top 5% of ticketed machines, 247 with ties);
  - it has well more tickets than its type's rate predicts (Poisson test, Benjamini–Hochberg q < 0.05).

  This is a screening flag for follow-up, not proof of a defect.
