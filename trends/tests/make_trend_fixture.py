#!/usr/bin/env python3
"""Deterministic synthetic IPA exports with planted trend effects, for testing the trends/ notebook.

Everything written here is FAKE: account names, addresses, cities, zip codes, phones, serials, case numbers, case
owners and every text field are invented (accounts 'Fake ... NNN', cities 'TestvilleNNN', addresses 'NNN Fake
Street', phones '555-01NN', serials 'FT9' + 6 digits, case numbers '9' + 7 digits). The zip codes are the
synthetic ones of verification/tests/make_fixture.py, which were checked not to equal any real customer's. The
files mimic the real exports exactly (sheet names, the 19 case-export headers and the 22 equipment-list headers in
their real order, Excel datetimes on the US Eastern wall clock), so the reader, the checks and the rate code can be
tested end to end without the private data. Only numpy, pandas, openpyxl and the standard library are used, and
the trends/ folder needs nothing from verification/: the header lists, the request-type weights and TEMPLATE_RE
are copied here as literals.

Usage
  python -I trends/tests/make_trend_fixture.py --out DIR [--seed 7] [--null] [--variant NAME] [--snapshots N]
                                               [--scale 1.0] [--split-from YYYY-MM-DD]
  truth = build(out, seed=7, null=False, variant=None, snapshots=1, scale=1.0)    # from a test (returns truth)
  (split_from='YYYY-MM-DD' moves the category_split date; the default is 2026-07-01)

The same arguments always give the same data and the same file bytes (fixed workbook created/modified properties
and zip timestamps). Random draws come from separate streams, so --null changes only the planted tickets: the
other tickets (all but their case numbers), the fleet and the extras are identical with and without it, and
--snapshots changes only which equipment files are written (and so the population of the expected counts).
build() refuses to write into a folder holding IPA_*.xlsx files that it did not write (it never overwrites a real
export); its own earlier files there are replaced.

Files written to DIR
  IPA_CaseHistory_2026-11-15.xlsx    sheet 'ipa_repair cases': the 19 headers in row 1, one row per case sorted by
                                     opening time, plus a small 'Summary' sheet. Workbook created/modified =
                                     2026-11-15 06:00, the export time. 'Date/Time Opened' and 'Trouble Closed
                                     Date/Time' are Excel datetimes (naive, US Eastern wall clock; closed is empty
                                     while a case is open).
  IPA_Active_Equipment_list_2026-11-14.xlsx
                                     sheet 'Equipment list - Monthly Report' with the 22 headers. With --snapshots N
                                     (N >= 2), N monthly snapshots dated the 14th of each month up to 2026-11-14;
                                     each lists the machines installed by its date and not yet removed by it.
                                     'Install Date', 'Go Live Date', 'Last PM date' and 'Current SC Expiration' are
                                     datetimes.
  truth.json                         the planted answers (see below).

Fleet (scale 1.0; --scale multiplies accounts and machines)
  150 accounts ('Fake Memorial Hospital 017', 'Fake Regional Medical Center 042', 'Fake Community Clinic 101',
  'Fake Surgery Center 133'; the largest are hospitals) of very uneven size (lognormal: a handful with 100+
  machines, many with 5-20) holding 4,800 listed machines. Models (family): LVD-Remote-2.0, MV-2.0, LVRR-WP,
  SV-48-2.0 (scrubEx, 41%); alEx LC-D, alEx MC-S (alEx, 47%); scrubBank 240 (12%); and scrubBank 120, a tiny model
  with 5 machines installed 2025-07..2026-01 (under 100 machine-months in any window: it must be pooled). The fleet
  is larger than ~4,000 and alEx-heavy so that the planted alEx fall has at least 30 tickets expected without the
  effect in 2026 Q3 (at the fleet's Computer Board rate an expected count of 30 *with* a x0.4 effect needs about
  4,500 alEx machines: --scale 2.1 or more). Install dates 2010-01-01..2026-11-10, weighted toward 2018-2025
  (2022-23 heaviest); 1% of listed machines have a blank Install Date; Go Live Date = install + 0-60 days (blank for
  10%, and while still in the future). Service Status follows age (Under Warranty when under 2 years old; Service
  Contract, No Coverage, Not Serviceable after). Service Plan 'Ricoh' or 'Bell and Howell', except ONE account of 60
  machines all on 'Vogeltronix' (third party: the notebook excludes it), whose ticket rate is x0.02. A few accounts
  are in Canada. Removed machines: 374 extra machines (7.8%) removed on a uniform random day inside the window, rate
  x1.5 (x2 with variant removed_2x), with no ticket on or after the removal day; about two thirds have a ticket, so
  ~5% of the listed count (~240) appear in the case export as serials missing from the newest list. They are on the
  older snapshots dated before their removal. About 0.5% of the tickets are on 19 serials that are on no snapshot
  at all.

Tickets (window 2024-01-01..2026-11-14 inclusive, Eastern)
  Unplanned tickets: per machine and day, Poisson with intensity
      base x age x account frailty x month shock x day factor x rate multiplier x issue weight x planted effect,
  from max(window start, install date) to min(removal, window end). age = 1.5 while the machine is under 4 years
  (1,461 days) old; frailty ~ Gamma(shape 3, mean 1) per account; month shock ~ lognormal(0, 0.05) per calendar
  month; day factor 0.3 on weekends and US federal holidays (pandas USFederalHolidayCalendar), else 1; rate
  multiplier 1 (listed), 1.5 (removed), 0.02 (Vogeltronix). `base` is set so that, without the planted effects,
  listed non-Vogeltronix machines average 6 unplanned tickets per 100 machine-months (machine-month = 30.4375
  days); with them the fleet runs at about 6.3. The issue (Trouble Code, Category) is drawn with the real
  unplanned-ticket counts of request_types_v0.csv (REQUEST_TYPES below; '[blank]' = an empty cell). Opened
  06:00-20:59, mostly business hours, whole minutes. The age step is a real (unplanted) change: a cohort crossing
  its 4th anniversary loses a third of its rate, so 2022 installs run about 15% lower in 2026 Q3 than in the four
  quarters before, on every issue (fleet-wide the ages balance: about +0.5%).
  Other rows (about 6% of all rows): Cancelled Request (Miscellaneous; rate 3.2% of the unplanned intensity),
  Duplicate Case (Miscellaneous; 0.6% of unplanned tickets get a copy opened 5-180 minutes later), Preventative
  Maintenance (Category Annual / Paid PM / blank; 1.6%, business days), and for 7% of machines installed inside the
  window one Installation ticket or Install Case 0-14 days after install (30% of Install Cases carry a repair code,
  which must still count as planned work).
  Field realism: Case Record Type 'General Case' ('alEx Case' for alEx, 'Install Case' for installs); Status
  'Trouble Closed' (88%), 'Closed', 'Case Closed', 'Ricoh-Closed'; 2% of tickets name another account; 0.3% of
  serials carry stray spaces; Sub Category blank for 31%; 2% of unplanned tickets are monitoring tickets whose
  Trouble Reported starts 'Monitoring - Daily ...' or 'Monitor weekly poll ...' (TEMPLATE_RE) and keep their
  normal Trouble Code / Category (the notebook files them under 'Monitoring').
  Data quality: in Jan-Feb 2024, 15% of unplanned tickets have a blank Category (Trouble Code kept); opened
  2026-10-26..2026-11-14, 40% of all rows are still open (Status 'Dispatch', blank Trouble Code, Category, Sub
  Category and closed time); 5 tickets carry the unmapped combination Network / Connectivity (not in v0); 3
  tickets on listed machines are dated 5-40 days before the machine's install date.

Planted effects (--null plants none of them; variant features still apply)
  1. touchscreen_install_cohort: Electronics / Touchscreen x3 for machines installed in calendar 2022 or 2023,
     throughout the window (a cohort difference, not a change).
  2. deposit_door_rise: Electro/Mechanical / Deposit Door x2 fleet-wide for tickets opened 2026-07-01..2026-09-30
     (the last complete quarter at the 2026-11-15 export).
  3. alex_computer_board_fall: Electronics / Computer Board x0.4 for family alEx, opened 2026-07-01..2026-09-30.
  Rises and the cohort effect are extra Poisson tickets on top of the null process; the fall thins the null
  process's alEx Computer Board tickets (each kept with probability 0.4). Each planted cell has >= 30 tickets
  expected in 2026 Q3 under the larger of its two hypotheses (with the effect for rises, without it for the fall).

Variants (--variant NAME; each changes only what it says)
  title_rows           Salesforce 'formatted' export: 3 title rows ('IPA Case History', 'Fake Report Owner',
                       'As of 11/15/2026') above the header (header in row 4), then a blank row, 'Generated By: Fake
                       User' and 'Confidential Information - Do Not Distribute' after the data.
  sheet_name           the case sheet is named 'Report 1' (and there is no Summary sheet).
  header_alias         the header 'Trouble Code Category' is written 'Trouble Code Cat.'.
  category_split       from 2026-07-01 (or --split-from) 'Deposit Door' is written 'Deposit Door - Latch' or
                       'Deposit Door - Sensor' (50/50), an IPA taxonomy change.
  trouble_code_rename  from 2026-07-01 'Preventative Maintenance' is written 'Preventive Maintenance' (planned work
                       would leak into unplanned).
  duplicate_case       one Case Number appears twice with different contents (Status, Category, Sub Category,
                       closed time and resolution differ); the copy follows the original row.
  text_dates           'Date/Time Opened' is text 'MM/DD/YYYY HH:MM AM/PM' on every row.
  mixed_dates          'Date/Time Opened' is text, about half the rows 'DD/MM/YYYY HH:MM' and half 'MM/DD/YYYY HH:MM'
                       (not reliably readable: the reader should refuse).
  central_clock        every opened and closed time is shifted -1 hour (exported by a US Central user).
  closed_only          rows with Status 'Dispatch' are dropped (a report filtered to closed cases).
  quarter_end_filter   only tickets opened up to 2026-09-30 are written and the export is dated 2026-10-15 (file
                       name and created property); closed times after the export are pulled back before it.
  baseline_spike       Computer Board x3 fleet-wide during October 2025 only (a one-month spike in the baseline).
  removed_2x           removed machines have twice the listed rate instead of 1.5x (run with --snapshots 1 to test
                       survivorship).
  blank_install        20% of listed machines have a blank Install Date (Go Live Date kept).
  blank_list_fields    3 listed machines with a blank Account Name, 3 with a blank Model, 3 with a blank Product
                       Family, and 2 rows with a blank Serial Number (their tickets then match no listed machine).

truth.json
  seed, null, variant, scale, window [first, last day], extract_date, snapshots [dates], case_file,
  equipment_files, counts {case_rows, unplanned, planned, cancelled, duplicate, monitoring, listed_machines_newest,
  removed_serials, third_party_machines, missing_install_dates, open_tickets, unmapped_tickets,
  unlisted_never_listed_tickets, tickets_before_install, plus removed_machines_generated, removed_serial_tickets,
  third_party_tickets, population_machines, population_machine_months, population_unplanned,
  fleet_rate_per_100_observed, fleet_rate_per_100_expected}, planted [{name, issue_level 'category', issue, group,
  trouble_code, scope, period [start, end_exclusive] or null, multiplier, expected_in_2026Q3,
  expected_without_effect_in_2026Q3, exposure_months_2026Q3, machines, fleet_expected_in_2026Q3,
  fleet_expected_without_effect_in_2026Q3 (the same Category over the whole population), expected_in_2026Q3_by_
  install_year (cohort cell), expected_by_month, expected_without_effect_by_month, exposure_months_by_month (calendar
  months, so any period length can be summed)}] (empty with --null, which adds null_expectations for the same cells
  instead), fake_strings {accounts, cities, serials_sample (first 50 on the newest list), case_numbers_sample (first
  50 rows)}, headers_case, headers_equipment, population, variant_info, base_rate_per_machine_day, monitoring_share,
  generator.
  counts are rows of the files as written, classified with the notebook's definitions (CASE_VIEWS: planned work =
  Trouble Code Preventative Maintenance or Installation, or Case Record Type Install Case; then Cancelled Request,
  Duplicate Case; the rest unplanned) on canonical labels, i.e. with a variant's relabelling undone (variant_info
  gives what the variant changed); removed_serials counts the removed machines' serials that appear in the case
  export (removed_machines_generated counts them all). Expected counts are sums of intensities over the population
  (machines on any written snapshot, non-blank serial, not Vogeltronix, non-blank install date; cell membership by the
  listed install year / family), counting what the notebook should see as that Category: monitoring tickets (2%) are
  left out, and in the by-month series the Jan-Feb 2024 blank Categories and the late open tickets are left out too
  (in 2026 Q3 neither applies). Exposure: days from max(period start, install) to min(period end, removal) /
  30.4375.
"""
import argparse
import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from openpyxl.writer.excel import ExcelWriter
from pandas.tseries.holiday import USFederalHolidayCalendar

