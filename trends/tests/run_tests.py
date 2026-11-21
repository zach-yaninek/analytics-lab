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
  5. publishing: files, manifest, privacy scan, byte-identical reruns, a planted leak stops publication and is
     recorded in failed/; a file locked in latest/ stops the swap (E30) and leaves latest/ whole
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
    # the two planted x3 cohorts are adjacent, so each sits in the other's 'newer' or 'older' comparator; at half size
    # (quick) only one of them may clear the bar, which is the conservative rule working as intended
    if QUICK['on']:
        either = [y for y in ('2022', '2023') if ts.status.get(y) == 'stands_out_higher']
        ok('Touchscreen 2022 or 2023 installs stand out', bool(either),
           f"2022 {ts.status.get('2022')}, 2023 {ts.status.get('2023')}")
    else:
        ok('Touchscreen 2022 installs stand out', ts.status.get('2022') == 'stands_out_higher', ts.status.get('2022'))
        ok('Touchscreen 2023 installs stand out', ts.status.get('2023') == 'stands_out_higher', ts.status.get('2023'))
    others = k[k.status.str.startswith('stands_out') & ~(k.issue.isin(['Touchscreen', 'Electronics'])
                                                          & k.install_cohort.isin(['2022', '2023']))]
    ok('no other install cohort stands out on the planted fixture', others.empty,
       str(list(zip(others.install_cohort, others.issue))[:6]))
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
    publishing(fx, truth)
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
