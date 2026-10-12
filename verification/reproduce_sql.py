"""Faithful reproduction of the case-only SQL results in Zac's notebook.

Runs Zac's SQL verbatim (copied from data/derived/notebook_dump.md and checked character-for-
character against the notebook source when the notebook is present) on the case table rebuilt
by common.load_all(), then compares every printed value with what the notebook displayed.

Outputs (pseudonymous / aggregate only):
  verification/outputs/repro_sql_<table>.csv   reproduced tables
  verification/outputs/repro_sql_claims.csv    one row per compared claim
  verification/outputs/repro_sql_pilot_consistency.csv, repro_sql_pilot_strata.csv
  verification/outputs/repro_sql_diagnostics.csv  extra aggregate checks behind issues_noticed

Run: cd /home/user/analytics-lab && python3 -I verification/reproduce_sql.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hashlib
import json

import numpy as np
import pandas as pd

import common

OUT = common.OUTPUTS
OUT.mkdir(parents=True, exist_ok=True)
PREFIX = 'repro_sql_'

# ---------------------------------------------------------------------------------------------
# 0. Environment guard: common.load_raw under pandas >= 3 turns missing text cells into NaN, and
#    common.clean(NaN) returns the literal string 'nan' (Zac's Colab used pandas 2 object dtype,
#    where openpyxl's None stayed None). Measure the defect, then restore pandas-2 semantics.
# ---------------------------------------------------------------------------------------------
diagnostics = []


def diag(name, value, note=''):
    diagnostics.append({'check': name, 'value': value, 'note': note})
    print(f'  [diag] {name}: {value}' + (f'  ({note})' if note else ''))


print('pandas', pd.__version__)
_raw_unpatched = common.load_raw()
nan_literals = {col: int((_raw_unpatched[col].map(common.clean) == 'nan').sum())
                for col in ['Trouble Code', 'Trouble Code Category', 'Trouble Code Sub Category',
                            'Trouble Resolution', 'Administrative Notes']}
diag('unpatched common.load_all: literal "nan" labels per column', json.dumps(nan_literals),
     'pandas-3 str dtype stores missing cells as NaN; clean(NaN) -> "nan"')
_orig_load_raw = common.load_raw


def load_raw_pandas2_semantics(path=common.XLS):
    """Same rows as common.load_raw, but missing cells are None (object dtype) as in pandas 2."""
    raw = _orig_load_raw(path)
    return raw.astype(object).where(raw.notna(), None)


common.load_raw = load_raw_pandas2_semantics  # load_all() looks the name up at call time
raw, maps, c, conn = common.load_all()
assert conn.execute('SELECT SUM(trouble_code IS NULL) FROM cases').fetchone()[0] == 101
assert conn.execute("SELECT COUNT(*) FROM cases WHERE trouble_code='nan' OR category='nan' "
                    "OR subcategory='nan'").fetchone()[0] == 0
frames = {'cases': pd.read_sql_query('SELECT * FROM cases', conn)}

# ---------------------------------------------------------------------------------------------
# 1. Zac's SQL, verbatim.
# ---------------------------------------------------------------------------------------------
SQL = {}
SQL['record_quality'] = """
SELECT COUNT(*) cases, COUNT(DISTINCT case_id) distinct_cases,
 COUNT(DISTINCT customer) customers, COUNT(DISTINCT machine_id) case_machines,
 COUNT(DISTINCT model) models, MIN(opened_at) first_opened, MAX(opened_at) last_opened
FROM cases
"""
SQL['linkage'] = """
SELECT COUNT(*) cases, SUM(d.machine_id IS NOT NULL) matched_cases,
 COUNT(DISTINCT CASE WHEN d.machine_id IS NOT NULL THEN c.machine_id END) matched_machines,
 ROUND(100.0*SUM(d.machine_id IS NOT NULL)/COUNT(*),2) matched_pct
FROM cases c LEFT JOIN devices d USING(machine_id)
"""
SQL['field_completeness'] = """
SELECT 'Trouble Reported' field, SUM(reported_present=0) missing, 100.0*SUM(reported_present=0)/COUNT(*) missing_pct FROM cases
UNION ALL SELECT 'Model #',SUM(model IS NULL),100.0*SUM(model IS NULL)/COUNT(*) FROM cases
UNION ALL SELECT 'Trouble Code',SUM(trouble_code IS NULL),100.0*SUM(trouble_code IS NULL)/COUNT(*) FROM cases
UNION ALL SELECT 'Trouble Code Category',SUM(category IS NULL),100.0*SUM(category IS NULL)/COUNT(*) FROM cases
UNION ALL SELECT 'Trouble Code Sub Category',SUM(subcategory IS NULL),100.0*SUM(subcategory IS NULL)/COUNT(*) FROM cases
UNION ALL SELECT 'Trouble Resolution',SUM(resolution_present=0),100.0*SUM(resolution_present=0)/COUNT(*) FROM cases
"""
SQL['hierarchy_ambiguity'] = """
SELECT trouble_code, subcategory, COUNT(DISTINCT category) categories,
 GROUP_CONCAT(DISTINCT category) category_values, COUNT(*) cases
FROM cases WHERE trouble_code IS NOT NULL AND subcategory IS NOT NULL AND category IS NOT NULL
GROUP BY trouble_code,subcategory HAVING COUNT(DISTINCT category)>1
ORDER BY cases DESC
"""
VIEWS_CELL15 = """
DROP VIEW IF EXISTS case_base;
CREATE VIEW case_base AS
SELECT c.*, substr(opened_at,1,7) month,
 COALESCE(trouble_code,'[Missing]') || ' / ' || COALESCE(category,'[Missing]') || ' / ' || COALESCE(subcategory,'[Missing]') AS issue_path,
 CASE WHEN trouble_code IN ('Preventative Maintenance','Installation') OR record_type='Install Case' THEN 'Planned work'
      WHEN category='Cancelled Request' THEN 'Cancelled request'
      WHEN category='Duplicate Case' THEN 'Duplicate case'
      WHEN category='No Trouble Found' THEN 'No Trouble Found'
      WHEN trouble_code IS NULL THEN 'Missing trouble code'
      ELSE 'Other recorded issue' END service_group
FROM cases c;
DROP VIEW IF EXISTS service_cases;
CREATE VIEW service_cases AS SELECT * FROM case_base
WHERE service_group NOT IN ('Planned work','Cancelled request','Duplicate case');
"""
SQL['service_groups'] = """
SELECT service_group,COUNT(*) cases,100.0*COUNT(*)/(SELECT COUNT(*) FROM cases) share_pct
FROM case_base GROUP BY service_group ORDER BY cases DESC
"""
SQL['customer_workload'] = """
SELECT customer,COUNT(*) cases,COUNT(DISTINCT machine_id) affected_machines,
 100.0*COUNT(*)/(SELECT COUNT(*) FROM cases) share_pct
FROM cases GROUP BY customer ORDER BY cases DESC,customer
"""
SQL['model_workload'] = """
SELECT model,COUNT(*) cases,COUNT(DISTINCT machine_id) affected_machines,
 100.0*COUNT(*)/(SELECT COUNT(*) FROM cases) share_pct
