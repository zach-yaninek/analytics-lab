# Follow-ups protocol: request types by machine age, and repeat-contact pairings

*29 October 2026. Status: **frozen before results**; amended after the first run (§12).*

**Scope and rules**
- This document fixes the populations, definitions, estimators, tests and thresholds for two questions IPA raised at
  the meeting on slides 4 and 5 of the update deck. They are answered by `verification/followups.py`.
- No Part A or Part B result in §4–§5 had been computed when this was written. §9 lists every look at the data so far.
- Changes after results are seen go in §12 as dated amendments, and the original text is kept.
- **Inputs:**
  - the case export (`data/raw/IPA_CaseHistory_Aug 2025-Aug2026.xlsx`). Its SHA-256 is `f060f581…646f`, the file
    every committed output was built from (`audit_case_workbook.csv`);
  - IPA's installed-base list of 19 October (`data/raw/IPA_Active_Equipment_list_2026-10-19.xlsx`, SHA-256
    `244b3a1d…713b`);
  - the committed ticket-to-device map (`verification/outputs/fu/`).
- **Inputs reproduce.** On 29 October every committed output of `reproduce_sql.py`, `reproduce_cleanroom.py`,
  `audit_case_logic.py`, `01_excel_reproducibility.py`, `flags.py`, `high_ticket_machines.py` and
  `fleet_exposure.py` reproduced byte for byte from these two files. The only difference was a column recording
  that Zac's notebook was not present.

## Bottom line
1. **Part A (slide 4): request types.** Do the *types* of request on machines under 4 years old (the first three bars
   of the age chart) differ from those on machines 4 years or older?
   - The primary comparison is **within model**. Six models have machines on both sides of 4 years, and they hold most
     of the under-4 tickets. Elsewhere, age and model design cannot be told apart.
   - The test permutes the under-4 / 4+ label among machines of the same model.
   - Per-type results are tested only if the global test passes, with Benjamini–Hochberg control at each level.
2. **Part A: was it fixed?** A fixed rule picks the three Categories that contribute most to the under-4 excess within
   model. Their excess in the first half of the period is compared with the second. The data cannot show a fix without
   IPA's dates of design or firmware changes (§10). This only describes whether the gap narrowed.
3. **Part B (slide 5): repeat pairings.** Uses Zac's repeat definition, unchanged: 6,665 eligible index tickets and
   1,574 repeats within 30 days, of which 631 are within 7 days.
   - The pairing distribution: index type → the next ticket's type.
   - Whether a quick follow-up is the same problem more often than the machine's usual mix of tickets would give.
   - Which models and telemetry types repeat more than the timing of their tickets would give by chance.
4. **Telemetry type is mostly the model under another name** (§3.6). It is reported beside model wherever it splits
   one. Rates on installed months by telemetry type need the telemetry database (§10).

## 1. The questions (as relayed from the meeting)
- **Slide 4.** IPA would like to know whether the types of service request differ between the first three age bars
  (<1, 1–2 and 2–4 years) and the others. They hope the types differ, which would suggest the extra tickets come from
  problems they have since fixed. They asked for ticket rates by machine and telemetry type, charts, and significance
  tests.
- **Slide 5.** IPA were surprised by the repeat-contact figures. They asked for:
  - the distribution of ticket pairings in 30-day and 7-day follow-ups;
  - whether particular machine or telemetry types are the most common offenders;
  - pairing distributions per machine and telemetry type.

