#!/usr/bin/env python3
"""Machines that generate an outsized share of unplanned service tickets: workload view vs exposure-adjusted view.

Question: which machines generate an outsized share of service tickets, and are they outliers once we account for
how long they were active and what kind of machine they are?

No database is opened. Everything is computed from the case workbook (via common.load_all) and from the local
outputs of earlier telemetry runs:
  verification/outputs/fu/fu_ticket_last10.csv   case_id -> telemetry machine_id (M#####), 30-day pre-ticket windows
  verification/outputs/fu/fu_devices.csv          device dictionary (type, host, customer, first/last active day)
  verification/outputs/db/db_host_level.csv       identifies the shared internal clearView host's pseudonym
  verification/outputs/db/db_machine_type_rates.csv  Zac's type-level rates (shown for comparison only)

Shared definitions (identical in every build so results are comparable)
  D1 Workload view. Unplanned tickets (Zac's service_cases view: excludes Planned work, Cancelled request,
     Duplicate case; 7,186 tickets) keyed by the case export's serial (pseudonym S#####). Workload-outsized = all
     machines whose count is >= the count of the machine ranked ceil(5% x ticketed machines) (185th of 3,685);
     ties included. A fixed threshold of >= 6 tickets is reported alongside.
  D2 Exposure view. Telemetry devices (M#####) excluding the shared internal host and NULL host. Period
     2025-08-01..2026-07-31 (ticket opened_at date, Eastern). Exposure months = calendar months from
     max(first_active, 2025-08-01) to min(last_active, 2026-07-31) inclusive; 0 if no overlap or not transacting.
     All such devices are included (zero-ticket ones too). Tickets = unplanned tickets in the period linked to a
     population device via case_id. Type rate r_t = sum tickets / sum exposure months per machine type (lower-cased,
     blank -> 'Unknown', as Zac); types with < 100 exposure months share one pooled rate (overall rate if that pool
     has no exposure). LITERAL READING (see Reconciliation): the rate numerator is every population ticket, including
     the 172 tickets on 80 devices with 0 exposure months (mostly non-transacting; sd2.0-49 alone has 117 of them).
     This inflates the pooled small-type rate to 103.7 per 100 months (141 tickets / 136 months). The variant that
     counts only tickets on devices with exposure > 0 is reported in htm_summary.json (exposed_numerator_variant).
     E_i = r_t x months_i (so sum E_i = sum tickets). Poisson upper tail p_i = P(X >= obs_i | E_i) for E_i > 0;
     Benjamini-Hochberg over those devices (m = 6,423), q < 0.05 = rate outlier. Negative-binomial check: one
     dispersion per rate group (each type; the small types share one, as they share the pooled rate), fitted by the
     method of moments on the variance function Var(y) = E + alpha E^2, i.e. alpha = max(0, sum((y - E)^2 - E) /
     sum(E^2)) over devices with E > 0; NB upper tail with mean E and variance E + alpha E^2; BH over the same devices.
     eb_rate = empirical-Bayes (gamma-Poisson) rate per 100 exposure months: 100 r_t (y + 1/alpha) / (E + 1/alpha),
     = 100 r_t when alpha = 0.
  D3 Classes (exposure-population devices): chronic_outlier = workload-outsized (by its serial's D1 count) AND rate
     outlier; high_volume_expected = workload-outsized only; rate_outlier_only = rate outlier only; none.
  D4 Concentration null: 1,000 Poisson draws (numpy default_rng(15072).poisson(E, size=(1000, devices))) with mean
     E_i for EVERY exposure-population device (6,621; zero-exposure devices keep their observed tickets and are
     always 0 in the null). Top-5% share (top ceil(5% x 6,621) = 332 devices), Gini over devices, and devices with
     >= 6 tickets, observed vs simulated. Restricted (E > 0 only) and exposed-numerator variants are in the summary.
  D5 Episodes: per serial, all unplanned tickets sorted by opened_at; a ticket opens a new episode if it is more
     than G days after the previous ticket (G = 7; sensitivity 3 and 14).
  Sensitivity: D1, D2 and D4 rerun without monitoring-template tickets (flags.monitoring_template on Trouble
     Reported).
  Also: C (profile of outsized / chronic machines) and E (pre-ticket telemetry from fu_ticket_last10).

Reconciliation with an independent clean-room build (same D1-D5, written without reading this script)
  Population, D1 and D5 agreed exactly. Three differences were found; each is resolved to the most literal reading
  of the shared definitions:
  1. D2 rate numerator. This script first left the 172 tickets on zero-exposure devices out of r_t (overall 7.30 per
     100 months, 120 Poisson outliers, 114 chronic incl. M07828, 92 high-volume-expected, 6 rate-outlier-only). D2
     says "r_t = sum tickets / sum exposure months" with tickets = all population tickets, so they now stay in the
     numerator (overall 7.54; 118 / 113 / 93 / 5). The old choice is kept as exposed_numerator_variant.
  2. D4 population. This script first simulated only the 6,423 devices with E > 0 (top 5% = 322 devices, 5,223
     tickets). D4 says "every exposure-population device", so the null now covers all 6,621 devices (332 devices,
     5,395 tickets). The null median for devices with >= 6 tickets moves from 3 to 15 because of (1), not (2): the
     inflated pooled small-type rate (sd2.0-49) gives the 13 small-type devices with exposure E of up to 12.4. All
     four combinations are reported in D4_variants, and observed concentration is far beyond the null in each.
  3. NB dispersion estimator. This script used sum((y - E)^2 - y); the moment equation for Var(y) = E + alpha E^2
     is sum((y - E)^2 - E). The two coincide when sum y = sum E within a group, which (1) breaks for types with
     tickets on zero-exposure devices. Now sum((y - E)^2 - E); the y-form gives the same NB-kept count.

Privacy: verification/outputs/htm_*.csv and htm_summary.json hold only pseudonyms (S#####, M#####, T#####,
Customer NNN, Host NNN), generic labels and aggregates. Free text is read in memory only (regex flags). Real
serials and account names go only to data/private/htm_private_*.csv (gitignored). A final check (text_leaks) scans
every text column of every public table, cell by cell and token by token, for real serials, account names and case
numbers. Numeric columns (counts, rates) are not scanned; no id is stored as a number.

Run:  cd /home/user/analytics-lab && python3 -I verification/high_ticket_machines.py
Deterministic: fixed seed, stable sorts. Exit status 1 if any check fails.
Figures: the run ends by calling viz/high_ticket/run_all.py (one plain matplotlib script per chart, each also
runnable on its own). They read only the htm_* outputs and write viz/figures/htm_NN_*.png
(pseudonymous) plus one real-name chart to deliverables/ (gitignored). Skipped with a message if matplotlib is not
installed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import OUTPUTS, PRIVATE, clean, load_all  # noqa: E402
from customer_fleet_audit import ERROR_NOTE  # noqa: E402
from flags import monitoring_template  # noqa: E402

FU = OUTPUTS / 'fu'
DB = OUTPUTS / 'db'
PREFIX = 'htm_'
PERIOD_START, PERIOD_END = '2025-08-01', '2026-07-31'
SEED = 15072
N_SIM = 1000
N_SIM_EPISODES = 200
MIN_TYPE_MONTHS = 100
Q_CUT = 0.05
TOP_SHARE = 0.05
FIXED_THRESHOLD = 6
CONTROL_OFFSET_DAYS = 35  # fu_ticket_last10.csv window 'control_minus35d' (db_followup.py)
GAPS = (3, 7, 14)
UNPLANNED_EXCLUDED = ('Planned work', 'Cancelled request', 'Duplicate case')
POOL = '(pooled small types)'
NOT_MATCHED = '(not device-matched)'
GRID = np.linspace(0, 1, 101)

# Resolution-text markers (Trouble Resolution; in memory only).
MARKERS = {
    'replaced': re.compile(r'\breplac(?:e|ed|es|ement|ements|ing)\b', re.I),
    'adjust': re.compile(r'\badjust', re.I),
    'training': re.compile(r'\btrain(?:ed|ing|s)?\b|\beducat', re.I),
    'user_error_operator': re.compile(r'\buser\s+error|\boperator', re.I),
    'parts_on_order': re.compile(r'\bon\s+order\b|\bordered\b|\bback\s*-?\s*order', re.I),
    'reset_reboot': re.compile(r'\bre-?set(?:s|ting)?\b|\bre-?boot', re.I),
}

CHECKS = []
FACTS = {}
PUBLIC = {}


def check(name, expected, actual, tol=0.0):
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float, np.integer, np.floating)):
        ok = abs(float(actual) - float(expected)) <= tol
    else:
        ok = expected == actual
    CHECKS.append({'check': name, 'expected': expected, 'actual': actual, 'status': 'PASS' if ok else 'FAIL'})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: expected {expected}, got {actual}")


def save(df, name):
    path = OUTPUTS / f'{PREFIX}{name}.csv'
    df.to_csv(path, index=False)
    PUBLIC[name] = df
    print(f'  wrote {path.relative_to(OUTPUTS.parents[1])} ({len(df):,} rows)')
    return df


def text_leaks(df, real):
    """Count real identifiers in the text columns of df: a whole cell, or a whole token inside a cell, that equals a
    real serial, account name or case number. Real serials are 4-5 digits and case numbers 8 digits, so digit-only
    cells are tested too. Numeric columns hold counts and rates and are not tested (a count can equal a 4-5-digit
    serial by chance); every id column in the public tables is text."""
    out = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            continue
        hits = set()
        for v in df[col].dropna().astype(str).unique():
            if v in real:
                hits.add(v)
            hits.update(t for t in re.findall(r'[A-Za-z0-9]+', v) if t in real)
        if hits:
            out[col] = len(hits)
    return out


def r(x, nd=4):
    if x is None:
        return None
    if isinstance(x, (float, np.floating)) and not np.isfinite(x):
        return None
    return round(float(x), nd)


def modal(series):
    """Most frequent non-null value; ties -> alphabetically first (deterministic). None if all null."""
    s = series.dropna()
    if s.empty:
        return None
    vc = s.value_counts()
    top = vc.max()
    return sorted(vc.index[vc == top].astype(str))[0]


# ----------------------------------------------------------------------------------------------------------------
# Distributions (no scipy available)
# ----------------------------------------------------------------------------------------------------------------
def poisson_sf(k, mu):
    """P(X >= k) for X ~ Poisson(mu), summed directly over the upper tail (accurate for tiny p)."""
    k = int(k)
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    if k <= mu:  # tail is large: complement of the lower sum is accurate
        lower = sum(math.exp(-mu + j * math.log(mu) - math.lgamma(j + 1)) for j in range(k))
        return max(0.0, 1.0 - lower)
    term = math.exp(-mu + k * math.log(mu) - math.lgamma(k + 1))
    total, j = term, k
    while term > total * 1e-17 and j < k + 10_000:
        j += 1
        term *= mu / j
        total += term
    return min(1.0, total)


def nb_sf(k, mu, alpha):
    """P(X >= k) for a gamma-Poisson with mean mu and variance mu + alpha mu^2 (Poisson if alpha == 0)."""
    if alpha <= 0:
        return poisson_sf(k, mu)
    k = int(k)
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    size = 1.0 / alpha
    p = size / (size + mu)
    q = 1.0 - p

    def logpmf(j):
        return math.lgamma(j + size) - math.lgamma(size) - math.lgamma(j + 1) + size * math.log(p) + j * math.log(q)

    if k <= mu:
        lower = sum(math.exp(logpmf(j)) for j in range(k))
        return max(0.0, 1.0 - lower)
    term = math.exp(logpmf(k))
    total, j = term, k
    while term > total * 1e-17 and j < k + 100_000:
        term *= (j + size) / (j + 1) * q
        j += 1
        total += term
    return min(1.0, total)


def bh(p):
    """Benjamini-Hochberg q-values (monotone, capped at 1)."""
    p = np.asarray(p, float)
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p, kind='mergesort')
    ranked = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out


def gini(x):
    x = np.sort(np.asarray(x, float))
    n, s = len(x), x.sum()
    if n == 0 or s == 0:
        return float('nan')
    return float(2 * np.sum(np.arange(1, n + 1) * x) / (n * s) - (n + 1) / n)


def top_share(x, share=TOP_SHARE):
    x = np.sort(np.asarray(x, float))[::-1]
    k = math.ceil(share * len(x))
    return float(x[:k].sum() / x.sum()) if x.sum() else float('nan')


def lorenz_top(x, grid=GRID):
    """Share of tickets held by the top g share of devices (devices ranked by tickets, descending)."""
    x = np.sort(np.asarray(x, float))[::-1]
    xs = np.linspace(0, 1, len(x) + 1)
    ys = np.concatenate([[0.0], np.cumsum(x) / x.sum()])
    return np.interp(grid, xs, ys)


# ----------------------------------------------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------------------------------------------
def load_inputs():
    raw, maps, cases, conn = load_all()
    base = pd.read_sql_query('SELECT * FROM case_base', conn)
    sc = pd.read_sql_query('SELECT * FROM service_cases', conn)
    # Text flags, in memory only, keyed by case_id.
    cid = raw['Case Number'].map(clean).map(maps['case']).to_numpy()

    def txt(x):
        return '' if x is None or (isinstance(x, float) and x != x) else str(x)

    rep, res, adm = raw['Trouble Reported'], raw['Trouble Resolution'], raw['Administrative Notes']
    flags = pd.DataFrame({'case_id': cid, 'monitoring': rep.map(monitoring_template).astype(bool).to_numpy()})
    flags['wrong_machine_note'] = [bool(ERROR_NOTE.search(txt(a) + ' ' + txt(b))) for a, b in zip(adm, res)]
    for key, rx in MARKERS.items():
        flags['res_' + key] = [bool(rx.search(txt(x))) for x in res]
    base = base.merge(flags, on='case_id', how='left', validate='1:1')
    sc = sc.merge(flags, on='case_id', how='left', validate='1:1')
    # Private lookups (memory only): S##### -> real serial, Customer NNN -> real account name, real case numbers.
    private = {'serial': {v: k for k, v in maps['serial'].items()},
               'account': {v: k for k, v in maps['account'].items()},
               'real_strings': (set(map(str, maps['serial'])) | set(map(str, maps['account']))
                                | set(map(str, maps['case']))) - {'None', ''}}
    real_acct = raw['Account Name'].map(clean)
    private['case_account'] = dict(zip(cid, real_acct))

    fu = pd.read_csv(FU / 'fu_ticket_last10.csv', low_memory=False)
    dev = pd.read_csv(FU / 'fu_devices.csv')
    dev['machine_type'] = dev.machine_type.map(lambda x: clean(x).lower() if clean(x) else 'Unknown')
    dev['transacting'] = dev.transacting.astype(str).eq('True')
    hosts = pd.read_csv(DB / 'db_host_level.csv')
    shared = hosts.loc[hosts.shared_internal_host == 1, 'host'].tolist()
    zac_rates = pd.read_csv(DB / 'db_machine_type_rates.csv')
    return raw, base, sc, fu, dev, shared, zac_rates, private


# ----------------------------------------------------------------------------------------------------------------
# D1 workload view
# ----------------------------------------------------------------------------------------------------------------
def workload(sc):
    cnt = sc.groupby('machine_id').size()
    cnt = cnt.sort_index().sort_values(ascending=False, kind='mergesort')
    n = len(cnt)
    k = math.ceil(TOP_SHARE * n)
    thr = int(cnt.iloc[k - 1])
    out = cnt >= thr
    res = {'counts': cnt, 'tickets': int(cnt.sum()), 'machines': n, 'rank_k': k, 'threshold': thr,
           'outsized': set(cnt.index[out]), 'outsized_machines': int(out.sum()),
           'outsized_ticket_share': float(cnt[out].sum() / cnt.sum()),
           'fixed_machines': int((cnt >= FIXED_THRESHOLD).sum()),
           'fixed_ticket_share': float(cnt[cnt >= FIXED_THRESHOLD].sum() / cnt.sum()),
           'ge10': int((cnt >= 10).sum()), 'max': int(cnt.max())}
    for p in (0.05, 0.10, 0.20):
        res[f'top{int(p * 100)}_share'] = float(cnt.iloc[:math.ceil(p * n)].sum() / cnt.sum())
    return res


# ----------------------------------------------------------------------------------------------------------------
# D2 exposure view
# ----------------------------------------------------------------------------------------------------------------
def exposure_frame(dev, shared):
    d = dev[dev.host.notna() & ~dev.host.isin(shared)].copy()
    start, end = pd.Timestamp(PERIOD_START), pd.Timestamp(PERIOD_END)
    first = pd.to_datetime(d.first_active).clip(lower=start)
    last = pd.to_datetime(d.last_active).clip(upper=end)
    months = (last.dt.year * 12 + last.dt.month) - (first.dt.year * 12 + first.dt.month) + 1
    ok = d.transacting & first.notna() & last.notna() & (first <= last)
    d['months'] = np.where(ok, months.fillna(0), 0).astype(int)
    return d.reset_index(drop=True)


def fit_exposure(d, tickets_by_device, rate_tickets='all', alpha_form='E'):
    """Add obs, expected, p/q values, NB check and eb_rate to the exposure frame d (returns a copy + rate table).

    rate_tickets='all' (main, literal D2): r_t counts every population ticket, including tickets on devices with
    0 exposure months. rate_tickets='exposed' (variant): only tickets on devices with exposure months > 0, so
    numerator and denominator cover the same devices.
    alpha_form='E' (main): alpha = sum((y - E)^2 - E) / sum(E^2), the moment equation for Var = E + alpha E^2;
    alpha_form='y' (variant): sum((y - E)^2 - y) / sum(E^2).
    """
    d = d.copy()
    d['tickets_obs'] = d.machine_id.map(tickets_by_device).fillna(0).astype(int)
    d['_rate_tickets'] = d.tickets_obs if rate_tickets == 'all' else d.tickets_obs.where(d.months > 0, 0)
    g = d.groupby('machine_type').agg(devices=('machine_id', 'size'), exposure_months=('months', 'sum'),
                                      tickets=('tickets_obs', 'sum'), tickets_rate=('_rate_tickets', 'sum'),
                                      zero_exposure_devices=('months', lambda m: int((m == 0).sum())))
    g['tickets_on_zero_exposure_devices'] = g.tickets - d[d.months > 0].groupby('machine_type').tickets_obs.sum() \
        .reindex(g.index).fillna(0).astype(int)
    small = set(g.index[g.exposure_months < MIN_TYPE_MONTHS])
    d['rate_group'] = np.where(d.machine_type.isin(small), POOL, d.machine_type)
    overall = d._rate_tickets.sum() / d.months.sum()
    rates = {}
    for grp, sub in d.groupby('rate_group'):
        rates[grp] = sub._rate_tickets.sum() / sub.months.sum() if sub.months.sum() > 0 else overall
    d = d.drop(columns='_rate_tickets')
    d['type_rate'] = d.rate_group.map(rates)
    d['expected'] = d.type_rate * d.months
    pos = d.expected > 0
    alphas = {}
    for grp, sub in d[pos].groupby('rate_group'):
        y, e = sub.tickets_obs.to_numpy(float), sub.expected.to_numpy(float)
        alphas[grp] = max(0.0, float(np.sum((y - e) ** 2 - (e if alpha_form == 'E' else y)) / np.sum(e ** 2)))
    d['alpha_nb'] = d.rate_group.map(alphas).fillna(0.0)
    d['p_poisson'] = np.nan
    d['p_nb'] = np.nan
    d.loc[pos, 'p_poisson'] = [poisson_sf(y, e) for y, e in zip(d.tickets_obs[pos], d.expected[pos])]
    d.loc[pos, 'p_nb'] = [nb_sf(y, e, a) for y, e, a in zip(d.tickets_obs[pos], d.expected[pos], d.alpha_nb[pos])]
    d['q_bh'] = np.nan
    d['q_nb'] = np.nan
    d.loc[pos, 'q_bh'] = bh(d.loc[pos, 'p_poisson'].to_numpy())
    d.loc[pos, 'q_nb'] = bh(d.loc[pos, 'p_nb'].to_numpy())
    d['rate_outlier'] = d.q_bh < Q_CUT
    d['nb_outlier'] = d.q_nb < Q_CUT
    inv = np.where(d.alpha_nb > 0, 1.0 / d.alpha_nb.where(d.alpha_nb > 0, 1.0), np.inf)
    theta = np.where(d.alpha_nb > 0, (d.tickets_obs + inv) / (d.expected + inv), 1.0)
    d['eb_rate'] = np.where(pos, 100 * d.type_rate * theta, np.nan)
    d['obs_rate'] = np.where(d.months > 0, 100 * d.tickets_obs / d.months.where(d.months > 0, 1), np.nan)
    table = g.reset_index()
    table['rate_group'] = np.where(table.machine_type.isin(small), POOL, table.machine_type)
    table['rate_per_100_months'] = table.rate_group.map(rates) * 100
    table['own_rate_per_100_months'] = np.where(table.exposure_months > 0,
                                                100 * table.tickets_rate / table.exposure_months.where(
                                                    table.exposure_months > 0, 1), np.nan)
    table = table.rename(columns={'tickets_rate': 'tickets_used_for_rate'})
    table['alpha_nb'] = table.rate_group.map(alphas)
    return d, table, float(overall)


def exposure_tickets(sc_period, case_to_m, population):
    m = sc_period.case_id.map(case_to_m)
    m = m[m.isin(population)]
    return m.value_counts()


# ----------------------------------------------------------------------------------------------------------------
# D4 concentration null
# ----------------------------------------------------------------------------------------------------------------
def concentration(obs, expected, seed=SEED, n_sim=N_SIM):
    rng = np.random.default_rng(seed)
    obs = np.asarray(obs, float)
    expected = np.asarray(expected, float)
    sims = rng.poisson(expected, size=(n_sim, len(expected)))
    t5 = np.array([top_share(s) for s in sims])
    gi = np.array([gini(s) for s in sims])
    g6 = (sims >= 6).sum(axis=1)
    curves = np.array([lorenz_top(s) for s in sims])
    res = {'devices': int(len(obs)), 'tickets_obs': int(obs.sum()), 'tickets_null_mean': float(sims.sum(1).mean()),
           'top5_share_obs': top_share(obs), 'top5_share_null_median': float(np.median(t5)),
           'top5_share_null_p95': float(np.percentile(t5, 95)), 'top5_share_null_max': float(t5.max()),
           'top5_share_p_value': float((np.sum(t5 >= top_share(obs)) + 1) / (n_sim + 1)),
           'gini_obs': gini(obs), 'gini_null_median': float(np.median(gi)),
           'gini_null_p95': float(np.percentile(gi, 95)),
           'ge6_obs': int((obs >= 6).sum()), 'ge6_null_median': float(np.median(g6)),
           'ge6_null_p95': float(np.percentile(g6, 95)), 'ge6_null_max': int(g6.max())}
    lor = pd.DataFrame({'device_share': GRID, 'ticket_share_obs': lorenz_top(obs),
                        'ticket_share_null_median': np.median(curves, axis=0),
                        'ticket_share_null_p2_5': np.percentile(curves, 2.5, axis=0),
                        'ticket_share_null_p97_5': np.percentile(curves, 97.5, axis=0)})
    return res, lor


# ----------------------------------------------------------------------------------------------------------------
# D5 episodes
# ----------------------------------------------------------------------------------------------------------------
def episodes(sc):
    s = sc[['machine_id', 'opened_at', 'case_id']].copy()
    s['ts'] = pd.to_datetime(s.opened_at)
    s = s.sort_values(['machine_id', 'ts', 'case_id'], kind='mergesort')
    gap = s.groupby('machine_id').ts.diff().dt.total_seconds() / 86400
    out = s.groupby('machine_id').size().rename('tickets').to_frame()
    for g in GAPS:
        new = gap.isna() | (gap > g)
        out[f'episodes_{g}d'] = new.groupby(s.machine_id).sum().astype(int)
    return out.reset_index()


def random_timing_followup(counts, lo, hi, gap_days=7, n_sim=N_SIM_EPISODES, seed=SEED):
    """Follow-up share if each machine's tickets were placed uniformly at random in [lo, hi] (rough null)."""
    rng = np.random.default_rng(seed)
    span = (hi - lo).total_seconds() / 86400
    res = []
    counts = np.asarray(counts, int)
    for _ in range(n_sim):
        follow = 0
        for n in counts:
            if n < 2:
                continue
            t = np.sort(rng.uniform(0, span, n))
            follow += int(np.sum(np.diff(t) <= gap_days))
        res.append(follow / counts.sum())
    return float(np.median(res)), float(np.percentile(res, 2.5)), float(np.percentile(res, 97.5))


