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
from ipa_trends import compare as CMP  # noqa: E402
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


def _edges_445(start, stop):
    """4-4-5 week periods (28, 28, 35 days) from `start` until an edge reaches `stop`."""
    edges, k = [T(start)], 0
    while edges[-1] < T(stop):
        edges.append(edges[-1] + pd.Timedelta(days=(28, 28, 35)[k % 3]))
        k += 1
    return [f'{e:%Y-%m-%d}' for e in edges]


def test_custom_periods():
    """PERIOD_EDGES: the wording says 'period' whatever the length, months and the canonical form stay those of
    RERUN_FREQUENCY (run id, dashboard key), and the baseline counts the explicit periods inside BASELINE_MONTHS."""
    from ipa_trends import report as REP
    yearly = ['2024-01-01', '2025-01-01', '2026-01-01', '2027-01-01']
    P = CFG.resolve({'PERIOD_EDGES': yearly})
    cad = P.cadence
    assert isinstance(cad, CAD.CustomPeriods) and cad.months == 3 and cad.canonical == '3M'
    assert (cad.noun, cad.plural, cad.variation) == ('period', 'periods', 'period-to-period variation')
    assert cad.previous(1) == 'the previous period' and cad.previous(4) == 'the previous four periods'
    assert REP._kind(cad) == 'Report (custom periods)' and P.public()['RERUN_FREQUENCY'] == '3M'
    assert type(CFG.resolve().cadence) is CAD.Cadence
    d0, d1, export = T('2024-01-01'), T('2026-11-15'), T('2026-11-15')

    def baseline(edges, d0=d0):
        g = CAD.period_grid(None, d0, d1, explicit_edges=edges)
        g = CAD.assign_statuses(g, d0, d1, export, 14, {}, 0.02)
        latest = CAD.latest_final(g)
        pos, intended, enough = CAD.baseline_positions(g, latest, 12, CAD.CustomPeriods(3, tuple(edges)))
        return g.label[latest], [g.label[p] for p in pos], intended, enough
    # yearly: 2025 against 2024 (before, 12 // 3 = 4 periods were intended and nothing was ever tested)
    assert baseline(yearly) == ('2025', ['2024'], 1, True)
    half = ['2024-01-01', '2024-07-01', '2025-01-01', '2025-07-01', '2026-01-01', '2026-07-01', '2027-01-01']
    assert baseline(half) == ('2026 H1', ['2025 H1', '2025 H2'], 2, True)
    lab, pos, intended, enough = baseline(_edges_445('2024-01-01', '2026-11-15'))
    assert lab == '28 Sep-25 Oct 2026' and len(pos) == 12 and intended == 12 and enough
    # a 53-week year is longer than the 12-month window: its baseline is the one period before, as for long cadences
    year53 = ['2023-12-31', '2025-01-05', '2026-01-04', '2027-01-03']
    assert baseline(year53, d0=T('2023-12-31')) == ('5 Jan 2025-3 Jan 2026', ['31 Dec 2023-4 Jan 2025'], 1, True)
    # explicit periods the data do not reach still count as intended (a back-run to 2024 has none of its one)
    early = ['2023-01-01'] + yearly
    g = CAD.assign_statuses(CAD.period_grid(None, d0, d1, explicit_edges=early), d0, d1, export, 14, {}, 0.02)
    pos, intended, enough = CAD.baseline_positions(g, 0, 12, CAD.CustomPeriods(3, tuple(early)))
    assert g.label[0] == '2024' and pos == [] and intended == 1 and not enough
    assert CAD.baseline_positions(g, 0, 12, CAD.CustomPeriods(3, tuple(yearly)))[1:] == (1, False)   # none before


def test_next_runs_and_cron():
    runs, cron = CAD.next_runs(CAD.Cadence(3), T('2026-10-01'), 14, 2)
    assert runs[0]['label'] == '2026 Q4' and runs[0]['due'] == '2027-01-15' and cron == '0 7 15 1,4,7,10 *'
    _, cron_m = CAD.next_runs(CAD.Cadence(1), T('2026-10-01'), 14, 2)
    assert cron_m == '0 7 15 * *'
    _, cron5 = CAD.next_runs(CAD.Cadence(5), T('2026-10-01'), 14, 2)
    assert cron5 is None                                    # 5 does not divide 12: daily --only-if-new instead


def test_next_runs_after_the_export():
    """A run's next run is due after its own export date. Exported 15 Nov 2026 with Oct still provisional (10.4% of
    its tickets open), Oct's due date (15 Nov) has passed: it needs a newer export, and the next run is Nov's. A
    back-run (LATEST_PERIOD) is not part of the schedule: it names neither, and its manifest no next_run_after."""
    from ipa_trends import engine
    from ipa_trends import publish as PUB
    from ipa_trends.notebook import next_run_lines
    d0, d1, ex = T('2026-01-01'), T('2026-11-15'), T('2026-11-15')

    def summary(P, months):
        g = CAD.period_grid(CAD.Cadence(months), d0, d1)
        g = CAD.assign_statuses(g, d0, d1, ex, 14, {'2026-10-01': 0.104}, 0.02)
        return engine.make_summary(P, g, None, {}, {}, None, None, None, None, None, ex, 'EXTRACTED_AT', d0, d1)
    M = CFG.resolve({'RERUN_FREQUENCY': 'monthly'})
    s = summary(M, 1)
    assert s['next_runs'][0] == {'label': 'Nov 2026', 'period_start': '2026-11-01', 'period_end': '2026-12-01',
                                 'due': '2026-12-15'}
    assert len(s['next_runs']) == 4 and all(r['due'] > '2026-11-15' for r in s['next_runs'])
    assert s['needs_newer_export'] == [{'label': 'Oct 2026', 'reason': '10.4% of its tickets were still open when '
                                                                       'exported'}]
    assert PUB.next_run_after(s, M) == '2026-12-15'
    assert next_run_lines(s, bold=False) == ['Next run due: 2026-12-15 (for Nov 2026).', 'Oct 2026 needs a newer '
                                             'export: 10.4% of its tickets were still open when exported.']
    B = CFG.resolve({'RERUN_FREQUENCY': 'monthly', 'LATEST_PERIOD': 'Sep 2026'})
    b = summary(B, 1)
    assert b['next_runs'] == b['needs_newer_export'] == [] and PUB.next_run_after(b, B) is None
    assert next_run_lines(b) == []
    q = summary(CFG.resolve(), 3)                          # quarterly: unchanged, Q4 due 15 Jan
    assert q['next_runs'][0]['label'] == '2026 Q4' and q['next_runs'][0]['due'] == '2027-01-15'
    assert q['needs_newer_export'] == []


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


def test_parameter_names_in_the_wrong_case():
    """papermill passes names as typed: a lower-case parameter name stops the run instead of leaving the default in
    force. Suggestions ignore case; functions, modules and _names are not parameters; a misspelt name next to the
    right one (still in memory after an earlier Run All) gets the Restart & Run All hint."""
    import types

    def problem(fn):
        try:
            fn()
        except ConfigError as e:
            return e
        raise AssertionError('accepted')
    for ns in ({'rerun_frequency': 'monthly'}, {'Rerun_Frequency': 'monthly', 'RERUN_FREQUENCY': 'quarterly'}):
        e = problem(lambda: CFG.collect(ns))
        assert e.code == 'E22' and 'parameter names are written in capitals: RERUN_FREQUENCY' in e.text(), e.text()
    assert CFG.collect({'seed': lambda: 0, 'stats': types.ModuleType('stats'), '_n_boot': 5, 'params': {},
                        'N_BOOT': 500}) == {'N_BOOT': 500}
    left = problem(lambda: CFG.collect({'RERUN_FREQUENCEY': 'monthly', 'RERUN_FREQUENCY': 'monthly'})).text()
    assert 'did you mean RERUN_FREQUENCY?' in left and 'Restart & Run All' in left
    assert 'Restart & Run All' not in problem(lambda: CFG.collect({'RERUN_FREQUENCEY': 'monthly'})).text()
    for item, right in (('rerun_frequency=monthly', 'RERUN_FREQUENCY'), ('n_bot=500', 'N_BOOT')):
        e = problem(lambda: CFG.parse_sets([item]))
        assert e.code == 'E22' and right in e.text() and 'Restart' not in e.text(), e.text()


