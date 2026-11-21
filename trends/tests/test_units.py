#!/usr/bin/env python3
"""Unit tests with hand-computed values (no IPA data). Run alone or through run_tests.py; pytest also works.

  python3 -I trends/tests/test_units.py
"""
import ast
import datetime as dt
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TRENDS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRENDS))

import numpy as np  # noqa: E402
import openpyxl  # noqa: E402
import pandas as pd  # noqa: E402

from ipa_trends import cadence as CAD  # noqa: E402
from ipa_trends import cohorts as COH  # noqa: E402
from ipa_trends import config as CFG  # noqa: E402
from ipa_trends import exposure as EXP  # noqa: E402
from ipa_trends import inputs as INP  # noqa: E402
from ipa_trends import privacy as PRIV  # noqa: E402
from ipa_trends import stats  # noqa: E402
from ipa_trends.definitions import fleet_exposure_copy as FX  # noqa: E402
from ipa_trends.definitions import htm_copy as H  # noqa: E402
from ipa_trends.errors import ConfigError, InputError  # noqa: E402

T = pd.Timestamp


def close(a, b, tol=1e-12):
    return abs(float(a) - float(b)) <= tol


# ------------------------------------------------------------------------------------------------ cadence
def test_frequency_forms():
    for v, n in (('quarterly', 3), ('monthly', 1), ('Monthly', 1), ('bimonthly', 2), ('semiannual', 6),
                 ('half-yearly', 6), ('annual', 12), ('yearly', 12), ('5 months', 5), ('3M', 3), ('3m', 3),
                 ('1 year', 12), ('2 years', 24), (4, 4), ('7', 7)):
        assert CAD.parse_frequency(v).months == n, v


def test_frequency_rejected():
    for v in ('weekly', '2 weeks', 'fortnightly', 'daily', 'Q', 'QS-OCT', 'M', 'MS', 'A', '2Q', 'W-SUN', '0',
              '25 months', 3.5, None, True, 'sometimes'):
        try:
            CAD.parse_frequency(v)
        except ConfigError as e:
            assert e.code == 'E20'
        else:
            raise AssertionError(f'{v!r} was accepted')


def test_nouns_follow_the_frequency():
    q, m, f = CAD.Cadence(3), CAD.Cadence(1), CAD.Cadence(5)
    assert q.previous(4) == 'the previous four quarters' and m.previous(12) == 'the previous 12 months'
    assert q.variation == 'quarter-to-quarter variation' and f.variation == 'period-to-period variation'
    assert q.canonical == '3M' and f.noun == '5-month period' and m.previous(1) == 'the previous month'


def test_grids_and_labels():
    d0, d1 = T('2025-08-01'), T('2026-09-01')
    cases = {(3, 1, None): (['2025 Q3', '2025 Q4', '2026 Q1', '2026 Q2', '2026 Q3'], [61, 92, 90, 91, 62]),
             (3, 1, '2025-08-01'): (['Aug-Oct 2025', 'Nov 2025-Jan 2026', 'Feb-Apr 2026', 'May-Jul 2026',
                                     'Aug-Oct 2026'], [92, 92, 89, 92, 31]),
             (3, 10, None): (['FY2025 Q4', 'FY2026 Q1', 'FY2026 Q2', 'FY2026 Q3', 'FY2026 Q4'],
                             [61, 92, 90, 91, 62]),
             (5, 1, None): (['Jun-Oct 2025', 'Nov 2025-Mar 2026', 'Apr-Aug 2026'], [92, 151, 153]),
             (6, 1, None): (['2025 H2', '2026 H1', '2026 H2'], [153, 181, 62]),
             (12, 1, None): (['2025', '2026'], [153, 243])}
    for (n, ysm, anchor), (labels, days) in cases.items():
        g = CAD.period_grid(CAD.Cadence(n), d0, d1, ysm, 'end', anchor)
        assert list(g.label) == labels, (n, ysm, anchor, list(g.label))
        assert list(g.covered_days) == days
        assert g.covered_days.sum() == (d1 - d0).days            # periods tile the data window
    g1 = CAD.period_grid(CAD.Cadence(1), d0, d1)
    assert len(g1) == 13 and g1.label.iloc[-1] == 'Aug 2026' and g1.label_long.iloc[0] == 'August 2025'
    assert CAD.period_label(T('2026-10-01'), T('2027-01-01'), 10, 'end') == 'FY2027 Q1'
    assert CAD.period_label(T('2026-10-01'), T('2027-01-01'), 10, 'start') == 'FY2026 Q1'
    assert CAD.period_label(T('2016-01-01'), T('2019-01-01')) == '2016-18'
    assert CAD.period_label(T('2026-06-01'), T('2026-09-01')) == 'Jun-Aug 2026'


