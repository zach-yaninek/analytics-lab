"""Statistics shared by the comparison and cohort modules (numpy and math only, no scipy).

  cluster sums      tickets and machine-months per (stratum, account) so that one bootstrap draw (a row of the
                    copied boot_weights matrix) reweights both the latest period and the baseline: the paired account
                    bootstrap.
  day factors       weekends and US federal holidays get their own ticket weight, estimated from the baseline's fleet
                    tickets, so a period with more business days is not mistaken for a rise.
  tau^2             the between-period variance of log rates beyond sampling noise: DerSimonian-Laird pooled over the
                    cells of an issue-level family, with a floor. Residuals are winsorised at +-3 total standard
                    deviations (sampling plus between-period, starting from the unwinsorised estimate), so a
                    one-period spike in a single cell cannot inflate it while ordinary period-to-period variation in
                    large cells is kept; a spike shared by many cells of the family is only partly pulled in and
                    raises tau^2 (more conservative). A cell with no ticket in its first or last period (a Category
                    that appeared or vanished)
                    is a broken series and is left out.
"""
import math

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

Z95 = 1.959964
Z_POWER80 = 2.801585       # 1.959964 + 0.841621: 80% power, two-sided 5%
WINSOR = 3.0
WINSOR_PASSES = 2          # winsorise, re-estimate tau^2, and winsorise again
TAU2_UNESTIMABLE = 0.005   # conservative fallback (about the calendar-day month-to-month spread of fleet counts)
MIN_CELL_EXPECTED_TAU = 5


def cluster_arrays(mp, col, keys, positions, clusters, levels):
    """T[level, cluster, key] tickets and M[level, cluster] machine-months over the given periods."""
    sub = mp[mp.period_pos.isin(list(positions))]
    li = sub[col].astype(object).map({v: i for i, v in enumerate(levels)})
    ok = li.notna().to_numpy()
    li = li[ok].astype(int).to_numpy()
    ci = sub.customer.map({c: i for i, c in enumerate(clusters)}).to_numpy()[ok]
    T = np.zeros((len(levels), len(clusters), len(keys)))
    M = np.zeros((len(levels), len(clusters)))
    if len(li):
        np.add.at(T, (li, ci), sub[keys].to_numpy(float)[ok])
        np.add.at(M, (li, ci), sub.months.to_numpy(float)[ok])
    return T, M


def boot_sums(W, T, M, chunk=8):
    """Bootstrap totals: Tb[b, level, key] = sum_c W[b, c] T[level, c, key], Mb[b, level]."""
    Mb = W @ M.T
    Tb = np.empty((W.shape[0], T.shape[0], T.shape[2]))
    for k0 in range(0, T.shape[2], chunk):
        Tb[:, :, k0:k0 + chunk] = np.einsum('bc,lck->blk', W, T[:, :, k0:k0 + chunk], optimize=True)
    return Tb, Mb


def two_sided_p(z):
    z = np.asarray(z, float)
    return np.array([math.erfc(abs(v) / math.sqrt(2)) if np.isfinite(v) else np.nan for v in z.ravel()]) \
        .reshape(z.shape)


def log_cc(o, e):
    """Continuity-corrected log ratio log((O + 1/2) / (E + 1/2)), defined when O = 0."""
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.log((np.asarray(o, float) + 0.5) / (np.asarray(e, float) + 0.5))


# ------------------------------------------------------------------------------------------------ day factors
def day_types(start, end):
    """Business days (Mon-Fri, not a US federal holiday) and other days in [start, end)."""
    days = pd.date_range(start, end - pd.Timedelta(days=1), freq='D')
    hol = USFederalHolidayCalendar().holidays(start, end)
    business = (days.dayofweek < 5) & ~days.isin(hol)
    return days, business


