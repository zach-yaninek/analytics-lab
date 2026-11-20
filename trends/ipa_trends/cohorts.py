"""Install cohorts: how machines installed in different date ranges compare. This is the view that surfaced the
Touchscreen peak (2022-23 installs at 1.54 per 100 machine-months, 3.9 times the 2024-26 rate).

For each install cohort x issue over the contrast window (the last CONTRAST_MONTHS of final periods up to the
latest one):

  profile         rate per 100 installed machine-months with the committed interval (copied group_rates)
  crude ratio     the cohort's rate over the rest of the fleet's rate
  same-age ratio  O / sum_b M(cohort, band) x rate(other cohorts, band), with b the age band of each machine in each
                  period: the cohort against machines of the same age from other cohorts. Bands where the other
                  cohorts have fewer than 100 machine-months are left out of both sides; the ratio is not estimable
                  when that drops more than 25% of the cohort's tickets.

Both ratios get paired account-bootstrap intervals and Benjamini-Hochberg q-values over the cohort x issue family.
A cohort 'stands out' only when both ratios are at least 1 + MIN_CONTRAST (or at most 1 / (1 + MIN_CONTRAST)) with
q < Q_CUT each, at least MIN_EXPECTED tickets are expected, and the window's labels are complete. Requiring both
guards against reading an age effect as a cohort effect, and the reverse. 'persisting' marks a cohort that also
stood out in the window ending one period earlier.
"""
import warnings

import numpy as np
import pandas as pd

from . import stats
from .definitions import association_copy as A
from .definitions import fleet_exposure_copy as FX
from .definitions import followups_copy as FU
from .inputs import UNKNOWN, UNMAPPED

MIN_COMPARATOR_MONTHS = 100
KEY_CHUNK = 8
MAX_DROPPED = 0.25
NOT_CALLED = (UNKNOWN,)


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


def contrast_window(grid, latest_pos, months, mask=None):
    """Final periods that start within the `months` before the latest period ends (latest included)."""
    if latest_pos is None:
        return []
    start = grid.period_end[latest_pos] - pd.DateOffset(months=int(months))
    ok = (grid.index <= latest_pos) & (grid.status == 'final') & (grid.period_start >= start)
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


def _context(mp, positions, cohorts):
    sub = mp[mp.period_pos.isin(positions) & (mp.months > 0)]
    age = sub.groupby('install_cohort', observed=True).apply(
        lambda g: np.average(g.age_years, weights=g.months) if g.months.sum() > 0 else np.nan, include_groups=False)
    top = {}
    for c, g in sub.groupby('install_cohort', observed=True):
        s = g.groupby('model').months.sum().sort_values(ascending=False)
        share = s / s.sum()
        top[str(c)] = ', '.join(f'{m} {100 * v:.0f}%' for m, v in share.head(3).items())
    return {str(k): float(v) for k, v in age.items()}, top


