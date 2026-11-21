"""Verbatim copies from verification/fleet_exposure.py. Do not edit by hand: regenerate with
trends/tests/sync_definitions.py --write (MIT side) and check with trends/tests/test_parity.py.
"""
import re

import numpy as np
import pandas as pd

from . import htm_copy as H


SEED = H.SEED

N_BOOT = 2000

MIN_TYPE_MONTHS = H.MIN_TYPE_MONTHS

MIN_CLUSTERS = 10

Q_CUT = H.Q_CUT

MONTH_DAYS = 365.25 / 12

AGE_EDGES = [-np.inf, 1, 2, 4, 6, 8, 10, np.inf]

AGE_LABELS = ['<1', '1-2', '2-4', '4-6', '6-8', '8-10', '10+']

POOL = 'Other models (<100 months each)'

THIRD_PARTY_PLANS = ('Vogeltronix',)

Z95, Z998 = 1.959964, 3.090232

SAFE_DIGITS = re.compile(r'Customer \d+|Host \d+|Location \d+|\b[SMT]\d{5}\b|\b\d{4}-\d{2}(?:-\d{2})?\b')

def norm(text):
    """Lower case, punctuation to spaces, single spaces: how names are compared in the privacy scan."""
    return ' '.join(re.sub(r'[^0-9a-z]+', ' ', str(text).lower()).split())

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

def byar(k, z=Z95):
    """Byar's approximation to the exact Poisson interval for a count k (within 1% for k >= 5; upper limit for
    k = 0 is 3.7, close to the exact 3.69)."""
    k = np.asarray(k, float)
    lo = np.where(k > 0, k * (1 - 1 / (9 * np.maximum(k, 1)) - z / (3 * np.sqrt(np.maximum(k, 1)))) ** 3, 0.0)
    hi = (k + 1) * (1 - 1 / (9 * (k + 1)) + z / (3 * np.sqrt(k + 1))) ** 3
    return lo, hi

def boot_weights(n_clusters, n_boot=N_BOOT, seed=SEED):
    """Cluster bootstrap: how many times each cluster is drawn in each resample (n_boot x n_clusters)."""
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_clusters, np.full(n_clusters, 1 / n_clusters), size=n_boot).astype(float)

def pct_ci(a, axis=0):
    lo, hi = np.nanpercentile(a, [2.5, 97.5], axis=axis)
    return lo, hi

def bh_q(p):
    """BH q-values over the non-NaN p-values (NaN stays NaN)."""
    p = np.asarray(p, float)
    q = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    q[ok] = H.bh(p[ok])
    return q

def months_between(start, end):
    return ((end - start).dt.days.clip(lower=0) / MONTH_DAYS).astype(float)

def age_band(start, end, install):
    """Age band at the midpoint of [start, end); NaN when the window is empty."""
    mid = start + (end - start) / 2
    years = ((mid - install).dt.days / 365.25).clip(lower=0)
    band = pd.cut(years, AGE_EDGES, labels=AGE_LABELS, right=False)
    return pd.Categorical(band.where(end > start), categories=AGE_LABELS, ordered=True), years

def add_rate_groups(m):
    model_months = m.groupby('model').months.sum()
    m['rate_group'] = np.where(m.model.map(model_months) >= MIN_TYPE_MONTHS, m.model, POOL)
    return m

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
