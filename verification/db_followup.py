#!/usr/bin/env python3
"""Follow-up to verify_with_db.py: the last 10 telemetry codes before every ticket on the corrected clock, device
locations, and the event-time columns. Read-only; uses the (device, date) index; no full table scan.

Clock rules (settled):
  * case 'Date/Time Opened' is US Eastern wall time with DST (confirmed by IPA, 12 Oct 2026);
  * telemetry transaction_time_utc AND transaction_time_local both hold UTC (verify_with_db.py steps 5-6 on the full
    DB: zone shifts of +1/+2/+3 h against Eastern, a +1 h seasonal shift, no DST gap, and peaks at 06-07 h and
    14-15 h local time once read as UTC).
  => a ticket's anchor on the telemetry clock is opened_at localised to America/New_York and converted to UTC
     (+4 h in daylight time, +5 h in standard time). Zac's pilot compared the two clocks directly ("equal clock").

Parts (each isolated; one failure does not stop the others):
  F1  every device-matched ticket: events in the 30 days before the anchor and its last 10 non-success codes
      (as raw events and as distinct codes), with 0 / 30 / 60-minute guard bands before the anchor
  F2  a control window on the same machine 35 days earlier (chance baseline); flags whether another ticket is near
  F3  Zac's 30 pilot tickets: his equal-clock window (reproduced against his printed counts) vs the corrected window
  F4  device location fields (location_name, city, state, country) vs the ticket account and hospital location,
      and how much of the fleet a location label can attribute to an account
  F5  event_time_utc / event_time_offset and a whole-fleet clock check on a rowid-block sample

Colab (with common.py and verify_with_db.py in the same folder):
  import sys; sys.path.insert(0, '/content/verification')
  import db_followup as f
  f.run('/content/data/ipa_transaction_events_202508_202608.db',
        '/content/data/IPA_CaseHistory_Aug 2025-Aug2026.xlsx', '/content/fu_out', '/content/fu_private')
Local:
  python3 -I verification/db_followup.py --db PATH --xlsx PATH --out verification/outputs/fu --private data/private/fu

Privacy: --out receives pseudonymous files only (T#####, M#####, Customer NNN, Host NNN, Location NNNN, generic
labels, states and time-zone groups). Location names, cities and the location-to-account crosswalk go to --private.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import difflib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common  # noqa: E402
import verify_with_db as V  # noqa: E402
from common import clean  # noqa: E402

CASE_TZ = ZoneInfo('America/New_York')   # confirmed by IPA
UTC = dt.timezone.utc
LOOKBACK_DAYS = 30
LAST_N = 10
GUARDS_MIN = (0, 30, 60)
CONTROL_SHIFT_DAYS = 35
SAMPLE_BLOCKS, SAMPLE_BLOCK_ROWS = 600, 2500
TELEMETRY_FIRST, TELEMETRY_LAST = '2025-08-01', '2026-08-28'
ZAC_PILOT = [r['case_id'] for r in V.ZAC_EXPECTED['pilot_offset0']]
STATE_NAMES = {
    'ALABAMA': 'AL', 'ALASKA': 'AK', 'ARIZONA': 'AZ', 'ARKANSAS': 'AR', 'CALIFORNIA': 'CA', 'COLORADO': 'CO',
    'CONNECTICUT': 'CT', 'DELAWARE': 'DE', 'DISTRICT OF COLUMBIA': 'DC', 'FLORIDA': 'FL', 'GEORGIA': 'GA',
    'HAWAII': 'HI', 'IDAHO': 'ID', 'ILLINOIS': 'IL', 'INDIANA': 'IN', 'IOWA': 'IA', 'KANSAS': 'KS', 'KENTUCKY': 'KY',
    'LOUISIANA': 'LA', 'MAINE': 'ME', 'MARYLAND': 'MD', 'MASSACHUSETTS': 'MA', 'MICHIGAN': 'MI', 'MINNESOTA': 'MN',
    'MISSISSIPPI': 'MS', 'MISSOURI': 'MO', 'MONTANA': 'MT', 'NEBRASKA': 'NE', 'NEVADA': 'NV', 'NEW HAMPSHIRE': 'NH',
    'NEW JERSEY': 'NJ', 'NEW MEXICO': 'NM', 'NEW YORK': 'NY', 'NORTH CAROLINA': 'NC', 'NORTH DAKOTA': 'ND',
    'OHIO': 'OH', 'OKLAHOMA': 'OK', 'OREGON': 'OR', 'PENNSYLVANIA': 'PA', 'RHODE ISLAND': 'RI',
    'SOUTH CAROLINA': 'SC', 'SOUTH DAKOTA': 'SD', 'TENNESSEE': 'TN', 'TEXAS': 'TX', 'UTAH': 'UT', 'VERMONT': 'VT',
    'VIRGINIA': 'VA', 'WASHINGTON': 'WA', 'WEST VIRGINIA': 'WV', 'WISCONSIN': 'WI', 'WYOMING': 'WY',
    'ONTARIO': 'ON', 'QUEBEC': 'QC', 'NEWFOUNDLAND': 'NL', 'NEWFOUNDLAND AND LABRADOR': 'NL', 'NOVA SCOTIA': 'NS',
    'NEW BRUNSWICK': 'NB', 'PRINCE EDWARD ISLAND': 'PE', 'MANITOBA': 'MB', 'SASKATCHEWAN': 'SK', 'ALBERTA': 'AB',
    'BRITISH COLUMBIA': 'BC', 'NFLD': 'NL'}
NAME_STOP = {'the', 'inc', 'llc', 'of', 'at', 'and', 'co', 'corp', 'corporation', 'ltd'}


# ----------------------------------------------------------------------------------------------------------------
# small run harness (same conventions as verify_with_db.py)
# ----------------------------------------------------------------------------------------------------------------
class Run:
    def __init__(self, db_path, xlsx_path, out_dir, private_dir):
        self.db_path, self.xlsx_path = Path(db_path), Path(xlsx_path)
        self.out, self.private = Path(out_dir), Path(private_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.private.mkdir(parents=True, exist_ok=True)
        self.t0 = time.time()
        self.steps, self.facts, self.checks, self.files = {}, {}, [], {'public': [], 'private': []}
        self.state = {}

    def log(self, msg):
        print(f'[{time.time() - self.t0:8.1f}s] {msg}', flush=True)

    def save(self, df, name, private=False):
        folder, prefix = (self.private, 'fu_private_') if private else (self.out, 'fu_')
        path = folder / f'{prefix}{name}.csv'
        df.to_csv(path, index=False)
        self.files['private' if private else 'public'].append(path.name)
        return path

    def fact(self, step, key, value):
        self.facts.setdefault(step, {})[key] = V.jsonable(value)

    def check(self, step, name, expected, actual):
        ok = 'INFO' if expected is None else ('PASS' if expected == actual else 'FAIL')
        self.checks.append({'step': step, 'check': name, 'expected': V.jsonable(expected),
                            'actual': V.jsonable(actual), 'status': ok})
        self.log(f'  [{ok}] {name}: expected {expected}, actual {actual}')

    def step(self, key, title, fn):
        self.log(f'{key}: {title}')
        t = time.time()
        try:
            note = fn(self)
            self.steps[key] = {'title': title, 'status': 'done', 'seconds': round(time.time() - t, 1), 'note': note}
        except Exception as e:  # noqa: BLE001 - each part is isolated by design
            line = traceback.extract_tb(e.__traceback__)[-1].lineno if e.__traceback__ else None
            self.steps[key] = {'title': title, 'status': 'ERROR', 'seconds': round(time.time() - t, 1),
                               'note': f'{type(e).__name__} at line {line}'}
            self.log(f'  ERROR in {key}: {type(e).__name__} at line {line}')
            (self.private / f'fu_private_error_{key}.txt').write_text(traceback.format_exc())
        self.write_summary()

    def write_summary(self):
        counts = pd.Series([c['status'] for c in self.checks]).value_counts().to_dict() if self.checks else {}
        summary = {'generated_utc': dt.datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S'),
                   'database_file': self.db_path.name, 'elapsed_seconds': round(time.time() - self.t0, 1),
                   'check_counts': counts, 'steps': self.steps, 'checks': self.checks, 'facts': self.facts,
                   'files': self.files}
        (self.out / 'fu_summary.json').write_text(json.dumps(V.jsonable(summary), indent=2, default=str))
        md = ['# Follow-up summary (db_followup.py)', '',
              f'Database `{self.db_path.name}`; elapsed {summary["elapsed_seconds"]} s; checks {counts}.', '',
              '| part | status | seconds | note |', '|---|---|---:|---|']
        md += [f"| {k} | {v['status']} | {v['seconds']} | {v['note']} |" for k, v in self.steps.items()]
        md += ['', '## Key facts', '']
        for step, kv in self.facts.items():
            md.append(f'### {step}')
            md += [f'- **{k}**: {json.dumps(V.jsonable(v), default=str)}' for k, v in kv.items()]
            md.append('')
        if self.checks:
            md += ['## Checks', '', '| part | check | expected | actual | status |', '|---|---|---|---|---|']
            md += [f"| {c['step']} | {c['check']} | {json.dumps(c['expected'])} | {json.dumps(c['actual'])} | "
                   f"{c['status']} |" for c in self.checks]
        (self.out / 'fu_summary.md').write_text('\n'.join(md) + '\n')
        return summary


# ----------------------------------------------------------------------------------------------------------------
# setup: DB, columns, devices, cases with Zac's exact pseudonyms
# ----------------------------------------------------------------------------------------------------------------
def open_ro(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    conn.execute('PRAGMA query_only=ON')
    conn.execute('PRAGMA cache_size=-1048576')
    return conn


def columns(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({V.qi(table)})')]


def norm_state(s):
    if not isinstance(s, str) or not s.strip():
        return None
    s = re.sub(r'\s+', ' ', s.strip().upper().replace('.', ''))
    return s if len(s) == 2 else STATE_NAMES.get(s, s)


def zone_for_state(st):
    return V.GROUP.get(V.STATE_TZ.get(st)) if st else None


def setup(R):
    R.state['conn'] = conn = open_ro(R.db_path)
    ev_cols, dev_cols = columns(conn, 'transaction_events'), columns(conn, 'devices')
    R.state['ev_cols'], R.state['dev_cols'] = ev_cols, dev_cols
    R.fact('setup', 'transaction_events_columns', ev_cols)
    R.fact('setup', 'devices_columns', dev_cols)
    want = [c for c in ['external_device_id', 'device_status', 'machine_type', 'clearview_url', 'location_name',
                        'city', 'state', 'country'] if c in dev_cols]
    dev = pd.read_sql_query(f'SELECT {", ".join(want)} FROM devices', conn)
    dev['device'] = dev.external_device_id.map(clean)
    raw = common.load_raw(R.xlsx_path)
    maps = common.build_maps(raw, dev.external_device_id)
    cases = common.build_cases(raw, maps)
    cases['serial'] = raw['Serial #'].map(clean)
    cases['account_real'] = raw['Account Name'].map(clean)
    cases['location_real'] = raw['Hospital City, State, Zip'].map(clean)
    con = common.case_database(cases.drop(columns=['serial', 'account_real', 'location_real']))
    groups = dict(con.execute('SELECT case_id, service_group FROM case_base').fetchall())
    cases['service_group'] = cases.case_id.map(groups)
    dev['machine_id'] = dev.device.map(maps['serial'])
    hosts = sorted(set(dev.clearview_url.dropna())) if 'clearview_url' in dev else []
    hostmap = {h: f'Host {i:03d}' for i, h in enumerate(hosts, 1)}
    dev['host'] = dev.clearview_url.map(hostmap) if 'clearview_url' in dev else None
    R.state.update(dev=dev, raw=raw, maps=maps, cases=cases)
    matched = cases[cases.serial.isin(set(dev.device))]
    R.check('setup', 'device-matched tickets (Zac: 6,113)', 6113 if len(dev) == 7183 else None, len(matched))
    return f'{len(dev)} devices, {len(cases)} tickets, {len(matched)} device-matched'


# ----------------------------------------------------------------------------------------------------------------
# window helpers
# ----------------------------------------------------------------------------------------------------------------
def to_utc_naive(opened_at):
    """'YYYY-MM-DD HH:MM:SS' US Eastern wall time -> naive UTC datetime."""
    local = dt.datetime.fromisoformat(opened_at).replace(tzinfo=CASE_TZ)
    return local.astimezone(UTC).replace(tzinfo=None)


def fetch_device_events(conn, device, lo_date, hi_date):
    rows = conn.execute('SELECT transaction_time_utc, transaction_code FROM transaction_events '
                        'WHERE external_device_id=? AND transaction_date_local>=? AND transaction_date_local<=?',
                        (device, lo_date, hi_date)).fetchall()
    rows = [r for r in rows if r[0] is not None]
    if not rows:
        return np.array([], dtype='datetime64[s]'), np.array([], dtype=object)
    t = np.array([r[0][:19] for r in rows], dtype='datetime64[s]')
    c = np.array([r[1] for r in rows], dtype=object)
    order = np.lexsort((c.astype(str), t))
    return t[order], c[order]


def merged_intervals(spans):
    spans = sorted(spans)
    out = []
    for lo, hi in spans:
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def summarise_window(t, c, anchor, guard_min=0, lookback_days=LOOKBACK_DAYS, n=LAST_N):
    """Events in [anchor - lookback, anchor - guard) for one device, given sorted times t and codes c."""
    hi = np.datetime64(anchor - dt.timedelta(minutes=guard_min), 's')
    lo = np.datetime64(anchor - dt.timedelta(days=lookback_days), 's')
    i0, i1 = np.searchsorted(t, lo, 'left'), np.searchsorted(t, hi, 'left')
    tw, cw = t[i0:i1], c[i0:i1]
    ns = cw != '00'
    tn, cn = tw[ns][::-1], cw[ns][::-1]                          # most recent first
    hours = ((np.datetime64(anchor, 's') - tn) / np.timedelta64(1, 'h')).astype(float) if len(tn) else np.array([])
    last_events = list(zip(cn[:n], hours[:n]))
    distinct, seen = [], set()
    for k, h in zip(cn, hours):
        if k not in seen:
            seen.add(k)
            distinct.append((k, h))
            if len(distinct) == n:
                break
    occ = pd.Series(cn).value_counts().to_dict() if len(cn) else {}
    return {'all_events': int(len(tw)), 'non_success_events': int(ns.sum()), 'distinct_codes': int(len(set(cn))),
            'rank1_code': cn[0] if len(cn) else None,
            'rank1_hours_before': round(float(hours[0]), 3) if len(cn) else None,
            'last10_events': '|'.join(k for k, _ in last_events),
            'last10_events_hours_before': '|'.join(f'{h:.2f}' for _, h in last_events),
            'last10_distinct': '|'.join(k for k, _ in distinct),
            'last10_distinct_hours_before': '|'.join(f'{h:.2f}' for _, h in distinct),
            'last10_distinct_occurrences': '|'.join(str(occ[k]) for k, _ in distinct),
            'last10_distinct_buckets': '|'.join(V.LOOKUP.get(k, 'Malformed') for k, _ in distinct),
            'last3_events': '|'.join(k for k, _ in last_events[:3])}


# ----------------------------------------------------------------------------------------------------------------
# F1 + F2: every device-matched ticket, corrected anchor, guard bands, control window
# ----------------------------------------------------------------------------------------------------------------
def f1_tickets(R):
    conn, cases, dev = R.state['conn'], R.state['cases'], R.state['dev']
    m = cases[cases.serial.isin(set(dev.device))].copy()
    m['anchor_utc'] = pd.to_datetime(m.opened_at.map(to_utc_naive))
    m['utc_offset_added_h'] = (m.anchor_utc - pd.to_datetime(m.opened_at)).dt.total_seconds() / 3600
    m['control_anchor_utc'] = m.anchor_utc - pd.Timedelta(days=CONTROL_SHIFT_DAYS)
    # another ticket on the same machine within [control - 30 d, control + 2 d] makes the control "not clean"
    all_anchor = cases.assign(a=pd.to_datetime(cases.opened_at.map(to_utc_naive)))[['serial', 'a']]
    by_serial = {s: np.sort(g.a.values.astype('datetime64[s]')) for s, g in all_anchor.groupby('serial')}

    def clean_control(row):
        a = by_serial[row.serial]
        lo = np.datetime64(row.control_anchor_utc - pd.Timedelta(days=LOOKBACK_DAYS), 's')
        hi = np.datetime64(row.control_anchor_utc + pd.Timedelta(days=2), 's')
        return not bool(((a >= lo) & (a <= hi)).any())

    m['control_clean'] = [clean_control(r) for r in m.itertuples()]
    span_lo = (m.control_anchor_utc - pd.Timedelta(days=LOOKBACK_DAYS + 1)).dt.strftime('%Y-%m-%d')
    span_hi = (m.anchor_utc + pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    m['_lo'], m['_hi'] = span_lo, span_hi
    rows, n_dev, n_rows = [], 0, 0
    devices = m.serial.unique()
    for i, serial in enumerate(devices, 1):
        g = m[m.serial == serial]
        times, codes = [], []
        for lo, hi in merged_intervals(list(zip(g._lo, g._hi))):
            t, c = fetch_device_events(conn, serial, lo, hi)
            times.append(t)
            codes.append(c)
        t = np.concatenate(times) if times else np.array([], dtype='datetime64[s]')
        c = np.concatenate(codes) if codes else np.array([], dtype=object)
        n_rows += len(t)
        n_dev += 1
        for r in g.itertuples():
            base = {'case_id': r.case_id, 'machine_id': r.machine_id, 'opened_at_eastern': r.opened_at,
                    'anchor_utc': r.anchor_utc.strftime('%Y-%m-%d %H:%M:%S'),
                    'utc_offset_added_h': r.utc_offset_added_h, 'model': r.model, 'record_type': r.record_type,
                    'status': r.status, 'service_group': r.service_group, 'trouble_code': r.trouble_code,
                    'category': r.category, 'subcategory': r.subcategory,
                    'lookback_truncated': (r.anchor_utc - pd.Timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')
                    < TELEMETRY_FIRST,
                    'after_telemetry_end': r.anchor_utc.strftime('%Y-%m-%d') > TELEMETRY_LAST}
            for gmin in GUARDS_MIN:
                rows.append({**base, 'window': f'corrected_guard{gmin}', 'control_clean': None,
                             **summarise_window(t, c, r.anchor_utc.to_pydatetime(), gmin)})
            rows.append({**base, 'window': f'control_minus{CONTROL_SHIFT_DAYS}d', 'control_clean': r.control_clean,
                         **summarise_window(t, c, r.control_anchor_utc.to_pydatetime(), 0)})
        if i % 500 == 0:
            R.log(f'  {i:,}/{len(devices):,} machines, {n_rows:,} events read')
    out = pd.DataFrame(rows)
    R.save(out, 'ticket_last10')
    R.state['ticket_last10'] = out
    main = out[out.window == 'corrected_guard0']
    usable = main[~main.lookback_truncated & ~main.after_telemetry_end]
    R.fact('F1', 'tickets', len(main))
    R.fact('F1', 'machines', n_dev)
    R.fact('F1', 'events_read', n_rows)
    R.fact('F1', 'utc_offset_added_hours', main.utc_offset_added_h.value_counts().to_dict())
    R.fact('F1', 'tickets_with_full_30d_lookback', len(usable))
    for label, sub in [('all', usable), ('unplanned', usable[~usable.service_group.isin(
            ['Planned work', 'Cancelled request', 'Duplicate case'])])]:
        R.fact('F1', f'{label}: tickets with any transaction in 30 d', int((sub.all_events > 0).sum()))
        R.fact('F1', f'{label}: tickets with >=1 non-success code in 30 d', int((sub.non_success_events > 0).sum()))
        R.fact('F1', f'{label}: tickets with >=10 distinct non-success codes in 30 d',
               int((sub.distinct_codes >= 10).sum()))
        R.fact('F1', f'{label}: median distinct non-success codes in 30 d', float(sub.distinct_codes.median()))
        R.fact('F1', f'{label}: median hours from rank-1 code to anchor', float(sub.rank1_hours_before.median()))
    # how the guard bands change the last-10 lists
    piv = out[out.window.str.startswith('corrected')].pivot_table(index='case_id', columns='window',
                                                                  values='last10_distinct', aggfunc='first')
    for gmin in GUARDS_MIN[1:]:
        col = f'corrected_guard{gmin}'
        R.fact('F1', f'last-10 distinct list unchanged with a {gmin}-min guard band',
               int((piv[col] == piv['corrected_guard0']).sum()))
    ctrl = out[(out.window == f'control_minus{CONTROL_SHIFT_DAYS}d') & out.control_clean.astype(bool)]
    R.fact('F2', 'clean control windows', len(ctrl))
    R.fact('F2', 'control: windows with >=1 non-success code', int((ctrl.non_success_events > 0).sum()))
    R.fact('F2', 'control: median distinct non-success codes', float(ctrl.distinct_codes.median()) if len(ctrl)
           else None)
    return f'{len(main)} tickets on {n_dev} machines; {n_rows:,} events read'


# ----------------------------------------------------------------------------------------------------------------
# F3: Zac's pilot, his equal-clock window vs the corrected window
# ----------------------------------------------------------------------------------------------------------------
def f3_pilot(R):
    conn, cases = R.state['conn'], R.state['cases']
    ids = R.state.get('pilot_ids') or ZAC_PILOT
    is_zac = ids == ZAC_PILOT
    pilot = cases[cases.case_id.isin(ids)].copy()
    R.check('F3', 'pilot ids present in this workbook', len(ids), len(pilot))
    expected = {r['case_id']: r for r in V.ZAC_EXPECTED['pilot_offset0']} if is_zac else {}
    rows, repro = [], 0
    for r in pilot.itertuples():
        naive = dt.datetime.fromisoformat(r.opened_at)
        corrected = to_utc_naive(r.opened_at)
        lo = (naive - dt.timedelta(days=32)).strftime('%Y-%m-%d')
        hi = (corrected + dt.timedelta(days=2)).strftime('%Y-%m-%d')
        t, c = fetch_device_events(conn, r.serial, lo, hi)
        zac = summarise_window(t, c, naive, 0)
        cor = summarise_window(t, c, corrected, 0)
        gap = (t >= np.datetime64(naive, 's')) & (t < np.datetime64(corrected, 's'))
        gap_ns = gap & (c != '00')
        e = expected.get(r.case_id, {})
        same = (zac['non_success_events'] == e.get('non_success_events') and
                zac['distinct_codes'] == e.get('distinct_codes') and zac['all_events'] == e.get('all_events'))
        repro += bool(same)
        z10, c10 = set(filter(None, zac['last10_distinct'].split('|'))), set(filter(None,
                                                                               cor['last10_distinct'].split('|')))
        rows.append({'case_id': r.case_id, 'service_group': r.service_group, 'trouble_code': r.trouble_code,
                     'category': r.category, 'hours_added': (corrected - naive).total_seconds() / 3600,
                     'zac_counts_reproduced': same,
                     'gap_events': int(gap.sum()), 'gap_non_success_events': int(gap_ns.sum()),
                     'gap_codes': '|'.join(pd.unique(c[gap_ns][::-1])),
                     **{f'zac_{k}': v for k, v in zac.items()}, **{f'corrected_{k}': v for k, v in cor.items()},
                     'rank1_same': zac['rank1_code'] == cor['rank1_code'],
                     'last3_same': zac['last3_events'] == cor['last3_events'],
                     'last10_distinct_same_list': zac['last10_distinct'] == cor['last10_distinct'],
                     'last10_distinct_jaccard': round(len(z10 & c10) / len(z10 | c10), 3) if (z10 | c10) else None})
    p = pd.DataFrame(rows).sort_values('case_id')
    R.save(p, 'pilot_equal_clock_vs_corrected')
    R.check('F3', "Zac's equal-clock counts reproduced (30-day window, offset 0)", len(pilot) if is_zac else None,
            repro)
    has = p[p.corrected_non_success_events > 0]
    R.fact('F3', 'tickets with non-success codes (equal clock / corrected)',
           [int((p.zac_non_success_events > 0).sum()), int((p.corrected_non_success_events > 0).sum())])
    R.fact('F3', 'tickets with non-success codes in the 4-5 h Zac missed', int((p.gap_non_success_events > 0).sum()))
    R.fact('F3', 'rank-1 code unchanged', f'{int(has.rank1_same.sum())}/{len(has)}')
    R.fact('F3', 'last-3 events unchanged', f'{int(has.last3_same.sum())}/{len(has)}')
    R.fact('F3', 'last-10 distinct list unchanged', f'{int(has.last10_distinct_same_list.sum())}/{len(has)}')
    R.fact('F3', 'median Jaccard of last-10 distinct sets', float(has.last10_distinct_jaccard.median())
           if len(has) else None)
    return f'{len(p)} pilot tickets'


# ----------------------------------------------------------------------------------------------------------------
# F4: device location fields vs ticket account / hospital location
# ----------------------------------------------------------------------------------------------------------------
def norm_name(s):
    if not isinstance(s, str):
        return None
    s = s.casefold().replace('&', ' and ').replace('?', "'")
    s = re.sub(r"[^\w\s]", ' ', s)
    toks = [w for w in s.split() if w not in NAME_STOP]
    return ' '.join(toks) or None


def name_match(a, b):
    if not (isinstance(a, str) and a.strip() and isinstance(b, str) and b.strip()):
        return 'missing'
    if a.strip().casefold() == b.strip().casefold():
        return 'exact'
    na, nb = norm_name(a), norm_name(b)
    if na == nb:
        return 'normalised'
    if na and nb and (na in nb or nb in na):
        return 'contained'
    ta, tb = set(na.split()), set(nb.split())
    if difflib.SequenceMatcher(None, na, nb).ratio() >= 0.85 or len(ta & tb) / max(len(ta | tb), 1) >= 0.6:
        return 'fuzzy'
    return 'different'


def f4_locations(R):
    conn, dev, cases = R.state['conn'], R.state['dev'].copy(), R.state['cases']
    loc_cols = [c for c in ['location_name', 'city', 'state', 'country'] if c in dev]
    cov = [{'field': f, 'non_blank_devices': int(dev[f].map(lambda x: isinstance(x, str) and bool(x.strip())).sum()),
            'distinct_values': int(dev[f].map(clean).nunique()), 'devices': len(dev)} for f in loc_cols]
    R.save(pd.DataFrame(cov), 'device_field_coverage')
    # first/last active date per device via the (device, date) index
    first_last = {}
    for d in dev.device:
        lo, hi = conn.execute('SELECT MIN(transaction_date_local), MAX(transaction_date_local) FROM transaction_events '
                              'WHERE external_device_id=?', (d,)).fetchone()
        first_last[d] = (lo, hi)
    dev['first_active'] = dev.device.map(lambda d: first_last[d][0])
    dev['last_active'] = dev.device.map(lambda d: first_last[d][1])
    dev['transacting'] = dev.first_active.notna()
    dev['state_norm'] = dev.state.map(norm_state) if 'state' in dev else None
    dev['zone'] = dev.state_norm.map(zone_for_state) if 'state' in dev else None
    R.state['dev'] = dev
    if 'location_name' not in dev:
        return 'no location_name column'
    # ticket side: modal account and hospital location per serial
    tk = cases[['serial', 'customer', 'account_real', 'location_real', 'opened_at']].copy()
    geo = tk.location_real.map(lambda s: V.LOC_RE.match(s.strip()) if isinstance(s, str) else None)
    tk['t_city'] = geo.map(lambda g: g.group('city').strip() if g else None)
    tk['t_state'] = geo.map(lambda g: g.group('st').upper() if g else None)
    modal = (tk.sort_values('opened_at').groupby('serial')
             .agg(customer=('customer', lambda s: s.value_counts().index[0]),
                  account_real=('account_real', lambda s: s.value_counts().index[0]),
                  t_city=('t_city', lambda s: s.value_counts().index[0] if s.notna().any() else None),
                  t_state=('t_state', lambda s: s.value_counts().index[0] if s.notna().any() else None),
                  tickets=('customer', 'size')).reset_index())
    d = dev.merge(modal, left_on='device', right_on='serial', how='left')
    d['loc_norm'] = d.location_name.map(norm_name)
    locs = sorted(set(d.loc_norm.dropna()))
    locmap = {s: f'Location {i:04d}' for i, s in enumerate(locs, 1)}
    d['location'] = d.loc_norm.map(locmap)
    tick = d[d.customer.notna()].copy()
    tick['name_match'] = [name_match(a, b) for a, b in zip(tick.location_name, tick.account_real)]
    tick['state_match'] = np.where(tick.state_norm.isna() | tick.t_state.isna(), 'missing',
                                   np.where(tick.state_norm == tick.t_state, 'same', 'different'))
    tick['city_match'] = [('missing' if not (isinstance(a, str) and isinstance(b, str)) else
                           'same' if norm_name(a) == norm_name(b) else 'different')
                          for a, b in zip(tick.city if 'city' in tick else [None] * len(tick), tick.t_city)]
    agree = []
    for col in ['name_match', 'state_match', 'city_match']:
        for k, v in tick[col].value_counts().items():
            agree.append({'comparison': col, 'result': k, 'ticketed_devices': int(v),
                          'share_pct': round(100 * v / len(tick), 2)})
    R.save(pd.DataFrame(agree), 'location_vs_ticket_agreement')
    # location -> accounts (through ticketed devices); classify locations; assign the fleet
    acc = tick.dropna(subset=['location']).groupby('location').customer.nunique()
    d['location_class'] = d.location.map(lambda L: 'No location' if not isinstance(L, str) else
                                         'No tickets' if L not in acc.index else
                                         'Single-account' if acc[L] == 1 else 'Multi-account')
    single = tick.dropna(subset=['location']).groupby('location').customer.agg(lambda s: s.value_counts().index[0])
    d['assigned_customer'] = np.where(d.location_class == 'Single-account', d.location.map(single), None)
    cls = (d.groupby('location_class').agg(locations=('location', 'nunique'), devices=('device', 'size'),
                                           ticketed_devices=('customer', lambda s: int(s.notna().sum())),
                                           transacting_devices=('transacting', 'sum')).reset_index())
    cls['share_of_fleet_pct'] = (100 * cls.devices / len(d)).round(2)
    R.save(cls, 'location_classes')
    acct = (d[d.assigned_customer.notna()].groupby('assigned_customer')
            .agg(devices_by_location=('device', 'size'), transacting=('transacting', 'sum'),
                 ticketed_devices=('customer', lambda s: int(s.notna().sum()))).reset_index()
            .rename(columns={'assigned_customer': 'customer'}))
    tix = cases.groupby('customer').size().rename('tickets_all').reset_index()
    acct = acct.merge(tix, on='customer', how='left')
    acct['unticketed_devices_added'] = acct.devices_by_location - acct.ticketed_devices
    R.save(acct, 'account_fleet_by_location')
    # location vs host consistency
    lh = d.dropna(subset=['location', 'host']).groupby('location').host.nunique().value_counts().sort_index()
    hl = d.dropna(subset=['location', 'host']).groupby('host').location.nunique().value_counts().sort_index()
    R.save(pd.DataFrame({'hosts_per_location': lh.index, 'locations': lh.values}), 'hosts_per_location')
    R.save(pd.DataFrame({'locations_per_host': hl.index, 'hosts': hl.values}), 'locations_per_host')
    # public device table (pseudonymous) and private crosswalk
    pub = d[['machine_id', 'host', 'location', 'location_class', 'assigned_customer', 'customer', 'state_norm', 'zone',
             'device_status', 'machine_type', 'first_active', 'last_active', 'transacting']].rename(
        columns={'customer': 'ticket_customer', 'state_norm': 'device_state'})
    R.save(pub, 'devices')
    R.save(tick[['machine_id', 'location', 'location_name', 'account_real', 'customer', 'name_match', 'city',
                 't_city', 'state_norm', 't_state']].rename(columns={'location_name': 'device_location_name',
                                                                      'account_real': 'ticket_account'}),
           'location_account_crosswalk', private=True)
    R.save(pd.DataFrame({'location': list(locmap.values()), 'location_name_normalised': list(locmap.keys())}),
           'location_map', private=True)
    R.fact('F4', 'devices with a location_name', int(d.loc_norm.notna().sum()))
    R.fact('F4', 'distinct locations (normalised)', len(locs))
    R.fact('F4', 'ticketed devices: location_name vs ticket account', tick.name_match.value_counts().to_dict())
    R.fact('F4', 'ticketed devices: device state vs ticket state', tick.state_match.value_counts().to_dict())
    R.fact('F4', 'fleet share by location class (%)', dict(zip(cls.location_class, cls.share_of_fleet_pct)))
    R.fact('F4', 'devices attributable to one account via location (incl. unticketed)',
           int(d.assigned_customer.notna().sum()))
    R.fact('F4', 'accounts with a location-based fleet', int(acct.customer.nunique()))
    return f'{len(d)} devices; {len(locs)} locations'


# ----------------------------------------------------------------------------------------------------------------
# F5: event_time columns + whole-fleet clock check on a rowid-block sample
# ----------------------------------------------------------------------------------------------------------------
def f5_sample(R):
    conn, dev, ev_cols = R.state['conn'], R.state['dev'], R.state['ev_cols']
    extra = [c for c in ['event_time_utc', 'event_time_offset'] if c in ev_cols]
    lo, hi = conn.execute('SELECT MIN(rowid), MAX(rowid) FROM transaction_events').fetchone()
    starts = np.linspace(lo, max(lo, hi - SAMPLE_BLOCK_ROWS), SAMPLE_BLOCKS).astype(np.int64)
    cols = ['external_device_id', 'transaction_time_utc', 'transaction_date_local', 'transaction_code'] + extra
    parts = []
    for s in np.unique(starts):
        parts.append(pd.DataFrame(conn.execute(f'SELECT {", ".join(cols)} FROM transaction_events WHERE rowid BETWEEN '
                                               f'? AND ?', (int(s), int(s) + SAMPLE_BLOCK_ROWS - 1)).fetchall(),
                                  columns=cols))
    smp = pd.concat(parts, ignore_index=True)
    zone = dict(zip(dev.device, dev.zone)) if 'zone' in dev else {}
    smp['zone'] = smp.external_device_id.map(lambda x: zone.get(clean(x)) or 'Unknown')
    smp['period'] = smp.transaction_date_local.map(V.dst_period)
    smp['tu'] = pd.to_datetime(smp.transaction_time_utc, errors='coerce')
    R.fact('F5', 'sample rows', len(smp))
    R.fact('F5', 'sample rows by device-state zone', smp.zone.value_counts().to_dict())
    # whole-fleet clock check, zones from the device's own state
    smp['hour'] = smp.tu.dt.hour
    b = smp.dropna(subset=['hour']).groupby(['zone', 'period', 'hour']).size().rename('n').reset_index()
    zones = [z for z in V.ZONE_ORDER if z in set(b.zone)]
    pz = V.profiles(b[b.zone.isin(zones)], 'hour', zones)
    obs_zone, obs_dst, rows = {}, {}, []
    for p in ('DST', 'Standard'):
        ref = pz.get(('Eastern', p))
        for z in zones:
            if z == 'Eastern' or ref is None or (z, p) not in pz or pz[(z, p)].sum() < 2000 or ref.sum() < 2000:
                continue
            est = V.shift_estimate(pz[(z, p)], ref)
            if est:
                obs_zone[(z, p)] = est[0]
                rows.append({'test': 'zone vs Eastern', 'zone': z, 'period': p, 'shift_h': round(est[0], 2),
                             'rows': int(pz[(z, p)].sum())})
    for z in zones:
        s_, d_ = pz.get((z, 'Standard')), pz.get((z, 'DST'))
        if s_ is not None and d_ is not None and s_.sum() >= 2000 and d_.sum() >= 2000:
            est = V.shift_estimate(s_, d_)
            if est:
                obs_dst[z] = est[0]
                rows.append({'test': 'Standard vs DST', 'zone': z, 'period': 'Std-DST', 'shift_h': round(est[0], 2),
                             'rows': int(pz[(z, 'Standard')].sum() + pz[(z, 'DST')].sum())})
    R.save(pd.DataFrame(rows), 'clock_shifts_device_state')
    scored, verdict = V.score_hypotheses(obs_zone, obs_dst, 0.5)
    consistent = [h for h, v in verdict.items() if v['consistent']]
    R.fact('F5', 'clock hypotheses consistent with device-state zones', consistent)
    R.check('F5', 'whole-fleet clock verdict (device-state zones)', ['utc'], consistent)
    # event_time_offset and event_time_utc
    if 'event_time_offset' in smp:
        off = pd.to_numeric(smp.event_time_offset, errors='coerce')
        R.fact('F5', 'event_time_offset values (top 15)', off.round(2).value_counts(dropna=False).head(15).to_dict())
        exp = [V.ZONE_OFFSETS[z][1 if p == 'DST' else 0] if z in V.ZONE_OFFSETS else np.nan
               for z, p in zip(smp.zone, smp.period)]
        exp = pd.Series(exp, index=smp.index, dtype=float)
        known = exp.notna() & off.notna()
        tab = (pd.DataFrame({'zone': smp.zone, 'period': smp.period, 'offset': off.round(2)})
               .groupby(['zone', 'period', 'offset'], dropna=False).size().rename('rows').reset_index())
        R.save(tab, 'event_time_offset_by_zone')
        R.fact('F5', 'share of rows where event_time_offset == UTC offset of device zone',
               round(float((off[known] == exp[known]).mean()), 4) if known.any() else None)
        R.fact('F5', 'share of rows where event_time_offset == minus UTC offset of device zone',
               round(float((off[known] == -exp[known]).mean()), 4) if known.any() else None)
        R.fact('F5', 'share of rows where event_time_offset == 0', round(float((off == 0).mean()), 4))
    if 'event_time_utc' in smp:
        et = pd.to_datetime(smp.event_time_utc, errors='coerce')
        lag = (et - smp.tu).dt.total_seconds() / 3600
        q = lag.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).round(3)
        R.fact('F5', 'event_time_utc - transaction_time_utc (hours) quantiles', q.to_dict())
        R.fact('F5', 'share of rows with event_time_utc == transaction_time_utc', round(float((lag == 0).mean()), 4))
        lz = (pd.DataFrame({'zone': smp.zone, 'period': smp.period, 'lag_h': lag}).dropna()
              .groupby(['zone', 'period']).lag_h.describe(percentiles=[0.05, 0.5, 0.95]).round(3).reset_index())
        R.save(lz, 'event_time_lag_by_zone')
    return f'{len(smp):,} sampled rows'


def run(db_path, xlsx_path, out_dir='fu_out', private_dir='fu_private', pilot_ids=None):
    """pilot_ids: defaults to Zac's 30 pilot tickets (pass other T##### ids only for testing)."""
    R = Run(db_path, xlsx_path, out_dir, private_dir)
    R.state['pilot_ids'] = list(pilot_ids) if pilot_ids else None
    R.log(f'db_followup: db={R.db_path.name} xlsx={R.xlsx_path.name} out={R.out}')
    R.step('setup', 'open DB, devices, cases', setup)
    if R.steps['setup']['status'] != 'done':
        return R.write_summary()
    R.step('F4', 'device location fields vs ticket accounts', f4_locations)
    R.step('F1', f'last {LAST_N} codes for every device-matched ticket (+ control windows)', f1_tickets)
    R.step('F3', "Zac's pilot: equal clock vs corrected clock", f3_pilot)
    R.step('F5', 'event_time columns and whole-fleet clock check (sample)', f5_sample)
    R.state['conn'].close()
    s = R.write_summary()
    R.log(f"done: checks {s['check_counts']}; summary: {R.out / 'fu_summary.md'}")
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True)
    ap.add_argument('--xlsx', default=str(common.XLS))
    ap.add_argument('--out', default=str(common.OUTPUTS / 'fu'))
    ap.add_argument('--private', default=str(common.PRIVATE / 'fu'))
    a = ap.parse_args(argv)
    s = run(a.db, a.xlsx, a.out, a.private)
    return 1 if any(v['status'] == 'ERROR' for v in s['steps'].values()) else 0


if __name__ == '__main__':
    sys.exit(main())