FROM cases GROUP BY model ORDER BY cases DESC,model
"""
SQL['issue_mix'] = """
SELECT COALESCE(category,'[Missing]') category,COUNT(*) cases,
 100.0*COUNT(*)/(SELECT COUNT(*) FROM service_cases) share_pct
FROM service_cases GROUP BY category ORDER BY cases DESC
"""
SQL['customer_issue_mix'] = """
SELECT customer,COALESCE(category,'[Missing]') category,COUNT(*) cases
FROM service_cases GROUP BY customer,category ORDER BY customer,cases DESC
"""
SQL['model_issue_mix'] = """
SELECT model,COALESCE(category,'[Missing]') category,COUNT(*) cases
FROM service_cases GROUP BY model,category ORDER BY model,cases DESC
"""
VIEWS_CELL27 = """
DROP VIEW IF EXISTS machine_month;
CREATE VIEW machine_month AS
SELECT t.machine_id,t.month,SUM(t.n) transactions,
 SUM(CASE WHEN k.provisional_fault=1 THEN t.n ELSE 0 END) fault_transactions,
 SUM(CASE WHEN k.bucket='Door issue' THEN t.n ELSE 0 END) door_transactions
FROM telemetry_month_code t LEFT JOIN codes k USING(transaction_code)
WHERE t.month>='2025-08' AND t.month<'2026-08'
GROUP BY t.machine_id,t.month;
DROP VIEW IF EXISTS comparison_month;
CREATE VIEW comparison_month AS
WITH ticket_counts AS (SELECT machine_id,month,COUNT(*) tickets FROM service_cases GROUP BY machine_id,month)
SELECT m.*,d.machine_type,d.host,d.shared_internal_host,
 COALESCE(c.tickets,0) tickets
FROM machine_month m JOIN devices d USING(machine_id)
LEFT JOIN ticket_counts c ON m.machine_id=c.machine_id AND m.month=c.month;
"""
SQL['ticket_cohort_exclusions'] = """
SELECT CASE WHEN d.machine_id IS NULL THEN 'No device match'
 WHEN d.shared_internal_host=1 THEN 'Shared/internal host'
 WHEN d.host IS NULL THEN 'Missing host'
 WHEN m.machine_id IS NULL THEN 'No transactions in ticket month'
 ELSE 'Included in comparison' END reason,COUNT(*) tickets
FROM service_cases c LEFT JOIN devices d USING(machine_id)
LEFT JOIN machine_month m ON c.machine_id=m.machine_id AND c.month=m.month
WHERE c.month>='2025-08' AND c.month<'2026-08'
GROUP BY reason ORDER BY tickets DESC
"""
SQL['case_monthly'] = """
SELECT month,COUNT(*) all_tickets,SUM(service_group NOT IN ('Planned work','Cancelled request','Duplicate case')) unplanned_tickets
FROM case_base GROUP BY month ORDER BY month
"""
VIEWS_CELL31 = """
DROP VIEW IF EXISTS repeat_cases;
CREATE VIEW repeat_cases AS
WITH ordered AS (
 SELECT *,LEAD(opened_at) OVER(PARTITION BY machine_id ORDER BY opened_at,case_id) next_opened,
 LEAD(category) OVER(PARTITION BY machine_id ORDER BY opened_at,case_id) next_category
 FROM service_cases)
SELECT *,julianday(next_opened)-julianday(opened_at) gap_days,
 CASE WHEN julianday(next_opened)-julianday(opened_at) BETWEEN 0 AND 30 THEN 1 ELSE 0 END repeat_30,
 CASE WHEN julianday(next_opened)-julianday(opened_at) BETWEEN 0 AND 30 AND category IS NOT NULL AND category=next_category THEN 1 ELSE 0 END same_category_30
FROM ordered WHERE opened_at<'2026-08-02';
"""
SQL['repeat_summary'] = """
SELECT COUNT(*) eligible_tickets,COUNT(DISTINCT machine_id) machines,
 SUM(repeat_30) repeat_tickets,SUM(same_category_30) same_category_repeats,
 100.0*SUM(repeat_30)/COUNT(*) repeat_pct,
 100.0*SUM(same_category_30)/COUNT(*) same_category_repeat_pct,
 SUM(repeat_30=1 AND gap_days=0) simultaneous_followups
FROM repeat_cases
"""
SQL['repeat_by_model'] = """
SELECT model,COUNT(*) eligible_tickets,SUM(repeat_30) repeat_tickets,
 100.0*SUM(repeat_30)/COUNT(*) repeat_pct
FROM repeat_cases GROUP BY model ORDER BY eligible_tickets DESC
"""
CELL_OF = {'record_quality': 11, 'linkage': 11, 'field_completeness': 13, 'hierarchy_ambiguity': 13,
           'service_groups': 15, 'customer_workload': 17, 'model_workload': 17, 'issue_mix': 20,
           'customer_issue_mix': 20, 'model_issue_mix': 20, 'ticket_cohort_exclusions': 27,
           'case_monthly': 29, 'repeat_summary': 31, 'repeat_by_model': 31}
VIEW_CELL = {15: VIEWS_CELL15, 27: VIEWS_CELL27, 31: VIEWS_CELL31}

# Verbatim check against the notebook itself (data/raw is local-only; skip if absent).
if common.NOTEBOOK.exists():
    nb = json.loads(common.NOTEBOOK.read_text())
    src = {i: ''.join(cell['source']) for i, cell in enumerate(nb['cells'])}
    for name, text in SQL.items():
        assert f"q('{name}', \"\"\"{text}\"\"\")" in src[CELL_OF[name]], f'SQL for {name} is not verbatim'
    for cell, text in VIEW_CELL.items():
        assert f'conn.executescript("""{text}""")' in src[cell], f'views of cell {cell} are not verbatim'
    print('Verbatim check: all', len(SQL), 'queries and 3 view scripts match the notebook source exactly.')
    VERBATIM = 'checked against notebook source'
else:
    print('WARNING: notebook not present; verbatim check skipped.')
    VERBATIM = 'not checked (notebook absent)'

results = {}


def q(name, sql):
    """Zac's q(): run SQL, keep the frame; save under our prefix."""
    result = pd.read_sql_query(sql, conn)
    result.to_csv(OUT / f'{PREFIX}{name}.csv', index=False)
    results[name] = result
    return result


# Telemetry tables are unavailable: create EMPTY stand-ins with Zac's column names so his
# device-dependent SQL can run verbatim. Only row totals (not reason splits) are meaningful.
conn.executescript("""
CREATE TABLE devices(machine_id TEXT, device_status TEXT, machine_type_raw TEXT, machine_type TEXT,
                     host TEXT, shared_internal_host INTEGER);
CREATE TABLE telemetry_month_code(month TEXT, transaction_code TEXT, n INTEGER, first_date TEXT,
                     last_date TEXT, clocks_differ INTEGER, missing_time INTEGER, machine_id TEXT);
CREATE TABLE codes(transaction_code TEXT, transaction_description TEXT, bucket TEXT,
                   provisional_fault INTEGER);
""")