# ------------------------------------------------------------------------------------------------ real schemas
# The 19 case-export headers and the 22 equipment-list headers, in the real order (verification/tests/make_fixture.py).
HEADERS = ['Date/Time Opened', 'Account Name', 'Hospital City, State, Zip', 'Shipping Country', 'Case Number',
           'Status', 'Dispatch #', 'Serial #', 'Model #', 'Product Name', 'Case Record Type', 'Case Owner',
           'Trouble Reported', 'Administrative Notes', 'Trouble Code', 'Trouble Code Category',
           'Trouble Code Sub Category', 'Trouble Resolution', 'Trouble Closed Date/Time']
EQUIP_HEADERS = ['Serial Number', 'Service Status', 'Account Name', 'Hospital Address', 'Hospital City',
                 'Hospital State', 'Hospital Zip Code', 'Shipping Country', 'Phone', 'Product Family', 'Model',
                 'Manufacturing Date Code', 'Poll Position', 'Location', 'Last PM date', 'Equipment Ownership',
                 'Vendor Credentialing', 'Vendor Credentialing Notes', 'Service Plan', 'Current SC Expiration',
                 'Install Date', 'Go Live Date']
CASE_SHEET = 'ipa_repair cases'
EQUIP_SHEET = 'Equipment list - Monthly Report'
# Monitoring-template tickets (verification/flags.py TEMPLATE_RE, verbatim).
TEMPLATE_RE = re.compile(
    r'^\W*(?:14\s*-?\s*days?\s+)?monitor(?:ing)?\b[^.;\n]{0,40}?\b(?:daily|weekly|poll(?:ing)?)\b', re.I)
PLANNED_CODES = ('Preventative Maintenance', 'Installation')
BLANK = '[blank]'
# (Trouble Code, Category, group, unplanned tickets) from verification/reference/request_types_v0.csv
# (v0, 2026-10-29); None is a blank cell ('[blank]' in the file). The counts are the issue-mix weights.
REQUEST_TYPES = [
    ('Electro/Mechanical', 'Deposit Door', 'Door', 1124), ('Electro/Mechanical', 'Main Door', 'Door', 568),
    ('Electro/Mechanical', 'User Door', 'Door', 515), ('Electro/Mechanical', 'Service Door', 'Door', 73),
    ('Electro/Mechanical', 'SAM', 'Mechanical', 588), ('Electro/Mechanical', 'Curtain', 'Mechanical', 510),
    ('Electro/Mechanical', 'Packer', 'Mechanical', 227),
    ('Electro/Mechanical', 'Counterweight System', 'Mechanical', 112),
    ('Electro/Mechanical', 'Drawers', 'Mechanical', 16), ('Electronics', 'Computer Board', 'Electronics', 679),
    ('Electronics', 'Touchscreen', 'Electronics', 562), ('Electronics', 'Power Supply', 'Electronics', 200),
    ('Electronics', 'Badge Reader', 'Electronics', 113), ('Electronics', 'Loader Board', 'Electronics', 47),
    ('Electronics', 'Camera', 'Electronics', 40), ('Electronics', 'Decoder', 'Electronics', 18),
    ('Electronics', 'Weight Scale', 'Electronics', 17), ('Electronics', None, 'Electronics', 7),
    ('Network', 'Network Settings', 'Network', 151), ('Network', 'Network Intermittent', 'Network', 114),
    ('Network', 'Dead Data Jack', 'Network', 64), ('Network', 'IP/Reprogramming', 'Network', 64),
    ('Network', 'Cable disconnected/Loose', 'Network', 51), ('Network', 'Firewall', 'Network', 30),
    ('Network', None, 'Network', 8), ('Network', 'Security Updates', 'Network', 1),
    ('Software', 'Issue', 'Software', 42), ('Software', 'User Access', 'Software', 26),
    ('Software', 'Credit Issues', 'Software', 13), ('Software', 'Training', 'Software', 7),
    ('Software', None, 'Software', 2), ('Software', 'Vendex Issues', 'Software', 1),
    ('Operator Error', 'Loading Error', 'Operator error', 116),
    ('Operator Error', 'Improper Use', 'Operator error', 41), ('Operator Error', None, 'Operator error', 1),
    ('Miscellaneous', 'Power', 'Other', 96), ('Miscellaneous', 'Parts Order', 'Other', 29),
    ('Miscellaneous', 'Physical Damage', 'Other', 22), ('Miscellaneous', 'Device Not Found', 'Other', 5),
    ('Canopy', 'Troubleshooting', 'Other', 2), ('Miscellaneous', 'No Trouble Found', 'No Trouble Found', 577),
    ('Miscellaneous', None, 'Not categorised', 190), (None, None, 'Not categorised', 101),
    ('Electro/Mechanical', None, 'Not categorised', 12), ('Repair/Investigate', None, 'Not categorised', 4)]
TC = np.array([r[0] for r in REQUEST_TYPES], dtype=object)
CAT = np.array([r[1] for r in REQUEST_TYPES], dtype=object)
W = np.array([r[3] for r in REQUEST_TYPES], dtype=float)
W /= W.sum()
N_ISSUES = len(REQUEST_TYPES)
V0_PAIRS = {(r[0] or BLANK, r[1] or BLANK) for r in REQUEST_TYPES}
ISSUE = {r[1]: i for i, r in enumerate(REQUEST_TYPES) if r[1] is not None}
I_TS, I_DD, I_CB = ISSUE['Touchscreen'], ISSUE['Deposit Door'], ISSUE['Computer Board']
NON_PLANTED = np.array([i for i in range(N_ISSUES) if i not in (I_TS, I_DD, I_CB) and CAT[i] is not None])

# ------------------------------------------------------------------------------------------------ calendar
WINDOW = ('2024-01-01', '2026-11-14')
DAY0 = np.datetime64(WINDOW[0], 'D')
DAYS = np.arange(DAY0, np.datetime64(WINDOW[1], 'D') + np.timedelta64(1, 'D'))
N_DAYS = len(DAYS)
NAT_D, NAT_M = np.datetime64('NaT', 'D'), np.datetime64('NaT', 'm')
MONTH_DAYS = 365.25 / 12
EXTRACT_DATE = '2026-11-15'
EXTRACT_HOUR = 6
NEWEST_SNAPSHOT = '2026-11-14'
QUARTER = ('2026-07-01', '2026-10-01')          # 2026 Q3, the last complete quarter at the export
SPIKE_MONTH = ('2025-10-01', '2025-11-01')
EARLY_BLANK = ('2024-01-01', '2024-03-01', 0.15)
OPEN_FROM, OPEN_SHARE = '2026-10-26', 0.40
SPLIT_FROM = '2026-07-01'
QUARTER_END = ('2026-10-01', '2026-10-15')      # quarter_end_filter: first day not written, export date

