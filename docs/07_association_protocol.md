# Association study protocol: ticket fields and the telemetry codes before each ticket

*22 October 2026. Status: **pre-specified protocol, draft for team review.** No result at the level of a Category has
been computed. The analysis script (`verification/association.py`, to follow) reads only committed outputs and runs
without the database. This document fixes what will be computed, on which tickets and how, before any results by
Category are seen. Later changes are dated amendments (`*[Amended <date>: …]*`). The original text is kept.*

**Why a protocol first.** TODOS.md item 1 asks for a crosswalk from ticket Categories to telemetry codes, agreed with
the team and then with IPA. Items 2–6 test it. If the crosswalk or the tests were chosen after looking at which
Categories line up with which codes, the results would confirm whatever was looked at. So we freeze:
- the crosswalk, `verification/reference/crosswalk_v0.csv`;
- the population, outcome, hypotheses, estimators and decision rule;

before running anything by Category. §10 lists every look at the data so far.

**How this was designed.**
- We drafted the design.
- An independent statistical reviewer critiqued it.
- A second review panel tried to refute each finding: three lenses (data feasibility, statistics, alignment with
  TODOS and repo conventions), with a skeptic per major finding.
- 21 findings survived and are applied here.
- Three independent drafters, working from code descriptions only, produced the crosswalk; the majority vote is v0
  (§3).

## Bottom line
1. **Primary question (H2a, specificity).** When a ticket's Category points at a set of telemetry codes, does that set
   show up in the machine's final 7 days before the ticket more often than it does before tickets for *other*
   faults? This is a comparison against the same machines' quiet periods 35 days earlier.
   - Comparing against tickets for other faults cancels the generic effect that any failing machine logs more codes.
     It also cancels slow drifts over time.
2. **Secondary questions,** tested in order only if H2a succeeds:
   - **H1:** does the target set appear more often before tickets than in the paired control?
   - Then each target set separately.
   - TODOS items 2–6 (enrichment, recency, match rates, machine types, sensitivities) are reported around them.
3. **Population:** 3,102 unplanned tickets on 2,500 machines. Each has a complete 30-day window before the ticket and
   a clean, complete control window on the same machine 35 days earlier. Neither window contains another ticket.
4. **Outcome:** a target code appears in the final 7 days of the window. The TODOS 30-day "last 10 codes" outcome is a
   pre-specified secondary.
5. **Crosswalk v0 is a team-review draft.** Results using it are provisional. The confirmatory version (v1) is frozen
   when IPA's code definitions arrive, before any run that uses it.

## 1. Data
**Source.** Everything comes from committed, pseudonymous outputs. No raw file or database is needed.
- **`verification/outputs/fu/fu_ticket_last10.csv`** (`db_followup.py`, parts F1 and F2): 6,113 device-matched
  tickets × 4 windows. For each window it gives:
  - all events;
  - non-success events (any code other than `00`);
  - the number of distinct non-success codes;
  - the **last 10 distinct non-success codes**, ordered by most recent occurrence. Each comes with the hours from that
    occurrence to the window's end and its count over the whole window.
- **`verification/outputs/fu/fu_devices.csv`:** machine type, assigned customer, first active day and whether the
  machine transacts, by M id.
- **`verification/outputs/db/db_codes_buckets.csv`:** the 49 codes seen in the telemetry, their descriptions and the
  team's provisional bucket (`verify_with_db.LOOKUP`; not validated by IPA).
- **`verification/reference/crosswalk_v0.csv`:** this protocol's crosswalk (§3).

**Windows** (`db_followup.py` L57–62, L292–416). A is the ticket's creation time, converted from US Eastern to UTC.
| Window | Span | Role |
|---|---|---|
| `corrected_guard0` | [A − 30 d, A) | ticket window (primary) |
| `corrected_guard30`, `corrected_guard60` | [A − 30 d, A − 30 min) and [A − 30 d, A − 60 min) | guard-band sensitivities; hours still measured from A |
| `control_minus35d` | [A − 65 d, A − 35 d) | paired control; hours measured from its own end, A − 35 d |