def test_edges_are_stable_across_runs():
    """A 5-month grid does not move when the data window moves (edges counted from a fixed anchor)."""
    a = CAD.period_grid(CAD.Cadence(5), T('2025-08-01'), T('2026-09-01'))
    b = CAD.period_grid(CAD.Cadence(5), T('2024-01-01'), T('2027-01-01'))
    assert set(a.period_start) <= set(b.period_start)


def test_statuses():
    g = CAD.period_grid(CAD.Cadence(3), T('2025-08-01'), T('2026-09-01'))
    share = {'2026-04-01': 0.05}
    s = CAD.assign_statuses(g, T('2025-08-01'), T('2026-09-01'), T('2026-09-10'), 14, share, 0.02)
    assert list(s.status) == ['partial', 'final', 'final', 'provisional', 'in_progress'], list(s.status)
    s = CAD.assign_statuses(g, T('2025-08-01'), T('2026-09-01'), T('2026-07-10'), 14, {}, 0.02)
    assert s.status[3] == 'provisional'                   # Q2 ends 1 Jul: only 9 days before the export
    s = CAD.assign_statuses(g, T('2025-08-01'), T('2026-09-01'), T('2026-07-15'), 14, {}, 0.02)
    assert s.status[3] == 'final'
    assert CAD.latest_final(s) == 3


def test_baseline_positions():
    g = CAD.period_grid(CAD.Cadence(3), T('2025-01-01'), T('2026-10-01'))
    g = CAD.assign_statuses(g, T('2025-01-01'), T('2026-10-01'), T('2026-12-01'), 14, {}, 0.02)
    latest = CAD.latest_final(g)
    assert g.label[latest] == '2026 Q3'
    pos, intended, enough = CAD.baseline_positions(g, latest, 12, CAD.Cadence(3))
    assert [g.label[p] for p in pos] == ['2025 Q3', '2025 Q4', '2026 Q1', '2026 Q2'] and intended == 4 and enough
    mask = pd.Series([True] * len(g))
    mask[pos[:3]] = False
    pos2, _, enough2 = CAD.baseline_positions(g, latest, 12, CAD.Cadence(3), mask=mask)
    assert len(pos2) == 1 and not enough2                  # needs at least half of the intended periods


def test_next_runs_and_cron():
    runs, cron = CAD.next_runs(CAD.Cadence(3), T('2026-10-01'), 14, 2)
    assert runs[0]['label'] == '2026 Q4' and runs[0]['due'] == '2027-01-15' and cron == '0 7 15 1,4,7,10 *'
    _, cron_m = CAD.next_runs(CAD.Cadence(1), T('2026-10-01'), 14, 2)
    assert cron_m == '0 7 15 * *'
    _, cron5 = CAD.next_runs(CAD.Cadence(5), T('2026-10-01'), 14, 2)
    assert cron5 is None                                    # 5 does not divide 12: daily --only-if-new instead


def test_cohort_bins():
    bins = CAD.cohort_bins(CAD.Cadence(12), '2016-01-01', last_install=T('2026-05-01'))
    labels = [b[0] for b in bins]
    assert labels[0] == 'Before 2016' and labels[1] == '2016' and labels[-1] == '2026', labels
    c = CAD.assign_cohorts(pd.Series([T('2010-03-01'), T('2022-12-31'), pd.NaT, T('2026-02-01')]), bins)
    assert list(c) == ['Before 2016', '2022', 'Unknown', '2026']
    ex = CAD.cohort_bins(None, None, ['2016-01-01', '2019-01-01', '2022-01-01', '2024-01-01', '2027-01-01'])
    assert [b[0] for b in ex] == ['Before 2016', '2016-18', '2019-21', '2022-23', '2024-26', 'From 2027']
    half = CAD.cohort_bins(CAD.Cadence(6), '2022-01-01', last_install=T('2022-08-01'))
    assert [b[0] for b in half] == ['Before 2022', '2022 H1', '2022 H2']


