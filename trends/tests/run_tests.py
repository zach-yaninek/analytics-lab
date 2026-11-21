#!/usr/bin/env python3
"""The whole test suite on synthetic data (no IPA data needed). Prints ALL OK or SOME PROBLEMS; exit 1 on a problem.

  python3 -I trends/tests/run_tests.py            everything (about 10-20 minutes)
  python3 -I trends/tests/run_tests.py --quick    smaller fixture, fewer cadences and variants (a few minutes)
  python3 -I trends/tests/run_tests.py --no-parity --no-notebook

  1. unit tests (hand-computed values)
  2. parity with verification/ (MIT repository only)
  3. cadences: quarterly (calendar, data-start anchor, fiscal), monthly, 2, 4, 5, 6 and 12 months, explicit edges:
     every run passes its runtime checks; tickets and machine-months add up to the same totals at every cadence;
     HISTORY_MONTHS changes no number
  4. planted effects: the Deposit Door rise and the alEx Computer Board fall in 2026 Q3 are flagged; the Touchscreen
     2022-23 install cohort stands out; a null fixture's false alarms are counted
  4b. install cohorts: Touchscreen x3 on 2025 installs stands out in the 2026 Q1 back-run and the default run while
     the 2026 cohort is still filling up; a pure age effect (Touchscreen x3 at age 3-5 years) makes no cohort stand out;
     in a 2024 Q4 back-run each row names its own window and the short history skips the interior same-age check
  5. publishing: files, manifest, privacy scan, byte-identical reruns, a planted leak stops publication and is
     recorded in failed/; a file locked in latest/ stops the swap (E30) and leaves latest/ whole
  5b. privacy scan: only trusted words exempt a one-word real string (a city typed into Model stops publication;
     single-word city names that equal package words do not; PRIVACY_ALLOW lets a genuine collision through), and
     the executed-notebook scan exempts exactly what the publish scan exempts
  6. export drift: title rows, another sheet name, a renamed header, a split Category, a renamed Trouble Code, a
     duplicate case, dates as text, mixed date formats, a Central-time export, a closed-only export, a report filtered
     to the quarter end, a one-month spike, removed machines, blank install dates and blank list fields
  7. the notebook headless (papermill or nbclient) at 3, 1 and 5 months, leaving no temporary folder; BASE_DIR in a
     parameter file; a back-run (its notebook in its own run folder, latest/ untouched); E01 and E10 give exit 2
     and a failure record on both engines; a misspelt parameter stops it (exit 2); the command line and the
     notebook write identical tables
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TRENDS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRENDS))
sys.path.insert(0, str(TRENDS / 'tests'))

import pandas as pd  # noqa: E402

RESULTS = []
QUICK = {'on': False}
TMP = Path(tempfile.mkdtemp(prefix='ipa_trends_tests_'))


def ok(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f'  ({detail})' if detail and not cond else ''))
    return bool(cond)


def fixture(name, **kw):
    import make_trend_fixture as MF
    out = TMP / name
    if not (out / 'truth.json').exists():
        MF.build(out, **kw)
    return out, json.loads((out / 'truth.json').read_text())


def params(fx, **kw):
    p = {'CASE_EXPORTS': str(fx / 'IPA_CaseHistory_*.xlsx'), 'EQUIPMENT_LISTS': str(fx / 'IPA_Active_Equipment_list_*.xlsx'),
         'OUTPUT_DIR': str(TMP / 'out' / fx.name), 'N_BOOT': 400, 'MAKE_CHARTS': False, 'MAKE_REPORT': False}
    p.update(kw)
    return p


def run(p, publish=False):
    from ipa_trends.engine import run as _run
    return _run(p, publish=publish, verbose=False)


def code_of(fn):
    from ipa_trends.errors import TrendsError
    try:
        return fn(), None
    except TrendsError as e:
        return None, e.code


# ------------------------------------------------------------------------------------------------ sections
def unit():
    print('1. Unit tests')
    import test_units
    for t in test_units.TESTS:
        try:
            t()
            ok(f'unit: {t.__name__}', True)
        except Exception as e:                       # noqa: BLE001
            ok(f'unit: {t.__name__}', False, f'{type(e).__name__}: {e}')


def parity():
    print('2. Parity with verification/ (MIT repository)')
    if not (TRENDS.parent / 'verification').exists():
        print('  verification/ not found: skipped (IPA copy)')
        return
    r = subprocess.run([sys.executable, '-I', str(TRENDS / 'tests' / 'test_parity.py')], capture_output=True, text=True)
    lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith('[')]
    fails = [ln for ln in lines if 'FAIL' in ln]
    ok(f'parity: {len(lines) - len(fails)}/{len(lines)} checks', r.returncode == 0, '; '.join(fails[:5]))


def cadences(fx, quick):
    print('3. Cadences')
    runs = {}
    settings = [('3M calendar', {}), ('1M', {'RERUN_FREQUENCY': 'monthly'}), ('5M', {'RERUN_FREQUENCY': '5 months'})]
    if not quick:
        settings += [('3M anchored', {'ANCHOR_DATE': '2024-02-01'}),
                     ('3M fiscal', {'YEAR_START_MONTH': 10}), ('2M', {'RERUN_FREQUENCY': 2}),
                     ('4M', {'RERUN_FREQUENCY': '4 months'}), ('6M', {'RERUN_FREQUENCY': 'semiannual'}),
                     ('12M', {'RERUN_FREQUENCY': 'annual'}),
                     ('explicit edges', {'PERIOD_EDGES': ['2024-01-01', '2024-03-31', '2024-06-30', '2024-09-29',
                                                          '2024-12-29', '2025-03-30', '2025-06-29', '2025-09-28',
                                                          '2025-12-28', '2026-03-29', '2026-06-28', '2026-09-27',
                                                          '2026-11-15']})]
    totals = {}
    for name, kw in settings:
        t0 = time.time()
        r, code = code_of(lambda: run(params(fx, **kw)))
        if not ok(f'{name}: runs and passes its runtime checks', r is not None, code):
            continue
        runs[name] = r
        g = r.tables['periods']
        rates = r.tables['rates']
        fl = rates[(rates.stratum_dim == 'fleet') & (rates.issue_key == 'all')]
        totals[name] = (int(fl.tickets.sum()), round(float(fl.machine_months.sum()), 6))
        ok(f'{name}: labels unique and statuses valid', g.label.is_unique and set(g.status) <= {
            'partial', 'in_progress', 'provisional', 'final'})
        print(f'      {name}: {len(g)} periods, latest {r.summary.get("latest_label")}, {time.time() - t0:.0f}s')
    ok('every cadence adds up to the same tickets and machine-months', len(set(totals.values())) == 1, str(totals))
    if '3M calendar' in runs:
        r2 = run(params(fx, HISTORY_MONTHS=60))
        a, b = runs['3M calendar'].tables['rates'], r2.tables['rates']
        ok('HISTORY_MONTHS changes no number', a.drop(columns=[]).equals(b))
    return runs


def planted(fx, truth, runs, null_fx):
    print('4. Planted effects')
    r = run(params(fx, CATEGORY_DIMS=['fleet', 'install_cohort', 'family'],
                   STRATIFY_BY=['install_cohort', 'family', 'model']))
    c = r.tables['changes']
    ok('latest final quarter is 2026 Q3', r.summary.get('latest_label') == '2026 Q3', r.summary.get('latest_label'))

    def status(dim, stratum, issue):
        x = c[(c.stratum_dim == dim) & (c.stratum == stratum) & (c.issue == issue)]
        return x.status.iloc[0] if len(x) else 'missing'
    ok('Deposit Door rise flagged (fleet)', status('fleet', 'Fleet', 'Deposit Door') == 'higher',
       status('fleet', 'Fleet', 'Deposit Door'))
    # the fall has about 14 tickets against 35 expected at full scale; the quick (half-size) fixture may only reach the
    # watch list, which is the conservative rule working as intended
    want = ('lower', 'watch_lower') if QUICK['on'] else ('lower',)
    ok('alEx Computer Board fall flagged', status('family', 'alEx', 'Computer Board') in want,
       status('family', 'alEx', 'Computer Board'))
    k = r.tables['cohort_contrasts']
    ts = k[(k.issue == 'Touchscreen')].set_index('install_cohort')
    for y in ('2022', '2023'):
        if y in ts.index:
            t = ts.loc[y]
            print(f'      Touchscreen {y}: {t.status}, crude {t.crude_ratio:.2f}, newer {t.newer_ratio:.2f}, older '
                  f'{t.older_ratio:.2f}, same age {t.same_age_ratio:.2f} ({t.same_age_lo:.2f}-{t.same_age_hi:.2f}), '
                  f'q {t.q_call:.2g}')
    # Both planted x3 cohorts pass every margin of the rule: at least 1.5x the rest of the fleet and 1.25x newer
    # installs, older installs and machines of the same age. Whether each is also beyond chance after the correction
    # depends on the fleet's size: the two cohorts are adjacent, so each sits in the other's 'newer' or 'older'
    # comparator. At full size both stand out (on seeds 7 and 11; on seed 3 only 2023 does). At half size (quick) only
    # one of them clears the bar (2023 on seeds 3, 7 and 11), which is the conservative rule working as intended.
    mc = r.params['MIN_CONTRAST']
    pr = ts.loc[[y for y in ('2022', '2023') if y in ts.index]]
    ok('Touchscreen 2022 and 2023 installs pass every margin of the rule (crude, newer, older, same age)',
       len(pr) == 2 and ((pr.crude_ratio >= 1 + mc) & (pr.newer_ratio >= 1 + mc / 2) & (pr.older_ratio >= 1 + mc / 2)
                         & (pr.same_age_ratio >= 1 + mc / 2)).all(),
       str(pr[['crude_ratio', 'newer_ratio', 'older_ratio', 'same_age_ratio']].round(2).to_dict('index')))
    if QUICK['on']:
        ok('Touchscreen 2022 or 2023 installs stand out',
           any(ts.status.get(y) == 'stands_out_higher' for y in ('2022', '2023')),
           f"2022 {ts.status.get('2022')}, 2023 {ts.status.get('2023')}")
    else:
        ok('Touchscreen 2022 installs stand out', ts.status.get('2022') == 'stands_out_higher', ts.status.get('2022'))
        ok('Touchscreen 2023 installs stand out', ts.status.get('2023') == 'stands_out_higher', ts.status.get('2023'))
    # (seed 7 at both sizes; at half size seed 3 also calls 2026 installs out on Door, as before the per-issue rule:
    # the newest cohort's months sit at the end of the window, where the planted Deposit Door rise is)
    others = k[k.status.str.startswith('stands_out') & ~(k.issue.isin(['Touchscreen', 'Electronics'])
                                                          & k.install_cohort.isin(['2022', '2023']))]
    ok('no other install cohort stands out on the planted fixture', others.empty,
       str(list(zip(others.install_cohort, others.issue))[:6]))
    # each row is worded over its own window; a row that was not tested states only its rate and the reason
    nt = k[k.status == 'not_tested']
    ok('cohort sentences: no nan or inf, and not-tested rows carry no ratio',
       not k.sentence.str.contains(r'\b(?:nan|inf)x?\b', regex=True).any()
       and not nt.sentence.str.contains('the rest of the fleet').any()
       and nt.sentence.str.contains('; not tested (', regex=False).all())
    ok('cohort sentences use the window of their own rows',
       all(s.endswith('.') and f' over {w}' in s for s, w in zip(k.sentence, k.window_label)))
    flags = c[c.status.isin(['higher', 'lower'])]
    # the Deposit Door rise is fleet-wide, so it shows in every stratum's Door and Deposit Door; the alEx Computer
    # Board fall shows in the fleet, in alEx and in its models
    import make_trend_fixture as MF
    alex_models = {m for m, fam in MF.MODEL_FAMILY.items() if fam == 'alEx'}
    explained = flags.issue.isin(['Deposit Door', 'Door']) | (flags.issue.isin(['Computer Board', 'Electronics'])
                                                              & (flags.stratum.isin(['Fleet', 'alEx'])
                                                                 | flags.stratum.isin(alex_models)))
    unexplained = flags[~explained]
    print(f'      flags on the planted fixture: {len(flags)}; not from a planted cell: '
          f'{list(zip(unexplained.stratum, unexplained.issue))}')
    m = run(params(fx, RERUN_FREQUENCY='monthly', CATEGORY_DIMS=['fleet', 'install_cohort', 'family'],
                   STRATIFY_BY=['install_cohort', 'family', 'model']))
    mc = m.tables['changes']
    lab = m.summary.get('latest_label')
    print(f'      monthly latest {lab}: flags {int(mc.status.isin(["higher", "lower"]).sum())}')
    n = run(params(null_fx, CATEGORY_DIMS=['fleet', 'install_cohort', 'family'],
                   STRATIFY_BY=['install_cohort', 'family', 'model']))
    nf = n.tables['changes']
    nflags = int(nf.status.isin(['higher', 'lower']).sum())
    ncoh = int(n.tables['cohort_contrasts'].status.str.startswith('stands_out').sum())
    ok(f'null fixture: at most one false flag ({nflags} flags of {int(nf.eligible.sum())} tested)', nflags <= 1)
    ok(f'null fixture: no install cohort stands out ({ncoh})', ncoh == 0)
    return r


def cohort_rule(base_fx, quick):
    print("4b. Install cohorts: the newest testable cohort, an age effect, each row's own window")
    # Touchscreen x3 on 2025 installs: in a 2026 Q1 back-run the 2026 cohort holds a handful of machine-months, and
    # in the default run (2026 Q3) it is still filling up; 2025 is then the newest testable cohort, compared on the
    # same-age ratio instead of with a near-empty 'newer installs' group. Full size even in quick mode: at half size
    # the 2025 cohort expects fewer than 10 Touchscreen tickets in the 2026 Q1 window, so it is too new to test itself.
    fx, _ = fixture('v_cohort_2025', variant='cohort_2025', scale=1.0)
    for latest in ('2026 Q1', None):
        r = run(params(fx, **({'LATEST_PERIOD': latest} if latest else {})))
        k = r.tables['cohort_contrasts']
        ts = k[k.issue == 'Touchscreen'].set_index('install_cohort')
        lab = r.summary.get('latest_label')
        t = ts.loc['2025'] if '2025' in ts.index else None
        detail = 'missing' if t is None else (f'{t.position}, {t.status}, crude {t.crude_ratio:.2f}, same age '
                                              f'{t.same_age_ratio:.2f}, q {t.q_call:.2g}')
        print(f'      cohort_2025, {lab}: Touchscreen 2025 {detail}; 2026 {ts.position.get("2026")}')
        ok(f'cohort_2025, {lab}: Touchscreen 2025 installs stand out as the newest testable cohort',
           t is not None and t.status == 'stands_out_higher' and t.position == 'newest', detail)
        ok(f'cohort_2025, {lab}: the 2026 cohort is too new to compare',
           ts.position.get('2026') == 'too_new' and ts.status.get('2026') == 'not_tested'
           and 'too new' in str(ts.not_tested_reason.get('2026')), f"{ts.position.get('2026')}")
        others = k[k.status.str.startswith('stands_out') & ~(k.issue.isin(['Touchscreen', 'Electronics'])
                                                              & (k.install_cohort == '2025'))]
        ok(f'cohort_2025, {lab}: no other install cohort stands out', others.empty,
           str(list(zip(others.install_cohort, others.issue))[:6]))
    # the day the 2026 cohort becomes testable (simulated by setting MIN_EXPECTED just under its expected Touchscreen
    # tickets), its few machine-months are still too few for a newer-installs comparison: 2025 must stay called out
    k = r.tables['cohort_contrasts']
    e26 = float(k[(k.issue == 'Touchscreen') & (k.install_cohort == '2026')].expected_crude.iloc[0])
    r = run(params(fx, MIN_EXPECTED=max(1.0, e26 - 0.05)))
    ts = r.tables['cohort_contrasts']
    ts = ts[ts.issue == 'Touchscreen'].set_index('install_cohort')
    ok(f'cohort_2025, the 2026 cohort just testable ({e26:.1f} expected): Touchscreen 2025 still stands out, compared '
       'like the newest cohort because its newer installs are too few', ts.status.get('2025') == 'stands_out_higher'
       and ts.position.get('2025') == 'newest' and ts.position.get('2026') == 'newest',
       f"2025 {ts.position.get('2025')} {ts.status.get('2025')}; 2026 {ts.position.get('2026')}")
    # Touchscreen x3 while a machine is 3-5 years old, the same for every install year: the cohorts at that age in the
    # window peak against newer and older installs, but match machines of the same age in other cohorts (no call-out
    # on seeds 3, 7 and 11 at full size; at half size seed 3 has the 2026 Door call-out noted in planted())
    hx, _ = fixture('v_age_hump', variant='age_hump', scale=0.5 if quick else 1.0)
    r = run(params(hx))
    k = r.tables['cohort_contrasts']
    st = k[k.status.str.startswith('stands_out')]
    ok('age_hump: no install cohort stands out (an age effect, not a cohort difference)', st.empty,
       str(list(zip(st.install_cohort, st.issue, st.q_call.round(4)))[:6]))
    ok('age_hump: the interior same-age check runs (at least 24 months of final history)',
       r.facts['cohorts'].get('same_age_check_interior') == {'all': True, 'labels': True},
       str(r.facts['cohorts'].get('history_months')))
    t = k[(k.issue == 'Touchscreen') & (k.install_cohort == '2022')]
    detail = 'missing' if t.empty else (f'crude {t.crude_ratio.iloc[0]:.2f}, newer {t.newer_ratio.iloc[0]:.2f}, older '
                                        f'{t.older_ratio.iloc[0]:.2f}, same age {t.same_age_ratio.iloc[0]:.2f}: '
                                        f'{t.not_tested_reason.iloc[0]}')
    print(f'      age_hump, Touchscreen 2022 installs: {detail}')
    ok('age_hump: Touchscreen 2022 installs peak against newer and older installs, and the note puts it down to age',
       len(t) == 1 and t.crude_ratio.iloc[0] >= 1.5 and t.newer_ratio.iloc[0] >= 1.25 and t.older_ratio.iloc[0] >= 1.25
       and t.not_tested_reason.iloc[0].startswith('in line with machines of the same age'), detail)
    # Each row is worded over the window of its own set of periods. In a 2024 Q4 back-run, 2024 Q1 (15% blank
    # Category in Jan-Feb 2024) is in the all-ticket window but not in the issue-level one. Its 12 months of final
    # history are too few for the interior same-age check, so an interior call-out's basis says so.
    from ipa_trends import cohorts as COH
    r = run(params(base_fx, LATEST_PERIOD='2024 Q4', OUTPUT_DIR=str(TMP / 'out' / 'cohort_back_run')), publish=True)
    k, info = r.tables['cohort_contrasts'], r.facts['cohorts']
    issue = k.issue_level != 'all'
    labels = {'all': sorted(set(k.window_label[~issue])), 'issue': sorted(set(k.window_label[issue]))}
    ok('2024 Q4 back-run: all-ticket rows cover 2024 Q1 to Q4, issue-level rows only Q2 to Q4 (complete labels)',
       labels == {'all': ['2024 Q1 to 2024 Q4'], 'issue': ['2024 Q2 to 2024 Q4']}
       and set(k.window_periods[issue]) == {3} and set(k.window_periods[~issue]) == {4}, str(labels))
    ok('2024 Q4 back-run: every sentence names its own window',
       all(f' over {w}' in s for s, w in zip(k.sentence, k.window_label)))
    pub = pd.read_csv(Path(r.paths['run_dir']) / 'cohort_contrasts.csv', dtype=str)
    key = ['install_cohort', 'issue_key']
    ok("2024 Q4 back-run: the published table keeps each row's window",
       pub.set_index(key).window_label.to_dict() == k.set_index(key).window_label.to_dict(),
       str(pub.groupby('window_label').size().to_dict()))
    called = k[k.status.str.startswith('stands_out') & (k.position == 'interior')]
    print(f'      2024 Q4 back-run: history {info.get("history_months")} months; interior call-outs {len(called)}')
    ok('2024 Q4 back-run: with 12 months of history the interior same-age check is skipped, and the basis says so',
       info.get('same_age_check_interior') == {'all': False, 'labels': False}
       and called.basis.str.contains(f'needs {COH.SAME_AGE_HISTORY_MONTHS} months of final history').all(),
       str(list(called.basis)[:3]))


def publishing(fx, truth):
    print('5. Publishing')
    from ipa_trends.errors import PrivacyError
    out = TMP / 'pub'
    p = params(fx, OUTPUT_DIR=str(out), MAKE_CHARTS='auto', MAKE_REPORT=True)
    r = run(p, publish=True)
    latest = out / 'latest'
    need = ['periods.csv', 'rates.csv', 'rates_final.csv', 'changes.csv', 'cohort_contrasts.csv', 'data_quality.csv',
            'strata.csv', 'unmapped.csv', 'schema.json', 'manifest.json']
    ok('latest/ holds every table, schema and manifest', all((latest / f).exists() for f in need),
       str([f for f in need if not (latest / f).exists()]))
    try:
        import ipa_trends.report  # noqa: F401
        have_report = True
    except ImportError:
        have_report = False
    if have_report:
        ok('report.html, report.pdf and the email text are written',
           all((latest / f).exists() for f in ('report.html', 'report.pdf', 'email_summary.txt')))
    man = json.loads((latest / 'manifest.json').read_text())
    ok('manifest: privacy scan found nothing', man['privacy']['hits'] == 0)
    ok('manifest: no absolute paths', str(TMP) not in json.dumps(man['inputs']))
    ok('manifest: the next run is due after the export date', (man['next_run_after'] or '') > man['extracted_at'],
       f"{man['next_run_after']} vs {man['extracted_at']}")
    first = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in latest.glob('*.csv')}
    run(p, publish=True)
    second = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in latest.glob('*.csv')}
    ok('a rerun on the same inputs writes byte-identical tables', first == second)
    ok('fake identifiers appear in no table', not any(
        s in (latest / f).read_text() for f in first for s in truth['fake_strings']['accounts'][:20]))
    before = (latest / 'manifest.json').read_bytes()
    leak = truth['fake_strings']['accounts'][0]
    try:
        run({**p, 'REPORT_TITLE': f'Trends for {leak}', 'MAKE_REPORT': True}, publish=True)
        caught = False
    except PrivacyError:
        caught = True
    ok('a planted leak (a real account name in the title) stops publication', caught or not have_report)
    ok('... and latest/ is left untouched', (latest / 'manifest.json').read_bytes() == before)
    records = sorted((out / 'failed').glob('*/error.txt'))
    ok('... and failed/<stamp>/error.txt records the code, stage and exit code only', not have_report or (
        records and records[-1].read_text().startswith('code: P01\nstage: privacy scan\nexit_code: 1\n')
        and leak not in records[-1].read_text()), str([r.read_text() for r in records]))
    # a monthly run, with DATA_END six weeks before the export, while a file in latest/ is open in Excel: on Windows
    # renaming latest/ then fails
    import os
    from ipa_trends import publish as PUB
    from ipa_trends.errors import OutputError
    def files():
        return {str(f.relative_to(latest)): f.read_bytes() for f in latest.rglob('*') if f.is_file()}
    previous = files()
    real, waits = os.replace, PUB.RETRY_WAITS

    def locked(src, dst, *a, **k):
        if Path(src) == latest:
            raise PermissionError(13, 'The process cannot access the file because it is being used')
        return real(src, dst, *a, **k)
    os.replace, PUB.RETRY_WAITS = locked, ()
    try:
        run({**p, 'RERUN_FREQUENCY': 'monthly', 'DATA_END': '2026-09-30', 'MAKE_CHARTS': False, 'MAKE_REPORT': False},
            publish=True)
        err = None
    except OutputError as e:
        err = e
    finally:
        os.replace, PUB.RETRY_WAITS = real, waits
    ok('a locked file in latest/ stops the swap with E30 (exit 2), saying latest/ was not updated',
       err is not None and err.code == 'E30' and err.exit_code == 2 and 'latest/ was not updated' in err.message,
       err and err.text())
    ok('... and latest/ still holds the whole previous run, nothing left half-copied',
       files() == previous and not list(out.rglob('*.partial'))
       and not [d.name for d in out.iterdir() if d.name.startswith('latest.')])
    monthly = [json.loads(m.read_text()) for m in (out / 'runs').glob('*_1M_*/manifest.json')]
    ok('... while the monthly run folder is complete, its next run due after the export date',
       len(monthly) == 1 and (monthly[0]['next_run_after'] or '') > monthly[0]['extracted_at'],
       str([(m['next_run_after'], m['extracted_at']) for m in monthly]))
    ok('... and W26 (closed cases only?) does not fire for data ending before the export: those tickets had weeks to '
       'close', len(monthly) == 1 and not [w for w in monthly[0]['warnings'] if w['code'] == 'W26'])
    return r


def variants(base_runs, quick):
    print('6. Export drift')
    base = base_runs.get('3M calendar')
    cases = [('title_rows', {}, None, 'W20'), ('sheet_name', {}, None, 'W18'), ('header_alias', {}, 'E03', None),
             ('header_alias', {'COLUMN_ALIASES': {'Trouble Code Cat.': 'Trouble Code Category'}}, None, None),
             ('duplicate_case', {}, 'E04', None), ('text_dates', {}, None, 'W13'), ('mixed_dates', {}, 'E05', None),
             ('category_split', {}, None, 'W04'), ('trouble_code_rename', {}, None, 'W04'),
             ('central_clock', {'CASE_CLOCK_TZ': 'America/Chicago'}, None, None),
             ('closed_only', {}, None, 'W26'), ('quarter_end_filter', {}, None, None),
             ('baseline_spike', {'RERUN_FREQUENCY': 'monthly'}, None, None), ('removed_2x', {}, None, None),
             ('blank_install', {}, None, 'W08'), ('blank_list_fields', {}, None, 'W22')]
    if quick:
        cases = [c for c in cases if c[0] in ('title_rows', 'header_alias', 'mixed_dates', 'category_split',
                                              'quarter_end_filter')]
    for variant, kw, want_code, want_warning in cases:
        fx, _ = fixture(f'v_{variant}', variant=variant, scale=0.6)
        r, code = code_of(lambda: run(params(fx, **kw)))
        label = f'{variant}{" with " + ",".join(kw) if kw else ""}'
        if want_code:
            ok(f'{label}: stops with {want_code}', code == want_code, code)
            continue
        if not ok(f'{label}: runs', r is not None, code):
            continue
        codes = {w['code'] for w in r.warnings}
        if want_warning:
            ok(f'{label}: warns {want_warning}', want_warning in codes, str(sorted(codes)))
        c = r.tables['changes']
        if variant == 'category_split':
            door = c[(c.stratum_dim == 'fleet') & (c.issue_group == 'Door') & (c.issue_level != 'all')]
            ok('category_split: Door is not flagged (taxonomy change)', not door.status.isin(['higher', 'lower']).any()
               and door.not_tested_reason.str.contains('taxonomy').any())
            held = [w['message'] for w in r.warnings if w['code'] == 'W27']
            ok('category_split: W27 names no group whose total W04 already held back', not held, str(held))
        if variant == 'trouble_code_rename':
            # renamed planned work lands in Unmapped, which is never tested, and blocks Other; Door keeps the planted
            # Deposit Door rise, so it is not part of this check
            leak = c[c.issue_group.isin(['Other', 'Unmapped']) & c.status.isin(['higher', 'lower'])]
            ok('trouble_code_rename: no false flag in Other or Unmapped', leak.empty, str(list(leak.issue)))
        if variant == 'quarter_end_filter':
            ok('quarter_end_filter: 2026 Q3 is final, not stuck provisional', r.summary.get('latest_label') == '2026 Q3',
               r.summary.get('latest_label'))
        if variant == 'baseline_spike':
            cb = c[(c.stratum_dim == 'fleet') & (c.issue == 'Computer Board')]
            ok('baseline_spike: no false Computer Board flag', not cb.status.isin(['higher', 'lower']).any())
        if variant == 'removed_2x':
            fl = c[(c.stratum_dim == 'fleet') & (c.status == 'higher')]
            ok('removed_2x: no false fleet increase from survivorship',
               fl[~fl.issue.isin(['Deposit Door', 'Door'])].empty, str(list(fl.issue)))
        if variant == 'closed_only':
            ok('closed_only: not marked ready to distribute', any(w.get('blocking') for w in r.warnings))
    split_category(quick)
    if base is not None:
        c = base.tables['changes']
        ok('unchanged fixture: no Category is taken to have appeared or disappeared',
           not c.not_tested_reason.str.contains('appeared or disappeared').any())
        zero = c[(c.tickets_latest == 0) & c.change_ratio.notna()]
        ok(f'cells with no tickets in the latest period ({len(zero)}): the ratio lies inside its interval',
           ((zero.ci_lo <= zero.change_ratio) & (zero.change_ratio <= zero.ci_hi)).all())
        fin = c[(c.crude_ratio > 0) & c.change_ratio.notna() & c.day_factor_baseline.notna()]
        gap = (fin.crude_ratio - fin.change_ratio * fin.day_factor_latest / fin.day_factor_baseline).abs()
        ok('crude ratio = change ratio x business-day factor on every row', (gap <= 1e-9 * fin.crude_ratio).all())
        nt = c[c.status == 'not_tested']
        ok('sentences: no nan or inf, and untested cells state no change',
           not c.sentence.str.contains(r'\bnan\b|\binf\b').any()
           and not nt.sentence.str.contains(r'% (?:above|below)|level with').any()
           and all(s.endswith(f'; not tested ({w}).') for s, w in zip(nt.sentence, nt.not_tested_reason)))
        per = base.tables['periods'].set_index('label')
        if not bool(per.label_ok.get('2024 Q1', True)):      # the fixture's 2024 Q1 has too many blank Categories
            label_baseline(run(params(fixture('base')[0], LATEST_PERIOD='2025 Q1')))
    edges = base_runs.get('explicit edges')
    if edges is not None:
        s = ' '.join(edges.tables['changes'].sentence)
        ok('explicit edges: sentences say periods, not quarters', 'period' in s and 'quarter' not in s)
    if not quick:
        yearly = run(params(fixture('base')[0], PERIOD_EDGES=['2024-01-01', '2025-01-01', '2026-01-01',
                                                               '2027-01-01']))
        fl = yearly.tables['changes']
        fl = fl[(fl.stratum_dim == 'fleet') & (fl.issue_key == 'all')]
        ok('yearly PERIOD_EDGES: 2025 is compared with 2024 (one period of baseline)',
           yearly.summary.get('latest_label') == '2025' and bool(fl.eligible.iloc[0])
           and 'the previous period' in fl.sentence.iloc[0], f'{yearly.summary.get("latest_label")}; '
                                                             f'{fl.not_tested_reason.iloc[0]}')
    if not quick:
        cfx, _ = fixture('v_central_clock', variant='central_clock', scale=0.6)
        bfx, _ = fixture('v_base_06', scale=0.6)
        a = run(params(cfx, CASE_CLOCK_TZ='America/Chicago')).tables['rates']
        b = run(params(bfx)).tables['rates']
        cols = ['period_key', 'stratum_dim', 'stratum', 'issue_key', 'tickets']
        ok('central_clock read as Chicago time gives the same tickets per period as the Eastern export',
           a[cols].reset_index(drop=True).equals(b[cols].reset_index(drop=True)))
        sfx, _ = fixture('v_snapshots', variant='removed_2x', snapshots=3, scale=0.6)
        r = run(params(sfx))
        ok('three monthly equipment lists: removed machines keep their exposure (ledger)',
           r.facts['population']['removed_machines'] > 0)


def _blank_serials(case, dest, every=50):
    """A copy of the case export in `dest` with Serial # blank on every `every`-th row (E10: over 0.5% of rows)."""
    import openpyxl
    wb = openpyxl.load_workbook(case)
    ws = wb['ipa_repair cases']
    col = [c.value for c in ws[1]].index('Serial #') + 1
    for r in range(2, ws.max_row + 1, every):
        ws.cell(r, col).value = None
    wb.save(dest / Path(case).name)


