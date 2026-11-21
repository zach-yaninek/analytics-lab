#!/usr/bin/env python3
"""IPA follow-ups: request types on machines under 4 vs 4+ years (Part A) and repeat-contact pairings (Part B).

Implements docs/09_followups_protocol.md (frozen 29 Oct 2026; request types v0, sha256 88b71f3c...). docs/09 is the
specification; the notes below only point to it.

  Part A (docs/09 §4)  6,750 unplanned tickets on 8,946 listed machines (slide 4's population); under 4 = age bands
        <1, 1-2 and 2-4. A1 crude rates by type; A2 Mantel-Haenszel share and rate ratios over support models; A3
        within-model permutation tests and the gate; A4 the extra tickets split into a within-model age part, a
        model-mix part and models with no 4+ support; A5 by model and telemetry type; A6 the halves check for the
        three Categories the rule picks; sensitivities S-A1..S-A10.
  Part B (docs/09 §5)  Zac's repeat contact on the 7,186 unplanned tickets (6,665 eligible index tickets). B0 pairs
        (SQL and pandas, ticket by ticket); B1 matrices; B2 same Category by gap and the within-machine shuffle
        test; B3 pairing classes; B4 random-timing null on each machine's own window; B5 offenders by model and
        telemetry type; B6 per-type class mixes and matrices.

Inputs: --xlsx (case export), --equipment (IPA's installed-base list), --fu-dir (the committed ticket-to-device map,
verification/outputs/fu/). Outputs (--out, default verification/outputs/followups/): ag_*.csv, rp_*.csv and
followups_summary.json; pseudonyms (T#####, S#####, Customer NNN), labels and aggregates only.

Run:  cd /home/user/analytics-lab && python3 -I verification/followups.py
      [--xlsx PATH --equipment PATH --fu-dir DIR --out DIR --n-boot N --n-perm N --n-sim N --no-pins]
The pins (docs/09 §8) run first and stop the run (exit 1) on any mismatch; --no-pins skips the ones tied to the real
export (for the synthetic fixture). Deterministic: fixed seeds, stable sorts. Exit status 1 if any check fails.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import argparse  # noqa: E402
import ast  # noqa: E402
import csv  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common  # noqa: E402
import fleet_exposure as FX  # noqa: E402
import high_ticket_machines as H  # noqa: E402
from association import ci, norm_type, perm_p  # noqa: E402
from flags import monitoring_template  # noqa: E402

REF = HERE / 'reference' / 'request_types_v0.csv'
REF_HASH = '88b71f3ce487a0f9d6d2aada2e29f24e54f198ae141498ffcba278a8cca85080'
OUT_DEFAULT = common.OUTPUTS / 'followups'
SEED_BOOT, SEED_PERM, SEED_SIM, SEED_SHUFFLE = FX.SEED, 15073, 15074, 15075
N_BOOT, N_PERM, N_SIM = 2000, 2000, 1000
PERIOD_START, PERIOD_END, SPLIT = FX.PERIOD_START, FX.PERIOD_END, FX.SPLIT
MONTH_DAYS = FX.MONTH_DAYS
YOUNG_BANDS = ('<1', '1-2', '2-4')
AGE_LABELS = ('Under 4', '4+')
GROUPS = ['Door', 'Mechanical', 'Electronics', 'Network', 'Software', 'Operator error', 'Other', 'No Trouble Found',
          'Monitoring', 'Not categorised']
PRIMARY = GROUPS[:9]                 # the analysis family: every group but Not categorised (docs/09 §4)
COMPONENT = GROUPS[:7]               # groups with Categories under them
BY_TROUBLE_CODE = {'Electronics': 'Electronics', 'Network': 'Network', 'Software': 'Software',
                   'Operator Error': 'Operator error'}
BLANK = '[blank]'
NO_CAT, MONITORING, NTF = 'Not categorised', 'Monitoring', 'No Trouble Found'
MIN_SUPPORT_MONTHS = 100
MIN_EST_TICKETS, MIN_EST_ACCOUNTS = 20, 10
MIN_SHOWN_TICKETS = 30
MIN_ELIGIBLE, MIN_REPEATS = 100, 50
MIN_FLOOR_ACCOUNTS = FX.MIN_CLUSTERS
ALPHA = 0.05
N_FIXED = 3
CUTOFF_DAYS = 30
SHORT_DAYS = 7
GAP_BINS = [(0, 1, '1 day or less'), (1, 7, 'over 1 to 7 days'), (7, 30, 'over 7 to 30 days'),
            (30, 90, 'over 30 to 90 days'), (90, 180, 'over 90 to 180 days'), (180, np.inf, 'over 180 days')]
CLASS_BINS = GAP_BINS[:3]
CLASSES = ['Monitoring involved', 'No Trouble Found involved', 'Category blank', 'Same Category',
           'Same group, other Category', 'Different group']
NO_MATCH, SEVERAL, UNKNOWN = 'No device match', 'Several types', 'Unknown'
NOT_TYPES = (NO_MATCH, SEVERAL, UNKNOWN)   # telemetry-type rows that are not types: shown, never pooled or tested
NOT_ESTIMABLE_BLANK = ('share_ratio_mh', 'rate_ratio_mh', 'z_cmh', 'excess_under4_tickets', 'p_perm', 'p_mc_se',
                       'share_ratio_lo',
                       'share_ratio_hi', 'share_ratio_undefined_draws', 'rate_ratio_lo', 'rate_ratio_hi',
                       'rate_ratio_ipf')   # docs/09 §4: a type that is not estimable is reported as counts only
INSTALL_COHORTS = [(2016, 2018), (2019, 2021), (2022, 2023), (2024, 2026)]   # §12 item 7: descriptive, added after
PREFIX_A, PREFIX_B = 'ag_', 'rp_'

CHECKS = []
PUBLIC = {}
FACTS = {}
PINS_ON = {'on': True}


# ----------------------------------------------------------------------------------------------------------------
# Copied verbatim from audit_case_logic.py, which runs its whole audit when imported. main() checks both copies
# against their sources by syntax tree.
# ----------------------------------------------------------------------------------------------------------------
REPEAT_VIEW_SQL = """
WITH ordered AS (
 SELECT *,LEAD(opened_at) OVER(PARTITION BY machine_id ORDER BY opened_at,case_id) next_opened,
 LEAD(category) OVER(PARTITION BY machine_id ORDER BY opened_at,case_id) next_category
 FROM {src})
SELECT *,julianday(next_opened)-julianday(opened_at) gap_days,
 CASE WHEN julianday(next_opened)-julianday(opened_at) BETWEEN 0 AND 30 THEN 1 ELSE 0 END repeat_30,
 CASE WHEN julianday(next_opened)-julianday(opened_at) BETWEEN 0 AND 30 AND category IS NOT NULL AND category=next_category THEN 1 ELSE 0 END same_category_30
