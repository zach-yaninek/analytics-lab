# Customer-to-fleet ownership: can tickets be put on a customer's installed fleet?

*Script:* `verification/customer_fleet_audit.py` (run `python3 -I verification/customer_fleet_audit.py [--db PATH]`).
*Outputs:* `verification/outputs/fleet_*.csv` (pseudonymous). Real names, addresses, serials and the hand-reviewed
account-to-system map are kept in `data/private/fleet_private_*.csv` (gitignored).
*Evidence tags:* **[data]** = computed here from the case export; **[Zac]** = Zac's printed output, not re-run (the
telemetry DB is not in this container); **[inferred]** = our reasoning or outside knowledge, not verified by IPA;
**[pending DB]** = decided by the checks in §7 once the DB arrives.

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
is no street line). There are 837 distinct address strings, because 8 addresses are each shared by two accounts.
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

**Range.** The 845 facility accounts are roughly **725–837 physical sites** and **320–436 health systems or
organisations**; the low end of the system range needs outside knowledge. Under L3b, 659 accounts (78%) and
**79.0% of tickets** belong to systems with more than one account. Under L3a the ticket share is 59.8%. Nine of
Zac's top-10 customers belong to such multi-account systems (seven under L3a) (`fleet_facility_vs_system.csv`).
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

Two of the class-A/D serials move between the same pair of sister facilities on one campus. Firmware is weak
evidence: the same drop from 7.1.0 to 4.2.1 also appears on serials that never change account, where Computer
Board tickets come before the change. **Interpretation [inferred]:** account switches are rare (8 of 3,773 serials, 0.2%) and almost
all stay within one system. They are not a material source of Zac's 31/83 counts, but they confirm that the case
`Account Name` is not a controlled ownership field.

### 3.3 How reliable is the serial on a ticket?
**[data]** `Model #` is constant within every one of the 3,773 serials, which suggests it is filled from an asset
record. The serial, by contrast, is chosen per case. 39 tickets (0.52%; 39 distinct serials) state that the wrong
machine, serial or site was used. Of these, 14 are coded No Trouble Found, 7 Cancelled Request and 2 have no
category. The other 16 carry a component category that may describe a different machine
(`fleet_serial_integrity.csv`). This is a lower bound, because errors that nobody noted are invisible.
*Implication for the classifier [inferred]:* exclude or flag these tickets when linking tickets to telemetry
codes.

### 3.4 Coverage: tickets can attribute at most 42% of the fleet to a customer
**[data + Zac]** The case export has 3,773 ticketed serials. Zac matched 3,041 of them to the 7,183-device
dictionary; the other 732 (19.4%) are not in it. So **at most 3,041 / 7,183 = 42.3%** of devices can be tied to a
customer through tickets. The other 4,142 devices (57.7%) had no ticket in the 13-month window and cannot be
assigned to anyone. Customers whose machines had no tickets do not appear at all (`fleet_coverage_bounds.csv`).
A customer-level denominator therefore cannot be built from tickets.

### 3.5 A naive "tickets per ticketed machine" by customer is biased
**[data]** By construction all 845 customers score at least 1.0. 230 score exactly 1.0; the median is 1.63 and the
maximum 11.0. The score rises with workload (Spearman ρ = 0.65 with ticket count): the median is 2.37 for the
top-10 customers by tickets, 2.45 for the top-50 and 1.50 for the rest (`fleet_naive_rate_summary.csv`,
`fleet_customer_naive_rates.csv`). Pooled, the matched tickets come to 2.01 per ticketed device but 0.85 per device
in the dictionary, a 2.36× inflation. The denominator conditions on failure, so the score measures repeat
concentration, not failure frequency. **Illustration [inferred, Poisson]**
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
  facilities is unknown. The 83 is therefore the size expected if host ≈ system, but it does not prove it.
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
- **Implication [inferred].** If the DB shows one host per system, the host can be the key for a *system-level*
  fleet denominator: devices and active machine-months per host, including unticketed machines. It can never give
  *facility-level* (Account Name) rates, because facilities within a host are not identified in telemetry.

## 5. What the evidence supports

| Claim | Status |
|---|---|
| Ticket workload (counts) by facility account | Supported. Counts only, not rates |
| Rates by telemetry `machine_type` (Zac §3.3) | Supported; denominators come from telemetry, not tickets |
| Customer-specific exposure rates from tickets | **Not supported.** At most 42% fleet coverage; denominator conditions on failure |
| "Tickets per machine" by customer from tickets | **Not supported.** ≥1.0 by construction and tracks workload |
| Facility = owner of a fleet | **Not supported.** Facilities nest in ~320–436 systems; 79% of tickets are in multi-account systems |
| System-level exposure rates using host as key | **Possible [pending DB]** if D1–D5 pass |
| Ticket serial = physical machine | Mostly. ≥0.5% of tickets are noted as wrong-machine; 8 serials switch account |

## 6. Recommendation: the minimal ownership register to request from IPA

Ask for the Salesforce **Asset (installed base)** export, one row per machine, joinable on serial =
`external_device_id`:
1. `serial`, `model`, product line, asset status (active / retired / loaner / demo / refurbished);
2. `account_id` and account name (the facility), **`parent_account_id`** and name (the health system or group);
3. ship-to or installed address (street line), **install date**, and **removal, transfer or decommission date**,
   ideally the Asset's account-change history;
4. the clearView instance or host assigned to the asset, and the service-contract or coverage flag.

Also ask: (a) whether one clearView instance corresponds to one parent account; (b) what the shared internal host
holds (demo, loaner, refurbishment, staging); (c) whether a case's serial is chosen from the asset lookup or typed.

## 7. Decisive checks once the DB arrives

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
