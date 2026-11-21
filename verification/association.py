#!/usr/bin/env python3
"""Association between service-ticket fields and the telemetry codes just before each ticket (TODOS items 2-6).

Implements docs/07_association_protocol.md: frozen 22 Oct 2026, crosswalk v0 (sha256 947b96ce...), with the
pre-run amendment in its §14. docs/07 is the specification; the definitions below only point to it.

  A1  unplanned: service_group not Planned work / Cancelled request / Duplicate case.
  A2  paired set: unplanned, both windows complete (not lookback-truncated, not after telemetry end), clean control.
  A3  primary population: A2 minus tickets with another ticket on the machine in [A-5 d, A), minus tickets whose
      window lies outside the machine's telemetry span (never transacting; last_active before the window's first day).
  A5  machine type: lower case, strip 'package name:', blank -> Unknown.  A6  calendar quarter of opened_at_eastern.
  A7  target set: a Category's target_codes in the crosswalk; mapped = non-empty.
  A8  present within k: listed with hours < k. A window is undetermined at k when distinct_codes > 10 and its 10th
      listed hours < k. Pairs with an undetermined window at 7 d leave every analysis at k <= 7 d; 30 d (720 h) is
      membership of the last-10 list.
  A9  b: present in the ticket window only; c: in the control only; matched OR b/c.
  A10 able to emit: set s appears in the clean, non-truncated control windows of >= 5 OTHER machines of the type
      (per machine and set, §14.1). Unknown never emits.
  A11 clusters: assigned_customer, else ticket_customer, else the machine (account); machine clusters for item 2.
  A12 a reported row needs >= 30 pairs and >= 10 discordant pairs.   A13 ratios with zero counts; inverted_cdf.

Primary: H2a (does a Category pick out its own codes, against tickets for other faults), log Mantel-Haenszel ratio
over type x quarter strata, account-cluster bootstrap and a within-stratum permutation of Category. Then H1, then
per-set enrichment (gated); H2b and item 2-6 tables; sensitivities S1-S13.

Inputs (committed, pseudonymous; read as strings): verification/outputs/fu/fu_ticket_last10.csv, fu/fu_devices.csv,
db/db_codes_buckets.csv, verification/reference/crosswalk_v0.csv; for S5 only htm_device_exposure.csv and
fleet/fx_machine_flags.csv; for S2/S10 only the optional local export outputs/flags/flags_by_case.csv.
Outputs: verification/outputs/assoc/as_*.csv and as_summary.json (pseudonyms, labels and aggregates only).

Run:  cd /home/user/analytics-lab && python3 -I verification/association.py [--blind] [--out DIR]
--blind writes the tables to --out but prints only check statuses, population counts and a SHA-256 per table (used
while the clean-room builds were compared, so that no result was seen before they agreed).
Cross-check (docs/07 §8, §14.10-16): two independent clean-room builds, written from docs/07 and the committed
inputs without reading this script, matched every one of the 33,515 compared cells exactly. The cells covered the
pairs, the item 2 tables with their intervals and q-values, the breakdowns, H2a with intervals and permutation p, H1
and the item 3 curves. They were compared while this script's outcomes were still hidden (--blind).
Deterministic: fixed seed, stable sorts. Exit status 1 if any check fails.
"""
import argparse
import copy
import csv
import hashlib
import io
import json
import math
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common  # noqa: E402
from common import OUTPUTS  # noqa: E402
from fleet_exposure import bh_q, boot_weights  # noqa: E402

SEED = 15072
N_BOOT = 2000
N_PERM = 2000
K_GRID = (0.5, 1.0, 2.0, 6.0, 24.0, 168.0, 720.0)
K7, K30 = 168.0, 720.0
GUARDS = {'corrected_guard30': 0.5, 'corrected_guard60': 1.0}
UNPLANNED_EXCLUDED = ('Planned work', 'Cancelled request', 'Duplicate case')
HIST0 = pd.Timestamp('2025-08-01 04:00')  # case history starts 1 Aug 2025 00:00 US Eastern
TELEMETRY_FIRST = pd.Timestamp('2025-08-01')
FROZEN_HASH = '947b96ce805ba8b8593aa43c728fad97afc382e4386ae06cca36ce5139f05d79'
MIN_PAIRS, MIN_DISC, MIN_EMIT, MIN_T_DISC = 30, 10, 5, 10
BUCKET_FAMILY = ('Stock-out', 'Door issue', 'Incomplete transaction', 'User behavior', 'Operational status',
                 'Mechanical fault', 'Electronics/software/comms', 'Undefined')
NON_TEAM_TARGETS = ('No identifiable issue', 'Not in telemetry', 'Administrative')
BINS = ((0, 2), (2, 6), (6, 24), (24, 168), (168, 720.01))
BIN_LABELS = ('[0,2) h', '[2,6) h', '[6,24) h', '[24,168) h', '[168,720] h')
STOCKOUT = ('03', '77')
S13_SET = '20|79|80'

FU = OUTPUTS / 'fu'
DB = OUTPUTS / 'db'
XWALK = HERE / 'reference' / 'crosswalk_v0.csv'
FLAGS = OUTPUTS / 'flags' / 'flags_by_case.csv'
PREFIX = 'as_'

# Counts stated in docs/07 §2-§6 (pinned, §8).
PINS = {
    'A2 paired tickets': 3259, 'A2 paired machines': 2504, 'A3 other ticket in [A-5d, A)': 157,
    'A3 never transacting': 102, 'A3 never transacting machines': 85, 'A3 last_active before window': 50,
    'A3 last_active before window machines': 47, 'A3 primary tickets': 2950, 'A3 primary machines': 2376,
    'A3 kept, silent before ticket day': 42, 'A3 kept, silent before A-7d': 31, 'A3 lead-in ticket [A-102,A-67)': 292,
    'A3 lead-in within 9 d': 56, 'A3 before 11 Nov 2025': 341, 'A3 A-67d before case history': 17,
    'A3 no Category': 39, 'A3 Trouble Code but no Category': 12, 'A5 named types': 23, 'A5 Unknown tickets': 14,
    'A6 2025Q4': 731, 'A6 2026Q1': 870, 'A6 2026Q2': 812, 'A6 2026Q3': 537, 'A7 mapped primary': 1736,
    'A8 undetermined ticket windows 7d': 29, 'A8 undetermined control windows 7d': 17, 'A8 pairs left out 7d': 39,
    'A8 determined pairs 7d': 2911, 'A8 clusters 7d': 610, 'A8 machines 7d': 2350, 'A8 mapped 7d': 1706,
    'A8 ticket windows > 10 distinct': 137, 'A8 control windows > 10 distinct': 94, 'A10 windows': 3388,
    'A11 clusters': 613, 'A11 by assigned_customer': 2902, 'A11 by ticket_customer': 48,
    'xw high': 26, 'xw medium': 9, 'xw low': 6, 'xw mapped Categories': 10, 'xw mapped matched tickets': 3298,
    'H1 population 7d': 1439, 'H1 population 30d': 1469, 'H2b K (Not in telemetry, primary)': 281,
    'frequent codes': 35, 'frequent windows': 5900, 'S1 added pairs': 99, 'S4 tickets': 2330, 'S5 dropped': 177,
    'S5 dropped machines': 175, 'S5b install year >= 2025': 521, 'S5b no install year': 132, 'S9 tickets': 5031,
}
T_ON_EMITTING = {'19|20|78|79|80': 563, '02|11|27|41|42|43|44|45|46|47|48': 220, '14|17|18|32|33|34|35': 213,
                 '13|25': 208, '30|31': 139, '76': 88, '77': 23, '04|19|60|61|78': 9, '16': 6, '66|67': 0}
NO_SET_CODES = ['01', '03', '05', '15', '26', '28', '56', '57', '58', '59', '81']
FREQUENT = ['01', '03', '04', '11', '13', '15', '16', '17', '18', '19', '20', '25', '26', '28', '30', '31', '32', '33',
            '34', '35', '41', '42', '43', '44', '45', '46', '47', '48', '66', '76', '77', '78', '79', '80', '81']
EMIT_TYPES = {  # types with >= 5 machines showing the set in clean control windows (A10)
    '19|20|78|79|80': ['scrubex-1', 'scrubex-3', 'scrubex-4', 'scrubex-5', 'scrubex-7', 'scrubex2.0-3', 'scrubex2.0-4',
                       'scrubex2.0-5'],
    '14|17|18|32|33|34|35': ['scrubex-1', 'scrubex-2', 'scrubex-4', 'scrubex-5', 'scrubex2.0-2', 'scrubex2.0-4',
                             'scrubex2.0-5', 'sd-49'],
    '30|31': ['scrubex-1', 'scrubex-2', 'scrubex-4', 'scrubex-5', 'scrubex2.0-2', 'scrubex2.0-4', 'scrubex2.0-5',
              'sd-49'],
    '02|11|27|41|42|43|44|45|46|47|48': ['alex2.0-1', 'alex2.0-3', 'mlc-1', 'sbsx-51', 'scrubex-1', 'scrubex-2',
                                         'scrubex-4', 'scrubex-5', 'scrubex2.0-2', 'scrubex2.0-4', 'scrubex2.0-5',
                                         'sd-49'],
    '76': ['scrubex-3', 'scrubex-4', 'scrubex-7', 'scrubex2.0-3', 'scrubex2.0-4', 'scrubex2.0-5'],
    '66|67': ['sbsx-49', 'sbsx-51'],
    '13|25': ['scrubex-1', 'scrubex-2', 'scrubex-4', 'scrubex2.0-2', 'scrubex2.0-3', 'scrubex2.0-4', 'scrubex2.0-5',
              'sd-49'],
    '16': ['alex2.0-1', 'alex2.0-3', 'mlc-1'],
    '77': ['scrubex-1', 'scrubex-2', 'scrubex-4', 'scrubex-5', 'scrubex2.0-2', 'scrubex2.0-4', 'scrubex2.0-5'],
    '04|19|60|61|78': ['sbsx-49', 'sbsx-51', 'scrubex-1', 'scrubex-3', 'scrubex-4', 'scrubex-5', 'scrubex-7',
                       'scrubex2.0-3', 'scrubex2.0-4', 'scrubex2.0-5'],
}

# Headline results, pinned exactly after the clean-room builds agreed and the outputs were unblinded (22 Oct 2026).
RESULT_PINS = {
    ('h2a', 168.0): (1.1683283379184424, 0.8514412699068736, 1.5633884185110032, 0.0004997501249375),
    ('h2a', 720.0): (0.6425975750192976, 0.3259633549478429, 1.012459758156402, 0.000999500249875),
    ('h1', 168.0): (6.479166666666667, 4.951612903225806, 8.868421052631579, 311, 48),
    ('h1', 720.0): (4.1, 3.064516129032258, 5.785714285714286, 205, 50),
}

CHECKS = []
PUBLIC = {}
BLIND = False
OUT = OUTPUTS / 'assoc'


# ----------------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------------
def check(name, expected, actual, tol=0.0):
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float, np.integer, np.floating)):
        ok = abs(float(actual) - float(expected)) <= tol
    else:
        ok = expected == actual
    CHECKS.append({'check': name, 'expected': None if BLIND else expected, 'actual': None if BLIND else actual,
                   'status': 'PASS' if ok else 'FAIL'})
    if BLIND:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    else:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: expected {expected}, got {actual}")
    return ok


def save(df, name):
    path = OUT / f'{PREFIX}{name}.csv'
    df.to_csv(path, index=False)
    PUBLIC[name] = df
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    print(f'  wrote {path.name} ({len(df):,} rows; sha256 {digest})')
    return df


