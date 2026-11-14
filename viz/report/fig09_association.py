#!/usr/bin/env python3
"""Report figure 9 (Results, Association results): the odds that a ticket's own codes appear in its final 7 days
rather than in its comparison window's final 7 days are 3.2 times those of other faults' tickets (95% interval
2.3-4.8); by code set the ratios are rough and do not rank the four sets with ratios above 1, Main Door is borderline,
and Computer Board was not shown to be specific; at 7 days the pooled result holds in every sensitivity check run so
far that gives one, but it rests almost entirely on scrubex machines and is provisional.

(a) The pooled ratio (cobalt diamond) and the ratio of each of the five code sets it pools (grey), with 95% bootstrap
    intervals over account clusters, on a log axis with a dashed line at 1. Main Door's interval starts at 1.01 (the
    Definitions' number, labelled), and Computer Board's crosses the line.
(b) The pooled 7-day ratio under each sensitivity check that gives one (13 rows of as_sensitivities.csv), as anonymous
    points in rising order with their 95% intervals (machine clusters for one check), all above the line at 1. The
    points are the checks' variants (8 numbered checks: S3, S5 and S7 give more than one), so the axis says so. The
    lowest and highest ratios, 2.33 and 3.55, are the Definitions' range.
The caption states that the pooled result rests almost entirely on scrubex machines (checked against the Definitions:
1,402 of the 1,439 tickets whose code set their type logs, 97%) and is provisional (crosswalk v1, check S12, pending).

The numbers are recomputed as notebook 06 recomputes them: the paired tickets and their windows from
fu/fu_ticket_last10.csv, machine types and activity from fu/fu_devices.csv (read without its customer columns), each
ticket's own code set from its Category, the 7-day specificity counts and Mantel-Haenszel ratios, and each sensitivity
check's pooled ratio, all asserted equal to the script's tables. The intervals come from as_h2a.csv and
as_sensitivities.csv; the pooled and per-set intervals are also replayed from the script's bootstrap seed, which fixes
their level (95%). Crosswalk v0 maps each mapped Category to its own code set, so the Category-to-set map is read from
as_h2a.csv's set and categories columns (the notebook reads it from verification/reference/, outside the outputs) and
checked against as_pairs.csv's code set for every paired ticket and against the pinned count of mapped tickets.

Inputs: verification/outputs/fu/fu_ticket_last10.csv, fu/fu_devices.csv, db/db_codes_buckets.csv,
assoc/as_pairs.csv (its cluster column gives the account clusters for the bootstrap replay; never printed),
assoc/as_h2a.csv, as_sensitivities.csv, as_by_type.csv, as_summary.json, htm_device_exposure.csv and
fleet/fx_machine_flags.csv (install years, for one check). Notebook 06 checks the same numbers.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import NullLocator  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig09_association'
LABEL = 'fig:association'
SHORT = 'Association results'

TICKET, COMPARISON = 'corrected_guard0', 'control_minus35d'
NOT_UNPLANNED = ['Planned work', 'Cancelled request', 'Duplicate case']
K_LIST = 720.0                # 30 days, in hours: there the outcome is membership of the last-10 list
HISTORY_START = pd.Timestamp('2025-08-01 04:00')   # the case history begins Aug 1st, 2025, 00:00 US Eastern (UTC)
DEPOSIT_DOOR, DEPOSIT_DOOR_S13 = '19|20|78|79|80', '20|79|80'   # check S13: without codes 19 and 78
ROUGH = 4                     # notebook 06: a ratio is rough when its interval's high end is over 4 times its low end
WINDOW_COLS = ['case_id', 'machine_id', 'opened_at_eastern', 'anchor_utc', 'service_group', 'category',
               'lookback_truncated', 'after_telemetry_end', 'window', 'control_clean', 'distinct_codes',
               'last10_distinct', 'last10_distinct_hours_before', 'last10_distinct_occurrences']
DEVICE_COLS = ['machine_id', 'machine_type', 'first_active', 'last_active', 'transacting']


def read_text(name, **kw):
    """A table from the outputs with every field as text, as association.py reads it (codes keep their 0s)."""
    return pd.read_csv(S.OUT / name, dtype=str, keep_default_na=False, **kw)


def flag(column):
    return column.to_numpy() == 'True'


def ratio(num, den):
    """docs/07 A13: num/den; +inf when only the denominator is 0; NaN when both are."""
    num, den = np.asarray(num, float), np.asarray(den, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(den > 0, num / np.where(den > 0, den, 1), np.where(num > 0, np.inf, np.nan))


def in_words(n):
    """A count as the report spells it: 4 -> 'four' (digits from 10 up)."""
    return 'zero one two three four five six seven eight nine'.split()[n] if 0 <= n < 10 else S.num(n)


class Window:
    """One window per ticket as arrays (notebook 06): each listed code's hours before the window's end (inf when not
    listed) and its occurrences in the window."""

    def __init__(self, d, col):
        self.H = np.full((len(d), len(col)), np.inf)
        self.O = np.zeros((len(d), len(col)))
        self.distinct = d.distinct_codes.astype(int).to_numpy()
        self.last = np.full(len(d), np.inf)  # hours of the last listed code (the 10th when the list is full)
        for i, (cs, hs, occ) in enumerate(zip(d.last10_distinct, d.last10_distinct_hours_before,
                                              d.last10_distinct_occurrences)):
            if cs:
                hours = [float(x) for x in hs.split('|')]
                for c, hr, oc in zip(cs.split('|'), hours, occ.split('|')):
                    self.H[i, col[c]], self.O[i, col[c]] = hr, float(oc)
                self.last[i] = hours[-1]

    def undetermined(self, k):
        """docs/07 A8: a full list whose 10th code lies within k cannot show whether an unlisted code did too."""
        return (self.distinct > 10) & (self.last < k) if k < K_LIST else np.zeros(len(self.distinct), bool)

    def present(self, k, mask):
        """(tickets x sets): a code of the set is listed with hours below k."""
        listed = (self.H < k) if k < K_LIST else np.isfinite(self.H)
        return (listed.astype(float) @ mask.astype(float)) > 0


class Specificity:
    """docs/07 §4 on the pairs in `sel` (notebook 06): own tickets T and comparator tickets K on machine types that
    log the set; b = the set only in the final k before the ticket, c = only in the comparison window's final k;
    Mantel-Haenszel within machine type x quarter, pooled over the sets that enter."""

    def __init__(self, stratum, sel, xt, xc, able, sets, target):
        self.sets = sets
        codes_of = [set(s.split('|')) for s in sets]
        self.disjoint = np.array([[not (a & b) for b in codes_of] for a in codes_of])
        self.keys = np.unique(stratum[sel])
        self.h = np.searchsorted(self.keys, stratum[sel])
        self.b, self.c = (xt & ~xc)[sel], (~xt & xc)[sel]
        self.able = able[sel]
        self.g = np.array([sets.index(t) if t else -1 for t in target[sel]])

    def stat(self):
        g, n_sets = self.g, len(self.sets)
        T = (g[:, None] == np.arange(n_sets)) & self.able
        K = (g >= 0)[:, None] & self.disjoint[np.maximum(g, 0)] & self.able
        bT, cT, bK, cK = (np.stack([np.bincount(self.h, weights=x[:, j], minlength=len(self.keys))
                                    for j in range(n_sets)], 1)
                          for x in (self.b & T, self.c & T, self.b & K, self.c & K))  # strata x sets
        n = bT + cT + bK + cK
        with np.errstate(divide='ignore', invalid='ignore'):
            num = np.where(n > 0, bT * cK / np.where(n > 0, n, 1), 0.0).sum(0)
            den = np.where(n > 0, cT * bK / np.where(n > 0, n, 1), 0.0).sum(0)
        enter = ((bT + cT).sum(0) >= 10) & (num > 0) & (den > 0)
        pooled = num[enter].sum() / den[enter].sum() if enter.any() else 0.0
        return dict(T=T, K=K, b_T=bT.sum(0), c_T=cT.sum(0), b_K=bK.sum(0), c_K=cK.sum(0), num=num, den=den,
                    enter=enter, ratio=ratio(num, den), pooled=pooled)


def recompute():
    """Notebook 06's recomputation of the 7-day association results from the committed outputs."""
    summary = json.loads((S.OUT / 'assoc' / 'as_summary.json').read_text())
    pins = summary['pinned_counts']
    h2a = pd.read_csv(S.OUT / 'assoc' / 'as_h2a.csv')
    k7 = float(h2a.loc[h2a.perm_p_role == 'decision', 'k'].item())   # the deciding row's look-back, hours
    h7 = h2a[h2a.k == k7].set_index('set')

    # The paired tickets and their four windows
    windows = read_text('fu/fu_ticket_last10.csv', usecols=WINDOW_COLS)
    win = {w: d.set_index('case_id').sort_index() for w, d in windows.groupby('window')}
    t0, c0 = win[TICKET], win[COMPARISON]
    S.check('fig09 the four windows list the same tickets', 1, int(all(d.index.equals(t0.index) for d in win.values())))
    ids = t0.index.to_numpy()
    unplanned = ~t0.service_group.isin(NOT_UNPLANNED).to_numpy()
    complete = (~flag(t0.lookback_truncated) & ~flag(t0.after_telemetry_end)
                & ~flag(c0.lookback_truncated) & ~flag(c0.after_telemetry_end))
    clean = flag(c0.control_clean)
    paired = unplanned & complete & clean
    pairs = read_text('assoc/as_pairs.csv').set_index('case_id')
    S.check('fig09 paired tickets = as_pairs.csv\'s', 1,
            int(set(ids[paired]) == set(pairs.index[pairs.in_paired == '1'])))

    codes_table = read_text('db/db_codes_buckets.csv')
    codes = sorted(set(codes_table.transaction_code) | {c for d in win.values() for s in d.last10_distinct
                                                        for c in s.split('|') if c}, key=lambda c: (len(c), c))
    col = {c: j for j, c in enumerate(codes)}
    W = {w: Window(d, col) for w, d in win.items()}
    WT, WC = W[TICKET], W[COMPARISON]

    # Machine type (A5), quarter (A6) and stratum
    devices = read_text('fu/fu_devices.csv', usecols=DEVICE_COLS).set_index('machine_id')
    mid = t0.machine_id.to_numpy()
    mtype = np.array([re.sub(r'^package name:\s*', '', devices.machine_type.get(m, '').strip().lower()) or 'Unknown'
                      for m in mid], dtype=object)
    quarter = pd.to_datetime(t0.opened_at_eastern).dt.to_period('Q').astype(str).to_numpy()
    stratum = np.array([f'{t}|{q}' for t, q in zip(mtype, quarter)], dtype=object)

    # Each ticket's own code set from its Category (crosswalk v0: one Category per set, read from as_h2a.csv)
    set_rows = h7.drop('POOLED')
    cat_set = dict(zip(set_rows.categories, set_rows.index))
    S.check('fig09 one Category per code set', len(set_rows), len(cat_set))
    S.check('fig09 mapped Categories = the pinned count', pins['xw mapped Categories'], len(cat_set))
    target = np.array([cat_set.get(c, '') if c else '' for c in t0.category], dtype=object)
    S.check('fig09 tickets with a mapped Category = the pinned count', pins['xw mapped matched tickets'],
            int((target != '').sum()))
    sets = sorted(cat_set.values())
    set_name = {s: n for n, s in cat_set.items()}

    def set_mask(sets_):
        M = np.zeros((len(codes), len(sets_)), bool)
        for j, s in enumerate(sets_):
            M[[col[c] for c in s.split('|')], j] = True
        return M

    # The main group (A3) and the pairs determined at 7 days (A8)
    A = pd.to_datetime(t0.anchor_utc).to_numpy()  # ticket creation time, UTC

    def other_ticket(lo_days, hi_days):
        """Per ticket: another ticket on the same machine was opened in [A - lo_days, A - hi_days)."""
        out = np.zeros(len(ids), bool)
        for _, g in pd.Series(A, index=np.arange(len(ids))).groupby(mid):
            a = np.sort(g.to_numpy())
            lo = np.searchsorted(a, g.to_numpy() - np.timedelta64(lo_days, 'D'))
            hi = np.searchsorted(a, g.to_numpy() - np.timedelta64(hi_days, 'D'))
            out[g.index.to_numpy()] = hi > lo
        return out

    def device_day(column):
        return pd.to_datetime(pd.Series([devices[column].get(m, '') for m in mid]), errors='coerce').to_numpy()

    first_active, last_active = device_day('first_active'), device_day('last_active')
    transacting = np.array([devices.transacting.get(m, '') == 'True' for m in mid])
    window_first_day = (pd.Series(A) - pd.Timedelta(days=30)).dt.normalize().to_numpy()
    outside_span = ~transacting | (~pd.isna(last_active) & (last_active < window_first_day))
    recent = other_ticket(5, 0)
    primary = paired & ~recent & ~outside_span
    det7 = ~(WT.undetermined(k7) | WC.undetermined(k7))
    sel7 = primary & det7

    def able_to_emit(sets_):
        """docs/07 A10: at least 5 other machines of the ticket's type show a code of the set in a clean, complete
        comparison window. Unknown type never does."""
        ok = flag(c0.control_clean) & ~flag(c0.lookback_truncated)
        shows = pd.DataFrame(WC.present(K_LIST, set_mask(sets_))[ok], columns=sets_).groupby(mid[ok]).any()
        type_of = pd.Series(mtype[ok], index=mid[ok]).groupby(level=0).first()
        machines = shows.groupby(type_of.reindex(shows.index).to_numpy()).sum()
        able = np.zeros((len(ids), len(sets_)), bool)
        for j, s in enumerate(sets_):
            others = (np.array([machines[s].get(t, 0) for t in mtype])
                      - np.array([bool(shows[s].get(m, False)) for m in mid]))
            able[:, j] = (mtype != 'Unknown') & (others >= 5)
        return able

    E = able_to_emit(sets)
    own = np.array([sets.index(t) if t else -1 for t in target])
    h1 = sel7 & (own >= 0) & np.array([E[i, j] if j >= 0 else False for i, j in enumerate(own)])
    script_pairs = pairs.loc[ids[paired]]
    S.check('fig09 main group = as_pairs.csv\'s', 0,
            int((script_pairs.in_primary.astype(int).to_numpy() != primary[paired]).sum()))
    S.check('fig09 pairs determined at 7 days = as_pairs.csv\'s', 0,
            int((script_pairs.determined_7d.astype(int).to_numpy() != det7[paired]).sum()))
    S.check('fig09 type, quarter and code set = as_pairs.csv\'s', 0,
            int((~((script_pairs.type == mtype[paired]) & (script_pairs.quarter == quarter[paired])
                   & (script_pairs.target_codes == target[paired]))).sum()))
    for pin, value in (('A2 paired tickets', paired.sum()), ('A3 primary tickets', primary.sum()),
                       ('A8 determined pairs 7d', sel7.sum()), ('H1 population 7d', h1.sum())):
        S.check(f'fig09 {pin} = the pinned count', pins[pin], int(value))

    # The 7-day specificity counts and ratios
    MS = set_mask(sets)
    xt7, xc7 = WT.present(k7, MS), WC.present(k7, MS)

    def spec(sel, xt, xc, able=E, sets_=sets, target_=target):
        return Specificity(stratum, sel, xt, xc, able, sets_, target_)

    spec7 = spec(sel7, xt7, xc7)
    obs = spec7.stat()
    entering = obs['enter']
    table_cols = ['n_T', 'n_K', 'b_T', 'c_T', 'b_K', 'c_K', 'entered']
    mine = np.c_[obs['T'].sum(0), obs['K'].sum(0), obs['b_T'], obs['c_T'], obs['b_K'], obs['c_K'], entering]
    S.check('fig09 per-set counts = as_h2a.csv', 0, int((mine != h7.loc[sets, table_cols].to_numpy()).sum()))
    S.check('fig09 per-set ratios = as_h2a.csv', 1, int(np.allclose(
        obs['ratio'], np.exp(h7.loc[sets, 'estimate'].astype(float)), equal_nan=True)))
    S.check('fig09 pooled ratio = as_h2a.csv', float(np.exp(h7.loc['POOLED', 'estimate'])), obs['pooled'], 1e-12)

    # The look-backs, in whole days, at which each window gives the deciding row's counts (notebook 06)
    def lookback_days(which):
        found = []
        for day in range(1, 31):
            x = W[which].present(24.0 * day, MS)
            xt, xc = (x, xc7) if which == TICKET else (xt7, x)
            st = spec(sel7, xt, xc).stat()
            if all((st[c] == h7.loc[sets, c].to_numpy()).all() for c in ('b_T', 'c_T', 'b_K', 'c_K')):
                found.append(day)
        return found

    # Bootstrap replay with the script's seed: the level whose percentile interval equals as_h2a.csv's
    cluster7 = pairs.cluster.loc[ids[sel7]].to_numpy()   # account clusters (A11), as the script assigns them
    clusters = np.array(sorted(set(cluster7)), dtype=object)
    S.check('fig09 account clusters at 7 days = the pinned count', pins['A8 clusters 7d'], len(clusters))
    cl = np.searchsorted(clusters, cluster7)
    n_boot, n_cl, n_sets, n_strata = summary['n_boot'], len(clusters), len(sets), len(spec7.keys)
    cell = spec7.h[:, None] * n_sets + np.arange(n_sets)

    def cluster_sums(x):
        M = np.zeros((n_cl, n_strata * n_sets))
        np.add.at(M, (np.repeat(cl, n_sets), cell.ravel()), x.astype(float).ravel())
        return M

    parts = [cluster_sums(x) for x in (spec7.b & obs['T'], spec7.c & obs['T'], spec7.b & obs['K'],
                                       spec7.c & obs['K'])]
    weights = np.random.default_rng(summary['seed']).multinomial(n_cl, np.full(n_cl, 1 / n_cl), size=n_boot)
    rbT, rcT, rbK, rcK = ((weights.astype(float) @ M).reshape(n_boot, n_strata, n_sets) for M in parts)
    rn = rbT + rcT + rbK + rcK
    with np.errstate(divide='ignore', invalid='ignore'):
        rnum = np.where(rn > 0, rbT * rcK / np.where(rn > 0, rn, 1), 0.0).sum(1)
        rden = np.where(rn > 0, rcT * rbK / np.where(rn > 0, rn, 1), 0.0).sum(1)
    boot_pooled, boot_sets = ratio(rnum[:, entering].sum(1), rden[:, entering].sum(1)), ratio(rnum, rden)
    lo, hi = np.exp(h7.loc['POOLED', ['ci_lo', 'ci_hi']].astype(float))
    tails = [t for t in (i / 4 for i in range(1, 101))
             if np.allclose(np.nanpercentile(boot_pooled, [t, 100 - t], method='inverted_cdf'), [lo, hi], rtol=1e-9)]
    S.check('fig09 exactly one level of the replayed bootstrap gives as_h2a.csv\'s interval', 1, len(tails))
    tail = tails[0] if tails else float('nan')

    # Each set that enters: ratio, interval (as_h2a.csv, replayed), permutation p, and the notebook's verdict
    by_set = []
    for j, s in enumerate(sets):
        if not entering[j]:
            continue
        r = h7.loc[s]
        low, high = float(np.exp(r.ci_lo)), float(np.exp(r.ci_hi))
        replay = np.nanpercentile(boot_sets[:, j], [tail, 100 - tail], method='inverted_cdf')
        S.check(f'fig09 {set_name[s]}: interval = the replayed bootstrap', 1,
                int(np.allclose(replay, [low, high], rtol=1e-9)))
        above, small = low > 1, float(r.perm_p) <= 0.05
        verdict = 'clear' if above and small else 'borderline' if above or small else 'not shown to be specific'
        by_set.append(dict(name=set_name[s], ratio=float(obs['ratio'][j]), low=low, high=high, p=float(r.perm_p),
                           verdict=verdict))
    by_set = pd.DataFrame(by_set).set_index('name').sort_values('ratio', ascending=False)

    # Sensitivity checks (notebook 06): each check's pooled 7-day ratio, recomputed
    sens = pd.read_csv(S.OUT / 'assoc' / 'as_sensitivities.csv')
    uT, uC = WT.undetermined(k7), WC.undetermined(k7)
    lead_in = other_ticket(102, 67)
    s4 = primary & ~lead_in & ((pd.Series(A) - pd.Timedelta(days=102)).to_numpy() >= HISTORY_START.to_datetime64())
    s5_drop = (~pd.isna(first_active) & (first_active > np.datetime64('2025-08-01'))
               & ((pd.Series(A) - pd.Timedelta(days=65)).to_numpy() < first_active + np.timedelta64(90, 'D')))
    serial_of = dict(pd.read_csv(S.OUT / 'htm_device_exposure.csv', usecols=['machine_id', 'serial_id']).to_numpy())
    install_year = dict(pd.read_csv(S.OUT / 'fleet' / 'fx_machine_flags.csv',
                                    usecols=['serial_id', 'install_year']).to_numpy())
    year = np.array([install_year.get(serial_of.get(m), np.nan) for m in mid], float)
    lifted = complete & clean & ~recent & ~outside_span            # planned, canceled and duplicate tickets back
    truncated_ok = (unplanned & ~flag(t0.after_telemetry_end) & ~flag(c0.after_telemetry_end) & clean & ~recent
                    & ~outside_span)                               # lookback-truncated windows included

    def guarded_control(g):
        """S3: the comparison window without codes under g hours, as a lower and an upper bound."""
        present = (((WC.H >= g) & (WC.H < k7)).astype(float) @ MS.astype(float)) > 0
        dropped_repeat = (((WC.H < g) & (WC.O > 1)).astype(float) @ MS.astype(float)) > 0
        unknown = ~present & (dropped_repeat | uC[:, None])
        return present, present | unknown

    variants = {'S1 planned/cancelled/duplicate put back': (lifted & det7, xt7, xc7)}
    for w, g in (('corrected_guard30', 0.5), ('corrected_guard60', 1.0)):
        low_c, high_c = guarded_control(g)
        keep = primary & det7 & ~W[w].undetermined(k7)
        variants[f'S3 guard {g:g} h, control lower bound'] = (keep, W[w].present(k7, MS), low_c)
        variants[f'S3 guard {g:g} h, control upper bound'] = (keep, W[w].present(k7, MS), high_c)
    variants.update({
        'S4 ticket-free lead-in (A >= 11 Nov 2025)': (s4 & det7, xt7, xc7),
        'S5 recently activated machines dropped': (primary & ~s5_drop & det7, xt7, xc7),
        'S5b installed 2025 or later dropped': (primary & ~(year >= 2025) & det7, xt7, xc7),
        'S6 lookback-truncated windows included': (truncated_ok & det7, xt7, xc7),
        'S7 undetermined pairs counted absent': (primary, xt7, xc7),
        'S7 undetermined pairs counted present': (primary, xt7 | uT[:, None], xc7 | uC[:, None]),
        'S8 machine clusters': (sel7, xt7, xc7),
    })
    recomputed = {v: (int(sel.sum()), spec(sel, xt, xc).stat()['pooled']) for v, (sel, xt, xc) in variants.items()}
    sets13 = sorted({DEPOSIT_DOOR_S13 if s == DEPOSIT_DOOR else s for s in sets})
    target13 = np.array([DEPOSIT_DOOR_S13 if t == DEPOSIT_DOOR else t for t in target], dtype=object)
    MS13 = set_mask(sets13)
    recomputed['S13 Deposit Door without 19 and 78'] = (int(sel7.sum()), spec(
        sel7, WT.present(k7, MS13), WC.present(k7, MS13), able_to_emit(sets13), sets13, target13).stat()['pooled'])

    rows = sens[sens.h2a.notna() & (sens.variant != 'primary')].copy()
    rows[['ratio', 'low', 'high']] = np.exp(rows[['h2a', 'h2a_lo', 'h2a_hi']].astype(float).to_numpy())
    rows['holds'] = (rows.ratio > 1) & (rows.low > 1) & (rows.h2a_perm_p <= 0.05)
    checks = rows[rows.k == k7].set_index('variant')
    S.check('fig09 every check with a 7-day pooled ratio is recomputed', 1, int(set(checks.index) == set(recomputed)))
    S.check('fig09 checks: pairs = as_sensitivities.csv', 0,
            int(sum(recomputed[v][0] != int(checks.n_pairs[v]) for v in checks.index)))
    S.check('fig09 checks: pooled ratios = as_sensitivities.csv', 0,
            float(max(abs(recomputed[v][1] - checks.ratio[v]) for v in checks.index)), 1e-9)
    holds_at = {k: bool(d.holds.all()) for k, d in rows.groupby('k')}
    s12 = sens.loc[sens.variant.str.startswith('S12'), 'status'].item()

    # The tickets whose own code set their type logs (H1), by machine family
    family = pd.Series(mtype).str.extract(r'^([a-z]+)', expand=False).fillna('Unknown').to_numpy()
    by_type = pd.read_csv(S.OUT / 'assoc' / 'as_by_type.csv')
    by_type = by_type[(by_type.k == k7) & (by_type.set == 'own set')
                      & (by_type.scope == 'emitting types (H1 population)')]
    n_scrubex = int((h1 & (family == 'scrubex')).sum())
    S.check('fig09 H1 tickets = as_by_type.csv', int(by_type.n_pairs.sum()), int(h1.sum()))
    S.check('fig09 H1 tickets on scrubex machines = as_by_type.csv',
            int(by_type.n_pairs[by_type.type.str.startswith('scrubex')].sum()), n_scrubex)

    return dict(k7=k7, pooled=obs['pooled'], lo=lo, hi=hi, level=1 - 2 * tail / 100, by_set=by_set,
                n_entering=int(entering.sum()), ticket_days=lookback_days(TICKET),
                comparison_days=lookback_days(COMPARISON), checks=checks.sort_values('ratio'), holds_at=holds_at,
                n_h1=int(h1.sum()), n_scrubex=n_scrubex, s12=s12)


