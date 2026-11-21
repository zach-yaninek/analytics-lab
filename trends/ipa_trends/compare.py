"""Time-trend call-outs: the latest final period against its trailing baseline, cell by cell (conservative flags).

For each cell (stratum x issue) with latest period L and the pooled final baseline periods B:

  E_L    = rate_B x M_L x f_L / fbar_B           f: business-day factor (stats.day_factors); fbar_B weights the
                                                 baseline periods by the cell's machine-months
  ratio  = O_L / E_L                             the crude rate ratio (not standardised for age or model mix),
                                                 adjusted only for the mix of business days
  Var(log ratio) = V_boot + tau^2 (1 + 1/K)      V_boot from the paired account bootstrap (the same draws reweight
                                                 L and B), tau^2 the between-period variance of the cell's family,
                                                 K the number of baseline periods

A cell is tested only when the latest period is final, the baseline has at least half its periods, E_L >= 10,
the baseline has >= 20 tickets from >= 10 accounts, the issue is a real issue (not 'Not categorised' or
'Unmapped'), and the data-quality gates pass for both L and B: Category labels complete enough, and no taxonomy
change (unmapped Trouble Code x Category combinations). One Benjamini-Hochberg correction runs over every tested
cell in the run.

  higher / lower          q < Q_CUT and |ratio - 1| >= MIN_CHANGE; an increase must also survive putting back the
                          tickets on machines missing from the equipment list (survivorship check), else it is a
                          watch item
  watch_higher / _lower   q < WATCH_Q and |ratio - 1| >= MIN_CHANGE (report only)
  no_clear_change         tested, neither of the above
  not_tested              with the reason
"""
import warnings

import numpy as np
import pandas as pd

from . import stats
from .cadence import baseline_positions
from .definitions import fleet_exposure_copy as FX
from .definitions import followups_copy as FU
from .exposure import category_mask, ticket_periods
from .inputs import NO_ACCOUNT, UNKNOWN, UNMAPPED
from .rates import DIM_COLUMN, DIM_LABEL

NOT_TESTED_ISSUES = (FU.NO_CAT, UNMAPPED)
NOT_TESTED_STRATA = (UNKNOWN, NO_ACCOUNT, 'nan', 'None')
MAX_UNDEFINED = 0.01


def _keys_for(dim, catalog, category_dims):
    lvl = dict(zip(catalog.issue_key, catalog.issue_level))
    return [k for k in catalog.issue_key if lvl[k] != 'category' or dim in category_dims]


def _levels(mp, col, positions):
    vals = mp.loc[mp.period_pos.isin(positions), col].dropna().astype(object)
    return sorted(set(vals), key=str)


def _period_months(mp, col, levels, positions):
    """Machine-months per level x period (for the business-day weighting of the baseline)."""
    sub = mp[mp.period_pos.isin(positions)]
    g = sub.groupby([sub[col].astype(object), 'period_pos']).months.sum().unstack(fill_value=0.0)
    return g.reindex(index=levels, columns=positions, fill_value=0.0).to_numpy(float)


def unlisted_frame(unl, grid, model_stratum, model_family):
    """Tickets on serials missing from every equipment list, with their period, issue keys, model stratum and
    family (from the ticket's Model #), and each serial's least possible exposure per period: from its first ticket
    day to the day after its last (fleet_exposure L622-623, clipped to each period)."""
    u = unl.copy()
    u['period_pos'] = ticket_periods(u, grid)
    u = u[u.period_pos >= 0]
    u['model_stratum'] = u.model_ticket.map(model_stratum)
    u['family'] = u.model_ticket.map(model_family)
    span = u.groupby('serial').agg(first=('ts', 'min'), last=('ts', 'max'), model=('model_ticket', 'first'))
    span['first'] = span['first'].dt.normalize()
    span['last'] = span['last'].dt.normalize() + pd.Timedelta(days=1)
    rows = []
    for p in range(len(grid)):
        a, b = grid.period_start[p], grid.period_end[p]
        mo = FX.months_between(span['first'].clip(lower=a), span['last'].clip(upper=b))
        rows.append(pd.DataFrame({'serial': span.index, 'period_pos': p, 'min_months': mo.to_numpy(),
                                  'model_stratum': span.model.map(model_stratum).to_numpy(),
                                  'family': span.model.map(model_family).to_numpy()}))
    months = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=['serial', 'period_pos', 'min_months', 'model_stratum', 'family'])
    return u, months[months.min_months > 0]