FROM ordered WHERE opened_at<'2026-08-02'
"""


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(100 * (c - h), 1), round(100 * (c + h), 1)


# ----------------------------------------------------------------------------------------------------------------
# Copied verbatim from reproduce_cleanroom.py (same reason, same check).
# ----------------------------------------------------------------------------------------------------------------
CUTOFF = pd.Timestamp('2026-08-02')
WINDOW = pd.Timedelta(days=30)


def repeat_frame(base, order_cols=('opened', 'case_id')):
    """LEAD(opened_at), LEAD(category) over unplanned tickets PARTITION BY machine ORDER BY opened."""
    r = base.sort_values(['serial', *order_cols]).copy()
    g = r.groupby('serial', sort=False)
    r['next_opened'] = g['opened'].shift(-1)
    r['next_category'] = g['category'].shift(-1)
    r['gap'] = r['next_opened'] - r['opened']
    return r


def repeat_summary(r, cutoff=CUTOFF, window=WINDOW, day_mode='exact', same_missing_equal=False):
    e = r[r['opened'] < cutoff]
    if day_mode == 'exact':
        rep = e['gap'].notna() & (e['gap'] >= pd.Timedelta(0)) & (e['gap'] <= window)
    elif day_mode == 'calendar':
        d = (e['next_opened'].dt.normalize() - e['opened'].dt.normalize())
        rep = d.notna() & (d >= pd.Timedelta(0)) & (d <= window)
    elif day_mode == 'strict':
        rep = e['gap'].notna() & (e['gap'] >= pd.Timedelta(0)) & (e['gap'] < window)
    if same_missing_equal:
        same = rep & (e['category'].fillna('[Missing]') == e['next_category'].fillna('[Missing]'))
    else:
        same = rep & e['category'].notna() & (e['category'] == e['next_category'])
    simul = rep & (e['gap'] == pd.Timedelta(0))
    return e, rep, same, simul


COPIES = {'audit_case_logic.py': ['REPEAT_VIEW_SQL', 'wilson'],
          'reproduce_cleanroom.py': ['CUTOFF', 'WINDOW', 'repeat_frame', 'repeat_summary']}


# ----------------------------------------------------------------------------------------------------------------
# Checks, output and small helpers
# ----------------------------------------------------------------------------------------------------------------
def check(name, expected, actual, tol=0.0):
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float, np.integer, np.floating)):
        ok = abs(float(actual) - float(expected)) <= tol
    else:
        ok = expected == actual
    CHECKS.append({'check': name, 'expected': expected, 'actual': actual, 'status': 'PASS' if ok else 'FAIL'})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: expected {expected}, got {actual}")
    return ok


def pin(name, expected, actual, tol=0.0):
    """A check tied to the real export (docs/09 §8); skipped with --no-pins (synthetic fixture)."""
    return check(name, expected, actual, tol) if PINS_ON['on'] else True


def save(out, df, name):
    df = df.reset_index(drop=True)
    path = out / f'{name}.csv'
    df.to_csv(path, index=False, float_format='%.10g')
    PUBLIC[name] = df
    print(f'  wrote {path.name} ({len(df):,} rows)')
    return df


def r(x, nd=6):
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), nd)
    return x


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, np.ndarray)):
        return [jsonable(v) for v in o]
    return r(o)


def interval(reps):
    """95% percentile interval over bootstrap replicates; undefined (NaN) draws are left out and counted."""
    lo, hi, undefined = ci(reps)
    return lo, hi, undefined


def bh_q(p):
    return FX.bh_q(np.asarray(p, float))


def chi2_sf(x, df):
    """P(chi-square with df degrees of freedom > x): the regularized upper incomplete gamma Q(df/2, x/2), by its
    series below a + 1 and its continued fraction above (no scipy here)."""
    a, z = df / 2, x / 2
    if x <= 0:
        return 1.0
    lead = math.exp(-z + a * math.log(z) - math.lgamma(a))
    if z < a + 1:
        term = total = 1 / a
        n = 0
        while abs(term) > abs(total) * 1e-15 and n < 10_000:
            n += 1
            term *= z / (a + n)
            total += term
        return max(0.0, 1 - lead * total)
    b, c, d = z + 1 - a, 1e300, 1 / (z + 1 - a)
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return lead * h


def request_types_hash(path):
    rows = sorted(csv.DictReader(open(path, newline='', encoding='utf-8')),
                  key=lambda x: (x['trouble_code'], x['category']))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['trouble_code', 'category', 'group'])
    for x in rows:
        w.writerow([x['trouble_code'], x['category'], x['group']])
    return hashlib.sha256(buf.getvalue().encode('utf-8')).hexdigest()


def copied_code_matches():
    """The copied definitions above, node by node, against their sources (syntax trees, no line numbers)."""
    mine = {n.targets[0].id if isinstance(n, ast.Assign) else n.name: ast.dump(n)
            for n in ast.parse(Path(__file__).read_text()).body
            if isinstance(n, ast.FunctionDef) or (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name))}
    out = {}
    for src, names in COPIES.items():
        theirs = {}
        for n in ast.parse((HERE / src).read_text()).body:
            if isinstance(n, ast.FunctionDef):
                theirs[n.name] = ast.dump(n)
            elif isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
                theirs.setdefault(n.targets[0].id, ast.dump(n))
        for name in names:
            out[f'{src}:{name}'] = mine.get(name) == theirs.get(name)
    return out


def real_sets(maps, equipment):
    """fleet_exposure.real_sets for a given equipment path (the fixture passes its own)."""
    text_cols = ['Account Name', 'Hospital Address', 'Hospital City', 'Location', 'Vendor Credentialing Notes']
    digit_cols = ['Serial Number', 'Hospital Zip Code', 'Phone']
    names = set(map(str, maps['account'])) | common.equipment_real_strings(equipment, columns=text_cols)
    ids = set(map(str, maps['serial'])) | set(map(str, maps['case'])) \
        | common.equipment_real_strings(equipment, columns=digit_cols)
    text = {n for n in map(FX.norm, names | {i for i in ids if not i.isdigit()}) if len(n) >= 4 and not n.isdigit()}
    digit = {i for i in ids if i.isdigit()} | {re.sub(r'\D', '', i) for i in ids if len(re.sub(r'\D', '', i)) >= 7}
    return {'text': text, 'digit': digit, 'max_words': max(len(t.split()) for t in text)}


# ----------------------------------------------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------------------------------------------
def assign_request_types(sc, ref):
    """docs/09 §3.3: cgroup (the group from Trouble Code x Category, no Monitoring override), group (Monitoring
    overrides) and ctype (the Category level). Returns the 'Trouble Code / Category' labels the reference does not
    list (mapped by the fallback rule)."""
    lut = dict(zip(zip(ref.trouble_code, ref.category), ref.group))
    tc, cat = sc.trouble_code.fillna(BLANK), sc.category.fillna(BLANK)
    grp = pd.Series([lut.get(k) for k in zip(tc, cat)], index=sc.index, dtype=object)
    unmapped = grp.isna()
    fallback = pd.Series(np.where(tc.isin(list(BY_TROUBLE_CODE)), tc.map(BY_TROUBLE_CODE),
                                  np.where(cat == BLANK, NO_CAT, 'Other')), index=sc.index)
    sc['cgroup'] = grp.where(~unmapped, fallback)
    sc['group'] = np.where(sc.monitoring, MONITORING, sc.cgroup)
    sc['ctype'] = np.where(sc.monitoring, MONITORING, np.where(cat == BLANK, NO_CAT, cat))
    return [f'{a} / {b}' for a, b in zip(tc[unmapped], cat[unmapped])]


def load(xlsx, equipment, fu_dir):
    """Unplanned tickets with request types and telemetry type; the installed-base machine frame (slide 4)."""
    raw = common.load_raw(xlsx)
    maps = common.build_maps(raw)
    cases = common.build_cases(raw, maps)
    conn = common.case_database(cases)
    sc = pd.read_sql('SELECT * FROM service_cases', conn)
    eq = common.load_equipment(equipment)
    maps = common.extend_maps(maps, eq)
    inv_serial = {v: k for k, v in maps['serial'].items()}
    case_text = dict(zip(raw['Case Number'].map(common.clean).map(maps['case']), raw['Trouble Reported']))
    sc['serial'] = sc.machine_id.map(inv_serial)
    sc['ts'] = pd.to_datetime(sc.opened_at)
    sc['monitoring'] = sc.case_id.map(case_text).map(monitoring_template).astype(bool)
    sc['core'] = ~sc.monitoring & (sc.service_group != NTF)
    FACTS['monitoring_all_tickets'] = int(raw['Trouble Reported'].map(monitoring_template).sum())

    unmapped = assign_request_types(sc, pd.read_csv(REF, dtype=str, keep_default_na=False))
    FACTS['request_types'] = {'hash': request_types_hash(REF), 'unmapped_tickets': len(unmapped),
                              'unmapped_combinations': sorted(set(unmapped))}

    # Telemetry type per machine (docs/09 §3.6): guard-0 rows of the ticket-to-device map, then the device's type.
    f = pd.read_csv(fu_dir / 'fu_ticket_last10.csv', usecols=['case_id', 'machine_id', 'window'], dtype=str)
    f = f[f.window == 'corrected_guard0'].rename(columns={'machine_id': 'device'})[['case_id', 'device']]
    d = pd.read_csv(fu_dir / 'fu_devices.csv', usecols=['machine_id', 'machine_type'], dtype=str,
                    keep_default_na=False)
    f['ttype'] = f.device.map(dict(zip(d.machine_id, d.machine_type.map(norm_type))))
    x = sc[['case_id', 'machine_id']].merge(f, on='case_id', how='inner')
    per = x.groupby('machine_id').ttype.agg(lambda s: s.iloc[0] if s.nunique() == 1 else SEVERAL)
    sc['ttype'] = sc.machine_id.map(per).fillna(NO_MATCH)
    FACTS['telemetry_map'] = {'tickets_matched': len(x), 'machines_matched': int(x.machine_id.nunique()),
                              'devices_matched': int(x.device.nunique()),
                              'machines_one_type': int((per != SEVERAL).sum()),
                              'machines_several_types': int((per == SEVERAL).sum()),
                              'machines_no_match': int(sc.loc[sc.ttype == NO_MATCH, 'machine_id'].nunique()),
                              'machines_unknown_type': int((per == UNKNOWN).sum()),
                              'tickets_on_typed_machines': int((~sc.ttype.isin(NOT_TYPES)).sum()),
                              'tickets': len(sc)}

    m_all, t_all = FX.machine_frame(eq, maps, sc)
    return raw, maps, cases, conn, sc, eq, m_all, t_all


# ----------------------------------------------------------------------------------------------------------------
# Pins (docs/09 §8): committed outputs this run must reproduce before any new result
# ----------------------------------------------------------------------------------------------------------------
def pins(sc, conn, m, t, ttype_facts):
    print('Pins')
    out = common.OUTPUTS
    ok = True
    fx = json.loads((out / 'fleet' / 'fx_summary.json').read_text())['fleet']
    exposed = m[m.months > 0]
    for key, val in (('machines', len(m)), ('machines_exposed', len(exposed)), ('accounts', m.customer.nunique()),
                     ('tickets', int(m.tickets.sum()))):
        ok &= check(f'pin fx_summary {key}', fx[key], val)
    ok &= check('pin fx_summary months', fx['months'], float(m.months.sum()), tol=1e-6)
    ages = pd.read_csv(out / 'fleet' / 'fx_age_rates.csv')
    g = exposed.groupby('age_band', observed=True).agg(machines=('serial', 'size'), months=('months', 'sum'),
                                                       tickets=('tickets', 'sum')).reindex(ages.age_band)
    ok &= check('pin fx_age_rates machines and tickets (7 rows)', True,
                bool((g.machines.to_numpy() == ages.machines.to_numpy()).all()
                     and (g.tickets.to_numpy() == ages.tickets.to_numpy()).all()))
    ok &= check('pin fx_age_rates months (7 rows)', 0.0, float(np.abs(g.months.to_numpy() - ages.months).max()),
                tol=1e-6)
    young = exposed.age_band.isin(YOUNG_BANDS)
    for lab, sel, want in (('under 4', young, (3629, 3987, 45103.3758)), ('4+', ~young, (3121, 4959, 64517.9138))):
        ok &= check(f'pin {lab}: tickets, machines', want[:2], (int(exposed[sel].tickets.sum()), int(sel.sum())))
        ok &= check(f'pin {lab}: months', want[2], float(exposed[sel].months.sum()), tol=5e-5)
    flags = pd.read_csv(out / 'fleet' / 'fx_machine_flags.csv')
    mine = m.set_index('serial_id').reindex(flags.serial_id)
    same = ((mine.model.to_numpy() == flags.model.to_numpy()) & (mine.age_band.astype(str).to_numpy()
            == flags.age_band.astype(str).to_numpy()) & (mine.tickets.to_numpy() == flags.tickets.to_numpy())
            & (mine.tickets_core.to_numpy() == flags.tickets_core.to_numpy())
            & (np.abs(mine.months.to_numpy() - flags.months.to_numpy()) < 1e-6))
    ok &= check('pin fx_machine_flags: all machines with tickets (model, age band, months, tickets, core)',
                len(flags), int(same.sum()))
    ok &= check('pin machines with tickets', 3457, int((m.tickets > 0).sum()))
    models = pd.read_csv(out / 'fleet' / 'fx_model_rates.csv')
    g = exposed.groupby('model').agg(machines=('serial', 'size'), tickets=('tickets', 'sum'),
                                     months=('months', 'sum')).reindex(models.model)
    ok &= check('pin fx_model_rates (34 rows): machines, tickets, months', len(models),
                int(((g.machines.to_numpy() == models.machines.to_numpy())
                     & (g.tickets.to_numpy() == models.tickets.to_numpy())
                     & (np.abs(g.months.to_numpy() - models.months.to_numpy()) < 1e-6)).sum()))
    core = exposed.groupby(young.map({True: 'u', False: 'o'})).tickets_core.sum()
    ok &= check('pin core tickets (total, under 4, 4+)', (6138, 3284, 2854),
                (int(exposed.tickets_core.sum()), int(core['u']), int(core['o'])))
    ok &= check('pin monitoring templates (all tickets)', 138, FACTS['monitoring_all_tickets'])
    ok &= check('pin unplanned tickets', 7186, len(sc))
    rs = pd.read_csv(out / 'repro_sql_repeat_summary.csv').iloc[0]
    sqlr = pd.read_sql(REPEAT_VIEW_SQL.format(src='service_cases'), conn)
    ok &= check('pin repro_sql_repeat_summary (eligible, machines, repeats, same Category)',
                (int(rs.eligible_tickets), int(rs.machines), int(rs.repeat_tickets), int(rs.same_category_repeats)),
                (len(sqlr), int(sqlr.machine_id.nunique()), int(sqlr.repeat_30.sum()),
                 int(sqlr.same_category_30.sum())))
    bins = pd.read_csv(out / 'audit_case_repeat_gap_bins.csv')
    gd = sqlr.gap_days[sqlr.repeat_30 == 1]
    edges = [(-1e-12, 0), (0, 1 / 24), (1 / 24, 4 / 24), (4 / 24, 1), (1, 2), (2, 7), (7, 14), (14, 30 + 1e-9)]
    mine_bins = [int(((gd > lo) & (gd <= hi)).sum()) if lo >= 0 else int((gd == 0).sum()) for lo, hi in edges]
    ok &= check('pin audit_case_repeat_gap_bins (8 bins)', bins.repeats.astype(int).tolist(), mine_bins)
    s7 = sqlr[(sqlr.repeat_30 == 1) & (sqlr.gap_days <= 7)]
    ok &= check('pin 7-day repeats and same Category', (631, 221), (len(s7), int(s7.same_category_30.sum())))
    bym = pd.read_csv(out / 'repro_sql_repeat_by_model.csv')
    g = sqlr.groupby('model').agg(eligible=('case_id', 'size'), repeats=('repeat_30', 'sum')).reindex(bym.model)
    ok &= check('pin repro_sql_repeat_by_model (31 rows)', len(bym),
                int(((g.eligible.to_numpy() == bym.eligible_tickets.to_numpy())
                     & (g.repeats.to_numpy() == bym.repeat_tickets.to_numpy())).sum()))
    comp = dict(pd.read_csv(out / 'audit_case_repeat_composition.csv').values)
    rep = sqlr[sqlr.repeat_30 == 1]
    nxt = sc.set_index('case_id')
    order = sc.sort_values(['machine_id', 'opened_at', 'case_id'])
    next_case = order.groupby('machine_id').case_id.shift(-1)
    next_of = dict(zip(order.case_id, next_case))
    ncat = rep.case_id.map(next_of).map(nxt.category)
    ok &= check('pin repeat composition: NTF on index, follow-up, either; follow-up Category blank',
                (int(comp['index_is_NTF']), int(comp['followup_is_NTF']), int(comp['either_is_NTF']),
                 int(comp['followup_category_missing'])),
                (int((rep.category == NTF).sum()), int((ncat == NTF).sum()),
                 int(((rep.category == NTF) | (ncat == NTF).to_numpy()).sum()), int(ncat.isna().sum())))
    mix = pd.read_csv(out / 'repro_clean_issue_mix.csv')
    g = sc.category.fillna('[Missing]').value_counts().reindex(mix.category)
    ok &= check('pin repro_clean_issue_mix (38 rows)', len(mix), int((g.to_numpy() == mix.cases.to_numpy()).sum()))
    sc.loc[~sc.monitoring, ['case_id', 'machine_id', 'opened_at', 'category', 'model']] \
        .to_sql('pin_nomon', conn, index=False, if_exists='replace')
    rk = pd.read_sql(REPEAT_VIEW_SQL.format(src='pin_nomon'), conn)
    ok &= check('pin slide 5: repeats without monitoring templates (1,438 / 6,529 = 22.0%)', (1438, 6529),
                (int(rk.repeat_30.sum()), len(rk)))
    ok &= check('pin ticket-to-device map: unplanned tickets matched', 5921, ttype_facts['tickets_matched'])
    ok &= check('pin ticket-to-device map: machines (serials) matched', 2993, ttype_facts['machines_matched'])
    return ok


# ----------------------------------------------------------------------------------------------------------------
# Part A machinery: strata tables, Mantel-Haenszel, CMH, permutations (numpy, vectorised over draws)
# ----------------------------------------------------------------------------------------------------------------
def tab(C, rows, s_idx, S):
    """Per-stratum sums of C's columns over the given rows (S x K)."""
    out = np.zeros((S, C.shape[1]))
    np.add.at(out, s_idx[rows], C[rows])
    return out


def mh_share(a, b, n1, n0):
    """Mantel-Haenszel share ratio per type: sum_s a*n0/N / sum_s b*n1/N (arrays ..., S, K and ..., S)."""
    N = n1 + n0
    with np.errstate(divide='ignore', invalid='ignore'):
        wa = np.where(N > 0, n0 / np.where(N > 0, N, 1), 0.0)[..., None]
        wb = np.where(N > 0, n1 / np.where(N > 0, N, 1), 0.0)[..., None]
        return (a * wa).sum(-2) / (b * wb).sum(-2)


def mh_rate(a, b, M1, M0):
    """Mantel-Haenszel rate ratio per type: sum_s a*M0/M / sum_s b*M1/M."""
    M = M1 + M0
    with np.errstate(divide='ignore', invalid='ignore'):
        wa = np.where(M > 0, M0 / np.where(M > 0, M, 1), 0.0)[..., None]
        wb = np.where(M > 0, M1 / np.where(M > 0, M, 1), 0.0)[..., None]
        return (a * wa).sum(-2) / (b * wb).sum(-2)


def cmh(a, b, n1, n0):
    """Global X = sum_k D_k^2 (1/E1_k + 1/E0_k) and per-type CMH z_k (docs/09 §4 A3); arrays ..., S, K."""
    N, n1_, n0_ = (n1 + n0)[..., None], n1[..., None], n0[..., None]
    m = a + b
    with np.errstate(divide='ignore', invalid='ignore'):
        Ns = np.where(N > 0, N, 1)
        E1 = np.where(N > 0, n1_ * m / Ns, 0.0)
        E0 = np.where(N > 0, n0_ * m / Ns, 0.0)
        V = np.where(N > 1, n1_ * n0_ * m * (N - m) / (Ns ** 2 * np.where(N > 1, N - 1, 1)), 0.0)
        D, E1k, E0k, Vk = (a - E1).sum(-2), E1.sum(-2), E0.sum(-2), V.sum(-2)
        ok = (E1k > 0) & (E0k > 0)
        X = np.where(ok, D ** 2 * (1 / np.where(ok, E1k, 1) + 1 / np.where(ok, E0k, 1)), 0.0).sum(-1)
        z = np.where(Vk > 0, D / np.sqrt(np.where(Vk > 0, Vk, 1)), 0.0)
    return X, z


def cmh_excess(a, b, n1, n0):
    """D_k = sum over strata of (a - E1): under-4 tickets of type k minus those expected at the same within-model
    mix (the numerator of cmh's z); arrays ..., S, K."""
    N = (n1 + n0)[..., None]
    with np.errstate(divide='ignore', invalid='ignore'):
        E1 = np.where(N > 0, n1[..., None] * (a + b) / np.where(N > 0, N, 1), 0.0)
    return (a - E1).sum(-2)


def perm_labels(young, s_idx, rows, strata, n_perm, rng):
    """{stratum: (machine rows, n_perm x n boolean labels)}: the under-4 label permuted among the given rows within
    each stratum, strata in the given (sorted) order so the random stream is fixed."""
    out = {}
    for s in strata:
        idx = np.flatnonzero(rows & (s_idx == s))
        if len(idx) == 0:
            continue
        lab = np.tile(young[idx], (n_perm, 1))
        if 0 < young[idx].sum() < len(idx):
            lab = rng.permuted(lab, axis=1)
        out[s] = (idx, lab)
    return out


def perm_tables(L, C, tot, target, n_target, n_perm):
    """Permuted under-4 counts (n_perm x n_target x K) and totals (n_perm x n_target): each permutation stratum's
    machines summed into its analysis stratum (target(first machine row) -> position)."""
    a = np.zeros((n_perm, n_target, C.shape[1]))
    n1 = np.zeros((n_perm, n_target))
    for s, (idx, lab) in L.items():
        j = target(idx[0])
        lf = lab.astype(float)
        a[:, j] += lf @ C[idx]
        n1[:, j] += lf @ tot[idx]
    return a, n1


def n_accounts(C, rows, acc_idx):
    """Per column: distinct accounts with at least one ticket among the rows."""
    return np.array([np.unique(acc_idx[rows & (C[:, k] > 0)]).size for k in range(C.shape[1])])


