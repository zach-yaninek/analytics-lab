"""Reconciliation: does this engine reproduce the numbers IPA has already seen, on the original two files?

The reference values are the aggregates committed under verification/outputs/ (fleet_exposure.py and followups.py
on the Aug 2025 - Aug 2026 case export and the 19 Oct 2026 equipment list), frozen in
ipa_trends/reference/reconcile_2025-08_2026-08.json by tests/build_reference.py. The engine is run five ways
(whole window; the two halves; monthly; install cohorts; install years) and every reference count, machine-month
and rate is compared. Intervals are compared only where the reference made them with the engine's rule
(fleet_exposure.group_rates): the rates by age band, family and model (R2, fx_*_rates.csv) and the under-4 and 4+
rates of ag_type_rates.csv (R3). ag_band_rates.csv (R4) and ag_install_pooled.csv (R8) are compared on counts,
machine-months and rates only: ag_install_pooled's intervals were made with association.ci (inverted-CDF
percentiles, no Byar widening), a different rule, and are not reproduced. The output holds counts and labels only,
so it is safe to paste back to the MIT team.

  ipa-trends reconcile --params params/reconcile_2025-08_2026-08.yaml [--deep]

Counts must match exactly; machine-months, rates and the compared intervals to a relative 1e-8 (the follow-up
tables were written with 10 significant digits). Intervals depend on the bootstrap draws, which depend on the
account order; they match only if the accounts are numbered exactly as the original pseudonyms, which this engine
reproduces.
"""
import json
import math
from pathlib import Path

import pandas as pd

from . import config as CFG

REFERENCE = Path(__file__).resolve().parent / 'reference' / 'reconcile_2025-08_2026-08.json'
RTOL = 1e-8


# ------------------------------------------------------------------------------------------------ reference
def build_reference(outputs):
    """Reference values from a verification/outputs folder (missing files are skipped)."""
    outputs = Path(outputs)
    ref = {'source': str(outputs.name)}
    s = outputs / 'fleet' / 'fx_summary.json'
    if s.exists():
        j = json.loads(s.read_text())
        ref['fleet'] = j['fleet']
        ref['third_party'] = j['third_party']
        m = j['match']
        ref['match'] = {'unplanned_in_window': m['unplanned tickets in period'],
                        'tickets_on_listed': m['unplanned tickets on listed machines'],
                        'unlisted_tickets': m['unplanned tickets on unlisted serials'],
                        'unlisted_serials': m['unlisted serials with unplanned tickets'],
                        'listed_machines': m['listed machines'], 'case_rows': m['ticket rows (all case types)'],
                        'tickets_before_install': m['tickets opened before the install date'],
                        'machines_start_at_pre_install_ticket': m['machines whose exposure starts at a pre-install '
                                                                    'ticket']}
        ref['unlisted_halves'] = j['unlisted']
    for name, file, key in (('age_rates', 'fleet/fx_age_rates.csv', 'age_band'),
                            ('family_rates', 'fleet/fx_family_rates.csv', 'family'),
                            ('model_rates', 'fleet/fx_model_rates.csv', 'model')):
        p = outputs / file
        if p.exists():
            d = pd.read_csv(p, keep_default_na=False)
            ref[name] = d[[key, 'machines', 'accounts', 'months', 'tickets', 'rate_per_100', 'ci_lo', 'ci_hi',
                           'ci_method']].rename(columns={key: 'stratum'}).to_dict('records')
    p = outputs / 'followups' / 'ag_type_rates.csv'
    if p.exists():
        ref['type_rates'] = pd.read_csv(p, keep_default_na=False).drop(
            columns=['rate_ratio', 'rate_ratio_lo', 'rate_ratio_hi', 'under4_share', 'plus4_share', 'share_ratio',
                     'share_ratio_lo', 'share_ratio_hi']).to_dict('records')
    p = outputs / 'followups' / 'ag_band_rates.csv'
    if p.exists():
        ref['band_rates'] = pd.read_csv(p, keep_default_na=False).to_dict('records')
    p = outputs / 'followups' / 'ag_install_pooled.csv'
    if p.exists():
        d = pd.read_csv(p, keep_default_na=False)
        ref['install_pooled'] = d[['category', 'unit', 'install', 'machines', 'months', 'tickets',
                                   'rate_per_100']].to_dict('records')
    s = outputs / 'followups' / 'followups_summary.json'
    if s.exists():
        f = json.loads(s.read_text())['facts']
        ref['definitions'] = {'request_types_hash': f['request_types']['hash'],
                              'unmapped_tickets': f['request_types']['unmapped_tickets'],
                              'monitoring_all_rows': f['monitoring_all_tickets']}
        ref['support_models'] = f['support']['support_models']
        ref['a6_categories'] = f.get('a6_categories')
    for name, file in (('unlisted_by_month', 'fleet/fx_unlisted_by_month.csv'),
                       ('case_monthly', 'repro_sql_case_monthly.csv')):
        p = outputs / file
        if p.exists():
            ref[name] = pd.read_csv(p, keep_default_na=False).to_dict('records')
    return ref