# ------------------------------------------------------------------------------------------------ config
def test_config_defaults_and_errors():
    P = CFG.resolve()
    assert P.cadence.months == 3 and P.baseline_months == 12 and P.history_months == 24
    assert CFG.resolve({'RERUN_FREQUENCY': '24 months'}).baseline_months == 24
    try:
        CFG.collect({'RERUN_FREQUENCEY': 'monthly'})
    except ConfigError as e:
        assert 'did you mean RERUN_FREQUENCY' in e.text()
    else:
        raise AssertionError('misspelt parameter accepted')
    try:
        CFG.resolve({'RERUN_FREQUENCY': 'weekly', 'YEAR_START_MONTH': 13, 'STRATIFY_BY': ['colour']})
    except ConfigError as e:
        assert len(e.problems) == 3
    else:
        raise AssertionError
    s = CFG.parse_sets(['RERUN_FREQUENCY=monthly', 'STRATIFY_BY=[model, family]', 'N_BOOT=500'])
    assert s == {'RERUN_FREQUENCY': 'monthly', 'STRATIFY_BY': ['model', 'family'], 'N_BOOT': 500}
    assert CFG.resolve({'STRATIFY_BY': '["model"]', 'CATEGORY_DIMS': '["fleet"]'}).STRATIFY_BY == ['model']


def test_notebook_parameters_cell():
    import nbformat
    nb = nbformat.read(str(TRENDS / 'ticket_trends.ipynb'), as_version=4)
    cells = [c for c in nb.cells if 'parameters' in c.metadata.get('tags', [])]
    assert len(cells) == 1
    vals = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(cells[0].source).body}
    assert vals == CFG.DEFAULTS
    for c in nb.cells:
        if c.cell_type == 'code':
            assert not c.get('outputs') and c.get('execution_count') is None
            assert not any(line.lstrip().startswith(('%', '!')) for line in c.source.splitlines())


def test_no_quarter_literals_in_code():
    """Nothing outside cadence.py and the parameter definitions is written for quarters or a fixed year."""
    allowed = {'cadence.py', 'config.py'}
    pat = re.compile(r"\bQ[1-4]\b|'quarter|\"quarter|\b3M\b|\b20[12]\d\b")
    bad = []
    for p in (TRENDS / 'ipa_trends').rglob('*.py'):
        if p.name in allowed or 'definitions' in p.parts or 'style' in p.parts or p.name == 'reconcile.py':
            continue
        text = p.read_text(encoding='utf-8')
        docs = set()                                   # docstrings are prose and may give examples
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(node):
                d = node.body[0]
                docs |= set(range(d.lineno, d.end_lineno + 1))
        for i, line in enumerate(text.splitlines(), 1):
            if i not in docs and pat.search(line.split('#', 1)[0]):
                bad.append(f'{p.name}:{i}')
    assert not bad, bad


# ------------------------------------------------------------------------------------------------ exposure
def _mini_pop(starts, installs, ends=None):
    n = len(starts)
    return pd.DataFrame({'serial': [f'X{i}' for i in range(n)], 'customer': ['Customer 001'] * n,
                         'model': ['M'] * n, 'family': ['F'] * n, 'service_status': ['S'] * n, 'country': ['USA'] * n,
                         'install_cohort': pd.Categorical(['2026'] * n), 'start': pd.to_datetime(starts),
                         'end': pd.to_datetime(ends or ['2026-09-01'] * n), 'install_date': pd.to_datetime(installs)})


def _mini_tickets(serials, times):
    n = len(serials)
    return pd.DataFrame({'serial': serials, 'ts': pd.to_datetime(times), 'group': ['Door'] * n,
                         'cgroup': ['Door'] * n, 'ctype': ['Deposit Door'] * n, 'monitoring': [False] * n})


