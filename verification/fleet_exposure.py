#!/usr/bin/env python3
"""Ticket rates adjusted for fleet exposure, from IPA's installed-base list, and the outliers that stay consistent.

Question: once we know how many machines each model, telemetry type and customer has, and for how long, which ones
generate more unplanned tickets than their fleet explains, and do they do so consistently?

Inputs (no database is opened):
  data/raw/IPA_Active_Equipment_list_2026-10-19.xlsx   IPA's active installed base (common.load_equipment)
  data/raw/IPA_CaseHistory_Aug 2025-Aug2026.xlsx        the case export (common.load_all)
  verification/outputs/htm_device_exposure.csv          telemetry-span exposure per device (interim type rates;
                                                        the 113 machines flagged in docs/05)
  verification/outputs/fleet/db/fxdb_devices.csv        OPTIONAL: device <-> list join from fleet_db_extract.py.
                                                        When present, telemetry-type rates use installed exposure.

Definitions
  F1 Population. Machines on the list (9,294). Tickets = unplanned tickets (Zac's service_cases view: excludes
     Planned work, Cancelled request, Duplicate case) opened 2025-08-01..2026-08-31 (Eastern) whose serial is on the
     list. Each ticket is attributed to the machine's account ON THE LIST (customer), so numerator and denominator
     use the same account.
  F2 Installed machine-months. Exposure runs from max(2025-08-01, install date) to 2026-09-01 (exclusive), in months
     of 365.25/12 days. If a machine has a ticket in the period before its install date, exposure starts on that
     ticket's date. Machines installed after the period have 0 months. Sensitivity: go-live date (install date when
     go-live is blank) instead of install date.
  F3 Rate groups. Models with >= MIN_TYPE_MONTHS (100) installed months get their own rate; the rest share one
     pooled group (POOL). Age band = years from install date to the midpoint of the machine's exposure window,
     cut at 1, 2, 4, 6, 8, 10 years.
  F4 Expected tickets. A Poisson main-effects model fitted by iterative proportional fitting:
     E_i = months_i x a[model group] x b[age band] (x c[service status] in the coverage variant), so expected equals
     observed in total for every level of every factor. Main = model + age; variants = model only (a plain model
     rate) and model + age + coverage.
  F5 Customers. STR = O / E. Two flags:
     Flagged (Poisson rule, as for machines) = >= 5 tickets AND Poisson BH q < 0.05 (BH over customers with E > 0):
       more tickets than the customer's fleet explains by chance.
     Beyond the funnel (extreme tier) = above the 99.8% limit of an overdispersion-adjusted funnel (Spiegelhalter
       2005) on the square-root scale: y = sqrt(O/E), s = 1/(2 sqrt(E)), z = (y - 1)/s; tau^2 by the additive
       random-effects moment estimator on z winsorised at the 10th/90th percentiles; z_D = (y - 1)/sqrt(s^2 + tau^2);
       z_D > 3.090: outside the normal spread among customers, not just beyond chance.
     Also the empirical-Bayes STR (gamma-Poisson, alpha by moments).
  F6 Machines. Flagged = >= 5 tickets AND Poisson BH q < 0.05 against E (model + age), BH over machines with E > 0.
  F7 Consistent outliers. The period is split at its midpoint, 2026-02-15 (H1 = 2025-08-01..2026-02-14,
     H2 = 2026-02-15..2026-08-31); each half's expected uses rates fitted within that half (model + age).
     Variants (12) = (expected: model | model+age | model+age+coverage) x (tickets | 7-day episodes)
       x (all unplanned | excluding monitoring-template and No Trouble Found tickets).
     Customers and machines: flagged (F5 Poisson rule / F6 rule) in >= 10 of the 12 variants AND one-sided Poisson
       p < 0.05 (O vs E) in each half. Consistently low customers: Poisson lower-tail BH q < 0.05 on the full period
       and lower-tail p < 0.05 in each half.
     Models: bootstrap 95% CI of the rate ratio to the fleet above 1 in both halves (below 1 in both = consistently
       low).
     Persistence statistics (customers with E >= 3 in each half) are compared with two nulls: a stratified
     permutation (second-half results shuffled among customers in the same decile of second-half expected tickets:
     heterogeneity, but not persistent) and Poisson draws from each half's expected (no heterogeneity at all).
     Machines: second-half O/E by first-half ticket count, against a permutation of first-half counts within
     model-group x age-band cells.
  F8 Uncertainty. Rates get Byar's 95% Poisson interval and a cluster bootstrap (accounts resampled with
     replacement, N_BOOT draws, seed 15072); tickets cluster within accounts, so the bootstrap interval is the one
     to read.

Privacy: outputs in verification/outputs/fleet/ hold only pseudonyms (Customer NNN, S#####, M#####), model,
type, category and status labels, and aggregates. Accounts and serials that never appear on a ticket get new
pseudonyms after the existing ones (common.extend_maps), so existing labels do not change. Real names for the
real-name chart variants go only to data/private/fx_private_customer_names.csv (gitignored). A final check
(text_leaks) scans every public text column for real serials, account names, case numbers and equipment-list
strings (addresses, cities, zips, phones).

Run:  cd /home/user/analytics-lab && python3 -I verification/fleet_exposure.py
Deterministic: fixed seed, stable sorts. Exit status 1 if any check fails.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common  # noqa: E402
import high_ticket_machines as H  # noqa: E402
from common import OUTPUTS, PRIVATE  # noqa: E402
from flags import monitoring_template  # noqa: E402

OUT = OUTPUTS / 'fleet'
DB_OUT = OUT / 'db'
PREFIX = 'fx_'
SEED = H.SEED
N_BOOT = 2000
N_NULL = 1000
MIN_TYPE_MONTHS = H.MIN_TYPE_MONTHS
Q_CUT = H.Q_CUT
MONTH_DAYS = 365.25 / 12
PERIOD_START = pd.Timestamp('2025-08-01')
PERIOD_END = pd.Timestamp('2026-09-01')          # exclusive
SPLIT = PERIOD_START + (PERIOD_END - PERIOD_START) / 2
SPLIT = SPLIT.normalize()                         # 2026-02-15
AGE_EDGES = [-np.inf, 1, 2, 4, 6, 8, 10, np.inf]
AGE_LABELS = ['<1', '1-2', '2-4', '4-6', '6-8', '8-10', '10+']
POOL = 'Other models (<100 months each)'
EPISODE_GAP_DAYS = 7
MIN_FLAG_TICKETS = 5
Z95, Z998 = 1.959964, 3.090232
MIN_VARIANTS = 10
VARIANT_EXPECTED = {'model': ['rate_group'], 'model_age': ['rate_group', 'age_band'],
                    'model_age_coverage': ['rate_group', 'age_band', 'service_status']}
VARIANT_COUNTS = ('tickets', 'episodes')
VARIANT_SCOPES = ('all', 'core')
PUBLIC = {}
FACTS = {}
check = H.check


def save(df, name):
    path = OUT / f'{PREFIX}{name}.csv'
    df.to_csv(path, index=False)
    PUBLIC[name] = df
    print(f'  wrote {path.relative_to(OUTPUTS.parents[1])} ({len(df):,} rows)')
    return df


def r(x, nd=4):
    return H.r(x, nd)


def text_leaks(df, real):
    """Real identifiers in the text columns of df (see load_inputs for the two kinds). Numeric columns hold counts
    and rates and are not tested; every id column in the public tables is text."""
    out = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            continue
        hits = set()
        for v in df[col].dropna().astype(str).unique():
            if v in real['digit'] or v in real['text']:
                hits.add(v)
            hits.update(t for t in re.findall(r'[A-Za-z0-9][A-Za-z0-9 .&\'-]*[A-Za-z0-9]', v) if t in real['text'])
            hits.update(t for t in re.findall(r'[A-Za-z0-9]+', v) if t in real['text'])
        if hits:
            out[col] = len(hits)
    return out


# ----------------------------------------------------------------------------------------------------------------
# Statistics helpers (numpy only)
# ----------------------------------------------------------------------------------------------------------------
def byar(k, z=Z95):
    """Byar's approximation to the exact Poisson interval for a count k (within 1% for k >= 5)."""
    k = np.asarray(k, float)
    lo = np.where(k > 0, k * (1 - 1 / (9 * np.maximum(k, 1)) - z / (3 * np.sqrt(np.maximum(k, 1)))) ** 3, 0.0)
    hi = (k + 1) * (1 - 1 / (9 * (k + 1)) + z / (3 * np.sqrt(k + 1))) ** 3
    return lo, hi