def listed(items, conj='and'):
    items = [str(i) for i in items]
    return f' {conj} '.join(items) if len(items) <= 2 else ', '.join(items[:-1]) + f', {conj} ' + items[-1]


def plot(out_dir=S.FIG_DIR):
    r = recompute()
    by_set, checks = r['by_set'], r['checks']
    md, cb = by_set.loc['Main Door'], by_set.loc['Computer Board']
    above_one = by_set[by_set.ratio > 1]
    apart = [(a, b) for a in above_one.index for b in above_one.index
             if above_one.high[a] < above_one.low[b]]          # a's interval wholly below b's
    rank = f"{'rank some of' if apart else 'do not rank'} the {in_words(len(above_one))} sets with ratios above 1"
    rough = 'rough' if (by_set.high / by_set.low > ROUGH).all() else 'not all rough'
    days_all_hold = [k / 24 for k, ok in sorted(r['holds_at'].items()) if ok]
    n_hold, n_checks = int(checks.holds.sum()), len(checks)
    status = 'provisional' if r['s12'].startswith('pending') else 'confirmatory'

    S.report_check('fig09 final days before the ticket (the deciding counts)', '7',
                   listed(S.num(d) for d in r['ticket_days']) or 'none')
    S.report_check('fig09 final days of the comparison window (the deciding counts)', '7',
                   listed(S.num(d) for d in r['comparison_days']) or 'none')
    S.report_check('fig09 pooled ratio', '3.2', S.num(r['pooled'], 1))
    S.report_check('fig09 interval level', '95%', S.pct(r['level']))
    S.report_check('fig09 pooled interval', '2.3–4.8', S.span(r['lo'], r['hi'], 1))
    S.report_check('fig09 by code set', 'rough', rough)
    S.report_check('fig09 ranking of the sets with ratios above 1', 'do not rank the four sets with ratios above 1',
                   rank)
    S.report_check('fig09 Main Door', 'borderline', md.verdict)
    S.report_check('fig09 Computer Board', 'not shown to be specific', cb.verdict)
    S.report_check('fig09 look-back at which every sensitivity check holds (days)', '7',
                   listed(S.num(d) for d in days_all_hold))
    S.report_check('fig09 sensitivity checks with a pooled ratio in which it holds', 'every',
                   'every' if n_hold == n_checks else f'{n_hold} of {n_checks}')
    S.report_check('fig09 status of the results', 'provisional', status)
    # The Definitions' numbers that the figure draws or the caption relies on
    S.report_check('fig09 sets pooled (Definitions)', 'five', in_words(r['n_entering']))
    S.report_check('fig09 Main Door: low end of its interval (Definitions)', '1.01', S.num(md.low, 2))
    S.report_check('fig09 Computer Board: its interval (Definitions)', 'includes 1',
                   'includes 1' if cb.low <= 1 <= cb.high else 'excludes 1')
    S.report_check('fig09 range of the pooled ratio over the checks (Definitions)', '2.33–3.55',
                   S.span(checks.ratio.min(), checks.ratio.max(), 2))
    S.report_check('fig09 tickets on scrubex machines (Definitions)', '1,402', S.num(r['n_scrubex']))
    S.report_check('fig09 tickets whose code set their type logs (Definitions)', '1,439', S.num(r['n_h1']))
    S.report_check('fig09 share on scrubex machines (Definitions)', '97%', S.pct(r['n_scrubex'] / r['n_h1']))
    S.check('fig09 every check\'s interval lies above 1', 1, int((checks.low > 1).all()))

    fig, (ax, bx) = S.figure(2.1, ncols=2, width_ratios=[1.3, 1])
    dashed = dict(color=S.GREY_DARK, lw=0.8, ls=(0, (4, 2.5)), zorder=2)

    # (a) the pooled ratio and each code set's ratio, with 95% intervals, on a log axis
    ys = [0.0] + [1.4 + i for i in range(len(by_set))]
    ax.axvline(1, **dashed)
    ax.hlines(ys[0], r['lo'], r['hi'], color=S.COBALT, lw=1.3, zorder=3)
    ax.plot(r['pooled'], ys[0], 'D', color=S.COBALT, ms=5, zorder=4)
    for y, (name, row) in zip(ys[1:], by_set.iterrows()):
        ax.hlines(y, row.low, row.high, color=S.GREY, lw=0.9, zorder=3)
        ax.plot(row.ratio, y, 'o', color=S.GREY, ms=3.6, zorder=4)
    backing = dict(facecolor=S.WHITE, edgecolor='none', pad=0.8)   # the light grid stops behind the readout
    readout = S.label(ax, r['hi'] * 1.18, ys[0], S.num(r['pooled'], 1), size=S.FONT, weight='bold', color=S.GREEN,
                      bbox=backing)
    ax.annotate(f'({S.span(r["lo"], r["hi"], 1)})', xy=(1, 0.5), xycoords=readout, xytext=(3, 0),
                textcoords='offset points', ha='left', va='center', fontsize=S.TICK, color=S.TEXT, bbox=backing)
    S.check('fig09 (a) readout = the pooled ratio', round(r['pooled'], 1), float(S.num(r['pooled'], 1)))
    y_md = ys[1 + list(by_set.index).index('Main Door')]
    S.label(ax, 0.9, y_md, S.num(md.low, 2), ha='right')          # Main Door's interval starts at 1.01
    ax.set_xscale('log')
    ax.set_xlim(0.15, 62)
    ticks = [0.25, 0.5, 1, 2, 4, 8, 16, 32]
    ax.set_xticks(ticks, [f'{t:g}' for t in ticks])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_yticks(ys, ['Pooled'] + list(by_set.index))
    ax.set_ylim(ys[-1] + 0.6, -0.65)
    ax.set_xlabel('Odds ratio (log scale)')
    S.clean(ax, grid='x', left=False)
    S.panel(ax, 'a', 'Pooled and by code set')

    # (b) the pooled ratio under each sensitivity check that gives one: anonymous points in rising order
    xs = np.arange(n_checks)
    bx.axhline(1, **dashed)
    bx.vlines(xs, checks.low, checks.high, color=S.COBALT, lw=0.9, zorder=3)
    bx.plot(xs, checks.ratio, 'o', color=S.COBALT, ms=3.3, zorder=4)
    for x, row in ((xs[0], checks.iloc[0]), (xs[-1], checks.iloc[-1])):   # the lowest and highest ratios
        text = S.num(row.ratio, 2)
        S.check(f'fig09 (b) label {text}', round(row.ratio, 2), float(text))
        S.label(bx, x, row.high * 1.08, text, ha='center', va='bottom')
    bx.set_yscale('log')
    bx.set_ylim(0.8, 7.0)
    bx.set_yticks([1, 2, 4], ['1', '2', '4'])
    bx.yaxis.set_minor_locator(NullLocator())
    bx.set_xlim(-0.8, n_checks - 0.2)
    # at tick level, as fig11's groups. The points are variants, not checks: S3 gives four (two guard bands, each as a
    # lower and an upper bound), S5 two (its rule and its secondary check) and S7 two (counted absent or present)
    bx.set_xticks([xs.mean()], ['Check variants, in order of ratio'])
    numbered = checks.index.str.extract(r'^(S\d+)', expand=False)
    S.check('fig09 (b) every point is a variant of a numbered check, and some checks give more than one', 1,
            int(numbered.notna().all() and numbered.nunique() < n_checks))
    bx.set_ylabel('Pooled odds ratio\n(log scale)', linespacing=1.1)   # two lines: shorter than the axis
    S.clean(bx, grid='y', bottom=False)
    S.panel(bx, 'b', 'Sensitivity checks')

    # Nothing drawn is clipped: every interval inside its panel's limits
    S.check('fig09 (a) intervals inside the axis', 1,
            int(ax.get_xlim()[0] < min(by_set.low.min(), r['lo'])
                and max(by_set.high.max(), r['hi']) < ax.get_xlim()[1]))
    S.check('fig09 (b) intervals inside the axis', 1,
            int(bx.get_ylim()[0] < checks.low.min() and checks.high.max() * 1.08 < bx.get_ylim()[1]))

    S.export(fig, NAME, out_dir)
    pc = lambda share: S.pct(share).replace('%', chr(92) + '%')  # noqa: E731
    return (f'The odds that a ticket\'s own codes appear in its final {S.num(r["k7"] / 24)} days rather than in its '
            f'comparison window\'s are {S.num(r["pooled"], 1)} times those of other faults\' tickets '
            f'({pc(r["level"])} interval {S.span(r["lo"], r["hi"], 1).replace("–", "--")}), a {status} result '
            f'resting almost entirely on scrubex machines. '
            f'(a)~By code set; (b)~by check variant; {pc(r["level"])} intervals.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
