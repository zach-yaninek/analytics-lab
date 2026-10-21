# Customer-to-fleet ownership: can tickets be put on a customer's installed fleet?

*Script:* `verification/customer_fleet_audit.py` (run `python3 -I verification/customer_fleet_audit.py [--db PATH]`).
*Outputs:* `verification/outputs/fleet_*.csv` (pseudonymous). Real names, addresses, serials and the hand-reviewed
account-to-system map are kept in `data/private/fleet_private_*.csv` (gitignored).
*Evidence tags:* **[data]** = computed here from the case export; **[Zac]** = Zac's printed output, not re-run (the
telemetry DB is not in this container); **[inferred]** = our reasoning or outside knowledge, not verified by IPA;
**[pending DB]** = decided by the checks in §7 once the DB arrives.

> **Update, 21 October 2026.** IPA sent its active installed-base list (19 October: serial, account, model,
> install date). `docs/06_fleet_exposure.md` uses it to compute customer-level rates. Its account field appears to
> be the install's account: it matches the ticket's account on 99.4% of matched rows, though IPA has not confirmed
> the source field. So the location-name route below is no longer needed for rates.
> - **Agreement with tickets:** 3,540 of the 3,773 ticket serials are on the list. Where they match, the ticket's
>   account equals the list's account on 99.4% of rows and the model on 100%.
> - **Rates by customer:** each customer's tickets are compared with what its own machines would generate at fleet
>   rates for their model and age (`fx_customer_rates.csv`).
>   - 63 customers have more tickets than their fleet predicts, beyond chance.
>   - 18 are consistent outliers, flagged under at least 10 of 12 variants and above expected in both halves.
>   - Customer 029, which has the most unplanned tickets on listed machines, is in line with its fleet.
> - **Still facility-level:** accounts are facilities; health-system rates still need parent accounts.
> - **Snapshot:** the list holds active machines only, so machines removed during the period are missing (docs/06 §1).
> - **Superseded statements below**, now marked *[Updated 21 Oct]*. docs/06 computes customer rates from the
>   list's account, which supersedes:
>   - the 14 Oct box's "No customer-level rate has been computed yet";
>   - the *[Updated 14 Oct]* notes in the Bottom line and the §5 table that point to `devices.location_name` as
>     the route to customer rates.
>
>   Per-clearView-instance rates (§5 table) are still not computed.

> **Update, 14 October 2026.** This document was written on 12 October from the case export and Zac's device
> dictionary, before the full-database run. The original text below is kept as the dated record; superseded
> statements are marked *[Updated 14 Oct]*. What the database added:
> - **The device table has a location name, and it matches the ticket account.** Source: `db_followup.py` F4, in
>   `verification/outputs/fu/fu_summary.md` and `fu_location_vs_ticket_agreement.csv`.
>   - `devices.location_name` equals the ticket's account for 99% of ticketed devices: 2,972 exact and 38 after
>     normalising, of 3,041.
>   - It attributes **6,171 of 7,183 devices (86%)**, including machines that never had a ticket, to one account
>     each, across 666 accounts.
>   - Customer-level (facility) exposure rates therefore look feasible for most of the fleet. The caveats:
>     - it is a current snapshot, not history;
>     - accounts are facilities, not health systems;
>     - IPA should confirm the field comes from the asset record.
>   - No customer-level rate has been computed yet. *[Updated 21 Oct: computed from IPA's installed-base list;
>     docs/06 §4.]*
> - **Host as a key** (`verification/outputs/db/db_host_class_fleet_share.csv`, `db_accounts_per_host.csv`,
>   `db_hosts_per_account.csv`):
>   - At account level, single-account hosts hold 59.6% of the fleet and multi-account hosts 27.2%, so host is not a
>     facility key.
>   - Most accounts sit on one host: 645 of 671.
>   - The system-level test in §7 (D4/D5) still needs IPA's instance-to-organisation list.
> - **Unmatched ticket serials** (`db_unmatched_near_match.csv`, `db_unmatched_profile.csv`):
>   - None of the 732 matches after case, character or leading-zero normalisation, so simple formatting differences
>     do not explain them.
>   - The unmatched share is highest for the ScrubExchange (83%) and ScrubBank (40%) record types.
> - **Zac's 16 / 31 / 83 reproduce on the database.** Excluding the shared internal host and devices with no host
>   gives 14 / 26 / 82 (`db_mapping_summary_variants.csv`).

