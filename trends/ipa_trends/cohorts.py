"""Install cohorts: how machines installed in different date ranges compare. This is the view that surfaced the
Touchscreen peak (2022-23 installs at 1.54 per 100 machine-months, 3.9 times the 2024-26 rate).

For each install cohort x issue:

  profile         rate per 100 installed machine-months over the contrast window (the last CONTRAST_MONTHS of final
                  periods), with the committed interval (copied group_rates)
  crude ratio     the cohort's rate over the rest of the fleet's rate, in the window
  newer / older   the cohort's rate over the rate of every cohort installed after it / before it, in the window
  same-age ratio  O / sum_b M(cohort, b) x rate(other cohorts, b) over every final period of the history, with b the
                  age band of each machine in each period: the cohort against machines of the same age from other
                  cohorts. Bands where the other cohorts have fewer than 100 machine-months are left out of both
                  sides; the ratio is not estimable when that drops more than 25% of the cohort's tickets.

All ratios get paired account-bootstrap intervals and p-values. A cohort 'stands out' (higher) when at least
MIN_EXPECTED tickets are expected, the window's labels are complete, and:

  - a cohort with both older and newer installs is at least 1 + MIN_CONTRAST times the rest of the fleet and at least
    1 + MIN_CONTRAST / 2 times both the newer and the older installs: a peak in the install-date profile, which no
    steady age effect (rates rising, or falling, with machine age) can produce. Two neighbouring cohorts can both
    stand out, since each is compared with all newer and all older installs;
  - the newest cohort, which has no newer installs, is at least 1 + MIN_CONTRAST times both the rest of the fleet and
    earlier installs observed at the same age;
  - and every one of those comparisons is beyond chance together: the call-out's p-value is the largest of their
    p-values (an intersection-union test), and one Benjamini-Hochberg correction runs over every cohort x issue cell
    (q below Q_CUT).

The oldest, pooled cohort ('Before ...') and 'Unknown' are shown but never called out. 'Lower' is the mirror image.
Within one year of data a pure same-age comparison cannot separate neighbouring install years from machine age
(docs/10), which is why the call-out rests on the peak; the same-age ratio is reported for context. 'persisting'
marks a cohort that also stood out in the window ending one period earlier.
"""
import warnings

import numpy as np
import pandas as pd

from . import rates as RT
from . import stats
from .definitions import association_copy as A
from .definitions import fleet_exposure_copy as FX
from .definitions import followups_copy as FU
from .inputs import UNKNOWN, UNMAPPED

MIN_COMPARATOR_MONTHS = 100
KEY_CHUNK = 8
MAX_DROPPED = 0.25


def same_age_table(O, M, min_comparator=MIN_COMPARATOR_MONTHS):
    """Same-age ratio for every cohort from cohort x band tickets O (C x B) and machine-months M (C x B).

    For cohort c: expected = sum over bands b with at least `min_comparator` machine-months in the other cohorts of
    M[c, b] x (tickets / machine-months of the other cohorts in band b). Returns (ratio, expected, observed in the
    kept bands, share of the cohort's tickets in dropped bands), each of length C."""
    O, M = np.asarray(O, float), np.asarray(M, float)
    o_rest, m_rest = O.sum(0)[None] - O, M.sum(0)[None] - M
    keep = m_rest >= min_comparator
    with np.errstate(invalid='ignore', divide='ignore'):
        e = np.where(keep, M * o_rest / m_rest, 0.0).sum(1)
        o = np.where(keep, O, 0.0).sum(1)
        dropped = np.where(O.sum(1) > 0, 1 - o / O.sum(1), 1 - np.where(keep, M, 0).sum(1) / M.sum(1))
        return o / e, e, o, dropped


def side_rates(o, m, order):
    """Tickets and machine-months of all newer and all older cohorts, for every cohort.

    o: (..., C, K) tickets, m: (..., C) machine-months on the cohort axis; `order` lists the positions of the dated
    cohorts in install order ('Unknown' left out). Returns (o_newer, m_newer, o_older, m_older) shaped like o and m,
    zero where a cohort has no newer / older cohorts (and for undated cohorts)."""
    o_new, m_new = np.zeros_like(o), np.zeros_like(m)
    o_old, m_old = np.zeros_like(o), np.zeros_like(m)
    so, sm = o[..., order, :], m[..., order]
    co, cm = np.cumsum(so, axis=-2), np.cumsum(sm, axis=-1)
    to, tm = co[..., -1:, :], cm[..., -1:]
    for j, c in enumerate(order):
        o_old[..., c, :] = co[..., j, :] - so[..., j, :]
        m_old[..., c] = cm[..., j] - sm[..., j]
        o_new[..., c, :] = to[..., 0, :] - co[..., j, :]
        m_new[..., c] = tm[..., 0] - cm[..., j]
    return o_new, m_new, o_old, m_old