def read(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def ratio(num, den):
    """num/den for non-negative counts (A13): den 0 and num > 0 -> +inf; 0/0 -> NaN (undefined)."""
    num = np.asarray(num, float)
    den = np.asarray(den, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(den > 0, num / np.where(den > 0, den, 1), np.where(num > 0, np.inf, np.nan))


def safe_log(x):
    x = np.asarray(x, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(np.isnan(x), np.nan, np.where(x > 0, np.log(np.where(x > 0, x, 1)),
                                                      np.where(x == 0, -np.inf, np.nan)))


def ci(reps):
    """95% percentile interval (A13): NaN replicates (undefined) are left out and counted; +-inf may be endpoints."""
    reps = np.asarray(reps, float)
    undefined = int(np.isnan(reps).sum())
    if undefined == len(reps):
        return np.nan, np.nan, undefined
    lo, hi = np.nanpercentile(reps, [2.5, 97.5], method='inverted_cdf')
    return float(lo), float(hi), undefined


def durkalski(b, c, cl_idx, n_cl):
    """Clustered McNemar (Durkalski): chi2 = (sum_k d_k)^2 / sum_k d_k^2, d_k = b_k - c_k; p two-sided; 0/0 -> p = 1.
    b, c: (n,) or (n, m) 0/1 arrays; returns p (scalar or (m,))."""
    d = np.asarray(b, float) - np.asarray(c, float)
    one = d.ndim == 1
    d = d.reshape(len(d), -1)
    D = np.zeros((n_cl, d.shape[1]))
    np.add.at(D, cl_idx, d)
    den = (D ** 2).sum(0)
    num = D.sum(0) ** 2
    with np.errstate(divide='ignore', invalid='ignore'):
        chi2 = np.where(den > 0, num / np.where(den > 0, den, 1), 0.0)
    p = np.array([math.erfc(math.sqrt(x / 2)) for x in chi2])
    return float(p[0]) if one else p


class Boot:
    """Cluster bootstrap over the sorted cluster labels of an analysed population (docs/07 §4 'Interval')."""
    _W = {}

    def __init__(self, labels):
        labels = np.asarray(labels, dtype=object)
        self.clusters = np.array(sorted(set(labels)), dtype=object)
        self.idx = np.searchsorted(self.clusters, labels)
        assert (self.clusters[self.idx] == labels).all()
        n = len(self.clusters)
        if n not in Boot._W:
            Boot._W[n] = boot_weights(n, N_BOOT, SEED)
        self.W = Boot._W[n]
        assert self.W.shape == (N_BOOT, n)

    def sums(self, X):
        X = np.asarray(X, float).reshape(len(self.idx), -1)
        S = np.zeros((len(self.clusters), X.shape[1]))
        np.add.at(S, self.idx, X)
        return S

    def rep(self, X, ones=False):
        S = self.sums(X)
        return S.sum(0, keepdims=True) if ones else self.W @ S


def fmt(x, nd=6):
    if x is None:
        return None
    if isinstance(x, (float, np.floating)):
        if np.isnan(x):
            return 'undefined'
        if np.isinf(x):
            return 'unbounded' if x > 0 else '-unbounded'
        return round(float(x), nd)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    return fmt(o)


# ----------------------------------------------------------------------------------------------------------------
# inputs
# ----------------------------------------------------------------------------------------------------------------
def crosswalk_hash(path):
    rows = sorted(csv.DictReader(open(path, newline='', encoding='utf-8')), key=lambda r: r['category'])
    cols = ['trouble_code', 'category', 'target_codes', 'target_bucket']
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(cols)
    for r in rows:
        w.writerow([r[c] for c in cols])
    return hashlib.sha256(buf.getvalue().encode('utf-8')).hexdigest()


def norm_type(x):
    x = re.sub(r'^package name:\s*', '', str(x).strip().lower())
    return x if x else 'Unknown'


class Window:
    """Dense view of one window type: hours H and occurrences O (tickets x codes; inf / 0 where not listed)."""

    def __init__(self, d, cidx):
        n, C = len(d), len(cidx)
        self.H = np.full((n, C), np.inf)
        self.O = np.zeros((n, C))
        self.distinct = d.distinct_codes.astype(int).to_numpy()
        self.length = np.zeros(n, int)
        self.last = np.full(n, np.inf)
        self.monotone = True
        self.bucket_ok = True
        codes, hrs, occ = (d[c].to_numpy() for c in ('last10_distinct', 'last10_distinct_hours_before',
                                                    'last10_distinct_occurrences'))
        bks = d.last10_distinct_buckets.to_numpy()
        for i in range(n):
            if not codes[i]:
                continue
            cs = codes[i].split('|')
            hs = [float(x) for x in hrs[i].split('|')]
            os_ = [float(x) for x in occ[i].split('|')]
            for c_, h_, o_ in zip(cs, hs, os_):
                self.H[i, cidx[c_]] = h_
                self.O[i, cidx[c_]] = o_
            self.length[i] = len(cs)
            self.last[i] = hs[-1]
            self.monotone &= all(a <= b for a, b in zip(hs, hs[1:]))
            self.bucket_ok &= len(bks[i].split('|')) == len(cs)

    def undetermined(self, k):
        if k >= K30:
            return np.zeros(len(self.distinct), bool)
        return (self.distinct > 10) & (self.last < k)

    def present(self, k, M):
        """(tickets x outcomes) presence within k for code masks M (codes x outcomes); k = 720 -> list membership."""
        A = (self.H < k) if k < K30 else np.isfinite(self.H)
        return (A.astype(np.float32) @ M.astype(np.float32)) > 0

    def min_hours(self, M):
        """(tickets x outcomes): smallest listed hours over the outcome's codes (inf when none listed)."""
        out = np.full((self.H.shape[0], M.shape[1]), np.inf)
        for j in range(M.shape[1]):
            cols = np.flatnonzero(M[:, j])
            if len(cols):
                out[:, j] = self.H[:, cols].min(1)
        return out


class GuardedControl:
    """S3: control window with codes whose hours < g dropped (docs/07 S3, §14.4); presence lower and upper bound."""

    def __init__(self, W, g):
        self.W, self.g = W, g

    def bounds(self, k, M):
        W, g = self.W, self.g
        if k < K30:
            pres = (((W.H >= g) & (W.H < k)).astype(np.float32) @ M.astype(np.float32)) > 0
            undet = W.undetermined(k)
        else:
            pres = (((W.H >= g) & np.isfinite(W.H)).astype(np.float32) @ M.astype(np.float32)) > 0
            dropped_any = ((W.H < g).sum(1) > 0)
            undet = (W.distinct > 10) & dropped_any
        dropped_multi = (((W.H < g) & (W.O > 1)).astype(np.float32) @ M.astype(np.float32)) > 0
        unknown = ~pres & (dropped_multi | undet[:, None])
        return pres, pres | unknown


# ----------------------------------------------------------------------------------------------------------------
# data model
# ----------------------------------------------------------------------------------------------------------------
class Data:
    def __init__(self):
        fu = read(FU / 'fu_ticket_last10.csv')
        check('fu_ticket_last10 rows', 24452, len(fu))
        self.win = {}
        for w in ('corrected_guard0', 'corrected_guard30', 'corrected_guard60', 'control_minus35d'):
            d = fu[fu.window == w].set_index('case_id').sort_index()
            check(f'{w}: one row per ticket', 6113, len(d))
            self.win[w] = d
        T0 = self.win['corrected_guard0']
        self.ids = T0.index.to_numpy()
        for w, d in self.win.items():
            assert (d.index.to_numpy() == self.ids).all()
        self.T0, self.C0 = T0, self.win['control_minus35d']

        cb = read(DB / 'db_codes_buckets.csv')
        self.bucket_of = dict(zip(cb.transaction_code, cb.bucket))
        listed = set()
        for d in self.win.values():
            for s in d.last10_distinct:
                listed.update(x for x in s.split('|') if x)
        self.codes = sorted(set(cb.transaction_code) | listed, key=lambda c: (len(c), c))
        for c in self.codes:
            self.bucket_of.setdefault(c, 'Malformed')
        self.cidx = {c: j for j, c in enumerate(self.codes)}
        self.valid_codes = [c for c in cb.transaction_code if c != '00' and self.bucket_of[c] != 'Malformed']
        self.W = {w: Window(d, self.cidx) for w, d in self.win.items()}
        for w, W in self.W.items():
            check(f'{w}: hours never decrease along each list', True, bool(W.monotone))
            check(f'{w}: list length = min(10, distinct_codes)', True,
                  bool((W.length == np.minimum(10, W.distinct)).all()))
            check(f'{w}: buckets column aligned with codes', True, bool(W.bucket_ok))
        check('control hours <= 720', True, bool(np.nanmax(np.where(np.isfinite(self.W['control_minus35d'].H),
                                                                     self.W['control_minus35d'].H, 0)) <= 720))
        for w, g in GUARDS.items():
            check(f'{w}: no code under {g} h', True, bool((self.W[w].H >= g).all()))

        dev = read(FU / 'fu_devices.csv').set_index('machine_id')
        self.dev = dev
        mid = T0.machine_id.to_numpy()
        self.mid = mid
        self.A = pd.to_datetime(T0.anchor_utc).to_numpy()
        self.type = np.array([norm_type(dev.machine_type.get(m, '')) for m in mid], dtype=object)
        self.quarter = pd.PeriodIndex(pd.to_datetime(T0.opened_at_eastern), freq='Q').astype(str).to_numpy()
        ac = np.array([dev.assigned_customer.get(m, '') for m in mid], dtype=object)
        tc = np.array([dev.ticket_customer.get(m, '') for m in mid], dtype=object)
        self.cluster_src = np.where(ac != '', 'assigned', np.where(tc != '', 'ticket_customer', 'machine'))
        self.account = np.where(ac != '', ac, np.where(tc != '', tc, mid)).astype(object)
        self.category = T0.category.to_numpy()
        self.trouble_code = T0.trouble_code.to_numpy()
        self.service_group = T0.service_group.to_numpy()
        self.model = T0.model.to_numpy()

        # crosswalk
        h = crosswalk_hash(XWALK)
        check('crosswalk sha256 = frozen hash (docs/07 §3)', FROZEN_HASH, h)
        xw = read(XWALK)
        self.xw = xw.set_index('category')
        check('crosswalk covers the 41 Categories', 41, len(xw))
        cats = set(c for c in self.category if c)
        check('every ticket Category is in the crosswalk', True, cats <= set(xw.category))
        for col, expected in (('high', 'xw high'), ('medium', 'xw medium'), ('low', 'xw low')):
            check(f'crosswalk confidence {col}', PINS[expected], int((xw.confidence == col).sum()))
        mapped_rows = xw[xw.target_codes != '']
        check('crosswalk mapped Categories', PINS['xw mapped Categories'], len(mapped_rows))
        check('crosswalk mapped matched tickets', PINS['xw mapped matched tickets'],
              int(mapped_rows.matched_tickets.astype(int).sum()))
        listed_codes = set(c for s in mapped_rows.target_codes for c in s.split('|'))
        check('every crosswalk code exists in the code table', True, listed_codes <= set(self.valid_codes))
        no_set = sorted(set(self.valid_codes) - listed_codes, key=lambda c: (len(c), c))
        check('valid codes in no target set (docs/07 §3)', NO_SET_CODES, no_set)
        self.target = np.array([self.xw.target_codes.get(c, '') if c else '' for c in self.category], dtype=object)
        self.tbucket = np.array([self.xw.target_bucket.get(c, '') if c else '' for c in self.category], dtype=object)
        self.sets = sorted(set(mapped_rows.target_codes))
        self.cat_set = {c: s for c, s in zip(xw.category, xw.target_codes)}
        self.cat_bucket = {c: b for c, b in zip(xw.category, xw.target_bucket)}

    # code masks ------------------------------------------------------------------------------------------------
    def mask(self, groups):
        """groups: list of code collections -> (codes x len(groups)) bool mask."""
        M = np.zeros((len(self.codes), len(groups)), bool)
        for j, g in enumerate(groups):
            for c in g:
                M[self.cidx[c], j] = True
        return M

    def bucket_mask(self, buckets):
        return self.mask([[c for c in self.codes if self.bucket_of[c] == b and c != '00'] for b in buckets])

    def set_mask(self, sets):
        return self.mask([s.split('|') for s in sets])


# ----------------------------------------------------------------------------------------------------------------
# populations (docs/07 §2, §6)
# ----------------------------------------------------------------------------------------------------------------
def other_ticket(D, lo_days, hi_days):
    """True when another ticket on the same machine has its anchor in [A - lo_days, A - hi_days)."""
    out = np.zeros(len(D.ids), bool)
    s = pd.Series(D.A, index=np.arange(len(D.ids)))
    for m, g in s.groupby(D.mid):
        a = np.sort(g.to_numpy())
        lo = np.searchsorted(a, g.to_numpy() - np.timedelta64(lo_days, 'D'), 'left')
        hi = np.searchsorted(a, g.to_numpy() - np.timedelta64(hi_days, 'D'), 'left')
        cnt = hi - lo
        if hi_days == 0:
            pass  # [A - lo, A) excludes the ticket itself
        out[g.index.to_numpy()] = cnt > 0
    return out


def populations(D):
    T0, C0 = D.T0, D.C0
    t = lambda s: s.to_numpy() == 'True'  # noqa: E731
    unpl = ~np.isin(D.service_group, UNPLANNED_EXCLUDED)
    okT = ~t(T0.lookback_truncated) & ~t(T0.after_telemetry_end)
    okC = ~t(C0.lookback_truncated) & ~t(C0.after_telemetry_end)
    clean = t(C0.control_clean)
    paired = unpl & okT & okC & clean
    check('A2 paired tickets', PINS['A2 paired tickets'], int(paired.sum()))
    check('A2 paired machines', PINS['A2 paired machines'], len(set(D.mid[paired])))
    p5 = other_ticket(D, 5, 0)
    dev = D.dev
    trans = np.array([dev.transacting.get(m, '') == 'True' for m in D.mid])
    la = pd.to_datetime(pd.Series([dev.last_active.get(m, '') for m in D.mid]), errors='coerce').to_numpy()
    fa = pd.to_datetime(pd.Series([dev.first_active.get(m, '') for m in D.mid]), errors='coerce').to_numpy()
    A = pd.Series(D.A)
    win_first_day = (A - pd.Timedelta(days=30)).dt.normalize().to_numpy()
    never = ~trans
    after_span = trans & ~pd.isna(la) & (la < win_first_day)
    step1 = paired & ~p5
    check('A3 other ticket in [A-5d, A)', PINS['A3 other ticket in [A-5d, A)'], int((paired & p5).sum()))
    check('A3 never transacting', PINS['A3 never transacting'], int((step1 & never).sum()))
    check('A3 never transacting machines', PINS['A3 never transacting machines'], len(set(D.mid[step1 & never])))
    check('A3 last_active before window', PINS['A3 last_active before window'], int((step1 & after_span).sum()))
    check('A3 last_active before window machines', PINS['A3 last_active before window machines'],
          len(set(D.mid[step1 & after_span])))
    primary = step1 & ~never & ~after_span
    check('A3 primary tickets', PINS['A3 primary tickets'], int(primary.sum()))
    check('A3 primary machines', PINS['A3 primary machines'], len(set(D.mid[primary])))
    day = A.dt.normalize().to_numpy()
    check('A3 kept, silent before ticket day', PINS['A3 kept, silent before ticket day'],
          int((primary & ~pd.isna(la) & (la < day)).sum()))
    check('A3 kept, silent before A-7d', PINS['A3 kept, silent before A-7d'],
          int((primary & ~pd.isna(la) & (la < (A - pd.Timedelta(days=7)).dt.normalize().to_numpy())).sum()))
    lead = other_ticket(D, 102, 67)
    near = other_ticket(D, 74, 67)
    check('A3 lead-in ticket [A-102,A-67)', PINS['A3 lead-in ticket [A-102,A-67)'], int((primary & lead).sum()))
    check('A3 lead-in within 9 d', PINS['A3 lead-in within 9 d'], int((primary & near).sum()))
    before_cut = (A - pd.Timedelta(days=102)).to_numpy() < HIST0.to_datetime64()
    check('A3 before 11 Nov 2025', PINS['A3 before 11 Nov 2025'], int((primary & before_cut).sum()))
    check('A3 A-67d before case history', PINS['A3 A-67d before case history'],
          int((primary & ((A - pd.Timedelta(days=67)).to_numpy() < HIST0.to_datetime64())).sum()))
    check('A3 no Category', PINS['A3 no Category'], int((primary & (D.category == '')).sum()))
    check('A3 Trouble Code but no Category', PINS['A3 Trouble Code but no Category'],
          int((primary & (D.category == '') & (D.trouble_code != '')).sum()))
    named = set(D.type[primary]) - {'Unknown'}
    check('A5 named types', PINS['A5 named types'], len(named))
    check('A5 Unknown tickets', PINS['A5 Unknown tickets'], int((primary & (D.type == 'Unknown')).sum()))
    for q in ('2025Q4', '2026Q1', '2026Q2', '2026Q3'):
        check(f'A6 {q}', PINS[f'A6 {q}'], int((primary & (D.quarter == q)).sum()))
    check('A11 clusters', PINS['A11 clusters'], len(set(D.account[primary])))
    check('A11 by assigned_customer', PINS['A11 by assigned_customer'],
          int((primary & (D.cluster_src == 'assigned')).sum()))
    check('A11 by ticket_customer', PINS['A11 by ticket_customer'],
          int((primary & (D.cluster_src == 'ticket_customer')).sum()))
    WT, WC = D.W['corrected_guard0'], D.W['control_minus35d']
    uT, uC = WT.undetermined(K7), WC.undetermined(K7)
    det7 = ~(uT | uC)
    check('A8 undetermined ticket windows 7d', PINS['A8 undetermined ticket windows 7d'], int((primary & uT).sum()))
    check('A8 undetermined control windows 7d', PINS['A8 undetermined control windows 7d'], int((primary & uC).sum()))
    check('A8 pairs left out 7d', PINS['A8 pairs left out 7d'], int((primary & ~det7).sum()))
    check('A8 determined pairs 7d', PINS['A8 determined pairs 7d'], int((primary & det7).sum()))
    check('A8 clusters 7d', PINS['A8 clusters 7d'], len(set(D.account[primary & det7])))
    check('A8 machines 7d', PINS['A8 machines 7d'], len(set(D.mid[primary & det7])))
    check('A8 ticket windows > 10 distinct', PINS['A8 ticket windows > 10 distinct'],
          int((primary & (WT.distinct > 10)).sum()))
    check('A8 control windows > 10 distinct', PINS['A8 control windows > 10 distinct'],
          int((primary & (WC.distinct > 10)).sum()))
    for k in K_GRID[:-1]:
        extra = primary & det7 & (WT.undetermined(k) | WC.undetermined(k))
        check(f'A8 no extra undetermined pair at k={k:g} h within the 7-d pairs', 0, int(extra.sum()))
    mapped = D.target != ''
    check('A7 mapped primary', PINS['A7 mapped primary'], int((primary & mapped).sum()))
    check('A8 mapped 7d', PINS['A8 mapped 7d'], int((primary & det7 & mapped).sum()))
    # S-variant populations
    lifted = (okT & okC & clean) & ~p5 & ~never & ~after_span
    check('S1 added pairs', PINS['S1 added pairs'], int((lifted & ~unpl).sum()))
    s4 = primary & ~before_cut & ~lead
    check('S4 tickets', PINS['S4 tickets'], int(s4.sum()))
    s5_drop = primary & ~pd.isna(fa) & (fa > TELEMETRY_FIRST.to_datetime64()) & \
        ((A - pd.Timedelta(days=65)).to_numpy() < fa + np.timedelta64(90, 'D'))
    check('S5 dropped', PINS['S5 dropped'], int(s5_drop.sum()))
    check('S5 dropped machines', PINS['S5 dropped machines'], len(set(D.mid[s5_drop])))
    ex = read(OUTPUTS / 'htm_device_exposure.csv')
    fx = read(OUTPUTS / 'fleet' / 'fx_machine_flags.csv')
    m2s = dict(zip(ex.machine_id, ex.serial_id))
    iy = dict(zip(fx.serial_id, fx.install_year))
    year = pd.to_numeric(pd.Series([iy.get(m2s.get(m, ''), '') for m in D.mid]), errors='coerce').to_numpy()
    s5b_drop = primary & (year >= 2025)
    check('S5b install year >= 2025', PINS['S5b install year >= 2025'], int(s5b_drop.sum()))
    check('S5b no install year', PINS['S5b no install year'], int((primary & np.isnan(year)).sum()))
    trunc_ok = unpl & ~t(T0.after_telemetry_end) & ~t(C0.after_telemetry_end) & clean & ~p5 & ~never & ~after_span
    usable = unpl & okT
    s9 = usable & trans & ~(~pd.isna(la) & (la < win_first_day))
    check('S9 tickets', PINS['S9 tickets'], int(s9.sum()))
    # D5 episode flag over unplanned tickets on the machine (gap > 7 d starts a new episode)
    first_ep = np.zeros(len(D.ids), bool)
    s = pd.Series(D.A, index=np.arange(len(D.ids)))[unpl]
    for m, g in s.groupby(D.mid[unpl]):
        g = g.sort_values(kind='mergesort')
        gap = g.diff().dt.total_seconds() / 86400
        first_ep[g.index.to_numpy()] = (gap.isna() | (gap > 7)).to_numpy()
    excl157 = paired & p5 & ~never & ~after_span
    return dict(unpl=unpl, okT=okT, okC=okC, clean=clean, paired=paired, p5=p5, primary=primary, det7=det7,
                mapped=mapped, lifted=lifted, s4=s4, s5=primary & ~s5_drop, s5b=primary & ~s5b_drop,
                s6=trunc_ok, s9=s9, s9_ep=s9 & first_ep, excl157=excl157, uT=uT, uC=uC)


# ----------------------------------------------------------------------------------------------------------------
# A10 emit, frequent codes
# ----------------------------------------------------------------------------------------------------------------
def emit_matrix(D, sets):
    C0 = D.C0
    t = lambda s: s.to_numpy() == 'True'  # noqa: E731
    win = t(C0.control_clean) & ~t(C0.lookback_truncated)
    check('A10 windows', PINS['A10 windows'], int(win.sum()))
    has = D.W['control_minus35d'].present(K30, D.set_mask(sets))[win]  # (windows x sets)
    mids = D.mid[win]
    types = D.type[win]
    own = pd.DataFrame(has, columns=sets).groupby(mids).any()  # machine x set
    mtype = pd.Series(types, index=mids).groupby(level=0).first()
    cnt = own.groupby(mtype.reindex(own.index).to_numpy()).sum()  # type x set: machines showing the set
    E = np.zeros((len(D.ids), len(sets)), bool)
    for j, s in enumerate(sets):
        c = np.array([cnt[s].get(tp, 0) for tp in D.type])
        o = np.array([bool(own[s].get(m, False)) for m in D.mid])
        E[:, j] = (D.type != 'Unknown') & ((c - o) >= MIN_EMIT)
    lists = {s: sorted(cnt.index[(cnt[s] >= MIN_EMIT) & (cnt.index != 'Unknown')].tolist()) for s in sets}
    return E, lists


# ----------------------------------------------------------------------------------------------------------------
# estimators
# ----------------------------------------------------------------------------------------------------------------
def enrich(XT, XC, boot, names, with_ci=True):
    """Paired enrichment rows (item 2 style) for outcome columns; boot carries the cluster index."""
    XT = np.asarray(XT, bool)
    XC = np.asarray(XC, bool)
    n = XT.shape[0]
    b = XT & ~XC
    c = ~XT & XC
    nT, nC, B, Cc = XT.sum(0), XC.sum(0), b.sum(0), c.sum(0)
    rows = pd.DataFrame({'outcome': names, 'n_pairs': n, 'n_T': nT, 'n_C': nC, 'b': B, 'c': Cc})
    rows['pT'] = nT / n if n else np.nan
    rows['pC'] = nC / n if n else np.nan
    rows['rd'] = rows.pT - rows.pC
    rows['lift'] = ratio(nT, nC)
    rows['mor'] = ratio(B, Cc)
    rows['estimable'] = (n >= MIN_PAIRS) & ((B + Cc) >= MIN_DISC)
    p = durkalski(b.astype(float), c.astype(float), boot.idx, len(boot.clusters)) if n else np.full(len(names), np.nan)
    rows['durkalski_p'] = p
    if with_ci and n:
        X = np.column_stack([np.ones(n), XT, XC, b, c]).astype(float)
        m = len(names)
        for ones in (True, False):
            R = boot.rep(X, ones=ones)
            nr, nTr, nCr, br, cr = R[:, :1], R[:, 1:1 + m], R[:, 1 + m:1 + 2 * m], R[:, 1 + 2 * m:1 + 3 * m], R[:, 1 + 3 * m:]
            with np.errstate(divide='ignore', invalid='ignore'):
                rd_r = np.where(nr > 0, (nTr - nCr) / np.where(nr > 0, nr, 1), np.nan)
            lift_r, mor_r = ratio(nTr, nCr), ratio(br, cr)
            if ones:
                ok = np.allclose(rd_r[0], rows.rd.to_numpy(), equal_nan=True) and \
                    np.array_equal(np.nan_to_num(mor_r[0], nan=-1, posinf=-2), np.nan_to_num(rows.mor.to_numpy(), nan=-1, posinf=-2))
                ONES_OK.append(bool(ok))
                continue
            for nm, Rx in (('rd', rd_r), ('lift', lift_r), ('mor', mor_r)):
                cis = [ci(Rx[:, j]) for j in range(m)]
                rows[f'{nm}_lo'] = [x[0] for x in cis]
                rows[f'{nm}_hi'] = [x[1] for x in cis]
                rows[f'{nm}_undefined_reps'] = [x[2] for x in cis]
    return rows


ONES_OK = []


class H2:
    """H2a / H2b machinery for one analysed population at one k (docs/07 §4, §14)."""

    def __init__(self, D, sel, sets, E, bS, cS, strata_keys, boot):
        self.D, self.sel, self.sets, self.E = D, sel, sets, E[sel]
        self.bS, self.cS = bS[sel].astype(float), cS[sel].astype(float)
        self.cat = D.category[sel]
        self.typ = D.type[sel]
        self.known = self.typ != 'Unknown'
        keys = sorted(set(strata_keys[sel]))
        self.hidx = np.searchsorted(np.array(keys, dtype=object), strata_keys[sel])
        self.H = len(keys)
        self.S = len(sets)
        self.boot = boot
        sidx = {s: j for j, s in enumerate(sets)}
        codes = [set(s.split('|')) for s in sets]
        self.disjoint = np.array([[not (a & b) for b in codes] for a in codes])  # [g, s]
        # Categories as integer codes (vocabulary sorted); set index and comparator flags per code
        self.vocab = sorted(set(D.category))
        self.code_of = {c: i for i, c in enumerate(self.vocab)}
        self.g_of = np.array([sidx.get(D.cat_set.get(c, ''), -1) if c else -1 for c in self.vocab])
        self.nit_of = np.array([D.cat_bucket.get(c, '') == 'Not in telemetry' for c in self.vocab])
        self.adm_of = np.array([D.cat_bucket.get(c, '') == 'Administrative' for c in self.vocab])

    def encode(self, cats):
        return np.array([self.code_of[c] for c in cats], dtype=np.int64)

    def groups(self, cc, comparator='mapped', admin=False):
        g = self.g_of[cc]
        base = self.E & self.known[:, None]
        T = (g[:, None] == np.arange(self.S)[None, :]) & base
        if comparator == 'mapped':
            mapped = g >= 0
            K = mapped[:, None] & self.disjoint[np.where(mapped, g, 0)] & base
        else:  # H2b: Not in telemetry (and Administrative under S1)
            nit = self.nit_of[cc] | (self.adm_of[cc] if admin else False)
            K = nit[:, None] & base
        return T, K

    def parts(self, T, K):
        H, S = self.H, self.S
        flat = (self.hidx[:, None] * S + np.arange(S)[None, :]).ravel()
        out = []
        for v in (self.bS * T, self.cS * T, self.bS * K, self.cS * K):
            out.append(np.bincount(flat, weights=v.ravel(), minlength=H * S).reshape(H, S))
        return out

    @staticmethod
    def mh(bT, cT, bK, cK):
        """Per-set and per-stratum MH terms -> (num_s, den_s) summed over strata (axis -2)."""
        n = bT + cT + bK + cK
        with np.errstate(divide='ignore', invalid='ignore'):
            num = np.where(n > 0, bT * cK / np.where(n > 0, n, 1), 0.0)
            den = np.where(n > 0, cT * bK / np.where(n > 0, n, 1), 0.0)
        return num.sum(-2), den.sum(-2)

    def stat(self, cats, comparator='mapped', admin=False, restrict=None):
        """Observed statistic: per-set log MH, entry flags, pooled log MH (-inf when no set enters)."""
        T, K = self.groups(cats, comparator, admin)
        bT, cT, bK, cK = self.parts(T, K)
        num, den = self.mh(bT, cT, bK, cK)
        tdisc = (bT + cT).sum(0)
        enter = (tdisc >= MIN_T_DISC) & (num > 0) & (den > 0)
        if restrict is not None:
            enter &= restrict
        per = safe_log(ratio(num, den))
        pooled = float(np.log(num[enter].sum() / den[enter].sum())) if enter.any() else -np.inf
        return dict(T=T, K=K, parts=(bT, cT, bK, cK), num=num, den=den, enter=enter, per=per, pooled=pooled,
                    tdisc=tdisc)

    def bootstrap(self, T, K, enter):
        """Per-set and pooled log MH over bootstrap replicates (entering sets fixed); plus the all-ones replicate."""
        H, S = self.H, self.S
        flat = self.hidx[:, None] * S + np.arange(S)[None, :]
        cl = self.boot.idx
        nC = len(self.boot.clusters)
        reps = {}
        for ones in (True, False):
            Q = []
            for v in (self.bS * T, self.cS * T, self.bS * K, self.cS * K):
                M = np.zeros((nC, H * S))
                np.add.at(M, (np.repeat(cl, S), flat.ravel()), v.ravel())
                R = M.sum(0, keepdims=True) if ones else self.boot.W @ M
                Q.append(R.reshape(len(R), H, S))
            num, den = self.mh(*Q)
            per = safe_log(ratio(num, den))
            pooled = safe_log(ratio(num[:, enter].sum(1), den[:, enter].sum(1))) if enter.any() else \
                np.full(len(num), np.nan)
            reps[ones] = (per, pooled)
        return reps

    def permute(self, pool, cats, perm_keys, rng, stat_fn):
        """Permute Category among `pool` within strata (sorted keys; tickets in case_id order); stat_fn(cats)->x."""
        keys = np.array(perm_keys, dtype=object)
        order = sorted(set(keys[pool]), key=lambda k: tuple(k.split('|')))  # by type, then quarter
        groups = [np.flatnonzero(pool & (keys == k)) for k in order]
        out = []
        base = cats.copy()
        for _ in range(N_PERM):
            cur = base.copy()
            for idx in groups:
                cur[idx] = rng.permutation(base[idx])
            out.append(stat_fn(cur))
        return np.array(out)


def perm_p(obs, null):
    null = np.asarray(null, float)
    p = (1 + np.sum(null >= obs)) / (len(null) + 1)
    return p, math.sqrt(p * (1 - p) / len(null))


# ----------------------------------------------------------------------------------------------------------------
# core analysis for one population (H2a pooled and per set, H1, item 2 buckets) — used by the primary and S-rows
# ----------------------------------------------------------------------------------------------------------------
class Core:
    def __init__(self, D, P, E, name, pop, presence, keep, cluster='account', admin=False, perm=True,
                 per_set_perm=False, h2b=False):
        self.D, self.name = D, name
        self.results = {}
        sets = D.sets
        MS = D.set_mask(sets)
        MB = D.bucket_mask(BUCKET_FAMILY)
        strata = np.array([f'{a}|{b}' for a, b in zip(D.type, D.quarter)], dtype=object)
        for k in (K7, K30):
            sel = pop & keep(k)
            XT_s, XC_s = presence(k, MS)
            bS, cS = XT_s & ~XC_s, ~XT_s & XC_s
            labels = (D.account if cluster == 'account' else D.mid)[sel]
            boot = Boot(labels)
            h2 = H2(D, sel, sets, E, bS, cS, strata, boot)
            cats = h2.encode(D.category[sel])
            obs = h2.stat(cats)
            row = dict(variant=name, k=k, n_pairs=int(sel.sum()), n_clusters=len(boot.clusters))
            reps = h2.bootstrap(obs['T'], obs['K'], obs['enter'])
            row['h2a_sets_entering'] = '; '.join(s for s, e in zip(sets, obs['enter']) if e)
            row['h2a'] = obs['pooled']
            lo, hi, und = ci(reps[False][1])
            row.update(h2a_lo=lo, h2a_hi=hi, h2a_undefined_reps=und)
            ONES_OK.append(bool(np.isclose(reps[True][1][0], obs['pooled']) or
                                (np.isinf(obs['pooled']) and np.isnan(reps[True][1][0]))))
            if perm:
                pool = D.mapped_flag[sel]
                rng = np.random.default_rng(SEED)
                pk = strata[sel]
                null = h2.permute(pool, cats, pk, rng, lambda cc: h2.stat(cc)['pooled'])
                check(f'{name} k={k:g}: unpermuted labels reproduce the observed H2a', True,
                      bool(h2.stat(cats.copy())['pooled'] == obs['pooled']))
                p, se = perm_p(obs['pooled'], null)
                row.update(h2a_perm_p=p, h2a_perm_mcse=se)
            self.results[('h2a', k)] = dict(obs=obs, reps=reps, h2=h2, sel=sel, boot=boot, bS=bS, cS=cS,
                                            XT_s=XT_s, XC_s=XC_s, cats=cats, strata=strata)
            if per_set_perm:
                rng = np.random.default_rng(SEED)

                def per_stat(cc):
                    st = h2.stat(cc)
                    return np.where(st['enter'], st['per'], -np.inf)
                null = h2.permute(D.mapped_flag[sel], cats, strata[sel], rng, per_stat)
                self.results[('h2a_per_null', k)] = null
            # H1
            own = np.array([D.sets.index(s) if s else -1 for s in D.target])
            h1pop = sel & (own >= 0) & (D.type != 'Unknown')
            h1pop &= np.array([E[i, own[i]] if own[i] >= 0 else False for i in range(len(own))])
            ii = np.flatnonzero(sel)
            pos = {j: q for q, j in enumerate(ii)}
            b1 = np.array([bS[i, own[i]] for i in np.flatnonzero(h1pop)], float)
            c1 = np.array([cS[i, own[i]] for i in np.flatnonzero(h1pop)], float)
            sub_idx = boot.idx[[pos[i] for i in np.flatnonzero(h1pop)]]
            X = np.zeros((int(sel.sum()), 2))
            X[[pos[i] for i in np.flatnonzero(h1pop)], 0] = b1
            X[[pos[i] for i in np.flatnonzero(h1pop)], 1] = c1
            R = boot.rep(X)
            h1 = ratio(b1.sum(), c1.sum())
            lo1, hi1, und1 = ci(ratio(R[:, 0], R[:, 1]))
            R1 = boot.rep(X, ones=True)
            ONES_OK.append(bool(np.isclose(ratio(R1[0, 0], R1[0, 1]), h1) or (np.isinf(h1) and np.isinf(ratio(R1[0, 0], R1[0, 1])))))
            row.update(h1_n=int(h1pop.sum()), h1_b=int(b1.sum()), h1_c=int(c1.sum()), h1=float(h1), h1_lo=lo1,
                       h1_hi=hi1, h1_undefined_reps=und1,
                       h1_durkalski_p=durkalski(b1, c1, sub_idx, len(boot.clusters)) if len(b1) else np.nan)
            self.results[('h1', k)] = dict(pop=h1pop, own=own, b=b1, c=c1, boot=boot, sel=sel, pos=pos)
            # item 2 buckets (machine clusters, as TODOS asks)
            XT_b, XC_b = presence(k, MB)
            mb = Boot(D.mid[sel])
            rows = enrich(XT_b[sel], XC_b[sel], mb, list(BUCKET_FAMILY), with_ci=True)
            for _, r in rows.iterrows():
                row[f"bucket:{r.outcome}:mor"] = r.mor
                row[f"bucket:{r.outcome}:mor_lo"] = r.get('mor_lo', np.nan)
                row[f"bucket:{r.outcome}:mor_hi"] = r.get('mor_hi', np.nan)
                row[f"bucket:{r.outcome}:rd"] = r.rd
                row[f"bucket:{r.outcome}:durkalski_p"] = r.durkalski_p
            self.results[('row', k)] = row
            if h2b:
                self.results[('h2b', k)] = self.run_h2b(h2, cats, strata[sel], obs['enter'], admin)

    def run_h2b(self, h2, cats, pk, enter_a, admin):
        D = self.D
        obs = h2.stat(cats, comparator='nit', admin=admin, restrict=enter_a)
        reps = h2.bootstrap(obs['T'], obs['K'], obs['enter'])
        lo, hi, und = ci(reps[False][1])
        inpool = (obs['T'][:, enter_a] | obs['K'][:, enter_a]).any(1) if enter_a.any() else np.zeros(len(cats), bool)
        rng = np.random.default_rng(SEED)
        null = h2.permute(inpool, cats, pk, rng,
                          lambda cc: h2.stat(cc, comparator='nit', admin=admin, restrict=enter_a)['pooled'])
        p, se = perm_p(obs['pooled'], null)
        return dict(obs=obs, lo=lo, hi=hi, undefined=und, p=p, mcse=se, reps=reps)


# ----------------------------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------------------------
def first_look(D, P):
    """docs/07 §8: the TODOS first look, reproduced exactly (3,259 paired tickets, 30-d last-10 list)."""
    sel = P['paired']
    MB = D.bucket_mask(['Electronics/software/comms', 'Door issue', 'Mechanical fault', 'Stock-out'])
    XT = D.W['corrected_guard0'].present(K30, MB)[sel]
    XC = D.W['control_minus35d'].present(K30, MB)[sel]
    want = {'Electronics/software/comms': (20.3, 13.1), 'Door issue': (67.9, 61.1), 'Mechanical fault': (54.6, 52.2),
            'Stock-out': (46.3, 45.3)}
    for j, b in enumerate(want):
        check(f'first look: {b} (ticket, control %)', want[b],
              (round(100 * XT[:, j].mean(), 1), round(100 * XC[:, j].mean(), 1)))
    anyT = (D.W['corrected_guard0'].distinct[sel] > 0).mean()
    anyC = (D.W['control_minus35d'].distinct[sel] > 0).mean()
    check('first look: any code (ticket, control %)', (90.2, 89.0), (round(100 * anyT, 1), round(100 * anyC, 1)))
    em = sel & (D.trouble_code == 'Electro/Mechanical')
    j = 1
    xt = D.W['corrected_guard0'].present(K30, MB)[em][:, j]
    xc = D.W['control_minus35d'].present(K30, MB)[em][:, j]
    check('first look: Electro/Mechanical Door (n, ticket %, control %)', (1781, 78.2, 67.8),
          (int(em.sum()), round(100 * xt.mean(), 1), round(100 * xc.mean(), 1)))


def main():
    global BLIND, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--blind', action='store_true')
    ap.add_argument('--out', default=str(OUTPUTS / 'assoc'))
    args = ap.parse_args()
    BLIND = args.blind
    OUT = Path(args.out)
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print('A. Load and pinned checks')
    D = Data()
    P = populations(D)
    D.mapped_flag = P['mapped']
    first_look(D, P)
    E, emit_lists = emit_matrix(D, D.sets)
    for s in D.sets:
        check(f'A10 emitting types for {s}', EMIT_TYPES[s], emit_lists[s])
    prim = P['primary']
    for s in D.sets:
        cats = [c for c, x in D.cat_set.items() if x == s]
        T = prim & np.isin(D.category, cats) & E[:, D.sets.index(s)]
        check(f'T on emitting types: {s}', T_ON_EMITTING[s], int(T.sum()))
    nit = prim & np.array([D.cat_bucket.get(c, '') == 'Not in telemetry' if c else False for c in D.category])
    check('H2b K (Not in telemetry, primary)', PINS['H2b K (Not in telemetry, primary)'], int(nit.sum()))
    MF = D.mask([[c] for c in D.valid_codes + [c for c in D.codes if D.bucket_of[c] == 'Malformed']])
    allc = D.valid_codes + [c for c in D.codes if D.bucket_of[c] == 'Malformed']
    WT, WC = D.W['corrected_guard0'], D.W['control_minus35d']
    win30 = np.vstack([WT.present(K30, MF)[prim], WC.present(K30, MF)[prim]])
    check('frequent windows', PINS['frequent windows'], win30.shape[0])
    freq = [c for c, n in zip(allc, win30.sum(0)) if n >= 0.01 * win30.shape[0]]
    freq = sorted(freq, key=lambda c: (len(c), c))
    check('frequent codes', FREQUENT, freq)

    def base_presence(k, M):
        return WT.present(k, M), WC.present(k, M)

    keep_primary = lambda k: P['det7'] if k <= K7 else np.ones(len(D.ids), bool)  # noqa: E731
    summary = {'generated_by': 'verification/association.py', 'protocol': 'docs/07_association_protocol.md',
               'crosswalk_sha256': FROZEN_HASH, 'seed': SEED, 'n_boot': N_BOOT, 'n_perm': N_PERM,
               'pinned_counts': PINS, 't_on_emitting_types': T_ON_EMITTING, 'emitting_types': emit_lists,
               'frequent_codes': freq}

    print('B. H2a, H1, per-set, H2b, negative controls')
    core = Core(D, P, E, 'primary', prim, base_presence, keep_primary, per_set_perm=True, h2b=True)
    sets = D.sets
    h2a_rows, h2b_rows, h1_rows, set_rows = [], [], [], []
    decision = {}
    for k in (K7, K30):
        R = core.results[('h2a', k)]
        obs, reps, h2 = R['obs'], R['reps'], R['h2']
        bT, cT, bK, cK = obs['parts']
        per_null = core.results[('h2a_per_null', k)]
        for j, s in enumerate(sets):
            lo, hi, und = ci(reps[False][0][:, j])
            pp, se = perm_p(obs['per'][j] if obs['enter'][j] else -np.inf, per_null[:, j]) if obs['enter'][j] \
                else (np.nan, np.nan)
            cats = sorted(c for c, x in D.cat_set.items() if x == s)
            h2a_rows.append(dict(k=k, set=s, categories='; '.join(cats), entered=int(obs['enter'][j]),
                                 n_T=int(obs['T'][:, j].sum()), n_K=int(obs['K'][:, j].sum()),
                                 b_T=int(bT[:, j].sum()), c_T=int(cT[:, j].sum()), b_K=int(bK[:, j].sum()),
                                 c_K=int(cK[:, j].sum()), estimate=obs['per'][j], ci_lo=lo, ci_hi=hi,
                                 undefined_reps=und, perm_p=pp, perm_mcse=se, perm_p_role='descriptive'))
        row = core.results[('row', k)]
        h2a_rows.append(dict(k=k, set='POOLED', categories='', entered=int(obs['enter'].any()),
                             n_T=int(obs['T'][:, obs['enter']].sum()),  # ticket-set combinations over entering sets
                             n_K=int(obs['K'][:, obs['enter']].sum()), b_T=int(bT[:, obs['enter']].sum()),
                             c_T=int(cT[:, obs['enter']].sum()), b_K=int(bK[:, obs['enter']].sum()),
                             c_K=int(cK[:, obs['enter']].sum()), estimate=row['h2a'], ci_lo=row['h2a_lo'],
                             ci_hi=row['h2a_hi'], undefined_reps=row['h2a_undefined_reps'], perm_p=row['h2a_perm_p'],
                             perm_mcse=row['h2a_perm_mcse'],
                             perm_p_role='decision' if k == K7 else 'secondary (30 d)'))
        if k == K7:
            decision['h2a_success'] = bool(np.isfinite(row['h2a']) and row['h2a'] > 0 and row['h2a_perm_p'] <= 0.05)
        # H2b
        hb = core.results[('h2b', k)]
        ob = hb['obs']
        for j, s in enumerate(sets):
            if not obs['enter'][j]:
                continue
            lo, hi, und = ci(hb['reps'][False][0][:, j])
            pb = ob['parts']
            h2b_rows.append(dict(k=k, set=s, entered=int(ob['enter'][j]), n_T=int(ob['T'][:, j].sum()),
                                 n_K=int(ob['K'][:, j].sum()), b_T=int(pb[0][:, j].sum()), c_T=int(pb[1][:, j].sum()),
                                 b_K=int(pb[2][:, j].sum()), c_K=int(pb[3][:, j].sum()), estimate=ob['per'][j],
                                 ci_lo=lo, ci_hi=hi, undefined_reps=und))
        h2b_rows.append(dict(k=k, set='POOLED', entered=int(ob['enter'].any()), estimate=ob['pooled'], ci_lo=hb['lo'],
                             ci_hi=hb['hi'], undefined_reps=hb['undefined'], perm_p=hb['p'], perm_mcse=hb['mcse']))
        # H1
        h1 = core.results[('h1', k)]
        gate_h1 = decision.get('h2a_success', False) if k == K7 else None
        h1_rows.append(dict(k=k, n_pairs=row['h1_n'], sum_b=row['h1_b'], sum_c=row['h1_c'], estimate=row['h1'],
                            ci_lo=row['h1_lo'], ci_hi=row['h1_hi'], undefined_reps=row['h1_undefined_reps'],
                            durkalski_p=row['h1_durkalski_p'],
                            status=('tested' if gate_h1 else 'not tested (H2a gate)') if k == K7 else 'secondary'))
        if k == K7:
            decision['h1_success'] = bool(gate_h1 and row['h1_b'] > row['h1_c'] and row['h1_durkalski_p'] <= 0.05)
        # per set (H1 population, own set)
        pop, own, boot, sel, pos = h1['pop'], h1['own'], h1['boot'], h1['sel'], h1['pos']
        bS, cS = R['bS'], R['cS']
        XT_s, XC_s = R['XT_s'], R['XC_s']
        srows = []
        for j, s in enumerate(sets):
            m = pop & (own == j)
            ii = np.flatnonzero(m)
            if not len(ii):
                srows.append(dict(k=k, set=s, n_pairs=0, b=0, c=0, tested=0))
                continue
            sub = Boot(D.account[sel])  # same clusters as the analysed pairs (one W per population)
            XT = np.zeros((int(sel.sum()), 1), bool)
            XC = np.zeros((int(sel.sum()), 1), bool)
            rowsel = np.zeros(int(sel.sum()), bool)
            rowsel[[pos[i] for i in ii]] = True
            XT[rowsel, 0] = XT_s[ii, j]
            XC[rowsel, 0] = XC_s[ii, j]
            # restrict sums to the subpopulation: rows outside it contribute zero to every cluster sum
            er = enrich_sub(XT[:, 0], XC[:, 0], rowsel, sub)
            er.update(k=k, set=s)
            srows.append(er)
        sr = pd.DataFrame(srows)
        sr['tested'] = ((sr.n_pairs >= MIN_PAIRS) & ((sr.b + sr.c) >= MIN_DISC)).astype(int)
        q = np.full(len(sr), np.nan)
        t = sr.tested.to_numpy() == 1
        if t.any():
            q[t] = bh_q(sr.loc[t, 'durkalski_p'].to_numpy())
        sr['bh_q'] = q
        gate_sets = decision.get('h1_success', False) if k == K7 else None
        sr['status'] = np.where(sr.tested == 1, ('tested' if gate_sets else 'not tested (H1 gate)') if k == K7
                                else 'secondary', 'not estimable (A12)')
        sr['enriched'] = ((sr.status == 'tested') & (sr.b > sr.c) & (sr.bh_q <= 0.05)).astype(int)
        set_rows.append(sr)
    summary['decision'] = decision
    hd, h1d = pd.DataFrame(h2a_rows), pd.DataFrame(h1_rows)
    for k in (K7, K30):
        r = hd[(hd.k == k) & (hd.set == 'POOLED')].iloc[0]
        rnd = lambda t: tuple(round(float(x), 12) for x in t)  # noqa: E731
        check(f'pinned pooled H2a at k={k:g} (estimate, interval, permutation p)', rnd(RESULT_PINS[('h2a', k)]),
              rnd((r.estimate, r.ci_lo, r.ci_hi, r.perm_p)))
        r = h1d[h1d.k == k].iloc[0]
        check(f'pinned H1 at k={k:g} (estimate, interval, b, c)', rnd(RESULT_PINS[('h1', k)]),
              rnd((r.estimate, r.ci_lo, r.ci_hi, r.sum_b, r.sum_c)))
    save(hd, 'h2a')
    save(pd.DataFrame(h2b_rows), 'h2b')
    save(h1d, 'h1')
    save(pd.concat(set_rows, ignore_index=True), 'sets')
    neg = negative_controls(D, P, E, core)
    save(neg, 'negative_controls')

    print('C. Item 2: buckets and frequent codes')
    item2(D, P, freq)
    print('D. Item 3: recency')
    recency(D, P, E, core)
    print('E. Item 4: excess presence fraction and match rates')
    item4(D, P, E, core)
    print('F. Item 6: machine type and model')
    item6(D, P, E, core)
    print('G. Sensitivities')
    sens = sensitivities(D, P, E, core)
    save(sens, 'sensitivities')
    for k in (K7, K30):
        a = float(neg.loc[(neg.k == k) & neg.h2a_s13.notna(), 'h2a_s13'].iloc[0])
        b = float(sens.loc[sens.variant.str.startswith('S13') & (sens.k == k), 'dd_h2a'].iloc[0])
        check(f'S13 k={k:g}: Core per-set estimate = negative-control estimate', True, bool(np.isclose(a, b)))
    check('all-ones bootstrap replicate reproduces every point estimate', True, all(ONES_OK))
    durk_mcnemar_check()
    pairs = pd.DataFrame({'case_id': D.ids, 'machine_id': D.mid, 'in_paired': P['paired'].astype(int),
                          'in_primary': prim.astype(int), 'determined_7d': P['det7'].astype(int),
                          'cluster': D.account, 'type': D.type, 'quarter': D.quarter, 'category': D.category,
                          'target_codes': D.target})
    save(pairs[P['paired'] | P['excl157']], 'pairs')
    print('H. Privacy')
    privacy()
    summary['checks'] = {'pass': sum(c['status'] == 'PASS' for c in CHECKS),
                         'fail': sum(c['status'] == 'FAIL' for c in CHECKS)}
    summary['check_list'] = CHECKS
    summary['elapsed_s'] = round(time.time() - t0, 1)
    txt = json.dumps(jsonable(summary), indent=1, allow_nan=False)
    (OUT / f'{PREFIX}summary.json').write_text(txt)
    print(f"  wrote {PREFIX}summary.json (sha256 {hashlib.sha256(txt.encode()).hexdigest()[:16]})")
    fails = [c for c in CHECKS if c['status'] == 'FAIL']
    print(f"\nDone in {time.time() - t0:.1f} s: {len(CHECKS) - len(fails)} checks passed, {len(fails)} failed.")
    return 1 if fails else 0


def enrich_sub(xt, xc, rowsel, boot):
    """Enrichment for a subpopulation of the analysed pairs; clusters of the full population (zero outside)."""
    xt = xt & rowsel
    xc = xc & rowsel
    b = xt & ~xc
    c = ~xt & xc
    n = int(rowsel.sum())
    X = np.column_stack([rowsel, xt, xc, b, c]).astype(float)
    R = boot.rep(X)
    nr, nTr, nCr, br, cr = (R[:, j] for j in range(5))
    with np.errstate(divide='ignore', invalid='ignore'):
        rd_r = np.where(nr > 0, (nTr - nCr) / np.where(nr > 0, nr, 1), np.nan)
    out = dict(n_pairs=n, n_T=int(xt.sum()), n_C=int(xc.sum()), b=int(b.sum()), c=int(c.sum()))
    out['pT'] = out['n_T'] / n
    out['pC'] = out['n_C'] / n
    out['rd'] = out['pT'] - out['pC']
    out['lift'] = float(ratio(out['n_T'], out['n_C']))
    out['mor'] = float(ratio(out['b'], out['c']))
    for nm, Rx in (('rd', rd_r), ('lift', ratio(nTr, nCr)), ('mor', ratio(br, cr))):
        lo, hi, und = ci(Rx)
        out[f'{nm}_lo'], out[f'{nm}_hi'], out[f'{nm}_undefined_reps'] = lo, hi, und
    R1 = boot.rep(X, ones=True)[0]
    ONES_OK.append(bool(np.isclose(ratio(R1[3], R1[4]), out['mor']) or
                        (np.isinf(out['mor']) and np.isinf(ratio(R1[3], R1[4]))) or
                        (np.isnan(out['mor']) and np.isnan(ratio(R1[3], R1[4])))))
    out['durkalski_p'] = durkalski(b[rowsel].astype(float), c[rowsel].astype(float), boot.idx[rowsel],
                                   len(boot.clusters))
    return out


# ----------------------------------------------------------------------------------------------------------------
# B (continued): negative controls and S13
# ----------------------------------------------------------------------------------------------------------------
def negative_controls(D, P, E, core):
    rows = []
    sets13 = [S13_SET]
    E13, lists13 = emit_matrix(D, sets13)
    for k in (K7, K30):
        R = core.results[('h2a', k)]
        sel, boot = R['sel'], R['h2'].boot
        M = D.mask([list(STOCKOUT)])
        XT = D.W['corrected_guard0'].present(k, M)[sel][:, 0]
        XC = D.W['control_minus35d'].present(k, M)[sel][:, 0]
        keep = ~np.isin(D.target[sel], [s for s in D.sets if set(s.split('|')) & set(STOCKOUT)])
        er = enrich_sub(XT, XC, keep, boot)
        er.update(k=k, control='Stock-out (03, 77), tickets whose set has neither code')
        rows.append(er)
        # S13: Deposit Door without 19 and 78 -> {20, 79, 80}; A10 recomputed; Improper Use joins K
        dd = sel & (D.category == 'Deposit Door') & E13[:, 0] & (D.type != 'Unknown')
        M13 = D.set_mask(sets13)
        XT13 = D.W['corrected_guard0'].present(k, M13)[:, 0]
        XC13 = D.W['control_minus35d'].present(k, M13)[:, 0]
        b13, c13 = XT13 & ~XC13, ~XT13 & XC13
        codes13 = set(S13_SET.split('|'))
        disj = np.array([bool(t) and not (set(t.split('|')) & codes13) for t in D.target])
        K13 = sel & disj & E13[:, 0] & (D.type != 'Unknown')
        strata = np.array([f'{a}|{b}' for a, b in zip(D.type, D.quarter)], dtype=object)
        keys = sorted(set(strata[sel]))
        num = den = 0.0
        for h in keys:
            mh = strata == h
            bT, cT = (b13 & dd & mh).sum(), (c13 & dd & mh).sum()
            bK, cK = (b13 & K13 & mh).sum(), (c13 & K13 & mh).sum()
            n = bT + cT + bK + cK
            if n:
                num += bT * cK / n
                den += cT * bK / n
        sub = dd[sel]
        er = enrich_sub(XT13[sel], XC13[sel], sub, boot)
        er.update(k=k, control='S13: Deposit Door tickets, set {20, 79, 80} (A10 recomputed)',
                  h2a_s13=float(safe_log(ratio(num, den))), n_K=int(K13.sum()))
        rows.append(er)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------------------------
# C. item 2
# ----------------------------------------------------------------------------------------------------------------
def item2(D, P, freq):
    WT, WC = D.W['corrected_guard0'], D.W['control_minus35d']
    prim = P['primary']
    buckets = list(BUCKET_FAMILY) + ['Malformed']
    MB = D.bucket_mask(buckets)
    many = D.mask([[c for c in D.codes if c != '00']])
    MC = D.mask([[c] for c in freq])
    out_b, out_c, brk = [], [], []
    for k in (K7, K30):
        sel = prim & (P['det7'] if k <= K7 else True)
        mb = Boot(D.mid[sel])
        XT = np.column_stack([WT.present(k, MB), WT.present(k, many)])[sel]
        XC = np.column_stack([WC.present(k, MB), WC.present(k, many)])[sel]
        rb = enrich(XT, XC, mb, buckets + ['any code'])
        fam = rb.outcome.isin(BUCKET_FAMILY).to_numpy()
        q = np.full(len(rb), np.nan)
        q[fam] = bh_q(rb.durkalski_p.to_numpy()[fam])
        rb['bh_q'] = q
        rb.insert(0, 'k', k)
        out_b.append(rb)
        rc = enrich(WT.present(k, MC)[sel], WC.present(k, MC)[sel], mb, freq)
        rc['bh_q'] = bh_q(rc.durkalski_p.to_numpy())
        rc.insert(0, 'k', k)
        out_c.append(rc)
        # breakdowns: Category, Trouble Code (pooled over its Categories), and the 157 (descriptive, unadjusted p)
        XTb = np.column_stack([WT.present(k, MB), WT.present(k, many)])
        XCb = np.column_stack([WC.present(k, MB), WC.present(k, many)])
        groups = []
        for c in sorted(set(D.category[sel]) - {''}):
            groups.append(('category', c, sel & (D.category == c)))
        for tc in sorted(set(D.trouble_code[sel & (D.category != '')]) - {''}):
            groups.append(('trouble_code', tc, sel & (D.category != '') & (D.trouble_code == tc)))
        ex = P['excl157'] & (P['det7'] if k <= K7 else True)
        groups.append(('excluded157', 'other ticket in [A-5d, A)', ex))
        for level, g, m in groups:
            lab = D.mid[m]
            bt = Boot(lab) if len(lab) else None
            r = enrich(XTb[m], XCb[m], bt, buckets + ['any code'], with_ci=False) if bt else None
            if r is None:
                continue
            r.insert(0, 'group', g)
            r.insert(0, 'level', level)
            r.insert(0, 'k', k)
            brk.append(r)
    b = pd.concat(out_b, ignore_index=True)
    c = pd.concat(out_c, ignore_index=True)
    br = pd.concat(brk, ignore_index=True)
    # Trouble Code row = sum of its Category rows (counts)
    ok = True
    for k in (K7, K30):
        cat = br[(br.k == k) & (br.level == 'category')]
        tcr = br[(br.k == k) & (br.level == 'trouble_code')]
        tc_of = {cg: D.xw.trouble_code.get(cg, '') for cg in cat.group.unique()}
        agg = cat.assign(tc=cat.group.map(tc_of)).groupby(['tc', 'outcome'])[['n_pairs', 'n_T', 'n_C', 'b', 'c']].sum()
        mine = tcr.set_index(['group', 'outcome'])[['n_pairs', 'n_T', 'n_C', 'b', 'c']]
        agg.index.names = ['group', 'outcome']
        ok &= agg.sort_index().equals(mine.sort_index())
    check('each Trouble Code row equals the sum of its Category rows', True, bool(ok))
    save(b, 'item2_buckets')
    save(c, 'item2_codes')
    save(br, 'item2_breakdowns')


# ----------------------------------------------------------------------------------------------------------------
# D. item 3
# ----------------------------------------------------------------------------------------------------------------
def recency(D, P, E, core):
    WT, WC = D.W['corrected_guard0'], D.W['control_minus35d']
    prim, det7 = P['primary'], P['det7']
    OUTS = list(BUCKET_FAMILY) + ['Malformed', 'any code']
    MB = np.column_stack([D.bucket_mask(list(BUCKET_FAMILY) + ['Malformed']), D.mask([[c for c in D.codes if c != '00']])])
    own = core.results[('h1', K7)]['own']
    h1pop7 = core.results[('h1', K7)]['pop']
    h1pop30 = core.results[('h1', K30)]['pop']
    MS = D.set_mask(D.sets)
    rows, bins, guard = [], [], []
    mono_ok, sub_ok, guard_ok, bins_ok = True, True, True, True
    prevT = prevC = None
    for k in K_GRID:
        sel = prim & (det7 if k <= K7 else True)
        XT, XC = WT.present(k, MB), WC.present(k, MB)
        r = enrich(XT[sel], XC[sel], Boot(D.mid[sel]), OUTS, with_ci=False)
        r.insert(0, 'k', k)
        r.insert(0, 'curve', 'bucket')
        rows.append(r)
        hp = (h1pop7 if k <= K7 else h1pop30)
        ii = np.flatnonzero(hp)
        xt = WT.present(k, MS)[ii, own[ii]]
        xc = WC.present(k, MS)[ii, own[ii]]
        r2 = enrich(xt[:, None], xc[:, None], Boot(D.account[hp]), ['target set'], with_ci=False)
        r2.insert(0, 'k', k)
        r2.insert(0, 'curve', 'target')
        rows.append(r2)
        if k <= K7:
            fix = prim & det7
            cur_T, cur_C = WT.present(k, MB)[fix], WC.present(k, MB)[fix]
            if prevT is not None:
                mono_ok &= bool((cur_T >= prevT).all() and (cur_C >= prevC).all())
            prevT, prevC = cur_T, cur_C
            mono_ok &= bool((cur_T <= WT.present(K30, MB)[fix]).all() and (cur_C <= WC.present(K30, MB)[fix]).all())
            for w, g in GUARDS.items():
                if k > g:
                    sub_ok &= bool((D.W[w].present(k, MB)[fix] <= cur_T).all())
    check('presence never decreases with k and sits inside 30-d list membership', True, mono_ok)
    check('guard-window presence sits inside corrected_guard0 presence at each k', True, sub_ok)
    # exclusive bins (all primary pairs) and their consistency with the curve on the 7-d pairs
    for name, M, popm, by_own in (('bucket', MB, prim, False), ('target', MS, h1pop30, True)):
        for side, Wd in (('ticket', WT), ('control', WC)):
            mh = Wd.min_hours(M)
            if by_own:
                ii = np.flatnonzero(popm)
                vals = mh[ii, own[ii]][:, None]
                full = (Wd.distinct[ii] > 10)[:, None]
                outs = ['target set']
            else:
                vals = mh[popm]
                full = (Wd.distinct[popm] > 10)[:, None]
                outs = OUTS
            for j, o in enumerate(outs):
                v = vals[:, j]
                rec = dict(curve=name, outcome=o, side=side, n=len(v))
                for (lo, hi), lab in zip(BINS, BIN_LABELS):
                    rec[lab] = int(((v >= lo) & (v < hi)).sum())
                rec['absent'] = int((~np.isfinite(v) & ~full[:, 0]).sum())
                rec['not listed, list full'] = int((~np.isfinite(v) & full[:, 0]).sum())
                bins.append(rec)
    fix = prim & det7
    for side, Wd in (('ticket', WT), ('control', WC)):
        mh = Wd.min_hours(MB)[fix]
        for edge in (2, 6, 24, 168):
            bins_ok &= bool(((mh < edge).sum(0) == Wd.present(edge, MB)[fix].sum(0)).all())
    check('exclusive bins add up to the cumulative curve', True, bins_ok)
    # guard rows (ticket side) at k = 6 h, 24 h, 7 d
    for w, g in GUARDS.items():
        Wg = D.W[w]
        fixg = fix & ~Wg.undetermined(K7)
        gc = GuardedControl(WC, g)
        for k in (6.0, 24.0, K7):
            r0 = WT.present(k, MB)[fixg].mean(0)
            rg = Wg.present(k, MB)[fixg].mean(0)
            c0 = WC.present(k, MB)[fixg].mean(0)
            clo, chi = (x[fixg].mean(0) for x in gc.bounds(k, MB))
            for o, a, b_, c_, l_, h_ in zip(OUTS, r0, rg, c0, clo, chi):
                guard.append(dict(window=w, guard_h=g, k=k, outcome=o, n_pairs=int(fixg.sum()), p_guard0=a,
                                  p_guard=b_, p_control=c_, p_control_guard_lo=l_, p_control_guard_hi=h_))
            hp = h1pop7 & ~Wg.undetermined(K7)
            ii = np.flatnonzero(hp)
            blo, bhi = gc.bounds(k, MS)
            guard.append(dict(window=w, guard_h=g, k=k, outcome='target set', n_pairs=len(ii),
                              p_guard0=WT.present(k, MS)[ii, own[ii]].mean(), p_guard=Wg.present(k, MS)[ii, own[ii]].mean(),
                              p_control=WC.present(k, MS)[ii, own[ii]].mean(), p_control_guard_lo=blo[ii, own[ii]].mean(),
                              p_control_guard_hi=bhi[ii, own[ii]].mean()))
    save(pd.concat(rows, ignore_index=True), 'recency')
    save(pd.DataFrame(bins), 'recency_bins')
    save(pd.DataFrame(guard), 'guard')


# ----------------------------------------------------------------------------------------------------------------
# E. item 4
# ----------------------------------------------------------------------------------------------------------------
def item4(D, P, E, core):
    WT, WC = D.W['corrected_guard0'], D.W['control_minus35d']
    MS = D.set_mask(D.sets)
    rows = []
    h = core.results[('h1', K7)]
    pop, own, boot, sel, pos = h['pop'], h['own'], h['boot'], h['sel'], h['pos']
    ii = np.flatnonzero(pop)
    rsel = np.array([pos[i] for i in ii])
    ks = [k for k in K_GRID if k <= K7]
    XT = np.column_stack([WT.present(k, MS)[ii, own[ii]] for k in ks]).astype(float)
    XC = np.column_stack([WC.present(k, MS)[ii, own[ii]] for k in ks]).astype(float)
    nsel = int(sel.sum())
    Xfull = np.zeros((nsel, 1 + 2 * len(ks)))
    Xfull[rsel, 0] = 1
    Xfull[rsel, 1:1 + len(ks)] = XT
    Xfull[rsel, 1 + len(ks):] = XC
    R = boot.rep(Xfull)
    n_r = R[:, :1]
    pT_r, pC_r = R[:, 1:1 + len(ks)] / n_r, R[:, 1 + len(ks):] / n_r
    pT, pC = XT.mean(0), XC.mean(0)
    for j, k in enumerate(ks):
        epf = (pT[j] - pC[j]) / pT[j] if pT[j] > 0 else np.nan
        with np.errstate(divide='ignore', invalid='ignore'):
            epf_r = np.where(pT_r[:, j] > 0, (pT_r[:, j] - pC_r[:, j]) / pT_r[:, j], np.nan)
        lo, hi, und = ci(epf_r)
        rows.append(dict(measure='excess presence fraction', k=k, n_pairs=len(ii), pT=pT[j], pC=pC[j], estimate=epf,
                         ci_lo=lo, ci_hi=hi, undefined_reps=und,
                         upper_bound=min(1.0, (1 - pC[j]) / pT[j]) if pT[j] > 0 else np.nan))
    tight = (pT - pC) / pT[-1]
    j = int(np.argmax(tight))
    with np.errstate(divide='ignore', invalid='ignore'):
        tr = (pT_r - pC_r) / pT_r[:, -1:]
    tr_max = np.nanmax(tr, axis=1)
    lo, hi, und = ci(tr_max)
    rows.append(dict(measure='tightest lower bound over k <= 7 d', k=ks[j], n_pairs=len(ii), estimate=tight[j],
                     ci_lo=lo, ci_hi=hi, undefined_reps=und))
    # 30 d
    h30 = core.results[('h1', K30)]
    i3 = np.flatnonzero(h30['pop'])
    xt3 = WT.present(K30, MS)[i3, own[i3]].astype(float)
    xc3 = WC.present(K30, MS)[i3, own[i3]].astype(float)
    pT3, pC3 = xt3.mean(), xc3.mean()
    X3 = np.zeros((int(h30['sel'].sum()), 3))
    r3 = np.array([h30['pos'][i] for i in i3])
    X3[r3, 0], X3[r3, 1], X3[r3, 2] = 1, xt3, xc3
    R3 = h30['boot'].rep(X3)
    with np.errstate(divide='ignore', invalid='ignore'):
        e3 = np.where(R3[:, 1] > 0, (R3[:, 1] - R3[:, 2]) / R3[:, 1], np.nan)
    lo3, hi3, und3 = ci(e3)
    rows.append(dict(measure='excess presence fraction', k=K30, n_pairs=len(i3), pT=pT3, pC=pC3,
                     estimate=(pT3 - pC3) / pT3 if pT3 > 0 else np.nan, ci_lo=lo3, ci_hi=hi3, undefined_reps=und3,
                     upper_bound=min(1.0, (1 - pC3) / pT3) if pT3 > 0 else np.nan))
    # concordant pairs at 7 d: more recent / more occurrences
    both = XT[:, -1].astype(bool) & XC[:, -1].astype(bool)
    mhT = WT.min_hours(MS)[ii, own[ii]]
    mhC = WC.min_hours(MS)[ii, own[ii]]
    occT = (WT.O[ii] * MS[:, own[ii]].T).sum(1)
    occC = (WC.O[ii] * MS[:, own[ii]].T).sum(1)
    for nm, flag in (('both present at 7 d: ticket code more recent', mhT < mhC),
                     ('both present at 7 d: ticket window count higher (whole-window occurrences)', occT > occC)):
        X = np.zeros((nsel, 2))
        X[rsel[both], 0] = 1
        X[rsel[both], 1] = flag[both]
        Rb = boot.rep(X)
        with np.errstate(divide='ignore', invalid='ignore'):
            sh = np.where(Rb[:, 0] > 0, Rb[:, 1] / Rb[:, 0], np.nan)
        lo, hi, und = ci(sh)
        rows.append(dict(measure=nm, k=K7, n_pairs=int(both.sum()),
                         estimate=flag[both].mean() if both.any() else np.nan, ci_lo=lo, ci_hi=hi,
                         undefined_reps=und))
    # Exploratory, added after unblinding (item 8 skeptic review; not pre-specified): the same measures for the codes
    # of every set that shares no code with the ticket's own set (the H2a comparator definition, docs/07 §4). They
    # show how much of the fraction is generic activity before a ticket rather than specific to the Category.
    sc = [set(x.split('|')) for x in D.sets]
    MU = D.mask([sorted(set().union(*(b for b in sc if not (a & b)))) for a in sc])
    uT = np.array([WT.present(k, MU)[ii, own[ii]].mean() for k in ks])
    uC = np.array([WC.present(k, MU)[ii, own[ii]].mean() for k in ks])
    for j, k in enumerate(ks):
        rows.append(dict(measure='exploratory: excess presence fraction, unrelated sets', k=k, n_pairs=len(ii),
                         pT=uT[j], pC=uC[j], estimate=(uT[j] - uC[j]) / uT[j] if uT[j] > 0 else np.nan))
    tu = (uT - uC) / uT[-1]
    rows.append(dict(measure='exploratory: tightest bound, unrelated sets', k=ks[int(np.argmax(tu))], n_pairs=len(ii),
                     estimate=float(tu.max())))
    bothu = WT.present(K7, MU)[ii, own[ii]] & WC.present(K7, MU)[ii, own[ii]]
    mhTu, mhCu = WT.min_hours(MU)[ii, own[ii]], WC.min_hours(MU)[ii, own[ii]]
    occTu = (WT.O[ii] * MU[:, own[ii]].T).sum(1)
    occCu = (WC.O[ii] * MU[:, own[ii]].T).sum(1)
    for nm, flag in (('exploratory: unrelated sets, both present at 7 d: ticket code more recent', mhTu < mhCu),
                     ('exploratory: unrelated sets, both present at 7 d: ticket window count higher', occTu > occCu)):
        rows.append(dict(measure=nm, k=K7, n_pairs=int(bothu.sum()), estimate=flag[bothu].mean()))
    save(pd.DataFrame(rows), 'item4')
    match_rates(D, P, E)


def match_rates(D, P, E):
    WT, WC = D.W['corrected_guard0'], D.W['control_minus35d']
    prim, det7 = P['primary'], P['det7']
    rows = []
    team = sorted(set(b for b in D.cat_bucket.values() if b and b not in NON_TEAM_TARGETS))
    # Exploratory (after unblinding; skeptic review): micro-averaged target-code precision and recall by look-back,
    # on the same 7-d pairs, to show what a linker gains by looking only at the final hours.
    sel7 = prim & det7 & (D.category != '')
    MS = D.set_mask(D.sets)
    for k in [x for x in K_GRID if x <= K7]:
        for side, Wd in (('ticket', WT), ('control', WC)):
            X = Wd.present(k, MS)
            tp = pr = pos = 0
            for j, s in enumerate(D.sets):
                pop = sel7 & E[:, j] & (D.type != 'Unknown')
                tgt = pop & (D.target == s)
                tp += int((tgt & X[:, j]).sum())
                pr += int((pop & X[:, j]).sum())
                pos += int(tgt.sum())
            rows.append(dict(k=k, side=side, kind='exploratory: target code by look-back', unit='MICRO (overall)',
                             true_pos=tp, n_present=pr, n_target=pos, recall=tp / pos if pos else np.nan,
                             precision=tp / pr if pr else np.nan))
    for k in (K7, K30):
        sel = prim & (det7 if k <= K7 else True) & (D.category != '')
        MS = D.set_mask(D.sets)
        for side, Wd in (('ticket', WT), ('control', WC)):
            X = Wd.present(k, MS)
            tp = pr = pos = 0
            for j, s in enumerate(D.sets):
                pop = sel & E[:, j] & (D.type != 'Unknown')
                tgt = pop & (D.target == s)
                pres = pop & X[:, j]
                TP = int((tgt & X[:, j]).sum())
                rows.append(dict(k=k, side=side, kind='target code', unit=s, population=int(pop.sum()),
                                 n_target=int(tgt.sum()), n_present=int(pres.sum()), true_pos=TP,
                                 recall=TP / tgt.sum() if tgt.sum() else np.nan,
                                 precision=TP / pres.sum() if pres.sum() else np.nan))
                tp, pr, pos = tp + TP, pr + int(pres.sum()), pos + int(tgt.sum())
            rows.append(dict(k=k, side=side, kind='target code', unit='MICRO (overall)', true_pos=tp, n_present=pr,
                             n_target=pos, recall=tp / pos if pos else np.nan, precision=tp / pr if pr else np.nan,
                             note='pools different per-set populations; a ticket can count in several precision '
                                  'denominators (§14.5)'))
            MBt = D.bucket_mask(team)
            XB = Wd.present(k, MBt)
            tp = pr = pos = 0
            for j, b in enumerate(team):
                tgt = sel & (D.tbucket == b)
                pres = sel & XB[:, j]
                TP = int((tgt & XB[:, j]).sum())
                rows.append(dict(k=k, side=side, kind='matching bucket', unit=b, population=int(sel.sum()),
                                 n_target=int(tgt.sum()), n_present=int(pres.sum()), true_pos=TP,
                                 recall=TP / tgt.sum() if tgt.sum() else np.nan,
                                 precision=TP / pres.sum() if pres.sum() else np.nan))
                tp, pr, pos = tp + TP, pr + int(pres.sum()), pos + int(tgt.sum())
            rows.append(dict(k=k, side=side, kind='matching bucket', unit='MICRO (overall)', true_pos=tp,
                             n_present=pr, n_target=pos, recall=tp / pos if pos else np.nan,
                             precision=tp / pr if pr else np.nan))
            # recall by Category
            for c in sorted(set(D.category[sel]) - {''}):
                m = sel & (D.category == c)
                s = D.cat_set.get(c, '')
                if s:
                    j = D.sets.index(s)
                    mm = m & E[:, j] & (D.type != 'Unknown')
                    rows.append(dict(k=k, side=side, kind='target code, by Category', unit=c, n_target=int(mm.sum()),
                                     true_pos=int((mm & X[:, j]).sum()),
                                     recall=(mm & X[:, j]).sum() / mm.sum() if mm.sum() else np.nan))
                b = D.cat_bucket.get(c, '')
                if b in team:
                    j = team.index(b)
                    rows.append(dict(k=k, side=side, kind='matching bucket, by Category', unit=c,
                                     n_target=int(m.sum()), true_pos=int((m & XB[:, j]).sum()),
                                     recall=(m & XB[:, j]).sum() / m.sum() if m.sum() else np.nan))
    save(pd.DataFrame(rows), 'match_rates')


# ----------------------------------------------------------------------------------------------------------------
# F. item 6
# ----------------------------------------------------------------------------------------------------------------
def item6(D, P, E, core):
    WT, WC = D.W['corrected_guard0'], D.W['control_minus35d']
    MS = D.set_mask(D.sets)
    rows, mrows = [], []
    for k in (K7, K30):
        h = core.results[('h1', k)]
        sel, own = h['sel'], h['own']
        XT, XC = WT.present(k, MS), WC.present(k, MS)
        mapped_all = sel & (own >= 0)
        for scope, pop in (('emitting types (H1 population)', h['pop']), ('all types', mapped_all)):
            for tp in sorted(set(D.type[pop])):
                m = pop & (D.type == tp)
                ii = np.flatnonzero(m)
                xt, xc = XT[ii, own[ii]], XC[ii, own[ii]]
                r = enrich(xt[:, None], xc[:, None], Boot(D.account[m]), ['target set'], with_ci=False).iloc[0].to_dict()
                r.update(k=k, scope=scope, type=tp, set='own set')
                rows.append(r)
                if scope.startswith('emitting'):  # docs/07 §5 item 6: per-set enrichment by machine type
                    for j, s_ in enumerate(D.sets):
                        mj = m & (own == j)
                        if not mj.any():
                            continue
                        jj = np.flatnonzero(mj)
                        r = enrich(XT[jj, j][:, None], XC[jj, j][:, None], Boot(D.account[mj]), ['target set'],
                                   with_ci=False).iloc[0].to_dict()
                        r.update(k=k, scope=scope, type=tp, set=s_)
                        rows.append(r)
        nonemit = mapped_all & ~h['pop']
        rows.append(dict(k=k, scope='mapped tickets on types that do not log their own set (or Unknown)',
                         type='(all)', set='own set', n_pairs=int(nonemit.sum())))
        pop = h['pop']
        for (tp, mo) in sorted(set(zip(D.type[pop], D.model[pop]))):
            m = pop & (D.type == tp) & (D.model == mo)
            ii = np.flatnonzero(m)
            xt, xc = XT[ii, own[ii]], XC[ii, own[ii]]
            r = enrich(xt[:, None], xc[:, None], Boot(D.account[m]), ['target set'], with_ci=False).iloc[0].to_dict()
            r.update(k=k, type=tp, model=mo)
            mrows.append(r)
    save(pd.DataFrame(rows), 'by_type')
    save(pd.DataFrame(mrows), 'by_model')


# ----------------------------------------------------------------------------------------------------------------
# G. sensitivities (docs/07 §6)
# ----------------------------------------------------------------------------------------------------------------
def sensitivities(D, P, E, core):
    WT, WC = D.W['corrected_guard0'], D.W['control_minus35d']
    prim, det7 = P['primary'], P['det7']
    rows = [core.results[('row', K7)], core.results[('row', K30)]]

    def base(k, M):
        return WT.present(k, M), WC.present(k, M)

    keep = lambda k: det7 if k <= K7 else np.ones(len(D.ids), bool)  # noqa: E731
    variants = []
    # S1
    D.mapped_flag_save = D.mapped_flag
    variants.append(('S1 planned/cancelled/duplicate put back', P['lifted'], base, keep, 'account', True))
    # S3 guard bands (ticket = guard window; control = emulated bounds)
    for w, g in GUARDS.items():
        Wg = D.W[w]
        gc = GuardedControl(WC, g)
        und_g = Wg.undetermined(K7)
        kg = lambda k, und_g=und_g: (det7 & ~und_g) if k <= K7 else np.ones(len(D.ids), bool)  # noqa: E731
        for bound in ('lower', 'upper'):
            def pres(k, M, Wg=Wg, gc=gc, bound=bound):
                lo, hi = gc.bounds(k, M)
                return Wg.present(k, M), (lo if bound == 'lower' else hi)
            variants.append((f'S3 guard {g:g} h, control {bound} bound', prim, pres, kg, 'account', False))
    variants.append(('S4 ticket-free lead-in (A >= 11 Nov 2025)', P['s4'], base, keep, 'account', False))
    variants.append(('S5 recently activated machines dropped', P['s5'], base, keep, 'account', False))
    variants.append(('S5b installed 2025 or later dropped', P['s5b'], base, keep, 'account', False))
    # S6: truncated windows included (A8 still applies)
    s6det = ~(WT.undetermined(K7) | WC.undetermined(K7))
    variants.append(('S6 lookback-truncated windows included', P['s6'],
                     base, lambda k: s6det if k <= K7 else np.ones(len(D.ids), bool), 'account', False))
    # S7: undetermined 7-d pairs kept, counted both ways
    uT, uC = P['uT'], P['uC']
    for bound in ('absent', 'present'):
        def pres7(k, M, bound=bound):
            xt, xc = WT.present(k, M), WC.present(k, M)
            if bound == 'present' and k <= K7:
                xt = xt | (WT.undetermined(k)[:, None])
                xc = xc | (WC.undetermined(k)[:, None])
            return xt, xc
        variants.append((f'S7 undetermined pairs counted {bound}', prim, pres7,
                         lambda k: np.ones(len(D.ids), bool), 'account', False))
    variants.append(('S8 machine clusters', prim, base, keep, 'machine', False))
    for name, pop, pres, kp, cl, admin in variants:
        print(f'  {name}')
        cc = Core(D, P, E, name, pop, pres, kp, cluster=cl, admin=admin, h2b=admin)
        for k in (K7, K30):
            r = cc.results[('row', k)]
            if admin:
                hb = cc.results[('h2b', k)]
                r.update(h2b=hb['obs']['pooled'], h2b_lo=hb['lo'], h2b_hi=hb['hi'], h2b_perm_p=hb['p'])
            rows.append(r)
    # S9: ticket side only
    for name, pop in (('S9 usable unplanned, ticket side', P['s9']), ('S9 first ticket of each D5 episode', P['s9_ep'])):
        for k in (K7, K30):
            sel = pop & ~(WT.undetermined(k) if k <= K7 else np.zeros(len(D.ids), bool))
            MB = D.bucket_mask(BUCKET_FAMILY)
            pT = WT.present(k, MB)[sel].mean(0)
            r = dict(variant=name, k=k, n_pairs=int(sel.sum()), h2a='n/a', h1='n/a')
            for o, v in zip(BUCKET_FAMILY, pT):
                r[f'bucket:{o}:pT'] = v
            rows.append(r)
    # S1, Cancelled request only (docs/07 §6: "A separate Cancelled request row tests 'faults that cleared on their
    # own'"). Administrative, no code set: H2a and H1 n/a. Item 2 bucket table with machine clusters, as in item2().
    MBs = D.bucket_mask(BUCKET_FAMILY)
    for k in (K7, K30):
        m = P['lifted'] & (D.service_group == 'Cancelled request') & keep(k)
        rb = enrich(WT.present(k, MBs)[m], WC.present(k, MBs)[m], Boot(D.mid[m]), list(BUCKET_FAMILY), with_ci=True)
        r = dict(variant='S1 Cancelled request only', k=k, n_pairs=int(m.sum()), n_clusters=len(set(D.mid[m])),
                 h2a='n/a', h1='n/a')
        for _, x in rb.iterrows():
            for f in ('pT', 'pC', 'mor', 'mor_lo', 'mor_hi', 'rd', 'durkalski_p'):
                r[f'bucket:{x.outcome}:{f}'] = x[f]
        rows.append(r)
    check('S1 Cancelled request pairs 7d', 89, int((P['lifted'] & (D.service_group == 'Cancelled request') & det7).sum()))
    # S13 (docs/07 §4, §6, §14.7): Deposit Door's set without 19 and 78; A10 recomputed; Improper Use joins K
    old = '19|20|78|79|80'
    D13 = copy.copy(D)  # shallow: windows shared; crosswalk maps replaced, D untouched
    D13.cat_set = {c: (S13_SET if x == old else x) for c, x in D.cat_set.items()}
    D13.target = np.array([S13_SET if t == old else t for t in D.target], dtype=object)
    D13.sets = sorted(set(v for v in D13.cat_set.values() if v))
    E13, _ = emit_matrix(D13, D13.sets)
    print('  S13 Deposit Door without 19 and 78')
    cc = Core(D13, P, E13, 'S13 Deposit Door without 19 and 78', prim, base, keep)
    j13 = D13.sets.index(S13_SET)
    for k in (K7, K30):
        r, R = cc.results[('row', k)], cc.results[('h2a', k)]
        o = R['obs']
        bT, cT, bK, cK = o['parts']
        lo, hi, und = ci(R['reps'][False][0][:, j13])
        r.update(dd_set=S13_SET, dd_entered=int(o['enter'][j13]), dd_n_T=int(o['T'][:, j13].sum()),
                 dd_n_K=int(o['K'][:, j13].sum()), dd_b_T=int(bT[:, j13].sum()), dd_c_T=int(cT[:, j13].sum()),
                 dd_b_K=int(bK[:, j13].sum()), dd_c_K=int(cK[:, j13].sum()), dd_h2a=float(o['per'][j13]),
                 dd_h2a_lo=lo, dd_h2a_hi=hi, dd_h2a_undefined_reps=und)
        rows.append(r)
    # S11: time trend across control windows
    for k in (K7, K30):
        sel = prim & keep(k)
        days = (pd.Series(D.A[sel]) - pd.Timedelta(days=35) - pd.Timestamp('2025-08-01')).dt.total_seconds().to_numpy() / 86400
        MB = D.bucket_mask(BUCKET_FAMILY)
        XC = WC.present(k, MB)[sel].astype(float)
        r = dict(variant='S11 time trend: slope x 35 d across control windows', k=k, n_pairs=int(sel.sum()))
        for j, o in enumerate(BUCKET_FAMILY):
            slope = np.polyfit(days, XC[:, j], 1)[0]
            r[f'bucket:{o}:trend_bias_35d'] = slope * 35
        h = core.results[('h1', k)]
        ii = np.flatnonzero(h['pop'])
        dd = (pd.Series(D.A[ii]) - pd.Timedelta(days=35) - pd.Timestamp('2025-08-01')).dt.total_seconds().to_numpy() / 86400
        xc = WC.present(k, D.set_mask(D.sets))[ii, h['own'][ii]].astype(float)
        r['target:trend_bias_35d'] = np.polyfit(dd, xc, 1)[0] * 35
        rows.append(r)
    flags_ok = FLAGS.exists() and (FLAGS.parent / 'flags_by_case.meta.json').exists()
    for name in ('S2 text flags', 'S10 interval-based clean rule'):
        rows.append(dict(variant=name, k=np.nan, status='computed' if flags_ok else 'pending local flag export'))
    if flags_ok:
        rows.extend(text_flag_rows(D, P, E, base, keep))
    rows.append(dict(variant='S12 crosswalk v1', k=np.nan, status='pending v1 (IPA code definitions)'))
    rows.append(dict(variant='S13 Deposit Door without 19 and 78', k=np.nan,
                     status='computed above (dd_* columns); also as_negative_controls.csv'))
    return pd.DataFrame(rows)


def text_flag_rows(D, P, E, base, keep):
    fl = read(FLAGS).set_index('case_id')
    meta = json.loads((FLAGS.parent / 'flags_by_case.meta.json').read_text())
    check('flags export covers every fu ticket', True, set(D.ids) <= set(fl.index))
    check('flags export built from the committed workbook', common.ZAC_WORKBOOK_SHA256, meta.get('workbook_sha256'))
    rows = []
    cols = [c for c in fl.columns if c != 'closed_at_eastern']
    flagged = {c: np.array([fl[c].get(i, 'False') == 'True' for i in D.ids]) for c in cols}
    flagged['any flag'] = np.any(np.column_stack(list(flagged.values())), axis=1)
    for c, f in flagged.items():
        cc = Core(D, P, E, f'S2 without {c}', P['primary'] & ~f, base, keep)
        for k in (K7, K30):
            rows.append(cc.results[('row', k)])
    return rows


def durk_mcnemar_check():
    """Durkalski equals McNemar's chi-square when every cluster holds one pair."""
    rng = np.random.default_rng(1)
    b = rng.integers(0, 2, 200)
    c = (1 - b) * rng.integers(0, 2, 200)
    p = durkalski(b.astype(float), c.astype(float), np.arange(200), 200)
    B, C = b.sum(), c.sum()
    p_mc = math.erfc(math.sqrt(((B - C) ** 2 / (B + C)) / 2))
    check('Durkalski = McNemar with one pair per cluster', True, bool(abs(p - p_mc) < 1e-12))


def privacy():
    allowed = re.compile(r'^(?:[TMS]\d{5}|20(?:25|26)|30462084)$')
    bad = 0
    for name, df in PUBLIC.items():
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                continue
            for v in df[col].dropna().unique():
                if isinstance(v, (int, float, np.number, np.bool_, bool)):
                    continue  # a number in a mixed column (e.g. 'n/a' beside estimates), not text
                for tok in re.findall(r'[A-Za-z]*\d{4,}', str(v)):
                    if not allowed.match(tok) and not re.fullmatch(r'20(?:25|26)Q[1-4]', tok):
                        bad += 1
    check('privacy: no unexpected 4+-digit token in any text column', 0, bad)
    if common.XLS.exists():
        import high_ticket_machines as H
        raw = common.load_raw()
        maps = common.build_maps(raw)
        real = (set(map(str, maps['serial'])) | set(map(str, maps['account'])) | set(map(str, maps['case']))) - {'None', ''}
        leaks = sum(len(H.text_leaks(df, real)) for df in PUBLIC.values())
        check('privacy: no real serial / account / case number in any text column', 0, leaks)
    else:
        print('  (raw workbook not present: real-identifier scan skipped)')


if __name__ == '__main__':
    sys.exit(main())
