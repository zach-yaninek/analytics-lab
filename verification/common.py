"""Shared loaders that rebuild Zac's case table exactly as notebook cell 4 does.

Everything here is read-only with respect to the source files. Real names and serials
stay in memory; only pseudonymous identifiers are written by the scripts that use this.
"""
import hashlib
import sqlite3
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
PRIVATE = ROOT / 'data' / 'private'
DERIVED = ROOT / 'data' / 'derived'
OUTPUTS = ROOT / 'verification' / 'outputs'
XLS = RAW / 'IPA_CaseHistory_Aug 2025-Aug2026.xlsx'
NOTEBOOK = RAW / 'IPA_Service_Ticket_SQL_Analysis.ipynb'
SHEET = 'ipa_repair cases'
# IPA's active installed-base list (received 19 Oct 2026); gitignored like every raw file.
EQUIPMENT = RAW / 'IPA_Active_Equipment_list_2026-10-19.xlsx'
EQUIP_SHEET = 'Equipment list - Monthly Report'
EQUIP_KEEP = {'Serial Number': 'serial', 'Account Name': 'account', 'Model': 'model', 'Product Family': 'family',
              'Service Status': 'service_status', 'Service Plan': 'service_plan',
              'Equipment Ownership': 'ownership', 'Shipping Country': 'country'}
EQUIP_DATES = {'install_date': 'Install Date', 'go_live_date': 'Go Live Date'}
EQUIP_PRIVATE_COLUMNS = ['Serial Number', 'Account Name', 'Hospital Address', 'Hospital City', 'Hospital Zip Code',
                         'Phone', 'Location', 'Poll Position', 'Vendor Credentialing Notes']

# Checksums recorded in Zac's notebook (cell 2).
ZAC_WORKBOOK_SHA256 = '8ffdc2482ee120b7ae59c42d9bec78210bd412e076e7ca9c013fdb8e51084ff8'
ZAC_DB_SHA256 = '7aa5d423bb381db2e1ab60c3dc95ca986e0e1140a4b41140ac3ea101382244d0'
SHARED_INTERNAL_HOST = 'https://ipa-production.thinkipa.net'
SEED = '15072'

RENAME = {'Date/Time Opened': 'opened_at', 'Trouble Closed Date/Time': 'closed_at', 'Model #': 'model',
          'Product Name': 'product', 'Case Record Type': 'record_type', 'Status': 'status',
          'Trouble Code': 'trouble_code', 'Trouble Code Category': 'category',
          'Trouble Code Sub Category': 'subcategory'}
TEXT_FIELDS = [('Trouble Reported', 'reported'), ('Trouble Resolution', 'resolution'),
               ('Administrative Notes', 'administrative')]


def clean(x):
    """Zac's identifier cleaner: strip whitespace, blank -> None (NaN-safe under pandas 3)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    return None if str(x).strip() == '' else str(x).strip()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_raw(path=XLS):
    """Read the case sheet the way cell 4 does (read-only, cached values, drop all-blank rows)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = wb[SHEET].values
        headers = next(rows)
        frame = pd.DataFrame([r for r in rows if any(v is not None for v in r)], columns=headers)
    finally:
        wb.close()  # read-only workbooks keep the file open until closed
    # pandas 3 turns blank text cells into NaN in str-dtype columns; Zac's Colab (pandas 2)
    # kept object columns holding None. Restore that so clean() and SQL NULLs behave as in Colab.
    return frame.astype(object).where(frame.notna(), None)