class AgeTest:
    """One under-4 vs 4+ comparison over model (or other) strata: tables, MH ratios, permutation tests, the gate."""

    def __init__(self, name, young, s_idx, S, rows, Cfam, fam_names, Ccat, cat_names, cat_group, acc_idx, months,
                 support, n_perm, rng, perm_strata=None, perm_s_idx=None):
        self.name, self.fam, self.cats, self.cat_group = name, list(fam_names), list(cat_names), list(cat_group)
        tot = Cfam.sum(1)
        self.rows = rows & support[s_idx]
        sup = np.flatnonzero(support)
        self.sup = sup
        y, o = self.rows & young, self.rows & ~young
        self.a, self.b = tab(Cfam, y, s_idx, S)[sup], tab(Cfam, o, s_idx, S)[sup]
        self.n1, self.n0 = tab(tot[:, None], y, s_idx, S)[sup, 0], tab(tot[:, None], o, s_idx, S)[sup, 0]
        self.M1 = tab(months[:, None], y, s_idx, S)[sup, 0]
        self.M0 = tab(months[:, None], o, s_idx, S)[sup, 0]
        self.ac = tab(Ccat, y, s_idx, S)[sup] if Ccat is not None else None
        self.bc = tab(Ccat, o, s_idx, S)[sup] if Ccat is not None else None
        self.sr, self.rr = mh_share(self.a, self.b, self.n1, self.n0), mh_rate(self.a, self.b, self.M1, self.M0)
        self.X, self.z = cmh(self.a, self.b, self.n1, self.n0)
        self.D = cmh_excess(self.a, self.b, self.n1, self.n0)
        self.acc = (n_accounts(Cfam, y, acc_idx), n_accounts(Cfam, o, acc_idx))
        self.est = (self.a.sum(0) >= MIN_EST_TICKETS) & (self.b.sum(0) >= MIN_EST_TICKETS) & \
            (self.acc[0] >= MIN_EST_ACCOUNTS) & (self.acc[1] >= MIN_EST_ACCOUNTS)
        if Ccat is not None:
            self.src = mh_share(self.ac, self.bc, self.n1, self.n0)
            _, self.zc = cmh(self.ac, self.bc, self.n1, self.n0)
            self.Dc = cmh_excess(self.ac, self.bc, self.n1, self.n0)
            self.accc = (n_accounts(Ccat, y, acc_idx), n_accounts(Ccat, o, acc_idx))
            self.estc = (self.ac.sum(0) >= MIN_EST_TICKETS) & (self.bc.sum(0) >= MIN_EST_TICKETS) & \
                (self.accc[0] >= MIN_EST_ACCOUNTS) & (self.accc[1] >= MIN_EST_ACCOUNTS)
        # Permutations: within strata (model by default), among machines with a ticket in the family.
        ps_idx = s_idx if perm_s_idx is None else perm_s_idx
        pstrata = sorted(set(ps_idx[self.rows & (tot > 0)])) if perm_strata is None else perm_strata
        self.machines = int((self.rows & (tot > 0)).sum())
        self.tickets = int(tot[self.rows].sum())
        self.p = self.pz = self.pzc = None
        if n_perm:
            L = perm_labels(young, ps_idx, self.rows & (tot > 0), pstrata, n_perm, rng)
            # A permutation stratum lies inside one analysis stratum (model x account inside model).
            pos = {s: i for i, s in enumerate(sup)}
            target = lambda row: pos[s_idx[row]]  # noqa: E731
            A, N1 = perm_tables(L, Cfam, tot, target, len(sup), n_perm)
            B, N0 = (self.a + self.b)[None] - A, (self.n1 + self.n0)[None] - N1
            self.Xp, zp = cmh(A, B, N1, N0)
            self.p, self.p_se = perm_p(self.X, self.Xp)
            self.pz = np.array([perm_p(abs(self.z[k]), np.abs(zp[:, k]))[0] for k in range(len(self.fam))])
            self.pz_se = np.array([perm_p(abs(self.z[k]), np.abs(zp[:, k]))[1] for k in range(len(self.fam))])
            if Ccat is not None:
                AC, _ = perm_tables(L, Ccat, tot, target, len(sup), n_perm)
                BC = (self.ac + self.bc)[None] - AC
                _, zcp = cmh(AC, BC, N1, N0)
                pc = [perm_p(abs(self.zc[k]), np.abs(zcp[:, k])) for k in range(len(self.cats))]
                self.pzc = np.array([x[0] for x in pc])
                self.pzc_se = np.array([x[1] for x in pc])
        self.gate()

    def gate(self):
        """docs/09 §4 A3: global p < 0.05, then groups (BH), then Categories within passing groups (BH)."""
        k = len(self.fam)
        self.tested = np.zeros(k, bool)
        self.q = np.full(k, np.nan)
        self.sig = np.zeros(k, bool)
        self.global_pass = self.p is not None and self.p < ALPHA
        if self.global_pass:
            self.tested = self.est.copy()
            q = bh_q(np.where(self.tested, self.pz, np.nan))
            self.q = q
            self.sig = self.tested & (q < ALPHA)
        if self.pzc is not None:
            kc = len(self.cats)
            self.testedc, self.qc, self.sigc = np.zeros(kc, bool), np.full(kc, np.nan), np.zeros(kc, bool)
            for gi, g in enumerate(self.fam):
                if not self.sig[gi] or g not in COMPONENT:
                    continue
                members = np.array([cg == g for cg in self.cat_group]) & self.estc
                if not members.any():
                    continue
                q = bh_q(np.where(members, self.pzc, np.nan))
                self.testedc |= members
                self.qc = np.where(members, q, self.qc)
                self.sigc |= members & (q < ALPHA)

    def test_row(self, description):
        return {'variant': self.name, 'description': description, 'statistic_X': self.X,
                'null_median': float(np.median(self.Xp)) if self.p is not None else np.nan,
                'null_p97_5': float(np.percentile(self.Xp, 97.5)) if self.p is not None else np.nan,
                'p': self.p if self.p is not None else np.nan, 'p_mc_se': self.p_se if self.p is not None else np.nan,
                'strata': len(self.sup), 'ticketed_machines': self.machines, 'tickets': self.tickets,
                'global_pass': bool(self.global_pass),
                'groups_significant': '; '.join(g for g, s in zip(self.fam, self.sig) if s),
                'groups_tested': int(self.tested.sum())}

    def type_rows(self, ci_sr=None, ci_rr=None, ipf=None):
        """One row per group and Category. docs/09 §4: a type that is not estimable is reported as counts only, so its
        ratios, z, p and intervals are left blank."""
        rows = []

        def counts_only(row):
            return row if row['estimable'] else row | {k: np.nan for k in NOT_ESTIMABLE_BLANK if k in row}
        for k, g in enumerate(self.fam):
            row = {'variant': self.name, 'level': 'group', 'type': g, 'group': g,
                   'under4_tickets': self.a[:, k].sum(), 'plus4_tickets': self.b[:, k].sum(),
                   'under4_accounts': self.acc[0][k], 'plus4_accounts': self.acc[1][k],
                   'under4_share': self.a[:, k].sum() / self.n1.sum(), 'plus4_share': self.b[:, k].sum() / self.n0.sum(),
                   'estimable': bool(self.est[k]), 'share_ratio_mh': self.sr[k], 'rate_ratio_mh': self.rr[k],
                   'z_cmh': self.z[k], 'excess_under4_tickets': self.D[k],
                   'p_perm': self.pz[k] if self.pz is not None else np.nan,
                   'p_mc_se': self.pz_se[k] if self.pz is not None else np.nan, 'tested': bool(self.tested[k]),
                   'q_bh': self.q[k], 'significant': bool(self.sig[k])}
            if ci_sr is not None:
                row |= {'share_ratio_lo': ci_sr[k][0], 'share_ratio_hi': ci_sr[k][1], 'share_ratio_undefined_draws':
                        ci_sr[k][2], 'rate_ratio_lo': ci_rr[k][0], 'rate_ratio_hi': ci_rr[k][1]}
            if ipf is not None:
                row['rate_ratio_ipf'] = ipf.get(g, np.nan)
            rows.append(counts_only(row))
        if self.ac is not None:
            for k, c in enumerate(self.cats):
                row = {'variant': self.name, 'level': 'category', 'type': c, 'group': self.cat_group[k],
                       'under4_tickets': self.ac[:, k].sum(), 'plus4_tickets': self.bc[:, k].sum(),
                       'under4_accounts': self.accc[0][k], 'plus4_accounts': self.accc[1][k],
                       'under4_share': self.ac[:, k].sum() / self.n1.sum(),
                       'plus4_share': self.bc[:, k].sum() / self.n0.sum(), 'estimable': bool(self.estc[k]),
                       'share_ratio_mh': self.src[k],
                       'rate_ratio_mh': mh_rate(self.ac[:, [k]], self.bc[:, [k]], self.M1, self.M0)[0],
                       'z_cmh': self.zc[k], 'excess_under4_tickets': self.Dc[k],
                       'p_perm': self.pzc[k] if self.pzc is not None else np.nan,
                       'p_mc_se': self.pzc_se[k] if self.pzc is not None else np.nan,
                       'tested': bool(self.testedc[k]) if self.pzc is not None else False,
                       'q_bh': self.qc[k] if self.pzc is not None else np.nan,
                       'significant': bool(self.sigc[k]) if self.pzc is not None else False}
                if ci_sr is not None:
                    j = len(self.fam) + k
                    row |= {'share_ratio_lo': ci_sr[j][0], 'share_ratio_hi': ci_sr[j][1],
                            'share_ratio_undefined_draws': ci_sr[j][2], 'rate_ratio_lo': ci_rr[j][0],
                            'rate_ratio_hi': ci_rr[j][1]}
                rows.append(counts_only(row))
        return rows


# ----------------------------------------------------------------------------------------------------------------
# Part A
# ----------------------------------------------------------------------------------------------------------------
def decompose(T, M, supm):
    """docs/09 §4 A4. T: (..., S, 2, K) tickets and M: (..., S, 2) months by stratum and age (0 = 4+, 1 = under 4);
    supm: support strata. Returns the extra tickets on under-4 machines at 4+ rates and its three parts (..., K):
    within-model age, model mix, models outside the support (short of 100 months in either age group); and the
    under-4 months (..., 1)."""
    with np.errstate(divide='ignore', invalid='ignore'):
        Ro = T[..., 0, :].sum(-2) / M[..., 0].sum(-1)[..., None]
        Ty_ = T[..., 1, :].sum(-2)
        My_ = M[..., 1].sum(-1)[..., None]
        Ros = T[..., 0, :] / M[..., 0][..., None]
        Ros = np.where(np.isfinite(Ros), Ros, np.nan)
        Tsup = T[..., supm, 1, :].sum(-2)
        Msup = M[..., supm, 1].sum(-1)[..., None]
        exp_same = (M[..., supm, 1][..., None] * Ros[..., supm, :]).sum(-2)
        Tout = T[..., ~supm, 1, :].sum(-2)
        Mout = M[..., ~supm, 1].sum(-1)[..., None]
        total = Ty_ - My_ * Ro
        within = Tsup - exp_same
        mix = exp_same - Msup * Ro
        outside = Tout - Mout * Ro
    return total, within, mix, outside, My_


def counts(mx, t, key, levels):
    x = pd.crosstab(t.serial, t[key]).reindex(index=mx.serial, columns=levels, fill_value=0)
    return x.to_numpy(float)


