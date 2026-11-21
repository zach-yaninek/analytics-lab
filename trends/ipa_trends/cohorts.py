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

All ratios get paired account-bootstrap intervals and p-values.

Each cohort x issue has a position, chosen per issue. The 'newest' cohort is the newest testable one: the newest
dated cohort (other than the oldest) with at least MIN_EXPECTED tickets expected in the window. Dated cohorts
installed after it are 'too_new' (usually because they are still filling up: machines were still being installed
during the window): they are shown but never compared or called out. Comparing the cohort before them with a
near-empty 'newer installs' group would hide a real difference for as long as the newest cohort fills up. For the
same reason, an earlier cohort whose newer installs would expect fewer than NEWER_SIDE_MIN_EXPECTED (40) tickets at the
rest of the fleet's rate is also 'newest', once the history is long enough for the same-age ratio (24 months): a
newer-installs comparison that small confirms only very large differences, and it stays that small for a while after
the newest cohort becomes testable. With a shorter history such a cohort stays interior, because its same-age ratio
then leans on the neighbouring cohorts, which may share its problem. The oldest, pooled cohort ('Before ...')
is 'oldest' and 'Unknown' is 'undated': both are shown but never called out.
The cohorts in between are 'interior'. When no cohort after the oldest is testable for an issue, the newest dated
cohort is 'newest' and none is 'too_new'.

A cohort 'stands out' (higher) when at least MIN_EXPECTED tickets are expected, the window's labels are complete, and:

  - an interior cohort is at least 1 + MIN_CONTRAST times the rest of the fleet and at least 1 + MIN_CONTRAST / 2
    times both the newer and the older installs: a peak in the install-date profile. A peak rules out an age effect
    that rises or falls steadily with machine age (a cohort in the middle of such a trend lies between its newer and
    older neighbours), but not a wear-out window: rates that are high only at some ages make the cohorts at those
    ages peak. So when the final history behind the window spans at least SAME_AGE_HISTORY_MONTHS (24) months and
    the same-age ratio is estimable, an interior cohort must also be at least 1 + MIN_CONTRAST / 2 times machines of
    the same age in other cohorts. With a shorter history, machines of the same age come mostly from the
    neighbouring install years (docs/10) and that check is skipped: the basis says so. Two neighbouring cohorts can
    both stand out, since each is compared with all newer and all older installs;
  - the newest cohort, which has no testable newer installs, is at least 1 + MIN_CONTRAST times both the rest of the
    fleet and machines of the same age in other cohorts;
  - and every one of those comparisons is beyond chance together: the call-out's p-value is the largest of their
    p-values (an intersection-union test), and one Benjamini-Hochberg correction runs over every eligible cohort x
    issue cell (q below Q_CUT).

'Lower' is the mirror image. 'persisting' marks a cohort that also stood out in the window ending one period
earlier. Each row carries the window label of its own set of periods: all-ticket rows use every final period of the
window, issue-level rows only those with complete Category labels (and the same-age history likewise).
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
SAME_AGE_HISTORY_MONTHS = 24        # final history an interior cohort's same-age check needs
NEWER_SIDE_MIN_EXPECTED = 40        # newer installs expecting fewer tickets are too few for the newer-installs
                                    # comparison: such a cohort is compared like the newest one


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


def history_months(grid, positions):
    """Whole months from the start of the first period at `positions` to the end of the last (0 when empty)."""
    if not positions:
        return 0
    a, b = grid.period_start[positions[0]], grid.period_end[positions[-1]]
    return int((b.year - a.year) * 12 + b.month - a.month - (b.day < a.day))


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else f'{", ".join(items[:-1])} and {items[-1]}'


def window_label(grid, positions, full=()):
    """'<first> to <last>' (or one label) for the periods at `positions`. Periods of `full` (the window of every final
    period) that fall between the first and the last but are not in `positions` (issue-level windows leave out periods
    with incomplete Category labels) are named: '<first> to <last> except <label> (incomplete Category labels)'."""
    if not positions:
        return ''
    first, last = grid.label[positions[0]], grid.label[positions[-1]]
    text = first if len(positions) == 1 else f'{first} to {last}'
    gaps = [grid.label[p] for p in full if positions[0] < p < positions[-1] and p not in set(positions)]
    if gaps:
        text += f' except {_join(gaps)} (incomplete Category labels)'
    return text