def test_parameter_files_and_text_values():
    """A relative --params path is also looked for in the trends folder; a malformed YAML or JSON file is E22 with the
    line and column (not E99); a date, a colon or a # in a text value survives YAML and --set."""
    import os

    def problem(fn):
        try:
            fn()
        except ConfigError as e:
            return e
        raise AssertionError('accepted')
    d = Path(tempfile.mkdtemp())
    here = os.getcwd()
    try:
        os.chdir(d)
        assert CFG.load_file('params/quarterly.example.yaml')['RERUN_FREQUENCY'] == 'quarterly'
        e = problem(lambda: CFG.load_file('params/missing.yaml'))
        # resolved on both sides: on Windows the temp folder's short name (RUNNER~1) resolves to the long one
        assert e.code == 'E22' and str((Path.cwd() / 'params' / 'missing.yaml').resolve()) in e.message, e.message
        assert str((TRENDS / 'params' / 'missing.yaml').resolve()) in e.message, e.message
    finally:
        os.chdir(here)
    (d / 'win.yaml').write_text('OUTPUT_DIR: "C:\\Users\\me\\OneDrive - IPA\\Trends"\n', encoding='utf-8')
    e = problem(lambda: CFG.load_file(d / 'win.yaml'))
    assert e.code == 'E22' and 'line 1, column' in e.message and 'single quotes' in e.fix, e.text()
    (d / 'ok.yaml').write_text("OUTPUT_DIR: 'C:\\Users\\me\\OneDrive - IPA\\Trends'\nLATEST_PERIOD: 2026-04-01\n"
                               "REPORT_TITLE: 'IPA: quarterly trends'\n", encoding='utf-8')
    P = CFG.resolve(CFG.load_file(d / 'ok.yaml'))
    assert (P.OUTPUT_DIR, P.LATEST_PERIOD, P.REPORT_TITLE) == ('C:\\Users\\me\\OneDrive - IPA\\Trends', '2026-04-01',
                                                               'IPA: quarterly trends')
    (d / 'comma.json').write_text('{"RERUN_FREQUENCY": "monthly",\n "N_BOOT": 500,\n}\n', encoding='utf-8')
    e = problem(lambda: CFG.load_file(d / 'comma.json'))
    # the position differs by Python version (3.13: the comma, line 2; 3.11-3.12: the closing brace, line 3)
    assert e.code == 'E22' and re.search(r'line \d+, column \d+', e.message), e.text()
    (d / 'bom.json').write_bytes(b'\xef\xbb\xbf{"RERUN_FREQUENCY": "monthly"}')
    assert CFG.load_file(d / 'bom.json') == {'RERUN_FREQUENCY': 'monthly'}
    (d / 'latin1.yaml').write_bytes('REPORT_TITLE: Caf\xe9\n'.encode('latin-1'))
    assert 'UTF-8' in problem(lambda: CFG.load_file(d / 'latin1.yaml')).message
    assert CFG.parse_sets(['REPORT_TITLE=IPA: quarterly trends', 'LATEST_PERIOD=2026-04-01', 'CASE_SHEET=Report #3',
                           'CASE_EXPORTS=[a.xlsx, b.xlsx]', 'N_BOOT=500']) == {
        'REPORT_TITLE': 'IPA: quarterly trends', 'LATEST_PERIOD': '2026-04-01', 'CASE_SHEET': 'Report #3',
        'CASE_EXPORTS': ['a.xlsx', 'b.xlsx'], 'N_BOOT': 500}
    assert CFG.parse_sets(["REPORT_TITLE='IPA: q'", 'LATEST_PERIOD=null', 'EQUIPMENT_LISTS=*.xlsx']) == {
        'REPORT_TITLE': 'IPA: q', 'LATEST_PERIOD': None, 'EQUIPMENT_LISTS': '*.xlsx'}
    assert CFG.resolve({'LATEST_PERIOD': dt.date(2026, 4, 1)}).LATEST_PERIOD == '2026-04-01'
    assert CFG.resolve({'LATEST_PERIOD': 2026}).LATEST_PERIOD == '2026'           # an annual label read as a number
    assert CFG.resolve().PRIVACY_ALLOW == [] and CFG.resolve({'PRIVACY_ALLOW': 'Remote'}).PRIVACY_ALLOW == ['Remote']
    assert problem(lambda: CFG.resolve({'PRIVACY_ALLOW': ['10098']})).code == 'E22'


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


def test_notebook_asks_for_restart_and_run_all():
    """A plain Run All keeps names from earlier runs (a corrected typo would still stop the run), so the notebook's
    instructions say Restart & Run All, and the committed notebook is the generated one."""
    import nbformat
    sys.path.insert(0, str(TRENDS / 'tests'))
    import make_notebook
    nb = nbformat.read(str(TRENDS / 'ticket_trends.ipynb'), as_version=4)
    assert nb.cells[0].cell_type == 'markdown' and 'Restart & Run All' in nb.cells[0].source
    assert '**Run All.**' not in nb.cells[0].source
    assert [c.source for c in nb.cells] == [c.source for c in make_notebook.build().cells]


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
    """y = (-0.1, 0, 0.05, 0.05), v = 0.002: Q = 7.5, C = 1,500, tau^2 = (7.5 - 3) / 1,500 = 0.003; no residual
    is beyond 3 total standard deviations sqrt(0.002 + 0.003), so winsorising changes nothing."""
    Q, C, df = stats.dl_pool([np.array([-0.1, 0, 0.05, 0.05])], [np.full(4, 0.002)])
    assert close(Q, 7.5, 1e-9) and close(C, 1500, 1e-9) and df == 3 and close((Q - df) / C, 0.003, 1e-12)
    # a one-period doubling in one of 11 pooled cells is pulled in: unwinsorised it alone gives tau^2 = 0.0054
    flat = [0.01 * np.array([1, -1, 1, -1, 1, -1])] * 10
    spike = [np.array([0, 0, 0, 0, 0, math.log(2)])]
    v = [np.full(6, 0.002)] * 11
    Q0, C0, df0 = stats.dl_pool(flat + spike, v, passes=0)
    Q1, C1, df1 = stats.dl_pool(flat + spike, v)
    raw0 = (500 * 5 / 6 * math.log(2) ** 2 + 10 * 0.3 - 55) / 27500                 # 0.00539
    assert close((Q0 - df0) / C0, raw0, 1e-12) and (Q1 - df1) / C1 < 0.1 * raw0


def test_tau2_rules():
    o = [np.array([100, 110, 90, 105, 95])] * 3
    e = [np.full(5, 100.0)] * 3
    tau2, f = stats.tau2_dl(o, e, [1, 1, 1], 0.001)
    assert f['estimable'] and tau2 >= 0.001
    # broken series are left out, not winsorised: a Category that vanished (no ticket in the last period where 82
    # are expected) or appeared (none in the first, 20 expected); a zero inside the history is ordinary variation
    gone = [np.array([100, 104, 96, 112, 0]), np.array([0, 22, 18, 21, 39])]
    tau2_gone, f = stats.tau2_dl(o + gone, e + [np.full(5, x.sum() / 5) for x in gone], [1] * 5, 0.001)
    assert tau2_gone == tau2 and f['broken_cells'] == 2 and f['cells'] == 3
    f = stats.tau2_dl(o + [np.array([8, 6, 0, 9, 7])], e + [np.full(5, 6.0)], [1] * 4, 0.001)[1]
    assert f['broken_cells'] == 0 and f['cells'] == 4
    tau2, f = stats.tau2_dl([np.array([3, 4, 2])], [np.array([3.0, 3.0, 3.0])], [1], 0.001)
    assert not f['estimable'] and tau2 == stats.TAU2_UNESTIMABLE  # cells expecting < 5 tickets do not count


def test_tau2_keeps_ordinary_variation():
    """One cell expecting 800 tickets a period, log-normal period effects with tau^2 = 0.01 over 10 periods: the
    mean estimate is within 10% of 0.01. Winsorising on the sampling standard deviation alone clipped about a
    third of the periods and gave about 0.005."""
    rng = np.random.default_rng(2)
    est = []
    for _ in range(1000):
        o = rng.poisson(800 * np.exp(rng.normal(0, 0.1, 10) - 0.005)).astype(float)
        est.append(stats.tau2_dl([o], [np.full(10, o.sum() / 10)], [1], 1e-12)[1]['raw'])
    assert abs(np.mean(est) - 0.01) < 0.001, np.mean(est)


def test_baseline_phrase_and_sentences():
    """Each row is worded from its own baseline; untested rows give the rate and the reason, never a ratio."""
    from types import SimpleNamespace
    q, m = CAD.Cadence(3), CAD.Cadence(1)
    assert CMP.baseline_phrase(q, 4, 4) == 'the previous four quarters'
    assert CMP.baseline_phrase(q, 3, 4) == 'three of the previous four quarters (those with complete Category labels)'
    assert CMP.baseline_phrase(m, 11, 12) == '11 of the previous 12 months (those with complete Category labels)'
    nan = float('nan')
    base = dict(stratum_dim='fleet', stratum='Fleet', issue='Door', rate_latest=1.92, change_ratio=1.07, ci_lo=0.95,
                ci_hi=1.2, status='no_clear_change', not_tested_reason='', baseline_periods_used=4,
                baseline_set='all', sustained=False, previous_status='')

    def say(cad=q, **kw):
        return CMP.sentence(SimpleNamespace(**{**base, **kw}), '2025 Q1', cad, 4)
    assert say() == ('Door: 1.92 per 100 installed machine-months in 2025 Q1, 7% above the previous four quarters '
                     '(95% interval -5% to +20%).')
    assert say(baseline_periods_used=3, baseline_set='labels') == (
        'Door: 1.92 per 100 installed machine-months in 2025 Q1, 7% above three of the previous four quarters (those '
        'with complete Category labels; 95% interval -5% to +20%).')
    assert say(change_ratio=0.998).startswith('Door: 1.92 per 100 installed machine-months in 2025 Q1, level with')
    untested = say(stratum_dim='install_cohort', stratum='2018', status='not_tested', change_ratio=nan, ci_lo=nan,
                   ci_hi=nan, not_tested_reason='fewer than 10 tickets expected')
    assert untested == ('Door (install cohort 2018): 1.92 per 100 installed machine-months in 2025 Q1; not tested '
                        '(fewer than 10 tickets expected).')
    big = say(status='not_tested', change_ratio=2.04, ci_lo=0.9, ci_hi=4.6, not_tested_reason='unknown stratum')
    assert '%' not in big and big.endswith('; not tested (unknown stratum).')
    gone = say(status='not_tested', rate_latest=nan, change_ratio=float('inf'), not_tested_reason='not estimable')
    assert 'nan' not in gone and 'inf' not in gone and 'no installed machine-months in 2025 Q1' in gone
    flag = dict(status='higher', change_ratio=1.5, ci_lo=1.25, ci_hi=1.8, sustained=True)
    assert say(previous_status='higher', **flag).endswith('not proof of a problem; also flagged last quarter.')
    assert say(previous_status='watch_higher', **flag).endswith('; also on the watch list last quarter.')
    assert say(status='watch_higher', change_ratio=1.5, ci_lo=0.98, ci_hi=2.3, sustained=True,
               previous_status='higher').endswith(': could still be chance; also flagged last quarter.')
    custom = CMP.sentence(SimpleNamespace(**{**base, **flag, 'sustained': False, 'baseline_periods_used': 1}),
                          '28 Sep-25 Oct 2026', CAD.CustomPeriods(3, ('2026-08-31', '2026-09-28', '2026-10-26')), 1)
    assert 'above the previous period' in custom and 'beyond normal period-to-period variation' in custom


def test_baseline_labels_per_row():
    """changes.csv names each row's own baseline: issue-level rows leave out a period with incomplete labels."""
    from types import SimpleNamespace
    from ipa_trends import publish as PUB
    periods = pd.DataFrame({'period_key': ['2024-01-01', '2024-04-01', '2024-07-01', '2024-10-01', '2025-01-01'],
                            'label': ['2024 Q1', '2024 Q2', '2024 Q3', '2024 Q4', '2025 Q1']})
    changes = pd.DataFrame({'stratum_dim': ['fleet', 'fleet'], 'stratum': ['Fleet', 'Fleet'],
                            'issue_key': ['all', 'group|Door'], 'baseline_periods_used': [4, 3],
                            'baseline_set': ['all', 'labels'], 'status': ['no_clear_change'] * 2})
    result = SimpleNamespace(tables={'periods': periods, 'changes': changes}, params={'RERUN_FREQUENCY': '3M'},
                             summary={'latest_period_key': '2025-01-01', 'latest_label': '2025 Q1',
                                      'baseline_labels': ['2024 Q1', '2024 Q2', '2024 Q3', '2024 Q4']},
                             facts={'comparison': {'baseline_positions': [0, 1, 2, 3],
                                                   'baseline_label_positions': [1, 2, 3]}})
    out = PUB.prepare_tables(result, 'run', 'hash')['changes']
    assert list(out.baseline_labels) == ['2024 Q1; 2024 Q2; 2024 Q3; 2024 Q4', '2024 Q2; 2024 Q3; 2024 Q4']
    assert list(out.baseline_set) == ['all', 'labels'] and list(out.baseline_periods_used) == [4, 3]