def part_a(out, m, t, unl, W, accounts, n_perm):
    print('Part A: request types on machines under 4 vs 4+')
    mx = m[m.months > 0].reset_index(drop=True)
    young = mx.age_band.isin(YOUNG_BANDS).to_numpy()
    mx['age_group'] = np.where(young, AGE_LABELS[0], AGE_LABELS[1])
    models = sorted(mx.model.unique())
    S = len(models)
    s_idx = mx.model.map({v: i for i, v in enumerate(models)}).to_numpy()
    acc_idx = mx.customer.map({a: i for i, a in enumerate(accounts)}).to_numpy()
    months = mx.months.to_numpy(float)
    tp = t[t.serial.isin(set(mx.serial))]
    pin('Part A tickets (slide 4 population)', 6750, len(tp))
    catmask = tp.cgroup.isin(COMPONENT) & (tp.ctype != NO_CAT) & ~tp.monitoring
    ctab = tp[catmask].groupby(['cgroup', 'ctype']).size().reset_index(name='n')
    ctab['o'] = ctab.cgroup.map({g: i for i, g in enumerate(GROUPS)})
    ctab = ctab.sort_values(['o', 'n', 'ctype'], ascending=[True, False, True])
    cats, cat_group = ctab.ctype.tolist(), ctab.cgroup.tolist()
    check('every Category lies in one group', len(cats), len(set(cats)))
    Cg = counts(mx, tp, 'group', GROUPS)
    Cc = counts(mx, tp[catmask], 'ctype', cats)
    check('Part A: group counts sum to the tickets', len(tp), int(Cg.sum()))
    M1 = np.bincount(s_idx[young], weights=months[young], minlength=S)
    M0 = np.bincount(s_idx[~young], weights=months[~young], minlength=S)
    support = (M1 >= MIN_SUPPORT_MONTHS) & (M0 >= MIN_SUPPORT_MONTHS)
    fam = [GROUPS.index(g) for g in PRIMARY]
    Cf = Cg[:, fam]
    tot = Cf.sum(1)
    all_rows = np.ones(len(mx), bool)
    perm_models = sorted(set(s_idx))

    # ------------------------------------------------------------- A2/A3 primary
    prim = AgeTest('primary', young, s_idx, S, all_rows, Cf, PRIMARY, Cc, cats, cat_group, acc_idx, months, support,
                   n_perm, np.random.default_rng((SEED_PERM, 0)), perm_strata=perm_models)
    sup = prim.sup
    cov = {'support_models': [models[s] for s in sup],
           'under4_family_tickets': int(tot[young].sum()), 'plus4_family_tickets': int(tot[~young].sum()),
           'under4_family_tickets_support': int(prim.n1.sum()), 'plus4_family_tickets_support': int(prim.n0.sum()),
           'under4_months_support': float(prim.M1.sum()), 'plus4_months_support': float(prim.M0.sum()),
           'under4_months': float(months[young].sum()), 'plus4_months': float(months[~young].sum())}
    cov['under4_share_support'] = cov['under4_family_tickets_support'] / cov['under4_family_tickets']
    cov['plus4_share_support'] = cov['plus4_family_tickets_support'] / cov['plus4_family_tickets']
    b46 = mx.age_band.astype(str).eq('4-6').to_numpy()
    cov['plus4_support_tickets_aged_4_6'] = float(tot[~young & b46 & support[s_idx]].sum() / prim.n0.sum())
    FACTS['support'] = cov
    print(f"  support: {len(sup)} models; {100 * cov['under4_share_support']:.1f}% of under-4 and "
          f"{100 * cov['plus4_share_support']:.1f}% of 4+ family tickets; global p = {prim.p:.4f}")

    # ------------------------------------------------------------- bootstrap (accounts; slide 4's draws)
    n_acc, n_boot = len(accounts), W.shape[0]
    cols = np.concatenate([Cg, Cc, tot[:, None], Cg.sum(1)[:, None]], axis=1)
    K = cols.shape[1]
    ig, ic, itot, iall = np.arange(10), 10 + np.arange(len(cats)), K - 2, K - 1
    A = np.zeros((n_acc, S, 2, K))
    np.add.at(A, (acc_idx, s_idx, young.astype(int)), cols)
    Mo = np.zeros((n_acc, S, 2))
    np.add.at(Mo, (acc_idx, s_idx, young.astype(int)), months)
    Tb = (W @ A.reshape(n_acc, -1)).reshape(n_boot, S, 2, K)
    Mb = (W @ Mo.reshape(n_acc, -1)).reshape(n_boot, S, 2)
    T0 = A.sum(0)
    M0s = Mo.sum(0)
    check('bootstrap tables: point totals = tickets', len(tp), float(T0[..., iall].sum()), tol=1e-9)
    fam_cols = np.array([ig[GROUPS.index(g)] for g in PRIMARY])
    sel = np.concatenate([fam_cols, ic])
    srb = mh_share(Tb[:, sup, 1][..., sel], Tb[:, sup, 0][..., sel], Tb[:, sup, 1, itot], Tb[:, sup, 0, itot])
    rrb = mh_rate(Tb[:, sup, 1][..., sel], Tb[:, sup, 0][..., sel], Mb[:, sup, 1], Mb[:, sup, 0])
    ci_sr = [interval(srb[:, j]) for j in range(len(sel))]
    ci_rr = [interval(rrb[:, j]) for j in range(len(sel))]
    ipf = {}
    in_support = np.isin(s_idx, sup)               # the same machines as the Mantel-Haenszel rate ratio
    for k, g in enumerate(PRIMARY):
        d = mx[in_support].reset_index(drop=True).assign(n=Cf[in_support, k])
        _, mult, _ = FX.ipf(d, 'n', ['model', 'age_group'])
        ag = mult['age_group']
        ipf[g] = float(ag.get(AGE_LABELS[0], np.nan) / ag.get(AGE_LABELS[1], np.nan)) \
            if ag.get(AGE_LABELS[1], 0) > 0 else np.nan
    adjusted = prim.type_rows(ci_sr, ci_rr, ipf)

    # ------------------------------------------------------------- A1 crude rates (descriptive)
    rows = []
    rate_cols = {}
    for j, g in enumerate(GROUPS):
        rate_cols[f't_{j}'] = Cg[:, j]
    for j, c in enumerate(cats):
        rate_cols[f'c_{j}'] = Cc[:, j]
    mxr = pd.concat([mx, pd.DataFrame(rate_cols)], axis=1)
    mxr['t_all'] = Cg.sum(1)
    Ty, To = Tb[:, :, 1].sum(1), Tb[:, :, 0].sum(1)
    My, Mo_ = Mb[:, :, 1].sum(1), Mb[:, :, 0].sum(1)
    for level, names, keyfmt, idxs in (('group', GROUPS, 't_{}', ig), ('category', cats, 'c_{}', ic),
                                        ('all', ['All unplanned tickets'], None, [iall])):
        for j, name in enumerate(names):
            col = 't_all' if keyfmt is None else keyfmt.format(j)
            g, _ = FX.group_rates(mxr, 'age_group', W, accounts, tickets=col)
            g = g.set_index('age_group')
            k = idxs[j]
            with np.errstate(divide='ignore', invalid='ignore'):
                rr_b = (Ty[:, k] / My) / (To[:, k] / Mo_)
                sh_b = (Ty[:, k] / Ty[:, iall]) / (To[:, k] / To[:, iall])
            yv, ov = g.loc[AGE_LABELS[0]], g.loc[AGE_LABELS[1]]
            rlo, rhi, _ = interval(rr_b)
            slo, shi, _ = interval(sh_b)
            rows.append({'level': level, 'type': name,
                         'group': name if level != 'category' else cat_group[j],
                         'under4_tickets': yv.tickets, 'plus4_tickets': ov.tickets,
                         'under4_months': yv.months, 'plus4_months': ov.months,
                         'under4_rate_per_100': yv.rate_per_100, 'under4_rate_lo': yv.ci_lo,
                         'under4_rate_hi': yv.ci_hi, 'plus4_rate_per_100': ov.rate_per_100,
                         'plus4_rate_lo': ov.ci_lo, 'plus4_rate_hi': ov.ci_hi,
                         'rate_ratio': yv.rate_per_100 / ov.rate_per_100 if ov.rate_per_100 > 0 else np.nan,
                         'rate_ratio_lo': rlo, 'rate_ratio_hi': rhi,
                         'under4_share': yv.tickets / T0[:, 1, iall].sum(), 'plus4_share': ov.tickets / T0[:, 0, iall].sum(),
                         'share_ratio': (yv.tickets / T0[:, 1, iall].sum()) / (ov.tickets / T0[:, 0, iall].sum())
                         if ov.tickets > 0 else np.nan, 'share_ratio_lo': slo, 'share_ratio_hi': shi})
    rates = pd.DataFrame(rows)
    allrow = rates[rates.level == 'all'].iloc[0]
    pin('A1: under-4 rate per 100 (slide 4: 3,629 / 45,103.38)', 100 * 3629 / 45103.3758,
          float(allrow.under4_rate_per_100), tol=1e-3)
    pin('A1: 4+ rate per 100 (slide 4: 3,121 / 64,517.91)', 100 * 3121 / 64517.9138,
          float(allrow.plus4_rate_per_100), tol=1e-3)
    check('A1: group tickets sum to all (under 4)', float(allrow.under4_tickets),
          float(rates[rates.level == 'group'].under4_tickets.sum()))

    # ------------------------------------------------------------- A4 decomposition (all 10 groups + estimable cats)
    supm = np.zeros(S, bool)
    supm[sup] = True

    point = decompose(T0, M0s, supm)
    boot = decompose(Tb, Mb, supm)
    check('A4: parts sum exactly to the extra tickets (every type)', 0.0,
          float(np.nanmax(np.abs(point[1] + point[2] + point[3] - point[0]))), tol=1e-6)
    est_cats = [j for j, c in enumerate(cats) if prim.estc[j]]
    drows = []
    for level, names, idxs in (('group', GROUPS, list(ig)), ('category', [cats[j] for j in est_cats],
                                                             [ic[j] for j in est_cats]),
                               ('all', ['All unplanned tickets'], [iall])):
        for name, k in zip(names, idxs):
            row = {'level': level, 'type': name,
                   'group': name if level != 'category' else cat_group[cats.index(name)]}
            for part, pv, bv in zip(('extra', 'within_model_age', 'model_mix', 'outside_support'), point[:4],
                                    boot[:4]):
                lo, hi, und = interval(bv[:, k])
                with np.errstate(divide='ignore', invalid='ignore'):
                    lo100, hi100, _ = interval(100 * bv[:, k] / boot[4][:, 0])
                row |= {f'{part}_tickets': pv[k], f'{part}_lo': lo, f'{part}_hi': hi,
                        f'{part}_per_100': 100 * pv[k] / point[4][0], f'{part}_per_100_lo': lo100,
                        f'{part}_per_100_hi': hi100, f'{part}_undefined_draws': und}
            drows.append(row)
    decomp = pd.DataFrame(drows)
    tot_row = decomp[decomp.level == 'all'].iloc[0]
    pin('A4: extra tickets (all) = 3,629 - 45,103.38 x 3,121 / 64,517.91',
          3629 - 45103.3758 * 3121 / 64517.9138, float(tot_row.extra_tickets), tol=0.05)
    check('A4: groups sum to the total (extra tickets)', float(tot_row.extra_tickets),
          float(decomp[decomp.level == 'group'].extra_tickets.sum()), tol=1e-6)

    # ------------------------------------------------------------- A5 by model
    alln = Cg.sum(1)
    tick_y = np.bincount(s_idx[young], weights=alln[young], minlength=S)
    tick_o = np.bincount(s_idx[~young], weights=alln[~young], minlength=S)
    shown = [s for s in range(S) if tick_y[s] >= MIN_SHOWN_TICKETS and tick_o[s] >= MIN_SHOWN_TICKETS]
    mrows, mp = [], []
    rng5 = np.random.default_rng((SEED_PERM, 5))
    for s in shown:
        rows_s = s_idx == s
        tm = AgeTest(f'model {models[s]}', young, s_idx, S, rows_s, Cf, PRIMARY, None, [], [], acc_idx, months,
                     np.isin(np.arange(S), [s]), n_perm, rng5)
        with np.errstate(divide='ignore', invalid='ignore'):
            rb = (Tb[:, s, 1, iall] / Mb[:, s, 1]) / (Tb[:, s, 0, iall] / Mb[:, s, 0])
        lo, hi, _ = interval(rb)
        mp.append(tm.p)
        for a_i, lab in ((1, AGE_LABELS[0]), (0, AGE_LABELS[1])):
            sel_m = rows_s & (young if a_i else ~young)
            row = {'model': models[s], 'age_group': lab, 'machines': int(sel_m.sum()),
                   'ticketed_machines': int((sel_m & (alln > 0)).sum()),
                   'accounts': int(np.unique(acc_idx[sel_m]).size), 'months': float(months[sel_m].sum()),
                   'tickets': int(alln[sel_m].sum()),
                   'rate_per_100': 100 * alln[sel_m].sum() / months[sel_m].sum(),
                   'rate_ratio_under4_vs_4plus': (tick_y[s] / M1[s]) / (tick_o[s] / M0[s]),
                   'rate_ratio_lo': lo, 'rate_ratio_hi': hi, 'mix_X': tm.X, 'mix_p': tm.p, 'mix_p_mc_se': tm.p_se}
            for j, g in enumerate(GROUPS):
                row[f'share_{g}'] = Cg[sel_m, j].sum() / alln[sel_m].sum()
                row[f'tickets_{g}'] = int(Cg[sel_m, j].sum())
            mrows.append(row)
    bym = pd.DataFrame(mrows) if mrows else pd.DataFrame(columns=['model', 'age_group', 'mix_p'])
    q = dict(zip([models[s] for s in shown], bh_q(mp))) if mp else {}
    bym['mix_q'] = bym.model.map(q)
    bym['mix_differs'] = bym.mix_q < ALPHA
    bym['in_support'] = bym.model.isin(cov['support_models'])

    # ------------------------------------------------------------- A5 by telemetry type (tickets only)
    mx['ttype'] = mx.serial_id.map(t.drop_duplicates('serial_id').set_index('serial_id').ttype) \
        if 'serial_id' in t else mx.serial.map(t.drop_duplicates('serial').set_index('serial').ttype)
    mx['ttype'] = mx.ttype.fillna('No ticket')
    types = sorted(mx.ttype.unique())
    ty_idx = mx.ttype.map({v: i for i, v in enumerate(types)}).to_numpy()
    tm_lab = mx.ttype + ' | ' + mx.model
    tm_levels = sorted(tm_lab.unique())
    tm_idx = tm_lab.map({v: i for i, v in enumerate(tm_levels)}).to_numpy()
    trows, tps = [], []
    rng6 = np.random.default_rng((SEED_PERM, 6))
    for ti, ty in enumerate(types):
        rows_t = ty_idx == ti
        ny, no = alln[rows_t & young].sum(), alln[rows_t & ~young].sum()
        shown_t = ty not in ('No ticket',) and ny >= MIN_SHOWN_TICKETS and no >= MIN_SHOWN_TICKETS \
            and ty not in NOT_TYPES
        p = p_se = X = np.nan
        if shown_t:
            sup_t = np.zeros(len(tm_levels), bool)
            sup_t[np.unique(tm_idx[rows_t])] = True
            tt = AgeTest(f'type {ty}', young, tm_idx, len(tm_levels), rows_t, Cf, PRIMARY, None, [], [], acc_idx,
                         months, sup_t, n_perm, rng6)
            p, p_se, X = tt.p, tt.p_se, tt.X
            tps.append((ty, p))
        for a_i, lab in ((1, AGE_LABELS[0]), (0, AGE_LABELS[1])):
            sel_t = rows_t & (young if a_i else ~young)
            n = alln[sel_t].sum()
            row = {'telemetry_type': ty, 'age_group': lab, 'ticketed_machines': int((sel_t & (alln > 0)).sum()),
                   'tickets': int(n), 'shown': bool(shown_t), 'mix_X': X, 'mix_p': p, 'mix_p_mc_se': p_se,
                   'models': '; '.join(sorted(mx.model[sel_t & (alln > 0)].unique()))}
            for j, g in enumerate(GROUPS):
                row[f'share_{g}'] = Cg[sel_t, j].sum() / n if n else np.nan
                row[f'tickets_{g}'] = int(Cg[sel_t, j].sum())
            trows.append(row)
    byt = pd.DataFrame(trows)
    qt = dict(zip([a for a, _ in tps], bh_q([b for _, b in tps]))) if tps else {}
    byt['mix_q'] = byt.telemetry_type.map(qt)
    byt['mix_differs'] = byt.mix_q < ALPHA
    byt = byt[byt.tickets > 0].sort_values(['shown', 'tickets'], ascending=[False, False])

    # ------------------------------------------------------------- A6 was it fixed? (halves)
    cands = [(point[1][ic[j]], cats[j], j) for j in est_cats if cat_group[j] in COMPONENT]
    cands = sorted([c for c in cands if c[0] > 0], key=lambda c: (-c[0], c[1]))[:N_FIXED]
    fixed = [c[1] for c in cands]
    FACTS['a6_categories'] = fixed
    h1_t = tp[tp.ts < SPLIT]
    h2_t = tp[tp.ts >= SPLIT]
    hrows = []
    half_boot = {}
    for hname, th, mcol in (('h1', h1_t, 'months_h1'), ('h2', h2_t, 'months_h2')):
        Ch = counts(mx, th[th.ctype.isin(fixed) & ~th.monitoring], 'ctype', fixed)
        Ch = np.concatenate([Ch, counts(mx, th, 'group', GROUPS).sum(1)[:, None]], axis=1)
        mh = mx[mcol].to_numpy(float)
        Ah = np.zeros((n_acc, S, 2, Ch.shape[1]))
        np.add.at(Ah, (acc_idx, s_idx, young.astype(int)), Ch)
        Mh = np.zeros((n_acc, S, 2))
        np.add.at(Mh, (acc_idx, s_idx, young.astype(int)), mh)
        pt = decompose(Ah.sum(0), Mh.sum(0), supm)
        bt = decompose((W @ Ah.reshape(n_acc, -1)).reshape(n_boot, S, 2, Ch.shape[1]),
                       (W @ Mh.reshape(n_acc, -1)).reshape(n_boot, S, 2), supm)
        msup = Mh.sum(0)[supm, 1].sum()
        msup_b = (W @ Mh.reshape(n_acc, -1)).reshape(n_boot, S, 2)[:, supm, 1].sum(1)
        half_boot[hname] = (pt, bt, msup, msup_b, Ah.sum(0), Mh.sum(0))
    for j, c in enumerate(fixed + ['All unplanned tickets']):
        row = {'category': c, 'group': cat_group[cats.index(c)] if c in cats else 'All',
               'full_period_within_model_age_tickets': point[1][ic[cats.index(c)]] if c in cats
               else point[1][iall]}
        vals = {}
        for hname in ('h1', 'h2'):
            pt, bt, msup, msup_b, Ah0, Mh0 = half_boot[hname]
            g_pt = 100 * pt[1][j] / msup
            g_bt = 100 * bt[1][:, j] / msup_b
            vals[hname] = (g_pt, g_bt)
            lo, hi, _ = interval(g_bt)
            row |= {f'{hname}_within_model_age_per_100': g_pt, f'{hname}_lo': lo, f'{hname}_hi': hi,
                    f'{hname}_under4_tickets_support': Ah0[supm, 1, j].sum(),
                    f'{hname}_under4_months_support': Mh0[supm, 1].sum(),
                    f'{hname}_under4_rate_per_100_support': 100 * Ah0[supm, 1, j].sum() / Mh0[supm, 1].sum(),
                    f'{hname}_same_model_4plus_rate_per_100': 100 * (Ah0[supm, 1, j].sum() - pt[1][j]) /
                    Mh0[supm, 1].sum()}
        did = vals['h2'][0] - vals['h1'][0]
        lo, hi, und = interval(vals['h2'][1] - vals['h1'][1])
        row |= {'change_h2_minus_h1': did, 'change_lo': lo, 'change_hi': hi, 'change_undefined_draws': und}
        hrows.append(row)
    halves = pd.DataFrame(hrows)
    yrows = []
    mxy = mx.assign(install_year=mx.install_date.dt.year)
    for c in fixed:
        cc = Cc[:, cats.index(c)]
        for s in sup:
            for yr, gg in mxy[s_idx == s].groupby('install_year'):
                idx = gg.index.to_numpy()
                yrows.append({'category': c, 'model': models[s], 'install_year': int(yr), 'machines': len(idx),
                              'months': float(months[idx].sum()), 'tickets': int(cc[idx].sum()),
                              'rate_per_100': 100 * cc[idx].sum() / months[idx].sum() if months[idx].sum() else np.nan,
                              'under4_machines': int(young[idx].sum())})
    inst = pd.DataFrame(yrows)
    # docs/09 §12 item 7 (added after the review; descriptive): the install-year rows pooled over the support models,
    # by install year and by cohort, with account-bootstrap intervals and each cohort's ratio to the newest cohort.
    yr = mxy.install_year.to_numpy()
    in_sup = np.isin(s_idx, sup)
    newest = '{}-{}'.format(INSTALL_COHORTS[-1][0], str(INSTALL_COHORTS[-1][1])[2:])
    prows = []
    for c in fixed + ['All unplanned tickets']:
        cc = (Cc[:, cats.index(c)] if c in cats else Cg.sum(1)).astype(float)
        units = [('year', str(int(y)), yr == y) for y in sorted(np.unique(yr[in_sup]))]
        units += [('cohort', '{}-{}'.format(a, str(b)[2:]), (yr >= a) & (yr <= b)) for a, b in INSTALL_COHORTS]
        reps_ = {}
        for kind, lab, sel in units:
            sel = sel & in_sup
            if not sel.any():                      # a cohort with no machine on the support models
                continue
            T_a = np.bincount(acc_idx[sel], weights=cc[sel], minlength=n_acc)
            M_a = np.bincount(acc_idx[sel], weights=months[sel], minlength=n_acc)
            with np.errstate(divide='ignore', invalid='ignore'):
                rb = 100 * (W @ T_a) / (W @ M_a)
            lo, hi, und = interval(rb)
            reps_[lab] = rb
            prows.append({'category': c, 'unit': kind, 'install': lab, 'machines': int(sel.sum()),
                          'months': float(months[sel].sum()), 'tickets': int(cc[sel].sum()),
                          'rate_per_100': 100 * cc[sel].sum() / months[sel].sum(), 'rate_lo': lo, 'rate_hi': hi,
                          'rate_undefined_draws': und, 'under4_share_of_machines': float(young[sel].mean())})
        point_c = {r['install']: r['rate_per_100'] for r in prows if r['category'] == c}
        for r in prows:
            if r['category'] == c and r['unit'] == 'cohort' and newest in reps_:
                with np.errstate(divide='ignore', invalid='ignore'):
                    lo, hi, und = interval(reps_[r['install']] / reps_[newest])
                r |= {'ratio_to_newest_cohort': r['rate_per_100'] / point_c[newest] if point_c[newest] else np.nan,
                      'ratio_lo': lo, 'ratio_hi': hi, 'ratio_undefined_draws': und}
    inst_pooled = pd.DataFrame(prows)
    check('A6: pooled install-year tickets = the per-model rows (three Categories)',
          int(inst.tickets.sum()) if len(inst) else 0,
          int(inst_pooled[(inst_pooled.unit == 'year') & inst_pooled.category.isin(fixed)].tickets.sum()))

    # ------------------------------------------------------------- sensitivities (ag_tests, extra adjusted rows)
    tests = [prim.test_row('Primary: within model (support models), 9 groups')]
    O = np.vstack([Cf[young].sum(0), Cf[~young].sum(0)])          # docs/09 §4 A3: descriptive only
    O = O[:, O.sum(0) > 0]
    E = O.sum(1, keepdims=True) * O.sum(0, keepdims=True) / O.sum()
    chi2 = float(((O - E) ** 2 / E).sum())
    tests.append({'variant': 'A3 unstratified (descriptive)',
                  'description': f'Unstratified chi-square on the 2 x {O.shape[1]} table, all models: it mixes models '
                                 'and ignores clustering, so it is descriptive only and not part of the gate',
                  'statistic_X': chi2, 'df': O.shape[1] - 1, 'p': chi2_sf(chi2, O.shape[1] - 1),
                  'tickets': int(O.sum())})
    rng_s = lambda k: np.random.default_rng((SEED_PERM, 10 + k))  # noqa: E731
    acct_model = (mx.model + ' | ' + mx.customer).to_numpy()
    am_levels = sorted(set(acct_model))
    am_idx = pd.Series(acct_model).map({v: i for i, v in enumerate(am_levels)}).to_numpy()
    s1 = AgeTest('S-A1 within model x account', young, s_idx, S, all_rows, Cf, PRIMARY, None, [], [], acc_idx, months,
                 support, n_perm, rng_s(1), perm_s_idx=am_idx,
                 perm_strata=sorted(set(am_idx[support[s_idx] & (tot > 0)])))
    both = pd.DataFrame({'am': am_idx, 'y': young, 't': tot})[tot > 0].groupby('am').agg(y=('y', 'max'),
                                                                                        o=('y', 'min'))
    informative = set(both.index[(both.y == 1) & (both.o == 0)])
    s1_tickets = float(tot[np.isin(am_idx, list(informative)) & support[s_idx]].sum())
    tests.append(s1.test_row(f'S-A1: permutation within model x account (strata with both age groups hold '
                             f'{s1_tickets:,.0f} of {prim.tickets:,} support tickets)'))
    extra_rows = s1.type_rows()
    for k, cut in ((2, 2.0), (3, 6.0)):
        yc = (mx.age_years < cut).to_numpy()
        M1c = np.bincount(s_idx[yc], weights=months[yc], minlength=S)
        M0c = np.bincount(s_idx[~yc], weights=months[~yc], minlength=S)
        supc = (M1c >= MIN_SUPPORT_MONTHS) & (M0c >= MIN_SUPPORT_MONTHS)
        tc_ = AgeTest(f'S-A2 cut at {cut:g} years', yc, s_idx, S, all_rows, Cf, PRIMARY, None, [], [], acc_idx,
                      months, supc, n_perm, rng_s(k), perm_strata=perm_models)
        tests.append(tc_.test_row(f'S-A2: under {cut:g} vs {cut:g}+ years, within model'))
        extra_rows += tc_.type_rows()
    old_inst = (mx.install_date < PERIOD_START).to_numpy()
    M1n = np.bincount(s_idx[young & old_inst], weights=months[young & old_inst], minlength=S)
    M0n = np.bincount(s_idx[~young & old_inst], weights=months[~young & old_inst], minlength=S)
    tn = AgeTest('S-A5 excluding new installs', young, s_idx, S, old_inst, Cf, PRIMARY, None, [], [], acc_idx, months,
                 (M1n >= MIN_SUPPORT_MONTHS) & (M0n >= MIN_SUPPORT_MONTHS), n_perm, rng_s(5),
                 perm_strata=perm_models)
    tests.append(tn.test_row('S-A5: excluding machines installed on or after 1 Aug 2025'))
    extra_rows += tn.type_rows()
    no_mn = [GROUPS.index(g) for g in COMPONENT]
    t6 = AgeTest('S-A6 without Monitoring and No Trouble Found', young, s_idx, S, all_rows, Cg[:, no_mn], COMPONENT,
                 None, [], [], acc_idx, months, support, n_perm, rng_s(6), perm_strata=perm_models)
    tests.append(t6.test_row('S-A6: 7 groups, without Monitoring and No Trouble Found'))
    extra_rows += t6.type_rows()
    t7 = AgeTest('S-A7 with Not categorised', young, s_idx, S, all_rows, Cg, GROUPS, None, [], [], acc_idx, months,
                 support, n_perm, rng_s(7), perm_strata=perm_models)
    tests.append(t7.test_row('S-A7: 10 groups, with Not categorised'))
    extra_rows += t7.type_rows()
    for k, (hname, th, mcol) in enumerate((('h1', h1_t, 'months_h1'), ('h2', h2_t, 'months_h2'))):
        Ch = counts(mx, th, 'group', GROUPS)[:, fam]
        th_ = AgeTest(f'S-A9 {hname}', young, s_idx, S, all_rows, Ch, PRIMARY, None, [], [], acc_idx,
                      mx[mcol].to_numpy(float), support, n_perm, rng_s(9 + k), perm_strata=perm_models)
        tests.append(th_.test_row(f'S-A9: {"first" if hname == "h1" else "second"} half only (age group as '
                                  'over the full period)'))
        extra_rows += th_.type_rows()

    # S-A4 Lexis split: machine-months and tickets by the machine's age at that moment.
    inst_d = mx.install_date
    bnd = inst_d + pd.to_timedelta(4 * 365.25, unit='D')
    st, en = mx.start, pd.Series(PERIOD_END, index=mx.index)
    my_ = FX.months_between(st, pd.concat([en, bnd], axis=1).min(axis=1).where(bnd > st, st))
    mo_ = FX.months_between(pd.concat([st, bnd], axis=1).max(axis=1), en)
    tl = tp.assign(b=tp.serial.map(dict(zip(mx.serial, bnd))))
    tl['y'] = tl.ts < tl.b
    Cy = counts(mx, tl[tl.y], 'group', GROUPS)[:, fam]
    Co = counts(mx, tl[~tl.y], 'group', GROUPS)[:, fam]
    aL, bL = tab(Cy, all_rows, s_idx, S), tab(Co, all_rows, s_idx, S)
    M1L = np.bincount(s_idx, weights=my_.to_numpy(float), minlength=S)
    M0L = np.bincount(s_idx, weights=mo_.to_numpy(float), minlength=S)
    supL = np.flatnonzero((M1L >= MIN_SUPPORT_MONTHS) & (M0L >= MIN_SUPPORT_MONTHS))
    srL = mh_share(aL[supL], bL[supL], aL[supL].sum(1), bL[supL].sum(1))
    check('S-A4: Lexis months add up to the exposure', float(months.sum()), float(my_.sum() + mo_.sum()), tol=1e-6)
    check('S-A4: Lexis tickets add up', float(tot.sum()), float(Cy.sum() + Co.sum()))
    for k, g in enumerate(PRIMARY):
        extra_rows.append({'variant': 'S-A4 Lexis split', 'level': 'group', 'type': g, 'group': g,
                           'under4_tickets': aL[supL, k].sum(), 'plus4_tickets': bL[supL, k].sum(),
                           'under4_share': aL[supL, k].sum() / aL[supL].sum(),
                           'plus4_share': bL[supL, k].sum() / bL[supL].sum(), 'share_ratio_mh': srL[k]})
    FACTS['lexis'] = {'support_models': len(supL), 'under4_months': float(my_.sum()), 'plus4_months': float(mo_.sum())}

    # S-A8 unlisted serials' tickets added to the 4+ group (strata: the ticket's model).
    u = unl[unl.group.isin(PRIMARY)]
    a8, b8 = prim.a.copy(), prim.b.copy()
    pos = {models[s]: i for i, s in enumerate(sup)}
    added = 0
    for (model, g), n in u.groupby(['model', 'group']).size().items():
        if model in pos:
            b8[pos[model], PRIMARY.index(g)] += n
            added += n
    sr8 = mh_share(a8, b8, a8.sum(1), b8.sum(1))
    for k, g in enumerate(PRIMARY):
        extra_rows.append({'variant': 'S-A8 unlisted tickets as 4+', 'level': 'group', 'type': g, 'group': g,
                           'under4_tickets': a8[:, k].sum(), 'plus4_tickets': b8[:, k].sum(),
                           'under4_share': a8[:, k].sum() / a8.sum(), 'plus4_share': b8[:, k].sum() / b8.sum(),
                           'share_ratio_mh': sr8[k]})
    FACTS['unlisted_added_to_4plus'] = {'tickets': int(added), 'unlisted_family_tickets': len(u)}
    tests.append({'variant': 'S-A4 Lexis split', 'description': 'S-A4: Lexis split (share ratios only; no test)'})
    tests.append({'variant': 'S-A8 unlisted tickets as 4+', 'description':
                  f'S-A8: {added:,} tickets on unlisted serials of support models added to 4+ (share ratios only)'})

    # S-A3 bands and S-A10 service status (descriptive)
    band_rows = []
    for band, gb in mx.groupby('age_band', observed=True):
        idx = gb.index.to_numpy()
        for j, g in enumerate(GROUPS + ['All unplanned tickets']):
            n = Cg[idx, j].sum() if j < 10 else alln[idx].sum()
            band_rows.append({'age_band': band, 'type': g, 'machines': len(idx), 'months': months[idx].sum(),
                              'tickets': n, 'rate_per_100': 100 * n / months[idx].sum(),
                              'share': n / alln[idx].sum()})
    bands = pd.DataFrame(band_rows)
    st_rows = []
    for (status, ag), gs in mx.groupby(['service_status', 'age_group']):
        idx = gs.index.to_numpy()
        n_all = alln[idx].sum()
        for j, g in enumerate(GROUPS):
            st_rows.append({'service_status': status, 'age_group': ag, 'type': g, 'machines': len(idx),
                            'months': months[idx].sum(), 'tickets': Cg[idx, j].sum(),
                            'share': Cg[idx, j].sum() / n_all if n_all else np.nan})
    status = pd.DataFrame(st_rows)

    # ------------------------------------------------------------- support table
    sp_rows = []
    for s in range(S):
        for a_i, lab in ((1, AGE_LABELS[0]), (0, AGE_LABELS[1])):
            sel_m = (s_idx == s) & (young if a_i else ~young)
            if not sel_m.any():
                continue
            sp_rows.append({'model': models[s], 'age_group': lab, 'machines': int(sel_m.sum()),
                            'ticketed_machines': int((sel_m & (alln > 0)).sum()),
                            'accounts': int(np.unique(acc_idx[sel_m]).size), 'months': months[sel_m].sum(),
                            'tickets': int(alln[sel_m].sum()), 'family_tickets': int(tot[sel_m].sum()),
                            'in_support': bool(support[s]),
                            'shown_by_model': s in shown})
    supp = pd.DataFrame(sp_rows)

    save(out, supp, PREFIX_A + 'support')
    save(out, rates, PREFIX_A + 'type_rates')
    adj = pd.DataFrame(adjusted + extra_rows)
    save(out, adj, PREFIX_A + 'type_adjusted')
    save(out, pd.DataFrame(tests), PREFIX_A + 'tests')
    save(out, decomp, PREFIX_A + 'decomposition')
    save(out, bym, PREFIX_A + 'by_model')
    save(out, byt, PREFIX_A + 'by_type')
    save(out, bands, PREFIX_A + 'band_rates')
    save(out, status, PREFIX_A + 'by_status')
    save(out, halves, PREFIX_A + 'halves')
    save(out, inst, PREFIX_A + 'install_year')
    save(out, inst_pooled, PREFIX_A + 'install_pooled')
    FACTS['part_a'] = {'global_X': prim.X, 'global_p': prim.p, 'global_p_mc_se': prim.p_se,
                       'global_pass': bool(prim.global_pass),
                       'groups_significant': [g for g, s in zip(PRIMARY, prim.sig) if s],
                       'categories_significant': [c for c, s in zip(cats, prim.sigc) if s],
                       'groups_estimable': [g for g, e in zip(PRIMARY, prim.est) if e],
                       'models_shown': [models[s] for s in shown],
                       'models_mix_differs': sorted(bym.model[bym.mix_differs].unique()),
                       'types_shown': sorted(byt.telemetry_type[byt.shown].unique()),
                       'types_mix_differs': sorted(byt.telemetry_type[byt.mix_differs.fillna(False)].unique()),
                       'extra_tickets': float(tot_row.extra_tickets),
                       'extra_within_model_age': float(tot_row.within_model_age_tickets),
                       'extra_model_mix': float(tot_row.model_mix_tickets),
                       'extra_outside_support': float(tot_row.outside_support_tickets),
                       'sensitivities': {x['variant']: {'p': x.get('p'), 'global_pass': x.get('global_pass'),
                                                        'groups_significant': x.get('groups_significant')}
                                         for x in tests}}
    return mx


