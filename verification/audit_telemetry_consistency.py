"""Adversarial logic audit of the telemetry-dependent cells of Zac's notebook (4, 6, 8, 11, 23, 25,
27, 29, 34, 37) WITHOUT the telemetry database.

What this script does
  1. Encodes every number Zac printed in those cells as a constant and checks the cross-table
     identities that must hold between them (sums, differences, rounding, bounds).
  2. Recomputes the case-side quantities that those identities depend on from the workbook
     (via common.py), e.g. unplanned tickets per month, month-boundary sensitivity, pilot anchors.
  3. Runs Zac's SQL *verbatim* (each string is asserted to occur in the notebook source) on small
     synthetic tables to demonstrate the semantics that drive the audit findings: the CASE
     precedence in ticket_cohort_exclusions, what cell 25's host/type counts include, and which
     cell-37 checks still pass when the logic is deliberately broken (tautology tests).

Status values in the output CSV
  PASS  identity holds          FAIL  identity violated
  INFO  derived quantity        FLAG  logic issue demonstrated (metric/check does not mean
                                      what the text says, or cannot detect the error it implies)

Privacy: output contains only pseudonyms (T#####, Customer NNN), aggregate counts, generic labels.

Run: cd /home/user/analytics-lab && python3 -I verification/audit_telemetry_consistency.py
Writes: verification/outputs/audit_tel_identities.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import datetime as dt
import json
import math
import re
import sqlite3

import numpy as np
import pandas as pd

import common

OUT = common.OUTPUTS
OUT.mkdir(parents=True, exist_ok=True)
ROWS = []


def rec(cid, cell, check, kind, zac, ours, status, note=''):
    ROWS.append({'id': cid, 'cell': cell, 'check': check, 'kind': kind, 'zac_printed': zac,
                 'computed': ours, 'status': status, 'note': note})
    print(f'[{status:4}] {cid:8} c{cell:<6} {check} | zac={zac} | ours={ours}' + (f' | {note}' if note else ''))


def eq(cid, cell, check, zac, ours, note=''):
    rec(cid, cell, check, 'identity', zac, ours, 'PASS' if zac == ours else 'FAIL', note)


def rounds_to(cid, cell, check, printed, exact, decimals=2, note=''):
    ok = abs(round(exact, decimals) - printed) < 10 ** (-decimals) / 2 + 1e-12
    rec(cid, cell, check, 'rounding', printed, round(exact, 6), 'PASS' if ok else 'FAIL', note)


def bound(cid, cell, check, cond, zac, ours, note=''):
    rec(cid, cell, check, 'bound', zac, ours, 'PASS' if cond else 'FAIL', note)


def info(cid, cell, check, ours, zac='', note=''):
    rec(cid, cell, check, 'derived', zac, ours, 'INFO', note)


def flag(cid, cell, check, ours, zac='', note='', kind='logic'):
    rec(cid, cell, check, kind, zac, ours, 'FLAG', note)


# =============================================================================================
# 0. Zac's printed outputs (data/derived/notebook_dump.md), transcribed as constants.
# =============================================================================================
TOTAL = 118_047_569                       # cell 9 / 11 / 23
SIZES = {'cases': 7471, 'devices': 7183, 'codes': 49, 'telemetry_month_code': 418_188,
         'source_code_totals': 49, 'pilot_selection': 30, 'pilot_events': 4736, 'pilot_window_counts': 90}
QUALITY = {'cases': 7471, 'customers': 845, 'case_machines': 3773, 'models': 31}
LINK = {'cases': 7471, 'matched_cases': 6113, 'matched_machines': 3041, 'matched_pct': 81.82, 'unmatched_msg': 1358}
COVER = {'first': '2025-08-01', 'last': '2026-08-28', 'represented': TOTAL, 'transacting_machines': 6951}
BUCKETS = {'Success': (110_166_059, 93.32), 'Stock-out': (3_236_592, 2.74), 'Door issue': (2_212_968, 1.87),
           'Mechanical fault': (844_284, 0.72), 'User behavior': (796_042, 0.67),
           'Incomplete transaction': (473_188, 0.40), 'Operational status': (268_236, 0.23),
           'Electronics/software/comms': (45_235, 0.04), 'Undefined': (4_959, 0.00), 'Malformed': (6, 0.00)}
NON_OK, NON_OK_PCT, FAULTS, FAULT_RATE, EX05_RATE, FINDING7_PCT = 7_881_510, 6.68, 889_519, 7.54, 7.43, 0.75
MAP_SUMMARY = {'models_multi_type': 16, 'customers_multi_host': 31, 'hosts_multi_customer': 83}
MODEL_MAP_15 = [('A-LC', 'Unknown', 10, 5), ('A-LC', 'alc-1', 2, 2), ('LC-24', 'mlc-1', 27, 16),
                ('LC-30', 'mlc-1', 255, 132), ('LC-30', 'Unknown', 1, 1), ('LVD-Remote', 'scrubex-2', 465, 241),
                ('LVD-Remote', 'scrubex-1', 23, 16), ('LVD-Remote', 'Unknown', 4, 3),
                ('LVD-Remote-2.0', 'scrubex2.0-2', 1227, 608), ('LVD-Remote-2.0', 'Unknown', 13, 6),
                ('LVD-Remote-2.0', 'scrubex2.0-3', 3, 1), ('LVD-Remote-2.0', 'sd2.0-49', 1, 1),
                ('LVLR-WOP', 'scrubex-1', 4, 2), ('LVRR-WOP', 'scrubex-3', 14, 6), ('LVRR-WP', 'scrubex-3', 293, 156)]
COHORT = {'all': dict(mm=70_057, tickets=4_933, tx=109_344_700, zero=65_847),
          'known': dict(mm=69_155, tickets=4_916, tx=108_944_603, zero=64_961)}
EXCL = {'Included in comparison': 4916, 'No device match': 1203, 'No transactions in ticket month': 479,
        'Missing host': 48, 'Shared/internal host': 18}
RATES_15 = pd.DataFrame([
    ('sbsx-51', 31, 319, 66, 907_989, 5_055, 20.69, 5.57), ('sd-49', 53, 584, 53, 440_144, 43_905, 9.08, 99.75),
    ('scrubex-7', 116, 1_352, 111, 2_660_481, 0, 8.21, 0.00),
    ('scrubex2.0-2', 1_172, 12_329, 999, 24_268_373, 318_802, 8.10, 13.14),
    ('scrubex2.0-3', 1_072, 11_141, 894, 17_881_352, 2_164, 8.02, 0.12),
    ('alex2.0-3', 470, 5_011, 397, 6_018_886, 32_699, 7.92, 5.43),
    ('alex2.0-1', 329, 3_571, 266, 4_404_065, 10_731, 7.45, 2.44),
    ('scrubex2.0-4', 913, 9_442, 684, 13_908_698, 68_082, 7.24, 4.89),
    ('scrubex-2', 520, 5_873, 397, 12_252_356, 171_892, 6.76, 14.03),
    ('mlc-1', 444, 5_087, 334, 4_475_320, 93_836, 6.57, 20.97),
    ('scrubex-1', 112, 1_246, 79, 2_154_700, 26_265, 6.34, 12.19),
    ('scrubex2.0-5', 153, 1_606, 89, 1_393_972, 6_631, 5.54, 4.76),
    ('scrubex-4', 366, 4_143, 204, 6_230_453, 32_354, 4.92, 5.19),
    ('scrubex-3', 494, 5_484, 246, 9_721_466, 17, 4.49, 0.00),
    ('scrubex-5', 82, 938, 37, 783_740, 5_766, 3.94, 7.36)],
    columns=['machine_type', 'machines', 'mm', 'tickets', 'tx', 'faults', 'rate100', 'fault1000'])
OVERALL_RATE = 7.11
MONTHLY = pd.DataFrame([
    ('2025-08', 5420, 360, 8_704_739, 6.64, 6.82), ('2025-09', 5605, 414, 9_040_975, 7.39, 7.10),
    ('2025-10', 5677, 472, 9_512_486, 8.31, 7.52), ('2025-11', 5675, 353, 8_319_121, 6.22, 8.03),
    ('2025-12', 5718, 436, 8_852_073, 7.63, 8.13), ('2026-01', 5739, 449, 8_987_779, 7.82, 8.08),
    ('2026-02', 5763, 379, 8_480_682, 6.58, 8.15), ('2026-03', 5903, 440, 9_480_766, 7.45, 7.78),
    ('2026-04', 5968, 408, 9_348_766, 6.84, 7.69), ('2026-05', 5952, 354, 9_097_448, 5.95, 7.18),
    ('2026-06', 5903, 442, 9_378_351, 7.49, 6.95), ('2026-07', 5832, 409, 9_741_417, 7.01, 7.23)],
    columns=['month', 'mm', 'tickets', 'tx', 'rate100', 'fault1000'])
CASE_MONTHLY = pd.DataFrame([
    ('2025-08', 567, 552), ('2025-09', 581, 550), ('2025-10', 663, 629), ('2025-11', 504, 477),
    ('2025-12', 596, 570), ('2026-01', 601, 586), ('2026-02', 552, 534), ('2026-03', 613, 601),
    ('2026-04', 557, 542), ('2026-05', 515, 485), ('2026-06', 632, 604), ('2026-07', 549, 534),
    ('2026-08', 541, 522)], columns=['month', 'all_tickets', 'unplanned'])
UNPLANNED_N = 7186                        # cell 15
PILOT_SUMMARY = {-12: (30, 26, 26), 0: (30, 26, 26), 12: (30, 26, 26)}
PILOT0 = pd.DataFrame([
    ('T00705', 93, 5, 1452), ('T00783', 82, 5, 1742), ('T00951', 82, 5, 1659), ('T00957', 867, 8, 7687),
    ('T01157', 45, 4, 726), ('T01287', 672, 7, 2740), ('T01629', 0, 0, 0), ('T01795', 6, 2, 208),
    ('T01796', 28, 4, 175), ('T01797', 34, 5, 262), ('T02128', 465, 9, 1969), ('T02229', 152, 4, 1572),
    ('T02268', 74, 5, 1458), ('T03075', 118, 5, 1079), ('T03079', 8, 2, 2037), ('T03326', 246, 7, 3954),
    ('T03959', 0, 0, 0), ('T04699', 303, 4, 1373), ('T04907', 29, 2, 62), ('T05185', 17, 3, 712),
    ('T05506', 0, 0, 0), ('T05683', 0, 0, 0), ('T05924', 145, 3, 544), ('T06107', 83, 5, 2556),
    ('T06354', 89, 3, 113), ('T06445', 3, 2, 912), ('T06663', 71, 5, 881), ('T06672', 318, 3, 1580),
    ('T06712', 3, 1, 627), ('T06912', 27, 4, 1038)], columns=['case_id', 'non_success', 'distinct', 'all_events'])
LAST_CODES = pd.DataFrame([
    ('T00705', '43', '2025-09-07 16:03:14', 34, 1, 'Door issue'),
    ('T00705', '11', '2025-09-05 16:09:03', 17, 2, 'Mechanical fault'),
    ('T00705', '03', '2025-09-04 15:16:19', 39, 3, 'Stock-out'),
    ('T00705', '34', '2025-09-03 23:49:29', 1, 4, 'Mechanical fault'),
    ('T00705', '25', '2025-09-03 18:40:22', 2, 5, 'Electronics/software/comms'),
    ('T00783', '03', '2025-09-10 13:18:50', 62, 1, 'Stock-out'),
    ('T00783', '77', '2025-09-09 12:29:51', 2, 2, 'Stock-out'),
    ('T00783', '32', '2025-09-09 10:28:53', 8, 3, 'Mechanical fault'),
    ('T00783', '17', '2025-09-09 10:28:39', 9, 4, 'Mechanical fault'),
    ('T00783', '11', '2025-09-02 10:12:00', 1, 5, 'Mechanical fault'),
    ('T00951', '19', '2025-09-18 23:24:49', 37, 1, 'User behavior'),
    ('T00951', '20', '2025-09-18 20:59:32', 14, 2, 'Door issue'),
    ('T00951', '01', '2025-09-18 12:09:58', 11, 3, 'Incomplete transaction'),
    ('T00951', '04', '2025-09-18 12:04:00', 16, 4, 'User behavior'),
    ('T00951', '79', '2025-09-10 14:39:34', 4, 5, 'Door issue')],
    columns=['case_id', 'code', 'last_seen', 'occurrences', 'rank', 'bucket'])
LAST3 = {'tickets_ge3': 26, 'repeated': 25}
CLOCKS_DIFFER = 155
CELL37_CHECKS = 14

# =============================================================================================
# 1. Zac's code, verbatim, and a guard that it really is the notebook's text.
# =============================================================================================
NB_SRC = '\n'.join(''.join(c['source']) for c in json.loads(common.NOTEBOOK.read_text())['cells']
                   if c['cell_type'] == 'code')
_ws = lambda s: re.sub(r'\s+', ' ', s).strip()
NB_NORM = _ws(NB_SRC)


def verbatim(sql):
    assert _ws(sql) in NB_NORM, 'SQL not found verbatim in notebook: ' + sql[:80]
    return sql


GROUPS = {'Success': ['00'], 'User behavior': ['04', '07', '10', '19', '21', '50', '60', '61', '78'],
          'Stock-out': ['03', '22', '51', '77'],
          'Operational status': ['53', '55', '68', '69', '70', '71', '72', '73', '74', '75', '76', '82', '83'],
          'Mechanical fault': ['02', '11', '14', '16', '17', '18', '31', '32', '33', '34', '35', '66', '67'],
          'Electronics/software/comms': ['05', '06', '08', '09', '13', '23', '24', '25', '52', '54'],
          'Door issue': ['12', '15', '20', '26', '27', '30', '41', '42', '43', '44', '45', '46', '47', '48', '56',
                         '57', '58', '59', '62', '63', '65', '79', '80', '81'],
          'Incomplete transaction': ['01'],
          'Undefined': ['28', '29', '36', '37', '38', '39', '40', '49', '64'] + [str(n) for n in range(84, 100)]}
assert "'Undefined':['28','29','36','37','38','39','40','49','64']+[str(n) for n in range(84,100)]" in NB_SRC
for g, ks in GROUPS.items():
    assert "'" + g + "':[" + ','.join("'" + k + "'" for k in ks if not (g == 'Undefined' and int(k) >= 84)) in NB_SRC, g
LOOKUP = {k: g for g, ks in GROUPS.items() for k in ks}

AGG_SQL = verbatim('''SELECT external_device_id, substr(transaction_date_local,1,7) AS month,
 transaction_code, COUNT(*) AS n, MIN(transaction_date_local) AS first_date,
 MAX(transaction_date_local) AS last_date,
 SUM(transaction_time_local IS NOT transaction_time_utc) AS clocks_differ,
 SUM(transaction_time_utc IS NULL OR transaction_date_local IS NULL) AS missing_time
 FROM transaction_events NOT INDEXED
 GROUP BY external_device_id, substr(transaction_date_local,1,7), transaction_code''')
TOTALS_SQL = verbatim('SELECT transaction_code,COUNT(*) n FROM transaction_events GROUP BY transaction_code')
MAP_SUMMARY_SQL = verbatim("""
SELECT 'Case models spanning more than one telemetry type' measure,COUNT(*) value FROM
 (SELECT c.model FROM cases c JOIN devices d USING(machine_id) GROUP BY c.model HAVING COUNT(DISTINCT d.machine_type)>1)
