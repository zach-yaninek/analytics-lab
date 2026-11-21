"""Installed machine-months per reporting period, and the population they belong to.

This is verification/fleet_exposure.py's machine_frame (definitions F1-F3) generalised from the full period and its
two halves to the edges of any reporting grid:

  population   machines on the equipment list(s), except those on a third-party service plan (and, by default,
               those with no install date); tickets = unplanned tickets (CASE_VIEWS) opened in [D0, D1) on them.
  start        max(D0, min(install date, first ticket)): a ticket before the listed install date starts exposure.
  end          D1 for machines on the newest list; for a machine that dropped off a later list, the midpoint between
               its last listing and its first absence, or the day after its last ticket if that is later.
  months       whole days / 30.4375 within each period: months_between(max(start, a_p), min(end, b_p)). Period
               edges fall at midnight, so a machine's months summed over the periods equal its whole-window months.
  age band     at the midpoint of the machine's exposure inside the period (fleet_exposure's age_band_h1/_h2 rule).

Real account names and serials stay in memory; machines carry their cluster label ('Customer NNN', as
common.build_maps numbers them) for the account bootstrap.
"""
import numpy as np
import pandas as pd

from .definitions import fleet_exposure_copy as FX
from .definitions import followups_copy as FU
from .errors import CheckError
from .inputs import UNMAPPED

FLEET = 'Fleet'


def population(ledger, tickets, d0, d1, params, warn):
    """The machine frame (one row per listed machine, with start, end and whole-window months), population
    tickets, unlisted tickets and the counts that reconcile them."""
    in_period = tickets[tickets.unplanned & (tickets.ts >= d0) & (tickets.ts < d1)]
    listed = set(ledger.serial)
    m = ledger.copy()
    m['third_party'] = m.service_plan.isin(params.THIRD_PARTY_PLANS)
    t_listed = in_period[in_period.serial.isin(listed)]
    first = t_listed.groupby('serial').ts.min().dt.normalize()
    last = t_listed.groupby('serial').ts.max().dt.normalize()
    m['first_ticket'] = m.serial.map(first)
    m['last_ticket'] = m.serial.map(last)
    m['ticket_before_install'] = m.first_ticket < m.install_date.dt.normalize()
    m['start'] = m[['install_date', 'first_ticket']].min(axis=1).clip(lower=d0)   # fleet_exposure L395
    missing = m.install_date.isna()
    if params.MISSING_INSTALL_DATE == 'data_start':
        m.loc[missing, 'start'] = d0
    end = pd.Series(d1, index=m.index)
    gone = ~m.on_newest
    if gone.any():
        e = pd.concat([m.loc[gone, 'removal_estimate'], m.loc[gone, 'last_ticket'] + pd.Timedelta(days=1)],
                      axis=1).max(axis=1)
        end[gone] = e.clip(upper=d1)
    m['end'] = end.fillna(m.start)
    m['months'] = FX.months_between(m.start, m.end).fillna(0.0)
    m['age_band'], m['age_years'] = FX.age_band(m.start, m.end, m.install_date)

    excluded_missing = missing & (params.MISSING_INSTALL_DATE == 'exclude')
    pop = m[~m.third_party & ~excluded_missing].copy().reset_index(drop=True)
    t = t_listed[t_listed.serial.isin(set(pop.serial))].copy()
    unl = in_period[~in_period.serial.isin(listed)].copy()
    third_t = int(t_listed.serial.isin(set(m.serial[m.third_party])).sum())
    miss_t = int(t_listed.serial.isin(set(m.serial[excluded_missing & ~m.third_party])).sum())
    facts = {'unplanned_in_window': len(in_period), 'tickets_on_listed': len(t_listed), 'unlisted_tickets': len(unl),
             'unlisted_serials': int(unl.serial.nunique()), 'listed_machines': len(m),
             'removed_machines': int(gone.sum()), 'third_party_machines': int(m.third_party.sum()),
             'third_party_tickets': third_t, 'missing_install_machines': int((missing & ~m.third_party).sum()),
             'missing_install_tickets': miss_t, 'population_machines': len(pop), 'population_tickets': len(t),
             'zero_month_machines': int((pop.months == 0).sum()), 'machines_exposed': int((pop.months > 0).sum()),
             'tickets_before_install': int((t.ts.dt.normalize() < t.serial.map(
                 pop.set_index('serial').install_date.dt.normalize())).sum()),
             'machines_start_at_pre_install_ticket': int(pop.ticket_before_install.sum()),
             'population_months': float(pop.months.sum())}
    checks = [('every unplanned ticket in the window is on a listed or an unlisted serial',
               len(in_period), len(t_listed) + len(unl)),
              ('population + third-party + missing-install tickets = tickets on listed machines',
               len(t_listed), len(t) + third_t + miss_t)]
    if missing.any() and params.MISSING_INSTALL_DATE == 'exclude':
        warn.add('W08', f'{facts["missing_install_machines"]} listed machine(s) have no install date; they and their '
                        f'{miss_t} ticket(s) are left out', "set MISSING_INSTALL_DATE = 'data_start' to include them")
    if gone.any():
        warn.add('W23', f'{int(gone.sum())} machine(s) appear on an older equipment list but not the newest; their '
                        'exposure ends midway between the two lists')
    return {'machines': m, 'pop': pop, 't': t, 'unlisted': unl, 'facts': facts, 'checks': checks}