conn.executescript(VIEWS_CELL15)  # (common.case_database already ran the same text; re-run verbatim)
quality = q('record_quality', SQL['record_quality'])
linkage = q('linkage', SQL['linkage'])  # with empty devices: only `cases` is meaningful
fields = q('field_completeness', SQL['field_completeness'])
ambiguity = q('hierarchy_ambiguity', SQL['hierarchy_ambiguity'])
service_mix = q('service_groups', SQL['service_groups'])
unplanned_n = int(service_mix.loc[~service_mix.service_group.isin(['Planned work', 'Cancelled request', 'Duplicate case']), 'cases'].sum())
customers = q('customer_workload', SQL['customer_workload'])
models = q('model_workload', SQL['model_workload'])
issues = q('issue_mix', SQL['issue_mix'])
q('customer_issue_mix', SQL['customer_issue_mix'])
q('model_issue_mix', SQL['model_issue_mix'])
conn.executescript(VIEWS_CELL27)
cohort_exclusions = q('ticket_cohort_exclusions', SQL['ticket_cohort_exclusions'])
case_monthly = q('case_monthly', SQL['case_monthly'])
conn.executescript(VIEWS_CELL31)
repeats = q('repeat_summary', SQL['repeat_summary'])
repeat_models = q('repeat_by_model', SQL['repeat_by_model'])

# Cell 18, verbatim except reading our CSV.
v = pd.read_csv(OUT / f'{PREFIX}customer_workload.csv').sort_values('cases', ascending=False)
x = np.arange(1, len(v) + 1); y = 100 * v.cases.cumsum() / v.cases.sum()
k = int(np.searchsorted(y.to_numpy(), 50) + 1)
k_top10 = float(y.iloc[9])
k_share = float(y.iloc[k - 1])

# Cell 21 heatmap data, verbatim except reading our CSV (no plotting).
v = pd.read_csv(OUT / f'{PREFIX}model_issue_mix.csv').fillna({'category': 'Missing'})
heat_models = v.groupby('model').cases.sum().nlargest(8).index
cats = v.groupby('category').cases.sum().nlargest(7).index
v = v[v.model.isin(heat_models)].copy(); v['display_category'] = v.category.where(v.category.isin(cats), 'Other categories')
a = v.pivot_table(index='model', columns='display_category', values='cases', aggfunc='sum', fill_value=0).reindex(index=heat_models, columns=list(cats) + ['Other categories'], fill_value=0)
tot = a.sum(axis=1); pct = a.div(tot, axis=0) * 100
assert np.allclose(pct.sum(axis=1), 100)
heat = pct.copy(); heat.insert(0, 'n', tot); heat.reset_index().to_csv(OUT / f'{PREFIX}model_issue_heatmap.csv', index=False)

# Cell 32 partition (verbatim arithmetic).
r = pd.read_csv(OUT / f'{PREFIX}repeat_summary.csv').iloc[0]
partition = [r.eligible_tickets - r.repeat_tickets, r.repeat_tickets - r.same_category_repeats, r.same_category_repeats]
partition_pct = [100 * x_ / r.eligible_tickets for x_ in partition]

# Cell 37 case-only checks, verbatim.
case_frame = frames['cases'].copy()
planned = case_frame.trouble_code.isin(['Preventative Maintenance', 'Installation']) | case_frame.record_type.eq('Install Case')
filtered = case_frame[~planned & ~case_frame.category.isin(['Cancelled Request', 'Duplicate Case'])].copy()
filtered = filtered.sort_values(['machine_id', 'opened_at', 'case_id'])
filtered['opening'] = pd.to_datetime(filtered.opened_at)
filtered['next'] = filtered.groupby('machine_id').opening.shift(-1)
filtered['gap'] = (filtered['next'] - filtered.opening).dt.total_seconds() / 86400
valid = filtered[filtered.opened_at < '2026-08-02']
pandas_repeat = int(valid.gap.between(0, 30).sum())
pandas_missing_sub = int(case_frame.subcategory.isna().sum())
sql_missing_sub = int(fields.loc[fields.field == 'Trouble Code Sub Category', 'missing'].iloc[0])

# ---------------------------------------------------------------------------------------------
# 2. Zac's printed values (transcribed from data/derived/notebook_dump.md; cell 18/32 from charts)
# ---------------------------------------------------------------------------------------------
Z = {
    'record_quality': [(7471, 7471, 845, 3773, 31, '2025-08-01 07:22:00', '2026-08-31 17:45:00')],
    'field_completeness': [('Trouble Reported', 0, 0.00), ('Model #', 0, 0.00), ('Trouble Code', 101, 1.35),
                           ('Trouble Code Category', 330, 4.42), ('Trouble Code Sub Category', 2315, 30.99),
                           ('Trouble Resolution', 641, 8.58)],
    'hierarchy_ambiguity': [
        ('Electronics', 'Replacement', 5, 'Power Supply,Decoder,Touchscreen,Computer Board,Camera', 292),
        ('Electro/Mechanical', 'Home Switch/Adjustment', 2, 'Packer,SAM', 125),
        ('Electro/Mechanical', 'Lock Adjustment', 2, 'Service Door,Deposit Door', 57),
        ('Electronics', 'Training', 2, 'Loader Board,Touchscreen', 25),
        ('Electro/Mechanical', 'Training', 5, 'User Door,Main Door,Counterweight System,Service Door,Deposit Door', 21),
        ('Software', 'End User', 2, 'Credit Issues,Training', 11)],
    'service_groups': [('Other recorded issue', 6508, 87.11), ('No Trouble Found', 577, 7.72),
                       ('Cancelled request', 247, 3.31), ('Missing trouble code', 101, 1.35),
                       ('Planned work', 23, 0.31), ('Duplicate case', 15, 0.20)],
    'customer_workload': [('Customer 171', 123, 45, 1.65), ('Customer 029', 116, 56, 1.55),
                          ('Customer 641', 92, 40, 1.23), ('Customer 529', 91, 31, 1.22),
                          ('Customer 054', 78, 32, 1.04), ('Customer 479', 71, 21, 0.95),
                          ('Customer 308', 70, 28, 0.94), ('Customer 062', 68, 31, 0.91),
                          ('Customer 602', 64, 38, 0.86), ('Customer 489', 61, 36, 0.82)],
    'model_workload': [('LVD-Remote-2.0', 1426, 710, 19.09), ('LVRR-WP-2.0', 1244, 612, 16.65),
                       ('MV-2.0', 936, 492, 12.53), ('LVD-Remote', 724, 397, 9.69), ('LVRR-WP', 589, 313, 7.88),
                       ('alEx LC-D', 575, 254, 7.70), ('MV', 456, 237, 6.10), ('LC-30', 305, 163, 4.08),
                       ('alEx SD 2.0', 158, 59, 2.11), ('alEx MC-D', 143, 67, 1.91)],
    'issue_mix': [('Deposit Door', 1124, 15.64), ('Computer Board', 679, 9.45), ('SAM', 588, 8.18),
                  ('No Trouble Found', 577, 8.03), ('Main Door', 568, 7.90), ('Touchscreen', 562, 7.82),
                  ('User Door', 515, 7.17), ('Curtain', 510, 7.10), ('[Missing]', 325, 4.52), ('Packer', 227, 3.16)],
    'case_monthly': [('2025-08', 567, 552), ('2025-09', 581, 550), ('2025-10', 663, 629), ('2025-11', 504, 477),
                     ('2025-12', 596, 570), ('2026-01', 601, 586), ('2026-02', 552, 534), ('2026-03', 613, 601),
                     ('2026-04', 557, 542), ('2026-05', 515, 485), ('2026-06', 632, 604), ('2026-07', 549, 534),
                     ('2026-08', 541, 522)],
    'repeat_summary': [(6665, 3495, 1574, 515, 23.62, 7.73, 0)],
    'repeat_by_model': [('LVD-Remote-2.0', 1288, 299, 23.21), ('LVRR-WP-2.0', 1101, 265, 24.07),
                        ('MV-2.0', 829, 183, 22.07), ('LVD-Remote', 655, 134, 20.46), ('alEx LC-D', 526, 160, 30.42),
                        ('LVRR-WP', 518, 118, 22.78), ('MV', 402, 93, 23.13), ('LC-30', 284, 42, 14.79),
                        ('alEx SD 2.0', 133, 41, 30.83), ('scrubBank 480', 130, 48, 36.92)],
}
# Cell 21 heatmap (read from the chart image): model, n, then % for the 7 top categories + Other.
ZAC_HEATMAP_COLS = ['Deposit Door', 'Computer Board', 'SAM', 'No Trouble Found', 'Main Door', 'Touchscreen', 'User Door', 'Other categories']
ZAC_HEATMAP = [('LVD-Remote-2.0', 1393, 1, 8, 20, 10, 9, 15, 15, 23), ('LVRR-WP-2.0', 1211, 53, 7, 0, 6, 1, 8, 0, 25),
               ('MV-2.0', 897, 24, 7, 7, 8, 4, 17, 6, 27), ('LVD-Remote', 695, 1, 13, 17, 8, 11, 3, 22, 24),
               ('alEx LC-D', 558, 0, 5, 0, 7, 5, 1, 0, 82), ('LVRR-WP', 554, 29, 17, 0, 9, 1, 2, 1, 41),
               ('MV', 427, 10, 15, 6, 8, 8, 6, 9, 38), ('LC-30', 298, 0, 11, 0, 6, 29, 2, 0, 53)]
