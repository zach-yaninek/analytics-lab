# Association study results: ticket fields and the telemetry codes before each ticket

*22 October 2026. Script: `verification/association.py`. It runs locally in about 2 minutes from committed outputs
only, with no raw file and no database, and has 147 self-checks. Every number below is in
`verification/outputs/assoc/as_summary.json` or an `as_*.csv`. Figures: `viz/figures/as_*.png`, drawn by
`viz/association/`. The protocol, `docs/07_association_protocol.md`, was frozen before any result was computed. This
document follows it. **Status: provisional.**
- **Crosswalk v0.** Results use the team-approved draft crosswalk. The confirmatory version, v1, waits for IPA's code
  definitions.
- **Text flags pending.** The sensitivities that need the local text-flag export (S2, S10) are pending.*

**How this was checked.**
- **Protocol first.** The study was pre-specified in docs/07: population, outcome, hypotheses, estimators, decision
  rules and 13 sensitivities. The crosswalk was drafted blind, signed off by the team and frozen by hash.
- **Blind clean-room builds.** Two independent clean-room builds, written from docs/07 alone, each in its own copy of
  the repository, reproduced every one of the 33,515 compared table cells exactly. That includes bootstrap intervals
  and permutation p-values.
- **Hidden until they agreed.** The comparison was made while this script's outcomes were still hidden: it printed
  only "agree" or "disagree" per cell. The readings settled during that comparison are dated amendments in docs/07 §14,
  committed before unblinding.
- **Skeptic review (item 8).** The four-lens skeptic review is recorded in the amendment at the end of this document.

## Bottom line
1. **A ticket's Category picks out its own codes.** This is the protocol's primary test, H2a, and it succeeds.
   - **The comparison.** A machine logs the codes that a ticket's Category points at in the final 7 days before the
     ticket. They rise from the machine's own quiet period 35 days earlier **3.2 times as strongly** as before tickets
     whose Category points at other faults.
   - **The numbers.** 95% interval 2.3 to 4.8; permutation p = 0.0005, the smallest possible with 2,000 permutations
     (`as_h2a.csv`; chart as_01).
   - **What it means.** The Category recorded at closure tends to agree with the codes the machine logged just before
     the call.
2. **The agreement is strongest for the SAM and the user doors, present for the deposit door, borderline for the main
   door, and absent for the computer board.**
   - **Specificity ratios:** SAM 8.0 (3.5 to 34.8); User Door 4.9 (2.5 to 12.5); Deposit Door 4.4 (1.6 to 34.3);
     Main Door 2.6 (1.01 to 30.7); Computer Board 0.5 (0.2 to 1.3).
   - **Packer.** Packer tickets show the clearest signal of all: its code was present only before the ticket 33 times,
     and only in the control 0 times. The entry rule leaves it out of the pooled test, because one side of its ratio is
     zero (§2). The pooled result is therefore conservative.
3. **The codes cluster in the final hours.** The ticket's own code set appears in the last 30 minutes before 23% of
   tickets, against 2% of the same machines' controls. By 7 days the gap is 68% against 50%, and by 30 days 76%
   against 65% (`as_recency.csv`; chart as_02).
   - **For a retrospective linker:** look first at the final hours. A 30-day look-back adds mostly codes that would
     have been there anyway.
4. **At least about half of the matching codes come from the ticket's fault.** Of tickets with their own codes present
   in the final 7 days, at least 49% (95% 45% to 53%) have them because of the fault rather than by chance, if the
   control is valid (`as_item4.csv`).
   - **What this is.** The figure is a lower bound, and no upper bound can be identified from presence data.
5. **Robust to every sensitivity that could be computed.** The pooled specificity ratio stays between 2.3 and 3.4, and
   its interval stays above 1, in all of these:
   - guard bands that drop the final 30 or 60 minutes;
   - a matched ticket-free lead-in;
   - dropping recently activated or recently installed machines;
   - truncated windows;
   - planned, cancelled and duplicate tickets put back;
   - machine-level clusters.

   (`as_sensitivities.csv`)