UNION ALL SELECT 'Customers spanning more than one observed host',COUNT(*) FROM
 (SELECT c.customer FROM cases c JOIN devices d USING(machine_id) GROUP BY c.customer HAVING COUNT(DISTINCT d.host)>1)
UNION ALL SELECT 'Hosts linked to more than one case customer',COUNT(*) FROM
 (SELECT d.host FROM cases c JOIN devices d USING(machine_id) WHERE d.host IS NOT NULL GROUP BY d.host HAVING COUNT(DISTINCT c.customer)>1)
""")
RATE_VIEWS = verbatim("""
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
""")
COHORT_SQL = verbatim("""
SELECT 'All represented active machine-months' cohort,COUNT(*) active_machine_months,
 SUM(tickets) tickets,SUM(transactions) transactions, SUM(tickets=0) zero_ticket_months
FROM comparison_month
UNION ALL SELECT 'Known nonshared hosts',COUNT(*),SUM(tickets),SUM(transactions),SUM(tickets=0)
FROM comparison_month WHERE shared_internal_host=0 AND host IS NOT NULL
""")
EXCL_SQL = verbatim("""
SELECT CASE WHEN d.machine_id IS NULL THEN 'No device match'
 WHEN d.shared_internal_host=1 THEN 'Shared/internal host'
 WHEN d.host IS NULL THEN 'Missing host'
 WHEN m.machine_id IS NULL THEN 'No transactions in ticket month'
 ELSE 'Included in comparison' END reason,COUNT(*) tickets