def label_baseline(r):
    """A run for 2025 Q1, whose baseline holds 2024 Q1 with incomplete Category labels: issue-level rows use the
    other three quarters, and their sentences and published baseline labels say so."""
    from ipa_trends import publish as PUB
    c = r.tables['changes']
    lab, every = c[c.baseline_set == 'labels'], c[c.baseline_set == 'all']
    ok('label-incomplete baseline: issue-level rows use 3 of the 4 quarters, all-ticket rows all 4',
       len(lab) and lab.baseline_periods_used.eq(3).all() and every.baseline_periods_used.eq(4).all())
    said = lab[lab.status != 'not_tested'].sentence
    ok('label-incomplete baseline: issue-level sentences name three of the previous four quarters',
       len(said) and said.str.contains(r'three of the previous four quarters \(those with complete Category labels;')
       .all() and every[every.status != 'not_tested'].sentence.str.contains('the previous four quarters [(]').all(),
       said.iloc[0] if len(said) else '')
    pub = PUB.prepare_tables(r, 'run', 'hash')['changes']
    ok('label-incomplete baseline: changes.csv names each row\'s own baseline quarters',
       set(pub[pub.baseline_set == 'labels'].baseline_labels) == {'2024 Q2; 2024 Q3; 2024 Q4'}
       and set(pub[pub.baseline_set == 'all'].baseline_labels) == {'2024 Q1; 2024 Q2; 2024 Q3; 2024 Q4'},
       str(sorted(set(pub.baseline_labels))))


