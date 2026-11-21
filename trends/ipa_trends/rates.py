"""Unplanned tickets per 100 installed machine-months for every period x stratum x issue.

Each cell goes through the copied fleet_exposure.group_rates, so the intervals follow the committed rule (F8): the
account cluster bootstrap (N_BOOT draws, seed 15072); for a cell in fewer than 10 accounts or with no tickets, the
wider of the bootstrap and Byar intervals; one account is 'not estimable' against the fleet.
"""
import warnings

import numpy as np
import pandas as pd

from .definitions import fleet_exposure_copy as FX
from .exposure import FLEET

DIM_COLUMN = {'fleet': '_fleet', 'install_cohort': 'install_cohort', 'family': 'family', 'model': 'model_stratum',
              'age_group': 'age_group', 'age_band': 'age_band', 'service_status': 'service_status',
              'country': 'country'}
DIM_LABEL = {'fleet': 'Fleet', 'install_cohort': 'Install cohort', 'family': 'Product family', 'model': 'Model',
             'age_group': 'Age group', 'age_band': 'Age band', 'service_status': 'Service status',
             'country': 'Country'}
RATE_COLUMNS = ['tickets', 'machine_months', 'machines', 'machines_with_ticket', 'accounts', 'rate_per_100', 'ci_lo',
                'ci_hi', 'ci_method', 'byar_lo', 'byar_hi', 'boot_lo', 'boot_hi', 'ratio_to_fleet', 'ratio_lo',
                'ratio_hi', 'vs_fleet']
WINDOW_DAYS_REF = 396        # the Aug 2025 - Aug 2026 window MIN_TYPE_MONTHS (100 machine-months) was set for


def pool_models(mp, grid, latest_pos, params):
    """The 'model' stratum: a model keeps its own series when it averages at least MIN_TYPE_MONTHS / 13.01 machines
    (100 machine-months over the original 396-day window, as fleet_exposure.add_rate_groups) over the data window,
    or over the latest final period (so a fast-growing new model is not hidden in the pool). Decided once per run.

    Returns (Series model -> stratum label, DataFrame describing each model)."""
    min_avg = params.MIN_TYPE_MONTHS / (WINDOW_DAYS_REF / FX.MONTH_DAYS)
    window_months = grid.covered_days.sum() / FX.MONTH_DAYS
    by = mp.groupby('model').months.sum()
    avg = by / window_months
    if latest_pos is not None:
        lp = mp[mp.period_pos == latest_pos].groupby('model').months.sum()
        avg_latest = (lp / (grid.covered_days[latest_pos] / FX.MONTH_DAYS)).reindex(by.index).fillna(0.0)
    else:
        avg_latest = pd.Series(0.0, index=by.index)
    own = (avg >= min_avg) | (avg_latest >= min_avg)
    pool_label = f'Other models (under {min_avg:.1f} machines on average)'
    if not params.POOL_SMALL_STRATA:
        own[:] = True
    label = pd.Series(np.where(own, by.index, pool_label), index=by.index)
    desc = pd.DataFrame({'model': by.index, 'avg_installed_machines': avg.to_numpy(),
                         'avg_installed_machines_latest': avg_latest.to_numpy(), 'own_series': own.to_numpy(),
                         'stratum': label.to_numpy()})
    return label, desc, pool_label


