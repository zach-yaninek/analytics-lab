"""Data and definitions for Zac's notebook figures, rebuilt in the IPA style (viz/zac_notebook/zac_*.py).

Zac's notebook (IPA_Service_Ticket_SQL_Analysis.ipynb) draws 10 figures from SQL views over the case export and the
telemetry database. Those tables were reproduced and checked against his results by the verification scripts:
  verification/outputs/repro_sql_<name>.csv   his case-export SQL, run verbatim on the workbook (reproduce_sql.py)
  verification/outputs/db/db_<name>.csv       his telemetry SQL, re-run on the full database (verify_with_db.py)
The charts read only these committed, pseudonymous tables, so they need neither the workbook nor the database. Only
the real-name variant of the customer chart reads the workbook (gitignored data/raw/) to put names back.

The definitions drawn on the charts follow Zac's SQL (cells 15, 27 and 31 of his notebook).
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / 'verification' / 'outputs'
DB = OUTPUTS / 'db'
FIG_DIR = ROOT / 'viz' / 'figures'
DELIVERABLES = ROOT / 'deliverables'
WORKBOOK = ROOT / 'data' / 'raw' / 'IPA_CaseHistory_Aug 2025-Aug2026.xlsx'


def load(name):
    """verification/outputs/repro_sql_<name>.csv: one of Zac's case-export tables."""
    return pd.read_csv(OUTPUTS / f'repro_sql_{name}.csv')


def load_db(name):
    """verification/outputs/db/db_<name>.csv: one of Zac's telemetry tables, re-run on the full database."""
    return pd.read_csv(DB / f'db_{name}.csv')


def period_text(rq=None):
    """'Aug 2025 to Aug 2026': first to last opened ticket in the case export (repro_sql_record_quality.csv)."""
    rq = load('record_quality') if rq is None else rq
    start, end = (pd.Timestamp(rq[c].iloc[0]).strftime('%b %Y') for c in ('first_opened', 'last_opened'))
    return f'{start} to {end}'


# ---------------------------------------------------------------------------------------------------------------
# Definitions (Zac's SQL)
# ---------------------------------------------------------------------------------------------------------------
UNPLANNED_DEFINITION = (
    'Unplanned tickets = every ticket except planned work (Preventative Maintenance or Installation trouble codes, '
    'and Install Cases), cancelled requests and duplicate cases. No Trouble Found tickets stay in.')

ACTIVE_MONTH_DEFINITION = (
    'Active machine-month = a calendar month from Aug 2025 to Jul 2026 in which a machine logged at least one '
    'telemetry transaction (Zac\'s denominator: months with no transactions do not count). Devices on the shared '
    'internal host or with no host are excluded.')

REPEAT_DEFINITION = (
    'Repeat contact = an unplanned ticket followed by another unplanned ticket on the same machine within 30 days of '
    'opening (0 to 30 days). Only index tickets opened before 2 Aug 2026 count, so each has a full 30-day window. A '
    'repeat contact is not necessarily a failed repair.')


# Customer charts (zac_02, zac_08). docs/03_customer_fleet_ownership.md section 3.1: most accounts read as one
# hospital or campus; a few are labs or units within a campus.
CUSTOMER_DEFINITION = (
    'Customer = the account name on the ticket. An account is usually a single facility (a hospital, campus or lab), '
    'not a health system: a health system with several facilities appears as several customers.')
WORKLOAD_NOTE = ('Counts measure workload, not reliability: a customer can rank high simply because it has more '
                 'machines installed, and the case export does not record installed machines per customer.')


def fault_code_definition():
    """Provisional fault codes, counted from the team's code buckets (db_codes_buckets.csv)."""
    codes = load_db('codes_buckets')
    fault = codes[codes.provisional_fault == 1]
    parts = ', '.join(f'{n} {b.lower()}' for b, n in fault.bucket.value_counts().sort_index(ascending=False).items())
    return (f'Provisional fault codes = the {len(fault)} transaction codes the team classes as faults ({parts}). '
            f'The buckets are provisional, not yet validated by IPA, and machine families differ in which codes '
            f'they can log.')


# ---------------------------------------------------------------------------------------------------------------
# Real names (private; workbook in gitignored data/raw/)
# ---------------------------------------------------------------------------------------------------------------
def _account_map():
    """{real account name: 'Customer NNN'} from the workbook, or None when the workbook is absent."""
    if not WORKBOOK.exists():
        return None
    sys.path.insert(0, str(ROOT / 'verification'))
    import common  # noqa: E402  (verification/common.py rebuilds Zac's deterministic pseudonyms)
    return common.build_maps(common.load_raw(WORKBOOK))['account']


def real_customer_names():
    """{'Customer NNN': real account name} for the real-name chart variant, or None without the workbook."""
    m = _account_map()
    return None if m is None else {v: k for k, v in m.items()}


def real_strings():
    """Every real account name (for the privacy scan of the pseudonymous figures), or None without the workbook.
    Never print these."""
    m = _account_map()
    return None if m is None else {str(k) for k in m if k and len(str(k)) >= 4}