# ------------------------------------------------------------------------------------------------ fleet
N_LISTED, N_ACCOUNTS, N_THIRD_PARTY = 4800, 150, 60
REMOVED_SHARE = 0.078               # removed machines generated; about two thirds have a ticket (~5% of listed)
MODELS = [('LVD-Remote-2.0', 'scrubEx', 0.15), ('MV-2.0', 'scrubEx', 0.12), ('LVRR-WP', 'scrubEx', 0.08),
          ('SV-48-2.0', 'scrubEx', 0.06), ('alEx LC-D', 'alEx', 0.28), ('alEx MC-S', 'alEx', 0.19),
          ('scrubBank 240', 'scrubBank', 0.12)]
MODEL_NAMES = np.array([m for m, _, _ in MODELS] + ['scrubBank 120'])
MODEL_FAMILY = {m: f for m, f, _ in MODELS} | {'scrubBank 120': 'scrubBank'}
MODEL_P = np.array([p for _, _, p in MODELS])
MODEL_P /= MODEL_P.sum()
TINY_MODEL, TINY_N, TINY_INSTALL = 'scrubBank 120', 5, ('2025-07-01', '2026-02-01')
PRODUCT_NAME = {'scrubEx': 'scrubEx / SD Case', 'alEx': 'alEx / AD Case', 'scrubBank': 'scrubBank / SB Case'}
THIRD_PARTY_PLAN, PLANS = 'Vogeltronix', ('Ricoh', 'Bell and Howell')
INSTALL_YEARS = np.arange(2010, 2027)
INSTALL_YEAR_W = np.array([1.0, 1.2, 1.4, 1.6, 1.9, 2.2, 2.6, 3.0, 5.0, 5.5, 5.0, 5.5, 7.0, 7.0, 6.0, 6.0, 4.3])
INSTALL_YEAR_W /= INSTALL_YEAR_W.sum()
YEAR_EDGES = np.array([np.datetime64(f'{y}-01-01', 'D') for y in INSTALL_YEARS] + [np.datetime64('2026-11-11', 'D')])
# Synthetic state / zip pairs of verification/tests/make_fixture.py (checked not to be real customers' codes).
US_LOCATIONS = [('NY', '10098'), ('MA', '02198'), ('OH', '43298'), ('IL', '60698'), ('TX', '75398'),
                ('CO', '80098'), ('UT', '84198'), ('AZ', '85098'), ('CA', '94198'), ('WA', '98198')]
CANADA_LOCATION = ('ON', 'K0A 9Z9')

# ------------------------------------------------------------------------------------------------ rates
TARGET_RATE = 6 / 100                # unplanned tickets per machine-month, listed non-third-party, no effects
YOUNG_DAYS, AGE_YOUNG = 1461, 1.5    # under 4 years old
FRAILTY_SHAPE = 3.0
SHOCK_SD = 0.05
WEEKEND_HOLIDAY = 0.3
REMOVED_MULT, REMOVED_MULT_2X, THIRD_PARTY_MULT = 1.5, 2.0, 0.02
TS_MULT, DD_MULT, CB_MULT, SPIKE_MULT = 3.0, 2.0, 0.4, 3.0
COHORT_YEARS = (2022, 2023)
MONITORING_SHARE = 0.02
CANCEL_SHARE, PM_SHARE, DUPLICATE_SHARE, INSTALL_TICKET_SHARE = 0.032, 0.016, 0.006, 0.07
ACCOUNT_MISMATCH, STRAY_SPACE, SUB_BLANK = 0.02, 0.003, 0.31
NEVER_LISTED_SHARE, N_BEFORE_INSTALL, N_UNMAPPED = 0.005, 3, 5
HOURS = np.arange(6, 21)
HOUR_P = np.array([2, 5, 9, 10, 10, 9, 8, 9, 9, 8, 6, 4, 3, 2, 1], dtype=float)
HOUR_P /= HOUR_P.sum()

PLANTED = [
    {'name': 'touchscreen_install_cohort', 'issue_level': 'category', 'issue': 'Touchscreen',
     'group': 'Electronics', 'trouble_code': 'Electronics', 'scope': {'install_years': list(COHORT_YEARS)},
     'period': None, 'multiplier': TS_MULT, 'key': 'ts'},
    {'name': 'deposit_door_rise', 'issue_level': 'category', 'issue': 'Deposit Door', 'group': 'Door',
     'trouble_code': 'Electro/Mechanical', 'scope': {}, 'period': list(QUARTER), 'multiplier': DD_MULT, 'key': 'dd'},
    {'name': 'alex_computer_board_fall', 'issue_level': 'category', 'issue': 'Computer Board',
     'group': 'Electronics', 'trouble_code': 'Electronics', 'scope': {'family': 'alEx'}, 'period': list(QUARTER),
     'multiplier': CB_MULT, 'key': 'cb'}]

VARIANTS = {
    'title_rows': "3 title rows above the header and 3 footer rows after the data (Salesforce formatted export)",
    'sheet_name': "case sheet named 'Report 1', no Summary sheet",
    'header_alias': "'Trouble Code Category' written as 'Trouble Code Cat.'",
    'category_split': "from 2026-07-01 'Deposit Door' written 'Deposit Door - Latch' / 'Deposit Door - Sensor'",
    'trouble_code_rename': "from 2026-07-01 'Preventative Maintenance' written 'Preventive Maintenance'",
    'duplicate_case': "one Case Number appears twice with different contents",
    'text_dates': "'Date/Time Opened' as text 'MM/DD/YYYY HH:MM AM/PM'",
    'mixed_dates': "'Date/Time Opened' as text, half 'DD/MM/YYYY HH:MM' and half 'MM/DD/YYYY HH:MM'",
    'central_clock': "all opened/closed times shifted -1 hour (US Central exporter)",
    'closed_only': "rows with Status 'Dispatch' dropped",
    'quarter_end_filter': "only tickets opened up to 2026-09-30, export dated 2026-10-15",
    'baseline_spike': "Computer Board x3 during October 2025 only",
    'removed_2x': "removed machines at 2x the listed rate",
    'blank_install': "20% of listed machines with a blank Install Date",
    'blank_list_fields': "a few listed machines with blank Account Name / Model / Product Family, 2 blank serials",
}
STREAMS = ['fleet', 'shock', 'main', 'removed2x', 'extras', 'special', 'case', 'variant']
MARKER = 'synthetic: trends/tests/make_trend_fixture.py'

SUBCATEGORIES = {
    'Deposit Door': ['Lock Adjustment', 'Damper Replacement', 'Prox Sensor', 'Solenoid'],
    'Main Door': ['Lock Solenoid', 'T-Handle Lock Switch', 'Slot Door Adjustment'],
    'User Door': ['Closed Switch', 'Lock Switch'], 'Service Door': ['Lock', 'Door Closed Switch'],
    'SAM': ['SAM Switch', 'Home Switch', 'Rail', 'Drive'], 'Curtain': ['Replacement/Adjustment', 'Bent Rod'],
    'Packer': ['Circuit Breaker/Reset Switch', 'Arm', 'Home Switch'],
    'Counterweight System': ['Cable/Alignment', 'Weight Adjustment', 'Lower Latch'],
    'Drawers': ['Drawer Slide Replacement'], 'Computer Board': ['Replacement', 'Firmware', 'SD Card'],
    'Touchscreen': ['Reseat Connector', 'Replacement'], 'Power Supply': ['Voltage Adjustment', 'Replacement'],
    'Badge Reader': ['Connection', 'Badge Compatibility', 'Replacement'], 'Weight Scale': ['Calibration'],
    'Network Settings': ['Configuration'], 'Connectivity': ['Training'], 'Power': ['Local Power'],
    'User Access': ['User Info'], 'Loading Error': ['Loader Training', 'Linen Obstruction']}
DEFAULT_SUBCATEGORIES = ['Replacement', 'Adjustment', 'Training']
REPORT_TEXTS = ['Fake report {n:04d}: {noun} problem reported by staff',
                'Fake report {n:04d}: staff say the {noun} is not working',
                'Fake report {n:04d}: please check the {noun}',
                'Fake report {n:04d}: unit stopped, {noun} suspected']
MONITOR_TEXTS = ['Monitoring - Daily poll alert {n:04d}: fake unit flagged',
                 'Monitor weekly poll {n:04d}: fake unit offline']
RESOLUTIONS = ['Fake resolution: replaced part', 'Fake resolution: adjusted and tested', 'Fake resolution: reset unit',
               'Fake resolution: reseated cable', 'Fake resolution: updated settings',
               'Fake resolution: no fault found on site']
CLOSED_STATUSES = (('Trouble Closed', 0.88), ('Closed', 0.93), ('Case Closed', 0.97), ('Ricoh-Closed', 1.0))


# ------------------------------------------------------------------------------------------------ helpers
def _day(s):
    return int((np.datetime64(s, 'D') - DAY0).astype(np.int64))


def _days(n):
    """Integer day counts -> timedelta64[D] (numpy deprecates adding bare integers to dates)."""
    return np.asarray(n, dtype=np.int64).astype('timedelta64[D]')


def _allocate(weights, total, minimum):
    """Integer sizes proportional to `weights`, each >= minimum, summing to `total` (largest remainders)."""
    exact = weights / weights.sum() * total
    sizes = np.maximum(minimum, np.floor(exact)).astype(np.int64)
    order = np.argsort(-(exact - np.floor(exact)), kind='stable')
    i = 0
    while sizes.sum() < total:
        sizes[order[i % len(sizes)]] += 1
        i += 1
    while sizes.sum() > total:
        sizes[int(np.argmax(sizes))] -= 1
    return sizes


def _draw_install(rng, n):
    """Install dates 2010-01-01..2026-11-10 with the year weights, uniform within a year."""
    y = rng.choice(len(INSTALL_YEARS), size=n, p=INSTALL_YEAR_W)
    length = (YEAR_EDGES[y + 1] - YEAR_EDGES[y]).astype(np.int64)
    return YEAR_EDGES[y] + _days(np.floor(rng.random(n) * length))


def _py(x):
    """numpy datetime64 (or NaT) -> datetime.datetime or None, for openpyxl."""
    if x is None or np.isnat(x):
        return None
    return x.astype('datetime64[s]').item()


