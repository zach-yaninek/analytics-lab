# IPA follow-ups: request types by machine age, and repeat-contact pairings (results)

*29 October 2026.*

**Script and inputs.**
- The script is `verification/followups.py`. It runs locally in about 15 seconds.
- It reads the two raw workbooks, which are gitignored, and the committed ticket-to-device map.
- It has 67 self-checks. 36 of them tie the run to numbers already committed, and 27 of those run before any new
  result.

**Where everything is.**
- **Tables:** `verification/outputs/followups/`. Almost every number below is in `followups_summary.json` or an
  `ag_*` / `rp_*` table there; the few that are not name their source.
- **Slide charts:** `viz/figures/slides/sl_18` to `sl_31`, which print their definitions on the image.
- **Protocol:** `docs/09_followups_protocol.md`, frozen and pushed before any result. Its §12 records the amendments
  and corrections made after the first run and after the two independent reviews.

**Why this was done.** IPA raised these questions after slides 4 and 5 of the update deck:
- whether young machines' extra tickets are different kinds of problem, ideally ones they have since fixed;
- what follows what in repeat contacts;
- which machine and telemetry types are the offenders.

**How it was checked.**
- **Protocol first.** docs/09 fixed the populations, request-type groups, tests, gate and thresholds before any result
  was computed. It was pushed in commit 146f179. The request-type groups are frozen by hash in
  `verification/reference/request_types_v0.csv`.
- **Pins.** Every committed number the analysis touches reproduces from the uploaded files:
  - slide 4's 6,750 tickets on 8,946 machines and its age-band rates;
  - Zac's 6,665 / 1,574 / 515 repeat counts;
  - the 631 seven-day repeats;
  - the 22.0% without monitoring templates.
- **Clean-room builds.** Three builds, written from docs/09 alone without seeing the script, matched:
  - Part A's global statistic exactly (X = 33.776), the gate's outcome, the decomposition to the ticket, and the halves;
  - Part B's pairs, classes, directions and same-by-gap shares exactly;
  - the null rates within simulation error.

  Where docs/09 allowed more than one reading, the choice is recorded in §12. None changes a conclusion.
- **Independent reviews.** Two rounds of reviewers re-derived the numbers with their own code, and a skeptic re-checked
  each finding. The confirmed findings are fixed; docs/09 §12 items 6 and 7 list the ones that touched the code.
- **Tests.**
  - A fixture test runs the script on synthetic data against an independent oracle, including a copy with planted
    answers.
  - 36 unit tests cover the edges: the 30-day, 7-day and 2 Aug boundaries, Mantel–Haenszel and the CMH excess on known
    tables, the chi-square tail, the exact decomposition, and the null against its closed form.
- **Not blind.** The Category shares by age were previewed while the protocol was planned (docs/09 §9). All four
  Categories that pass the gate (Touchscreen, Packer, Curtain and SAM) were among those seen, so their q-values are
  descriptive; the group-level result is the test.

**Terms used below.**
- **Under 4 / 4+:** the machine's age at the midpoint of its months on IPA's list; under 4 = the first three bars of
  slide 4 (<1, 1–2 and 2–4 years).
- **Support models:** the 15 models with at least 100 machine-months in each age group. Within-model comparisons use
  only these.
- **Share ratio:** a type's share of under-4 machines' tickets ÷ its share of 4+ machines' tickets of the same model,
  pooled over the support models (Mantel–Haenszel). 1 = the same mix.
- **Excess:** under-4 tickets of a type minus those expected at the same within-model mix (the CMH numerator,
  `excess_under4_tickets`).
- **The gate:** the global within-model test first; then the groups, Benjamini–Hochberg (q < 0.05); then the
  Categories within groups that pass. **q** is the Benjamini–Hochberg q-value.
- **Estimable:** at least 20 tickets from at least 10 accounts in each age group. Types that are not estimable are
  reported as counts only.
- **Index ticket / repeat:** an unplanned ticket opened before 2 Aug 2026; it repeats if the next unplanned ticket on
  the same machine opens within 30 days (or 7). A repeat contact, not necessarily a failed repair.
- **SRR (ratio to the fleet):** a unit's observed ÷ random-timing repeats, divided by the fleet's 1.53.
- **Non-overlapping pairs:** repeat pairs taken in time order so that no ticket is in two pairs.
- **Same-Category lift:** a unit's same-Category share of repeats ÷ its share among ticket pairs 90+ days apart.
  **Matrix lift:** observed ÷ expected pairs if follow-up types were unrelated to index types within model.