ZAC_PILOT = ['T00705', 'T00783', 'T00951', 'T00957', 'T01157', 'T01287', 'T01629', 'T01795', 'T01796', 'T01797',
             'T02128', 'T02229', 'T02268', 'T03075', 'T03079', 'T03326', 'T03959', 'T04699', 'T04907', 'T05185',
             'T05506', 'T05683', 'T05924', 'T06107', 'T06354', 'T06445', 'T06663', 'T06672', 'T06712', 'T06912']
ZAC_COHORT_EXCLUSIONS = {'Included in comparison': 4916, 'No device match': 1203,
                         'No transactions in ticket month': 479, 'Missing host': 48, 'Shared/internal host': 18}
ZAC_LINKAGE = {'cases': 7471, 'matched_cases': 6113, 'matched_machines': 3041, 'matched_pct': 81.82}
# Cell 25 model_type_mapping.head(15) (needs devices; used only for cross-table logic checks).
ZAC_MODEL_MAP_HEAD15 = [('A-LC', 'Unknown', 10, 5), ('A-LC', 'alc-1', 2, 2), ('LC-24', 'mlc-1', 27, 16),
                        ('LC-30', 'mlc-1', 255, 132), ('LC-30', 'Unknown', 1, 1), ('LVD-Remote', 'scrubex-2', 465, 241),
                        ('LVD-Remote', 'scrubex-1', 23, 16), ('LVD-Remote', 'Unknown', 4, 3),
                        ('LVD-Remote-2.0', 'scrubex2.0-2', 1227, 608), ('LVD-Remote-2.0', 'Unknown', 13, 6),
                        ('LVD-Remote-2.0', 'scrubex2.0-3', 3, 1), ('LVD-Remote-2.0', 'sd2.0-49', 1, 1),
                        ('LVLR-WOP', 'scrubex-1', 4, 2), ('LVRR-WOP', 'scrubex-3', 14, 6), ('LVRR-WP', 'scrubex-3', 293, 156)]

# ---------------------------------------------------------------------------------------------
# 3. Comparison helpers.
# ---------------------------------------------------------------------------------------------
claims = []


def norm(value):
    if isinstance(value, (float, np.floating)):
        return round(float(value) + 0.0, 2)
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def rows_of(df, n=None):
    d = df if n is None else df.head(n)
    return [tuple(norm(x) for x in row) for row in d.itertuples(index=False)]


def fmt(rows):
    return ' ; '.join('|'.join(str(x) for x in row) for row in rows)


def claim(cid, section, description, zac, ours, status, note=''):
    claims.append({'claim_id': cid, 'notebook_section': section, 'description': description,
                   'zac_value': str(zac), 'our_value': str(ours), 'status': status, 'note': note})
    print(f'[{status:>16}] {cid}: zac={zac} ours={ours}' + (f' -- {note}' if note else ''))


def table_claim(cid, section, description, name, df, note=''):
    zac = Z[name]
    ours = rows_of(df, len(zac))
    bad = [i for i, (a, b) in enumerate(zip(zac, ours)) if tuple(norm(x) for x in a) != b]
    status = 'match' if not bad and len(ours) == len(zac) else 'mismatch'
    extra = f'{len(zac)} displayed rows compared cell by cell (2 dp)'
    if bad:
        extra += f'; differing rows (0-based): {bad}'
    claim(cid, section, description, fmt(zac), fmt(ours), status, (extra + ('; ' + note if note else '')))
    return bad


def scalar_claim(cid, section, description, zac, ours, note='', tol=0):
    ok = (zac == ours) if tol == 0 else abs(float(zac) - float(ours)) <= tol
    claim(cid, section, description, zac, ours, 'match' if ok else 'mismatch', note)


# ---------------------------------------------------------------------------------------------
# 4. Claims.
# ---------------------------------------------------------------------------------------------
print('\n== Claims ==')
wb_sha = common.sha256_file(common.XLS)
claim('C02_workbook_sha256', 'Cell 2 (source verification)', 'SHA-256 of the case workbook',
      common.ZAC_WORKBOOK_SHA256[:16] + '...', wb_sha[:16] + '...',
      'match' if wb_sha == common.ZAC_WORKBOOK_SHA256 else 'mismatch',
      'File bytes differ from the version Zac verified; every content-level claim below is compared anyway.')
scalar_claim('C09_cases_rows', 'Cell 9 (table sizes)', 'Rows in the cases table', 7471, len(frames['cases']))

