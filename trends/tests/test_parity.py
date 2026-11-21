#!/usr/bin/env python3
"""MIT-side parity: the trend engine against the scripts that produced the numbers IPA has seen.

Runs only when ../verification exists (the MIT repository); IPA's standalone copy skips it.
  1. every copied definition equals its source (syntax trees; the reference CSV byte for byte), and the chart style
     files are byte copies;
  2. machine frame: on VD's synthetic fixture, the engine with edges [2025-08-01, 2026-02-15, 2026-09-01] equals
     fleet_exposure.machine_frame serial by serial (start, months, halves, tickets, age bands, accounts) and uses the
     same account order for the bootstrap. Two machines without tickets are moved to install dates after the window
     and inside the second half, so machines without exposure (no age band) are compared too;
  3. rates: the engine's rates by family, age band and model equal fleet_exposure.group_rates on that frame,
     intervals included;
  4. reconcile: followups.py (Part A) is run on the fixture; the reconcile machinery rebuilds its reference values
     and must match all of them (and must fail on a perturbed copy).
Run: python3 -I trends/tests/test_parity.py      (prints ALL OK or SOME PROBLEMS; exit 1 on a problem)
"""
import copy
import filecmp
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TRENDS = Path(__file__).resolve().parents[1]
ROOT = TRENDS.parent
VER = ROOT / 'verification'
sys.path.insert(0, str(TRENDS))
sys.path.insert(0, str(TRENDS / 'tests'))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RESULTS = []


def ok(name, cond):
    RESULTS.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    return bool(cond)


EDGES = ['2025-08-01', '2026-02-15', '2026-09-01']
NO_EXPOSURE_INSTALLS = (pd.Timestamp('2026-09-20'), pd.Timestamp('2026-05-04'))   # after the window; in the 2nd half


def fixture():
    """VD's synthetic workbooks (make_fixture.py, local clock), built into a temporary folder, with the two
    machines of NO_EXPOSURE_INSTALLS added (see no_exposure_machines)."""
    sys.path.insert(0, str(VER / 'tests'))
    sys.path.insert(0, str(VER))
    import make_fixture
    out = Path(tempfile.mkdtemp(prefix='trends_parity_'))
    with open(out / 'build.log', 'w') as log:
        subprocess.run([sys.executable, '-I', str(VER / 'tests' / 'make_fixture.py'), '--out', str(out)],
                       check=True, stdout=log, stderr=log)
    no_exposure_machines(out / 'fake_cases.xlsx', out / make_fixture.EQUIPMENT_FILE)
    return out, out / 'fake_cases.xlsx', out / make_fixture.EQUIPMENT_FILE


def no_exposure_machines(xlsx, equipment):
    """Rewrite the equipment copy: the first two listed serials without tickets get the install dates of
    NO_EXPOSURE_INSTALLS, so one machine has no exposure in the window and another none in its first half (their
    age bands are missing, which the band checks must compare as equal)."""
    import openpyxl

    def key(s):                         # how a serial could still meet a ticket (spaces, case, leading zeros)
        return str(s).strip().casefold().lstrip('0')
    cases = pd.read_excel(xlsx, sheet_name='ipa_repair cases', usecols=['Serial #'], dtype=str)
    ticketed = {key(s) for s in cases['Serial #'].dropna()}
    wb = openpyxl.load_workbook(equipment)
    ws = wb.worksheets[0]
    head = [c.value for c in ws[1]]
    i_serial, i_install, i_live = head.index('Serial Number'), head.index('Install Date'), head.index('Go Live Date')
    rows = sorted((r for r in ws.iter_rows(min_row=2) if r[i_serial].value and key(r[i_serial].value) not in ticketed),
                  key=lambda r: key(r[i_serial].value))
    assert len(rows) >= len(NO_EXPOSURE_INSTALLS), 'the fixture has too few listed serials without tickets'
    for r, day in zip(rows, NO_EXPOSURE_INSTALLS):
        r[i_install].value = r[i_live].value = day.to_pydatetime()
    wb.save(equipment)