# ----------------------------------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------------------------------
def main():
    t0 = time.time()
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    print('Loading inputs ...')
    raw, base, sc, fu, dev, shared, zac_rates, private = load_inputs()
    print(f'  {len(base):,} tickets; {len(sc):,} unplanned on {sc.machine_id.nunique():,} machines; '
          f'{len(dev):,} devices; shared internal host(s): {shared}')
    check('unplanned tickets (service_cases)', 7186, len(sc))
    check('ticketed machines (unplanned)', 3685, int(sc.machine_id.nunique()))
    check('monitoring-template tickets (all tickets)', 138, int(base.monitoring.sum()))
    check('telemetry devices', 7183, len(dev))
    check('shared internal host identified', 1, len(shared))

    # Linkage case_id -> M#####, and serial S##### -> M##### (unique both ways).
    main_w = fu[fu.window == 'corrected_guard0']
    case_to_m = dict(zip(main_w.case_id, main_w.machine_id))
    check('device-matched tickets in fu_ticket_last10', 6113, len(case_to_m))
    link = base[['case_id', 'machine_id']].assign(m=base.case_id.map(case_to_m)).dropna(subset=['m'])
    s_to_m_n = link.groupby('machine_id').m.nunique()
    m_to_s_n = link.groupby('m').machine_id.nunique()
    check('serial -> telemetry id is one-to-one', 0, int((s_to_m_n > 1).sum() + (m_to_s_n > 1).sum()))
    s_to_m = dict(link.drop_duplicates('machine_id')[['machine_id', 'm']].itertuples(index=False))
    m_to_s = {v: k for k, v in s_to_m.items()}
    devi = dev.set_index('machine_id')

    # ---------------------------------------------------------------- D1
    print('D1 workload view ...')
    W = workload(sc)
    print(f"  top-5% rank {W['rank_k']} has {W['threshold']} tickets -> {W['outsized_machines']} machines "
          f"(ties) hold {W['outsized_ticket_share']:.1%}; >=6: {W['fixed_machines']}")
    check('top 5% (185 machines) ticket share', 0.183, round(W['top5_share'], 3))
    check('top 10% ticket share', 0.294, round(W['top10_share'], 3))
    check('top 20% ticket share', 0.456, round(W['top20_share'], 3))
    check('machines with >=6 unplanned tickets', 147, W['fixed_machines'])
    check('machines with >=10 unplanned tickets', 21, W['ge10'])
    check('max unplanned tickets on one machine', 23, W['max'])
    outsized = W['outsized']

    # ---------------------------------------------------------------- D2
    print('D2 exposure view ...')
    expo = exposure_frame(dev, shared)
    population = set(expo.machine_id)
    in_period = sc.opened_at.str[:10].between(PERIOD_START, PERIOD_END)
    sc_period = sc[in_period]
    tick = exposure_tickets(sc_period, case_to_m, population)
    E, rate_table, overall_rate = fit_exposure(expo, tick)
    pos = E.expected > 0
    zero_exp_tickets = int(E.loc[~pos, 'tickets_obs'].sum())
    print(f"  {len(E):,} devices, {E.months.sum():,} exposure months, {E.tickets_obs.sum():,} tickets "
          f"({zero_exp_tickets} on devices with 0 exposure months); overall {100 * overall_rate:.2f} / 100 months")
    check('sum expected (all devices) = sum observed (literal D2 numerator)', int(E.tickets_obs.sum()),
          round(float(E.expected.sum()), 6), tol=1e-6)
    W_out_m = E.machine_id.map(m_to_s).isin(outsized)
    # Variant: tickets on zero-exposure devices left out of the rate numerator (this script's original choice).
    EX, _, overall_x = fit_exposure(expo, tick, rate_tickets='exposed')
    exposed_variant = {
        'overall_rate_per_100_months': 100 * overall_x,
        'pooled_small_rate_per_100_months': float(100 * EX.loc[EX.rate_group == POOL, 'type_rate'].iloc[0])
        if (EX.rate_group == POOL).any() else None,
        'rate_outliers_poisson': int(EX.rate_outlier.sum()),
        'rate_outliers_nb_kept': int((EX.rate_outlier & EX.nb_outlier).sum()),
        'chronic_outliers': int((EX.rate_outlier & W_out_m).sum()),
        'high_volume_expected': int((~EX.rate_outlier & W_out_m).sum()),
        'rate_outlier_only': int((EX.rate_outlier & ~W_out_m).sum()),
        'chronic_overlap_with_main': int((EX.rate_outlier & W_out_m & E.rate_outlier).sum()),
        'chronic_only_in_variant': sorted(EX.machine_id[EX.rate_outlier & W_out_m & ~E.rate_outlier])}
    print(f"  exposed-numerator variant (zero-exposure tickets out of rate numerator): overall "
          f"{exposed_variant['overall_rate_per_100_months']:.2f}, pooled small types "
          f"{exposed_variant['pooled_small_rate_per_100_months']:.1f} / 100 months; rate outliers "
          f"{exposed_variant['rate_outliers_poisson']}, chronic {exposed_variant['chronic_outliers']} "
          f"(+{exposed_variant['chronic_only_in_variant']})")
    # Variant: NB dispersion with y instead of E in the variance correction.
    EY, _, _ = fit_exposure(expo, tick, alpha_form='y')
    nb_y_kept = int((EY.rate_outlier & EY.nb_outlier).sum())
    rate_n = int(E.rate_outlier.sum())
    nb_kept = int((E.rate_outlier & E.nb_outlier).sum())
    print(f'  rate outliers (Poisson BH q<0.05): {rate_n}; still q<0.05 under NB: {nb_kept} '
          f'(y-form alpha: {nb_y_kept}); NB outliers total {int(E.nb_outlier.sum())}')

    # Exposure diagnostics: period tickets opened before the device's first / after its last transaction day.
    tp = sc_period.assign(m=sc_period.case_id.map(case_to_m))
    tp = tp[tp.m.isin(population)]
    day = tp.opened_at.str[:10]
    fa, la = tp.m.map(devi.first_active), tp.m.map(devi.last_active)
    E['tickets_before_first_active'] = E.machine_id.map(tp[fa.notna() & (day < fa)].m.value_counts()) \
        .fillna(0).astype(int)
    E['tickets_after_last_active'] = E.machine_id.map(tp[la.notna() & (day > la)].m.value_counts()) \
        .fillna(0).astype(int)

    # ---------------------------------------------------------------- D3
    E['serial_id'] = E.machine_id.map(m_to_s)
    E['serial_unplanned_tickets'] = E.serial_id.map(W['counts']).fillna(0).astype(int)
    E['workload_outsized'] = E.serial_id.isin(outsized)
    E['class'] = np.select([E.workload_outsized & E.rate_outlier, E.workload_outsized, E.rate_outlier],
                           ['chronic_outlier', 'high_volume_expected', 'rate_outlier_only'], 'none')
    cls = E['class'].value_counts().to_dict()
    chronic_ids = sorted(E.loc[E['class'] == 'chronic_outlier', 'machine_id'])
    chronic_serials = {m_to_s[m] for m in chronic_ids}
    print(f'  classes: {cls}')
    out_in_pop = int(E.workload_outsized.sum())
    out_matched = sum(1 for s in outsized if s in s_to_m)
    out_shared = sum(1 for s in outsized if s in s_to_m and devi.loc[s_to_m[s], 'host'] in shared)
    out_null = sum(1 for s in outsized if s in s_to_m and pd.isna(devi.loc[s_to_m[s], 'host']))

    # Ticket-level model per device (modal ticket model over the serial's unplanned tickets).
    model_s = sc.groupby('machine_id').model.agg(modal)
    E['model'] = E.serial_id.map(model_s)
    E['customer'] = E.assigned_customer.where(E.assigned_customer.notna(), E.ticket_customer)

    # ---------------------------------------------------------------- D4
    print('D4 concentration null ...')
    C4, lorenz = concentration(E.tickets_obs, E.expected)
    print(f"  top-5% share obs {C4['top5_share_obs']:.3f} vs null median {C4['top5_share_null_median']:.3f} "
          f"(p95 {C4['top5_share_null_p95']:.3f}); gini {C4['gini_obs']:.3f} vs {C4['gini_null_median']:.3f}; "
          f">=6: {C4['ge6_obs']} vs {C4['ge6_null_median']:.0f} (p95 {C4['ge6_null_p95']:.0f})")
    D4_KEYS = ('devices', 'tickets_obs', 'top5_share_obs', 'top5_share_null_median', 'top5_share_null_p95',
               'gini_obs', 'gini_null_median', 'gini_null_p95', 'ge6_obs', 'ge6_null_median', 'ge6_null_p95')
    d4_variants = {
        'E_pos_only': concentration(E.loc[pos, 'tickets_obs'], E.loc[pos, 'expected'])[0],
        'exposed_numerator_all_devices': concentration(EX.tickets_obs, EX.expected)[0],
        'exposed_numerator_E_pos_only': concentration(EX.loc[EX.expected > 0, 'tickets_obs'],
                                                      EX.loc[EX.expected > 0, 'expected'])[0]}
    d4_variants = {k: {kk: v[kk] for kk in D4_KEYS} for k, v in d4_variants.items()}
    for k, v in d4_variants.items():
        print(f"  D4 variant {k}: top-5% {v['top5_share_obs']:.3f} vs {v['top5_share_null_median']:.3f}; gini "
              f"{v['gini_obs']:.3f} vs {v['gini_null_median']:.3f}; >=6 {v['ge6_obs']} vs {v['ge6_null_median']:.0f}")
    wl = lorenz_top(W['counts'].to_numpy())
    lorenz['ticket_share_workload_ticketed_machines'] = wl
    lorenz['population'] = (f"obs/null: all {C4['devices']} exposure-population devices; "
                            f"workload column: {W['machines']} ticketed serials (unplanned)")

    # ---------------------------------------------------------------- D5
    print('D5 episodes ...')
    ep = episodes(sc)
    ep['workload_outsized'] = ep.machine_id.isin(outsized)
    ep['telemetry_id'] = ep.machine_id.map(s_to_m)
    ep['chronic_outlier'] = ep.machine_id.isin(chronic_serials)
    D5 = {}
    for label, mask in [('outsized', ep.workload_outsized), ('other', ~ep.workload_outsized),
                        ('chronic', ep.chronic_outlier)]:
        sub = ep[mask]
        row = {'machines': int(len(sub)), 'tickets': int(sub.tickets.sum()),
               'tickets_per_machine_median': float(sub.tickets.median())}
        for g in GAPS:
            row[f'episodes_per_machine_median_{g}d'] = float(sub[f'episodes_{g}d'].median())
            row[f'episodes_per_machine_mean_{g}d'] = float(sub[f'episodes_{g}d'].mean())
            row[f'followup_share_{g}d'] = float(1 - sub[f'episodes_{g}d'].sum() / sub.tickets.sum())
        D5[label] = row
    ts = pd.to_datetime(sc.opened_at)
    for label, mask in [('outsized', ep.workload_outsized), ('other', ~ep.workload_outsized)]:
        D5[label]['followup_share_7d_random_timing'] = random_timing_followup(ep.tickets[mask], ts.min(), ts.max())
    print(f"  outsized: {D5['outsized']['tickets_per_machine_median']:.0f} tickets, "
          f"{D5['outsized']['episodes_per_machine_median_7d']:.0f} episodes (median); follow-up share 7d "
          f"{D5['outsized']['followup_share_7d']:.1%} vs other {D5['other']['followup_share_7d']:.1%}")

    # ---------------------------------------------------------------- Sensitivity (no monitoring templates)
    print('Sensitivity: excluding monitoring-template tickets ...')
    sc2 = sc[~sc.monitoring]
    W2 = workload(sc2)
    tick2 = exposure_tickets(sc2[sc2.opened_at.str[:10].between(PERIOD_START, PERIOD_END)], case_to_m, population)
    E2, _, overall2 = fit_exposure(expo, tick2)
    E2['workload_outsized'] = E2.machine_id.map(m_to_s).isin(W2['outsized'])
    chronic2 = set(E2.machine_id[E2.workload_outsized & E2.rate_outlier])
    C4b, _ = concentration(E2.tickets_obs, E2.expected)
    sens = {'monitoring_tickets_excluded_unplanned': int(sc.monitoring.sum()),
            'workload_tickets': int(len(sc2)), 'workload_machines': W2['machines'],
            'workload_threshold': W2['threshold'], 'workload_outsized_machines': W2['outsized_machines'],
            'workload_outsized_share': W2['outsized_ticket_share'], 'ge6_machines': W2['fixed_machines'],
            'ge10_machines': W2['ge10'], 'max': W2['max'],
            'top5_share_185': W2['top5_share'], 'exposure_tickets': int(E2.tickets_obs.sum()),
            'overall_rate_per_100_months': 100 * overall2,
            'pooled_small_rate_per_100_months': float(100 * E2.loc[E2.rate_group == POOL, 'type_rate'].iloc[0])
            if (E2.rate_group == POOL).any() else None,
            'rate_outliers_poisson': int(E2.rate_outlier.sum()),
            'rate_outliers_nb': int((E2.rate_outlier & E2.nb_outlier).sum()),
            'chronic_outliers': len(chronic2),
            'high_volume_expected': int((E2.workload_outsized & ~E2.rate_outlier).sum()),
            'rate_outlier_only': int((~E2.workload_outsized & E2.rate_outlier).sum()),
            'chronic_overlap_with_main': len(chronic2 & set(chronic_ids)),
            'chronic_dropped_vs_main': sorted(set(chronic_ids) - chronic2),
            'chronic_added_vs_main': sorted(chronic2 - set(chronic_ids)),
            **{k: C4b[k] for k in ('top5_share_obs', 'top5_share_null_median', 'top5_share_null_p95', 'gini_obs',
                                   'gini_null_median', 'gini_null_p95', 'ge6_obs', 'ge6_null_median',
                                   'ge6_null_p95')}}
    sens_text = (f"Excluding the {sens['monitoring_tickets_excluded_unplanned']} monitoring-template unplanned "
                 f"tickets ({sens['workload_tickets']:,} tickets on {sens['workload_machines']:,} machines): workload "
                 f"threshold {sens['workload_threshold']} tickets -> {sens['workload_outsized_machines']} outsized "
                 f"machines ({sens['workload_outsized_share']:.1%} of tickets; top 5% hold "
                 f"{sens['top5_share_185']:.1%}; >=6: {sens['ge6_machines']}; >=10: {sens['ge10_machines']}; max "
                 f"{sens['max']}). Exposure tickets {sens['exposure_tickets']:,}; overall rate "
                 f"{sens['overall_rate_per_100_months']:.2f} per 100 months (pooled small types "
                 f"{sens['pooled_small_rate_per_100_months']:.1f}). Rate outliers {sens['rate_outliers_poisson']} "
                 f"(Poisson), {sens['rate_outliers_nb']} also under NB; chronic {sens['chronic_outliers']}, "
                 f"high-volume-expected {sens['high_volume_expected']}, rate-outlier-only "
                 f"{sens['rate_outlier_only']}; the chronic set is a subset of the main run's "
                 f"({sens['chronic_overlap_with_main']} shared, {len(sens['chronic_dropped_vs_main'])} dropped, "
                 f"{len(sens['chronic_added_vs_main'])} added). D4 over all exposure-population devices: top-5% "
                 f"share {sens['top5_share_obs']:.3f} vs null median {sens['top5_share_null_median']:.3f} (p95 "
                 f"{sens['top5_share_null_p95']:.3f}); Gini {sens['gini_obs']:.3f} vs {sens['gini_null_median']:.3f} "
                 f"(p95 {sens['gini_null_p95']:.3f}); >=6 {sens['ge6_obs']} vs null median "
                 f"{sens['ge6_null_median']:.0f} (p95 {sens['ge6_null_p95']:.0f}). Conclusion unchanged.")
    print('  ' + sens_text)

    # ---------------------------------------------------------------- Machine-level frame (serial)
    mach = W['counts'].rename('unplanned_tickets').rename_axis('machine_id').reset_index()
    mach['workload_outsized'] = mach.machine_id.isin(outsized)
    mach['ge6'] = mach.unplanned_tickets >= FIXED_THRESHOLD
    mach['telemetry_id'] = mach.machine_id.map(s_to_m)
    mach['model'] = mach.machine_id.map(model_s)
    mm = mach.telemetry_id
    for col in ('machine_type', 'device_status', 'host', 'first_active', 'last_active', 'assigned_customer',
                'ticket_customer'):
        mach[col] = mm.map(devi[col]) if col in devi else None
    mach['device_status'] = mach.device_status.fillna(NOT_MATCHED)
    cust_s = sc.groupby('machine_id').customer.agg(modal)
    mach['customer'] = mach.assigned_customer.where(mach.assigned_customer.notna(), mach.ticket_customer)
    mach['customer'] = mach.customer.where(mach.customer.notna(), mach.machine_id.map(cust_s))
    mach['ticket_customers'] = mach.machine_id.map(sc.groupby('machine_id').customer.nunique())
    emap = E.set_index('machine_id')
    mach['exposure_population'] = mach.telemetry_id.isin(population)
    mach['exposure_months'] = mm.map(emap.months)
    mach['class'] = mm.map(emap['class'])
    mach['chronic_outlier'] = mach['class'].eq('chronic_outlier')
    mach['appeared_in_period'] = mach.first_active.notna() & (mach.first_active > PERIOD_START)
    mach['host_kind'] = np.select([mach.telemetry_id.isna(), mach.host.isna(), mach.host.isin(shared)],
                                  [NOT_MATCHED, 'NULL host', 'shared internal host'], 'customer host')

    # ---------------------------------------------------------------- C profiles
    print('C profiles ...')
    groups = {
        'workload_outsized': set(mach.machine_id[mach.workload_outsized]),
        'other_ticketed': set(mach.machine_id[~mach.workload_outsized]),
        'chronic_outlier': set(mach.machine_id[mach['class'] == 'chronic_outlier']),
        'high_volume_expected': set(mach.machine_id[mach['class'] == 'high_volume_expected']),
        'rate_outlier_only': set(mach.machine_id[mach['class'] == 'rate_outlier_only']),
        'exposure_ticketed_none': set(mach.machine_id[(mach['class'] == 'none')]),
    }
    prof = []

    def add(group, measure, num, den, note=''):
        prof.append({'group': group, 'measure': measure, 'numerator': num, 'denominator': den,
                     'value': r(num / den) if den else None, 'note': note})

    sc_sorted = sc.sort_values(['machine_id', 'opened_at', 'case_id'], kind='mergesort').copy()
    sc_sorted['prev_category'] = sc_sorted.groupby('machine_id').category.shift(1)
    sc_sorted['has_prev'] = sc_sorted.groupby('machine_id').cumcount() > 0
    seen_any = []
    for _, g in sc_sorted.groupby('machine_id', sort=False):
        seen = set()
        for c in g.category:
            seen_any.append(c is not None and c in seen)
            if c is not None:
                seen.add(c)
    sc_sorted['same_as_any_earlier'] = seen_any

    for gname, ids in groups.items():
        gm = mach[mach.machine_id.isin(ids)]
        gt = sc_sorted[sc_sorted.machine_id.isin(ids)]
        gb = base[base.machine_id.isin(ids)]
        n, nt = len(gm), len(gt)
        add(gname, 'machines', n, 1)
        add(gname, 'unplanned_tickets', nt, 1)
        add(gname, 'tickets_per_machine_mean', nt, n)
        add(gname, 'tickets_per_machine_median', float(gm.unplanned_tickets.median()) if n else None, 1)
        add(gname, 'device_matched', int(gm.telemetry_id.notna().sum()), n)
        for st, k in gm.device_status.value_counts().sort_index().items():
            add(gname, f'device_status={st}', int(k), n)
        for hk, k in gm.host_kind.value_counts().sort_index().items():
            add(gname, f'host_kind={hk}', int(k), n)
        matched = gm[gm.telemetry_id.notna()]
        add(gname, 'appeared_in_period (first_active > 2025-08-01), matched', int(matched.appeared_in_period.sum()),
            len(matched))
        add(gname, 'not transacting (no first_active), matched', int(matched.first_active.isna().sum()), len(matched))
        ex = gm[gm.exposure_population]
        add(gname, 'exposure_months_median (exposure population)', float(ex.exposure_months.median())
            if len(ex) else None, 1)
        add(gname, 'exposure_months_lt12 (exposure population)', int((ex.exposure_months < 12).sum()), len(ex))
        add(gname, 'serials with >1 ticket account', int((gm.ticket_customers > 1).sum()), n)
        add(gname, 'distinct customers', int(gm.customer.nunique()), 1)
        add(gname, 'distinct hosts (matched)', int(matched.host.nunique()), 1)
        # ticket composition
        add(gname, 'NTF (No Trouble Found) share of unplanned', int(gt.category.eq('No Trouble Found').sum()), nt)
        add(gname, 'missing trouble code share of unplanned', int(gt.trouble_code.isna().sum()), nt)
        add(gname, 'missing category share of unplanned', int(gt.category.isna().sum()), nt)
        add(gname, 'monitoring-template share of unplanned', int(gt.monitoring.sum()), nt)
        add(gname, 'wrong-machine note share of unplanned', int(gt.wrong_machine_note.sum()), nt)
        add(gname, 'cancelled share of ALL tickets', int(gb.service_group.eq('Cancelled request').sum()), len(gb))
        add(gname, 'duplicate share of ALL tickets', int(gb.service_group.eq('Duplicate case').sum()), len(gb))
        add(gname, 'planned share of ALL tickets', int(gb.service_group.eq('Planned work').sum()), len(gb))
        add(gname, 'wrong-machine note share of ALL tickets', int(gb.wrong_machine_note.sum()), len(gb))
        for key in MARKERS:
            add(gname, f'resolution marker: {key}', int(gt['res_' + key].sum()), nt)
        # same-category recurrence
        pr = gt[gt.has_prev & gt.category.notna() & gt.prev_category.notna()]
        add(gname, 'same category as previous ticket (both non-missing)', int((pr.category == pr.prev_category).sum()),
            len(pr))
        mix = gt.category.dropna().value_counts(normalize=True)
        add(gname, 'baseline: same category if drawn from group mix (sum p^2)', float((mix ** 2).sum()), 1)
        ae = gt[gt.has_prev & gt.category.notna()]
        add(gname, 'category already seen earlier on the machine', int(ae.same_as_any_earlier.sum()), len(ae))
    profile = pd.DataFrame(prof)

    # Customer / host clustering, with a permutation baseline (random machines of the same number).
    rng = np.random.default_rng(SEED)
    cust_arr = mach.customer.fillna('(none)').to_numpy()
    host_arr = mach.host.to_numpy(dtype=object)
    is_out = mach.workload_outsized.to_numpy()
    n_out = int(is_out.sum())

    def clust(mask):
        cs = pd.Series(cust_arr[mask]).value_counts()
        hs = pd.Series(host_arr[mask]).dropna().value_counts()
        return len(cs), float(cs.iloc[:5].sum() / mask.sum()), len(hs), int((cs >= 2).sum())

    obs_cl = clust(is_out)
    perm = []
    for _ in range(N_SIM):
        mask = np.zeros(len(mach), bool)
        mask[rng.choice(len(mach), n_out, replace=False)] = True
        perm.append(clust(mask))
    perm = np.array(perm, float)
    cl = {'outsized_machines': n_out, 'customers_holding': obs_cl[0],
          'customers_holding_null_median': float(np.median(perm[:, 0])),
          'top5_customers_share_of_outsized': obs_cl[1],
          'top5_customers_share_null_median': float(np.median(perm[:, 1])),
          'top5_customers_share_null_p95': float(np.percentile(perm[:, 1], 95)),
          'hosts_holding': obs_cl[2], 'hosts_holding_null_median': float(np.median(perm[:, 2])),
          'customers_with_2plus_outsized': obs_cl[3],
          'customers_with_2plus_outsized_null_median': float(np.median(perm[:, 3])),
          'customers_with_2plus_outsized_null_p95': float(np.percentile(perm[:, 3], 95)),
          'outsized_matched': out_matched, 'outsized_on_shared_host': out_shared, 'outsized_on_null_host': out_null,
          'outsized_in_exposure_population': out_in_pop}
    chronic_cust = E.loc[E['class'] == 'chronic_outlier', 'customer'].fillna('(none)').value_counts()
    cl['chronic_customers_holding'] = int(len(chronic_cust))
    cl['chronic_hosts_holding'] = int(E.loc[E['class'] == 'chronic_outlier', 'host'].nunique())
    print(f"  outsized machines on {cl['customers_holding']} customers "
          f"(random: {cl['customers_holding_null_median']:.0f}); "
          f"top-5 customers hold {cl['top5_customers_share_of_outsized']:.1%} (random median "
          f"{cl['top5_customers_share_null_median']:.1%}, p95 {cl['top5_customers_share_null_p95']:.1%})")
    for k, v in cl.items():
        add('workload_outsized', f'clustering: {k}', v, 1)
    profile = pd.DataFrame(prof)

    # Issue mix (category / subcategory / trouble code) per group, long format.
    mix_rows = []
    for gname in ('workload_outsized', 'other_ticketed', 'chronic_outlier'):
        gt = sc[sc.machine_id.isin(groups[gname])]
        for field in ('trouble_code', 'category', 'subcategory'):
            vc = gt[field].fillna('[Missing]').value_counts()
            for val, k in vc.sort_index().items():
                mix_rows.append({'group': gname, 'field': field, 'value': val, 'tickets': int(k),
                                 'share': r(k / len(gt))})
    issue_mix = pd.DataFrame(mix_rows)
    piv = issue_mix[issue_mix.field == 'category'].pivot_table(index='value', columns='group', values='share',
                                                               aggfunc='first').fillna(0)
    piv['diff_pp'] = 100 * (piv.get('workload_outsized', 0) - piv.get('other_ticketed', 0))
    cat_diff = piv.sort_values('diff_pp', kind='mergesort')

    # Type / model mix
    tm = []
    for field in ('machine_type', 'model'):
        col = mach[field].fillna(NOT_MATCHED if field == 'machine_type' else '[Missing]')
        tot_out, tot_oth = int(mach.workload_outsized.sum()), int((~mach.workload_outsized).sum())
        for val in sorted(col.unique()):
            sel = col == val
            o = int((sel & mach.workload_outsized).sum())
            t = int((sel & ~mach.workload_outsized).sum())
            tm.append({'field': field, 'value': val, 'outsized_machines': o, 'outsized_share': r(o / tot_out),
                       'other_machines': t, 'other_share': r(t / tot_oth),
                       'pct_of_value_outsized': r(o / (o + t)),
                       'unplanned_tickets': int(mach.unplanned_tickets[sel].sum()),
                       'tickets_per_machine': r(mach.unplanned_tickets[sel].mean(), 3),
                       'chronic_outliers': int((sel & mach.chronic_outlier).sum())})
    type_mix = pd.DataFrame(tm)

    # ---------------------------------------------------------------- E pre-ticket telemetry
    print('E pre-ticket telemetry ...')
    unpl_ids = set(sc.case_id)
    usable = main_w[~main_w.lookback_truncated.astype(bool) & ~main_w.after_telemetry_end.astype(bool)
                    & main_w.case_id.isin(unpl_ids)].copy()
    ctrl = fu[(fu.window == f'control_minus{CONTROL_OFFSET_DAYS}d') & fu.control_clean.astype(str).eq('True')
              & ~fu.lookback_truncated.astype(bool) & fu.case_id.isin(set(usable.case_id))]
    ctrl = ctrl.set_index('case_id')
    m_class = E.set_index('machine_id')['class']
    s_out = {s_to_m[s] for s in outsized if s in s_to_m}
    usable['device_class'] = usable.machine_id.map(m_class).fillna('(not in exposure population)')
    usable['group'] = np.select([usable.device_class.eq('chronic_outlier'), usable.machine_id.isin(s_out)],
                                ['chronic', 'workload_outsized'], 'other')
    usable['workload_outsized'] = usable.machine_id.isin(s_out)

    def nsp(df):
        return np.where(df.all_events > 0, 1000 * df.non_success_events / df.all_events.where(df.all_events > 0, 1),
                        np.nan)

    buckets = sorted({b for v in fu.last10_distinct_buckets.dropna() for b in v.split('|')})

    def bset(v):
        return set(v.split('|')) if isinstance(v, str) and v else set()

    pre = pd.DataFrame({'case_id': usable.case_id, 'machine_id': usable.machine_id,
                        'serial_id': usable.machine_id.map(m_to_s), 'group': usable.group,
                        'device_class': usable.device_class, 'workload_outsized': usable.workload_outsized,
                        'category': usable.category.fillna('[Missing]'),
                        'all_events_30d': usable.all_events, 'non_success_events_30d': usable.non_success_events,
                        'non_success_per_1000': nsp(usable), 'distinct_codes_30d': usable.distinct_codes,
                        'last10_buckets': usable.last10_distinct_buckets.fillna('')})
    cw = ctrl.reindex(pre.case_id)
    pre['control_clean_available'] = pre.case_id.isin(ctrl.index).to_numpy()
    pre['control_all_events_30d'] = cw.all_events.to_numpy()
    pre['control_non_success_events_30d'] = cw.non_success_events.to_numpy()
    pre['control_non_success_per_1000'] = nsp(cw)
    pre['control_distinct_codes_30d'] = cw.distinct_codes.to_numpy()
    pre['control_last10_buckets'] = cw.last10_distinct_buckets.fillna('').to_numpy()
    pre['control_last10_buckets'] = pre.control_last10_buckets.where(pre.control_clean_available, None)
    pre = pre.sort_values('case_id', kind='mergesort').reset_index(drop=True)

    tel = []
    pre['wo'] = pre.workload_outsized.map({True: 'workload_outsized (incl. chronic)', False: 'not outsized'})
    group_defs = [('chronic', pre.group == 'chronic'),
                  ('workload_outsized_not_chronic', pre.group == 'workload_outsized'),
                  ('workload_outsized_all', pre.workload_outsized), ('other', pre.group == 'other')]
    for gname, gmask in group_defs:
        g = pre[gmask]
        for window, sub, ev, ns, bk in [
                ('ticket (all usable)', g, 'all_events_30d', 'non_success_per_1000', 'last10_buckets'),
                ('ticket (paired)', g[g.control_clean_available], 'all_events_30d', 'non_success_per_1000',
                 'last10_buckets'),
                ('control (paired)', g[g.control_clean_available], 'control_all_events_30d',
                 'control_non_success_per_1000', 'control_last10_buckets')]:
            per_m = sub.groupby('machine_id')[ev].median()
            row = {'group': gname, 'window': window, 'tickets': int(len(sub)),
                   'machines': int(sub.machine_id.nunique()),
                   'all_events_median': r(sub[ev].median(), 1), 'all_events_mean': r(sub[ev].mean(), 1),
                   'all_events_machine_median': r(per_m.median(), 1),
                   'zero_events_share': r((sub[ev] == 0).mean()) if len(sub) else None,
                   'non_success_per_1000_median': r(sub[ns].median(), 1),
                   'non_success_per_1000_mean': r(sub[ns].mean(), 1)}
            sets = sub[bk].map(bset)
            for b in buckets:
                row[f'bucket_present: {b}'] = r(sets.map(lambda s, b=b: b in s).mean()) if len(sub) else None
            tel.append(row)
    pre_summary = pd.DataFrame(tel)
    pre = pre.drop(columns=['wo'])
    print(pre_summary[['group', 'window', 'tickets', 'machines', 'all_events_median', 'non_success_per_1000_median']]
          .to_string(index=False))

    # ---------------------------------------------------------------- Tables
    print('Writing tables ...')
    mc = mach[['machine_id', 'telemetry_id', 'unplanned_tickets', 'workload_outsized', 'ge6', 'model',
               'machine_type', 'device_status', 'host_kind', 'host', 'customer', 'exposure_population',
               'exposure_months', 'class']].copy()
    mc = mc.rename(columns={'class': 'exposure_class'})
    mc['chronic_outlier'] = mc.exposure_class.eq('chronic_outlier')
    save(mc.sort_values(['unplanned_tickets', 'machine_id'], ascending=[False, True], kind='mergesort'),
         'machine_counts')
    de = E[['machine_id', 'serial_id', 'machine_type', 'rate_group', 'model', 'months', 'tickets_obs', 'expected',
            'obs_rate', 'type_rate', 'alpha_nb', 'p_poisson', 'q_bh', 'p_nb', 'q_nb', 'eb_rate',
            'serial_unplanned_tickets', 'workload_outsized', 'rate_outlier', 'nb_outlier', 'class', 'customer',
            'host', 'device_status', 'first_active', 'tickets_before_first_active', 'tickets_after_last_active']].copy()
    de['type_rate'] = 100 * de.type_rate
    de = de.rename(columns={'type_rate': 'type_rate_per_100_months', 'obs_rate': 'obs_rate_per_100_months',
                            'eb_rate': 'eb_rate_per_100_months'})
    for c in ('expected', 'obs_rate_per_100_months', 'type_rate_per_100_months', 'eb_rate_per_100_months', 'alpha_nb'):
        de[c] = de[c].round(6)
    save(de.sort_values(['q_bh', 'machine_id'], kind='mergesort', na_position='last'), 'device_exposure')
    zr = zac_rates.set_index('machine_type').tickets_per_100_active_months
    rate_table['zac_rate_per_100_active_months'] = rate_table.machine_type.map(zr)
    rt = E.groupby('machine_type').agg(rate_outliers=('rate_outlier', 'sum'),
                                       nb_outliers=('nb_outlier', 'sum'),
                                       chronic=('class', lambda s: int((s == 'chronic_outlier').sum())),
                                       workload_outsized=('workload_outsized', 'sum'))
    rate_table = rate_table.merge(rt, left_on='machine_type', right_index=True, how='left')
    save(rate_table.sort_values('exposure_months', ascending=False, kind='mergesort'), 'type_rates')
    save(lorenz, 'lorenz')
    save(type_mix, 'type_mix')
    save(ep.sort_values(['tickets', 'machine_id'], ascending=[False, True], kind='mergesort'), 'episodes')
    save(pre, 'pre_ticket')
    save(pre_summary, 'pre_ticket_summary')
    save(profile, 'profile')
    save(issue_mix, 'issue_mix')

    # Customers
    tot_dev = dev.assigned_customer.value_counts()
    cu = mach.groupby('customer').agg(ticketed_machines=('machine_id', 'size'),
                                      unplanned_tickets=('unplanned_tickets', 'sum'),
                                      workload_outsized_machines=('workload_outsized', 'sum'),
                                      chronic_outlier_machines=('chronic_outlier', 'sum'))
    ec = E.groupby('customer').agg(exposure_devices=('machine_id', 'size'), exposure_months=('months', 'sum'),
                                   exposure_tickets=('tickets_obs', 'sum'), expected_tickets=('expected', 'sum'))
    cu = cu.join(ec, how='outer').join(tot_dev.rename('total_devices'), how='outer').fillna(0)
    for c in ('ticketed_machines', 'unplanned_tickets', 'workload_outsized_machines', 'chronic_outlier_machines',
              'exposure_devices', 'exposure_months', 'exposure_tickets', 'total_devices'):
        cu[c] = cu[c].astype(int)
    cu['expected_tickets'] = cu.expected_tickets.round(3)
    cu = cu.rename_axis('customer').reset_index()
    cu = cu[(cu.ticketed_machines > 0) | (cu.total_devices > 0)]
    cu = cu[['customer', 'chronic_outlier_machines', 'workload_outsized_machines', 'total_devices',
             'ticketed_machines', 'unplanned_tickets', 'exposure_devices', 'exposure_months', 'exposure_tickets',
             'expected_tickets']]
    save(cu.sort_values(['chronic_outlier_machines', 'workload_outsized_machines', 'unplanned_tickets', 'customer'],
                        ascending=[False, False, False, True], kind='mergesort'), 'customer_chronic')

    # Chronic categories
    chron = E[E['class'] == 'chronic_outlier'][['machine_id', 'serial_id', 'model', 'serial_unplanned_tickets']]
    cc_rows, top3 = [], []
    for row in chron.sort_values('machine_id').itertuples():
        vc = sc[sc.machine_id == row.serial_id].category.fillna('[Missing]').value_counts()
        vc = vc.reset_index().sort_values(['count', 'category'], ascending=[False, True], kind='mergesort')
        for v in vc.itertuples():
            cc_rows.append({'machine_id': row.machine_id, 'model': row.model,
                            'total_tickets': row.serial_unplanned_tickets,
                            'category': v.category, 'tickets': int(v.count)})
        t3 = {'machine_id': row.machine_id, 'serial_id': row.serial_id, 'model': row.model,
              'total_tickets': row.serial_unplanned_tickets,
              'exposure_months': int(emap.loc[row.machine_id, 'months']),
              'tickets_in_period': int(emap.loc[row.machine_id, 'tickets_obs']),
              'expected': round(float(emap.loc[row.machine_id, 'expected']), 3),
              'q_bh': float(emap.loc[row.machine_id, 'q_bh']), 'q_nb': float(emap.loc[row.machine_id, 'q_nb']),
              'customer': emap.loc[row.machine_id, 'customer'], 'distinct_categories': int(len(vc))}
        for i in range(3):
            t3[f'cat{i + 1}'] = vc.category.iloc[i] if i < len(vc) else None
            t3[f'cat{i + 1}_tickets'] = int(vc['count'].iloc[i]) if i < len(vc) else 0
        top3.append(t3)
    save(pd.DataFrame(cc_rows), 'chronic_categories')
    chronic_top3 = save(pd.DataFrame(top3), 'chronic_top3')

    # ---------------------------------------------------------------- Private files (gitignored)
    inv_serial, inv_acct, case_acct = private['serial'], private['account'], private['case_account']
    pv = mach[mach.workload_outsized].copy()
    acct_by_s = sc.assign(acct=sc.case_id.map(case_acct)).groupby('machine_id').acct
    pv['real_serial'] = pv.machine_id.map(inv_serial)
    pv['real_account_modal'] = pv.machine_id.map(acct_by_s.agg(modal))
    pv['real_accounts_all'] = pv.machine_id.map(acct_by_s.agg(lambda s: ' | '.join(sorted(set(s.dropna())))))
    pv['customer_real_name'] = pv.customer.map(inv_acct)
    pv = pv[['machine_id', 'telemetry_id', 'real_serial', 'real_account_modal', 'real_accounts_all', 'customer',
             'customer_real_name', 'unplanned_tickets', 'model', 'machine_type', 'device_status', 'class']]
    pv = pv.sort_values(['unplanned_tickets', 'machine_id'], ascending=[False, True], kind='mergesort')
    p1 = PRIVATE / 'htm_private_outsized_machines.csv'
    pv.to_csv(p1, index=False)
    cust_any = sorted(set(cu.customer[(cu.chronic_outlier_machines > 0) | (cu.workload_outsized_machines > 0)]))
    pc = pd.DataFrame({'customer': cust_any, 'real_account_name': [inv_acct.get(c) for c in cust_any]})
    pc = pc.merge(cu[['customer', 'chronic_outlier_machines', 'workload_outsized_machines', 'total_devices',
                      'ticketed_machines', 'unplanned_tickets']], on='customer', how='left')
    p2 = PRIVATE / 'htm_private_customer_names.csv'
    pc.to_csv(p2, index=False)
    print(f'  wrote {p1.relative_to(OUTPUTS.parents[1])} ({len(pv)} rows), '
          f'{p2.relative_to(OUTPUTS.parents[1])} ({len(pc)} rows)  [private, gitignored]')

    # ---------------------------------------------------------------- Checks
    print('Checks ...')
    check('workload-outsized machines >= threshold of the 185th machine', W['outsized_machines'],
          int((W['counts'] >= W['threshold']).sum()))
    check('every exposure device has months in [0, 12]', True, bool(E.months.between(0, 12).all()))
    check('exposure population excludes shared/NULL host', 0, int(E.host.isna().sum() + E.host.isin(shared).sum()))
    check('chronic = outsized AND rate outlier', int((E.workload_outsized & E.rate_outlier).sum()),
          int(cls.get('chronic_outlier', 0)))
    check('NB-kept outliers <= Poisson outliers', True, nb_kept <= rate_n)
    # Reconciled with the independent clean-room build (see docstring).
    check('D2 exposure devices / months / tickets', (6621, 71559, 5395),
          (int(len(E)), int(E.months.sum()), int(E.tickets_obs.sum())))
    check('D2 Poisson rate outliers (literal numerator)', 118, rate_n)
    check('D2 Poisson outliers kept under NB (E-form and y-form alpha)', (2, 2), (nb_kept, nb_y_kept))
    check('D3 chronic / high-volume-expected / rate-outlier-only', (113, 93, 5),
          tuple(int(cls.get(k, 0)) for k in ('chronic_outlier', 'high_volume_expected', 'rate_outlier_only')))
    check('D4 null covers every exposure-population device (top 5% = 332)', (6621, 332),
          (C4['devices'], math.ceil(TOP_SHARE * C4['devices'])))
    check('episode counts never exceed tickets', True,
          bool(ep[[f'episodes_{g}d' for g in GAPS]].le(ep.tickets, axis=0).all().all()))
    check('episodes monotone in gap (3d >= 7d >= 14d)', True,
          bool(((ep.episodes_3d >= ep.episodes_7d) & (ep.episodes_7d >= ep.episodes_14d)).all()))
    check('pre-ticket rows are usable unplanned tickets', int(len(usable)), len(pre))
    check('lorenz curve ends at 1', 1.0, round(float(lorenz.ticket_share_obs.iloc[-1]), 9))
    check('customer table: outsized machines sum', W['outsized_machines'], int(cu.workload_outsized_machines.sum()))
    check('customer table: chronic machines sum', int(cls.get('chronic_outlier', 0)),
          int(cu.chronic_outlier_machines.sum()))
    check('every customer with an outsized/chronic machine has a real name (private)', 0,
          int(pc.real_account_name.isna().sum()))
    # privacy: no real serial / account / case number in any text column of any public table
    leaks = 0
    for name, df in PUBLIC.items():
        for col, n in text_leaks(df, private['real_strings']).items():
            leaks += n
            print(f'    LEAK in {name}.{col}: {n} values')
    check('public text columns: no real serial / account / case number (cell or token)', 0, leaks)
    sc_det = sorted(f'{c}' for c in chronic_ids)
    check('chronic ids are M##### pseudonyms', True, all(re.fullmatch(r'M\d{5}', c) for c in sc_det))

    # ---------------------------------------------------------------- Summary
    summ = {
        'generated_by': 'verification/high_ticket_machines.py', 'seed': SEED, 'n_sim': N_SIM,
        'definitions': {'period': [PERIOD_START, PERIOD_END], 'min_type_months': MIN_TYPE_MONTHS, 'q_cut': Q_CUT,
                        'workload_rank': W['rank_k'], 'fixed_threshold': FIXED_THRESHOLD, 'top_share': TOP_SHARE,
                        'case_export_period': [sc.opened_at.min()[:10], sc.opened_at.max()[:10]],
                        'episode_gaps_days': list(GAPS), 'n_sim_episodes': N_SIM_EPISODES,
                        'control_offset_days': CONTROL_OFFSET_DAYS, 'shared_internal_host': shared},
        'D1_workload': {k: (r(v) if isinstance(v, float) else v) for k, v in W.items()
                        if k not in ('counts', 'outsized')},
        'D2_exposure': {'devices': int(len(E)), 'devices_with_exposure': int(pos.sum()),
                        'exposure_months_total': int(E.months.sum()), 'tickets': int(E.tickets_obs.sum()),
                        'tickets_on_zero_exposure_devices': zero_exp_tickets,
                        'devices_with_tickets': int((E.tickets_obs > 0).sum()),
                        'unplanned_tickets_in_period': int(len(sc_period)),
                        'in_period_device_matched': int(sc_period.case_id.map(case_to_m).notna().sum()),
                        'overall_rate_per_100_months': r(100 * overall_rate),
                        'zac_overall_rate_per_100_active_months': r(100 * 4916 / 69155),
                        'pooled_small_types': sorted(rate_table.machine_type[rate_table.rate_group == POOL]),
                        'pooled_small_rate_per_100_months': r(float(100 * E.loc[E.rate_group == POOL,
                                                                                    'type_rate'].iloc[0]))
                        if (E.rate_group == POOL).any() else None,
                        'rate_outliers_poisson': rate_n, 'rate_outliers_nb_kept': nb_kept,
                        'rate_outliers_nb_kept_y_form_alpha': nb_y_kept,
                        'nb_outliers_total': int(E.nb_outlier.sum()),
                        'alpha_nb_by_group': {k: r(v) for k, v in E.groupby('rate_group').alpha_nb.first().items()},
                        'alpha_estimator': 'max(0, sum((y - E)^2 - E) / sum(E^2)) per rate group, devices with E > 0',
                        'rate_numerator': 'all population tickets in the period (literal D2), incl. zero-exposure '
                                          'devices',
                        'exposed_numerator_variant': {k: r(v) if isinstance(v, float) else v
                                                      for k, v in exposed_variant.items()}},
        'D3_classes': {k: int(v) for k, v in cls.items()}, 'chronic_outlier_ids': chronic_ids,
        'D3_exposure_diagnostics_by_class': {
            k: {'devices': int(len(g)), 'tickets_in_period': int(g.tickets_obs.sum()),
                'tickets_before_first_active': int(g.tickets_before_first_active.sum()),
                'devices_with_ticket_before_first_active': int((g.tickets_before_first_active > 0).sum()),
                'tickets_after_last_active': int(g.tickets_after_last_active.sum()),
                'devices_exposure_lt12_months': int((g.months < 12).sum())}
            for k, g in E.groupby('class')},
        'D4_concentration': {k: r(v) if isinstance(v, float) else v for k, v in C4.items()},
        'D4_variants': {g: {k: r(v) if isinstance(v, float) else v for k, v in d.items()}
                        for g, d in d4_variants.items()},
        'D5_episodes': {g: {k: (r(v) if isinstance(v, float) else [r(x) for x in v] if isinstance(v, tuple) else v)
                            for k, v in d.items()} for g, d in D5.items()},
        'clustering': {k: r(v) if isinstance(v, float) else v for k, v in cl.items()},
        'sensitivity_excl_monitoring': {k: r(v) if isinstance(v, float) else v for k, v in sens.items()},
        'sensitivity_text': sens_text,
        'category_diff_pp_outsized_minus_other': {k: r(v, 2) for k, v in cat_diff.diff_pp.items()
                                                  if abs(v) >= 1.0},
        'checks': {'PASS': sum(c['status'] == 'PASS' for c in CHECKS),
                   'FAIL': sum(c['status'] == 'FAIL' for c in CHECKS)},
        'check_list': [{k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v))
                        for k, v in c.items()} for c in CHECKS],
    }
    path = OUTPUTS / f'{PREFIX}summary.json'
    path.write_text(json.dumps(summ, indent=2, default=lambda o: o.item() if hasattr(o, 'item') else str(o)) + '\n')
    print(f'  wrote {path.relative_to(OUTPUTS.parents[1])}')
    print(f"Done in {time.time() - t0:.1f} s; checks {summ['checks']}")
    print(chronic_top3[['machine_id', 'model', 'total_tickets', 'exposure_months', 'tickets_in_period', 'expected',
                        'cat1', 'cat1_tickets']].to_string(index=False))
    return 1 if summ['checks']['FAIL'] else 0


def plots():
    """Draw the figures last, from the htm_* outputs just written (viz/high_ticket/run_all.py).
    Skipped with a message if matplotlib is missing. Returns 1 if plotting failed, else 0."""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print('Plots skipped: matplotlib is not installed (the htm_* tables above are complete without them).')
        return 0
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viz' / 'high_ticket'))
        from run_all import main as plot_main
        plot_main()
    except Exception as exc:  # report, but keep the analysis outputs and their check status
        print(f'Plots failed: {type(exc).__name__}: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    status = main()
    sys.exit(max(status, plots()))