table_claim('C11_record_quality', 'Cell 11 / 1.1', 'record_quality: cases, distinct cases, customers, case machines, models, first/last opened',
            'record_quality', quality,
            'case_machines counts distinct S-ids; the serial->id map is 1:1 so the count equals the M-id count')
claim('C11_linkage', 'Cell 11 / 1.1', 'linkage: cases / matched_cases / matched_machines / matched_pct',
      '|'.join(str(x) for x in ZAC_LINKAGE.values()), f"{int(linkage.loc[0, 'cases'])}|n/a|n/a|n/a",
      'not_reproducible',
      'Needs the devices table. Verbatim SQL run against an empty devices stand-in reproduces only the denominator '
      f"cases={int(linkage.loc[0, 'cases'])} (assert linkage.cases==len(cases) holds).")

table_claim('C13_field_completeness', 'Cell 13 / 1.2', 'field_completeness: missing count and % for 6 fields', 'field_completeness', fields)
bad = table_claim('C13_hierarchy_ambiguity', 'Cell 13 / 1.2', 'hierarchy_ambiguity: code/subcategory pairs spanning >1 category',
                  'hierarchy_ambiguity', ambiguity,
                  'GROUP_CONCAT(DISTINCT) order is SQLite scan order (row order of the sheet), not guaranteed')
set_equal = all(set(a[3].split(',')) == set(b[3].split(',')) for a, b in zip(Z['hierarchy_ambiguity'], rows_of(ambiguity)))
scalar_claim('C13_ambiguity_count', 'Cell 13 / 1.2', 'Printed: number of code/subcategory combinations spanning >1 category',
             6, len(ambiguity), f'category sets equal irrespective of order: {set_equal}')

table_claim('C15_service_groups', 'Cell 15 / 1.3', 'service_groups: cases and share by mutually exclusive service group', 'service_groups', service_mix)
scalar_claim('C15_unplanned_total', 'Cell 15 / 1.3', 'Printed unplanned-service population (all groups except planned/cancelled/duplicate)',
             7186, unplanned_n)

table_claim('C17_customer_workload_top10', 'Cell 17 / 2.1', 'customer_workload.head(10): cases, affected machines, share', 'customer_workload', customers)
table_claim('C17_model_workload_top10', 'Cell 17 / 2.1', 'model_workload.head(10): cases, affected machines, share', 'model_workload', models)
scalar_claim('C17_top10_customer_share', 'Cell 17 / 2.1', 'Printed: top 10 customers share of all tickets (%)', '11.2',
             f'{customers.head(10).share_pct.sum():.1f}', f'unrounded {customers.head(10).share_pct.sum():.4f}')
scalar_claim('C17_top3_model_share', 'Cell 17 / 2.1', 'Printed: top 3 models share of all tickets (%)', '48.3',
             f'{models.head(3).share_pct.sum():.1f}', f'unrounded {models.head(3).share_pct.sum():.4f}')
claim('C17_workload_totals', 'Cell 17 / 6.1 check', 'customer and model workload totals both equal all cases',
      '7471=7471=7471 (check Pass)', f'{int(customers.cases.sum())}={int(models.cases.sum())}={len(frames["cases"])}',
      'match' if int(customers.cases.sum()) == int(models.cases.sum()) == len(frames['cases']) else 'mismatch',
      'tautological: any GROUP BY over the same table sums to its row count')

scalar_claim('C18_concentration_k', 'Cell 18 (chart annotation)', 'Customer labels needed to reach 50% of tickets (searchsorted(y,50)+1)',
             126, k, f'cumulative share at k = {k_share:.3f}%; at k-1 = {float(y.iloc[k - 2]):.3f}%; value read from the chart image')
scalar_claim('C18_top10_annotation', 'Cell 18 (chart annotation)', 'Chart annotation: Top 10 share of tickets (%)', '11.2', f'{k_top10:.1f}')

ours_heat = [(m_, int(tot[m_]), *[int(f'{pct.loc[m_, col]:.0f}') for col in pct.columns]) for m_ in heat_models]
claim('C21_model_issue_heatmap', 'Cell 21 (chart)', 'Model x category heatmap: 8 models, n and whole-% per top-7 category + Other',
      f"cols={'|'.join(ZAC_HEATMAP_COLS)} ; " + fmt(ZAC_HEATMAP), f"cols={'|'.join(pct.columns)} ; " + fmt(ours_heat),
      'match' if (list(pct.columns) == ZAC_HEATMAP_COLS and ours_heat == [tuple(r_) for r_ in ZAC_HEATMAP]) else 'mismatch',
      f"64 cells + 8 n values read from the chart image. Curtain ({int(issues.set_index('category').cases['Curtain'])} tickets) misses the top-7 "
      f"by {int(issues.set_index('category').cases['User Door'] - issues.set_index('category').cases['Curtain'])} tickets, so alEx LC-D shows "
      f"{pct.loc['alEx LC-D', 'Other categories']:.0f}% 'Other categories'.")
table_claim('C20_issue_mix_top10', 'Cell 20 / 2.2', 'issue_mix.head(10): category counts and share of unplanned tickets', 'issue_mix', issues)
scalar_claim('C20_issue_headline', 'Cell 20 / 2.2', 'Printed: most frequent category, tickets, % of unplanned',
             'Deposit Door|1124|15.6', f"{issues.iloc[0].category}|{int(issues.iloc[0].cases)}|{issues.iloc[0].share_pct:.1f}")
scalar_claim('C20_service_cases_total', 'Cell 20 / 2.2', 'issue_mix denominator (service_cases rows) equals unplanned total', 7186,
             int(issues.cases.sum()))

excl_total = int(cohort_exclusions.tickets.sum())
claim('C27_cohort_exclusions_total', 'Cell 27 / 3.3', 'ticket_cohort_exclusions: total unplanned tickets Aug 2025-Jul 2026 (sum of reasons)',
      f'{sum(ZAC_COHORT_EXCLUSIONS.values())} (= ' + '+'.join(str(v_) for v_ in ZAC_COHORT_EXCLUSIONS.values()) + ')',
      excl_total, 'match' if excl_total == sum(ZAC_COHORT_EXCLUSIONS.values()) else 'mismatch',
      'Verbatim SQL with empty devices/telemetry stand-ins: all rows fall in "No device match"; LEFT JOINs to '
      'unique keys cannot multiply rows, so the total is device-independent. Reason split is not reproducible.')
monthly_unplanned_aug_jul = int(case_monthly.loc[(case_monthly.month >= '2025-08') & (case_monthly.month < '2026-08'), 'unplanned_tickets'].sum())
claim('C29_vs_C27_crosscheck', 'Cells 27 + 29', 'case_monthly unplanned Aug25-Jul26 equals cohort_exclusions total',
      '6664 (Zac: 552+...+534 vs 4916+1203+479+48+18)', monthly_unplanned_aug_jul,
      'match' if monthly_unplanned_aug_jul == sum(ZAC_COHORT_EXCLUSIONS.values()) else 'mismatch',
      "cross-table consistency of Zac's own printed tables")