6. **What this does not show.**
   - **Prediction.** It does not show that codes predict tickets, because only the weeks before tickets were examined.
   - **Correctness.** It does not show that Categories are correct, or that the provisional code meanings are IPA's.
   - **Built-in agreement.** If technicians read clearView when they set Category, part of the agreement is built in.
     That question is open with IPA, and the text-flag sensitivity (S2) that bounds it from the ticket text is pending
     a local run of `verification/flags.py --write`.

## 1. The data
- **Primary population** (docs/07 A3): 2,950 unplanned tickets on 2,376 machines, 5 October 2025 to 31 August 2026.
  Each has:
  - a 30-day window before the ticket;
  - a clean control window on the same machine 35 days earlier;
  - no other ticket in either window;
  - telemetry on the machine at the time.
- **Pairs used at 7 days.** 2,911 tickets on 2,350 machines and 610 account clusters. 39 pairs leave, because one of
  their windows has more than 10 distinct codes and so cannot show whether a code fell in the final 7 days (A8).
- **Mapped tickets.** 1,706 of those 2,911 have a Category with a code set. H1 uses the 1,439 tickets on machine types
  that log their own set (A10).
- **Reproductions.** The TODOS first look is reproduced exactly: 3,259 paired tickets; Electronics 20.3% vs 13.1%, Door
  67.9% vs 61.1%. So is every count docs/07 states (`as_summary.json`, `pinned_counts`).

## 2. H2a, the primary test: specificity (`as_h2a.csv`; chart as_01)
**Pooled H2a at 7 days:** specificity ratio 3.22 (95% 2.34 to 4.77); one-sided permutation p = 0.0005.
- **How it was computed.** Category was shuffled within machine type × quarter, 2,000 times. The interval is a
  bootstrap over 610 account clusters.
- **Decision.** H2a succeeds.

**Per set** (descriptive; only the pooled test decides):

| Code set | Tickets (target / comparator) | Discordant pairs, target (b / c) | Specificity ratio (95%) | Permutation p |
|---|---|---|---|---|
| SAM (14, 17–18, 32–35) | 203 / 746 | 89 / 6 | 8.0 (3.5–34.8) | 0.0005 |
| User Door (02, 11, 27, 41–48) | 218 / 939 | 68 / 12 | 4.9 (2.5–12.5) | 0.0005 |
| Deposit Door (19–20, 78–80) | 554 / 376 | 45 / 13 | 4.4 (1.6–34.3) | 0.0015 |
| Main Door (30–31) | 134 / 815 | 45 / 5 | 2.6 (1.01–30.7) | 0.077 |
| Computer Board (13, 25) | 207 / 1,143 | 22 / 11 | 0.5 (0.2–1.3) | 0.91 |

**Not in the pooled test** (entry rule, docs/07 §4):
- **Packer:** b = 33 and c = 0 on the target side. The rule needs a non-zero numerator and denominator, so a set whose
  every discordant pair points the same way is left out.
- **Improper Use, Weight Scale and Loading Error:** 3, 4 and 3 discordant pairs.
- **Counterweight System:** its codes 66 and 67 are logged only by sbsx machines, while its tickets are on alEx and mlc
  machines.

**Computer Board's codes are not specific.**
- Code 25, "No Communications with Dispenser", rises before tickets in general: 10.8% vs 3.5%, matched OR 4.5 (item 2).
- It rises no more before Computer Board tickets than before tickets for other faults.
- The crosswalk question about code 13 (which board?) and code 25 is therefore one for IPA (§7).

**30 days (TODOS outcome, secondary):** 1.90 (1.39 to 2.75), p = 0.001. It is weaker, as expected: at 30 days the
codes are near ceiling, and the window is more exposed to drift.

**H2b (descriptive):** fault tickets against Network and other Not-in-telemetry tickets, specificity ratio 8.8 (5.0 to
22.8). Faults the log can see stand apart much more from issues it cannot see than from each other (`as_h2b.csv`).

## 3. H1 and the per-set step (`as_h1.csv`, `as_sets.csv`; chart as_03)
**H1** (tested, because H2a succeeded). Over 1,439 tickets on machine types that log their own set:
- 311 have the set present in the final 7 days before the ticket but not in the control, and 48 the reverse.
- Matched odds ratio 6.5 (95% 5.0 to 8.9); Durkalski p < 0.001. H1 succeeds.

