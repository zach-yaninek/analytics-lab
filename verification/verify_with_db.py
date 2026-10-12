#!/usr/bin/env python3
"""DB-backed verification of Zac's telemetry results and of the telemetry timestamp semantics.

Run it once the 17 GB telemetry database is available, either here or in Zac's Colab.

Local:
  cd /home/user/analytics-lab
  python3 -I verification/verify_with_db.py --db data/raw/ipa_transaction_events_202508_202608.db \
      --xlsx "data/raw/IPA_CaseHistory_Aug 2025-Aug2026.xlsx" \
      --out verification/outputs/db --private data/private/db [--skip-scans] [--sha256]
Colab (after cell 2 of Zac's notebook has produced SRC and XLS):
  # upload verification/common.py and verification/verify_with_db.py to /content/verification/
  import sys; sys.path.insert(0, '/content/verification')
  import verify_with_db as v
  summary = v.run(SRC, XLS, 'db_out', 'db_private')

What it does (each step is isolated; one failure does not stop the others; outputs are written as soon as each
step finishes and db_summary.json/md is rewritten after every step):
  0  schema, indexes, column resolution, value formats, row counts, optional SHA-256 vs Zac's checksum
  1  device dictionary (rows, uniqueness after clean(), machine types, statuses, hosts, shared internal host)
  2  ticket-to-device linkage and a pseudonymous profile of unmatched tickets
  3  case-model -> machine-type map, Zac's mapping_summary, variants, and a host-level ownership audit
  4  ONE pass over transaction_events reproducing Zac's telemetry_month_code; reconciliation; Zac's machine-type
     rates, monthly comparison, cohort tables and (4b) the 30-ticket pilot, compared with his printed values
  5  clock test A: hour-of-day profiles by hospital time-zone group x DST period, scored against clock hypotheses
  6  clock test B: hourly counts around the 2025-11-02 and 2026-03-08 DST transitions
  7  rows whose local and UTC strings differ (Zac: 155) and, if present, ingestion-minus-transaction offsets
  8  summary (expected vs actual, decisions)

Efficiency: steps 4-7 share ONE read of transaction_events. The table is read in rowid chunks
(NOT INDEXED + rowid BETWEEN). Every scan query runs on a chunk while its pages are cached, and the
per-chunk partial aggregates are merged exactly. Memory stays bounded: a single 118M-row GROUP BY with
temp_store=MEMORY would need a ~10 GB sorter. Without a rowid (or with --no-chunk), each query is a separate
full scan.

Privacy: --out receives only pseudonymous/aggregate files (M##### machines, Customer NNN, Host NNN, T##### cases,
generic labels). Real account names, serials and clearView URLs go only to --private.
The database is opened read-only (mode=ro, PRAGMA query_only=ON) and is never written.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
from collections import Counter  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common  # noqa: E402
from common import clean  # noqa: E402

# ==============================================================================================================
# Configuration: adapt here if the real schema differs. None = auto-detect from CANDIDATES.
# ==============================================================================================================
CONFIG = {
    'events_table': 'transaction_events',
    'devices_table': 'devices',
    'codes_table': 'transaction_codes',
    'events': {'device': 'external_device_id', 'date_local': 'transaction_date_local',
               'time_local': 'transaction_time_local', 'time_utc': 'transaction_time_utc',
               'code': 'transaction_code', 'ingest': None},
    'devices': {'device': 'external_device_id', 'status': 'device_status', 'type': 'machine_type',
                'url': 'clearview_url'},
    'codes': {'code': 'transaction_code', 'description': 'transaction_description'},
    'chunk_rows': 2_000_000,      # rowids per chunk (~300 MB of pages at ~145 bytes/row)
    'cache_mb': 1024,             # SQLite page cache
    'threads': 4,                 # SQLite sorter worker threads
    'sample_modulus': 1000,       # ingestion sample: rowid % N == 0
    'min_zone_rows': 5000,        # minimum transactions per zone x period profile to score it
    'min_transition_ref': 1.0,    # minimum adjacent-day mean count to classify a DST-transition day
    'ingest_clock_is_utc': None,  # None = infer from the column name / 'Z' or '+00:00' suffixes
    'shift_tolerance_h': 0.5,     # |observed - predicted| shift tolerance in hours
    'dst_years': (2024, 2027),    # years for the US/Canada DST CASE expression
    'data_window': ('2025-08-01', '2026-08-31'),
}
CANDIDATES = {
    'device': [r'external_device_id', r'device_?id', r'serial', r'machine_?id'],
    'date_local': [r'transaction_date_local', r'date_local', r'local_date', r'transaction_date$', r'^date$'],
    'time_local': [r'transaction_time_local', r'time_local', r'local_time', r'datetime_local', r'transaction_time$'],
    'time_utc': [r'transaction_time_utc', r'time_utc', r'utc_time', r'datetime_utc'],
    'code': [r'transaction_code', r'^code$', r'error_code', r'event_code', r'status_code'],
    'ingest': [r'ingest', r'receiv', r'insert', r'creat', r'load', r'upload', r'arriv', r'server', r'etl',
               r'process', r'logged', r'record', r'updat', r'modif', r'import', r'sync'],
    'status': [r'device_status', r'status'],
    'type': [r'machine_type', r'type', r'model'],
    'url': [r'clearview', r'url', r'host'],
    'description': [r'desc', r'name', r'text', r'label'],
}

# ==============================================================================================================
# Zac's printed values (notebook cells 9-37). Used as expected values unless --expected-json is given.
# ==============================================================================================================
_RATE_COLS = ['machine_type', 'machines', 'active_machine_months', 'tickets', 'transactions', 'fault_transactions',
              'tickets_per_100_active_months', 'fault_codes_per_1000_transactions']
_RATES = """sbsx-51 31 319 66 907989 5055 20.69 5.57
sd-49 53 584 53 440144 43905 9.08 99.75
scrubex-7 116 1352 111 2660481 0 8.21 0.00
scrubex2.0-2 1172 12329 999 24268373 318802 8.10 13.14
scrubex2.0-3 1072 11141 894 17881352 2164 8.02 0.12
alex2.0-3 470 5011 397 6018886 32699 7.92 5.43
alex2.0-1 329 3571 266 4404065 10731 7.45 2.44
scrubex2.0-4 913 9442 684 13908698 68082 7.24 4.89
scrubex-2 520 5873 397 12252356 171892 6.76 14.03
mlc-1 444 5087 334 4475320 93836 6.57 20.97
scrubex-1 112 1246 79 2154700 26265 6.34 12.19
scrubex2.0-5 153 1606 89 1393972 6631 5.54 4.76
scrubex-4 366 4143 204 6230453 32354 4.92 5.19
scrubex-3 494 5484 246 9721466 17 4.49 0.00
scrubex-5 82 938 37 783740 5766 3.94 7.36"""
_MONTH_COLS = ['month', 'active_machine_months', 'tickets', 'transactions', 'tickets_per_100_active_months',
               'fault_codes_per_1000_transactions']
_MONTHLY = """2025-08 5420 360 8704739 6.64 6.82
2025-09 5605 414 9040975 7.39 7.10
2025-10 5677 472 9512486 8.31 7.52
2025-11 5675 353 8319121 6.22 8.03
2025-12 5718 436 8852073 7.63 8.13
2026-01 5739 449 8987779 7.82 8.08
2026-02 5763 379 8480682 6.58 8.15
2026-03 5903 440 9480766 7.45 7.78
2026-04 5968 408 9348766 6.84 7.69
2026-05 5952 354 9097448 5.95 7.18
2026-06 5903 442 9378351 7.49 6.95
2026-07 5832 409 9741417 7.01 7.23"""
_MODEL_MAP = """A-LC|Unknown|10|5
A-LC|alc-1|2|2
LC-24|mlc-1|27|16
LC-30|mlc-1|255|132
LC-30|Unknown|1|1
LVD-Remote|scrubex-2|465|241
LVD-Remote|scrubex-1|23|16
LVD-Remote|Unknown|4|3
LVD-Remote-2.0|scrubex2.0-2|1227|608
LVD-Remote-2.0|Unknown|13|6
LVD-Remote-2.0|scrubex2.0-3|3|1
LVD-Remote-2.0|sd2.0-49|1|1
LVLR-WOP|scrubex-1|4|2
LVRR-WOP|scrubex-3|14|6
LVRR-WP|scrubex-3|293|156"""
_PILOT0 = """T00705 93 5 1452|T00783 82 5 1742|T00951 82 5 1659|T00957 867 8 7687|T01157 45 4 726|T01287 672 7 2740
T01629 0 0 0|T01795 6 2 208|T01796 28 4 175|T01797 34 5 262|T02128 465 9 1969|T02229 152 4 1572|T02268 74 5 1458
T03075 118 5 1079|T03079 8 2 2037|T03326 246 7 3954|T03959 0 0 0|T04699 303 4 1373|T04907 29 2 62|T05185 17 3 712
T05506 0 0 0|T05683 0 0 0|T05924 145 3 544|T06107 83 5 2556|T06354 89 3 113|T06445 3 2 912|T06663 71 5 881
T06672 318 3 1580|T06712 3 1 627|T06912 27 4 1038"""
_LAST_CODES = """T00705|43|2025-09-07 16:03:14|34|1
T00705|11|2025-09-05 16:09:03|17|2
T00705|03|2025-09-04 15:16:19|39|3
T00705|34|2025-09-03 23:49:29|1|4
T00705|25|2025-09-03 18:40:22|2|5
T00783|03|2025-09-10 13:18:50|62|1
T00783|77|2025-09-09 12:29:51|2|2
T00783|32|2025-09-09 10:28:53|8|3
T00783|17|2025-09-09 10:28:39|9|4
T00783|11|2025-09-02 10:12:00|1|5
T00951|19|2025-09-18 23:24:49|37|1
T00951|20|2025-09-18 20:59:32|14|2
T00951|01|2025-09-18 12:09:58|11|3
T00951|04|2025-09-18 12:04:00|16|4
T00951|79|2025-09-10 14:39:34|4|5"""


def _num(x):
    return float(x) if '.' in x else int(x)


ZAC_EXPECTED = {
    'devices_rows': 7183, 'devices_unique': True, 'codes_rows': 49,
    'record_quality': {'cases': 7471, 'distinct_cases': 7471, 'customers': 845, 'case_machines': 3773, 'models': 31,
                       'first_opened': '2025-08-01 07:22:00', 'last_opened': '2026-08-31 17:45:00'},
    'linkage': {'cases': 7471, 'matched_cases': 6113, 'matched_machines': 3041, 'matched_pct': 81.82},
    'mapping_summary': {'Case models spanning more than one telemetry type': 16,
                        'Customers spanning more than one observed host': 31,
                        'Hosts linked to more than one case customer': 83},
    'model_type_mapping_head': [dict(zip(['model', 'machine_type', 'matched_cases', 'machines'],
                                         [r[0], r[1], int(r[2]), int(r[3])]))
                                for r in (line.split('|') for line in _MODEL_MAP.splitlines())],
    'telemetry_groups': 418188, 'telemetry_rows': 118047569, 'clocks_differ': 155, 'missing_time': 0,
    'null_local_date': 0,              # implied: missing_time = SUM(utc IS NULL OR date_local IS NULL) = 0
    'unmapped_telemetry_devices': 0,   # implied: his assert df.external_device_id.isin(serialmap).all()
    'coverage': {'first_transaction_date': '2025-08-01', 'last_transaction_date': '2026-08-28',
                 'represented_transactions': 118047569, 'transacting_machines': 6951},
    'bucket_totals': {'Success': 110166059, 'Stock-out': 3236592, 'Door issue': 2212968,
                      'Mechanical fault': 844284, 'User behavior': 796042, 'Incomplete transaction': 473188,
                      'Operational status': 268236, 'Electronics/software/comms': 45235, 'Undefined': 4959,
                      'Malformed': 6},
    'non_success': 7881510, 'non_success_pct': 6.68, 'narrow_faults': 889519, 'narrow_per_1000': 7.54,
    'narrow_per_1000_ex05': 7.43,
    'comparison_cohort': [
        {'cohort': 'All represented active machine-months', 'active_machine_months': 70057, 'tickets': 4933,
         'transactions': 109344700, 'zero_ticket_months': 65847},
        {'cohort': 'Known nonshared hosts', 'active_machine_months': 69155, 'tickets': 4916,
         'transactions': 108944603, 'zero_ticket_months': 64961}],
    'ticket_cohort_exclusions': {'Included in comparison': 4916, 'No device match': 1203,
                                 'No transactions in ticket month': 479, 'Missing host': 48,
                                 'Shared/internal host': 18},
    'machine_type_rates': [dict(zip(_RATE_COLS, [r[0]] + [_num(x) for x in r[1:]]))
                           for r in (line.split() for line in _RATES.splitlines())],
    'overall_rate': 7.11,
    'monthly_comparison': [dict(zip(_MONTH_COLS, [r[0]] + [_num(x) for x in r[1:]]))
                           for r in (line.split() for line in _MONTHLY.splitlines())],
    'pilot_events': 4736,
    'pilot_scenario_summary': [{'offset_hours': o, 'tickets': 30, 'tickets_with_transactions': 26,
                                'tickets_with_non_success': 26} for o in (-12, 0, 12)],
    'pilot_offset0': [dict(zip(['case_id', 'non_success_events', 'distinct_codes', 'all_events'],
                               [r[0]] + [int(x) for x in r[1:]]))
                      for r in (item.split() for item in _PILOT0.replace('\n', '|').split('|'))],
    'pilot_last_codes_head': [dict(zip(['case_id', 'transaction_code', 'last_seen', 'occurrences', 'recency_rank'],
                                       [r[0], r[1], r[2], int(r[3]), int(r[4])]))
                              for r in (line.split('|') for line in _LAST_CODES.splitlines())],
    'pilot_repeated_last3': {'tickets_with_3': 26, 'with_repeated_codes': 25},
}

# Zac's provisional code buckets (cell 4), verbatim.
GROUPS = {'Success': ['00'], 'User behavior': ['04', '07', '10', '19', '21', '50', '60', '61', '78'],
          'Stock-out': ['03', '22', '51', '77'],
          'Operational status': ['53', '55', '68', '69', '70', '71', '72', '73', '74', '75', '76', '82', '83'],
          'Mechanical fault': ['02', '11', '14', '16', '17', '18', '31', '32', '33', '34', '35', '66', '67'],
          'Electronics/software/comms': ['05', '06', '08', '09', '13', '23', '24', '25', '52', '54'],
          'Door issue': ['12', '15', '20', '26', '27', '30', '41', '42', '43', '44', '45', '46', '47', '48', '56',
                         '57', '58', '59', '62', '63', '65', '79', '80', '81'],
          'Incomplete transaction': ['01'],
          'Undefined': ['28', '29', '36', '37', '38', '39', '40', '49', '64'] + [str(n) for n in range(84, 100)]}
LOOKUP = {k: g for g, ks in GROUPS.items() for k in ks}

# Zac's SQL (cells 11, 23, 25, 27, 29), verbatim except for whitespace.
ZAC_SQL = {
    'record_quality': """SELECT COUNT(*) cases, COUNT(DISTINCT case_id) distinct_cases,
 COUNT(DISTINCT customer) customers, COUNT(DISTINCT machine_id) case_machines,
 COUNT(DISTINCT model) models, MIN(opened_at) first_opened, MAX(opened_at) last_opened FROM cases""",
    'linkage': """SELECT COUNT(*) cases, SUM(d.machine_id IS NOT NULL) matched_cases,
 COUNT(DISTINCT CASE WHEN d.machine_id IS NOT NULL THEN c.machine_id END) matched_machines,
 ROUND(100.0*SUM(d.machine_id IS NOT NULL)/COUNT(*),2) matched_pct