def contrast_window(grid, latest_pos, months, mask=None):
    """Final periods that start within the `months` before the latest period ends (latest included)."""
    if latest_pos is None:
        return []
    start = grid.period_end[latest_pos] - pd.DateOffset(months=int(months))
    ok = (grid.index <= latest_pos) & (grid.status == 'final') & (grid.period_start >= start)
    if mask is not None:
        ok &= np.asarray(mask, bool)
    return [int(i) for i in grid.index[ok]]


def history(grid, latest_pos, mask=None):
    """Every final period up to the latest one."""
    ok = (grid.index <= latest_pos) & (grid.status == 'final')
    if mask is not None:
        ok &= np.asarray(mask, bool)
    return [int(i) for i in grid.index[ok]]


def window_machines(mp, positions, keys):
    """Per-machine totals over the window (so machine counts are machines, not machine-periods)."""
    sub = mp[mp.period_pos.isin(positions)]
    agg = sub.groupby('serial', sort=False).agg(customer=('customer', 'first'),
                                                install_cohort=('install_cohort', 'first'),
                                                months=('months', 'sum'))
    agg[keys] = sub.groupby('serial', sort=False)[keys].sum()
    return agg.reset_index()


def _arrays(mp, positions, cohorts, bands, keys, clusters):
    """T[cohort, band, cluster, key] tickets and M[cohort, band, cluster] machine-months over the periods."""
    sub = mp[mp.period_pos.isin(positions)].copy()
    sub['_cb'] = [f'{c}\x1f{b}' for c, b in zip(sub.install_cohort.astype(str), sub.age_band.astype(str))]
    combos = [f'{c}\x1f{b}' for c in cohorts for b in bands]
    T, M = stats.cluster_arrays(sub, '_cb', keys, positions, clusters, combos)
    return (T.reshape(len(cohorts), len(bands), len(clusters), len(keys)),
            M.reshape(len(cohorts), len(bands), len(clusters)))


def _ci(draws):
    lo, hi, _ = A.ci(draws)
    return lo, hi


def _context(mp, positions):
    sub = mp[mp.period_pos.isin(positions) & (mp.months > 0)]
    age, top = {}, {}
    for c, g in sub.groupby('install_cohort', observed=True):
        age[str(c)] = float(np.average(g.age_years, weights=g.months)) if g.months.sum() > 0 else np.nan
        s = g.groupby('model').months.sum().sort_values(ascending=False)
        top[str(c)] = ', '.join(f'{m} {100 * v / s.sum():.0f}%' for m, v in s.head(3).items())
    return age, top