def _poisson_events(rng, lam):
    """(row, column) of every event of independent Poisson counts with intensities `lam` (2-d)."""
    cnt = rng.poisson(lam)
    r, c = np.nonzero(cnt)
    k = cnt[r, c]
    return np.repeat(r, k), np.repeat(c, k)


def _fields(n, rng):
    """Per-ticket random draws used to fill the text and status columns (one stream per process)."""
    return {'mod': rng.choice(HOURS, size=n, p=HOUR_P) * 60 + rng.integers(0, 60, n),
            'dur': np.clip(rng.lognormal(np.log(20 * 60), 1.1, n), 15, 45 * 1440).astype(np.int64),
            'status_u': rng.random(n), 'open_u': rng.random(n), 'blank_u': rng.random(n), 'mon_u': rng.random(n),
            'acct_u': rng.random(n), 'acct_k': rng.integers(0, 1 << 30, n), 'space_u': rng.random(n),
            'space_k': rng.integers(0, 3, n), 'disp_u': rng.random(n), 'disp_no': rng.integers(0, 10 ** 6, n),
            'owner': rng.integers(0, 3, n), 'sub_u': rng.random(n), 'sub_k': rng.integers(0, 1 << 30, n),
            'txt_n': rng.integers(0, 10 ** 4, n), 'txt_k': rng.integers(0, 1 << 30, n), 'admin_u': rng.random(n),
            'res_u': rng.random(n), 'pick_u': rng.random(n)}


def _part(mi, day, kind, tc, cat, src, fields):
    n = len(mi)

    def arr(v):
        if isinstance(v, np.ndarray):
            return v.astype(object)
        out = np.empty(n, dtype=object)
        out[:] = [v] * n
        return out
    return {'mi': np.asarray(mi, np.int64), 'day': np.asarray(day, np.int64), 'kind': arr(kind), 'tc': arr(tc),
            'cat': arr(cat), 'src': arr(src), **fields}


def _take(fields, mask):
    return {k: v[mask] for k, v in fields.items()}


def _isin(values, choices):
    """Element-wise membership for object arrays that may hold None (np.isin may sort, which fails on None)."""
    choices = set(choices)
    return np.fromiter((v in choices for v in values), dtype=bool, count=len(values))


# ------------------------------------------------------------------------------------------------ fleet
def _make_fleet(rng, scale):
    n_listed = max(150, int(round(N_LISTED * scale)))
    n_acc = max(15, int(round(N_ACCOUNTS * scale)))
    n_tp = max(6, int(round(N_THIRD_PARTY * scale)))
    n_removed = max(5, int(round(REMOVED_SHARE * n_listed)))
    n_never = max(3, int(round(n_listed / 250)))
    n_grid, width = n_listed + n_removed, max(3, len(str(n_acc)))

    # accounts
    tp = int(rng.integers(n_acc))
    others = np.array([k for k in range(n_acc) if k != tp])
    sizes = np.zeros(n_acc, np.int64)
    sizes[others] = _allocate(rng.lognormal(np.log(17.0), 1.05, len(others)), n_listed - n_tp, 3)
    sizes[tp] = n_tp
    frailty = rng.gamma(FRAILTY_SHAPE, 1 / FRAILTY_SHAPE, n_acc)
    rank = np.empty(n_acc, np.int64)
    rank[np.argsort(-sizes, kind='stable')] = np.arange(n_acc)
    kinds = [('Memorial Hospital', 'Regional Medical Center') if r < 0.4 * n_acc else
             ('Community Clinic', 'Surgery Center') for r in rank]
    canada = set(rng.choice(others, size=max(1, int(round(0.02 * n_acc))), replace=False).tolist())
    loc = rng.integers(len(US_LOCATIONS), size=n_acc)
    ricoh = rng.random(n_acc) < 0.55
    acc = {'n': n_acc, 'tp': tp, 'size': sizes, 'frailty': frailty,
           'name': [f'Fake {kinds[k][rank[k] % 2]} {k + 1:0{width}d}' for k in range(n_acc)],
           'city': [f'Testville{k + 1:0{width}d}' for k in range(n_acc)],
           'address': [f'{101 + k} Fake Street' for k in range(n_acc)],
           'state': [CANADA_LOCATION[0] if k in canada else US_LOCATIONS[loc[k]][0] for k in range(n_acc)],
           'zip': [CANADA_LOCATION[1] if k in canada else US_LOCATIONS[loc[k]][1] for k in range(n_acc)],
           'country': ['Canada' if k in canada else 'USA' for k in range(n_acc)],
           'phone': [f'555-01{(k + 1) % 100:02d}' for k in range(n_acc)]}

    # machines: listed (0..n_listed-1), removed (..n_grid-1), never listed (..n_all-1)
    acct = np.concatenate([np.repeat(np.arange(n_acc), sizes),
                           rng.choice(others, size=n_removed, p=sizes[others] / sizes[others].sum()),
                           rng.choice(others, size=n_never)])
    model = MODEL_NAMES[rng.choice(len(MODELS), size=n_grid + n_never, p=MODEL_P)]
    tiny = rng.choice(np.flatnonzero(acct[:n_listed] != tp), size=TINY_N, replace=False)
    model[tiny] = TINY_MODEL
    install = np.full(n_grid + n_never, NAT_D, dtype='datetime64[D]')
    install[:n_listed] = _draw_install(rng, n_listed)
    t0, t1 = (np.datetime64(x, 'D') for x in TINY_INSTALL)
    install[tiny] = t0 + _days(rng.integers(0, int((t1 - t0).astype(np.int64)), TINY_N))
    removal_idx = np.full(n_grid + n_never, -1, np.int64)
    removal_idx[n_listed:n_grid] = rng.integers(1, N_DAYS, n_removed)
    inst_r = _draw_install(rng, n_removed)
    limit = DAY0 + _days(removal_idx[n_listed:n_grid] - 30)
    for _ in range(200):
        bad = inst_r >= limit
        if not bad.any():
            break
        inst_r[bad] = _draw_install(rng, int(bad.sum()))
    install[n_listed:n_grid] = np.minimum(inst_r, limit - _days(1))
    numbers = rng.choice(10 ** 6, size=n_grid + n_never, replace=False)
    serial = np.array([f'FT9{x:06d}' for x in numbers])

    listed = np.zeros(n_grid + n_never, bool)
    listed[:n_listed] = True
    removed = np.zeros(n_grid + n_never, bool)
    removed[n_listed:n_grid] = True
    tpm = listed & (acct == tp)
    family = np.array([MODEL_FAMILY[m] for m in model])
    blank_install = listed & (rng.random(n_grid + n_never) < 0.01) & (model != TINY_MODEL)

    # list attributes (grid machines; constant across snapshots except Last PM date and future go-live dates)
    g = slice(0, n_grid)
    ref = np.where(removed[g], DAY0 + _days(np.maximum(removal_idx[g], 0)), np.datetime64(NEWEST_SNAPSHOT, 'D'))
    age_y = (ref - install[g]).astype(np.int64) / 365.25
    u = rng.random(n_grid)
    status = np.where(age_y < 2, np.where(u < 0.75, 'Under Warranty', 'Service Contract'),
                      np.where(age_y < 10, np.select([u < 0.68, u < 0.88], ['Service Contract', 'No Coverage'],
                                                     'Not Serviceable'),
                               np.select([u < 0.40, u < 0.65], ['Service Contract', 'No Coverage'],
                                         'Not Serviceable')))
    flip = rng.random(n_grid) < 0.10
    plan = np.where(ricoh[acct[g]] ^ flip, PLANS[0], PLANS[1]).astype(object)
    plan[tpm[g]] = THIRD_PARTY_PLAN
    go_live = install[g] + _days(rng.integers(0, 61, n_grid))
    go_live[(rng.random(n_grid) < 0.10) | blank_install[g]] = NAT_D
    sc_exp = np.where(status == 'Service Contract',
                      np.datetime64('2027-01-01', 'D') + _days(rng.integers(0, 730, n_grid)),
                      np.where(status == 'Under Warranty', install[g] + _days(730), NAT_D))
    mfg_lag = rng.integers(0, 2, n_grid)
    attrs = {'status': status.astype(object), 'plan': plan, 'go_live': go_live, 'sc_exp': sc_exp,
             'mfg': np.array([f'FAKE-{int(str(d)[:4]) - lag}' for d, lag in zip(install[g], mfg_lag)], dtype=object),
             'poll': np.array([f'{x:02d}' for x in rng.integers(1, 5, n_grid)], dtype=object),
             'location': np.array([f'Fake Pharmacy {x}' for x in rng.integers(1, 4, n_grid)], dtype=object),
             'ownership': np.where(rng.random(n_grid) < 0.7, 'Customer Owned', 'Leased').astype(object),
             'vendor': np.where(rng.random(n_grid) < 0.1, 'Required', None).astype(object),
             'vendor_notes': np.where(rng.random(n_grid) < 0.5, 'Fake note', None).astype(object),
             'pm_phase': rng.integers(0, 365, n_grid), 'pm_none': rng.random(n_grid) < 0.25}
    install_idx = np.where(np.isnat(install), 10 ** 6, (install - DAY0).astype(np.int64))
    year = np.where(np.isnat(install), 0, install.astype('datetime64[Y]').astype(np.int64) + 1970)
    mult = np.where(removed, REMOVED_MULT, np.where(tpm, THIRD_PARTY_MULT, 1.0))
    return {'n_listed': n_listed, 'n_removed': n_removed, 'n_never': n_never, 'n_grid': n_grid,
            'acct': acct, 'model': model, 'family': family, 'install': install, 'install_idx': install_idx,
            'year': year, 'removal_idx': removal_idx, 'serial': serial, 'listed': listed, 'removed': removed,
            'tp': tpm, 'blank_install': blank_install, 'mult': mult, 'cohort': np.isin(year, COHORT_YEARS),
            'alex': family == 'alEx', 'attrs': attrs}, acc


