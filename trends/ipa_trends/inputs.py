"""Reading IPA's exports: the case report (tickets) and the equipment list snapshots (installed base).

The reader is a port of verification/common.py's load_raw and load_equipment (openpyxl read-only, cached values,
all-blank rows dropped, the pandas-3 null fix) with tolerances for what a fresh Salesforce export may look like:
the header row is found within the first 10 rows, header names are matched after trimming and case-folding (then
through COLUMN_ALIASES), report title and footer rows are skipped, and dates stored as text are read with one
format per column. Only the needed columns are kept; Trouble Reported is turned into the monitoring flag and
dropped. Messages give codes, counts, column names and Excel row numbers, never cell values.

The ticket table runs the copied CASE_VIEWS (Zac's unplanned-ticket definition) verbatim in an in-memory SQLite
database, then the copied monitoring rule and request-type mapping.
"""
import datetime as dt
import difflib
import glob
import hashlib
import math
import os
import re
import sqlite3
import zipfile
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

from .definitions import common_copy as C
from .definitions import flags_copy as F
from .definitions import followups_copy as FU
from .errors import InputError

DEFINITIONS = Path(__file__).resolve().parent / 'definitions'
REFERENCE = DEFINITIONS / 'request_types_v0.csv'
CASE_REQUIRED = ['Case Number', 'Account Name', 'Serial #', 'Date/Time Opened', 'Case Record Type', 'Status',
                 'Trouble Code', 'Trouble Code Category', 'Trouble Reported']
CASE_OPTIONAL = ['Trouble Code Sub Category', 'Trouble Closed Date/Time', 'Model #']
CASE_KNOWN = CASE_REQUIRED + CASE_OPTIONAL + ['Hospital City, State, Zip', 'Shipping Country', 'Dispatch #',
                                              'Product Name', 'Case Owner', 'Administrative Notes',
                                              'Trouble Resolution']
EQUIP_REQUIRED = ['Serial Number', 'Account Name', 'Model', 'Product Family', 'Service Plan', 'Install Date']
EQUIP_OPTIONAL = ['Service Status', 'Equipment Ownership', 'Shipping Country', 'Go Live Date']
EQUIP_KNOWN = EQUIP_REQUIRED + EQUIP_OPTIONAL + list(C.EQUIP_PRIVATE_COLUMNS) + [
    'Hospital State', 'Manufacturing Date Code', 'Last PM date', 'Vendor Credentialing', 'Current SC Expiration']
CLOSED_STATUSES = ('Trouble Closed', 'Ricoh-Closed', 'Closed', 'Case Closed')     # docs/04 §2.4
OPEN_STATUSES = ('Dispatch',)
# values in the Aug 2025 - Aug 2026 export (verification/outputs/fleet/fx_unlisted_by_record_type.csv, docs/01 §2.4);
# a new value may mark planned work, so it raises a warning
KNOWN_RECORD_TYPES = ('scrubEx / SD Case', 'alEx Case', 'General Case', 'ScrubBank', 'ScrubExchange', 'Install Case',
                      '.')
EXCLUDED_GROUPS = ('Planned work', 'Cancelled request', 'Duplicate case')          # CASE_VIEWS' service_cases
UNMAPPED = 'Unmapped'
NO_ACCOUNT = '[no account]'
UNKNOWN = 'Unknown'
DATE_FORMATS = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%m/%d/%Y %I:%M %p',
                '%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %H:%M', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y', '%m/%d/%y %I:%M %p',
                '%m/%d/%y %H:%M', '%m/%d/%y', '%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y', '%d.%m.%Y %H:%M',
                '%d.%m.%Y']
DAY_FIRST = {f for f in DATE_FORMATS if f.startswith('%d')}
DATE_IN_NAME = re.compile(r'(\d{4})-?(\d{2})-?(\d{2})')


def norm_header(h):
    return ' '.join(str(h).split()).casefold() if h is not None else ''


def rows_text(rows, limit=5):
    """'rows 12, 15, 40 and 7 more' from Excel row numbers (no cell values)."""
    rows = list(rows)
    head = ', '.join(str(r) for r in rows[:limit])
    return f'Excel row{"s" if len(rows) > 1 else ""} {head}' + (f' and {len(rows) - limit} more' if len(rows) > limit
                                                               else '')


class Warnings:
    """Collected warnings: (code, message, fix). Messages carry counts and labels, never identifiers."""

    def __init__(self):
        self.items = []

    def add(self, code, message, fix=None, blocking=False):
        """blocking=True: the numbers may be wrong, so the run is not marked ready to distribute."""
        self.items.append({'code': code, 'message': message, 'fix': fix, 'blocking': bool(blocking)})