def issue_catalog(t):
    """Issue keys, levels and labels: all unplanned tickets, the request groups, and the Categories under the
    component groups (Part A's rule: followups.py L708, Monitoring and blank Category excluded)."""
    groups = list(FU.GROUPS) + ([UNMAPPED] if (t.group == UNMAPPED).any() else [])
    rows = [{'issue_key': 'all', 'issue_level': 'all', 'issue_group': '', 'issue': 'All unplanned tickets'}]
    rows += [{'issue_key': f'group|{g}', 'issue_level': 'group', 'issue_group': g, 'issue': g} for g in groups]
    catmask = category_mask(t)
    ctab = t[catmask].groupby(['cgroup', 'ctype']).size().reset_index(name='n')
    ctab['o'] = ctab.cgroup.map({g: i for i, g in enumerate(FU.GROUPS)})
    ctab = ctab.sort_values(['o', 'n', 'ctype'], ascending=[True, False, True])
    rows += [{'issue_key': f'category|{g}|{c}', 'issue_level': 'category', 'issue_group': g, 'issue': c}
             for g, c in zip(ctab.cgroup, ctab.ctype)]
    cat = pd.DataFrame(rows)
    cat['order'] = np.arange(len(cat))
    return cat


def category_mask(t):
    return t.cgroup.isin(FU.COMPONENT) & (t.ctype != FU.NO_CAT) & ~t.monitoring


def ticket_periods(t, grid):
    """Position of each ticket's period (a_p <= ts < b_p); -1 when no period holds it."""
    starts = grid.period_start.to_numpy(dtype='datetime64[ns]')
    ends = grid.period_end.to_numpy(dtype='datetime64[ns]')
    ts = t.ts.to_numpy(dtype='datetime64[ns]')
    pos = np.searchsorted(starts, ts, side='right') - 1
    ok = (pos >= 0) & (ts < ends[np.clip(pos, 0, len(ends) - 1)])
    return np.where(ok, pos, -1)


