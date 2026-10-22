# Association study protocol: ticket fields and the telemetry codes before each ticket

*22 October 2026. Status: **pre-specified protocol, draft for team review.** No ticket-against-control result by
Category has been computed. One power check before v0 counted pairs, discordant pairs and control-window prevalence for
three Category sets of a hypothetical crosswalk (§10, look 4). The analysis script, `verification/association.py`, is
to follow. It reads only the committed files listed in §1 and runs without the database. This document fixes what will
be computed, on which tickets and how, before any ticket-against-control result by Category is seen. Later changes are
dated amendments (`*[Amended <date>: …]*`), and the original text is kept. Every count in §2–§6 was computed from
those files during planning. `association.py` re-derives each one as a check and writes it to
`verification/outputs/assoc/as_summary.json`.*

**Why a protocol first.** TODOS.md item 1 asks for a crosswalk from ticket Categories to telemetry codes, agreed with
the team and then with IPA. Items 2–6 test it. If the crosswalk or the tests were chosen after looking at which
Categories line up with which codes, the results would confirm whatever was looked at. So two things are frozen before
anything is run by Category:
- the crosswalk, `verification/reference/crosswalk_v0.csv`;
- the population, outcome, hypotheses, estimators and decision rules.

§10 lists every look at the data so far.

**How this was designed.**
- We drafted the design, and an independent statistical reviewer critiqued it.
- Two review panels then each worked through three lenses, with a skeptic assigned to every major finding:
  - the first reviewed the design (data feasibility, statistics, alignment with TODOS and repo conventions);
  - the second reviewed this document and the crosswalk (implementability, facts, conventions).
- Every surviving finding is applied here: 21 from the first panel and 24 from the second.
- Three independent drafters produced the crosswalk; the majority vote is v0 (§3).

## Bottom line
1. **Primary question (H2a, specificity).** Take one set of codes, for example the SAM codes.
   - For every ticket, we check whether any of them appeared in the machine's final 7 days before the ticket.
   - We also check the final 7 days of a ticket-free 30-day stretch on the same machine 35 days earlier: the control.
   - H2a asks whether the set rises from control to ticket more for tickets whose Category points at it than for
     tickets whose Category points at unrelated codes.
   - Each set is compared in turn, and the sets are pooled for the test.
   - Comparing against tickets for other faults is designed to remove two things: the generic effect that any failing
     machine logs more codes, and slow drifts. It removes them only where they change the odds of the set equally
     before both kinds of ticket, within a machine type and quarter (§11).
2. **Then, in order, only if H2a succeeds:**
   - **H1:** does a ticket's own code set appear more often before the ticket than in the control?
   - Then each set separately.
   - TODOS items 2–6 (enrichment, recency, match rates, machine types, sensitivities) are reported around them. Every
     estimate is shown, tested or not.
3. **Population:** 2,950 unplanned tickets on 2,376 machines that transact.
   - Each ticket's 30-day window, and its clean control window on the same machine 35 days earlier, start after
     telemetry begins and after the machine's first active day.
   - The ticket window starts on or before the machine's last active day.
   - Neither window contains another ticket.
4. **Outcome:** a code of the set appears in the final 7 days of the window. The TODOS 30-day "last 10 codes" outcome
   is a pre-specified secondary.
5. **Crosswalk v0 is a team-review draft, and results using it are provisional.** The confirmatory version, v1, is
   frozen when IPA's code definitions arrive, before any run that uses it.
6. **What a result can and cannot show.**
   - **If H2a succeeds,** the codes a Category points at rise before that Category's tickets more than before other
     tickets. In other words, the Category recorded at closure tends to agree with the codes logged just before the
     ticket.
   - **What that does not show:**
     - that codes predict tickets, because only the weeks before tickets are examined;
     - that Categories are correct;
     - that the provisional code meanings are IPA's.
   - **Built-in agreement.** If technicians read clearView when they set Category, part of the agreement is built in
     (§11).
   - **If H2a does not succeed,** docs/08 will say the data do not show a Category-specific match under crosswalk v0,
     not that there is none. Several sets have few tickets (§4).

## 1. Data
Everything comes from committed, pseudonymous files. No raw file or database is needed. **All CSVs are read as
strings** (`dtype=str, keep_default_na=False`). Codes keep their leading zeros, and an empty list is `''`.
- **`verification/outputs/fu/fu_ticket_last10.csv`** (`db_followup.py` parts F1 and F2): 6,113 device-matched tickets
  × 4 windows. For each window it gives:
  - all events;
  - non-success events (any code other than `00`);
  - `distinct_codes`, the number of distinct non-success codes, uncapped;
  - the **last 10 distinct non-success codes**, ordered by most recent occurrence. Each code comes with the hours
    from that occurrence to the window's end (to A for the two guard windows), to 2 decimals (`db_followup.py` L316),
    and its count over the whole window.
  - On all 24,452 rows the list holds min(10, `distinct_codes`) codes.
- **`verification/outputs/fu/fu_devices.csv`** (by M id): machine type, assigned customer, ticket customer, first and
  last active day, and whether the machine transacts.
- **`verification/outputs/db/db_codes_buckets.csv`:** the 49 values seen in the telemetry: 00 "OK", 46 non-success
  codes and two malformed values. It gives their descriptions and the team's provisional bucket
  (`verify_with_db.LOOKUP`; not validated by IPA).
- **`verification/reference/crosswalk_v0.csv`:** this protocol's crosswalk (§3).
- **`verification/outputs/htm_device_exposure.csv`** (M id to S id) and **`verification/outputs/fleet/fx_machine_flags.csv`**
  (`install_year` by S id): used only for S5's secondary check.
- **`verification/outputs/flags/flags_by_case.csv`** (optional; not yet produced): the local text-flag export (§6). It
  is used only for S2 and S10.

**Windows** (`db_followup.py` L57–62, L292–416). A is the ticket's creation time, converted from US Eastern to UTC.

| Window | Span | Hours measured from | Role |
|---|---|---|---|
| `corrected_guard0` | [A − 30 d, A) | A | ticket window (primary) |
| `corrected_guard30`, `corrected_guard60` | [A − 30 d, A − 30 min), [A − 30 d, A − 60 min) | A | guard-band sensitivity (S3) |
| `control_minus35d` | [A − 65 d, A − 35 d) | its own end, A − 35 d | paired control |

`control_clean` is true when no other ticket on the machine, of any kind, opened in [A − 67 d, A − 5 d). That means
no other ticket's 30-day window overlaps the control, and none opened in the 2 days before it.