# ------------------------------------------------------------------------------------------------ files
def snapshot_date(path, mapping):
    name = Path(path).name
    if name in mapping:
        return pd.Timestamp(mapping[name])
    m = DATE_IN_NAME.search(name)
    if m:
        try:
            return pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _matches(params, patterns):
    out = []
    for pat in patterns:
        out += [Path(p) for p in glob.glob(str(params.path(pat)))]
    return sorted({p.resolve() for p in out if not p.name.startswith('~$')})


def find_inputs(params, warn):
    """The case export to use (the newest match) and every equipment-list snapshot, with their dates."""
    cases = _matches(params, params.CASE_EXPORTS)
    if not cases:
        raise InputError('E01', f'no case export matches {params.CASE_EXPORTS}',
                         'save the case report as .xlsx in the input folder, or set CASE_EXPORTS')
    def key(p):
        d = snapshot_date(p, {})
        return (d if d is not None else pd.Timestamp.min, p.stat().st_mtime, p.name)
    cases = sorted(cases, key=key)
    if len(cases) > 1:
        warn.add('W19', f'{len(cases)} case exports match; using the newest ({cases[-1].name}), ignoring '
                        f'{len(cases) - 1}', 'move older exports to another folder if this is not the one you meant')
    equipment = _matches(params, params.EQUIPMENT_LISTS)
    if not equipment:
        raise InputError('E01', f'no equipment list matches {params.EQUIPMENT_LISTS}',
                         'save the equipment list (Monthly Report) as .xlsx in the input folder, or set '
                         'EQUIPMENT_LISTS')
    snaps = []
    for p in equipment:
        d = snapshot_date(p, params.EQUIPMENT_LIST_DATES)
        if d is None:
            raise InputError('E09', f'the date of equipment list {p.name} is unknown',
                             "put the date in the file name (IPA_Active_Equipment_list_YYYY-MM-DD.xlsx) or set "
                             "EQUIPMENT_LIST_DATES = {'<file name>': 'YYYY-MM-DD'}")
        snaps.append((d, p))
    dates = [d for d, _ in snaps]
    if len(set(dates)) != len(dates):
        raise InputError('E09', 'two equipment lists have the same date', 'keep one list per date')
    return cases[-1], sorted(snaps)


def fingerprint(df, sort_by):
    """One-way hash of the cleaned values the analysis reads, in a fixed order: identifies an export's content even
    after Excel re-saves the file (which changes its bytes)."""
    d = df.sort_values(sort_by, kind='mergesort').astype(str)
    return hashlib.sha256(d.to_csv(index=False, lineterminator='\n').encode('utf-8')).hexdigest()[:16]


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------ workbook reader
def _open_workbook(path):
    path = Path(path)
    if path.suffix.lower() == '.xls':
        raise InputError('E01', f'{path.name} is an old Excel .xls file', 'open it in Excel and save it as .xlsx')
    if path.suffix.lower() not in ('.xlsx', '.xlsm'):
        raise InputError('E01', f'{path.name} is not an Excel .xlsx file', 'export the report as Excel (.xlsx)')
    if not zipfile.is_zipfile(path):
        raise InputError('E01', f'{path.name} cannot be opened as .xlsx (it may be encrypted by a sensitivity label, '
                                'or still downloading)', 'save an unencrypted copy as .xlsx')
    try:
        return openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:                       # noqa: BLE001 - the type is reported, never the content
        raise InputError('E01', f'{path.name} cannot be read as a workbook ({type(e).__name__})',
                         'open it in Excel and save it again as .xlsx')