`control_clean` is true when no other ticket on the machine, of any kind, opened in [A − 67 d, A − 5 d).

## 2. Definitions
- **A1. Unplanned.** `service_group` is not Planned work, Cancelled request or Duplicate case (Zac's `service_cases`
  view; `common.CASE_VIEWS`). This keeps No Trouble Found and Missing trouble code.
- **A2. Paired set.** Unplanned tickets meeting three conditions:
  - both windows have `lookback_truncated` = `after_telemetry_end` = False;
  - `control_clean` is true;
  - this gives **3,259 tickets on 2,504 machines**, which reproduces the TODOS first look exactly.
- **A3. Primary population.** The paired set minus the **157** tickets with another ticket on the machine opened in
  [A − 5 d, A). That leaves **3,102 tickets on 2,500 machines.**
  - **No ticket in either window.** Neither window, nor the 2 days before it, contains another ticket opened on the
    machine.
  - **One ticket per episode.** Any two primary tickets on one machine are at least 67 days apart. Every primary
    ticket is therefore the first of its own 7-day episode (definition D5 in docs/05).
  - **The asymmetry that remains, stated exactly:**
    - The ticket window has at least 37 ticket-free days before it. The control window can start as little as 2 days
      after an earlier ticket: 305 primary tickets have one in [A − 102 d, A − 67 d), 57 of them within 9 days of
      the control's start. That earlier visit's after-effects inflate the control, which biases results **toward no
      effect**.
    - Controls are also conditioned on no ticket in [A − 35 d, A − 5 d). If code bursts tend to lead to tickets, that
      depletes code-heavy controls, which biases H1 and item 2 **away from** no effect. It largely cancels in H2a.
  - **Categories.** Analyses by Category also drop the 45 primary tickets with no Category.
- **A4. Text flags are not a primary exclusion.** A ticket that quotes a code or mentions clearView often does so
  *because* the codes were there. Excluding such tickets selects on the outcome. The flags enter as sensitivities
  (§6).
- **A5. Machine type.** From `fu_devices.csv`, normalised:
  - lower case;
  - a leading `package name:` stripped;
  - blank becomes `Unknown`.

  The primary population has 25 types, and 27 tickets are Unknown. Unknown is left out of analyses restricted by
  machine type, and counted.
- **A6. Calendar quarter.** The quarter of the ticket's creation date, US Eastern. The primary population covers
  2025-Q4 to 2026-Q3 (756, 903, 853 and 590 tickets). It starts on 5 October 2025, because the control window needs
  telemetry from 1 August 2025.
- **A7. Target set.** A Category's `target_codes` in the crosswalk.
  - A ticket is **mapped** when its Category has a non-empty target set.
  - Two Categories with an identical target set form one set s.
- **A8. Code present within k.** A code in a window's last-10 list whose most recent occurrence is less than k hours
  before the window's end.
  - **Why this is exact.** The list is ordered by most recent occurrence. So a code absent from the list cannot have
    occurred within k unless all 10 slots are filled by codes more recent than k.
  - **Undetermined windows.** Those cases are counted as *undetermined*. In the primary population at k = 7 d there are
    30 ticket and 19 control windows; at 24 h, 1 and 0; at 30 d, 231 and 158.
- **A9. Discordant pairs.**
  - For a set s and a ticket, **b** means s is present in the ticket window but not the control, and **c** the
    reverse.
  - The matched odds ratio is b/c. This is the case-crossover estimand.
  - Concordant pairs carry no information about it.
- **A10. Able to emit.** Machine type τ can emit set s, for a machine m of that type, when s appears anywhere in the
  last-10 list of the control window of **at least 5 other machines** of type τ.
  - The windows counted are all 6,113 tickets' control windows that are not lookback-truncated.
  - Machine m itself is left out.
  - No ticket-window outcome enters this rule.
  - A check pins the list of emitting types for each set.