# ------------------------------------------------------------------------------------------------ engine runs
def _base(params, n_boot=2000):
    over = {k: v for k, v in params.items()}
    over.update({'DATA_START': '2025-08-01', 'DATA_END': '2026-08-31', 'LABEL_LAG_DAYS': 0, 'MAX_OPEN_SHARE': 1.0,
                 'MAX_BLANK_CATEGORY_SHARE': 1.0, 'MAX_UNMAPPED_SHARE': 1.0, 'UNMAPPED_POLICY': 'fallback',
                 'POOL_SMALL_STRATA': False, 'MAKE_CHARTS': False, 'MAKE_REPORT': False, 'N_BOOT': n_boot,
                 'SEED': 15072, 'THIRD_PARTY_PLANS': ['Vogeltronix'], 'MISSING_INSTALL_DATE': 'exclude'})
    return over


def engine_runs(params, support_models=None, say=print, n_boot=2000):
    """The five engine runs on the original files (publish=False). n_boot: 2000 as in the committed analysis."""
    from .engine import run
    base = _base(params, n_boot)
    runs = {}
    say('  run 1/5: whole window, by model, family, age band and age group')
    runs['whole'] = run({**base, 'PERIOD_EDGES': ['2025-08-01', '2026-09-01'],
                         'STRATIFY_BY': ['model', 'family', 'age_band', 'age_group'],
                         'CATEGORY_DIMS': ['fleet', 'age_group']}, publish=False, verbose=False)
    say('  run 2/5: the two halves')
    runs['halves'] = run({**base, 'PERIOD_EDGES': ['2025-08-01', '2026-02-15', '2026-09-01'], 'STRATIFY_BY': [],
                          'CATEGORY_DIMS': ['fleet']}, publish=False, verbose=False)
    say('  run 3/5: monthly')
    runs['monthly'] = run({**base, 'RERUN_FREQUENCY': 'monthly', 'STRATIFY_BY': [], 'CATEGORY_DIMS': ['fleet']},
                          publish=False, verbose=False)
    if support_models:
        cohort = {**base, 'PERIOD_EDGES': ['2025-08-01', '2026-09-01'], 'STRATIFY_BY': ['install_cohort'],
                  'CATEGORY_DIMS': ['fleet', 'install_cohort'], 'MODEL_FILTER': list(support_models)}
        say('  run 4/5: install cohorts on the support models')
        runs['cohorts'] = run({**cohort, 'INSTALL_COHORT_EDGES': ['2016-01-01', '2019-01-01', '2022-01-01',
                                                                  '2024-01-01', '2027-01-01']},
                              publish=False, verbose=False)
        say('  run 5/5: install years on the support models')
        runs['years'] = run({**cohort, 'INSTALL_COHORT_WIDTH': '1 year', 'INSTALL_COHORT_START': '1990-01-01'},
                            publish=False, verbose=False)
    return runs