def read_sheet(path, sheet, required, optional, known, aliases, warn, kind, extra=()):
    """Rows of one sheet as an object frame (None for blanks) with the canonical column names that were found.

    Returns (frame, meta). `extra` columns are read when present (privacy-scan strings only)."""
    path = Path(path)
    wb = _open_workbook(path)
    try:
        created = getattr(wb.properties, 'created', None)
        if sheet in wb.sheetnames:
            ws = wb[sheet]
            used = sheet
        else:
            others = [s for s in wb.sheetnames if s.strip().lower() != 'summary']
            if len(others) != 1:
                raise InputError('E02', f'{kind}: sheet {sheet!r} not found in {path.name}; its sheets are '
                                        f'{wb.sheetnames}', 'set the sheet name parameter to the right sheet')
            ws, used = wb[others[0]], others[0]
            warn.add('W18', f'{kind}: sheet {sheet!r} not found; read the only other sheet, {used!r}',
                     'set the sheet name parameter if this is wrong')
        alias = {norm_header(k): v for k, v in aliases.items()}
        canon = {norm_header(h): h for h in known}
        needed = list(required) + list(optional) + list(extra)

        def canonical(h):
            n = norm_header(h)
            return alias.get(n) or canon.get(n)

        rows = ws.iter_rows(values_only=True)
        head, header_row, skipped = None, None, 0
        want = max(3, math.ceil(len(required) / 2))
        for i, row in enumerate(rows, 1):
            hits = sum(1 for h in row if h is not None and canonical(h) in needed + list(known))
            if hits >= want:
                head, header_row = row, i
                break
            skipped += 1
            if i >= 10:
                break
        if head is None:
            raise InputError('E03', f'{kind}: no header row found in the first 10 rows of {path.name}',
                             'export the report with its column headers (Details Only)')
        index, seen = {}, {}
        for j, h in enumerate(head):
            c = canonical(h) if h is not None else None
            if c is None:
                continue
            if c in index:
                raise InputError('E03', f'{kind}: two columns are both read as {c!r}', 'rename or delete one of them')
            index[c] = j
            seen[c] = h
        missing = [c for c in required if c not in index]
        if missing:
            headers = [str(h) for h in head if h is not None]
            hints = []
            for c in missing:
                close = difflib.get_close_matches(c, headers, n=1, cutoff=0.5)
                hints.append(f"'{c}'" + (f" (closest header: '{close[0]}'; add COLUMN_ALIASES = "
                                         f"{{'{close[0]}': '{c}'}})" if close else ''))
            raise InputError('E03', f'{kind}: required column(s) not found in {path.name}: ' + '; '.join(hints),
                             'export the columns listed in trends/README.md, or map renamed ones with COLUMN_ALIASES')
        cols = [c for c in needed if c in index]
        data, excel_rows, blank_rows, non_data = [], [], 0, 0
        for i, row in enumerate(rows, header_row + 1):
            if not any(v is not None for v in row):
                blank_rows += 1
                continue
            vals = [row[index[c]] if index[c] < len(row) else None for c in cols]
            filled_required = sum(1 for c, v in zip(cols, vals) if c in required and v is not None
                                  and str(v).strip() != '')
            if filled_required < 2:              # report title, group or footer row ("Generated By: ...")
                non_data += 1
                continue
            data.append(vals)
            excel_rows.append(i)
    finally:
        wb.close()
    frame = pd.DataFrame(data, columns=cols)
    frame = frame.astype(object).where(frame.notna(), None)       # the pandas-3 null fix (common.load_raw)
    frame.index = pd.Index(excel_rows, name='excel_row')
    if non_data:
        warn.add('W20', f'{kind}: skipped {non_data} title, group or footer row(s) without data')
    meta = {'file': path.name, 'bytes': path.stat().st_size, 'sha256': file_sha256(path), 'sheet': used,
            'header_row': header_row, 'rows': len(frame), 'blank_rows': blank_rows, 'non_data_rows': non_data,
            'columns_missing_optional': [c for c in optional if c not in index],
            'created': f'{pd.Timestamp(created):%Y-%m-%d %H:%M:%S}' if created else None,
            'modified': f'{dt.datetime.fromtimestamp(path.stat().st_mtime):%Y-%m-%d %H:%M:%S}'}
    return frame, meta


# ------------------------------------------------------------------------------------------------ dates
def _clean_date_text(s):
    s = s.replace(' ', ' ').replace('\xa0', ' ').strip()
    s = re.sub(r'^(\d{1,2}/\d{1,2}/\d{2,4}),\s*', r'\1 ', s)        # '11/21/2025, 7:11 AM'
    return ' '.join(s.split())