def positions(c, dated, min_expected, newer_min=NEWER_SIDE_MIN_EXPECTED, same_age_ok=None):
    """Position of every cohort x issue row, chosen per issue: 'undated' (Unknown), 'oldest' (the first dated cohort,
    pooled), 'newest' (the newest testable cohort: the newest dated cohort after the oldest with at least
    `min_expected` tickets expected, and any earlier testable cohort whose newer installs would expect fewer than
    `newer_min` tickets at the rest of the fleet's rate, too few for a reliable newer-installs comparison, provided its
    same-age ratio can be trusted (`same_age_ok`: 24 months of history; without it the cohort stays interior, as the
    same-age ratio of a short history leans on the neighbouring cohorts)), 'too_new' (dated cohorts
    installed after the newest testable one) or 'interior'. When no cohort after the oldest is testable for an issue,
    the newest dated cohort is 'newest' and none is 'too_new'.

    c: rows with install_cohort, issue_key and expected_crude; dated: the dated cohorts in install order."""
    rank = c.install_cohort.map({k: j for j, k in enumerate(dated)}).astype(float)
    testable = (rank > 0) & (c.expected_crude.fillna(0) >= min_expected)
    newest = rank.where(testable).groupby(c.issue_key).transform('max').fillna(len(dated) - 1)
    # a cohort whose newer installs are too few for the newer-installs comparison is compared like the newest one
    thin = pd.Series(False, index=c.index)
    if 'expected_newer_side' in c:
        thin = testable & (rank < newest) & (c.expected_newer_side.fillna(0) < newer_min)
        if same_age_ok is not None:
            thin &= pd.Series(same_age_ok, index=c.index).fillna(False).astype(bool)
    return pd.Series(np.select([rank.isna(), rank == 0, (rank == newest) | thin, rank > newest],
                               ['undated', 'oldest', 'newest', 'too_new'], 'interior'), index=c.index, dtype=object)


