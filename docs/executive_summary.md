# Service Tickets & Telemetry: Executive Summary

*Roper IPA × MIT Analytics Lab. Prepared for the IPA meeting, 13 October 2026.*
*Team: Zachary Yaninek, Zachary Baylis, Varun Ram Narayanan, Nathanael Muller.*

> Repository version. Customer names are pseudonymised, following the repo convention; the Word memo given to IPA
> (`deliverables/IPA_Executive_Summary.docx`, not committed) uses real facility names. Supporting detail is in
> `docs/02`–`docs/04`.

## Purpose
Our SQL pipeline links IPA's 13-month Salesforce case history to machine telemetry:
- 7,471 service tickets, August 2025 to August 2026;
- 118 million transactions from 7,183 devices.

Before building the ticket classifier, we independently re-verified every result and identified the data questions
only IPA can answer.

## What we found
1. **The analysis is sound and reproducible.** Three independent implementations re-derived every case-export
   figure exactly. The telemetry tables pass 85 internal consistency checks; the final re-run on the full database
   is scripted and pending.
2. **Service workload is concentrated by product and not by customer.**
   - Three model families (LVD-Remote-2.0, LVRR-WP-2.0, MV-2.0) account for 48% of tickets.
   - The ten busiest facilities account for only 11%; the largest is Customer 171 with 123 tickets.
   - Deposit Door is the most common recorded issue: 1,124 tickets, 16% of unplanned service.
3. **The fleet ticket rate is about 7 per 100 machine-months.†** There were 4,916 unplanned tickets over 69,155
   machine-months with telemetry activity, giving 7.11. Depending on how months without transactions are treated,
   the rate is 6.5–7.8.
4. **Most non-success telemetry is stock-outs and door events.†**
   - 6.7% of transactions are non-success: stock-outs 2.7%, door events 1.9%, mechanical and electronic fault codes
     0.75%.
   - Some machine types log almost no fault codes (scrubex-3: 17 in 9.7 M transactions), while another logs about
     100 per 1,000. That probably reflects which codes each family reports, so we are not yet ranking types by fault
     rate.
5. **About one in four tickets is followed by another on the same machine within 30 days (23.6%).**
   - 40% of those follow-ups come within a week.
   - This measures repeat contact, not failed repairs.
   - Excluding help-desk monitoring follow-ups, the rate is 22.0%.
6. **Customer-level rates are not yet possible.** Tickets link only 3,041 of the 7,183 telemetry devices (42%) to an
   account, and accounts are individual facilities that nest within health systems. Until an ownership mapping is
   available, we report workload counts by facility and rates by machine type.
7. **Ticket times and machine times are on different, partly unknown clocks.**
   - Case timestamps follow one shared daylight-saving clock, very likely US Eastern, not hospital-local time.
   - The telemetry's "local" and "UTC" columns are identical, so its clock is unknown.
   - That leaves up to 5 hours of uncertainty when lining a ticket up with the machine codes just before it.
8. **Trouble codes are completed at closure.** 1 of 64 open tickets had a trouble code, against 461 of 461 tickets
   closed in the same month. Resolution notes are written while the ticket is open. Which fields the classifier may
   use therefore depends on whether it runs at intake or retrospectively.

† To be re-confirmed on the full telemetry database this week.

## What we need from IPA

| # | Request | Why we need it |
|---|---|---|
| 1 | An installed-base mapping: parent-account IDs on the case export and the organisation each clearView instance serves. Ideally the asset list: serial, account, parent account, install, and removal dates. | Without it we cannot compute rates per customer or health system. Tickets reach only 42% of devices, and any per-customer rate built from ticketed machines is biased toward machines that failed. |
| 2 | **The time zone of the case export (the exporting user's Salesforce setting) and of the telemetry timestamps (UTC, machine-local or server). What are the 155 rows where the two telemetry clocks differ?** | Aligning a ticket with the codes logged just before it needs both clocks. A wrong assumption shifts the look-back window by up to 5 hours and changes which codes the classifier sees. |
| 3 | A review of our provisional code buckets (door codes, code 05), and which codes each machine family or firmware version can emit. | Fault-code rates range from about 0 to about 100 per 1,000 across machine types. Without code-support information we cannot compare types fairly (project objective 1) or define classifier targets. |
| 4 | **When Trouble Code, Category, and Dispatch # are set, and whether the close time is stamped automatically. A Field History Tracking export would answer this.** | It decides which ticket fields are legitimate classifier inputs, and whether close time can mark the end of an incident. |
| 5 | **How "Monitoring – Daily/Poll" tickets are created, and whether they count as customer demand.** | There are 138 of them (1.8%), and they are involved in 11% of repeat contacts. If telemetry alerts trigger them, matching them back to telemetry is circular. |
| 6 | The intended use of the ticket classifier (intake triage or retrospective linking for engineering), and permission to process ticket text with a language model after contact details are redacted. | This sets the feature list (due 10/13) and the evaluation design. About 300 tickets contain phone numbers or e-mail addresses. |
| 7 | Why 732 ticket serials (18% of tickets) are missing from the telemetry device list (serial format, non-networked or retired machines?), and what a month with no transactions means. Install and decommission dates if available. | These tickets drop out of every telemetry analysis. 528 tickets fall in silent months, which moves the fleet rate anywhere from 6.5 to 7.8. |

## Next steps
- **10/13:** classifier feature list in two variants (intake and retrospective), with flags for monitoring tickets
  and telemetry-quoting text, and time-based evaluation.
- **10/14:** integrate the machine-type, stock-out and repeat analyses. Re-run all telemetry checks on the full
  database (scripted).
- **10/16:** classifier data pipeline. Redraw the ticket-review sample from closed, customer-reported tickets.
- **10/23:** compare zero-shot classifiers on an independently labelled, later held-out period.

*Definitions.* "Unplanned" tickets exclude preventive maintenance and installations, cancelled requests and
duplicate cases. "Machine-month with telemetry activity" means a machine recorded at least one transaction that
month (August 2025 to July 2026; IPA's internal clearView instance excluded).
