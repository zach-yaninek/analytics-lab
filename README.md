# analytics-lab
Code repository for my Analytics Lab project (Roper IPA × MIT Analytics Lab).

## Review of the IPA service-ticket SQL analysis (Oct 2026)

| Document | What it covers |
|---|---|
| `docs/executive_summary.md` | One-page summary for the IPA meeting (pseudonymised; the Word memo for IPA is generated locally, not committed) |
| `docs/01_what_zac_did.md` | Section-by-section account of Zac's notebook: pipeline, methods, results, caveats |
| `docs/02_verification_report.md` | Independent verification: reproduction results, findings on methods, pending items |
| `docs/03_customer_fleet_ownership.md` | Can tickets or telemetry be attributed to customers' fleets? |
| `docs/04_timestamp_semantics.md` | Case and telemetry clocks, field-update timing, implications for the classifier |
| `docs/05_high_ticket_machines.md` | Machines with an outsized share of tickets: workload and exposure-adjusted views, figures |
| `TODOS.md` | Plan for the association analysis (ticket fields ↔ last 10 telemetry codes before the ticket) |

### Layout
- `verification/common.py`: rebuilds Zac's `cases` table exactly, with the same cleaning and deterministic
  pseudonyms.
- `verification/*.py`: reproductions (`reproduce_sql.py`, `reproduce_cleanroom.py`, `01_excel_reproducibility.py`),
  audits (`audit_case_logic.py`, `audit_telemetry_consistency.py`), `customer_fleet_audit.py`,
  `timestamp_semantics.py`, `flags.py` (canonical monitoring-ticket and telemetry-mention flags) and
  `verify_with_db.py` (everything that needs the telemetry DB), `db_followup.py` (last-10 codes per ticket on the
  corrected clock; also needs the DB), and `high_ticket_machines.py` with `plot_high_ticket_machines.py` (local only,
  reads the committed `fu_*`/`db_*` outputs).
- `verification/tests/`: synthetic-fixture self-test for `verify_with_db.py`.
- `verification/outputs/`: pseudonymous aggregate outputs; `figures/` holds the charts.
- `data/` and `deliverables/` are gitignored. Raw files, real names and the IPA-facing memo never leave the local
  machine.

### Running
1. Put the inputs in `data/raw/`:
   - `IPA_CaseHistory_Aug 2025-Aug2026.xlsx`
   - optionally `IPA_Service_Ticket_SQL_Analysis.ipynb`
   - optionally the telemetry DB `ipa_transaction_events_202508_202608.db`
2. Run the scripts:

```bash
python3 -I verification/reproduce_sql.py           # Zac's SQL, verbatim, on the case export
python3 -I verification/reproduce_cleanroom.py     # independent pandas re-derivation
python3 -I verification/timestamp_semantics.py     # ~3 min
python3 -I verification/flags.py
python3 -I verification/tests/run_fixture_tests.py # self-test of the DB script (~70 s)
python3 -I verification/verify_with_db.py --db data/raw/ipa_transaction_events_202508_202608.db \
    --xlsx "data/raw/IPA_CaseHistory_Aug 2025-Aug2026.xlsx" --out verification/outputs/db --private data/private/db
python3 -I verification/high_ticket_machines.py   # ~20 s, no DB; ends by drawing the htm_* figures
```

Requires Python 3.12+ with pandas, numpy and openpyxl; matplotlib for the figures (skipped with a message if it is
missing).