## Bottom line

### Slide 4: do young machines' tickets differ in type?
1. **Young machines have more tickets of almost every type.**
   - Machines under 4 years old have **8.0** unplanned tickets per 100 installed machine-months, against **4.8** for
     older ones (×1.66).
   - By type the crude ratio is close to ×1.66 for the four largest groups: Door ×1.73 (1.49–2.01), Electronics ×1.71
     (1.43–2.10), Mechanical ×1.64 (1.33–2.04), No Trouble Found ×1.65 (1.32–2.05).
   - Network is lower, ×1.10 (0.83–1.45), and Monitoring higher, ×3.09 (1.94–5.19).
   - Chart [sl_18](../viz/figures/slides/sl_18_age_type_rates.png).
2. **Within model, the mix differs, but modestly.** The comparison is under 4 against 4+ on the 15 support models,
   which hold 99% of under-4 and 69% of 4+ tickets. The mix differs (permutation p < 0.001). After the gate, two
   groups differ:
   - **Electronics** is a larger share of young machines' tickets: share ratio **1.31** (95% 1.09–1.62). Its excess of
     49 under-4 tickets is almost all **Touchscreen** (+44; share ratio **1.85**, 1.39–2.53).
   - **Mechanical** is a smaller share: **0.70** (0.59–0.84), a shortfall of 62 tickets. **Packer** has the lowest
     ratio, 0.51 (0.35–0.76), and the largest part (−24), but **SAM** (−19) and **Curtain** (−13) together account for
     more.
   - **SAM and Curtain** (0.78 each) pass the permutation gate, but their account-bootstrap intervals include 1
     (0.61–1.02 and 0.61–1.08), and SAM's p (0.041, Monte Carlo SE 0.004) is close to 0.05. Treat them as borderline.
   - **Door as a whole does not differ** (1.06; 0.93–1.19). Within it, **Deposit Door** is a larger share on young
     machines (1.31; 1.11–1.57; +42 tickets), and User Door and Service Door are smaller. These Door Categories were
     not formally tested, because the Door group did not pass the gate.
   - The q-values of the four Categories that pass are descriptive (see "Not blind" above).
   - Charts [sl_19](../viz/figures/slides/sl_19_age_mix_adjusted.png) and
     [sl_20](../viz/figures/slides/sl_20_age_categories.png).
3. **The extra tickets come mostly from age within model, not from which models are young.**
   - Under-4 machines had **1,447** more tickets than 4+ machines' rates would give them. That splits into:
     - **1,156 (80%) within model** (95% 682–1,597): young machines run above older machines of the same model;
     - **282 model mix**: young machines are more often high-rate models;
     - **9** on models outside the comparison.
   - By group, within model:
     - Door +535 (363–702), nearly all **Deposit Door** (+481);
     - Electronics +472 (331–626): **Touchscreen** +281 and Computer Board +91;
     - No Trouble Found +118.
   - **Mechanical** shows +278 extra tickets in all but −127 within model. Its excess is model mix: alEx curtain
     repairs on young alEx machines.
   - The Touchscreen excess sits on machines installed in 2022–23, which are 2–4 years old this year (item 4).
   - Chart [sl_21](../viz/figures/slides/sl_21_age_excess.png).
