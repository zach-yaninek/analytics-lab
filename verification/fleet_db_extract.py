#!/usr/bin/env python3
"""Telemetry-database extract for fleet_exposure.py: every telemetry device, whether it is on IPA's installed-base
list, its telemetry type and host, and how long it was transaction-active. Run once, locally, next to the database.

Question it answers for fleet_exposure.py: which listed machines are networked (have a telemetry device), which
telemetry machine_type each listed model reports, and in how many months of Zac's period each device transacted.
With verification/outputs/fleet/db/fxdb_devices.csv present, fleet_exposure.py rates telemetry types on installed
exposure (machines on the list) instead of telemetry-span exposure.

Inputs (read-only; the database is opened mode=ro with PRAGMA query_only and is never written)
  --db         the telemetry database, e.g. data/raw/ipa_transaction_events_202508_202608.db. Tables used:
               devices(external_device_id, device_status, machine_type, clearview_url) and
               transaction_events(external_device_id, transaction_date_local), the latter only through the
               (external_device_id, transaction_date_local) index: a few index seeks per device, no table scan.
  --xlsx       the case export (common.XLS); only to rebuild Zac's machine ids
  --equipment  IPA's active installed-base list (common.EQUIPMENT)
  --fu-devices verification/outputs/fu/fu_devices.csv (db_followup.py); when it describes the same devices, the
               machine ids, hosts and first/last active days are checked against it

Definitions
  E1 Device = clean(external_device_id). machine_id = Zac's M##### from common.build_maps(raw, device ids), the
     same ids as fu_devices.csv and fu_ticket_last10.csv.
  E2 serial_id = the S##### used by fleet_exposure.py: common.extend_maps(common.build_maps(raw),
     common.load_equipment()) (S numbering, not the M map). A device is on the list (on_list = 1) when its id equals
     a list serial exactly, both clean()ed. Devices that would match only after stripping leading zeros on both sides
     are counted in the match summary and listed in the private crosswalk; they are NOT joined.
  E3 machine_type lower-cased, blank -> 'Unknown' (as Zac). host = 'Host NNN', the rank of the raw clearview_url among
     the sorted distinct URLs (db_followup.py, verify_with_db.py); shared_host = 1 for common.SHARED_INTERNAL_HOST
     (trailing '/' ignored).
  E4 first_active / last_active = MIN / MAX(transaction_date_local) over all of the device's events (as db_followup
     F4); first_active_in_period / last_active_in_period the same within 2025-08-01..2026-07-31.
     active_months_in_period = calendar months 2025-08..2026-07 with >= 1 event, i.e. Zac's transaction-active
     machine-months (his machine_month view); summed over all devices they reproduce his 70,057.

Outputs (--out, default verification/outputs/fleet/db; pseudonymous)
  fxdb_devices.csv               one row per device, sorted by machine_id: machine_id, serial_id (blank if not
                                 listed), on_list (0/1), machine_type, host, shared_host (0/1), device_status,
                                 first_active, last_active, active_months_in_period, first_active_in_period,
                                 last_active_in_period
  fxdb_match_summary.csv         measure, value: devices, devices on the list, listed machines networked,
                                 leading-zero extra matches, counts by product family
  fxdb_model_type_crosswalk.csv  model (from the list), machine_type (from the database), machines (on-list devices)
Private (--private, default data/private/fleet_db; gitignored)
  fxdb_private_serial_crosswalk.csv  real device id <-> machine_id <-> serial_id, and the list serials a device would
                                     match after stripping leading zeros
  fxdb_private_host_map.csv          Host NNN <-> clearview_url

Privacy: the public files hold only M#####, S#####, Host NNN, model / type / family / status labels, dates and
counts. A final check scans every text column of the public files: real serials, device ids and case numbers that
are all digits are leaks as whole cells; account names, URLs, URL host names and other ids as whole cells or as
tokens (4+ characters); any cell that looks like a URL is a leak. Nothing real is printed.

Run:  cd /home/user/analytics-lab && python3 -I verification/fleet_db_extract.py \\
          --db data/raw/ipa_transaction_events_202508_202608.db
Deterministic: no randomness; rows sorted by machine_id. Exit status 1 if any check fails.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import argparse  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
import time  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common  # noqa: E402
from common import clean  # noqa: E402

PREFIX = 'fxdb_'
PERIOD_FIRST, PERIOD_END = '2025-08-01', '2026-08-01'      # Zac's window: month >= '2025-08' AND month < '2026-08'
PERIOD_MONTHS = [p.strftime('%Y-%m') for p in pd.period_range('2025-08', '2026-07', freq='M')]
ZAC_DEVICES, ZAC_ACTIVE_MONTHS = 7183, 70057               # verify_with_db.py step 4: all represented machine-months
COLUMNS = ['machine_id', 'serial_id', 'on_list', 'machine_type', 'host', 'shared_host', 'device_status',
           'first_active', 'last_active', 'active_months_in_period', 'first_active_in_period',
           'last_active_in_period']
LABELS = {'machine_id': r'M\d{5,}', 'serial_id': r'S\d{5,}', 'host': r'Host \d{3,}'}
URL_LIKE = re.compile(r'://|^www\.|\bhttps?\b', re.IGNORECASE)
CHECKS = []
T0 = time.time()


def log(msg):
    print(f'[{time.time() - T0:7.1f}s] {msg}', flush=True)


def check(name, expected, actual):
    """expected None -> INFO (reported, never fails)."""
    status = 'INFO' if expected is None else ('PASS' if expected == actual else 'FAIL')
    CHECKS.append({'check': name, 'expected': expected, 'actual': actual, 'status': status})
    print(f'  [{status}] {name}: expected {expected}, got {actual}', flush=True)
    return status != 'FAIL'


# ----------------------------------------------------------------------------------------------------------------
# Database (read-only; same open and per-device index queries as db_followup.py)
# ----------------------------------------------------------------------------------------------------------------
def open_ro(path):
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f'database file not found: --db {path.name}')
    last = None
    for extra in ('', '&immutable=1'):     # immutable=1: read-only media or a WAL file without its -shm
        try:
            conn = sqlite3.connect(path.as_uri() + '?mode=ro' + extra, uri=True)
            conn.execute('PRAGMA query_only=ON')
            conn.execute('PRAGMA cache_size=-1048576')
            conn.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()
            return conn
        except sqlite3.Error as e:
            last = e
    raise last


def columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def read_devices(conn):
    dev_cols = columns(conn, 'devices')
    if 'external_device_id' not in dev_cols:
        raise SystemExit('devices.external_device_id not found')
    want = [c for c in ['external_device_id', 'device_status', 'machine_type', 'clearview_url'] if c in dev_cols]
    dev = pd.read_sql_query(f'SELECT {", ".join(want)} FROM devices', conn)
    for c in ('device_status', 'machine_type', 'clearview_url'):
        if c not in dev:
            dev[c] = None
    dev = dev.astype(object).where(dev.notna(), None)
    dev['device'] = dev.external_device_id.map(clean)
    return dev


def activity_sql():
    """One statement per device: overall MIN/MAX day, in-period MIN/MAX day and one EXISTS per period month.
    Every subquery is a seek on the (external_device_id, transaction_date_local) index."""
    base = 'FROM transaction_events WHERE external_device_id=?1'
    parts = [f'(SELECT MIN(transaction_date_local) {base})', f'(SELECT MAX(transaction_date_local) {base})',
             f'(SELECT MIN(transaction_date_local) {base} AND transaction_date_local>=?2 AND '
             f'transaction_date_local<?3)',
             f'(SELECT MAX(transaction_date_local) {base} AND transaction_date_local>=?2 AND '
             f'transaction_date_local<?3)']
    params = [PERIOD_FIRST, PERIOD_END]
    for month in PERIOD_MONTHS:
        lo = f'{month}-01'
        hi = (pd.Period(month, 'M') + 1).strftime('%Y-%m-01')
        i = len(params) + 2
        parts.append(f'EXISTS(SELECT 1 {base} AND transaction_date_local>=?{i} AND transaction_date_local<?{i + 1})')
        params += [lo, hi]
    return 'SELECT ' + ',\n '.join(parts), params


def device_activity(conn, devices):
    sql, params = activity_sql()
    rows = []
    for i, d in enumerate(devices, 1):
        if d is None:
            rows.append((None, None, None, None, 0))
            continue
        r = conn.execute(sql, [d] + params).fetchone()
        rows.append((r[0], r[1], r[2], r[3], int(sum(r[4:]))))
        if i % 1000 == 0:
            log(f'  activity: {i:,}/{len(devices):,} devices')
    return pd.DataFrame(rows, columns=['first_active', 'last_active', 'first_active_in_period',
                                       'last_active_in_period', 'active_months_in_period'])


# ----------------------------------------------------------------------------------------------------------------
# Privacy scan
# ----------------------------------------------------------------------------------------------------------------
def real_strings(raw, eq, dev):
    """Real identifiers for the scan (never written). Digit ids are leaks as whole cells only; text identifiers
    (accounts, URLs, URL host names, non-digit ids) as whole cells or as tokens of 4+ characters."""
    ids = (set(dev.device.dropna()) | set(dev.external_device_id.dropna().astype(str))
           | set(eq.serial.dropna()) | set(raw['Serial #'].map(clean).dropna())
           | set(raw['Case Number'].map(clean).dropna()))
    accounts = set(raw['Account Name'].map(clean).dropna()) | set(eq.account.dropna())
    urls = set(dev.clearview_url.dropna().astype(str))
    hosts = {urlsplit(u.strip()).netloc for u in urls if '://' in u} | {u.strip().rstrip('/') for u in urls}
    hosts = {h for h in hosts if h}
    strs = {str(s) for s in ids | accounts | urls | hosts}
    return {'digit': {s for s in strs if s.isdigit()},
            'text': {s for s in strs if not s.isdigit() and len(s) >= 4},
            'hosts': {h for h in hosts if len(h) >= 4}}


def text_leaks(df, real):
    """{column: number of distinct leaking values} over the text columns of df (fleet_exposure.text_leaks, plus a
    URL pattern and host-name substrings)."""
    out = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            continue
        hits = set()
        for v in df[col].dropna().astype(str).unique():
            if v in real['digit'] or v in real['text'] or URL_LIKE.search(v):
                hits.add(v)
            hits.update(t for t in re.findall(r'[A-Za-z0-9][A-Za-z0-9 .&\'-]*[A-Za-z0-9]', v) if t in real['text'])
            hits.update(t for t in re.findall(r'[A-Za-z0-9]+', v) if t in real['text'])
            hits.update(h for h in real['hosts'] if h in v)
        if hits:
            out[col] = len(hits)
    return out


# ----------------------------------------------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------------------------------------------
def strip_zeros(s):
    return s.lstrip('0') if isinstance(s, str) else None


def build(dev, raw, eq):
    """Device table with pseudonyms (dev must carry the activity columns)."""
    ids = [d for d in dev.device if d is not None]
    mmap = common.build_maps(raw, ids)['serial']                          # Zac's M##### (db_followup.py setup)
    smap = common.extend_maps(common.build_maps(raw), eq)['serial']      # fleet_exposure.py's S#####
    listed = set(eq.serial.dropna())
    d = dev.copy()
    d['machine_id'] = d.device.map(mmap)
    d['on_list'] = d.device.isin(listed).astype(int)
    d['serial_id'] = d.device.map(smap).where(d.on_list == 1, None)
    d['machine_type'] = d.machine_type.map(lambda x: clean(x).lower() if clean(x) else 'Unknown')
    url = d.clearview_url
    hosts = sorted(set(url.dropna()))
    hostmap = {h: f'Host {i:03d}' for i, h in enumerate(hosts, 1)}
    d['host'] = url.map(hostmap)
    d['shared_host'] = url.fillna('').astype(str).str.rstrip('/').eq(common.SHARED_INTERNAL_HOST).astype(int)
    d['device_status'] = d.device_status.map(clean)
    # Leading zeros (report only): off-list devices whose id equals a list serial once zeros are stripped.
    by_stripped = {}
    for s in sorted(listed):
        if strip_zeros(s):
            by_stripped.setdefault(strip_zeros(s), []).append(s)
    d['zero_stripped_list_serials'] = [None if on or not strip_zeros(x) else '|'.join(by_stripped.get(strip_zeros(x),
                                                                                                     [])) or None
                                       for x, on in zip(d.device, d.on_list)]
    return d.sort_values('machine_id', kind='mergesort', na_position='last').reset_index(drop=True), hostmap


def match_summary(d, eq):
    listed = set(eq.serial.dropna())
    on = d[d.on_list == 1]
    networked = set(on.device)
    active = set(on.device[on.active_months_in_period > 0])
    zero = d[d.zero_stripped_list_serials.notna()]
    zero_serials = {s for v in zero.zero_stripped_list_serials for s in v.split('|')}
    rows = [('devices', len(d)),
            ('distinct device ids after clean()', int(d.device.nunique())),
            ('devices with any transaction', int(d.first_active.notna().sum())),
            ('devices active in period (>= 1 month 2025-08..2026-07)', int((d.active_months_in_period > 0).sum())),
            ('active machine-months in period (all devices)', int(d.active_months_in_period.sum())),
            ('listed machines', len(eq)),
            ('devices on list', len(on)),
            ('devices not on list', int((d.on_list == 0).sum())),
            ('listed machines networked', len(networked)),
            ('listed machines networked and active in period', len(active)),
            ('listed machines not networked', len(listed - networked)),
            ('active machine-months in period (devices on list)', int(on.active_months_in_period.sum())),
            ("devices on list with machine_type 'Unknown'", int((on.machine_type == 'Unknown').sum())),
            ('devices on list on the shared internal host', int(on.shared_host.sum())),
            ('devices on list with no host', int(on.host.isna().sum())),
            ('leading-zero extra matches: devices (report only, not joined)', len(zero)),
            ('leading-zero extra matches: listed machines not otherwise networked',
             len(zero_serials - networked))]
    fam = eq.assign(networked=eq.serial.isin(networked), active=eq.serial.isin(active))
    fam['family'] = fam.family.fillna('[Missing]')
    for f, g in fam.groupby('family', sort=True):
        rows += [(f'family {f}: listed machines', len(g)), (f'family {f}: networked', int(g.networked.sum())),
                 (f'family {f}: networked and active in period', int(g.active.sum()))]
    return pd.DataFrame(rows, columns=['measure', 'value'])


def model_type_crosswalk(d, eq):
    on = d[d.on_list == 1].merge(eq[['serial', 'model']], left_on='device', right_on='serial', how='left')
    on['model'] = on.model.fillna('[Missing]')
    return (on.groupby(['model', 'machine_type']).size().rename('machines').reset_index()
            .sort_values(['model', 'machine_type'], kind='mergesort').reset_index(drop=True))


def compare_fu(d, fu_path):
    """Machine ids, hosts and first/last active days against db_followup.py's fu_devices.csv (same DB only)."""
    if not fu_path or not Path(fu_path).exists():
        check('machine ids / hosts / active days equal fu_devices.csv', None, 'file not found')
        return
    fu = pd.read_csv(fu_path, dtype=str, keep_default_na=False)
    if len(fu) != len(d):
        check('machine ids / hosts / active days equal fu_devices.csv', None,
              f'different device count ({len(fu)} vs {len(d)}): not compared')
        return
    mine = d[['machine_id', 'host', 'first_active', 'last_active']].fillna('').astype(str)
    mine = mine.sort_values('machine_id').reset_index(drop=True)
    theirs = fu[['machine_id', 'host', 'first_active', 'last_active']].sort_values('machine_id').reset_index(drop=True)
    check('machine ids equal fu_devices.csv', True, mine.machine_id.tolist() == theirs.machine_id.tolist())
    for col in ('host', 'first_active', 'last_active'):
        check(f'{col} per machine equals fu_devices.csv', 0, int((mine[col] != theirs[col]).sum()))