def test_months_split_into_quarters():
    """Install 2026-02-10, calendar quarters to 2026-09-01: 50 / 91 / 62 days."""
    grid = CAD.period_grid(CAD.Cadence(3), T('2026-01-01'), T('2026-09-01'))
    pop = _mini_pop(['2026-02-10'], ['2026-02-10'])
    t = _mini_tickets(['X0', 'X0'], ['2026-03-31 23:59:59', '2026-04-01 00:00:00'])
    cat = EXP.issue_catalog(t)
    mp, outside = EXP.machine_periods(pop, t, grid, cat, [])
    m = mp.sort_values('period_pos').months.to_list()
    assert close(m[0], 50 / 30.4375) and close(m[1], 91 / 30.4375) and close(m[2], 62 / 30.4375)
    assert close(m[0], 1.6427104722792607) and close(m[1], 2.9897330595482545) and close(m[2], 2.0369609856262834)
    whole = FX.months_between(pd.Series([T('2026-02-10')]), pd.Series([T('2026-09-01')]))[0]
    assert close(sum(m), whole) and close(whole, 6.669404517453799)
    assert close(FX.months_between(pd.Series([T('2025-08-01')]), pd.Series([T('2026-09-01')]))[0],
                 13.010266940451745)
    t_by = mp.set_index('period_pos')['all']
    assert t_by[0] == 1 and t_by[1] == 1 and outside == 0  # 23:59:59 on 31 Mar is Q1; midnight 1 Apr is Q2


def test_age_band_per_period():
    """Age at the midpoint of the machine's exposure inside each period (fleet_exposure's halves rule)."""
    grid = CAD.period_grid(None, T('2025-08-01'), T('2026-09-01'),
                           explicit_edges=['2025-08-01', '2026-02-15', '2026-09-01'])
    pop = _mini_pop(['2025-08-01'], ['2021-12-01'])
    cat = EXP.issue_catalog(_mini_tickets([], []))
    mp, _ = EXP.machine_periods(pop, _mini_tickets([], []), grid, cat, [])
    assert list(mp.sort_values('period_pos').age_band.astype(str)) == ['2-4', '4-6']


def test_ledger_and_removal():
    a = pd.DataFrame({'serial': ['A', 'B', 'C'], 'account': ['x', 'y', 'y'], 'model': ['M'] * 3, 'family': ['F'] * 3,
                      'service_status': ['S'] * 3, 'service_plan': ['P'] * 3, 'ownership': [None] * 3,
                      'country': ['USA'] * 3, 'install_date': pd.to_datetime(['2020-01-01'] * 3),
                      'go_live_date': pd.NaT})
    b = a[a.serial != 'B'].assign(account=lambda d: d.account.where(d.serial != 'C', 'z'))
    led, newest = INP.build_ledger([(T('2026-01-14'), a), (T('2026-03-14'), b)])
    led = led.set_index('serial')
    assert newest == T('2026-03-14') and led.loc['A'].on_newest and not led.loc['B'].on_newest
    assert led.loc['B'].removal_estimate == T('2026-02-12')     # midway between 14 Jan and 14 Mar (59 days)
    assert led.loc['C'].account == 'z'                            # attributes from the newest listing
    one, _ = INP.build_ledger([(T('2026-01-14'), a)])
    assert one.on_newest.all() and list(one.serial) == ['A', 'B', 'C']


def test_account_labels_reproduce_pseudonyms():
    labels = INP.account_labels({'b', 'a', 'c'}, ['c', 'd', 'e'])
    assert labels == {'a': 'Customer 001', 'b': 'Customer 002', 'c': 'Customer 003', 'd': 'Customer 004',
                      'e': 'Customer 005'}
    many = INP.account_labels({f'acct{i:04d}' for i in range(1001)}, [])
    order = sorted(many.values())                                  # sorted as strings, as the bootstrap order was
    assert order.index('Customer 1000') == order.index('Customer 100') + 1