def split_category(quick):
    """A split Category whose new names were added to REQUEST_TYPES_LOCAL leaves nothing unmapped, so only the
    appeared / vanished rule stops false flags: none on Deposit Door or its new names, at the split quarter and one
    quarter after (when the new names have part of a baseline). CATEGORY_ALIASES instead continues the series."""
    local = TMP / 'request_types_local.csv'
    local.write_text('trouble_code,category,group\nElectro/Mechanical,Deposit Door - Latch,Door\n'
                     'Electro/Mechanical,Deposit Door - Sensor,Door\n', encoding='utf-8')
    names = ['Deposit Door', 'Deposit Door - Latch', 'Deposit Door - Sensor']
    when = [('split quarter', 'v_category_split', {})]
    if not quick:
        when.append(('one quarter after the split', 'v_category_split_q2', {'split_from': '2026-04-01'}))
    for label, name, build in when:
        fx, _ = fixture(name, variant='category_split', scale=0.6, **build)
        r, code = code_of(lambda: run(params(fx, REQUEST_TYPES_LOCAL=str(local))))
        if not ok(f'category_split with REQUEST_TYPES_LOCAL, {label}: runs', r is not None, code):
            continue
        c = r.tables['changes']
        bad = c[c.issue.isin(names) & c.status.isin(['higher', 'lower'])]
        ok(f'category_split with REQUEST_TYPES_LOCAL, {label}: no Deposit Door, Latch or Sensor flag', bad.empty,
           str(list(zip(bad.stratum, bad.issue, bad.status))[:6]))
        door = c[(c.issue_group == 'Door') & (c.issue_level == 'category')]
        fleet = c[(c.stratum_dim == 'fleet') & (c.issue.isin(['Door'] + names))].set_index('issue')
        ok(f'category_split with REQUEST_TYPES_LOCAL, {label}: Door Categories held back as a taxonomy change, '
           'the Door group still tested', not door.eligible.any()
           and 'taxonomy' in str(fleet.not_tested_reason.get('Deposit Door')) and bool(fleet.eligible.get('Door')),
           str(fleet.not_tested_reason.to_dict()))
        ok(f'category_split with REQUEST_TYPES_LOCAL, {label}: W27 says Category-level tests were held back',
           any(w['code'] == 'W27' for w in r.warnings), str(sorted({w['code'] for w in r.warnings})))
    if not quick:
        fx, _ = fixture('v_category_split', variant='category_split', scale=0.6)
        r = run(params(fx, CATEGORY_ALIASES={n: 'Deposit Door' for n in names[1:]}))
        c = r.tables['changes']
        dd = c[(c.stratum_dim == 'fleet') & (c.issue == 'Deposit Door')].status
        ok('category_split with CATEGORY_ALIASES: the series continues, the planted Deposit Door rise is flagged '
           'and nothing is held back', list(dd) == ['higher'] and not c.not_tested_reason.str.contains(
               'appeared or disappeared').any(), str(list(dd)))