def same(a, b):
    """Equal element by element, a missing value equal to a missing value (an age band is missing for a machine
    without exposure; pandas 3 keeps NaN through astype(str), and NaN never equals NaN)."""
    a, b = a.astype(object), b.astype(object)
    return bool(((a == b) | (a.isna() & b.isna())).all())


def verification_frames(xlsx, equipment):
    import common
    import fleet_exposure as FXv
    from flags import monitoring_template
    raw = common.load_raw(xlsx)
    maps = common.build_maps(raw)
    cases = common.build_cases(raw, maps)
    conn = common.case_database(cases)
    sc = pd.read_sql('SELECT * FROM service_cases', conn)
    eq = common.load_equipment(equipment)
    maps = common.extend_maps(maps, eq)
    inv = {v: k for k, v in maps['serial'].items()}
    text = dict(zip(raw['Case Number'].map(common.clean).map(maps['case']), raw['Trouble Reported']))
    sc['serial'] = sc.machine_id.map(inv)
    sc['ts'] = pd.to_datetime(sc.opened_at)
    sc['monitoring'] = sc.case_id.map(text).map(monitoring_template).astype(bool)
    sc['core'] = ~sc.monitoring & (sc.service_group != 'No Trouble Found')
    m_all, _ = FXv.machine_frame(eq, maps, sc)
    m = FXv.add_rate_groups(m_all[~m_all.third_party].copy().reset_index(drop=True))
    return FXv, m, sorted(m.customer.unique())


def engine_frames(xlsx, equipment, list_date, edges):
    from ipa_trends import cadence, config, exposure, inputs
    P = config.resolve({'UNMAPPED_POLICY': 'fallback', 'PERIOD_EDGES': edges, 'CASE_EXPORTS': str(xlsx),
                        'EQUIPMENT_LISTS': str(equipment)})
    W = inputs.Warnings()
    fr, meta = inputs.read_sheet(xlsx, P.CASE_SHEET, inputs.CASE_REQUIRED, inputs.CASE_OPTIONAL, inputs.CASE_KNOWN,
                                 {}, W, 'case')
    t, _, _, _, accts = inputs.build_tickets(fr, meta, P, W)
    e, _, _ = inputs.read_equipment(equipment, P, W)
    led, _ = inputs.build_ledger([(pd.Timestamp(list_date), e)])
    led['customer'] = led.account.map(inputs.account_labels(accts, led.account))
    d0, d1 = pd.Timestamp(edges[0]), pd.Timestamp(edges[-1])
    pr = exposure.population(led, t, d0, d1, P, W)
    pop = pr['pop']
    bins = cadence.cohort_bins(P.cohort_width, P.INSTALL_COHORT_START, last_install=pop.install_date.max())
    pop['install_cohort'] = cadence.assign_cohorts(pop.install_date, bins)
    grid = cadence.period_grid(None, d0, d1, explicit_edges=edges)
    cat = exposure.issue_catalog(pr['t'])
    mp, outside = exposure.machine_periods(pop, pr['t'], grid, cat, ['install_cohort'])
    return pop, mp, sorted(pop.customer.unique()), outside