# ----------------------------------------------------------------------------------------------------------------
# Part B machinery
# ----------------------------------------------------------------------------------------------------------------
def pair_class(ix, nx):
    """docs/09 §3.5: the first class that applies, for index/next rows given as Series."""
    mon = ix.monitoring.to_numpy(bool) | nx.monitoring.to_numpy(bool)
    ntf = (ix.ctype.to_numpy() == NTF) | (nx.ctype.to_numpy() == NTF)
    blank = ix.category.isna().to_numpy(bool) | nx.category.isna().to_numpy(bool)
    same = (ix.category.to_numpy() == nx.category.to_numpy()).astype(bool)
    same_g = (ix.cgroup.to_numpy() == nx.cgroup.to_numpy()).astype(bool)
    return np.select([mon, ntf.astype(bool), blank, same, same_g], CLASSES[:5], CLASSES[5])


def direction(i_flag, n_flag):
    i_flag, n_flag = np.asarray(i_flag, bool), np.asarray(n_flag, bool)
    return np.select([i_flag & n_flag, i_flag, n_flag], ['both', 'index only', 'follow-up only'], 'neither')


def gap_bin(days, bins):
    out = np.full(len(days), '', dtype=object)
    for lo, hi, lab in bins:
        sel = (days > lo) & (days <= hi) if lo > 0 else (days >= 0) & (days <= hi)
        out[sel] = lab
    return out