# ------------------------------------------------------------------------------------------------ statistics
def test_byar_and_bh():
    lo, hi = FX.byar(np.array([0, 10]))
    assert close(lo[0], 0) and abs(hi[0] - 3.668) < 1e-3 and abs(lo[1] - 4.787) < 1e-3 and abs(hi[1] - 18.391) < 1e-3
    q = H.bh(np.array([0.01, 0.04, 0.03, 0.20]))
    assert np.allclose(q, [0.04, 0.0533333333, 0.0533333333, 0.20])
    assert np.isnan(FX.bh_q(np.array([np.nan, 0.01]))[0])


def test_dl_pool_worked_example():
    """y = (-0.1, 0, 0.05, 0.05), v = 0.002: Q = 7.5, C = 1,500, tau^2 = (7.5 - 3) / 1,500 = 0.003."""
    Q, C, df = stats.dl_pool([np.array([-0.1, 0, 0.05, 0.05])], [np.full(4, 0.002)])
    assert close(Q, 7.5, 1e-9) and close(C, 1500, 1e-9) and df == 3 and close((Q - df) / C, 0.003, 1e-12)
    # a one-period spike is pulled in to +-3 standard errors
    Q2, _, _ = stats.dl_pool([np.array([0, 0, 0, 1.0])], [np.full(4, 0.002)])
    assert Q2 < 500 * 1.0 ** 2


def test_tau2_rules():
    o = [np.array([100, 110, 90, 105, 95])] * 3
    e = [np.full(5, 100.0)] * 3
    tau2, f = stats.tau2_dl(o, e, [1, 1, 1], 0.001)
    assert f['estimable'] and tau2 >= 0.001
    tau2, f = stats.tau2_dl([np.array([3, 4, 2])], [np.array([3.0, 3.0, 3.0])], [1], 0.001)
    assert not f['estimable'] and tau2 == stats.TAU2_UNESTIMABLE  # cells expecting < 5 tickets do not count


def test_two_sided_p():
    assert abs(stats.two_sided_p(np.array([1.959964]))[0] - 0.05) < 1e-6
    assert np.isnan(stats.two_sided_p(np.array([np.nan]))[0])


def test_same_age_ratio():
    """Two cohorts, two age bands: cohort A has 20 + 30 tickets in 100 + 200 months; the other cohort's band rates
    are 30 / 300 = 0.1 and 40 / 400 = 0.1, so A expects 10 + 20 = 30 and its same-age ratio is 50 / 30."""
    O = np.array([[20, 30], [30, 40]])
    M = np.array([[100, 200], [300, 400]])
    ratio, e, o, dropped = COH.same_age_table(O, M, min_comparator=100)
    assert close(ratio[0], 50 / 30, 1e-12) and close(e[0], 30, 1e-12) and dropped[0] == 0
    ratio, e, o, dropped = COH.same_age_table(O, M, min_comparator=350)   # band 1's comparator (300) too small
    assert close(e[0], 20, 1e-12) and close(o[0], 30, 1e-12) and close(dropped[0], 20 / 50, 1e-12)


def test_day_factors():
    grid = CAD.period_grid(CAD.Cadence(1), T('2026-01-01'), T('2026-04-01'))
    days = pd.date_range('2026-01-01', '2026-03-31', freq='D')
    _, business = stats.day_types(T('2026-01-01'), T('2026-04-01'))
    flat = pd.DataFrame({'ts': np.repeat(days, 3)})
    f, w, _ = stats.day_factors(flat, grid, [0, 1, 2])
    assert close(w, 1.0, 1e-12) and np.allclose(f, 1.0)
    planted = pd.DataFrame({'ts': np.concatenate([np.repeat(d, 10 if b else 3) for d, b in zip(days, business)])})
    f, w, _ = stats.day_factors(planted, grid, [0, 1, 2])
    assert close(w, 0.3, 1e-9)                        # non-business days at 3 tickets vs 10
    assert f[1] > f[0]                                 # February (no holiday weekdays lost) vs January (2 holidays)