FROM cases c LEFT JOIN devices d USING(machine_id)""",
    'telemetry_date_coverage': """SELECT MIN(first_date) first_transaction_date,MAX(last_date) last_transaction_date,
 SUM(n) represented_transactions,COUNT(DISTINCT machine_id) transacting_machines FROM telemetry_month_code""",
    'telemetry_buckets': """SELECT k.bucket,SUM(t.n) transactions,
 100.0*SUM(t.n)/(SELECT SUM(n) FROM telemetry_month_code) all_transaction_pct
FROM telemetry_month_code t LEFT JOIN codes k USING(transaction_code)
GROUP BY k.bucket ORDER BY transactions DESC""",
    'code_totals': """SELECT t.transaction_code,k.transaction_description,k.bucket,SUM(t.n) transactions
FROM telemetry_month_code t LEFT JOIN codes k USING(transaction_code)
GROUP BY t.transaction_code,k.transaction_description,k.bucket ORDER BY transactions DESC""",
    'model_type_mapping': """SELECT c.model,d.machine_type,COUNT(*) matched_cases,COUNT(DISTINCT c.machine_id) machines
FROM cases c JOIN devices d USING(machine_id)
GROUP BY c.model,d.machine_type ORDER BY c.model,matched_cases DESC""",
    'customer_host_audit': """SELECT c.customer,COUNT(DISTINCT d.host) observed_hosts,
 COUNT(DISTINCT c.machine_id) matched_machines
FROM cases c JOIN devices d USING(machine_id) GROUP BY c.customer""",
    'mapping_summary': """SELECT 'Case models spanning more than one telemetry type' measure,COUNT(*) value FROM
 (SELECT c.model FROM cases c JOIN devices d USING(machine_id) GROUP BY c.model HAVING COUNT(DISTINCT d.machine_type)>1)
UNION ALL SELECT 'Customers spanning more than one observed host',COUNT(*) FROM
 (SELECT c.customer FROM cases c JOIN devices d USING(machine_id) GROUP BY c.customer HAVING COUNT(DISTINCT d.host)>1)
UNION ALL SELECT 'Hosts linked to more than one case customer',COUNT(*) FROM
 (SELECT d.host FROM cases c JOIN devices d USING(machine_id) WHERE d.host IS NOT NULL GROUP BY d.host
  HAVING COUNT(DISTINCT c.customer)>1)""",
    'views': """
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
LEFT JOIN ticket_counts c ON m.machine_id=c.machine_id AND m.month=c.month;""",
    'comparison_cohort': """SELECT 'All represented active machine-months' cohort,COUNT(*) active_machine_months,
 SUM(tickets) tickets,SUM(transactions) transactions, SUM(tickets=0) zero_ticket_months
FROM comparison_month
UNION ALL SELECT 'Known nonshared hosts',COUNT(*),SUM(tickets),SUM(transactions),SUM(tickets=0)
FROM comparison_month WHERE shared_internal_host=0 AND host IS NOT NULL""",
    'ticket_cohort_exclusions': """SELECT CASE WHEN d.machine_id IS NULL THEN 'No device match'
 WHEN d.shared_internal_host=1 THEN 'Shared/internal host'
 WHEN d.host IS NULL THEN 'Missing host'
 WHEN m.machine_id IS NULL THEN 'No transactions in ticket month'
 ELSE 'Included in comparison' END reason,COUNT(*) tickets
FROM service_cases c LEFT JOIN devices d USING(machine_id)
LEFT JOIN machine_month m ON c.machine_id=m.machine_id AND c.month=m.month
WHERE c.month>='2025-08' AND c.month<'2026-08'
GROUP BY reason ORDER BY tickets DESC""",
    'machine_type_rates': """SELECT machine_type,COUNT(DISTINCT machine_id) machines,COUNT(*) active_machine_months,
 SUM(tickets) tickets,SUM(transactions) transactions,SUM(fault_transactions) fault_transactions,
 100.0*SUM(tickets)/COUNT(*) tickets_per_100_active_months,
 1000.0*SUM(fault_transactions)/SUM(transactions) fault_codes_per_1000_transactions
FROM comparison_month WHERE shared_internal_host=0 AND host IS NOT NULL
GROUP BY machine_type ORDER BY tickets_per_100_active_months DESC""",
    'monthly_comparison': """SELECT month,COUNT(*) active_machine_months,SUM(tickets) tickets,SUM(transactions) transactions,
 100.0*SUM(tickets)/COUNT(*) tickets_per_100_active_months,
 1000.0*SUM(fault_transactions)/SUM(transactions) fault_codes_per_1000_transactions