def machine_periods(pop, t, grid, catalog, dims):
    """One row per machine x period with exposure or tickets: months, age band, the stratum columns in `dims`,
    the cluster label, and one ticket-count column per issue key."""
    n, p = len(pop), len(grid)
    s = pop.start.to_numpy(dtype='datetime64[ns]')
    e = pop.end.to_numpy(dtype='datetime64[ns]')
    a = grid.period_start.to_numpy(dtype='datetime64[ns]')
    b = grid.period_end.to_numpy(dtype='datetime64[ns]')
    seg_s = pd.Series(np.maximum(s[:, None], a[None, :]).ravel())
    seg_e = pd.Series(np.minimum(e[:, None], b[None, :]).ravel())
    months = FX.months_between(seg_s, seg_e).to_numpy()
    install = pd.Series(np.repeat(pop.install_date.to_numpy(dtype='datetime64[ns]'), p))
    band, years = FX.age_band(seg_s, seg_e, install)
    mp = pd.DataFrame({'mi': np.repeat(np.arange(n), p), 'period_pos': np.tile(np.arange(p), n),
                       'months': months, 'age_band': band, 'age_years': years.to_numpy()})
    # tickets per machine x period x issue
    tpos = ticket_periods(t, grid)
    mi = t.serial.map({sv: i for i, sv in enumerate(pop.serial)}).to_numpy()
    keys = [np.full(len(t), 'all', dtype=object), ('group|' + t.group.astype(str)).to_numpy()]
    cm = category_mask(t).to_numpy()
    ck = np.where(cm, 'category|' + t.cgroup.astype(str) + '|' + t.ctype.astype(str), None)
    long = pd.DataFrame({'mi': np.concatenate([mi, mi, mi[cm]]),
                         'period_pos': np.concatenate([tpos, tpos, tpos[cm]]),
                         'issue_key': np.concatenate([keys[0], keys[1], ck[cm]])})
    long = long[long.period_pos >= 0]
    counts = long.groupby(['mi', 'period_pos', 'issue_key']).size().unstack('issue_key', fill_value=0)
    counts = counts.reindex(columns=catalog.issue_key, fill_value=0).astype('int32')
    mp = mp.join(counts, on=['mi', 'period_pos'])
    mp[list(catalog.issue_key)] = mp[list(catalog.issue_key)].fillna(0).astype('int32')
    mp = mp[(mp.months > 0) | (mp['all'] > 0)].reset_index(drop=True)
    attrs = pop[['serial', 'customer', 'model', 'family', 'service_status', 'country', 'install_cohort']]
    mp = mp.join(attrs, on='mi')
    mp['age_group'] = np.where(mp.age_band.isna(), None,
                               np.where(mp.age_band.astype(str).isin(FU.YOUNG_BANDS), FU.AGE_LABELS[0],
                                        FU.AGE_LABELS[1]))
    mp['_fleet'] = FLEET
    outside = int((tpos < 0).sum())
    return mp, outside


def invariants(pop, t, mp, grid, catalog, outside):
    """Runtime checks that the numbers add up; any failure stops the run before anything is published."""
    checks = []
    per_machine = mp.groupby('mi').months.sum().reindex(range(len(pop)), fill_value=0.0)
    whole = pop.months.to_numpy()
    # whole days add up exactly; months differ only by float rounding
    checks.append(('months summed over periods = whole-window months (every machine)', 0.0,
                   float(np.abs(per_machine.to_numpy() - whole).max()) if len(pop) else 0.0, 1e-9))
    checks.append(('each population ticket falls in exactly one period', len(t), int(mp['all'].sum()) + outside,
                   0))
    gcols = [k for k in catalog.issue_key if k.startswith('group|')]
    checks.append(('request groups add up to all tickets', int(mp['all'].sum()), int(mp[gcols].sum().sum()), 0))
    inside = ticket_periods(t, grid) >= 0
    for g in FU.COMPONENT:
        ccols = [k for k in catalog.issue_key if k.startswith(f'category|{g}|')]
        tg = t[inside & (t.cgroup == g) & ~t.monitoring]
        blank = int((tg.ctype == FU.NO_CAT).sum())
        checks.append((f'{g}: non-Monitoring tickets = its Categories + its blank-Category tickets',
                       len(tg), int(mp[ccols].sum().sum()) + blank, 0))
    return checks


def run_checks(checks):
    """Raise CheckError listing every failed invariant."""
    failed = []
    for name, expected, actual, *tol in checks:
        tol = tol[0] if tol else 0
        ok = abs(float(actual) - float(expected)) <= tol if isinstance(expected, (int, float)) else expected == actual
        if not ok:
            failed.append(f'{name}: expected {expected}, got {actual}')
    if failed:
        raise CheckError('C01', 'runtime check(s) failed, so nothing was published: ' + '; '.join(failed),
                         'report this to the MIT team with manifest.json from the failed run')
    return len(checks)