FROM service_cases c LEFT JOIN devices d USING(machine_id)
LEFT JOIN machine_month m ON c.machine_id=m.machine_id AND c.month=m.month
WHERE c.month>='2025-08' AND c.month<'2026-08'
GROUP BY reason ORDER BY tickets DESC
""")
PILOT_SQL = verbatim("""
WITH offsets AS (SELECT -12 offset_hours UNION ALL SELECT 0 UNION ALL SELECT 12),
windows AS (
 SELECT p.case_id,o.offset_hours,datetime(c.opened_at,printf('%+d hours',o.offset_hours)) anchor
 FROM pilot_selection p JOIN cases c USING(case_id) CROSS JOIN offsets o),
counts AS (
 SELECT w.case_id,w.offset_hours,COUNT(e.transaction_code) non_success_events,
 COUNT(DISTINCT e.transaction_code) distinct_codes
 FROM windows w LEFT JOIN pilot_events e ON e.case_id=w.case_id
 AND e.transaction_time_utc>=datetime(w.anchor,'-30 days') AND e.transaction_time_utc<w.anchor
 GROUP BY w.case_id,w.offset_hours)
SELECT a.*,b.all_events,CASE WHEN b.all_events=0 THEN 'No transactions observed'
 WHEN a.non_success_events=0 THEN 'Only success transactions observed'
 ELSE 'Candidate codes available' END availability
FROM counts a JOIN pilot_window_counts b USING(case_id,offset_hours)
ORDER BY a.case_id,a.offset_hours
""")


def zac_devices(frame):
    """Cell 4's device post-processing, verbatim apart from the variable name."""
    devices = frame.copy()
    clean = common.clean
    devices.external_device_id = devices.external_device_id.map(clean)
    hosts = sorted(set(devices.clearview_url.dropna()))
    hostmap = {s: f'Host {i:03d}' for i, s in enumerate(hosts, 1)}
    devices['machine_id'] = devices.external_device_id
    devices['host'] = devices.clearview_url.map(hostmap)
    devices['shared_internal_host'] = devices.clearview_url.fillna('').str.rstrip('/').eq(common.SHARED_INTERNAL_HOST).astype(int)
    devices['machine_type'] = devices.machine_type.map(lambda x: clean(x).lower() if clean(x) else 'Unknown')
    return devices[['machine_id', 'machine_type', 'host', 'shared_internal_host']]


for line in ["devices['shared_internal_host']=devices.clearview_url.fillna('').str.rstrip('/').eq('" + common.SHARED_INTERNAL_HOST + "').astype(int)",
             "hosts=sorted(set(devices.clearview_url.dropna()))",
             "devices['machine_type']=devices.machine_type.map(lambda x:clean(x).lower() if clean(x) else 'Unknown')"]:
    assert line in NB_SRC, line

# =============================================================================================
# 2. Case table, rebuilt as in cell 4 (pandas-2 None semantics restored; see reproduce_sql.py).
# =============================================================================================
_orig_load_raw = common.load_raw


def _load_raw_pandas2(path=common.XLS):
    r = _orig_load_raw(path)
    return r.astype(object).where(r.notna(), None)


common.load_raw = _load_raw_pandas2
raw, maps, cases, conn = common.load_all()
assert conn.execute('SELECT SUM(trouble_code IS NULL) FROM cases').fetchone()[0] == 101
sc = pd.read_sql_query('SELECT case_id,customer,machine_id,opened_at,month,service_group FROM service_cases', conn)
cb = pd.read_sql_query('SELECT case_id,month,service_group FROM case_base', conn)
win = sc[(sc.month >= '2025-08') & (sc.month < '2026-08')]
print(f'pandas {pd.__version__}; cases {len(cases)}; unplanned Aug25-Jul26 {len(win)}')

# =============================================================================================
# 3. Cell 4 / 23: code buckets.
# =============================================================================================
codes_all = [f'{i:02d}' for i in range(100)]
dups = sum(len(ks) for ks in GROUPS.values()) - len(LOOKUP)
eq('B01', '4', 'lookup has no code assigned to two buckets', 0, dups)
eq('B02', '4', "every two-digit code '00'..'99' is in the lookup (100 codes)", 100, sum(k in LOOKUP for k in codes_all))
eq('B03', '4', 'lookup contains nothing except two-digit strings', 0, sum(not re.fullmatch(r'\d\d', k) for k in LOOKUP))
probes = {'5': None, '005': None, ' 05': None, '05 ': None, '100': None, '': None, 'dictionary NULL': None, 'int 5': None}
for p in probes:
    key = None if p == 'dictionary NULL' else (5 if p == 'int 5' else p)
    probes[p] = LOOKUP.get(key, 'Malformed')
flag('B04', '4', "values that would be bucketed 'Malformed' (lookup.get(x,'Malformed'))", json.dumps(probes),
     note="the 6 Malformed transactions carry a NON-NULL code that is in IPA's dictionary but is not a 2-digit "
          "string (e.g. '5','100',' 05', int 5). A NULL *telemetry* code is excluded: it cannot match the LEFT JOIN "
          "and would print an 11th, NULL-bucket row in cell 23 (10 rows printed), and cell-37 check 5 (groupby drops "
          "NaN keys) would fail.")
bucket_sum = sum(v[0] for v in BUCKETS.values())
eq('B05', '23', 'bucket transactions sum to all transactions', TOTAL, bucket_sum,
   'also proves no duplicated dictionary code is used (a duplicate would inflate the LEFT JOIN sum)')
eq('B06', '23', 'non-success = total - Success (code 00 only)', NON_OK, TOTAL - BUCKETS['Success'][0])
eq('B07', '23', 'non-success = sum of the 9 non-Success buckets', NON_OK, bucket_sum - BUCKETS['Success'][0])
rounds_to('B08', '23', 'non-success %', NON_OK_PCT, 100 * NON_OK / TOTAL)
eq('B09', '23', 'narrow faults = Mechanical + Electronics', FAULTS,
   BUCKETS['Mechanical fault'][0] + BUCKETS['Electronics/software/comms'][0])
rounds_to('B10', '23', 'narrow faults per 1,000', FAULT_RATE, 1000 * FAULTS / TOTAL)
rounds_to('B11', '39', 'finding 7: narrow faults %', FINDING7_PCT, 100 * FAULTS / TOTAL)
for i, (b, (n, pct)) in enumerate(BUCKETS.items()):
    rounds_to(f'B12.{i}', '23', f'all_transaction_pct for {b}', pct, 100 * n / TOTAL)
lo = math.ceil(FAULTS - (EX05_RATE + 0.005) * TOTAL / 1000)
hi = math.floor(FAULTS - (EX05_RATE - 0.005) * TOTAL / 1000)
info('B13', '23', 'code 05 count implied by 7.54 -> 7.43 per 1,000 (integer interval)', f'[{lo:,}, {hi:,}]',
     note=f'= {100*lo/BUCKETS["Electronics/software/comms"][0]:.1f}-{100*hi/BUCKETS["Electronics/software/comms"][0]:.1f}% '
          f'of the Electronics bucket; Electronics without 05 = {45235-hi:,}-{45235-lo:,}')
bound('B14', '23', 'implied code-05 count fits inside the Electronics bucket', 0 < lo <= hi <= 45_235, '<=45,235', f'{lo}-{hi}')
eq('B15', '9', 'dictionary rows (codes) = distinct telemetry codes (source_code_totals)', SIZES['codes'], SIZES['source_code_totals'],
   'with B05 and no NULL-bucket row, the 49 dictionary codes and the 49 telemetry codes are the same set; '
   'so at most 48 of the 100 lookup codes occur, and the Malformed code(s) are in IPA\'s own dictionary')

# =============================================================================================
# 4. Cell 6: aggregation.
# =============================================================================================
info('A01', '6/37', 'events whose local and UTC clock strings differ (IS NOT is NULL-safe)', CLOCKS_DIFFER,
     note=f'{CLOCKS_DIFFER/TOTAL*1e6:.2f} per million; 99.99987% identical -> the two columns are the same clock and '
          'one label is wrong. Includes rows where exactly one side is NULL (local NULL counts as differing).')
flag('A02', '6', 'month is substr(transaction_date_local) but pilot windows use transaction_time_utc',
     'no check that transaction_date_local = substr(transaction_time_utc,1,10)',
     note='with A01 the clocks are probably equal, but date_local is a third column never compared; '
          'one COUNT(*) WHERE transaction_date_local<>substr(transaction_time_utc,1,10) settles it')