def run(db, xlsx=common.XLS, equipment=common.EQUIPMENT, out=common.OUTPUTS / 'fleet' / 'db',
        private=common.PRIVATE / 'fleet_db', fu_devices=common.OUTPUTS / 'fu' / 'fu_devices.csv'):
    """Returns (exit status, {name: public frame})."""
    CHECKS.clear()
    out, private = Path(out), Path(private)
    if out.resolve() == private.resolve():
        raise SystemExit('--out and --private must be different directories')
    log(f'fleet_db_extract: db={Path(db).name}')
    conn = open_ro(db)
    try:
        dev = read_devices(conn)
        log(f'  devices: {len(dev):,}; reading activity through the (device, date) index')
        act = device_activity(conn, dev.device.tolist())
    finally:
        conn.close()
    dev = pd.concat([dev.reset_index(drop=True), act], axis=1)
    log('  case export (machine ids) and installed-base list (serial ids)')
    raw = common.load_raw(xlsx)
    eq = common.load_equipment(equipment)
    d, hostmap = build(dev, raw, eq)

    print('Checks')
    check('device ids non-blank after clean()', 0, int(d.device.isna().sum()))
    check('device ids unique after clean()', True, bool(d.device.dropna().is_unique))
    check('every device has an M##### machine_id', True, bool(d.machine_id.notna().all()))
    check('every listed serial is unique', len(eq), int(eq.serial.nunique()))
    on = d[d.on_list == 1]
    check('every on-list device has an S##### serial_id', True,
          bool(on.serial_id.fillna('').str.fullmatch(LABELS['serial_id']).all()))
    check('each listed machine is matched by at most one device', True, bool(on.serial_id.is_unique))
    check('first_active <= last_active', 0, int((d.first_active > d.last_active).sum()))
    check('active months within 0..12', True, bool(d.active_months_in_period.between(0, len(PERIOD_MONTHS)).all()))
    check(f'active machine-months in period (Zac: {ZAC_ACTIVE_MONTHS:,})',
          ZAC_ACTIVE_MONTHS if len(d) == ZAC_DEVICES else None, int(d.active_months_in_period.sum()))
    compare_fu(d, fu_devices)

    pub = {'devices': d[COLUMNS],
           'match_summary': match_summary(d, eq),
           'model_type_crosswalk': model_type_crosswalk(d, eq)}
    check('crosswalk machines = devices on list', int(d.on_list.sum()), int(pub['model_type_crosswalk'].machines.sum()))
    labels_ok = all(pub['devices'][c].dropna().astype(str).str.fullmatch(p).all() for c, p in LABELS.items())
    check('machine, serial and host labels are pseudonyms', True, bool(labels_ok))
    real = real_strings(raw, eq, d)
    leaks = 0
    for name, df in pub.items():
        for col, n in text_leaks(df, real).items():
            leaks += n
            print(f'    LEAK in {PREFIX}{name}.{col}: {n} values')
    check('public text columns: no real serial / device id / case / account / url', 0, leaks)
    fails = [c for c in CHECKS if c['status'] == 'FAIL']
    if any('LEAK' in c['check'] or 'pseudonyms' in c['check'] for c in fails):
        log('privacy check failed: public files NOT written')
        return 1, pub

    out.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)
    for name, df in pub.items():
        df.to_csv(out / f'{PREFIX}{name}.csv', index=False)
        print(f'  wrote {PREFIX}{name}.csv ({len(df):,} rows) to --out')
    priv = d[['device', 'machine_id', 'serial_id', 'on_list', 'zero_stripped_list_serials']].rename(
        columns={'device': 'real_device_id', 'zero_stripped_list_serials': 'list_serial_if_zeros_stripped'})
    priv.to_csv(private / f'{PREFIX}private_serial_crosswalk.csv', index=False)
    pd.DataFrame({'host': list(hostmap.values()), 'clearview_url': list(hostmap.keys())}).to_csv(
        private / f'{PREFIX}private_host_map.csv', index=False)
    print(f'  wrote {PREFIX}private_serial_crosswalk.csv and {PREFIX}private_host_map.csv to --private (gitignored)')

    s = dict(zip(pub['match_summary'].measure, pub['match_summary'].value))
    print('\nSummary')
    for k in ('devices', 'devices with any transaction', 'active machine-months in period (all devices)',
              'listed machines', 'devices on list', 'listed machines networked',
              'listed machines networked and active in period',
              'leading-zero extra matches: devices (report only, not joined)'):
        print(f'  {k}: {s[k]:,}')
    print(f"  machine types on list: {pub['devices'].loc[on.index, 'machine_type'].nunique()}; "
          f"models on list with a device: {pub['model_type_crosswalk'].model.nunique()}")
    print(f'\n{len(CHECKS) - len(fails)}/{len(CHECKS)} checks pass or are informational'
          + (f"; FAILED: {[c['check'] for c in fails]}" if fails else ''))
    return (1 if fails else 0), pub


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True)
    ap.add_argument('--xlsx', default=str(common.XLS))
    ap.add_argument('--equipment', default=str(common.EQUIPMENT))
    ap.add_argument('--out', default=str(common.OUTPUTS / 'fleet' / 'db'))
    ap.add_argument('--private', default=str(common.PRIVATE / 'fleet_db'))
    ap.add_argument('--fu-devices', default=str(common.OUTPUTS / 'fu' / 'fu_devices.csv'))
    a = ap.parse_args(argv)
    status, _ = run(a.db, a.xlsx, a.equipment, a.out, a.private, a.fu_devices)
    return status


if __name__ == '__main__':
    sys.exit(main())