def _chunk_rows(ctx, cohorts, order, bands, kk, win, hist, set_name):
    """Statistics for one chunk of issue keys."""
    W = ctx.W
    Tw4, Mw3 = _arrays(ctx.mp, win, cohorts, bands, kk, ctx.clusters)
    Th4, Mh3 = _arrays(ctx.mp, hist, cohorts, bands, kk, ctx.clusters)
    Tw, Mw = Tw4.sum(1), Mw3.sum(1)                         # cohort x cluster (x key)
    tb, mb = stats.boot_sums(W, Tw, Mw)                    # draws x cohort x key, draws x cohort
    o_c, m_c = Tw.sum(1), Mw.sum(1)                         # cohort x key, cohort
    rows = []
    with np.errstate(invalid='ignore', divide='ignore'), warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)    # cells with no spread: reported as not estimable
        # crude: the cohort against the rest of the fleet (every other cohort, undated ones included)
        o_r, m_r = o_c.sum(0)[None] - o_c, m_c.sum() - m_c
        crude = (o_c / m_c[:, None]) / (o_r / m_r[:, None])
        e_crude = m_c[:, None] * o_r / m_r[:, None]
        tb_r, mb_r = tb.sum(1, keepdims=True) - tb, mb.sum(1, keepdims=True) - mb
        crude_b = (tb / mb[..., None]) / (tb_r / mb_r[..., None])
        log_crude_b = stats.log_cc(tb, mb[..., None] * tb_r / mb_r[..., None])
        sd_crude = np.nanstd(log_crude_b, axis=0, ddof=1)
        z_crude = stats.log_cc(o_c, e_crude) / sd_crude
        # newer and older installs (dated cohorts only)
        on, mn, oo, mo = side_rates(o_c, m_c, order)
        newer = (o_c / m_c[:, None]) / (on / mn[:, None])
        older = (o_c / m_c[:, None]) / (oo / mo[:, None])
        onb, mnb, oob, mob = side_rates(tb, mb, order)
        newer_b = (tb / mb[..., None]) / (onb / mnb[..., None])
        older_b = (tb / mb[..., None]) / (oob / mob[..., None])
        # z statistics: each ratio as observed over expected-at-the-comparison-rate, with its bootstrap spread
        e_new, e_old = m_c[:, None] * on / mn[:, None], m_c[:, None] * oo / mo[:, None]
        z_newer = stats.log_cc(o_c, e_new) / np.nanstd(stats.log_cc(tb, mb[..., None] * onb / mnb[..., None]),
                                                       axis=0, ddof=1)
        z_older = stats.log_cc(o_c, e_old) / np.nanstd(stats.log_cc(tb, mb[..., None] * oob / mob[..., None]),
                                                       axis=0, ddof=1)
        # same age, over the whole final history
        Oh, Mh = Th4.sum(2), Mh3.sum(2)                     # cohort x band x key, cohort x band
        o_rest_b, m_rest_b = Oh.sum(0)[None] - Oh, Mh.sum(0)[None] - Mh
        keep = m_rest_b >= MIN_COMPARATOR_MONTHS            # fixed from the point estimate
        e_sa = np.where(keep[..., None], Mh[..., None] * o_rest_b / m_rest_b[..., None], 0.0).sum(1)
        o_sa = np.where(keep[..., None], Oh, 0.0).sum(1)
        same_age = o_sa / e_sa
        o_hist = Oh.sum(1)
        dropped = np.where(o_hist > 0, 1 - o_sa / o_hist, 1 - (np.where(keep, Mh, 0).sum(1) / Mh.sum(1))[:, None])
        Thb, Mhb = stats.boot_sums(W, Th4.reshape(-1, Th4.shape[2], Th4.shape[3]), Mh3.reshape(-1, Mh3.shape[2]))
        Thb = Thb.reshape(-1, len(cohorts), len(bands), len(kk))
        Mhb = Mhb.reshape(-1, len(cohorts), len(bands))
        thr, mhr = Thb.sum(1, keepdims=True) - Thb, Mhb.sum(1, keepdims=True) - Mhb
        e_sa_b = np.where(keep[None, ..., None], Mhb[..., None] * thr / mhr[..., None], 0.0).sum(2)
        o_sa_b = np.where(keep[None, ..., None], Thb, 0.0).sum(2)
        sa_b = o_sa_b / e_sa_b
        z_sa = stats.log_cc(o_sa, e_sa) / np.nanstd(stats.log_cc(o_sa_b, e_sa_b), axis=0, ddof=1)
    acc = (Tw > 0).sum(1)                                   # cohort x key: accounts with tickets in the window
    for ci, coh in enumerate(cohorts):
        for ki, key in enumerate(kk):
            clo, chi = _ci(crude_b[:, ci, ki])
            nlo, nhi = _ci(newer_b[:, ci, ki])
            olo, ohi = _ci(older_b[:, ci, ki])
            slo, shi = _ci(sa_b[:, ci, ki])
            rows.append({'install_cohort': coh, 'issue_key': key, 'window_set': set_name, 'window_periods': len(win),
                         'tickets': o_c[ci, ki], 'machine_months': m_c[ci], 'rest_tickets': o_r[ci, ki],
                         'rest_months': m_r[ci], 'crude_ratio': crude[ci, ki], 'crude_lo': clo, 'crude_hi': chi,
                         'expected_crude': e_crude[ci, ki], 'z_crude': z_crude[ci, ki],
                         'newer_ratio': newer[ci, ki], 'newer_lo': nlo, 'newer_hi': nhi, 'z_newer': z_newer[ci, ki],
                         'older_ratio': older[ci, ki], 'older_lo': olo, 'older_hi': ohi, 'z_older': z_older[ci, ki],
                         'same_age_ratio': same_age[ci, ki], 'same_age_lo': slo, 'same_age_hi': shi,
                         'z_same_age': z_sa[ci, ki], 'expected_same_age': e_sa[ci, ki],
                         'same_age_dropped_share': dropped[ci, ki], 'accounts_with_tickets': int(acc[ci, ki])})
    return rows