FROM comparison_month WHERE shared_internal_host=0 AND host IS NOT NULL
GROUP BY month ORDER BY month""",
}

# ==============================================================================================================
# Hospital location -> time-zone group (same rules as verification/timestamp_semantics.py, copied here so this
# script runs standalone in Colab with only common.py).
# ==============================================================================================================
STATE_TZ = {
    **{s: 'America/New_York' for s in 'CT DC DE FL GA MA MD ME NC NH NJ NY OH PA RI SC VA VT WV KY'.split()},
    'MI': 'America/Detroit', 'IN': 'America/Indiana/Indianapolis',
    **{s: 'America/Chicago' for s in 'AL AR IA IL KS LA MN MO MS ND NE OK SD TN TX WI'.split()},
    **{s: 'America/Denver' for s in 'CO MT NM UT WY'.split()}, 'ID': 'America/Boise',
    'AZ': 'America/Phoenix',
    **{s: 'America/Los_Angeles' for s in 'CA NV OR WA'.split()},
    'AK': 'America/Anchorage', 'HI': 'Pacific/Honolulu',
    'ON': 'America/Toronto', 'QC': 'America/Toronto', 'NL': 'America/St_Johns', 'NFLD': 'America/St_Johns',
    'NS': 'America/Halifax', 'NB': 'America/Moncton', 'PE': 'America/Halifax', 'MB': 'America/Winnipeg',
    'SK': 'America/Regina', 'AB': 'America/Edmonton', 'BC': 'America/Vancouver',
}
ZIP_RULES = [('TX', ('798', '799', '885'), 'America/Denver'), ('FL', ('324', '325'), 'America/Chicago'),
             ('IN', ('463', '464', '476', '477'), 'America/Chicago'),
             ('TN', ('373', '374', '376', '377', '378', '379'), 'America/New_York'),
             ('KY', ('420', '421', '422', '423', '424'), 'America/Chicago'),
             ('NE', ('690', '691', '692', '693'), 'America/Denver'), ('OR', ('979',), 'America/Boise'),
             ('ID', ('835', '836', '837', '838'), 'America/Los_Angeles')]
GROUP = {'America/New_York': 'Eastern', 'America/Detroit': 'Eastern', 'America/Indiana/Indianapolis': 'Eastern',
         'America/Toronto': 'Eastern', 'America/Chicago': 'Central', 'America/Winnipeg': 'Central',
         'America/Denver': 'Mountain', 'America/Boise': 'Mountain', 'America/Edmonton': 'Mountain',
         'America/Phoenix': 'Arizona (no DST)', 'America/Regina': 'Saskatchewan (no DST)',
         'America/Los_Angeles': 'Pacific', 'America/Vancouver': 'Pacific', 'America/Anchorage': 'Alaska',
         'Pacific/Honolulu': 'Hawaii (no DST)', 'America/St_Johns': 'Newfoundland',
         'America/Halifax': 'Atlantic', 'America/Moncton': 'Atlantic'}
# (standard, daylight) UTC offsets in hours per zone group.
ZONE_OFFSETS = {'Eastern': (-5, -4), 'Central': (-6, -5), 'Mountain': (-7, -6), 'Arizona (no DST)': (-7, -7),
                'Pacific': (-8, -7), 'Alaska': (-9, -8), 'Hawaii (no DST)': (-10, -10), 'Atlantic': (-4, -3),
                'Saskatchewan (no DST)': (-6, -6), 'Newfoundland': (-3.5, -2.5)}
ZONE_ORDER = ['Eastern', 'Central', 'Mountain', 'Arizona (no DST)', 'Pacific', 'Atlantic', 'Newfoundland',
              'Saskatchewan (no DST)', 'Alaska', 'Hawaii (no DST)']
LOC_RE = re.compile(r'^(?P<city>.*),\s*(?P<st>[A-Za-z]{2,})\s+(?P<zip>\S.*)$')


def locate(location):
    m = LOC_RE.match((location or '').strip()) if isinstance(location, str) else None
    if not m:
        return None, None
    st, zp = m.group('st').upper(), m.group('zip').strip()
    zip3 = zp[:3] if re.match(r'^\d{5}', zp) else ('0' + zp)[:3] if re.fullmatch(r'\d{4}', zp) else zp[:3].upper()
    tz = STATE_TZ.get(st)
    for rst, prefixes, rtz in ZIP_RULES:
        if st == rst and zip3 in prefixes:
            tz = rtz
    return st, GROUP.get(tz)


def _off(zone, period):
    return ZONE_OFFSETS[zone][1 if period == 'DST' else 0]


# Clock hypotheses: recorded hour minus true local wall hour, for zone z in period p ('DST' or 'Standard').
HYPOTHESES = {
    'machine_local_dst': ('each machine records its own local wall clock, with DST where the location observes it',
                          lambda z, p: 0.0, lambda z: ZONE_OFFSETS[z][0] != ZONE_OFFSETS[z][1]),
    'utc': ('the recorded clock is UTC', lambda z, p: -_off(z, p), lambda z: False),
    'local_standard_no_dst': ('local standard time all year (machine clocks ignore DST)',
                              lambda z, p: _off(z, 'Standard') - _off(z, p), lambda z: False),
    'fixed_eastern_wall': ('one US Eastern wall clock (with DST) for every machine, e.g. server time',
                           lambda z, p: _off('Eastern', p) - _off(z, p), lambda z: True),
    'fixed_central_wall': ('one US Central wall clock (with DST) for every machine',
                           lambda z, p: _off('Central', p) - _off(z, p), lambda z: True),
    'fixed_pacific_wall': ('one US Pacific wall clock (with DST) for every machine',
                           lambda z, p: _off('Pacific', p) - _off(z, p), lambda z: True),
}


def us_dst_bounds(year):
    """US/Canada DST start (second Sunday of March) and end (first Sunday of November)."""
    march = dt.date(year, 3, 1)
    spring = march + dt.timedelta(days=(6 - march.weekday()) % 7 + 7)
    nov = dt.date(year, 11, 1)
    return spring, nov + dt.timedelta(days=(6 - nov.weekday()) % 7)


def qi(name):
    return '"' + str(name).replace('"', '""') + '"'


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if (x is None or math.isnan(x)) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if x is pd.NA or x is pd.NaT:
        return None
    return x


def fetch_df(conn, sql, params=(), batch=200_000):
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    parts = []
    while True:
        rows = cur.fetchmany(batch)
        if not rows:
            break
        parts.append(pd.DataFrame.from_records(rows, columns=cols))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


class GroupAcc:
    """Exact merge of partial GROUP BY results (sum/min/max), consolidated when it grows."""

    def __init__(self, keys, sums=(), mins=(), maxs=(), limit=2_000_000):
        self.keys, self.sums, self.mins, self.maxs = list(keys), list(sums), list(mins), list(maxs)
        self.parts, self.pending, self.limit = [], 0, limit

    def add(self, df):
        if len(df):
            self.parts.append(df)
            self.pending += len(df)
        if self.pending > self.limit:
            self._consolidate()

    def _consolidate(self):
        if len(self.parts) <= 1 and self.pending <= self.limit:
            return
        df = pd.concat(self.parts, ignore_index=True)
        for c in self.sums:
            df[c] = pd.to_numeric(df[c]).fillna(0).astype('int64')
        # pandas runs min/max on strings group by group in Python; use ordered category codes instead
        cats = {}
        for c in self.mins + self.maxs:
            if not pd.api.types.is_numeric_dtype(df[c]):
                cat = pd.Categorical(df[c].astype(object).where(df[c].notna(), None))
                cats[c] = cat.categories
                codes = cat.codes.astype('float64')
                codes[codes < 0] = np.nan
                df[c] = codes
        agg = {**{c: 'sum' for c in self.sums}, **{c: 'min' for c in self.mins}, **{c: 'max' for c in self.maxs}}
        out = df.groupby(self.keys, dropna=False, sort=False).agg(agg).reset_index()
        for c, categories in cats.items():
            vals = np.asarray(categories, dtype=object)
            codes = out[c].to_numpy()
            out[c] = pd.Series([None if np.isnan(k) else vals[int(k)] for k in codes], index=out.index,
                               dtype=object)
        self.parts, self.pending = [out], len(out)
        if self.pending > self.limit // 2:
            self.limit = 2 * self.pending

    def result(self):
        if not self.parts:
            return pd.DataFrame(columns=self.keys + self.sums + self.mins + self.maxs)
        self.limit = 0
        self._consolidate()
        out = self.parts[0]
        for c in self.sums:
            out[c] = pd.to_numeric(out[c]).fillna(0).astype('int64')
        return out


class DevIndex:
    """Device id -> small int, to keep the hour aggregates compact."""

    def __init__(self):
        self.idx = {}

    def encode(self, values):
        return np.fromiter((self.idx.setdefault(v, len(self.idx)) for v in values), dtype=np.int64, count=len(values))

    def decode_map(self):
        return {i: v for v, i in self.idx.items()}


def shift_estimate(target, ref):
    """Shift s (hours) maximising corr(target, roll(ref, s)): target(h) ~ ref(h - s), i.e. target is s hours later.
    Returns (continuous estimate via parabolic refinement, best integer shift, correlation, runner-up correlation)."""
    t = np.asarray(target, float)
    r = np.asarray(ref, float)
    if t.sum() <= 0 or r.sum() <= 0:
        return None
    t, r = t / t.sum(), r / r.sum()
    shifts = np.arange(-11, 13)
    sc = np.array([np.corrcoef(t, np.roll(r, s))[0, 1] for s in shifts])
    sc = np.nan_to_num(sc, nan=-1.0)
    i = int(np.argmax(sc))
    y0, y1, y2 = sc[(i - 1) % 24], sc[i], sc[(i + 1) % 24]
    denom = y0 - 2 * y1 + y2
    frac = 0.5 * (y0 - y2) / denom if denom < 0 else 0.0
    runner = float(np.max(np.delete(sc, i)))
    return float(shifts[i] + frac), int(shifts[i]), float(sc[i]), runner


def circ_diff(a, b):
    return ((a - b + 12) % 24) - 12


# ==============================================================================================================
# Run state, logging, checks, outputs
# ==============================================================================================================
class Run:
    def __init__(self, db_path, xlsx_path, out_dir, private_dir, opts):
        self.db_path = Path(db_path)
        self.xlsx_path = Path(xlsx_path)
        self.out = Path(out_dir)
        self.private = Path(private_dir)
        self.opts = opts
        self.cfg = json.loads(json.dumps(CONFIG))
        self.cfg.update(opts.get('config') or {})
        if opts.get('chunk_rows'):
            self.cfg['chunk_rows'] = int(opts['chunk_rows'])
        if opts.get('cache_mb'):
            self.cfg['cache_mb'] = int(opts['cache_mb'])
        self.out.mkdir(parents=True, exist_ok=True)
        self.private.mkdir(parents=True, exist_ok=True)
        self.t0 = time.time()
        self.checks, self.decisions, self.steps, self.facts = [], {}, {}, {}
        self.outputs = {'public': [], 'private': []}
        self.plog_path = self.private / 'db_private_run.log'
        self.plog_path.write_text('')
        if opts.get('expected_json'):
            self.expected = json.loads(Path(opts['expected_json']).read_text())
            self.expected_source = Path(opts['expected_json']).name
        else:
            self.expected = ZAC_EXPECTED
            self.expected_source = "Zac's notebook outputs (embedded constants)"
        self.state = {}

    # ---- logging
    def log(self, msg):
        print(f'[{time.time() - self.t0:8.1f}s] {msg}', flush=True)
        self.plog(msg)

    def plog(self, msg):
        with self.plog_path.open('a') as f:
            f.write(f'[{time.time() - self.t0:8.1f}s] {msg}\n')

    # ---- outputs
    def save(self, df, name, private=False):
        folder = self.private if private else self.out
        path = folder / (('db_private_' if private else 'db_') + name + '.csv')
        df.to_csv(path, index=False)
        key = 'private' if private else 'public'
        if path.name not in self.outputs[key]:
            self.outputs[key].append(path.name)
        return path

    def fact(self, step, key, value):
        self.facts.setdefault(step, {})[key] = jsonable(value)

    def exp(self, key, sub=None):
        v = self.expected.get(key)
        if sub is not None and isinstance(v, dict):
            v = v.get(sub)
        return v

    def check(self, step, name, expected, actual, tol=None, note=''):
        if expected is None:
            status = 'INFO'
        elif actual is None:
            status = 'FAIL'
        elif tol is not None and isinstance(expected, (int, float)) and not isinstance(expected, bool):
            try:
                status = 'PASS' if abs(float(actual) - float(expected)) <= tol + 1e-9 else 'FAIL'
            except (TypeError, ValueError):
                status = 'FAIL'
        else:
            a = actual
            if isinstance(expected, (int, np.integer)) and not isinstance(expected, bool):
                try:
                    a = int(actual)
                except (TypeError, ValueError):
                    pass
            status = 'PASS' if jsonable(a) == jsonable(expected) else 'FAIL'
        self.checks.append({'step': step, 'check': name, 'expected': jsonable(expected), 'actual': jsonable(actual),
                            'status': status, 'note': note})
        if status == 'FAIL':
            self.log(f'  CHECK FAIL  {name}: expected {expected!r}, actual {actual!r}')
        return status

    def compare_rows(self, step, name, actual_df, expected_rows, key, cols, tol_cols=(), tol=0.005):
        """Row-by-row comparison of a recomputed table against printed rows; writes a diff table."""
        if not expected_rows:
            self.check(step, name, None, f'{len(actual_df)} rows', note='no printed values to compare')
            return
        exp = pd.DataFrame(expected_rows)
        act = actual_df.copy()
        if isinstance(key, str):
            key = [key]
        for k in key:
            exp[k] = exp[k].astype(str)
            act[k] = act[k].astype(str)
        m = exp.merge(act[key + cols], on=key, how='left', suffixes=('_expected', '_actual'), indicator=True)
        rows_ok = []
        for _, r in m.iterrows():
            ok = r['_merge'] == 'both'
            for c in cols:
                e, a = r[c + '_expected'], r[c + '_actual']
                if pd.isna(a):
                    ok = False
                elif c in tol_cols:
                    ok &= abs(float(a) - float(e)) <= tol + 1e-9
                else:
                    ok &= str(a) == str(e) if isinstance(e, str) else float(a) == float(e)
            rows_ok.append(bool(ok))
        m['match'] = rows_ok
        self.save(m.drop(columns='_merge'), name + '_vs_expected')
        self.check(step, f'{name}: printed rows reproduced', f'{len(exp)}/{len(exp)}',
                   f'{int(sum(rows_ok))}/{len(exp)}', note='see db_' + name + '_vs_expected.csv')

    # ---- summary
    def write_summary(self):
        counts = Counter(c['status'] for c in self.checks)
        summary = {
            'generated_utc': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'database_file': self.db_path.name, 'workbook_file': self.xlsx_path.name,
            'expected_values_source': self.expected_source,
            'elapsed_seconds': round(time.time() - self.t0, 1),
            'check_counts': dict(counts), 'steps': self.steps, 'decisions': self.decisions,
            'checks': self.checks, 'facts': self.facts, 'outputs': self.outputs,
        }
        (self.out / 'db_summary.json').write_text(json.dumps(jsonable(summary), indent=2, default=str))
        md = ['# DB-backed verification summary', '',
              f"Database `{self.db_path.name}`; workbook `{self.xlsx_path.name}`; expected values: "
              f"{self.expected_source}. Generated {summary['generated_utc']} UTC; "
              f"elapsed {summary['elapsed_seconds']} s.", '',
              'Checks: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())), '', '## Steps', '',
              '| step | status | seconds | note |', '|---|---|---:|---|']
        for k, v in self.steps.items():
            md.append(f"| {k} | {v.get('status')} | {v.get('seconds', '')} | {v.get('note', '')} |")
        md += ['', '## Decisions', '']
        for k, v in self.decisions.items():
            verdict = v.get('verdict') if isinstance(v, dict) else v
            md.append(f'- **{k}**: {verdict}')
            if isinstance(v, dict) and v.get('rule'):
                md.append(f"  - rule: {v['rule']}")
        md += ['', '## Checks (expected vs actual)', '', '| step | check | expected | actual | status |',
               '|---|---|---|---|---|']
        for c in self.checks:
            e, a = json.dumps(c['expected'], default=str), json.dumps(c['actual'], default=str)
            e = e if len(e) <= 80 else e[:77] + '...'
            a = a if len(a) <= 80 else a[:77] + '...'
            md.append(f"| {c['step']} | {c['check']} | {e} | {a} | {c['status']} |")
        md += ['', '## Output files', '', 'Public (pseudonymous): ' + ', '.join(self.outputs['public']), '',
               f"Private (--private, not for commit): {len(self.outputs['private'])} files."]
        (self.out / 'db_summary.md').write_text('\n'.join(md) + '\n')
        return summary

    # ---- step runner
    def step(self, key, title, fn):
        self.log(f'===== {key}: {title}')
        t = time.time()
        try:
            note = fn(self) or ''
            self.steps[key] = {'title': title, 'status': 'done', 'seconds': round(time.time() - t, 1), 'note': note}
        except SkipStep as e:
            self.steps[key] = {'title': title, 'status': 'skipped', 'seconds': round(time.time() - t, 1),
                               'note': str(e)}
            self.log(f'  skipped: {e}')
        except Exception as e:  # noqa: BLE001 - keep going; full traceback goes to the private log only
            tb = traceback.format_exc()
            frame = traceback.extract_tb(e.__traceback__)[-1]
            self.steps[key] = {'title': title, 'status': 'ERROR', 'seconds': round(time.time() - t, 1),
                               'note': f'{type(e).__name__} at line {frame.lineno} ({frame.name}); '
                                       f'details in the private run log'}
            self.log(f'  ERROR in {key}: {type(e).__name__} at line {frame.lineno}')
            self.plog(tb)
        self.write_summary()


class SkipStep(Exception):
    pass


def hyp_check(R, step, label, key, exp_key):
    """Per-test check: the expected (planted) hypothesis must be among the hypotheses consistent with the test.
    Individual tests can be legitimately ambiguous; the combined verdict (step 8) must be exact."""
    d, e = R.decisions.get(key, {}), R.exp(exp_key)
    cons = d.get('consistent_hypotheses', [])
    if e is None:
        R.check(step, label, None, d.get('verdict'))
    else:
        R.check(step, f'{label}: expected hypothesis {e} is consistent', True, e in cons,
                note='consistent: ' + (', '.join(cons) or 'none'))


def need(R, *keys):
    missing = [k for k in keys if R.state.get(k) is None]
    if missing:
        raise SkipStep('needs ' + ', '.join(missing) + ' from an earlier step')


# ==============================================================================================================
# Step 0: open read-only, schema, indexes, column resolution, formats, counts
# ==============================================================================================================
def open_ro(R):
    path = R.db_path.resolve()
    if not path.exists():
        raise FileNotFoundError('database file not found')
    stat = path.stat()
    R.state['db_stat'] = (stat.st_size, stat.st_mtime_ns)
    last = None
    for extra in ('', '&immutable=1'):
        try:
            conn = sqlite3.connect(path.as_uri() + '?mode=ro' + extra, uri=True)
            conn.execute('PRAGMA query_only=ON')
            conn.execute('PRAGMA temp_store=MEMORY')
            conn.execute(f"PRAGMA cache_size=-{int(R.cfg['cache_mb']) * 1024}")
            conn.execute(f"PRAGMA threads={int(R.cfg['threads'])}")
            if R.opts.get('mmap_gb'):
                conn.execute(f"PRAGMA mmap_size={int(R.opts['mmap_gb'] * 1024 ** 3)}")
            conn.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()
            if extra:
                R.log('  opened with immutable=1 (plain read-only open failed, e.g. WAL without -shm)')
            return conn
        except sqlite3.Error as e:
            last = e
    raise last


def resolve_columns(R, table, logical, available):
    """Map logical names -> actual columns using CONFIG, then CANDIDATES regexes."""
    resolved, used = {}, set()
    order = [k for k in logical if k != 'ingest'] + (['ingest'] if 'ingest' in logical else [])
    for key in order:
        pref = logical[key]
        col = pref if pref in available else None
        if col is None:
            for pat in CANDIDATES.get(key, []):
                hits = [c for c in available if c not in used and re.search(pat, c, re.I)]
                if hits:
                    col = hits[0]
                    break
        resolved[key] = col
        if col:
            used.add(col)
    return resolved


def value_pattern(v):
    if v is None:
        return '<NULL>'
    s = str(v)
    p = re.sub(r'[0-9]', '9', s)
    p = re.sub(r'[A-Za-z]', 'A', p)
    return (p[:40] + '...') if len(p) > 40 else p + f' <{type(v).__name__}>'


def classify_time(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return 'empty'
    if all(isinstance(v, (int, float)) for v in vals):
        return 'epoch_ms' if np.median(vals) > 1e11 else 'epoch_s'
    s = [str(v) for v in vals]
    iso = np.mean([bool(re.match(r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}', x)) for x in s])
    if iso >= 0.99:
        return 'iso_datetime'
    if np.mean([bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', x)) for x in s]) >= 0.99:
        return 'iso_date'
    return 'other'


def step0_schema(R):
    conn = R.state['conn'] = open_ro(R)
    R.fact('0', 'sqlite_library_version', sqlite3.sqlite_version)
    R.fact('0', 'db_size_bytes', R.state['db_stat'][0])
    master = fetch_df(conn, "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")
    R.log('  sqlite_master: ' + ', '.join(f'{t}:{n}' for t, n in zip(master.type, master.name)))
    tables = master[master.type.isin(['table', 'view'])].name.tolist()
    schema_rows, index_rows = [], []
    for t in tables:
        for r in conn.execute(f'PRAGMA table_info({qi(t)})').fetchall():
            schema_rows.append({'table': t, 'cid': r[0], 'column': r[1], 'type': r[2], 'notnull': r[3],
                                'pk': r[5]})
        for il in conn.execute(f'PRAGMA index_list({qi(t)})').fetchall():
            cols = [c[2] for c in conn.execute(f'PRAGMA index_info({qi(il[1])})').fetchall()]
            index_rows.append({'table': t, 'index': il[1], 'unique': il[2], 'origin': il[3] if len(il) > 3 else '',
                               'partial': il[4] if len(il) > 4 else '', 'columns': ','.join(map(str, cols))})
    schema, idx = pd.DataFrame(schema_rows), pd.DataFrame(index_rows, columns=['table', 'index', 'unique', 'origin',
                                                                               'partial', 'columns'])
    R.save(master[['type', 'name', 'tbl_name', 'sql']], 'schema_master')
    R.save(schema, 'schema_columns')
    R.save(idx, 'schema_indexes')
    for t in tables:
        cols = schema[schema.table == t]
        R.log(f'  table {t}: ' + ', '.join(f'{c} {ty}' for c, ty in zip(cols.column, cols.type)))
    for _, r in idx.iterrows():
        R.log(f"  index {r['index']} on {r['table']}({r['columns']})")

    cfg = R.cfg
    names = {'events': cfg['events_table'], 'devices': cfg['devices_table'], 'codes': cfg['codes_table']}
    for k, t in list(names.items()):
        if t not in tables:
            hits = [x for x in tables if k[:-1] in x.lower() or (k == 'events' and 'transaction' in x.lower()
                                                                    and 'code' not in x.lower())]
            names[k] = hits[0] if hits else None
    R.state['tables'] = names
    cols = {}
    for k, t in names.items():
        avail = schema[schema.table == t].column.tolist() if t else []
        cols[k] = resolve_columns(R, t, cfg[k], avail) if t else {}
    ev = cols['events']
    if ev.get('ingest'):
        sample = [r[0] for r in conn.execute(f"SELECT {qi(ev['ingest'])} FROM {qi(names['events'])} LIMIT 500")]
        if classify_time(sample) not in ('iso_datetime', 'epoch_s', 'epoch_ms'):
            R.log(f"  ingestion candidate {ev['ingest']} does not look like a timestamp; ignored")
            ev['ingest'] = None
    if ev.get('time_utc') and ev.get('time_utc') == ev.get('time_local'):
        ev['time_utc'] = None
    R.state['cols'] = cols
    res = pd.DataFrame([{'table': names[k], 'logical': lk, 'column': c} for k in cols for lk, c in cols[k].items()])
    R.save(res, 'schema_resolution')
    R.log('  resolved columns: ' + '; '.join(f'{k}.{lk}={c}' for k in cols for lk, c in cols[k].items()))
    if not names['events'] or not ev.get('device') or not ev.get('code'):
        raise RuntimeError('cannot resolve the events table/device/code columns; edit CONFIG at the top')
    other_ts = [c for c in schema[schema.table == names['events']].column
                if c not in ev.values() and re.search('|'.join(CANDIDATES['ingest']), c, re.I)]
    R.fact('0', 'other_timestamp_like_columns', other_ts)
    R.check('0', 'ingestion/received timestamp column found', None, ev.get('ingest'),
            note='used by the step-7 offset test; skipped gracefully if absent')

    # value formats (patterns only: digits->9, letters->A)
    sample = fetch_df(conn, f"SELECT * FROM {qi(names['events'])} LIMIT 2000")
    fmt_rows = []
    for c in sample.columns:
        pats = Counter(value_pattern(v) for v in sample[c].astype(object).where(sample[c].notna(), None))
        for p, n in pats.most_common(3):
            fmt_rows.append({'table': names['events'], 'column': c, 'pattern': p, 'n_in_first_2000': n})
    R.save(pd.DataFrame(fmt_rows), 'value_formats')
    kinds = {k: classify_time(sample[ev[k]].tolist()) if ev.get(k) in sample.columns else None
             for k in ('date_local', 'time_local', 'time_utc', 'ingest')}
    R.state['kinds'] = kinds
    R.fact('0', 'time_formats', kinds)
    R.log(f'  time formats: {kinds}')
    R.save(sample.head(20), 'events_first_rows', private=True)

    # SQL expressions adapted to the formats
    tl, dl, tu = (qi(ev[k]) if ev.get(k) else None for k in ('time_local', 'date_local', 'time_utc'))

    def hour_expr(col, kind):
        if col is None:
            return 'NULL'
        if kind == 'epoch_s':
            return f"CAST(strftime('%H', {col}, 'unixepoch') AS INTEGER)"
        if kind == 'epoch_ms':
            return f"CAST(strftime('%H', {col}/1000, 'unixepoch') AS INTEGER)"
        if kind == 'iso_datetime':
            return f'CAST(substr({col},12,2) AS INTEGER)'
        return f"CAST(strftime('%H', {col}) AS INTEGER)"

    def date_expr(col, kind):
        if col is None:
            return 'NULL'
        if kind == 'epoch_s':
            return f"date({col}, 'unixepoch')"
        if kind == 'epoch_ms':
            return f"date({col}/1000, 'unixepoch')"
        return f'substr({col},1,10)'

    # day = 'YYYY-MM-DD' of the local date; month = Zac's substr(transaction_date_local,1,7)
    if dl and kinds['date_local'] in ('epoch_s', 'epoch_ms'):
        day = date_expr(dl, kinds['date_local'])
        month, dl_expr = f'substr({day},1,7)', day
    elif dl:
        day, month, dl_expr = f'substr({dl},1,10)', f'substr({dl},1,7)', dl
    else:
        day = date_expr(tl, kinds['time_local'])
        month, dl_expr = f'substr({day},1,7)', day
    R.state['date_iso'] = bool(dl) and kinds['date_local'] == 'iso_date'
    dcmp = dl if R.state['date_iso'] else day
    y0, y1 = R.cfg['dst_years']
    dst_case = 'CASE ' + ' '.join(
        f"WHEN {dcmp} >= '{a}' AND {dcmp} < '{b}' THEN 1" for a, b in (us_dst_bounds(y) for y in range(y0, y1 + 1))
    ) + ' ELSE 0 END'
    R.state['expr'] = {
        'dev': qi(ev['device']), 'code': qi(ev['code']), 'tl': tl or 'NULL', 'tu': tu or 'NULL',
        'dl': dl_expr, 'day': day, 'month': month,
        'tl_date': date_expr(tl, kinds['time_local']), 'hour_local': hour_expr(tl, kinds['time_local']),
        'hour_utc': hour_expr(tu, kinds['time_utc']), 'dst': dst_case,
        'ingest': qi(ev['ingest']) if ev.get('ingest') else None, 'events': qi(names['events']),
    }
    R.plog('SQL expressions: ' + json.dumps(R.state['expr']))
    if kinds['time_local'] not in ('iso_datetime',):
        R.log(f"  WARNING: time_local format is {kinds['time_local']}; hour expression adapted, check results")

    # row counts
    counts = []
    for k, t in names.items():
        if not t:
            continue
        if k == 'events':
            try:
                lo, hi = conn.execute(f'SELECT MIN(rowid), MAX(rowid) FROM {qi(t)}').fetchone()
                R.state['has_rowid'] = lo is not None
                R.state['rowid_range'] = (lo, hi)
                counts.append({'table': t, 'rows': None, 'min_rowid': lo, 'max_rowid': hi,
                               'note': 'exact count comes from the step-4 scan'})
            except sqlite3.OperationalError:
                R.state['has_rowid'] = False
                counts.append({'table': t, 'rows': None, 'note': 'WITHOUT ROWID table: chunked scan unavailable'})
        else:
            counts.append({'table': t, 'rows': conn.execute(f'SELECT COUNT(*) FROM {qi(t)}').fetchone()[0]})
    try:
        stat1 = fetch_df(conn, 'SELECT tbl, idx, stat FROM sqlite_stat1')
        R.save(stat1, 'sqlite_stat1')
    except sqlite3.Error:
        pass
    R.save(pd.DataFrame(counts), 'row_counts')
    R.fact('0', 'has_rowid', R.state.get('has_rowid'))
    R.fact('0', 'rowid_range', R.state.get('rowid_range'))
    R.log(f"  events rowid range {R.state.get('rowid_range')}; has_rowid={R.state.get('has_rowid')}")
    codes_n = next((c['rows'] for c in counts if c['table'] == names['codes']), None)
    R.check('0', 'transaction_codes rows', R.exp('codes_rows'), codes_n)

    # indexes by leading column (used to pick fast paths)
    lead = {}
    for _, r in idx[idx.table == names['events']].iterrows():
        first = r['columns'].split(',')[0] if r['columns'] else None
        lead.setdefault(first, []).append(r['index'])
    R.state['lead_index'] = lead
    if R.opts.get('sha256'):
        R.log('  computing SHA-256 of the database file (17 GB: a few minutes)')
        digest = common.sha256_file(R.db_path)
        R.fact('0', 'db_sha256', digest)
        R.check('0', "database SHA-256 equals Zac's verified checksum", common.ZAC_DB_SHA256, digest)
    return f"{len(tables)} tables, {len(idx)} indexes"


# ==============================================================================================================
# Step 1: devices dictionary
# ==============================================================================================================
def step1_devices(R):
    conn, names, dc = R.state['conn'], R.state['tables'], R.state['cols']['devices']
    if not names.get('devices') or not dc.get('device'):
        raise SkipStep('devices table/id column not found')
    sel = [f"{qi(dc[k])} AS {k}" if dc.get(k) else f'NULL AS {k}' for k in ('device', 'status', 'type', 'url')]
    d = fetch_df(conn, f"SELECT {', '.join(sel)} FROM {qi(names['devices'])}")
    d['raw_id'] = d['device']
    d['device'] = d['device'].map(clean)
    n_rows, n_unique = len(d), d.device.nunique(dropna=True)
    R.check('1', 'devices rows', R.exp('devices_rows'), n_rows)
    R.check('1', 'device ids unique after clean()', R.exp('devices_unique'), bool(d.device.is_unique))
    R.fact('1', 'device_ids_null_or_blank', int(d.device.isna().sum()))
    R.fact('1', 'device_ids_changed_by_clean', int((d.raw_id.astype(str) != d.device.astype(str)).sum()))
    upper = d.device.dropna().str.upper()
    R.fact('1', 'device_ids_colliding_case_insensitive', int(upper.duplicated(keep=False).sum()))
    d['machine_type_raw'] = d['type']
    d['machine_type'] = d['type'].map(lambda x: clean(x).lower() if clean(x) else 'Unknown')
    url = d['url']
    d['url_norm'] = url.map(lambda u: u.strip().rstrip('/').lower() if isinstance(u, str) else None)
    d['shared_internal_host'] = url.fillna('').astype(str).str.rstrip('/').eq(common.SHARED_INTERNAL_HOST).astype(int)
    hosts = sorted(set(url.dropna()))
    hostmap = {s: f'Host {i:03d}' for i, s in enumerate(hosts, 1)}
    d['host'] = url.map(hostmap)
    raw = R.state.get('raw')
    if raw is None:
        raw = R.state['raw'] = common.load_raw(R.xlsx_path)
    maps = common.build_maps(raw, [x for x in d.raw_id if clean(x) is not None])
    maps['host'] = hostmap
    R.state['maps'] = maps
    d['machine_id'] = d.device.map(maps['serial'])
    R.state['devices'] = d
    summary = {'rows': n_rows, 'distinct_ids_after_clean': n_unique, 'machine_types': d.machine_type.nunique(),
               'unknown_type_devices': int((d.machine_type == 'Unknown').sum()), 'distinct_hosts': len(hosts),
               'distinct_hosts_normalised': d.url_norm.dropna().nunique(),
               'blank_string_hosts': int((url.fillna('x').astype(str).str.strip() == '').sum()),
               'null_host_devices': int(url.isna().sum()),
               'shared_internal_host_devices': int(d.shared_internal_host.sum()),
               'shared_internal_host_url_variants': int(url[d.shared_internal_host == 1].nunique()),
               'hosts_with_trailing_slash': int(sum(h.endswith('/') for h in hosts))}
    for k, v in summary.items():
        R.fact('1', k, v)
    R.save(pd.DataFrame([summary]), 'devices_summary')
    R.save(d.machine_type.value_counts(dropna=False).rename_axis('machine_type').reset_index(name='devices'),
           'devices_machine_types')
    R.save(d['status'].fillna('[NULL]').value_counts().rename_axis('device_status').reset_index(name='devices'),
           'devices_status')
    R.save(pd.crosstab(d.machine_type, d['status'].fillna('[NULL]')).reset_index(), 'devices_type_by_status')
    R.save(pd.DataFrame({'host': list(hostmap.values()), 'clearview_url': list(hostmap.keys())}), 'host_map',
           private=True)
    R.log(f"  devices {n_rows:,}; unique after clean {d.device.is_unique}; types {summary['machine_types']}; "
          f"hosts {len(hosts):,}; shared-host devices {summary['shared_internal_host_devices']:,}; "
          f"NULL-host devices {summary['null_host_devices']:,}")
    return f'{n_rows} devices, {len(hosts)} hosts'


# ==============================================================================================================
# Step 2: linkage
# ==============================================================================================================
def build_analysis_db(R):
    """Zac's cell-4 tables in an in-memory SQLite: cases (+views), devices, codes."""
    raw, maps, d = R.state['raw'], R.state['maps'], R.state['devices']
    cases = common.build_cases(raw, maps)
    adb = common.case_database(cases)
    d[['machine_id', 'status', 'machine_type_raw', 'machine_type', 'host', 'shared_internal_host']].rename(
        columns={'status': 'device_status'}).to_sql('devices', adb, index=False, if_exists='replace')
    names, cc = R.state['tables'], R.state['cols']['codes']
    if names.get('codes') and cc.get('code'):
        codes = fetch_df(R.state['conn'], f"SELECT * FROM {qi(names['codes'])}")
        codes = codes.rename(columns={cc['code']: 'transaction_code'})
        if cc.get('description') and cc['description'] in codes:
            codes = codes.rename(columns={cc['description']: 'transaction_description'})
        if 'transaction_description' not in codes:
            codes['transaction_description'] = None
        codes['bucket'] = codes.transaction_code.map(lambda x: LOOKUP.get(x, 'Malformed'))
        codes['provisional_fault'] = codes.bucket.isin(['Mechanical fault', 'Electronics/software/comms']).astype(int)
        codes[['transaction_code', 'transaction_description', 'bucket', 'provisional_fault']].to_sql(
            'codes', adb, index=False, if_exists='replace')
        R.save(codes[['transaction_code', 'transaction_description', 'bucket', 'provisional_fault']], 'codes_buckets')
    adb.executescript('CREATE UNIQUE INDEX IF NOT EXISTS ix_cases ON cases(case_id);'
                      'CREATE INDEX IF NOT EXISTS ix_casemachine ON cases(machine_id,opened_at);'
                      'CREATE INDEX IF NOT EXISTS ix_devices ON devices(machine_id);')
    R.state['cases'] = cases
    R.state['adb'] = adb