def _taxonomy_tickets(quarters, split_from=None):
    """Electro/Mechanical tickets per quarter from 2025 Q1: Deposit Door 30 (Door) and SAM 20 (Mechanical); from
    quarter `split_from`, Deposit Door is written 'Deposit Door - Latch' / '- Sensor', both mapped to Door (as in a
    REQUEST_TYPES_LOCAL file). Software: 10 a quarter, one of them a 'Training' ticket in the last quarter only."""
    rows = []
    for q in range(quarters):
        cats = [('SAM', 'Mechanical', 20), ('Issue', 'Software', 10 - (q == quarters - 1))]
        if split_from is not None and q >= split_from:
            cats += [('Deposit Door - Latch', 'Door', 15), ('Deposit Door - Sensor', 'Door', 15)]
        else:
            cats += [('Deposit Door', 'Door', 30)]
        if q == quarters - 1:
            cats += [('Training', 'Software', 1)]      # 10% of Software but one ticket: too few to judge
        for cat, grp, n in cats:
            tc = 'Software' if grp == 'Software' else 'Electro/Mechanical'
            start = T('2025-01-15') + pd.DateOffset(months=3 * q)
            rows += [{'ts': start + pd.Timedelta(hours=i), 'trouble_code': tc, 'category': cat, 'cgroup': grp,
                      'ctype': cat, 'monitoring': False, 'unmapped': False} for i in range(n)]
    return pd.DataFrame(rows)


def _fleet_category_cells(t, latest_start, base_periods):
    """Fleet Category rows of a comparison: tickets in the latest quarter, expected = the baseline quarters' mean."""
    now = t[t.ts >= T(latest_start)].groupby(['cgroup', 'ctype']).size()
    base = t[t.ts < T(latest_start)].groupby(['cgroup', 'ctype']).size() / base_periods
    keys = sorted(set(now.index) | set(base.index))
    return pd.DataFrame({'stratum_dim': 'fleet', 'issue_level': 'category', 'issue_group': [k[0] for k in keys],
                         'issue': [k[1] for k in keys], 'tickets_latest': [now.get(k, 0) for k in keys],
                         'expected_latest': [base.get(k, 0.0) for k in keys]})


def test_taxonomy_gate_appeared_and_vanished():
    """A split Category mapped in REQUEST_TYPES_LOCAL leaves no unmapped tickets, but its new names appear and the
    old name vanishes: the Category-level tests of the Trouble Code's groups are suspended, the groups stay tested.
    It holds at the split quarter and while the baseline still holds a quarter before the split."""
    groups = {'Electro/Mechanical': ['Door', 'Mechanical', 'Not categorised'], 'Software': ['Software']}
    grid = CAD.period_grid(CAD.Cadence(3), T('2025-01-01'), T('2026-01-01'))
    t = _taxonomy_tickets(4, split_from=3)
    every, unmapped_cat, moved, facts = CMP.taxonomy_blocked(t, grid, 3, groups, 0.05, [0, 1, 2],
                                                             _fleet_category_cells(t, '2025-10-01', 3), 10)
    assert every == set() and unmapped_cat == set() and moved == {'Door', 'Mechanical'}
    assert facts == {'appeared': ['Electro/Mechanical / Deposit Door - Latch',
                                  'Electro/Mechanical / Deposit Door - Sensor'], 'vanished': ['Door / Deposit Door']}
    grid5 = CAD.period_grid(CAD.Cadence(3), T('2025-01-01'), T('2026-04-01'))
    t = _taxonomy_tickets(5, split_from=3)                           # latest 2026 Q1, split in 2025 Q4
    cells = _fleet_category_cells(t, '2026-01-01', 4)                 # Deposit Door: 22.5 expected, none seen
    _, _, moved, facts = CMP.taxonomy_blocked(t, grid5, 4, groups, 0.05, [0, 1, 2, 3], cells, 10)
    assert moved == {'Door', 'Mechanical'} and len(facts['appeared']) == 2 and facts['vanished']
    t = _taxonomy_tickets(5, split_from=1)                           # the whole baseline is after the split
    assert CMP.taxonomy_blocked(t, grid5, 4, groups, 0.05, [1, 2, 3], _fleet_category_cells(
        t[t.ts >= T('2025-04-01')], '2026-01-01', 3), 10)[:3] == (set(), set(), set())
    t = _taxonomy_tickets(4)                                         # no change; one rare 'Training' ticket
    assert CMP.taxonomy_blocked(t, grid, 3, groups, 0.05, [0, 1, 2], _fleet_category_cells(t, '2025-10-01', 3),
                                10)[:3] == (set(), set(), set())
    # unmapped combinations are still caught from the latest period alone, at every level of the groups
    t = _taxonomy_tickets(4, split_from=3)
    t['unmapped'] = t.category.str.contains(' - ')
    every, _, moved, _ = CMP.taxonomy_blocked(t, grid, 3, groups, 0.05, [0, 1, 2],
                                              _fleet_category_cells(t, '2025-10-01', 3), 10)
    assert {'Door', 'Mechanical', 'Unmapped'} <= every and moved == set()


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


def test_cohort_positions_per_issue():
    """The newest testable cohort of each issue is 'newest'; newer, still-filling cohorts are 'too_new'."""
    dated = ['Before 2016', '2016', '2017', '2018']
    exp = {'a': [50, 20, 30, 3],          # 2018 still filling up: 2017 is the newest testable cohort
           'b': [50, 20, 4, 3],           # 2017 and 2018 too small: 2016 is the newest testable cohort
           'c': [50, 2, 4, 3],            # nothing after the oldest is testable: no 'too_new', 2018 is 'newest'
           'd': [50, 20, 30, 40]}         # the usual case
    c = pd.DataFrame([{'install_cohort': k, 'issue_key': i, 'expected_crude': e}
                      for i, es in exp.items() for k, e in zip(dated + ['Unknown'], es + [12])])
    pos = COH.positions(c, dated, 10).groupby([c.issue_key, c.install_cohort]).first()
    assert [pos['a', k] for k in dated + ['Unknown']] == ['oldest', 'interior', 'newest', 'too_new', 'undated']
    assert [pos['b', k] for k in dated] == ['oldest', 'newest', 'too_new', 'too_new']
    assert [pos['c', k] for k in dated] == ['oldest', 'interior', 'interior', 'newest']
    assert [pos['d', k] for k in dated] == ['oldest', 'interior', 'interior', 'newest']
    # a cohort whose newer installs would expect fewer than 40 tickets is compared like the newest one, also when a
    # newer cohort is testable (the day 2018 reaches 10 expected tickets, 2017's newer side is still tiny)
    c['expected_newer_side'] = c.install_cohort.map({'Before 2016': 900, '2016': 120, '2017': 39, '2018': 0,
                                                     'Unknown': np.nan})
    pos = COH.positions(c, dated, 10).groupby([c.issue_key, c.install_cohort]).first()
    assert [pos['d', k] for k in dated] == ['oldest', 'interior', 'newest', 'newest']
    assert [pos['a', k] for k in dated] == ['oldest', 'interior', 'newest', 'too_new']     # unchanged
    assert pos['d', 'Unknown'] == 'undated'
    assert [pos['c', k] for k in dated] == ['oldest', 'interior', 'interior', 'newest']   # 2017 is not testable


def test_cohort_call_rule():
    """Interior: a peak (1.5x the rest, 1.25x newer and older) and, with enough history, 1.25x the same age; newest:
    1.5x the rest and 1.5x the same age. The p-value is the largest of the comparisons the rule uses."""
    def row(pos, crude, newer, older, same, dropped=0.0, p=(1e-6, 2e-5, 3e-4, 4e-3)):
        return {'position': pos, 'crude_ratio': crude, 'newer_ratio': newer, 'older_ratio': older,
                'same_age_ratio': same, 'same_age_dropped_share': dropped, 'p_crude': p[0], 'p_newer': p[1],
                'p_older': p[2], 'p_same_age': p[3]}
    c = pd.DataFrame([row('interior', 2.8, 1.9, 3.8, 1.6),                 # 0 peak, and above the same age
                      row('interior', 2.6, 2.3, 2.8, 1.0),                 # 1 peak, in line with the same age
                      row('interior', 2.6, 2.3, 2.8, 1.0),                 # 2 the same, history too short
                      row('interior', 2.0, 1.1, 2.4, 1.6),                 # 3 no peak (in line with newer installs)
                      row('newest', 3.3, np.nan, 3.3, 2.9),                # 4 newest
                      row('newest', 3.3, np.nan, 3.3, 1.2),                # 5 newest, in line with the same age
                      row('newest', 3.3, np.nan, 3.3, 2.9, dropped=0.5),   # 6 same age not estimable
                      row('too_new', 9.0, np.nan, 9.0, 9.0),               # 7 never called
                      row('interior', 0.5, 0.7, 0.6, 0.7),                 # 8 lower: the mirror image
                      row('interior', 2.8, 1.9, 3.8, 1.6, p=(1e-6, 2e-5, 3e-4, np.nan)),   # 9 missing p counts as 1
                      row('oldest', 3.0, 3.0, np.nan, 3.0)])               # 10 never called
    check = [True, True, False, True, True, True, False, False, True, True, False]
    up, down, p_call, age_like = COH.call_rule(c, 0.5, check)
    assert list(up) == [True, False, True, False, True, False, False, False, False, True, False]
    assert list(down) == [False] * 8 + [True, False, False]
    assert close(p_call[0], 4e-3) and close(p_call[2], 3e-4) and close(p_call[4], 4e-3) and close(p_call[8], 4e-3)
    assert close(p_call[9], 1.0) and all(close(p_call[i], 1.0) for i in (1, 3, 5, 6, 7, 10))
    assert list(age_like) == [False, True] + [False] * 9