# ------------------------------------------------------------------------------------------------ comparison
class Tally:
    def __init__(self):
        self.rows = []

    def add(self, target, item, expected, actual, kind='value'):
        if expected is None or (isinstance(expected, float) and math.isnan(expected)):
            ok = actual is None or (isinstance(actual, float) and math.isnan(actual))
        elif isinstance(expected, str):
            ok = str(actual) == expected
        elif kind == 'count':
            ok = actual is not None and float(actual) == float(expected)
        else:
            ok = actual is not None and not (isinstance(actual, float) and math.isnan(actual)) \
                and math.isclose(float(actual), float(expected), rel_tol=RTOL, abs_tol=1e-12)
        self.rows.append({'target': target, 'item': item, 'expected': expected, 'actual': actual, 'kind': kind,
                          'ok': bool(ok)})
        return ok


def _rate_rows(result, dim, key, period_pos=0):
    r = result.tables['rates']
    return r[(r.stratum_dim == dim) & (r.issue_key == key) & (r.period_pos == period_pos)].set_index('stratum')


def compare(ref, runs):
    t = Tally()
    w = runs.get('whole')
    if w is not None and 'fleet' in ref:
        f, pf = ref['fleet'], w.facts['population']
        fl = _rate_rows(w, 'fleet', 'all').iloc[0]
        t.add('R1 fleet', 'machines', f['machines'], pf['population_machines'], 'count')
        t.add('R1 fleet', 'machines exposed', f['machines_exposed'], pf['machines_exposed'], 'count')
        t.add('R1 fleet', 'accounts', f['accounts'], w.facts['clusters'], 'count')
        t.add('R1 fleet', 'machine-months', f['months'], pf['population_months'])
        t.add('R1 fleet', 'tickets', f['tickets'], pf['population_tickets'], 'count')
        t.add('R1 fleet', 'rate per 100', f['rate_per_100'], fl.rate_per_100)
        t.add('R1 fleet', 'machines with a ticket', f['machines_with_ticket'], fl.machines_with_ticket, 'count')
        t.add('R1 fleet', 'zero-month machines', f['machines_zero_months'], pf['zero_month_machines'], 'count')
        tp = ref['third_party']
        t.add('R1 third party', 'machines', tp['machines'], pf['third_party_machines'], 'count')
        t.add('R1 third party', 'tickets', tp['tickets'], pf['third_party_tickets'], 'count')
        for k, v in ref['match'].items():
            if k == 'case_rows':
                t.add('R1 match', k, v, w.facts['tickets']['case_rows'], 'count')
            elif k in pf:
                t.add('R1 match', k, v, pf[k], 'count')
    for name, dim in (('age_rates', 'age_band'), ('family_rates', 'family'), ('model_rates', 'model')):
        if w is None or name not in ref:
            continue
        mine = _rate_rows(w, dim, 'all')
        for row in ref[name]:
            s = str(row['stratum'])
            m = mine.loc[s] if s in mine.index else None
            for col in ('machines', 'accounts', 'tickets'):
                t.add(f'R2 {name}', f'{s} {col}', row[col], None if m is None else m[col], 'count')
            for col, mcol in (('months', 'machine_months'), ('rate_per_100', 'rate_per_100')):
                t.add(f'R2 {name}', f'{s} {col}', row[col], None if m is None else m[mcol])
            for col in ('ci_lo', 'ci_hi'):
                t.add(f'R2 {name} intervals', f'{s} {col}', row[col], None if m is None else m[col], 'interval')
            t.add(f'R2 {name} intervals', f'{s} ci_method', row['ci_method'], None if m is None else m.ci_method)
    if w is not None and 'type_rates' in ref:
        cat = w.tables['rates'][['issue_key', 'issue_level', 'issue_group', 'issue']].drop_duplicates()
        for row in ref['type_rates']:
            level, name, grp = row['level'], row['type'], row['group']
            sel = cat[(cat.issue_level == level) & (cat.issue == name) & ((cat.issue_group == grp) | (level != 'category'))]
            key = sel.issue_key.iloc[0] if len(sel) else None
            mine = _rate_rows(w, 'age_group', key) if key else pd.DataFrame()
            for lab, pre in (('Under 4', 'under4'), ('4+', 'plus4')):
                m = mine.loc[lab] if lab in mine.index else None
                t.add('R3 ag_type_rates', f'{name} {lab} tickets', row[f'{pre}_tickets'],
                      None if m is None else m.tickets, 'count')
                t.add('R3 ag_type_rates', f'{name} {lab} months', row[f'{pre}_months'],
                      None if m is None else m.machine_months)
                t.add('R3 ag_type_rates', f'{name} {lab} rate', row[f'{pre}_rate_per_100'],
                      None if m is None else m.rate_per_100)
                for c in ('lo', 'hi'):
                    t.add('R3 ag_type_rates intervals', f'{name} {lab} rate_{c}', row[f'{pre}_rate_{c}'],
                          None if m is None else m[f'ci_{c}'], 'interval')
    if w is not None and 'band_rates' in ref:
        for row in ref['band_rates']:
            name = row['type']
            key = 'all' if name == 'All unplanned tickets' else f'group|{name}'
            mine = _rate_rows(w, 'age_band', key)
            s = str(row['age_band'])
            m = mine.loc[s] if s in mine.index else None
            t.add('R4 ag_band_rates', f'{s} {name} machines', row['machines'], None if m is None else m.machines, 'count')
            t.add('R4 ag_band_rates', f'{s} {name} tickets', row['tickets'], None if m is None else m.tickets, 'count')
            t.add('R4 ag_band_rates', f'{s} {name} months', row['months'], None if m is None else m.machine_months)
            t.add('R4 ag_band_rates', f'{s} {name} rate', row['rate_per_100'], None if m is None else m.rate_per_100)
    h = runs.get('halves')
    if h is not None and 'fleet' in ref:
        for pos, half in ((0, 'h1'), (1, 'h2')):
            m = _rate_rows(h, 'fleet', 'all', pos).iloc[0]
            t.add('R5 halves', f'{half} tickets', ref['fleet'][f'tickets_{half}'], m.tickets, 'count')
            t.add('R5 halves', f'{half} rate', ref['fleet'][f'rate_{half}'], m.rate_per_100)
            dq = h.tables['data_quality'].iloc[pos]
            if 'unlisted_halves' in ref:
                t.add('R5 halves', f'{half} unlisted tickets', ref['unlisted_halves'][f'tickets_{half}'],
                      dq.unlisted_tickets, 'count')
    mo = runs.get('monthly')
    if mo is not None:
        dq = mo.tables['data_quality'].assign(month=lambda d: d.period_key.str[:7]).set_index('month')
        for row in ref.get('unlisted_by_month', []):
            m = dq.loc[row['month']] if row['month'] in dq.index else None
            t.add('R6 monthly', f"{row['month']} unplanned", row['tickets'], None if m is None else m.unplanned, 'count')
            t.add('R6 monthly', f"{row['month']} unlisted", row['unlisted'], None if m is None else m.unlisted_tickets,
                  'count')
        for row in ref.get('case_monthly', []):
            m = dq.loc[row['month']] if row['month'] in dq.index else None
            t.add('R6 monthly', f"{row['month']} all case rows", row['all_tickets'],
                  None if m is None else m.case_rows, 'count')
    if w is not None and 'definitions' in ref:
        d, tf = ref['definitions'], w.facts['tickets']
        t.add('R7 definitions', 'request-type reference hash', d['request_types_hash'], tf['request_types_hash'])
        t.add('R7 definitions', 'unmapped tickets', d['unmapped_tickets'], tf['unmapped_tickets'], 'count')
        t.add('R7 definitions', 'monitoring templates (all rows)', d['monitoring_all_rows'], tf['monitoring_all_rows'],
              'count')
    for unit, run_name in (('cohort', 'cohorts'), ('year', 'years')):
        rr = runs.get(run_name)
        if rr is None or 'install_pooled' not in ref:
            continue
        cat = rr.tables['rates'][['issue_key', 'issue']].drop_duplicates()
        for row in [x for x in ref['install_pooled'] if x['unit'] == unit]:
            name = row['category']
            key = 'all' if name == 'All unplanned tickets' else \
                (cat[cat.issue == name].issue_key.iloc[0] if (cat.issue == name).any() else None)
            mine = _rate_rows(rr, 'install_cohort', key) if key else pd.DataFrame()
            s = str(row['install'])
            m = mine.loc[s] if s in mine.index else None
            if m is None and row['tickets'] == 0 and row['machines'] == 0:
                continue
            t.add(f'R8 install_pooled ({unit})', f'{s} {name} machines', row['machines'],
                  None if m is None else m.machines, 'count')
            t.add(f'R8 install_pooled ({unit})', f'{s} {name} tickets', row['tickets'],
                  None if m is None else m.tickets, 'count')
            t.add(f'R8 install_pooled ({unit})', f'{s} {name} months', row['months'],
                  None if m is None else m.machine_months)
            t.add(f'R8 install_pooled ({unit})', f'{s} {name} rate', row['rate_per_100'],
                  None if m is None else m.rate_per_100)
    return t