def ticket_zones(raw):
    geo = raw['Hospital City, State, Zip'].map(locate)
    t = pd.DataFrame({'serial': raw['Serial #'].map(clean), 'state': geo.map(lambda g: g[0]),
                      'zone': geo.map(lambda g: g[1] or 'Unparsed')})
    rows = []
    for serial, g in t.groupby('serial', sort=False):
        zc = g.zone.value_counts()
        sc = g.state.value_counts()
        top = zc.index[0] if len(zc) == 1 or zc.iloc[0] > zc.iloc[1] else 'Ambiguous'
        rows.append({'serial': serial, 'zone': top, 'modal_state': sc.index[0] if len(sc) else None,
                     'tickets': len(g), 'states': g.state.nunique(), 'zones': g.zone.nunique()})
    return t, pd.DataFrame(rows)


def step2_linkage(R):
    need(R, 'devices')
    build_analysis_db(R)
    adb, cases = R.state['adb'], R.state['cases']
    q = fetch_df(adb, ZAC_SQL['record_quality'])
    R.save(q, 'record_quality')
    for c in q.columns:
        R.check('2', f'record_quality.{c}', R.exp('record_quality', c), q.loc[0, c])
    lk = fetch_df(adb, ZAC_SQL['linkage'])
    R.save(lk, 'linkage')
    for c in lk.columns:
        R.check('2', f'linkage.{c}', R.exp('linkage', c), lk.loc[0, c], tol=0.005 if c == 'matched_pct' else None)
    R.log(f"  linkage: {int(lk.loc[0, 'matched_cases']):,} of {int(lk.loc[0, 'cases']):,} tickets, "
          f"{int(lk.loc[0, 'matched_machines']):,} machines, {lk.loc[0, 'matched_pct']}%")

    # zones per ticket / serial (used again in step 5)
    raw = R.state['raw']
    tz_ticket, tz_serial = ticket_zones(raw)
    R.state['serial_zone'] = tz_serial
    d = R.state['devices']
    dev_set = set(d.device.dropna())
    base = fetch_df(adb, 'SELECT case_id, machine_id, model, record_type, status, trouble_code, service_group, month '
                         'FROM case_base')
    zone_by_case = dict(zip(cases.case_id, tz_ticket.zone))      # build_cases keeps the workbook row order
    base['zone'] = base.case_id.map(zone_by_case)
    base['matched'] = base.machine_id.isin(set(d.machine_id.dropna()))
    rows = []
    for dim in ['record_type', 'model', 'status', 'trouble_code', 'service_group', 'zone', 'month']:
        g = base.assign(v=base[dim].fillna('[NULL]')).groupby('v').agg(
            tickets=('case_id', 'size'), unmatched=('matched', lambda s: int((~s).sum())))
        g['unmatched_pct'] = (100 * g.unmatched / g.tickets).round(2)
        rows.append(g.reset_index().rename(columns={'v': 'value'}).assign(dimension=dim))
    R.save(pd.concat(rows)[['dimension', 'value', 'tickets', 'unmatched', 'unmatched_pct']], 'unmatched_profile')

    # near-match diagnostics for unmatched serials (aggregate public, detail private)
    serials = raw['Serial #'].map(clean)
    um = serials[~serials.isin(dev_set)]
    norms = {'upper': lambda s: s.upper(), 'alnum_upper': lambda s: re.sub(r'[^0-9A-Za-z]', '', s).upper(),
             'alnum_upper_no_leading_zeros': lambda s: re.sub(r'[^0-9A-Za-z]', '', s).upper().lstrip('0')}
    near, private_rows = [], []
    for name, f in norms.items():
        idx = {}
        for x in dev_set:
            idx.setdefault(f(x), []).append(x)
        hit = um.map(lambda s: f(s) in idx if isinstance(s, str) else False)
        near.append({'normalisation': name, 'unmatched_tickets': len(um), 'unmatched_serials': um.nunique(),
                     'tickets_matching_after_normalisation': int(hit.sum()),
                     'serials_matching_after_normalisation': int(um[hit].nunique())})
        for s in um[hit].unique():
            private_rows.append({'normalisation': name, 'ticket_serial': s, 'device_ids': ';'.join(idx[f(s)])})
    R.save(pd.DataFrame(near), 'unmatched_near_match')
    R.save(pd.DataFrame(private_rows, columns=['normalisation', 'ticket_serial', 'device_ids']),
           'unmatched_near_match', private=True)
    R.save(um.value_counts().rename_axis('ticket_serial').reset_index(name='tickets'), 'unmatched_serials',
           private=True)
    return f"{int(lk.loc[0, 'matched_cases'])} matched tickets"


# ==============================================================================================================
# Step 3: model->type map, mapping summary (+variants), host-level audit
# ==============================================================================================================
def mapping_measures(m, host_col='host', account_col='customer'):
    """Zac's three measures on a matched ticket frame (one row per matched ticket)."""
    a = int((m.groupby('model').machine_type.nunique() > 1).sum())
    b = int((m.dropna(subset=[host_col]).groupby(account_col)[host_col].nunique() > 1).sum())
    c = int((m.dropna(subset=[host_col]).groupby(host_col)[account_col].nunique() > 1).sum())
    return a, b, c