def parse_dates(values, column, kind, date_format=None, strict=True, warn=None):
    """Timestamps (naive) for a column of Excel datetimes and/or text. One format per column: the first format in
    DATE_FORMATS (month-first before day-first) that reads every text value, or DATE_FORMAT. A column that only
    reads as a mix of month-first and day-first is refused (E05). Text with a time zone is converted to US Eastern.

    strict=True: unreadable values stop the run (E05). strict=False: they become NaT and are counted.
    Returns (Series of Timestamp/NaT, facts)."""
    facts = {'text_values': 0, 'unreadable': 0, 'tz_converted': 0, 'format': None}
    result = {}
    text_idx, text_vals = [], []
    for i, v in values.items():
        if v is None or (not isinstance(v, (str, dt.datetime, dt.date)) and pd.isna(v)) or v is pd.NaT:
            continue                              # None, NaN, NA and NaT are blanks
        if isinstance(v, (dt.datetime, dt.date, pd.Timestamp)):
            ts = pd.Timestamp(v)
            if ts.tzinfo is not None:
                ts = ts.tz_convert('America/New_York').tz_localize(None)
                facts['tz_converted'] += 1
            result[i] = ts
        else:
            s = _clean_date_text(str(v))
            if s:
                text_idx.append(i)
                text_vals.append(s)
    facts['text_values'] = len(text_vals)
    bad_rows = []
    fmt = date_format
    if text_vals:
        distinct = sorted(set(text_vals))
        if fmt is None:
            # one format for the whole column: the first that reads every value (month-first is tried first)
            fmt = next((f for f in DATE_FORMATS if all(_try(s, f) is not None for s in distinct)), None)
            if fmt is None:
                only_day_first = [s for s in distinct if any(_try(s, f) for f in DAY_FIRST)
                                  and not any(_try(s, f) for f in DATE_FORMATS if f not in DAY_FIRST)]
                only_month_first = [s for s in distinct if not any(_try(s, f) for f in DAY_FIRST)
                                    and any(_try(s, f) for f in DATE_FORMATS if f not in DAY_FIRST)]
                if only_day_first and only_month_first:
                    raise InputError('E05', f'{kind}: {column!r} mixes month-first and day-first dates stored as '
                                            'text, so some dates cannot be read reliably',
                                     "set DATE_FORMAT to the export's format, for example '%m/%d/%Y %I:%M %p'")
        parsed = {}
        for i, s in zip(text_idx, text_vals):
            if s not in parsed:
                ts = _try(s, fmt) if fmt is not None else None
                if ts is None and date_format is None:        # as common._timestamp: pandas reads the value
                    try:
                        ts = pd.Timestamp(pd.to_datetime(s))
                    except (ValueError, TypeError, OverflowError):
                        ts = None
                if ts is not None and ts.tzinfo is not None:
                    ts = ts.tz_convert('America/New_York').tz_localize(None)
                    facts['tz_converted'] += 1
                parsed[s] = ts
            if parsed[s] is None:
                bad_rows.append(i)
            else:
                result[i] = parsed[s]
    out = pd.Series([result.get(i, pd.NaT) for i in values.index], index=values.index, dtype='datetime64[ns]')
    facts['format'] = fmt
    facts['unreadable'] = len(bad_rows)
    if bad_rows and strict:
        raise InputError('E05', f'{kind}: {len(bad_rows)} value(s) in {column!r} are not readable dates '
                                f'({rows_text(bad_rows)})', 'fix those cells, or set DATE_FORMAT')
    if warn is not None and text_vals:
        warn.add('W13', f'{kind}: {len(text_vals)} value(s) in {column!r} are dates stored as text (read as '
                        f'{fmt or "mixed formats"})')
    return out, facts


def _try(s, fmt):
    try:
        return pd.Timestamp(dt.datetime.strptime(s, fmt))
    except ValueError:
        return None


def to_eastern(ts, tz, warn):
    """Convert naive wall-clock times on another zone's clock to naive US Eastern (the case clock the analysis
    uses). Ambiguous fall-back hours are read as standard time and counted."""
    if tz == 'America/New_York':
        return ts, 0
    s = pd.Series(ts)
    loc = s.dt.tz_localize(tz, ambiguous='NaT', nonexistent='shift_forward')
    amb = loc.isna() & s.notna()
    if amb.any():
        loc[amb] = s[amb].dt.tz_localize(tz, ambiguous=False, nonexistent='shift_forward')
    out = loc.dt.tz_convert('America/New_York').dt.tz_localize(None)
    if amb.any():
        warn.add('W21', f'{int(amb.sum())} opened time(s) fell in the repeated daylight-saving hour; read as '
                        'standard time')
    return out, int(amb.sum())