info('A03', '11', 'MIN/MAX of transaction_date_local are ISO dates', f"{COVER['first']}..{COVER['last']}",
     note="text MIN/MAX would surface 'MM/DD/YYYY' or alphabetic dates; ISO extremes imply consistent ISO format at "
          'least in the first character; months outside Aug25-Aug26 cannot exist')
outside = TOTAL - COHORT['all']['tx']
info('A04', '11/27', 'transactions outside Aug 2025-Jul 2026 (= Aug 1-28 2026)', outside,
     note=f'{outside/28:,.0f}/day vs Jul 2026 known-host cohort {MONTHLY.tx.iloc[-1]/31:,.0f}/day -> Aug 2026 looks '
          'complete through the 28th; correctly excluded from rates')
eq('A05', '9', 'pilot_window_counts rows = 30 tickets x 3 offsets', SIZES['pilot_window_counts'], 30 * 3)
mm_aug26_max = COVER['transacting_machines']
bound('A06', '9/27', 'machine-month-code rows >= active machine-months (Aug25-Jul26 + Aug26)',
      SIZES['telemetry_month_code'] >= COHORT['all']['mm'], SIZES['telemetry_month_code'], COHORT['all']['mm'],
      note=f"average distinct codes per active machine-month in [{SIZES['telemetry_month_code']/(COHORT['all']['mm']+mm_aug26_max):.2f}, "
           f"{SIZES['telemetry_month_code']/COHORT['all']['mm']:.2f}]")

# =============================================================================================
# 5. Cell 11: linkage and coverage.
# =============================================================================================
rounds_to('L01', '11', 'matched_pct', LINK['matched_pct'], 100 * LINK['matched_cases'] / LINK['cases'])
eq('L02', '11', 'unmatched tickets message = cases - matched', LINK['unmatched_msg'], LINK['cases'] - LINK['matched_cases'])
eq('L03', '11', 'case table rows (rebuilt) = linkage cases', LINK['cases'], len(cases))
eq('L04', '11', 'distinct ticket serials (rebuilt) = case_machines', QUALITY['case_machines'], int(cases.machine_id.nunique()))
eq('L05', '4', 'blank serials in workbook (sorted() over {None,str} would have crashed cell 4)', 0,
   int(raw['Serial #'].map(common.clean).isna().sum()))
info('L06', '11', 'ticket serials with no device match', QUALITY['case_machines'] - LINK['matched_machines'],
     note=f"{100*(QUALITY['case_machines']-LINK['matched_machines'])/QUALITY['case_machines']:.1f}% of ticket serials; "
          f"{LINK['unmatched_msg']:,} tickets")
info('L07', '9/11', 'dictionary devices with zero transactions in the whole extract',
     SIZES['devices'] - COVER['transacting_machines'],
     note='cell 37 check 8 proves every transacting machine is in the dictionary, so 7,183-6,951 never transact')
model_matched = {}
for m, _t, n, _k in MODEL_MAP_15[:-1]:
    model_matched[m] = model_matched.get(m, 0) + n
model_cases = cases.model.value_counts()
bound('L08', '25', 'matched cases per fully-printed model <= its ticket count',
      all(model_matched[m] <= model_cases[m] for m in model_matched), '', json.dumps(
          {m: f'{model_matched[m]}/{int(model_cases[m])}' for m in model_matched}))
binary_sorted = sorted(cases.model.unique())
first_rows = list(dict.fromkeys(m for m, *_ in MODEL_MAP_15))
skipped = [m for m in binary_sorted[:binary_sorted.index('LVRR-WP') + 1] if m not in first_rows]
info('L09', '25', 'models that sort inside the printed range but have no row (must have 0 matched cases)',
     json.dumps(skipped), note='consistent with repro_sql_linkage_model_bounds.csv (A-MC, A-SC, LVD-LOCAL unmatched)')

# =============================================================================================
# 6. Cell 25: model->type and customer/host audit.
# =============================================================================================
types_by_model = {}
for m, t, *_ in MODEL_MAP_15[:-1]:
    types_by_model.setdefault(m, set()).add(t)
multi_incl = sorted(m for m, s in types_by_model.items() if len(s) > 1)
multi_excl = sorted(m for m, s in types_by_model.items() if len(s - {'Unknown'}) > 1)
flag('M01', '25', "COUNT(DISTINCT machine_type) counts 'Unknown' as a type (7 fully printed models)",
     f'multi-type incl. Unknown={multi_incl}; excl. Unknown={multi_excl}', MAP_SUMMARY['models_multi_type'],
     note=f'{len(multi_incl)-len(multi_excl)} of the {len(multi_incl)} visible multi-type models are multi-type only '
          f"because of 'Unknown'; the printed 16 is an upper bound (true count <= {16-(len(multi_incl)-len(multi_excl))})")
cust_serials = cases.groupby('customer').machine_id.nunique()
serial_custs = cases.groupby('machine_id').customer.nunique()
multi_serials = serial_custs[serial_custs > 1].index
info('M02', '25', 'customers with >=2 distinct ticket serials (upper bound before matching for "spanning >1 host")',
     int((cust_serials >= 2).sum()), MAP_SUMMARY['customers_multi_host'], note=f'of {QUALITY["customers"]} customers')
info('M03', '25', 'serials appearing under >1 customer label; customers involved; their tickets',
     f'{len(multi_serials)} serials; {cases[cases.machine_id.isin(multi_serials)].customer.nunique()} customers; '
     f'{int(cases.machine_id.isin(multi_serials).sum())} tickets', MAP_SUMMARY['hosts_multi_customer'],
     note='each such serial, if matched and hosted, links its host to >=2 customers by itself (<= 8 of the 83)')

# Synthetic test of Zac's map_summary SQL and cell-4 host processing.
dev_raw = pd.DataFrame({
    'external_device_id': ['A1', 'A2', 'B1', 'B2', 'C1', 'D1', 'E1', 'F1'],
    'machine_type': ['scrubex-2', None, 'scrubex-2', 'scrubex-2', 'mlc-1', 'mlc-1', 'mlc-1', 'mlc-1'],
    'clearview_url': ['https://h1.example', common.SHARED_INTERNAL_HOST, 'https://h2.example',
                      'https://h2.example/', 'https://h3.example', None, '', common.SHARED_INTERNAL_HOST.upper()]})
dev = zac_devices(dev_raw)
toy_cases = pd.DataFrame({'customer': ['Cust A', 'Cust A', 'Cust B', 'Cust B', 'Cust C', 'Cust D', 'Cust E', 'Cust F'],
                          'machine_id': ['A1', 'A2', 'B1', 'B2', 'C1', 'D1', 'E1', 'F1'],
                          'model': ['M1', 'M1', 'M1', 'M1', 'M2', 'M2', 'M2', 'M2']})
t = sqlite3.connect(':memory:')
toy_cases.to_sql('cases', t, index=False)
dev.to_sql('devices', t, index=False)
ms = dict(t.execute(MAP_SUMMARY_SQL).fetchall())
flag('M04', '25', 'synthetic: customer with own host + 1 machine on shared internal host',
     f"customers spanning >1 host = {ms['Customers spanning more than one observed host']} (A: own+internal, B: trailing-slash variant)",
     note='Zac\'s SQL counts the internal host as an observed host and treats URL spelling variants as different hosts; '
          'expected 0 genuine multi-host customers here', kind='synthetic')
flag('M05', '25', 'synthetic: model with one real type + Unknown',
     f"models spanning >1 type = {ms['Case models spanning more than one telemetry type']} (M1: scrubex-2 + Unknown)",
     note='expected 0 genuine multi-type models (M2 is mlc-1 only)', kind='synthetic')
e_row = dev[dev.machine_id == 'E1'].iloc[0]
f_row = dev[dev.machine_id == 'F1'].iloc[0]
flag('M06', '4/27', "synthetic: empty-string clearview_url and case/scheme variant of the internal URL",
     f"''-> host={e_row.host!r}, shared={e_row.shared_internal_host}; upper-case internal -> host={f_row.host!r}, shared={f_row.shared_internal_host}",
     note="'' is not NULL, gets a Host label and lands in the 'Known nonshared hosts' cohort; "
          "the shared flag only strips '/', so case/whitespace/http variants of the internal URL are not excluded",
     kind='synthetic')