def _calendar(rng):
    idx = pd.DatetimeIndex(DAYS)
    hol = USFederalHolidayCalendar().holidays(start=WINDOW[0], end=WINDOW[1])
    off = (idx.dayofweek >= 5) | idx.isin(hol)
    month = np.asarray((idx.year - 2024) * 12 + idx.month - 1)
    n_months = int(month.max()) + 1
    shock = np.exp(rng.normal(0.0, SHOCK_SD, n_months))
    d = np.arange(N_DAYS)
    starts = np.flatnonzero(np.r_[True, np.diff(month) != 0])
    return {'dayf': np.where(np.asarray(off), WEEKEND_HOLIDAY, 1.0), 'shock': shock, 'shock_day': shock[month],
            'month': month, 'month_starts': starts,
            'month_labels': [str(DAYS[s])[:7] for s in starts],
            'q3': (d >= _day(QUARTER[0])) & (d < _day(QUARTER[1])),
            'spike': (d >= _day(SPIKE_MONTH[0])) & (d < _day(SPIKE_MONTH[1])),
            'early': d < _day(EARLY_BLANK[1]), 'late': d >= _day(OPEN_FROM)}


def _intensity(f, cal):
    """Null-model intensity per grid machine and day (all issues), the activity mask and the calibrated base."""
    n = f['n_grid']
    start = np.clip(f['install_idx'][:n], 0, N_DAYS)
    end = np.where(f['removed'][:n], f['removal_idx'][:n], N_DAYS)
    d = np.arange(N_DAYS)
    active = (d >= start[:, None]) & (d < end[:, None])
    unit = np.where(d < (f['install_idx'][:n] + YOUNG_DAYS)[:, None], AGE_YOUNG, 1.0)
    unit *= active
    unit *= (cal['shock_day'] * cal['dayf'])[None, :]
    unit *= (f['frailty_m'][:n] * f['mult'][:n])[:, None]
    calib = f['listed'][:n] & ~f['tp'][:n]
    base = TARGET_RATE * (active[calib].sum() / MONTH_DAYS) / unit[calib].sum()
    return unit * base, active, float(base)


# ------------------------------------------------------------------------------------------------ tickets
def _simulate(lam, rows, f, cal, null, spike, seq, tag):
    """Unplanned tickets (and duplicates) on grid `rows` with null intensity `lam` plus the planted effects."""
    r_base, r_ts, r_dd, r_cb, r_spike, r_dup = (np.random.default_rng(s) for s in seq.spawn(6))
    m, d = _poisson_events(r_base, lam[rows])
    m = rows[m]
    issue = r_base.choice(N_ISSUES, size=len(m), p=W)
    fb = _fields(len(m), r_base)
    cand = r_dup.random(len(m)) < DUPLICATE_SHARE      # drawn for every null ticket: same set with --null
    fd = _fields(int(cand.sum()), r_dup)
    fd['mod'] = fb['mod'][cand] + r_dup.integers(5, 181, int(cand.sum()))
    keep = np.ones(len(m), bool)
    if not null:                                        # fall: thin alEx Computer Board in 2026 Q3
        u = r_cb.random(len(m))
        keep = ~((issue == I_CB) & f['alex'][m] & cal['q3'][d]) | (u < CB_MULT)
    parts = [_part(m[keep], d[keep], 'unplanned', TC[issue[keep]], CAT[issue[keep]], tag, _take(fb, keep)),
             _part(m[cand][keep[cand]], d[cand][keep[cand]], 'duplicate', 'Miscellaneous', 'Duplicate Case',
                   tag + '_duplicate', _take(fd, keep[cand]))]
    q3 = np.flatnonzero(cal['q3'])
    if not null:
        rr = rows[f['cohort'][rows]]                   # Touchscreen x3 for 2022-23 installs (extra 2x)
        mm, dd = _poisson_events(r_ts, lam[rr] * ((TS_MULT - 1) * W[I_TS]))
        parts.append(_part(rr[mm], dd, 'unplanned', TC[I_TS], CAT[I_TS], tag + '_ts', _fields(len(mm), r_ts)))
        mm, dd = _poisson_events(r_dd, lam[np.ix_(rows, q3)] * ((DD_MULT - 1) * W[I_DD]))
        parts.append(_part(rows[mm], q3[dd], 'unplanned', TC[I_DD], CAT[I_DD], tag + '_dd', _fields(len(mm), r_dd)))
    if spike:
        sp = np.flatnonzero(cal['spike'])
        mm, dd = _poisson_events(r_spike, lam[np.ix_(rows, sp)] * ((SPIKE_MULT - 1) * W[I_CB]))
        parts.append(_part(rows[mm], sp[dd], 'unplanned', TC[I_CB], CAT[I_CB], tag + '_spike',
                           _fields(len(mm), r_spike)))
    return parts


def _extras(lam, active, f, cal, rng):
    """Cancelled requests, preventative maintenance and installation tickets (independent of the effects)."""
    n = f['n_grid']
    parts = []
    mm, dd = _poisson_events(rng, lam * CANCEL_SHARE)
    parts.append(_part(mm, dd, 'cancelled', 'Miscellaneous', 'Cancelled Request', 'cancelled',
                       _fields(len(mm), rng)))
    w = active * cal['dayf'][None, :] * (~f['tp'][:n])[:, None]
    mm, dd = _poisson_events(rng, w * (PM_SHARE * lam.sum() / w.sum()))
    fp = _fields(len(mm), rng)
    cat = np.where(fp['pick_u'] < 0.6, 'Annual', np.where(fp['pick_u'] < 0.85, 'Paid PM', None))
    parts.append(_part(mm, dd, 'pm', 'Preventative Maintenance', cat.astype(object), 'pm', fp))
    inst = f['install_idx'][:n]
    end = np.where(f['removed'][:n], f['removal_idx'][:n], N_DAYS)
    pick = (inst >= 0) & (inst < N_DAYS) & ~f['tp'][:n] & (rng.random(n) < INSTALL_TICKET_SHARE)
    idx = np.flatnonzero(pick)
    day = inst[idx] + rng.integers(0, 15, len(idx))
    ok = (day < N_DAYS) & (day < end[idx])
    idx, day = idx[ok], day[ok]
    fi = _fields(len(idx), rng)
    is_case = rng.random(len(idx)) < 0.5
    repair = rng.choice(N_ISSUES, size=len(idx), p=W)
    u = fi['pick_u']
    tc = np.where(is_case & (u >= 0.7), TC[repair], np.where(is_case & (u >= 0.4), None, 'Installation'))
    cat = np.where(is_case & (u >= 0.7), CAT[repair], None)
    parts.append(_part(idx, day, np.where(is_case, 'install_case', 'installation'), tc.astype(object),
                       cat.astype(object), 'installation', fi))
    return parts


def _specials(lam, f, cal, rng):
    """Tickets on never-listed serials, tickets before the install date, and the unmapped Network/Connectivity."""
    n = f['n_grid']
    parts = []
    k = max(f['n_never'], int(round(NEVER_LISTED_SHARE * lam.sum())))
    who = np.r_[np.arange(f['n_never']), rng.integers(0, f['n_never'], k - f['n_never'])]
    day = rng.choice(N_DAYS, size=k, p=cal['dayf'] / cal['dayf'].sum())
    issue = rng.choice(N_ISSUES, size=k, p=W)
    parts.append(_part(n + who, day, 'unplanned', TC[issue], CAT[issue], 'never_listed', _fields(k, rng)))
    inst = f['install_idx'][:n]
    ok = (f['listed'][:n] & ~f['tp'][:n] & ~f['blank_install'][:n] & (f['model'][:n] != TINY_MODEL)
          & (inst >= _day('2024-03-01')) & (inst <= _day('2026-06-30')))
    who = rng.choice(np.flatnonzero(ok), size=N_BEFORE_INSTALL, replace=False)
    issue = NON_PLANTED[rng.choice(len(NON_PLANTED), size=N_BEFORE_INSTALL, p=W[NON_PLANTED] / W[NON_PLANTED].sum())]
    parts.append(_part(who, inst[who] - rng.integers(5, 41, N_BEFORE_INSTALL), 'unplanned', TC[issue], CAT[issue],
                       'before_install', _fields(N_BEFORE_INSTALL, rng)))
    before = set(who.tolist())
    lo, hi = _day('2025-01-01'), _day('2026-09-30')
    ok = f['listed'][:n] & ~f['tp'][:n] & ~f['blank_install'][:n] & (inst <= hi - 30)
    who = rng.choice(np.flatnonzero(ok), size=N_UNMAPPED, replace=False)
    first = np.maximum(inst[who], lo)
    day = first + np.floor(rng.random(N_UNMAPPED) * (hi + 1 - first)).astype(np.int64)
    parts.append(_part(who, day, 'unplanned', 'Network', 'Connectivity', 'unmapped', _fields(N_UNMAPPED, rng)))
    return parts, before