def ipf_expected(df, count, factors, months='months', iters=500, tol=1e-9):
    """Poisson main-effects fit by iterative proportional fitting.

    E_i = months_i x prod_f a_f[level_i(f)], scaled so that sum(E) = sum(count) within every level of every factor.
    A level with no observed tickets gets expected 0 (its rate is 0).
    """
    e = df[months].astype(float) * (df[count].sum() / df[months].sum())
    for _ in range(iters):
        worst = 0.0
        for f in factors:
            obs = df.groupby(f, observed=True)[count].sum()
            exp = e.groupby(df[f], observed=True).sum()
            adj = (obs / exp).where(exp > 0, 0.0)
            e = e * df[f].map(adj).astype(float).fillna(0.0)
            worst = max(worst, float((obs - exp).abs().max()))
        if worst < tol:
            break
    return e.to_numpy()


def funnel(O, E, winsor=0.10):
    """Overdispersion-adjusted funnel z (Spiegelhalter 2005, square-root scale, additive random effects).

    Returns z_D (NaN where E == 0), tau^2 and phi (the winsorised dispersion)."""
    O, E = np.asarray(O, float), np.asarray(E, float)
    ok = E > 0
    y = np.sqrt(np.where(ok, O / np.where(ok, E, 1), np.nan))
    s = np.where(ok, 1 / (2 * np.sqrt(np.where(ok, E, 1))), np.nan)
    z = (y - 1) / s
    lo, hi = np.nanpercentile(z[ok], [100 * winsor, 100 * (1 - winsor)])
    zw = np.clip(z[ok], lo, hi)
    n = int(ok.sum())
    phi = float(np.mean(zw ** 2))
    w = 1 / s[ok] ** 2
    tau2 = max(0.0, (n * phi - (n - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    zd = (y - 1) / np.sqrt(s ** 2 + tau2)
    return zd, tau2, phi


def funnel_limit(E, tau2, z):
    """STR control limits at expected count E for a funnel with between-unit variance tau2 (sqrt scale)."""
    E = np.asarray(E, float)
    half = z * np.sqrt(1 / (4 * E) + tau2)
    return np.maximum(0.0, 1 - half) ** 2, (1 + half) ** 2


def eb_alpha(O, E):
    """Gamma-Poisson dispersion by moments: Var(O) = E + alpha E^2 (alpha >= 0)."""
    O, E = np.asarray(O, float), np.asarray(E, float)
    ok = E > 0
    return max(0.0, float(np.sum((O[ok] - E[ok]) ** 2 - E[ok]) / np.sum(E[ok] ** 2)))


def spearman(a, b):
    a = pd.Series(a).rank().to_numpy()
    b = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(a, b)[0, 1])


def boot_weights(n_clusters, n_boot=N_BOOT, seed=SEED):
    """Cluster bootstrap: how many times each cluster is drawn in each resample (n_boot x n_clusters)."""
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_clusters, np.full(n_clusters, 1 / n_clusters), size=n_boot).astype(float)


def pct_ci(a, axis=0):
    lo, hi = np.nanpercentile(a, [2.5, 97.5], axis=axis)
    return lo, hi


# ----------------------------------------------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------------------------------------------
def load_inputs():
    raw, maps, cases, conn = common.load_all()
    sc = pd.read_sql('SELECT * FROM service_cases', conn)
    eq = common.load_equipment()
    maps = common.extend_maps(maps, eq)
    inv_serial = {v: k for k, v in maps['serial'].items()}
    case_text = dict(zip(raw['Case Number'].map(common.clean).map(maps['case']), raw['Trouble Reported']))
    sc['serial'] = sc.machine_id.map(inv_serial)
    sc['ts'] = pd.to_datetime(sc.opened_at)
    sc['monitoring'] = sc.case_id.map(case_text).map(monitoring_template)
    sc['core'] = ~sc.monitoring & (sc.service_group != 'No Trouble Found')
    # Identifiers that are digits (serials, case numbers, zips, phones) are leaks as whole cells; text identifiers
    # (account names, addresses, cities, location labels) as whole cells or as tokens of 4+ characters.
    # Location and poll-position numbers ('2', '08') are room and slot labels, not identifiers.
    text_cols = ['Account Name', 'Hospital Address', 'Hospital City', 'Location', 'Vendor Credentialing Notes']
    digit_cols = ['Serial Number', 'Hospital Zip Code', 'Phone']
    real = {'digit': set(map(str, maps['serial'])) | set(map(str, maps['case']))
            | set(common.equipment_real_strings(columns=digit_cols)),
            'text': {s for s in set(map(str, maps['account'])) | common.equipment_real_strings(columns=text_cols)
                     if not s.isdigit() and len(s) >= 4}}
    htm = pd.read_csv(OUTPUTS / 'htm_device_exposure.csv')
    fxdb = pd.read_csv(DB_OUT / 'fxdb_devices.csv') if (DB_OUT / 'fxdb_devices.csv').exists() else None
    return raw, maps, sc, eq, real, htm, fxdb


def months_between(start, end):
    return ((end - start).dt.days.clip(lower=0) / MONTH_DAYS).astype(float)


def machine_frame(eq, maps, sc):
    """One row per listed machine: pseudonyms, attributes, exposure (full period and halves), ticket counts."""
    m = pd.DataFrame({'serial': eq.serial, 'serial_id': eq.serial.map(maps['serial']),
                      'customer': eq.account.map(maps['account']), 'model': eq.model, 'family': eq.family,
                      'service_status': eq.service_status, 'service_plan': eq.service_plan,
                      'ownership': eq.ownership, 'country': eq.country,
                      'install_date': eq.install_date, 'go_live_date': eq.go_live_date})
    t = sc[sc.serial.isin(set(m.serial)) & (sc.ts >= PERIOD_START) & (sc.ts < PERIOD_END)].copy()
    first = t.groupby('serial').ts.min().dt.normalize()
    m['first_ticket'] = m.serial.map(first)
    m['ticket_before_install'] = m.first_ticket < m.install_date.dt.normalize()
    start_inst = m[['install_date', 'first_ticket']].min(axis=1)
    m['start'] = start_inst.clip(lower=PERIOD_START)
    live = m.go_live_date.fillna(m.install_date)
    m['start_live'] = pd.concat([live, m.first_ticket], axis=1).min(axis=1).clip(lower=PERIOD_START)
    end = pd.Series(PERIOD_END, index=m.index)
    m['months'] = months_between(m.start, end)
    m['months_live'] = months_between(m.start_live, end)
    m['months_h1'] = months_between(m.start, pd.Series(SPLIT, index=m.index).where(m.start < SPLIT, m.start))
    m['months_h2'] = months_between(m.start.clip(lower=SPLIT), end)
    mid = m.start + (end - m.start) / 2
    m['age_years'] = ((mid - m.install_date).dt.days / 365.25).clip(lower=0)
    m['age_band'] = pd.Categorical(pd.cut(m.age_years, AGE_EDGES, labels=AGE_LABELS, right=False),
                                   categories=AGE_LABELS, ordered=True)

    # Ticket counts: all / core, full / halves, and 7-day episodes.
    def count(frame):
        return m.serial.map(frame.groupby('serial').size()).fillna(0).astype(int)
    h1, h2 = t.ts < SPLIT, t.ts >= SPLIT
    m['tickets'] = count(t)
    m['tickets_h1'] = count(t[h1])
    m['tickets_h2'] = count(t[h2])
    m['tickets_core'] = count(t[t.core])
    for scope, frame in (('', t), ('_core', t[t.core])):
        s = frame.sort_values(['serial', 'ts', 'case_id'], kind='mergesort')
        gap = s.groupby('serial').ts.diff().dt.total_seconds() / 86400
        new = gap.isna() | (gap > EPISODE_GAP_DAYS)
        m[f'episodes{scope}'] = m.serial.map(new.groupby(s.serial).sum()).fillna(0).astype(int)
    model_months = m.groupby('model').months.sum()
    m['rate_group'] = np.where(m.model.map(model_months) >= MIN_TYPE_MONTHS, m.model, POOL)
    return m, t


# ----------------------------------------------------------------------------------------------------------------
# Rates by group with Byar and cluster-bootstrap intervals
# ----------------------------------------------------------------------------------------------------------------
def group_rates(m, by, W, accounts, tickets='tickets', months='months', extra=None):
    """Rates per 100 months for each level of `by`, with Byar and account-bootstrap CIs and the ratio to the fleet."""
    acc_idx = m.customer.map({a: i for i, a in enumerate(accounts)}).to_numpy()
    levels = sorted(m[by].dropna().unique(), key=str)
    lev_idx = m[by].map({v: i for i, v in enumerate(levels)}).to_numpy()
    G, A = len(levels), len(accounts)
    T = np.zeros((G, A))
    M = np.zeros((G, A))
    np.add.at(T, (lev_idx, acc_idx), m[tickets].to_numpy(float))
    np.add.at(M, (lev_idx, acc_idx), m[months].to_numpy(float))
    Tb, Mb = W @ T.T, W @ M.T
    with np.errstate(invalid='ignore', divide='ignore'):
        rate_b = Tb / Mb
        fleet_b = Tb.sum(1) / Mb.sum(1)
        ratio_b = rate_b / fleet_b[:, None]
    fleet = m[tickets].sum() / m[months].sum()
    g = m.groupby(by, observed=True).agg(machines=('serial', 'size'), months=(months, 'sum'),
                                         tickets=(tickets, 'sum'),
                                         machines_with_ticket=(tickets, lambda s: int((s > 0).sum())),
                                         accounts=('customer', 'nunique')).reindex(levels)
    g['rate_per_100'] = 100 * g.tickets / g.months
    lo, hi = byar(g.tickets)
    g['byar_lo'] = 100 * lo / g.months
    g['byar_hi'] = 100 * hi / g.months
    blo, bhi = pct_ci(rate_b)
    g['boot_lo'], g['boot_hi'] = 100 * blo, 100 * bhi
    g['ratio_to_fleet'] = g.rate_per_100 / (100 * fleet)
    rlo, rhi = pct_ci(ratio_b)
    g['ratio_boot_lo'], g['ratio_boot_hi'] = rlo, rhi
    g['vs_fleet'] = np.select([g.ratio_boot_lo > 1, g.ratio_boot_hi < 1], ['above', 'below'], 'not different')
    g['share_of_machines'] = g.machines / g.machines.sum()
    g['share_of_months'] = g.months / g.months.sum()
    g['share_of_tickets'] = g.tickets / g.tickets.sum()
    g['share_machines_with_ticket'] = g.machines_with_ticket / g.machines
    if extra is not None:
        g = g.join(extra)
    g.index.name = by
    return g.reset_index(), float(fleet)


def adjusted_ratio(m, by, expected_col, W, accounts):
    """O / E per level of `by` (E from another adjustment, e.g. age only), with an account-bootstrap CI."""
    acc_idx = m.customer.map({a: i for i, a in enumerate(accounts)}).to_numpy()
    levels = sorted(m[by].dropna().unique(), key=str)
    lev_idx = m[by].map({v: i for i, v in enumerate(levels)}).to_numpy()
    T = np.zeros((len(levels), len(accounts)))
    Ex = np.zeros_like(T)
    np.add.at(T, (lev_idx, acc_idx), m.tickets.to_numpy(float))
    np.add.at(Ex, (lev_idx, acc_idx), m[expected_col].to_numpy(float))
    with np.errstate(invalid='ignore', divide='ignore'):
        rb = (W @ T.T) / (W @ Ex.T)
    lo, hi = pct_ci(rb)
    point = T.sum(1) / Ex.sum(1)
    return pd.DataFrame({by: levels, 'age_adjusted_ratio': point, 'age_adjusted_lo': lo, 'age_adjusted_hi': hi})


# ----------------------------------------------------------------------------------------------------------------
# Customers: funnel, EB, variants
# ----------------------------------------------------------------------------------------------------------------
def upper_p(O, E):
    """One-sided Poisson P(X >= O | E); NaN where E == 0."""
    return np.array([H.poisson_sf(o, e) if e > 0 else np.nan for o, e in zip(O, E)])


def lower_p(O, E):
    """One-sided Poisson P(X <= O | E); NaN where E == 0."""
    return np.array([1.0 - H.poisson_sf(o + 1, e) if e > 0 else np.nan for o, e in zip(O, E)])


def poisson_flags(O, E):
    """Customer flag on the Poisson rule used for machines: >= 5 tickets and BH q < 0.05 (over units with E > 0)."""
    O, E = pd.Series(O), pd.Series(E)
    pos = E > 0
    q = pd.Series(np.nan, index=O.index)
    q[pos] = H.bh(upper_p(O[pos], E[pos]))
    return (O >= MIN_FLAG_TICKETS) & (q < Q_CUT)


def critical_count(E, level=0.05):
    """Smallest count k with P(X >= k | E) < level, per unit (so a simulated count is significant iff >= k)."""
    out = []
    for e in np.asarray(E, float):
        k = int(e)
        while H.poisson_sf(k, e) >= level:
            k += 1
        while k > 0 and H.poisson_sf(k - 1, e) < level:
            k -= 1
        out.append(k)
    return np.array(out)


def customer_table(m, count, expected):
    c = m.assign(_o=m[count], _e=expected).groupby('customer').agg(O=('_o', 'sum'), E=('_e', 'sum'))
    zd, tau2, phi = funnel(c.O, c.E)
    c['z_d'] = zd
    return c, tau2, phi


def variant_expected(m, count, scope_col, factors):
    d = m.assign(_c=m[scope_col])
    return ipf_expected(d, '_c', factors)


# ----------------------------------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------------------------------
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    print('Loading inputs')
    raw, maps, sc, eq, real, htm, fxdb = load_inputs()
    m, t = machine_frame(eq, maps, sc)
    accounts = sorted(m.customer.unique())
    W = boot_weights(len(accounts))

    # ------------------------------------------------------------------ Match between tickets and the list
    print('Match')
    in_period = sc[(sc.ts >= PERIOD_START) & (sc.ts < PERIOD_END)]
    listed = set(m.serial)
    all_rows = raw.assign(serial=raw['Serial #'].map(common.clean), account=raw['Account Name'].map(common.clean),
                          model=raw['Model #'].map(common.clean))
    match = all_rows.merge(eq[['serial', 'account', 'model']], on='serial', how='inner', suffixes=('', '_list'))
    unl = in_period[~in_period.serial.isin(listed)]
    rows = [('ticket rows (all case types)', len(all_rows)),
            ('ticket rows whose serial is on the list', int(all_rows.serial.isin(listed).sum())),
            ('ticket serials', all_rows.serial.nunique()),
            ('ticket serials on the list', int(all_rows.serial.drop_duplicates().isin(listed).sum())),
            ('matched rows: ticket account = list account', int((match.account == match.account_list).sum())),
            ('matched rows: ticket model = list model', int((match.model == match.model_list).sum())),
            ('matched rows', len(match)),
            ('unplanned tickets in period', len(in_period)),
            ('unplanned tickets on listed machines', int(in_period.serial.isin(listed).sum())),
            ('unplanned tickets on unlisted serials', len(unl)),
            ('unlisted serials with unplanned tickets', unl.serial.nunique()),
            ('listed machines', len(m)),
            ('listed accounts', m.customer.nunique()),
            ('listed machines installed after the period (0 months)', int((m.months == 0).sum())),
            ('tickets opened before the install date', int((t.ts.dt.normalize() < t.serial.map(
                m.set_index('serial').install_date.dt.normalize())).sum())),
            ('machines whose exposure starts at a pre-install ticket', int(m.ticket_before_install.sum()))]
    match_t = pd.DataFrame(rows, columns=['measure', 'value'])
    by_month = in_period.assign(month=in_period.ts.dt.strftime('%Y-%m'), unlisted=~in_period.serial.isin(listed)) \
        .groupby('month').agg(tickets=('case_id', 'size'), unlisted=('unlisted', 'sum')).reset_index()
    by_month['unlisted_share'] = by_month.unlisted / by_month.tickets
    by_rt = unl.groupby('record_type').size().rename('unplanned_tickets').reset_index() \
        .sort_values(['unplanned_tickets', 'record_type'], ascending=[False, True])
    save(match_t, 'match')
    save(by_month, 'unlisted_by_month')
    save(by_rt, 'unlisted_by_record_type')
    check('every listed serial is unique', len(eq), eq.serial.nunique())
    check('every unplanned ticket in period is either listed or unlisted', len(in_period),
          int(in_period.serial.isin(listed).sum()) + len(unl))
    check('machine-frame tickets = unplanned tickets on listed machines', int(in_period.serial.isin(listed).sum()),
          int(m.tickets.sum()))
    check('halves sum to the full period (tickets)', int(m.tickets.sum()), int(m.tickets_h1.sum() + m.tickets_h2.sum()))
    check('halves sum to the full period (months)', float(m.months.sum()), float(m.months_h1.sum() + m.months_h2.sum()),
          tol=1e-6)

    # ------------------------------------------------------------------ Expected counts
    print('Expected counts (IPF)')
    m['E_model'] = ipf_expected(m, 'tickets', ['rate_group'])
    m['E'] = ipf_expected(m, 'tickets', ['rate_group', 'age_band'])
    m['E_cov'] = ipf_expected(m, 'tickets', ['rate_group', 'age_band', 'service_status'])
    m['E_age'] = ipf_expected(m, 'tickets', ['age_band'])
    for h in ('h1', 'h2'):
        d = m.assign(months=m[f'months_{h}'])
        m[f'E_{h}'] = ipf_expected(d, f'tickets_{h}', ['rate_group', 'age_band'])
    for col in ('E_model', 'E', 'E_cov', 'E_age'):
        check(f'{col}: expected total = observed total', int(m.tickets.sum()), float(m[col].sum()), tol=1e-3)
    for f in ('rate_group', 'age_band'):
        worst = float((m.groupby(f, observed=True).tickets.sum() - m.groupby(f, observed=True).E.sum()).abs().max())
        check(f'E (model + age) matches observed within every {f}', 0.0, worst, tol=1e-3)
    check('fleet STR = 1', 1.0, float(m.tickets.sum() / m.E.sum()), tol=1e-9)

    # ------------------------------------------------------------------ Rates by group
    print('Rates by model, family, age, coverage, plan, country')
    fleet_rate = 100 * m.tickets.sum() / m.months.sum()
    age_adj = adjusted_ratio(m, 'model', 'E_age', W, accounts).set_index('model')
    models, _ = group_rates(m, 'model', W, accounts, extra=age_adj)
    models['family'] = models.model.map(m.groupby('model').family.first())
    models['own_rate'] = models.months >= MIN_TYPE_MONTHS
    models = models.sort_values(['tickets', 'model'], ascending=[False, True])
    save(models, 'model_rates')
    fams, _ = group_rates(m, 'family', W, accounts)
    save(fams.sort_values(['tickets', 'family'], ascending=[False, True]), 'family_rates')
    ages, _ = group_rates(m, 'age_band', W, accounts)
    ages['age_band'] = pd.Categorical(ages.age_band, AGE_LABELS, ordered=True)
    save(ages.sort_values('age_band'), 'age_rates')
    cov, _ = group_rates(m, 'service_status', W, accounts)
    save(cov.sort_values(['months', 'service_status'], ascending=[False, True]), 'coverage_rates')
    plan, _ = group_rates(m, 'service_plan', W, accounts)
    save(plan.sort_values(['months', 'service_plan'], ascending=[False, True]), 'service_plan_rates')
    ctry, _ = group_rates(m, 'country', W, accounts)
    save(ctry, 'country_rates')
    rg, _ = group_rates(m, 'rate_group', W, accounts)
    check('model rates: tickets sum to fleet', int(m.tickets.sum()), int(models.tickets.sum()))
    check('model rates: months sum to fleet', float(m.months.sum()), float(models.months.sum()), tol=1e-6)
    check('age rates: tickets sum to fleet', int(m.tickets.sum()), int(ages.tickets.sum()))

    # Model consistency across halves (rate ratio to each half's fleet rate).
    halves = []
    for h in ('h1', 'h2'):
        g, _ = group_rates(m, 'rate_group', W, accounts, tickets=f'tickets_{h}', months=f'months_{h}')
        halves.append(g.set_index('rate_group')[['months', 'tickets', 'rate_per_100', 'ratio_to_fleet',
                                                 'ratio_boot_lo', 'ratio_boot_hi', 'vs_fleet']].add_suffix(f'_{h}'))
    mo = rg.set_index('rate_group')[['machines', 'months', 'tickets', 'rate_per_100', 'ratio_to_fleet',
                                     'ratio_boot_lo', 'ratio_boot_hi', 'vs_fleet']].join(halves)
    mo['consistent'] = np.select([(mo.vs_fleet_h1 == 'above') & (mo.vs_fleet_h2 == 'above'),
                                  (mo.vs_fleet_h1 == 'below') & (mo.vs_fleet_h2 == 'below')],
                                 ['consistently above', 'consistently below'], 'not consistent')
    mo = mo.reset_index().sort_values(['ratio_to_fleet', 'rate_group'], ascending=[False, True])
    save(mo, 'outlier_models')

    # ------------------------------------------------------------------ Telemetry types
    print('Telemetry types')
    if fxdb is not None:
        basis = 'installed'
        d = fxdb[fxdb.on_list.astype(bool)].merge(m, on='serial_id', how='inner')
        d['machine_type'] = d.machine_type.fillna('Unknown').str.strip().str.lower()
        types, _ = group_rates(d, 'machine_type', W, accounts)
        net = m.assign(networked=np.where(m.serial_id.isin(set(fxdb.loc[fxdb.on_list.astype(bool), 'serial_id'])),
                                          'networked', 'not networked'))
        netr, _ = group_rates(net, 'networked', W, accounts)
        save(netr, 'networked_rates')
        cross = d.groupby(['model', 'machine_type']).size().rename('machines').reset_index()
        save(cross, 'model_type_crosswalk')
    else:
        basis = 'telemetry-span'
        d = htm[htm.months > 0].copy()
        d['customer'] = d.customer.fillna(d.host.fillna('(no host)'))
        d = d.rename(columns={'tickets_obs': 'tickets', 'machine_id': 'serial'})
        acc_t = sorted(d.customer.unique())
        types, _ = group_rates(d, 'machine_type', boot_weights(len(acc_t)), acc_t)
    types['exposure_basis'] = basis
    types['own_rate'] = types.months >= MIN_TYPE_MONTHS
    save(types.sort_values(['tickets', 'machine_type'], ascending=[False, True]), 'type_rates')
    FACTS['type_exposure_basis'] = basis

    # ------------------------------------------------------------------ Customers
    print('Customers')
    c, tau2, phi = customer_table(m, 'tickets', m.E)
    c['E_model'] = m.groupby('customer').E_model.sum()
    c['E_coverage'] = m.groupby('customer').E_cov.sum()
    c['machines'] = m.groupby('customer').size()
    c['months'] = m.groupby('customer').months.sum()
    c['machines_with_ticket'] = m.groupby('customer').tickets.apply(lambda s: int((s > 0).sum()))
    c['rate_per_100'] = np.where(c.months > 0, 100 * c.O / c.months.where(c.months > 0, 1), np.nan)
    c['STR'] = np.where(c.E > 0, c.O / c.E.where(c.E > 0, 1), np.nan)
    c['STR_model_only'] = np.where(c.E_model > 0, c.O / c.E_model.where(c.E_model > 0, 1), np.nan)
    lo, hi = byar(c.O)
    c['STR_lo'] = np.where(c.E > 0, lo / c.E.where(c.E > 0, 1), np.nan)
    c['STR_hi'] = np.where(c.E > 0, hi / c.E.where(c.E > 0, 1), np.nan)
    alpha = eb_alpha(c.O, c.E)
    k = 1 / alpha if alpha > 0 else np.inf
    c['STR_eb'] = np.where(c.E > 0, (c.O + k) / (c.E + k), np.nan) if np.isfinite(k) else c.STR
    c['above_95'] = c.z_d > Z95
    c['flagged'] = c.z_d > Z998
    c['below_998'] = c.z_d < -Z998
    pos = c.E > 0
    c['p_poisson'] = np.nan
    c.loc[pos, 'p_poisson'] = [H.poisson_sf(o, e) for o, e in zip(c.O[pos], c.E[pos])]
    c['q_poisson'] = np.nan
    c.loc[pos, 'q_poisson'] = H.bh(c.loc[pos, 'p_poisson'].to_numpy())
    c['q_poisson_low'] = np.nan
    c.loc[pos, 'q_poisson_low'] = H.bh(lower_p(c.O[pos], c.E[pos]))
    c['poisson_flagged'] = poisson_flags(c.O, c.E)
    cov_mix = m.pivot_table(index='customer', columns='service_status', values='months', aggfunc='sum',
                            fill_value=0.0)
    cov_mix = cov_mix.div(cov_mix.sum(axis=1).where(cov_mix.sum(axis=1) > 0, 1), axis=0)
    cov_mix.columns = ['months_share_' + str(x).lower().replace(' ', '_') for x in cov_mix.columns]
    c = c.join(cov_mix)
    top_model = m.groupby(['customer', 'model']).months.sum().reset_index() \
        .sort_values(['customer', 'months', 'model'], ascending=[True, False, True]).drop_duplicates('customer')
    c['top_model'] = top_model.set_index('customer').model
    c['top_model_months_share'] = top_model.set_index('customer').months / c.months.where(c.months > 0, 1)
    check('customer O sums to fleet', int(m.tickets.sum()), int(c.O.sum()))
    check('customer E sums to fleet', int(m.tickets.sum()), float(c.E.sum()), tol=1e-3)
    FACTS['customer_funnel'] = {'tau2': tau2, 'phi_winsorised': phi, 'eb_alpha': alpha,
                                'customers_with_E': int(pos.sum()), 'flagged_998': int(c.flagged.sum()),
                                'above_95': int(c.above_95.sum()), 'below_998': int(c.below_998.sum()),
                                'poisson_q_lt_0.05_high': int(((c.q_poisson < Q_CUT) & (c.O > c.E)).sum())}

    # Go-live sensitivity: same fit with go-live exposure.
    ml = m.assign(months=m.months_live)
    El = ipf_expected(ml, 'tickets', ['rate_group', 'age_band'])
    cl, tau2l, _ = customer_table(ml, 'tickets', El)
    FACTS['go_live_sensitivity'] = {'fleet_rate_per_100': 100 * m.tickets.sum() / m.months_live.sum(),
                                    'months': float(m.months_live.sum()), 'flagged_998': int((cl.z_d > Z998).sum()),
                                    'flagged_overlap_with_main': int(((cl.z_d > Z998) & c.flagged).sum())}

    # ------------------------------------------------------------------ Variants (customers and machines)
    print('Variants (12) for customers and machines')
    scope_col = {('tickets', 'all'): 'tickets', ('tickets', 'core'): 'tickets_core',
                 ('episodes', 'all'): 'episodes', ('episodes', 'core'): 'episodes_core'}
    c['variants_flagged'] = 0          # Poisson rule (BH q < 0.05 and >= 5 tickets), as for machines
    c['variants_funnel'] = 0           # beyond the 99.8% overdispersion-adjusted funnel limit
    m['variants_flagged'] = 0
    variant_rows = []
    for ename, factors in VARIANT_EXPECTED.items():
        for cnt in VARIANT_COUNTS:
            for scope in VARIANT_SCOPES:
                col = scope_col[(cnt, scope)]
                e = variant_expected(m, cnt, col, factors)
                cv, tv, _ = customer_table(m, col, e)
                fl = cv.z_d > Z998
                c['variants_funnel'] += fl.reindex(c.index).fillna(False).astype(int)
                cf = poisson_flags(cv.O, cv.E)
                c['variants_flagged'] += cf.reindex(c.index).fillna(False).astype(int)
                p = np.where(e > 0, [H.poisson_sf(o, x) if x > 0 else 1.0 for o, x in zip(m[col], e)], np.nan)
                q = np.full(len(m), np.nan)
                q[e > 0] = H.bh(p[e > 0])
                mf = (m[col].to_numpy() >= MIN_FLAG_TICKETS) & (q < Q_CUT)
                m['variants_flagged'] += mf.astype(int)
                variant_rows.append({'expected': ename, 'count': cnt, 'scope': scope, 'total': int(m[col].sum()),
                                     'tau2': tv, 'customers_flagged': int(cf.sum()),
                                     'customers_beyond_funnel_998': int(fl.sum()), 'machines_flagged': int(mf.sum())})
    variants = save(pd.DataFrame(variant_rows), 'outlier_variants')
    check('12 variants', 12, len(variants))

    # ------------------------------------------------------------------ Halves (customers)
    print('Halves')
    for h in ('h1', 'h2'):
        ch, th, _ = customer_table(m, f'tickets_{h}', m[f'E_{h}'])
        c[f'O_{h}'], c[f'E_{h}'], c[f'z_d_{h}'] = ch.O, ch.E, ch.z_d
        c[f'STR_{h}'] = np.where(ch.E > 0, ch.O / ch.E.where(ch.E > 0, 1), np.nan)
        c[f'above_95_{h}'] = ch.z_d > Z95
        c[f'p_{h}'] = upper_p(ch.O, ch.E)
        c[f'p_low_{h}'] = lower_p(ch.O, ch.E)
        FACTS[f'tau2_{h}'] = th
    c['consistent_outlier'] = (c.variants_flagged >= MIN_VARIANTS) & (c.p_h1 < 0.05) & (c.p_h2 < 0.05)
    c['consistent_low'] = (c.q_poisson_low < Q_CUT) & (c.p_low_h1 < 0.05) & (c.p_low_h2 < 0.05)

    # Persistence statistics vs two nulls, on customers with E >= 3 in each half.
    el = c[(c.E_h1 >= 3) & (c.E_h2 >= 3)].copy()
    rng = np.random.default_rng(SEED)

    def persist_stats(s1, s2, f1, f2):
        top1 = s1 >= np.quantile(s1, 0.9)
        top2 = s2 >= np.quantile(s2, 0.9)
        return spearman(s1, s2), float((top1 & top2).sum() / top1.sum()), int((f1 & f2).sum())

    obs_stats = persist_stats(el.STR_h1.to_numpy(), el.STR_h2.to_numpy(), (el.p_h1 < 0.05).to_numpy(),
                              (el.p_h2 < 0.05).to_numpy())
    dec = pd.qcut(el.E_h2.rank(method='first'), 10, labels=False).to_numpy()
    perm = []
    s2, f2 = el.STR_h2.to_numpy(), (el.p_h2 < 0.05).to_numpy()
    for _ in range(N_NULL):
        idx = np.arange(len(el))
        for g in range(10):
            sel = np.where(dec == g)[0]
            idx[sel] = rng.permutation(sel)
        perm.append(persist_stats(el.STR_h1.to_numpy(), s2[idx], (el.p_h1 < 0.05).to_numpy(), f2[idx]))
    perm = np.array(perm)
    pois = []
    k1, k2 = critical_count(el.E_h1), critical_count(el.E_h2)
    for _ in range(N_NULL):
        o1 = rng.poisson(el.E_h1.to_numpy())
        o2 = rng.poisson(el.E_h2.to_numpy())
        pois.append(persist_stats(o1 / el.E_h1.to_numpy(), o2 / el.E_h2.to_numpy(), o1 >= k1, o2 >= k2))
    pois = np.array(pois)
    prow = []
    for i, name in enumerate(['spearman_STR_h1_h2', 'top_decile_retained_share', 'significant_in_both_halves']):
        prow.append({'level': 'customer', 'statistic': name, 'units': len(el), 'observed': obs_stats[i],
                     'perm_null_median': float(np.median(perm[:, i])),
                     'perm_null_p2_5': float(np.percentile(perm[:, i], 2.5)),
                     'perm_null_p97_5': float(np.percentile(perm[:, i], 97.5)),
                     'perm_p_value': float((np.sum(perm[:, i] >= obs_stats[i]) + 1) / (N_NULL + 1)),
                     'poisson_null_median': float(np.median(pois[:, i])),
                     'poisson_null_p97_5': float(np.percentile(pois[:, i], 97.5))})

    # ------------------------------------------------------------------ Machines: flags, halves, persistence
    print('Machines')
    pos_m = m.E > 0
    m['p_poisson'] = np.nan
    m.loc[pos_m, 'p_poisson'] = [H.poisson_sf(o, e) for o, e in zip(m.tickets[pos_m], m.E[pos_m])]
    m['q_poisson'] = np.nan
    m.loc[pos_m, 'q_poisson'] = H.bh(m.loc[pos_m, 'p_poisson'].to_numpy())
    m['flagged'] = (m.tickets >= MIN_FLAG_TICKETS) & (m.q_poisson < Q_CUT)
    for h in ('h1', 'h2'):
        ph = np.where(m[f'E_{h}'] > 0, [H.poisson_sf(o, e) if e > 0 else 1.0
                                        for o, e in zip(m[f'tickets_{h}'], m[f'E_{h}'])], np.nan)
        m[f'p_{h}'] = ph
    m['consistent_outlier'] = (m.variants_flagged >= MIN_VARIANTS) & (m.p_h1 < 0.05) & (m.p_h2 < 0.05)
    alpha_m = {g: eb_alpha(s.tickets, s.E) for g, s in m[pos_m].groupby('rate_group')}
    m['alpha_nb'] = m.rate_group.map(alpha_m).fillna(0.0)
    m['p_nb'] = np.nan
    m.loc[pos_m, 'p_nb'] = [H.nb_sf(o, e, a) for o, e, a in zip(m.tickets[pos_m], m.E[pos_m], m.alpha_nb[pos_m])]
    m['q_nb'] = np.nan
    m.loc[pos_m, 'q_nb'] = H.bh(m.loc[pos_m, 'p_nb'].to_numpy())

    # Second-half O/E by first-half tickets (machines installed before the split).
    both = m[(m.months_h1 > 0) & (m.months_h2 > 0)].copy()
    both['h1_group'] = pd.cut(both.tickets_h1, [-1, 0, 1, 2, 3, np.inf], labels=['0', '1', '2', '3', '4+'])
    groups = ['0', '1', '2', '3', '4+']
    gi = both.h1_group.map({g: i for i, g in enumerate(groups)}).astype(int).to_numpy()
    acc_b = sorted(both.customer.unique())
    ai = both.customer.map({a: i for i, a in enumerate(acc_b)}).to_numpy()
    O2 = np.zeros((5, len(acc_b)))
    E2 = np.zeros_like(O2)
    np.add.at(O2, (gi, ai), both.tickets_h2.to_numpy(float))
    np.add.at(E2, (gi, ai), both.E_h2.to_numpy(float))
    Wb = boot_weights(len(acc_b))
    with np.errstate(invalid='ignore', divide='ignore'):
        rb = (Wb @ O2.T) / (Wb @ E2.T)
    blo, bhi = pct_ci(rb)
    cell = both.rate_group.astype(str) + '|' + both.age_band.astype(str)
    cells = [np.where(cell.to_numpy() == v)[0] for v in sorted(cell.unique())]
    h1 = both.tickets_h1.to_numpy()
    o2, e2 = both.tickets_h2.to_numpy(float), both.E_h2.to_numpy(float)
    null = []
    for _ in range(N_NULL):
        hp = h1.copy()
        for sel in cells:
            hp[sel] = h1[rng.permutation(sel)]
        g = np.digitize(np.minimum(hp, 4), [0.5, 1.5, 2.5, 3.5])
        null.append([o2[g == i].sum() / e2[g == i].sum() if e2[g == i].sum() > 0 else np.nan for i in range(5)]
                    + [o2[hp >= 3].sum() / e2[hp >= 3].sum()])
    null = np.array(null)
    null3 = null[:, 5]
    null = null[:, :5]
    mp = pd.DataFrame({'first_half_tickets': groups,
                       'machines': both.groupby('h1_group', observed=False).size().reindex(groups).to_numpy(),
                       'second_half_tickets': O2.sum(1), 'second_half_expected': E2.sum(1),
                       'second_half_ratio': O2.sum(1) / E2.sum(1), 'boot_lo': blo, 'boot_hi': bhi,
                       'perm_null_median': np.nanmedian(null, 0), 'perm_null_p2_5': np.nanpercentile(null, 2.5, 0),
                       'perm_null_p97_5': np.nanpercentile(null, 97.5, 0)})
    save(mp, 'outlier_machine_persistence')
    hi3 = both.tickets_h1 >= 3
    obs3 = float(both.tickets_h2[hi3].sum() / both.E_h2[hi3].sum())
    prow.append({'level': 'machine', 'statistic': 'second_half_ratio_if_3plus_first_half', 'units': int(hi3.sum()),
                 'observed': obs3, 'perm_null_median': float(np.median(null3)),
                 'perm_null_p2_5': float(np.percentile(null3, 2.5)),
                 'perm_null_p97_5': float(np.percentile(null3, 97.5)),
                 'perm_p_value': float((np.sum(null3 >= obs3) + 1) / (N_NULL + 1)),
                 'poisson_null_median': 1.0, 'poisson_null_p97_5': np.nan})
    prow.append({'level': 'machine', 'statistic': 'spearman_OE_h1_h2', 'units': int(((both.E_h1 > 0.3)
                                                                                      & (both.E_h2 > 0.3)).sum()),
                 'observed': spearman((both.tickets_h1 / both.E_h1)[(both.E_h1 > 0.3) & (both.E_h2 > 0.3)],
                                      (both.tickets_h2 / both.E_h2)[(both.E_h1 > 0.3) & (both.E_h2 > 0.3)]),
                 'perm_null_median': np.nan, 'perm_null_p2_5': np.nan, 'perm_null_p97_5': np.nan,
                 'perm_p_value': np.nan, 'poisson_null_median': np.nan, 'poisson_null_p97_5': np.nan})
    persistence = save(pd.DataFrame(prow), 'outlier_persistence')

    # Overlap with the 113 machines flagged in docs/05 (telemetry-span exposure).
    chronic = htm[htm['class'] == 'chronic_outlier']
    m['in_docs05_113'] = m.serial_id.isin(set(chronic.serial_id))
    span = chronic.set_index('serial_id').months
    m['docs05_span_months'] = m.serial_id.map(span)
    short = chronic[chronic.months < 12].serial_id
    sm = m[m.serial_id.isin(set(short))]
    FACTS['docs05_overlap'] = {
        'docs05_flagged': int(len(chronic)), 'on_list': int(m.in_docs05_113.sum()),
        'flagged_now': int((m.in_docs05_113 & m.flagged).sum()),
        'consistent_now': int((m.in_docs05_113 & m.consistent_outlier).sum()),
        'short_span_flagged': int(len(short)), 'short_span_on_list': int(len(sm)),
        'short_span_installed_during_period': int((sm.install_date >= PERIOD_START).sum()),
        'short_span_installed_before_period': int((sm.install_date < PERIOD_START).sum()),
        'short_span_flagged_now': int(sm.flagged.sum())}

    # ------------------------------------------------------------------ Drivers of consistent-outlier customers
    print('Drivers')
    cats = t.assign(customer=t.serial.map(m.set_index('serial').customer),
                    category=t.category.fillna('[Missing]'))
    drv = []
    for cust in sorted(c.index[c.consistent_outlier | c.flagged]):
        mm = m[m.customer == cust].assign(excess=lambda d: d.tickets - d.E)
        exc = float(mm.tickets.sum() - mm.E.sum())
        top2 = mm.sort_values(['excess', 'serial_id'], ascending=[False, True]).head(2)
        cc = cats[cats.customer == cust].category.value_counts()
        cc = cc.sort_index().sort_values(ascending=False, kind='mergesort')
        drv.append({'customer': cust, 'consistent_outlier': bool(c.loc[cust, 'consistent_outlier']),
                    'flagged': bool(c.loc[cust, 'flagged']), 'machines': len(mm),
                    'tickets': int(mm.tickets.sum()), 'expected': float(mm.E.sum()), 'excess': exc,
                    'top2_machines_excess': float(top2.excess.sum()),
                    'top2_share_of_excess': float(top2.excess.sum() / exc) if exc > 0 else np.nan,
                    'machines_above_expected_share': float((mm.tickets > mm.E).mean()),
                    'flagged_machines': int(mm.flagged.sum()),
                    'top_category': cc.index[0] if len(cc) else None,
                    'top_category_share': float(cc.iloc[0] / cc.sum()) if len(cc) else np.nan,
                    'top_model': c.loc[cust, 'top_model'],
                    'months_share_service_contract': c.loc[cust].get('months_share_service_contract', np.nan)})
    drivers = pd.DataFrame(drv)
    if len(drivers):
        drivers['pattern'] = np.where(drivers.top2_share_of_excess >= 0.5, 'a few machines', 'spread across fleet')
    save(drivers, 'outlier_drivers')

    # ------------------------------------------------------------------ Lorenz (customers)
    print('Concentration across customers')
    grid = np.linspace(0, 1, 101)
    nct = int((c.months > 0).sum())
    cc_ = c[c.months > 0]
    obs_l = H.lorenz_top(cc_.O.to_numpy(), grid)
    exp_l = H.lorenz_top(cc_.E.to_numpy(), grid)
    sims = rng.poisson(cc_.E.to_numpy(), size=(N_NULL, nct))
    sim_l = np.array([H.lorenz_top(s, grid) for s in sims])
    lor = pd.DataFrame({'customer_share': grid, 'ticket_share_obs': obs_l, 'expected_share': exp_l,
                        'ticket_share_null_median': np.median(sim_l, 0),
                        'ticket_share_null_p2_5': np.percentile(sim_l, 2.5, 0),
                        'ticket_share_null_p97_5': np.percentile(sim_l, 97.5, 0)})
    save(lor, 'customer_lorenz')
    check('customer lorenz ends at 1', 1.0, round(float(lor.ticket_share_obs.iloc[-1]), 9))

    # ------------------------------------------------------------------ Save customer and machine tables
    cust = c.reset_index().rename(columns={'O': 'tickets', 'E': 'expected', 'E_model': 'expected_model_only',
                                           'E_coverage': 'expected_with_coverage'})
    cust = cust.sort_values(['tickets', 'customer'], ascending=[False, True])
    save(cust, 'customer_rates')
    keep = ['serial_id', 'customer', 'model', 'family', 'rate_group', 'service_status', 'age_band', 'months',
            'months_h1', 'months_h2', 'tickets', 'tickets_h1', 'tickets_h2', 'tickets_core', 'episodes', 'E',
            'E_model', 'E_cov', 'E_h1', 'E_h2', 'p_poisson', 'q_poisson', 'q_nb', 'flagged', 'p_h1', 'p_h2',
            'variants_flagged', 'consistent_outlier', 'in_docs05_113', 'docs05_span_months',
            'ticket_before_install']
    mach = m[keep].assign(install_year=m.install_date.dt.year).rename(
        columns={'E': 'expected', 'E_model': 'expected_model_only', 'E_cov': 'expected_with_coverage',
                 'E_h1': 'expected_h1', 'E_h2': 'expected_h2'})
    mach = mach[(mach.tickets > 0) | mach.in_docs05_113].sort_values(['tickets', 'serial_id'],
                                                                      ascending=[False, True])
    save(mach, 'machine_flags')
    oc = cust[['customer', 'machines', 'tickets', 'expected', 'STR', 'STR_eb', 'z_d', 'flagged', 'variants_flagged',
               'variants_funnel', 'poisson_flagged', 'O_h1', 'E_h1', 'STR_h1', 'p_h1', 'z_d_h1', 'O_h2', 'E_h2',
               'STR_h2', 'p_h2', 'z_d_h2', 'consistent_outlier', 'consistent_low']]
    save(oc[(oc.expected >= 1) | oc.flagged], 'outlier_customers')

    # ------------------------------------------------------------------ Private real names
    names = eq.assign(customer=eq.account.map(maps['account'])).drop_duplicates('customer')[['customer', 'account']]
    top15 = set(cust.head(15).customer)
    wanted = top15 | set(cust[cust.flagged | cust.consistent_outlier].customer)
    priv = names[names.customer.isin(wanted)].rename(columns={'account': 'real_account_name'}) \
        .sort_values('customer')
    priv.to_csv(PRIVATE / 'fx_private_customer_names.csv', index=False)
    print(f'  wrote data/private/fx_private_customer_names.csv ({len(priv)} rows, gitignored)')

    # ------------------------------------------------------------------ Summary
    pm = persistence.set_index('statistic')
    summ = {
        'generated_by': 'verification/fleet_exposure.py', 'seed': SEED, 'n_boot': N_BOOT, 'n_null': N_NULL,
        'definitions': {'period': [str(PERIOD_START.date()), str((PERIOD_END - pd.Timedelta(days=1)).date())],
                        'split': str(SPLIT.date()), 'month_days': MONTH_DAYS, 'min_type_months': MIN_TYPE_MONTHS,
                        'age_bands': AGE_LABELS, 'episode_gap_days': EPISODE_GAP_DAYS,
                        'min_flag_tickets': MIN_FLAG_TICKETS, 'q_cut': Q_CUT, 'z95': Z95, 'z998': Z998,
                        'min_variants': MIN_VARIANTS, 'n_variants': len(variants), 'pool_label': POOL,
                        'equipment_list_date': '2026-10-19'},
        'fleet': {'machines': len(m), 'accounts': int(m.customer.nunique()), 'months': float(m.months.sum()),
                  'tickets': int(m.tickets.sum()), 'rate_per_100': float(fleet_rate),
                  'machines_with_ticket': int((m.tickets > 0).sum()),
                  'machines_zero_months': int((m.months == 0).sum()),
                  'tickets_h1': int(m.tickets_h1.sum()), 'tickets_h2': int(m.tickets_h2.sum()),
                  'rate_h1': float(100 * m.tickets_h1.sum() / m.months_h1.sum()),
                  'rate_h2': float(100 * m.tickets_h2.sum() / m.months_h2.sum())},
        'match': dict(zip(match_t.measure, map(int, match_t.value))),
        'customers': FACTS['customer_funnel'] | {
            'consistent_outliers': int(c.consistent_outlier.sum()), 'consistent_low': int(c.consistent_low.sum()),
            'poisson_flagged': int(c.poisson_flagged.sum()),
            'consistent_outliers_beyond_funnel_998': int((c.consistent_outlier & c.flagged).sum()),
            'flagged_in_10plus_variants': int((c.variants_flagged >= MIN_VARIANTS).sum())},
        'machines': {'flagged': int(m.flagged.sum()), 'flagged_nb': int(((m.q_nb < Q_CUT)
                                                                         & (m.tickets >= MIN_FLAG_TICKETS)).sum()),
                     'consistent_outliers': int(m.consistent_outlier.sum()),
                     'flagged_in_10plus_variants': int((m.variants_flagged >= MIN_VARIANTS).sum())},
        'models': {'consistently_above': sorted(mo.rate_group[mo.consistent == 'consistently above']),
                   'consistently_below': sorted(mo.rate_group[mo.consistent == 'consistently below'])},
        'persistence': {k: {kk: r(v) if isinstance(v, float) else v for kk, v in row.items()}
                        for k, row in pm.to_dict('index').items()},
        'docs05_overlap': FACTS['docs05_overlap'], 'go_live_sensitivity': FACTS['go_live_sensitivity'],
        'type_exposure_basis': basis, 'tau2_h1': FACTS['tau2_h1'], 'tau2_h2': FACTS['tau2_h2']}
    (OUT / f'{PREFIX}summary.json').write_text(json.dumps(summ, indent=2, default=lambda o: r(o, 6)))
    print(f'  wrote verification/outputs/fleet/{PREFIX}summary.json')

    # ------------------------------------------------------------------ Privacy and label checks
    leaks = 0
    for name, df in PUBLIC.items():
        for col, n in text_leaks(df, real).items():
            leaks += n
            print(f'    LEAK in {name}.{col}: {n} values')
    check('public text columns: no real serial / account / case / equipment-list string', 0, leaks)
    labels = pd.concat([cust.customer, mach.customer, mach.serial_id])
    check('customer and serial labels are pseudonyms', True,
          bool(labels.str.fullmatch(r'Customer \d{3,4}|S\d{5}').all()))

    fails = [c_ for c_ in H.CHECKS if c_['status'] != 'PASS']
    print(f'\n{len(H.CHECKS) - len(fails)}/{len(H.CHECKS)} checks pass')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