def _equipment_rows(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = wb[EQUIP_SHEET].values
        headers = next(rows)
        return pd.DataFrame([r for r in rows if any(v is not None for v in r)], columns=headers)
    finally:
        wb.close()


def load_equipment(path=EQUIPMENT):
    """IPA's active installed-base list, keeping only the fields the analysis uses.

    Address, city, zip, phone, location, poll position and credentialing columns are dropped here, so they never
    reach an analysis frame. Dates are Timestamps; country is normalised to USA / Canada.
    """
    raw = _equipment_rows(path)
    out = pd.DataFrame({new: raw[old].map(clean) for old, new in EQUIP_KEEP.items()})
    for col in ('install_date', 'go_live_date'):
        out[col] = pd.to_datetime(raw[EQUIP_DATES[col]], errors='coerce')
    out['country'] = out.country.str.upper().replace({'UNITED STATES': 'USA'}).str.title().replace({'Usa': 'USA'})
    return out


def equipment_real_strings(path=EQUIPMENT, columns=None):
    """Real strings from the equipment list (accounts, serials, addresses, cities, zips, phones, locations) for
    privacy scans only. Never written anywhere."""
    raw = _equipment_rows(path)
    cols = [c for c in (columns or EQUIP_PRIVATE_COLUMNS) if c in raw]
    return {s for c in cols for s in raw[c].map(clean).dropna().astype(str)}


def _timestamp(value):
    """Element-wise equivalent of cell 4's pd.to_datetime(...).dt.strftime for mixed cells."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        value = pd.to_datetime(value)
    return pd.Timestamp(value).strftime('%Y-%m-%d %H:%M:%S')


def build_maps(raw, device_ids=None):
    """Rebuild Zac's deterministic pseudonym maps.

    `acctmap` and `casemap` depend only on the workbook, so they match the notebook exactly.
    `serialmap` also depends on the telemetry device dictionary; without it, machine labels
    are prefixed 'S' instead of 'M' so they are never mistaken for Zac's machine_id values.
    """
    ticket_serials = set(raw['Serial #'].map(clean))
    if device_ids is None:
        serialmap = {s: f'S{i:05d}' for i, s in enumerate(sorted(ticket_serials), 1)}
    else:
        serials = sorted(set(map(clean, device_ids)) | ticket_serials)
        serialmap = {s: f'M{i:05d}' for i, s in enumerate(serials, 1)}
    accounts = sorted(raw['Account Name'].map(clean).unique())
    acctmap = {s: f'Customer {i:03d}' for i, s in enumerate(accounts, 1)}
    casemap = {s: f'T{i:05d}' for i, s in enumerate(sorted(raw['Case Number'].map(clean)), 1)}
    return {'serial': serialmap, 'account': acctmap, 'case': casemap}


def extend_maps(maps, equipment):
    """Add pseudonyms for installed-base serials and accounts that never appear on a ticket.

    Existing labels are untouched (Customer 171 stays Customer 171). New accounts continue the Customer numbering
    and new serials the S numbering, each in sorted order, so the result depends only on the two source files.
    """
    out = {k: dict(v) for k, v in maps.items()}
    serial_prefix = next(iter(out['serial'].values()))[0]  # 'S' (ticket serials only) or 'M' (with devices)
    for key, prefix, width in (('account', 'Customer ', 3), ('serial', serial_prefix, 5)):
        known = out[key]
        start = max(int(v.split()[-1].lstrip('SM')) for v in known.values())
        new = sorted(set(equipment[key].dropna()) - set(known))
        known.update({s: f'{prefix}{i:0{width}d}' for i, s in enumerate(new, start + 1)})
    return out


def build_cases(raw, maps):
    """Cell 4's `cases` table: pseudonymous ids, cleaned labels, text presence/length only."""
    c = pd.DataFrame({'case_id': raw['Case Number'].map(clean).map(maps['case']),
                      'customer': raw['Account Name'].map(clean).map(maps['account']),
                      'machine_id': raw['Serial #'].map(clean).map(maps['serial'])})
    for source, target in RENAME.items():
        if target.endswith('_at'):
            c[target] = raw[source].map(_timestamp)
        else:
            c[target] = raw[source].map(clean)
    for column, label in TEXT_FIELDS:
        c[label + '_present'] = raw[column].map(lambda x: int(clean(x) is not None))
        c[label + '_length'] = raw[column].map(lambda x: len(clean(x) or ''))
    return c


# Zac's views, verbatim from notebook cell 15.
CASE_VIEWS = """
DROP VIEW IF EXISTS case_base;
CREATE VIEW case_base AS
SELECT c.*, substr(opened_at,1,7) month,
 COALESCE(trouble_code,'[Missing]') || ' / ' || COALESCE(category,'[Missing]') || ' / ' || COALESCE(subcategory,'[Missing]') AS issue_path,
 CASE WHEN trouble_code IN ('Preventative Maintenance','Installation') OR record_type='Install Case' THEN 'Planned work'
      WHEN category='Cancelled Request' THEN 'Cancelled request'
      WHEN category='Duplicate Case' THEN 'Duplicate case'
      WHEN category='No Trouble Found' THEN 'No Trouble Found'
      WHEN trouble_code IS NULL THEN 'Missing trouble code'
      ELSE 'Other recorded issue' END service_group
FROM cases c;
DROP VIEW IF EXISTS service_cases;
CREATE VIEW service_cases AS SELECT * FROM case_base
WHERE service_group NOT IN ('Planned work','Cancelled request','Duplicate case');
"""


def case_database(cases, path=':memory:'):
    """SQLite connection holding `cases` plus Zac's case_base/service_cases views."""
    conn = sqlite3.connect(path)
    cases.to_sql('cases', conn, index=False, if_exists='replace')
    conn.executescript(CASE_VIEWS)
    return conn


def pilot_order(case_id):
    """Cell 8's deterministic sampling key."""
    return hashlib.sha256((SEED + case_id).encode()).hexdigest()


def load_all(device_ids=None):
    """Convenience: raw frame, maps, cases frame and an in-memory SQLite connection."""
    raw = load_raw()
    maps = build_maps(raw, device_ids)
    cases = build_cases(raw, maps)
    return raw, maps, cases, case_database(cases)


if __name__ == '__main__':
    raw, maps, cases, conn = load_all()
    print('rows', len(cases), 'customers', cases.customer.nunique(), 'machines', cases.machine_id.nunique(),
          'models', cases.model.nunique())
    print('opened', cases.opened_at.min(), cases.opened_at.max())
    print('workbook sha256 matches Zac:', sha256_file(XLS) == ZAC_WORKBOOK_SHA256)