- **A11. Clusters.**
  - **Account clusters,** for H2a, H2b, H1 and the per-set tests. The cluster is the machine's
    `assigned_customer`, else its `ticket_customer`, else the machine itself. That gives 640 clusters in the primary
    population: 3,045 tickets by assigned customer and 57 by ticket customer. Account clusters are used because
    Category is assigned by service staff working per account.
  - **Machine clusters,** for the item 2 tables, as TODOS asks. For H2a they are a sensitivity.
- **A12. Reporting threshold.** A stratum is reported only with at least 30 pairs and at least 10 discordant pairs.
  Otherwise it is "not estimable".

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
- Bucket-level analyses use `target_bucket`. The specificity tests use `target_codes`. Code sets are sharper because
  the provisional buckets cut across components: the deposit-door codes fall in Door issue, User behavior and
  Mechanical fault.

**How v0 was made.**
- **Drafters.** Three independent drafters worked from the code descriptions, the Category and Sub Category names, and
  the machine families each Category occurs on:
  - a *literal* drafter: a code only if its description names the component;
  - a *mechanism* drafter: codes a fault of the component would directly cause;
  - a *coverage-skeptical* drafter: codes only when a fault surely shows in a transaction outcome.
- **Blind drafting.** None of them saw any data that relates tickets to codes.
- **Voting.** A code enters a Category's target set when a majority of drafters chose it. The bucket is the majority
  bucket.
- **The `drafters` and `review_note` columns** record each drafter's choice and where they disagreed.
- **Confidence** measures agreement:
  - *high* when all three drafters chose the same codes and bucket (26 rows);
  - *medium* when two drafters' choices equal the final row (9);
  - *low* when only one drafter's codes equal it (6).
- **Coverage.** 10 Categories have a non-empty target set. Together they cover 3,298 of the 6,113 matched tickets.
- **Overlap.** Two sets overlap: Improper Use {04, 19, 60, 61, 78} and Deposit Door {19, 20, 78, 79, 80} share 19 and
  78. Under H2a each leaves the other's comparison (§4).
- **Not in any set.** Five codes appear in no target set:
  - 05 "Already Dispensed";
  - 15 "Blocked Door";
  - 26 "Open Door Dispense";
  - 81 "Opening Door Blocked";
  - 28 "Undefined".
- **The largest Electronics Categories have empty sets.** Touchscreen (472 tickets) and Badge Reader (91) have no code
  that describes them, so electronics enrichment can only be tied to a Category through Computer Board (13, 25) and
  Weight Scale (16).

**Review and freezing.**
- **The team reviews v0 first,** the "team" step of item 1. The rows flagged for review are listed at the end of
  this section.
- **Then it is frozen.** The hash covers the four columns that drive the analysis: `trouble_code, category,
  target_codes, target_bucket`.
  - **How it is computed.** Write those four columns, header included, as CSV with Python's `csv` module (minimal
    quoting, `\n` line endings), with rows sorted by `category`. Take the sha256 of the UTF-8 bytes.
  - **Where it is used.** The value is recorded here, and `association.py` checks it on every run.
  - **What it ignores.** Editing a rationale or a note does not break the freeze.
- **Frozen hash: pending team sign-off.**
- **v1** is the IPA-reviewed crosswalk. It is frozen before any run that uses it and becomes the confirmatory
  version. v0 results stay in the record as provisional. Rows that change from v0 to v1 are listed.

**Rows flagged for review.** These are the rows where the drafters disagreed, by how much they matter. The CSV's
`review_note` gives each disagreement in full.