# ------------------------------------------------------------------------------------------------ tickets
def load_reference(params):
    """The frozen v0 request-type reference plus local additions (which may not redefine a v0 row)."""
    ref = pd.read_csv(REFERENCE, dtype=str, keep_default_na=False)
    if FU.request_types_hash(REFERENCE) != FU.REF_HASH:
        raise InputError('E07', 'the request-type reference (request_types_v0.csv) has been edited',
                         'restore it and put additions in REQUEST_TYPES_LOCAL')
    if params.REQUEST_TYPES_LOCAL:
        path = params.path(params.REQUEST_TYPES_LOCAL)
        if not path.exists():
            raise InputError('E08', f'REQUEST_TYPES_LOCAL file {path.name} not found', None)
        local = pd.read_csv(path, dtype=str, keep_default_na=False)
        need = {'trouble_code', 'category', 'group'}
        if not need <= set(local.columns):
            raise InputError('E08', f'{path.name} needs columns trouble_code, category, group', None)
        clash = set(zip(local.trouble_code, local.category)) & set(zip(ref.trouble_code, ref.category))
        if clash:
            raise InputError('E08', f'{path.name} redefines {len(clash)} combination(s) of the v0 reference',
                             'local rows may only add new Trouble Code x Category combinations')
        bad = sorted(set(local.group) - set(FU.GROUPS))
        if bad:
            raise InputError('E08', f'{path.name} uses unknown group(s) {bad}', f'use one of {FU.GROUPS}')
        ref = pd.concat([ref, local[list(ref.columns.intersection(local.columns))]], ignore_index=True)
    return ref