# =============================================================================================
# 7. Cell 27: cohorts, exclusions, machine-type rates.
# =============================================================================================
A, K = COHORT['all'], COHORT['known']
dmm, dt_, dtx, dz = A['mm'] - K['mm'], A['tickets'] - K['tickets'], A['tx'] - K['tx'], A['zero'] - K['zero']
info('R01', '27', 'host-excluded active machine-months / tickets / transactions / zero-ticket months',
     f'{dmm} / {dt_} / {dtx:,} / {dz}',
     note=f'{dtx/dmm:,.0f} tx per excluded mm vs {K["tx"]/K["mm"]:,.0f} kept; ticket rate {100*dt_/dmm:.2f} vs '
          f'{100*K["tickets"]/K["mm"]:.2f} per 100 mm; All-represented rate = {100*A["tickets"]/A["mm"]:.2f}, so the host '
          f'exclusion moves the headline by only +{100*K["tickets"]/K["mm"]-100*A["tickets"]/A["mm"]:.2f}')
bound('R02', '27', 'tickets >= ticket-bearing machine-months (both cohorts)',
      A['tickets'] >= A['mm'] - A['zero'] and K['tickets'] >= K['mm'] - K['zero'],
      f"{A['tickets']}>={A['mm']-A['zero']}; {K['tickets']}>={K['mm']-K['zero']}",
      f"{K['tickets']/(K['mm']-K['zero']):.3f} tickets per ticket-bearing mm")
bound('R03', '27', 'excluded ticket-bearing mm <= excluded tickets', dmm - dz <= dt_, f'{dmm-dz}<={dt_}', dt_)
excl_total = sum(EXCL.values())
eq('R04', '27/29', 'exclusion reasons sum = Zac case_monthly unplanned Aug25-Jul26',
   int(CASE_MONTHLY.unplanned.iloc[:12].sum()), excl_total)
eq('R05', '27', 'exclusion reasons sum = rebuilt unplanned tickets Aug25-Jul26 (workbook)', excl_total, len(win))
eq('R06', '27/37', "'Included in comparison' = Known-host cohort tickets", EXCL['Included in comparison'], K['tickets'])
host_excl = EXCL['Missing host'] + EXCL['Shared/internal host']
host_excl_active = A['tickets'] - K['tickets']
eq('R07', '27', 'All-represented tickets = Included + host-excluded tickets in ACTIVE months',
   A['tickets'], EXCL['Included in comparison'] + host_excl_active)
flag('R08', '27', 'host-excluded tickets that fall in months with NO transactions (hidden by CASE precedence)',
     host_excl - host_excl_active, f'{host_excl} host-excluded, {host_excl_active} differ between cohorts',
     note="the CASE tests shared/missing host BEFORE 'no transactions', so the 479 counts silent months for "
          f"known-host devices only; device-matched tickets in silent months = 479 + {host_excl-host_excl_active} = "
          f"{EXCL['No transactions in ticket month']+host_excl-host_excl_active}")
dev_matched = excl_total - EXCL['No device match']
silent_all = EXCL['No transactions in ticket month'] + host_excl - host_excl_active
eq('R09', '27', 'device-matched tickets = All-represented tickets + tickets in silent months', dev_matched, A['tickets'] + silent_all)
info('R10', '27', 'share of device-matched tickets in silent machine-months: known-host vs host-excluded devices',
     f"{100*EXCL['No transactions in ticket month']/(K['tickets']+EXCL['No transactions in ticket month']):.1f}% vs "
     f"{100*(host_excl-host_excl_active)/host_excl:.1f}%",
     note='host-excluded devices are mostly non-reporting; the 17 tickets that differ are not the 66 that are excluded')
info('R11', '27', 'unplanned Aug25-Jul26 tickets with no device match', f"{EXCL['No device match']} "
     f"({100*EXCL['No device match']/excl_total:.2f}%)", note='close to the all-ticket 18.18% unmatched rate')
# Bias of dropping the 479 tickets (and their silent months) from numerator and denominator.
T, M, S = K['tickets'], K['mm'], EXCL['No transactions in ticket month']
rate = 100 * T / M
addback_lo, addback_hi = 100 * (T + S) / (M + S), 100 * (T + S) / (M + 1)
rest_mm = K['mm'] - int(RATES_15.mm.sum())
mach_lo = int(RATES_15.machines.sum()) + math.ceil(rest_mm / 12)
mach_hi = COVER['transacting_machines']
silent_lo, silent_hi = 12 * mach_lo - M, 12 * mach_hi - M
full_lo, full_hi = 100 * (T + S) / (M + silent_hi), 100 * (T + S) / (M + silent_lo)
flag('R12', '27', 'rate if the 479 silent-month tickets are added back with their own machine-months',
     f'[{addback_lo:.3f}, {addback_hi:.3f}] per 100 (vs {rate:.3f})', OVERALL_RATE,
     note=f'+{addback_lo-rate:.2f} to +{addback_hi-rate:.2f} (+{100*(addback_lo/rate-1):.1f}%); dropping both numerator '
          'and denominator of a down-all-month machine biases the active-month rate DOWN')
info('R13', '27', 'rate per installed machine-month if every cohort machine were installed all 12 months',
     f'[{full_lo:.2f}, {full_hi:.2f}] per 100', OVERALL_RATE,
     note=f'cohort machines in [{mach_lo:,}, {mach_hi:,}] -> silent zero-ticket months in [{silent_lo:,}, {silent_hi:,}]; '
          'adding those pulls the rate DOWN, so the net direction depends on install dates (not in the data)')
rounds_to('R14', '27', 'overall comparison rate = Known cohort tickets / mm', OVERALL_RATE, rate)
for i, r in RATES_15.iterrows():
    ok = (abs(round(100 * r.tickets / r.mm, 2) - r.rate100) < .005 + 1e-9 and
          abs(round(1000 * r.faults / r.tx, 2) - r.fault1000) < .005 + 1e-9 and
          r.machines <= r.mm <= 12 * r.machines and r.mm >= 100 and r.tickets >= 20)
    rec(f'R15.{i:02d}', '27', f'{r.machine_type}: rate/100, faults/1000, machines<=mm<=12*machines, chart screen',
        'row arithmetic', f'{r.rate100}/{r.fault1000}',
        f'{100*r.tickets/r.mm:.4f}/{1000*r.faults/r.tx:.4f}; {r.mm/r.machines:.2f} mo/machine', 'PASS' if ok else 'FAIL')
bound('R16', '27', 'printed 15 rows are sorted by rate descending', RATES_15.rate100.is_monotonic_decreasing, '', '')
s15 = RATES_15[['machines', 'mm', 'tickets', 'tx', 'faults']].sum()
rest = {'mm': K['mm'] - int(s15.mm), 'tickets': K['tickets'] - int(s15.tickets), 'tx': K['tx'] - int(s15.tx)}
bound('R17', '27', 'sum of the 15 printed types <= Known cohort (mm, tickets, tx, machines<=6,951)',
      all(v >= 0 for v in rest.values()) and int(s15.machines) <= COVER['transacting_machines'],
      'Known cohort', f"15-type sums mm={int(s15.mm):,} tickets={int(s15.tickets):,} tx={int(s15.tx):,} machines={int(s15.machines):,}")
info('R18', '27', 'unprinted types (Unknown + small types): mm / tickets / tx / rate',
     f"{rest['mm']:,} / {rest['tickets']} / {rest['tx']:,} / {100*rest['tickets']/rest['mm']:.2f} per 100",
     note=f"printed rows cover {100*int(s15.mm)/K['mm']:.1f}% of mm and {100*int(s15.tickets)/K['tickets']:.1f}% of tickets")
# Faults in the Known cohort reconstructed from the monthly rates (+-0.005/1000 rounding per month).
f_mid = float((MONTHLY.fault1000 * MONTHLY.tx / 1000).sum())
f_err = float((0.005 * MONTHLY.tx / 1000).sum())
info('R19', '29', 'Known-cohort fault transactions implied by the monthly table',
     f'{f_mid:,.0f} +- {f_err:,.0f}', note=f'overall {1000*f_mid/K["tx"]:.3f} per 1,000 vs cell-23 all-data {1000*FAULTS/TOTAL:.3f}')
bound('R20', '27/29', 'faults of the 15 printed types <= implied cohort faults', int(s15.faults) <= f_mid + f_err,
      f'{f_mid-f_err:,.0f}..{f_mid+f_err:,.0f}', f'{int(s15.faults):,}',
      note=f'unprinted types carry {f_mid-f_err-int(s15.faults):,.0f}..{f_mid+f_err-int(s15.faults):,.0f} faults over '
           f"{rest['tx']:,} tx")
