"""Clean-room reproduction of the Excel-only results in Zac's service-ticket notebook.

Clean-room rules followed here:
  * Only the notebook's method text and printed outputs (data/derived/notebook_methods_only.md)
    were used as the specification. Zac's code (the .ipynb / notebook_dump.md) was not read.
  * From verification/common.py only load_raw(), clean() and build_maps() (customer / case
    pseudonyms) are used. The case fields, service groups and every table are re-derived
    here in pandas directly from the raw workbook columns.

Where the method text is ambiguous, the most literal reading is the headline value and each
alternative reading is computed in repro_clean_alternatives.csv with its numeric effect.

Privacy: outputs contain only pseudonyms (Customer NNN), generic labels (models, trouble
codes/categories, record types, statuses) and aggregate counts. Raw account names, serials,
case numbers and free text stay in memory.

Run:    cd /home/user/analytics-lab && python3 -I verification/reproduce_cleanroom.py
Writes: verification/outputs/repro_clean_*.csv (one per table) and repro_clean_claims.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hashlib

import numpy as np
import pandas as pd

from common import XLS, build_maps, clean, load_raw

OUT = Path(__file__).resolve().parent / 'outputs'
OUT.mkdir(parents=True, exist_ok=True)
PREFIX = 'repro_clean_'

claims = []
alternatives = []


# ----------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------
def nz(x):
    """clean() made NaN-safe.

    pandas 3 reads blank workbook cells into str-dtype columns as NaN, and clean(NaN) would
    return the literal string 'nan'. The method text says blank strings are missing, so NaN,
    None and whitespace-only strings all become None here.
    """
    if x is None or (not isinstance(x, str) and pd.isna(x)):
        return None
    return clean(x)


def pct(n, d, nd=2):
    return round(100.0 * n / d, nd)


def fmt(v):
    if isinstance(v, (float, np.floating)):
        return f'{float(v):.2f}'
    if isinstance(v, (np.integer,)):
        return str(int(v))
    return str(v)


def claim(cid, section, description, zac, ours, note='', tol=0.006, status=None):
    """Record one comparison. Numbers match within `tol` (printed values are rounded)."""
    if status is None:
        try:
            status = 'match' if abs(float(zac) - float(ours)) <= tol else 'mismatch'
        except (TypeError, ValueError):
            status = 'match' if str(zac) == str(ours) else 'mismatch'
    claims.append({'claim_id': cid, 'notebook_section': section, 'description': description,
                   'zac_value': fmt(zac), 'our_value': fmt(ours), 'status': status, 'note': note})
    return status


def alt(topic, reading, metric, literal_value, alt_value, note=''):
    alternatives.append({'topic': topic, 'alternative_reading': reading, 'metric': metric,
                         'literal_value': fmt(literal_value), 'alternative_value': fmt(alt_value),
                         'delta': fmt(alt_value - literal_value) if isinstance(literal_value, (int, float, np.number))
                         and isinstance(alt_value, (int, float, np.number)) else '',
                         'note': note})


def save(df, name):
    df.to_csv(OUT / f'{PREFIX}{name}.csv', index=False)


def compare_table(cid_prefix, section, ours, zac_rows, key, cols, label):
    """Compare a printed top-N table row by row (key-aligned) and also its ordering."""
    ours_idx = ours.set_index(key)
    for zr in zac_rows:
        k = zr[key]
        for c in cols:
            if k not in ours_idx.index:
                claim(f'{cid_prefix}.{k}.{c}', section, f'{label} {k}: {c}', zr[c], 'absent', 'row not found')
                continue
            claim(f'{cid_prefix}.{k}.{c}', section, f'{label} {k}: {c}', zr[c], ours_idx.loc[k, c])
    zac_order = [zr[key] for zr in zac_rows]
    our_order = list(ours[key].head(len(zac_rows)))
    claim(f'{cid_prefix}.order', section, f'{label}: top-{len(zac_rows)} ordering',
          ' > '.join(map(str, zac_order)), ' > '.join(map(str, our_order)))


# ----------------------------------------------------------------------------------------
# 0. Load and derive case fields directly from the raw workbook columns
# ----------------------------------------------------------------------------------------
raw = load_raw()
maps = build_maps(raw)

digest = hashlib.sha256(Path(XLS).read_bytes()).hexdigest()
claim('0.workbook_sha256', 'Cell 2', 'Workbook checksum (Zac prints "Verified original" only; his hash '
      'is not shown in the method text)', 'Verified original (hash not printed)', digest[:12] + '...',
      'Method text prints no hash, so this cannot be compared clean-room. Every Excel count below '
      'nevertheless reproduces, so the content Zac analysed matches this file on every printed measure.',
      status='not_reproducible')

c = pd.DataFrame({
    'case_number': raw['Case Number'].map(nz),        # in memory only
    'account': raw['Account Name'].map(nz),           # in memory only
    'serial': raw['Serial #'].map(nz),                # in memory only
    'model': raw['Model #'].map(nz),
    'record_type': raw['Case Record Type'].map(nz),
    'status': raw['Status'].map(nz),
    'trouble_code': raw['Trouble Code'].map(nz),
    'category': raw['Trouble Code Category'].map(nz),
    'subcategory': raw['Trouble Code Sub Category'].map(nz),
    'reported': raw['Trouble Reported'].map(nz),      # in memory only
    'resolution': raw['Trouble Resolution'].map(nz),  # in memory only
})
c['case_id'] = c['case_number'].map(maps['case'])
c['customer'] = c['account'].map(maps['account'])
c['opened'] = pd.to_datetime(raw['Date/Time Opened'])
c['month'] = c['opened'].dt.strftime('%Y-%m')
N = len(c)
assert c['case_id'].notna().all() and c['customer'].notna().all()

# ----------------------------------------------------------------------------------------
# 1.1 Record counts
# ----------------------------------------------------------------------------------------
S = '1.1 unit of analysis (Cell 11)'
rc = pd.DataFrame([{
    'cases': N, 'distinct_cases': c['case_number'].nunique(), 'customers': c['account'].nunique(),
    'case_machines': c['serial'].nunique(), 'models': c['model'].nunique(),
    'first_opened': c['opened'].min().strftime('%Y-%m-%d %H:%M:%S'),
    'last_opened': c['opened'].max().strftime('%Y-%m-%d %H:%M:%S')}])
save(rc, 'record_counts')
zac_rc = {'cases': 7471, 'distinct_cases': 7471, 'customers': 845, 'case_machines': 3773, 'models': 31,
          'first_opened': '2025-08-01 07:22:00', 'last_opened': '2026-08-31 17:45:00'}
for k, v in zac_rc.items():
    claim(f'1.1.{k}', S, f'Record counts: {k}', v, rc.loc[0, k])
# Alternative identifier normalisation (case-fold + internal whitespace collapse)
norm = lambda s: s.map(lambda x: None if x is None else ' '.join(x.split()).casefold())
for col, lab in [('account', 'customers'), ('serial', 'case_machines'), ('model', 'models')]:
    alt('1.1 identifiers', 'case-fold and collapse internal whitespace instead of strip-only', lab,
        int(c[col].nunique()), int(norm(c[col]).nunique()), 'Text says only whitespace is stripped.')

# ----------------------------------------------------------------------------------------
# 1.2 Field completeness and hierarchy ambiguity
# ----------------------------------------------------------------------------------------
S = '1.2 field availability (Cell 13)'
fields = [('Trouble Reported', 'reported'), ('Model #', 'model'), ('Trouble Code', 'trouble_code'),
          ('Trouble Code Category', 'category'), ('Trouble Code Sub Category', 'subcategory'),
          ('Trouble Resolution', 'resolution')]
fc = pd.DataFrame([{'field': f, 'missing': int(c[col].isna().sum()), 'missing_pct': pct(c[col].isna().sum(), N)}
                   for f, col in fields])
save(fc, 'field_completeness')
zac_fc = {'Trouble Reported': (0, 0.00), 'Model #': (0, 0.00), 'Trouble Code': (101, 1.35),
          'Trouble Code Category': (330, 4.42), 'Trouble Code Sub Category': (2315, 30.99),
          'Trouble Resolution': (641, 8.58)}
for f, (m, p) in zac_fc.items():
    row = fc.set_index('field').loc[f]
    claim(f'1.2.missing.{f}', S, f'{f}: missing rows', m, int(row['missing']))
    claim(f'1.2.missing_pct.{f}', S, f'{f}: missing %', p, float(row['missing_pct']))
# Alternative: raw NaN only (no blank-string rule). The workbook has no blank / whitespace-only
# strings in these fields, so the blank-string rule has no effect.
for f, col in fields:
    alt('1.2 completeness', 'count only empty cells (ignore blank-string rule)', f'{f} missing',
        int(c[col].isna().sum()), int(raw[f].isna().sum()))

# Code / subcategory combinations that span more than one recorded category.
hier = c[c['trouble_code'].notna() & c['subcategory'].notna()]
combos = (hier.groupby(['trouble_code', 'subcategory'])
          .agg(categories=('category', 'nunique'),
               category_values=('category', lambda s: ','.join(sorted(s.dropna().unique()))),
               cases=('case_id', 'size'), cases_with_category=('category', 'count'))
          .reset_index())
multi = combos[combos['categories'] > 1].sort_values(['cases', 'trouble_code', 'subcategory'],
                                                      ascending=[False, True, True]).reset_index(drop=True)
save(multi, 'hierarchy_multicategory_combos')
claim('1.2.multicategory_combos', S, 'Code/subcategory combinations spanning >1 recorded category', 6, len(multi))
zac_combo = [('Electronics', 'Replacement', 5, 'Power Supply,Decoder,Touchscreen,Computer Board,Camera', 292),
             ('Electro/Mechanical', 'Home Switch/Adjustment', 2, 'Packer,SAM', 125),
             ('Electro/Mechanical', 'Lock Adjustment', 2, 'Service Door,Deposit Door', 57),
             ('Electronics', 'Training', 2, 'Loader Board,Touchscreen', 25),
             ('Electro/Mechanical', 'Training', 5, 'User Door,Main Door,Counterweight System,Service Door,Deposit Door', 21),
             ('Software', 'End User', 2, 'Credit Issues,Training', 11)]
mi = multi.set_index(['trouble_code', 'subcategory'])
for tc, sc, ncat, vals, ncase in zac_combo:
    key = f'{tc} / {sc}'
    if (tc, sc) not in mi.index:
        claim(f'1.2.combo.{key}', S, f'Combo {key}', ncase, 'absent')
        continue
    r = mi.loc[(tc, sc)]
    claim(f'1.2.combo.{key}.categories', S, f'Combo {key}: distinct categories', ncat, int(r['categories']))
    claim(f'1.2.combo.{key}.category_values', S, f'Combo {key}: category set (order-insensitive)',
          ','.join(sorted(vals.split(','))), r['category_values'],
          'Zac lists values in an unsorted (first-seen) order; compared as sets.')
    claim(f'1.2.combo.{key}.cases', S, f'Combo {key}: cases', ncase, int(r['cases']),
          f'cases with non-missing category = {int(r["cases_with_category"])}')
# Alternative: treat a missing subcategory as its own combination value and/or count a
# missing category as a distinct "category".
h_alt = c[c['trouble_code'].notna()].assign(subcategory=c['subcategory'].fillna('[Missing]'))
n_alt1 = int((h_alt.groupby(['trouble_code', 'subcategory'])['category'].nunique() > 1).sum())
alt('1.2 hierarchy', 'missing subcategory treated as a combination value', 'multi-category combos',
    len(multi), n_alt1, 'e.g. Miscellaneous/[Missing] spans Cancelled Request, Duplicate Case, NTF, Parts Order ...')
h_alt2 = hier.assign(category=hier['category'].fillna('[Missing]'))
n_alt2 = int((h_alt2.groupby(['trouble_code', 'subcategory'])['category'].nunique() > 1).sum())
alt('1.2 hierarchy', 'missing category counted as a distinct category value', 'multi-category combos',
    len(multi), n_alt2)

# ----------------------------------------------------------------------------------------
# 1.3 Service-outcome groups (mutually exclusive; precedence exactly as written)
# ----------------------------------------------------------------------------------------
S = '1.3 service outcomes (Cell 15)'
PLANNED_CODES = {'Preventative Maintenance', 'Installation'}
cond = {
    'Planned work': c['trouble_code'].isin(PLANNED_CODES) | c['record_type'].eq('Install Case'),
    'Cancelled request': c['category'].eq('Cancelled Request'),
    'Duplicate case': c['category'].eq('Duplicate Case'),
    'No Trouble Found': c['category'].eq('No Trouble Found'),
    'Missing trouble code': c['trouble_code'].isna(),
}
c['service_group'] = 'Other recorded issue'
assigned = pd.Series(False, index=c.index)
for g, m in cond.items():
    c.loc[m & ~assigned, 'service_group'] = g
    assigned |= m
ORDER = ['Other recorded issue', 'No Trouble Found', 'Cancelled request', 'Missing trouble code',
         'Planned work', 'Duplicate case']
sg = (c['service_group'].value_counts().rename_axis('service_group').reset_index(name='cases'))
sg['share_pct'] = sg['cases'].map(lambda n: pct(n, N))
sg = sg.sort_values('cases', ascending=False).reset_index(drop=True)
save(sg, 'service_groups')
zac_sg = {'Other recorded issue': (6508, 87.11), 'No Trouble Found': (577, 7.72), 'Cancelled request': (247, 3.31),
          'Missing trouble code': (101, 1.35), 'Planned work': (23, 0.31), 'Duplicate case': (15, 0.20)}
sgi = sg.set_index('service_group')
for g, (n, p) in zac_sg.items():
    claim(f'1.3.group.{g}.cases', S, f'Service group {g}: cases', n, int(sgi.loc[g, 'cases']))
    claim(f'1.3.group.{g}.share', S, f'Service group {g}: share %', p, float(sgi.loc[g, 'share_pct']))
claim('1.3.groups_sum', S, 'Service groups reconcile to all cases', N, int(sg['cases'].sum()))
UNPLANNED_EXCL = {'Planned work', 'Cancelled request', 'Duplicate case'}
c['unplanned'] = ~c['service_group'].isin(UNPLANNED_EXCL)
U = int(c['unplanned'].sum())
claim('1.3.unplanned_population', S, 'Unplanned-service population (excl. planned, cancelled, duplicate)', 7186, U)

# Overlaps between rules (precedence only matters where rules overlap)
ov = []
names = list(cond)
for i, a in enumerate(names):
    for b in names[i + 1:]:
        ov.append({'rule_a': a, 'rule_b': b, 'cases_matching_both': int((cond[a] & cond[b]).sum())})
ov = pd.DataFrame(ov)
save(ov, 'service_group_rule_overlaps')
planned_parts = pd.DataFrame([
    {'component': 'Trouble Code = Preventative Maintenance', 'cases': int(c['trouble_code'].eq('Preventative Maintenance').sum())},
    {'component': 'Trouble Code = Installation', 'cases': int(c['trouble_code'].eq('Installation').sum())},
    {'component': 'Case Record Type = Install Case', 'cases': int(c['record_type'].eq('Install Case').sum())},
    {'component': 'Install Case with a different (non-planned) trouble code',
     'cases': int((c['record_type'].eq('Install Case') & ~c['trouble_code'].isin(PLANNED_CODES)).sum())},
    {'component': 'Union = Planned work', 'cases': int(cond['Planned work'].sum())}])
save(planned_parts, 'planned_work_components')

# Alternatives for 1.3
pw_codes_only = c['trouble_code'].isin(PLANNED_CODES)
alt('1.3 planned work', 'planned = trouble code PM/Installation only (ignore Install Case record type)',
    'Planned work cases', int(cond['Planned work'].sum()), int(pw_codes_only.sum()),
    'Text explicitly says an install record type is planned, so the literal reading includes it.')
alt('1.3 planned work', 'planned = trouble code PM/Installation only (ignore Install Case record type)',
    'unplanned population', U, int(U + (cond['Planned work'] & ~pw_codes_only).sum()))
pm_cat = c['category'].isin({'Paid PM', 'Annual'})
alt('1.3 planned work', 'planned = PM/Installation codes + Install Case + categories Paid PM/Annual',
    'Planned work cases', int(cond['Planned work'].sum()), int((cond['Planned work'] | pm_cat).sum()),
    'Paid PM / Annual categories already sit under the PM trouble code.')
c_alt = c.assign(g2=c['service_group'])
mcat = c['category'].isna() & ~c['service_group'].isin(['Planned work', 'Cancelled request', 'Duplicate case',
                                                         'No Trouble Found'])
alt('1.3 missing group', '"missing broad code" read as missing Trouble Code Category instead of Trouble Code',
    'Missing group cases', int(cond['Missing trouble code'].sum() - (cond['Missing trouble code'] & cond['Planned work']).sum()),
    int(mcat.sum()), 'Unplanned population unchanged (both are inside it).')
alt('1.3 unplanned', 'also exclude No Trouble Found', 'unplanned population', U,
    int((c['unplanned'] & c['service_group'].ne('No Trouble Found')).sum()),
    'Text explicitly keeps NTF in; shown for scale only.')
alt('1.3 unplanned', 'also exclude Missing trouble code', 'unplanned population', U,
    int((c['unplanned'] & c['service_group'].ne('Missing trouble code')).sum()),
    'Text explicitly keeps missing labels in; shown for scale only.')

# ----------------------------------------------------------------------------------------
# 2.1 Customer and model workload (all cases)
# ----------------------------------------------------------------------------------------
S = '2.1 workload (Cell 17)'


def workload(key):
    w = (c.groupby(key).agg(cases=('case_id', 'size'), affected_machines=('serial', 'nunique'))
         .reset_index())
    w['share_pct'] = w['cases'].map(lambda n: pct(n, N))
    w = w.sort_values(['cases', key], ascending=[False, True]).reset_index(drop=True)
    w['rank'] = np.arange(1, len(w) + 1)
    w['cum_share_pct'] = (100.0 * w['cases'].cumsum() / N).round(2)
    return w


cw = workload('customer')
mw = workload('model')
save(cw, 'customer_workload')   # pseudonymous labels and counts only
save(mw, 'model_workload')
zac_cw = [('Customer 171', 123, 45, 1.65), ('Customer 029', 116, 56, 1.55), ('Customer 641', 92, 40, 1.23),
          ('Customer 529', 91, 31, 1.22), ('Customer 054', 78, 32, 1.04), ('Customer 479', 71, 21, 0.95),
          ('Customer 308', 70, 28, 0.94), ('Customer 062', 68, 31, 0.91), ('Customer 602', 64, 38, 0.86),
          ('Customer 489', 61, 36, 0.82)]
compare_table('2.1.customer', S, cw,
              [dict(customer=a, cases=b, affected_machines=m, share_pct=s) for a, b, m, s in zac_cw],
              'customer', ['cases', 'affected_machines', 'share_pct'], 'Customer workload')
zac_mw = [('LVD-Remote-2.0', 1426, 710, 19.09), ('LVRR-WP-2.0', 1244, 612, 16.65), ('MV-2.0', 936, 492, 12.53),
          ('LVD-Remote', 724, 397, 9.69), ('LVRR-WP', 589, 313, 7.88), ('alEx LC-D', 575, 254, 7.70),
          ('MV', 456, 237, 6.10), ('LC-30', 305, 163, 4.08), ('alEx SD 2.0', 158, 59, 2.11),
          ('alEx MC-D', 143, 67, 1.91)]
compare_table('2.1.model', S, mw,
              [dict(model=a, cases=b, affected_machines=m, share_pct=s) for a, b, m, s in zac_mw],
              'model', ['cases', 'affected_machines', 'share_pct'], 'Model workload')
top10_cust = round(100.0 * cw['cases'].head(10).sum() / N, 1)
top3_model = round(100.0 * mw['cases'].head(3).sum() / N, 1)
claim('2.1.top10_customer_share', S, 'Top-10 customers share of all tickets (%)', 11.2, top10_cust,
      f'{int(cw["cases"].head(10).sum())}/{N}; 10th={int(cw["cases"].iloc[9])}, 11th={int(cw["cases"].iloc[10])} '
      '(no tie at the cut)', tol=0.05)
claim('2.1.top3_model_share', S, 'Top-3 models share of all tickets (%)', 48.3, top3_model,
      f'{int(mw["cases"].head(3).sum())}/{N}', tol=0.05)
# 50 % concentration: smallest number of customers (largest first) reaching >= 50 % of tickets
n50 = int((cw['cases'].cumsum() < 0.5 * N).sum() + 1)
claim('2.1.customers_for_50pct', S, 'Customers needed to reach 50% of all tickets (largest first)',
      'not printed in method/output text', n50,
      f'Cumulative share at that rank = {cw["cum_share_pct"].iloc[n50 - 1]:.2f}% of {N}; '
      f'{len(cw)} customers in total ({pct(n50, len(cw))}% of customer labels). Zac\'s text describes '
      'concentration only via the top-10 / top-3 figures; any 50% figure may live in a chart cell '
      'whose output is not in the method text.', status='not_reproducible')
alt('2.1 concentration', '50% threshold as strictly greater than half (> 3,735.5 equals >= 3,736)',
    'customers for 50%', n50, int((cw['cases'].cumsum() <= 0.5 * N).sum() + 1), 'N is odd, so identical.')
cust_u = c[c['unplanned']].groupby('customer').size().sort_values(ascending=False)
alt('2.1 concentration', 'unplanned tickets only as the base', 'customers for 50%', n50,
    int((cust_u.cumsum() < 0.5 * U).sum() + 1))
alt('2.1 concentration', 'unplanned tickets only as the base', 'top-10 customer share %', top10_cust,
    round(100.0 * cust_u.head(10).sum() / U, 1))

# ----------------------------------------------------------------------------------------
# 2.2 Issue mix among unplanned tickets
# ----------------------------------------------------------------------------------------
S = '2.2 issue mix (Cell 20)'
un = c[c['unplanned']]
im = (un['category'].fillna('[Missing]').value_counts().rename_axis('category').reset_index(name='cases'))
im['share_pct'] = im['cases'].map(lambda n: pct(n, U))
im = im.sort_values(['cases', 'category'], ascending=[False, True]).reset_index(drop=True)
save(im, 'issue_mix')
zac_im = [('Deposit Door', 1124, 15.64), ('Computer Board', 679, 9.45), ('SAM', 588, 8.18),
          ('No Trouble Found', 577, 8.03), ('Main Door', 568, 7.90), ('Touchscreen', 562, 7.82),
          ('User Door', 515, 7.17), ('Curtain', 510, 7.10), ('[Missing]', 325, 4.52), ('Packer', 227, 3.16)]
compare_table('2.2.issue', S, im, [dict(category=a, cases=b, share_pct=s) for a, b, s in zac_im],
              'category', ['cases', 'share_pct'], 'Unplanned issue mix')
claim('2.2.top_category_share', S, 'Deposit Door share of unplanned tickets (1 dp)', 15.6,
      round(100.0 * im.loc[0, 'cases'] / U, 1), f'top category = {im.loc[0, "category"]}', tol=0.05)
# Why some categories are 1-2 lower than the all-case counts: planned work removed
diff = c['category'].fillna('[Missing]').value_counts().sub(im.set_index('category')['cases'], fill_value=0)
diff = diff[diff > 0].astype(int).sort_values(ascending=False)
removed = (c[~c['unplanned']].assign(category=c['category'].fillna('[Missing]'))
           .groupby(['category', 'service_group']).size().unstack(fill_value=0))
removed = removed.reindex(diff.index).reset_index()
removed.insert(1, 'all_minus_unplanned', diff.values)
save(removed, 'issue_mix_removed_by_exclusions')
# Service group by ticket status: where do the "missing trouble code" tickets come from?
sgs = pd.crosstab(c['service_group'], c['status']).reindex(ORDER).reset_index()
save(sgs, 'service_group_by_status')
alt('2.2 issue mix', 'all cases as the base instead of unplanned', 'Deposit Door share %',
    float(im.loc[0, 'share_pct']), pct(int(c['category'].eq('Deposit Door').sum()), N))
# Model-by-category (eight highest-volume models, Cell 21 chart) -- no printed numbers to compare
top8 = mw['model'].head(8)
mic = pd.crosstab(un['model'], un['category'].fillna('[Missing]'), normalize='index').mul(100).round(2)
save(mic.loc[top8].reset_index(), 'model_issue_mix_top8_pct')
cic = pd.crosstab(un['customer'], un['category'].fillna('[Missing]'))
save(cic.reset_index(), 'customer_issue_mix_counts')

# ----------------------------------------------------------------------------------------
# 3.4 Monthly ticket counts (Excel-only part)
# ----------------------------------------------------------------------------------------
S = '3.4 monthly tickets (Cell 29, second table)'
mo = (c.groupby('month').agg(all_tickets=('case_id', 'size'), unplanned_tickets=('unplanned', 'sum'))
      .reset_index())
mo['unplanned_tickets'] = mo['unplanned_tickets'].astype(int)
save(mo, 'monthly')
zac_mo = {'2025-08': (567, 552), '2025-09': (581, 550), '2025-10': (663, 629), '2025-11': (504, 477),
          '2025-12': (596, 570), '2026-01': (601, 586), '2026-02': (552, 534), '2026-03': (613, 601),
          '2026-04': (557, 542), '2026-05': (515, 485), '2026-06': (632, 604), '2026-07': (549, 534),
          '2026-08': (541, 522)}
moi = mo.set_index('month')
claim('3.4.months', S, 'Number of months in case export', len(zac_mo), len(mo))
for m, (a, u) in zac_mo.items():
    claim(f'3.4.{m}.all', S, f'{m} all tickets', a, int(moi.loc[m, 'all_tickets']))
    claim(f'3.4.{m}.unplanned', S, f'{m} unplanned tickets', u, int(moi.loc[m, 'unplanned_tickets']))
window = mo[(mo['month'] >= '2025-08') & (mo['month'] <= '2026-07')]
aug_jul = int(window['unplanned_tickets'].sum())
zac_aug_jul = sum(u for m, (a, u) in zac_mo.items() if m <= '2026-07')
claim('3.4.unplanned_aug25_jul26', S, 'Unplanned tickets Aug 2025-Jul 2026 (sum of Zac monthly table)',
      zac_aug_jul, aug_jul)
excl_sum = 4916 + 1203 + 479 + 48 + 18
claim('3.3.exclusion_table_total', '3.3 comparison cohort (Cell 27 reason table)',
      'Sum of Zac ticket-exclusion reasons equals unplanned Aug25-Jul26 total', excl_sum, aug_jul,
      'Cross-table consistency: 4,916 included + 1,203 no device match + 479 no transactions + 48 missing '
      'host + 18 shared host. Telemetry split itself cannot be checked without the DB.')
zac_rate_month_tickets = [360, 414, 472, 353, 436, 449, 379, 440, 408, 354, 442, 409]
claim('3.4.rate_table_tickets_sum', '3.4 monthly rates (Cell 29, first table)',
      'Sum of monthly comparison-cohort tickets equals 4,916 included tickets (internal consistency only)',
      4916, sum(zac_rate_month_tickets), 'Uses only Zac\'s printed numbers; no recomputation possible without the DB.')
zac_rate_month_amm = [5420, 5605, 5677, 5675, 5718, 5739, 5763, 5903, 5968, 5952, 5903, 5832]
claim('3.4.rate_table_amm_sum', '3.4 monthly rates (Cell 29, first table)',
      'Sum of monthly active machine-months equals cohort total 69,155 (printed numbers only)',
      69155, sum(zac_rate_month_amm), 'Internal consistency of Zac\'s printed tables; telemetry not recomputed.')
# Cell 27 type table shows 15 rows; compare its column sums to the cohort row (printed numbers only)
zac_type_tickets = [66, 53, 111, 999, 894, 397, 266, 684, 397, 334, 79, 89, 204, 246, 37]
zac_type_amm = [319, 584, 1352, 12329, 11141, 5011, 3571, 9442, 5873, 5087, 1246, 1606, 4143, 5484, 938]
claim('3.3.type_table_tickets_sum', '3.3 rates by type (Cell 27)',
      'Tickets summed over the 15 displayed machine types vs 4,916 comparison-cohort tickets', 4916,
      sum(zac_type_tickets),
      f'{4916 - sum(zac_type_tickets)} tickets and {69155 - sum(zac_type_amm)} active machine-months sit in types '
      'not displayed (text: "All types remain in the exported table"); the displayed table is a subset, so the '
      'gap is expected, not an error. Printed numbers only.', status='partial')
claim('3.4.unplanned_aug_2026', S, 'Unplanned tickets in Aug 2026 (= 7,186 - Aug25-Jul26 total)', U - zac_aug_jul,
      int(moi.loc['2026-08', 'unplanned_tickets']))

# ----------------------------------------------------------------------------------------
# 4.1 30-day repeat contact
# ----------------------------------------------------------------------------------------
S = '4.1 repeat contact (Cell 31)'
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


r = repeat_frame(un)
e, rep, same, simul = repeat_summary(r)
rs = pd.DataFrame([{'eligible_tickets': len(e), 'machines': e['serial'].nunique(), 'repeat_tickets': int(rep.sum()),
                    'same_category_repeats': int(same.sum()), 'repeat_pct': pct(rep.sum(), len(e)),
                    'same_category_repeat_pct': pct(same.sum(), len(e)), 'simultaneous_followups': int(simul.sum())}])
save(rs, 'repeat_summary')
zac_rs = {'eligible_tickets': 6665, 'machines': 3495, 'repeat_tickets': 1574, 'same_category_repeats': 515,
          'repeat_pct': 23.62, 'same_category_repeat_pct': 7.73, 'simultaneous_followups': 0}
for k, v in zac_rs.items():
    claim(f'4.1.{k}', S, f'Repeat summary: {k}', v, rs.loc[0, k])
claim('4.1.repeat_pct_1dp', S, 'Repeat contact % (text, 1 dp)', 23.6, round(100 * rep.sum() / len(e), 1), tol=0.05)
claim('4.1.same_pct_1dp', S, 'Same-category repeat % (text, 1 dp)', 7.7, round(100 * same.sum() / len(e), 1), tol=0.05)

# by model (index-ticket model), top 10 by eligible tickets
bm = (e.assign(rep=rep.astype(int)).groupby('model')
      .agg(eligible_tickets=('case_id', 'size'), repeat_tickets=('rep', 'sum')).reset_index())
bm['repeat_pct'] = [pct(a, b) for a, b in zip(bm['repeat_tickets'], bm['eligible_tickets'])]
bm = bm.sort_values(['eligible_tickets', 'model'], ascending=[False, True]).reset_index(drop=True)
save(bm, 'repeat_by_model')
zac_bm = [('LVD-Remote-2.0', 1288, 299, 23.21), ('LVRR-WP-2.0', 1101, 265, 24.07), ('MV-2.0', 829, 183, 22.07),
          ('LVD-Remote', 655, 134, 20.46), ('alEx LC-D', 526, 160, 30.42), ('LVRR-WP', 518, 118, 22.78),
          ('MV', 402, 93, 23.13), ('LC-30', 284, 42, 14.79), ('alEx SD 2.0', 133, 41, 30.83),
          ('scrubBank 480', 130, 48, 36.92)]
compare_table('4.1.model', S, bm,
              [dict(model=a, eligible_tickets=b, repeat_tickets=x, repeat_pct=p) for a, b, x, p in zac_bm],
              'model', ['eligible_tickets', 'repeat_tickets', 'repeat_pct'], 'Repeat by model')
claim('4.1.cell32_eligible', 'Cell 32 caption', 'Index tickets with complete 30-day follow-up', 6665, len(e))

# Diagnostics on the same-timestamp case in the data
same_time_pairs = int((r['gap'] == pd.Timedelta(0)).sum())
r_all = repeat_frame(c)
same_time_all = int((r_all['gap'] == pd.Timedelta(0)).sum())
# Alternatives for 4.1
base_rep, base_same = int(rep.sum()), int(same.sum())
for label, kw in [('calendar-day difference (date(next) - date(current) <= 30)', dict(day_mode='calendar')),
                  ('strict window (gap < 30 days)', dict(day_mode='strict')),
                  ('eligibility cutoff opened < 2026-08-01', dict(cutoff=pd.Timestamp('2026-08-01'))),
                  ('eligibility cutoff opened <= last opening - 30 days (2026-08-01 17:45)',
                   dict(cutoff=c['opened'].max() - WINDOW + pd.Timedelta(minutes=1)))]:
    e2, rep2, same2, _ = repeat_summary(r, **kw)
    alt('4.1 repeat', label, 'eligible tickets', len(e), len(e2))
    alt('4.1 repeat', label, 'repeat tickets', base_rep, int(rep2.sum()))
    alt('4.1 repeat', label, 'repeat %', float(rs.loc[0, 'repeat_pct']), pct(rep2.sum(), len(e2)))
    alt('4.1 repeat', label, 'same-category repeats', base_same, int(same2.sum()))
e2, rep2, same2, _ = repeat_summary(r, same_missing_equal=True)
alt('4.1 repeat', 'same-category also counts missing==missing', 'same-category repeats', base_same, int(same2.sum()))
# Next ticket of ANY service group (LEAD over all tickets), index still unplanned
r_any = r_all[r_all['unplanned']]
e3, rep3, same3, simul3 = repeat_summary(r_any)
alt('4.1 repeat', 'LEAD over all tickets (next ticket may be planned/cancelled/duplicate); index unplanned',
    'repeat tickets', base_rep, int(rep3.sum()))
alt('4.1 repeat', 'LEAD over all tickets (next ticket may be planned/cancelled/duplicate); index unplanned',
    'same-category repeats', base_same, int(same3.sum()))
e4, rep4, same4, simul4 = repeat_summary(r_all)
alt('4.1 repeat', 'all tickets as both index and follow-up (no unplanned filter)', 'eligible tickets', len(e), len(e4))
alt('4.1 repeat', 'all tickets as both index and follow-up (no unplanned filter)', 'repeat tickets', base_rep,
    int(rep4.sum()))
alt('4.1 repeat', 'all tickets as both index and follow-up (no unplanned filter)', 'simultaneous follow-ups',
    int(simul.sum()), int(simul4.sum()),
    f'Exactly {same_time_all} same-machine pair shares an opening timestamp in the full export; '
    f'{same_time_pairs} such pair(s) among unplanned tickets.')
alt('4.1 repeat', 'machines counted over all unplanned tickets, not only eligible index tickets', 'machines',
    int(e['serial'].nunique()), int(un['serial'].nunique()))

# ----------------------------------------------------------------------------------------
# Cell 39 headline statements that are Excel-only
# ----------------------------------------------------------------------------------------
S = '6.2 findings (Cell 39)'
claim('6.2.f1.tickets', S, 'Finding 1: distinct tickets', 7471, c['case_number'].nunique())
claim('6.2.f1.customers', S, 'Finding 1: customer labels', 845, c['customer'].nunique())
claim('6.2.f1.models', S, 'Finding 1: model labels', 31, c['model'].nunique())
claim('6.2.f3.top3', S, 'Finding 3: top-3 model share (%)', 48.3, top3_model, tol=0.05)
claim('6.2.f5.subcat_missing', S, 'Finding 5: subcategory missing', 2315, int(c['subcategory'].isna().sum()))
claim('6.2.f5.subcat_missing_pct', S, 'Finding 5: subcategory missing % (1 dp)', 31.0,
      round(100 * c['subcategory'].isna().sum() / N, 1), tol=0.05)
claim('6.2.f6.eligible', S, 'Finding 6: unplanned tickets with complete follow-up', 6665, len(e))
claim('6.2.f6.repeat', S, 'Finding 6: followed by another ticket on same machine within 30 days', 1574, base_rep)
claim('6.2.f6.repeat_pct', S, 'Finding 6: repeat % (1 dp)', 23.6, round(100 * base_rep / len(e), 1), tol=0.05)

# ----------------------------------------------------------------------------------------
# Write combined outputs and print a short report
# ----------------------------------------------------------------------------------------
cl = pd.DataFrame(claims)
save(cl, 'claims')
al = pd.DataFrame(alternatives)
save(al, 'alternatives')

print(f'Claims: {len(cl)}  ' + '  '.join(f'{k}={v}' for k, v in cl['status'].value_counts().items()))
bad = cl[cl['status'] == 'mismatch']
if len(bad):
    print('\nMISMATCHES')
    print(bad[['claim_id', 'zac_value', 'our_value', 'note']].to_string(index=False))
print('\nRecord counts'); print(rc.to_string(index=False))
print('\nService groups'); print(sg.to_string(index=False)); print('Unplanned:', U)
print('\nPlanned-work components'); print(planned_parts.to_string(index=False))
print('\nRule overlaps (non-zero)'); print(ov[ov['cases_matching_both'] > 0].to_string(index=False))
print('\nMulti-category combos'); print(multi.to_string(index=False))
print('\nRepeat summary'); print(rs.to_string(index=False))
print('\nCustomers for 50%:', n50, 'top10 share', top10_cust, 'top3 model share', top3_model)
print('Unplanned Aug25-Jul26:', aug_jul)
print('\nAlternatives'); print(al.to_string(index=False))