**Per set** (tested, because H1 succeeded):
- **Enriched** (b > c and BH q ≤ 0.05): 5 of the 6 sets that meet the reporting threshold.

  | Set | Matched odds ratio (95%) | Ticket vs control |
  |---|---|---|
  | SAM | 14.8 (7.8–47.5) | 79% vs 38% |
  | Main Door | 9.0 (4.1–44) | 45% vs 15% |
  | User Door | 5.7 (3.4–11.8) | 85% vs 60% |
  | Deposit Door | 3.5 (2.0–7.7) | 86% vs 81% |
  | Packer | 33 to 0 | 59% vs 21% |
- **Not enriched:** Computer Board, 2.0 (1.0 to 4.8), q = 0.08.

## 4. Item 2: enrichment by bucket and by code (`as_item2_buckets.csv`, `as_item2_codes.csv`)
**Final 7 days, 2,911 pairs, machine-cluster intervals:**

| Bucket | Ticket | Control | Matched OR (95%) | BH q |
|---|---|---|---|---|
| Electronics/software/comms | 12.6% | 5.1% | 3.7 (2.9–4.8) | < 0.001 |
| Door issue | 54.1% | 42.6% | 2.4 (2.1–2.8) | < 0.001 |
| Operational status | 8.4% | 5.5% | 2.1 (1.6–2.7) | < 0.001 |
| Mechanical fault | 40.5% | 36.2% | 1.5 (1.3–1.8) | < 0.001 |
| Stock-out (negative control) | 39.2% | 40.0% | 0.86 (0.69–1.07) | 0.24 |
| User behavior | 36.3% | 37.7% | 0.78 (0.62–0.96) | 0.04 |
| Incomplete transaction | 26.2% | 26.2% | 1.00 (0.83–1.22) | 1.00 |

- **Frequent codes.** 24 of the 35 frequent codes are enriched before tickets (q ≤ 0.05). One is less common before
  tickets: 04 "Half Garment", 22.4% vs 25.0%.
- **The largest code-level ratios:** the numbered user doors (e.g. 48, "User Door 8 is Open", 22 to 1), 25 "No
  Communications with Dispenser" (4.5), 30 "Main Door not Closed" (4.0) and 81 "Opening Door Blocked" (3.5).
- **At 30 days (the TODOS window):** Electronics 20.9% vs 13.7% (2.4), Door 71.4% vs 64.0% (2.0), Mechanical 56.9% vs
  54.7% (1.4).
- **Stock-out at 30 days.** It also edges up, 48.4% vs 47.3% (1.5, 1.1 to 2.1). This is one sign that the 30-day window
  picks up generic differences between the two periods that the 7-day window does not.
- **Breakdowns.** By Category and Trouble Code they are in `as_item2_breakdowns.csv`.
  - **No Trouble Found tickets** also show door codes before them: 44.0% vs 32.5%, matched OR 3.0. That fits NTF often
    meaning an intermittent fault the technician could not reproduce (IPA question, §7).
  - **The 157 tickets left out** because another ticket came in the 5 days before them show the strongest
    pre-ticket rise of all: Electronics 23.3% vs 4.8%. They are repeat calls on a fault still present.

## 5. Item 3: recency (`as_recency.csv`, `as_recency_bins.csv`, `as_guard.csv`; chart as_02)
**Code-set presence, ticket window vs control** (1,439 tickets; 1,469 at 30 days):

| Window | Ticket | Control |
|---|---|---|
| 30 min | 23.5% | 1.5% |
| 1 h | 31.3% | 3.5% |
| 2 h | 39.3% | 7.3% |
| 6 h | 47.6% | 13.9% |
| 1 day | 56.2% | 25.9% |
| 7 days | 68.4% | 50.1% |
| 30 days | 75.6% | 65.0% |

- **What this shows.** Most of the difference between ticket and control is in the final day, and much of it in the
  final hours.