table_claim('C29_case_monthly', 'Cell 29 / 3.4', 'case_monthly: all and unplanned tickets by month (13 rows)', 'case_monthly', case_monthly)
table_claim('C31_repeat_summary', 'Cell 31 / 4.1', 'repeat_summary: eligible, machines, repeats, same-category, %, simultaneous',
            'repeat_summary', repeats)
scalar_claim('C31_repeat_headline', 'Cell 31 / 4.1', 'Printed: repeat % and same-category repeat %', '23.6|7.7',
             f"{repeats.loc[0, 'repeat_pct']:.1f}|{repeats.loc[0, 'same_category_repeat_pct']:.1f}")
table_claim('C31_repeat_by_model_top10', 'Cell 31 / 4.1', 'repeat_by_model.head(10): eligible, repeats, %', 'repeat_by_model', repeat_models)
scalar_claim('C32_repeat_partition', 'Cell 32 (chart)', 'Repeat composition chart: none / different-or-missing category / same category',
             '5091|1059|515 ; 76.4|15.9|7.7',
             '|'.join(str(int(p)) for p in partition) + ' ; ' + '|'.join(f'{p:.1f}' for p in partition_pct))
scalar_claim('C37_independent_repeat', 'Cell 37 / 6.1', 'Independent pandas repeat count equals SQL repeat_tickets (check Pass)',
             '1574 = 1574', f"{pandas_repeat} = {int(repeats.loc[0, 'repeat_tickets'])}")
scalar_claim('C37_missing_subcategory', 'Cell 37 / 6.1', 'pandas isna(subcategory) equals SQL missing count (check Pass)',
             '2315 = 2315', f'{pandas_missing_sub} = {sql_missing_sub}',
             'not independent: both read the same cases.subcategory column')
scalar_claim('C37_service_groups_reconcile', 'Cell 37 / 6.1', 'service group counts sum to all cases (check Pass)',
             '7471 = 7471', f'{int(service_mix.cases.sum())} = {len(frames["cases"])}', 'tautological check')
findings_zac = ['7,471 distinct tickets, 845 customer labels, 31 model labels', 'top three models 48.3%',
                'sub-category missing 2,315 (31.0%)', '6,665 eligible, 1,574 repeats (23.6%)']
findings_ours = [f"{len(frames['cases']):,} distinct tickets, {int(quality.loc[0, 'customers']):,} customer labels, {int(quality.loc[0, 'models'])} model labels",
                 f'top three models {models.head(3).share_pct.sum():.1f}%',
                 f"sub-category missing {sql_missing_sub:,} ({fields.loc[fields.field == 'Trouble Code Sub Category', 'missing_pct'].iloc[0]:.1f}%)",
                 f"{int(repeats.loc[0, 'eligible_tickets']):,} eligible, {int(repeats.loc[0, 'repeat_tickets']):,} repeats ({repeats.loc[0, 'repeat_pct']:.1f}%)"]
scalar_claim('C39_case_only_findings', 'Cell 39 / 6.2', 'Findings 1, 3, 5, 6 (case-only numbers)', ' ; '.join(findings_zac), ' ; '.join(findings_ours))

# ---------------------------------------------------------------------------------------------
# 5. Pilot selection (cell 8) consistency without the device dictionary.
# ---------------------------------------------------------------------------------------------
print('\n== Pilot selection (cell 8) ==')
# Cell 8 verbatim, minus `c.machine_id.isin(devices.machine_id)` (devices unavailable).
eligible = c[c.opened_at.between('2025-09-02', '2026-07-31 23:59:59')].copy()
eligible['stratum'] = eligible.trouble_code.fillna('Missing')
eligible['sample_order'] = eligible.case_id.map(lambda x: hashlib.sha256(('15072' + x).encode()).hexdigest())
eligible['within_stratum'] = eligible.sort_values('sample_order').groupby('stratum').cumcount()
assert (eligible.sample_order == eligible.case_id.map(common.pilot_order)).all()
naive_pilot = eligible.sort_values(['within_stratum', 'sample_order']).head(30)

E = eligible.sort_values('sample_order').reset_index(drop=True)
P = set(ZAC_PILOT)
missing_from_window = sorted(P - set(E.case_id))
assert len(P) == 30
E['zac_pick'] = E.case_id.isin(P)
E['pick_round'] = np.where(E.zac_pick, E[E.zac_pick].groupby('stratum').cumcount().reindex(E.index), -1)
picks = E[E.zac_pick].copy()
picks['rank_among_date_eligible'] = picks.within_stratum
picks['implied_skipped_before'] = picks.within_stratum - picks.pick_round
R = int(picks.pick_round.max())
h_star = picks.loc[picks.pick_round == R, 'sample_order'].max()
# Zac's ordering = sort by (round, hash); his head(30) must be exactly the picks with (round, hash) <= (R, h*).

# Tail constraints per stratum: the next eligible ticket after the last pick must sort after (R, h*).
strata_rows = []
for s, g in E.groupby('stratum'):
    g = g.sort_values('sample_order')
    gp = g[g.zac_pick]
    last_rank = int(gp.within_stratum.max()) if len(gp) else -1
    r_s = len(gp) - 1
    rest = g[g.within_stratum > last_rank]
    if r_s + 1 < R:
        tail = len(rest)
    elif r_s + 1 == R:
        tail = int((rest.sample_order < h_star).sum())
    else:
        tail = 0
    gaps = int((g.within_stratum <= last_rank).sum() - len(gp))
    strata_rows.append({'stratum': s, 'date_eligible_tickets': len(g), 'zac_picks': len(gp),
                        'max_round': r_s, 'skipped_between_picks': gaps, 'implied_ineligible_tail': tail,
                        'implied_no_device_total': gaps + tail})
strata = pd.DataFrame(strata_rows).sort_values('date_eligible_tickets', ascending=False)
strata.to_csv(OUT / f'{PREFIX}pilot_strata.csv', index=False)

# Contradiction test: a skipped ticket on the same machine as a pick must have a device match.
pick_machines = set(picks.machine_id)
skip_mask = pd.Series(False, index=E.index)
for s, g in E.groupby('stratum'):
    gp = g[g.zac_pick]
    last_rank = int(gp.within_stratum.max()) if len(gp) else -1
    r_s = len(gp) - 1
    between = g[(~g.zac_pick) & (g.within_stratum <= last_rank)]
    skip_mask.loc[between.index] = True
    rest = g[g.within_stratum > last_rank]
    if r_s + 1 < R:
        skip_mask.loc[rest.index] = True
    elif r_s + 1 == R:
        skip_mask.loc[rest[rest.sample_order < h_star].index] = True