def step3_mapping(R):
    need(R, 'adb')
    adb, d = R.state['adb'], R.state['devices']
    mm = fetch_df(adb, ZAC_SQL['model_type_mapping'])
    R.save(mm, 'model_type_mapping')
    R.compare_rows('3', 'model_type_mapping_head', mm, R.exp('model_type_mapping_head'),
                   key=['model', 'machine_type'], cols=['matched_cases', 'machines'])
    ms = fetch_df(adb, ZAC_SQL['mapping_summary'])
    R.save(fetch_df(adb, ZAC_SQL['customer_host_audit']), 'customer_host_audit')
    for _, r in ms.iterrows():
        R.check('3', f"mapping_summary: {r['measure']}", R.exp('mapping_summary', r['measure']), r['value'])
    # variants on a pandas frame of matched tickets (one row per ticket)
    m = fetch_df(adb, 'SELECT c.case_id, c.customer, c.machine_id, c.model, d.machine_type, d.host, '
                      'd.shared_internal_host FROM cases c JOIN devices d USING(machine_id)')
    dd = d.dropna(subset=['machine_id']).drop_duplicates('machine_id').set_index('machine_id')
    m['host_norm'] = m.machine_id.map(dd.url_norm)
    modal = m.groupby('machine_id').customer.agg(lambda s: s.value_counts().sort_index().idxmax())
    m['modal_customer'] = m.machine_id.map(modal)
    clean_hosts = m[(m.shared_internal_host == 0) & m.host.notna()]
    variants = [
        ('Zac (pandas re-implementation)', mapping_measures(m)),
        ('excluding shared internal host and NULL host', mapping_measures(clean_hosts)),
        ("excluding 'Unknown' machine type (measure 1 only)",
         (int((m[m.machine_type != 'Unknown'].groupby('model').machine_type.nunique() > 1).sum()), None, None)),
        ('host URL normalised (trim, lower, no trailing slash)', mapping_measures(m, host_col='host_norm')),
        ('one modal account per machine', mapping_measures(m, account_col='modal_customer')),
        ('one modal account per machine, excl. shared/NULL host',
         mapping_measures(clean_hosts.assign(modal_customer=clean_hosts.machine_id.map(modal)),
                          account_col='modal_customer')),
    ]
    vt = pd.DataFrame([{'variant': v, 'models_spanning_gt1_type': a, 'customers_spanning_gt1_host': b,
                        'hosts_with_gt1_customer': c} for v, (a, b, c) in variants])
    for col in vt.columns[1:]:
        vt[col] = vt[col].astype('Int64')
    R.save(vt, 'mapping_summary_variants')
    zac_vals = tuple(int(x) for x in ms.value)
    R.check('3', 'pandas re-implementation equals Zac SQL mapping_summary', list(zac_vals), list(variants[0][1]))
    R.log('  mapping variants:\n' + vt.to_string(index=False))
    R.state['matched_tickets'] = m
    host_level(R, transacting=None)
    return f'mapping_summary {list(zac_vals)}'


def host_level(R, transacting=None):
    """Per-host audit: fleet devices, ticketed devices, ticket accounts, transacting devices; fleet shares."""
    d, m, maps = R.state['devices'], R.state['matched_tickets'], R.state['maps']
    inv_acct = {v: k for k, v in maps['account'].items()}
    dev = d[['machine_id', 'host', 'url', 'shared_internal_host']].copy()
    dev['transacting'] = dev.machine_id.isin(transacting) if transacting is not None else np.nan
    dev['host_key'] = dev.host.fillna('(no host)')
    tick = m.assign(host_key=m.host.fillna('(no host)'))
    per = dev.groupby('host_key').agg(devices_in_fleet=('machine_id', 'size'),
                                      shared_internal_host=('shared_internal_host', 'max'))
    if transacting is not None:
        per['transacting_devices'] = dev.groupby('host_key').transacting.sum().astype(int)
    tg = tick.groupby('host_key').agg(devices_with_tickets=('machine_id', 'nunique'), tickets=('case_id', 'size'),
                                      ticket_accounts=('customer', 'nunique'),
                                      ticket_accounts_modal=('modal_customer', 'nunique'))
    per = per.join(tg, how='left').fillna({'devices_with_tickets': 0, 'tickets': 0, 'ticket_accounts': 0,
                                           'ticket_accounts_modal': 0})
    acct_lists = tick.groupby('host_key').customer.agg(lambda s: ';'.join(sorted(set(s))))
    per['accounts'] = acct_lists

    def klass(row, col):
        if row.name == '(no host)':
            return 'No host (NULL)'
        if row.shared_internal_host:
            return 'Shared internal host'
        if row[col] == 0:
            return 'No tickets'
        return 'Single-account' if row[col] == 1 else 'Multi-account'

    per['host_class'] = per.apply(lambda r: klass(r, 'ticket_accounts'), axis=1)
    per['host_class_modal_account'] = per.apply(lambda r: klass(r, 'ticket_accounts_modal'), axis=1)
    per = per.reset_index().rename(columns={'host_key': 'host'})
    for c in ['devices_with_tickets', 'tickets', 'ticket_accounts', 'ticket_accounts_modal']:
        per[c] = per[c].astype(int)
    R.save(per, 'host_level')
    priv = per.copy()
    url_of = {v: k for k, v in maps['host'].items()}
    priv.insert(1, 'clearview_url', priv.host.map(url_of))
    priv['accounts'] = priv.accounts.map(lambda s: ';'.join(inv_acct.get(x, x) for x in s.split(';'))
                                         if isinstance(s, str) else s)
    R.save(priv, 'host_level', private=True)
    total = int(per.devices_in_fleet.sum())
    shares = []
    for col in ['host_class', 'host_class_modal_account']:
        g = per.groupby(col).agg(hosts=('host', 'size'), devices=('devices_in_fleet', 'sum'),
                                 devices_with_tickets=('devices_with_tickets', 'sum'))
        g['share_of_fleet_pct'] = (100 * g.devices / total).round(2)
        if 'transacting_devices' in per:
            g['transacting_devices'] = per.groupby(col).transacting_devices.sum()
            g['share_of_transacting_pct'] = (100 * g.transacting_devices / max(1, per.transacting_devices.sum())
                                             ).round(2)
        shares.append(g.reset_index().rename(columns={col: 'host_class'}).assign(account_rule=col))
    sh = pd.concat(shares)
    R.save(sh, 'host_class_fleet_share')
    real = per[~per.host_class.isin(['No host (NULL)', 'Shared internal host'])]
    aph = real[real.ticket_accounts > 0].ticket_accounts.value_counts().sort_index()
    R.save(aph.rename_axis('accounts_per_host').reset_index(name='hosts'), 'accounts_per_host')
    hpa = m[(m.shared_internal_host == 0) & m.host.notna()].groupby('customer').host.nunique().value_counts()
    R.save(hpa.sort_index().rename_axis('hosts_per_account').reset_index(name='accounts'), 'hosts_per_account')
    for _, r in sh[sh.account_rule == 'host_class'].iterrows():
        R.fact('3', f"fleet_share_pct[{r['host_class']}]", r['share_of_fleet_pct'])
        R.fact('3', f"hosts[{r['host_class']}]", r['hosts'])
    if R.exp('host_classes') and transacting is None:
        got = sh[sh.account_rule == 'host_class'].set_index('host_class').hosts.to_dict()
        for k, v in R.exp('host_classes').items():
            R.check('3', f'hosts in class {k}', v, got.get(k, 0))
    R.log('  host classes (per-ticket accounts):\n' + sh[sh.account_rule == 'host_class'].to_string(index=False))


# ==============================================================================================================
# Pilot selection (cell 8) and extraction
# ==============================================================================================================
def pilot_select(R):
    cases, d = R.state['cases'], R.state['devices']
    c = cases
    eligible = c[c.machine_id.isin(d.machine_id) & c.opened_at.between('2025-09-02', '2026-07-31 23:59:59')].copy()
    eligible['stratum'] = eligible.trouble_code.fillna('Missing')
    eligible['sample_order'] = eligible.case_id.map(common.pilot_order)
    eligible['within_stratum'] = eligible.sort_values('sample_order').groupby('stratum').cumcount()
    pilot = eligible.sort_values(['within_stratum', 'sample_order']).head(30).copy()
    inverse = {v: k for k, v in R.state['maps']['serial'].items()}
    pilot['device'] = pilot.machine_id.map(inverse)
    pilot['anchor'] = pilot.opened_at.map(dt.datetime.fromisoformat)
    pilot['lo'] = (pilot.anchor - dt.timedelta(days=32)).map(lambda x: x.strftime('%Y-%m-%d'))
    pilot['hi'] = (pilot.anchor + dt.timedelta(days=2)).map(lambda x: x.strftime('%Y-%m-%d'))
    R.state['pilot'] = pilot
    return pilot


def pilot_via_index(R):
    e, ev = R.state['expr'], R.state['cols']['events']
    pilot = R.state['pilot']
    sql = (f"SELECT {e['tu']} AS transaction_time_utc, {e['code']} AS transaction_code FROM {e['events']} "
           f"WHERE {e['dev']}=? AND {e['dl']}>=? AND {e['dl']}<=? ORDER BY {e['tu']} DESC, {e['code']}")
    R.plog('pilot SQL: ' + sql)
    vals = {}
    for row in pilot.itertuples():
        vals[row.case_id] = R.state['conn'].execute(sql, (row.device, row.lo, row.hi)).fetchall()
    R.state['pilot_vals'] = vals
    R.log(f'  pilot extracted via index for {len(vals)} tickets')


def pilot_from_rows(R, rows):
    """rows: DataFrame(dev, tu, code, dl) for the pilot devices; reproduce cell 8's per-ticket extraction."""
    rows = rows if rows is not None else pd.DataFrame(columns=['dev', 'tu', 'code', 'dl'])
    vals = {}
    for row in R.state['pilot'].itertuples():
        sub = rows[(rows.dev == row.device) & (rows.dl >= row.lo) & (rows.dl <= row.hi)]
        sub = sub.sort_values(['code']).sort_values(['tu'], ascending=False, kind='stable', na_position='last')
        vals[row.case_id] = [(None if pd.isna(t) else t, k) for t, k in zip(sub.tu, sub.code)]
    return vals


# ==============================================================================================================
# The shared pass over transaction_events (steps 4-7)
# ==============================================================================================================
def build_tasks(R):
    e = R.state['expr']
    E = e['events']
    tasks = []
    acc_a = GroupAcc(['external_device_id', 'month', 'transaction_code'],
                     sums=['n', 'clocks_differ', 'missing_time', 'null_local_date', 'date_time_mismatch'],
                     mins=['first_date'], maxs=['last_date'])
    sel_a = (f"SELECT {e['dev']} AS external_device_id, {e['month']} AS month, {e['code']} AS transaction_code, "
             f"COUNT(*) AS n, MIN({e['dl']}) AS first_date, MAX({e['dl']}) AS last_date, "
             f"SUM({e['tl']} IS NOT {e['tu']}) AS clocks_differ, "
             f"SUM({e['tu']} IS NULL OR {e['dl']} IS NULL) AS missing_time, "
             f"SUM({e['dl']} IS NULL) AS null_local_date, "
             f"SUM({e['tl_date']} IS NOT {e['day']}) AS date_time_mismatch "
             f"FROM {E} NOT INDEXED {{where}} GROUP BY {e['dev']}, {e['month']}, {e['code']}")
    tasks.append({'name': 'A_month_code', 'sql': sel_a, 'acc': acc_a, 'big_sort': True})

    devidx = R.state['devidx'] = DevIndex()
    acc_b = GroupAcc(['dev', 'month', 'dst', 'hour_local', 'hour_utc'], sums=['n', 'date_time_mismatch'])
    sel_b = (f"SELECT {e['dev']} AS dev, {e['month']} AS month, {e['dst']} AS dst, {e['hour_local']} AS hour_local, "
             f"{e['hour_utc']} AS hour_utc, COUNT(*) AS n, SUM({e['tl_date']} IS NOT {e['day']}) AS date_time_mismatch "
             f"FROM {E} NOT INDEXED {{where}} GROUP BY 1, 2, 3, 4, 5")
    tasks.append({'name': 'B_hours', 'sql': sel_b, 'acc': acc_b, 'encode': True, 'big_sort': True})

    days = transition_days(R)
    R.state['transition_days'] = days
    day_list = ','.join(f"'{x}'" for x in sorted({x for t in days for x in t['days']}))
    acc_c = GroupAcc(['dev', 'day', 'hour_local', 'hour_utc'], sums=['n'])
    sel_c = (f"SELECT {e['dev']} AS dev, {e['day']} AS day, {e['hour_local']} AS hour_local, "
             f"{e['hour_utc']} AS hour_utc, COUNT(*) AS n FROM {E} {{not_indexed}} "
             f"WHERE {e['day']} IN ({day_list}) {{and_where}} GROUP BY 1, 2, 3, 4")
    lead = R.state.get('lead_index', {})
    date_col = R.state['cols']['events'].get('date_local')
    R.state['date_indexed'] = bool(date_col and date_col in lead and R.state.get('date_iso'))
    if R.state['date_indexed']:
        # equality on the raw column lets SQLite use the date index
        sel_c_idx = sel_c.replace(f"WHERE {e['day']} IN", f"WHERE {qi(date_col)} IN")
        tasks.append({'name': 'C_transition_days', 'sql': sel_c_idx, 'acc': acc_c, 'encode': True,
                      'indexed_once': True})
    else:
        tasks.append({'name': 'C_transition_days', 'sql': sel_c, 'acc': acc_c, 'encode': True})

    if e['tu'] != 'NULL':
        sel_d = (f"SELECT rowid AS row_id, {e['dev']} AS dev, {e['dl']} AS date_local, {e['tl']} AS time_local, "
                 f"{e['tu']} AS time_utc, {e['code']} AS transaction_code"
                 + (f", {e['ingest']} AS ingest" if e['ingest'] else '') +
                 f" FROM {E} {{not_indexed}} WHERE {e['tl']} IS NOT {e['tu']} {{and_where}}")
        if not R.state.get('has_rowid'):
            sel_d = sel_d.replace('rowid AS row_id', 'NULL AS row_id')
        tasks.append({'name': 'D_clock_differ', 'sql': sel_d, 'rows': []})
    if e['ingest'] and R.state.get('has_rowid'):
        mod = int(R.cfg['sample_modulus'])
        sel_e = (f"SELECT {e['dev']} AS dev, {e['day']} AS day, {e['tl']} AS time_local, {e['tu']} AS time_utc, "
                 f"{e['ingest']} AS ingest FROM {E} {{not_indexed}} WHERE rowid % {mod} = 0 {{and_where}}")
        tasks.append({'name': 'E_ingest_sample', 'sql': sel_e, 'rows': []})
    if R.state.get('pilot') is not None:
        p = R.state['pilot']
        ph = ','.join('?' * p.device.nunique())
        sel_f = (f"SELECT {e['dev']} AS dev, {e['tu']} AS tu, {e['code']} AS code, {e['dl']} AS dl FROM {E} "
                 f"{{not_indexed}} WHERE {e['dev']} IN ({ph}) AND {e['dl']} >= ? AND {e['dl']} <= ? {{and_where}}")
        tasks.append({'name': 'F_pilot_rows', 'sql': sel_f, 'rows': [],
                      'params': list(p.device.unique()) + [p.lo.min(), p.hi.max()]})
    acc_g = GroupAcc(['transaction_code'], sums=['n'])
    sel_g = f"SELECT {e['code']} AS transaction_code, COUNT(*) AS n FROM {E} {{not_indexed}} {{where}} GROUP BY 1"
    tasks.append({'name': 'G_code_totals', 'sql': sel_g, 'acc': acc_g, 'chunk_only': True})
    for t in tasks:
        t['secs'] = 0.0
        t.setdefault('params', [])
    return tasks


def transition_days(R):
    lo, hi = R.cfg['data_window']
    out = []
    y0, y1 = R.cfg['dst_years']
    for y in range(y0, y1 + 1):
        spring, fall = us_dst_bounds(y)
        for kind, day in (('spring', spring), ('fall', fall)):
            if lo <= day.isoformat() <= hi:
                out.append({'kind': kind, 'day': day.isoformat(),
                            'days': [(day + dt.timedelta(days=k)).isoformat() for k in (-1, 0, 1)]})
    return out