def test_cohort_window_labels_and_history():
    grid = CAD.period_grid(CAD.Cadence(3), T('2024-01-01'), T('2026-10-01'))
    full = [7, 8, 9, 10]
    assert COH.window_label(grid, full) == '2025 Q4 to 2026 Q3'
    assert COH.window_label(grid, [8, 9, 10], full) == '2026 Q1 to 2026 Q3'
    assert COH.window_label(grid, [7, 9, 10], full) == '2025 Q4 to 2026 Q3 except 2026 Q1 (incomplete Category labels)'
    assert COH.window_label(grid, [10], full) == '2026 Q3' and COH.window_label(grid, []) == ''
    assert COH.history_months(grid, list(range(11))) == 33 and COH.history_months(grid, list(range(1, 8))) == 21
    assert COH.history_months(grid, []) == 0


def test_cohort_sentences():
    """Not-tested rows state the rate and the reason, with no ratios; ratios are written only when finite; each row
    uses its own window label."""
    base = {'issue': 'Touchscreen', 'install_cohort': '2026', 'rate_per_100': 0.6612,
            'window_label': '2026 Q1 to 2026 Q3', 'status': 'not_tested',
            'not_tested_reason': 'too new: still filling up (8.7 expected tickets)',
            'position': 'too_new', 'crude_ratio': np.inf, 'newer_ratio': np.nan, 'older_ratio': 0.9,
            'same_age_ratio': np.nan, 'same_age_check': False, 'persisting': False}
    r = pd.Series(base)
    assert COH.sentence(r, 'ignored') == ('Touchscreen, 2026 installs: 0.66 per 100 installed machine-months over '
                                          '2026 Q1 to 2026 Q3; not tested (too new: still filling up (8.7 expected '
                                          'tickets)).')
    r = pd.Series({**base, 'install_cohort': 'Before 2016', 'status': 'no_clear_difference', 'position': 'oldest'})
    s = COH.sentence(r)
    assert s.startswith('Touchscreen, installs before 2016: 0.66 per 100') and 'inf' not in s and 'nan' not in s
    r = pd.Series({**base, 'install_cohort': '2022', 'status': 'stands_out_higher', 'position': 'interior',
                   'crude_ratio': 2.75, 'newer_ratio': 1.85, 'older_ratio': 3.78, 'same_age_ratio': 1.65,
                   'same_age_check': True, 'persisting': True})
    assert COH.sentence(r).endswith('2.8x the rest of the fleet (1.9x newer installs, 3.8x older installs, 1.6x other '
                                    'cohorts at the same age over the whole history); it stood out in the previous '
                                    'window too.')
    r = pd.Series({**base, 'status': 'stands_out_higher', 'position': 'newest', 'crude_ratio': 3.27,
                   'same_age_ratio': 2.92, 'window_label': None})
    assert COH.sentence(r, '2025 Q4 to 2026 Q3') == (
        'Touchscreen, 2026 installs: 0.66 per 100 installed machine-months over 2025 Q4 to 2026 Q3, 3.3x the rest of '
        'the fleet and 2.9x other cohorts at the same age over the whole history.')


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


# ------------------------------------------------------------------------------------------------ report wording
def _report_change(dim, stratum, key, issue, status, ratio, lo, hi, q, used, sustained=False, previous=''):
    return {'stratum_dim': dim, 'stratum': stratum, 'issue_key': key, 'issue': issue,
            'issue_level': 'all' if key == 'all' else ('group' if key.startswith('group|') else 'category'),
            'status': status, 'eligible': status != 'not_tested', 'change_ratio': ratio, 'ci_lo': lo, 'ci_hi': hi,
            'q_value': q, 'rate_latest': 2.0 * ratio, 'rate_baseline': 2.0, 'baseline_periods_used': used,
            'sustained': sustained, 'previous_status': previous, 'survivor_note': '', 'not_tested_reason': ''}


def _report_run(changes, contrasts=None, history=None, latest=4, label_ok=None, dq=None, **params):
    """A report _Run on hand-made tables: the 11 quarters 2025 Q1 (position 0) to 2027 Q3 (in progress), with the
    four quarters before `latest` as its baseline."""
    import types
    from ipa_trends import report as REP
    P = CFG.resolve({'HISTORY_MONTHS': history, **params})
    grid = CAD.period_grid(CAD.Cadence(3), T('2025-01-01'), T('2027-10-01'))
    grid['status'] = ['final'] * (len(grid) - 1) + ['in_progress']
    grid['status_reason'] = [''] * (len(grid) - 1) + ['the data end inside it']
    grid['role'] = ['baseline' if latest - 4 <= i < latest else ('latest' if i == latest else '')
                    for i in range(len(grid))]
    grid['label_ok'] = label_ok if label_ok is not None else [True] * len(grid)
    base = [grid.label[i] for i in range(latest - 4, latest)]
    summary = {'latest_label': grid.label[latest], 'baseline_labels': base, 'tested': int(sum(
        r['status'] != 'not_tested' for r in changes)), 'cohort_window': f'{base[1]} to {grid.label[latest]}'}
    facts = {'cohorts': {'window': base[1:] + [grid.label[latest]]}, 'blank_category_limit': 0.083}
    result = types.SimpleNamespace(summary=summary, facts=facts, warnings=[])
    tables = {'periods': grid, 'changes': pd.DataFrame(changes), 'cohort_contrasts': contrasts}
    if dq is not None:
        tables['data_quality'] = dq
    return REP._Run(result, tables, P, 'run'), REP


def test_report_baseline_phrase():
    """Each change row is worded from its own baseline: issue-level rows leave out baseline periods whose Category
    labels are incomplete, and say so instead of naming the run's full baseline."""
    from ipa_trends.report import _baseline_phrase as bp
    q, m = CAD.Cadence(3), CAD.Cadence(1)
    assert bp(q, 4, 4) == 'the previous four quarters' and bp(q, 1, 1) == 'the previous quarter'
    assert bp(q, 3, 4) == 'three of the previous four quarters (those with complete Category labels)'
    assert bp(q, 0, 4) == 'no baseline' and bp(m, 12, 12) == 'the previous 12 months'
    assert bp(m, 11, 12) == '11 of the previous 12 months (those with complete Category labels)'
    rows = [_report_change('fleet', 'Fleet', 'all', 'All unplanned tickets', 'higher', 1.3, 1.1, 1.5, 0.01, 4,
                           True, 'watch_higher'),
            _report_change('fleet', 'Fleet', 'group|Door', 'Door', 'higher', 1.5, 1.2, 1.9, 0.001, 3, True, 'higher'),
            _report_change('model', 'MV-2.0', 'group|Door', 'Door', 'watch_higher', 1.4, 1.05, 1.9, 0.1, 3, True,
                           'watch_higher')]
    R, REP = _report_run(rows, label_ok=[False] + [True] * 10)
    assert R.dropped == ['2025 Q1'] and 'leave out 2025 Q1 (Category labels incomplete)' in R.defs(issues=True)[2]
    assert '2025 Q1 is left out of issue-level baselines (Category labels incomplete).' in R.data_notes()
    door = R.flags[R.flags.issue_key == 'group|Door'].iloc[0]
    item = R.change_item(door)
    assert 'three of the previous four quarters (those with complete Category labels)' in item, item
    assert item.endswith('; also flagged last quarter.'), item
    line = R.fleet_line()
    assert '30% above the previous four quarters' in line and line.endswith('also on the watch list last quarter.')
    rows_html, own = REP._change_rows(R, R.flags)                  # Door first (smaller q-value), then the fleet
    assert own and rows_html[1][5] == 'the previous four quarters' and rows_html[1][-1] == \
        'yes, also on the watch list last quarter'
    assert rows_html[0][5].startswith('three of the previous four')
    assert rows_html[0][-1] == 'yes, also flagged last quarter'
    watch, _ = REP._change_rows(R, R.watch, watch=True)
    assert watch[0][-1] == 'could still be chance; also on the watch list last quarter'
    assert R.baseline_summary(R.changes) == ('the previous four quarters for all unplanned tickets; three of the '
                                             'previous four quarters (those with complete Category labels) for issues')
    assert ('1 more change is on the watch list: reported, not flagged, because it could still be chance.'
            in R.key_messages())
    full, _ = _report_run([dict(r, baseline_periods_used=4) for r in rows])     # labels complete: no extra column
    plain, own = REP._change_rows(full, full.flags)
    assert not own and len(plain[0]) == len(rows_html[0]) - 1 and full.dropped == []
    assert full.flags.iloc[0].issue == 'Door'
    assert 'above the previous four quarters' in full.change_item(full.flags.iloc[0])
    assert full.baseline_summary(None) == full.previous


def test_report_not_flagged_wording():
    """'No change was beyond normal variation' only when every tested interval includes no change; otherwise the
    report says nothing was flagged and how many changes with intervals excluding no change could still be chance."""
    calm = [_report_change('fleet', 'Fleet', 'all', 'All unplanned tickets', 'no_clear_change', 1.05, 0.9, 1.2, 0.8, 4),
            _report_change('fleet', 'Fleet', 'group|Door', 'Door', 'no_clear_change', 0.95, 0.8, 1.1, 0.8, 4)]
    R, _ = _report_run(calm)
    assert R.none_flagged() == ('No change in 2026 Q1 was beyond normal quarter-to-quarter variation (2 issue and '
                                'breakdown cells tested).')
    many = calm + [_report_change('fleet', 'Fleet', 'group|Electronics', 'Electronics', 'no_clear_change', 0.7, 0.55,
                                  0.9, 0.24, 4),
                   _report_change('family', 'alEx', 'group|Door', 'Door', 'no_clear_change', 0.88, 0.8, 0.97, 0.3, 4)]
    R, _ = _report_run(many)
    assert R.beyond() == (1, 1, 0)
    text = R.none_flagged()
    assert text.startswith('No change in 2026 Q1 was flagged (a flag needs a q-value below 0.05 after correcting for 4 '
                           'tested cells, and a change of at least 20%); 1 change with an interval excluding no change '
                           'could still be chance;'), text
    assert 'beyond normal variation' not in text and 'was under the 20% practical threshold' in text


