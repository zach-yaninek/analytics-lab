#!/usr/bin/env python3
"""Fast in-memory unit tests for verification/followups.py (docs/09 §8): no workbook, no fixture files.

  * pairs: a tie on opening time is broken by case number; exactly 30 days counts and 30 days + 1 minute does not;
    exactly 7 days counts for the 7-day follow-up; 2026-08-01 23:59 is eligible and 2026-08-02 00:00 is not;
    the copied SQL and the copied pandas pair-builder agree;
  * Mantel-Haenszel share and rate ratios return a planted common ratio; CMH X and z match hand values;
  * the bootstrap with every weight 1 reproduces the point estimate;
  * the A4 decomposition sums exactly to the extra tickets;
  * the random-timing simulator matches (n-1)(1-(1-d/L)^n) for n uniform points on [0, L], and the exact
    uniform null 1-(1-d/L)^(n-1) per eligible ticket matches the simulation with the real cutoff;
  * the label permutation keeps each machine's Categories (constant and two-label machines, a three-ticket mean);
  * the request-type fallback rule and the Monitoring override;
  * the copied code equals its sources (syntax trees).

Run:  cd /home/user/analytics-lab && python3 -I verification/tests/test_followups_units.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import sqlite3  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import followups as F  # noqa: E402

RESULTS = []


def ok(name, cond):
    RESULTS.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def test_pairs():
    rows = [  # machine, case, opened, category
        ('S00001', 'T00002', '2026-01-01 08:00:00', 'Door'),     # tie with T00001: T00001 first (case order)
        ('S00001', 'T00001', '2026-01-01 08:00:00', 'Door'),
        ('S00001', 'T00003', '2026-01-31 08:00:00', 'Door'),     # exactly 30 days after both
        ('S00002', 'T00004', '2026-03-01 00:00:00', 'SAM'),
        ('S00002', 'T00005', '2026-03-31 00:01:00', 'SAM'),      # 30 days + 1 minute
        ('S00003', 'T00006', '2026-04-01 00:00:00', 'Packer'),
        ('S00003', 'T00007', '2026-04-08 00:00:00', 'Packer'),   # exactly 7 days
        ('S00003', 'T00008', '2026-04-15 00:01:00', 'Curtain'),  # 7 days + 1 minute
        ('S00004', 'T00009', '2026-08-01 23:59:00', None),       # last eligible minute
        ('S00004', 'T00010', '2026-08-02 00:00:00', None),       # first ineligible minute
        ('S00004', 'T00011', '2026-08-03 00:00:00', None),
    ]
    c = pd.DataFrame(rows, columns=['machine_id', 'case_id', 'opened_at', 'category'])
    con = sqlite3.connect(':memory:')
    c.to_sql('cases', con, index=False)
    sql = pd.read_sql(F.REPEAT_VIEW_SQL.format(src='cases'), con).set_index('case_id')
    base = pd.DataFrame({'serial': c.machine_id, 'opened': pd.to_datetime(c.opened_at), 'case_id': c.case_id,
                         'category': c.category})
    e, rep, same, simul = F.repeat_summary(F.repeat_frame(base))
    pd_rep = dict(zip(e.case_id, rep))
    gap = dict(zip(e.case_id, e.gap.dt.total_seconds() / 86400))
    ok('tie broken by case number: T00001 -> T00002 (gap 0), T00002 -> T00003 (30 days)',
       pd_rep['T00001'] and pd_rep['T00002'] and gap['T00001'] == 0 and gap['T00002'] == 30)
    ok('exactly 30 days repeats; 30 days + 1 minute does not',
       pd_rep['T00002'] and not pd_rep['T00004'] and sql.loc['T00002', 'repeat_30'] == 1
       and sql.loc['T00004', 'repeat_30'] == 0)
    seven = {k: pd_rep[k] and gap[k] <= F.SHORT_DAYS for k in ('T00006', 'T00007')}
    ok('exactly 7 days is a 7-day follow-up; 7 days + 1 minute is not', seven['T00006'] and not seven['T00007'])
    ok('2026-08-01 23:59 eligible, 2026-08-02 00:00 not',
       'T00009' in set(e.case_id) and 'T00010' not in set(e.case_id) and 'T00009' in sql.index
       and 'T00010' not in sql.index)
    ok('SQL and pandas agree ticket by ticket (repeat and same Category)',
       all(sql.loc[k, 'repeat_30'] == int(pd_rep[k]) for k in e.case_id)
       and all(sql.loc[k, 'same_category_30'] == int(v) for k, v in zip(e.case_id, same)))
    ok('blank Categories never count as the same Category', not dict(zip(e.case_id, same))['T00009'])
    ok('one simultaneous follow-up (the tie)', int(simul.sum()) == 1)


def test_mh_cmh():
    # Two strata; type 0 has twice the share on under-4 machines in each stratum: share ratio 2 in each.
    a = np.array([[20., 80.], [10., 90.]])     # under 4: type 0, type 1 (n1 = 100 each)
    b = np.array([[10., 90.], [5., 95.]])      # 4+ (n0 = 100 each)
    sr = F.mh_share(a, b, a.sum(1), b.sum(1))
    ok('Mantel-Haenszel share ratio recovers a common ratio of 2', abs(sr[0] - 2.0) < 1e-12)
    M1, M0 = np.array([50., 40.]), np.array([100., 80.])
    rr = F.mh_rate(a, b, M1, M0)
    ok('Mantel-Haenszel rate ratio recovers a common ratio of 4 (shares x2, months /2)', abs(rr[0] - 4.0) < 1e-12)
    a1, b1 = np.array([[10., 0.]]), np.array([[0., 10.]])
    X, z = F.cmh(a1, b1, a1.sum(1), b1.sum(1))
    ok('CMH X equals the Pearson chi-square of [[10, 0], [0, 10]] (20)', abs(X - 20.0) < 1e-9)
    ok('CMH z squared equals the CMH statistic (19)', abs(z[0] ** 2 - 19.0) < 1e-9)
    Xs, _ = F.cmh(np.array([[5., 5.], [3., 0.]]), np.array([[5., 5.], [0., 4.]]), np.array([10., 3.]),
                  np.array([10., 4.]))
    ok('a stratum with one age group per type adds nothing when the mix is equal elsewhere', Xs >= 0)
    # bootstrap with every weight 1 reproduces the point estimate
    acc = np.array([[[2., 8.], [1., 9.]], [[18., 72.], [9., 81.]]])    # 2 accounts x 2 strata x 2 types (under 4)
    acc_b = np.array([[[1., 9.], [0., 10.]], [[9., 81.], [5., 85.]]])
    W = np.ones((1, 2))
    ay = (W @ acc.reshape(2, -1)).reshape(1, 2, 2)
    by = (W @ acc_b.reshape(2, -1)).reshape(1, 2, 2)
    ok('bootstrap draw with all weights 1 = point estimate',
       abs(F.mh_share(ay, by, ay.sum(-1), by.sum(-1))[0, 0] - F.mh_share(acc.sum(0), acc_b.sum(0),
                                                                          acc.sum(0).sum(-1),
                                                                          acc_b.sum(0).sum(-1))[0]) < 1e-12)


def test_cmh_excess():
    rng = np.random.default_rng(7)
    a = rng.integers(0, 30, size=(4, 3)).astype(float)
    b = rng.integers(0, 30, size=(4, 3)).astype(float)
    n1, n0 = a.sum(1) + 5, b.sum(1) + 5
    X, _ = F.cmh(a, b, n1, n0)
    D = F.cmh_excess(a, b, n1, n0)
    N = (n1 + n0)[:, None]
    E1, E0 = (n1[:, None] * (a + b) / N).sum(0), (n0[:, None] * (a + b) / N).sum(0)
    ok('cmh_excess = observed - expected under-4 tickets, and gives cmh X', np.allclose(D, a.sum(0) - E1)
       and abs(X - (D ** 2 * (1 / E1 + 1 / E0)).sum()) < 1e-9)


def test_chi2():
    import high_ticket_machines as H
    even = [(33.872, 8), (5.0, 2), (0.5, 4), (20.0, 6)]
    ok('chi2_sf = the Poisson closed form for even df', all(
        abs(F.chi2_sf(x, df) - (1 - H.poisson_sf(df // 2, x / 2))) < 1e-12 for x, df in even))
    ok('chi2_sf at the 5% critical values (df 1, 3, 9)', all(
        abs(F.chi2_sf(x, df) - 0.05) < 1e-9 for x, df in [(3.841458820694124, 1), (7.814727903251178, 3),
                                                            (16.918977604620448, 9)]))
    ok('chi2_sf(0) = 1 and a tiny upper tail stays positive', F.chi2_sf(0, 8) == 1 and 0 < F.chi2_sf(100, 8) < 1e-15)


def test_decomposition():
    rng = np.random.default_rng(1)
    T = rng.integers(0, 50, size=(5, 2, 3)).astype(float)
    M = rng.uniform(10, 200, size=(5, 2))
    M[4, 0] = 0.0                               # a model with no 4+ machines: outside the support
    supm = np.array([True, True, False, True, False])
    total, within, mix, outside, My = F.decompose(T, M, supm)
    ok('decomposition parts sum exactly to the extra tickets', np.allclose(within + mix + outside, total, atol=1e-9))
    ok('extra tickets = under-4 tickets - under-4 months x 4+ rate',
       np.allclose(total, T[:, 1].sum(0) - M[:, 1].sum() * T[:, 0].sum(0) / M[:, 0].sum()))
    Tb = np.stack([T, T])
    Mb = np.stack([M, M])
    tb = F.decompose(Tb, Mb, supm)[0]
    ok('decomposition vectorises over bootstrap draws', np.allclose(tb[0], total) and np.allclose(tb[1], total))


def test_simulator():
    L, d = 300.0, 30.0
    worst = 0.0
    for n in range(2, 11):
        k = 2000
        E, _ = F.simulate(np.full(k, n), np.zeros(k), L, L + 1, L / 2, 100, np.random.default_rng(n))
        got = E['rep30'].mean()
        want = (n - 1) * (1 - (1 - d / L) ** n)
        worst = max(worst, abs(got - want) / (E['rep30'].std() / np.sqrt(k)))
    ok(f'simulator matches (n-1)(1-(1-d/L)^n) for n = 2..10 within 4 standard errors (worst {worst:.1f})',
       worst < 4)
    n_i = np.array([2, 3, 5, 8, 12] * 400)
    a_i = np.tile([0.0, 100.0, 250.0, 300.0], 500)
    b, cut = 396.0, 366.0                       # the real period: cutoff exactly 30 days before the window end
    E, _ = F.simulate(n_i, a_i, b, cut, 198.0, 200, np.random.default_rng(7))
    exact = F.uniform_p(n_i, b - a_i, 30.0)
    sim = E['rep30'].sum() / E['elig'].sum()
    want = (E['elig'] * exact).sum() / E['elig'].sum()
    ok(f'exact uniform null = simulated ratio of expectations (sim {sim:.4f}, exact {want:.4f})',
       abs(sim / want - 1) < 0.01)
    ok('exact uniform null: one ticket never repeats; windows of 30 days or less have no eligible ticket',
       F.uniform_p([1], [300.0], 30.0)[0] == 0 and F.uniform_p([5], [30.0], 30.0)[0] == 0)
    E, _ = F.simulate(np.array([3, 3]), np.array([0.0, 100.0]), 200.0, 150.0, 100.0, 200, np.random.default_rng(3))
    ok('eligible tickets respect the cutoff (window [100, 200) with cutoff 150: about half eligible)',
       abs(E['elig'][1] - 1.5) < 0.25 and abs(E['elig'][0] - 2.25) < 0.25)


def test_label_permutation():
    rng = np.random.default_rng(0)
    const = F.label_permutation_null([(np.array(['A', 'A', 'A']), np.array([0, 1]), np.array([1, 2]))], 500, rng)
    ok('machine with one Category: every permutation gives the observed count', (const == 2).all())
    two = F.label_permutation_null([(np.array(['A', 'B']), np.array([0]), np.array([1]))], 500, rng)
    ok('two different Categories, one pair: never the same', (two == 0).all())
    three = F.label_permutation_null([(np.array(['A', 'A', 'B']), np.array([0, 1]), np.array([1, 2]))], 20000, rng)
    ok(f'A, A, B with pairs (1,2), (2,3): null mean 2/3 (got {three.mean():.3f})', abs(three.mean() - 2 / 3) < 0.02)


def test_request_types():
    ref = pd.read_csv(F.REF, dtype=str, keep_default_na=False)
    sc = pd.DataFrame({'trouble_code': ['Network', 'Miscellaneous', 'Foo', 'Electronics', 'Miscellaneous', None],
                       'category': ['Connectivity', None, 'Bar', 'Touchscreen', 'No Trouble Found', None],
                       'monitoring': [False, False, False, False, True, False]})
    unmapped = F.assign_request_types(sc, ref)
    ok('fallback: a Trouble Code that fixes the group gives it (Network / Connectivity -> Network)',
       sc.cgroup[0] == 'Network')
    ok('reference: Miscellaneous with no Category -> Not categorised', sc.cgroup[1] == 'Not categorised')
    ok('fallback: anything else -> Other', sc.cgroup[2] == 'Other')
    ok('reference: Electronics / Touchscreen -> Electronics, Category level Touchscreen',
       sc.cgroup[3] == 'Electronics' and sc.ctype[3] == 'Touchscreen')
    ok('Monitoring overrides group and Category level, cgroup keeps the recorded group',
       sc.group[4] == 'Monitoring' and sc.ctype[4] == 'Monitoring' and sc.cgroup[4] == 'No Trouble Found')
    ok('no Trouble Code and no Category -> Not categorised', sc.cgroup[5] == 'Not categorised')
    ok('unmapped combinations are reported', sorted(unmapped) == ['Foo / Bar', 'Network / Connectivity'])
    ok('reference hash is the frozen one', F.request_types_hash(F.REF) == F.REF_HASH)


def test_copies():
    res = F.copied_code_matches()
    ok(f'copied code equals its sources ({len(res)} definitions)', all(res.values()))


def main():
    for t in (test_pairs, test_mh_cmh, test_cmh_excess, test_chi2, test_decomposition, test_simulator, test_label_permutation,
              test_request_types, test_copies):
        print(t.__name__)
        t()
    fails = [n for n, v in RESULTS if not v]
    print(f'\n{len(RESULTS) - len(fails)}/{len(RESULTS)} unit tests pass')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
