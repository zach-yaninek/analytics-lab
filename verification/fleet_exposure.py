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
  F1 Population. Machines on the list (9,294) EXCEPT those on a third-party service plan (THIRD_PARTY_PLANS:
     Vogeltronix, 239 machines at one account, 3 tickets in about 3,000 machine-months: their service work rarely
     reaches this case export, most likely because the third party handles it (IPA is asked to confirm), so they are
     treated as not at risk of an IPA ticket; reported separately, and the fleet rate with them is a sensitivity). Tickets = unplanned tickets (Zac's service_cases view: excludes Planned work,
     Cancelled request, Duplicate case) opened 2025-08-01..2026-08-31 (Eastern) whose serial is in the population.
     Each ticket is attributed to the machine's account ON THE LIST (customer), so numerator and denominator use
     the same account. The list holds only machines active on 2026-10-19: tickets on serials that are not listed
     (removed or replaced machines) drop out with their unknown exposure; fx_unlisted_by_model.csv and the
     rate_with_unlisted_max column (unlisted tickets put back with their least possible exposure, first to last
     ticket) bound the effect.
  F2 Installed machine-months. Exposure runs from max(2025-08-01, install date) to 2026-09-01 (exclusive), in months
     of 365.25/12 days. If a machine has a ticket in the period before its install date (4 machines), exposure starts
     on that ticket's date: the list's install date is the install at the current account. Machines installed after
     the period have 0 months; they are not counted as machines in the rate tables and have no age band.
     Sensitivity: go-live date (install date when go-live is blank) instead of install date.
  F3 Rate groups. Models with >= MIN_TYPE_MONTHS (100) installed months get their own rate; the rest share one
     pooled group (POOL). Age band = years from install date to the midpoint of the machine's exposure window
     (full period; for each half's fit, that half's window), cut at 1, 2, 4, 6, 8, 10 years.
  F4 Expected tickets. A Poisson main-effects model fitted by iterative proportional fitting:
     E_i = months_i x a[model group] x b[age band] (x c[service status] in the coverage variant), so expected equals
     observed in total for every level of every factor. Main = model + age; variants = model only (a plain model
     rate) and model + age + coverage. Service status is the list's 2026-10-19 snapshot, applied to the whole period.
     Model comparisons use the age-standardised ratio from the same joint fit: O_model / sum(months x b[age]),
     scaled so the fleet's ratio is 1 (crude rate ratios are kept as descriptive columns).
  F5 Customers. STR = O / E. Two flags:
     Flagged (Poisson rule, as for machines) = >= 5 tickets AND Poisson BH q < 0.05 (BH over customers with E > 0):
       more tickets than the fleet's model + age rates predict for that customer's machines, beyond Poisson chance.
       Tickets cluster within a customer's machines, so this is a screening flag, not proof of a problem.
     Beyond the funnel (extreme tier) = above the 99.8% limit of an overdispersion-adjusted funnel (Spiegelhalter
       2005) on the square-root scale: y = sqrt(O/E), s = 1/(2 sqrt(E)), z = (y - 1)/s; tau^2 by the additive
       random-effects moment estimator on z winsorised at the 10th/90th percentiles (a somewhat low estimate for
       long-tailed heterogeneity, so the funnel is if anything narrow); z_D = (y - 1)/sqrt(s^2 + tau^2);
       z_D > 3.090: outside the normal spread among customers, not just beyond chance.
     Also the empirical-Bayes STR (gamma-Poisson, alpha by moments).
  F6 Machines. Flagged = >= 5 tickets AND Poisson BH q < 0.05 against E (model + age), BH over machines with E > 0.
     The negative-binomial check (one dispersion per model group) is reported alongside.
  F7 Consistent outliers. The period is split at its midpoint, 2026-02-15 (H1 = 2025-08-01..2026-02-14,
     H2 = 2026-02-15..2026-08-31); each half's expected uses rates fitted within that half (model + age).
     Variants (12) = (expected: model | model+age | model+age+coverage) x (tickets | 7-day episodes)
       x (all unplanned | excluding monitoring-template and No Trouble Found tickets).
     Customers and machines: flagged (F5 Poisson rule / F6 rule) in >= 10 of the 12 variants AND one-sided Poisson
       p < 0.05 (O vs E) in each half: "persistently above the fleet's model + age rate".
     Consistently low customers, the mirror image: lower-tail Poisson BH q < 0.05 in >= 10 of the 12 variants AND
       lower-tail p < 0.05 in each half. Low counts mostly mean few tickets reach IPA (no coverage, not
       serviceable), not more reliable machines.
     Models: age-standardised ratio (F4) with a 95% interval above 1 in both halves (below 1 in both =
       consistently low).
     Persistence statistics (customers with E >= 3 in each half): split-half Spearman of STR, top-decile
       retention, significant (p < 0.05) in both halves, and out of sample: of the customers flagged (Poisson BH
       q < 0.05) in one half, the share significant in the other. Two nulls: a stratified permutation (second-half
       results shuffled among customers in the same decile of second-half expected tickets: heterogeneity, but not
       persistent) and Poisson draws from each half's expected (no heterogeneity at all).
     Machines: second-half O/E by first-half ticket count, for machines with exposure in both halves, against two
       permutations of first-half counts: within model-group x age-band cells, and within customer (persistence
       that comes from the site, not the machine). Out of sample: machines flagged (q < 0.05) in H1, their H2 O/E.
  F8 Uncertainty. Rates get Byar's 95% Poisson interval and a cluster bootstrap (accounts resampled with
     replacement, N_BOOT draws, seed 15072); tickets cluster within accounts, so the bootstrap interval is the one
     to read. For a group in fewer than MIN_CLUSTERS accounts or with no tickets the bootstrap interval is
     degenerate, so the reported interval is the wider of the two (ci_method says which); a group in one account
     is 'not estimable' against the fleet.