def test_report_not_flagged_charts():
    """With no flag but changes whose intervals exclude no change, the chart titles say nothing was flagged and name
    what could still be chance; the changes chart's legend says 'Not flagged' and its subtitle counts the cells it
    leaves out."""
    from ipa_trends import style as STYLE
    S = STYLE.load()
    if S is None:
        return
    rows = [_report_change('fleet', 'Fleet', 'all', 'All unplanned tickets', 'no_clear_change', 1.05, 0.9, 1.2, 0.8, 4),
            _report_change('fleet', 'Fleet', 'group|Electronics', 'Electronics', 'no_clear_change', 0.7, 0.55, 0.9,
                           0.24, 4),
            _report_change('model', 'MV-2.0', 'group|Door', 'Door', 'no_clear_change', 1.5, 1.1, 2.0, 0.3, 4)]
    R, REP = _report_run(rows)
    import contextlib
    import io
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):    # save() prints the path
        groups = REP.chart_group_trends(S, R, Path(d) / 'groups.png')
        changes = REP.chart_changes(S, R, Path(d) / 'changes.png')
    assert groups == 'No request group was flagged in 2026 Q1; Electronics (-30%) could still be chance', groups
    assert changes == 'No change in 2026 Q1 was flagged; 2 changes could still be chance', changes
    texts = [t for drawn in S.TEXTS.values() for t in drawn]
    assert 'Not flagged' in texts and not any('No clear change' in t for t in texts)
    assert any('1 of the 2 changes that could still be chance is in a cell not drawn here' in t for t in texts)


def test_report_forest_rows():
    """The changes chart lists fleet-level flags first and keeps a row of each flagged direction its title counts."""
    head = [_report_change('fleet', 'Fleet', 'all', 'All unplanned tickets', 'no_clear_change', 1.0, 0.9, 1.1, 0.9, 4)]
    up = [_report_change('install_cohort', str(2010 + i), 'group|Door', 'Door', 'higher', 1.6, 1.3, 2.0,
                         0.001 * (i + 1), 4) for i in range(16)]
    fleet_down = _report_change('fleet', 'Fleet', 'cat|Electronics|Computer Board', 'Computer Board', 'lower', 0.5,
                                0.35, 0.75, 0.04, 4)
    R, REP = _report_run(head + up + [fleet_down])
    h, extra, hidden = REP._forest_rows(R)
    assert len(h) == 1 and len(extra) == REP.MAX_FOREST_ROWS - 1 and hidden == 17 - len(extra)
    assert extra.iloc[0].issue == 'Computer Board'                 # fleet-level first, though its q-value is larger
    assert extra.attrs['forced'] == []                             # ... so it is among the strongest rows anyway
    far_down = dict(fleet_down, stratum_dim='model', stratum='MV-2.0', q_value=0.049)
    R, REP = _report_run(head + up + [far_down])
    _, extra, hidden = REP._forest_rows(R)
    assert len(extra) == REP.MAX_FOREST_ROWS - 1 and 'lower' in set(extra.status) and hidden == 3
    assert list(extra.q_value) == sorted(extra.q_value)            # still strongest first
    assert extra.attrs['forced'] == ['lower']                      # kept for the title, not for its strength


def test_report_history_note_for_back_runs():
    """A back-run's time charts end at its own period: the note says the later periods are left out, not earlier."""
    from types import SimpleNamespace
    from ipa_trends import report as REP
    def note(before, after):
        R = SimpleNamespace(hidden_periods=before + after, hidden_before=before, hidden_after=after,
                            labels=['2024 Q1', '2025 Q1'], plural='quarters', noun='quarter')
        return REP._Run.history_note(R)
    assert note(0, 0) == ''
    assert note(2, 0) == 'Quarters before 2024 Q1 are not shown (HISTORY_MONTHS); rates.csv holds every quarter.'
    assert note(0, 6) == ('Quarters after 2025 Q1 are not shown (a back-run reports as of 2025 Q1); rates.csv holds '
                          'every quarter.')
    assert 'before 2024 Q1 (HISTORY_MONTHS) and after 2025 Q1' in note(2, 6)


def test_report_history_and_cohort_rule():
    """HISTORY_MONTHS limits the time charts' axis but always keeps the baseline and latest periods; the cohort rule
    text follows the parameters and never claims that a peak rules out every age effect."""
    rows = [_report_change('fleet', 'Fleet', 'all', 'All unplanned tickets', 'no_clear_change', 1.0, 0.9, 1.1, 0.9, 4)]
    R, _ = _report_run(rows, history=None, latest=9)               # default 24 months: 2025 Q4 to 2027 Q3
    assert R.labels[0] == '2025 Q4' and len(R.labels) == 8 and R.hidden_periods == 3
    assert R.labels[R.latest_pos] == '2027 Q2' and [R.labels[i] for i in R.baseline_pos][0] == '2026 Q2'
    assert R.history_note() == 'Quarters before 2025 Q4 are not shown (HISTORY_MONTHS); rates.csv holds every quarter.'
    R, _ = _report_run(rows, history=12, latest=6)                 # 12 months, but the baseline starts in 2025 Q3
    assert R.labels[0] == '2025 Q3' and R.hidden_periods == 2 and R.baseline_pos == [0, 1, 2, 3]
    assert R.labels[R.latest_pos] == '2026 Q3' and R.status[-1] == 'in_progress'
    assert len(R.series('fleet', 'all')) == len(R.labels) == 9 and len(R.series('fleet', 'all', every=True)) == 11
    assert 'ok' not in R.series('fleet', 'all').columns and list(R.series('fleet', 'all').label) == R.labels
    R, _ = _report_run(rows, history=60)
    assert R.hidden_periods == 0 and R.history_note() == ''
    for form in ('full', 'definition', 'lede', 'short'):
        text = R.cohort_rule(form)
        assert '1.5x the rest of the fleet' in text and '1.25x both newer and older installs' in text, form
        assert 'cannot produce' not in text and 'same age' in text and '0.05' in text, form
        assert 'Benjamini-Hochberg-corrected largest' in text, form
    full = R.cohort_rule('full')
    assert 'rises or falls steadily with machine age' in full and 'wear-out window' in full and '24 months' in full
    assert 'still filling up' in full and 'largest p-value' in full and '12 months of final quarters' in full
    R6, _ = _report_run(rows, MIN_CONTRAST=0.6, Q_CUT=0.01, WATCH_Q=0.1)
    assert '1.6x the rest of the fleet and at least 1.3x both' in R6.cohort_rule('full')
    assert 'below 0.01' in R6.cohort_rule('lede')
    assert 'for the fleet and by install cohort only, the Categories' in R.method_items()[0]
    assert 'nine analysed groups' in R.group_definition() and 'Not categorised' in R.group_definition()


def test_report_same_age_note():
    """The cohort section says whether this run's final history is long enough for the same-age check, for all
    unplanned tickets and for issues (whose periods need complete Category labels)."""
    rows = [_report_change('fleet', 'Fleet', 'all', 'All unplanned tickets', 'no_clear_change', 1.0, 0.9, 1.1, 0.9, 4)]
    cc = pd.DataFrame({'issue_key': ['all', 'group|Door'], 'issue_level': ['all', 'group'],
                       'issue': ['All unplanned tickets', 'Door'], 'install_cohort': ['2022', '2022'],
                       'status': ['no_clear_difference'] * 2, 'eligible': [True, True], 'crude_ratio': [1.1, 1.2],
                       'window_periods': [4, 4]})
    R, REP = _report_run(rows, cc)                                 # 15 months: 2025 Q1 to 2026 Q1
    assert R.history_months() == {'all': 15, 'labels': 15}
    assert R.same_age_note() == R.same_age_note(gaps_only=True) == (
        'This run has only 15 months of final history, so the same-age check does not apply yet: a peak could still '
        'reflect machine age (a wear-out window).')
    R, _ = _report_run(rows, cc, latest=9)                         # 30 months: 2025 Q1 to 2027 Q2
    assert R.same_age_note() == 'This run has 30 months of final history, so the same-age check applies.'
    assert R.same_age_note(gaps_only=True) == '' and REP.SAME_AGE_HISTORY_MONTHS == 24
    R, _ = _report_run(rows, cc, latest=9, label_ok=[False] * 3 + [True] * 8)
    assert R.history_months() == {'all': 30, 'labels': 21}
    assert R.same_age_note().startswith('This run has 30 months of final history, but only 21 with complete Category '
                                        'labels, so for issues the same-age check does not apply yet')
    R.facts['cohorts']['history_months'] = {'all': 33, 'labels': 30}    # the cohorts' own figures come first
    assert R.same_age_note() == 'This run has 33 months of final history, so the same-age check applies.'
    R, _ = _report_run(rows, cc.iloc[:1], latest=9, label_ok=[False] * 3 + [True] * 8)   # no issue rows
    assert R.same_age_note(gaps_only=True) == ''
    # a cohort item names the row's own window: the engine's sentence when it does, else the same facts
    row = {'issue': 'Touchscreen', 'install_cohort': '2023', 'rate_per_100': 1.64, 'crude_ratio': 2.8,
           'newer_ratio': 2.75, 'older_ratio': 2.8, 'same_age_ratio': 2.0, 'position': 'interior',
           'window_label': '2026 Q1 to 2026 Q3', 'sentence': 'Touchscreen, 2023 installs: over 2025 Q4 to 2026 Q3.'}
    item = next(pd.DataFrame([row]).itertuples())
    assert R.cohort_item(item) == ('Touchscreen, 2023 installs: 1.64 per 100 installed machine-months over 2026 Q1 '
                                   'to 2026 Q3, 2.8x the rest of the fleet (2.8x newer installs, 2.8x older installs).')
    item = next(pd.DataFrame([dict(row, sentence='Touchscreen over 2026 Q1 to 2026 Q3.')]).itertuples())
    assert R.cohort_item(item) == 'Touchscreen over 2026 Q1 to 2026 Q3.'