def contrasts(ctx, latest_pos, months=None):
    """Cohort profile and contrasts for the window ending with `latest_pos`. Returns (DataFrame, info)."""
    P, grid, mp = ctx.params, ctx.grid, ctx.mp
    months = months or P.CONTRAST_MONTHS
    win_all = contrast_window(grid, latest_pos, months)
    if not win_all:
        return pd.DataFrame(), {'window': []}
    win_lab = contrast_window(grid, latest_pos, months, mask=ctx.label_ok)
    hist_all, hist_lab = history(grid, latest_pos), history(grid, latest_pos, mask=ctx.label_ok)
    present = set(mp.loc[mp.period_pos.isin(win_all), 'install_cohort'].astype(str))
    cohorts = [str(c) for c in mp.install_cohort.cat.categories if str(c) in present]
    order = [i for i, c in enumerate(cohorts) if c != UNKNOWN]
    bands = list(FX.AGE_LABELS)
    level_of = dict(zip(ctx.catalog.issue_key, ctx.catalog.issue_level))
    keys = list(ctx.catalog.issue_key)
    rows = []
    for set_name, win, hist, kk_all in (('all', win_all, hist_all, [k for k in keys if level_of[k] == 'all']),
                                        ('labels', win_lab, hist_lab, [k for k in keys if level_of[k] != 'all'])):
        if not win or not kk_all:
            continue
        for k0 in range(0, len(kk_all), KEY_CHUNK):        # issues in chunks: bounded memory
            rows += _chunk_rows(ctx, cohorts, order, bands, kk_all[k0:k0 + KEY_CHUNK], win, hist, set_name)
    c = pd.DataFrame(rows)
    c = c.merge(ctx.catalog[['issue_key', 'issue_level', 'issue_group', 'issue', 'order']], on='issue_key')
    c['p_crude'] = stats.two_sided_p(c.z_crude)
    with np.errstate(invalid='ignore', divide='ignore'):
        c['rate_per_100'] = 100 * c.tickets / c.machine_months
        c['rate_rest'] = 100 * c.rest_tickets / c.rest_months
    dated = [cohorts[i] for i in order]
    oldest, newest = (dated[0], dated[-1]) if dated else (None, None)
    c['position'] = np.select([c.install_cohort == UNKNOWN, c.install_cohort == newest, c.install_cohort == oldest],
                              ['undated', 'newest', 'oldest'], 'interior')

    reason = pd.Series('', index=c.index, dtype=object)

    def block(mask, why):
        reason[(reason == '') & mask] = why
    block(c.position == 'undated', 'install date unknown')
    block(c.issue.isin((FU.NO_CAT, UNMAPPED)), 'not an issue (no Category / unmapped)')
    block((c.window_set == 'labels') & (c.window_periods < max(1, len(win_all) // 2)),
          'Category labels incomplete in too many window periods')
    block(c.expected_crude.fillna(0) < P.MIN_EXPECTED, f'fewer than {P.MIN_EXPECTED:g} tickets expected')
    block(c.accounts_with_tickets < 2, 'tickets from fewer than 2 accounts')
    block(~np.isfinite(c.z_crude), 'not estimable')
    c['eligible'] = reason == ''
    for col in ('newer', 'older', 'same_age'):
        c[f'p_{col}'] = stats.two_sided_p(c[f'z_{col}'])
    hi, lo = 1 + P.MIN_CONTRAST, 1 / (1 + P.MIN_CONTRAST)
    side_hi, side_lo = 1 + P.MIN_CONTRAST / 2, 1 / (1 + P.MIN_CONTRAST / 2)
    interior, newest = c.position == 'interior', c.position == 'newest'
    sa_ok = c.same_age_dropped_share <= MAX_DROPPED
    # a candidate points the same way on every comparison it needs, by at least the practical margins
    up = np.where(interior, (c.crude_ratio >= hi) & (c.newer_ratio >= side_hi) & (c.older_ratio >= side_hi),
                  newest & sa_ok & (c.crude_ratio >= hi) & (c.same_age_ratio >= hi))
    down = np.where(interior, (c.crude_ratio <= lo) & (c.newer_ratio <= side_lo) & (c.older_ratio <= side_lo),
                    newest & sa_ok & (c.crude_ratio <= lo) & (c.same_age_ratio <= lo))
    # intersection-union test: every comparison must hold, so the call-out's p-value is the largest of theirs
    p_int = np.fmax(c.p_crude, np.fmax(c.p_newer, c.p_older))
    p_new = np.fmax(c.p_crude, c.p_same_age)
    c['p_call'] = np.where(up | down, np.where(interior, p_int, p_new), 1.0)
    q = np.full(len(c), np.nan)
    if c.eligible.any():
        q[c.eligible.to_numpy()] = FX.bh_q(c.p_call[c.eligible].fillna(1.0).to_numpy())
    c['q_call'] = q
    called = c.eligible & (c.q_call < P.Q_CUT)
    c['status'] = np.select([called & up, called & down, c.eligible],
                            ['stands_out_higher', 'stands_out_lower', 'no_clear_difference'], 'not_tested')
    c['basis'] = np.select([c.status.str.startswith('stands_out') & interior,
                            c.status.str.startswith('stands_out') & newest],
                           ['above (or below) both newer and older installs',
                            'against earlier installs at the same age'], '')
    big = c.eligible & ((c.crude_ratio >= hi) | (c.crude_ratio <= lo)) & ~c.status.str.startswith('stands_out')
    note = np.select([big & (c.position == 'oldest'), big & interior & ~(up | down),
                      big & newest & ~(up | down), big],
                     ['oldest pooled cohort: no older installs to compare with',
                      'in line with newer or older installs: may be an age effect',
                      'not different from earlier installs at the same age',
                      'could still be chance'], '')
    c['not_tested_reason'] = np.where(reason != '', reason, note)

    # profile: committed rates and intervals per cohort over the window (machines counted once)
    prof = []
    for set_name, win, kk in (('all', win_all, [k for k in keys if level_of[k] == 'all']),
                              ('labels', win_lab, [k for k in keys if level_of[k] != 'all'])):
        if not win or not kk:
            continue
        wm = window_machines(mp, win, kk)
        wm['install_cohort'] = wm.install_cohort.astype(str)
        many = RT.rates_many(wm, 'install_cohort', kk, ctx.W, ctx.clusters)
        for key in kk:
            g = many[key]
            if g.empty:
                continue
            g['issue_key'] = key
            prof.append(g[['install_cohort', 'issue_key', 'machines', 'accounts', 'ci_lo', 'ci_hi', 'ci_method',
                           'ratio_to_fleet', 'vs_fleet']])
    if prof:
        c = c.merge(pd.concat(prof, ignore_index=True), on=['install_cohort', 'issue_key'], how='left')
    age, top = _context(mp, win_all)
    c['mean_age_years'] = c.install_cohort.map(age)
    c['top_models'] = c.install_cohort.map(top)
    order_of = {str(k): i for i, k in enumerate(mp.install_cohort.cat.categories)}
    c['cohort_order'] = c.install_cohort.map(order_of)
    c = c.sort_values(['order', 'cohort_order']).reset_index(drop=True)
    info = {'window': [grid.label[p] for p in win_all],
            'window_label': grid.label[win_all[0]] if len(win_all) == 1
            else f'{grid.label[win_all[0]]} to {grid.label[win_all[-1]]}',
            'window_positions': win_all, 'window_label_positions': win_lab, 'history_periods': len(hist_all)}
    return c, info


def add_persisting(c, prev):
    if prev is None or prev.empty or c.empty:
        c['persisting'] = False
        return c
    p = prev.set_index(['install_cohort', 'issue_key']).status
    prev_status = [p.get(k, '') for k in zip(c.install_cohort, c.issue_key)]
    c['persisting'] = c.status.str.startswith('stands_out') & (pd.Series(prev_status, index=c.index) == c.status)
    return c


def sentence(r, window_label):
    """Executive wording for one cohort x issue."""
    text = (f'{r.issue}, {r.install_cohort} installs: {r.rate_per_100:.2f} per 100 installed machine-months over '
            f'{window_label}, {r.crude_ratio:.1f}x the rest of the fleet')
    if r.position == 'newest':
        text += f' and {r.same_age_ratio:.1f}x earlier installs at the same age'
    elif np.isfinite(r.newer_ratio) and np.isfinite(r.older_ratio):
        text += f' ({r.newer_ratio:.1f}x newer installs, {r.older_ratio:.1f}x older installs)'
    if getattr(r, 'persisting', False):
        text += '; it stood out in the previous window too'
    return text + '.'