**Bottom line.**
- Zac's call is right: with the case export and device dictionary as delivered, we cannot report exposure rates per
  customer account. *[Updated 14 Oct: the database's device location name changes this for 86% of devices; see the
  Update above.]* *[Updated 21 Oct: IPA's installed-base list gives every listed machine's account; customer rates
  on installed exposure are in docs/06 §4.]*
- No field links devices to accounts. *[Updated 14 Oct: `devices.location_name` in the source database does.]* Ticket serials reach only 3,041 of 7,183 devices (42%; at most 52.5% even if
  every unmatched serial were recovered).
- `Account Name` behaves as a facility that nests in a few hundred health systems.
- His 31/83/16 crosswalk counts include counting artefacts, but they are consistent with clearView instances that
  serve more than one facility.
- Per-clearView-instance rates need no ownership data and can be computed once the DB arrives. *[Updated 14 Oct: the
  location name is now the better route to customer rates.]* *[Updated 21 Oct: superseded by the installed-base
  list (docs/06).]* Labelling them as
  customer or system rates needs IPA's parent-account and instance-to-organisation mapping, or the full asset list.
- These conclusions were re-derived by independent reviewers (data/derived/workflowB_result.json, K2a–K2j), and
  the corrections they found are folded in below.

## 1. Question

Zac's notebook reports ticket workload by `customer` (the Salesforce `Account Name`). The team would like to report
**customer-specific exposure rates**: tickets, or fault codes, per installed machine at each customer. That needs a
denominator: the machines each customer owns, including the ones that never had a ticket. Can the case export or
the clearView host in the telemetry `devices` table supply that ownership?

## 2. Zac's evidence (cells 24–25, 40)

- **[Zac]** Using exact serial links (cases JOIN devices), 31 customers span more than one observed clearView
  host, 83 hosts are linked to more than one case customer, and 16 case `Model #` labels span more than one telemetry
  `machine_type`.
- **[Zac]** His conclusion: customer-specific exposure rates are not reported "without a verified customer-to-fleet
  mapping". Fleet comparisons use the telemetry `machine_type` instead, and cell 40 lists ownership as unresolved.
- **[data]** We agree with the conclusion. The sections below show why it holds, and what would resolve it.

## 3. What we verified from the case export

### 3.1 `Account Name` is a facility, not a customer system
**[data]** All 845 accounts have exactly one address string ("City,State ZIP+4" or a Canadian postal code; there
is no street line). That alone does not prove facility granularity: the address is probably an Account-record
field copied onto every case. The facility reading rests on two other facts. Account names read as individual
hospitals or campuses, and there are almost as many distinct sites as accounts (837 address strings and 725
City+State+ZIP5 for 845 accounts). No two labels look like spelling variants of one site: they never collide after
normalisation, and the 20 pairs with fuzzy similarity ≥ 0.90 are all at different sites. Some accounts are units
within a campus. There are 837 distinct address strings because 8 addresses are each shared by two accounts.
In 6 of those 8 pairs both accounts belong to the same system (same ZIP+4 or postal code). The other 2 pairs are
co-located but different organisations: one pair matches only on a 5-digit ZIP, and one is a Canadian shared
campus (`fleet_shared_addresses.csv`).

**Physical sites and parent systems at increasing levels of grouping** (`fleet_account_granularity.csv`):