def _unlisted_cells(u, um, dim, level, key, positions):
    """Unlisted tickets for a cell and their least exposure over the given periods (None if the dimension cannot be
    attributed from a ticket: install cohort and age need the machine's install date)."""
    if dim not in ('fleet', 'model', 'family'):
        return None
    uu = u[u.period_pos.isin(positions)]
    mm = um[um.period_pos.isin(positions)]
    if dim != 'fleet':
        col = DIM_COLUMN[dim] if dim == 'model' else 'family'
        uu, mm = uu[uu[col] == level], mm[mm[col] == level]
    if key == 'all':
        n = len(uu)
    elif key.startswith('group|'):
        n = int((uu.group == key.split('|', 1)[1]).sum())
    else:
        _, g, c = key.split('|', 2)
        n = int((category_mask(uu) & (uu.cgroup == g) & (uu.ctype == c)).sum())
    return float(n), float(mm.min_months.sum())


def taxonomy_blocked(t, grid, latest_pos, code_groups, max_share):
    """Groups whose tests are unsafe because Trouble Code x Category combinations missing from the reference reach
    more than max_share of a Trouble Code's tickets in the latest period (a split or renamed Category, say).

    Returns (groups blocked at every level, groups blocked at the Category level only). When the Trouble Code fixes
    the group (Electronics, Network, Software, Operator Error), the new Category still lands in the right group, so
    only that group's Category-level tests are unsafe; otherwise the group(s) the Trouble Code maps to are blocked."""
    pos = ticket_periods(t, grid)
    tl = t[pos == latest_pos]
    all_levels, category_only = set(), set()
    if tl.empty:
        return all_levels, category_only
    share = tl.groupby(tl.trouble_code.fillna(FU.BLANK)).unmapped.mean()
    for tc, s in share.items():
        if s <= max_share:
            continue
        if tc in FU.BY_TROUBLE_CODE:
            category_only.add(FU.BY_TROUBLE_CODE[tc])
        else:
            all_levels |= set(code_groups.get(tc, [])) | {'Other', FU.NO_CAT, UNMAPPED}
    return all_levels, category_only - all_levels


