# analytics-lab
Code repository for my Analytics Lab project (Roper IPA × MIT Analytics Lab).

## Review of the IPA service-ticket SQL analysis (Oct 2026)

| Document | What it covers |
|---|---|
| `docs/executive_summary.md` | One-page summary for the IPA meeting (pseudonymised; `viz/deliverables/build_memo.py` builds the real-name Word memo for IPA locally, never committed) |
| `docs/01_what_zac_did.md` | Section-by-section account of Zac's notebook: pipeline, methods, results, caveats |
| `docs/02_verification_report.md` | Independent verification: reproduction results, findings on methods, pending items |
| `docs/03_customer_fleet_ownership.md` | Can tickets or telemetry be attributed to customers' fleets? |
| `docs/04_timestamp_semantics.md` | Case and telemetry clocks, field-update timing, implications for the classifier |
| `docs/05_high_ticket_machines.md` | Machines with an outsized share of tickets: workload and exposure-adjusted views, figures |
| `docs/06_fleet_exposure.md` | Ticket rates adjusted for fleet exposure (IPA's installed-base list): models, ages, customers, consistent outliers |
| `docs/07_association_protocol.md` | Pre-specified protocol for the association study (ticket Category ↔ codes before the ticket), frozen before any result |
| `docs/08_association_results.md` | Results of the association study: specificity (H2a), enrichment, recency, sensitivities |
| `docs/09_followups_protocol.md` | Protocol for IPA's follow-ups on slides 4 and 5 (request types by machine age; repeat pairings), frozen before results |
| `docs/10_followups_results.md` | Results of the follow-ups: request types on machines under 4 vs 4+ years; what repeat contacts are; offenders |
| `TODOS.md` | Plan for the association analysis (ticket fields ↔ last 10 telemetry codes before the ticket) |

### Layout
- `verification/common.py`: rebuilds Zac's `cases` table exactly, with the same cleaning and deterministic
  pseudonyms.
- `verification/*.py`: reproductions (`reproduce_sql.py`, `reproduce_cleanroom.py`, `01_excel_reproducibility.py`),
  audits (`audit_case_logic.py`, `audit_telemetry_consistency.py`), `customer_fleet_audit.py`,
  `timestamp_semantics.py`, `flags.py` (canonical monitoring-ticket and telemetry-mention flags) and
  `verify_with_db.py` (everything that needs the telemetry DB), `db_followup.py` (last-10 codes per ticket on the
  corrected clock; also needs the DB), and `high_ticket_machines.py` (local only, reads the committed
  `fu_*`/`db_*` outputs), `fleet_exposure.py` (rates on IPA's installed-base list; local only) and
  `fleet_db_extract.py` (joins telemetry devices to the installed-base list; needs the DB), `association.py` (the
  association study of docs/07 and docs/08; committed outputs only) with its crosswalk in `verification/reference/`,
  and `flags.py --write` (per-ticket text flags for the association sensitivities; needs the case export), and
  `followups.py` (IPA's follow-ups of docs/09 and docs/10; local only, with its request-type groups in
  `verification/reference/request_types_v0.csv`).
- `viz/`: every chart, in one shared style (see `viz/README.md`).
  - `viz/style/`: the reusable style: `ipa.mplstyle` (a plain matplotlib style sheet) and `ipa_style.py` (palette,
    title band, footer for definitions and notes, save).
  - `viz/high_ticket/`: one script per high-ticket-machine chart (`htm_01_*.py` … `htm_08_*.py`).
  - `viz/fleet_exposure/`: one script per fleet-exposure chart (`fx_01_*.py` … `fx_12_*.py`).
  - `viz/association/`: one script per association chart (`as_01_*.py` … `as_03_*.py`).
  - `viz/zac_notebook/`: Zac's 10 notebook figures rebuilt in the same style (`zac_01_*.py` … `zac_10_*.py`).
  - `viz/slides/`: card-sized versions for the IPA meeting deck (`sl_01_*.py` … `sl_31_*.py`); `sl_18` to `sl_31` are
    IPA's follow-ups (docs/10) and print their definitions on the image. The two customer charts (`sl_06`, `sl_07`)
    also draw a real-name variant into `deliverables/slides/`.
  - `viz/deliverables/`: builds the real-name deliverables into the gitignored `deliverables/`: `build_memo.py` (the
    Word memo from `docs/executive_summary.md`, laid out by `memo_docx.js`), `build_deck_pdf.py` (a PDF of the deck
    with real names, printed by `deck_pdf.js`) and `names.py` (the private name table, and same-length placeholder
    names for checking layouts without looking at real ones). The code is committed; its outputs never are.
    `followups_pptx.js` builds the follow-up PowerPoint (slides 4.1-5.4, text in `followups_pptx.json`; no customer
    names) into the same folder; `build_followups_pptx.py` builds its real-name version, which adds the update deck's
    customer slides 6 and 7 with real names.
  - `viz/figures/`: the rendered PNGs.
- `verification/tests/`: synthetic-fixture self-test for `verify_with_db.py` and the other scripts that read raw
  files, and `test_followups_units.py` (fast unit tests for `followups.py`).
- `verification/outputs/`: pseudonymous aggregate outputs.
- `data/` and `deliverables/` are gitignored. Raw files, real names and the IPA-facing memo never leave the local
  machine.

### Running
1. Put the inputs in `data/raw/`:
   - `IPA_CaseHistory_Aug 2025-Aug2026.xlsx`
   - optionally `IPA_Service_Ticket_SQL_Analysis.ipynb`
   - `IPA_Active_Equipment_list_2026-10-19.xlsx` (IPA's installed-base list, for `fleet_exposure.py`)
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
python3 -I verification/fleet_exposure.py         # ~30 s, no DB; installed-base rates and consistent outliers
python3 -I verification/fleet_db_extract.py --db data/raw/ipa_transaction_events_202508_202608.db  # optional
python3 -I verification/association.py            # ~2 min, no raw data, no DB; association study (docs/07, docs/08)
python3 -I verification/followups.py              # ~15 s, no DB; IPA follow-ups (docs/09, docs/10)
python3 -I verification/tests/test_followups_units.py  # ~20 s; unit tests for followups.py
python3 -I verification/flags.py --write          # local only: per-ticket text flags for association S2/S10
python3 -I viz/run_all.py                                 # redraw the page charts and run their checks
python3 -I viz/slides/run_all.py                          # redraw the slide charts (incl. follow-ups sl_18-sl_31)
export NODE_PATH="$(npm root -g)"                         # the Node packages of the four builders below
python3 -I viz/deliverables/build_memo.py                 # local only: deliverables/IPA_Executive_Summary.docx
python3 -I viz/deliverables/build_deck_pdf.py --deck DECK_DIR --assets ASSET_MAP.json  # local only: the deck PDF
node viz/deliverables/followups_pptx.js --assets DECK_IMAGES              # the follow-up PowerPoint
python3 -I viz/deliverables/build_followups_pptx.py --assets DECK_IMAGES  # local only: its real-name version
python3 -I viz/high_ticket/htm_03_observed_vs_expected.py # redraw one chart (any viz/*/htm_NN_*.py, zac_NN_*.py or fx_NN_*.py)
```

Requires Python 3.12+ with pandas, numpy and openpyxl; matplotlib for the figures (skipped with a message if it is
missing).

The real-name deliverables also need `data/private/fx_private_customer_names.csv` (written by `fleet_exposure.py`),
the real-name charts (drawn by `viz/run_all.py` and `viz/slides/run_all.py`), pandoc 3, and Node with the `docx`,
`playwright` and `pptxgenjs` packages and Playwright's Chromium
(`npm install -g docx playwright pptxgenjs && npx playwright install chromium`), found through `NODE_PATH` as above.
The deck PDF reads the deck's own files (`deck.json` and `slides/*.html`, from the Slides artifact) and a JSON map
from each of its image asset ids to a local copy of that image, and requires every customer chart of the deck (each
slide chart whose script declares `REAL_PNG`) to be swapped for its real-name file. The builders print counts and
pseudonyms only, never a name; `--twin OUT_DIR` builds a copy with placeholder names (and placeholder customer
charts) for checking the layout without seeing a real name.