def render(sql, chunked):
    if chunked:
        return sql.format(where='WHERE rowid BETWEEN ? AND ?', and_where='AND rowid BETWEEN ? AND ?',
                          not_indexed='NOT INDEXED')
    return sql.format(where='', and_where='', not_indexed='')


def consume(R, t, df):
    if not len(df):
        return
    if 'acc' in t:
        if t.get('encode'):
            df['dev'] = R.state['devidx'].encode(df['dev'].tolist())
        t['acc'].add(df)
    else:
        t['rows'].append(df)


def scan_pass(R, tasks):
    conn = R.state['conn']
    plans = []
    chunked = bool(R.state.get('has_rowid')) and not R.opts.get('no_chunk')
    for t in tasks:
        if t.get('indexed_once'):
            sql = render(t['sql'], False)
            t0 = time.time()
            plans.append({'task': t['name'], 'mode': 'indexed once',
                          'plan': ' | '.join(r[-1] for r in conn.execute('EXPLAIN QUERY PLAN ' + sql, t['params']))})
            consume(R, t, fetch_df(conn, sql, t['params']))
            t['secs'] += time.time() - t0
            R.log(f"  {t['name']}: indexed query done in {t['secs']:.1f}s")
    loop = [t for t in tasks if not t.get('indexed_once')]
    if chunked:
        lo, hi = R.state['rowid_range']
        step = int(R.cfg['chunk_rows'])
        nchunks = max(1, math.ceil((hi - lo + 1) / step))
        for t in loop:
            sql = render(t['sql'], True)
            plans.append({'task': t['name'], 'mode': 'chunked',
                          'plan': ' | '.join(r[-1] for r in conn.execute('EXPLAIN QUERY PLAN ' + sql,
                                                                         t['params'] + [lo, lo]))})
        R.save(pd.DataFrame(plans), 'query_plans')
        R.log(f'  chunked pass: rowids {lo:,}..{hi:,} in {nchunks} chunks of {step:,}; '
              f"tasks {[t['name'] for t in loop]}")
        start_t, last_log = time.time(), 0.0
        rows_seen = 0
        for i, start in enumerate(range(lo, hi + 1, step), 1):
            end = min(start + step - 1, hi)
            for t in loop:
                t0 = time.time()
                df = fetch_df(conn, render(t['sql'], True), t['params'] + [start, end])
                if t['name'] == 'A_month_code' and len(df):
                    rows_seen += int(pd.to_numeric(df.n).sum())
                consume(R, t, df)
                t['secs'] += time.time() - t0
            el = time.time() - start_t
            if el - last_log > 20 or i == nchunks or i <= 2:
                last_log = el
                frac = (end - lo + 1) / (hi - lo + 1)
                eta = el / frac * (1 - frac) if frac > 0 else float('nan')
                R.log(f'  chunk {i}/{nchunks}: {frac:6.1%} of rowid range, {rows_seen:,} rows, '
                      f'{rows_seen / max(el, 1e-9):,.0f} rows/s, elapsed {el:,.0f}s, ETA {eta:,.0f}s')
    else:
        R.log('  full-scan mode (no rowid or --no-chunk): one statement per task; SQLite sorts before the first '
              'row arrives, so progress is only reported per task')
        for t in loop:
            if t.get('chunk_only'):
                continue
            if 'rowid %' in t['sql'] and not R.state.get('has_rowid'):
                continue
            sql = render(t['sql'], False)
            plans.append({'task': t['name'], 'mode': 'full',
                          'plan': ' | '.join(r[-1] for r in conn.execute('EXPLAIN QUERY PLAN ' + sql, t['params']))})
            if t.get('big_sort'):
                conn.execute('PRAGMA temp_store=FILE')   # a 118M-row sorter must not live in RAM
            t0 = time.time()
            cur = conn.execute(sql, t['params'])
            cols = [c[0] for c in cur.description]
            n = 0
            while True:
                rows = cur.fetchmany(200_000)
                if not rows:
                    break
                n += len(rows)
                consume(R, t, pd.DataFrame.from_records(rows, columns=cols))
                R.log(f"  {t['name']}: {n:,} result rows ({time.time() - t0:,.0f}s)")
            conn.execute('PRAGMA temp_store=MEMORY')
            t['secs'] += time.time() - t0
            R.log(f"  {t['name']}: done in {t['secs']:,.1f}s")
        R.save(pd.DataFrame(plans), 'query_plans')
    timing = {t['name']: round(t['secs'], 1) for t in tasks}
    R.fact('4', 'scan_task_seconds', timing)
    R.log(f'  pass timings (s): {timing}')
    res = {}
    for t in tasks:
        if 'acc' in t:
            res[t['name']] = t['acc'].result() if (chunked or not t.get('chunk_only')) else None
        else:
            res[t['name']] = pd.concat(t['rows'], ignore_index=True) if t['rows'] else None
    R.state['scan'] = res
    return res


def step_pass(R):
    need(R, 'expr')
    if R.opts.get('skip_scans'):
        raise SkipStep('--skip-scans')
    if R.state.get('cases') is not None and R.state.get('devices') is not None:
        try:
            pilot_select(R)
            lead = R.state.get('lead_index', {})
            if R.state['cols']['events']['device'] in lead:
                pilot_via_index(R)
        except Exception as e:  # noqa: BLE001
            R.log(f'  pilot preparation failed ({type(e).__name__}); pilot step will be skipped')
            R.plog(traceback.format_exc())
            R.state['pilot'] = None
    tasks = build_tasks(R)
    scan_pass(R, tasks)
    if R.state.get('pilot') is not None and 'F_pilot_rows' in R.state['scan']:
        scan_vals = pilot_from_rows(R, R.state['scan'].get('F_pilot_rows'))
        if R.state.get('pilot_vals') is None:
            R.state['pilot_vals'] = scan_vals
        else:   # two independent extraction paths must agree (as multisets: tie order within a second may differ)
            same = all(Counter(R.state['pilot_vals'][k]) == Counter(scan_vals[k]) for k in scan_vals)
            R.check('4b', 'pilot extraction: per-ticket indexed queries == rows collected in the scan', True, same)
    return 'one pass over transaction_events'


# ==============================================================================================================
# Step 4: Zac's aggregation, reconciliation and rate tables
# ==============================================================================================================
def step4_zac_tables(R):
    need(R, 'scan')
    a = R.state['scan']['A_month_code']
    serialmap = R.state['maps']['serial'] if R.state.get('maps') else {}
    n_groups, n_rows = len(a), int(a.n.sum())
    R.log(f'  telemetry_month_code groups {n_groups:,}; rows {n_rows:,}')
    R.check('4', 'telemetry_month_code groups', R.exp('telemetry_groups'), n_groups)
    R.check('4', 'atomic transactions represented', R.exp('telemetry_rows'), n_rows)
    R.check('4', 'rows with local string IS NOT utc string (clocks_differ)', R.exp('clocks_differ'),
            int(a.clocks_differ.sum()))
    R.check('4', 'missing_time (utc NULL or local date NULL)', R.exp('missing_time'), int(a.missing_time.sum()))
    R.check('4', 'rows with NULL local date', R.exp('null_local_date'), int(a.null_local_date.sum()))
    R.check('4', 'rows whose local date differs from the date part of the local time string',
            R.exp('date_time_mismatch'), int(a.date_time_mismatch.sum()),
            note='0 means transaction_date_local was derived from the same clock as transaction_time_local')
    R.fact('4', 'groups_with_null_month', int(a.month.isna().sum()))
    ids = pd.Series(a.external_device_id.unique())
    unmapped = ids[~ids.isin(serialmap)]
    R.check('4', 'telemetry device ids absent from Zac serialmap (raw, unclean ids)',
            R.exp('unmapped_telemetry_devices'), len(unmapped))
    R.fact('4', 'unmapped_ids_that_match_after_clean', int(unmapped.map(clean).isin(serialmap).sum()))
    if R.state.get('devices') is not None:
        dset = set(R.state['devices'].device.dropna())
        R.fact('4', 'transacting_ids_not_in_devices_table', int((~ids.map(clean).isin(dset)).sum()))
        R.fact('4', 'device_table_ids_without_transactions', int(len(dset - set(ids.map(clean)))))
    # independent reconciliations
    b = R.state['scan'].get('B_hours')
    if b is not None:
        R.check('4', 'row total: month-code aggregation == hour aggregation (independent query)', n_rows,
                int(b.n.sum()))
    g = R.state['scan'].get('G_code_totals')
    by_code = a.groupby('transaction_code', dropna=False).n.sum()
    if g is None and R.state['cols']['events']['code'] in R.state.get('lead_index', {}):
        R.log('  independent code totals via the code index')
        e = R.state['expr']
        g = fetch_df(R.state['conn'], f"SELECT {e['code']} AS transaction_code, COUNT(*) AS n FROM {e['events']} "
                                      f"GROUP BY 1")
    if g is not None:
        ind = {str(k): int(v) for k, v in g.groupby('transaction_code', dropna=False).n.sum().items()}
        agg = {str(k): int(v) for k, v in by_code.items()}
        R.check('4', 'every code total reconciles to an independent COUNT(*) GROUP BY code', True, ind == agg)
    if R.state.get('rowid_range') and R.state['rowid_range'][0] is not None:
        lo, hi = R.state['rowid_range']
        R.fact('4', 'rowid_span_minus_rows', (hi - lo + 1) - n_rows)
    if R.exp('code_totals'):
        exp_codes = R.exp('code_totals')
        R.check('4', 'code totals equal planted totals', {k: int(v) for k, v in sorted(exp_codes.items())},
                {str(k): int(v) for k, v in sorted(by_code.items())})
    months = a.groupby('month', dropna=False).agg(rows=('n', 'sum'), devices=('external_device_id', 'nunique'),
                                                  clocks_differ=('clocks_differ', 'sum'),
                                                  date_time_mismatch=('date_time_mismatch', 'sum')).reset_index()
    R.save(months, 'telemetry_by_month')

    # Zac's telemetry_month_code -> analysis DB, then his queries
    adb = R.state.get('adb')
    if adb is None:
        raise SkipStep('case/device tables unavailable (step 1/2 failed); aggregation checks above still ran')
    tmc = a.copy()
    tmc['machine_id'] = tmc.external_device_id.map(serialmap)
    tmc.drop(columns='external_device_id').to_sql('telemetry_month_code', adb, index=False, if_exists='replace')
    adb.executescript('CREATE INDEX IF NOT EXISTS ix_month ON telemetry_month_code(machine_id,month);')
    cov = fetch_df(adb, ZAC_SQL['telemetry_date_coverage'])
    R.save(cov, 'telemetry_date_coverage')
    for c in cov.columns:
        R.check('4', f'coverage.{c}', R.exp('coverage', c), cov.loc[0, c])
    have_codes = adb.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='codes'").fetchone()[0]
    if not have_codes:
        raise SkipStep('codes table missing; bucket and rate tables skipped')
    bt = fetch_df(adb, ZAC_SQL['telemetry_buckets'])
    R.save(bt, 'telemetry_buckets')
    eb = R.exp('bucket_totals') or {}
    got = {('[not in codes table]' if pd.isna(k) else k): int(v) for k, v in zip(bt.bucket, bt.transactions)}
    for k in sorted(set(eb) | set(got)):
        R.check('4', f'bucket total: {k}', eb.get(k) if eb else None, got.get(k, 0))
    ct = fetch_df(adb, ZAC_SQL['code_totals'])
    R.save(ct, 'telemetry_code_totals')
    total = int(ct.transactions.sum())
    non_ok = int(ct.loc[ct.transaction_code != '00', 'transactions'].sum())
    faults = int(ct.loc[ct.bucket.isin(['Mechanical fault', 'Electronics/software/comms']), 'transactions'].sum())
    code05 = int(ct.loc[ct.transaction_code == '05', 'transactions'].sum())
    R.check('4', 'non-success transactions', R.exp('non_success'), non_ok)
    R.check('4', 'non-success %', R.exp('non_success_pct'), round(100 * non_ok / total, 2), tol=0.005)
    R.check('4', 'narrow fault transactions', R.exp('narrow_faults'), faults)
    R.check('4', 'narrow faults per 1,000', R.exp('narrow_per_1000'), round(1000 * faults / total, 2), tol=0.005)
    R.check('4', 'narrow faults per 1,000 excluding code 05', R.exp('narrow_per_1000_ex05'),
            round(1000 * (faults - code05) / total, 2), tol=0.005)
    adb.executescript(ZAC_SQL['views'])
    co = fetch_df(adb, ZAC_SQL['comparison_cohort'])
    R.save(co, 'comparison_cohort')
    R.compare_rows('4', 'comparison_cohort', co, R.exp('comparison_cohort'), 'cohort',
                   ['active_machine_months', 'tickets', 'transactions', 'zero_ticket_months'])
    ex = fetch_df(adb, ZAC_SQL['ticket_cohort_exclusions'])
    R.save(ex, 'ticket_cohort_exclusions')
    ee = R.exp('ticket_cohort_exclusions') or {}
    gotx = dict(zip(ex.reason, ex.tickets))
    for k in sorted(set(ee) | set(gotx)):
        R.check('4', f'ticket_cohort_exclusions: {k}', ee.get(k) if ee else None, int(gotx.get(k, 0)))
    rates = fetch_df(adb, ZAC_SQL['machine_type_rates'])
    R.save(rates, 'machine_type_rates')
    R.compare_rows('4', 'machine_type_rates', rates, R.exp('machine_type_rates'), 'machine_type', _RATE_COLS[1:],
                   tol_cols=_RATE_COLS[-2:])
    R.check('4', 'rate numerator == directly linked eligible tickets', int(gotx.get('Included in comparison', 0)),
            int(rates.tickets.sum()))
    if len(rates):
        R.check('4', 'overall comparison rate per 100 active machine-months', R.exp('overall_rate'),
                round(100 * rates.tickets.sum() / rates.active_machine_months.sum(), 2), tol=0.005)
    mon = fetch_df(adb, ZAC_SQL['monthly_comparison'])
    R.save(mon, 'monthly_comparison')
    R.compare_rows('4', 'monthly_comparison', mon, R.exp('monthly_comparison'), 'month', _MONTH_COLS[1:],
                   tol_cols=_MONTH_COLS[-2:])
    # transacting devices -> host-level audit with fleet shares
    if R.state.get('matched_tickets') is not None:
        host_level(R, transacting=set(tmc.machine_id.dropna()))
    return f'{n_groups} groups, {n_rows} rows'