| Level | Rule | Count | Evidence |
|---|---|---:|---|
| Account (Zac's `customer`) | distinct cleaned `Account Name` | 845 | data |
| Site | distinct address string | 837 | data |
| Site (campus within system) | reviewed system + City + State + ZIP5 | 796 | inferred |
| Site (lower bound) | City + State + ZIP5, any organisation | 725 | data |
| System L2a | first distinctive name token, same state | 550 | data, algorithmic |
| System L2b | first distinctive name token, any state | 488 | data, algorithmic |
| System L3a | reviewed: brand visible in names/addresses only | 436 | data + manual review |
| **System L3b** | **L3a + documented ownership affiliations** | **320** | **inferred** |
| L3b sensitivity | each federal veterans' facility its own system | 401 | inferred |
| L3b sensitivity | each federal veterans' and military facility its own system | 416 | inferred |
| L3b sensitivity | without the 10 industry/lab accounts | 312 | inferred |

**Method.** Names are lower-cased, mis-encoded apostrophes (`?`) are repaired, and a leading "the" is dropped.
The brand key is the first token, unless that token is a generic word such as saint, memorial, university or
children's; then it is the first two tokens. A name with no distinctive token stays on its own. L2b produces 96
multi-account clusters. Manual review confirmed 85 and split 11 false merges, for example two unrelated hospitals
whose names begin with the same place word (`fleet_l2b_cluster_review.csv`). L3a also adds members whose brand
is visible in the name but which the token rule misses (acronyms; brand words that are not the first token). L3b
adds affiliations from public knowledge of hospital ownership. It changes the grouping of 223 accounts, 207 with
high and 16 with medium confidence (`fleet_review_evidence.csv`). These affiliations are not in the data, and IPA
has not confirmed them.

**Range.** The 845 facility accounts are roughly **725–837 physical sites** and **a few hundred health systems or
organisations**. The system count depends on the grouping rules and is a judgement, not a data fact:
- The reviewed tiers give 320–436; the low end needs outside knowledge.
- Even the "algorithmic" tiers depend on a hand-built stoplist. An independent check with simple alternative
  first-token rules gave 368–673 groups.

Under L3b, 659 accounts (78%) and 79.0% of tickets belong to systems with more than one account; under L3a the
ticket share is 59.8%. Across rule sets it runs from about half to four-fifths of tickets. Nine of Zac's top-10
customers belong to such multi-account systems (seven under L3a) (`fleet_facility_vs_system.csv`). For any
sponsor-facing system count, use IPA's parent-account IDs instead of these heuristics.
The case data also hold 82 federal veterans' facilities, 16 military facilities, 10 industry/laboratory accounts,
and 39 Canadian accounts (`fleet_segments.csv`, `fleet_shipping_country.csv`). The country label has two spellings
for each country.

### 3.2 The 8 serials that appear under more than one account
**[data]** Each of the 8 changes account exactly once, in time order. The gap between the last ticket under the
first account and the first ticket under the second is 7–306 days. Seven stay within one reviewed system (five on
name evidence alone) and the same city; four of those stay on the same ZIP5 campus. One moves between unrelated systems in different states.
Rules are applied in order of evidence strength (`fleet_multi_account_serials.csv`; the private file holds the
reading of each ticket's notes):

| Class | Serials | Basis |
|---|---:|---|
| A. Data-entry error noted on a switched ticket | 2 | a note says the wrong site or machine was selected |
| B. Same machine, account inconsistent | 1 | the second ticket is logged as a repeat of the same fault |
| C. Probable transfer or re-assignment within the system | 1 | clean 3/3 split, 36-day gap |
| D. Within the system, ambiguous | 3 | only one ticket on one side |
| E. Cross-system, cross-state | 1 | firmware string drops and the record type changes, so most likely a mistyped serial |

Two of the class-A/D serials (S00520, S00771) move in the same direction between the same pair of sister facilities
on one campus, months apart. That looks like one account-level re-assignment at that site, not two independent
errors. "Switches exactly once" carries information only for the 6 serials with ≥3 tickets; for the 2 with two
tickets it is automatic. Firmware is weak
evidence: the same drop from 7.1.0 to 4.2.1 also appears on serials that never change account, where Computer
Board tickets come before the change. **Interpretation [inferred]:** account switches are rare (8 of 3,773 serials, 0.2%) and almost
all stay within one system. They are not a material source of Zac's 31/83 counts, but they confirm that the case
`Account Name` is not a controlled ownership field.

### 3.3 How reliable is the serial on a ticket?
**[data]** Each of the 3,773 serials carries a single `Model #` across all its tickets (31 models span the
serials), which suggests the model is filled from an asset record. The serial, by contrast, is chosen per case.

**Wrong-machine tickets.** At least **39 tickets (0.52%)** state, in a narrow keyword search of Administrative Notes
and Resolution, that the wrong machine, serial or site was used (`fleet_serial_integrity.csv`):
- Of these, 14 are coded No Trouble Found, 7 Cancelled Request and 2 have no category.
- The other 16 carry a component category that may describe a different machine.

**Broader review.** A second, manual review over all three text fields with broader phrasing found **about 52 clear
cases (0.70%), 56 including borderline wording**. This is one reviewer's judgement and cannot be reproduced by
rule. It found 4 further tickets that record identity errors on the *machine* side: 1 wrong serial programmed into
a machine and 3 with incorrect site information in the polling configuration. Those corrupt the telemetry device
or host side of the join, not the ticket.

All of these are lower bounds, because errors that nobody noted are invisible.
*Implication for the classifier [inferred]:* exclude or flag these tickets when linking tickets to telemetry
codes.

### 3.4 Coverage: tickets can attribute at most 42% of the fleet to a customer
**[data + Zac]** The case export has 3,773 ticketed serials. Zac matched 3,041 of them to the 7,183-device
dictionary; the other 732 (19.4%) are not in it. So **at most 3,041 / 7,183 = 42.3%** of devices can be tied to a
customer through tickets. The other 4,142 devices (57.7%) had no ticket in the 13-month window and cannot be
assigned to anyone. Customers whose machines had no tickets do not appear at all (`fleet_coverage_bounds.csv`).
A customer-level denominator therefore cannot be built from tickets.

The 42.3% holds under Zac's exact, whitespace-only serial match. If every one of the 732 unmatched ticket serials
were a formatting variant of a dictionary ID, the ceiling would be 3,773 / 7,183 = 52.5%. 497 ticket serials (on 889
tickets) are 4-digit, concentrated in older models (LVD-Remote, MV, LVRR-WP), and notes refer to an "IPA"+digits
serial form. No 5-digit serial begins with 0, so Excel zero-dropping is not evident. Whether the 4-digit serials
match the dictionary is a check for the DB (D6). The denominator is the device dictionary, which may include
internal, retired or never-transacting devices (232 never transact), not the installed base.

### 3.5 A naive "tickets per ticketed machine" by customer is biased
This is a misuse to avoid, not a correction of Zac. He never computed this ratio: his cell-17 table shows cases and
affected machines side by side and explicitly disclaims rates.

**[data]** By construction all 845 customers score at least 1.0. 230 score exactly 1.0, 134 of them because they
have only one ticket. The median is 1.63 and the maximum 11.0. The score rises with workload: Spearman ρ = 0.65
with ticket count overall, and 0.44 among the 711 accounts with ≥2 tickets, since part of the overall correlation
is the 1.0 floor. The median is 2.37 for the top-10 customers by tickets, 2.45 for the top-50 and 1.50 for the rest
(`fleet_naive_rate_summary.csv`, `fleet_customer_naive_rates.csv`).

Pooled, the matched tickets come to 2.01 per ticketed device but 0.85 per device in the dictionary. That 2.36× gap
is simply 7,183 / 3,041, the reciprocal of the 42.3% coverage, not an independent result. The denominator
conditions on failure, so the score measures repeat concentration, not failure frequency. **Illustration [inferred, Poisson]**
(`fleet_truncation_illustration.csv`): if every machine at customer X has 0.1 tickets a year and every machine at
customer Y has 2.0, the true rates differ 20-fold, but the naive scores (1.05 and 2.31) differ only 2.2-fold. The
observed 42.3% ticketed share is below the 57.3% that a common rate would give. That gap points to strong
machine-level heterogeneity, assuming all dictionary devices were in service for the whole window.

## 4. Interpreting Zac's 31 / 83 / 16

- **What a host is [inferred].** `clearview_url` identifies a hosted clearView instance. The one URL visible in
  the code is IPA's shared internal production instance. Its form suggests the pattern `<org>.thinkipa.net`,
  roughly one instance per customer organisation. We have not seen any other URL.
- **Why accounts and hosts overlap [inferred].** If an instance serves a health system and accounts are
  facilities, then every host serving a multi-facility system is "linked to >1 customer" by design. That is what
  the 83 measures. We count 109 (L3a) to 134 (L3b) multi-account systems (`fleet_host_expectations.csv`). Fewer
  would appear in Zac's join, because 19.4% of ticketed serials are unmatched and the hosting of federal
  facilities is unknown.

  What the 83 shows is narrower. It is consistent with *any* hosting coarser than the facility: system, regional,
  multi-system or partner-hosted instances, or a mix that includes on-premise servers. It argues against
  one-instance-per-facility hosting. It does not by itself show that hosts are health systems, and it is not by
  itself evidence of data error. Only the host × system cross-tab (D4) and IPA's list of which organisation each
  instance serves can settle it. The `<org>` naming pattern is extrapolated from a single internal URL.
- **The 31 multi-host customers are the more informative number.** They are 4.9% of the 632 customers with ≥2
  ticketed serials (a lower bound on the rate, because some serials do not match). If host ≈ system, a single
  facility should rarely span hosts. The possible sources are: (a) the shared internal host; (b) a system that
  runs more than one instance; (c) tickets with a wrong serial that belongs to another system's machine; (d) real
  cross-system transfers. §3.2 suggests (d) is about 1 case.
- **Shared internal host [data, logic].** Zac's `COUNT(DISTINCT d.host)` counts the shared host like any other
  host (only NULL is ignored). It can add at most **1** to the 83. To the 31 it adds one for every customer with
  one machine on the shared host and another elsewhere. Zac's cohort table shows 18 in-window unplanned tickets
  on the shared host. Out-of-window and planned tickets are not counted there, so the inflation of the 31 cannot
  be bounded from the printed outputs. It could be anywhere from none to more than half. **[pending DB: D2, D3]**
- **Host key spelling [data, logic].** `Host NNN` is keyed on the raw URL with no trimming or lower-casing, yet
  the shared-host flag uses `rstrip('/')`. If any instance appears both with and without a trailing slash, it
  counts as two hosts and inflates both numbers. **[pending DB: D1]**
- **The 16 models [data, logic].** Zac maps NULL `machine_type` to the string `Unknown` before
  `COUNT(DISTINCT)`, so `Unknown` alone can make a model "multi-type". In the 15 printed rows, 2 models (A-LC,
  LC-30) qualify only through `Unknown`. One (LVD-Remote-2.0) adds two single-machine anomalies, and one
  (LVD-Remote) has a genuine second type (16 machines) (`fleet_model_type_note.csv`). The full count needs the DB.
- **Upper bounds?** Within Zac's matched set, the artefacts above (shared host, `Unknown` type, URL spellings) make
  the 31 and 16 overstate genuine mismatches. They are still not upper bounds on true cross-instance ownership:
  - 19.4% of ticketed serials do not match.
  - NULL hosts are ignored.
  - Machines that never had a ticket are invisible.

  URL normalisation is also not monotone for the 83. Merging two spellings that each carry a different single
  customer creates a new multi-customer host, so a cleaned 83 can go up as well as down.
- **Implication [inferred].** Per-instance rates (tickets per active machine-month, faults or stock-outs per 1,000
  transactions, unticketed machines included) need no ownership data. They join tickets to devices by serial and
  can be computed as soon as the DB is available. A clean host-to-system mapping is needed only to *label* them as
  health-system rates, or to sum instances into systems. Facility-level (Account Name) rates are possible only
  where IPA confirms that an instance serves a single facility. Telemetry does not identify facilities within a
  multi-facility instance. A clearView URL is also a current snapshot, so host assignment must be stable over the
  window for any of this to hold.

## 5. What the evidence supports

| Claim | Status |
|---|---|
| Ticket workload (counts) by facility account | Supported. Counts only, not rates |
| Rates by telemetry `machine_type` (Zac §3.3) | Supported; denominators come from telemetry, not tickets |
| Customer-specific exposure rates from tickets | **Not supported.** At most 42% fleet coverage; denominator conditions on failure. *[Updated 14 Oct: from the device location name instead, feasible for 86% of devices pending IPA's confirmation.]* *[Updated 21 Oct: computed from IPA's installed-base list for 9,055 machines at 1,065 accounts (docs/06 §4).]* |
| "Tickets per machine" by customer from tickets | **Not supported.** ≥1.0 by construction and tracks workload |
| Facility = owner of a fleet | **Not supported.** Facilities nest in a few hundred systems; roughly half to four-fifths of tickets are in multi-account systems, depending on grouping rules |
| Per-clearView-instance rates (incl. unticketed machines) | **Computable [pending DB]**, no ownership data needed; label as "clearView instance". *[Updated 14 Oct: DB available; not yet computed.]* |
| System-level exposure rates using host as key | **Possible [pending DB]** if D1–D5 pass and IPA confirms which organisation each instance serves. *[Updated 14 Oct: host is not a facility key (single-account hosts hold 59.6% of the fleet); the system-level test still needs IPA's list.]* |
| Ticket serial = physical machine | Mostly. At least 0.5% (about 0.7% on manual review) of tickets are noted as wrong-machine; 8 serials switch account |

### 5.1 Does the project need customer-specific exposure rates?
No objective in the project plan requires them. Objectives 1–4 and the classifier work at the level of machine type
and of individual machines within a type. The one customer item is the stock-out "customer hotspot table". That is
a per-use rate (per 1,000 transactions), so it needs no installed-base denominator, and it can be built per
clearView instance once the DB is here: exclude shared and NULL hosts, apply a volume screen, and label it
"clearView instance".

Attributing telemetry to accounts through ticketed serials would cover only 42% of devices and select on failure.
The ownership gap should not block the plan's deliverables. One caveat for the "confirmed machine-family mapping"
deliverable: three case models (A-MC, A-SC, LVD-LOCAL; 16 serials) have no device-dictionary match, and A-LC matches
only 7 of 44 serials. The A-series is poorly linked.

## 6. Recommendation: the minimal ownership register to request from IPA

**Lighter first step.** Ask for (a) Account ID and Parent Account ID added to the existing case export, which settles
the system grouping for workload counts, and (b) IPA's list of which organisation each clearView instance serves
and what sits on the internal instance, which labels the per-instance telemetry rates. Together these cover the
project-plan deliverables.

**Full register.** *[Updated 21 Oct: IPA sent the active list: serial, account, model, install date and service
status. Parent account IDs and removal dates are still needed (docs/06 §8).]* For exposure rates by customer or
system, ask for the installed-base or asset list behind the
case Serial # lookup. It may be the standard Salesforce Asset object, a custom equipment object or an ERP table. It
should have one row per machine and be joinable on serial = `external_device_id`. The rates are possible only as
far as the register is complete; non-networked or out-of-contract machines may be missing.
1. `serial`, `model`, product line, asset status (active / retired / loaner / demo / refurbished);
2. `account_id` and account name (the facility), **`parent_account_id`** and name (the health system or group);
3. ship-to or installed address (street line), **install date**, and **removal, transfer or decommission date**,
   ideally the Asset's account-change history;
4. the clearView instance or host assigned to the asset, and the service-contract or coverage flag.

Also ask: (a) whether one clearView instance corresponds to one parent account; (b) what the shared internal host
holds (demo, loaner, refurbishment, staging); (c) whether a case's serial is chosen from the asset lookup or typed.

## 7. Decisive checks once the DB arrives *[partly run 12–14 Oct: the account-level host checks and unmatched
serials, in the Update above; the system-level D4/D5 still need IPA's list]*

`customer_fleet_audit.py --db PATH` runs D1–D7 against the source `devices` table plus the Excel cases. `--with-
telemetry` adds D8, which scans all 17 GB. Pseudonymous results go to `fleet_db_D*.csv`. The private
host-URL-to-accounts listing for manual review goes to `data/private/fleet_private_db_hosts.csv`. For agents using
Zac's `analysis.sqlite`, load `data/private/fleet_private_customer_system_map.csv` as table
`customer_system(customer, system)`. It holds pseudonyms only.

| Check | Query (Zac's analysis.sqlite schema) | Decision rule |
|---|---|---|
| D1 host spelling | in the source DB: `GROUP BY lower(rtrim(replace(clearview_url,'https://',''),'/'))` with `COUNT(DISTINCT clearview_url)>1` | any collapse: re-key hosts and recount 31/83 |
| D2 recount | cell-25 SQL with `WHERE d.shared_internal_host=0 AND d.host IS NOT NULL`; again with `c.customer` replaced by `s.system` (JOIN `customer_system`); models with `d.machine_type<>'Unknown'` | if the system-level, shared-excluded counts fall to near 0, host ≈ system |
| D3 decompose the 31 | per multi-host customer: hosts, machines and tickets per host, shared flag, whether the minority host has 1 machine with 1 ticket, whether one of the 8 serials is involved | share explained by shared host, stray serials, transfers or split fleets |
| D4 classify hosts | per host: devices, ticketed devices, `COUNT(DISTINCT customer)`, `COUNT(DISTINCT system)`, classed as no tickets / single customer / single system / multi-system / shared | device share on single-system hosts = share of fleet with a usable system denominator |
| D5 hosts per system | `SELECT system, COUNT(DISTINCT host)` over non-shared, non-NULL hosts | host usable as system key if ≥90% of systems and of devices sit on one host (threshold is our judgement) |
| D6 unmatched serials | the 732 unmatched serials by model, record type and country; tolerant re-match (case, leading zeros, hyphens) | whether they are non-networked models, Canada, retired units or entry errors |
| D7 invisible fleet | per host: devices, `device_status` mix, share never ticketed | how much ticket-derived fleets understate installed fleets |
| D8 system denominators | per host and month: `COUNT(DISTINCT machine_id)` from `telemetry_month_code` | active machine-months for hosts that pass D4/D5 |

**Interpretation rule.** If D1 is clean, D4 puts ≥90% of ticketed devices on single-system hosts, and D5 puts
≥90% of systems on one host, system-level exposure rates can be reported with host as the key. They must be
labelled "clearView instance (≈ health system)", not "customer". Otherwise, report only `machine_type`-level rates
until IPA provides the Asset register in §6.