def report(t, out=print):
    df = pd.DataFrame(t.rows)
    if df.empty:
        out('No reference values to compare.')
        return False
    by = df.groupby('target').ok.agg(['sum', 'size'])
    out('Reconciliation against the numbers IPA has seen (counts and labels only):')
    for target, r in by.iterrows():
        out(f"  {'PASS' if r['sum'] == r['size'] else 'FAIL'}  {target:<34} {int(r['sum'])}/{int(r['size'])} match")
    bad = df[~df.ok]
    for r in bad.head(40).itertuples():
        out(f'    differs: {r.target} | {r.item}: expected {r.expected}, got {r.actual}')
    if len(bad) > 40:
        out(f'    ... and {len(bad) - 40} more')
    values_ok = bad[bad.kind != 'interval'].empty
    with_iv = sorted({str(x).split()[0] for x in df.target[df.kind == 'interval']})   # R2, R3: the others have none
    intervals = (f'intervals compared ({", ".join(with_iv)}): '
                 f'{"all match" if bad[bad.kind == "interval"].empty else "differ (see above)"}'
                 if with_iv else 'no intervals compared')
    out(f'Values (counts, machine-months, rates): {"all match" if values_ok else "DIFFERENCES"}; {intervals}; '
        f'{int(df.ok.sum())}/{len(df)} in all.')
    return bad.empty