def comparison(ctx, latest_pos, tau2=None):
    """One row per cell for latest period `latest_pos`. ctx carries the run's frames (see engine.Context).
    Returns (DataFrame, info dict). tau2: {'head': x, 'category': y}; estimated here when None."""
    P, grid, mp = ctx.params, ctx.grid, ctx.mp
    base_all, intended, enough_all = baseline_positions(grid, latest_pos, P.baseline_months, ctx.cadence)
    base_lab, _, enough_lab = baseline_positions(grid, latest_pos, P.baseline_months, ctx.cadence,
                                                 mask=pd.Series(ctx.label_ok, index=grid.index))
    f, w_day, dfacts = stats.day_factors(ctx.t, grid, base_all if base_all else [latest_pos])
    blocked, blocked_cat = taxonomy_blocked(ctx.t, grid, latest_pos, ctx.code_groups, P.MAX_UNMAPPED_SHARE)
    level_of = dict(zip(ctx.catalog.issue_key, ctx.catalog.issue_level))
    cells = []
    for dim in ['fleet'] + list(ctx.dims):
        col = DIM_COLUMN[dim]
        keys = _keys_for(dim, ctx.catalog, ctx.category_dims)
        levels = _levels(mp, col, [latest_pos] + base_all)
        if not levels:
            continue
        TL, ML = stats.cluster_arrays(mp, col, keys, [latest_pos], ctx.clusters, levels)
        TLb, MLb = stats.boot_sums(ctx.W, TL, ML)
        per_set = {}
        for name, pos in (('all', base_all), ('labels', base_lab)):
            TB, MB = stats.cluster_arrays(mp, col, keys, pos, ctx.clusters, levels)
            TBb, MBb = stats.boot_sums(ctx.W, TB, MB)
            pm = _period_months(mp, col, levels, pos) if pos else np.zeros((len(levels), 0))
            with np.errstate(invalid='ignore', divide='ignore'):
                fbar = (pm @ f[pos]) / pm.sum(1) if pos else np.full(len(levels), np.nan)
            per_set[name] = (pos, TB, MB, TBb, MBb, fbar)
        for ki, key in enumerate(keys):
            name = 'all' if level_of[key] == 'all' else 'labels'
            pos, TB, MB, TBb, MBb, fbar = per_set[name]
            O_L, M_L = TL[:, :, ki].sum(1), ML.sum(1)
            O_B, M_B = TB[:, :, ki].sum(1), MB.sum(1)
            with np.errstate(invalid='ignore', divide='ignore'):
                ratio_f = f[latest_pos] / fbar
                E_L = O_B / M_B * M_L * ratio_f
                Eb = TBb[:, :, ki] / MBb * MLb * ratio_f[None, :]
            logs = stats.log_cc(TLb[:, :, ki], Eb)
            undefined = np.isnan(logs).mean(0)
            with np.errstate(invalid='ignore'), warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)   # cells undefined in every draw: reported below
                v_boot = np.nanvar(logs, axis=0, ddof=1)
            acc_b = (TB[:, :, ki] > 0).sum(1)
            for li, lev in enumerate(levels):
                cells.append({'stratum_dim': dim, 'stratum': str(lev), 'issue_key': key, 'tickets_latest': O_L[li],
                              'months_latest': M_L[li], 'tickets_baseline': O_B[li], 'months_baseline': M_B[li],
                              'expected_latest': E_L[li], 'day_factor_latest': f[latest_pos],
                              'day_factor_baseline': fbar[li], 'v_boot': v_boot[li],
                              'undefined_draws_share': undefined[li], 'accounts_with_tickets_baseline': int(acc_b[li]),
                              'baseline_periods_used': len(pos), 'baseline_set': name})
    c = pd.DataFrame(cells)
    c = c.merge(ctx.catalog[['issue_key', 'issue_level', 'issue_group', 'issue', 'order']], on='issue_key',
                how='left')
    with np.errstate(invalid='ignore', divide='ignore'):
        v_pois = 1 / (c.tickets_latest + 0.5) + 1 / (c.tickets_baseline + 0.5)
        c['deff'] = np.maximum(1.0, (c.v_boot / v_pois).fillna(1.0))
    c['tau_family'] = np.where(c.issue_level == 'category', 'category', 'head')
    if tau2 is None:
        tau2, tau_facts = ctx.estimate_tau2(latest_pos, c)
    else:
        tau_facts = {}
    c['tau2'] = c.tau_family.map(tau2)
    K = c.baseline_periods_used.clip(lower=1)
    c['sd_log'] = np.sqrt(c.v_boot + c.tau2 * (1 + 1 / K))
    with np.errstate(invalid='ignore', divide='ignore'):
        c['change_ratio'] = c.tickets_latest / c.expected_latest
        c['crude_ratio'] = (c.tickets_latest / c.months_latest) / (c.tickets_baseline / c.months_baseline)
        c['rate_latest'] = 100 * c.tickets_latest / c.months_latest
        c['rate_baseline'] = 100 * c.tickets_baseline / c.months_baseline
    lr = stats.log_cc(c.tickets_latest, c.expected_latest)
    c['z'] = lr / c.sd_log
    c['p_value'] = stats.two_sided_p(c.z)
    c['ci_lo'] = np.exp(lr - stats.Z95 * c.sd_log)
    c['ci_hi'] = np.exp(lr + stats.Z95 * c.sd_log)
    c['mdc_pct'] = 100 * (np.exp(stats.Z_POWER80 * c.sd_log) - 1)

    # eligibility
    reason = pd.Series('', index=c.index, dtype=object)

    def block(mask, why):
        reason[(reason == '') & mask] = why
    issue_level_cell = c.issue_level != 'all'
    block(pd.Series(not enough_all, index=c.index),
          f'not enough history: {len(base_all)} of {intended} baseline periods are final')
    block(issue_level_cell & (not bool(ctx.label_ok[latest_pos])), 'Category labels incomplete in the latest period')
    block(issue_level_cell & (not enough_lab), 'not enough baseline periods with complete Category labels')
    block(c.issue.isin(NOT_TESTED_ISSUES), 'not an issue (no Category / unmapped)')
    block(c.stratum.isin(NOT_TESTED_STRATA), 'unknown stratum')
    block(c.issue_group.isin(blocked) & (c.issue_level != 'all'), 'possible taxonomy change (unmapped Categories)')
    block(c.issue_group.isin(blocked_cat) & (c.issue_level == 'category'),
          'possible taxonomy change (new Categories in this group)')
    block(c.expected_latest.fillna(0) < P.MIN_EXPECTED, f'fewer than {P.MIN_EXPECTED:g} tickets expected')
    block(c.tickets_baseline < P.MIN_BASELINE_TICKETS, f'fewer than {P.MIN_BASELINE_TICKETS:g} baseline tickets')
    block(c.accounts_with_tickets_baseline < P.MIN_ACCOUNTS,
          f'baseline tickets come from fewer than {P.MIN_ACCOUNTS} accounts')
    block(c.undefined_draws_share > MAX_UNDEFINED, 'unstable bootstrap (stratum missing from some resamples)')
    block(~np.isfinite(c.sd_log) | ~np.isfinite(c.change_ratio), 'not estimable')
    c['eligible'] = reason == ''
    c['not_tested_reason'] = reason
    no_basis = ~(c.expected_latest > 0)            # nothing expected: the ratio and its interval mean nothing
    c.loc[no_basis, ['change_ratio', 'ci_lo', 'ci_hi', 'z', 'p_value', 'mdc_pct']] = np.nan
    q = np.full(len(c), np.nan)
    if c.eligible.any():
        q[c.eligible.to_numpy()] = FX.bh_q(c.p_value[c.eligible].to_numpy())
    c['q_value'] = q

    # survivorship check for increases
    surv, note = [], []
    lp = [latest_pos]
    for r in c.itertuples():
        if not (r.eligible and r.change_ratio >= 1 + P.MIN_CHANGE):
            surv.append(np.nan)
            note.append('')
            continue
        pos = per_pos(base_all, base_lab, r.baseline_set)
        uL = _unlisted_cells(ctx.unlisted, ctx.unlisted_months, r.stratum_dim, _level(r), r.issue_key, lp)
        uB = _unlisted_cells(ctx.unlisted, ctx.unlisted_months, r.stratum_dim, _level(r), r.issue_key, pos)
        if uL is None:   # not attributable: apply the fleet's relative change for the same issue
            fl = c[(c.stratum_dim == 'fleet') & (c.issue_key == r.issue_key)]
            if fl.empty:
                surv.append(np.nan)
                note.append('')
                continue
            fl = fl.iloc[0]
            ufL = _unlisted_cells(ctx.unlisted, ctx.unlisted_months, 'fleet', None, r.issue_key, lp)
            ufB = _unlisted_cells(ctx.unlisted, ctx.unlisted_months, 'fleet', None, r.issue_key, pos)
            upl = _uplift(fl.tickets_latest, fl.months_latest, *ufL) / _uplift(fl.tickets_baseline,
                                                                               fl.months_baseline, *ufB)
            s = r.change_ratio * upl
        else:
            with np.errstate(invalid='ignore', divide='ignore'):
                s = ((r.tickets_latest + uL[0]) / (r.months_latest + uL[1])) / \
                    ((r.tickets_baseline + uB[0]) / (r.months_baseline + uB[1])) * \
                    (r.day_factor_baseline / r.day_factor_latest)
        surv.append(s)
        ok = np.isfinite(s) and np.exp(np.log(s) - stats.Z95 * r.sd_log) > 1 and s - 1 >= P.MIN_CHANGE
        note.append('' if ok else 'may reflect machines missing from the equipment list')
    c['survivor_ratio'], c['survivor_note'] = surv, note

    up = c.change_ratio >= 1 + P.MIN_CHANGE
    down = c.change_ratio <= 1 - P.MIN_CHANGE
    flag = c.eligible & (c.q_value < P.Q_CUT)
    watch = c.eligible & (c.q_value < P.WATCH_Q)
    status = np.select([flag & up & (c.survivor_note == ''), flag & down, watch & up, watch & down, c.eligible],
                       ['higher', 'lower', 'watch_higher', 'watch_lower', 'no_clear_change'], 'not_tested')
    c['status'] = status
    c.loc[(c.status == 'watch_higher') & (c.survivor_note != ''), 'not_tested_reason'] = c.survivor_note
    info = {'latest_pos': latest_pos, 'baseline_positions': base_all, 'baseline_label_positions': base_lab,
            'baseline_intended': intended, 'enough': enough_all, 'day_factor': dfacts, 'tau2': tau2,
            'tau2_facts': tau_facts, 'taxonomy_blocked_groups': sorted(blocked),
            'taxonomy_blocked_category_groups': sorted(blocked_cat)}
    return c, info