def simulate(n_i, a_i, b, cutoff, split, n_sim, rng, sampler=None, chunk=200):
    """Random-timing null (docs/09 §5 B4): each machine's n_i tickets uniform on its own window [a_i, b) (days).
    Returns per-machine expected eligible tickets and repeats (30 and 7 days), the same by half, and per-simulation
    fleet totals."""
    n_i, a_i = np.asarray(n_i, int), np.asarray(a_i, float)
    keys = ('elig', 'rep30', 'rep7', 'elig_h1', 'rep30_h1', 'elig_h2', 'rep30_h2')
    E = {k: np.zeros(len(n_i)) for k in keys}
    per_sim = {k: np.zeros(n_sim) for k in ('elig', 'rep30', 'rep7')}
    for n in sorted(set(n_i)):
        idx = np.flatnonzero(n_i == n)
        for c0 in range(0, len(idx), chunk):
            ix = idx[c0:c0 + chunk]
            U = rng.random((n_sim, len(ix), n))
            if sampler is None:
                t = a_i[ix][None, :, None] + U * (b - a_i[ix])[None, :, None]
            else:
                t = sampler(a_i[ix], U)
            t.sort(axis=-1)
            elig = t < cutoff
            h1 = t < split
            if n > 1:
                gap = np.diff(t, axis=-1)
                e_ = elig[..., :-1]
                r30 = e_ & (gap <= CUTOFF_DAYS)
                r7 = e_ & (gap <= SHORT_DAYS)
                h1_ = h1[..., :-1]
            else:
                r30 = r7 = h1_ = np.zeros((n_sim, len(ix), 0), bool)
            vals = {'elig': elig.sum(-1), 'rep30': r30.sum(-1), 'rep7': r7.sum(-1),
                    'elig_h1': (elig & h1).sum(-1), 'rep30_h1': (r30 & h1_).sum(-1),
                    'elig_h2': (elig & ~h1).sum(-1), 'rep30_h2': (r30 & ~h1_).sum(-1)}
            for k in keys:
                E[k][ix] = vals[k].mean(0)
            for k in per_sim:
                per_sim[k] += vals[k].sum(1)
    return E, per_sim


def label_permutation_null(machines, n_perm, rng):
    """docs/09 §12 amendment 1: [(labels, pair rows i, pair rows j)] per machine; each machine's labels permuted
    among its own tickets; returns the number of same-label pairs in each permutation."""
    null = np.zeros(n_perm)
    for labels, pi, pj in machines:
        perms = rng.permuted(np.tile(labels, (n_perm, 1)), axis=1)
        null += (perms[:, pi] == perms[:, pj]).sum(1)
    return null


def uniform_p(n_i, L_i, d):
    """Exact repeat probability per eligible ticket under the uniform own-window null: with the eligibility cutoff
    30 days before the window end, every eligible ticket has its whole d-day window inside the machine's window,
    so P(next ticket within d days) = 1 - (1 - d/L)^(n - 1), the same for every eligible ticket (= the ratio of
    expectations the simulation estimates)."""
    n_i, L_i = np.asarray(n_i, float), np.asarray(L_i, float)
    with np.errstate(invalid='ignore'):
        return np.where((n_i > 1) & (L_i > CUTOFF_DAYS), 1 - (1 - d / np.where(L_i > 0, L_i, 1)) ** (n_i - 1), 0.0)


def ratio_p(reps, null=1.0):
    """Two-sided bootstrap p for a ratio against 1: 2 x min(share <= 1, share >= 1), with +1 in each count."""
    reps = np.asarray(reps, float)
    reps = reps[~np.isnan(reps)]
    n = len(reps)
    if not n:
        return np.nan
    return float(min(1.0, 2 * min((np.sum(reps <= null) + 1) / (n + 1), (np.sum(reps >= null) + 1) / (n + 1))))