def machine_frame_parity(xlsx, equipment, list_date='2026-10-19', no_band=None):
    """[(check, ok)]: the engine against fleet_exposure.machine_frame, machine by machine (also used by
    `ipa-trends reconcile --deep` on the real files). Age bands are compared with a missing band equal to a missing
    band; `no_band` (a dict), when given, receives the engine's number of machines without a band in the whole
    window, h1 and h2."""
    sys.path.insert(0, str(VER))
    FXv, m, acc_v = verification_frames(xlsx, equipment)
    pop, mp, acc_e, outside = engine_frames(xlsx, equipment, list_date, EDGES)
    o, n = m.set_index('serial'), pop.set_index('serial')
    res = [('same machines in the population', set(o.index) == set(n.index)),
           ('same accounts in the same bootstrap order', acc_v == acc_e),
           ('no ticket falls outside the periods', outside == 0)]
    common_ix = o.index.intersection(n.index)
    o, n = o.loc[common_ix], n.loc[common_ix]
    res += [('exposure start (every machine)', bool((o.start == n.start).all())),
            ('whole-window machine-months (every machine)', float((o.months - n.months).abs().max()) < 1e-12),
            ('whole-window age band (every machine)', same(o.age_band, n.age_band)),
            ('account label (every machine)', bool((o.customer == n.customer).all()))]
    counts = {'whole': int(n.age_band.isna().sum())}
    for pos, h in ((0, 'h1'), (1, 'h2')):
        q = mp[mp.period_pos == pos].set_index('serial')
        mm = q.months.reindex(common_ix).fillna(0.0)
        tt = q['all'].reindex(common_ix).fillna(0)
        ab = q.age_band.reindex(common_ix)
        counts[h] = int(ab.isna().sum())
        res += [(f'{h} machine-months (every machine)', float((o[f'months_{h}'] - mm).abs().max()) < 1e-12),
                (f'{h} tickets (every machine)', bool((o[f'tickets_{h}'] == tt).all())),
                (f'{h} age band (every machine)', same(o[f'age_band_{h}'], ab))]
    if no_band is not None:
        no_band.update(counts)
    return res


def rates_parity(xlsx, equipment):
    """The engine's whole-window rates (via reconcile's run) against group_rates on fleet_exposure's frame."""
    from ipa_trends import reconcile
    FXv, m, acc = verification_frames(xlsx, equipment)
    W = FXv.boot_weights(len(acc), 200)
    runs = reconcile.engine_runs({'CASE_EXPORTS': str(xlsx), 'EQUIPMENT_LISTS': str(equipment),
                                  'EQUIPMENT_LIST_DATES': {Path(equipment).name: '2026-10-19'},
                                  'THIRD_PARTY_PLANS': ['Vogeltronix']}, None, say=lambda *a: None, n_boot=200)
    r = runs['whole'].tables['rates']
    res = []
    for dim, col in (('family', 'family'), ('age_band', 'age_band'), ('model', 'model')):
        g, _ = FXv.group_rates(m, col, W, acc)
        mine = r[(r.stratum_dim == dim) & (r.issue_key == 'all')].set_index('stratum')
        g = g.set_index(g[col].astype(str))
        same = set(g.index) == set(mine.index)
        if same:
            mine = mine.loc[g.index]
            for c_v, c_e in (('machines', 'machines'), ('tickets', 'tickets'), ('accounts', 'accounts')):
                same &= bool((g[c_v].to_numpy() == mine[c_e].to_numpy()).all())
            for c in ('months', 'rate_per_100', 'ci_lo', 'ci_hi', 'ratio_lo', 'ratio_hi'):
                c_e = 'machine_months' if c == 'months' else c
                same &= bool(np.allclose(g[c].to_numpy(float), mine[c_e].to_numpy(float), rtol=1e-12,
                                         equal_nan=True))
        res.append((f'rates by {dim}: counts, machine-months, rates and intervals equal group_rates', same))
    return res, runs