## 2. Populations
| | Part A | Part B |
|---|---|---|
| Tickets | 6,750 unplanned tickets on listed machines, 1 Aug 2025 – 31 Aug 2026 (slide 4's population) | Zac's 7,186 unplanned tickets, including 433 on serials not on IPA's list |
| Machines | 8,946 listed machines with exposure; third-party-plan (Vogeltronix) machines excluded | 3,685 machines with an unplanned ticket |
| Unit of analysis | ticket, in machine and account clusters | eligible index ticket (6,665), in machine and account clusters |

Each chart states which population it uses.

## 3. Definitions
1. **Unplanned ticket.** Every ticket except planned work (Preventative Maintenance or Installation trouble codes,
   and Install Cases), cancelled requests and duplicate cases. No Trouble Found tickets stay in.
2. **Installed machine-month and age.** These are `fleet_exposure.machine_frame`'s:
   - exposure runs from install (or the first ticket, if earlier; no earlier than 1 Aug 2025) to 31 Aug 2026;
   - age is the years from install to the midpoint of that exposure.
   - **Under 4** = age bands <1, 1–2 and 2–4; **4+** = 4–6, 6–8, 8–10 and 10+.

   | | Tickets | Machines | Machine-months | Per 100 |
   |---|---|---|---|---|
   | Under 4 | 3,629 | 3,987 | 45,103.38 | 8.05 |
   | 4+ | 3,121 | 4,959 | 64,517.91 | 4.84 |
3. **Request type.** Two levels.
   - **Group:** frozen in `verification/reference/request_types_v0.csv` (45 Trouble Code × Category rows, SHA-256 of
     the sorted trouble_code, category and group columns `88b71f3c…5080`).

     | Group | What it holds | Unplanned tickets |
     |---|---|---|
     | Door | Electro/Mechanical: Deposit, Main, User, Service Door | 2,280 |
     | Mechanical | Electro/Mechanical: SAM, Curtain, Packer, Counterweight System, Drawers | 1,453 |
     | Electronics | Trouble Code Electronics, any Category | 1,683 |
     | Network | Trouble Code Network | 483 |
     | Software | Trouble Code Software | 91 |
     | Operator error | Trouble Code Operator Error | 158 |
     | Other | Miscellaneous: Power, Parts Order, Physical Damage, Device Not Found; Canopy | 154 |
     | No Trouble Found | Category No Trouble Found | 577 |
     | Not categorised | No Category, under Electro/Mechanical, Miscellaneous or Repair/Investigate, or no Trouble Code | 307 |
     | Monitoring | Any ticket with the "Monitoring – Daily/Poll" template (`flags.monitoring_template`); this overrides the group | (moves from the rows above) |

   - **Category:** the recorded Category, with "Not categorised" for a blank Category and "Monitoring" as above.
   - **Combinations not in the file.** A Trouble Code that fixes the group (Electronics, Network, Software, Operator
     Error) gives that group. Otherwise a blank Category gives Not categorised, and anything else gives Other. On the
     real export the count of such tickets is 0, and that count is pinned.
4. **Repeat contact** (Zac's definition, `audit_case_logic.REPEAT_VIEW_SQL`, unchanged).
   - Unplanned tickets are ordered per machine by opening time, then case number. Each ticket's **next ticket** is the
     following one.
   - An index ticket is **eligible** if opened before 2 Aug 2026, so it has a full 30-day window.
   - It **repeats** if its next ticket opens 0 to 30 days later. A **7-day follow-up** is a repeat 0 to 7 days later,
     and the denominator stays the same 6,665.
   - **Same Category** means both Categories are recorded and equal.
   - A repeat contact is not necessarily a failed repair.
5. **Pairing.** An index ticket and its next ticket, for repeats only.
   - **Pairing classes,** the first that applies:
     1. Monitoring involved (either ticket);
     2. No Trouble Found involved (either);
     3. Category blank (either);
     4. Same Category;
     5. Same group, other Category;
     6. Different group.
   - Monitoring and No Trouble Found are also split by direction: index, follow-up or both.
6. **Telemetry type.**
   - **Source:** the clearView `machine_type` (normalised by `association.norm_type`) of the device matched to the
     machine's tickets. The committed ticket-to-device map (`fu_ticket_last10.csv`, guard-0 rows, then
     `fu_devices.csv`) covers 5,921 of the 7,186 unplanned tickets, on 2,993 machines.
   - **Machine level:** a machine takes its type when every matched ticket points to devices of one type. Otherwise
     it is "Several types", and with no match it is "No device match".
   - **It mostly names the model.** On the committed links:
     - scrubex2.0-2, -3, -4 and -5 are LVD-Remote-2.0, LVRR-WP-2.0, MV-2.0 and SV-48-2.0;
     - scrubex-2 is LVD-Remote; scrubex-4 is MV; mlc-1 is LC-30 and MC-30;
     - sbsx-51 is scrubBank 480; sd2.0-49 is alEx SD 2.0; sd-49 is SD-64.
   - **Where type adds to model:**
     - alex2.0-1 and alex2.0-3 each span four alEx models;
     - LVRR-WP splits into scrubex-3 (almost all 4+) and scrubex-7;
     - scrubex-1 covers several legacy models.

## 4. Part A: request types on machines under 4 vs 4+ years
**Notation.** For model s and type k:
- a_sk and b_sk are under-4 and 4+ tickets;
- n1_s and n0_s are the totals over the analysis family; N_s = n1_s + n0_s; m_sk = a_sk + b_sk;
- M1_s and M0_s are machine-months.

**Analysis family:**
- **Primary:** the 9 groups other than Not categorised: Door, Mechanical, Electronics, Network, Software, Operator
  error, Other, No Trouble Found and Monitoring.
- **Category level:** the Categories within the first 7 groups.

**Support.** Models with at least 100 installed machine-months in each age group. The support's share of under-4
and 4+ tickets is reported, and tickets outside it are shown separately.

**Estimable.** A type is estimable when, on the support, it has at least 20 tickets in each age group, from at least
10 accounts in each. Other types are reported as counts only, marked "not estimable", and are not tested.

### Analyses
- **A1. Rates by type (descriptive, not adjusted for model).**
  - The rate per 100 installed machine-months by type and age group, from `fleet_exposure.group_rates` with that
    type's count as tickets.
  - The crude rate ratio and crude share ratio (a_k/n1)/(b_k/n0), with bootstrap intervals.
- **A2. Same-model mix (primary).**
  - Mantel–Haenszel share ratio: SR_k = Σ_s a_sk·n0_s/N_s ÷ Σ_s b_sk·n1_s/N_s over support models. 1 = the same
    share of tickets within model.
  - Mantel–Haenszel rate ratio: RR_k = Σ_s a_sk·M0_s/M_s ÷ Σ_s b_sk·M1_s/M_s.
  - Cross-check: `fleet_exposure.ipf` with model and age-group factors, per type.
- **A3. Tests.**
  - **Global statistic:** X = Σ_k D_k²·(1/E1_k + 1/E0_k), where:
    - D_k = Σ_s (a_sk − E1_sk);
    - E1_sk = n1_s·m_sk/N_s and E0_sk = n0_s·m_sk/N_s;
    - E1_k and E0_k are their sums over s.
  - **Per-type statistic:** z_k = D_k/√V_k, with V_k = Σ_s n1_s·n0_s·m_sk·(N_s − m_sk)/(N_s²·(N_s − 1)) (Cochran–
    Mantel–Haenszel).
  - **Primary permutation:** within each support model, the under-4/4+ label is permuted among the model's machines
    with at least one ticket in the family. This keeps each machine's tickets together and each model's number of
    under-4 ticketed machines fixed. 2,000 permutations.
  - **p-values:** p = (1 + #{X* ≥ X})/2,001 for the global test, and the same with |z_k| per type
    (`association.perm_p`).
  - **Gate:**
    1. The global p < 0.05.
    2. The estimable groups' p-values, BH q < 0.05.
    3. Within each group that passes, its estimable Categories' p-values, BH within the group, q < 0.05.

    Nothing below a failed step is called significant. Every estimate is still shown, with its interval.
  - **Descriptive only:** the unstratified chi-square on the 2 × 9 table, which mixes models.
- **A4. Where the extra tickets come from.**
  - Extra tickets of type k on under-4 machines, relative to 4+ rates: X_k = T_y,k − M_y·R_o,k. This splits exactly
    into three parts:
    - **Within-model age part:** support under-4 tickets minus what their months would give at the same model's 4+
      rate, T^sup_y,k − Σ_s M1_s·R_o,s,k;
    - **Model-mix part:** Σ_s M1_s·R_o,s,k − M^sup_y·R_o,k;
    - **Models with no 4+ support:** T^out_y,k − M^out_y·R_o,k.
  - Reported in tickets and per 100 under-4 machine-months, with bootstrap intervals.
- **A5. By machine and telemetry type.**
  - A support table: machines, ticketed machines, accounts, months and tickets by model × age group.
  - **Models with at least 30 tickets in each age group:**
    - the under-4/4+ rate per 100 machine-months and their ratio (bootstrap);
    - the type shares in each age group;
    - a within-model mix test: X for that model alone, with labels permuted among its ticketed machines, 2,000
      permutations, BH over models.
  - **Telemetry types with at least 30 tickets in each age group:** the same, using tickets only, with permutation
    within type × model.
  - Rates by telemetry type on installed months are not computed, because zero-ticket machines have no type (§10).
- **A6. Was it fixed?**
  - **Rule:** the three estimable Categories in Door, Mechanical, Electronics, Network, Software, Operator error and
    Other with the largest positive within-model age part (A4, in tickets) over the full period.
  - **For each:**
    - the within-model age part per 100 under-4 machine-months, in the first half (1 Aug 2025 – 14 Feb 2026) and the
      second (15 Feb – 31 Aug 2026);
    - the difference, second minus first, with a bootstrap interval;
    - rate per 100 machine-months by install year within each support model (descriptive).
  - Age groups stay as defined over the full period, so each machine keeps its group in both halves. Older machines
    in the same half are the calendar control.
  - Choosing the Categories on the whole period does not by itself make the second half look lower: under no change,
    both halves share the selection equally in expectation.
  - **A narrowing gap fits a fix but is not proof of one.** It is also what a retrofit to older machines in the
    other direction, a change in technicians' Category habits, or chance could give. A production change (newer
    installs only) would show in the install-year rows rather than between the halves.
- **Sensitivities.** Each is a row of `ag_tests.csv`, giving the global p and the gate outcome.
  - S-A1: permutation within model × account (and the tickets these strata hold).
  - S-A2: cuts at 2 and at 6 years instead of 4.
  - S-A3: the type mix and rates across all 7 age bands (`ag_band_rates.csv`, descriptive).
  - S-A4: a Lexis split. Each machine-month and each ticket takes the machine's age group at that moment, so machines
    that cross 4 years during the period contribute to both groups. MH share ratios only; no permutation.
  - S-A5: excluding machines installed on or after 1 Aug 2025 (new installs, commissioning and warranty calling).
  - S-A6: without Monitoring and No Trouble Found.
  - S-A7: with Not categorised added to the family.
  - S-A8: tickets on serials not on IPA's list added to the 4+ group with their least possible exposure (first to last
    ticket, as `fx_unlisted_by_model.csv`). MH share ratios only.
  - S-A9: each half separately (global test in each).
  - S-A10: type mix within service status (a snapshot; descriptive).