skipped = E[skip_mask]
contradictions = int(skipped.machine_id.isin(pick_machines).sum())
K = int(skip_mask.sum())
# Tickets whose models have zero device-matched tickets in Zac's cell-25 table (models sorted before
# 'LVRR-WP' that are absent from his head(15) list) are known no-match tickets.
models_sorted = sorted(c.model.unique())
shown = [m_ for m_, *_ in ZAC_MODEL_MAP_HEAD15]
zero_match_models = [m_ for m_ in models_sorted if m_ < 'LVRR-WP' and m_ not in shown]
skipped_known_nomatch = int(skipped.model.isin(zero_match_models).sum())
picks_known_nomatch = int(picks.model.isin(zero_match_models).sum())

sg = pd.read_sql_query('SELECT case_id, service_group FROM case_base', conn).set_index('case_id').service_group
picks['pick_round'] = picks.pick_round.astype(int)
picks['implied_skipped_before'] = picks.implied_skipped_before.astype(int)
picks['service_group'] = picks.case_id.map(sg)
pc = picks[['case_id', 'stratum', 'pick_round', 'rank_among_date_eligible', 'implied_skipped_before', 'model', 'record_type',
            'status', 'service_group']].copy()
pc['opened_month'] = picks.opened_at.str[:7]
pc = pc.sort_values('case_id')
pc.to_csv(OUT / f'{PREFIX}pilot_consistency.csv', index=False)
print(pc.to_string(index=False))
print(strata.to_string(index=False))
naive_overlap = len(P & set(naive_pilot.case_id))
consistent = (not missing_from_window) and contradictions == 0 and picks_known_nomatch == 0
base_rate = 1358 / 7471
examined = K + 30
# Negative-binomial plausibility: P(>= K no-match draws before 30 matched) if each ticket is unmatched w.p. base_rate.
from math import comb
p_tail = 1 - sum(comb(j + 29, j) * (1 - base_rate) ** 30 * base_rate ** j for j in range(K))
diag('pilot: implied no-device tickets / examined', f'{K}/{examined}', f'P(>= {K} | p_unmatched={base_rate:.3f}) = {p_tail:.3f}')
diag('pilot: models of implied no-device tickets', json.dumps(skipped.model.value_counts().to_dict()))
diag('pilot: picks by service_group', json.dumps(picks.service_group.value_counts().to_dict()))
diag('pilot: picks by status', json.dumps(picks.status.value_counts().to_dict()))
diag('pilot: picks per stratum vs date-eligible share', json.dumps({s_: f"{int(n_)}/{int(t_)}" for s_, n_, t_ in
                                                                  strata[['stratum', 'zac_picks', 'date_eligible_tickets']].itertuples(index=False)}))
claim('C08_pilot_selection', 'Cell 8 / 5.1', "Zac's 30 pilot case_ids are consistent with his selection rule (lowest-hash eligible ticket per stratum per round)",
      ','.join(ZAC_PILOT[:3]) + ',... (30 ids, cell 34)',
      f'consistent={consistent}; rounds 0..{R}; implied no-device tickets={K} of {examined} examined ({100 * K / examined:.1f}%)',
      'partial' if consistent else 'mismatch',
      f'all 30 in date window: {not missing_from_window}; '
      f'implied-skipped tickets sharing a machine with a pick (contradiction): {contradictions}; '
      f'picks from zero-match models: {picks_known_nomatch}; skipped tickets from zero-match models: {skipped_known_nomatch}; '
      f'naive (no device filter) top-30 overlaps {naive_overlap}/30; overall no-match base rate {100 * base_rate:.1f}% '
      f'(P(>= {K} skipped before 30 matches) = {p_tail:.2f}). Per-pick skips in repro_sql_pilot_consistency.csv. '
      'Eligibility itself needs devices, so this is a necessary-condition test only.')

# ---------------------------------------------------------------------------------------------
# 6. Linkage cross-checks possible without devices.
# ---------------------------------------------------------------------------------------------
print('\n== Linkage (cell 11) logic checks ==')
alex_cases = int((c.record_type == 'alEx Case').sum())
model_totals = c.model.value_counts()
mm = pd.DataFrame(ZAC_MODEL_MAP_HEAD15, columns=['model', 'machine_type', 'matched_cases', 'machines'])
complete_models = [m_ for m_ in mm.model.unique() if m_ != 'LVRR-WP']  # LVRR-WP may continue past row 15
known = []
for m_ in complete_models + zero_match_models:
    matched = int(mm.loc[mm.model == m_, 'matched_cases'].sum())
    total = int(model_totals[m_])
    rt = c.loc[c.model == m_, 'record_type'].value_counts()
    known.append({'model': m_, 'cases': total, 'matched_cases_zac_cell25': matched, 'implied_unmatched': total - matched,
                  'alEx_Case_record_type': int(rt.get('alEx Case', 0)),
                  'min_unmatched_non_alEx_record_type': max(0, total - matched - int(rt.get('alEx Case', 0)))})
known = pd.DataFrame(known)
known.to_csv(OUT / f'{PREFIX}linkage_model_bounds.csv', index=False)
print(known.to_string(index=False))
min_non_alex_unmatched = int(known.min_unmatched_non_alEx_record_type.sum())
alex_picks = int((picks.record_type == 'alEx Case').sum())
claim('C11_linkage_unmatched_1358', 'Cell 11 / 1.1', "Printed: 1,358 tickets have no exact device-dictionary match",
      1358, f'not computable; alEx Case record type count = {alex_cases}', 'not_reproducible',
      f'Equality with the alEx Case count is a coincidence: Zac\'s own cell-25 table implies >= {min_non_alex_unmatched} unmatched '
      f'tickets whose record type is not alEx Case (models {", ".join(complete_models + zero_match_models)}), and {alex_picks} of his 30 '
      f'device-matched pilot tickets are alEx Case. Models with zero matched tickets in cell 25: {zero_match_models}.')
claim('C11_C25_machines_bound', 'Cells 11 + 17 + 25', 'cell-25 matched machines per model never exceed cell-17 affected machines',
      'sum over types per model', 'see repro_sql_linkage_model_bounds.csv',
      'match' if all(mm.groupby('model').machines.sum()[m_] <= c.loc[c.model == m_, 'machine_id'].nunique() for m_ in mm.model.unique()) else 'mismatch',
      'cross-table consistency only')
claim('C27_reason_split', 'Cell 27 / 3.3', 'ticket_cohort_exclusions reason split', json.dumps(ZAC_COHORT_EXCLUSIONS), 'needs devices/telemetry',
      'not_reproducible', f'Only the total ({excl_total}) is device-independent. Unmatched outside this cohort implied by Zac: '
      f'1358 - 1203 = {1358 - 1203} of {len(c) - excl_total} tickets that are planned/cancelled/duplicate or opened Aug 2026.')

# ---------------------------------------------------------------------------------------------
# 7. Extra diagnostics behind issues_noticed (aggregate only).
# ---------------------------------------------------------------------------------------------
print('\n== Diagnostics ==')
diag('workbook sha256 equals Zac', wb_sha == common.ZAC_WORKBOOK_SHA256)
rc = pd.read_sql_query('SELECT * FROM repeat_cases', conn)
diag('repeat eligible opened on 2026-08-01 (6665 vs 6664 Aug25-Jul26)', int((rc.month == '2026-08').sum()))
last_open = c.opened_at.max()
trunc = rc[pd.to_datetime(rc.opened_at) + pd.Timedelta(days=30) > pd.Timestamp(last_open)]
diag('eligible index tickets whose 30-day window ends after the last export timestamp', len(trunc),
     f'export ends {last_open}')