- **Guard bands.** Dropping the final 30 or 60 minutes lowers code-set presence at 7 days only from 68.4% to 68.1% and
  67.5%. The pooled specificity ratio moves from 3.2 to between 3.1 and 3.4 (S3, `as_sensitivities.csv`).
- **The ticketing process.** Codes produced by the call itself, such as the caller trying the machine again, cannot
  be separated from the fault in this data. The guard bands show the result does not depend on them.

## 6. Items 4 and 6: how much the codes explain, and machine types (`as_item4.csv`, `as_match_rates.csv`, `as_by_type.csv`)
**Excess presence fraction (pT − pC)/pT.**
- **Values:** 0.93 at 30 minutes, 0.81 at 2 hours, 0.54 at 1 day, 0.27 at 7 days and 0.14 at 30 days.
- **Tightest lower bound** over the windows up to 7 days: 0.49 (95% 0.45 to 0.53, at 6 hours).
- **What it means.** If the control is valid, at least 49% of tickets with their own codes in the final 7 days owe
  those codes to the fault. docs/07 A3 lists the two ways the control may not be valid, which push in opposite
  directions.

**Where both windows have the code set** (673 tickets), the ticket window's code is:
- more recent in 76% (72% to 80%);
- more frequent over the window in 79% (76% to 82%).

A linker can use timing and counts, not only presence.

**Match rates** (descriptive; Category is a closure label, not a gold standard). At 7 days, over all sets:

| Match | Recall | Precision |
|---|---|---|
| Target code present (control baseline) | 68.4% (50.1%) | 19.1% (16.3%) |
| Matching bucket present, as TODOS asks (control baseline) | 48.1% (33.6%) | 21.9% (17.2%) |

Precision is low because the same codes are present before many tickets for other faults. Presence alone is a weak
classifier; timing and specificity matter.

**Machine types.**
- **Estimable types:** the six that meet the reporting threshold all show enrichment of the ticket's own code set.
  - scrubex2.0-4 13.3, scrubex2.0-5 8.0, scrubex2.0-2 6.8, scrubex2.0-3 6.1, scrubex-4 4.8, scrubex-2 4.3.
- **Too few tickets:** the other types have too few tickets on their own.
- **Models within type:** `as_by_model.csv`.

## 7. Limits and questions for IPA
**Limits.**
- **One control, always earlier.** S11 finds drift across control windows worth at most 0.9 points over 35 days, against
  an 18-point difference in code-set presence at 7 days.
- **Who the result describes.** Tickets that follow about two quiet months on the machine. Chronic machines are
  under-represented (docs/05).
- **Not yet measured:**
  - the text-flag exclusions (S2);
  - the interval-based clean rule (S10);
  - crosswalk v1 (S12).
- **Provisional meanings.** The bucket and code meanings are provisional; IPA to confirm.

**Questions for IPA** (added to TODOS item 9):
- **Code definitions for crosswalk v1,** in particular:
  - **13 and 25.** Which board does 13 "Invalid Driver Board Response" refer to? Is 25 "No Communications with
    Dispenser" a symptom of many faults rather than of the computer board?
  - **66 and 67.** Which family logs them? They are emitted only by sbsx machines here.
- **clearView.** Do technicians consult clearView when they set Category?
- **No Trouble Found.** What does NTF mean in practice? NTF tickets show door codes rising before them.

## Figures
![The codes a ticket's Category points at rise 3.2x more before it than before other faults' tickets](../viz/figures/as_01_specificity_by_set.png)
![A ticket's own codes appear in its final 30 minutes for 23% of tickets, against 2% of controls](../viz/figures/as_02_recency.png)
![5 of 6 code sets are clearly more often present before their tickets; Computer Board is not](../viz/figures/as_03_enrichment_by_set.png)

## Privacy
- **Public outputs:** `verification/outputs/assoc/` holds only T##### and M##### ids, Customer NNN as cluster labels,
  Categories, codes, machine types and aggregates.
- **Privacy scan:** the script checks every text column and summary string against the pseudonym formats. When the raw
  workbook is present locally, it also checks them against real serials, account names and case numbers.
- **Figures:** the charts show code sets, Categories and counts only.