4. **"Fixed" cannot be shown without IPA's dates, but the install years point to Touchscreen.**
   - **By install year** (15 support models; chart [sl_31](../viz/figures/slides/sl_31_install_years.png);
     `ag_install_pooled.csv`), tickets per 100 machine-months:

     | Installed | Touchscreen | Deposit Door | Computer Board | All unplanned |
     |---|---|---|---|---|
     | 2019–21 | 0.27 | 0.62 | 0.41 | 4.8 |
     | 2022–23 | **1.54** | 1.35 | 0.50 | 7.8 |
     | 2024–26 | 0.39 | **2.13** | 0.65 | 8.3 |
     | 2022–23 ÷ 2024–26 | **×3.9 (2.9–5.4)** | ×0.63 (0.49–0.83) | ×0.76 (0.46–1.21) | ×0.95 (0.81–1.10) |

     - **Touchscreen** tickets cluster on machines installed in 2022–23, and machines installed since 2024 are back near
       the earlier rate. The same holds within each big 2.0 model (2022–23 against 2024–26 installs): LVD-Remote-2.0
       2.66 against 0.59, MV-2.0 2.57 against 0.58, LVRR-WP-2.0 1.15 against 0.37 (`ag_install_year.csv`).
     - **Deposit Door** rises with each newer install cohort, most on LVRR-WP-2.0 (1.50, 3.76, 6.70) and MV-2.0 (0.87,
       1.58, 2.26).
     - **Computer Board** has no 2022–23 peak.
     - **All unplanned tickets:** the newest machines have as many tickets as the 2022–23 ones. Their mix has moved
       from Touchscreen to Deposit Door.
   - **Reading.** The Touchscreen pattern fits a problem in 2022–23 production that later machines do not have. In one
     year of data it cannot be told from a failure peak at 2–4 years, because install year and age move together.
     Earlier ticket history (did 2019–21 installs peak at 2–4 years?) or IPA's change dates would tell which. The
     cohorts were grouped after the review, so the ratios are descriptive (docs/09 §12 item 7).
   - **By half** (pre-specified): a rule fixed in advance picked the three Categories with the largest within-model
     excess. For each, the young-minus-older gap per 100 under-4 machine-months, second half against first:

     | Category | First half | Second half | Change (95%) |
     |---|---|---|---|
     | Deposit Door | 1.05 | 1.11 | +0.07 (−0.35 to 0.47) |
     | Touchscreen | 0.42 | 0.83 | **+0.41 (0.15 to 0.66)**: the gap widened |
     | Computer Board | 0.41 | 0.02 | **−0.39 (−0.69 to −0.12)**: the gap closed |

     - Touchscreen's gap widened: young machines went from 0.78 to 1.06 per 100 machine-months, while older machines
       of the same models went from 0.36 to 0.23.
     - Computer Board's gap closed, which fits a fix but does not prove one: about two-fifths of it is older machines'
       rate rising (0.29 to 0.46), not young machines' falling (0.70 to 0.48).
   - IPA's dates of design or firmware changes would turn both views into a test. Chart
     [sl_23](../viz/figures/slides/sl_23_age_halves.png).
5. **By model** (the six models with at least 30 tickets in each age group; chart
   [sl_22](../viz/figures/slides/sl_22_age_by_model.png)):
   - **Rates.** Young machines run above older ones on five of the six:

     | Model | Under-4 ÷ 4+ rate (95%) |
     |---|---|
     | LVD-Remote-2.0 | ×1.43 (1.18–1.75) |
     | LVRR-WP-2.0 | ×2.12 (1.63–2.82) |
     | MV-2.0 | ×1.94 |
     | SV-48-2.0 | ×1.74 |
     | LVRR-WP | ×2.44 |

     alEx LC-D is the exception: ×0.77 (0.47–1.31).
   - **Mix.** The mix differs by age within LVD-Remote-2.0, LVRR-WP-2.0 (q = 0.0015 each) and LVRR-WP (q = 0.022):
     - LVRR-WP-2.0's young machines: Door 60% of tickets against 47%; Mechanical 5% against 14%;
     - LVD-Remote-2.0's young machines: Electronics 31% against 22%; Mechanical 18% against 28%.
6. **Telemetry type mostly re-labels model** (docs/09 §3.6). Of the types that cut across models:
   - alex2.0-1 and alex2.0-3, which span the alEx models, show no clear age difference in mix (q = 0.21);
   - scrubex-7 does (q = 0.0023). It carries 57 of LVRR-WP's 63 under-4 tickets.

   Rates on installed months by telemetry type still need the database extract.
7. **Robustness** (`ag_tests.csv`, `ag_type_adjusted.csv`):
   - **Permuting within model × account**, which allows for site practice, the mix still differs (p = 0.025), but no
     single group then passes Benjamini–Hochberg.
   - **Under 2 vs 2+ years** (12 models): a larger but different difference (p < 0.001). The youngest machines have
     more Door (1.19), Other (1.74) and Monitoring (2.08) tickets and fewer Electronics (0.74); Mechanical does not
     differ (0.93).
   - **Under 6 vs 6+:** no clear difference (p = 0.06); nothing passes, and Electronics turns below 1 (0.79).
   - **Excluding machines installed during the period, or Monitoring and No Trouble Found:** the same result.
   - **Each half alone:** p = 0.05 (first half) and 0.001 (second).

   So the under-4 difference is real but modest, and its parts sit at different ages. Door tickets are a larger share
   on the youngest machines; Electronics is 30% of 2–4-year-old machines' tickets, against 17% under 1, 20% at 1–2
   and 18% at 4–6 (crude shares, which mix models; `ag_band_rates.csv`).