def notebook(fx):
    print('7. Notebook')
    try:
        import nbclient  # noqa: F401
    except ImportError:
        print('  nbclient not installed: skipped')
        return
    from ipa_trends import cli
    nbtmp = TMP / 'nbtmp'                        # the command line's temporary folders, to see that none is left
    nbtmp.mkdir()
    saved_tmp, tempfile.tempdir = tempfile.tempdir, str(nbtmp)
    for freq in ('quarterly', 'monthly', '5 months'):
        out = TMP / f'nb_{freq.replace(" ", "")}'
        argv = ['run', '--engine', 'notebook', '--set', f'RERUN_FREQUENCY={freq}', '--set',
                f'CASE_EXPORTS={fx}/IPA_CaseHistory_*.xlsx', '--set',
                f'EQUIPMENT_LISTS={fx}/IPA_Active_Equipment_list_*.xlsx', '--set', f'OUTPUT_DIR={out}', '--set',
                'N_BOOT=400', '--set', 'MAKE_CHARTS=False', '--set', 'MAKE_REPORT=False', '--quiet']
        rc = cli.main(argv)
        ok(f'notebook headless at {freq}: exit 0', rc == 0, rc)
        ok(f'notebook headless at {freq}: executed notebook saved', bool(list(out.glob('runs/*/executed_notebook.ipynb'))))
    ok('notebook headless: no temporary folder is left behind', not list(nbtmp.iterdir()), str(list(nbtmp.iterdir())))
    # BASE_DIR in a parameter file: the notebook reads and writes the folders the parameters name
    base = TMP / 'nb_base'
    (base / 'data' / 'raw').mkdir(parents=True)
    for f in list(fx.glob('IPA_*.xlsx')):
        shutil.copy(f, base / 'data' / 'raw' / f.name)
    pfile = TMP / 'nb_base.json'
    pfile.write_text(json.dumps({'BASE_DIR': str(base), 'N_BOOT': 400, 'MAKE_CHARTS': False, 'MAKE_REPORT': False}))
    def home():                                  # the trends folder's own data/output
        d = TRENDS / 'data' / 'output'
        return sorted((str(p.relative_to(d)), p.stat().st_mtime_ns) for p in d.rglob('*')) if d.exists() else None
    home_before = home()
    rc = cli.main(['run', '--engine', 'notebook', '--params', str(pfile), '--quiet'])
    bout = base / 'data' / 'output'
    first = json.loads((bout / 'latest' / 'manifest.json').read_text())['run_id'] if (
        bout / 'latest' / 'manifest.json').exists() else None
    ok('BASE_DIR from a parameter file, --engine notebook: exit 0, published under BASE_DIR with its notebook',
       rc == 0 and first and (bout / 'runs' / first / 'executed_notebook.ipynb').exists(), rc)
    ok('... and nothing was written to the trends folder\'s data/output', home() == home_before)
    # a back-run with the notebook engine: its notebook is filed under the back-run, and latest/ is left alone
    if first:
        def latest_files():
            return {str(f): f.read_bytes() for f in (bout / 'latest').rglob('*') if f.is_file()}
        snap = latest_files()
        nb_first = (bout / 'runs' / first / 'executed_notebook.ipynb').read_bytes()
        rc = cli.main(['run', '--engine', 'notebook', '--params', str(pfile), '--set', 'LATEST_PERIOD=2025 Q2',
                       '--quiet'])
        back = [d for d in (bout / 'runs').iterdir() if d.name != first]
        nb_back = back[0] / 'executed_notebook.ipynb' if len(back) == 1 else None
        text = nb_back.read_text() if nb_back and nb_back.exists() else ''
        ok('a back-run with --engine notebook: exit 0, its executed notebook saved in its own run folder',
           rc == 0 and bool(text), f'{rc} {[d.name for d in back]}')
        ok('... latest/ and the latest run\'s notebook are left untouched',
           latest_files() == snap
           and (bout / 'runs' / first / 'executed_notebook.ipynb').read_bytes() == nb_first)
        ok('... and the notebook says latest/ was not changed, and names no next run',
           'a back-run: `latest/` was not changed' in text and 'also copied to `latest/`' not in text
           and 'Next run due' not in text and len(back) == 1
           and json.loads((back[0] / 'manifest.json').read_text())['next_run_after'] is None)
    # input errors: the same code and exit code on both engines, and a failure record
    e10 = TMP / 'nb_e10'
    e10.mkdir()
    for f in fx.glob('IPA_Active_Equipment_list_*.xlsx'):
        shutil.copy(f, e10 / f.name)
    _blank_serials(next(fx.glob('IPA_CaseHistory_*.xlsx')), e10, every=50)
    for code, src in (('E01', TMP / 'nb_missing'), ('E10', e10)):
        for engine in ('direct', 'notebook'):
            out = TMP / f'nb_{code}_{engine}'
            rc = cli.main(['run', '--engine', engine, '--set', f'CASE_EXPORTS={src}/IPA_CaseHistory_*.xlsx', '--set',
                           f'EQUIPMENT_LISTS={src}/IPA_Active_Equipment_list_*.xlsx', '--set', f'OUTPUT_DIR={out}',
                           '--quiet'])
            recs = [r.read_text() for r in out.glob('failed/*/error.txt')]
            ok(f'{code} with --engine {engine}: exit 2 and a failure record with that code',
               rc == 2 and len(recs) == 1 and recs[0].startswith(f'code: {code}\nstage: inputs\nexit_code: 2\n'),
               f'{rc} {recs}')
    ok('E10 with --engine notebook: the scanned executed notebook is kept with the failure record',
       bool(list((TMP / 'nb_E10_notebook').glob('failed/*/executed_notebook.ipynb'))))
    # a text parameter is not an output: a run that stops before the publish scan must not file what was typed into
    # it (the executed notebook's injected values are left out of every copy)
    out = TMP / 'nb_E10_title'
    typed = 'Trends for Fake Memorial Hospital 001'
    rc = cli.main(['run', '--engine', 'notebook', '--set', f'CASE_EXPORTS={e10}/IPA_CaseHistory_*.xlsx', '--set',
                   f'EQUIPMENT_LISTS={e10}/IPA_Active_Equipment_list_*.xlsx', '--set', f'OUTPUT_DIR={out}',
                   '--set', f'REPORT_TITLE={typed}', '--quiet'])
    filed = [f for f in out.rglob('*') if f.is_file()]
    ok('E10 with --engine notebook and a name typed into REPORT_TITLE: the failure record and its notebook never '
       'show it', rc == 2 and any(f.name == 'executed_notebook.ipynb' for f in filed)
       and not [f for f in filed if typed in f.read_text(encoding='utf-8', errors='ignore')],
       f'{rc} {[f.name for f in filed]}')
    tempfile.tempdir = saved_tmp
    bad = TMP / 'nb_bad'
    bad.mkdir(parents=True, exist_ok=True)
    rc = subprocess.run([sys.executable, '-m', 'papermill', str(TRENDS / 'ticket_trends.ipynb'), str(bad / 'x.ipynb'),
                         '-p', 'RERUN_FREQUENCEY', 'monthly', '--cwd', str(TRENDS)], capture_output=True, text=True)
    if 'No module named papermill' in rc.stderr:
        print('  papermill not installed: misspelling check skipped')
    else:
        ok('a misspelt papermill parameter stops the notebook (E22)', rc.returncode != 0 and 'E22' in (rc.stdout +
                                                                                                         rc.stderr))
    # command line vs notebook: identical tables
    out_cli, out_nb = TMP / 'same_cli', TMP / 'same_nb'
    common = ['--set', f'CASE_EXPORTS={fx}/IPA_CaseHistory_*.xlsx', '--set',
              f'EQUIPMENT_LISTS={fx}/IPA_Active_Equipment_list_*.xlsx', '--set', 'N_BOOT=400', '--set',
              'MAKE_CHARTS=False', '--set', 'MAKE_REPORT=False', '--quiet']
    cli.main(['run', '--set', f'OUTPUT_DIR={out_cli}'] + common)
    cli.main(['run', '--engine', 'notebook', '--set', f'OUTPUT_DIR={out_nb}'] + common)
    a = {f.name: f.read_bytes() for f in (out_cli / 'latest').glob('*.csv')}
    b = {f.name: f.read_bytes() for f in (out_nb / 'latest').glob('*.csv')}
    ok('the command line and the notebook write byte-identical tables', a == b and len(a) > 0)