def test_report_data_quality_gate():
    """The data-quality chart draws and counts the run's own Category gate (label_ok), not MAX_BLANK_CATEGORY_SHARE."""
    from ipa_trends import style as STYLE
    S = STYLE.load()
    if S is None:
        return
    rows = [_report_change('fleet', 'Fleet', 'all', 'All unplanned tickets', 'no_clear_change', 1.0, 0.9, 1.1, 0.9, 4)]
    blank = [0.06, 0.07, 0.04, 0.03, 0.065, 0.12, 0.04, 0.03, 0.04, 0.03, 0.30]     # above 5% but under 8.3% in five
    ok = [b <= 0.083 for b in blank]
    R, REP = _report_run(rows, label_ok=ok, history=60)
    R.dq = pd.DataFrame({'period_key': list(R.periods.period_key), 'open_share': 0.0, 'blank_category_share': blank,
                         'unlisted_share': 0.01, 'label_ok': ok})
    import contextlib
    import io
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):    # save() prints the path
        title = REP.chart_data_quality(S, R, Path(d) / 'dq.png')
    assert title == '1 quarter had too many blank Categories for issue-level tests', title     # the in-progress one
    texts = [t for drawn in S.TEXTS.values() for t in drawn]                                 # is not counted
    assert any('5% or twice the typical share (8.3% in this run)' in t for t in texts), texts


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


def test_closed_only_check():
    """W26 looks at every ticket opened in the 14 days before the export, whatever DATA_END says: none open among 30
    or more is blocking; one open, fewer than 30, or only older tickets (an earlier DATA_END) is not."""
    from ipa_trends.engine import closed_only_check
    ex = T('2026-11-15')

    def codes(opened, open_flags):
        w = INP.Warnings()
        closed_only_check(pd.DataFrame({'ts': pd.to_datetime(opened), 'is_open': open_flags}), ex, w)
        return [(x['code'], x.get('blocking')) for x in w.items]
    recent = list(pd.date_range('2026-11-02 09:00', periods=40, freq='7h'))     # 2 to 13 Nov
    assert codes(recent, [False] * 40) == [('W26', True)]
    assert codes(recent, [False] * 39 + [True]) == []
    assert codes(recent[:29], [False] * 29) == []
    older = list(pd.date_range('2026-09-01', periods=200, freq='5h'))           # before DATA_END = 30 Sep
    assert codes(older + recent[:10], [False] * 210) == []
    assert codes(recent + [ex + pd.Timedelta(hours=8)], [False] * 41)[0] == ('W26', True)     # the export day counts


# ------------------------------------------------------------------------------------------------ failures, publishing
def test_exit_codes_follow_the_codes():
    """Every code is raised with the class whose exit code the README documents: 1 for C and P codes, 2 for E01-E31
    (inputs, parameters, the output folder), 3 for E99. E30 and E31 are OutputErrors."""
    from ipa_trends import errors as ERR
    codes = ('E01', 'E10', 'E22', 'E25', 'E30', 'E31', 'C01', 'P01', 'E99', 'E1', 'X01', None)
    assert [ERR.exit_code_for(c) for c in codes] == [2, 2, 2, 2, 2, 2, 1, 1, 3, 3, 3, 3]
    classes = {c.__name__: c for c in (ERR.TrendsError, ERR.ConfigError, ERR.InputError, ERR.OutputError,
                                        ERR.CheckError, ERR.PrivacyError)}
    seen = set()
    for p in (TRENDS / 'ipa_trends').rglob('*.py'):
        for cls, code in re.findall(r"(\w+Error)\(\[?\(?'([ECP]\d{2})'", p.read_text(encoding='utf-8')):
            if cls in classes:
                seen.add(code)
                assert classes[cls].exit_code == ERR.exit_code_for(code), (p.name, cls, code)
    assert {'E01', 'E10', 'E20', 'E22', 'E30', 'E31', 'C01', 'P01', 'E99'} <= seen, sorted(seen)
    assert ERR.NotebookError('E10', 'E10: x').exit_code == 2 and ERR.NotebookError('E99', 'E99: x').exit_code == 3
    assert [ERR.stage_for(c) for c in ('E05', 'E22', 'E30', 'C01', 'P01', 'E99')] == [
        'inputs', 'parameters', 'publish', 'checks', 'privacy scan', 'run']


def test_failure_record():
    """failed/<stamp>/error.txt holds the code, stage and exit code, never the message (it can name local paths);
    nothing is written for E31, or inside a git work tree that does not ignore OUTPUT_DIR."""
    import shutil
    from ipa_trends import __version__
    from ipa_trends import publish as PUB
    from ipa_trends.errors import OutputError
    d = Path(tempfile.mkdtemp())
    e = InputError('E01', 'no case export matches /home/someone/IPA_CaseHistory_*.xlsx', 'save it')
    path, note = PUB.record_failure(d / 'out', e)
    assert path.read_text() == f'code: E01\nstage: inputs\nexit_code: 2\npackage_version: {__version__}\n'
    assert path.parent.parent == d / 'out' / 'failed' and str(path) in note
    again, _ = PUB.record_failure(d / 'out', e)
    assert again != path and again.exists() and path.exists()          # a second failure keeps the first record
    nb = d / 'executed.ipynb'
    nb.write_text('{}')
    path, note = PUB.record_failure(d / 'out', e, files={'executed_notebook.ipynb': nb})
    assert (path.parent / 'executed_notebook.ipynb').exists() and 'with executed_notebook.ipynb' in note
    assert PUB.record_failure(d / 'e31', OutputError('E31', 'x'))[0] is None and not (d / 'e31').exists()
    if shutil.which('git'):
        repo = d / 'repo'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True, capture_output=True)
        path, note = PUB.record_failure(repo / 'out', e)
        assert path is None and 'git repository' in note and not (repo / 'out').exists()
        (d / 'stage').mkdir()
        (d / 'stage' / 'manifest.json').write_text('{}')
        try:
            PUB.place_run(d / 'stage', repo / 'out', 'r1')
        except OutputError as e31:
            assert e31.code == 'E31' and e31.exit_code == 2 and not (repo / 'out').exists()
        else:
            raise AssertionError('no E31')
        (repo / '.gitignore').write_text('out/\n')
        assert PUB.record_failure(repo / 'out', e)[0] is not None


def test_failures_are_recorded_with_exit_codes():
    """An input error stops a publishing run with exit 2 and a failure record, from the engine and the command line;
    a parameter problem is recorded when OUTPUT_DIR can still be read; a run that does not publish writes nothing."""
    import contextlib
    import io
    from ipa_trends import cli, engine
    d = Path(tempfile.mkdtemp())
    p = {'CASE_EXPORTS': str(d / 'missing' / '*.xlsx'), 'OUTPUT_DIR': str(d / 'out')}
    for publish in (False, True):
        try:
            engine.run(p, publish=publish, verbose=False)
        except InputError as e:
            assert e.code == 'E01' and e.stage == 'inputs' and e.exit_code == 2
            record = e.failure_record
        else:
            raise AssertionError('no E01')
        assert (record is not None) == publish and (d / 'out').exists() == publish
    assert record[0].read_text().startswith('code: E01\nstage: inputs\nexit_code: 2\n')
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = cli.main(['run', '--set', f'CASE_EXPORTS={d}/missing/*.xlsx', '--set', f'OUTPUT_DIR={d}/cli'])
    assert rc == 2 and len(list((d / 'cli' / 'failed').glob('*/error.txt'))) == 1 and 'Failure record' in err.getvalue()
    with contextlib.redirect_stderr(io.StringIO()):
        rc = cli.main(['run', '--set', 'RERUN_FREQUENCY=weekly', '--set', f'OUTPUT_DIR={d}/cfg'])
    rec = next((d / 'cfg' / 'failed').glob('*/error.txt')).read_text()
    assert rc == 2 and rec.startswith('code: E20\nstage: parameters\nexit_code: 2\n')
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = cli.main(['run', '--params', str(d / 'missing.yaml')])
    assert rc == 2 and 'no failure record was written: OUTPUT_DIR could not be read' in err.getvalue()


def test_private_log():
    """An unexpected error's traceback goes to a new 0600 file in this user's 0700 folder; when that cannot be
    written, E99 says so and still never shows the exception's message (exit 3 on the command line)."""
    import contextlib
    import io
    import os
    import shutil
    import stat
    from ipa_trends import cli, engine
    leak = "could not convert string to float: 'Fake Memorial Hospital 017'"
    d = Path(tempfile.mkdtemp())
    saved, umask = tempfile.tempdir, os.umask(0o022)
    tempfile.tempdir = str(d)

    def boom(args):
        raise ValueError(leak)
    real = cli.cmd_next_runs
    try:
        try:
            boom(None)
        except ValueError as e:
            err = engine.unexpected(e, 'analysis')
        assert err.code == 'E99' and err.exit_code == 3 and leak not in err.text() and 'private log' in err.text()
        assert 'during analysis, in test_units.' not in err.text()            # only frames of the package are named
        log = next(d.glob('ipa_trends_logs_*/*.log'))
        assert leak in log.read_text()
        if os.name == 'posix':
            assert stat.S_IMODE(log.stat().st_mode) == 0o600 and stat.S_IMODE(log.parent.stat().st_mode) == 0o700
            assert log.parent.name == f'ipa_trends_logs_{os.getuid()}'
        shutil.rmtree(log.parent)
        log.parent.write_text('a file where the log folder should be')
        cli.cmd_next_runs = boom
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            rc = cli.main(['next-runs'])
        assert rc == 3 and 'could not be saved' in out.getvalue() and 'Fake Memorial' not in out.getvalue()
    finally:
        cli.cmd_next_runs = real
        tempfile.tempdir = saved
        os.umask(umask)


