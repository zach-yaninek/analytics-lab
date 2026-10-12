#!/usr/bin/env python3
"""End-to-end test of verify_with_db.py on synthetic fixtures with planted answers.

Builds three fake databases + workbooks under data/derived/fixture/ (gitignored, FAKE data only), runs the
verification on each with the fixture's own expected values, and asserts:
  * no step errors and no failed checks;
  * the combined clock verdict recovers the planted clock.
It also exercises the full-scan fallback (--no-chunk) and the index-only mode (--skip-scans).

Run:  cd /home/user/analytics-lab && python3 -I verification/tests/run_fixture_tests.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import contextlib  # noqa: E402
import io  # noqa: E402

import common  # noqa: E402
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


def main():
    results = [run_variant(*v) for v in VARIANTS]
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