def privacy_scan(fx, null_fx):
    """Only trusted words (package literals, request-type labels) exempt a one-word real string: copies of the
    fixtures with edited equipment lists, published end to end, and the executed-notebook scan on the same words."""
    print('5b. Privacy scan: trusted words only')
    import nbformat
    import openpyxl
    from ipa_trends import config as CFG
    from ipa_trends.engine import scan_notebook

    def edited(src, name, edit):
        out = TMP / f'priv_{name}'
        shutil.copytree(src, out, dirs_exist_ok=True)
        path = next(out.glob('IPA_Active_Equipment_list_*.xlsx'))
        wb = openpyxl.load_workbook(path)
        ws = wb['Equipment list - Monthly Report']
        col = {c.value: i for i, c in enumerate(ws[1])}
        edit(list(ws.iter_rows(min_row=2)), col)
        wb.save(path)
        return out

    def published(p):
        r, code = code_of(lambda: run(p, publish=True))
        man = Path(p['OUTPUT_DIR']) / 'runs' / (r.paths['run_id'] if r is not None else '-') / 'manifest.json'
        return code, json.loads(man.read_text())['privacy']['hits'] if man.exists() else None
    kept = {}

    def trusted_words(rows, c):
        words = ['Normal', 'Orange', 'Door', 'Power', 'Training', 'Badge', 'Network', 'Unknown', 'Before', 'Hospital']
        accounts = sorted({r[c['Account Name']].value for r in rows} - {None})
        city = dict(zip(accounts, words))
        for i, r in enumerate(rows):
            a = r[c['Account Name']].value
            if a in city:
                r[c['Hospital City']].value = city[a]
            elif a == accounts[-1]:
                kept['city'] = r[c['Hospital City']].value
            if i % 50 == 0:
                r[c['Location']].value = 'Security'
            if i % 70 == 0:
                r[c['Vendor Credentialing Notes']].value = 'Badge'
    wfx = edited(null_fx, 'words', trusted_words)
    code, hits = published(params(wfx, OUTPUT_DIR=str(TMP / 'out' / 'priv_words')))
    ok('null fixture whose one-word cities, locations and notes equal package or request-type words (Normal, Door, '
       'Badge...) publishes with 0 privacy hits', code is None and hits == 0, f'{code} {hits}')

    def city_in_model(rows, c):
        by = {}
        for r in rows:
            by.setdefault(r[c['Account Name']].value, []).append(r)
        for r in by[sorted(a for a, rs in by.items() if a and len(rs) >= 3)[0]][:3]:
            r[c['Model']].value = r[c['Hospital City']].value
    lean = {'STRATIFY_BY': ['install_cohort'], 'CATEGORY_DIMS': ['fleet']}      # strata.csv always lists the models
    out = TMP / 'out' / 'priv_city'
    r, code = code_of(lambda: run(params(edited(fx, 'city', city_in_model), OUTPUT_DIR=str(out), **lean), publish=True))
    ok('a city typed into the Model column stops publication (P01)', code == 'P01', code)
    ok('... and nothing is published', not list(out.glob('runs/*/manifest.json')) and not (out / 'latest').exists())

    def remote(rows, c):
        for r in rows[:5]:
            r[c['Location']].value = 'Remote'
    rfx = edited(fx, 'remote', remote)
    code, _ = published(params(rfx, OUTPUT_DIR=str(TMP / 'out' / 'priv_remote'), **lean))
    ok('a one-word Location equal to a model word (Remote; LVD-Remote-2.0) is a genuine collision: P01', code == 'P01',
       code)
    code, hits = published(params(rfx, OUTPUT_DIR=str(TMP / 'out' / 'priv_remote'), PRIVACY_ALLOW=['Remote'], **lean))
    ok("... which PRIVACY_ALLOW = ['Remote'] lets through, with 0 privacy hits", code is None and hits == 0,
       f'{code} {hits}')

    def notebook_with(name, text):
        nb = nbformat.v4.new_notebook()
        cell = nbformat.v4.new_code_cell('result = notebook.run_and_show(params)')
        cell.outputs = [nbformat.v4.new_output('display_data', data={'text/markdown': text})]
        nb.cells = [cell]
        nbformat.write(nb, str(TMP / f'priv_{name}.ipynb'))
        return TMP / f'priv_{name}.ipynb'
    P = CFG.resolve(params(wfx))
    ok('the executed-notebook scan exempts what the publish scan exempts (a Badge note; the Badge Reader Category)',
       scan_notebook(P, notebook_with('badge', '- Badge Reader: higher than the baseline')) == 0)
    ok('... and still finds a real city in a notebook',
       scan_notebook(P, notebook_with('city', f"- {kept['city']}")) == 1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--no-parity', action='store_true')
    ap.add_argument('--no-notebook', action='store_true')
    a = ap.parse_args(argv)
    QUICK['on'] = a.quick
    t0 = time.time()
    unit()
    if not a.no_parity:
        parity()
    scale = 0.5 if a.quick else 1.0
    fx, truth = fixture('base', scale=scale)
    null_fx, _ = fixture('null', null=True, scale=scale)
    runs = cadences(fx, a.quick)
    planted(fx, truth, runs, null_fx)
    cohort_rule(fx, a.quick)
    publishing(fx, truth)
    privacy_scan(fx, null_fx)
    variants(runs, a.quick)
    if not a.no_notebook:
        notebook(fx)
    bad = [n for n, g in RESULTS if not g]
    print(f'\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks pass in {time.time() - t0:.0f}s')
    for n in bad:
        print(f'  FAILED: {n}')
    print('ALL OK' if not bad else 'SOME PROBLEMS')
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