def _canonical(parts, f, acc, cal, rng):
    """All rows in their canonical form (before any variant), sorted by opening time, with case numbers."""
    T = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    n = len(T['mi'])
    opened = DAYS[T['day']].astype('datetime64[m]') + T['mod'].astype('timedelta64[m]')
    serial = f['serial'][T['mi']]
    order = np.lexsort((np.arange(n), serial, opened.astype(np.int64)))
    T = {k: v[order] for k, v in T.items()}
    opened, serial = opened[order], serial[order]
    mi, kind, src, day = T['mi'], T['kind'], T['src'], T['day']
    unplanned = kind == 'unplanned'
    monitoring = unplanned & ~_isin(src, ['before_install', 'unmapped']) & (T['mon_u'] < MONITORING_SHARE)
    blank_cat = unplanned & cal['early'][day] & (T['blank_u'] < EARLY_BLANK[2])
    is_open = cal['late'][day] & (T['open_u'] < OPEN_SHARE)
    tc, cat = T['tc'].copy(), T['cat'].copy()
    sub = np.array([None if (c is None or k != 'unplanned' or su < SUB_BLANK) else
                    SUBCATEGORIES.get(c, DEFAULT_SUBCATEGORIES)[sk % len(SUBCATEGORIES.get(c, DEFAULT_SUBCATEGORIES))]
                    for c, k, su, sk in zip(cat, kind, T['sub_u'], T['sub_k'])], dtype=object)
    noun = [(c or t or 'machine').lower() for t, c in zip(tc, cat)]
    cat[blank_cat] = None
    sub[blank_cat] = None
    for a in (tc, cat, sub):
        a[is_open] = None
    cap = np.datetime64(f'{EXTRACT_DATE}T{EXTRACT_HOUR - 1:02d}:00', 'm')
    closed = opened + T['dur'].astype('timedelta64[m]')
    late = closed > cap
    closed[late] = opened[late] + ((cap - opened[late]).astype(np.int64) // 2).astype('timedelta64[m]')
    closed[is_open] = NAT_M
    acct = f['acct'][mi]
    other = T['acct_u'] < ACCOUNT_MISMATCH
    acct = np.where(other, (acct + 1 + T['acct_k'] % (acc['n'] - 1)) % acc['n'], acct)
    q = T['status_u']
    status = np.select([q < p for _, p in CLOSED_STATUSES], [s for s, _ in CLOSED_STATUSES], 'Ricoh-Closed')
    status = np.where(is_open, 'Dispatch', status).astype(object)
    rtype = np.where(kind == 'install_case', 'Install Case',
                     np.where(f['family'][mi] == 'alEx', 'alEx Case', 'General Case')).astype(object)
    rows = {h: np.empty(n, dtype=object) for h in HEADERS}
    for i in range(n):
        k, nn, kk = kind[i], int(T['txt_n'][i]), int(T['txt_k'][i])
        if monitoring[i]:
            text = MONITOR_TEXTS[kk % len(MONITOR_TEXTS)].format(n=nn)
        elif k == 'pm':
            text = f'Fake request {nn:04d}: scheduled preventative maintenance visit'
        elif k in ('installation', 'install_case'):
            text = f'Fake request {nn:04d}: new machine installation'
        elif k == 'duplicate':
            text = f'Fake report {nn:04d}: same problem reported again'
        else:
            text = REPORT_TEXTS[kk % len(REPORT_TEXTS)].format(n=nn, noun=noun[i])
        if k == 'cancelled':
            res = 'Fake resolution: request cancelled by customer'
        elif k == 'duplicate':
            res = 'Fake resolution: duplicate, see earlier case'
        else:
            res = RESOLUTIONS[kk % len(RESOLUTIONS)]
        if T['res_u'][i] < 0.08 or (is_open[i] and T['res_u'][i] < 0.56):
            res = None
        s = str(serial[i])
        if T['space_u'][i] < STRAY_SPACE:
            s = (' ' + s, s + ' ', ' ' + s + ' ')[T['space_k'][i]]
        a = acct[i]
        no_dispatch = k == 'install_case' or T['disp_u'][i] < (0.5 if k == 'cancelled' else 0.15)
        rows['Account Name'][i] = acc['name'][a]
        rows['Hospital City, State, Zip'][i] = f"{acc['city'][a]}, {acc['state'][a]} {acc['zip'][a]}"
        rows['Shipping Country'][i] = acc['country'][a]
        rows['Status'][i] = status[i]
        rows['Dispatch #'][i] = None if no_dispatch else f"D-{int(T['disp_no'][i]):06d}"
        rows['Serial #'][i] = s
        rows['Model #'][i] = str(f['model'][mi[i]])
        rows['Product Name'][i] = PRODUCT_NAME[str(f['family'][mi[i]])]
        rows['Case Record Type'][i] = rtype[i]
        rows['Case Owner'][i] = 'Fake Owner ' + 'ABC'[T['owner'][i]]
        rows['Trouble Reported'][i] = text
        rows['Administrative Notes'][i] = None if T['admin_u'][i] < 0.35 else f'Fake admin note {kk % 1000:03d}'
        rows['Trouble Code'][i] = tc[i]
        rows['Trouble Code Category'][i] = cat[i]
        rows['Trouble Code Sub Category'][i] = sub[i]
        rows['Trouble Resolution'][i] = res
    numbers = np.sort(rng.choice(10 ** 7, size=n, replace=False))
    rows['Case Number'] = np.array([f'9{x:07d}' for x in numbers], dtype=object)
    return {'rows': rows, 'opened': opened, 'closed': closed, 'kind': kind, 'src': src, 'mi': mi,
            'serial': serial, 'monitoring': monitoring, 'open': is_open}


def _select(C, mask):
    return {k: ({h: v[mask] for h, v in C['rows'].items()} if k == 'rows' else C[k][mask]) for k in C}


def _classify(rows):
    tc, cat, rt = rows['Trouble Code'], rows['Trouble Code Category'], rows['Case Record Type']
    planned = _isin(tc, PLANNED_CODES) | (rt == 'Install Case')
    cancelled = ~planned & (cat == 'Cancelled Request')
    duplicate = ~planned & ~cancelled & (cat == 'Duplicate Case')
    return planned, cancelled, duplicate, ~(planned | cancelled | duplicate)


# ------------------------------------------------------------------------------------------------ writing
def _check_out_dir(out):
    """Refuse to touch IPA_*.xlsx files this generator did not write; remove its own earlier ones."""
    mine = []
    for p in sorted(out.glob('IPA_CaseHistory_*.xlsx')) + sorted(out.glob('IPA_Active_Equipment_list_*.xlsx')):
        try:
            with zipfile.ZipFile(p) as z:
                ours = MARKER in z.read('docProps/core.xml').decode('utf-8', 'replace')
        except (zipfile.BadZipFile, KeyError, OSError):
            ours = False
        if not ours:
            raise FileExistsError(f'{p.name} in {out} was not written by make_trend_fixture.py: refusing to '
                                  f'overwrite it; write the fixture to an empty folder')
        mine.append(p)
    for p in mine:
        p.unlink()


def _save(wb, path, when):
    """Save with fixed created/modified properties and fixed zip timestamps (byte-identical reruns)."""
    wb.properties.created = when
    wb.properties.modified = when
    wb.properties.creator = 'Fake Report Owner'
    wb.properties.description = MARKER
    buf = io.BytesIO()
    archive = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, allowZip64=True)
    ExcelWriter(wb, archive).save()      # openpyxl's save_workbook would stamp `modified` with the current time
    stamp = (when.year, when.month, when.day, when.hour, when.minute, 0)
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zin, \
            zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zout.writestr(zi, zin.read(info.filename))


def _write_case(path, header, data, sheet, when, title=(), footer=(), summary=True):
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(sheet)
    for t in title:
        ws.append([t])
    ws.append(header)
    for r in data:
        ws.append(r)
    for t in footer:
        ws.append([t] if t is not None else [])
    if summary:
        cats = pd.Series([r[HEADERS.index('Trouble Code Category')] for r in data], dtype=object).dropna()
        sm = wb.create_sheet('Summary')
        sm.append(['Top repair issue (FAKE)', 'Cases', 'Share'])
        for c, k in cats.value_counts().head(5).items():
            sm.append([c, int(k), round(int(k) / len(data), 3)])
    _save(wb, path, when)