| Category (matched tickets) | v0 | Question for the reviewer |
|---|---|---|
| Deposit Door (994), low | 19, 20, 78, 79, 80 | Keep 19 "Deposit Door not Opened" and 78 "Receiver Deposit Door not completely opened"? The team's lookup calls them user behaviour, and the skeptic left them out. Add 81 "Opening Door Blocked" (mechanism only)? |
| Computer Board (529), low | 13, 25 | Keep 25 "No Communications with Dispenser", which does not name the board? Add 05 "Already Dispensed" (mechanism only)? |
| SAM (491), medium | 14, 17, 18, 32–35 | Keep 14 "Broken Limit Switches", which does not name the SAM? |
| Curtain (477), medium | none | The mechanism drafter mapped 15 "Blocked Door" and 56/57 "Top/Bottom Door not Closed" under Door issue. |
| User Door (399), low | 02, 11, 27, 41–48 | Keep the generic lock codes 02 "Door did not unlock", 11 "Door Did not Open" and 27 "Door did not lock"? The literal drafter kept only 41–48; the mechanism drafter also added 14, 15 and 26. |
| Power Supply (170), medium | none | The mechanism drafter mapped 13 and 25 for low voltage. |
| Counterweight System (102), low | 66, 67 | The link to "Did not reach horizontal/vertical position" is inferred. The literal drafter mapped none; the mechanism drafter added 56, 57 and 59. |
| Loading Error (86), low | 77 | "Item not stocked" puts an operator-error Category on a stock-out code, so Stock-out is no longer a clean negative control (§4). The mechanism drafter mapped 30, 31 and 76 instead. |
| Service Door (51), medium | none | The mechanism drafter mapped 30 "Main Door not Closed". |
| Improper Use (31), low | 04, 19, 60, 61, 78 | These user-behaviour codes are common in normal use. They overlap Deposit Door on 19 and 78. |
| Weight Scale (16), medium | 16 | The bucket is Electronics; the team's lookup puts 16 "Bad Weight" in Mechanical. |
| Issue (29), Decoder (12), medium | none | The mechanism drafter mapped 05 and 13 respectively. |
| Device Not Found (4), Troubleshooting (1), medium | none | Bucket only: Not in telemetry, Administrative or No identifiable issue. |

**Unanimous rows worth a glance:**
- **Main Door** maps to 30 and 31. Code 31, "Slot Doors in Improper Position", comes in through the Slot Door
  sub-category.
- **Packer** maps to 76. Its bucket is Mechanical, while the team's lookup puts 76 in Operational status.
- **Touchscreen and Badge Reader** map to no code.

## 4. Outcome, hypotheses and estimators
**Primary outcome:** a target code is present within 7 days (A8, k = 168 h).
- **Undetermined windows** are left out of the primary analysis. As sensitivities they are counted both ways: as
  present, and as absent.
- **When 7 days was chosen.** The independent reviewer proposed 7 days before any 7-day result was seen. That was the
  first statistical critique, on 22 October. §10 then records the looks at 7 days by bucket.
- **Secondary windows:** k = 0.5 h, 1 h, 2 h, 6 h, 24 h and 30 d. At 30 d, "in the last-10 list" is the TODOS
  outcome, and it runs through the same H2a and H1 steps.

**H2a, primary: does the Category pick out its own codes?** For each target set s:
- **Population.** Restrict to primary, mapped tickets on types able to emit s (A10). Unknown type is left out.
- **Two groups:**
  - **T (target):** tickets whose Category's target set is s;
  - **K (comparator):** mapped tickets whose target set shares no code with s.
- **Tickets in neither group.** Those whose target set partly overlaps s, without equalling it, leave the comparison
  for s.
- **Strata.** h = machine type × calendar quarter.
- **Estimator.** The Mantel–Haenszel log odds ratio over the discordant pairs:

  `H2a(s) = log[ Σ_h b_T,h · c_K,h / n_h  ÷  Σ_h c_T,h · b_K,h / n_h ]`, with n_h = b_T,h + c_T,h + b_K,h + c_K,h.

  This is the log of the ratio of the two matched odds ratios. It is above 0 when tickets for s show s more strongly
  than tickets for other faults do.
- **Entry.** A set enters only if T has at least 10 discordant pairs and both the numerator and the denominator are
  non-zero. Otherwise it is "not estimable".