def build_tickets(frame, meta, params, warn):
    """All case rows with Zac's service_group, the unplanned flag, monitoring, request types and open status.

    Real account names and serials are kept in memory (clusters, matching, the privacy scan) and never written."""
    n_rows = len(frame)
    # every ticket account in the export: the base of the pseudonym numbering (common.build_maps), hence the order
    # in which the bootstrap resamples accounts
    all_accounts = set(frame['Account Name'].map(C.clean)) - {None}
    t = pd.DataFrame(index=frame.index)
    for col, new in (('Case Number', 'case_number'), ('Account Name', 'account'), ('Serial #', 'serial'),
                     ('Case Record Type', 'record_type'), ('Status', 'status'), ('Trouble Code', 'trouble_code'),
                     ('Trouble Code Category', 'category'), ('Trouble Code Sub Category', 'subcategory'),
                     ('Model #', 'model_ticket')):
        t[new] = frame[col].map(C.clean) if col in frame else None
    if params.CATEGORY_ALIASES:
        t['category'] = t.category.map(lambda c: params.CATEGORY_ALIASES.get(c, c) if c is not None else None)
    t['monitoring'] = frame['Trouble Reported'].map(F.monitoring_template).astype(bool)

    opened, dfacts = parse_dates(frame['Date/Time Opened'], 'Date/Time Opened', 'case export', params.DATE_FORMAT,
                                 strict=True, warn=warn)
    missing_open = opened.isna()
    if missing_open.any():
        raise InputError('E05', f'case export: {int(missing_open.sum())} row(s) have no Date/Time Opened '
                                f'({rows_text(frame.index[missing_open])})', 'fix those rows in the export')
    opened, _ = to_eastern(opened, params.CASE_CLOCK_TZ, warn)
    opened.index = frame.index
    t['opened_at'] = opened.map(C._timestamp)                       # verbatim: 'YYYY-MM-DD HH:MM:SS' strings
    t['ts'] = pd.to_datetime(t.opened_at)                           # as fleet_exposure: naive Eastern
    if 'Trouble Closed Date/Time' in frame:
        closed, _ = parse_dates(frame['Trouble Closed Date/Time'], 'Trouble Closed Date/Time', 'case export',
                                params.DATE_FORMAT, strict=False, warn=None)
        closed, _ = to_eastern(closed, params.CASE_CLOCK_TZ, warn)
        closed.index = frame.index
        t['closed_ts'] = closed
    else:
        t['closed_ts'] = pd.NaT

    # blank identifiers: a few are dropped with a count; many mean a broken export
    blank = t.case_number.isna() | t.serial.isna()
    if blank.mean() > 0.005:
        raise InputError('E10', f'case export: {int(blank.sum())} of {n_rows} rows have no Case Number or Serial #',
                         'check that the export includes those columns for every row')
    if blank.any():
        warn.add('W10', f'case export: {int(blank.sum())} row(s) without a Case Number or Serial # were left out')
    t = t[~blank].copy()
    acct_blank = t.account.isna()
    if acct_blank.any():
        warn.add('W10', f'case export: {int(acct_blank.sum())} ticket(s) have no Account Name')
    # duplicate case numbers: identical rows are dropped; different contents stop the run
    dup = t.case_number.duplicated(keep=False)
    if dup.any():
        cols = ['account', 'serial', 'opened_at', 'record_type', 'status', 'trouble_code', 'category']
        g = t[dup].groupby('case_number')[cols].nunique(dropna=False)
        conflicting = g[(g > 1).any(axis=1)]
        if len(conflicting):
            rows = t.index[t.case_number.isin(conflicting.index)]
            raise InputError('E04', f'case export: {len(conflicting)} Case Number(s) appear more than once with '
                                    f'different contents ({rows_text(rows)})', 'export the report again')
        n_drop = int(t.case_number.duplicated().sum())
        t = t[~t.case_number.duplicated()].copy()
        warn.add('W16', f'case export: {n_drop} identical duplicate row(s) were dropped')

    # Zac's service_group and the unplanned population, by the verbatim views
    conn = sqlite3.connect(':memory:')
    try:
        base = pd.DataFrame({'case_id': np.arange(len(t)), 'opened_at': t.opened_at.to_numpy(),
                             'record_type': t.record_type.to_numpy(), 'trouble_code': t.trouble_code.to_numpy(),
                             'category': t.category.to_numpy(), 'subcategory': t.subcategory.to_numpy()})
        base.to_sql('cases', conn, index=False)
        conn.executescript(C.CASE_VIEWS)
        sg = pd.read_sql('SELECT case_id, service_group FROM case_base ORDER BY case_id', conn)
        n_unplanned_view = int(pd.read_sql('SELECT COUNT(*) n FROM service_cases', conn).n[0])
    finally:
        conn.close()
    t['service_group'] = sg.service_group.to_numpy()
    t['unplanned'] = ~t.service_group.isin(EXCLUDED_GROUPS)
    assert int(t.unplanned.sum()) == n_unplanned_view
    t['is_open'] = ~t.status.isin(CLOSED_STATUSES)
    unknown_status = ~t.status.isin(CLOSED_STATUSES + OPEN_STATUSES)
    if unknown_status.any():
        warn.add('W09', f'case export: {int(unknown_status.sum())} ticket(s) have a Status outside the known values; '
                        'they are treated as open', 'tell the MIT team or IPA analytics if a new status was added')
    unknown_rt = ~t.record_type.isin(KNOWN_RECORD_TYPES)
    if unknown_rt.any():
        n = int(unknown_rt.sum())
        warn.add('W09', f'case export: {n} ticket(s) have a Case Record Type outside the known values',
                 'check whether a new record type marks planned work; until then the run is not marked ready to '
                 'distribute' if n >= 10 else 'check whether a new record type marks planned work', blocking=n >= 10)

    # request types (docs/09 §3.3) on every row; only unplanned rows are analysed
    ref = load_reference(params)
    t['cgroup'], t['group'], t['ctype'] = None, None, None
    lut = set(zip(ref.trouble_code, ref.category))
    tc, cat = t.trouble_code.fillna(FU.BLANK), t.category.fillna(FU.BLANK)
    t['unmapped'] = [k not in lut for k in zip(tc, cat)]
    work = t[['trouble_code', 'category', 'monitoring']].copy()
    labels = FU.assign_request_types(work, ref)
    t['cgroup'], t['group'], t['ctype'] = work.cgroup, work.group, work.ctype
    if params.UNMAPPED_POLICY == 'separate':
        # combinations missing from the reference whose Trouble Code does not fix the group get their own group,
        # which is reported but never tested (a new or split Category must not look like a change in Door or Other)
        sep = t.unmapped & ~t.trouble_code.isin(list(FU.BY_TROUBLE_CODE))
        t.loc[sep, 'cgroup'] = UNMAPPED
        t.loc[sep & ~t.monitoring, 'group'] = UNMAPPED
    unp = t[t.unplanned]
    combos = (unp[unp.unmapped].assign(tc=unp.trouble_code.fillna(FU.BLANK), ca=unp.category.fillna(FU.BLANK))
              .groupby(['tc', 'ca']).size().rename('tickets').reset_index()
              .rename(columns={'tc': 'trouble_code', 'ca': 'category'}).sort_values(['tickets', 'trouble_code'],
                                                                                    ascending=[False, True]))
    if len(combos):
        warn.add('W04', f'{int(combos.tickets.sum())} unplanned ticket(s) in {len(combos)} Trouble Code x Category '
                        'combination(s) are not in the request-type reference (see unmapped.csv)',
                 'add them to a REQUEST_TYPES_LOCAL file once IPA confirms where they belong')
    code_groups = ref.groupby('trouble_code').group.agg(lambda s: sorted(set(s))).to_dict()
    meta['content_fingerprint'] = fingerprint(t[['case_number', 'account', 'serial', 'opened_at', 'record_type',
                                                 'status', 'trouble_code', 'category']], 'case_number')
    facts = {'case_rows': n_rows, 'rows_kept': len(t), 'planned': int((t.service_group == 'Planned work').sum()),
             'cancelled': int((t.service_group == 'Cancelled request').sum()),
             'duplicate': int((t.service_group == 'Duplicate case').sum()), 'unplanned': int(t.unplanned.sum()),
             'monitoring_all_rows': int(t.monitoring.sum()), 'opened_text_values': dfacts['text_values'],
             'unmapped_tickets': int(combos.tickets.sum()) if len(combos) else 0,
             'unmapped_combinations': len(combos), 'request_types_hash': FU.request_types_hash(REFERENCE)}
    return t.reset_index(), combos, code_groups, facts, all_accounts