gap = rc.gap_days.dropna()
diag('repeat gaps within 1 minute of the 30-day boundary', int(((gap - 30).abs() < 1 / 1440).sum()))
diag('repeat gaps < 1 day (same-day re-contact, possible unlabelled duplicates)', int(((rc.repeat_30 == 1) & (rc.gap_days < 1)).sum()))
diag('repeat gaps < 1 hour', int(((rc.repeat_30 == 1) & (rc.gap_days < 1 / 24)).sum()))
diag('repeat gaps exactly 0 (simultaneous)', int(((rc.repeat_30 == 1) & (rc.gap_days == 0)).sum()))
# Same-category within 30 days by ANY later ticket (Zac's LEAD only looks at the next ticket).
sc = pd.read_sql_query("SELECT case_id,machine_id,opened_at,category FROM service_cases", conn)
sc['t'] = pd.to_datetime(sc.opened_at)
idx = sc[sc.opened_at < '2026-08-02']
mrg = idx.merge(sc, on='machine_id', suffixes=('', '_n'))
mrg = mrg[((mrg.t_n > mrg.t) | ((mrg.t_n == mrg.t) & (mrg.case_id_n > mrg.case_id))) & ((mrg.t_n - mrg.t) <= pd.Timedelta(days=30))]
any_same = mrg[mrg.category.notna() & (mrg.category == mrg.category_n)].case_id.nunique()
diag('index tickets with ANY same-category follow-up within 30 days', int(any_same),
     f"Zac's LEAD-based same_category_repeats = {int(repeats.loc[0, 'same_category_repeats'])}")
diag('repeat_30 tickets whose next ticket has missing category', int(((rc.repeat_30 == 1) & rc.next_category.isna()).sum()))
diag('repeat_30 tickets whose own category is missing', int(((rc.repeat_30 == 1) & rc.category.isna()).sum()))
cb = pd.read_sql_query('SELECT * FROM case_base', conn)
diag('status x service_group (Dispatch row)', json.dumps(cb[cb.status == 'Dispatch'].service_group.value_counts().to_dict()))
diag('Missing trouble code group by status', json.dumps(cb[cb.service_group == 'Missing trouble code'].status.value_counts().to_dict()))
pw = cb[cb.service_group == 'Planned work']
diag('Planned work composition', json.dumps({'PM code': int((pw.trouble_code == 'Preventative Maintenance').sum()),
                                             'Installation code': int((pw.trouble_code == 'Installation').sum()),
                                             'Install Case record type': int((pw.record_type == 'Install Case').sum())}))
diag('Install Case tickets with a non-planned trouble code',
     int(((cb.record_type == 'Install Case') & ~cb.trouble_code.isin(['Preventative Maintenance', 'Installation'])).sum()))
diag('General Case record type count vs Cancelled request group', f"{int((c.record_type == 'General Case').sum())} vs "
     f"{int((cb.service_group == 'Cancelled request').sum())}; overlap "
     f"{int(((c.record_type == 'General Case') & (c.category == 'Cancelled Request')).sum())}")
diag("record_type '.' tickets", int((c.record_type == '.').sum()))
diag('serials (machine ids) with >1 customer label', int((c.groupby('machine_id').customer.nunique() > 1).sum()))
diag('serials (machine ids) with >1 model label', int((c.groupby('machine_id').model.nunique() > 1).sum()))
acct_norm = raw['Account Name'].map(common.clean).str.casefold().str.replace(r'[^a-z0-9]', '', regex=True)
diag('customer labels that collapse after case/punctuation/space normalisation',
     int(raw['Account Name'].map(common.clean).nunique() - acct_norm.nunique()))
model_norm = c.model.str.casefold().str.replace(r'[^a-z0-9]', '', regex=True)
diag('model labels that collapse after case/punctuation normalisation', int(c.model.nunique() - model_norm.nunique()))
diag('customer rank-10 vs rank-11 cases (tie at top-10 boundary?)', f"{int(customers.cases.iloc[9])} vs {int(customers.cases.iloc[10])}")
ties = repeat_models.eligible_tickets.duplicated(keep=False).sum()
diag('repeat_by_model rows with tied eligible_tickets (unstable order)', int(ties))
ties_issue = issues.cases.duplicated(keep=False).sum()
diag('issue_mix rows with tied cases (unstable order)', int(ties_issue))
diag('date-eligible pilot window starts 2025-09-02: tickets opened 2025-09-01 excluded', int(c.opened_at.str.startswith('2025-09-01').sum()))
diag('pilot strata present (date-eligible)', len(strata))
diag('NTF category under trouble codes', json.dumps(c[c.category == 'No Trouble Found'].trouble_code.fillna('NULL').value_counts().to_dict()))
diag('Duplicate Case category under trouble codes', json.dumps(c[c.category == 'Duplicate Case'].trouble_code.fillna('NULL').value_counts().to_dict()))
diag('Cancelled Request category under trouble codes', json.dumps(c[c.category == 'Cancelled Request'].trouble_code.fillna('NULL').value_counts().to_dict()))
diag('category present but trouble_code NULL', int((c.trouble_code.isna() & c.category.notna()).sum()))
diag('subcategory present but category NULL', int((c.category.isna() & c.subcategory.notna()).sum()))
open_rc = rc[rc.status == 'Dispatch']
diag('open (Dispatch) tickets in repeat denominator', len(open_rc))
diag('Dispatch (open) tickets by opened month', json.dumps(c[c.status == 'Dispatch'].opened_at.str[:7].value_counts().sort_index().to_dict()))
diag('Trouble Reported shorter than 10 characters (length only)', int((c.reported_length < 10).sum()))
diag('Miscellaneous trouble code: NTF+Cancelled+Duplicate share', f"{int(c.category.isin(['No Trouble Found', 'Cancelled Request', 'Duplicate Case']).sum())}/{int((c.trouble_code == 'Miscellaneous').sum())}")
pd.DataFrame(diagnostics).to_csv(OUT / f'{PREFIX}diagnostics.csv', index=False)

# ---------------------------------------------------------------------------------------------
# 8. Write claims and gate.
# ---------------------------------------------------------------------------------------------
cl = pd.DataFrame(claims)
cl['sql_verbatim'] = VERBATIM
cl.to_csv(OUT / f'{PREFIX}claims.csv', index=False)
print('\nClaim status counts:', cl.status.value_counts().to_dict())
EXPECTED_MISMATCH = {'C02_workbook_sha256'}  # file bytes differ; contents reproduce
unexpected = sorted(set(cl.loc[cl.status == 'mismatch', 'claim_id']) - EXPECTED_MISMATCH)
assert not unexpected, f'Unexpected mismatches: {unexpected}'
print('PASS: every case-only claim reproduces; only the known workbook checksum differs.')