out_tx = TOTAL - K['tx']
bound('R21', '23/29', 'faults outside the Known cohort Aug25-Jul26 are plausible (0 <= faults <= tx)',
      0 <= FAULTS - (f_mid + f_err) and FAULTS - (f_mid - f_err) <= out_tx, f'{out_tx:,} tx',
      f'{FAULTS-f_mid-f_err:,.0f}..{FAULTS-f_mid+f_err:,.0f} faults = '
      f'{1000*(FAULTS-f_mid)/out_tx:.2f} per 1,000 (Aug 2026 + host-excluded)')
zero_fault = RATES_15[RATES_15.fault1000 <= 0.12]
info('R22', '27', 'types with <=0.12 narrow-fault codes per 1,000 transactions (code support differs by type)',
     f"{list(zero_fault.machine_type)}: {int(zero_fault.tickets.sum())} tickets "
     f"({100*zero_fault.tickets.sum()/K['tickets']:.1f}% of cohort), {int(zero_fault.mm.sum()):,} mm",
     note='for these types a narrow-fault label is almost never observable -> classifier label prior depends on type')
sd = RATES_15.set_index('machine_type').loc['sd-49']
info('R23', '27', 'sd-49 share of cohort narrow faults vs share of transactions',
     f"{100*sd.faults/f_mid:.1f}% of faults from {100*sd.tx/K['tx']:.2f}% of transactions")

# =============================================================================================
# 8. Cell 29: monthly series.
# =============================================================================================
eq('T01', '29', 'sum of monthly active machine-months = Known cohort', K['mm'], int(MONTHLY.mm.sum()))
eq('T02', '29', 'sum of monthly tickets = Known cohort', K['tickets'], int(MONTHLY.tickets.sum()))
eq('T03', '29', 'sum of monthly transactions = Known cohort', K['tx'], int(MONTHLY.tx.sum()))
ok_rows = all(abs(round(100 * r.tickets / r.mm, 2) - r.rate100) < .005 + 1e-9 for r in MONTHLY.itertuples())
rec('T04', '29', 'every monthly tickets_per_100 = 100*tickets/mm (rounded)', 'row arithmetic', '12 rows', '', 'PASS' if ok_rows else 'FAIL')
rounds_to('T05', '29', 'printed min monthly rate', 5.95, (100 * MONTHLY.tickets / MONTHLY.mm).min())
rounds_to('T06', '29', 'printed max monthly rate', 8.31, (100 * MONTHLY.tickets / MONTHLY.mm).max())
eq('T07', '29', 'case_monthly all_tickets sum = 7,471', QUALITY['cases'], int(CASE_MONTHLY.all_tickets.sum()))
eq('T08', '29', 'case_monthly unplanned sum = cell-15 unplanned population', UNPLANNED_N, int(CASE_MONTHLY.unplanned.sum()))
rebuilt_month = cb.groupby('month').agg(all=('case_id', 'size'),
                                        unpl=('service_group', lambda s: (~s.isin(['Planned work', 'Cancelled request', 'Duplicate case'])).sum()))
eq('T09', '29', 'case_monthly reproduced from workbook (13 months, both columns)', True,
   bool((rebuilt_month['all'].values == CASE_MONTHLY.all_tickets.values).all() and
        (rebuilt_month['unpl'].values == CASE_MONTHLY.unplanned.values).all()))
bound('T10', '29', 'cohort tickets <= unplanned tickets in every month',
      bool((MONTHLY.tickets.values <= CASE_MONTHLY.unplanned.values[:12]).all()), '', '')
share = MONTHLY.tickets.values / CASE_MONTHLY.unplanned.values[:12]
p_pool = MONTHLY.tickets.sum() / CASE_MONTHLY.unplanned.values[:12].sum()
z = (MONTHLY.tickets.values - p_pool * CASE_MONTHLY.unplanned.values[:12]) / np.sqrt(
    CASE_MONTHLY.unplanned.values[:12] * p_pool * (1 - p_pool))
info('T11', '29', 'share of unplanned tickets that reach the comparison cohort, by month',
     json.dumps({m: round(100 * s, 1) for m, s in zip(MONTHLY.month, share)}),
     note=f'pooled {100*p_pool:.1f}%; Aug 2025 z={z[0]:.1f} (others {z[1:].min():.1f}..{z[1:].max():.1f}); '
          'the first month loses an unusual share of tickets - cause (no match / silent month) not printed')
for h in (4, 6, 12):
    t_open = pd.to_datetime(win.opened_at)
    moved = int(((t_open + pd.Timedelta(hours=h)).dt.strftime('%Y-%m') != win.month).sum() +
                ((t_open - pd.Timedelta(hours=h)).dt.strftime('%Y-%m') != win.month).sum())
    info(f'T12.{h}', '27/29', f'unplanned Aug25-Jul26 tickets whose month changes under a +/-{h}h case-vs-telemetry clock shift',
         f'{moved} ({100*moved/len(win):.2f}%)', note='upper bound on tickets that could be mis-joined to the wrong machine-month')
    if h == 6:
        info('T13', '27', "share of the 479 'no transactions in ticket month' tickets a +/-6h clock mismatch could explain",
             f'<= {moved} ({100*moved/EXCL["No transactions in ticket month"]:.1f}%)',
             note='under the plausible offsets (C03) the silent-month exclusion is not a clock artifact; under +/-12h it could be up to 193')

# =============================================================================================
# 8b. Case clock evidence (needed to judge the pilot's offset scenarios). Hospital state is parsed
#     in memory from 'Hospital City, State, Zip'; only zone-level aggregates are written.
# =============================================================================================
ZONE = {}
for _s in 'NY GA NJ NC MA PA ON OH VA FL CT MD SC IN WV MI DC DE ME QC NH KY VT RI'.split():
    ZONE[_s] = 'Eastern'
for _s in 'TX IL WI LA MO IA NE MN ND MS AL AR OK KS TN SD MB'.split():
    ZONE[_s] = 'Central'
for _s in 'NM CO UT MT ID WY AB'.split():
    ZONE[_s] = 'Mountain'
for _s in 'CA OR WA NV BC'.split():
    ZONE[_s] = 'Pacific'
ZONE.update({'AZ': 'Arizona', 'HI': 'Hawaii'})
_loc = raw['Hospital City, State, Zip'].map(common.clean).fillna('')
_state = _loc.str.extract(r',\s*([A-Z]{2})\b(?!.*,\s*[A-Z]{2}\b)')[0]
zone = pd.Series(_state.map(ZONE).values, index=cases.case_id.values)
_t = pd.to_datetime(cases.opened_at.values)
hour = pd.Series(_t.hour + _t.minute / 60, index=cases.case_id.values)
med = hour.groupby(zone).agg(['size', 'median', lambda x: int((x < 7).sum())])
info('C01', '4/34', 'median case-clock opening hour by hospital time zone (n, median, opened before 07:00)',
     json.dumps({z: [int(r['size']), round(float(r['median']), 2), int(r['<lambda_0>'])] for z, r in med.iterrows()}),
     note=f'{int(zone.notna().sum())}/{len(zone)} tickets mapped (split-zone states assigned to majority zone). '
          'Medians rise westward (Eastern 10.9 -> Pacific 13.0): the case clock is ONE fixed zone (service desk / '
          'exporter), not hospital-local time')
eq('C02', '4/34', 'case opening timestamps with non-zero seconds (case clock has minute precision)', 0,
   int((cases.opened_at.str[17:19] != '00').sum()))
dst = {}
for d in ('2025-11-02', '2026-03-08'):
    d0 = pd.Timestamp(d)
    before = hour[(_t >= d0 - pd.Timedelta(days=21)) & (_t < d0)]
    after = hour[(_t >= d0) & (_t < d0 + pd.Timedelta(days=21))]
    dst[d] = round(float(after.quantile(.05) - before.quantile(.05)), 2)
info('C03', '4/34', 'shift of the 5th-percentile opening hour across DST changes (3 weeks either side), hours', json.dumps(dst),
     note='a UTC case clock would shift by about +1h in Nov and -1h in Mar; observed shifts are small, so the case '
          'clock observes DST (a US civil zone). If telemetry is true UTC, delta = +4..+6h; if it is hospital-local, '
          'delta = 0 to -3h (-6h Hawaii) relative to an Eastern case clock')
pz = zone.reindex(PILOT0.case_id).fillna('Unmapped')
info('C04', '8/34', 'hospital time zones of the 26 pilot tickets with events / all 30',
     f"{json.dumps(pz[(PILOT0.all_events > 0).values].value_counts().to_dict())} / {json.dumps(pz.value_counts().to_dict())}")