def part_b(out, sc, conn, m_all, m, W_seed, n_boot, n_perm, n_sim):
    print('Part B: repeat-contact pairings')
    base = pd.DataFrame({'serial': sc.machine_id, 'opened': sc.ts, 'case_id': sc.case_id, 'category': sc.category})
    rf = repeat_frame(base)
    e, rep, same, simul = repeat_summary(rf)
    pin('B0: eligible index tickets', 6665, len(e))
    pin('B0: repeats within 30 days', 1574, int(rep.sum()))
    pin('B0: same-Category repeats', 515, int(same.sum()))
    pin('B0: simultaneous follow-ups', 0, int(simul.sum()))
    sqlr = pd.read_sql(REPEAT_VIEW_SQL.format(src='service_cases'), conn).set_index('case_id')
    pe = e.assign(repeat_30=rep.astype(int), same_category_30=same.astype(int)).set_index('case_id')
    sq = sqlr.reindex(pe.index)
    check('B0: SQL and pandas: the same eligible tickets', len(sqlr), len(pe))
    check('B0: SQL and pandas agree ticket by ticket (repeat_30)', 0,
          int((sq.repeat_30.to_numpy() != pe.repeat_30.to_numpy()).sum()))
    check('B0: SQL and pandas agree ticket by ticket (same_category_30)', 0,
          int((sq.same_category_30.to_numpy() != pe.same_category_30.to_numpy()).sum()))
    gdiff = np.abs(sq.gap_days.to_numpy() - pe.gap.dt.total_seconds().to_numpy() / 86400)
    check('B0: SQL and pandas agree on the gap (days)', 0.0, float(np.nanmax(gdiff)), tol=1e-6)

    # Index and next ticket attributes, in repeat_frame's order.
    attrs = sc.set_index('case_id')
    rf = rf.assign(next_case=rf.groupby('serial', sort=False).case_id.shift(-1))
    ev = rf[rf.opened < CUTOFF].copy()
    ev['gap_days'] = ev.gap.dt.total_seconds() / 86400
    ev['repeat_30'] = rep.reindex(ev.index).astype(bool).to_numpy()
    ev['repeat_7'] = ev.repeat_30 & (ev.gap_days <= SHORT_DAYS)
    ix = attrs.reindex(ev.case_id)
    nx = attrs.reindex(ev.next_case)
    pairs = pd.DataFrame({
        'case_id': ev.case_id.to_numpy(), 'next_case_id': ev.next_case.to_numpy(),
        'machine_id': ev.serial.to_numpy(), 'customer': ix.customer.to_numpy(), 'model': ix.model.to_numpy(),
        'telemetry_type': ix.ttype.to_numpy(), 'opened_date': ev.opened.dt.strftime('%Y-%m-%d').to_numpy(),
        'index_group': ix.group.to_numpy(), 'index_category': ix.ctype.to_numpy(),
        'next_group': nx.group.to_numpy(), 'next_category': nx.ctype.to_numpy(),
        'index_monitoring': ix.monitoring.to_numpy(bool), 'next_monitoring': nx.monitoring.fillna(False).to_numpy(bool),
        'gap_days': ev.gap_days.to_numpy(), 'repeat_30': ev.repeat_30.to_numpy(), 'repeat_7': ev.repeat_7.to_numpy(),
        'same_category': (ix.category.to_numpy() == nx.category.to_numpy()) & ix.category.notna().to_numpy(),
        'half': np.where(ev.opened < SPLIT, 'h1', 'h2')})
    pairs['same_category'] = pairs.same_category & pairs.repeat_30
    cls = np.full(len(pairs), '', dtype=object)
    has_next = pairs.next_case_id.notna().to_numpy()
    cls[has_next] = pair_class(ix[has_next].reset_index(), nx[has_next].reset_index())
    pairs['pair_class'] = np.where(pairs.repeat_30, cls, '')
    pairs['monitoring_direction'] = np.where(pairs.repeat_30, direction(pairs.index_monitoring, pairs.next_monitoring),
                                             '')
    ntf_i = (pairs.index_category == NTF).to_numpy()
    ntf_n = (pairs.next_category == NTF).to_numpy()
    pairs['ntf_direction'] = np.where(pairs.repeat_30, direction(ntf_i, ntf_n), '')
    pairs['gap_bin'] = np.where(pairs.repeat_30, gap_bin(pairs.gap_days.to_numpy(), CLASS_BINS), '')
    check('B0: same-Category repeats in the pairs table', int(same.sum()), int(pairs.same_category.sum()))
    pin('B0: 7-day repeats; same Category within 7 days', (631, 221),
          (int(pairs.repeat_7.sum()), int((pairs.same_category & pairs.repeat_7).sum())))
    check('B3: every repeat has a class', 0, int((pairs.repeat_30 & (pairs.pair_class == '')).sum()))
    R = pairs[pairs.repeat_30]

    # ------------------------------------------------------------- B1 matrices
    mrows = []
    for win, sel in (('30 days', R), ('7 days', R[R.repeat_7])):
        for level, icol, ncol in (('group', 'index_group', 'next_group'), ('category', 'index_category',
                                                                            'next_category')):
            obs = sel.groupby([icol, ncol]).size()
            # within-model expectation: E_ij = sum_s R_si C_sj / N_s
            rs = sel.groupby(['model', icol]).size()
            cs = sel.groupby(['model', ncol]).size()
            ns = sel.groupby('model').size()
            expv = {}
            for (mdl, i), ri in rs.items():
                cj = cs.loc[mdl]
                for j, c in cj.items():
                    expv[(i, j)] = expv.get((i, j), 0.0) + ri * c / ns[mdl]
            rowtot = sel.groupby(icol).size()
            for (i, j), n in obs.items():
                mrows.append({'window': win, 'level': level, 'index_type': i, 'next_type': j, 'pairs': int(n),
                              'row_share': n / rowtot[i], 'row_pairs': int(rowtot[i]),
                              'expected_within_model': expv.get((i, j), np.nan),
                              'lift': n / expv[(i, j)] if expv.get((i, j), 0) > 0 else np.nan})
    matrix = pd.DataFrame(mrows)

    # ------------------------------------------------------------- B2 same Category by gap over all pairs
    ok = sc[(sc.ctype != NO_CAT) & ~sc.monitoring].sort_values(['machine_id', 'ts', 'case_id'])
    gaps, sames, mach = [], [], []
    for mid, g in ok.groupby('machine_id', sort=True):
        if len(g) < 2:
            continue
        tt = g.ts.to_numpy('datetime64[s]').astype(np.int64) / 86400
        cc = g.category.to_numpy()
        i, j = np.triu_indices(len(g), 1)
        gaps.append(tt[j] - tt[i])
        sames.append(cc[i] == cc[j])
        mach.append(np.full(len(i), mid, dtype=object))
    gaps, sames, mach = np.concatenate(gaps), np.concatenate(sames), np.concatenate(mach)
    gb = gap_bin(gaps, GAP_BINS)
    acct_of = sc.groupby('machine_id').customer.agg(lambda s: s.mode().iloc[0])
    model_of = sc.groupby('machine_id').model.agg(lambda s: s.mode().iloc[0])
    type_of = sc.groupby('machine_id').ttype.first()
    allpairs = pd.DataFrame({'machine_id': mach, 'gap_days': gaps, 'same': sames, 'bin': gb})
    allpairs['customer'] = allpairs.machine_id.map(acct_of)
    accts_b = sorted(sc.customer.unique())
    WB = FX.boot_weights(len(accts_b), n_boot, W_seed)
    a_idx = {a: i for i, a in enumerate(accts_b)}
    sg_rows = []
    for lo, hi, lab in GAP_BINS:
        sb = allpairs[allpairs.bin == lab]
        per_m = sb.groupby('machine_id').same.agg(['sum', 'size'])
        ai = sb.customer.map(a_idx).to_numpy()
        S_ = np.bincount(ai, weights=sb.same.to_numpy(float), minlength=len(accts_b))
        N_ = np.bincount(ai, minlength=len(accts_b)).astype(float)
        with np.errstate(divide='ignore', invalid='ignore'):
            sh_b = (WB @ S_) / (WB @ N_)
        lo_, hi_, _ = interval(sh_b)
        sg_rows.append({'gap_bin': lab, 'pairs': len(sb), 'same_category_pairs': int(sb.same.sum()),
                        'share_pairs': sb.same.mean(), 'share_lo': lo_, 'share_hi': hi_,
                        'machines': len(per_m), 'share_machines': (per_m['sum'] / per_m['size']).mean()})
    sgap = pd.DataFrame(sg_rows)
    near = allpairs[allpairs.gap_days <= CUTOFF_DAYS].groupby('machine_id').same.mean()
    far = allpairs[allpairs.gap_days > 90].groupby('machine_id').same.mean()
    pc = pd.concat([near.rename('near'), far.rename('far')], axis=1).dropna()
    pc['d'] = pc.near - pc.far
    pc['ai'] = pc.index.map(acct_of).map(a_idx)
    Dsum = np.bincount(pc.ai, weights=pc.d.to_numpy(), minlength=len(accts_b))
    Dn = np.bincount(pc.ai, minlength=len(accts_b)).astype(float)
    lo_, hi_, _ = interval((WB @ Dsum) / (WB @ Dn))
    FACTS['paired_contrast'] = {'machines': len(pc), 'mean_difference': float(pc.d.mean()), 'lo': lo_, 'hi': hi_,
                                'near_share_mean': float(pc.near.mean()), 'far_share_mean': float(pc.far.mean())}
    baseline_far = allpairs[allpairs.gap_days > 90]

    # Within-machine tests (B2): repeat pairs with both Categories recorded, neither Monitoring, on machines with
    # at least 2 such pairs.
    rr = R[(R.index_category != NO_CAT) & (R.next_category != NO_CAT) & ~R.index_monitoring & ~R.next_monitoring]
    cnt = rr.groupby('machine_id').size()
    use = rr[rr.machine_id.isin(cnt.index[cnt >= 2])].sort_values(['machine_id', 'case_id'])
    obs = int((use.index_category == use.next_category).sum())
    # (a) As written in docs/09 §5 B2: follow-up Categories shuffled among the machine's repeat pairs. A ticket that
    # is one pair's follow-up and the next pair's index can then be paired with itself, which inflates the null
    # (docs/09 §12, amendment 1); reported for the record only.
    rng = np.random.default_rng(SEED_SHUFFLE)
    null = np.zeros(n_perm)
    for mid, g in use.groupby('machine_id', sort=True):
        i_c, f_c = g.index_category.to_numpy(), g.next_category.to_numpy()
        perms = rng.permuted(np.tile(f_c, (n_perm, 1)), axis=1)
        null += (perms == i_c[None]).sum(1)
    p, se = perm_p(obs, null)
    # (b) Amendment 1: Category labels permuted among each machine's own tickets (recorded Category, not
    # Monitoring), opening times fixed, so the repeat pairs stay the same pairs of tickets. Null: the machine's
    # Categories come in random order; one-sided p for the number of same-Category repeat pairs.
    lab = sc[(sc.ctype != NO_CAT) & ~sc.monitoring & sc.machine_id.isin(set(use.machine_id))] \
        .sort_values(['machine_id', 'ts', 'case_id'])
    machines = []
    for mid, g in lab.groupby('machine_id', sort=True):
        pos = {c: i for i, c in enumerate(g.case_id)}
        u = use[use.machine_id == mid]
        machines.append((g.category.to_numpy(), u.case_id.map(pos).to_numpy(), u.next_case_id.map(pos).to_numpy()))
    null2 = label_permutation_null(machines, n_perm, np.random.default_rng((SEED_SHUFFLE, 1)))
    p2, se2 = perm_p(obs, null2)
    # (c) Sensitivity: only non-overlapping pairs (in time order, a pair is kept when neither ticket is in a pair
    # already kept), follow-up Categories shuffled among the machine's kept pairs.
    keep_rows = []
    for mid, g in use.groupby('machine_id', sort=True):
        seen = set()
        for r_ in g.sort_values('opened_date', kind='mergesort').itertuples():
            if r_.case_id not in seen and r_.next_case_id not in seen:
                keep_rows.append(r_.Index)
                seen.update((r_.case_id, r_.next_case_id))
    nov = use.loc[keep_rows]
    obs3 = int((nov.index_category == nov.next_category).sum())
    rng = np.random.default_rng((SEED_SHUFFLE, 2))
    null3 = np.zeros(n_perm)
    for mid, g in nov.groupby('machine_id', sort=True):
        perms = rng.permuted(np.tile(g.next_category.to_numpy(), (n_perm, 1)), axis=1)
        null3 += (perms == g.index_category.to_numpy()[None]).sum(1)
    p3, se3 = perm_p(obs3, null3)
    FACTS['shuffle'] = {'machines': int(use.machine_id.nunique()), 'pairs': len(use), 'observed_same': obs,
                        'observed_share': obs / len(use) if len(use) else np.nan,
                        'label_permutation': {'null_mean': float(null2.mean()),
                                              'null_p97_5': float(np.percentile(null2, 97.5)), 'p': p2,
                                              'p_mc_se': se2,
                                              'null_share': float(null2.mean() / len(use)) if len(use) else np.nan,
                                              'tickets_permuted': len(lab)},
                        'non_overlapping_followup_shuffle': {'pairs': len(nov), 'observed_same': obs3,
                                                             'null_mean': float(null3.mean()), 'p': p3,
                                                             'p_mc_se': se3},
                        'as_written_followup_shuffle': {'null_mean': float(null.mean()),
                                                        'null_p97_5': float(np.percentile(null, 97.5)), 'p': p,
                                                        'p_mc_se': se,
                                                        'null_share': float(null.mean() / len(use)) if len(use) else np.nan,
                                                        'note': 'pairs a ticket with itself; not used'}}

    # ------------------------------------------------------------- B3 classes by gap bin
    crows = []
    for lab in [b[2] for b in CLASS_BINS] + ['all repeats']:
        sb = R if lab == 'all repeats' else R[R.gap_bin == lab]
        for c in CLASSES:
            n = int((sb.pair_class == c).sum())
            crows.append({'gap_bin': lab, 'pair_class': c, 'pairs': n, 'share_of_bin': n / len(sb) if len(sb) else
                          np.nan, 'share_of_eligible': n / len(pairs), 'bin_pairs': len(sb)})
    for c, col in (('Monitoring involved', 'monitoring_direction'), ('No Trouble Found involved', 'ntf_direction')):
        for d, n in R[R.pair_class == c][col].value_counts().items():
            crows.append({'gap_bin': 'all repeats', 'pair_class': f'{c}: {d}', 'pairs': int(n),
                          'share_of_bin': n / len(R), 'share_of_eligible': n / len(pairs), 'bin_pairs': len(R)})
    classes = pd.DataFrame(crows)

    # ------------------------------------------------------------- B4 random-timing null
    mach_n = sc.groupby('machine_id').size()
    listed = m_all.set_index('serial_id')
    start = listed.start.reindex(mach_n.index)
    a_days = ((start.fillna(PERIOD_START) - PERIOD_START).dt.total_seconds() / 86400).to_numpy()
    is_listed = start.notna().to_numpy()
    b_days = (PERIOD_END - PERIOD_START).total_seconds() / 86400
    cut_days = (CUTOFF - PERIOD_START).total_seconds() / 86400
    split_days = (SPLIT - PERIOD_START).total_seconds() / 86400
    first_t = sc.groupby('machine_id').ts.min().reindex(mach_n.index)
    check('B4: every ticket lies in its machine window', 0,
          int((((first_t - PERIOD_START).dt.total_seconds() / 86400).to_numpy() < a_days - 1e-9).sum()))
    rng_sim = np.random.default_rng(SEED_SIM)
    Eu, Su = simulate(mach_n.to_numpy(), a_days, b_days, cut_days, split_days, n_sim, rng_sim)
    all_t = np.sort(((sc.ts - PERIOD_START).dt.total_seconds() / 86400).to_numpy())
    xs = np.concatenate([[0.0], all_t, [b_days]])
    ys = np.linspace(0, 1, len(xs))

    def calendar(a, U):
        Fa = np.interp(a, xs, ys)[None, :, None]
        return np.interp(Fa + U * (1 - Fa), ys, xs)

    Ec, Sc = simulate(mach_n.to_numpy(), a_days, b_days, cut_days, split_days, n_sim,
                      np.random.default_rng((SEED_SIM, 1)), sampler=calendar)
    Ef, Sf = simulate(mach_n.to_numpy(), np.zeros(len(mach_n)), b_days, cut_days, split_days, n_sim,
                      np.random.default_rng((SEED_SIM, 2)))
    obs_m = pairs.groupby('machine_id').agg(elig=('case_id', 'size'), rep30=('repeat_30', 'sum'),
                                            rep7=('repeat_7', 'sum')).reindex(mach_n.index).fillna(0)
    # Uniform nulls: exact p_i (uniform_p); the calendar-weighted null has no closed form and uses the simulation.
    L_own, L_full = b_days - a_days, np.full(len(mach_n), b_days)
    p30, p7 = uniform_p(mach_n, L_own, CUTOFF_DAYS), uniform_p(mach_n, L_own, SHORT_DAYS)
    p30f, p7f = uniform_p(mach_n, L_full, CUTOFF_DAYS), uniform_p(mach_n, L_full, SHORT_DAYS)
    p30h1 = p30h2 = p30
    with np.errstate(divide='ignore', invalid='ignore'):
        p30c = np.where(Ec['elig'] > 0, Ec['rep30'] / np.where(Ec['elig'] > 0, Ec['elig'], 1), 0.0)
        sim30 = Eu['rep30'].sum() / Eu['elig'].sum()
    exact30 = float((Eu['elig'] * p30).sum() / Eu['elig'].sum())
    check('B4: the simulation agrees with the exact uniform null (fleet, within 2% relative)', 0.0,
          abs(sim30 / exact30 - 1), tol=0.02)
    pmap = {k: dict(zip(mach_n.index, v)) for k, v in (('p30', p30), ('p7', p7), ('p30c', p30c), ('p30h1', p30h1),
                                                       ('p30h2', p30h2), ('p30f', p30f), ('p7f', p7f))}
    pairs['null_p30'] = pairs.machine_id.map(pmap['p30'])
    pairs['null_p7'] = pairs.machine_id.map(pmap['p7'])
    pairs['null_p30_calendar'] = pairs.machine_id.map(pmap['p30c'])
    pairs['null_p30_half'] = np.where(pairs.half == 'h1', pairs.machine_id.map(pmap['p30h1']),
                                      pairs.machine_id.map(pmap['p30h2']))
    nrows = []
    allm = np.ones(len(mach_n), bool)
    for variant, E_, S_, sel in (('own window, uniform', Eu, Su, allm),
                                 ('own window, calendar-weighted', Ec, Sc, allm),
                                 ('own window, uniform, listed machines only', Eu, None, is_listed),
                                 ('full period window, uniform', Ef, Sf, allm)):
        full = variant.startswith('full')
        for win, key, pk, ok_col in (('30 days', 'rep30', 'p30f' if full else ('p30c' if 'calendar' in variant
                                                                                else 'p30'), 'rep30'),
                                     ('7 days', 'rep7', 'p7f' if full else 'p7', 'rep7')):
            if 'calendar' in variant and win == '7 days':
                continue
            ids = mach_n.index[sel]
            o = obs_m.loc[ids, ok_col].sum()
            el = obs_m.loc[ids, 'elig'].sum()
            expct = float((obs_m.loc[ids, 'elig'] * pd.Series(pmap[pk]).reindex(ids)).sum())
            row = {'variant': variant, 'window': win, 'machines': int(sel.sum()), 'eligible': int(el),
                   'observed_repeats': int(o), 'observed_pct': 100 * o / el, 'expected_repeats': expct,
                   'null_pct': 100 * expct / el, 'observed_over_expected': o / expct,
                   'simulated_eligible_mean': float(E_['elig'][sel].sum()),
                   'simulated_repeats_mean': float(E_[key][sel].sum())}
            if S_ is not None:
                rate = S_[key] / S_['elig']
                row |= {'null_pct_sim_median': 100 * float(np.median(rate)),
                        'null_pct_sim_p2_5': 100 * float(np.percentile(rate, 2.5)),
                        'null_pct_sim_p97_5': 100 * float(np.percentile(rate, 97.5))}
            nrows.append(row)
    # high_ticket_machines.random_timing_followup (docs/05's helper: one common window, all tickets as the
    # denominator), re-run at 30 days for the record. docs/02 F2's 14.8% is the full-period window row above.
    med, lo_, hi_ = H.random_timing_followup(mach_n.to_numpy(), sc.ts.min(), sc.ts.max(), gap_days=CUTOFF_DAYS,
                                             n_sim=200)
    nrows.append({'variant': 'high_ticket_machines helper (docs/05): one common window, all tickets as denominator '
                             '(200 simulations)',
                  'window': '30 days', 'machines': len(mach_n), 'null_pct_sim_median': 100 * med,
                  'null_pct_sim_p2_5': 100 * lo_, 'null_pct_sim_p97_5': 100 * hi_})
    nulls = pd.DataFrame(nrows)
    fleet_oe = float(nulls.iloc[0].observed_over_expected)

    # ------------------------------------------------------------- B5 offenders, B6 class mix and matrices
    pairs['account_idx'] = pairs.customer.map(a_idx)
    O_all = np.bincount(pairs.account_idx, weights=pairs.repeat_30.astype(float), minlength=len(accts_b))
    E_all = np.bincount(pairs.account_idx, weights=pairs.null_p30.to_numpy(), minlength=len(accts_b))
    Ob, Eb = WB @ O_all, WB @ E_all
    fleet_b = Ob / Eb
    halves_fleet = {}
    for h in ('h1', 'h2'):
        sh = pairs[pairs.half == h]
        halves_fleet[h] = sh.repeat_30.sum() / sh.null_p30_half.sum()
    months_cut = FX.months_between(m.start, pd.Series(CUTOFF, index=m.index))
    m_listed = m.assign(months_to_cutoff=months_cut)
    listed_ids = set(m_listed.serial_id)

    def offenders(key, label, plural):
        n_el = pairs.groupby(key).size()
        big = n_el.index[(n_el >= MIN_ELIGIBLE) | (n_el.index.isin(NOT_TYPES) & (key == 'telemetry_type'))]
        unit = pairs[key].where(pairs[key].isin(big), f'Other {plural}')
        rows = []
        for u in sorted(unit.unique(), key=lambda v: (v.startswith('Other '), -int((unit == v).sum()), v)):
            g = pairs[unit == u]
            o, el = int(g.repeat_30.sum()), len(g)
            ex = float(g.null_p30.sum())
            Og = np.bincount(g.account_idx, weights=g.repeat_30.astype(float), minlength=len(accts_b))
            Eg = np.bincount(g.account_idx, weights=g.null_p30.to_numpy(), minlength=len(accts_b))
            Ng = np.bincount(g.account_idx, minlength=len(accts_b)).astype(float)
            with np.errstate(divide='ignore', invalid='ignore'):
                pct_b = 100 * (WB @ Og) / (WB @ Ng)
                oe_b = (WB @ Og) / (WB @ Eg)
                srr_b = oe_b / fleet_b
            plo, phi, _ = interval(pct_b)
            oelo, oehi, _ = interval(oe_b)
            n_acc_g = int(g.customer.nunique())
            if n_acc_g < MIN_FLOOR_ACCOUNTS:
                wlo, whi = wilson(o, el)
                plo, phi = min(plo, wlo), max(phi, whi)
            slo, shi, sund = interval(srr_b)
            srr = (o / ex) / fleet_oe if ex > 0 else np.nan
            per_m = g.groupby('machine_id').repeat_30.sum().sort_values(ascending=False, kind='mergesort')
            top_n = max(1, math.ceil(0.05 * len(per_m)))
            rr_ = g[g.repeat_30 & (g.index_category != NO_CAT) & (g.next_category != NO_CAT)
                    & ~g.index_monitoring & ~g.next_monitoring]
            bl = baseline_far[baseline_far.machine_id.isin(set(g.machine_id))]
            row = {label: u, 'pooled': u.startswith('Other '), 'eligible': el, 'machines': int(g.machine_id.nunique()),
                   'accounts': n_acc_g, 'tickets_per_machine': el / g.machine_id.nunique(), 'repeats_30': o,
                   'repeat_pct': 100 * o / el, 'repeat_pct_lo': plo, 'repeat_pct_hi': phi,
                   'repeats_7': int(g.repeat_7.sum()), 'repeat_7_pct': 100 * g.repeat_7.mean(),
                   'share_of_all_repeats': o / pairs.repeat_30.sum(), 'share_of_eligible': el / len(pairs),
                   'expected_repeats': ex, 'null_pct': 100 * ex / el, 'observed_over_expected': o / ex if ex else np.nan,
                   'observed_over_expected_lo': oelo, 'observed_over_expected_hi': oehi, 'srr': srr, 'srr_lo': slo, 'srr_hi': shi, 'srr_undefined_draws': sund, 'srr_p': ratio_p(srr_b),
                   'repeats_on_top5pct_machines_share': per_m.iloc[:top_n].sum() / o if o else np.nan,
                   'top5pct_machines': top_n,
                   'same_category_share_recorded_pairs': (rr_.index_category == rr_.next_category).mean()
                   if len(rr_) else np.nan, 'same_category_repeats_considered': len(rr_),
                   'baseline_same_share_over_90d': bl.same.mean() if len(bl) else np.nan,
                   'baseline_pairs': len(bl)}
            row['same_category_lift'] = row['same_category_share_recorded_pairs'] / row['baseline_same_share_over_90d'] \
                if row['baseline_same_share_over_90d'] else np.nan
            for h in ('h1', 'h2'):
                gh = g[g.half == h]
                eh = gh.null_p30_half.sum()
                row[f'srr_{h}'] = (gh.repeat_30.sum() / eh) / halves_fleet[h] if eh > 0 else np.nan
                row[f'eligible_{h}'] = len(gh)
            if label == 'model':                 # the pooled row: every listed model without a row of its own
                ml = m_listed[~m_listed.model.isin(big)] if row['pooled'] else m_listed[m_listed.model == u]
                rl = g[g.machine_id.isin(listed_ids & set(ml.serial_id))]
                mm = ml.months_to_cutoff.sum()
                row['repeats_per_100_months_listed'] = 100 * rl.repeat_30.sum() / mm if mm > 0 else np.nan
                row['listed_months_to_cutoff'] = mm
            rows.append(row)
        df = pd.DataFrame(rows)
        test = ~df.pooled & ~df[label].isin(NOT_TYPES)
        df['srr_q'] = np.nan
        if test.any():
            df.loc[test, 'srr_q'] = bh_q(df.loc[test, 'srr_p'])
        df['vs_fleet'] = np.select([(df.srr_lo > 1) & (df.srr_q < ALPHA), (df.srr_hi < 1) & (df.srr_q < ALPHA)],
                                   ['above', 'below'], 'in line')
        df.loc[df.pooled, 'vs_fleet'] = 'pooled (not tested)'
        df.loc[~df.pooled & ~test, 'vs_fleet'] = 'not a type (not tested)'
        return df, unit

    by_model, unit_m = offenders('model', 'model', 'models')
    by_type, unit_t = offenders('telemetry_type', 'telemetry_type', 'telemetry types')
    check('B5: model rows sum to the eligible tickets', len(pairs), int(by_model.eligible.sum()))
    check('B5: type rows sum to the eligible tickets', len(pairs), int(by_type.eligible.sum()))
    check('B5: model rows hold every listed machine-month to the cutoff', float(m_listed.months_to_cutoff.sum()),
          float(by_model.listed_months_to_cutoff.sum()), 1e-6)
    check('B5: rows that are not telemetry types stand alone, never pooled',
          sorted(set(pairs.telemetry_type) & set(NOT_TYPES)), sorted(set(by_type.telemetry_type) & set(NOT_TYPES)))

    irows = []
    for g_, gg in pairs.groupby('index_group'):
        el, o, o7 = len(gg), int(gg.repeat_30.sum()), int(gg.repeat_7.sum())
        Og = np.bincount(gg.account_idx, weights=gg.repeat_30.astype(float), minlength=len(accts_b))
        Ng = np.bincount(gg.account_idx, minlength=len(accts_b)).astype(float)
        with np.errstate(divide='ignore', invalid='ignore'):
            lo_, hi_, _ = interval(100 * (WB @ Og) / (WB @ Ng))
        ex = gg.null_p30.sum()
        irows.append({'index_group': g_, 'eligible': el, 'repeats_30': o, 'repeat_pct': 100 * o / el,
                      'repeat_pct_lo': lo_, 'repeat_pct_hi': hi_, 'repeats_7': o7, 'repeat_7_pct': 100 * o7 / el,
                      'null_pct': 100 * ex / el, 'observed_over_expected': o / ex if ex else np.nan,
                      'srr': (o / ex) / fleet_oe if ex else np.nan})
    itype = pd.DataFrame(irows)
    itype['o'] = itype.index_group.map({g: i for i, g in enumerate(GROUPS)})
    itype = itype.sort_values('o').drop(columns='o')

    def class_mix(unit, label, plural):
        rows = []
        Ru = R.assign(unit=unit[pairs.repeat_30.to_numpy()].to_numpy())
        cnt = Ru.groupby('unit').size()
        keep = cnt.index[(cnt >= MIN_REPEATS) | (cnt.index.isin(NOT_TYPES) & (label == 'telemetry_type'))]
        Ru['unit'] = Ru.unit.where(Ru.unit.isin(keep), f'Other {plural}')
        for u, g in Ru.groupby('unit'):
            for c in CLASSES:
                n = int((g.pair_class == c).sum())
                rows.append({label: u, 'repeats': len(g), 'pair_class': c, 'pairs': n, 'share': n / len(g)})
        return pd.DataFrame(rows)

    cmix = pd.concat([class_mix(unit_m, 'model', 'models').rename(columns={'model': 'unit'}).assign(unit_kind='model'),
                      class_mix(unit_t, 'telemetry_type', 'telemetry types').rename(columns={'telemetry_type': 'unit'})
                      .assign(unit_kind='telemetry type')], ignore_index=True)
    mm_rows = []
    for kind, key in (('model', 'model'), ('telemetry type', 'telemetry_type')):
        for u, g in R.groupby(key):
            for win, sel in (('30 days', g), ('7 days', g[g.repeat_7])):
                rowtot = sel.groupby('index_group').size()
                for (i, j), n in sel.groupby(['index_group', 'next_group']).size().items():
                    mm_rows.append({'unit_kind': kind, 'unit': u, 'window': win, 'index_group': i, 'next_group': j,
                                    'pairs': int(n), 'row_share': n / rowtot[i], 'row_pairs': int(rowtot[i]),
                                    'small_cell': n < 5})
    mmat = pd.DataFrame(mm_rows)

    pub_pairs = pairs.drop(columns=['account_idx'])
    save(out, pub_pairs, PREFIX_B + 'pairs')
    save(out, matrix, PREFIX_B + 'matrix')
    save(out, sgap, PREFIX_B + 'same_by_gap')
    save(out, classes, PREFIX_B + 'classes')
    save(out, itype, PREFIX_B + 'index_type')
    save(out, by_model, PREFIX_B + 'by_model')
    save(out, by_type, PREFIX_B + 'by_type')
    save(out, nulls, PREFIX_B + 'null')
    save(out, cmix, PREFIX_B + 'class_mix')
    save(out, mmat, PREFIX_B + 'model_matrices')
    FACTS['part_b'] = {
        'eligible': len(pairs), 'repeats_30': int(pairs.repeat_30.sum()), 'repeats_7': int(pairs.repeat_7.sum()),
        'same_category_30': int(pairs.same_category.sum()),
        'same_category_7': int((pairs.same_category & pairs.repeat_7).sum()),
        'fleet_null_pct_30': float(nulls.iloc[0].null_pct), 'fleet_observed_over_expected_30': fleet_oe,
        'fleet_null_pct_7': float(nulls.iloc[1].null_pct),
        'fleet_observed_over_expected_7': float(nulls.iloc[1].observed_over_expected),
        'high_ticket_helper_null_pct_30': 100 * med,
        'models_above': sorted(by_model.model[by_model.vs_fleet == 'above']),
        'models_below': sorted(by_model.model[by_model.vs_fleet == 'below']),
        'types_above': sorted(by_type.telemetry_type[by_type.vs_fleet == 'above']),
        'types_below': sorted(by_type.telemetry_type[by_type.vs_fleet == 'below']),
        'class_shares_30': {c: float((R.pair_class == c).mean()) for c in CLASSES},
        'class_shares_7': {c: float((R[R.repeat_7].pair_class == c).mean()) for c in CLASSES}}
    return pairs