## 2. Definitions
- **A1. Unplanned.** `service_group` is not Planned work, Cancelled request or Duplicate case (Zac's `service_cases`
  view; `common.CASE_VIEWS`). No Trouble Found and Missing trouble code stay in.
- **A2. Paired set.** Unplanned tickets meeting all of:
  - both windows have `lookback_truncated` = `after_telemetry_end` = False;
  - `control_clean` is true.

  This gives **3,259 tickets on 2,504 machines**, and it reproduces the TODOS first look exactly.
- **A3. Primary population.** Two steps from the paired set.
  1. Drop the **157** tickets with another ticket on the machine opened in [A − 5 d, A). That leaves 3,102.
  2. Drop the **152** tickets whose ticket window lies outside the machine's telemetry span. That leaves **2,950
     tickets on 2,376 machines.** The 152 are:
     - 102 tickets on 85 machines that never transact (`transacting` = False; all have a blank `first_active`, and
       both their windows are empty);
     - 50 tickets on 47 machines whose `last_active` is earlier than the window's first day (the date of A − 30 d).

     This step is the counterpart, at the end of the span, of the first-active rule (`db_followup.py` L349–350). It
     follows docs/06 (tickets inside each device's span).
  - **Machines that went silent.** 42 kept tickets are on machines whose last active day is before the ticket's day,
    31 of them before A − 7 d. They stay in, because a machine falling silent can be the fault itself. They are
    counted.
  - **No ticket in either window.** Neither window, nor the 2 days before it, contains another ticket opened on the
    machine.
  - **One ticket per episode.** Any two primary tickets on one machine are at least 67 days apart. So every primary
    ticket is the first of its own 7-day episode (D5 in docs/05).
  - **The asymmetry that remains, stated exactly.** It points in two directions.
    - **Toward no effect.** The ticket window has at least 37 ticket-free days before it, while the control window can
      start as little as 2 days after an earlier ticket. 292 primary tickets have such a ticket in [A − 102 d,
      A − 67 d), and 56 of those are within 9 days of the control's start. This is a lower bound: for the 341 tickets
      before 11 November 2025, that span starts before the case history does. The earlier visit's after-effects can
      inflate the control.
    - **Away from no effect.** Controls are also conditioned on no ticket in [A − 35 d, A − 5 d). If code bursts tend
      to lead to tickets, that depletes code-heavy controls. This biases H1, item 2 and the item 4 fraction away from no
      effect. In H2a it is removed only if the depletion is the same before target and comparator tickets, which is not
      measured.
    - **Partly unobserved guard.** For 17 tickets, A − 67 d falls before the case history begins. The case history
      begins on 1 August 2025 at 00:00 US Eastern, which is 04:00 UTC, and A is compared with it in UTC.
  - **Categories.** Analyses by Category also drop the 39 primary tickets with no Category. 12 of them have a Trouble
    Code and count in the overall rows only.
- **A4. Text flags are not a primary exclusion.** A ticket that quotes a code or mentions clearView often does so
  *because* the codes were there, so excluding such tickets selects on the outcome. The flags enter as sensitivities
  (S2).
- **A5. Machine type.** From `fu_devices.csv`, normalised:
  - lower case;
  - strip a leading `package name:` and any whitespace after it (regex `^package name:\s*`, as in
    `fleet_exposure.py` L730);
  - blank becomes `Unknown`.

  The primary population has 23 named types, plus Unknown on 14 tickets. Unknown is left out of every analysis
  restricted by type, and counted.
- **A6. Calendar quarter.** The quarter of the ticket's creation date, US Eastern (`opened_at_eastern`).
  - The primary population covers 2025-Q4 to 2026-Q3: 731, 870, 812 and 537 tickets.
  - It starts on 5 October 2025, because the control window needs telemetry from 1 August 2025.
- **A7. Target set.** A Category's `target_codes` in the crosswalk.
  - A ticket is **mapped** when its Category has a non-empty target set. There are 1,736 mapped primary tickets.
  - Categories with an identical target set form one set s. In v0 all ten sets are distinct.
- **A8. Code present within k (k < 720 h).** A code is present within k when it is in the window's last-10 list with
  stored hours below k.
  - **Undetermined.** A window is *undetermined at k* when `distinct_codes` is above 10 and the 10th listed code's
    hours are below k. Then a code not in its list may still have occurred within k. When `distinct_codes` ≤ 10 the
    list is complete, and nothing is undetermined.
  - **Not judged per outcome.** Undetermined is a property of the window and k, not of the outcome. Keeping a window
    only when its outcome happens to be listed would select on the outcome.
  - **Pairs left out.** A pair is left out when either of its windows is undetermined at 7 d. The remaining **2,911
    pairs** are used for **every k ≤ 7 d** and every analysis: buckets, codes, target sets, marginal shares, H2a, H1,
    item 3 and item 4. Curves over k therefore run over one fixed set of pairs.
    - At 7 d, 29 ticket and 17 control windows are undetermined, which removes 39 pairs.
    - At shorter k, only 1 window (at 24 h) would be undetermined, and that pair is already among the 39.
  - **What the 2,911 pairs hold:** 610 account clusters, 2,350 machines and 1,706 mapped tickets.
  - **At 720 h (30 d)** the outcome is membership of the last-10 list, which is the TODOS definition. All 2,950 pairs
    are used. 137 ticket and 94 control windows have more than 10 distinct codes. There, list membership can miss a
    code that did occur (§12).
- **A9. Discordant pairs.** For a set s and a ticket:
  - **b:** s is present in the ticket window but not in the control;
  - **c:** the reverse.

  The matched odds ratio is b/c, the case-crossover estimand. A value of 1 means s is as often present only in the
  control as only before the ticket. Above 1 means it is more often present only before the ticket. Pairs where both
  windows have s, or neither does, carry no information about it.
- **A10. Able to emit.** Machine type τ can emit set s, for machine m of that type, when some code of s appears
  anywhere in the last-10 list of the control window of **at least 5 other machines** of type τ.
  - **Windows counted:** the control windows, from all 6,113 tickets, that are clean and not lookback-truncated: 3,388
    windows.
  - **Why only those:** a clean control overlaps no ticket's 30-day window, so no ticket-window period enters the rule,
    and neither does any Category.
  - **Exclusions:** machine m itself, and Unknown type, which never emits.
  - **Check:** the emitting types for each set are written out and checked.
  - **Consequence on v0:** Counterweight System's codes 66 and 67 are emitted only by sbsx-49 and sbsx-51. Its 47
    primary tickets are all on other types, so the set cannot be tested (§3).
- **A11. Clusters.** Cluster labels are used as given, so a ticket_customer equal to another machine's
  assigned_customer is the same cluster.
  - **Account clusters,** for H2a, H2b, H1 and the per-set tests. The cluster is the machine's `assigned_customer`,
    else its `ticket_customer`, else the machine itself. That gives **613 clusters** in the primary population:
    2,902 tickets by assigned customer and 48 by ticket customer. Category is assigned by service staff working per
    account.
  - **Machine clusters,** for the item 2 tables (as TODOS asks), and as a sensitivity for H2a (S8).
- **A12. Reporting threshold.** A *reported row* (a bucket, code, Category, Trouble Code, machine type, or the 157)
  needs at least 30 pairs and at least 10 discordant pairs. Otherwise it is "not estimable". A12 never removes a
  Mantel–Haenszel stratum or a permutation stratum: every stratum enters the sums.
- **A13. Zero counts when resampling.** This applies to every ratio given a bootstrap interval.
  - **Zero cases.** In a replicate, a zero numerator gives a ratio of 0, a zero denominator gives +∞, and 0/0 is
    undefined.
  - **Interval method.** Percentile intervals use `np.nanpercentile(x, [2.5, 97.5], method='inverted_cdf')`, not
    `fleet_exposure.pct_ci`, whose linear interpolation turns infinite replicates into a missing endpoint.
  - **Reporting.** An infinite endpoint is reported as unbounded. Undefined replicates are left out, and counted.

## 3. The crosswalk (item 1)
**File: `verification/reference/crosswalk_v0.csv`.**

**Columns:** `trouble_code, category, matched_tickets, target_codes, target_bucket, confidence, rationale, drafters,
review_note, status, version`.
- `target_codes` is a `|`-separated list, possibly empty.
- `target_bucket` is one of:
  - the team's provisional buckets;
  - `No identifiable issue` (No Trouble Found);
  - `Not in telemetry`;
  - `Administrative` (dispositions, not issues).

**What each column is used for.**
- **`target_codes`** drives H2a, H2b, H1, the per-set tests, item 4's code match and the negative controls.
- **`target_bucket`** classifies tickets, never codes. It has three uses:
  - H2b's comparator (Not in telemetry or Administrative), including the S1 tickets;
  - the No Trouble Found row;
  - item 4's "matching bucket" (§5).
- **Codes keep their own team bucket.** The item 2 and item 3 bucket tables use each code's own team bucket from
  `db_codes_buckets.csv`. So code 76 stays Operational status on a Packer ticket, and 16 stays Mechanical fault on a
  Weight Scale ticket.

**Codes and bucket disagree in 5 of the 10 mapped Categories** (2,059 of their 3,298 matched tickets):
- Deposit Door: 19 and 78 are User behavior;
- Main Door: 31 is Mechanical fault;
- User Door: 02 and 11 are Mechanical fault;
- Packer: 76 is Operational status;
- Weight Scale: 16 is Mechanical fault.

This is why the specificity tests use code sets: the team's buckets cut across components.

**How v0 was made.**
- **Three independent drafters.** They worked from the code descriptions and provisional buckets, the Category and
  Sub Category names, and the machine families each Category occurs on. Each had a different approach:
  - a *literal* drafter: a code only if its description names the component;
  - a *mechanism* drafter: codes a fault of the component would directly cause;
  - a *coverage-skeptical* drafter: codes only when a fault surely shows in a transaction outcome.
- **Blind drafting.** None of them saw any data relating tickets to codes.
- **Majority vote.** A code enters a Category's set when a majority of drafters chose it, and the bucket is the
  majority bucket. The `drafters` and `review_note` columns record each drafter's choice and where they disagreed.
- **Confidence measures agreement.**
  - *High:* all three chose the same codes and bucket (26 rows).
  - *Medium:* two drafters' choices equal the row (9).
  - *Low:* only one drafter's codes equal it (6).
- **Coverage.** 10 Categories have a non-empty set. Together they cover 3,298 of the 6,113 matched tickets, and 1,736
  primary tickets.
- **Overlap.** Improper Use {04, 19, 60, 61, 78} and Deposit Door {19, 20, 78, 79, 80} share codes 19 and 78. Under
  H2a, each leaves the other's comparison (§4).
- **Codes in no set.** Eleven of the 46 non-success codes are in no set:
  - 01 "Incomplete Transaction";
  - 03 "Item not available" (a Stock-out negative-control code, §4);
  - 05 "Already Dispensed";
  - 15 "Blocked Door";
  - 26 "Open Door Dispense";
  - 28 "UNMAPPED CODE 28" (Undefined);
  - 56 and 57 "Top/Bottom Door not Closed";
  - 58 and 59 "Top/Bottom Door not Locked";
  - 81 "Opening Door Blocked".
- **Electronics.**
  - Three of the four largest Electronics Categories have empty sets: Touchscreen (472 matched tickets), Power Supply
    (170) and Badge Reader (91). No code describes them.
  - The team's Electronics bucket is codes 05, 13 and 25. So bucket-level Electronics enrichment can be tied to a
    Category only through Computer Board (13, 25).

**How the team reviews v0** (the "team" step of item 1).
- **What reviewers may use:**
  - the code descriptions;
  - the Category and Sub Category names;
  - the machine families;
  - the emitting types under A10, which come from control windows only, with no Category;
  - what they know about the machines.
- **What reviewers may not use.** Until v0 is frozen, no reviewer computes, requests or looks at any count or table of
  codes by Category, Sub Category or Trouble Code in ticket or control windows. That covers `fu_ticket_last10.csv` and
  the database. If anyone has, it is recorded in §10 and v0 is frozen unchanged.
- **Answers.**
  - Every question below has a default, which is v0. A question left unanswered keeps its default.
  - A question the team cannot settle without IPA's code definitions also keeps its default and is added to §13.
- **Recording.** A changed row gets the `review_note` "Team <date>: <decision and reason>", and is listed under the
  table as a dated amendment. At sign-off every row's `status` becomes "team-approved <date>, pending IPA".
- **Sign-off.** The date and the reviewers are recorded next to the frozen hash, with each reviewer's confirmation that
  they followed this rule.
- **IPA's review for v1** follows the same rule. IPA is sent this section, the crosswalk and the code descriptions, but
  no results by Category. Each change from v0 to v1 cites an IPA code definition.

**Rows for review.** Counts are matched tickets and primary tickets. The primary count is the most a Category can put
into H2a's target group. "T on emitting types" is the count left after A10.

| Category (matched / primary), confidence | v0 | Question, with the default |
|---|---|---|
| Deposit Door (994 / 573), low | 19, 20, 78, 79, 80; Door issue | Keep 19 "Deposit Door not Opened" and 78 "Receiver Deposit Door not completely opened"? The team's lookup calls them user behaviour, and the skeptic drafter left them out. Add 81 "Opening Door Blocked" (mechanism only)? **Default: keep 19 and 78; no 81.** T on emitting types: 563. |
| Computer Board (529 / 291), low | 13, 25; Electronics | Keep 25 "No Communications with Dispenser", which does not name the board? Add 05 "Already Dispensed" (mechanism only)? Does 13 "Invalid Driver Board Response" name the computer board, or a separate driver board (IPA)? **Default: keep 13 and 25; no 05.** T: 208. |
| SAM (491 / 220), medium | 14, 17, 18, 32–35; Mechanical | Keep 14 "Broken Limit Switches", which does not name the SAM? **Default: keep.** T: 213. |
| Curtain (477 / 215), medium | none; Mechanical | Map 15 "Blocked Door" and 56/57 "Top/Bottom Door not Closed" under Door issue (mechanism only: the curtain guards the door opening)? **Default: no codes.** |
| User Door (399 / 223), low | 02, 11, 27, 41–48; Door issue | Keep the generic lock codes 02 "Door did not unlock", 11 "Door Did not Open" and 27 "Door did not lock"? The literal drafter kept only 41–48; the mechanism drafter also added 14, 15 and 26. With 02/11/27 in, alEx and mlc types count as able to emit the set (A10). **Default: keep 02, 11 and 27.** T: 220. |
| Power Supply (170 / 85), medium | none; Electronics | Map 13 and 25 for low voltage (mechanism only)? If so, Power Supply joins Computer Board's set (A7). **Default: no codes.** |
| Counterweight System (102 / 47), low | 66, 67; Mechanical | 66 and 67, "Did not reach horizontal/vertical position", are inferred, and A10 finds them emitted only by sbsx-49 and sbsx-51, while every Counterweight ticket is on alEx or mlc machines. Keep, map none (literal), or add 56, 57 and 59 to 66 and 67 (mechanism)? **Default: 66, 67, which cannot be tested (T: 0).** |
| Loading Error (86 / 31), low | 77; Stock-out | Keep 77 "Item not stocked"? If kept, Loading Error tickets leave the Stock-out negative control (§4). The skeptic drafter added 03 "Item not available"; the mechanism drafter mapped 30, 31 and 76 under User behavior instead. **Default: 77.** T: 23. |
| Service Door (51 / 22), medium | none; Door issue | Map 30 "Main Door not Closed" (mechanism only: the service-door switch may report through the main-door interlock)? It would partly overlap Main Door {30, 31}. **Default: no codes.** |
| Improper Use (31 / 17), low | 04, 19, 60, 61, 78; User behavior | Keep these five user-behaviour codes, which are common in normal use, or map none (literal)? **Default: keep.** T: 9. |
| Weight Scale (16 / 6), medium | 16; Electronics | Use the Electronics bucket (literal, skeptic) or Mechanical fault (mechanism, and the team's lookup for 16 "Bad Weight")? Code 16 itself is unanimous. With 6 tickets the set cannot enter H2a, so this affects only item 4's bucket match. **Default: Electronics.** |
| Issue (29 / 16), Decoder (12 / 4), medium | none; Electronics | Map 05 "Already Dispensed" to Issue, and 13 to Decoder (mechanism only)? **Default: no codes.** |
| Device Not Found (4 / 2), Troubleshooting (1 / 1), medium | none; Not in telemetry | Keep Not in telemetry, or use Administrative (Device Not Found, skeptic) or No identifiable issue (Troubleshooting, mechanism)? **Default: Not in telemetry.** |

**Unanimous rows worth a glance:**
- **Main Door → 30, 31.** Code 31, "Slot Doors in Improper Position", comes in through the Slot Door sub-category.
  139 of its 239 primary tickets are on emitting types; most of the rest are alEx.
- **Packer → 76.** Its bucket is Mechanical; the team's lookup puts 76 in Operational status.
- **Touchscreen and Badge Reader** map to no code.

**Freezing.** The hash covers the four columns that drive the analysis: `trouble_code, category, target_codes,
target_bucket`. Editing a rationale or a note does not change it.
- **How it is computed.**
  1. Read the file with every field as a string, and empty fields left empty: `csv.DictReader(open(p, newline='',
     encoding='utf-8'))`.
  2. Sort the rows by `category`, in Python's default string order.
  3. Write the four columns, header included, with `csv.writer(buf, lineterminator='\n')`, which uses minimal quoting.
  4. Take the sha256 of the UTF-8 bytes.
- **Test vector.** The v0 draft committed on 22 October gives
  `947b96ce805ba8b8593aa43c728fad97afc382e4386ae06cca36ce5139f05d79`.
- **Frozen hash: pending team sign-off.** `association.py` checks it on every run.
- **v1 and v0.** v1, reviewed by IPA, is frozen before any run that uses it, and becomes the confirmatory version. v0
  results stay in the record as provisional. Rows that change from v0 to v1 are listed.

## 4. Outcome, hypotheses and estimators
**Primary outcome:** a code of the set is present within 7 days (A8, k = 168 h), on the 2,911 pairs determined at
7 d. Undetermined pairs are counted both ways as a sensitivity (S7).
- **When 7 days was chosen.** The independent reviewer proposed it, in the first statistical critique on 22 October,
  before any 7-day result was seen. §10 then records the looks at 7 days by bucket.

**Secondary windows.** k = 0.5 h, 1 h, 2 h, 6 h, 24 h and 30 d. At 30 d the outcome is membership of the last-10 list
(A8), and it runs through the same H2a and H1 steps.

**H2a, primary: does the Category pick out its own codes?** For each target set s:
- **Population.** Primary, mapped tickets on types able to emit s (A10). Unknown type is left out.
- **Groups:**
  - **T (target):** tickets whose Category's target set is s.
  - **K (comparator):** mapped tickets whose target set shares no code with s.
  - Tickets whose set partly overlaps s without equalling it are in neither group for s.
- **Strata.** h is machine type × calendar quarter. With b and c as in A9, the estimator is the Mantel–Haenszel log
  odds ratio over the discordant pairs:

  `H2a(s) = log[ Σ_h b_T,h · c_K,h / n_h  ÷  Σ_h c_T,h · b_K,h / n_h ]`, with n_h = b_T,h + c_T,h + b_K,h + c_K,h.

  This is the log of the ratio of the two matched odds ratios. It is above 0 when tickets for s show s more strongly
  than tickets for other faults do.
- **Entry.** A set enters only if two conditions hold. Otherwise the set does not enter H2a.
  - T has at least 10 discordant pairs over all strata of its population, including strata where K has none.
  - Both the numerator and the denominator are non-zero.

  On v0, Counterweight System (T = 0 on emitting types), Weight Scale (6) and Improper Use (9) cannot enter. The T
  counts on emitting types are checked:
  - Deposit Door 563, User Door 220, SAM 213, Computer Board 208;
  - Main Door 139, Packer 88, Loading Error 23.
- **Pooled H2a.** The same estimator over strata s × type × quarter, for every set that enters. A ticket can be a
  comparator for several sets; the bootstrap and the permutation keep that dependence. If no set enters, H2a is not
  estimable and does not succeed.
- **Interval.** Account-cluster bootstrap.
  - **Cluster order.** The clusters are the sorted A11 labels of the pairs analysed at that k:
    - 610 for the 2,911 pairs used at every k ≤ 7 d;
    - 613 for the 2,950 pairs used at 30 d.
  - **Weights.** `W = boot_weights(len(clusters), 2000, 15072)` (`fleet_exposure.py` L288), and column j weights
    `clusters[j]`.
  - **One W per population and cluster type.** It serves every estimate on that population: each set's H2a, the pooled
    H2a, H1 and per-set enrichment. A cluster with no tickets in an estimate's subpopulation contributes zero.
  - **Fixed entering sets.** The entering sets are fixed at their observed values. Each replicate recomputes every
    stratified sum over those sets, without re-applying the entry rule.
  - The 95% percentile interval follows A13.
- **Null.** Category is permuted among the mapped tickets of the analysed pairs within each type × quarter stratum,
  2,000 times. That is 1,706 tickets at 7 d and 1,736 at 30 d.
  - **Generator.** One generator, `np.random.default_rng(15072)`, is created once.
  - **Order.** Strata are taken sorted by type, then quarter. Within each stratum the tickets are sorted by `case_id`,
    and their Categories are reordered with `rng.permutation`.
  - **What is recomputed.** Each permutation recomputes the whole pooled statistic from the permuted labels, entry rule
    included. A permutation in which no set enters counts as below the observed value.
  - **p-value.** One-sided: p = (1 + the number of permutations whose pooled statistic is at least the observed value)
    / 2,001. Its Monte Carlo standard error is √(p(1 − p)/2,000).
- **Decision.** H2a succeeds if the pooled estimate is above 0 and the one-sided permutation p is at most 0.05. The
  bootstrap interval is reported alongside.

**H2b, secondary (outside the gated sequence): fault tickets against tickets the telemetry cannot see.** For each set s
that entered H2a:
- **T** is as in H2a.
- **K** is the primary tickets on types able to emit s whose `target_bucket` is Not in telemetry. There are 281 such
  tickets in the primary population before the type restriction. Administrative tickets join K only in S1.
- The estimator, strata, pooling and bootstrap are as in H2a. The permutation is among T ∪ K, within type × quarter.
- H2b is reported with its permutation p as a descriptive secondary, and no claim rests on it.

**No Trouble Found** is in neither H2a nor H2b, and is reported descriptively. It may mean no fault, or a fault the
technician could not reproduce; which one is asked of IPA (§13).

**Gated sequence.** Each step's test is run only if the previous one succeeds. Every step's estimates and intervals are
reported either way, marked "not tested" when the gate stops before them. The item 2 tests are not gated.
1. **H2a.**
2. **H1.**
   - **Population:** every mapped primary ticket whose type can emit its own target set (A10), Unknown left out, whether
     or not its set entered H2a. On v0 that is 1,439 tickets at 7 d and 1,469 at 30 d.
   - **Estimator:** Σb / Σc, with an account-cluster bootstrap interval.
   - **Test:** Durkalski on account clusters (§5).
   - **Decision:** H1 succeeds if Σb > Σc and the two-sided Durkalski p is at most 0.05.
3. **Per-set enrichment.**
   - **Population:** the H1 tickets whose target set is s.
   - **Which sets are tested:** a set is tested only if it meets A12 in that population.
   - **Per tested set:** b/c, risk difference and lift, with account-cluster bootstrap intervals, and the two-sided
     Durkalski p.
   - **Multiple testing:** Benjamini–Hochberg across the tested sets. A set is enriched if b > c and q ≤ 0.05.

**Negative controls.**
- **Stock-out as an outcome** (codes 03, 77), among tickets whose target set contains neither code. That is every
  ticket except Loading Error, which v0 maps to 77.
  - Enrichment here estimates the generic "a machine is in trouble" effect.
  - Restocking visits can also produce these codes.
  - TODOS noted that no Category corresponds to Stock-out. The v0 drafters disagree for Loading Error (§3).
- **Deposit Door without codes 19 and 78** (S13). These are the user-behaviour codes "Deposit Door not Opened" and
  "Receiver Deposit Door not completely opened". This variant shows how much of a Deposit Door result rests on them.

## 5. Secondary analyses (TODOS items 2, 3, 4 and 6)
**Item 2. Enrichment by bucket and by frequent code.**
- **What is reported.** For each bucket and each **frequent code**, at 7 d and 30 d, a bucket being present when any
  code with that team bucket is present:
  - the share of ticket windows and of control windows where it is present;
  - risk difference, lift (pT/pC) and matched odds ratio b/c;
  - a machine-cluster bootstrap interval, with machines sorted by `machine_id`;
  - a clustered McNemar test (Durkalski) on machine clusters.
- **Frequent code.** A code present in at least 1% of the 5,900 primary windows (ticket and control together) at
  30 d, counted marginally. On the committed data that is 35 codes, and the list is checked (§8).
- **The test.** χ² = (Σ_k (b_k − c_k))² / Σ_k (b_k − c_k)², summed over clusters k, with p = erfc(√(χ²/2)), two-sided.
  - If every cluster has b_k = c_k, then χ² = 0 and p = 1.
  - Plain McNemar is not used because it ignores clustering.
- **Multiple testing.** Benjamini–Hochberg, q ≤ 0.05, within each of four families: buckets at 7 d, buckets at 30 d,
  frequent codes at 7 d and frequent codes at 30 d.
  - **The bucket family** is the eight non-success buckets other than Malformed: Stock-out, Door issue, Incomplete
    transaction, User behavior, Operational status, Mechanical fault, Electronics/software/comms and Undefined.
  - **Reported but not tested:** Malformed and "any code".
  - **Only the overall rows are in the families.** The breakdown rows show unadjusted p-values and are descriptive.
- **Breakdowns:**
  - overall;
  - by Category;
  - by Trouble Code, pooling the pairs of every ticket whose Category belongs to it, so each Trouble Code row is the
    sum of its Category rows;
  - descriptively, for the 157 tickets left out at A3 step 1.

**Item 3. Recency.**
- **Cumulative presence.** Presence within k for k = 0.5, 1, 2, 6, 24, 168 and 720 h, ticket against control.
  - Bucket curves use the primary population. Target-set curves use the H1 population.
  - Every k up to 7 d uses the same pairs, those determined at 7 d, so the curve is cumulative over one fixed set of
    pairs. 30 d uses list membership (A8).
  - This answers how far back a linker should look.
- **Exclusive bins (TODOS).**
  - Each outcome goes in the bin of its smallest listed hours: [0, 2) h, [2, 6) h, [6, 24) h, [24, 168) h,
    [168, 720] h.
  - An outcome that is not listed is *absent* when `distinct_codes` ≤ 10, and goes in its own column, "not listed,
    list full", otherwise.
  - This table is descriptive.
- **Guard windows.**
  - In the guard windows, the hours are measured from A. So guard g at k covers [A − k, A − g), and it is compared
    with `corrected_guard0` at the same k.
  - A8 is applied to the guard window's own list. No k ≤ g is computed.
  - Reported on the ticket side at k = 6 h, 24 h and 7 d, with S3's control-side bounds.

**Item 4. How much of the target signal the ticket explains.**
- **Excess presence fraction.**
  - **Definition:** (pT − pC)/pT for the ticket's own target set, at each k, on the H1 population.
  - **What it bounds:** if the control is valid, it is a **lower bound** on the share of target-present tickets whose
    target code comes from the ticket's fault (the Tian–Pearl lower bound on the probability of necessity).
  - **Caveat:** A3 gives two ways the control may not be valid, one pushing the fraction down and one pushing it up.
    So it is reported with its interval, not as a guaranteed bound.
  - **Upper bound:** min(1, (1 − pC)/pT), reported alongside. It is below 1 only when pT + pC > 1.
- **Tightest lower bound.** The maximum over k ≤ 7 d of (pT(k) − pC(k))/pT(7 d), with its k and an interval. Taking
  the maximum over k biases it slightly upward.
- **Pairs where both windows have the target.** Descriptive shares of those pairs where:
  - the ticket window's most recent target code is more recent than the control's;
  - the ticket window's target count is higher.
- **Match rates.** Precision and recall at 7 d and 30 d, for two kinds of match. Both are computed on ticket windows,
  then recomputed with control-window presence in place of ticket-window presence as the chance baseline.
  - **Target code present** (per set s). Population: primary tickets with a Category, on types able to emit s, with
    Unknown left out.
    - Recall: the share of tickets whose Category targets s that have s present.
    - Precision: among tickets with s present, the share whose Category targets s.
  - **Matching bucket present** (per team bucket B, as TODOS asks). Population: primary tickets with a Category.
    - Recall: the share of tickets whose `target_bucket` is B that have a code of team bucket B present.
    - Precision: among tickets with a B code present, the share whose `target_bucket` is B.
    - This covers Categories with no target codes but a team bucket.
  - **Overall:** the micro-average, which sums true positives and denominators over the sets, or over the buckets.
  - **By Category:** recall only. Precision belongs to a set or a bucket, not to a Category.
  - Both kinds are **descriptive**: Category is a label set at closure, not a gold standard.

**Item 6. Machine type and model.**
- H1 and per-set enrichment by machine type, on emitting types and on all types.
- Model within type, descriptive. On every matched ticket, the model on the ticket equals the model on the installed
  list (docs/06).

## 6. Sensitivities (TODOS item 5)
Each is reported for H2a, H1 and the item 2 bucket table at 7 d and 30 d, in one table. Each sensitivity population
draws its own bootstrap weights over its own sorted clusters.

| # | Variant | Population | Purpose |
|---|---|---|---|
| S1 | Planned, cancelled and duplicate tickets put back | +99 pairs: 90 Cancelled request, 5 Planned work, 4 Duplicate case | TODOS "with and without". 96 are Administrative in the crosswalk (Cancelled Request, Duplicate Case, Paid PM) and join H2b's comparator and the item 2 tables. The other 3 (1 SAM, 2 with no Category) follow their Category. A separate Cancelled request row tests "faults that cleared on their own". |
| S2 | Text flags, each separately and all together | needs `verification/outputs/flags/flags_by_case.csv` | monitoring_template, telemetry_mention (template, clearView or clariFy), code_ref and wrong_machine_note, each by field (Trouble Reported, Resolution, Administrative Notes), plus their union. The share flagged is reported by month and by Category. |
| S3 | Guard bands, 30 and 60 min | ticket side from the committed guard windows | Covers codes produced by the ticketing process itself, and residual clock error. Control side: codes with hours < g are dropped, giving three outcomes. **Present:** a code of s has g ≤ hours < k. **Unknown:** not present, but a dropped code of s has occurrences > 1, or the window is undetermined. **Absent:** otherwise. The lower bound counts unknown as absent and the upper bound counts it as present. |
| S4 | Matched ticket-free lead-in | 2,330 tickets: no ticket in [A − 102 d, A − 67 d), and A ≥ 11 Nov 2025, so that the span lies within the case history (1 Aug 2025 + 102 d) | Removes the first asymmetry in A3. |
| S5 | Recently activated machines | drops 177 tickets on 175 machines | **Rule:** drop a ticket when its machine's first_active is after 1 August 2025 and the control window starts less than 90 days after first_active: A − 65 d < first_active + 90 d, i.e. A < first_active + 155 d. first_active is read as 00:00 that day. **Kept:** a first_active of 1 August 2025 is left-censored (active when telemetry began) and is never dropped. **Secondary check:** drop machines installed at their current account in 2025 or later, using install year from the installed-base list (521 tickets). The 132 tickets with no year are kept. |
| S6 | Lookback-truncated windows included | adds pairs with a truncated window | TODOS item 5. |
| S7 | Undetermined pairs at 7 d counted both ways | 39 pairs (29 ticket, 17 control windows) | A8. |
| S8 | Machine instead of account clusters | none | A11. |
| S9 | Usable unplanned tickets, ticket side only | 5,031 tickets: the 5,312 with both A1 and the A3 step-2 span rule applied, which leaves out 281 tickets with empty windows | Shows whether the paired subset is typical. A per-ticket D5 episode flag is applied (a gap over 7 d starts a new episode; the first ticket is kept). |
| S10 | Interval-based clean rule | needs close times from `flags_by_case.csv` | Pre-declared now: a pair is unclean when either window overlaps any other ticket's [opened, closed + 2 d]. |
| S11 | Time trend | none | The slope of target presence on calendar date across control windows, × 35 d, gives the bias it would add to the paired difference. |
| S12 | Crosswalk v1 | when it exists | Replaces v0 as the confirmatory version. |
| S13 | Deposit Door without codes 19 and 78 | none | Negative-control variant (§4). |

**The local flag export (to be written).** A `--write` mode will be added to `verification/flags.py`, and you run it
locally on the raw workbook. It writes `flags_by_case.csv`. S2 and S10 cannot run until that file exists.
- **Rules it carries.** It copies two rules into `flags.py` rather than importing them, because
  `timestamp_semantics.py` runs its whole pipeline on import:
  - `CODE_REF_RE`, from `timestamp_semantics.py` L184–188;
  - the wrong-machine rule `ERROR_NOTE`, from `customer_fleet_audit.py` L64–66.
- **Columns:**
  - `case_id`;
  - per-field booleans for the monitoring template, telemetry mention and quoted-code rules;
  - a wrong-machine-note boolean;
  - `closed_at_eastern`.

  It holds no text and is committed like the other per-ticket files.
- **Count checks.** Against the committed reference values: code_ref 350, templates 138, wrong machine at least 39.
- **Expected direction.** Dropping flagged tickets lowers presence in the ticket window for the sets most often quoted.
  That biases H1 and H2a toward no effect, by different amounts for different sets and quarters.

## 7. Classifier evaluation design (item 7; design only)
**Use case.** The retrospective linker IPA chose (docs/04 §5). Its inputs are the ✔ fields in the docs/04
"Retrospective linker" column.

**Reference labels.**
- **What labellers see:** the ticket text and the machine's codes, but **not** Trouble Code, Category or Sub Category.
  Those can be classifier inputs, so they cannot also be the reference.
- **Sample:** closed, unplanned, customer-reported tickets, stratified on the target sets. It replaces Zac's pilot
  template.

**Splits.**
- **By time:** the test period ends at least two weeks before the end of the case history, 31 August 2026 (docs/04
  §5.2; the export itself is dated 1 September 2026), and results are reported by period. The ticket template drifted from December 2025.
- **By machine:** no machine is in both the labelled development sample and the test set.

**Text handling.**
- `Device FW` is parsed into a field.
- Results are reported with quoted codes and system names both masked and unmasked.
- **Prerequisite:** a phone and e-mail redaction rule, with documented edge cases, must exist before any text goes to a
  language model. The "~300 tickets" in docs/04 has no committed script yet.

## 8. Checks and verification (item 8)
**Checks in `association.py`.** A failed check makes the script exit with an error.
- **It reproduces the first look exactly:**
  - 3,259 pairs;
  - Electronics 20.3% vs 13.1%; Door 67.9 vs 61.1; Mechanical 54.6 vs 52.2; Stock-out 46.3 vs 45.3; any code 90.2
    vs 89.0;
  - Electro/Mechanical tickets, Door: 1,781 tickets, 78.2 vs 67.8.
- **It pins every count stated in §2–§6** and writes each to `as_summary.json`:
  - A2: 3,259 / 2,504.
  - A3: 157; 102 on 85 machines; 50 on 47; 2,950 / 2,376; 42 and 31; 292 / 56 / 341 / 17; 39 and 12.
  - A5: 23 + Unknown 14. A6: 731 / 870 / 812 / 537. A7: 1,736.
  - A8: 29 / 17 / 39 / 2,911; 610 clusters, 2,350 machines, 1,706 mapped; 137 / 94.
  - A10: 3,388 windows, and the emitting types per set.
  - A11: 613 (2,902 / 48).
  - §3: 26 / 9 / 6; 10 sets; 3,298; the eleven codes in no set.
  - §4: the T counts; H1 1,439 (7 d) and 1,469 (30 d); K 281.
  - §5: the 35 frequent codes.
  - §6: S1 +99; S4 2,330; S5 177, 521 and 132; S9 5,031.
- **Window checks.** Control hours are at most 720. The guard windows hold no code under 0.5 h or 1 h.
- **Crosswalk checks.** The hash matches, all 41 Categories are covered, and every listed code exists.
- **Bootstrap check.** A replicate with all weights equal to 1 reproduces the point estimate.
- **Clean-room check.** The agreed clean-room numbers match.
- **Privacy check.** The privacy scan is clean.

**Clean-room build.** Independent agents rebuild, from this document and the files in §1 alone, without reading
`association.py`:
- the pairs;
- the item 2 table: buckets, frequent codes, and the Trouble Code and Category strata;
- H2a and H1;
- the item 3 curve.

How the two builds must agree:
- **Exactly:** counts, shares, point estimates and Durkalski p-values.
- **Within Monte Carlo noise:** bootstrap interval endpoints, within 10% of the interval's width. Permutation
  p-values, within 3·√(2p(1 − p)/2,000), which is 0.021 at p = 0.05.

Differences are settled in favour of the most literal reading of this protocol. The agreed numbers become checks.

**Skeptic review.** Four lenses: statistics; recency and item 4; strata and sensitivities; wording and privacy. It runs
before `docs/08_association_results.md` is committed, as it did for docs/05 and docs/06.

## 9. Deviations from TODOS items 1–9
TODOS is ticked from this table.

| TODOS | Here | Why |
|---|---|---|
| 1. Crosswalk to buckets | Code-level target sets plus a bucket. Drafted blind by three drafters; reviewed by the team, then by IPA (v1 is confirmatory). | Buckets cut across components |
| 2. Paired shares, RD, lift, McNemar, machine-clustered bootstrap, by Trouble Code and Category | As asked, at 7 d and 30 d. McNemar is clustered (Durkalski). Trouble Code rows pool their Categories. | Tickets on one machine are not independent |
| 2. "Done when … second independent implementation" | Clean-room build (§8) | as asked |
| 3. Recency bins and guard bands | Cumulative presence within k decides. The exclusive bins are descriptive. Guard bands are a sensitivity for the headline results. | Cumulative presence is what a linker uses |
| 4. Match rate, precision and recall | The excess presence fraction leads: a lower bound if the control is valid. Precision and recall are descriptive, for target codes and for the matching bucket. | Category is not a gold standard |
| 5. Monitoring, telemetry-mention and wrong-machine tickets | Sensitivities (S2), not primary exclusions | Excluding them selects on the outcome |
| 5. Repeat tickets | The primary population is one ticket per episode by construction; the D5 flag is applied in S9 | A3 |
| 5. Planned, cancelled, duplicate; truncated windows | S1, S6 | as asked |
| 6. Machine type; model (fleet follow-ups) | Emitting types (A10); model within type, descriptive | Code support differs by family |
| 7. Classifier evaluation | Design only (§7) | Lower priority (IPA, 13 Oct) |
| 8. Adversarial verification | Clean room plus skeptic review this round | as asked |
| (new) Primary hypothesis | H2a specificity; H1 enrichment follows it | H1 is close to guaranteed positive |
| (new) Primary outcome | 7 days; the TODOS 30-day last-10 list is secondary | 30 days is near ceiling (Door is in 61% of controls) and more exposed to drift |
| (new) Primary population | Drops 152 tickets outside their machine's telemetry span | Their "complete" windows are empty |

## 10. Looks at the data so far
Recorded so readers can judge what this protocol could have been tuned to. Bases are given with each number.
1. **The TODOS first look** (3,259 paired set): 30-day bucket shares, ticket against control. It included
   Electro/Mechanical tickets × Door and the Network observation.
2. **docs/05 part E:** non-success rates and Door shares for chronic and other machines.
3. **Planning, 22 October:**
   - code frequencies over all tickets;
   - Category counts;
   - the balance of total transactions between the windows (median ratio 1.00);
   - Electronics presence in control windows by month, falling from 16% to 11% over the year.
4. **After the reviewer proposed 7 days:**
   - **Bucket shares at 7 d and 24 h:** Electronics 12.9% vs 5.2% at 7 d, on the 3,259 paired set, with undetermined
     windows counted as absent.
   - **The reviewers' bucket-level figures:** matched odds ratios at 7 d and 30 d; the final-hour shares (23.9% of
     ticket windows against 8.8% of controls have a code in the final 30 minutes, on 3,102 tickets); and bucket shares
     under different undetermined rules (finding notes, 22 October).
   - **A power check by one first-panel reviewer, before v0 existed.** For a hypothetical crosswalk, it counted pairs,
     discordant pairs and control-window prevalence per Category set. What reached the protocol author:
     - Deposit Door: 568 pairs, 60 of them discordant; control prevalence 66.5% (code 19 alone, 54.7%);
     - control prevalence: SAM 9%, User Door 3%.
   - **What those power numbers do and do not reveal.** They give no direction, but they limit the size of the
     contrast. Since b + c = 60, Deposit Door's ticket-window prevalence lies within 60/568 = 10.6 points of its 66.5%
     control prevalence.
   - **Who saw them.** The crosswalk drafters never saw these numbers. The protocol author saw them before writing the
     review questions in §3. The 19/78 question and S13 follow the skeptic drafter's blind choice and the code list's
     User behavior label, but the author had seen code 19's control prevalence when writing them.
5. **The second review panel, on this document:**
   - population counts;
   - the T counts on emitting types (A10, from control windows by type, with no outcome by Category);
   - bucket-level shares under the undetermined rules.

**No ticket-window share by Category, and no ticket-against-control contrast by Category, has been viewed.** That holds
for the protocol author, the drafters and the reviewers; the team reviewers confirm it at sign-off. The only
Category-level outcome quantities seen are the look-4 power counts above.

## 11. Limits
- **One control, always earlier.** Anything that changes over time on a machine (wear, firmware, use) differs between
  the windows by 35 days.
  - S11 measures generic drift.
  - H2a removes drift only where it changes the odds of s equally before target and comparator tickets. A drift in one
    set's codes, such as a firmware build that starts logging SAM codes, is not removed.
  - A case-time-control design needs the database (§12).
- **Who the result describes.** Tickets that follow about two quiet months on the machine. Chronic machines are
  under-represented: clean controls exist for 21% of their tickets, against 72% of other tickets (docs/05 part E).
- **The provisional buckets and codes are not IPA's definitions.** "IPA to confirm" applies to every bucket and to the
  meaning of every code.
- **Category as recorded.** Category is set near closure. If technicians read clearView when they set it, part of the
  association is built in (IPA question, §13). S2 bounds this from the text, not from the process.
- **Small sets.** Several target sets have under 100 tickets on emitting types (§4). A null H2a may reflect power,
  not absence.

## 12. Deferred (needs the database; added to TODOS)
- **Re-extract windows without the last-10 cap,** giving every code's count and most recent time. This removes the
  undetermined cases at every k, and gives true presence within 30 d, of which the TODOS list outcome is a lower bound.
- **Four referent weeks per ticket** (days −63 to −35), with a Mantel–Haenszel OR. This adds power and a built-in trend
  check.
- **A case-time-control analysis** on pseudo-anchors in ticket-free stretches.
- **A code × machine type table over the full year,** which replaces the A10 rule.

## 13. Questions for IPA (item 9 additions)
- Review of crosswalk v0, and IPA's code definitions for v1. This includes whether 13 "Invalid Driver Board Response"
  refers to the computer board, and which family logs 66/67.
- Which codes each machine family or firmware version can emit.
- Whether technicians look at clearView when they set Category and Sub Category. If they do, part of the association is
  built in.
- What "No Trouble Found" means in practice: no fault, or a fault that could not be reproduced?

## Privacy
- **Inputs.** Committed pseudonymous outputs only:
  - T#####, M#####, S##### (S5 only), Customer NNN, Host NNN and Location NNNN;
  - US state and zone in `fu_devices.csv`.
- **Outputs.** T and M ids; Customer NNN only as an aggregate cluster label; Category, code and type labels. No host,
  location, state or zone.
- **Privacy scan.** `association.py` checks every text column and every summary string against the pseudonym formats.
  When the raw workbook is present locally, it also runs `text_leaks` against real serials, account names and case
  numbers.
- **The flag export.** `verification/outputs/flags/flags_by_case.csv` holds booleans and a close time per T id, and no
  text. It is committed like the other per-ticket outputs.
- **Raw text** is read only on the local machine, by `flags.py`, and never written.