### Slide 5: what are the repeat contacts?
8. **What follows what.** Of the 1,574 repeats within 30 days (chart
   [sl_27](../viz/figures/slides/sl_27_repeat_classes.png)):

   | Pairing | Share |
   |---|---|
   | Same Category | **31%** |
   | Same group, other Category | 10% |
   | Different group | **32%** |
   | A Monitoring ticket involved | 11% |
   | No Trouble Found involved | 13% |
   | A blank Category involved | 4% |

   - **The three process classes** (Monitoring, No Trouble Found or a blank Category involved) are 28% together.
   - **Zac's 515 same-Category repeats** are the 490 in the Same Category class plus 25 that involve No Trouble Found
     (23) or a Monitoring ticket (2), which the class order puts first.
   - **Within 7 days:** same Category 33%, Monitoring 17%, different group 26%.
   - **Monitoring.** It is mostly the follow-up: a monitoring ticket is the follow-up in 128 repeats (125 of them after
     another kind of ticket, a help-desk check), and the index only in 45.
   - **No Trouble Found** splits both ways, counted within its class (docs/09 §12 item 4): 96 as the index only, 82 as
     the follow-up only, 23 both.
   - Charts [sl_24](../viz/figures/slides/sl_24_repeat_pairings_7d.png) (7 days) and
     [sl_25](../viz/figures/slides/sl_25_repeat_pairings_30d.png) (30 days).
9. **The same problem comes back quickly** (chart [sl_26](../viz/figures/slides/sl_26_same_problem_by_gap.png)).
   - **By gap.** Over every pair of tickets on one machine with a recorded Category, monitoring excluded (6,980 pairs;
     No Trouble Found counts as a Category), the same-Category share falls with the gap between them:

     | Gap | Pairs | Same Category |
     |---|---|---|
     | Up to 1 day | 63 | 46% |
     | 1–7 days | 522 | 44% |
     | 7–30 days | 1,291 | 36% |
     | 30–90 days | 1,967 | 34.5% |
     | 90–180 days | 1,730 | 30.5% |
     | Over 180 days | 1,407 | 27% |

     These are all pairs, not only consecutive ones, so the 46% is not the same measure as item 8's 32% of repeats a
     day or less apart. Pairs a day or less apart may include duplicate tickets for one call (docs/09 B3): 12 of the
     81 one-day repeats are under an hour apart (`rp_pairs.csv`).
   - **Per machine.** Pairs within 30 days share a Category 13 points more often than pairs 90+ days apart (95% 9–18; 390
     machines).
   - **Against the machine's own mix.** Of the 833 repeats with a recorded Category on both tickets (monitoring
     excluded) on the 299 machines with two or more such repeats, **39%** share it, against **33%** if each machine's
     Categories came in random order (p < 0.001). Over all 1,336 such repeats it is 38% (`rp_pairs.csv`).
   - **But a follow-up does not clearly match its own index more than the machine's other repeats.** On
     non-overlapping pairs it matches 38% of the time against 37% by chance (p = 0.16). Quick repeats tend to be the
     machine's current problem.
   - **By group, the follow-up repeats the index's group:**
     - Mechanical 57% of Mechanical repeats;
     - Door 49%;
     - Electronics 46%;
     - Network 38%.
10. **Offenders by volume are the biggest models; once ticket volume and timing are allowed for, no model or telemetry
    type stands out from the fleet.**
    - **The random-timing baseline.** If each machine's tickets came at random over its own months, 15.4% of tickets
      would repeat within 30 days. 23.6% do (×1.53). Within 7 days it is 4.1% against 9.5% (×2.30).
    - **By volume:** LVD-Remote-2.0 holds 19% of all repeats, LVRR-WP-2.0 17% and MV-2.0 12%.
    - **By model, beyond volume:** raw repeat rates run from 14.8% (LC-30) to 36.9% (scrubBank 480), but they track
      tickets per machine. Every model's observed ÷ expected is above 1 (1.11 to 1.78), clearly so for all but LC-30
      (1.11; 95% 0.76–1.49). Relative to the fleet's 1.53, no model differs after Benjamini–Hochberg:
      - LC-30 is lowest, at 0.73 (0.50–0.97);
      - LVD-Remote is highest, at 1.16 (1.00–1.35);
      - q = 0.17 for both.
    - **By telemetry type:** no type differs either; every type's observed ÷ expected is clearly above 1 except mlc-1's
      (1.27; 0.97–1.67). "No device match" and "Unknown" are rows of their own but are not telemetry types, so they are
      not tested.
    - Chart [sl_28](../viz/figures/slides/sl_28_repeat_offenders.png) (by model and by telemetry type).
