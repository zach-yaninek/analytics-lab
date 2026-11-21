"""Inventory support for docs/01_what_zac_did.md.

Re-derives the Excel-only headline numbers that Zac's notebook printed, checks the
structure of his provisional code taxonomy, and describes the pilot strata. Output is
aggregate / pseudonymous only (Customer NNN, T#####, generic category labels).

Run: cd /home/user/analytics-lab && python3 -I verification/01_excel_reproducibility.py
Writes: verification/outputs/01_excel_reproducibility.csv
        verification/outputs/01_taxonomy_buckets.csv
        verification/outputs/01_pilot_strata.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from common import (OUTPUTS, XLS, ZAC_WORKBOOK_SHA256, build_cases, build_maps, case_database, load_raw,
                    pilot_order, sha256_file)

OUTPUTS.mkdir(parents=True, exist_ok=True)
rows = []


def record(section, metric, zac, ours):
    if isinstance(zac, float) or isinstance(ours, float):
        match = abs(float(zac) - float(ours)) < 0.006
    else:
        match = str(zac) == str(ours)
    rows.append({'section': section, 'metric': metric, 'zac_printed': zac, 'recomputed': ours,
                 'match': 'yes' if match else 'NO'})


# pandas 3 reads blank workbook cells into str-dtype columns as NaN, and common.clean(NaN)
# returns the string 'nan' instead of None. Zac's Colab run (object columns holding None)
# produced SQL NULLs. Restore None before cleaning so the rebuilt table matches cell 4.
raw = load_raw()
raw = raw.astype(object).where(raw.notna(), None)
maps = build_maps(raw)
cases = build_cases(raw, maps)
conn = case_database(cases)
assert not cases.isin(['nan', 'None', 'NaT']).any().any(), 'stringified missing values leaked into cases'
sql = lambda s: pd.read_sql_query(s, conn)

record('0 inputs', 'workbook sha256 equals checksum in cell 2', 'True', str(sha256_file(XLS) == ZAC_WORKBOOK_SHA256))

# ---- 1.1 record quality (Excel part only; linkage and telemetry coverage need the DB)
q = sql("""SELECT COUNT(*) cases, COUNT(DISTINCT case_id) distinct_cases, COUNT(DISTINCT customer) customers,
 COUNT(DISTINCT machine_id) case_machines, COUNT(DISTINCT model) models, MIN(opened_at) first_opened,
 MAX(opened_at) last_opened FROM cases""").iloc[0]
for k, z in [('cases', 7471), ('distinct_cases', 7471), ('customers', 845), ('case_machines', 3773),
             ('models', 31), ('first_opened', '2025-08-01 07:22:00'), ('last_opened', '2026-08-31 17:45:00')]:
    record('1.1', k, z, q[k])

# ---- 1.2 field completeness and hierarchy ambiguity
f = sql("""
SELECT 'Trouble Reported' field, SUM(reported_present=0) missing, 100.0*SUM(reported_present=0)/COUNT(*) missing_pct FROM cases
UNION ALL SELECT 'Model #',SUM(model IS NULL),100.0*SUM(model IS NULL)/COUNT(*) FROM cases
UNION ALL SELECT 'Trouble Code',SUM(trouble_code IS NULL),100.0*SUM(trouble_code IS NULL)/COUNT(*) FROM cases
UNION ALL SELECT 'Trouble Code Category',SUM(category IS NULL),100.0*SUM(category IS NULL)/COUNT(*) FROM cases
UNION ALL SELECT 'Trouble Code Sub Category',SUM(subcategory IS NULL),100.0*SUM(subcategory IS NULL)/COUNT(*) FROM cases
UNION ALL SELECT 'Trouble Resolution',SUM(resolution_present=0),100.0*SUM(resolution_present=0)/COUNT(*) FROM cases""")
for field, z in [('Trouble Reported', 0), ('Model #', 0), ('Trouble Code', 101), ('Trouble Code Category', 330),
                 ('Trouble Code Sub Category', 2315), ('Trouble Resolution', 641)]:
    record('1.2', f'missing {field}', z, int(f.loc[f.field == field, 'missing'].iloc[0]))
amb = sql("""SELECT trouble_code, subcategory, COUNT(DISTINCT category) categories, COUNT(*) cases
FROM cases WHERE trouble_code IS NOT NULL AND subcategory IS NOT NULL AND category IS NOT NULL
GROUP BY trouble_code,subcategory HAVING COUNT(DISTINCT category)>1 ORDER BY cases DESC""")
record('1.2', 'code/subcategory combos spanning >1 category', 6, len(amb))
record('1.2', 'ambiguity row cases (in printed order)', '292;125;57;25;21;11', ';'.join(map(str, amb.cases)))

# ---- 1.3 service groups
sg = sql("SELECT service_group, COUNT(*) cases FROM case_base GROUP BY service_group").set_index('service_group').cases
for g, z in [('Other recorded issue', 6508), ('No Trouble Found', 577), ('Cancelled request', 247),
             ('Missing trouble code', 101), ('Planned work', 23), ('Duplicate case', 15)]:
    record('1.3', f'service_group {g}', z, int(sg.get(g, 0)))
record('1.3', 'unplanned population', 7186, int(sql('SELECT COUNT(*) n FROM service_cases').n[0]))

# ---- 2.1 workload
cust = sql("""SELECT customer,COUNT(*) cases,COUNT(DISTINCT machine_id) affected_machines,
 100.0*COUNT(*)/(SELECT COUNT(*) FROM cases) share_pct FROM cases GROUP BY customer ORDER BY cases DESC,customer""")
zac_top = 'Customer 171:123;Customer 029:116;Customer 641:92;Customer 529:91;Customer 054:78;' \
          'Customer 479:71;Customer 308:70;Customer 062:68;Customer 602:64;Customer 489:61'
record('2.1', 'top-10 customers (label:cases)', zac_top,
       ';'.join(f'{a}:{b}' for a, b in zip(cust.customer.head(10), cust.cases.head(10))))
record('2.1', 'top-10 customers affected machines', '45;56;40;31;32;21;28;31;38;36',
       ';'.join(map(str, cust.affected_machines.head(10))))
record('2.1', 'top-10 customer share %', 11.2, round(cust.share_pct.head(10).sum(), 1))
y = 100 * cust.cases.cumsum() / cust.cases.sum()
record('2.1', 'customer labels needed for 50% (chart 08)', 126, int(np.searchsorted(y.to_numpy(), 50) + 1))
mod = sql("""SELECT model,COUNT(*) cases,COUNT(DISTINCT machine_id) affected_machines,
 100.0*COUNT(*)/(SELECT COUNT(*) FROM cases) share_pct FROM cases GROUP BY model ORDER BY cases DESC,model""")
record('2.1', 'top-10 models (cases)', '1426;1244;936;724;589;575;456;305;158;143', ';'.join(map(str, mod.cases.head(10))))
record('2.1', 'top-10 models (affected machines)', '710;612;492;397;313;254;237;163;59;67',
       ';'.join(map(str, mod.affected_machines.head(10))))
record('2.1', 'top-3 model share %', 48.3, round(mod.share_pct.head(3).sum(), 1))

# ---- 2.2 issue mix
iss = sql("""SELECT COALESCE(category,'[Missing]') category,COUNT(*) cases FROM service_cases
 GROUP BY category ORDER BY cases DESC""")
record('2.2', 'top-10 categories (cases)', '1124;679;588;577;568;562;515;510;325;227', ';'.join(map(str, iss.cases.head(10))))
record('2.2', 'top category', 'Deposit Door', iss.category.iloc[0])
heat = sql('SELECT model, COUNT(*) n FROM service_cases GROUP BY model ORDER BY n DESC').head(8)
record('2.2', 'heatmap model n (chart 09)', '1393;1211;897;695;558;554;427;298', ';'.join(map(str, heat.n)))

# ---- 3.4 case-only monthly series
cm = sql("""SELECT month,COUNT(*) all_tickets,
 SUM(service_group NOT IN ('Planned work','Cancelled request','Duplicate case')) unplanned_tickets
 FROM case_base GROUP BY month ORDER BY month""")
record('3.4', 'case_monthly all_tickets (13 months)', '567;581;663;504;596;601;552;613;557;515;632;549;541',
       ';'.join(map(str, cm.all_tickets)))
record('3.4', 'case_monthly unplanned (13 months)', '552;550;629;477;570;586;534;601;542;485;604;534;522',
       ';'.join(map(str, cm.unplanned_tickets)))

# ---- 4.1 repeats (Zac's view verbatim)
conn.executescript("""
DROP VIEW IF EXISTS repeat_cases;
CREATE VIEW repeat_cases AS
WITH ordered AS (
 SELECT *,LEAD(opened_at) OVER(PARTITION BY machine_id ORDER BY opened_at,case_id) next_opened,
 LEAD(category) OVER(PARTITION BY machine_id ORDER BY opened_at,case_id) next_category
 FROM service_cases)