def step4b_pilot(R):
    if R.opts.get('skip_scans') and R.state.get('pilot_vals') is None:
        need(R, 'cases', 'devices', 'expr')
        pilot_select(R)
        if R.state['cols']['events']['device'] not in R.state.get('lead_index', {}):
            raise SkipStep('--skip-scans and no index on the device column')
        pilot_via_index(R)
    need(R, 'pilot', 'pilot_vals')
    pilot, vals = R.state['pilot'], R.state['pilot_vals']
    events, windows, last, three = [], [], [], []
    for row in pilot.itertuples():
        v = vals[row.case_id]
        anchor = row.anchor
        for off in (-12, 0, 12):
            a = anchor + dt.timedelta(hours=off)
            low = a - dt.timedelta(days=30)
            win = [(t, k) for t, k in v if t is not None and low.isoformat(' ') <= t < a.isoformat(' ')]
            ns = [(t, k) for t, k in win if k != '00']
            windows.append({'case_id': row.case_id, 'offset_hours': off, 'all_events': len(win),
                            'non_success_events': len(ns), 'distinct_codes': len({k for _, k in ns})})
        events += [(row.case_id, t, k) for t, k in v if k != '00']
        lo, hi = (anchor - dt.timedelta(days=30)).isoformat(' '), anchor.isoformat(' ')
        ns0 = pd.DataFrame([(t, k) for t, k in v if k != '00' and t is not None and lo <= t < hi],
                           columns=['t', 'k'])
        if len(ns0):
            g = ns0.groupby('k').agg(last_seen=('t', 'max'), occurrences=('t', 'size')).reset_index()
            g = g.sort_values(['last_seen', 'k'], ascending=[False, True]).head(10)
            for rank, r in enumerate(g.itertuples(), 1):
                last.append({'case_id': row.case_id, 'transaction_code': r.k, 'last_seen': r.last_seen,
                             'occurrences': r.occurrences, 'recency_rank': rank})
            top3 = ns0.sort_values(['t', 'k'], ascending=[False, True]).head(3)
            three.append({'case_id': row.case_id, 'raw_events': len(top3), 'distinct_codes': top3.k.nunique()})
    w = pd.DataFrame(windows)
    R.save(w, 'pilot_window_counts')
    R.check('4b', 'pilot non-success events extracted', R.exp('pilot_events'), len(events))
    summ = w.groupby('offset_hours').agg(tickets=('case_id', 'size'),
                                         tickets_with_transactions=('all_events', lambda s: int((s > 0).sum())),
                                         tickets_with_non_success=('non_success_events',
                                                                   lambda s: int((s > 0).sum()))).reset_index()
    R.save(summ, 'pilot_scenario_summary')
    R.compare_rows('4b', 'pilot_scenario_summary', summ, R.exp('pilot_scenario_summary'), 'offset_hours',
                   ['tickets', 'tickets_with_transactions', 'tickets_with_non_success'])
    w0 = w[w.offset_hours == 0].drop(columns='offset_hours')
    R.compare_rows('4b', 'pilot_offset0', w0, R.exp('pilot_offset0'), 'case_id',
                   ['non_success_events', 'distinct_codes', 'all_events'])
    lc = pd.DataFrame(last, columns=['case_id', 'transaction_code', 'last_seen', 'occurrences', 'recency_rank'])
    R.save(lc, 'pilot_last_distinct_codes')
    R.compare_rows('4b', 'pilot_last_codes_head', lc.head(15), R.exp('pilot_last_codes_head'),
                   ['case_id', 'recency_rank'], ['transaction_code', 'last_seen', 'occurrences'])
    th = pd.DataFrame(three, columns=['case_id', 'raw_events', 'distinct_codes'])
    full = th[th.raw_events == 3]
    R.check('4b', 'pilot: tickets with >=3 non-success events / with a repeated code in the last three',
            jsonable(R.exp('pilot_repeated_last3')),
            {'tickets_with_3': len(full), 'with_repeated_codes': int((full.distinct_codes < 3).sum())})
    return f'{len(pilot)} pilot tickets'


# ==============================================================================================================
# Step 5: hour-of-day profiles by zone group x DST period
# ==============================================================================================================
def device_zone_map(R):
    sz = R.state.get('serial_zone')
    if sz is None:
        raw = R.state.get('raw')
        if raw is None:
            raw = R.state['raw'] = common.load_raw(R.xlsx_path)
        _, sz = ticket_zones(raw)
        R.state['serial_zone'] = sz
    return dict(zip(sz.serial, sz.zone))


UNLINKED = 'Unlinked (no ticket location)'


def zone_of(devices, dz):
    """Map raw device ids -> hospital zone group, computing each distinct id once."""
    s = pd.Series(devices)
    uniq = {u: (dz.get(clean(u), UNLINKED) if isinstance(u, str) else UNLINKED) for u in s.dropna().unique()}
    return s.map(uniq).fillna(UNLINKED).to_numpy()


def profiles(df, hour_col, zones):
    """zone x period -> 24-vector of counts."""
    out = {}
    df = df[df[hour_col].between(0, 23)]
    for (z, p), g in df.groupby(['zone', 'period']):
        out[(z, p)] = np.bincount(g[hour_col].astype(int), weights=g.n, minlength=24)[:24]
    for z in zones:
        if (z, 'DST') in out or (z, 'Standard') in out:
            out[(z, 'All')] = out.get((z, 'DST'), np.zeros(24)) + out.get((z, 'Standard'), np.zeros(24))
    return out


def score_hypotheses(obs_zone, obs_dst, tol):
    """obs_zone: {(zone, period): shift vs Eastern}; obs_dst: {zone: Standard-vs-DST shift}."""
    rows, verdict = [], {}
    for h, (desc, rec, _) in HYPOTHESES.items():
        n = ok = 0
        for (z, p), s in obs_zone.items():
            pred = rec(z, p) - rec('Eastern', p)
            good = abs(circ_diff(s, pred)) <= tol
            rows.append({'hypothesis': h, 'test': 'zone vs Eastern', 'zone': z, 'period': p, 'observed': round(s, 2),
                         'predicted': pred, 'match': good})
            n += 1
            ok += good
        for z, s in obs_dst.items():
            pred = rec(z, 'Standard') - rec(z, 'DST')
            good = abs(circ_diff(s, pred)) <= tol
            rows.append({'hypothesis': h, 'test': 'Standard vs DST (same zone)', 'zone': z, 'period': 'Std-DST',
                         'observed': round(s, 2), 'predicted': pred, 'match': good})
            n += 1
            ok += good
        verdict[h] = {'comparisons': n, 'matches': ok, 'consistent': n > 0 and ok == n}
    return pd.DataFrame(rows), verdict


def step5_clock_profiles(R):
    need(R, 'scan')
    b = R.state['scan']['B_hours'].copy()
    dz = device_zone_map(R)
    inv = R.state['devidx'].decode_map()
    b['device'] = b.dev.map(inv)
    b['zone'] = zone_of(b.device, dz)
    b['period'] = np.where(b.dst.astype(int) == 1, 'DST', 'Standard')
    dev_z = b.groupby('zone').device.nunique()
    R.save(dev_z.rename_axis('zone').reset_index(name='transacting_devices'), 'clock_devices_by_zone')
    R.fact('5', 'transacting_devices_by_zone', dev_z.to_dict())
    zones = [z for z in ZONE_ORDER if z in set(b.zone)]
    min_rows = int(R.cfg['min_zone_rows'])
    tol = float(R.cfg['shift_tolerance_h'])
    clocks = [('local', 'hour_local')]
    if b.hour_utc.notna().any() and not (b.hour_utc.fillna(-1) == b.hour_local.fillna(-1)).all():
        clocks.append(('utc', 'hour_utc'))
    R.fact('5', 'utc_hour_differs_from_local_hour_rows', int(b.loc[b.hour_utc.fillna(-1) != b.hour_local.fillna(-1),
                                                                   'n'].sum()))
    prof_rows, shift_rows, results = [], [], {}
    for label, col in clocks:
        pz = profiles(b[b.zone.isin(zones)], col, zones)
        allz = b.assign(zone='All devices')
        pz.update(profiles(allz, col, ['All devices']))
        for (z, p), v in pz.items():
            for h in range(24):
                prof_rows.append({'clock_column': label, 'zone': z, 'period': p, 'hour': h, 'transactions': int(v[h]),
                                  'share_pct': round(100 * v[h] / v.sum(), 3) if v.sum() else None})
        obs_zone, obs_dst = {}, {}
        for p in ('DST', 'Standard'):
            ref = pz.get(('Eastern', p))
            if ref is None or ref.sum() < min_rows:
                continue
            for z in zones:
                if z in ('Eastern', 'Newfoundland') or (z, p) not in pz or pz[(z, p)].sum() < min_rows:
                    continue
                est = shift_estimate(pz[(z, p)], ref)
                if est:
                    obs_zone[(z, p)] = est[0]
                    shift_rows.append({'clock_column': label, 'test': 'zone vs Eastern', 'zone': z, 'period': p,
                                       'shift_h': round(est[0], 2), 'best_integer_shift': est[1],
                                       'corr': round(est[2], 4), 'runner_up_corr': round(est[3], 4),
                                       'rows': int(pz[(z, p)].sum())})
        for z in zones + ['All devices']:
            if z == 'Newfoundland':
                continue
            s, d = pz.get((z, 'Standard')), pz.get((z, 'DST'))
            if s is None or d is None or s.sum() < min_rows or d.sum() < min_rows:
                continue
            est = shift_estimate(s, d)
            if est:
                if z != 'All devices':
                    obs_dst[z] = est[0]
                shift_rows.append({'clock_column': label, 'test': 'Standard vs DST (same zone)', 'zone': z,
                                   'period': 'Std-DST', 'shift_h': round(est[0], 2), 'best_integer_shift': est[1],
                                   'corr': round(est[2], 4), 'runner_up_corr': round(est[3], 4),
                                   'rows': int(s.sum() + d.sum())})
        table, verdict = score_hypotheses(obs_zone, obs_dst, tol)
        R.save(table.assign(clock_column=label), f'clock_hypotheses_{label}')
        results[label] = verdict
        consistent = [h for h, v in verdict.items() if v['consistent']]
        R.log(f'  [{label}] zone shifts vs Eastern: ' + ', '.join(f'{z}/{p} {s:+.2f}h' for (z, p), s in
                                                                    obs_zone.items()))
        R.log(f'  [{label}] Standard-vs-DST shifts: ' + ', '.join(f'{z} {s:+.2f}h' for z, s in obs_dst.items()))
        R.log(f'  [{label}] hypotheses consistent with every comparison: {consistent or "none"}')
        R.decisions[f'clock_profiles_{label}'] = {
            'verdict': (consistent[0] if len(consistent) == 1 else
                        'inconclusive: no hypothesis fits every comparison' if not consistent else
                        'ambiguous: ' + ', '.join(consistent)),
            'consistent_hypotheses': consistent,
            'scores': verdict, 'zone_shifts_vs_eastern': {f'{z}|{p}': round(s, 2) for (z, p), s in obs_zone.items()},
            'standard_vs_dst_shifts': {z: round(s, 2) for z, s in obs_dst.items()},
            'rule': ('Profiles of transaction_time_' + label + ' hours by hospital zone. Machine-local wall clock: '
                     'zone shifts vs Eastern ~0 and Standard-vs-DST shifts ~0. UTC: Central +1, Mountain +2, '
                     'Pacific +3 (Arizona +3 in DST months, +2 in standard months) and Standard-vs-DST +1 in '
                     'DST-observing zones. Fixed server wall clock: zone shifts like UTC, Standard-vs-DST 0 except '
                     f'no-DST zones. Tolerance +/-{tol} h; profiles need >= {min_rows:,} rows.')}
    R.save(pd.DataFrame(prof_rows), 'clock_hour_profiles')
    R.save(pd.DataFrame(shift_rows), 'clock_shift_estimates')
    monthly = (b[b.zone.isin(zones)].groupby(['zone', 'month', 'hour_local']).n.sum().reset_index()
               .rename(columns={'n': 'transactions'}))
    R.save(monthly, 'clock_hour_by_zone_month')
    mm = b[b.date_time_mismatch > 0].groupby(['zone', 'hour_local']).date_time_mismatch.sum().reset_index()
    R.save(mm, 'date_time_mismatch_by_zone_hour')
    v = R.decisions['clock_profiles_local']['verdict']
    hyp_check(R, '5', 'hour profiles (transaction_time_local)', 'clock_profiles_local', 'clock_hypothesis')
    return v


# ==============================================================================================================
# Step 6: DST transition days
# ==============================================================================================================
def step6_dst_transition(R):
    c = R.state.get('scan', {}).get('C_transition_days') if R.state.get('scan') else None
    if c is None and R.opts.get('skip_scans'):
        need(R, 'expr')
        date_col = R.state['cols']['events'].get('date_local')
        if not (date_col and date_col in R.state.get('lead_index', {}) and R.state.get('date_iso')):
            raise SkipStep('--skip-scans and no usable index on the local date column')
        e = R.state['expr']
        days = R.state['transition_days'] = transition_days(R)
        day_list = ','.join(f"'{x}'" for x in sorted({x for t in days for x in t['days']}))
        R.state['devidx'] = R.state.get('devidx') or DevIndex()
        c = fetch_df(R.state['conn'],
                     f"SELECT {e['dev']} AS dev, {e['day']} AS day, {e['hour_local']} AS hour_local, "
                     f"{e['hour_utc']} AS hour_utc, COUNT(*) AS n FROM {e['events']} "
                     f"WHERE {qi(R.state['cols']['events']['date_local'])} IN ({day_list}) GROUP BY 1, 2, 3, 4")
        c['dev'] = R.state['devidx'].encode(c.dev.tolist())
    if c is None:
        raise SkipStep('transition-day counts unavailable')
    dz = device_zone_map(R)
    inv = R.state['devidx'].decode_map()
    c = c.copy()
    c['zone'] = zone_of(c.dev.map(inv), dz)
    hourly = c.groupby(['zone', 'day', 'hour_local']).n.sum().reset_index()
    allrows = c.groupby(['day', 'hour_local']).n.sum().reset_index().assign(zone='All devices')
    hourly = pd.concat([hourly, allrows], ignore_index=True)
    R.save(hourly.rename(columns={'n': 'transactions'}), 'dst_transition_hourly')
    min_ref = float(R.cfg['min_transition_ref'])
    rows = []
    for t in R.state['transition_days']:
        prev, day, nxt = t['days']
        hour = 2 if t['kind'] == 'spring' else 1
        for z, g in hourly.groupby('zone'):
            def cnt(dd, g=g, hour=hour):
                return int(g[(g.day == dd) & (g.hour_local == hour)].n.sum())
            ref = (cnt(prev) + cnt(nxt)) / 2
            val = cnt(day)
            ratio = val / ref if ref > 0 else None
            cls, llr = transition_class(t['kind'], val, ref, min_ref)
            rows.append({'transition': t['kind'], 'day': day, 'hour': hour, 'zone': z, 'count_on_day': val,
                         'mean_count_adjacent_days': ref, 'ratio': None if ratio is None else round(ratio, 3),
                         'log_likelihood_ratio': None if llr is None else round(llr, 2), 'classification': cls})
    met = pd.DataFrame(rows)
    R.save(met, 'dst_transition_metrics')
    # score hypotheses: does each zone's recorded clock jump at local 02:00 on the transition days?
    verdict = {}
    for h, (_, _, jumps) in HYPOTHESES.items():
        n = ok = 0
        for _, r in met.iterrows():
            if r.zone not in ZONE_OFFSETS or r.classification in ('insufficient data', 'unclear'):
                continue
            pred = jumps(r.zone)
            obs = r.classification in ('gap', 'doubled')
            n += 1
            ok += pred == obs
        verdict[h] = {'comparisons': n, 'matches': ok, 'consistent': n > 0 and ok == n}
    consistent = [h for h, v in verdict.items() if v['consistent']]
    R.log('  DST transition ratios:\n' + met.to_string(index=False))
    R.decisions['dst_transition'] = {
        'verdict': (consistent[0] if len(consistent) == 1 else
                    'inconclusive: no hypothesis fits every zone' if not consistent else
                    'ambiguous: ' + ', '.join(consistent)),
        'consistent_hypotheses': consistent, 'scores': verdict,
        'rule': ('Hourly counts by local date and transaction_time_local hour, compared with the mean of the two '
                 'adjacent days. A DST-observing local wall clock has an (almost) empty 02:00-02:59 on the '
                 'spring-forward day and a ~2x 01:00-01:59 on the fall-back day, but not in Arizona/Hawaii/'
                 'Saskatchewan. UTC or local standard time: neither occurs anywhere. A single fixed DST wall clock: '
                 'both occur in every zone, including no-DST zones. Each zone is classified by a Poisson '
                 'log-likelihood ratio (gap: rate 2% of adjacent days vs 100%; doubled: 200% vs 100%), |LLR| > 3 '
                 '(~20:1); smaller |LLR| is "unclear" and not scored. For large counts the cut-offs are a ratio of '
                 '~0.25 (spring) and ~1.44 (fall).')}
    hyp_check(R, '6', 'DST-transition days', 'dst_transition', 'dst_transition_hypothesis')
    return R.decisions['dst_transition']['verdict']