# =============================================================================================
# 9. Cells 8 / 34: pilot.
# =============================================================================================
pil = cases.set_index('case_id').loc[PILOT0.case_id, ['opened_at', 'machine_id']]
eq('P01', '8', 'all 30 printed pilot case_ids exist in the rebuilt case table', 30, int(pil.opened_at.notna().sum()))
o = pd.to_datetime(pil.opened_at)
bound('P02', '8', "pilot anchors lie inside the eligibility window '2025-09-02'..'2026-07-31 23:59:59'",
      bool(((pil.opened_at >= '2025-09-02') & (pil.opened_at <= '2026-07-31 23:59:59')).all()),
      '', f'{pil.opened_at.min()}..{pil.opened_at.max()}')
first_needed = (dt.datetime(2025, 9, 2) - dt.timedelta(days=32)).strftime('%Y-%m-%d')
last_needed = (dt.datetime(2026, 7, 31, 23, 59) + dt.timedelta(days=2)).strftime('%Y-%m-%d')
bound('P03', '8', 'eligibility window keeps the whole extraction range inside telemetry coverage',
      first_needed >= COVER['first'] and last_needed <= COVER['last'], f"{COVER['first']}..{COVER['last']}",
      f'{first_needed}..{last_needed}', 'earliest eligible date minus 32 days equals the first telemetry date exactly')
# Buffer: events with utc in [a-30d, a) for a = anchor + offset must have local date inside
# [date(anchor-32d), date(anchor+2d)], for any constant local-minus-utc shift s.
slack_lo, slack_hi = [], []
for anchor in o:
    lo_d = pd.Timestamp((anchor - pd.Timedelta(days=32)).date())
    hi_d = pd.Timestamp((anchor + pd.Timedelta(days=2)).date()) + pd.Timedelta(days=1)
    for off in (-12, 0, 12):
        a = anchor + pd.Timedelta(hours=off)
        for s in range(-14, 15):
            slack_lo.append(((a - pd.Timedelta(days=30) + pd.Timedelta(hours=s)) - lo_d).total_seconds() / 3600)
            slack_hi.append((hi_d - (a + pd.Timedelta(hours=s))).total_seconds() / 3600)
bound('P04', '8', 'extraction buffer covers every window for any local-vs-UTC shift in [-14h, +14h]',
      min(slack_lo) >= 0 and min(slack_hi) > 0, '', f'min slack {min(slack_lo):.1f}h (start) / {min(slack_hi):.1f}h (end)')
# Window bounds: Python (cell 8) vs SQLite (cell 34) for the 90 real windows.
s = sqlite3.connect(':memory:')
mism = 0
for anchor_s in pil.opened_at:
    for off in (-12, 0, 12):
        a = dt.datetime.fromisoformat(anchor_s) + dt.timedelta(hours=off)
        py = ((a - dt.timedelta(days=30)).isoformat(' '), a.isoformat(' '))
        sq = s.execute("SELECT datetime(datetime(?,printf('%+d hours',?)),'-30 days'), datetime(?,printf('%+d hours',?))",
                       (anchor_s, off, anchor_s, off)).fetchone()
        mism += py != sq
eq('P05', '8/34', 'Python window bounds == SQLite window bounds for all 90 windows', 0, mism,
   'this equality is ALL that cell-37 check 9 can establish')
eq('P06', '34', 'tickets with all_events>0 at offset 0 = summary', PILOT_SUMMARY[0][1], int((PILOT0.all_events > 0).sum()))
eq('P07', '34', 'tickets with non_success>0 at offset 0 = summary', PILOT_SUMMARY[0][2], int((PILOT0.non_success > 0).sum()))
bound('P08', '34', 'per-ticket: distinct<=non_success<=all_events; distinct<=48; labels consistent',
      bool(((PILOT0.distinct <= PILOT0.non_success) & (PILOT0.non_success <= PILOT0.all_events) & (PILOT0.distinct <= 48)).all()),
      '', '30 rows')
ns0 = int(PILOT0.non_success.sum())
bound('P09', '9/34', 'offset-0 window non-success events <= pilot_events extracted', ns0 <= SIZES['pilot_events'],
      SIZES['pilot_events'], ns0, f'ratio {ns0/SIZES["pilot_events"]:.4f} vs 30/35 days = {30/35:.4f} '
      '(extraction spans 35 calendar dates); consistent with date_local and utc being one clock')
for cid, g in LAST_CODES.groupby('case_id'):
    p = PILOT0.set_index('case_id').loc[cid]
    eq(f'P10.{cid}', '34', f'{cid}: occurrences over its 5 listed codes = window non_success (distinct=5)',
       int(p.non_success), int(g.occurrences.sum()))
eq('P11', '34/4', 'printed bucket of each listed code = cell-4 lookup', 15,
   int(sum(LOOKUP.get(r.code) == r.bucket for r in LAST_CODES.itertuples())))
bound('P12', '34', 'listed last_seen strictly descending within ticket and ranks 1..5',
      all(g.last_seen.is_monotonic_decreasing and list(g['rank']) == [1, 2, 3, 4, 5] for _, g in LAST_CODES.groupby('case_id')), '', '')
gaps = {}
for cid, g in LAST_CODES.groupby('case_id'):
    op = pd.Timestamp(pil.loc[cid, 'opened_at'])
    top = pd.Timestamp(g.last_seen.iloc[0])
    oldest = pd.Timestamp(g.last_seen.iloc[-1])
    assert op - pd.Timedelta(days=30) <= oldest and top < op
    gaps[cid] = round((op - top).total_seconds() / 3600, 2)
flag('P13', '34', 'hours between the most recent non-success code and case opening (offset 0)', json.dumps(gaps),
     note='rank-1/last-three codes are only computed at offset 0, which is right only if telemetry is '
          'hospital-local AND the case clock is the hospital zone (23/26 pilot tickets are Eastern, C04). If the '
          'telemetry clock is true UTC the anchor should be +4..+6h (C03): for T00783 (gap 2.3h) every event logged '
          'in the 4-6h before the real opening is missing from its last-codes list; for a hospital >=3h west of the '
          'case clock its rank-1 code would be logged after opening. The +/-12h scenarios test only counts>0')
forced = int(((PILOT0.non_success >= 3) & (PILOT0.distinct <= 2)).sum())
eq('P14', '34', 'tickets with >=3 non-success events at offset 0', LAST3['tickets_ge3'], int((PILOT0.non_success >= 3).sum()))
bound('P15', '34', "'25 of 26 repeated' >= tickets forced to repeat (window has <=2 distinct codes)",
      LAST3['repeated'] >= forced, LAST3['repeated'], forced)
p_silent = silent_all / dev_matched
tail = sum(math.comb(30, k) * p_silent ** k * (1 - p_silent) ** (30 - k) for k in range(4, 31))
info('P16', '34/27', '4/30 pilot tickets have no transactions in any window vs silent-month share in cell 27',
     f'4/30 = 13.3% vs {100*p_silent:.1f}%', note=f'P(>=4 of 30) = {tail:.2f}; not an anomaly')
info('P17', '34', 'minimum per-ticket all_events among tickets with any events (offset 0)',
     int(PILOT0.loc[PILOT0.all_events > 0, 'all_events'].min()),
     note='a 12h shift keeps 29.5 of 30 days, so "26/26 in all scenarios" is near-certain by construction '
          '(the scenario test has almost no power). Only per-scenario totals are printed, so it is not shown that '
          'the same 26 tickets qualify in each scenario')

# =============================================================================================
# 10. Synthetic tests of Zac's verbatim SQL (cells 6, 27, 34, 37).
# =============================================================================================
rng = np.random.default_rng(20261012)
n = 5000
ts = pd.Timestamp('2025-08-01') + pd.to_timedelta(rng.integers(0, 365 * 24 * 3600, n), unit='s')
ev = pd.DataFrame({'external_device_id': rng.choice(['D1', 'D2', 'D3', 'D4'], n),
                   'transaction_time_utc': ts.strftime('%Y-%m-%d %H:%M:%S'),
                   'transaction_code': rng.choice(['00', '00', '00', '03', '11', '05', '43'], n)})
ev['transaction_time_local'] = ev.transaction_time_utc
ev['transaction_date_local'] = ev.transaction_time_utc.str[:10]


def run_agg(sql):
    x = sqlite3.connect(':memory:')
    ev.to_sql('transaction_events', x, index=False)
    tmc = pd.read_sql_query(sql, x)
    tot = pd.read_sql_query(TOTALS_SQL, x)
    agg = tmc.groupby('transaction_code').n.sum().sort_index()
    src = tot.set_index('transaction_code').n.sort_index()
    return tmc, (int(tot.n.sum()) == int(tmc.n.sum()), agg.equals(src), int(agg.sum()) == int(tmc.n.sum()),
                 int(tmc.missing_time.sum()) == 0)