def contrasts(ctx, latest_pos, months=None):
    """Cohort profile and contrasts for the window ending with `latest_pos`. Returns (DataFrame, info)."""
    P, grid, mp = ctx.params, ctx.grid, ctx.mp
    months = months or P.CONTRAST_MONTHS
    win_all = contrast_window(grid, latest_pos, months)
    win_lab = contrast_window(grid, latest_pos, months, mask=ctx.label_ok)
    if not win_all:
        return pd.DataFrame(), {'window': []}
    cohorts = [c for c in mp.install_cohort.cat.categories
               if (mp.loc[mp.period_pos.isin(win_all), 'install_cohort'] == c).any()]
    bands = list(FX.AGE_LABELS)
    keys = list(ctx.catalog.issue_key)
    level_of = dict(zip(ctx.catalog.issue_key, ctx.catalog.issue_level))
    rows = []
    for set_name, win, kk_all in (('all', win_all, [k for k in keys if level_of[k] == 'all']),
                              ('labels', win_lab, [k for k in keys if level_of[k] != 'all'])):
        if not win or not kk_all:
            continue
        sub = mp[mp.period_pos.isin(win)].copy()
        sub['_cb'] = [f'{c}\x1f{b}' for c, b in zip(sub.install_cohort.astype(str), sub.age_band.astype(str))]
        combos = [f'{c}\x1f{b}' for c in cohorts for b in bands]
        for k0 in range(0, len(kk_all), KEY_CHUNK):           # issues in chunks: bounded memory
            kk = kk_all[k0:k0 + KEY_CHUNK]
            T, M = stats.cluster_arrays(sub, '_cb', kk, win, ctx.clusters, combos)
            C, B, K, NC = len(cohorts), len(bands), len(kk), len(ctx.clusters)
            T4, M3 = T.reshape(C, B, NC, K), M.reshape(C, B, NC)
            O = T4.sum(2)                     # C x B x K
            Mo = M3.sum(2)                    # C x B
            Ob, Mb = O.sum(0), Mo.sum(0)      # B x K, B
            O_rest, M_rest = Ob[None] - O, Mb[None] - Mo
            keep = M_rest >= MIN_COMPARATOR_MONTHS          # C x B, fixed from the point estimate
            Tb, Mbb = stats.boot_sums(ctx.W, T, M)          # draws x (C*B) x K, draws x (C*B)
            Tb, Mbb = Tb.reshape(-1, C, B, K), Mbb.reshape(-1, C, B)
            with np.errstate(invalid='ignore', divide='ignore'):
                o_c, m_c = O.sum(1), Mo.sum(1)                              # C x K, C
                o_r, m_r = O_rest.sum(1), M_rest.sum(1)
                crude = (o_c / m_c[:, None]) / (o_r / m_r[:, None])
                e_crude = m_c[:, None] * o_r / m_r[:, None]
                rate_rb = O_rest / M_rest[:, :, None]                       # C x B x K
                e_sa = np.where(keep[:, :, None], Mo[:, :, None] * rate_rb, 0.0).sum(1)
                o_sa = np.where(keep[:, :, None], O, 0.0).sum(1)
                same_age = o_sa / e_sa
                dropped = np.where(o_c > 0, 1 - o_sa / o_c,
                                   1 - (np.where(keep, Mo, 0).sum(1) / m_c)[:, None])
                # bootstrap
                tb_c, mb_c = Tb.sum(2), Mbb.sum(2)                           # d x C x K, d x C
                tb_tot, mb_tot = Tb.sum(1), Mbb.sum(1)                       # d x B x K, d x B
                tb_r = tb_tot[:, None] - Tb                                  # d x C x B x K
                mb_r = mb_tot[:, None] - Mbb                                 # d x C x B
                crude_b = (tb_c / mb_c[:, :, None]) / (tb_r.sum(2) / mb_r.sum(2)[:, :, None])
                log_crude_b = stats.log_cc(tb_c, mb_c[:, :, None] * tb_r.sum(2) / mb_r.sum(2)[:, :, None])
                e_sa_b = np.where(keep[None, :, :, None], Mbb[..., None] * tb_r / mb_r[..., None], 0.0).sum(2)
                o_sa_b = np.where(keep[None, :, :, None], Tb, 0.0).sum(2)
                sa_b = o_sa_b / e_sa_b
                log_sa_b = stats.log_cc(o_sa_b, e_sa_b)
                sd_crude = np.nanstd(log_crude_b, axis=0, ddof=1)
                sd_sa = np.nanstd(log_sa_b, axis=0, ddof=1)
                # degenerate cells (no exposure, no spread) give NaN here and are reported as not estimable
                z_crude = stats.log_cc(o_c, e_crude) / sd_crude
                z_sa = stats.log_cc(o_sa, e_sa) / sd_sa
            acc = (T4.sum(1) > 0).sum(1)                                    # C x K accounts with tickets
            for ci, coh in enumerate(cohorts):
                for ki, key in enumerate(kk):
                    clo, chi, _ = A.ci(crude_b[:, ci, ki])
                    slo, shi, _ = A.ci(sa_b[:, ci, ki])
                    rows.append({'install_cohort': coh, 'issue_key': key, 'window_set': set_name,
                                 'window_periods': len(win), 'tickets': o_c[ci, ki], 'machine_months': m_c[ci],
                                 'rest_tickets': o_r[ci, ki], 'rest_months': m_r[ci], 'crude_ratio': crude[ci, ki],
                                 'crude_lo': clo, 'crude_hi': chi, 'expected_crude': e_crude[ci, ki],
                                 'z_crude': z_crude[ci, ki], 'same_age_ratio': same_age[ci, ki], 'same_age_lo': slo,
                                 'same_age_hi': shi, 'expected_same_age': e_sa[ci, ki], 'z_same_age': z_sa[ci, ki],
                                 'same_age_dropped_share': dropped[ci, ki], 'accounts_with_tickets': int(acc[ci, ki])})
    c = pd.DataFrame(rows)
    c = c.merge(ctx.catalog[['issue_key', 'issue_level', 'issue_group', 'issue', 'order']], on='issue_key')
    c['p_crude'] = stats.two_sided_p(c.z_crude)
    c['p_same_age'] = stats.two_sided_p(c.z_same_age)
    with np.errstate(invalid='ignore', divide='ignore'):
        c['rate_per_100'] = 100 * c.tickets / c.machine_months
        c['rate_rest'] = 100 * c.rest_tickets / c.rest_months

    reason = pd.Series('', index=c.index, dtype=object)

    def block(mask, why):
        reason[(reason == '') & mask] = why
    block(c.install_cohort.isin(NOT_CALLED), 'install date unknown')
    block(c.issue.isin((FU.NO_CAT, UNMAPPED)), 'not an issue (no Category / unmapped)')
    block((c.window_set == 'labels') & (c.window_periods < max(1, len(win_all) // 2)),
          'Category labels incomplete in too many window periods')
    block(c.expected_crude.fillna(0) < P.MIN_EXPECTED, f'fewer than {P.MIN_EXPECTED:g} tickets expected')
    block(c.accounts_with_tickets < 2, 'tickets from fewer than 2 accounts')
    block(c.same_age_dropped_share > MAX_DROPPED, 'too few machines of the same age in other cohorts')
    block(~np.isfinite(c.z_crude) | ~np.isfinite(c.z_same_age), 'not estimable')
    c['eligible'] = reason == ''
    c['not_tested_reason'] = reason
    for col in ('crude', 'same_age'):
        q = np.full(len(c), np.nan)
        if c.eligible.any():
            q[c.eligible.to_numpy()] = FX.bh_q(c[f'p_{col}'][c.eligible].to_numpy())
        c[f'q_{col}'] = q
    hi, lo = 1 + P.MIN_CONTRAST, 1 / (1 + P.MIN_CONTRAST)
    both = c.eligible & (c.q_crude < P.Q_CUT) & (c.q_same_age < P.Q_CUT)
    c['status'] = np.select([both & (c.crude_ratio >= hi) & (c.same_age_ratio >= hi),
                             both & (c.crude_ratio <= lo) & (c.same_age_ratio <= lo), c.eligible],
                            ['stands_out_higher', 'stands_out_lower', 'no_clear_difference'], 'not_tested')

    # profile: committed rates and intervals per cohort over the window (machines counted once)
    prof = []
    for set_name, win, kk in (('all', win_all, [k for k in keys if level_of[k] == 'all']),
                              ('labels', win_lab, [k for k in keys if level_of[k] != 'all'])):
        if not win or not kk:
            continue
        wm = window_machines(mp, win, kk)
        wm['install_cohort'] = wm.install_cohort.astype(str)
        for key in kk:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                g, _ = FX.group_rates(wm, 'install_cohort', ctx.W, ctx.clusters, tickets=key, months='months')
            g = g.rename(columns={'months': 'machine_months_profile'})
            g['issue_key'] = key
            prof.append(g[['install_cohort', 'issue_key', 'machines', 'accounts', 'ci_lo', 'ci_hi', 'ci_method',
                           'ratio_to_fleet', 'vs_fleet']])
    prof = pd.concat(prof, ignore_index=True) if prof else pd.DataFrame()
    c['install_cohort'] = c.install_cohort.astype(str)
    c = c.merge(prof, on=['install_cohort', 'issue_key'], how='left')
    age, top = _context(mp, win_all, cohorts)
    c['mean_age_years'] = c.install_cohort.map(age)
    c['top_models'] = c.install_cohort.map(top)
    order = {str(k): i for i, k in enumerate(mp.install_cohort.cat.categories)}
    c['cohort_order'] = c.install_cohort.map(order)
    c = c.sort_values(['order', 'cohort_order']).reset_index(drop=True)
    info = {'window': [grid.label[p] for p in win_all], 'window_label': f'{grid.label[win_all[0]]} to '
            f'{grid.label[win_all[-1]]}' if len(win_all) > 1 else grid.label[win_all[0]],
            'window_positions': win_all, 'window_label_positions': win_lab}
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
    pct = 100 * (r.crude_ratio - 1)
    word = 'above' if pct >= 0 else 'below'
    text = (f'{r.issue}, {r.install_cohort} installs: {r.rate_per_100:.2f} per 100 installed machine-months over '
            f'{window_label}, {r.crude_ratio:.1f}x the rest of the fleet and {r.same_age_ratio:.1f}x machines of the '
            f'same age in other cohorts')
    if r.persisting:
        text += '; it stood out in the previous window too'
    return text + '.'