def _snapshot_rows(f, acc, eq, date):
    """Rows of the equipment list dated `date`: machines installed by then and not yet removed."""
    n = f['n_grid']
    S = np.datetime64(date, 'D')
    inst, a = f['install'][:n], f['attrs']
    removal = np.where(f['removed'][:n], DAY0 + _days(np.maximum(f['removal_idx'][:n], 0)),
                       np.datetime64('2100-01-01', 'D'))
    present = np.flatnonzero((inst <= S) & (removal > S))
    key = sorted(present, key=lambda i: (eq['account'][i] or '', eq['serial'][i] or ''))
    out = []
    for i in key:
        k = f['acct'][i]
        phase = int(a['pm_phase'][i])
        since = int((S - inst[i]).astype(np.int64)) - phase
        last_pm = None if (a['pm_none'][i] or since < 0) else \
            _py(inst[i] + np.timedelta64(phase + 365 * (since // 365), 'D'))
        gl = a['go_live'][i]
        out.append([eq['serial'][i], a['status'][i], eq['account'][i], acc['address'][k], acc['city'][k],
                    acc['state'][k], acc['zip'][k], acc['country'][k], acc['phone'][k], eq['family'][i],
                    eq['model'][i], a['mfg'][i], a['poll'][i], a['location'][i], last_pm, a['ownership'][i],
                    a['vendor'][i], a['vendor_notes'][i], a['plan'][i], _py(a['sc_exp'][i]),
                    None if eq['blank_install'][i] else _py(inst[i]),
                    None if (np.isnat(gl) or gl > S) else _py(gl)])
    return present, out


# ------------------------------------------------------------------------------------------------ build
def build(out, seed=7, null=False, variant=None, snapshots=1, scale=1.0, split_from=None):
    """Write the fixture files to `out` and return the truth dict (also written to out/truth.json)."""
    if variant is not None and variant not in VARIANTS:
        raise ValueError(f'unknown variant {variant!r}; choose from {sorted(VARIANTS)}')
    if split_from is not None and variant != 'category_split':
        raise ValueError('split_from applies to the category_split variant only')
    split_from = f'{pd.Timestamp(split_from or SPLIT_FROM):%Y-%m-%d}'
    snapshots = int(snapshots)
    if snapshots < 1:
        raise ValueError('snapshots must be at least 1')
    if not scale > 0:
        raise ValueError('scale must be positive')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    _check_out_dir(out)
    seq = dict(zip(STREAMS, np.random.SeedSequence(seed).spawn(len(STREAMS))))
    rng = {k: np.random.default_rng(s) for k, s in seq.items()}

    # fleet, calendar, null intensity
    f, acc = _make_fleet(rng['fleet'], scale)
    f['frailty_m'] = acc['frailty'][f['acct']]
    cal = _calendar(rng['shock'])
    lam, active, base = _intensity(f, cal)
    n_grid = f['n_grid']
    removed_rows = np.flatnonzero(f['removed'][:n_grid])

    # tickets
    parts = _simulate(lam, np.arange(n_grid), f, cal, null, variant == 'baseline_spike', seq['main'], 'main')
    if variant == 'removed_2x':                 # extra process: removed machines from 1.5x to 2x (all effects)
        parts += _simulate(lam * (REMOVED_MULT_2X / REMOVED_MULT - 1), removed_rows, f, cal, null, False,
                           seq['removed2x'], 'removed_2x')
    parts += _extras(lam, active, f, cal, rng['extras'])
    special, before_machines = _specials(lam, f, cal, rng['special'])
    parts += special
    C = _canonical(parts, f, acc, cal, rng['case'])
    vr = rng['variant']
    info = {}

    # row-set variants (canonical labels kept)
    extract = EXTRACT_DATE
    if variant == 'closed_only':
        info['dropped_open_rows'] = int(C['open'].sum())
        C = _select(C, ~C['open'])
    if variant == 'quarter_end_filter':
        keep = C['opened'] < np.datetime64(QUARTER_END[0], 'm')
        info['dropped_rows'] = int((~keep).sum())
        C = _select(C, keep)
        extract = QUARTER_END[1]
        cap = np.datetime64(f'{extract}T{EXTRACT_HOUR - 1:02d}:00', 'm')
        late = ~np.isnat(C['closed']) & (C['closed'] > cap)
        half = ((cap - C['opened'][late]).astype(np.int64) // 2).astype('timedelta64[m]')
        C['closed'][late] = C['opened'][late] + half
        info['closed_times_pulled_back'] = int(late.sum())
        info['last_opened_written'] = str(C['opened'].max())[:10]
    if variant == 'duplicate_case':
        r = C['rows']
        _, _, _, unpl = _classify(r)
        y = C['opened'].astype('datetime64[D]')
        ok = (unpl & ~C['monitoring'] & ~C['open'] & (y >= np.datetime64('2025-04-01'))
              & (y < np.datetime64('2025-07-01')) & f['listed'][C['mi']] & (r['Trouble Code'] == 'Electro/Mechanical')
              & ~_isin(r['Trouble Code Category'], ['Touchscreen', 'Deposit Door', 'Computer Board', None]))
        i = int(vr.choice(np.flatnonzero(ok)))            # a 2025 Q2 door/mechanical ticket: no planted cell moves
        alt = [c for t, c, _, _ in REQUEST_TYPES
               if t == 'Electro/Mechanical' and c not in (None, r['Trouble Code Category'][i], 'Deposit Door')]
        dup = {k: ({h: np.insert(x, i + 1, x[i]) for h, x in v.items()} if k == 'rows' else np.insert(v, i + 1, v[i]))
               for k, v in C.items()}
        dr = dup['rows']
        dr['Status'][i + 1] = 'Closed' if dr['Status'][i] != 'Closed' else 'Trouble Closed'
        dr['Trouble Code Category'][i + 1] = alt[int(vr.integers(len(alt)))]
        dr['Trouble Code Sub Category'][i + 1] = None
        dr['Trouble Resolution'][i + 1] = 'Fake resolution: record updated after revisit'
        dup['closed'][i + 1] = dup['closed'][i] + np.timedelta64(2 * 1440, 'm')
        C = dup
        hr = 2
        info.update({'case_number': str(dr['Case Number'][i]), 'excel_rows': [i + hr, i + 1 + hr],
                     'categories': [dr['Trouble Code Category'][i], dr['Trouble Code Category'][i + 1]]})

    # counts (rows as written, canonical labels)
    R = C['rows']
    planned, cancelled, duplicate, unplanned = _classify(R)
    pairs = [(t or BLANK, c or BLANK) for t, c in zip(R['Trouble Code'], R['Trouble Code Category'])]
    unmapped = unplanned & np.array([p not in V0_PAIRS for p in pairs], bool)
    monitoring = np.array([bool(TEMPLATE_RE.search(t or '')) for t in R['Trouble Reported']], bool)

    # equipment lists (list variants first)
    eq = {'serial': f['serial'][:n_grid].astype(object),
          'account': np.array([acc['name'][k] for k in f['acct'][:n_grid]], dtype=object),
          'model': f['model'][:n_grid].astype(object), 'family': f['family'][:n_grid].astype(object),
          'blank_install': f['blank_install'][:n_grid].copy()}
    listed_rows = np.flatnonzero(f['listed'][:n_grid])
    protect = np.zeros(n_grid, bool)
    protect[list(before_machines)] = True
    if variant == 'blank_install':
        need = int(round(0.20 * len(listed_rows))) - int(eq['blank_install'][listed_rows].sum())
        pool = listed_rows[~eq['blank_install'][listed_rows] & ~protect[listed_rows]]
        eq['blank_install'][vr.choice(pool, size=need, replace=False)] = True
        info['blank_install_machines'] = int(eq['blank_install'][listed_rows].sum())
    if variant == 'blank_list_fields':
        pool = listed_rows[~f['tp'][listed_rows] & ~protect[listed_rows] & (f['model'][listed_rows] != TINY_MODEL)]
        pick = vr.choice(pool, size=11, replace=False)
        for col, sel in (('account', pick[:3]), ('model', pick[3:6]), ('family', pick[6:9]), ('serial', pick[9:])):
            eq[col][sel] = None
        info.update({'blank_account_serials': f['serial'][pick[:3]].tolist(),
                     'blank_model_serials': f['serial'][pick[3:6]].tolist(),
                     'blank_family_serials': f['serial'][pick[6:9]].tolist(),
                     'blank_serial_rows': 2, 'blank_serial_true_serials': f['serial'][pick[9:]].tolist()})
    snap_dates = [(pd.Timestamp(NEWEST_SNAPSHOT) - pd.DateOffset(months=k)).strftime('%Y-%m-%d')
                  for k in range(snapshots - 1, -1, -1)]
    on_any = np.zeros(n_grid, bool)
    equipment_files = []
    for date in snap_dates:
        present, rows = _snapshot_rows(f, acc, eq, date)
        on_any[present] = True
        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet(EQUIP_SHEET)
        ws.append(EQUIP_HEADERS)
        for r in rows:
            ws.append(r)
        name = f'IPA_Active_Equipment_list_{date}.xlsx'
        _save(wb, out / name, dt.datetime.fromisoformat(date).replace(hour=EXTRACT_HOUR))
        equipment_files.append(name)
        if date == snap_dates[-1]:
            newest_present, newest_rows = present, rows

    # population and expectations
    has_serial = np.array([s is not None for s in eq['serial']], bool)
    pop_mask = on_any & has_serial & ~f['tp'][:n_grid] & ~eq['blank_install']
    pop = np.flatnonzero(pop_mask)
    rowmult = np.where(f['removed'][:n_grid] & (variant == 'removed_2x'), REMOVED_MULT_2X / REMOVED_MULT, 1.0)
    label = ((1 - MONITORING_SHARE) * np.where(cal['early'], 1 - EARLY_BLANK[2], 1.0)
             * np.where(cal['late'], 1 - OPEN_SHARE, 1.0))     # share of tickets written with their Category
    if variant == 'quarter_end_filter':
        label = label * (np.arange(N_DAYS) < _day(QUARTER_END[0]))

    def effect(i, rows, drop=None):
        e = np.ones((len(rows), N_DAYS))
        if not null:
            if i == I_TS and drop != 'ts':
                e[f['cohort'][rows]] *= TS_MULT
            if i == I_DD and drop != 'dd':
                e[:, cal['q3']] *= DD_MULT
            if i == I_CB and drop != 'cb':
                e[np.ix_(f['alex'][rows], cal['q3'])] *= CB_MULT
        if variant == 'baseline_spike' and i == I_CB and drop != 'spike':
            e[:, cal['spike']] *= SPIKE_MULT
        return e

    def per_day(i, rows, drop=None):
        return (lam[rows] * rowmult[rows, None] * effect(i, rows, drop)).sum(0) * W[i]

    def monthly(x):
        return {m: round(float(v), 3) for m, v in zip(cal['month_labels'], np.add.reduceat(x, cal['month_starts']))}

    def cell(entry, use_null):
        i = ISSUE[entry['issue']]
        sc = entry['scope']
        sel = pop_mask.copy()
        if 'install_years' in sc:
            yr = np.where(eq['blank_install'], 0, f['year'][:n_grid])
            sel &= np.isin(yr, sc['install_years'])
        if 'family' in sc:
            sel &= np.array([x == sc['family'] for x in eq['family']], bool)
        rows = np.flatnonzero(sel)
        drop = entry['key']
        with_e, without = per_day(i, rows), per_day(i, rows, drop)
        fleet_with, fleet_without = per_day(i, pop), per_day(i, pop, drop)
        expo = active[rows].sum(0) / MONTH_DAYS
        q3 = cal['q3']
        lq = label[q3]
        res = {k: v for k, v in entry.items() if k != 'key'}
        if use_null:
            res['multiplier'] = 1.0
        res.update({'expected_in_2026Q3': round(float((with_e[q3] * lq).sum()), 3),
                    'expected_without_effect_in_2026Q3': round(float((without[q3] * lq).sum()), 3),
                    'exposure_months_2026Q3': round(float(expo[q3].sum()), 3),
                    'machines': int(len(rows)),
                    'fleet_expected_in_2026Q3': round(float((fleet_with[q3] * lq).sum()), 3),
                    'fleet_expected_without_effect_in_2026Q3': round(float((fleet_without[q3] * lq).sum()), 3)})
        if 'install_years' in sc:
            yr = f['year'][rows]
            res['expected_in_2026Q3_by_install_year'] = {
                str(y): round(float((per_day(i, rows[yr == y])[q3] * lq).sum()), 3) for y in sc['install_years']}
        res.update({'expected_by_month': monthly(with_e * label),
                    'expected_without_effect_by_month': monthly(without * label),
                    'exposure_months_by_month': monthly(expo)})
        return res

    planted = [] if null else [cell(e, False) for e in PLANTED]
    lam_pop = lam[pop] * rowmult[pop, None]
    gen_total = lam_pop.sum()
    for i in (I_TS, I_DD, I_CB):
        gen_total += W[i] * (lam_pop * (effect(i, pop) - 1)).sum()
    pop_months = float(active[pop].sum() / MONTH_DAYS)
    pop_serials = set(f['serial'][pop].tolist())
    on_pop = np.array([s in pop_serials for s in C['serial']], bool)

    # variants that change labels or formats (counts above stay canonical)
    case_sheet, header, title, footer = CASE_SHEET, list(HEADERS), [], []
    R = {h: v.copy() for h, v in C['rows'].items()}
    opened, closed = C['opened'].copy(), C['closed'].copy()
    if variant == 'category_split':
        hit = (R['Trouble Code Category'] == 'Deposit Door') & (opened >= np.datetime64(split_from, 'm'))
        R['Trouble Code Category'][hit] = np.where(vr.random(int(hit.sum())) < 0.5, 'Deposit Door - Latch',
                                                   'Deposit Door - Sensor')
        info.update({'from': split_from, 'canonical': 'Deposit Door',
                     'written': ['Deposit Door - Latch', 'Deposit Door - Sensor'], 'rows': int(hit.sum())})
    if variant == 'trouble_code_rename':
        hit = (R['Trouble Code'] == 'Preventative Maintenance') & (opened >= np.datetime64(SPLIT_FROM, 'm'))
        R['Trouble Code'][hit] = 'Preventive Maintenance'
        info.update({'from': SPLIT_FROM, 'canonical': 'Preventative Maintenance', 'written': 'Preventive Maintenance',
                     'rows': int(hit.sum()),
                     'rows_leaking_into_unplanned': int((hit & (R['Case Record Type'] != 'Install Case')).sum())})
    if variant == 'central_clock':
        opened = opened - np.timedelta64(60, 'm')
        closed = closed - np.timedelta64(60, 'm')
        info.update({'shift_hours': -1, 'clock': 'America/Chicago'})
    if variant == 'header_alias':
        header[HEADERS.index('Trouble Code Category')] = 'Trouble Code Cat.'
        info.update({'canonical': 'Trouble Code Category', 'written': 'Trouble Code Cat.'})
    if variant == 'sheet_name':
        case_sheet = 'Report 1'
        info['case_sheet'] = case_sheet
    if variant == 'title_rows':
        title = ['IPA Case History', 'Fake Report Owner', f'As of {pd.Timestamp(extract):%m/%d/%Y}']
        footer = [None, 'Generated By: Fake User', 'Confidential Information - Do Not Distribute']
        info.update({'header_row': len(title) + 1, 'title_rows': title, 'footer_rows': footer})
    opened_out = [_py(x) for x in opened]
    if variant == 'text_dates':
        opened_out = [x.strftime('%m/%d/%Y %I:%M %p') for x in opened_out]
        info['format'] = '%m/%d/%Y %I:%M %p'
    if variant == 'mixed_dates':
        day_first = vr.random(len(opened_out)) < 0.5
        opened_out = [x.strftime('%d/%m/%Y %H:%M' if d else '%m/%d/%Y %H:%M') for x, d in zip(opened_out, day_first)]
        dom = np.array([x.day for x in (_py(o) for o in opened)])
        info.update({'formats': ['%d/%m/%Y %H:%M', '%m/%d/%Y %H:%M'], 'rows_day_first': int(day_first.sum()),
                     'rows_month_first': int((~day_first).sum()), 'rows_ambiguous': int((dom <= 12).sum())})
    if variant == 'baseline_spike':
        sp = cal['spike']
        with_s, without_s = per_day(I_CB, pop)[sp] * label[sp], per_day(I_CB, pop, 'spike')[sp] * label[sp]
        info.update({'issue': 'Computer Board', 'period': list(SPIKE_MONTH), 'multiplier': SPIKE_MULT,
                     'expected_in_period': round(float(with_s.sum()), 3),
                     'expected_without_spike_in_period': round(float(without_s.sum()), 3)})
    if variant == 'removed_2x':
        e_removed = lam[removed_rows].sum() * REMOVED_MULT_2X / REMOVED_MULT
        info.update({'removed_multiplier': REMOVED_MULT_2X,
                     'expected_tickets_on_removed_machines': round(float(e_removed), 3)})
    data = []
    for j in range(len(opened_out)):
        row = [R[h][j] for h in HEADERS]
        row[0] = opened_out[j]
        row[-1] = _py(closed[j])
        data.append(row)
    case_file = f'IPA_CaseHistory_{extract}.xlsx'
    when = dt.datetime.fromisoformat(extract).replace(hour=EXTRACT_HOUR)
    _write_case(out / case_file, header, data, case_sheet, when, title, footer, summary=variant != 'sheet_name')

    # truth
    mi = C['mi']
    newest_install = {eq['serial'][i]: f['install'][i] for i in newest_present
                      if not eq['blank_install'][i] and eq['serial'][i] is not None}
    before = np.array([s in newest_install and o.astype('datetime64[D]') < newest_install[s]
                       for s, o in zip(C['serial'], C['opened'])], bool)
    never = mi >= n_grid
    on_removed, on_tp = f['removed'][mi], f['tp'][mi]
    pop_unplanned = int((unplanned & on_pop).sum())
    counts = {'case_rows': len(data), 'unplanned': int(unplanned.sum()), 'planned': int(planned.sum()),
              'cancelled': int(cancelled.sum()), 'duplicate': int(duplicate.sum()), 'monitoring': int(monitoring.sum()),
              'listed_machines_newest': len(newest_rows), 'removed_serials': int(len(set(mi[on_removed].tolist()))),
              'third_party_machines': int(f['tp'][newest_present].sum()),
              'missing_install_dates': int(eq['blank_install'][newest_present].sum()),
              'open_tickets': int((C['rows']['Status'] == 'Dispatch').sum()), 'unmapped_tickets': int(unmapped.sum()),
              'unlisted_never_listed_tickets': int(never.sum()), 'tickets_before_install': int(before.sum()),
              'removed_machines_generated': int(f['n_removed']), 'removed_serial_tickets': int(on_removed.sum()),
              'third_party_tickets': int(on_tp.sum()),
              'population_machines': int(len(pop)), 'population_machine_months': round(pop_months, 3),
              'population_unplanned': pop_unplanned,
              'fleet_rate_per_100_observed': round(100 * pop_unplanned / pop_months, 4),
              'fleet_rate_per_100_expected': round(float(100 * gen_total / pop_months), 4)}
    truth = {'seed': seed, 'null': bool(null), 'variant': variant, 'scale': scale, 'window': list(WINDOW),
             'extract_date': extract, 'snapshots': snap_dates, 'case_file': case_file,
             'equipment_files': equipment_files, 'counts': counts, 'planted': planted}
    if null:
        truth['null_expectations'] = [cell(e, True) for e in PLANTED]
    truth.update({
        'fake_strings': {'accounts': list(acc['name']), 'cities': list(acc['city']),
                         'serials_sample': [r[0] for r in newest_rows if r[0] is not None][:50],
                         'case_numbers_sample': [str(x) for x in R['Case Number'][:50]]},
        'headers_case': list(HEADERS), 'headers_equipment': list(EQUIP_HEADERS),
        'population': ('machines on any written equipment snapshot with a non-blank serial, service plan not '
                       f'{THIRD_PARTY_PLAN} and a non-blank install date; cells by listed install year / family; '
                       'tickets = unplanned, not monitoring-template, opened in the period (Eastern)'),
        'variant_info': info, 'base_rate_per_machine_day': base, 'monitoring_share': MONITORING_SHARE,
        'generator': MARKER})
    (out / 'truth.json').write_text(json.dumps(truth, indent=1, default=str) + '\n', encoding='utf-8')
    label_of = {'touchscreen_install_cohort': 'Touchscreen 2022-23 installs', 'deposit_door_rise': 'Deposit Door',
                'alex_computer_board_fall': 'alEx Computer Board'}
    summary = '; '.join(f"{label_of[e['name']]} {e['expected_in_2026Q3']:.1f} "
                        f"(without effect {e['expected_without_effect_in_2026Q3']:.1f})"
                        for e in (planted or truth['null_expectations']))
    print(f"{out}: {case_file} {counts['case_rows']:,} rows, {counts['unplanned']:,} unplanned; "
          f"{counts['listed_machines_newest']:,} listed machines (+{counts['removed_serials']} removed serials with "
          f"tickets) in "
          f"{len(equipment_files)} snapshot(s); fleet rate {counts['fleet_rate_per_100_observed']:.2f}/100 mm; "
          f"2026Q3 expected{' (null)' if null else ''}: {summary}; variant={variant}")
    return truth


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                                 epilog='Variants: ' + '; '.join(f'{k}: {v}' for k, v in VARIANTS.items()))
    ap.add_argument('--out', required=True, help='folder to write the workbooks and truth.json to')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--null', action='store_true', help='plant no effects')
    ap.add_argument('--variant', choices=sorted(VARIANTS), default=None)
    ap.add_argument('--snapshots', type=int, default=1, help='monthly equipment snapshots ending 2026-11-14')
    ap.add_argument('--scale', type=float, default=1.0, help='multiplies the number of accounts and machines')
    ap.add_argument('--split-from', default=None, help="category_split: first day of the split (default 2026-07-01)")
    a = ap.parse_args(argv)
    try:
        build(a.out, seed=a.seed, null=a.null, variant=a.variant, snapshots=a.snapshots, scale=a.scale,
              split_from=a.split_from)
    except (FileExistsError, ValueError) as e:
        raise SystemExit(f'make_trend_fixture: {e}')


if __name__ == '__main__':
    main()