def transition_class(kind, val, ref, min_ref=1.0):
    """Poisson log-likelihood ratio for one zone on a DST-transition day.
    spring: H1 'gap' (rate = 2% of the adjacent-day mean) vs H0 'no gap' (rate = mean);
    fall:   H1 'doubled' (rate = 2 x mean) vs H0 'not doubled' (rate = mean). Decide when |LLR| > 3."""
    if ref < min_ref or ref <= 0:
        return 'insufficient data', None
    if kind == 'spring':
        eps = 0.02
        llr = val * math.log(eps) + ref * (1 - eps)
        return ('gap' if llr > 3 else 'no gap' if llr < -3 else 'unclear'), llr
    llr = val * math.log(2) - ref
    return ('doubled' if llr > 3 else 'not doubled' if llr < -3 else 'unclear'), llr


# ==============================================================================================================
# Step 7: rows where local and UTC strings differ; ingestion offsets
# ==============================================================================================================
def parse_ts(s):
    s = pd.Series(s)
    if pd.api.types.is_numeric_dtype(s):
        unit = 'ms' if s.dropna().median() > 1e11 else 's'
        return pd.to_datetime(s, unit=unit, errors='coerce')
    return pd.to_datetime(s.astype(object).where(s.notna(), None), errors='coerce', utc=True,
                          format='ISO8601').dt.tz_localize(None)


def step7_offsets(R):
    need(R, 'scan')
    scan = R.state['scan']
    dz = device_zone_map(R)
    serialmap = R.state['maps']['serial'] if R.state.get('maps') else {}
    d = scan.get('D_clock_differ')
    notes = []
    if d is not None or 'D_clock_differ' in scan:
        d = d if d is not None else pd.DataFrame(columns=['row_id', 'dev', 'date_local', 'time_local', 'time_utc',
                                                          'transaction_code'])
        d = d.copy()
        d['offset_hours'] = ((parse_ts(d.time_local) - parse_ts(d.time_utc)).dt.total_seconds() / 3600).round(3)
        d['machine_id'] = d.dev.map(lambda x: serialmap.get(x, serialmap.get(clean(x), 'unmapped')))
        d['zone'] = zone_of(d.dev, dz)
        d['utc_is_null'] = d.time_utc.isna()
        pub_cols = ['row_id', 'machine_id', 'zone', 'date_local', 'time_local', 'time_utc', 'offset_hours',
                    'transaction_code', 'utc_is_null'] + (['ingest'] if 'ingest' in d else [])
        R.save(d[pub_cols], 'clock_differ_rows')
        R.save(d, 'clock_differ_rows', private=True)
        a = scan.get('A_month_code')
        R.check('7', 'rows with local IS NOT utc (dumped)', R.exp('clocks_differ'), len(d))
        if a is not None:
            R.check('7', 'dumped rows == clocks_differ total from the aggregation', int(a.clocks_differ.sum()),
                    len(d))
        summ = (d.assign(offset=d.offset_hours.astype(object).where(d.offset_hours.notna(), 'NULL utc'))
                .groupby(['zone', 'offset']).size().reset_index(name='rows'))
        R.save(summ, 'clock_differ_summary')
        R.fact('7', 'clock_differ_offsets_hours', d.offset_hours.value_counts(dropna=False).head(20).to_dict())
        R.fact('7', 'clock_differ_devices', int(d.dev.nunique()))
        R.log(f'  {len(d)} rows differ; offsets (h): {d.offset_hours.value_counts(dropna=False).head(10).to_dict()}')
        notes.append(f'{len(d)} differing rows')
    e = scan.get('E_ingest_sample')
    if e is None:
        R.decisions['ingestion_offsets'] = {'verdict': 'not run: no ingestion/received timestamp column'
                                            if not R.state['expr']['ingest'] else 'not run: no rowid for sampling'}
        R.check('7', 'ingestion offsets', R.exp('ingestion_hypothesis'),
                R.decisions['ingestion_offsets']['verdict'] if R.exp('ingestion_hypothesis') is None else None)
        return '; '.join(notes + ['ingestion test skipped'])
    e = e.copy()
    e['zone'] = zone_of(e.dev, dz)
    e['period'] = e.day.map(lambda x: dst_period(x))
    ing = parse_ts(e.ingest)
    e['delta_local_h'] = (ing - parse_ts(e.time_local)).dt.total_seconds() / 3600
    e['delta_utc_h'] = (ing - parse_ts(e.time_utc)).dt.total_seconds() / 3600
    R.fact('7', 'ingest_sample_rows', len(e))
    R.fact('7', 'ingest_distinct_share', round(e.ingest.nunique() / max(1, len(e)), 4))
    rows = []
    for (z, p), g in e.groupby(['zone', 'period']):
        x = g.delta_local_h.dropna()
        if not len(x):
            continue
        q = x.quantile([0.01, 0.05, 0.10, 0.5, 0.9]).values
        rows.append({'zone': z, 'period': p, 'n': len(x), 'p01_h': round(q[0], 3), 'p05_h': round(q[1], 3),
                     'p10_h': round(q[2], 3), 'p50_h': round(q[3], 3), 'p90_h': round(q[4], 3),
                     'mode_rounded_h': float(x.round().mode().iloc[0]), 'share_negative': round((x < 0).mean(), 4)})
    off = pd.DataFrame(rows)
    R.save(off, 'ingestion_offsets')
    R.save(e.groupby(['zone', 'period', e.delta_local_h.round()]).size().reset_index(name='rows')
           .rename(columns={'delta_local_h': 'delta_rounded_h'}), 'ingestion_offset_hist')
    tol = float(R.cfg['shift_tolerance_h'])
    min_n = 30
    good_rows = off[(off.n >= min_n) & off.zone.isin(ZONE_OFFSETS) & (off.zone != 'Newfoundland')] \
        if len(off) else off
    p05 = {(r.zone, r.period): float(r.p05_h) for r in good_rows.itertuples()}
    cross = {(z, p): v - p05[('Eastern', p)] for (z, p), v in p05.items()
             if z != 'Eastern' and ('Eastern', p) in p05}
    within = {z: p05[(z, 'Standard')] - p05[(z, 'DST')] for z in {z for z, _ in p05}
              if (z, 'Standard') in p05 and (z, 'DST') in p05}
    # Within-zone (Standard - DST) differences also contain the ingestion clock's own DST change, so they are
    # scored only when the ingestion clock is evidently UTC (name or value suffix), or CONFIG says so.
    is_utc = R.cfg.get('ingest_clock_is_utc')
    if is_utc is None:
        name = R.state['cols']['events'].get('ingest') or ''
        vals = e.ingest.dropna().astype(str).head(1000)
        is_utc = bool(re.search(r'utc|gmt', name, re.I)) or bool(len(vals)) and bool(
            vals.str.contains(r'(?:Z|[+-]00:?00)$', regex=True).mean() > 0.99)
    R.fact('7', 'ingest_clock_treated_as_utc', bool(is_utc))
    verdict, trows = {}, []
    for h, (_, rec, _) in HYPOTHESES.items():
        n = ok = 0

        def delta(z, p, rec=rec):
            # ingest - recorded = (UTC + latency + c) - (local + rec), local = UTC + offset
            return -_off(z, p) - rec(z, p)

        tests = [('zone vs Eastern', z, p, s, delta(z, p) - delta('Eastern', p)) for (z, p), s in cross.items()]
        if is_utc:
            tests += [('Standard vs DST (same zone)', z, 'Std-DST', s, delta(z, 'Standard') - delta(z, 'DST'))
                      for z, s in within.items()]
        for test, z, p, s, pred in tests:
            good = abs(s - pred) <= tol
            trows.append({'hypothesis': h, 'test': test, 'zone': z, 'period': p, 'observed_h': round(s, 2),
                          'predicted_h': pred, 'match': good})
            n += 1
            ok += good
        verdict[h] = {'comparisons': n, 'matches': ok, 'consistent': n > 0 and ok == n}
    R.save(pd.DataFrame(trows), 'ingestion_hypotheses')
    consistent = [h for h, v in verdict.items() if v['consistent']]
    R.log('  ingestion offsets (ingest - transaction_time_local), hours:\n' + off.to_string(index=False))
    R.decisions['ingestion_offsets'] = {
        'verdict': (consistent[0] if len(consistent) == 1 else
                    'inconclusive: no hypothesis fits every zone' if not consistent else
                    'ambiguous: ' + ', '.join(consistent)),
        'consistent_hypotheses': consistent, 'scores': verdict,
        'zone_p05_minus_eastern_h': {f'{z}|{p}': round(s, 2) for (z, p), s in cross.items()},
        'standard_minus_dst_p05_h': {z: round(s, 2) for z, s in within.items()},
        'ingest_clock_treated_as_utc': bool(is_utc),
        'rule': ('Sample rowid % {0} = 0. The lower envelope (p05) of ingestion minus transaction_time_local is '
                 'the clock offset plus the minimum upload delay. If the transaction times are machine-local, the '
                 'envelope differs by zone like the UTC offsets (Pacific - Eastern = +3 h). If they are UTC, it is '
                 'the same in every zone. Cross-zone differences cancel the ingestion clock\'s own zone. When the '
                 'ingestion clock is UTC, the within-zone Standard - DST difference is also scored (+1 h for a '
                 'DST-observing local clock, 0 for UTC or local standard time). Zones need >= {1} sampled rows.'
                 ).format(R.cfg['sample_modulus'], min_n)}
    hyp_check(R, '7', 'ingestion offsets', 'ingestion_offsets', 'ingestion_hypothesis')
    return '; '.join(notes + [R.decisions['ingestion_offsets']['verdict']])


def dst_period(day):
    if not isinstance(day, str):
        return 'Unknown'
    y = int(day[:4])
    a, b = us_dst_bounds(y)
    return 'DST' if a.isoformat() <= day[:10] < b.isoformat() else 'Standard'


# ==============================================================================================================
# Step 8: final decision and summary
# ==============================================================================================================
def step8_summary(R):
    sets = []
    for k in ('clock_profiles_local', 'dst_transition', 'ingestion_offsets'):
        v = R.decisions.get(k)
        if isinstance(v, dict) and 'consistent_hypotheses' in v:
            sets.append((k, set(v['consistent_hypotheses'])))
    if sets:
        inter = set.intersection(*[s for _, s in sets])
        verdict = (sorted(inter)[0] if len(inter) == 1 else
                   'conflicting: the tests support different hypotheses' if not inter else
                   'ambiguous: ' + ', '.join(sorted(inter)))
        expl = HYPOTHESES[verdict][0] if verdict in HYPOTHESES else ''
        R.decisions['clock_verdict'] = {
            'verdict': verdict + (f' ({expl})' if expl else ''), 'hypothesis': verdict,
            'consistent_hypotheses': sorted(inter), 'tests_used': [k for k, _ in sets],
            'rule': 'intersection of the hypotheses consistent with every test that ran'}
        R.check('8', 'combined clock verdict (intersection of all clock tests)', R.exp('clock_hypothesis'), verdict)
    if R.state.get('db_stat'):
        st = R.db_path.resolve().stat()
        R.check('8', 'database file unchanged (size, mtime)', True,
                (st.st_size, st.st_mtime_ns) == tuple(R.state['db_stat']))
    adb = R.state.get('adb')
    if adb is not None and R.opts.get('save_sqlite', True):
        target = R.private / 'db_analysis.sqlite'
        if target.exists():
            target.unlink()
        dst = sqlite3.connect(target)
        adb.backup(dst)
        b = R.state.get('scan', {}).get('B_hours') if R.state.get('scan') else None
        if b is not None:
            inv = R.state['devidx'].decode_map()
            serialmap = R.state['maps']['serial']
            hb = b.assign(machine_id=b.dev.map(inv).map(lambda x: serialmap.get(x))).drop(columns='dev')
            hb.to_sql('telemetry_month_hour', dst, index=False, if_exists='replace')
        dst.commit()
        dst.close()
        R.outputs['private'].append(target.name)
    return R.decisions.get('clock_verdict', {}).get('verdict', 'no clock tests ran')


# ==============================================================================================================
# Entry points
# ==============================================================================================================
def run(db_path, xlsx_path=None, out_dir=None, private_dir=None, skip_scans=False, sha256=False,
        expected_json=None, no_chunk=False, chunk_rows=None, cache_mb=None, mmap_gb=0, config=None):
    """Run every step; returns the summary dict. Colab: run(SRC, XLS, 'db_out', 'db_private')."""
    xlsx_path = xlsx_path or common.XLS
    out_dir = out_dir or (common.OUTPUTS / 'db')
    private_dir = private_dir or (common.PRIVATE / 'db')
    R = Run(db_path, xlsx_path, out_dir, private_dir,
            {'skip_scans': skip_scans, 'sha256': sha256, 'expected_json': expected_json, 'no_chunk': no_chunk,
             'chunk_rows': chunk_rows, 'cache_mb': cache_mb, 'mmap_gb': mmap_gb, 'config': config})
    R.log(f'verify_with_db: db={R.db_path.name} xlsx={R.xlsx_path.name} out={R.out} private={R.private}')
    R.step('0', 'schema, indexes, formats, counts', step0_schema)
    R.step('1', 'device dictionary', step1_devices)
    R.step('2', 'ticket-device linkage', step2_linkage)
    R.step('3', 'model/type map, mapping summary, host-level audit', step3_mapping)
    R.step('pass', 'single pass over transaction_events (feeds 4-7)', step_pass)
    R.step('4', "Zac's aggregation, reconciliation and rate tables", step4_zac_tables)
    R.step('4b', '30-ticket pilot reproduction', step4b_pilot)
    R.step('5', 'clock test: hour profiles by zone x DST period', step5_clock_profiles)
    R.step('6', 'clock test: DST transition days', step6_dst_transition)
    R.step('7', 'differing clock rows and ingestion offsets', step7_offsets)
    R.step('8', 'decision and summary', step8_summary)
    if R.state.get('conn') is not None:
        R.state['conn'].close()
    summary = R.write_summary()
    R.log(f"done: checks {summary['check_counts']}; clock verdict: "
          f"{R.decisions.get('clock_verdict', {}).get('verdict', 'n/a')}")
    R.log(f'summary: {R.out / "db_summary.md"}')
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True)
    ap.add_argument('--xlsx', default=str(common.XLS))
    ap.add_argument('--out', default=str(common.OUTPUTS / 'db'))
    ap.add_argument('--private', default=str(common.PRIVATE / 'db'))
    ap.add_argument('--skip-scans', action='store_true', help='skip the full pass over transaction_events')
    ap.add_argument('--sha256', action='store_true', help="hash the DB and compare with Zac's checksum")
    ap.add_argument('--expected-json', help='override expected values (e.g. fixture_truth.json)')
    ap.add_argument('--no-chunk', action='store_true', help='one full-scan statement per query instead of chunks')
    ap.add_argument('--chunk-rows', type=int)
    ap.add_argument('--cache-mb', type=int)
    ap.add_argument('--mmap-gb', type=float, default=0)
    a = ap.parse_args(argv)
    s = run(a.db, a.xlsx, a.out, a.private, a.skip_scans, a.sha256, a.expected_json, a.no_chunk, a.chunk_rows,
            a.cache_mb, a.mmap_gb)
    bad = s['check_counts'].get('FAIL', 0) + sum(v.get('status') == 'ERROR' for v in s['steps'].values())
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