def test_latest_swap_survives_a_lock():
    """latest/ is replaced as a whole. A lock while swapping (os.replace refused, as on Windows while Excel holds a
    file), or a full disk, leaves it exactly as it was, with no latest.new/, latest.old/ or .partial file left (E30,
    exit 2); if latest/ cannot even be put back, E30 says where the previous run is. A clean run then replaces
    latest/ whole, its manifest.json last."""
    import os
    from ipa_trends import publish as PUB
    from ipa_trends.errors import OutputError
    d = Path(tempfile.mkdtemp())

    def staged(name, files):
        for rel, text in files.items():
            (d / name / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / name / rel).write_text(text)
        return d / name
    one = staged('one', {'rates.csv': '1', 'unmapped.csv': '1', 'charts/a.png': '1', 'manifest.json': '1'})
    two = staged('two', {'rates.csv': '2', 'charts/b.png': '2', 'manifest.json': '2'})
    out, latest = d / 'out', d / 'out' / 'latest'

    def state(folder=latest):
        return {p.relative_to(folder).as_posix(): p.read_text() for p in folder.rglob('*') if p.is_file()}
    assert PUB.place_run(one, out, 'run1') == out / 'runs' / 'run1'
    first = state()
    assert first == {'rates.csv': '1', 'unmapped.csv': '1', 'charts/a.png': '1', 'manifest.json': '1'}
    real, waits = os.replace, PUB.RETRY_WAITS
    PUB.RETRY_WAITS = ()
    lock, full, eio = PermissionError(13, 'in use'), OSError(28, 'No space left on device'), OSError(5, 'I/O error')
    locks = [('moving latest/ aside', lambda src, dst: Path(src) == latest, 'latest/ was not updated', lock),
             ('moving latest.new/ in', lambda src, dst: Path(src).name == 'latest.new', 'latest/ was not updated',
              lock),
             ('a file in runs/', lambda src, dst: Path(dst) == out / 'runs' / 'run3' / 'rates.csv',
              'latest/ was not updated', lock),
             # any other failure to write OUTPUT_DIR is E30 as well, with the system's reason
             ('a full disk in runs/', lambda src, dst: Path(dst) == out / 'runs' / 'run3' / 'rates.csv',
              'No space left on device. latest/ was not updated', full),
             ('a full disk in latest.new/', lambda src, dst: Path(dst).parent.name == 'latest.new',
              'No space left on device. latest/ was not updated', full),
             ('an I/O error moving latest.new/ in', lambda src, dst: Path(src).name == 'latest.new',
              'I/O error. latest/ was not updated', eio),
             ('putting latest/ back as well', lambda src, dst: Path(src).name in ('latest.new', 'latest.old'),
              'latest/ is missing: the previous run is in latest.old/', lock),
             ('the manifest, copied into latest/ last', lambda src, dst: Path(dst) == latest / 'manifest.json',
              'latest/ holds this run without its manifest', lock)]
    try:
        for what, locked, says, exc in locks:
            def replace(src, dst, *a, **k):
                if locked(src, dst):
                    raise exc
                return real(src, dst, *a, **k)
            os.replace = replace
            try:
                PUB.place_run(two, out, 'run3' if 'runs' in what else 'run2')
            except OutputError as e:
                assert e.code == 'E30' and e.exit_code == 2 and says in e.message, (what, e.message)
            else:
                raise AssertionError(f'no E30 when {what}')
            finally:
                os.replace = real
            assert not list(out.rglob('*.partial')), what
            if 'back' in what:
                assert state(out / 'latest.old') == first and not latest.exists()
            elif 'manifest' in what:                                    # no manifest: --only-if-new runs again
                assert state() == {'rates.csv': '2', 'charts/b.png': '2'} and not (out / 'latest.old').exists()
            else:
                assert state() == first and sorted(p.name for p in out.iterdir()) == ['latest', 'runs'], what
        assert state(out / 'runs' / 'run2') == state(two)                # the run folder itself was published
    finally:
        os.replace, PUB.RETRY_WAITS = real, waits
    calls = []

    def spy(src, dst, *a, **k):
        calls.append((Path(src).name, Path(dst).relative_to(out).as_posix()))
        return real(src, dst, *a, **k)
    os.replace = spy
    try:
        PUB.place_run(two, out, 'run2')
    finally:
        os.replace = real
    assert state() == {'rates.csv': '2', 'charts/b.png': '2', 'manifest.json': '2'}
    assert sorted(p.name for p in out.iterdir()) == ['latest', 'runs']
    # latest/ is swapped as a folder, and its manifest.json arrives last, as a new file (a flow watches it)
    assert calls.index(('latest', 'latest.old')) < calls.index(('latest.new', 'latest')) < len(calls) - 1
    assert calls[-1] == ('manifest.json.partial', 'latest/manifest.json')
    assert not [c for c in calls if c[1] == 'latest.new/manifest.json']


def test_notebook_error_codes():
    """--engine notebook takes the whole code from the notebook's error text (E10, not 'E1') and exits as that
    code's class does; anything but a coded error is E99, without its message, which goes to the private log."""
    from ipa_trends import cli

    class Failed(Exception):
        def __init__(self, ename, evalue):
            self.ename, self.evalue = ename, evalue
    cases = [('InputError', 'E10: case export: 60 of 5135 rows have no Case Number or Serial #', 'E10', 2),
             ('InputError', 'E01: no case export matches data/raw/IPA_CaseHistory_*.xlsx', 'E01', 2),
             ('ConfigError', '2 parameter problem(s):\nE20: RERUN_FREQUENCY = weekly\nE22: X is not a parameter',
              'E20', 2), ('OutputError', 'E30: could not replace latest/', 'E30', 2),
             ('CheckError', 'C01: runtime check(s) failed', 'C01', 1), ('PrivacyError', 'P01: the scan', 'P01', 1),
             ('TrendsError', 'E99: unexpected KeyError during analysis', 'E99', 3), ('KeyError', "'E10'", 'E99', 3)]
    d = Path(tempfile.mkdtemp())
    saved, tempfile.tempdir = tempfile.tempdir, str(d)
    try:
        for ename, evalue, code, rc in cases:
            e = cli._notebook_error(Failed(ename, evalue), {})
            assert (e.code, e.exit_code) == (code, rc), (ename, evalue, e.code)
            assert (e.text() == evalue) == (ename != 'KeyError')
        e = cli._notebook_error(Failed('ValueError', "could not convert string to float: 'Fake Memorial'"), {})
        assert e.code == 'E99' and 'unexpected ValueError; the executed notebook shows where' in e.text()
        assert 'Fake Memorial' not in e.text() and 'private log' in e.text() and 'Fix:' in e.text()
        e = cli._notebook_error(RuntimeError('Kernel died'), {}, executed=False)
        assert e.code == 'E99' and 'could not be run (unexpected RuntimeError)' in e.text()
        assert 'Kernel died' not in e.text() and 'executed notebook' not in e.text()
        logs = ''.join(p.read_text() for p in d.glob('ipa_trends_logs_*/*.log'))
        assert 'Fake Memorial' in logs and 'Kernel died' in logs
    finally:
        tempfile.tempdir = saved
    assert cli._notebook_error(None, {}).code == 'E99'
    assert cli._notebook_error(Failed('InputError', 'E05: x'), {'code': 'E05', 'stage': 'inputs'}).stage == 'inputs'


def test_notebook_engine_injects_base_dir():
    """--engine notebook always injects BASE_DIR, so the notebook reads and writes the folders the parameters name;
    a failure under the nbclient fallback (papermill missing) keeps its code and exit code and is recorded."""
    import contextlib
    import io
    import json
    import os
    import nbformat
    from ipa_trends import cli, nbexec
    d = Path(tempfile.mkdtemp())
    (d / 'tmp').mkdir()
    (d / 'p.json').write_text(json.dumps({'BASE_DIR': str(d / 'base'), 'OUTPUT_DIR': 'output'}))
    seen = {}

    class Failed(Exception):
        ename, evalue = 'InputError', 'E01: no case export matches data/raw/IPA_CaseHistory_*.xlsx'

    def fake(notebook, out_path, params, cwd=None, kernel_name='python3'):
        seen.update(params, env=os.environ.get('IPA_TRENDS_RESULT'))
        nbformat.write(nbformat.v4.new_notebook(), str(out_path))
        raise Failed()
    real_exec, real_pm, saved_tmp = nbexec.execute, sys.modules.get('papermill'), tempfile.tempdir
    nbexec.execute, sys.modules['papermill'], tempfile.tempdir = fake, None, str(d / 'tmp')
    try:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = cli.main(['run', '--engine', 'notebook', '--params', str(d / 'p.json')])
    finally:
        nbexec.execute, tempfile.tempdir = real_exec, saved_tmp
        if real_pm is None:
            sys.modules.pop('papermill', None)
        else:
            sys.modules['papermill'] = real_pm
    assert seen['BASE_DIR'] == str((d / 'base').resolve()) and seen['OUTPUT_DIR'] == 'output'
    assert seen['env'].endswith('result.json') and 'IPA_TRENDS_RESULT' not in os.environ
    assert rc == 2 and 'E01: no case export' in err.getvalue() and 'E99' not in err.getvalue()
    assert len(list((d / 'base' / 'output' / 'failed').glob('*/error.txt'))) == 1
    # its inputs are missing, so the executed notebook cannot be scanned: it stays in its temporary folder, named
    kept = list((d / 'tmp').glob('ipa_trends_nb_*/executed.ipynb'))
    assert len(kept) == 1 and str(kept[0]) in err.getvalue()


def test_notebook_engine_publishes_after_the_scan():
    """--engine notebook: the notebook only stages its run, and the command line publishes it, with the executed
    notebook in its run folder (not in latest/), once the notebook's outputs pass the privacy scan. A real identifier
    in them (P01, exit 1) publishes nothing, latest/ included, and deletes the notebook; so does a P01 from the run's
    own scan inside the notebook, whose parameters cell may hold the leak. No temporary folder stays."""
    import contextlib
    import io
    import json
    import os
    import nbformat
    from ipa_trends import cli, engine, nbexec
    d = Path(tempfile.mkdtemp())
    (d / 'tmp').mkdir()
    out, mode = d / 'out', {}

    class Failed(Exception):
        ename, evalue = 'PrivacyError', ("P01: the privacy scan found real identifiers in 1 output field(s): "
                                         "['report and charts']; nothing was published")

    def fake(notebook, out_path, params, cwd=None, kernel_name='python3'):     # what run_and_show does in the kernel
        handoff = Path(os.environ['IPA_TRENDS_RESULT'])
        if mode.get('p01'):                      # e.g. an account name in REPORT_TITLE
            nbformat.write(nbformat.v4.new_notebook(), str(out_path))
            handoff.write_text(json.dumps({'ok': False, 'code': 'P01', 'stage': 'privacy scan', 'exit_code': 1}))
            raise Failed()
        stage = handoff.parent / 'stage'
        stage.mkdir()
        (stage / 'rates.csv').write_text('a\n1\n')
        (stage / 'manifest.json').write_text('{}')
        nbformat.write(nbformat.v4.new_notebook(), str(out_path))
        handoff.write_text(json.dumps({'ok': True, 'run_id': 'r1', 'output_dir': str(out), 'staged': str(stage),
                                       'run_dir': str(out / 'runs' / 'r1'), 'latest_dir': str(out / 'latest'),
                                       'distribution_ready': True, 'warnings': [],
                                       'summary': {'latest_label': '2026 Q3', 'frequency_name': 'quarterly'}}))
    saved = nbexec.execute, sys.modules.get('papermill'), engine.scan_notebook, tempfile.tempdir
    nbexec.execute, sys.modules['papermill'], tempfile.tempdir = fake, None, str(d / 'tmp')
    argv = ['run', '--engine', 'notebook', '--set', f'OUTPUT_DIR={out}', '--quiet']
    try:
        engine.scan_notebook = lambda P, path: 2
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(argv)
        assert rc == 1 and 'P01' in err.getvalue() and not (out / 'latest').exists() and not (out / 'runs').exists()
        rec = next(out.glob('failed/*/error.txt'))
        assert rec.read_text().startswith('code: P01\nstage: notebook privacy scan\nexit_code: 1\n')
        assert not (rec.parent / 'executed_notebook.ipynb').exists() and not list((d / 'tmp').iterdir())
        engine.scan_notebook = lambda P, path: 0
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            rc = cli.main(argv)
        assert rc == 0 and (out / 'latest' / 'rates.csv').exists() and 'Executed notebook saved to' in said.getvalue()
        assert (out / 'runs' / 'r1' / 'executed_notebook.ipynb').exists()
        assert not (out / 'latest' / 'executed_notebook.ipynb').exists() and not list((d / 'tmp').iterdir())
        mode['p01'] = True
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = cli.main(['run', '--engine', 'notebook', '--set', f'OUTPUT_DIR={d / "out2"}', '--quiet'])
        rec = next((d / 'out2').glob('failed/*/error.txt'))
        assert rc == 1 and rec.read_text().startswith('code: P01\nstage: privacy scan\nexit_code: 1\n')
        assert not (rec.parent / 'executed_notebook.ipynb').exists() and not (d / 'out2' / 'runs').exists()
        assert 'so it was deleted' in err.getvalue() and not list((d / 'tmp').iterdir())
    finally:
        nbexec.execute, engine.scan_notebook, tempfile.tempdir = saved[0], saved[2], saved[3]
        if saved[1] is None:
            sys.modules.pop('papermill', None)
        else:
            sys.modules['papermill'] = saved[1]