11. **Pairings per model** (charts [sl_29](../viz/figures/slides/sl_29_class_mix.png), by model and by telemetry
    type, and [sl_30](../viz/figures/slides/sl_30_model_matrices.png)).
    - **Same Category, as a share of all the model's repeats** (the class mix; descriptive, not tested):

      | Model | Same Category |
      |---|---|
      | alEx LC-D | 39% |
      | LVRR-WP-2.0 | 36% |
      | MV-2.0 | 34% |
      | LVRR-WP | 31% |
      | LVD-Remote-2.0 | 30% |
      | MV | 23% |
      | LVD-Remote | 21% |

    - **Same-Category lift.** This uses the repeats where both tickets have a recorded Category and neither is a
      monitoring ticket (`same_category_share_recorded_pairs`), against the same model's ticket pairs 90+ days apart:
      - LVD-Remote-2.0: 39% against 20%, twice as often (lift 1.97);
      - MV-2.0: 43% against 24% (1.75);
      - LVRR-WP-2.0: 44% against 36% (1.22);
      - alEx LC-D: 48% against 48% (1.00). Its tickets are mostly curtain repairs, so same Category is the norm at any
        gap.
    - **Telemetry types (class mix):** alex2.0-1's repeats are 49% the same Category; mlc-1's are 53% a different
      group.
12. **Slide 5's random-timing figure.**
    - The "about 14.8%" in slide 5's notes (docs/02 F2) is what one common window for every machine gives: 14.8% here.
    - On each machine's own months it is 15.4%.
    - The conclusion stands: the clustering is real.

## 1. Data and populations
- **Part A**, slide 4's population:
  - 6,750 unplanned tickets on 8,946 listed machines, 1 Aug 2025 to 31 Aug 2026; third-party-plan machines excluded;
  - under 4 years: 3,629 tickets, 3,987 machines, 45,103 machine-months;
  - 4+: 3,121 tickets, 4,959 machines, 64,518 machine-months.
- **Part B**, Zac's population:
  - 7,186 unplanned tickets, including the 433 on serials not on IPA's list (`verification/outputs/fleet/fx_summary.json`);
  - 6,665 eligible index tickets (opened before 2 Aug 2026) on 3,495 machines.
- **Request types:** ten groups from IPA's Trouble Code (docs/09 §3.3). The Category is the second level. A blank
  Category is "Not categorised", except under the Electronics, Network, Software and Operator Error codes, which keep
  their group.
- **Telemetry type:** the clearView type of the device matched to the machine's tickets.
  - A device matches 2,993 machines (82% of tickets). 35 of them have a blank type ("Unknown"), so 2,958 machines
    have a telemetry type.
  - "No device match" (692 machines) and "Unknown" are shown but are not types.
  - No machine matches devices of two types.

## 2. Part A details
- **Crude rates** (`ag_type_rates.csv`). By rate, every group's estimate is higher on young machines; Network
  (0.83–1.45) and Software (0.68–2.28) are not clearly so.
  - By crude share the large groups barely move: Door 1.04, Electronics 1.03, Mechanical 0.99. Network (0.66;
    0.50–0.86) and Monitoring (1.86; 1.21–3.05) do. The unstratified chi-square on the 2 × 9 table is 33.9 on 8 degrees
    of freedom (p < 0.001); it mixes models and ignores clustering, so it is descriptive only.
  - At Category level the crude mix differs strongly: Deposit Door ×2.05 (1.69–2.53) and Touchscreen ×2.54
    (1.98–3.26) are larger shares; Main Door, User Door and Computer Board (×0.54–0.58) smaller. That is partly because
    young machines are mostly 2.0 models. Within model these shrink (Deposit Door 1.31, Touchscreen 1.85, Main Door
    1.01), and Curtain reverses (crude 1.76, within model 0.78).
  - Electronics and Mechanical shift as groups only within model.
