"""Verbatim copies from verification/followups.py. Do not edit by hand: regenerate with
trends/tests/sync_definitions.py --write (MIT side) and check with trends/tests/test_parity.py.
"""
import csv
import hashlib
import io

import numpy as np
import pandas as pd


REF_HASH = '88b71f3ce487a0f9d6d2aada2e29f24e54f198ae141498ffcba278a8cca85080'

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

INSTALL_COHORTS = [(2016, 2018), (2019, 2021), (2022, 2023), (2024, 2026)]   # §12 item 7: descriptive, added after

def request_types_hash(path):
    rows = sorted(csv.DictReader(open(path, newline='', encoding='utf-8')),
                  key=lambda x: (x['trouble_code'], x['category']))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['trouble_code', 'category', 'group'])
    for x in rows:
        w.writerow([x['trouble_code'], x['category'], x['group']])
    return hashlib.sha256(buf.getvalue().encode('utf-8')).hexdigest()

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