# ------------------------------------------------------------------------------------------------ inputs
def _workbook(path, header, rows, sheet='ipa_repair cases', title_rows=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for r in title_rows:
        ws.append(r)
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_reader_tolerances():
    d = Path(tempfile.mkdtemp())
    header = INP.CASE_REQUIRED
    row = ['C1', 'Fake Clinic 1', 'S1', dt.datetime(2026, 1, 5, 9, 30), 'General Case', 'Trouble Closed', 'Network',
           'Firewall', 'text']
    _workbook(d / 'a.xlsx', ['  case number '] + header[1:], [row, [None] * 9, ['Generated By: Fake'] + [None] * 8],
              title_rows=[['Report title'], ['As of today']])
    w = INP.Warnings()
    fr, meta = INP.read_sheet(d / 'a.xlsx', 'ipa_repair cases', INP.CASE_REQUIRED, INP.CASE_OPTIONAL, INP.CASE_KNOWN,
                              {}, w, 'case export')
    assert meta['header_row'] == 3 and len(fr) == 1 and meta['non_data_rows'] == 1 and meta['blank_rows'] == 1
    renamed = ['Case Number', 'Account Name', 'Serial #', 'Date/Time Opened', 'Case Record Type', 'Status',
               'Trouble Code', 'Trouble Code Cat.', 'Trouble Reported']
    _workbook(d / 'b.xlsx', renamed, [row])
    try:
        INP.read_sheet(d / 'b.xlsx', 'ipa_repair cases', INP.CASE_REQUIRED, INP.CASE_OPTIONAL, INP.CASE_KNOWN, {},
                       INP.Warnings(), 'case export')
    except InputError as e:
        assert e.code == 'E03' and "COLUMN_ALIASES = {'Trouble Code Cat.': 'Trouble Code Category'}" in e.message
        assert 'Fake Clinic' not in e.text()
    else:
        raise AssertionError
    fr, _ = INP.read_sheet(d / 'b.xlsx', 'ipa_repair cases', INP.CASE_REQUIRED, INP.CASE_OPTIONAL, INP.CASE_KNOWN,
                           {'Trouble Code Cat.': 'Trouble Code Category'}, INP.Warnings(), 'case export')
    assert 'Trouble Code Category' in fr.columns
    _workbook(d / 'c.xlsx', header, [row], sheet='Report 1')
    w = INP.Warnings()
    INP.read_sheet(d / 'c.xlsx', 'ipa_repair cases', INP.CASE_REQUIRED, INP.CASE_OPTIONAL, INP.CASE_KNOWN, {}, w,
                   'case export')
    assert any(x['code'] == 'W18' for x in w.items)
    (d / 'old.xls').write_bytes(b'not a zip')
    try:
        INP.read_sheet(d / 'old.xls', 's', [], [], [], {}, INP.Warnings(), 'case')
    except InputError as e:
        assert e.code == 'E01' and '.xls' in e.message


def test_dates_as_text():
    s = pd.Series(['11/21/2025 7:11 AM', '01/02/2026 1:05 PM', None, '12/31/2025 11:59 PM'])
    out, f = INP.parse_dates(s, 'Date/Time Opened', 'case')
    assert out[0] == T('2025-11-21 07:11') and out[1] == T('2026-01-02 13:05') and pd.isna(out[2])
    assert out[3] == T('2025-12-31 23:59') and f['format'] == '%m/%d/%Y %I:%M %p'
    mixed = pd.Series(['13/04/2027 10:00', '04/13/2027 10:00'])
    try:
        INP.parse_dates(mixed, 'Date/Time Opened', 'case')
    except InputError as e:
        assert e.code == 'E05'
    else:
        raise AssertionError('mixed day-first and month-first dates accepted')
    tz, f = INP.parse_dates(pd.Series(['2026-01-05T14:30:00Z']), 'Date/Time Opened', 'case')
    assert tz[0] == T('2026-01-05 09:30') and f['tz_converted'] == 1         # UTC -> US Eastern (EST)
    bad = pd.Series(['not a date'])
    try:
        INP.parse_dates(bad, 'Date/Time Opened', 'case')
    except InputError as e:
        assert e.code == 'E05' and 'not a date' not in e.text()
    else:
        raise AssertionError


def test_clock_conversion():
    w = INP.Warnings()
    s = pd.Series(pd.to_datetime(['2026-03-31 23:30', '2026-11-01 01:30']))
    out, amb = INP.to_eastern(s, 'America/Chicago', w)
    assert out[0] == T('2026-04-01 00:30') and amb == 1         # 23:30 Central on 31 Mar is Q2 in Eastern


# ------------------------------------------------------------------------------------------------ privacy
def test_privacy_scan_and_masking():
    real = PRIV.real_sets({'Fake Memorial Hospital 017'}, {'FT9000123', '90000042'}, {'90000042'},
                          {'text': {'Testville 05'}, 'digit': {'10098'}})
    clean = pd.DataFrame({'stratum': ['2026 Q2', 'FY2027', 'LVD-Remote-2.0'], 'run_id': ['2026-11-14_3M_a1b2c3d4'] * 3})
    assert PRIV.scan_frame(clean, real, 't') == {}
    leak = pd.DataFrame({'stratum': ['ok', 'fake memorial hospital 017 east'], 'note': ['zip 10098', '']})
    hits = PRIV.scan_frame(leak, real, 't')
    assert hits == {'t.stratum': 1, 't.note': 1}
    assert PRIV.scan_texts(['Customer at Testville 05 site'], real, 'r') == {'r': 1}
    assert '[redacted]' in PRIV.redact('ticket at Fake Memorial Hospital 017 today', real)


def test_repository_allowlist():
    """Only code, docs, tests, the empty notebook, example parameters and public aggregates are committed."""
    try:
        listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '.'],
                                cwd=TRENDS, capture_output=True, text=True, timeout=30).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return
    allowed = re.compile(r'(\.py|\.md|\.toml|\.txt|\.ipynb|\.example\.yaml|\.gitignore|\.mplstyle|'
                         r'reconcile_[\w-]+\.yaml|request_types_v0\.csv|reference/reconcile_[\w-]+\.json)$')
    bad = [f for f in listed if not allowed.search(f)]
    assert not bad, bad