SELECT *,julianday(next_opened)-julianday(opened_at) gap_days,
 CASE WHEN julianday(next_opened)-julianday(opened_at) BETWEEN 0 AND 30 THEN 1 ELSE 0 END repeat_30,
 CASE WHEN julianday(next_opened)-julianday(opened_at) BETWEEN 0 AND 30 AND category IS NOT NULL AND category=next_category THEN 1 ELSE 0 END same_category_30
FROM ordered WHERE opened_at<'2026-08-02';""")
r = sql("""SELECT COUNT(*) eligible_tickets,COUNT(DISTINCT machine_id) machines,SUM(repeat_30) repeat_tickets,
 SUM(same_category_30) same_category_repeats,100.0*SUM(repeat_30)/COUNT(*) repeat_pct,
 100.0*SUM(same_category_30)/COUNT(*) same_category_repeat_pct,SUM(repeat_30=1 AND gap_days=0) simultaneous_followups
 FROM repeat_cases""").iloc[0]
for k, z in [('eligible_tickets', 6665), ('machines', 3495), ('repeat_tickets', 1574), ('same_category_repeats', 515),
             ('repeat_pct', 23.62), ('same_category_repeat_pct', 7.73), ('simultaneous_followups', 0)]:
    record('4.1', k, z, round(float(r[k]), 2) if isinstance(z, float) else int(r[k]))
rm = sql("""SELECT model,COUNT(*) eligible_tickets,SUM(repeat_30) repeat_tickets FROM repeat_cases
 GROUP BY model ORDER BY eligible_tickets DESC""").head(10)
record('4.1', 'repeat_by_model top-10 eligible', '1288;1101;829;655;526;518;402;284;133;130', ';'.join(map(str, rm.eligible_tickets)))
record('4.1', 'repeat_by_model top-10 repeats', '299;265;183;134;160;118;93;42;41;48', ';'.join(map(str, rm.repeat_tickets)))

# ---- 6.1 Excel-only checks reproduced as Zac wrote them
case_frame = cases.copy()
planned = case_frame.trouble_code.isin(['Preventative Maintenance', 'Installation']) | case_frame.record_type.eq('Install Case')
filt = case_frame[~planned & ~case_frame.category.isin(['Cancelled Request', 'Duplicate Case'])].copy()
filt = filt.sort_values(['machine_id', 'opened_at', 'case_id'])
filt['opening'] = pd.to_datetime(filt.opened_at)
filt['next'] = filt.groupby('machine_id').opening.shift(-1)
filt['gap'] = (filt['next'] - filt.opening).dt.total_seconds() / 86400
valid = filt[filt.opened_at < '2026-08-02']
record('6.1', 'check 12 pandas repeat count', 1574, int(valid.gap.between(0, 30).sum()))
record('6.1', 'check 13 pandas missing subcategory', 2315, int(case_frame.subcategory.isna().sum()))
record('6.1', 'check 1 case ids unique', 'True', str(case_frame.case_id.is_unique))
record('6.1', 'check 11 customer total == model total == cases', 'True',
       str(int(cust.cases.sum()) == int(mod.cases.sum()) == len(case_frame)))

pd.DataFrame(rows).to_csv(OUTPUTS / '01_excel_reproducibility.csv', index=False)

# ---- Taxonomy structure (cell 4 lookup, verbatim)
groups = {'Success': ['00'], 'User behavior': ['04', '07', '10', '19', '21', '50', '60', '61', '78'],
          'Stock-out': ['03', '22', '51', '77'],
          'Operational status': ['53', '55', '68', '69', '70', '71', '72', '73', '74', '75', '76', '82', '83'],
          'Mechanical fault': ['02', '11', '14', '16', '17', '18', '31', '32', '33', '34', '35', '66', '67'],
          'Electronics/software/comms': ['05', '06', '08', '09', '13', '23', '24', '25', '52', '54'],
          'Door issue': ['12', '15', '20', '26', '27', '30', '41', '42', '43', '44', '45', '46', '47', '48', '56', '57',
                         '58', '59', '62', '63', '65', '79', '80', '81'],
          'Incomplete transaction': ['01'],
          'Undefined': ['28', '29', '36', '37', '38', '39', '40', '49', '64'] + [str(n) for n in range(84, 100)]}
allcodes = [k for ks in groups.values() for k in ks]
tax = pd.DataFrame([{'bucket': g, 'n_codes': len(ks), 'provisional_fault': int(g in ('Mechanical fault', 'Electronics/software/comms')),
                     'codes': ' '.join(ks)} for g, ks in groups.items()])
tax.to_csv(OUTPUTS / '01_taxonomy_buckets.csv', index=False)
print(tax[['bucket', 'n_codes', 'provisional_fault']].to_string(index=False))
print('total codes', len(allcodes), 'distinct', len(set(allcodes)),
      'covers 00-99 exactly:', sorted(allcodes) == [f'{i:02d}' for i in range(100)])

# ---- Pilot strata: trouble codes of the 30 printed pilot case ids, plus Excel-side eligibility window
pilot_ids = ['T00705', 'T00783', 'T00951', 'T00957', 'T01157', 'T01287', 'T01629', 'T01795', 'T01796', 'T01797',
             'T02128', 'T02229', 'T02268', 'T03075', 'T03079', 'T03326', 'T03959', 'T04699', 'T04907', 'T05185',
             'T05506', 'T05683', 'T05924', 'T06107', 'T06354', 'T06445', 'T06663', 'T06672', 'T06712', 'T06912']
win = cases[cases.opened_at.between('2025-09-02', '2026-07-31 23:59:59')].copy()
win['stratum'] = win.trouble_code.fillna('Missing')
win['sample_order'] = win.case_id.map(pilot_order)
win['rank_in_stratum_excel_window'] = win.sort_values('sample_order').groupby('stratum').cumcount()
p = win[win.case_id.isin(pilot_ids)]
print('pilot ids found in Excel window:', len(p), 'of', len(pilot_ids))
strata = (win.groupby('stratum').size().rename('window_tickets').to_frame()
          .join(p.groupby('stratum').size().rename('pilot_tickets')).fillna(0).astype(int)
          .sort_values('window_tickets', ascending=False))
strata.to_csv(OUTPUTS / '01_pilot_strata.csv')
print(strata.to_string())
print('tickets in Excel window (before device-match filter):', len(win), 'strata:', win.stratum.nunique())
print('pilot rank-in-stratum (Excel window, before device filter):', sorted(p.rank_in_stratum_excel_window.tolist()))
print('pilot service groups:', sql("SELECT service_group, COUNT(*) n FROM case_base WHERE case_id IN (%s) GROUP BY 1"
                                   % ','.join(f"'{x}'" for x in pilot_ids)).to_dict('records'))

out = pd.DataFrame(rows)
print(out.to_string(index=False, max_colwidth=60))
print('mismatches:', int((out.match == 'NO').sum()), 'of', len(out))