## 5. Part B: repeat-contact pairings
- **B0. Pairs.** `REPEAT_VIEW_SQL` and `wilson` are copied verbatim from `audit_case_logic.py`, and `repeat_frame`
  and `repeat_summary` from `reproduce_cleanroom.py`. Both modules run their whole scripts when imported. Each copy
  is checked against its source by syntax-tree equality.
  - The pandas pairs equal the SQL ticket by ticket: repeat_30, same_category_30 and the gap.
  - **Pins:** 6,665 eligible, 3,495 machines, 1,574 repeats, 515 same Category, 631 within 7 days (221 same
    Category).
- **B1. Pairing matrices.**
  - Index type → follow-up type, at group and Category level, for 7- and 30-day repeats: counts and row shares.
  - **Lift (descriptive):** the observed count ÷ the count expected if, within model, follow-up types were unrelated
    to index types: E_ij = Σ_s R_si·C_sj/N_s, over repeats.
  - No chi-square on the matrix: consecutive pairs share tickets, and machines differ.
- **B2. Same problem, or the machine's usual mix?**
  - **Pairs:** all pairs of unplanned tickets on the same machine, both with a recorded Category and neither
    Monitoring.
  - **Same-Category share by gap:** 1 day or less, over 1 to 7, over 7 to 30, over 30 to 90, over 90 to 180, and over
    180 days. Weighted by pairs, and by machines (each machine's share, averaged over machines).
  - Pairs more than 90 days apart give each machine's usual mix.
  - **Paired contrast:** among machines with pairs in both, the mean of (share at 30 days or less) − (share at over
    90 days), with a bootstrap interval.
  - **Within-machine shuffle test:**
    - Machines: those with at least 2 thirty-day repeat pairs, with both Categories recorded and neither ticket
      Monitoring.
    - The follow-up Categories are shuffled among that machine's repeat pairs, 2,000 times.
    - One-sided p for the number of same-Category pairs: does a quick follow-up repeat its own index's Category beyond
      the machine's habits?
- **B3. Pairing classes** (§3.5): shares by gap of 1 day or less, over 1 to 7, and over 7 to 30 days, with
  directions.
  - Pairs 1 day or less apart are flagged as possible unlabelled duplicates.
  - Merging same-machine tickets under 24 hours is known to give 22.65% (`audit_case_population_sensitivity.csv`).
- **B4. Random-timing null.** The existing `high_ticket_machines.random_timing_followup` uses one common window and
  divides by all tickets, so it is not comparable to 23.6%. It is rebuilt here:
  - **Windows:** machine i's n_i unplanned tickets are placed uniformly at random in its own window.
    - Listed machines: `machine_frame`'s start (install or first ticket, no earlier than 1 Aug 2025) to 1 Sep 2026.
    - Unlisted machines: 1 Aug 2025 to 1 Sep 2026.
  - **Same rules:** the same eligibility rule (before 2 Aug 2026), the same repeat rule, and 1,000 simulations.
  - **Expected repeats:** machine i's null repeat probability per eligible ticket is p_i = E[repeats_i]/E[eligible_i].
    A group's expected repeats are E_m = Σ_{i∈m} eligible_i·p_i, from observed eligible counts.
  - **Measures:** observed ÷ expected (O/E), and the standardised repeat ratio SRR_m = (O_m/E_m)/(O/E)_fleet.
  - **Sensitivities:**
    - times drawn from the fleet's empirical ticket-time distribution within each window (calendar-weighted);
    - listed machines only.
  - Unit-tested against the exact (n−1)·(1−(1−d/L)ⁿ) for n uniform points on [0, L] with no cutoff.
  - **Slide 5.** Its speaker notes say random timing would give "about 14.8%" (docs/02 F2, no committed code). This
    re-derives that figure, and slide 5 and docs/02 are corrected if it differs.
- **B5. Offenders.** By model (the ticket's model, as in `repro_sql_repeat_by_model.csv`) and by telemetry type, for
  those with at least 100 eligible tickets; the rest are pooled as "Other". For each:
  - eligible tickets, repeats, repeat % with a bootstrap interval;
  - **volume:** share of all repeats;
  - **beyond volume:** null %, O/E, and SRR with a bootstrap interval;
  - p = 2·min(share of draws ≤ 1, share ≥ 1), with BH q;
  - **class:** "above" or "below" when the interval excludes 1 and q < 0.05;
  - SRR in each half (index tickets before / from 15 Feb 2026);
  - repeats per 100 machine-months up to 2 Aug 2026 (listed machines only);
  - the share of its repeats on its top 5% of machines;
  - same-Category share of repeats against its own baseline (B2's pairs over 90 days, for that model), as a lift.

  Also the repeat % by index type (group), with O/E.
- **B6. Pairing distributions per type.**
  - The class mix (B3) per model and per telemetry type with at least 50 repeats; the rest are pooled.
  - Full group-level matrices per model and per type, at 7 and 30 days, in `rp_model_matrices.csv`. Cells under 5 are
    flagged.
  - Descriptive: same-Category shares depend on how concentrated each model's Categories are (§9), so there is no test
    across models.

## 6. Statistical conventions
- **Intervals:** 95% percentile intervals from 2,000 bootstrap draws over accounts (`fleet_exposure.boot_weights`,
  seed 15072). Accounts are taken in sorted order over the population, so Part A's draws are slide 4's.
  - Undefined draws (a zero denominator) are left out and counted (`association.ci`).
  - Byar or Wilson intervals are used only as a floor for groups with fewer than 10 accounts (`group_rates`' rule).
- **Seeds:** permutations 15073, simulations 15074, within-machine shuffles 15075.
- **Monte Carlo standard errors** are reported with every permutation p.
- **Software:** numpy and pandas only.

## 7. Outputs and charts
- **Tables:** `verification/outputs/followups/`.

  | Part | Files |
  |---|---|
  | A | `ag_support`, `ag_type_rates`, `ag_type_adjusted`, `ag_tests`, `ag_decomposition`, `ag_by_model`, `ag_by_type`, `ag_band_rates`, `ag_halves` |
  | B | `rp_pairs` (one row per eligible ticket, pseudonymous), `rp_matrix`, `rp_same_by_gap`, `rp_classes`, `rp_index_type`, `rp_by_model`, `rp_by_type`, `rp_null`, `rp_model_matrices` |

  Plus `followups_summary.json`: pins, test results, check counts, and the exact definition strings the charts draw.
- **Slide charts:** `viz/slides/sl_18…sl_30`, in the deck's style. Every chart prints the definitions of the terms it
  uses on the image, and `viz/slides/run_all.py` checks that.
- **Results:** `docs/10_followups_results.md`.

## 8. Checks
- **Pins.** These stop the run, before any new result, if any differs:

  | Pin | Value |
  |---|---|
  | `fx_summary.json` | 9,055 machines, 8,946 exposed, 1,065 accounts, 109,621.2895 months, 6,750 tickets |
  | `fx_age_rates.csv` | all 7 rows |
  | `fx_machine_flags.csv` | all 3,457 machines with tickets: model, age band, months, tickets, core tickets |
  | `fx_model_rates.csv` | all 34 rows |
  | Core tickets | 6,138 (3,284 under 4, 2,854 4+) |
  | Monitoring templates | 138 |
  | `repro_sql_repeat_summary.csv` | 6,665 / 3,495 / 1,574 / 515 / 0 |
  | `audit_case_repeat_gap_bins.csv` | 12/4/65/121/429/358/585; 631 within 7 days; 221 same Category within 7 days |
  | `repro_sql_repeat_by_model.csv` | all 31 rows |
  | `audit_case_repeat_composition.csv` | No Trouble Found on index 133, follow-up 151, either 260; follow-up Category blank 116 |
  | `repro_clean_issue_mix.csv` | all 38 rows |
  | Slide 5 | 22.0% without monitoring templates |
  | Ticket-to-device map | 5,921 tickets on 2,993 machines |
  | Request types | the reference's hash, and 0 unmapped combinations |
- **Fixture test.** `verification/tests/run_fixture_tests.py` (`run_followups`) runs the script on the synthetic
  `extended` fixture and checks it against:
  - an independent pandas oracle;
  - the copied SQL;
  - a calibration check (uniform planted times give O/E near 1);
  - a planted copy with known extra same-Category repeats, monitoring texts and a Touchscreen excess;
  - privacy, and byte-identical reruns.
- **Unit tests** (`verification/tests/test_followups_units.py`):
  - the 30-day, 7-day and 2 Aug edges;
  - Mantel–Haenszel on known tables;
  - the exact decomposition;
  - the simulator against the formula;
  - the shuffle keeping each machine's Categories;
  - the copied code against its sources.
- **Independent re-derivation.** Agents that have not seen `followups.py` recompute the headline numbers from this
  document, and differences are arbitrated before the results are written up.

## 9. Looks at the data so far
Recorded so readers can judge what this protocol could have been tuned to.
1. **Everything already committed:**
   - slides 4 and 5;
   - the age-band rates;
   - repeat counts and their composition;
   - repeat counts by model, and the issue mix by model (`repro_clean_model_issue_mix_top8_pct.csv`);
   - the top 5% of machines (175) holding 47.3% of repeats;
   - index tickets from August 2025 repeating more (25.4% vs 23.5%).
2. **A read-only preview while planning (28 October)** of Category shares on under-4 vs 4+ machines. It used the
   committed device-matched tickets, about 84% of Part A's population, not this protocol's definitions.
   - **Under-4 machines' tickets were more often:**
     - Deposit Door (21.9% vs 10.9%);
     - Touchscreen (10.7% vs 4.7%);
     - Curtain (8.8% vs 5.5%).
   - **4+ machines' tickets were more often:**
     - Main Door (10.8% vs 5.5%);
     - Computer Board (11.8% vs 7.0%);
     - User Door (9.1% vs 5.1%);
     - Counterweight (3.2% vs 0.6%).
   - **Within model:**
     - LVRR-WP-2.0: Deposit Door 57.4% vs 39.3%, Packer 4.8% vs 13.8%;
     - MV-2.0: Touchscreen 17.8% vs 4.9%;
     - LVD-Remote-2.0: Touchscreen 17.2% vs 10.6%, SAM 18.1% vs 24.3%.
   - **So Part A is not blind.** The global within-model test and the A6 rule were fixed after these shares were seen.
     Per-type p-values for the Categories named above are best read as descriptive.
3. **Ticket counts by telemetry type × model and × age group** on the committed device links (§3.6), with no
   Category.
4. **A design review's facts from committed outputs:**
   - the chance two tickets of a model share a Category: 0.33 for LVRR-WP-2.0 and 0.30 for alEx LC-D, against 0.12
     for LVD-Remote-2.0 and MV-2.0;
   - 59% of monitoring tickets come within 7 days of another ticket;
   - 90% of 4+ tickets on the three big 2.0 models are in the 4–6 band.
5. **The Trouble Code × Category counts over all 7,186 unplanned tickets**, with no age or repeat split, used to
   build `request_types_v0.csv`.

No Part B pairing matrix, same-by-gap share, class mix, random-timing figure or SRR has been computed.

## 10. What this cannot show
- **That a problem was fixed.** That needs IPA's dates of design, part or firmware changes, and which models or
  installs they reached.
- **Telemetry-type rates on installed months.** Zero-ticket machines have no telemetry type until
  `fleet_db_extract.py` runs on the database. Until then, telemetry types are compared by ticket mix and repeats per
  ticket.
- **Whether a repeat is a failed repair.** A revisit may or may not get a new case number (IPA request 7).
- **Age effects on models that are all young or all old.** These are separated from design only within the six
  models that span both.

## 11. Questions for IPA
- **The fix list:** what was changed (design, part, firmware), when, and on which models or install dates.
- **Revisits:** whether a technician's revisit gets a new case number.
- **Monitoring tickets:** how "Monitoring – Daily/Poll" tickets are raised (request 5).
- **The database extract** for telemetry-type rates on installed months.

## 12. Amendments
**Amended 29 October 2026, after the first full run.** Three independent clean-room builds (§8), written from this
document alone, were compared with `followups.py`. They matched it:
- Part A's statistic, gate, decomposition and halves;
- Part B's pairs, classes, directions and same-by-gap shares;
- the null rates, within Monte Carlo error.

The first run and the comparison raised two problems, one factual error and several readings the text left open.
Where this section and an earlier one differ, this section governs.

1. **B2 within-machine test (a problem in the design).**
   - **The flaw.** As written, the shuffle pairs a ticket with itself whenever that ticket is one pair's follow-up
     and the next pair's index. Such a pairing always matches, so the null is inflated: null mean 383 against 323
     observed, p = 1.0. 412 of the 833 pairs are chained this way. The main analysis and one clean-room build found
     this independently.
   - **Replacement.** Each machine's Category labels are permuted among its own tickets (recorded Category, not
     Monitoring), with opening times fixed, so the repeat pairs stay the same pairs of tickets. 2,000 permutations,
     one-sided p.
   - **Sensitivity.** Only non-overlapping pairs: in time order, a pair is kept when neither ticket is already in a
     kept pair, and follow-up Categories are shuffled among the kept pairs.
   - The as-written result is reported for the record.
2. **B4 computed exactly.**
   - **Why a closed form exists.** The eligibility cutoff falls exactly 30 days before the window end. So under the
     uniform null, every eligible ticket has its whole window inside the machine's window, and its repeat
     probability is exactly 1 − (1 − d/L_i)^(n_i − 1). This is the ratio of expectations the simulation estimates.
   - **How it is used.** The uniform nulls use the exact value. The 1,000 simulations are kept as a check (the fleet
     agrees within 1%) and give the null's spread. The calendar-weighted null has no closed form and uses the
     simulation.
   - **A full-period variant** is added: every machine's tickets spread over 1 Aug 2025 – 31 Aug 2026. It reproduces
     docs/02 F2's 14.8%.
3. **Erratum (Bottom line and §10).** "Six models have machines on both sides of 4 years" is wrong.
   - 19 models have machines on both sides.
   - The support rule (at least 100 machine-months in each age group) gives 15 models. They hold 98.6% of under-4 and
     68.5% of 4+ family tickets.
   - Six models have at least 30 tickets in each age group, which is A5's threshold.
4. **Readings where the text allows more than one.** These were fixed before the results were written up. The
   clean-room builds' alternatives change no conclusion.
   - **Category level:** shares use the primary family's totals, the same denominators as the groups, and the
     Category p-values come from the group-level permutations. Using totals over the seven component groups instead
     moves estimable Categories' share ratios by at most 0.045.
   - **A1 and A5:** shares use all unplanned tickets as the denominator, so the ten groups sum to 100%.
   - **A4:** per-100 figures divide by all under-4 machine-months, which keeps the parts additive.
   - **A6:** per-100 figures divide by the support's under-4 machine-months in each half, giving a rate gap on the
     models compared.
   - **A4's third part** is "models outside the support": models short of 100 months in either age group, not only
     those with no 4+ machines.
   - **B2:** No Trouble Found counts as a recorded Category, and every same-machine pair is used, with no 2 Aug cutoff.
   - **B3:** No Trouble Found directions are counted within its class, after Monitoring.
   - **Telemetry type:**
     - "No device match", and "Unknown" (a blank device type), are shown as rows but are not telemetry types and are
       not tested.
     - "Several types" never occurs, since every serial matches one device.
5. **Definitions.** The definition strings the charts draw live in `viz/slides/followup_terms.py`, filled with numbers
   from `followups_summary.json`, not in the summary itself.
6. **Corrections after the independent review (29 October 2026).** Two output rows did not follow this text, and one
   column name was ambiguous. No test, q-value or conclusion changes.
   - **"Unknown"** (57 eligible tickets, 12 repeats) had been pooled into "Other telemetry types" in B5 and B6. As
     item 4 says, it is now a row of its own and is not tested.
   - **The pooled "Other models" row** reported 0 listed machine-months. It now holds every listed model without a
     row of its own: 15,240 machine-months. A check confirms the model rows hold every listed machine-month.
   - **`same_category_share_of_repeats`** is renamed `same_category_share_recorded_pairs`. It is the share among the
     repeats where both tickets have a recorded Category and neither is a monitoring ticket, not among all repeats.

## Privacy
- **Outputs.** Pseudonyms only: S#####, M#####, T#####, Customer NNN. Model, Category and type labels.
- **Privacy scan.** `followups.py` runs `fleet_exposure.text_leaks` over every output table and the summary, against
  real serials, accounts and case numbers built from the given input files.
- **Raw files.** The workbooks and the text of tickets never leave `data/`, which is gitignored.
