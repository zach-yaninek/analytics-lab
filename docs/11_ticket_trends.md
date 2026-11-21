# 11 · Recurring service-ticket trends for IPA (Nov 2026)

**What was asked.** The project lead proposed to IPA a notebook that, once a quarter, reruns the service-ticket
analysis: machine-month-normalised ticket trends for different issues, further stratified by machine type. IPA
agreed; its Product & Customer Service analytics team owns the analytics and delivery, alongside its executive
Product Insights Dashboard. The rerun frequency is a free parameter (quarterly or monthly in practice).

**Decisions (the lead, Nov 2026)**

| Question | Decision |
|---|---|
| Denominator | Installed machine-months from IPA's equipment list. This is the basis of Part A and the executive summary (6.16 per 100), and needs only the case export and the list. |
| Machine type | Install cohort first (how the 2022-23 Touchscreen peak surfaced), plus model and product family |
| Call-outs | Conservative screening flags |
| Sharing | The run writes a report, email text and tables; IPA's own tools send them |
| Environment | Portable Python and Jupyter; papermill or nbclient for headless runs |

**Where it lives.** `trends/` holds a self-contained package (`ipa_trends`), the notebook (`ticket_trends.ipynb`),
a command line (`ipa-trends`), tests and docs:

- `trends/README.md` is the runbook;
- `trends/METHOD.md` gives the definitions and statistics.

The definitions are verbatim copies of `verification/common.py`, `flags.py`, `followups.py`, `fleet_exposure.py`,
`high_ticket_machines.py` and `association.py`, guarded by `trends/tests/sync_definitions.py` and
`trends/tests/test_parity.py`.

**What is new compared with the analysis IPA saw**

- **Per-period rates.** Rates for every reporting period (no existing code computed rates per period × issue),
  generalising fleet_exposure's two-halves exposure rule to any period grid. Months add up exactly across periods.
- **An equipment-list ledger.** It counters the single snapshot's survivorship trend: unlisted tickets fall from
  11.1% in Aug 2025 to 1.0% in Aug 2026.
- **Time-trend call-outs.** The latest final period is compared with the previous 12 months, and install cohorts
  are compared with the rest of the fleet, with newer and older installs (a peak), and with machines of the same age
  in other cohorts (`trends/METHOD.md` §5 gives the rule).
- **Data-quality gates.** These cover late Category labels, open tickets, taxonomy changes, closed-only or
  incomplete exports, and the case clock.

**Reconciliation.** `ipa-trends reconcile` reproduces, on the original two files, the committed numbers in
`fx_summary.json`, `fx_age_rates.csv`, `fx_family_rates.csv`, `fx_model_rates.csv`, `ag_type_rates.csv`,
`ag_band_rates.csv`, the halves, the monthly counts and `ag_install_pooled.csv`. Intervals are compared for
`fx_age_rates.csv`, `fx_family_rates.csv`, `fx_model_rates.csv` and the under-4 and 4+ rates of `ag_type_rates.csv`.
`ag_band_rates.csv` and `ag_install_pooled.csv` are compared on counts, machine-months and rates:
`ag_install_pooled.csv`'s intervals were made with a different rule (association.ci: inverted-CDF percentiles, no
Byar widening) and are not reproduced. On VD's synthetic fixture the engine already matches
`fleet_exposure.machine_frame` machine by machine and `followups.py`'s tables value by value
(`trends/tests/test_parity.py`). The run on IPA's files is to be done by the lead.