def test_rates_many_equals_group_rates():
    """The vectorised rates equal the copied fleet_exposure.group_rates for every key (the committed interval rule)."""
    from ipa_trends import rates as RT
    rng = np.random.default_rng(3)
    n = 600
    m = pd.DataFrame({'serial': [f'S{i}' for i in range(n)],
                      'customer': rng.choice([f'Customer {i:03d}' for i in range(1, 41)], n),
                      'grp': rng.choice(['a', 'b', 'c', 'tiny', None], n, p=[0.4, 0.3, 0.2, 0.05, 0.05]),
                      'months': np.where(rng.random(n) < 0.05, 0.0, rng.uniform(0.5, 3.0, n))})
    m.loc[m.grp == 'tiny', 'customer'] = 'Customer 001'          # a level in one account: not estimable
    for k in ('k1', 'k2', 'zero'):
        m[k] = rng.poisson(0.2 if k != 'zero' else 0.0, n) * (m.months > 0)
    clusters = sorted(m.customer.unique())
    W = FX.boot_weights(len(clusters), 300, 11)
    many = RT.rates_many(m, 'grp', ['k1', 'k2', 'zero'], W, clusters)
    for k in ('k1', 'k2', 'zero'):
        ref, _ = FX.group_rates(m, 'grp', W, clusters, tickets=k)
        mine = many[k]
        assert list(ref.grp) == list(mine.grp)
        for c in ('machines', 'machines_with_ticket', 'accounts', 'tickets'):
            assert (ref[c].to_numpy() == mine[c].to_numpy()).all(), (k, c)
        for c in ('months', 'rate_per_100', 'byar_lo', 'byar_hi', 'boot_lo', 'boot_hi', 'ratio_to_fleet', 'ci_lo',
                  'ci_hi', 'ratio_lo', 'ratio_hi'):
            assert np.allclose(ref[c].to_numpy(float), mine[c].to_numpy(float), rtol=1e-12, atol=1e-15,
                               equal_nan=True), (k, c)
        assert list(ref.ci_method) == list(mine.ci_method) and list(ref.vs_fleet) == list(mine.vs_fleet), k


TESTS = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f'  [PASS] {t.__name__}')
        except Exception as e:                      # noqa: BLE001
            failed += 1
            print(f'  [FAIL] {t.__name__}: {type(e).__name__}: {e}')
    print(f'{len(TESTS) - failed}/{len(TESTS)} unit tests pass')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
