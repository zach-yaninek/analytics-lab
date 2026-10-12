#!/usr/bin/env python3
"""End-to-end test of verify_with_db.py on synthetic fixtures with planted answers.

Builds three fake databases + workbooks under data/derived/fixture/ (gitignored, FAKE data only), runs the
verification on each with the fixture's own expected values, and asserts:
  * no step errors and no failed checks;
  * the combined clock verdict recovers the planted clock.
It also exercises the full-scan fallback (--no-chunk) and the index-only mode (--skip-scans).

It also runs db_followup.py on an extended fixture (the real DB's location and event-time columns) and checks the
last-10 code lists against an independent plain-pandas recomputation.

Run:  cd /home/user/analytics-lab && python3 -I verification/tests/run_fixture_tests.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import contextlib  # noqa: E402
import io  # noqa: E402

import json  # noqa: E402
import sqlite3  # noqa: E402

import pandas as pd  # noqa: E402

import common  # noqa: E402
import db_followup  # noqa: E402
import make_fixture  # noqa: E402
import verify_with_db  # noqa: E402

BASE = common.DERIVED / 'fixture'
VARIANTS = [  # name, clock, ingestion column, indexes, seed, extra run options
    ('local', 'local', 'ingested_at_utc', 'full', 7, {}),
    ('utc', 'utc', 'received_at', 'none', 11, {}),
    ('local_noingest', 'local', '', 'none', 23, {}),
    ('local_nochunk', 'local', 'ingested_at_utc', 'full', 7, {'no_chunk': True}),
]


def run_variant(name, clock, ingest, indexes, seed, opts):
    out = BASE / name
    db, xlsx, truth = make_fixture.build(out, clock, ingest, indexes, seed=seed)
    with contextlib.redirect_stdout(io.StringIO()) as log:
        s = verify_with_db.run(db, xlsx, out / 'out', out / 'private', expected_json=truth, chunk_rows=100_000,
                               **opts)
    (out / 'run.log').write_text(log.getvalue())
    errors = [k for k, v in s['steps'].items() if v['status'] == 'ERROR']
    fails = [c['check'] for c in s['checks'] if c['status'] == 'FAIL']
    verdict = s['decisions'].get('clock_verdict', {}).get('hypothesis')
    planted = 'machine_local_dst' if clock == 'local' else 'utc'
    ok = not errors and not fails and verdict == planted
    print(f"{name:15s} checks {s['check_counts']}  verdict={verdict}  planted={planted}  "
          f"{'OK' if ok else 'PROBLEM'}" + (f'  errors={errors}' if errors else '') + (f'  fails={fails}' if fails
                                                                                    else ''))
    return ok


def independent_last10(db, xlsx, case_ids):
    """Plain-pandas recomputation of the corrected-clock last-10 lists (no db_followup code)."""
    raw = common.load_raw(xlsx)
    cmap = common.build_maps(raw)['case']
    t = pd.DataFrame({'case_id': raw['Case Number'].map(common.clean).map(cmap),
                      'serial': raw['Serial #'].map(common.clean),
                      'opened': pd.to_datetime(raw['Date/Time Opened'])})
    t = t[t.case_id.isin(case_ids)]
    t['anchor'] = (t.opened.dt.tz_localize('America/New_York').dt.tz_convert('UTC').dt.tz_localize(None))
    con = sqlite3.connect(db)
    out = {}
    for serial, g in t.groupby('serial'):
        ev = pd.read_sql_query('SELECT transaction_time_utc AS tu, transaction_code AS code FROM transaction_events '
                               'WHERE external_device_id=?', con, params=(serial,))
        ev['tu'] = pd.to_datetime(ev.tu)
        ev = ev.dropna(subset=['tu']).sort_values(['tu', 'code'])
        for r in g.itertuples():
            w = ev[(ev.tu >= r.anchor - pd.Timedelta(days=30)) & (ev.tu < r.anchor) & (ev.code != '00')].iloc[::-1]
            out[r.case_id] = ('|'.join(w.code.head(10)), '|'.join(pd.unique(w.code)[:10]))
    con.close()
    return out


def run_followup():
    """db_followup.py on an extended fixture (real DB's extra columns) with planted answers."""
    out = BASE / 'extended'
    db, xlsx, truth = make_fixture.build(out, 'utc', '', 'full', seed=11, extended=True)
    truth = json.loads(truth.read_text())
    ids = sorted(common.build_maps(common.load_raw(xlsx))['case'].values())[::9][:30]
    with contextlib.redirect_stdout(io.StringIO()) as log:
        s = db_followup.run(db, xlsx, out / 'fu_out', out / 'fu_private', pilot_ids=ids)
    (out / 'fu_run.log').write_text(log.getvalue())
    errors = [k for k, v in s['steps'].items() if v['status'] != 'done']
    fails = [c['check'] for c in s['checks'] if c['status'] == 'FAIL']
    f = s['facts']
    last10 = pd.read_csv(out / 'fu_out' / 'fu_ticket_last10.csv', dtype=str, keep_default_na=False)
    main = last10[last10.window == 'corrected_guard0']
    ind = independent_last10(db, xlsx, set(main.case_id))
    agree = sum(ind.get(r.case_id) == (r.last10_events, r.last10_distinct) for r in main.itertuples())
    problems = []
    if errors or fails:
        problems.append(f'errors={errors} fails={fails}')
    if len(main) != truth['linkage']['matched_cases']:
        problems.append(f"tickets {len(main)} != matched {truth['linkage']['matched_cases']}")
    if agree != len(main):
        problems.append(f'last-10 lists agree with independent pandas for {agree}/{len(main)} tickets')
    if f['F4']['ticketed devices: location_name vs ticket account'] != truth['extended']['name_match_ticketed_devices']:
        problems.append('location name-match counts differ from planted')
    if f['F5']['share of rows where event_time_offset == minus UTC offset of device zone'] < 0.99:
        problems.append('event_time_offset convention not recovered')
    ok = not problems
    print(f"{'followup':15s} steps {[k for k in s['steps']]}  last-10 agree {agree}/{len(main)}  "
          f"{'OK' if ok else 'PROBLEM ' + '; '.join(problems)}")
    return ok


def main():
    results = [run_variant(*v) for v in VARIANTS]
    results.append(run_followup())
    # index-only mode: steps 0-3, the pilot and the indexed DST-transition test must run without errors
    out = BASE / 'local'
    with contextlib.redirect_stdout(io.StringIO()):
        s = verify_with_db.run(out / 'fake_telemetry.db', out / 'fake_cases.xlsx', out / 'out_skip',
                               out / 'private_skip', skip_scans=True, expected_json=out / 'fixture_truth.json')
    errors = [k for k, v in s['steps'].items() if v['status'] == 'ERROR']
    ran = [k for k, v in s['steps'].items() if v['status'] == 'done']
    ok = not errors and {'0', '1', '2', '3', '4b', '6'} <= set(ran)
    print(f"{'skip_scans':15s} steps done {ran}  checks {s['check_counts']}  {'OK' if ok else 'PROBLEM'}")
    results.append(ok)
    print('ALL OK' if all(results) else 'SOME PROBLEMS')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