Privacy: outputs in verification/outputs/fleet/ hold only pseudonyms (Customer NNN, S#####, M#####), model,
type, category and status labels, and aggregates. Accounts and serials that never appear on a ticket get new
pseudonyms after the existing ones (common.extend_maps), so existing labels do not change. Real names for the
real-name chart variants go only to data/private/fx_private_customer_names.csv (gitignored). A final check
(text_leaks) scans every public text column and every string in fx_summary.json, case-insensitively and as word
n-grams, for real account names, addresses, cities and location labels, and for real serials, case numbers, zips
and phones (whole cells, and 4+-digit tokens outside pseudonyms and dates).

Run:  cd /home/user/analytics-lab && python3 -I verification/fleet_exposure.py
Deterministic: fixed seed, stable sorts. Exit status 1 if any check fails.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import json  # noqa: E402
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
MIN_CLUSTERS = 10
Q_CUT = H.Q_CUT
MONTH_DAYS = 365.25 / 12
PERIOD_START = pd.Timestamp('2025-08-01')
PERIOD_END = pd.Timestamp('2026-09-01')          # exclusive
SPLIT = (PERIOD_START + (PERIOD_END - PERIOD_START) / 2).normalize()   # 2026-02-15
AGE_EDGES = [-np.inf, 1, 2, 4, 6, 8, 10, np.inf]
AGE_LABELS = ['<1', '1-2', '2-4', '4-6', '6-8', '8-10', '10+']
POOL = 'Other models (<100 months each)'
THIRD_PARTY_PLANS = ('Vogeltronix',)
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


# ----------------------------------------------------------------------------------------------------------------
# Privacy scan
# ----------------------------------------------------------------------------------------------------------------
SAFE_DIGITS = re.compile(r'Customer \d+|Host \d+|Location \d+|\b[SMT]\d{5}\b|\b\d{4}-\d{2}(?:-\d{2})?\b')


def norm(text):
    """Lower case, punctuation to spaces, single spaces: how names are compared in the privacy scan."""
    return ' '.join(re.sub(r'[^0-9a-z]+', ' ', str(text).lower()).split())


def real_sets(maps):
    """Real strings for the privacy scan (never written): text names compared as normalised word n-grams, digit
    identifiers compared as whole cells and as 4+-digit tokens."""
    text_cols = ['Account Name', 'Hospital Address', 'Hospital City', 'Location', 'Vendor Credentialing Notes']
    digit_cols = ['Serial Number', 'Hospital Zip Code', 'Phone']
    names = set(map(str, maps['account'])) | common.equipment_real_strings(columns=text_cols)
    ids = set(map(str, maps['serial'])) | set(map(str, maps['case'])) \
        | common.equipment_real_strings(columns=digit_cols)
    text = {n for n in map(norm, names | {i for i in ids if not i.isdigit()}) if len(n) >= 4 and not n.isdigit()}
    digit = {i for i in ids if i.isdigit()} | {re.sub(r'\D', '', i) for i in ids if len(re.sub(r'\D', '', i)) >= 7}
    return {'text': text, 'digit': digit, 'max_words': max(len(t.split()) for t in text)}


def text_leaks(df, real):
    """Real identifiers in the text columns of df. Numeric columns hold counts and rates and are not tested; every
    id column in the public tables is text."""
    out = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            continue
        hits = set()
        for v in df[col].dropna().astype(str).unique():
            if v.strip() in real['digit']:
                hits.add(v)
            words = norm(v).split()
            for k in range(1, min(real['max_words'], len(words)) + 1):
                hits.update(' '.join(words[i:i + k]) for i in range(len(words) - k + 1)
                            if ' '.join(words[i:i + k]) in real['text'])
            hits.update(t for t in re.findall(r'\d{4,}', SAFE_DIGITS.sub(' ', v)) if t in real['digit'])
        if hits:
            out[col] = len(hits)
    return out


def json_strings(obj):
    """Every key and string value in a JSON-like object, for the privacy scan."""
    if isinstance(obj, dict):
        return [str(k) for k in obj] + [s for v in obj.values() for s in json_strings(v)]
    if isinstance(obj, (list, tuple)):
        return [s for v in obj for s in json_strings(v)]
    return [obj] if isinstance(obj, str) else []


# ----------------------------------------------------------------------------------------------------------------
# Statistics helpers (numpy only)
# ----------------------------------------------------------------------------------------------------------------
def byar(k, z=Z95):
    """Byar's approximation to the exact Poisson interval for a count k (within 1% for k >= 5; upper limit for
    k = 0 is 3.7, close to the exact 3.69)."""
    k = np.asarray(k, float)
    lo = np.where(k > 0, k * (1 - 1 / (9 * np.maximum(k, 1)) - z / (3 * np.sqrt(np.maximum(k, 1)))) ** 3, 0.0)
    hi = (k + 1) * (1 - 1 / (9 * (k + 1)) + z / (3 * np.sqrt(k + 1))) ** 3
    return lo, hi


def ipf(df, count, factors, months='months', iters=500, tol=1e-9):
    """Poisson main-effects fit by iterative proportional fitting.

    E_i = months_i x base x prod_f a_f[level_i(f)], so that sum(E) = sum(count) within every level of every factor.
    A level with no observed tickets gets expected 0 (its rate is 0); rows with no level (NaN) get 0.
    Returns (E as an array, {factor: Series of level multipliers}, base rate).
    """
    base = df[count].sum() / df[months].sum()
    e = df[months].astype(float) * base
    mult = {f: pd.Series(1.0, index=pd.Index(df[f].dropna().unique())) for f in factors}
    for _ in range(iters):
        worst = 0.0
        for f in factors:
            obs = df.groupby(f, observed=True)[count].sum()
            exp = e.groupby(df[f], observed=True).sum()
            adj = (obs / exp).where(exp > 0, 0.0)
            mult[f] = mult[f] * adj.reindex(mult[f].index).fillna(0.0)
            e = e * df[f].map(adj).astype(float).fillna(0.0)
            worst = max(worst, float((obs - exp).abs().max()))
        if worst < tol:
            break
    return e.to_numpy(), mult, base


def age_factors_batch(t, mo, iters=300):
    """Age multipliers of the model + age main-effects fit for a batch of (group x age) ticket and month tables
    (shape B x G x A), by the same proportional fitting as ipf(); scale is arbitrary."""
    e = mo * (t.sum((1, 2)) / mo.sum((1, 2)))[:, None, None]
    cm = np.ones((t.shape[0], t.shape[2]))
    with np.errstate(invalid='ignore', divide='ignore'):
        for _ in range(iters):
            r = np.where(e.sum(2) > 0, t.sum(2) / e.sum(2), 0.0)
            e = e * r[:, :, None]
            c = np.where(e.sum(1) > 0, t.sum(1) / e.sum(1), 0.0)
            e = e * c[:, None, :]
            cm = cm * c
    return cm


def ipf_expected(df, count, factors, months='months'):
    return ipf(df, count, factors, months)[0]


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


def upper_p(O, E):
    """One-sided Poisson P(X >= O | E); NaN where E == 0."""
    return np.array([H.poisson_sf(o, e) if e > 0 else np.nan for o, e in zip(O, E)])


def lower_p(O, E):
    """One-sided Poisson P(X <= O | E); NaN where E == 0."""
    return np.array([1.0 - H.poisson_sf(o + 1, e) if e > 0 else np.nan for o, e in zip(O, E)])


def bh_q(p):
    """BH q-values over the non-NaN p-values (NaN stays NaN)."""
    p = np.asarray(p, float)
    q = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    q[ok] = H.bh(p[ok])
    return q


def poisson_flags(O, E, low=False):
    """Flag on the Poisson rule used for machines: >= 5 tickets and BH q < 0.05 over units with E > 0.
    low=True: the mirror image, lower-tail BH q < 0.05 (no minimum count)."""
    O, E = np.asarray(O, float), np.asarray(E, float)
    if low:
        return bh_q(lower_p(O, E)) < Q_CUT
    return (O >= MIN_FLAG_TICKETS) & (bh_q(upper_p(O, E)) < Q_CUT)


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


def null_row(level, statistic, units, observed, perm, pois=None, note=''):
    perm = np.asarray(perm, float)
    return {'level': level, 'statistic': statistic, 'units': units, 'observed': observed,
            'perm_null_median': float(np.nanmedian(perm)), 'perm_null_p2_5': float(np.nanpercentile(perm, 2.5)),
            'perm_null_p97_5': float(np.nanpercentile(perm, 97.5)),
            'perm_p_value': float((np.sum(perm >= observed) + 1) / (len(perm) + 1)),
            'poisson_null_median': float(np.median(pois)) if pois is not None else np.nan,
            'poisson_null_p97_5': float(np.percentile(pois, 97.5)) if pois is not None else np.nan, 'note': note}


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
    htm = pd.read_csv(OUTPUTS / 'htm_device_exposure.csv')
    fxdb = pd.read_csv(DB_OUT / 'fxdb_devices.csv') if (DB_OUT / 'fxdb_devices.csv').exists() else None
    fxdb_match = pd.read_csv(DB_OUT / 'fxdb_match_summary.csv') if (DB_OUT / 'fxdb_match_summary.csv').exists() \
        else None
    return raw, maps, sc, eq, real_sets(maps), htm, fxdb, fxdb_match


def months_between(start, end):
    return ((end - start).dt.days.clip(lower=0) / MONTH_DAYS).astype(float)


def age_band(start, end, install):
    """Age band at the midpoint of [start, end); NaN when the window is empty."""
    mid = start + (end - start) / 2
    years = ((mid - install).dt.days / 365.25).clip(lower=0)
    band = pd.cut(years, AGE_EDGES, labels=AGE_LABELS, right=False)
    return pd.Categorical(band.where(end > start), categories=AGE_LABELS, ordered=True), years


def machine_frame(eq, maps, sc):
    """One row per listed machine: pseudonyms, attributes, exposure (full period and halves), ticket counts."""
    m = pd.DataFrame({'serial': eq.serial, 'serial_id': eq.serial.map(maps['serial']),
                      'customer': eq.account.map(maps['account']), 'model': eq.model, 'family': eq.family,
                      'service_status': eq.service_status, 'service_plan': eq.service_plan,
                      'ownership': eq.ownership, 'country': eq.country,
                      'install_date': eq.install_date, 'go_live_date': eq.go_live_date})
    m['third_party'] = m.service_plan.isin(THIRD_PARTY_PLANS)
    t = sc[sc.serial.isin(set(m.serial)) & (sc.ts >= PERIOD_START) & (sc.ts < PERIOD_END)].copy()
    first = t.groupby('serial').ts.min().dt.normalize()
    m['first_ticket'] = m.serial.map(first)
    m['ticket_before_install'] = m.first_ticket < m.install_date.dt.normalize()
    m['start'] = m[['install_date', 'first_ticket']].min(axis=1).clip(lower=PERIOD_START)
    live = m.go_live_date.fillna(m.install_date)
    m['start_live'] = pd.concat([live, m.first_ticket], axis=1).min(axis=1).clip(lower=PERIOD_START)
    end = pd.Series(PERIOD_END, index=m.index)
    split = pd.Series(SPLIT, index=m.index)
    m['months'] = months_between(m.start, end)
    m['months_live'] = months_between(m.start_live, end)
    end_h1 = split.where(m.start < SPLIT, m.start)
    start_h2 = m.start.clip(lower=SPLIT)
    m['months_h1'] = months_between(m.start, end_h1)
    m['months_h2'] = months_between(start_h2, end)
    m['age_band'], m['age_years'] = age_band(m.start, end, m.install_date)
    m['age_band_h1'], _ = age_band(m.start, end_h1, m.install_date)
    m['age_band_h2'], _ = age_band(start_h2, end, m.install_date)

    # Ticket counts: all / core, full / halves, and 7-day episodes.
    def count(frame):
        return m.serial.map(frame.groupby('serial').size()).fillna(0).astype(int)
    m['tickets'] = count(t)
    m['tickets_h1'] = count(t[t.ts < SPLIT])
    m['tickets_h2'] = count(t[t.ts >= SPLIT])
    m['tickets_core'] = count(t[t.core])
    for scope, frame in (('', t), ('_core', t[t.core])):
        s = frame.sort_values(['serial', 'ts', 'case_id'], kind='mergesort')
        gap = s.groupby('serial').ts.diff().dt.total_seconds() / 86400
        new = gap.isna() | (gap > EPISODE_GAP_DAYS)
        m[f'episodes{scope}'] = m.serial.map(new.groupby(s.serial).sum()).fillna(0).astype(int)
    return m, t


def add_rate_groups(m):
    model_months = m.groupby('model').months.sum()
    m['rate_group'] = np.where(m.model.map(model_months) >= MIN_TYPE_MONTHS, m.model, POOL)
    return m


# ----------------------------------------------------------------------------------------------------------------
# Rates and ratios by group, with Byar and cluster-bootstrap intervals
# ----------------------------------------------------------------------------------------------------------------
def _cluster_sums(m, by, cols, clusters):
    idx = m.customer.map({a: i for i, a in enumerate(clusters)}).to_numpy()
    levels = sorted(m[by].dropna().unique(), key=str)
    lev = m[by].map({v: i for i, v in enumerate(levels)})
    ok = lev.notna().to_numpy()
    lev = lev[ok].astype(int).to_numpy()
    out = []
    for col in cols:
        a = np.zeros((len(levels), len(clusters)))
        np.add.at(a, (lev, idx[ok]), m[col].to_numpy(float)[ok])
        out.append(a)
    return levels, out


def classify(g, lo_col, hi_col):
    return np.select([g.clusters < 2, g[lo_col] > 1, g[hi_col] < 1],
                     ['not estimable (one account)', 'above', 'below'], 'not different')


def group_rates(m, by, W, clusters, tickets='tickets', months='months', extra=None):
    """Rates per 100 months for each level of `by`: Byar and cluster-bootstrap CIs, the ratio to the fleet, and its
    interval (bootstrap; the wider of bootstrap and Byar for groups in < MIN_CLUSTERS clusters or with 0 tickets)."""
    levels, (T, M) = _cluster_sums(m, by, [tickets, months], clusters)
    Tb, Mb = W @ T.T, W @ M.T
    with np.errstate(invalid='ignore', divide='ignore'):
        rate_b = Tb / Mb
        ratio_b = rate_b / (Tb.sum(1) / Mb.sum(1))[:, None]
    fleet = m[tickets].sum() / m[months].sum()
    exposed = m[m[months] > 0]
    g = exposed.groupby(by, observed=True).agg(machines=('serial', 'size'),
                                               machines_with_ticket=(tickets, lambda s: int((s > 0).sum())),
                                               clusters=('customer', 'nunique')).reindex(levels)
    g[['machines', 'machines_with_ticket', 'clusters']] = g[['machines', 'machines_with_ticket', 'clusters']] \
        .fillna(0).astype(int)
    g['months'], g['tickets'] = M.sum(1), T.sum(1)
    g['rate_per_100'] = 100 * g.tickets / g.months
    lo, hi = byar(g.tickets)
    g['byar_lo'], g['byar_hi'] = 100 * lo / g.months, 100 * hi / g.months
    blo, bhi = pct_ci(rate_b)
    g['boot_lo'], g['boot_hi'] = 100 * blo, 100 * bhi
    g['ratio_to_fleet'] = g.rate_per_100 / (100 * fleet)
    rlo, rhi = pct_ci(ratio_b)
    weak = (g.clusters < MIN_CLUSTERS) | (g.tickets == 0)
    g['ci_method'] = np.where(weak, 'wider of bootstrap and Byar', 'cluster bootstrap')
    g['ci_lo'] = np.where(weak, np.fmin(g.boot_lo, g.byar_lo), g.boot_lo)
    g['ci_hi'] = np.where(weak, np.fmax(g.boot_hi, g.byar_hi), g.boot_hi)
    g['ratio_lo'] = np.where(weak, np.fmin(rlo, g.byar_lo / (100 * fleet)), rlo)
    g['ratio_hi'] = np.where(weak, np.fmax(rhi, g.byar_hi / (100 * fleet)), rhi)
    g['vs_fleet'] = classify(g, 'ratio_lo', 'ratio_hi')
    g['share_of_machines'] = g.machines / g.machines.sum()
    g['share_of_months'] = g.months / g.months.sum()
    g['share_of_tickets'] = g.tickets / g.tickets.sum()
    g['share_machines_with_ticket'] = g.machines_with_ticket / g.machines.where(g.machines > 0)
    g['fleet_rate_per_100'] = 100 * fleet
    if extra is not None:
        g = g.join(extra)
    g.index.name = by
    return g.reset_index().rename(columns={'clusters': 'accounts'}), float(fleet)


def age_standardised(m, by, W, clusters, tickets='tickets', months='months', age='age_band'):
    """Age-standardised ratio per level of `by` from the joint model + age fit (F4): O / sum(months x b[age]),
    scaled so the fleet's ratio is 1, with a cluster-bootstrap interval (wider of bootstrap and Byar for weak
    groups) and the classification against 1."""
    d = m[m[months] > 0]
    _, mult, base = ipf(d, tickets, ['rate_group', age], months=months)
    e_age = d[months] * base * d[age].map(mult[age]).astype(float).fillna(0.0)
    d = d.assign(_e=e_age * d[tickets].sum() / e_age.sum())
    levels, (T, E) = _cluster_sums(d, by, [tickets, '_e'], clusters)
    # Bootstrap: re-fit the joint model + age fit in every resample (on the resampled group x age tables), so the
    # interval carries the uncertainty of the age factors and of the fleet level as well as of the group's own count.
    ci = d.customer.map({a: i for i, a in enumerate(clusters)}).to_numpy()
    groups = sorted(d.rate_group.unique())
    gi = d.rate_group.map({g: i for i, g in enumerate(groups)}).to_numpy()
    ai = d[age].map({a: i for i, a in enumerate(AGE_LABELS)}).astype(int).to_numpy()
    li = d[by].map({v: i for i, v in enumerate(levels)}).astype(int).to_numpy()
    C, G, A, L = len(clusters), len(groups), len(AGE_LABELS), len(levels)
    tg, mg, ml = np.zeros((C, G, A)), np.zeros((C, G, A)), np.zeros((C, L, A))
    np.add.at(tg, (ci, gi, ai), d[tickets].to_numpy(float))
    np.add.at(mg, (ci, gi, ai), d[months].to_numpy(float))
    np.add.at(ml, (ci, li, ai), d[months].to_numpy(float))

    def ratios(w):
        t_ = (w @ tg.reshape(C, -1)).reshape(-1, G, A)
        m_ = (w @ mg.reshape(C, -1)).reshape(-1, G, A)
        l_ = (w @ ml.reshape(C, -1)).reshape(-1, L, A)
        o_ = w @ T.T
        cm = age_factors_batch(t_, m_)
        with np.errstate(invalid='ignore', divide='ignore'):
            return o_ * (m_.sum(1) * cm).sum(1)[:, None] / (t_.sum((1, 2))[:, None] * (l_ * cm[:, None, :]).sum(2))

    point = ratios(np.ones((1, C)))[0]
    check(f'age-standardised ({by}, {tickets}): batch re-fit at unit weights = point estimate', 0.0,
          float(np.nanmax(np.abs(point - T.sum(1) / E.sum(1)))), tol=1e-6)
    lo, hi = pct_ci(ratios(W))
    g = pd.DataFrame({by: levels, 'tickets': T.sum(1), 'expected_age_only': E.sum(1)})
    g['clusters'] = d.groupby(by).customer.nunique().reindex(levels).to_numpy()
    g['age_std_ratio'] = g.tickets / g.expected_age_only
    blo, bhi = byar(g.tickets)
    weak = (g.clusters < MIN_CLUSTERS) | (g.tickets == 0)
    g['age_std_lo'] = np.where(weak, np.fmin(lo, blo / g.expected_age_only), lo)
    g['age_std_hi'] = np.where(weak, np.fmax(hi, bhi / g.expected_age_only), hi)
    g['age_std_vs_fleet'] = classify(g, 'age_std_lo', 'age_std_hi')
    return g.drop(columns=['tickets', 'clusters'])


# ----------------------------------------------------------------------------------------------------------------
# Customers
# ----------------------------------------------------------------------------------------------------------------
def customer_table(m, count, expected):
    c = m.assign(_o=m[count], _e=expected).groupby('customer').agg(O=('_o', 'sum'), E=('_e', 'sum'))
    zd, tau2, phi = funnel(c.O, c.E)
    c['z_d'] = zd
    return c, tau2, phi


# ----------------------------------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------------------------------
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    print('Loading inputs')
    raw, maps, sc, eq, real, htm, fxdb, fxdb_match = load_inputs()
    m_all, t_all = machine_frame(eq, maps, sc)
    third = m_all[m_all.third_party]
    m = add_rate_groups(m_all[~m_all.third_party].copy().reset_index(drop=True))
    t = t_all[t_all.serial.isin(set(m.serial))]
    accounts = sorted(m.customer.unique())
    W = boot_weights(len(accounts))
    rng = np.random.default_rng(SEED)

    # ------------------------------------------------------------------ Match between tickets and the list
    print('Match')
    in_period = sc[(sc.ts >= PERIOD_START) & (sc.ts < PERIOD_END)]
    listed = set(m_all.serial)
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
            ('listed machines', len(m_all)),
            ('listed accounts', m_all.customer.nunique()),
            ('listed machines on a third-party service plan (excluded)', len(third)),
            ('accounts with only third-party machines (excluded)',
             int(len(set(third.customer) - set(m.customer)))),
            ('unplanned tickets on third-party machines (excluded)', int(third.tickets.sum())),
            ('machines in the population', len(m)),
            ('accounts in the population', m.customer.nunique()),
            ('population machines installed after the period (0 months)', int((m.months == 0).sum())),
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
    check('population + third-party tickets = tickets on listed machines', int(in_period.serial.isin(listed).sum()),
          int(m.tickets.sum() + third.tickets.sum()))
    check('halves sum to the full period (tickets)', int(m.tickets.sum()), int(m.tickets_h1.sum() + m.tickets_h2.sum()))
    check('halves sum to the full period (months)', float(m.months.sum()), float(m.months_h1.sum() + m.months_h2.sum()),
          tol=1e-6)
    check('every exposed machine has an age band', 0, int((m.months > 0).sum() - m.age_band.notna().sum()))

    # Survivorship bound: tickets on unlisted serials by model and half, with the least exposure they could have
    # had (from the day of their first ticket in the period to the day after their last), so the rate with them put
    # back is an upper bound.
    u = unl.assign(half=np.where(unl.ts < SPLIT, 'h1', 'h2'))
    last = u.groupby('serial').agg(model=('model', 'first'), first=('ts', 'min'), last=('ts', 'max'),
                                   tickets=('case_id', 'size'))
    last['min_months'] = ((last['last'].dt.normalize() + pd.Timedelta(days=1) - last['first'].dt.normalize())
                          .dt.days / MONTH_DAYS)
    ub = last.groupby('model').agg(unlisted_serials=('tickets', 'size'), unlisted_tickets=('tickets', 'sum'),
                                   unlisted_min_months=('min_months', 'sum'))
    ub = ub.join(u.pivot_table(index='model', columns='half', values='case_id', aggfunc='size', fill_value=0)
                 .add_prefix('unlisted_tickets_'))
    listed_t = m.groupby('model').agg(listed_tickets=('tickets', 'sum'), listed_tickets_h1=('tickets_h1', 'sum'),
                                      listed_tickets_h2=('tickets_h2', 'sum'))
    ub = listed_t.join(ub, how='outer').fillna(0)
    ub['unlisted_share_of_tickets'] = ub.unlisted_tickets / (ub.unlisted_tickets + ub.listed_tickets)
    ub.index.name = 'model'
    save(ub.reset_index().sort_values(['unlisted_tickets', 'model'], ascending=[False, True]), 'unlisted_by_model')

    # ------------------------------------------------------------------ Expected counts
    print('Expected counts (IPF)')
    m['E_model'] = ipf_expected(m, 'tickets', ['rate_group'])
    m['E'] = ipf_expected(m, 'tickets', ['rate_group', 'age_band'])
    m['E_cov'] = ipf_expected(m, 'tickets', ['rate_group', 'age_band', 'service_status'])
    for h in ('h1', 'h2'):
        d = m.assign(months=m[f'months_{h}'], age_band=m[f'age_band_{h}'])
        m[f'E_{h}'] = ipf_expected(d, f'tickets_{h}', ['rate_group', 'age_band'])
        check(f'E_{h}: expected total = observed total', int(m[f'tickets_{h}'].sum()), float(m[f'E_{h}'].sum()),
              tol=1e-3)
    for col in ('E_model', 'E', 'E_cov'):
        check(f'{col}: expected total = observed total', int(m.tickets.sum()), float(m[col].sum()), tol=1e-3)
    for f in ('rate_group', 'age_band'):
        worst = float((m.groupby(f, observed=True).tickets.sum() - m.groupby(f, observed=True).E.sum()).abs().max())
        check(f'E (model + age) matches observed within every {f}', 0.0, worst, tol=1e-3)
    check('fleet STR = 1', 1.0, float(m.tickets.sum() / m.E.sum()), tol=1e-9)

    # ------------------------------------------------------------------ Rates by group
    print('Rates by model, family, age, coverage, plan, country')
    fleet_rate = 100 * m.tickets.sum() / m.months.sum()
    std = age_standardised(m, 'model', W, accounts).set_index('model')
    models, _ = group_rates(m, 'model', W, accounts, extra=std)
    models['family'] = models.model.map(m.groupby('model').family.first())
    models['own_rate'] = models.months >= MIN_TYPE_MONTHS
    ubm = ub.reindex(models.model).fillna(0)
    models['unlisted_tickets'] = ubm.unlisted_tickets.to_numpy()
    models['rate_with_unlisted_max'] = 100 * (models.tickets + ubm.unlisted_tickets.to_numpy()) / \
        (models.months + ubm.unlisted_min_months.to_numpy())
    models = models.sort_values(['tickets', 'model'], ascending=[False, True])
    save(models, 'model_rates')
    fams, _ = group_rates(m, 'family', W, accounts)
    save(fams.sort_values(['tickets', 'family'], ascending=[False, True]), 'family_rates')
    ages, _ = group_rates(m, 'age_band', W, accounts)
    ages['age_band'] = pd.Categorical(ages.age_band, AGE_LABELS, ordered=True)
    save(ages.sort_values('age_band'), 'age_rates')
    cov, _ = group_rates(m, 'service_status', W, accounts)
    save(cov.sort_values(['months', 'service_status'], ascending=[False, True]), 'coverage_rates')
    plan, _ = group_rates(m_all.assign(rate_group=''), 'service_plan', boot_weights(m_all.customer.nunique()),
                          sorted(m_all.customer.unique()))
    plan['in_population'] = ~plan.service_plan.isin(THIRD_PARTY_PLANS)
    save(plan.sort_values(['months', 'service_plan'], ascending=[False, True]), 'service_plan_rates')
    ctry, _ = group_rates(m, 'country', W, accounts)
    save(ctry, 'country_rates')
    check('model rates: tickets sum to fleet', int(m.tickets.sum()), int(models.tickets.sum()))
    check('model rates: months sum to fleet', float(m.months.sum()), float(models.months.sum()), tol=1e-6)
    check('age rates: tickets sum to fleet', int(m.tickets.sum()), int(ages.tickets.sum()))

    # Models in each half: crude ratio (descriptive) and age-standardised ratio (classification).
    rg, _ = group_rates(m, 'rate_group', W, accounts)
    mo = rg.set_index('rate_group')[['machines', 'accounts', 'months', 'tickets', 'rate_per_100', 'ratio_to_fleet',
                                     'ratio_lo', 'ratio_hi', 'vs_fleet']] \
        .rename(columns={'ratio_to_fleet': 'crude_ratio', 'ratio_lo': 'crude_lo', 'ratio_hi': 'crude_hi',
                         'vs_fleet': 'crude_vs_fleet'})
    mo = mo.join(age_standardised(m, 'rate_group', W, accounts).set_index('rate_group'))
    for h in ('h1', 'h2'):
        g, _ = group_rates(m, 'rate_group', W, accounts, tickets=f'tickets_{h}', months=f'months_{h}')
        mo = mo.join(g.set_index('rate_group')[['tickets', 'rate_per_100', 'ratio_to_fleet']]
                     .rename(columns={'ratio_to_fleet': 'crude_ratio'}).add_suffix(f'_{h}'))
        s = age_standardised(m, 'rate_group', W, accounts, tickets=f'tickets_{h}', months=f'months_{h}',
                             age=f'age_band_{h}').set_index('rate_group')
        mo = mo.join(s.add_suffix(f'_{h}'))
    mo['consistent'] = np.select([(mo.age_std_vs_fleet_h1 == 'above') & (mo.age_std_vs_fleet_h2 == 'above'),
                                  (mo.age_std_vs_fleet_h1 == 'below') & (mo.age_std_vs_fleet_h2 == 'below')],
                                 ['consistently above', 'consistently below'], 'not consistent')
    mo = mo.reset_index().sort_values(['age_std_ratio', 'rate_group'], ascending=[False, True])
    save(mo, 'outlier_models')

    # ------------------------------------------------------------------ Telemetry types
    print('Telemetry types')
    if fxdb is not None:
        basis = 'installed'
        on = fxdb[fxdb.on_list.astype(str).isin(['1', 'True', 'true'])]
        check('fxdb: one device per listed serial', True, bool(on.serial_id.is_unique))
        d = on.drop_duplicates('serial_id').merge(m, on='serial_id', how='inner', validate='one_to_one')
        d['machine_type'] = d.machine_type.map(lambda x: 'Unknown' if common.clean(x) in (None, 'Unknown', 'unknown')
                                               else common.clean(x).lower())
        types, _ = group_rates(d, 'machine_type', W, accounts)
        active = set(on.loc[(on.active_months_in_period > 0) & (on.shared_host.astype(int) == 0), 'serial_id'])
        net = m.assign(networked=np.select([m.serial_id.isin(active), m.serial_id.isin(set(on.serial_id))],
                                           ['networked, active in period', 'networked, not active'],
                                           'not networked'))
        netr, _ = group_rates(net, 'networked', W, accounts)
        if fxdb_match is not None:
            extra = fxdb_match[fxdb_match.measure.str.contains('leading', case=False)]
            netr['leading_zero_extra_matches'] = int(extra.value.sum()) if len(extra) else 0
        save(netr, 'networked_rates')
        check('type rates: tickets = networked tickets', int(net.loc[net.networked != 'not networked',
                                                                         'tickets'].sum()), int(types.tickets.sum()))
        cross = d.groupby(['model', 'machine_type']).size().rename('machines').reset_index()
        save(cross, 'model_type_crosswalk')
        types['ratio_basis'] = 'installed fleet on the list'
    else:
        basis = 'telemetry-span'
        d = htm[htm.months > 0].copy()
        d['customer'] = d.customer.fillna(d.host.fillna('(no host)'))
        d['machine_type'] = d.machine_type.astype(str).str.replace(r'^package name:\s*', '', regex=True)
        # Only tickets inside each device's active span have exposure behind them.
        d['tickets'] = d.tickets_obs - d.tickets_before_first_active.fillna(0) - d.tickets_after_last_active.fillna(0)
        d = d.rename(columns={'machine_id': 'serial'})
        clus = sorted(d.customer.unique())
        types, _ = group_rates(d, 'machine_type', boot_weights(len(clus)), clus)
        types = types.rename(columns={'accounts': 'clusters'})
        types['ratio_basis'] = 'telemetry fleet, Aug 2025 to Jul 2026 (12 months)'
        FACTS['type_span_tickets_outside_span'] = int(htm[htm.months > 0].tickets_obs.sum() - d.tickets.sum())
    types['exposure_basis'] = basis
    types['own_rate'] = types.months >= MIN_TYPE_MONTHS
    save(types.sort_values(['tickets', 'machine_type'], ascending=[False, True]), 'type_rates')

    # ------------------------------------------------------------------ Customers
    print('Customers')
    c, tau2, phi = customer_table(m, 'tickets', m.E)
    c['E_model'] = m.groupby('customer').E_model.sum()
    c['E_coverage'] = m.groupby('customer').E_cov.sum()
    c['machines'] = m[m.months > 0].groupby('customer').size().reindex(c.index).fillna(0).astype(int)
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
    c['flagged'] = c.z_d > Z998            # beyond the 99.8% funnel (extreme tier)
    c['below_998'] = c.z_d < -Z998
    c['p_poisson'] = upper_p(c.O, c.E)
    c['q_poisson'] = bh_q(c.p_poisson)
    c['q_poisson_low'] = bh_q(lower_p(c.O, c.E))
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
                                'customers_with_E': int((c.E > 0).sum()), 'flagged_998': int(c.flagged.sum()),
                                'above_95': int(c.above_95.sum()), 'below_998': int(c.below_998.sum()),
                                'poisson_q_lt_0.05_high': int(((c.q_poisson < Q_CUT) & (c.O > c.E)).sum())}

    # Sensitivities: go-live exposure, and the population with the third-party machines put back.
    ml = m.assign(months=m.months_live)
    cl, _, _ = customer_table(ml, 'tickets', ipf_expected(ml, 'tickets', ['rate_group', 'age_band']))
    FACTS['go_live_sensitivity'] = {'scope': 'go-live date for exposure only; age bands from the install date',
                                    'fleet_rate_per_100': 100 * m.tickets.sum() / m.months_live.sum(),
                                    'months': float(m.months_live.sum()), 'flagged_998': int((cl.z_d > Z998).sum()),
                                    'flagged_overlap_with_main': int(((cl.z_d > Z998) & c.flagged).sum()),
                                    'poisson_flagged': int(poisson_flags(cl.O, cl.E).sum()),
                                    'poisson_flagged_overlap': int((poisson_flags(cl.O, cl.E) &
                                                                    c.poisson_flagged.to_numpy()).sum())}
    ma = add_rate_groups(m_all.copy())
    ca, tau2a, _ = customer_table(ma, 'tickets', ipf_expected(ma, 'tickets', ['rate_group', 'age_band']))
    FACTS['with_third_party_sensitivity'] = {
        'machines': len(ma), 'months': float(ma.months.sum()), 'tickets': int(ma.tickets.sum()),
        'fleet_rate_per_100': float(100 * ma.tickets.sum() / ma.months.sum()), 'tau2': tau2a,
        'eb_alpha': eb_alpha(ca.O, ca.E), 'poisson_flagged': int(poisson_flags(ca.O, ca.E).sum())}

    # ------------------------------------------------------------------ Variants (customers and machines)
    print('Variants (12) for customers and machines')
    scope_col = {('tickets', 'all'): 'tickets', ('tickets', 'core'): 'tickets_core',
                 ('episodes', 'all'): 'episodes', ('episodes', 'core'): 'episodes_core'}
    c['variants_flagged'] = 0          # Poisson rule (BH q < 0.05 and >= 5 tickets), as for machines
    c['variants_low'] = 0              # lower-tail Poisson BH q < 0.05
    c['variants_funnel'] = 0           # beyond the 99.8% overdispersion-adjusted funnel limit
    m['variants_flagged'] = 0
    variant_rows = []
    for ename, factors in VARIANT_EXPECTED.items():
        for cnt in VARIANT_COUNTS:
            for scope in VARIANT_SCOPES:
                col = scope_col[(cnt, scope)]
                e = ipf_expected(m, col, factors)
                cv, tv, _ = customer_table(m, col, e)
                fl = pd.Series(cv.z_d > Z998, index=cv.index)
                cf = pd.Series(poisson_flags(cv.O, cv.E), index=cv.index)
                cl_ = pd.Series(poisson_flags(cv.O, cv.E, low=True), index=cv.index)
                c['variants_funnel'] += fl.reindex(c.index).fillna(False).astype(int)
                c['variants_flagged'] += cf.reindex(c.index).fillna(False).astype(int)
                c['variants_low'] += cl_.reindex(c.index).fillna(False).astype(int)
                mf = poisson_flags(m[col].to_numpy(), e)
                m['variants_flagged'] += mf.astype(int)
                variant_rows.append({'expected': ename, 'count': cnt, 'scope': scope, 'total': int(m[col].sum()),
                                     'tau2': tv, 'customers_flagged': int(cf.sum()),
                                     'customers_low': int(cl_.sum()),
                                     'customers_beyond_funnel_998': int(fl.sum()), 'machines_flagged': int(mf.sum())})
    variants = save(pd.DataFrame(variant_rows), 'outlier_variants')
    check('12 variants', 12, len(variants))

    # ------------------------------------------------------------------ Halves (customers)
    print('Halves')
    for h in ('h1', 'h2'):
        ch, th, _ = customer_table(m, f'tickets_{h}', m[f'E_{h}'])
        c[f'O_{h}'], c[f'E_{h}'], c[f'z_d_{h}'] = ch.O, ch.E, ch.z_d
        c[f'STR_{h}'] = np.where(ch.E > 0, ch.O / ch.E.where(ch.E > 0, 1), np.nan)
        c[f'p_{h}'] = upper_p(ch.O, ch.E)
        c[f'p_low_{h}'] = lower_p(ch.O, ch.E)
        c[f'q_{h}'] = bh_q(c[f'p_{h}'])
        FACTS[f'tau2_{h}'] = th
    c['consistent_outlier'] = (c.variants_flagged >= MIN_VARIANTS) & (c.p_h1 < 0.05) & (c.p_h2 < 0.05)
    c['consistent_low'] = (c.variants_low >= MIN_VARIANTS) & (c.p_low_h1 < 0.05) & (c.p_low_h2 < 0.05)

    # Persistence statistics vs two nulls, on customers with E >= 3 in each half.
    el = c[(c.E_h1 >= 3) & (c.E_h2 >= 3)].copy()

    def persist_stats(s1, s2, sig1, sig2, fl1, fl2):
        top1 = s1 >= np.quantile(s1, 0.9)
        top2 = s2 >= np.quantile(s2, 0.9)
        return (spearman(s1, s2), float((top1 & top2).sum() / top1.sum()), int((sig1 & sig2).sum()),
                float((fl1 & sig2).sum() / max(fl1.sum(), 1)), float((fl2 & sig1).sum() / max(fl2.sum(), 1)))

    s1, s2 = el.STR_h1.to_numpy(), el.STR_h2.to_numpy()
    sig1, sig2 = (el.p_h1 < 0.05).to_numpy(), (el.p_h2 < 0.05).to_numpy()
    fl1, fl2 = (el.q_h1 < Q_CUT).to_numpy(), (el.q_h2 < Q_CUT).to_numpy()
    obs_stats = persist_stats(s1, s2, sig1, sig2, fl1, fl2)
    dec = pd.qcut(el.E_h2.rank(method='first'), 10, labels=False).to_numpy()
    perm = []
    for _ in range(N_NULL):
        idx = np.arange(len(el))
        for g in range(10):
            sel = np.where(dec == g)[0]
            idx[sel] = rng.permutation(sel)
        perm.append(persist_stats(s1, s2[idx], sig1, sig2[idx], fl1, fl2[idx]))
    perm = np.array(perm)
    pois = []
    k1, k2 = critical_count(el.E_h1), critical_count(el.E_h2)
    for _ in range(N_NULL):
        o1, o2 = rng.poisson(el.E_h1.to_numpy()), rng.poisson(el.E_h2.to_numpy())
        q1 = bh_q(upper_p(o1, el.E_h1.to_numpy())) < Q_CUT
        q2 = bh_q(upper_p(o2, el.E_h2.to_numpy())) < Q_CUT
        pois.append(persist_stats(o1 / el.E_h1.to_numpy(), o2 / el.E_h2.to_numpy(), o1 >= k1, o2 >= k2, q1, q2))
    pois = np.array(pois)
    names = ['spearman_STR_h1_h2', 'top_decile_retained_share', 'significant_in_both_halves',
             'flagged_h1_significant_h2_share', 'flagged_h2_significant_h1_share']
    notes = ['', 'top 10% by STR in H1 also top 10% in H2', 'p < 0.05 in each half',
             f'{int(fl1.sum())} customers flagged (q < 0.05) in H1', f'{int(fl2.sum())} customers flagged in H2']
    prow = [null_row('customer', n, len(el), obs_stats[i], perm[:, i], pois[:, i], notes[i])
            for i, n in enumerate(names)]

    # ------------------------------------------------------------------ Machines: flags, halves, persistence
    print('Machines')
    m['p_poisson'] = upper_p(m.tickets, m.E)
    m['q_poisson'] = bh_q(m.p_poisson)
    m['flagged'] = (m.tickets >= MIN_FLAG_TICKETS) & (m.q_poisson < Q_CUT)
    for h in ('h1', 'h2'):
        m[f'p_{h}'] = upper_p(m[f'tickets_{h}'], m[f'E_{h}'])
        m[f'q_{h}'] = bh_q(m[f'p_{h}'])
    m['consistent_outlier'] = (m.variants_flagged >= MIN_VARIANTS) & (m.p_h1 < 0.05) & (m.p_h2 < 0.05)
    pos_m = m.E > 0
    alpha_m = {g: eb_alpha(s.tickets, s.E) for g, s in m[pos_m].groupby('rate_group')}
    m['alpha_nb'] = m.rate_group.map(alpha_m).fillna(0.0)
    m['p_nb'] = np.nan
    m.loc[pos_m, 'p_nb'] = [H.nb_sf(o, e, a) for o, e, a in zip(m.tickets[pos_m], m.E[pos_m], m.alpha_nb[pos_m])]
    m['q_nb'] = bh_q(m.p_nb)
    inv = 1 / m.alpha_nb.where(m.alpha_nb > 0)
    m['STR_eb'] = np.where(pos_m, np.where(m.alpha_nb > 0, (m.tickets + inv) / (m.E + inv), m.tickets / m.E), np.nan)

    # Second-half O/E by first-half tickets (machines with exposure in both halves).
    both = m[(m.months_h1 > 0) & (m.months_h2 > 0)].copy()
    groups = ['0', '1', '2', '3', '4+']
    gi = np.minimum(both.tickets_h1.to_numpy(), 4)
    acc_b = sorted(both.customer.unique())
    both['h1_group'] = gi
    _, (O2, E2) = _cluster_sums(both, 'h1_group', ['tickets_h2', 'E_h2'], acc_b)
    with np.errstate(invalid='ignore', divide='ignore'):
        rb = (boot_weights(len(acc_b)) @ O2.T) / (boot_weights(len(acc_b)) @ E2.T)
    blo, bhi = pct_ci(rb)
    o2, e2 = both.tickets_h2.to_numpy(float), both.E_h2.to_numpy(float)

    def group_ratios(hp):
        g = np.minimum(hp, 4)
        return [o2[g == i].sum() / e2[g == i].sum() if e2[g == i].sum() > 0 else np.nan for i in range(5)] + \
            [o2[hp >= 3].sum() / e2[hp >= 3].sum()]

    def permuted(cells):
        h1 = both.tickets_h1.to_numpy()
        hp = h1.copy()
        for sel in cells:
            hp[sel] = h1[rng.permutation(sel)]
        return group_ratios(hp)

    cell = (both.rate_group.astype(str) + '|' + both.age_band.astype(str)).to_numpy()
    cells = [np.where(cell == v)[0] for v in sorted(set(cell))]
    custs = both.customer.to_numpy()
    ccells = [np.where(custs == v)[0] for v in sorted(set(custs))]
    null_cell = np.array([permuted(cells) for _ in range(N_NULL)])
    null_cust = np.array([permuted(ccells) for _ in range(N_NULL)])
    obs = group_ratios(both.tickets_h1.to_numpy())
    mp = pd.DataFrame({'first_half_tickets': groups,
                       'machines': [int((gi == i).sum()) for i in range(5)],
                       'second_half_tickets': O2.sum(1), 'second_half_expected': E2.sum(1),
                       'second_half_ratio': obs[:5], 'boot_lo': blo, 'boot_hi': bhi,
                       'cell_null_median': np.nanmedian(null_cell[:, :5], 0),
                       'cell_null_p2_5': np.nanpercentile(null_cell[:, :5], 2.5, 0),
                       'cell_null_p97_5': np.nanpercentile(null_cell[:, :5], 97.5, 0),
                       'customer_null_median': np.nanmedian(null_cust[:, :5], 0),
                       'customer_null_p2_5': np.nanpercentile(null_cust[:, :5], 2.5, 0),
                       'customer_null_p97_5': np.nanpercentile(null_cust[:, :5], 97.5, 0)})
    save(mp, 'outlier_machine_persistence')
    hi3 = int((both.tickets_h1 >= 3).sum())
    prow.append(null_row('machine', 'second_half_ratio_if_3plus_first_half', hi3, obs[5], null_cell[:, 5],
                         note='null: first-half counts permuted within model-group x age-band cells; Poisson '
                              'null is 1 by construction'))
    prow.append(null_row('machine', 'second_half_ratio_if_3plus_first_half_within_customer', hi3, obs[5],
                         null_cust[:, 5], note='null: first-half counts permuted among machines of the same '
                                               'customer (site-level persistence)'))
    f1 = both.q_h1 < Q_CUT
    prow.append({'level': 'machine', 'statistic': 'h1_flagged_second_half_ratio', 'units': int(f1.sum()),
                 'observed': float(both.tickets_h2[f1].sum() / both.E_h2[f1].sum()) if f1.any() else np.nan,
                 'perm_null_median': np.nan, 'perm_null_p2_5': np.nan, 'perm_null_p97_5': np.nan,
                 'perm_p_value': np.nan, 'poisson_null_median': np.nan, 'poisson_null_p97_5': np.nan,
                 'note': f'machines flagged (q < 0.05) on H1 alone; their H1 ratio was '
                         f'{both.tickets_h1[f1].sum() / both.E_h1[f1].sum():.2f}'})
    persistence = save(pd.DataFrame(prow), 'outlier_persistence')

    # Overlap with the 113 machines flagged in docs/05 (telemetry-span exposure).
    chronic = htm[htm['class'] == 'chronic_outlier']
    m['in_docs05_113'] = m.serial_id.isin(set(chronic.serial_id))
    m['docs05_span_months'] = m.serial_id.map(chronic.set_index('serial_id').months)
    short = chronic[chronic.months < 12].serial_id   # docs/05: "22 of the 113 have under 12 months"
    sm = m[m.serial_id.isin(set(short))]
    FACTS['docs05_overlap'] = {
        'docs05_flagged': int(len(chronic)), 'in_population': int(m.in_docs05_113.sum()),
        'on_list_third_party': int(third.serial_id.isin(set(chronic.serial_id)).sum()),
        'flagged_now': int((m.in_docs05_113 & m.flagged).sum()),
        'consistent_now': int((m.in_docs05_113 & m.consistent_outlier).sum()),
        'short_span_definition': 'telemetry span < 12 months',
        'short_span_flagged': int(len(short)), 'short_span_in_population': int(len(sm)),
        'short_span_installed_during_period': int((sm.install_date >= PERIOD_START).sum()),
        'short_span_installed_before_period': int((sm.install_date < PERIOD_START).sum()),
        'short_span_flagged_now': int(sm.flagged.sum())}

    # ------------------------------------------------------------------ Drivers of outlier customers
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
        n_exposed = int((mm.months > 0).sum())
        drv.append({'customer': cust, 'consistent_outlier': bool(c.loc[cust, 'consistent_outlier']),
                    'beyond_funnel_998': bool(c.loc[cust, 'flagged']), 'machines': n_exposed,
                    'tickets': int(mm.tickets.sum()), 'expected': float(mm.E.sum()), 'excess': exc,
                    'STR': float(c.loc[cust, 'STR']), 'STR_eb': float(c.loc[cust, 'STR_eb']),
                    'z_d': float(c.loc[cust, 'z_d']),
                    'top2_machines_excess': float(top2.excess.sum()),
                    'top2_share_of_excess': float(top2.excess.sum() / exc) if exc > 0 else np.nan,
                    'machines_above_expected_share': float((mm[mm.months > 0].tickets > mm[mm.months > 0].E).mean()),
                    'flagged_machines': int(mm.flagged.sum()),
                    'top_category': cc.index[0] if len(cc) else None,   # ties: alphabetically first
                    'top_category_ties': int((cc == cc.iloc[0]).sum()) if len(cc) else 0,
                    'top_category_share': float(cc.iloc[0] / cc.sum()) if len(cc) else np.nan,
                    'top_model': c.loc[cust, 'top_model'],
                    'months_share_service_contract': c.loc[cust].get('months_share_service_contract', np.nan)})
    drivers = pd.DataFrame(drv)
    if len(drivers):
        drivers['pattern'] = np.select(
            [drivers.machines < 10, drivers.top2_share_of_excess >= 0.5],
            ['small fleet (<10 machines)', 'a few machines'], 'spread across fleet')
    save(drivers, 'outlier_drivers')

    # ------------------------------------------------------------------ Lorenz (customers)
    print('Concentration across customers')
    grid = np.linspace(0, 1, 101)
    cc_ = c[c.months > 0]
    sims = rng.poisson(cc_.E.to_numpy(), size=(N_NULL, len(cc_)))
    sim_l = np.array([H.lorenz_top(s, grid) for s in sims])
    lor = pd.DataFrame({'customer_share': grid, 'ticket_share_obs': H.lorenz_top(cc_.O.to_numpy(), grid),
                        'expected_share': H.lorenz_top(cc_.E.to_numpy(), grid),
                        'ticket_share_null_median': np.median(sim_l, 0),
                        'ticket_share_null_p2_5': np.percentile(sim_l, 2.5, 0),
                        'ticket_share_null_p97_5': np.percentile(sim_l, 97.5, 0)})
    save(lor, 'customer_lorenz')
    check('customer lorenz ends at 1', 1.0, round(float(lor.ticket_share_obs.iloc[-1]), 9))

    # ------------------------------------------------------------------ Save customer and machine tables
    cust = c.reset_index().rename(columns={'O': 'tickets', 'E': 'expected', 'E_model': 'expected_model_only',
                                           'E_coverage': 'expected_with_coverage', 'flagged': 'beyond_funnel_998'})
    cust = cust.sort_values(['tickets', 'customer'], ascending=[False, True])
    save(cust, 'customer_rates')
    keep = ['serial_id', 'customer', 'model', 'family', 'rate_group', 'service_status', 'age_band', 'months',
            'months_h1', 'months_h2', 'tickets', 'tickets_h1', 'tickets_h2', 'tickets_core', 'episodes', 'E',
            'E_model', 'E_cov', 'E_h1', 'E_h2', 'STR_eb', 'p_poisson', 'q_poisson', 'q_nb', 'flagged', 'p_h1',
            'p_h2', 'variants_flagged', 'consistent_outlier', 'in_docs05_113', 'docs05_span_months',
            'ticket_before_install']
    mach = m[keep].assign(install_year=m.install_date.dt.year).rename(
        columns={'E': 'expected', 'E_model': 'expected_model_only', 'E_cov': 'expected_with_coverage',
                 'E_h1': 'expected_h1', 'E_h2': 'expected_h2'})
    mach = mach[(mach.tickets > 0) | mach.in_docs05_113].sort_values(['tickets', 'serial_id'],
                                                                      ascending=[False, True])
    save(mach, 'machine_flags')
    oc = cust[['customer', 'machines', 'tickets', 'expected', 'STR', 'STR_eb', 'z_d', 'beyond_funnel_998',
               'poisson_flagged', 'variants_flagged', 'variants_low', 'variants_funnel', 'O_h1', 'E_h1', 'STR_h1',
               'p_h1', 'q_h1', 'z_d_h1', 'O_h2', 'E_h2', 'STR_h2', 'p_h2', 'q_h2', 'z_d_h2', 'consistent_outlier',
               'consistent_low', 'months_share_no_coverage', 'months_share_not_serviceable']]
    save(oc[(oc.expected >= 1) | oc.beyond_funnel_998 | oc.consistent_low], 'outlier_customers')

    # ------------------------------------------------------------------ Private real names
    names = eq.assign(customer=eq.account.map(maps['account'])).drop_duplicates('customer')[['customer', 'account']]
    wanted = set(cust.head(15).customer) | set(cust[cust.beyond_funnel_998 | cust.consistent_outlier
                                                    | cust.poisson_flagged].customer)
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
                        'min_clusters': MIN_CLUSTERS, 'age_bands': AGE_LABELS,
                        'episode_gap_days': EPISODE_GAP_DAYS, 'min_flag_tickets': MIN_FLAG_TICKETS, 'q_cut': Q_CUT,
                        'z95': Z95, 'z998': Z998, 'min_variants': MIN_VARIANTS, 'n_variants': len(variants),
                        'pool_label': POOL, 'third_party_plans': list(THIRD_PARTY_PLANS),
                        'equipment_list_date': '2026-10-19'},
        'fleet': {'machines': len(m), 'machines_exposed': int((m.months > 0).sum()),
                  'accounts': int(m.customer.nunique()), 'months': float(m.months.sum()),
                  'tickets': int(m.tickets.sum()), 'rate_per_100': float(fleet_rate),
                  'machines_with_ticket': int((m.tickets > 0).sum()),
                  'machines_zero_months': int((m.months == 0).sum()),
                  'tickets_h1': int(m.tickets_h1.sum()), 'tickets_h2': int(m.tickets_h2.sum()),
                  'rate_h1': float(100 * m.tickets_h1.sum() / m.months_h1.sum()),
                  'rate_h2': float(100 * m.tickets_h2.sum() / m.months_h2.sum())},
        'third_party': {'machines': len(third), 'accounts': int(third.customer.nunique()),
                        'months': float(third.months.sum()), 'tickets': int(third.tickets.sum())},
        'match': dict(zip(match_t.measure, map(int, match_t.value))),
        'customers': FACTS['customer_funnel'] | {
            'poisson_flagged': int(c.poisson_flagged.sum()),
            'flagged_in_10plus_variants': int((c.variants_flagged >= MIN_VARIANTS).sum()),
            'consistent_outliers': int(c.consistent_outlier.sum()),
            'consistent_outliers_beyond_funnel_998': int((c.consistent_outlier & c.flagged).sum()),
            'consistent_outliers_inside_funnel_95': int((c.consistent_outlier & (c.z_d < Z95)).sum()),
            'consistent_low': int(c.consistent_low.sum()),
            'consistent_low_mostly_uncovered': int((c.consistent_low & ((c.get('months_share_no_coverage', 0)
                                                    + c.get('months_share_not_serviceable', 0)) >= 0.5)).sum())},
        'machines': {'flagged': int(m.flagged.sum()),
                     'flagged_nb': int(((m.q_nb < Q_CUT) & (m.tickets >= MIN_FLAG_TICKETS)).sum()),
                     'flagged_in_10plus_variants': int((m.variants_flagged >= MIN_VARIANTS).sum()),
                     'consistent_outliers': int(m.consistent_outlier.sum())},
        'models': {'consistently_above': sorted(mo.rate_group[mo.consistent == 'consistently above']),
                   'consistently_below': sorted(mo.rate_group[mo.consistent == 'consistently below'])},
        'unlisted': {'tickets': len(unl), 'tickets_h1': int((unl.ts < SPLIT).sum()),
                     'tickets_h2': int((unl.ts >= SPLIT).sum())},
        'persistence': {k: {kk: (r(v) if isinstance(v, float) else v) for kk, v in row.items()}
                        for k, row in pm.to_dict('index').items()},
        'docs05_overlap': FACTS['docs05_overlap'], 'go_live_sensitivity': FACTS['go_live_sensitivity'],
        'with_third_party_sensitivity': FACTS['with_third_party_sensitivity'],
        'type_exposure_basis': basis, 'type_span_tickets_outside_span': FACTS.get('type_span_tickets_outside_span'),
        'tau2_h1': FACTS['tau2_h1'], 'tau2_h2': FACTS['tau2_h2']}
    text = json.dumps(summ, indent=2, default=lambda o: r(o, 6))
    (OUT / f'{PREFIX}summary.json').write_text(text)
    print(f'  wrote verification/outputs/fleet/{PREFIX}summary.json')

    # ------------------------------------------------------------------ Privacy and label checks
    PUBLIC['summary.json'] = pd.DataFrame({'string': json_strings(json.loads(text))})
    n_leaks = 0
    for name, df in PUBLIC.items():
        for col, n in text_leaks(df, real).items():
            n_leaks += n
            print(f'    LEAK in {name}.{col}: {n} values')
    check('public tables and summary: no real name, address, serial, case, zip or phone', 0, n_leaks)
    labels = pd.concat([cust.customer, mach.customer, mach.serial_id, drivers.get('customer', pd.Series(dtype=str))])
    check('customer and serial labels are pseudonyms', True,
          bool(labels.str.fullmatch(r'Customer \d{3,4}|S\d{5}').all()))

    fails = [c_ for c_ in H.CHECKS if c_['status'] != 'PASS']
    print(f'\n{len(H.CHECKS) - len(fails)}/{len(H.CHECKS)} checks pass')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