def main(args):
    P = CFG.load_file(args.params) if args.params else {}
    P.update(CFG.parse_sets(args.set))
    ref = json.loads(REFERENCE.read_text(encoding='utf-8'))
    print('Running the engine on the original files (about 1-2 minutes)...')
    runs = engine_runs(P, ref.get('support_models'))
    w = runs['whole']
    case = w.facts['inputs']['case_export']
    expected_sha = ref.get('inputs', {}).get('case_export_sha256')
    print(f"Case export: {case['file']} (content fingerprint {case.get('content_fingerprint')}; "
          f"{'same bytes as the committed analysis' if case['sha256'] == expected_sha else 'bytes differ from the committed analysis (an Excel re-save changes them; the values below decide)'})")
    print(f"Bootstrap weights fingerprint: {w.facts['bootstrap_weights_fingerprint']} "
          f"({w.facts['clusters']} accounts, 2000 draws, seed 15072)")
    ok = report(compare(ref, runs))
    if getattr(args, 'deep', False):
        ok &= deep(P)
    return 0 if ok else 1


def deep(params):
    """MIT side: the engine's machine frame against verification/fleet_exposure.machine_frame, machine by machine."""
    import sys
    root = Path(__file__).resolve().parents[2]
    if not (root / 'verification').exists():
        print('--deep needs verification/ (the MIT repository)')
        return True
    sys.path.insert(0, str(root / 'verification'))
    sys.path.insert(0, str(root / 'trends' / 'tests'))
    import test_parity
    P = CFG.resolve(_base(params))
    from . import inputs as INP
    case, snaps = INP.find_inputs(P, INP.Warnings())
    res = test_parity.machine_frame_parity(case, snaps[-1][1], snaps[-1][0])
    for name, ok in res:
        print(f"  {'PASS' if ok else 'FAIL'}  deep: {name}")
    return all(ok for _, ok in res)