# ------------------------------------------------------------------------------------------------ equipment
def read_equipment(path, params, warn):
    """One equipment-list snapshot: the EQUIP_KEEP fields (cleaned), install and go-live dates, and real strings
    for the privacy scan (never written)."""
    frame, meta = read_sheet(path, params.EQUIPMENT_SHEET, EQUIP_REQUIRED, EQUIP_OPTIONAL, EQUIP_KNOWN,
                             params.COLUMN_ALIASES, warn, f'equipment list {Path(path).name}',
                             extra=[c for c in C.EQUIP_PRIVATE_COLUMNS if c not in EQUIP_REQUIRED])
    out = pd.DataFrame(index=frame.index)
    for old, new in C.EQUIP_KEEP.items():
        out[new] = frame[old].map(C.clean) if old in frame else None
    for new, old in C.EQUIP_DATES.items():
        if old in frame:
            d, f = parse_dates(frame[old], old, f'equipment list {Path(path).name}', params.DATE_FORMAT,
                               strict=False)
            nonblank = int(frame[old].map(lambda v: v is not None and str(v).strip() != '').sum())
            if f['unreadable'] and f['unreadable'] > 0.01 * max(nonblank, 1):
                raise InputError('E05', f'equipment list: {f["unreadable"]} {old} value(s) are not readable dates',
                                 'fix those cells, or set DATE_FORMAT')
            if f['unreadable']:
                warn.add('W08', f'equipment list: {f["unreadable"]} {old} value(s) are not readable dates and were '
                                'treated as blank')
            out[new] = d.to_numpy()
        else:
            out[new] = pd.NaT
    if out.country.notna().any():
        out['country'] = out.country.str.upper().replace({'UNITED STATES': 'USA'}).str.title().replace({'Usa': 'USA'})
    blank_serial = out.serial.isna()
    if blank_serial.any():
        warn.add('W10', f'equipment list: {int(blank_serial.sum())} row(s) without a Serial Number were left out')
    out = out[~blank_serial]
    dup = out.serial.duplicated(keep=False)
    if dup.any():
        raise InputError('E06', f'equipment list {Path(path).name}: {int(out.serial[dup].nunique())} serial(s) are '
                                f'listed more than once ({rows_text(out.index[dup])})',
                         'remove the duplicate rows from the list')
    for col, fill, label in (('account', NO_ACCOUNT, 'Account Name'), ('model', UNKNOWN, 'Model'),
                             ('family', UNKNOWN, 'Product Family')):
        miss = out[col].isna()
        if miss.any():
            warn.add('W22', f'equipment list: {int(miss.sum())} machine(s) have no {label}; grouped as {fill!r}')
            out.loc[miss, col] = fill
    meta['content_fingerprint'] = fingerprint(out[['serial', 'account', 'model', 'family', 'service_plan',
                                                   'install_date']], 'serial')
    text_cols = ['Account Name', 'Hospital Address', 'Hospital City', 'Location', 'Vendor Credentialing Notes']
    digit_cols = ['Serial Number', 'Hospital Zip Code', 'Phone']
    private = {'text': {s for c in text_cols if c in frame for s in frame[c].map(C.clean).dropna().astype(str)},
               'digit': {s for c in digit_cols if c in frame for s in frame[c].map(C.clean).dropna().astype(str)}}
    return out.reset_index(drop=True), meta, private