def test_notebook_show_says_where_the_outputs_are():
    """The notebook says '(also copied to latest/)' only when latest/ was replaced; a back-run says it was not."""
    from types import SimpleNamespace
    from ipa_trends import notebook as NB
    shown, real = [], NB._display
    NB._display = lambda: (shown.append, (lambda s: s), (lambda filename: filename), (lambda s: s))
    try:
        for latest in ('/x/latest', None):
            NB.show(SimpleNamespace(summary={'latest_label': '2025 Q2', 'frequency_name': 'quarterly'}, tables={},
                                    warnings=[], paths={'run_dir': '/x/runs/r', 'latest_dir': latest,
                                                        'distribution_ready': True}))
    finally:
        NB._display = real
    assert 'also copied to `latest/`' in shown[0] and 'back-run' not in shown[0]
    assert 'a back-run: `latest/` was not changed' in shown[1] and 'also copied' not in shown[1]


def test_notebook_says_where_the_failure_is_recorded():
    """Run All that stops prints where the failure record is (or why there is none) before the error itself."""
    import contextlib
    import io
    from ipa_trends import notebook as NB
    d = Path(tempfile.mkdtemp())
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        try:
            NB.run_and_show({'CASE_EXPORTS': str(d / 'missing' / '*.xlsx'), 'OUTPUT_DIR': str(d / 'out')})
        except InputError as e:
            assert e.code == 'E01' and e.failure_record[0].exists()
        else:
            raise AssertionError('no E01')
    assert said.getvalue().startswith(f"Failure record: {d / 'out' / 'failed'}")


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


def test_privacy_allow_never_covers_an_identifier():
    """PRIVACY_ALLOW lets a genuine collision through, but never an account name or a serial (letters included)."""
    real = PRIV.real_sets(names={'Acme Clinic'}, ids={'AB1234'}, cases=set(), private={'text': {'Remote'}})
    vocab = PRIV.trusted_vocabulary(CFG.resolve())
    def hits(allow):
        return PRIV.scan_texts(['model AB1234', 'Acme Clinic', 'LVD Remote'], PRIV.for_outputs(real, vocab, allow),
                               'x').get('x', 0)
    assert hits([]) == 3, hits([])
    assert hits(['Remote']) == 2, hits(['Remote'])                       # the collision goes through
    assert hits(['AB1234', 'Acme Clinic', 'Remote']) == 2                # the serial and the account never do


def test_privacy_vocabulary_holds_trusted_words_only():
    """Only trusted words exempt a one-word real string: the package's own literals, the request-type labels and
    REQUEST_TYPES_LOCAL. A city typed into the Model column is a hit; a city or note equal to a package or request-type
    word (Normal, Badge) is not; PRIVACY_ALLOW lets a genuine collision through, never an account name."""
    P = CFG.resolve()
    real = PRIV.real_sets({'Fake Community Clinic 012', 'Zenith'}, {'FT9000123'}, set(),
                          {'text': {'Testville012', 'Normal', 'Badge', 'Remote'}, 'digit': set()})
    s = PRIV.output_strings(real, P)
    assert {'testville012', 'remote', 'zenith', 'fake community clinic 012'} <= s['text']
    assert not {'normal', 'badge'} & s['text']
    strata = pd.DataFrame({'stratum_dim': ['model', 'model'], 'stratum': ['Other models', 'LVD-Remote-2.0'],
                           'member': ['Testville012', 'LVD-Remote-2.0']})
    assert PRIV.scan_frame(strata, s, 'strata') == {'strata.stratum': 1, 'strata.member': 2}
    assert PRIV.scan_texts(['- Badge Reader: 12 tickets, in the normal range'], s, 'notebook') == {}
    allowed = PRIV.output_strings(real, CFG.resolve({'PRIVACY_ALLOW': ['Remote', 'Zenith']}))
    assert 'remote' not in allowed['text'] and 'zenith' in allowed['text']
    assert PRIV.scan_frame(strata, allowed, 'strata') == {'strata.member': 1}
    d = Path(tempfile.mkdtemp())
    (d / 'local.csv').write_text('trouble_code,category,group\nElectro/Mechanical,Latch Sensor,Door\n',
                                 encoding='utf-8')
    latch = PRIV.real_sets(set(), set(), set(), {'text': {'Latch'}, 'digit': set()})
    assert 'latch' in PRIV.output_strings(latch, P)['text']
    assert 'latch' not in PRIV.output_strings(latch, CFG.resolve({'REQUEST_TYPES_LOCAL': str(d / 'local.csv')}))['text']
    # every word of a generated period or install-cohort label is a package word, or a year or number (masked)
    labels = {'Unknown'}
    for n in (1, 2, 3, 4, 5, 6, 12, 24):
        for ysm, named, anchor in ((1, 'end', None), (4, 'end', None), (10, 'start', None), (1, 'end', '2025-02-15')):
            g = CAD.period_grid(CAD.Cadence(n), T('2023-01-01'), T('2027-01-01'), ysm, named, anchor)
            labels |= set(g.label) | set(g.label_long)
    g = CAD.period_grid(None, T('2025-08-01'), T('2026-09-01'),
                        explicit_edges=['2025-08-01', '2026-02-15', '2026-09-01'])
    labels |= set(g.label) | set(g.label_long)
    for width in ('1 year', '6 months', 'quarterly', '2 years'):
        bins = CAD.cohort_bins(CAD.parse_frequency(width), '2016-01-01', last_install=T('2026-05-01'))
        labels |= {b[0] for b in bins}
    words = {w for lab in labels for w in FX.norm(PRIV.mask(lab)).split() if len(w) >= 4 and not w.isdigit()}
    assert words and words <= PRIV.trusted_vocabulary(P), words - PRIV.trusted_vocabulary(P)


def test_notebook_scan_uses_the_publish_vocabulary():
    """The executed-notebook scan exempts exactly what the publish scan exempts: a 'Badge' credentialing note does not
    stop a notebook that shows the Badge Reader Category, a city does, and PRIVACY_ALLOW applies."""
    import nbformat
    from ipa_trends import engine
    real = PRIV.real_sets({'Fake Community Clinic 012'}, set(), set(),
                          {'text': {'Badge', 'Testville012', 'Remote'}, 'digit': set()})
    d = Path(tempfile.mkdtemp())

    def notebook(i, text):
        nb = nbformat.v4.new_notebook()
        cell = nbformat.v4.new_code_cell('result')
        cell.outputs = [nbformat.v4.new_output('display_data', data={'text/markdown': text})]
        nb.cells = [cell]
        nbformat.write(nb, str(d / f'{i}.ipynb'))
        return d / f'{i}.ipynb'
    saved = engine.real_strings
    engine.real_strings = lambda P: real
    try:
        P = CFG.resolve()
        assert engine.scan_notebook(P, notebook(1, '- Badge Reader: 12 tickets in the latest period')) == 0
        assert engine.scan_notebook(P, notebook(2, '- Model Testville012: 3 machines')) == 1
        assert engine.scan_notebook(P, notebook(3, '- LVD-Remote-2.0: higher')) == 1
        assert engine.scan_notebook(CFG.resolve({'PRIVACY_ALLOW': ['Remote']}), notebook(3, '- LVD-Remote-2.0')) == 0
    finally:
        engine.real_strings = saved


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


def test_reconcile_report_names_the_compared_intervals():
    """Intervals are compared for R2 and R3 only (ag_band_rates has none; ag_install_pooled's were made with another
    rule), so the summary line names the targets whose intervals were compared."""
    from ipa_trends import reconcile as REC
    t = REC.Tally()
    t.add('R2 age_rates intervals', '<1 ci_lo', 1.0, 1.0, 'interval')
    t.add('R3 ag_type_rates intervals', 'Door Under 4 rate_lo', 2.0, 2.0, 'interval')
    t.add('R8 install_pooled (year)', '2015 Door rate', 0.0, 0.0)
    lines = []
    assert REC.report(t, out=lines.append)
    assert lines[-1] == ('Values (counts, machine-months, rates): all match; intervals compared (R2, R3): all match; '
                         '3/3 in all.'), lines[-1]
    t = REC.Tally()
    t.add('R8 install_pooled (cohort)', '2016-18 Door months', 5.0, 5.0)
    lines = []
    REC.report(t, out=lines.append)
    assert 'no intervals compared' in lines[-1]
    assert 'association.ci' in REC.__doc__ and 'every count, machine-month, rate and\ninterval' not in REC.__doc__


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