- **Model-adjusted mix** (`ag_type_adjusted.csv`, variant `primary`):
  - On the same 15 models, the Mantel–Haenszel rate ratios agree with a Poisson main-effects fit by iterative
    proportional fitting (IPF) for the large groups: Door 1.85 against 1.85, Mechanical 0.96 against 0.96,
    Electronics 2.18 against 2.14. Small groups differ more, for example Monitoring 2.46 against 2.78.
  - All nine primary groups were estimable. 15 Categories were estimable; the rest are reported as counts only.
  - Each type's excess (`excess_under4_tickets`) is the CMH numerator: under-4 tickets minus those expected at the
    same within-model mix.
- **The gate:**
  1. Global test: p < 0.001.
  2. Groups passing Benjamini–Hochberg: Mechanical and Electronics (q = 0.002 each).
  3. Categories within them: Touchscreen (q = 0.002), Packer (0.003), Curtain (0.036) and SAM (0.041). All four were
     seen in the planning preview, so these q-values are descriptive.

  Monitoring (1.66; 0.93–3.61) and Software (0.58) did not pass at the group step. Every permutation p has its Monte
  Carlo standard error in `p_mc_se`.
- **Decomposition** (`ag_decomposition.csv`): the per-group and per-Category parts with intervals, in tickets and per
  100 under-4 machine-months. In all: 3.21 extra tickets per 100 (2.50–3.94), of which 2.56 within model (1.51–3.50)
  and 0.63 model mix (−0.08 to 1.49). The parts add to the total exactly; this is checked in code.
- **By model and by telemetry type:** `ag_by_model.csv` and `ag_by_type.csv`, with shares of every group and the
  within-model or within-type mix test. `ag_support.csv` has machines, accounts, months and tickets by model and age
  group.
- **Sensitivities:**
  - `ag_tests.csv` (global tests, and the descriptive unstratified chi-square);
  - `ag_type_adjusted.csv`, under its variants. Notable rows:
    - **Lexis split**, which assigns each month and ticket the machine's age at the time: Electronics 1.26,
      Mechanical 0.71;
    - **unlisted serials' tickets added as 4+:** Electronics 1.37, Mechanical 0.73;
    - **6-year cut:** nothing passes; Electronics turns below 1 (0.79, not significant).

  Also `ag_band_rates.csv` (all seven age bands) and `ag_by_status.csv` (the mix within service status).
- **Halves and install years:** `ag_halves.csv`, `ag_install_year.csv` (by model) and `ag_install_pooled.csv`
  (pooled over the support models, by year and cohort, with intervals and each cohort's ratio to 2024–26). The halves
  keep each machine's full-period age group.

## 3. Part B details
- **Pairs** (`rp_pairs.csv`, one row per eligible ticket).
  - These equal Zac's SQL ticket by ticket; the largest gap difference is 5 × 10⁻¹⁰ days (checked in the run, not
    stored).
  - Each row carries the index and next ticket's groups and Categories, the class, direction flags and the
    random-timing probability.
- **Matrices** (`rp_matrix.csv`). Group and Category level, at 7 and 30 days, with row shares and the matrix lift.
  - Network → Network shows a matrix lift of 3.65.
  - Not categorised and the small groups have large lifts on small counts.
- **Same Category by gap** (`rp_same_by_gap.csv`): 6,980 same-machine pairs with a recorded Category, monitoring
  excluded, with account-bootstrap intervals.
- **Within-machine tests** (`followups_summary.json` → `shuffle`):
  - **The test used** (amendment 1 in docs/09 §12) is the label permutation: observed 323 same-Category pairs among 833
    pairs on 299 machines, against a null mean of 276.
  - **Non-overlapping pairs:** 199 of 525 against 193.
  - **The as-written shuffle is not used.** It paired tickets with themselves (null mean 383).
- **Null** (`rp_null.csv`):

  | Variant | Null % | Observed ÷ expected |
  |---|---|---|
  | Own windows, exact | 15.41 | 1.53 |
  | Own windows, simulated median | 15.28 | |
  | Calendar-weighted | 15.5 | 1.52 |
  | Listed machines only | 15.19 | 1.53 |
  | One common window | 14.84 | 1.59 |
  | high_ticket_machines helper (one common window, all tickets as denominator) | 14.18 | |

  docs/02 F2's 14.8% matches the one-common-window row.
