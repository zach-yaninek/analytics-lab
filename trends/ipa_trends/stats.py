"""Statistics shared by the comparison and cohort modules (numpy and math only, no scipy).

  cluster sums      tickets and machine-months per (stratum, account) so that one bootstrap draw (a row of the
                    copied boot_weights matrix) reweights both the latest period and the baseline: the paired account
                    bootstrap.
  day factors       weekends and US federal holidays get their own ticket weight, estimated from the baseline's fleet
                    tickets, so a period with more business days is not mistaken for a rise.
  tau^2             the between-period variance of log rates beyond sampling noise: DerSimonian-Laird pooled over the
                    cells of an issue-level family, with standardised residuals winsorised at +-3 (a one-month spike
                    cannot inflate it) and a floor.
"""
import math

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

Z95 = 1.959964
Z_POWER80 = 2.801585       # 1.959964 + 0.841621: 80% power, two-sided 5%
WINSOR = 3.0
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
def dl_pool(ys, vs):
    """DerSimonian-Laird moment sums over cells: ys, vs are lists of arrays (log rates and their sampling
    variances per period). Residuals beyond +-3 standard errors are pulled in to +-3 first.
    Returns (Q, C, df); tau^2 = (Q - df) / C."""
    Q = C = df = 0.0
    for y, v in zip(ys, vs):
        y, v = np.asarray(y, float), np.asarray(v, float)
        w = 1 / v
        ybar = np.sum(w * y) / np.sum(w)
        z = np.clip((y - ybar) / np.sqrt(v), -WINSOR, WINSOR)
        y = ybar + z * np.sqrt(v)
        ybar = np.sum(w * y) / np.sum(w)
        Q += float(np.sum(w * (y - ybar) ** 2))
        C += float(np.sum(w) - np.sum(w ** 2) / np.sum(w))
        df += len(y) - 1
    return Q, C, df


def tau2_dl(O, E, deff, floor):
    """Between-period variance of log rates, pooled over cells.

    O, E: lists of arrays (one per cell) of per-period observed and expected counts (E sums to O within a cell);
    deff: per-cell design effect (>= 1) for clustering within accounts. Cells qualify when every period expects at
    least 5 tickets and there are 3+ periods. Fewer than 5 pooled degrees of freedom: not estimable, and a
    conservative default is used. Returns (tau2, facts)."""
    ys, vs = [], []
    for o, e, d in zip(O, E, deff):
        o, e = np.asarray(o, float), np.asarray(e, float)
        if len(o) < 3 or (e < MIN_CELL_EXPECTED_TAU).any():
            continue
        ys.append(log_cc(o, e))
        vs.append(max(float(d), 1.0) / (e + 0.5))
    Q, C, df = dl_pool(ys, vs)
    if df < 5 or C <= 0:
        return max(floor, TAU2_UNESTIMABLE), {'cells': len(ys), 'df': df, 'estimable': False}
    return max(floor, (Q - df) / C), {'cells': len(ys), 'df': df, 'estimable': True, 'raw': (Q - df) / C}