# ----------------------------------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--xlsx', type=Path, default=common.XLS)
    ap.add_argument('--equipment', type=Path, default=common.EQUIPMENT)
    ap.add_argument('--fu-dir', type=Path, default=common.OUTPUTS / 'fu')
    ap.add_argument('--out', type=Path, default=OUT_DEFAULT)
    ap.add_argument('--n-boot', type=int, default=N_BOOT)
    ap.add_argument('--n-perm', type=int, default=N_PERM)
    ap.add_argument('--n-sim', type=int, default=N_SIM)
    ap.add_argument('--no-pins', action='store_true', help='skip the pins tied to the real export (fixture runs)')
    args = ap.parse_args(argv)
    t0 = time.time()
    PINS_ON['on'] = not args.no_pins
    warnings.filterwarnings('ignore', message='All-NaN slice encountered')  # undefined draws are counted instead
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    print('Copied code and the request-type reference')
    for name, same in copied_code_matches().items():
        check(f'copied verbatim: {name}', True, same)
    check('request_types_v0.csv hash (docs/09 §3.3)', REF_HASH, request_types_hash(REF))

    print('Loading inputs')
    raw, maps, cases, conn, sc, eq, m_all, t_all = load(args.xlsx, args.equipment, args.fu_dir)
    check('every unplanned ticket has a machine', 0, int(sc.machine_id.isna().sum()))
    m = FX.add_rate_groups(m_all[~m_all.third_party].copy().reset_index(drop=True))
    t = t_all[t_all.serial.isin(set(m.serial))].copy()
    t['serial_id'] = t.serial.map(dict(zip(m.serial, m.serial_id)))
    accounts = sorted(m.customer.unique())
    W = FX.boot_weights(len(accounts), args.n_boot, SEED_BOOT)
    in_period = sc[(sc.ts >= PERIOD_START) & (sc.ts < PERIOD_END)]
    unl = in_period[~in_period.serial.isin(set(m_all.serial))]
    if not args.no_pins:
        if not pins(sc, conn, m, t, FACTS['telemetry_map']):
            print('\nA pin failed: stopping before any new result.')
            return 1
        check('pin request types: no unmapped Trouble Code x Category combination', 0,
              FACTS['request_types']['unmapped_tickets'])
    part_a(out, m, t, unl, W, accounts, args.n_perm)
    part_b(out, sc, conn, m_all, m, SEED_BOOT, args.n_boot, args.n_perm, args.n_sim)

    print('Summary and privacy scan')
    summ = {'generated_by': 'verification/followups.py', 'protocol': 'docs/09_followups_protocol.md',
            'seeds': {'bootstrap': SEED_BOOT, 'permutation': SEED_PERM, 'simulation': SEED_SIM,
                      'shuffle': SEED_SHUFFLE},
            'n_boot': args.n_boot, 'n_perm': args.n_perm, 'n_sim': args.n_sim, 'pins_run': not args.no_pins,
            'definitions': {'young_bands': list(YOUNG_BANDS), 'groups': GROUPS, 'primary_family': PRIMARY,
                            'min_support_months': MIN_SUPPORT_MONTHS, 'min_estimable_tickets': MIN_EST_TICKETS,
                            'min_estimable_accounts': MIN_EST_ACCOUNTS, 'min_shown_tickets': MIN_SHOWN_TICKETS,
                            'min_eligible': MIN_ELIGIBLE, 'min_repeats_class_mix': MIN_REPEATS, 'alpha': ALPHA,
                            'gap_bins': [b[2] for b in GAP_BINS], 'classes': CLASSES,
                            'cutoff': str(CUTOFF.date()), 'split': str(SPLIT.date()),
                            'period': [str(PERIOD_START.date()), str((PERIOD_END - pd.Timedelta(days=1)).date())]},
            'facts': FACTS,
            'checks': {'pass': sum(c['status'] == 'PASS' for c in CHECKS),
                       'fail': sum(c['status'] != 'PASS' for c in CHECKS)}}
    text = json.dumps(jsonable(summ), indent=2)
    real = real_sets(maps, args.equipment)
    PUBLIC['summary.json'] = pd.DataFrame({'string': FX.json_strings(json.loads(text))})
    n_leaks = 0
    for name, df in PUBLIC.items():
        for col, n in FX.text_leaks(df, real).items():
            n_leaks += n
            print(f'    LEAK in {name}.{col}: {n} values')
    check('outputs and summary: no real name, address, serial, case, zip or phone', 0, n_leaks)
    ids = pd.concat([PUBLIC[PREFIX_B + 'pairs'][c].dropna() for c in ('case_id', 'next_case_id', 'machine_id',
                                                                       'customer')])
    check('per-ticket ids are pseudonyms', True, bool(ids.str.fullmatch(r'T\d{5}|S\d{5}|Customer \d{3,4}').all()))
    summ['checks'] = {'pass': sum(c['status'] == 'PASS' for c in CHECKS),
                      'fail': sum(c['status'] != 'PASS' for c in CHECKS), 'list': CHECKS}
    (out / 'followups_summary.json').write_text(json.dumps(jsonable(summ), indent=2) + '\n')
    print(f'  wrote {(out / "followups_summary.json").name}')
    fails = [c for c in CHECKS if c['status'] != 'PASS']
    print(f'\n{len(CHECKS) - len(fails)}/{len(CHECKS)} checks pass; {time.time() - t0:.0f} s')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