def reconcile_parity(xlsx, equipment, runs_whole):
    """followups.py on the fixture; reconcile's comparison must match every value it can find."""
    from ipa_trends import reconcile
    out = Path(tempfile.mkdtemp(prefix='trends_followups_'))
    fu = out / 'fu_stub'
    fu.mkdir()
    (fu / 'fu_ticket_last10.csv').write_text('case_id,machine_id,window\n')
    (fu / 'fu_devices.csv').write_text('machine_id,machine_type\n')
    (out / 'followups').mkdir()
    run = subprocess.run([sys.executable, '-I', str(VER / 'followups.py'), '--xlsx', str(xlsx), '--equipment',
                          str(equipment), '--fu-dir', str(fu), '--out', str(out / 'followups'), '--no-pins',
                          '--n-boot', '200', '--n-perm', '200', '--n-sim', '200'], capture_output=True, text=True)
    res = [('followups.py ran on the fixture', run.returncode == 0)]
    if run.returncode != 0:
        print(run.stdout[-2000:], run.stderr[-2000:])
        return res
    ref = reconcile.build_reference(out)
    runs = reconcile.engine_runs({'CASE_EXPORTS': str(xlsx), 'EQUIPMENT_LISTS': str(equipment),
                                  'EQUIPMENT_LIST_DATES': {Path(equipment).name: '2026-10-19'}},
                                 ref.get('support_models'), say=lambda *a: None, n_boot=200)
    t = reconcile.compare(ref, runs)
    rows = pd.DataFrame(t.rows)
    bad = rows[~rows.ok]
    for r in bad.head(10).itertuples():
        print(f'    differs: {r.target} | {r.item}: expected {r.expected}, got {r.actual}')
    for target in sorted(rows.target.unique()):
        sub = rows[rows.target == target]
        res.append((f'reconcile on the fixture: {target} ({int(sub.ok.sum())}/{len(sub)})', bool(sub.ok.all())))
    worse = copy.deepcopy(ref)
    worse['type_rates'][0]['under4_tickets'] += 1
    res.append(('reconcile fails on a perturbed reference', not all(r['ok'] for r in
                                                                   reconcile.compare(worse, runs).rows)))
    return res


def copies():
    import sync_definitions
    res = [(f'definitions: {lab}', good) for lab, good in sync_definitions.check(verbose=False)]
    style = TRENDS / 'ipa_trends' / 'style'
    for name in ('ipa_style.py', 'ipa.mplstyle'):
        src = ROOT / 'viz' / 'style' / name
        res.append((f'style: {name} is a byte copy', (style / name).exists()
                    and filecmp.cmp(src, style / name, shallow=False)))
    fixture_gen = TRENDS / 'tests' / 'make_trend_fixture.py'
    if fixture_gen.exists():
        sys.path.insert(0, str(VER / 'tests'))
        import make_fixture
        import make_trend_fixture as MT
        res.append(('synthetic fixture uses the 19 real case headers', list(MT.HEADERS) == list(make_fixture.HEADERS)))
        res.append(('synthetic fixture uses the 22 real equipment headers',
                    list(MT.EQUIP_HEADERS) == list(make_fixture.EQUIP_HEADERS)))
    return res


def main():
    if not VER.exists():
        print('verification/ not found: parity checks run only in the MIT repository (skipped)')
        return 0
    print('Copied definitions and style')
    for name, good in copies():
        ok(name, good)
    print('Fixture (verification/tests/make_fixture.py)')
    base, xlsx, equipment = fixture()
    print('Machine frame against fleet_exposure.machine_frame')
    no_band = {}
    frame_checks = machine_frame_parity(xlsx, equipment, no_band=no_band)
    for name, good in frame_checks:
        ok(name, good)
    ok(f"all {len(frame_checks)} machine-frame checks pass with machines without exposure in the fixture "
       f"(no age band: whole window {no_band['whole']}, h1 {no_band['h1']}, h2 {no_band['h2']})",
       len(frame_checks) == 13 and all(g for _, g in frame_checks)
       and no_band['whole'] >= 1 and no_band['h1'] >= 2 and no_band['h2'] >= 1)
    print('Rates against fleet_exposure.group_rates')
    res, runs = rates_parity(xlsx, equipment)
    for name, good in res:
        ok(name, good)
    print('Reconciliation machinery against followups.py (Part A) on the fixture')
    for name, good in reconcile_parity(xlsx, equipment, runs):
        ok(name, good)
    bad = [n for n, g in RESULTS if not g]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} parity checks pass\n{'ALL OK' if not bad else 'SOME PROBLEMS'}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