- **Offenders** (`rp_by_model.csv`, `rp_by_type.csv`). Each row gives:
  - repeat %, with an interval;
  - share of all repeats;
  - random-timing %, observed ÷ expected with its interval, and SRR with interval, p and q, and SRR in each half;
  - repeats per 100 machine-months up to 2 Aug (listed machines);
  - the share of repeats on the top 5% of machines (40–67% of a model's repeats, 35–58% of a telemetry type's);
  - the same-Category share of the repeats where both tickets have a recorded Category and neither is a monitoring
    ticket (`same_category_share_recorded_pairs`), and its same-Category lift.
  - "No device match" and "Unknown" are rows of their own and are not tested. The pooled "Other" rows hold only models
    or types with under 100 eligible tickets.
- **Class mixes and matrices per model and type:** `rp_class_mix.csv` and `rp_model_matrices.csv` (cells under 5
  flagged). The class mix pools units with under 50 repeats, so its "Other" rows differ from the offenders'.
- **Repeat % by index type** (`rp_index_type.csv`):
  - Door 20.0%;
  - Mechanical 27.7%;
  - Monitoring 35.3%. Monitoring's observed ÷ expected is only 0.94: monitoring tickets sit on busy machines.

## 4. Limits
- **Age and model.** Age is separated from design only within models that have machines on both sides of 4 years.
  On the big 2.0 models, "4+" mostly means 4–6 years.
- **Age and install year.** In one year of data they move together, so a production problem and a failure peak at a
  given age look the same. Earlier ticket history would separate them.
- **Clustering.** The within-model permutation moves whole machines but not whole accounts. Within model × account
  the difference survives (p = 0.025), but no single group does.
- **"Fixed".** It cannot be shown without fix dates. A change in technicians' Category habits, or a retrofit to older
  machines, would look the same between halves.
- **Repeats are repeat contacts, not failed repairs.** Whether a revisit gets a new case number is for IPA to
  confirm (request 7). Pairs a day or less apart may include unmarked duplicates.
- **Telemetry types** are compared by ticket mix and repeats per ticket only. Zero-ticket machines have no type until
  `fleet_db_extract.py` runs on the database.
- **The look at Category shares by age while planning** (docs/09 §9) means Part A is not blind.

## 5. Questions for IPA
- **The fix list.** What was changed (design, part or firmware), when, and on which models or install dates. First:
  what changed in touchscreens between 2022–23 and 2024 production, and what is happening to Deposit Doors on the
  newest machines.
- **Earlier tickets.** A year or two of earlier ticket history, to tell a 2022–23 production problem from a failure
  peak at 2–4 years.
- **Revisits.** Whether a revisit gets a new case number, and whether two tickets within an hour can be one call.
- **Monitoring.** How "Monitoring – Daily/Poll" tickets are raised. They are the follow-up in 128 repeats.
- **The database extract** for telemetry-type rates on installed months.

## Figures (slide charts, `viz/figures/slides/`)
**Slide 4 follow-up.**

| Chart | Shows |
|---|---|
| sl_18 | Rates by request type, under 4 vs 4+ |
| sl_19 | Same-model share ratios by group |
| sl_20 | The same by Category |
| sl_21 | Where the extra tickets come from |
| sl_22 | Shares by model and telemetry type |
| sl_31 | Rates by install year: all tickets, Touchscreen, Deposit Door, Computer Board |
| sl_23 | The halves check |

**Slide 5 follow-up.**

| Chart | Shows |
|---|---|
| sl_24 | 7-day pairing matrix |
| sl_25 | 30-day pairing matrix |
| sl_26 | Same Category by gap |
| sl_27 | Pairing classes by gap |
| sl_28 | Offenders by model and by telemetry type |
| sl_29 | Pairing classes per model and per telemetry type |
| sl_30 | Pairing matrices for the four models with the most repeats |

Every chart prints its definitions on the image. `viz/slides/run_all.py` runs each chart's number checks and checks
that every definition from `viz/slides/followup_terms.py` is printed in full.

## Privacy
- **Outputs:** T#####, S#####, Customer NNN, model, Category, group and telemetry-type labels, and aggregates only.
- **The scan:** `followups.py` scans every table and the summary for real serials, accounts, case numbers,
  addresses, zips and phones, built from the input files. No hit.
- **Raw files:** the workbooks stay in `data/`, which is gitignored.