- **Pooled H2a.** The same estimator over strata s × type × quarter, pooling every set that enters. A ticket can be a
  comparator for several sets; the bootstrap and the permutation keep that dependence.
- **Interval.** Account-cluster bootstrap (A11):
  - 2,000 replicates, multinomial cluster weights (`fleet_exposure.boot_weights`), seed 15072;
  - every stratified sum recomputed in each replicate;
  - 95% percentile interval.
- **Null.** Category is permuted among mapped primary tickets within each type × quarter stratum, 2,000 times, and
  the pooled statistic recomputed. The one-sided p-value is (number of permutations ≥ observed + 1) / 2,001.
- **Decision.** H2a succeeds if the pooled estimate is above 0 and the one-sided permutation p is at most 0.05. The
  bootstrap interval is reported alongside.

**H2b, secondary: fault tickets against tickets the telemetry cannot see.**
- Same estimator.
- **Comparator K:** tickets whose `target_bucket` is Not in telemetry or Administrative.
- **Permutation:** only between those two groups.
- **No Trouble Found** is in neither H2a nor H2b. It is reported descriptively, because NTF often means an
  intermittent fault that does show in codes.

**Gated sequence.** Each step is tested only if the previous one succeeds.
1. **H2a.**
2. **H1.** Among mapped primary tickets on emitting types, compare the target set's presence in the ticket window with
   its presence in the control. The estimator is the pooled matched odds ratio Σb / Σc, with an account-cluster
   bootstrap interval and a clustered McNemar test (Durkalski) on account clusters, at α = 0.05.
3. **Per-set enrichment.** For each estimable set s: b/c, risk difference and lift, with intervals and the Durkalski
   test. Benjamini–Hochberg across sets, q ≤ 0.05.

Everything else is descriptive, with intervals; the exception is item 2's tests, which TODOS asks for.

**Negative controls.**
- **Stock-out as an outcome** (codes 03, 77), among tickets whose target set contains neither code. That is every
  ticket except Loading Error, which v0 maps to 77.
  - Enrichment here estimates the generic "a machine is in trouble" effect.
  - Restocking visits can also produce these codes.
  - TODOS noted that no Category corresponds to Stock-out. The v0 drafters disagree for Loading Error; see the
    flagged rows in §3.