def day_factors(t, grid, positions):
    """Weight of a non-business day relative to a business day, estimated from the fleet's tickets in the given
    (baseline) periods, and each period's average day weight f_p = (B_p + w N_p) / (B_p + N_p).

    Returns (f as an array over all periods, w, facts)."""
    lo, hi = grid.covered_start.min(), grid.covered_end.max()
    days, business = day_types(lo, hi)
    is_bus = pd.Series(business, index=days)
    tb = tn = db = dn = 0.0
    for p in positions:
        a, b = grid.covered_start[p], grid.covered_end[p]
        sel = is_bus[(is_bus.index >= a) & (is_bus.index < b)]
        db += sel.sum()
        dn += (~sel).sum()
        tt = t[(t.ts >= a) & (t.ts < b)]
        bus_t = is_bus.reindex(tt.ts.dt.normalize()).to_numpy()
        tb += np.nansum(bus_t == True)       # noqa: E712 - numpy bool array
        tn += np.nansum(bus_t == False)      # noqa: E712
    w = 1.0
    if db > 0 and dn > 0 and tb > 0:
        w = float(np.clip((tn / dn) / (tb / db), 0.02, 1.5))
    f = []
    for p in range(len(grid)):
        sel = is_bus[(is_bus.index >= grid.covered_start[p]) & (is_bus.index < grid.covered_end[p])]
        f.append((sel.sum() + w * (~sel).sum()) / max(len(sel), 1))
    return np.array(f, float), w, {'non_business_day_weight': w, 'baseline_business_days': int(db),
                                   'baseline_other_days': int(dn)}


# ------------------------------------------------------------------------------------------------ tau^2
def _dl_sums(ys, vs, tau2=None):
    """DerSimonian-Laird moment sums (Q, C, df) over cells. With tau2, residuals beyond +-WINSOR total standard
    deviations sqrt(v + tau2) are first pulled in to +-WINSOR."""
    Q = C = df = 0.0
    for y, v in zip(ys, vs):
        y, v = np.asarray(y, float), np.asarray(v, float)
        w = 1 / v
        ybar = np.sum(w * y) / np.sum(w)
        if tau2 is not None:
            s = np.sqrt(v + tau2)
            y = ybar + np.clip((y - ybar) / s, -WINSOR, WINSOR) * s
            ybar = np.sum(w * y) / np.sum(w)
        Q += float(np.sum(w * (y - ybar) ** 2))
        C += float(np.sum(w) - np.sum(w ** 2) / np.sum(w))
        df += len(y) - 1
    return Q, C, df


def dl_pool(ys, vs, passes=WINSOR_PASSES):
    """DerSimonian-Laird moment sums over cells: ys, vs are lists of arrays (log rates and their sampling
    variances per period).

    Residuals are winsorised at +-3 total standard deviations sqrt(v + tau^2): tau^2 starts at the unwinsorised
    estimate and is re-estimated after each winsorising pass (`passes` of them). Scaling by the sampling variance
    alone would clip ordinary between-period variation in large cells (where v is small) and bias tau^2 low; a
    one-period spike in one cell still lies far outside the pooled total scale and is pulled in.
    Returns (Q, C, df) of the last pass; tau^2 = (Q - df) / C."""
    Q, C, df = _dl_sums(ys, vs)
    for _ in range(int(passes)):
        if df <= 0 or C <= 0:
            break
        Q, C, df = _dl_sums(ys, vs, max(0.0, (Q - df) / C))
    return Q, C, df


def tau2_dl(O, E, deff, floor):
    """Between-period variance of log rates, pooled over cells.

    O, E: lists of arrays (one per cell) of per-period observed and expected counts (E sums to O within a cell);
    deff: per-cell design effect (>= 1) for clustering within accounts; periods in time order. Cells qualify when
    there are 3+ periods, every period expects at least 5 tickets, and the first and the last period each have at
    least one. No ticket at either end where 5 or more are expected means the Category appeared or vanished during
    the history (a split or renamed Category): a broken series, not between-period variation, and a split breaks
    many cells at once, enough to swamp the winsorising. Fewer than 5 pooled degrees of freedom: not estimable, and
    a conservative default is used. Returns (tau2, facts)."""
    ys, vs = [], []
    broken = 0
    for o, e, d in zip(O, E, deff):
        o, e = np.asarray(o, float), np.asarray(e, float)
        if len(o) < 3 or (e < MIN_CELL_EXPECTED_TAU).any():
            continue
        if o[0] == 0 or o[-1] == 0:
            broken += 1
            continue
        ys.append(log_cc(o, e))
        vs.append(max(float(d), 1.0) / (e + 0.5))
    Q, C, df = dl_pool(ys, vs)
    if df < 5 or C <= 0:
        return max(floor, TAU2_UNESTIMABLE), {'cells': len(ys), 'df': df, 'estimable': False, 'broken_cells': broken}
    return max(floor, (Q - df) / C), {'cells': len(ys), 'df': df, 'estimable': True, 'raw': (Q - df) / C,
                                      'broken_cells': broken}
