"""Hospital location -> time zone, shared by timestamp_semantics.py and case_order.py.

A ticket's hospital is located from the case export's 'Hospital City, State, Zip'. The state or province gives the
IANA zone; for the states that span two zones, public 3-digit ZIP prefixes pick the zone. Outputs show only the state
and the resulting zone.
"""
import re

import pandas as pd

STATE_TZ = {
    **{s: 'America/New_York' for s in 'CT DC DE FL GA MA MD ME NC NH NJ NY OH PA RI SC VA VT WV KY'.split()},
    'MI': 'America/Detroit', 'IN': 'America/Indiana/Indianapolis',
    **{s: 'America/Chicago' for s in 'AL AR IA IL KS LA MN MO MS ND NE OK SD TN TX WI'.split()},
    **{s: 'America/Denver' for s in 'CO MT NM UT WY'.split()}, 'ID': 'America/Boise',
    'AZ': 'America/Phoenix',
    **{s: 'America/Los_Angeles' for s in 'CA NV OR WA'.split()},
    'AK': 'America/Anchorage', 'HI': 'Pacific/Honolulu',
    # Canada
    'ON': 'America/Toronto', 'QC': 'America/Toronto', 'NL': 'America/St_Johns', 'NFLD': 'America/St_Johns',
    'NS': 'America/Halifax', 'NB': 'America/Moncton', 'PE': 'America/Halifax', 'MB': 'America/Winnipeg',
    'SK': 'America/Regina', 'AB': 'America/Edmonton', 'BC': 'America/Vancouver',
}
# Split states: (state, 3-digit ZIP prefixes, zone, note). Only prefixes whose zone differs from the state default.
ZIP_RULES = [   # public time-zone geography by 3-digit ZIP prefix; outputs show only state + resulting zone
    ('TX', ('798', '799', '885'), 'America/Denver'),
    ('FL', ('324', '325'), 'America/Chicago'),
    ('IN', ('463', '464', '476', '477'), 'America/Chicago'),
    ('TN', ('373', '374', '376', '377', '378', '379'), 'America/New_York'),
    ('KY', ('420', '421', '422', '423', '424'), 'America/Chicago'),
    ('NE', ('690', '691', '692', '693'), 'America/Denver'),
    ('OR', ('979',), 'America/Boise'),
    ('ID', ('835', '836', '837', '838'), 'America/Los_Angeles'),
]
GROUP = {'America/New_York': 'Eastern', 'America/Detroit': 'Eastern', 'America/Indiana/Indianapolis': 'Eastern',
         'America/Toronto': 'Eastern', 'America/Chicago': 'Central', 'America/Winnipeg': 'Central',
         'America/Denver': 'Mountain', 'America/Boise': 'Mountain', 'America/Edmonton': 'Mountain',
         'America/Phoenix': 'Arizona (no DST)', 'America/Regina': 'Saskatchewan (no DST)',
         'America/Los_Angeles': 'Pacific', 'America/Vancouver': 'Pacific', 'America/Anchorage': 'Alaska',
         'Pacific/Honolulu': 'Hawaii (no DST)', 'America/St_Johns': 'Newfoundland',
         'America/Halifax': 'Atlantic', 'America/Moncton': 'Atlantic'}
ZONE_ORDER = ['Newfoundland', 'Atlantic', 'Eastern', 'Central', 'Mountain', 'Arizona (no DST)', 'Pacific',
              'Alaska', 'Hawaii (no DST)', 'Unparsed']

LOC_RE = re.compile(r'^(?P<city>.*),\s*(?P<st>[A-Za-z]{2,})\s+(?P<zip>\S.*)$')
COUNTRY = {'USA': 'US', 'United States': 'US', 'Canada': 'CA', 'CANADA': 'CA'}


def locate(location, country):
    m = LOC_RE.match((location or '').strip())
    if not m:
        return pd.Series({'state': None, 'zip3': None, 'iana': None, 'zip_rule': 'unparsed'})
    st, zp = m.group('st').upper(), m.group('zip').strip()
    zip3 = zp[:3] if re.match(r'^\d{5}', zp) else ('0' + zp)[:3] if re.fullmatch(r'\d{4}', zp) else zp[:3].upper()
    tz, rule = STATE_TZ.get(st), 'state default'
    for rst, prefixes, rtz in ZIP_RULES:
        if st == rst and zip3 in prefixes:
            tz, rule = rtz, f'{st} split-zone ZIP3 rule -> {GROUP[rtz]}'
    if re.fullmatch(r'\d{4}', zp):
        rule += ' (4-digit ZIP, leading zero dropped)'
    return pd.Series({'state': st, 'zip3': zip3, 'iana': tz, 'zip_rule': rule if tz else 'state not mapped'})