def per_pos(base_all, base_lab, name):
    return base_all if name == 'all' else base_lab


def _level(r):
    return None if r.stratum_dim == 'fleet' else r.stratum


def _uplift(o, m, u, um):
    with np.errstate(invalid='ignore', divide='ignore'):
        return ((o + u) / (m + um)) / (o / m) if o > 0 and m > 0 else 1.0


def add_sustained(c, prev):
    """Mark cells whose previous period was flagged (or on watch) in the same direction."""
    if prev is None or prev.empty:
        c['sustained'] = False
        c['previous_status'] = ''
        return c
    p = prev.set_index(['stratum_dim', 'stratum', 'issue_key']).status
    key = list(zip(c.stratum_dim, c.stratum, c.issue_key))
    c['previous_status'] = [p.get(k, '') for k in key]
    same_up = c.status.isin(['higher', 'watch_higher']) & c.previous_status.isin(['higher', 'watch_higher'])
    same_dn = c.status.isin(['lower', 'watch_lower']) & c.previous_status.isin(['lower', 'watch_lower'])
    c['sustained'] = same_up | same_dn
    return c


def sentence(r, latest_label, cadence, k):
    """Executive wording for one cell; nouns follow the cadence; never 'significant'."""
    where = '' if r.stratum_dim == 'fleet' else f' ({DIM_LABEL[r.stratum_dim].lower()} {r.stratum})'
    pct = 100 * (r.change_ratio - 1)
    lo, hi = 100 * (r.ci_lo - 1), 100 * (r.ci_hi - 1)
    direction = 'above' if pct >= 0 else 'below'
    text = (f'{r.issue}{where}: {r.rate_latest:.2f} per 100 installed machine-months in {latest_label}, '
            f'{abs(pct):.0f}% {direction} {cadence.previous(k)} (95% interval {lo:+.0f}% to {hi:+.0f}%)')
    if r.status in ('higher', 'lower'):
        text += f', beyond normal {cadence.variation}: a screening flag for follow-up, not proof of a problem'
    elif r.status.startswith('watch'):
        text += ': could still be chance'
    if getattr(r, 'sustained', False):
        text += f'; also flagged last {cadence.noun}'
    return text + '.'