def call_rule(c, min_contrast, same_age_check):
    """The call-out rule for every row (see the module docstring). Returns (up, down, p_call, age_like) as arrays:
    candidate higher / lower (by the practical margins), the intersection-union p-value of the comparisons the
    candidate needs (1 for non-candidates), and interior rows that peak against newer and older installs but are in
    line with machines of the same age in other cohorts (only the same-age condition fails).

    c: rows with position, crude / newer / older / same_age ratios, their p-values and same_age_dropped_share;
    same_age_check: per row, whether an interior row must pass the same-age condition (history long enough and the
    same-age ratio estimable). A missing p-value counts as 1."""
    hi, lo = 1 + min_contrast, 1 / (1 + min_contrast)
    side_hi, side_lo = 1 + min_contrast / 2, 1 / (1 + min_contrast / 2)
    interior, newest = (c.position == 'interior').to_numpy(), (c.position == 'newest').to_numpy()
    check = interior & np.asarray(same_age_check, bool)
    sa_ok = (c.same_age_dropped_share <= MAX_DROPPED).to_numpy()
    crude, newer, older, same = (c[f'{k}_ratio'].to_numpy(float) for k in ('crude', 'newer', 'older', 'same_age'))
    p = {k: c[f'p_{k}'].fillna(1.0).to_numpy(float) for k in ('crude', 'newer', 'older', 'same_age')}
    with np.errstate(invalid='ignore'):
        peak_up = (crude >= hi) & (newer >= side_hi) & (older >= side_hi)
        peak_down = (crude <= lo) & (newer <= side_lo) & (older <= side_lo)
        sa_up, sa_down = same >= side_hi, same <= side_lo
        up = np.where(interior, peak_up & (~check | sa_up), newest & sa_ok & (crude >= hi) & (same >= hi))
        down = np.where(interior, peak_down & (~check | sa_down), newest & sa_ok & (crude <= lo) & (same <= lo))
    p_int = np.maximum(p['crude'], np.maximum(p['newer'], p['older']))
    p_int = np.where(check, np.maximum(p_int, p['same_age']), p_int)
    p_new = np.maximum(p['crude'], p['same_age'])
    p_call = np.where(up | down, np.where(interior, p_int, p_new), 1.0)
    age_like = check & ((peak_up & ~sa_up) | (peak_down & ~sa_down))
    return up, down, p_call, age_like


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
        # the newer installs' tickets if they had the rest of the fleet's rate: how much a newer-installs test can see
        e_newer_side = mn[:, None] * o_r / m_r[:, None]
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
                         'expected_newer_side': e_newer_side[ci, ki],
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
    # each row carries the window of its own set of periods, and whether its same-age history is long enough
    sets = {'all': (win_all, hist_all), 'labels': (win_lab, hist_lab)}
    labels = {s: window_label(grid, w, win_all) for s, (w, _) in sets.items()}
    span = {s: history_months(grid, h) for s, (_, h) in sets.items()}
    long_history = {s: m >= SAME_AGE_HISTORY_MONTHS for s, m in span.items()}
    c['window_label'] = c.window_set.map(labels)
    c['p_crude'] = stats.two_sided_p(c.z_crude)
    with np.errstate(invalid='ignore', divide='ignore'):
        c['rate_per_100'] = 100 * c.tickets / c.machine_months
        c['rate_rest'] = 100 * c.rest_tickets / c.rest_months
    dated = [cohorts[i] for i in order]
    # the newer-side fallback needs a same-age ratio worth trusting: 24 months of history, few tickets dropped
    trusted = c.window_set.map(long_history).astype(bool) & (c.same_age_dropped_share <= MAX_DROPPED)
    c['position'] = positions(c, dated, P.MIN_EXPECTED, same_age_ok=trusted)
    # cohorts with machines installed during the window are still filling up
    pop = getattr(ctx, 'pop', None)
    filling = {s: (set(dated) if pop is None or not w else
                   set(pop.loc[pop.install_date >= grid.period_start[w[0]], 'install_cohort'].astype(str)))
               for s, (w, _) in sets.items()}

    reason = pd.Series('', index=c.index, dtype=object)

    def block(mask, why):
        m = (reason == '') & mask
        reason[m] = why[m] if isinstance(why, pd.Series) else why
    block(c.position == 'undated', 'install date unknown')
    block(c.issue.isin((FU.NO_CAT, UNMAPPED)), 'not an issue (no Category / unmapped)')
    block((c.window_set == 'labels') & (c.window_periods < max(1, len(win_all) // 2)),
          'Category labels incomplete in too many window periods')
    block((c.position == 'too_new') & pd.Series([k in filling[s] for k, s in zip(c.install_cohort, c.window_set)],
                                                index=c.index),
          c.expected_crude.map(lambda e: f'too new: still filling up ({np.floor(e * 10 + 1e-9) / 10:.1f} expected '
                                         'tickets)' if _finite(e) else 'too new: still filling up'))  # 9.98 -> 9.9
    block(c.expected_crude.fillna(0) < P.MIN_EXPECTED, f'fewer than {P.MIN_EXPECTED:g} tickets expected')
    block(c.accounts_with_tickets < 2, 'tickets from fewer than 2 accounts')
    block(~np.isfinite(c.z_crude), 'not estimable')
    c['eligible'] = reason == ''
    for col in ('newer', 'older', 'same_age'):
        c[f'p_{col}'] = stats.two_sided_p(c[f'z_{col}'])
    hi, lo = 1 + P.MIN_CONTRAST, 1 / (1 + P.MIN_CONTRAST)
    interior, newest = c.position == 'interior', c.position == 'newest'
    sa_ok = c.same_age_dropped_share <= MAX_DROPPED
    long_enough = c.window_set.map(long_history).astype(bool)
    # the same-age comparison is part of the rule for the newest cohort, and for an interior one with enough history
    c['same_age_check'] = newest | (interior & long_enough & sa_ok)
    up, down, p_call, age_like = call_rule(c, P.MIN_CONTRAST, c.same_age_check)
    c['p_call'] = p_call
    q = np.full(len(c), np.nan)
    if c.eligible.any():
        q[c.eligible.to_numpy()] = FX.bh_q(c.p_call[c.eligible].fillna(1.0).to_numpy())
    c['q_call'] = q
    called = c.eligible & (c.q_call < P.Q_CUT)
    c['status'] = np.select([called & up, called & down, c.eligible],
                            ['stands_out_higher', 'stands_out_lower', 'no_clear_difference'], 'not_tested')
    stands = c.status.str.startswith('stands_out')
    side = pd.Series(np.where(c.status == 'stands_out_lower', 'below', 'above'), index=c.index)
    short = c.window_set.map(span).map(
        lambda m: f'; the same-age check needs {SAME_AGE_HISTORY_MONTHS} months of final history ({m} available)')
    c['basis'] = np.select(
        [stands & interior & c.same_age_check, stands & interior & ~long_enough, stands & interior, stands & newest],
        [side + ' both newer and older installs and other cohorts at the same age',
         side + ' both newer and older installs' + short,
         side + ' both newer and older installs; the same-age ratio could not be estimated',
         np.where(c.get('expected_newer_side', pd.Series(np.inf, index=c.index)).fillna(np.inf) < NEWER_SIDE_MIN_EXPECTED,
                  'newer installs too few to compare with: ', 'newest testable cohort: ')
         + side + ' the rest of the fleet and other cohorts at the same age'], '')
    big = c.eligible & ((c.crude_ratio >= hi) | (c.crude_ratio <= lo)) & ~stands
    note = np.select([big & (c.position == 'oldest'), big & age_like & (c.crude_ratio >= hi), big & age_like,
                      big & interior & ~(up | down), big & newest & ~sa_ok, big & newest & ~(up | down), big],
                     ['oldest pooled cohort: no older installs to compare with',
                      'in line with machines of the same age in other cohorts: may be an age (wear-out) effect',
                      'in line with machines of the same age in other cohorts: may be an age effect',
                      'in line with newer or older installs: may be an age effect',
                      'no same-age comparison: too few machines of the same age in other cohorts',
                      'in line with machines of the same age in other cohorts: may be an age effect',
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
    info = {'window': [grid.label[p] for p in win_all], 'window_label': labels['all'],
            'window_label_issue_level': labels['labels'],
            'window_positions': win_all, 'window_label_positions': win_lab, 'history_periods': len(hist_all),
            'history_months': span, 'same_age_check_interior': long_history}
    return c, info


def add_persisting(c, prev):
    if prev is None or prev.empty or c.empty:
        c['persisting'] = False
        return c
    p = prev.set_index(['install_cohort', 'issue_key']).status
    prev_status = [p.get(k, '') for k in zip(c.install_cohort, c.issue_key)]
    c['persisting'] = c.status.str.startswith('stands_out') & (pd.Series(prev_status, index=c.index) == c.status)
    return c


def _phrase(label):
    """'2022 installs', 'installs before 2016', 'installs from Jan 2025', 'installs with no install date'."""
    s = str(label)
    if s.startswith('Before '):
        return f'installs before {s[7:]}'
    if s.startswith('From '):
        return f'installs from {s[5:]}'
    return 'installs with no install date' if s == UNKNOWN else f'{s} installs'


def _finite(v):
    try:
        return bool(np.isfinite(float(v)))
    except (TypeError, ValueError):
        return False


def sentence(r, window_label=None):
    """Executive wording for one cohort x issue, over the row's own window (`r.window_label`; `window_label` is only
    the fallback for a row without one). A row that was not tested states its rate and why, with no ratios; a ratio
    is written only when it is finite."""
    window = getattr(r, 'window_label', None)
    window = window if isinstance(window, str) and window else (window_label or 'the cohort window')
    rate = (f'{r.rate_per_100:.2f} per 100 installed machine-months' if _finite(r.rate_per_100)
            else 'no installed machine-months')
    text = f'{r.issue}, {_phrase(r.install_cohort)}: {rate} over {window}'
    if getattr(r, 'status', '') == 'not_tested':
        why = getattr(r, 'not_tested_reason', '')
        return f'{text}; not tested ({why if isinstance(why, str) and why.strip() else "not estimable"}).'
    if _finite(r.crude_ratio):
        text += f', {r.crude_ratio:.1f}x the rest of the fleet'
    same = (f'{r.same_age_ratio:.1f}x other cohorts at the same age over the whole history'
            if _finite(r.same_age_ratio) else '')
    if r.position == 'newest':
        if same:
            text += f' and {same}'
    elif _finite(r.newer_ratio) and _finite(r.older_ratio):
        sides = [f'{r.newer_ratio:.1f}x newer installs', f'{r.older_ratio:.1f}x older installs']
        if same and getattr(r, 'same_age_check', False):
            sides.append(same)
        text += f' ({", ".join(sides)})'
    if getattr(r, 'persisting', False):
        text += '; it stood out in the previous window too'
    return text + '.'