- **Deposit Door without codes 19 and 78.** These two are user-behaviour codes ("Deposit Door not Opened", "Receiver
  Deposit Door not completely opened"). This variant shows how much of any Deposit Door result rests on them.

## 5. Secondary analyses (TODOS items 2, 3, 4 and 6)
**Item 2. Enrichment by bucket and by frequent code.**
- **What is reported.** For each bucket and each **frequent code**, at 7 d and at 30 d:
  - share of ticket windows with it present;
  - share of control windows with it present;
  - risk difference, lift (pT / pC) and the matched odds ratio b/c;
  - a machine-cluster bootstrap interval;
  - a clustered McNemar test (Durkalski) on machine clusters.
- **Frequent code.** A code present in at least 1% of the 6,204 primary windows (ticket and control together) at
  30 d, counted marginally.
- **The test.** χ² = (Σ_k (b_k − c_k))² / Σ_k (b_k − c_k)² over clusters k, with p = erfc(√(χ²/2)). Plain McNemar is
  not used because it ignores clustering.
- **Multiple testing.** Benjamini–Hochberg is applied separately within the bucket family and the code family.
- **Breakdowns.** Overall, by Category with a Trouble Code roll-up, and for the 157 tickets left out by A3
  (descriptive).

**Item 3. Recency.**
- **Main view.** Cumulative presence within k, for k = 0.5, 1, 2, 6, 24, 168 and 720 h, ticket against control, by
  bucket and for the target set. This answers how far back a linker should look.
- **Exclusive bins (TODOS).** Bins by the most recent occurrence: 0–2 h, 2–6 h, 6–24 h, 1–7 d and 7–30 d. This table
  is descriptive.
- **Guard bands.** On the ticket side, at k = 6 h, 24 h and 7 d.

**Item 4. How much of the target signal the ticket explains.**
- **Excess presence fraction.**
  - Definition: (pT − pC) / pT, for the ticket's own target set, at each k.
  - **What it bounds.** If the control is valid, this is a **lower bound** on the share of target-present tickets
    whose target code comes from the ticket's fault (the Tian–Pearl lower bound on the probability of necessity).
  - **No upper bound.** Presence data cannot identify one: it is min(1, (1 − pC) / pT).
- **Tightest lower bound.** max over k ≤ 7 d of (pT(k) − pC(k)) / pT(7 d), with its k and an interval. Taking the
  maximum over k biases it slightly upward, and we say so.
- **Pairs where both windows have the target.** Descriptive shares of pairs where the ticket window's most recent
  target code is more recent than the control's, and where its count is higher.
- **Match rates.** Precision and recall of "target present" against the Category's target, overall and by Category,
  with the control windows' values alongside. These are **descriptive**, because Category is a label set at closure,
  not a gold standard.

**Item 6. Machine type and model.**
- H1 and per-set enrichment by machine type: on emitting types only, and on all types.
- Model, within type, descriptive. On every matched ticket the model on the ticket equals the model on the installed
  list (docs/06).

## 6. Sensitivities (TODOS item 5)
Each is reported for H2a, H1, and the item 2 bucket table at 7 d and 30 d, in one table.

| # | Variant | Population effect | Purpose |
|---|---|---|---|
| S1 | Planned, cancelled and duplicate tickets put back | +102 pairs (93 Cancelled request, 5 Planned work, 4 Duplicate case) | TODOS "with and without". They are Administrative in the crosswalk, so they join H2b and the item 2 tables. A separate Cancelled request row tests "faults that cleared on their own". |
| S2 | Text flags, each separately and all together | needs `verification/outputs/flags/flags_by_case.csv` (local run, below) | Monitoring template, telemetry mention, quoted code, wrong-machine note, each by field (Trouble Reported, Resolution, Administrative Notes). The share flagged is also reported by month and by Category. |
| S3 | Guard bands, 30 and 60 min | ticket side from the committed guard windows | Codes produced by the ticketing process itself, or residual clock error. Control-side emulation is reported as bounds. |
| S4 | Matched ticket-free lead-in: no ticket in [A − 102 d, A − 67 d) | 2,472 tickets, only where that history is observable (A ≥ 10 Nov 2025) | Removes the asymmetry in A3. |
| S5 | Recently activated machines | drops 187 tickets | first_active is the first telemetry day. 1 August 2025 is left-censored (active when telemetry began), so the 90-day rule applies only where first_active is later. A secondary check uses install year (≥ 2025), from the installed-base list; 159 tickets have no year. |
| S6 | Lookback-truncated windows included | adds pairs with a truncated window | TODOS item 5. |
| S7 | Undetermined 7-day windows counted both ways | 30 ticket and 19 control windows | A8. |
| S8 | Machine instead of account clusters | none | A11. |
| S9 | All 5,312 usable unplanned tickets, ticket side only | adds tickets without a clean control | Shows whether the paired subset is typical. Applies the D5 episode rule with a per-ticket flag. |
| S10 | Interval-based clean rule | needs close times (`flags_by_case.csv`) | Pre-declared now: a pair is unclean when either window overlaps any other ticket's [opened, closed + 2 d]. |
| S11 | Time trend | none | The slope of target presence on calendar date across control windows, × 35 d, gives the bias it would add to the paired difference. |
| S12 | Crosswalk v1 | when it exists | It replaces v0 as confirmatory. |
| S13 | Deposit Door without codes 19 and 78 | none | Negative-control variant (§4). |

**The local flag export** (`python3 -I verification/flags.py --write`) writes `flags_by_case.csv`.
- **Columns:** `case_id`, per-field booleans for the monitoring template, telemetry mention and quoted-code rules, a
  wrong-machine-note boolean, and `closed_at_eastern`. No text.
- **Expected direction.** Dropping flagged tickets lowers presence in the ticket window for the sets most often quoted.
  That biases H1 and H2a toward no effect, by different amounts for different sets and quarters.

## 7. Classifier evaluation design (item 7; design only)
**Use case.** The retrospective linker IPA chose (docs/04 §5). Its inputs are the ✔ fields in the docs/04
"Retrospective linker" column.

**Reference labels.**
- **What labellers see.** The ticket text and the machine's codes, but **not** Trouble Code, Category or Sub Category.
  Those can be classifier inputs, so they cannot also be the reference.
- **Sample.** Closed, unplanned, customer-reported tickets, stratified on the target sets. Zac's pilot template is
  replaced.

**Splits.**
- **By time:** the test period ends at least two weeks before the export date (31 August 2026; docs/04 §5.2), and
  results are reported by period. The ticket template drifted from December 2025.
- **By machine:** no machine is in both the labelled development sample and the test set.

**Text handling.**
- `Device FW` is parsed into a field.
- Results are reported with quoted codes and system names masked and unmasked.
- **Prerequisite:** a phone and e-mail redaction rule, with documented edge cases, must exist before any text goes
  to a language model. The "~300 tickets" in docs/04 has no committed script yet.

## 8. Checks and verification (item 8)
**Checks in `association.py`.** A failed check makes the script exit with an error.
- It reproduces the first look exactly:
  - 3,259 pairs;
  - Electronics 20.3% vs 13.1%, Door 67.9 vs 61.1, Mechanical 54.6 vs 52.2, Stock-out 46.3 vs 45.3, any code 90.2 vs
    89.0;
  - Electro/Mechanical tickets, Door: 1,781 tickets, 78.2 vs 67.8.
- It pins the population counts in A3–A8.
- Control hours are at most 720.
- The guard windows hold no code under 0.5 h or 1 h.
- The crosswalk hash matches, the crosswalk covers all 41 Categories, and every listed code exists.
- A bootstrap replicate with all weights equal to 1 reproduces the point estimate.
- The agreed clean-room numbers match.
- The privacy scan is clean.

**Clean-room build.** Independent agents rebuild, from this document and the committed files alone, without reading
`association.py`:
- the pairs;
- the item 2 table, for buckets, frequent codes and Trouble Code and Category strata;
- H2a and H1;
- the item 3 curve.

Differences are settled in favour of the most literal reading of this protocol, and the agreed numbers become checks.

**Skeptic review.** Four lenses: statistics; recency and item 4; strata and sensitivities; wording and privacy. It
runs before `docs/08_association_results.md` is committed, as for docs/05 and docs/06.

## 9. Deviations from TODOS items 1–9
TODOS is ticked from this table.

| TODOS | Here | Why |
|---|---|---|
| 1. Crosswalk to buckets | Code-level target sets, plus a bucket; drafted blind by three drafters; reviewed by the team, then IPA (v1 confirmatory) | Buckets cut across components |
| 2. Paired shares, RD, lift, McNemar, machine-clustered bootstrap, by Trouble Code and Category | As asked, at 7 d and 30 d; McNemar clustered (Durkalski); the Trouble Code view is a roll-up of Category | Tickets on one machine are not independent |
| 2. "Done when … second independent implementation" | Clean-room build (§8) | as asked |
| 3. Recency bins and guard bands | Cumulative presence within k decides; exclusive bins are descriptive; guard bands are a sensitivity for every headline result | Cumulative presence is what a linker uses |
| 4. Match rate, precision and recall | The excess presence fraction (a lower bound) leads; precision and recall are descriptive | Category is not a gold standard; precision and recall saturate at 30 d |
| 5. Monitoring, telemetry-mention and wrong-machine tickets | Sensitivities, not primary exclusions | Excluding them selects on the outcome |
| 5. Repeat tickets | Primary is one ticket per episode by construction; the D5 flag is applied in S9 | A3 |
| 5. Planned, cancelled, duplicate; truncated windows | S1, S6 | as asked |
| 6. Machine type; model (fleet follow-ups) | Emitting types (A10); model within type, descriptive | Code support differs by family |
| 7. Classifier evaluation | Design only (§7) | Lower priority (IPA, 13 Oct) |
| 8. Adversarial verification | Clean room plus skeptic review this round | as asked |
| (new) Primary hypothesis | H2a specificity; H1 enrichment comes after it | H1 is close to guaranteed positive |
| (new) Primary outcome | 7 days; the TODOS 30-day last-10 list is secondary | 30 days is near ceiling (Door is in 61% of controls) and more exposed to drift |

## 10. Looks at the data so far
Recorded so readers can judge what this protocol could have been tuned to.
1. **The TODOS first look:** 30-day bucket shares, ticket against control, including Electro/Mechanical tickets × Door
   and the Network observation.
2. **docs/05 part E:** non-success rates and Door shares for chronic and other machines.
3. **Planning, 22 October:**
   - code frequencies over all tickets;
   - Category counts;
   - the balance of total transactions between windows (median ratio 1.00);
   - Electronics presence in control windows by month (16% down to 11% over the year).
4. **After the reviewer proposed 7 days:**
   - bucket shares at 7 d and 24 h (Electronics 12.9% vs 5.2% at 7 d);
   - reviewers' bucket-level matched odds ratios at 7 d and 30 d;
   - the final-hour shares: 23.9% of ticket windows against 8.8% of controls have a code in the last 30 minutes;
   - a power check by one reviewer on the review panel, before v0 existed. For a *hypothetical* crosswalk it counted
     pairs, discordant pairs and control-window prevalence per Category set. What reached the protocol author:
     - Deposit Door: 568 pairs, of which 60 are discordant; control prevalence 66.5% (code 19 alone, 54.7%);
     - control prevalence, SAM 9% and User Door 3%.

     These are not ticket-against-control contrasts by Category, and the drafters never saw them.

**No table of Category against ticket-window codes has been viewed.** The crosswalk drafters saw only code
descriptions, Category and Sub Category names and the machine families each Category occurs on.

## 11. Limits
- **One control, always earlier.** Anything that changes over time on a machine (wear, firmware, use) differs between
  the windows by 35 days. S11 measures generic drift, and H2a cancels drift that does not depend on the fault. A
  drift specific to one code, such as a firmware build that starts logging SAM codes, is not cancelled. A
  case-time-control design needs the database (§12).
- **Who the result describes.** It describes tickets that follow about two quiet months on the machine. Chronic
  machines are under-represented: clean controls exist for 21% of their tickets, against 72% of others (docs/05
  part E).
- **The provisional buckets and codes are not IPA's definitions.** "IPA to confirm" applies to every bucket.
- **Category as recorded.** Category is set near closure. If technicians read clearView when they set it, part of the
  association is built in (IPA question 9). S2 bounds this from the text, not from the process.

## 12. Deferred (needs the database; added to TODOS)
- **Re-extract windows without the last-10 cap:** every code's count and most recent time. This makes the 30-day
  outcome exact.
- **Four referent weeks** (days −63 to −35) per ticket, with a Mantel–Haenszel OR: more power and a built-in trend
  check.
- **A case-time-control analysis** on pseudo-anchors in ticket-free stretches.
- **A table of code by machine type over the full year,** which replaces the A10 rule.

## 13. Questions for IPA (item 9 additions)
- Review of crosswalk v0, and IPA's code definitions for v1.
- Which codes each machine family or firmware version can emit.
- Whether technicians look at clearView when they set Category and Sub Category. If they do, part of the association
  is built in.
- What "No Trouble Found" means in practice: no fault, or a fault that could not be reproduced?

## Privacy
- **Inputs:** every input is a committed pseudonymous output (T#####, M#####, Customer NNN).
- **Outputs:** they hold only those ids, labels and aggregates.
- **The flag export:** it carries only booleans and a close time per T id.
- **Raw text** is read only on the local machine, by `flags.py`, and never written.