def build_ledger(snapshots):
    """Union of the equipment-list snapshots, one row per serial.

    Attributes come from the newest snapshot that lists the serial. A machine missing from a later snapshot is
    taken as removed midway between its last listing and its first absence (exposure.py extends this to the day
    after its last ticket when that is later). With one snapshot this is exactly fleet_exposure's list."""
    snapshots = sorted(snapshots, key=lambda s: s[0])
    dates = [d for d, _ in snapshots]
    frames = []
    for d, f in snapshots:
        frames.append(f.assign(_snap=d))
    allrows = pd.concat(frames, ignore_index=True)
    newest_rows = allrows.sort_values('_snap', kind='mergesort').groupby('serial', sort=False).tail(1)
    listed = allrows.groupby('serial')._snap.agg(['min', 'max', 'size']).rename(
        columns={'min': 'first_listed', 'max': 'last_listed', 'size': 'snapshots_listed'})
    led = newest_rows.drop(columns='_snap').set_index('serial').join(listed).reset_index()
    newest = dates[-1]
    led['on_newest'] = led.last_listed == newest

    def first_absent(last):
        later = [d for d in dates if d > last]
        return later[0] if later else pd.NaT
    led['first_absent'] = led.last_listed.map(first_absent)
    led['removal_estimate'] = (led.last_listed + (led.first_absent - led.last_listed) / 2).dt.normalize()
    # keep the newest snapshot's row order first (as fleet_exposure iterates the list), then removed machines
    order = {s: i for i, s in enumerate(snapshots[-1][1].serial)}
    led['_o'] = led.serial.map(order).fillna(len(order) + led.index.to_series()).astype(float)
    return led.sort_values('_o', kind='mergesort').drop(columns='_o').reset_index(drop=True), newest


# ------------------------------------------------------------------------------------------------ clusters
def account_labels(ticket_accounts, list_accounts):
    """Pseudonym labels exactly as common.build_maps then common.extend_maps number them: ticket accounts in sorted
    order as 'Customer 001'..., then accounts only on the list, continuing the numbering. The bootstrap resamples
    accounts in the sorted order of these labels, so this order reproduces the committed intervals. Kept in memory
    only."""
    known = sorted({a for a in ticket_accounts if a is not None})
    labels = {a: f'Customer {i:03d}' for i, a in enumerate(known, 1)}
    start = len(known)
    new = sorted({a for a in list_accounts if a is not None} - set(labels))
    labels.update({a: f'Customer {i:03d}' for i, a in enumerate(new, start + 1)})
    return labels


# ------------------------------------------------------------------------------------------------ inspect
def inspect(path, sheet, known, aliases=None):
    """Values-free description of a workbook: sheets, header row, header names, and the type profile of each
    column (counts of dates, numbers, text, blanks; shapes of date text such as '99/99/9999 9:99 AA')."""
    aliases = aliases or {}
    wb = _open_workbook(path)
    try:
        out = {'file': Path(path).name, 'sheets': wb.sheetnames}
        ws = wb[sheet] if sheet in wb.sheetnames else wb[[s for s in wb.sheetnames
                                                         if s.lower() != 'summary'][0]]
        out['sheet_read'] = ws.title
        canon = {norm_header(h): h for h in known}
        alias = {norm_header(k): v for k, v in aliases.items()}
        rows = ws.iter_rows(values_only=True)
        head, hrow = None, None
        for i, row in enumerate(rows, 1):
            if sum(1 for h in row if h is not None and (norm_header(h) in canon or norm_header(h) in alias)) >= 3:
                head, hrow = row, i
                break
            if i >= 10:
                break
        out['header_row'] = hrow
        if head is None:
            out['problem'] = 'no header row in the first 10 rows'
            return out
        profile = {j: {'header': str(h), 'recognised_as': alias.get(norm_header(h)) or canon.get(norm_header(h)),
                       'date': 0, 'number': 0, 'text': 0, 'blank': 0, 'shapes': {}}
                   for j, h in enumerate(head) if h is not None}
        n = 0
        for row in rows:
            n += 1
            for j, p in profile.items():
                v = row[j] if j < len(row) else None
                if v is None or (isinstance(v, str) and not v.strip()):
                    p['blank'] += 1
                elif isinstance(v, (dt.datetime, dt.date)):
                    p['date'] += 1
                elif isinstance(v, (int, float)):
                    p['number'] += 1
                else:
                    p['text'] += 1
                    if p['recognised_as'] and ('Date' in p['recognised_as'] or 'Time' in p['recognised_as']):
                        shape = re.sub(r'[A-Za-z]', 'A', re.sub(r'\d', '9', str(v).strip()))
                        p['shapes'][shape] = p['shapes'].get(shape, 0) + 1
        out['data_rows'] = n
        out['columns'] = [{k: (dict(sorted(v.items(), key=lambda kv: -kv[1])[:5]) if k == 'shapes' else v)
                           for k, v in p.items()} for p in profile.values()]
        return out
    finally:
        wb.close()