good, gchk = run_agg(AGG_SQL)
broken_sql = AGG_SQL.replace("substr(transaction_date_local,1,7)", "substr(date(transaction_date_local,'+20 days'),1,7)")
broken, bchk = run_agg(broken_sql)
wrong_months = int(((pd.to_datetime(ev.transaction_date_local) + pd.Timedelta(days=20)).dt.strftime('%Y-%m')
                    != ev.transaction_date_local.str[:7]).sum())
flag('S01', '6/37', "synthetic: month shifted by +20 days; cell-6 assert and cell-37 checks 5, 6, 7",
     f'correct SQL passes={gchk}; broken SQL passes={bchk}; events moved to a wrong month={wrong_months:,}/{n:,}',
     note='all four still pass: they compare COUNT(*) of one table with itself and detect only lost or duplicated '
          'rows, never a wrong month, machine or clock', kind='synthetic')
# Exclusion CASE precedence and cohort rows (cell 27) on toy data.
x = sqlite3.connect(':memory:')
pd.DataFrame({'machine_id': ['M1', 'M2', 'M3'], 'machine_type': ['a', 'a', 'a'],
              'host': ['Host 001', 'Host 002', None], 'shared_internal_host': [0, 1, 0]}).to_sql('devices', x, index=False)
pd.DataFrame({'machine_id': ['M1', 'M2', 'M3'], 'month': ['2026-01'] * 3, 'transaction_code': ['00'] * 3,
              'n': [100, 100, 100]}).to_sql('telemetry_month_code', x, index=False)
pd.DataFrame({'transaction_code': ['00'], 'bucket': ['Success'], 'provisional_fault': [0]}).to_sql('codes', x, index=False)
pd.DataFrame({'machine_id': ['M1', 'M1', 'M2', 'M2', 'M3', 'M3', 'M9'],
              'month': ['2026-01', '2026-02', '2026-01', '2026-02', '2026-01', '2026-02', '2026-01'],
              'service_group': ['Other recorded issue'] * 7}).to_sql('service_cases', x, index=False)
x.executescript(RATE_VIEWS)
tc = x.execute(COHORT_SQL).fetchall()
te = dict(x.execute(EXCL_SQL).fetchall())
flag('S02', '27', 'synthetic: 2 tickets per device (active Jan + silent Feb) on known, shared and missing hosts',
     f'cohorts={[(r[0][:13], r[2]) for r in tc]}; exclusions={te}',
     note="All-minus-Known = 2 tickets (the active-month ones) while 4 tickets are host-excluded; the 2 silent-month "
          "host tickets never reach 'No transactions'. Real data: 17 vs 66 -> 49 hidden silent-month tickets",
     kind='synthetic')
# Cell-37 check 9: shared inputs -> a wrong clock assumption still reconciles.
pe = sqlite3.connect(':memory:')
ev1 = ev[ev.external_device_id == 'D1'].copy()
anchors = ['2025-10-15 10:00:00', '2026-03-08 09:30:00']
pd.DataFrame({'case_id': ['T1', 'T2']}).to_sql('pilot_selection', pe, index=False)
pd.DataFrame({'case_id': ['T1', 'T2'], 'opened_at': anchors}).to_sql('cases', pe, index=False)
rows_e, rows_w = [], []
for cid, an in zip(['T1', 'T2'], anchors):
    for off in (-12, 0, 12):
        a = dt.datetime.fromisoformat(an) + dt.timedelta(hours=off)
        low = a - dt.timedelta(days=30)
        w = [(tt, k) for tt, k in zip(ev1.transaction_time_utc, ev1.transaction_code) if low.isoformat(' ') <= tt < a.isoformat(' ')]
        rows_w.append((cid, off, len(w), sum(k != '00' for _, k in w)))
    rows_e += [(cid, tt, k) for tt, k in zip(ev1.transaction_time_utc, ev1.transaction_code) if k != '00']
pd.DataFrame(rows_e, columns=['case_id', 'transaction_time_utc', 'transaction_code']).to_sql('pilot_events', pe, index=False)
pd.DataFrame(rows_w, columns=['case_id', 'offset_hours', 'all_events', 'non_success_events']).to_sql('pilot_window_counts', pe, index=False)
res = pd.read_sql_query(PILOT_SQL, pe).merge(pd.DataFrame(rows_w, columns=['case_id', 'offset_hours', 'all_events', 'non_success_events']),
                                             on=['case_id', 'offset_hours'], suffixes=('_sql', '_raw'))
flag('S03', '34/37', 'synthetic: cell-37 check 9 with telemetry deliberately on a different clock',
     f"reconciles={bool(res.eval('non_success_events_sql == non_success_events_raw').all())} for 6 windows",
     note='both sides read the same events with the same anchors, so the check passes whatever the true clock offset; '
          'it validates string-vs-datetime arithmetic only', kind='synthetic')
# Cell-37 check 4: alternative service-group definitions still 'reconcile'.
alt = conn.execute("""SELECT COUNT(*), SUM(CASE WHEN trouble_code IN ('Preventative Maintenance','Installation') THEN 1 ELSE 0 END)
                      FROM cases""").fetchone()
flag('S04', '15/37', "cell-37 check 4 with the Install-Case clause removed from the CASE",
     f'groups still sum to {alt[0]:,}; Planned work would be {alt[1]} instead of 23',
     note='any CASE with an ELSE partitions all rows, so the check cannot fail', kind='synthetic')

# =============================================================================================
# 11. Cell 37 check classification (static).
# =============================================================================================
CLASS = [
    (1, 'Distinct case identifiers', 'meaningful', 'casemap is a dict: duplicate Case Numbers would collide'),
    (2, 'Distinct device identifiers', 'redundant', 'already asserted in cell 4 (external_device_id.is_unique) and the map is injective'),
    (3, 'No lost or multiplied case rows', 'tautological given 2', 'LEFT JOIN on a unique key cannot multiply or drop rows'),
    (4, 'Service groups reconcile', 'tautological', 'CASE ... ELSE partitions every row (S04)'),
    (5, 'Every telemetry code reconciles to independent raw SQL', 'weak', 'same table counted twice; detects only lost/duplicated rows (S01)'),
    (6, 'All source transactions represented', 'tautological', "manifest['telemetry_rows'] is SUM(n) of the same table"),
    (7, 'No missing transaction dates in aggregate', 'meaningful', 'real data property (NULL utc/date_local)'),
    (8, 'Every aggregate machine is in dictionary', 'meaningful', 'real data property'),
    (9, 'All provisional-window counts reconcile', 'weak', 'same events, same anchors; cannot detect a wrong clock (S03, P05)'),
    (10, 'Rate numerator reconciles to direct eligible-case join', 'weak', 'two joins over the same keys and month definition; detects duplicate keys only'),
    (11, 'Workload totals reconcile', 'tautological', 'GROUP BY totals always equal COUNT(*)'),
    (12, 'Independent repeat-contact calculation', 'meaningful', 'separate pandas re-implementation of the filter and LEAD'),
    (13, 'Independent missing-subcategory count', 'tautological', 'same column counted twice'),
    (14, 'Original database preserved during extraction', 'near-tautological', 'source opened with mode=ro + query_only; size/mtime only'),
]
eq('V01', '37', 'number of checks printed', CELL37_CHECKS, len(CLASS))
for k, name, cls, why in CLASS:
    assert f"check('{name}'" in NB_SRC, name
    rec(f'V{k+1:02d}', '37', f'check {k}: {name}', 'check-classification', 'Pass', cls,
        'FLAG' if cls in ('tautological', 'tautological given 2', 'weak', 'redundant', 'near-tautological') else 'INFO', why)
missing = ['bucket coverage / Malformed listing', 'exclusion reasons sum to the unplanned Aug-Jul total (R04)',
           'per-type rows sum to the cohort', 'transaction_date_local vs time_utc date agreement (A02)',
           'shared-host URL normalisation / empty-string hosts (M06)', 'pilot window covers the clock-offset range (P04)']
flag('V16', '37', 'identities NOT checked in cell 37 that would test logic rather than arithmetic', '; '.join(missing))

# =============================================================================================
out = pd.DataFrame(ROWS)
out.to_csv(OUT / 'audit_tel_identities.csv', index=False)
counts = out.status.value_counts().to_dict()
print('\nsummary', counts)
assert counts.get('FAIL', 0) == 0, out[out.status == 'FAIL']
