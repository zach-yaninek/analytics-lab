#!/usr/bin/env python3
"""Regenerate trends/ticket_trends.ipynb from config.DEFAULTS and config.COMMENTS (developer tool).

The notebook's parameters cell must hold exactly DEFAULTS (test_units checks it), so whenever a parameter is added
or a default changes, run:  python3 -I trends/tests/make_notebook.py
"""
import sys
from pathlib import Path

TRENDS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRENDS))

import nbformat  # noqa: E402

from ipa_trends import config  # noqa: E402

GROUPS = [('Cadence', ['RERUN_FREQUENCY', 'YEAR_START_MONTH', 'FISCAL_YEAR_NAMED_BY', 'ANCHOR_DATE', 'PERIOD_EDGES',
                       'LATEST_PERIOD', 'BASELINE_MONTHS', 'HISTORY_MONTHS', 'LABEL_LAG_DAYS', 'MAX_OPEN_SHARE',
                       'MAX_BLANK_CATEGORY_SHARE', 'MAX_UNMAPPED_SHARE']),
          ('Inputs (relative paths are read from the trends folder)',
           ['CASE_EXPORTS', 'CASE_SHEET', 'EQUIPMENT_LISTS', 'EQUIPMENT_SHEET', 'EQUIPMENT_LIST_DATES', 'EXTRACTED_AT',
            'DATA_START', 'DATA_END', 'COLUMN_ALIASES', 'CATEGORY_ALIASES', 'REQUEST_TYPES_LOCAL', 'UNMAPPED_POLICY',
            'CASE_CLOCK_TZ', 'DATE_FORMAT', 'BASE_DIR', 'OUTPUT_DIR']),
          ('Breakdowns', ['STRATIFY_BY', 'CATEGORY_DIMS', 'INSTALL_COHORT_WIDTH', 'INSTALL_COHORT_START',
                          'INSTALL_COHORT_EDGES', 'MODEL_FILTER', 'POOL_SMALL_STRATA', 'MIN_TYPE_MONTHS',
                          'MIN_CELL_MONTHS', 'THIRD_PARTY_PLANS', 'MISSING_INSTALL_DATE']),
          ('Call-outs (conservative screening flags)',
           ['Q_CUT', 'WATCH_Q', 'MIN_CHANGE', 'MIN_CONTRAST', 'CONTRAST_MONTHS', 'MIN_EXPECTED',
            'MIN_BASELINE_TICKETS', 'MIN_ACCOUNTS', 'TAU2_FLOOR', 'N_BOOT', 'SEED', 'COHORT_MAP_ISSUES']),
          ('Outputs', ['MAKE_CHARTS', 'MAKE_REPORT', 'REPORT_TITLE', 'PRIVACY_ALLOW'])]

INTRO = """# IPA service-ticket trends

Reruns the service-ticket analysis on fresh exports: **unplanned tickets per 100 installed machine-months**, by
issue (request group and Category), for every reporting period, broken down by **install cohort** (machines
installed in different date ranges), product family and model. Each run compares the latest complete period with
the previous 12 months and calls out changes conservatively, and lists install cohorts that stand out.

**Each cycle**
1. About two weeks after the period ends, save the new case report and that month's equipment list into
   `trends/data/raw/` (keep the earlier equipment lists there too).
2. Check the parameters below. Normally nothing changes; to switch cadence, edit only `RERUN_FREQUENCY`
   (`'quarterly'` or `'monthly'`; any whole number of months works). Parameter names are written in capitals.
3. **Restart & Run All** (Kernel menu; in VS Code, Restart, then Run All). A plain Run All keeps the names left
   from earlier runs, so a name you have corrected would still stop the run. The results appear below and in
   `trends/data/output/latest/`: `report.pdf` to attach, `email_summary.txt` to paste, and CSV tables for the
   dashboard.

If something is wrong with an input, the run stops before computing anything and says how to fix it. See
`trends/README.md` for the full runbook and `trends/METHOD.md` for the definitions and statistics."""

OUTRO = """## Next steps

- Read the data-quality notes above. A period marked *provisional* is reported in the next run.
- Send `latest/report.pdf` with the text of `latest/email_summary.txt` to the distribution list, once
  "Ready to distribute" says yes. After a back-run (`LATEST_PERIOD` set), `latest/` is unchanged: send the files
  from the run folder named above instead.
- The Product Insights Dashboard reads `latest/rates_final.csv` (and the other tables; columns in `schema.json`).
- Flags are screening flags for follow-up, not proof of a problem."""

RUN = """import pathlib
import sys

_here = pathlib.Path.cwd()
for _p in (_here, _here / 'trends', _here.parent):
    if (_p / 'ipa_trends').is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from ipa_trends import config, notebook

params = config.collect(globals())   # every ALL-CAPS name above; a misspelt or lower-case name stops the run
result = notebook.run_and_show(params)"""


def parameters_source():
    names = [n for _, ns in GROUPS for n in ns]
    assert sorted(names) == sorted(config.DEFAULTS), set(config.DEFAULTS) ^ set(names)
    lines = ['# Parameters: edit here, or pass them with papermill (-p NAME value, or -f params.yaml).']
    for title, ns in GROUPS:
        lines.append(f'\n# ---- {title}')
        for n in ns:
            lines.append(f'{n} = {config.DEFAULTS[n]!r}  # {config.COMMENTS[n]}')
    return '\n'.join(lines)


def build():
    nb = nbformat.v4.new_notebook()
    nb.metadata['kernelspec'] = {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}
    nb.metadata['language_info'] = {'name': 'python'}
    params = nbformat.v4.new_code_cell(parameters_source())
    params.metadata['tags'] = ['parameters']
    nb.cells = [nbformat.v4.new_markdown_cell(INTRO), params, nbformat.v4.new_code_cell(RUN),
                nbformat.v4.new_markdown_cell(OUTRO)]
    for i, c in enumerate(nb.cells):
        c['id'] = f'cell-{i}'
    return nb


if __name__ == '__main__':
    out = TRENDS / 'ticket_trends.ipynb'
    nbformat.write(build(), str(out))
    print(f'wrote {out}')