def rates_many(m, by, keys, W, clusters, months='months'):
    """fleet_exposure.group_rates for many ticket columns at once: the same arithmetic, vectorised over the keys.

    group_rates (copied verbatim in definitions/) stays the reference: tests check that this returns its values for
    every key (counts exactly; machine-months, rates, ratios and intervals to floating-point rounding). Returns one
    frame per key, with group_rates' columns."""
    levels = sorted(m[by].dropna().unique(), key=str)
    if not levels:
        return {k: pd.DataFrame() for k in keys}
    lev = m[by].map({v: i for i, v in enumerate(levels)})
    ok = lev.notna().to_numpy()
    li = lev[ok].astype(int).to_numpy()
    ci = m.customer.map({a: i for i, a in enumerate(clusters)}).to_numpy()[ok]
    L, C, K = len(levels), len(clusters), len(keys)
    T = np.zeros((L, C, K))
    M = np.zeros((L, C))
    np.add.at(T, (li, ci), m[keys].to_numpy(float)[ok])
    np.add.at(M, (li, ci), m[months].to_numpy(float)[ok])
    Mb = W @ M.T                                                   # draws x levels
    Tb = np.einsum('bc,lck->blk', W, T, optimize=True)             # draws x levels x keys
    with np.errstate(invalid='ignore', divide='ignore'):
        rate_b = Tb / Mb[:, :, None]
        ratio_b = rate_b / (Tb.sum(1) / Mb.sum(1)[:, None])[:, None, :]
        fleet = m[keys].to_numpy(float).sum(0) / m[months].to_numpy(float).sum()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)          # levels empty in every draw give NaN, as before
        blo, bhi = FX.pct_ci(rate_b)
        rlo, rhi = FX.pct_ci(ratio_b)
    exposed = m[m[months] > 0]
    base = exposed.groupby(by, observed=True).agg(machines=('serial', 'size'), clusters=('customer', 'nunique'))
    base = base.reindex(levels)
    with_ticket = (exposed[keys] > 0).groupby(exposed[by], observed=True).sum().reindex(levels)
    machines = base.machines.fillna(0).astype(int).to_numpy()
    accounts = base.clusters.fillna(0).astype(int).to_numpy()
    out = {}
    for k, key in enumerate(keys):
        g = pd.DataFrame({by: levels, 'machines': machines,
                          'machines_with_ticket': with_ticket[key].fillna(0).astype(int).to_numpy(),
                          'accounts': accounts, 'months': M.sum(1), 'tickets': T[:, :, k].sum(1)})
        with np.errstate(invalid='ignore', divide='ignore'):
            g['rate_per_100'] = 100 * g.tickets / g.months
            lo, hi = FX.byar(g.tickets)
            g['byar_lo'], g['byar_hi'] = 100 * lo / g.months, 100 * hi / g.months
            g['boot_lo'], g['boot_hi'] = 100 * blo[:, k], 100 * bhi[:, k]
            g['ratio_to_fleet'] = g.rate_per_100 / (100 * fleet[k])
            weak = (g.accounts < FX.MIN_CLUSTERS) | (g.tickets == 0)
            g['ci_method'] = np.where(weak, 'wider of bootstrap and Byar', 'cluster bootstrap')
            g['ci_lo'] = np.where(weak, np.fmin(g.boot_lo, g.byar_lo), g.boot_lo)
            g['ci_hi'] = np.where(weak, np.fmax(g.boot_hi, g.byar_hi), g.boot_hi)
            g['ratio_lo'] = np.where(weak, np.fmin(rlo[:, k], g.byar_lo / (100 * fleet[k])), rlo[:, k])
            g['ratio_hi'] = np.where(weak, np.fmax(rhi[:, k], g.byar_hi / (100 * fleet[k])), rhi[:, k])
        g['vs_fleet'] = FX.classify(g.rename(columns={'accounts': 'clusters'}), 'ratio_lo', 'ratio_hi')
        g['fleet_rate_per_100'] = 100 * fleet[k]
        out[key] = g
    return out


def rate_table(mp, grid, catalog, dims, category_dims, W, clusters, params):
    """Long table of rates: one row per period x (dimension, stratum) x issue."""
    level_of = dict(zip(catalog.issue_key, catalog.issue_level))
    rows = []
    checks = []
    for p, g in grid.iterrows():
        fp = mp[mp.period_pos == p]
        if fp.empty:
            continue
        months_in_period = g.covered_days / FX.MONTH_DAYS
        for dim in ['fleet'] + list(dims):
            col = DIM_COLUMN[dim]
            keys = [k for k in catalog.issue_key if level_of[k] != 'category' or dim in category_dims]
            many = rates_many(fp, col, keys, W, clusters)
            for key in keys:
                r = many[key]
                if r.empty:
                    continue
                r = r.rename(columns={col: 'stratum', 'months': 'machine_months'})
                r['stratum'] = r.stratum.astype(str)
                r['avg_installed_machines'] = r.machine_months / months_in_period
                r['stratum_dim'], r['issue_key'], r['period_pos'] = dim, key, p
                rows.append(r[['period_pos', 'stratum_dim', 'stratum', 'issue_key', 'avg_installed_machines']
                              + RATE_COLUMNS])
                if key == 'all' and dim != 'fleet':
                    exposed_all = fp.loc[fp[col].notna(), 'all'].sum()
                    checks.append((f'{g.label}: {dim} strata add up to the fleet (tickets)', float(fp['all'].sum()),
                                   float(r.tickets.sum()) + float(fp['all'].sum() - exposed_all), 1e-9))
                    checks.append((f'{g.label}: {dim} strata add up to the fleet (machine-months)',
                                   float(fp.months.sum()), float(r.machine_months.sum())
                                   + float(fp.loc[fp[col].isna(), 'months'].sum()), 1e-6))
    out = pd.concat(rows, ignore_index=True)
    out = out.merge(catalog[['issue_key', 'issue_level', 'issue_group', 'issue', 'order']], on='issue_key',
                    how='left')
    out = out.merge(grid[['period_key', 'label', 'period_start', 'period_end', 'status']].rename(
        columns={'label': 'period_label'}), left_on='period_pos', right_index=True, how='left')
    out['meets_min_exposure'] = out.machine_months >= params.MIN_CELL_MONTHS
    return out, checks


def stratum_order(dim, values, pop):
    """Display order of strata: cohorts and age bands in time order, others by size."""
    values = list(dict.fromkeys(values))
    if dim == 'install_cohort':
        cats = list(pop.install_cohort.cat.categories)
        return sorted(values, key=lambda v: cats.index(v) if v in cats else len(cats))
    if dim == 'age_band':
        cats = list(FX.AGE_LABELS)
        return sorted(values, key=lambda v: cats.index(v) if v in cats else len(cats))
    if dim == 'fleet':
        return [FLEET]
    return values
