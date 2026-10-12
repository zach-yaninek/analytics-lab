"""Case-side timestamp semantics and field-update timing (Zac's open item 6.3, bullet 2).

Questions answered from the case export alone (the telemetry DB is not needed):
  A. Which clock 'Date/Time Opened' / 'Trouble Closed Date/Time' are recorded in
     (hospital-local vs one fixed clock; DST-observing vs UTC/non-DST), via zone-shift,
     DST, Arizona/Hawaii (no-DST) and help-desk-hour tests.
  B. Close-timestamp quality (durations, missing/text values, precision, heaping, batching).
  C. Which ticket fields are available at opening vs filled later (leakage for an
     at-opening classifier), including date stamps parsed from Administrative Notes.
  D. Monitoring-originated tickets (ticket text derived from clearView/clariFy telemetry).
  E. What the clock conclusion implies for the notebook's pilot windows (cells 8/34).

Privacy: free text, names, locations below state level, case numbers and serials are read
in memory only. Outputs contain pseudonyms (T#####, S#####, Owner NN), generic labels
(states, time-zone groups, models, codes, statuses) and aggregate counts.

Run: cd /home/user/analytics-lab && python3 -I verification/timestamp_semantics.py
Writes verification/outputs/ts_*.csv (no figures: matplotlib is not installed here)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import datetime as dt
import re
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import OUTPUTS, XLS, build_cases, build_maps, case_database, load_raw, sha256_file

OUTPUTS.mkdir(parents=True, exist_ok=True)
pd.set_option('display.width', 220)
pd.set_option('display.max_columns', 40)
pd.set_option('display.max_rows', 200)
RNG = np.random.default_rng(15072)
B_FAST = 2000      # bootstrap reps for quantile statistics
B_KS = 500         # bootstrap reps for the KS-minimising shift (slower)
FACTS = []         # (section, item, value) rows for ts_facts.csv


def out(df, name):
    path = OUTPUTS / f'ts_{name}.csv'
    df.to_csv(path, index=False)
    print(f'  -> verification/outputs/ts_{name}.csv ({len(df)} rows)')
    return df


def fact(section, item, value):
    FACTS.append({'section': section, 'item': item, 'value': value})
    print(f'  [{section}] {item}: {value}')


def banner(text):
    print('\n' + '=' * 100 + '\n' + text + '\n' + '=' * 100)


# ============================================================================================
# Load (cell-4 rebuild; pandas-3 NaN -> None fix as in 01_excel_reproducibility.py)
# ============================================================================================
banner('Load')
raw0 = load_raw()
raw = raw0.astype(object).where(raw0.notna(), None)
maps = build_maps(raw)
cases = build_cases(raw, maps)
conn = case_database(cases)
base = pd.read_sql_query('SELECT case_id, service_group FROM case_base', conn)
cases = cases.merge(base, on='case_id', how='left', validate='1:1')
assert len(cases) == 7471 and cases.case_id.is_unique
fact('load', 'workbook_sha256_prefix', sha256_file(XLS)[:12])
fact('load', 'rows', len(cases))

opened = pd.to_datetime(cases.opened_at)
closed = pd.to_datetime(cases.closed_at)
cases['opened'] = opened
cases['closed'] = closed
cases['hf'] = opened.dt.hour + opened.dt.minute / 60          # fractional opening hour, recorded clock
cases['dow'] = opened.dt.dayofweek
cases['weekday'] = cases.dow < 5
EXPORT_LAST_OPEN = opened.max()
EXPORT_REF = max(opened.max(), closed.max())                  # export ran no earlier than this
fact('load', 'first_opened', str(opened.min()))
fact('load', 'last_opened', str(EXPORT_LAST_OPEN))
fact('load', 'latest_timestamp_any_column (export ran at/after)', str(EXPORT_REF))

# ============================================================================================
# A1. Hospital state/province -> IANA zone -> zone group
# ============================================================================================
banner('A1. Location -> time zone')
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


loc = pd.concat([raw['Hospital City, State, Zip'], raw['Shipping Country']], axis=1)
geo = pd.DataFrame([locate(a, b) for a, b in loc.itertuples(index=False)])
cases = pd.concat([cases, geo], axis=1)
cases['country'] = raw['Shipping Country'].map(lambda x: COUNTRY.get(x, x))
cases['zone'] = cases.iana.map(GROUP).fillna('Unparsed')
mapping = (cases.groupby(['country', 'state', 'iana', 'zone', 'zip_rule'], dropna=False).size()
           .rename('tickets').reset_index().sort_values(['zone', 'state']))
out(mapping, 'zone_mapping')
fact('A1', 'unparsed_locations', int((cases.zone == 'Unparsed').sum()))
fact('A1', 'country_vs_state_conflicts',
     int(((cases.country == 'CA') != cases.state.isin(['ON', 'QC', 'NL', 'NFLD', 'NS', 'NB', 'PE', 'MB', 'SK', 'AB',
                                                         'BC'])).sum()))
fact('A1', 'tickets_by_zone', cases.zone.value_counts().to_dict())
fact('A1', 'zip_rule_hits', cases.loc[~cases.zip_rule.str.startswith('state default'), 'zip_rule'].value_counts().to_dict())


# UTC offsets of the hospital zone and of US Eastern at the recorded opening time.
def utc_off(tzname, naive):
    return naive.replace(tzinfo=ZoneInfo(tzname)).utcoffset().total_seconds() / 3600


NY = 'America/New_York'
cases['off_hosp'] = [utc_off(z, t.to_pydatetime()) if z else np.nan for z, t in zip(cases.iana, opened)]
cases['off_east'] = [utc_off(NY, t.to_pydatetime()) for t in opened]
cases['eastern_dst'] = cases.off_east == -4
cases['season'] = np.where(cases.eastern_dst, 'DST (EDT)', 'Standard (EST)')
# Expected recorded-clock shift vs Eastern hospitals if all tickets are on one DST-observing Eastern clock.
cases['expected_shift_fixed_eastern'] = cases.off_east - cases.off_hosp
fact('A1', 'eastern_dst_boundaries_in_data',
     f"DST tickets {int(cases.eastern_dst.sum())}, standard {int((~cases.eastern_dst).sum())}; "
     f"standard period {opened[~cases.eastern_dst].min()} .. {opened[~cases.eastern_dst].max()}")

# ============================================================================================
# D (needed early). Monitoring-originated tickets: flags from Trouble Reported (in memory only)
# ============================================================================================
reported = raw['Trouble Reported'].fillna('').astype(str)
resolution = raw['Trouble Resolution'].fillna('').astype(str)
notes = raw['Administrative Notes'].fillna('').astype(str)
MON_TEMPLATE_RE = r'^\W*monitor(?:ing)?\b|monitor(?:ing)?\s*-?\s*\[?\s*(?:daily|poll|weekly)|during monitoring|\bday monitoring\b'
TELEMETRY_UI_RE = r'clear\s*-?\s*view|clari\s*fy|\bcanopy\b|\biot\b'
CODE_REF_RE = (r'\b(?:error|err|code)\s*(?:code\s*)?#?\s*\d{1,2}\b|\b\d{2}\s+errors?\b|'
               r'\bcode\s+\d{2}\b')
cases['mon_template'] = reported.str.contains(MON_TEMPLATE_RE, case=False, regex=True)
cases['telemetry_ui'] = reported.str.contains(TELEMETRY_UI_RE, case=False, regex=True)
cases['code_ref'] = reported.str.contains(CODE_REF_RE, case=False, regex=True)
cases['device_fw'] = reported.str.contains(r'device\s*fw\s*:', case=False, regex=True)
cases['monitoring_any'] = cases.mon_template | cases.telemetry_ui
# Zac-comparable sibling definition used in audit_case_logic.py (for cross-reference only)
cases['proactive_sibling'] = reported.str.contains(r'monitoring\s*-?\s*(?:daily|poll|weekly)|^\s*monitoring\b',
                                                   case=False, regex=True)

# ============================================================================================
# A2. Opening-hour distributions by zone and shift vs Eastern
# ============================================================================================
banner('A2. Opening-hour distributions by zone; shift vs Eastern')
Q = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
QGRID = np.round(np.arange(0.05, 0.951, 0.05), 2)
T_GRID = np.arange(-12 * 60, 36 * 60 + 1) / 60.0             # minute grid; data are minute-precise
SHIFTS = np.round(np.arange(-3.0, 8.0001, 0.05), 2)

SUBSETS = {
    'all': np.ones(len(cases), bool),
    'weekday_reactive': (cases.weekday & ~cases.mon_template & (cases.service_group != 'Planned work')).to_numpy(),
    'monitoring_template': cases.mon_template.to_numpy(),
    'planned_work': (cases.service_group == 'Planned work').to_numpy(),
}
DESK_DRIVEN = {'monitoring_template', 'planned_work'}   # created on the desk's schedule, not when a hospital calls
fact('A2', 'subset_sizes', {k: int(v.sum()) for k, v in SUBSETS.items()})


def qstats(x):
    x = np.asarray(x, float)
    d = {'n': len(x)}
    if len(x) == 0:
        return d
    d.update({f'p{int(q * 100):02d}': round(float(np.quantile(x, q)), 2) for q in Q})
    d.update({'mean': round(float(x.mean()), 2), 'min': round(float(x.min()), 2), 'max': round(float(x.max()), 2),
              'share_before_07': round(float((x < 7).mean()), 4), 'share_07_08': round(float(((x >= 7) & (x < 8)).mean()), 4),
              'share_before_09': round(float((x < 9).mean()), 4), 'share_from_17': round(float((x >= 17).mean()), 4),
              'share_from_19': round(float((x >= 19).mean()), 4)})
    return d


def ks_curve(z, e):
    """KS distance between (z - d) and e for each shift d in SHIFTS (exact on the minute grid)."""
    zs, es = np.sort(z), np.sort(e)
    fe = np.searchsorted(es, T_GRID, side='right') / len(es)
    tt = T_GRID[None, :] + SHIFTS[:, None]
    fz = np.searchsorted(zs, tt.ravel(), side='right').reshape(tt.shape) / len(zs)
    return np.abs(fz - fe[None, :]).max(1)


def ks_shift(z, e):
    curve = ks_curve(z, e)
    i = int(curve.argmin())
    return float(SHIFTS[i]), float(curve[i]), curve


def qa_shift(z, e):
    return float(np.mean(np.quantile(z, QGRID) - np.quantile(e, QGRID)))


def boot(fn, z, e, reps):
    vals = np.empty(reps)
    for b in range(reps):
        vals[b] = fn(RNG.choice(z, len(z)), RNG.choice(e, len(e)))
    return np.percentile(vals, [2.5, 97.5])


def compare(z, e, ks_reps=B_KS, fast_reps=B_FAST):
    """Shift of z relative to e: median diff, low-tail diffs, quantile-alignment and KS-minimising shift + CIs."""
    z, e = np.asarray(z, float), np.asarray(e, float)
    row = {'n': len(z), 'n_ref': len(e)}
    if len(z) < 5:
        return row
    med = lambda a, b: float(np.median(a) - np.median(b))
    row['median_diff'] = round(med(z, e), 2)
    row['median_diff_lo'], row['median_diff_hi'] = np.round(boot(med, z, e, fast_reps), 2)
    for q in (0.05, 0.10, 0.25, 0.75, 0.90):
        row[f'p{int(q * 100):02d}_diff'] = round(float(np.quantile(z, q) - np.quantile(e, q)), 2)
    row['qa_shift'] = round(qa_shift(z, e), 2)
    row['qa_shift_lo'], row['qa_shift_hi'] = np.round(boot(qa_shift, z, e, fast_reps), 2)
    s, d, curve = ks_shift(z, e)
    row['ks_shift'], row['ks_at_shift'] = s, round(d, 3)
    row['ks_at_0'] = round(float(curve[np.where(SHIFTS == 0)[0][0]]), 3)
    if ks_reps:
        row['ks_shift_lo'], row['ks_shift_hi'] = np.round(boot(lambda a, b: ks_shift(a, b)[0], z, e, ks_reps), 2)
    return row


zones_present = [z for z in ZONE_ORDER if (cases.zone == z).any()]
qrows, srows = [], []
for sname, smask in SUBSETS.items():
    sub = cases[smask]
    e = sub.loc[sub.zone == 'Eastern', 'hf'].to_numpy()
    for zname in zones_present:
        zsub = sub[sub.zone == zname]
        qrows.append({'subset': sname, 'zone': zname, **qstats(zsub.hf)})
        if zname == 'Eastern' or len(zsub) < 5:
            continue
        expected = round(float(zsub.expected_shift_fixed_eastern.mean()), 2)
        desk_driven = sname in DESK_DRIVEN
        srows.append({'subset': sname, 'zone': zname, 'timing_driver': 'desk' if desk_driven else 'caller',
                      # caller-driven tickets follow hospital-local hours; desk-driven ones follow desk hours
                      'expected_shift_H_local': -expected if desk_driven else 0.0,
                      'expected_shift_H_fixed_clock_mean': 0.0 if desk_driven else expected,
                      **compare(zsub.hf.to_numpy(), e, ks_reps=B_KS if sname in ('all', 'weekday_reactive') else 0)})
# Desk-driven control, pooled: monitoring-template tickets for all non-Eastern hospitals. If the export were
# hospital-local, tickets the desk creates during its own hours would appear EARLIER by each zone's offset.
for sname in ('monitoring_template', 'planned_work'):
    sub = cases[SUBSETS[sname]]
    e = sub.loc[sub.zone == 'Eastern', 'hf'].to_numpy()
    zsub = sub[(sub.zone != 'Eastern')]
    if len(zsub) >= 5 and len(e) >= 5:
        srows.append({'subset': sname, 'zone': 'non-Eastern pooled', 'timing_driver': 'desk',
                      'expected_shift_H_local': round(float(-zsub.expected_shift_fixed_eastern.mean()), 2),
                      'expected_shift_H_fixed_clock_mean': 0.0,
                      **compare(zsub.hf.to_numpy(), e, ks_reps=0)})
qtab = out(pd.DataFrame(qrows), 'open_hour_by_zone')
stab = out(pd.DataFrame(srows), 'zone_shift_vs_eastern')
print(qtab[qtab.subset.isin(['all', 'weekday_reactive', 'monitoring_template'])].to_string(index=False))
print(stab.to_string(index=False))

# Hourly histogram on the recorded clock (weekdays / weekends) by zone
hist = (cases.assign(hour=opened.dt.hour, daytype=np.where(cases.weekday, 'weekday', 'weekend'))
        .pivot_table(index=['daytype', 'hour'], columns='zone', values='case_id', aggfunc='count', fill_value=0)
        .reindex(columns=zones_present).reset_index())
out(hist, 'open_hour_hist_by_zone')

# Reconstructed local-hour medians under alternative fixed clocks (all tickets; weekday reactive)
lrows = []
for sname in ('all', 'weekday_reactive'):
    sub = cases[SUBSETS[sname]]
    for zname in zones_present:
        zsub = sub[sub.zone == zname]
        if len(zsub) == 0:
            continue
        r = {'subset': sname, 'zone': zname, 'n': len(zsub), 'recorded_median': round(float(zsub.hf.median()), 2),
             'recorded_p10': round(float(zsub.hf.quantile(.10)), 2)}
        for clock, tzname in [('US_Eastern', NY), ('US_Central', 'America/Chicago')]:
            off_clock = np.array([utc_off(tzname, t.to_pydatetime()) for t in zsub.opened])
            local = zsub.hf.to_numpy() + (zsub.off_hosp.to_numpy() - off_clock)
            r[f'local_median_if_{clock}'] = round(float(np.median(local)), 2)
            r[f'local_p10_if_{clock}'] = round(float(np.quantile(local, .10)), 2)
            r[f'local_share_before_07_if_{clock}'] = round(float((local < 7).mean()), 3)
        lrows.append(r)
out(pd.DataFrame(lrows), 'local_hour_reconstruction')

# ============================================================================================
# A3. DST test
# ============================================================================================
banner('A3. DST test (Eastern hospitals; desk-opening edge, all zones)')
drows = []
east = cases[cases.zone == 'Eastern']
WINDOWS = {
    'full_season': (east.eastern_dst, ~east.eastern_dst),
    'fall_4wk (2025-10-05..11-01 vs 11-02..11-29)': (
        east.opened.between('2025-10-05', '2025-11-01 23:59') ,
        east.opened.between('2025-11-02', '2025-11-29 23:59')),
    'spring_4wk (2026-03-08..04-04 vs 02-08..03-07)': (
        east.opened.between('2026-03-08', '2026-04-04 23:59'),
        east.opened.between('2026-02-08', '2026-03-07 23:59')),
}
for sname in ('all', 'weekday_reactive'):
    smask = pd.Series(SUBSETS[sname], index=cases.index).loc[east.index]
    for wname, (m_dst, m_std) in WINDOWS.items():
        z = east.loc[m_std & smask, 'hf'].to_numpy()       # standard period
        e = east.loc[m_dst & smask, 'hf'].to_numpy()       # DST period (reference)
        drows.append({'subset': sname, 'window': wname, 'comparison': 'Standard minus DST (Eastern hospitals)',
                      'expected_if_DST_observing_wall_clock': 0.0, 'expected_if_UTC_or_nonDST_clock': 1.0,
                      **compare(z, e)})
dst_tab = out(pd.DataFrame(drows), 'dst_test')
print(dst_tab.to_string(index=False))

# Desk-opening edge by season (weekdays, all zones): an hour-6 vs hour-7 edge would move under a non-DST clock.
wk = cases[cases.weekday].copy()
wk['hour'] = wk.opened.dt.hour
wk['day'] = wk.opened.dt.strftime('%Y-%m-%d')
first = wk.groupby('day').agg(first_hf=('hf', 'min'), n=('hf', 'size'), season=('season', 'first'))
EDGE_WINDOWS = [('full period', 'DST (EDT)', None, None), ('full period', 'Standard (EST)', None, None),
                ('fall: 4 wk before', 'DST (EDT)', '2025-10-05', '2025-11-01'),
                ('fall: 4 wk after', 'Standard (EST)', '2025-11-02', '2025-11-29'),
                ('spring: 4 wk before', 'Standard (EST)', '2026-02-08', '2026-03-07'),
                ('spring: 4 wk after', 'DST (EDT)', '2026-03-08', '2026-04-04')]
erows = []
for wname, season, lo, hi in EDGE_WINDOWS:
    g = wk[wk.season == season] if lo is None else wk[(wk.day >= lo) & (wk.day <= hi)]
    fd = first.loc[sorted(set(g.day))]
    erows.append({'window': wname, 'season': season, 'weekday_tickets': len(g), 'weekdays': len(fd),
                  'tickets_before_06': int((g.hf < 6).sum()), 'tickets_06h': int((g.hour == 6).sum()),
                  'tickets_07h': int((g.hour == 7).sum()), 'tickets_08h': int((g.hour == 8).sum()),
                  'share_07h': round(float((g.hour == 7).mean()), 4),
                  'first_ticket_of_day_median': round(float(fd.first_hf.median()), 2),
                  'first_ticket_of_day_p10': round(float(fd.first_hf.quantile(.10)), 2),
                  'first_ticket_of_day_p90': round(float(fd.first_hf.quantile(.90)), 2),
                  'days_first_ticket_07h': int(((fd.first_hf >= 7) & (fd.first_hf < 8)).sum()),
                  'days_first_ticket_before_07': int((fd.first_hf < 7).sum()),
                  'minutes_after_07_of_first_ticket_median': round(float(((fd.first_hf - 7) * 60).median()), 1)})
edge = out(pd.DataFrame(erows), 'dst_desk_edge')
print(edge.to_string(index=False))
first['month'] = first.index.str[:7]
med = (first.groupby('month').agg(weekdays=('n', 'size'), first_ticket_median=('first_hf', 'median'),
                                  first_ticket_p90=('first_hf', lambda s: s.quantile(.9)))
       .join(wk.assign(month=wk.day.str[:7]).groupby('month').agg(
           weekday_tickets=('hf', 'size'), share_07h=('hour', lambda s: (s == 7).mean()),
           median_open_hour_eastern_hospitals=('hf', lambda s: np.nan))))
med['median_open_hour_eastern_hospitals'] = wk[wk.zone == 'Eastern'].groupby(wk.day.str[:7]).hf.median()
med['season'] = wk.groupby(wk.day.str[:7]).season.agg(lambda s: '/'.join(sorted(set(s))))
out(med.round(3).reset_index(), 'desk_edge_by_month')
# Edge on DST transition days
for day in ('2025-11-02', '2025-11-03', '2026-03-08', '2026-03-09'):
    g = cases[cases.opened.dt.strftime('%Y-%m-%d') == day]
    fact('A3', f'tickets_on_{day}', f'{len(g)} (earliest {g.hf.min() if len(g) else None})')
fact('A3', 'tickets_in_ambiguous_hour_2025-11-02_01h', int(((cases.opened >= '2025-11-02 01:00') & (cases.opened < '2025-11-02 02:00')).sum()))
fact('A3', 'tickets_in_nonexistent_hour_2026-03-08_02h', int(((cases.opened >= '2026-03-08 02:00') & (cases.opened < '2026-03-08 03:00')).sum()))

# Monthly profile: Eastern vs West (Pacific+Mountain+Arizona) weekday-reactive
mrows = []
wr = cases[SUBSETS['weekday_reactive']]
for (month, zone), g in wr.assign(month=wr.opened.dt.strftime('%Y-%m')).groupby(['month', 'zone']):
    if zone in ('Eastern', 'Central', 'Pacific', 'Mountain', 'Arizona (no DST)'):
        mrows.append({'month': month, 'zone': zone, 'season': g.season.mode().iat[0], **qstats(g.hf)})
out(pd.DataFrame(mrows), 'monthly_open_hour')

# ============================================================================================
# A4. Arizona / Hawaii (no DST) seasonal difference-in-differences
# ============================================================================================
banner('A4. No-DST hospitals: (zone - Eastern) summer minus winter')


def did_stat(fn, zs, zw, es, ew):
    return (fn(zs) - fn(zw)) - (fn(es) - fn(ew))


arows = []
for sname in ('all', 'weekday_reactive'):
    sub = cases[SUBSETS[sname]]
    es = sub.loc[(sub.zone == 'Eastern') & sub.eastern_dst, 'hf'].to_numpy()
    ew = sub.loc[(sub.zone == 'Eastern') & ~sub.eastern_dst, 'hf'].to_numpy()
    for zname in ('Arizona (no DST)', 'Hawaii (no DST)', 'Pacific', 'Central', 'Mountain', 'no-DST pooled (AZ+HI)'):
        zmask = sub.zone.isin(['Arizona (no DST)', 'Hawaii (no DST)']) if zname.startswith('no-DST') else sub.zone == zname
        zz = sub[zmask]
        zs, zw = zz.loc[zz.eastern_dst, 'hf'].to_numpy(), zz.loc[~zz.eastern_dst, 'hf'].to_numpy()
        if len(zs) < 3 or len(zw) < 3:
            continue
        exp_fixed = (zz.loc[zz.eastern_dst, 'expected_shift_fixed_eastern'].mean()
                     - zz.loc[~zz.eastern_dst, 'expected_shift_fixed_eastern'].mean())
        r = {'subset': sname, 'zone': zname, 'n_summer': len(zs), 'n_winter': len(zw),
             'zone_median_summer': round(float(np.median(zs)), 2), 'zone_median_winter': round(float(np.median(zw)), 2),
             'zone_mean_summer': round(float(zs.mean()), 2), 'zone_mean_winter': round(float(zw.mean()), 2),
             'eastern_median_summer': round(float(np.median(es)), 2), 'eastern_median_winter': round(float(np.median(ew)), 2),
             'expected_DiD_H_local': 0.0, 'expected_DiD_H_fixed_clock': round(float(exp_fixed), 2)}
        for label, fn in (('mean', np.mean), ('median', np.median)):
            obs = did_stat(fn, zs, zw, es, ew)
            bs = np.array([did_stat(fn, RNG.choice(zs, len(zs)), RNG.choice(zw, len(zw)),
                                    RNG.choice(es, len(es)), RNG.choice(ew, len(ew))) for _ in range(B_FAST)])
            # permutation of the zone's season labels (H0: no seasonal shift relative to Eastern)
            pooled = np.concatenate([zs, zw])
            eastern_part = fn(es) - fn(ew)
            perm = np.empty(B_FAST)
            for b in range(B_FAST):
                p = RNG.permutation(pooled)
                perm[b] = (fn(p[:len(zs)]) - fn(p[len(zs):])) - eastern_part
            r[f'DiD_{label}'] = round(float(obs), 2)
            r[f'DiD_{label}_lo'], r[f'DiD_{label}_hi'] = np.round(np.percentile(bs, [2.5, 97.5]), 2)
            r[f'DiD_{label}_perm_p_two_sided'] = round(float((np.abs(perm) >= abs(obs) - 1e-12).mean()), 4)
        arows.append(r)
az_tab = out(pd.DataFrame(arows), 'nodst_did')
print(az_tab.to_string(index=False))

# ============================================================================================
# A5. Weekday / weekend, help-desk hours, owners
# ============================================================================================
banner('A5. Day of week and help-desk hour structure')
DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
dz = pd.crosstab(cases.zone, cases.dow).reindex(index=zones_present, columns=range(7), fill_value=0)
dz.columns = DOW
dz['tickets'] = dz.sum(axis=1)
for d in DOW:
    dz[f'share_{d}'] = (dz[d] / dz.tickets).round(4)
dz['weekend_share'] = ((dz.Sat + dz.Sun) / dz.tickets).round(4)
out(dz.reset_index(), 'weekday_by_zone')
fact('A5', 'weekend_tickets', int((~cases.weekday).sum()))
fact('A5', 'weekend_share', round(float((~cases.weekday).mean()), 4))
fact('A5', 'weekday_tickets_before_07', int(((cases.hf < 7) & cases.weekday).sum()))
fact('A5', 'all_tickets_before_07', int((cases.hf < 7).sum()))
fact('A5', 'opened_seconds_nonzero', int((opened.dt.second != 0).sum()))
fact('A5', 'opened_minute_00_share', round(float((opened.dt.minute == 0).mean()), 4))
fact('A5', 'opened_minute_heaping_00_15_30_45_share', round(float(opened.dt.minute.isin([0, 15, 30, 45]).mean()), 4))

# Owners (pseudonymised by volume rank): shift windows on the recorded clock
owner = raw['Case Owner'].map(lambda x: None if x is None else str(x).strip())
rank = {o: f'Owner {i:02d}' for i, o in enumerate(owner.value_counts().index, 1)}
cases['owner'] = owner.map(rank).fillna('[blank]')
orows = []
for o, g in cases.groupby('owner'):
    if len(g) < 30:
        continue
    w = g[g.weekday]
    orows.append({'owner': o, 'tickets': len(g), 'weekend_tickets': int((~g.weekday).sum()),
                  'weekday_min_hour': round(float(w.hf.min()), 2), 'weekday_p01': round(float(w.hf.quantile(.01)), 2),
                  'weekday_p05': round(float(w.hf.quantile(.05)), 2), 'weekday_median': round(float(w.hf.median()), 2),
                  'weekday_p95': round(float(w.hf.quantile(.95)), 2), 'weekday_p99': round(float(w.hf.quantile(.99)), 2),
                  'weekday_share_before_07': round(float((w.hf < 7).mean()), 4),
                  'share_eastern_hospitals': round(float((g.zone == 'Eastern').mean()), 3),
                  'share_monitoring_template': round(float(g.mon_template.mean()), 3),
                  'open_status_tickets': int((g.status == 'Dispatch').sum())})
own_tab = out(pd.DataFrame(orows).sort_values('tickets', ascending=False), 'owner_shift_windows')
print(own_tab.to_string(index=False))
fact('A5', 'distinct_owners', int(owner.nunique()))

# US holidays (desk closures would show as near-zero weekday volume)
HOL = {'2025-09-01': 'Labor Day', '2025-11-27': 'Thanksgiving', '2025-11-28': 'Day after Thanksgiving',
       '2025-12-24': 'Christmas Eve', '2025-12-25': 'Christmas', '2026-01-01': 'New Year', '2026-01-19': 'MLK Day',
       '2026-02-16': 'Presidents Day', '2026-05-25': 'Memorial Day', '2026-07-03': 'Independence Day (observed)'}
daily = cases.groupby(cases.opened.dt.strftime('%Y-%m-%d')).size()
wk_days = pd.date_range('2025-08-01', '2026-08-31', freq='B').strftime('%Y-%m-%d')
daily_wk = daily.reindex(wk_days, fill_value=0)
hrows = [{'date': d, 'holiday': h, 'tickets': int(daily.get(d, 0)),
          'median_weekday_tickets': float(daily_wk.drop(list(HOL), errors='ignore').median())} for d, h in HOL.items()]
out(pd.DataFrame(hrows), 'holidays')

# ============================================================================================
# B. Close timestamps
# ============================================================================================
banner('B. Close timestamps')
ctypes = raw['Trouble Closed Date/Time'].map(lambda v: type(v).__name__)
fact('B', 'closed_value_types', ctypes.value_counts().to_dict())
txt = raw['Trouble Closed Date/Time'][ctypes == 'str']
fact('B', 'closed_text_values', {cases.case_id[i]: v for i, v in txt.items()})
fact('B', 'closed_text_value_status', cases.loc[txt.index, 'status'].tolist())
fact('B', 'closed_missing_by_status', cases.loc[closed.isna(), 'status'].value_counts().to_dict())
fact('B', 'status_counts', cases.status.value_counts().to_dict())
fact('B', 'closed_present_by_status', cases.loc[closed.notna(), 'status'].value_counts().to_dict())
fact('B', 'closed_seconds_nonzero', int((closed.dropna().dt.second != 0).sum()))
dur = (closed - opened).dt.total_seconds() / 3600
cases['dur_h'] = dur
d = dur.dropna()
fact('B', 'durations_n', len(d))
fact('B', 'durations_negative', int((d < 0).sum()))
fact('B', 'durations_zero', int((d == 0).sum()))
fact('B', 'durations_under_1h_positive', int(((d > 0) & (d < 1)).sum()))
drow = [{'group': 'all_closed', **{f'p{int(q * 100):02d}_hours': round(float(d.quantile(q)), 2)
                                   for q in (.01, .05, .10, .25, .5, .75, .90, .95, .99)},
         'n': len(d), 'max_hours': round(float(d.max()), 1)}]
for g, s in cases[cases.dur_h.notna()].groupby('service_group'):
    drow.append({'group': f'service_group={g}', **{f'p{int(q * 100):02d}_hours': round(float(s.dur_h.quantile(q)), 2)
                                                     for q in (.01, .05, .10, .25, .5, .75, .90, .95, .99)},
                 'n': len(s), 'max_hours': round(float(s.dur_h.max()), 1)})
out(pd.DataFrame(drow), 'close_duration_quantiles')
labels = ['negative', 'zero', '(0,1h)', '[1,4h)', '[4,24h)', '[1,3d)', '[3,7d)', '[7,30d)', '>=30d']
dbin = pd.cut(d, bins=[-np.inf, 0, 1e-9, 1, 4, 24, 72, 168, 720, np.inf], labels=labels, right=False)
dcount = dbin.value_counts().reindex(labels)
out(pd.DataFrame({'duration_bin': labels, 'tickets': dcount.to_numpy()}), 'close_duration_bins')
zero = cases[cases.dur_h == 0]
fact('B', 'zero_duration_by_service_group', zero.service_group.value_counts().to_dict())
fact('B', 'zero_duration_by_record_type', zero.record_type.value_counts().to_dict())
fact('B', 'zero_duration_by_category', zero.category.fillna('[NULL]').value_counts().to_dict())

# Minute heaping: system timestamps ~uniform over minutes; hand-typed times heap on :00/:15/:30/:45
mh = []
for label, s in (('opened', opened), ('closed', closed.dropna())):
    m = s.dt.minute
    mh.append({'timestamp': label, 'n': len(s), 'share_minute_00': round(float((m == 0).mean()), 4),
               'share_minute_30': round(float((m == 30).mean()), 4),
               'share_quarter_hours': round(float(m.isin([0, 15, 30, 45]).mean()), 4),
               'share_multiple_of_5': round(float((m % 5 == 0).mean()), 4),
               'uniform_expectation_quarter_hours': round(4 / 60, 4), 'uniform_expectation_multiple_of_5': round(12 / 60, 4)})
out(pd.DataFrame(mh), 'minute_heaping')

# Batch-closure clustering: identical close minute shared by several tickets
cc = closed.dropna().value_counts()
oc = opened.value_counts()
fact('B', 'distinct_close_minutes', len(cc))
fact('B', 'close_minutes_shared_by_2plus', int((cc >= 2).sum()))
fact('B', 'tickets_in_shared_close_minutes', int(cc[cc >= 2].sum()))
fact('B', 'max_tickets_one_close_minute', int(cc.max()))
fact('B', 'open_minutes_shared_by_2plus (baseline)', int((oc >= 2).sum()))
fact('B', 'tickets_in_shared_open_minutes (baseline)', int(oc[oc >= 2].sum()))
shared = cases[cases.closed.isin(cc[cc >= 2].index)]
grp = shared.groupby('closed').agg(n=('case_id', 'size'), machines=('machine_id', 'nunique'),
                                   customers=('customer', 'nunique'), owners=('owner', 'nunique'),
                                   same_open_minute=('opened', 'nunique'))
fact('B', 'shared_close_groups_same_machine', int((grp.machines == 1).sum()))
fact('B', 'shared_close_groups_same_customer', int((grp.customers == 1).sum()))
fact('B', 'shared_close_groups_also_same_open_minute', int((grp.same_open_minute == 1).sum()))
fact('B', 'shared_close_groups_spanning_2plus_customers', int((grp.customers > 1).sum()))
# Daily closing volume spikes (possible batch clean-up days)
cday = closed.dropna().dt.strftime('%Y-%m-%d').value_counts()
fact('B', 'close_days_top5', cday.head(5).to_dict())
fact('B', 'close_per_day_median', float(cday.median()))
fact('B', 'closed_after_last_opened_ticket', int((closed > EXPORT_LAST_OPEN).sum()))
fact('B', 'closed_weekend_share', round(float((closed.dropna().dt.dayofweek >= 5).mean()), 4))
fact('B', 'closed_before_07_share', round(float((closed.dropna().dt.hour < 7).mean()), 4))

# Close-hour by zone (weekday closes): a second, independent clock test
cl = cases[cases.closed.notna() & (cases.closed.dt.dayofweek < 5) & (cases.dur_h > 0)].copy()
cl['chf'] = cl.closed.dt.hour + cl.closed.dt.minute / 60
crow = []
ce = cl.loc[cl.zone == 'Eastern', 'chf'].to_numpy()
for zname in zones_present:
    zz = cl[cl.zone == zname]
    r = {'zone': zname, **qstats(zz.chf)}
    if zname != 'Eastern' and len(zz) >= 5:
        r.update({k: v for k, v in compare(zz.chf.to_numpy(), ce, ks_reps=0).items()
                  if k in ('median_diff', 'median_diff_lo', 'median_diff_hi', 'qa_shift', 'qa_shift_lo', 'qa_shift_hi',
                           'ks_shift')})
        r['expected_shift_H_fixed_clock_mean'] = round(float(zz.expected_shift_fixed_eastern.mean()), 2)
    crow.append(r)
close_zone = out(pd.DataFrame(crow), 'close_hour_by_zone')
print(close_zone[['zone', 'n', 'p10', 'p50', 'p90', 'median_diff', 'qa_shift', 'ks_shift',
                  'expected_shift_H_fixed_clock_mean']].to_string(index=False))

# Tech ETA appointment times typed into Administrative Notes (text clock) vs zone, and vs close time
ETA_RE = re.compile(r'\beta\b[^0-9]{0,15}(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\s*([AP]M)', re.I)
erows = []
for i, t in notes.items():
    for m in ETA_RE.finditer(t):
        mo, da, yr, hh, mi, ap = m.groups()
        try:
            hh = int(hh) % 12 + (12 if ap.upper() == 'PM' else 0)
            when = dt.datetime(int(yr), int(mo), int(da), hh, int(mi))
        except ValueError:
            continue
        erows.append({'idx': i, 'eta': when})
eta = pd.DataFrame(erows)
fact('B', 'eta_stamps_parsed', len(eta))
if len(eta):
    eta = eta.merge(cases[['zone', 'closed', 'opened']], left_on='idx', right_index=True)
    eta['eta_hf'] = eta.eta.dt.hour + eta.eta.dt.minute / 60
    # last ETA per ticket on the close date: close minus ETA (hours)
    same = eta[eta.eta.dt.date == eta.closed.dt.date].sort_values('eta').groupby('idx').tail(1)
    same = same.assign(close_minus_eta=(same.closed - same.eta).dt.total_seconds() / 3600)
    erows2 = []
    for zname in zones_present:
        a = eta[eta.zone == zname]
        b = same[same.zone == zname]
        if len(a) == 0:
            continue
        erows2.append({'zone': zname, 'eta_stamps': len(a), 'eta_hour_median': round(float(a.eta_hf.median()), 2),
                       'eta_hour_p10': round(float(a.eta_hf.quantile(.1)), 2),
                       'eta_hour_p90': round(float(a.eta_hf.quantile(.9)), 2),
                       'tickets_eta_on_close_date': len(b),
                       'close_minus_eta_median_h': round(float(b.close_minus_eta.median()), 2) if len(b) else None,
                       'close_minus_eta_p25_h': round(float(b.close_minus_eta.quantile(.25)), 2) if len(b) else None,
                       'close_minus_eta_p75_h': round(float(b.close_minus_eta.quantile(.75)), 2) if len(b) else None})
    eta_tab = out(pd.DataFrame(erows2), 'eta_vs_close_by_zone')
    print(eta_tab.to_string(index=False))

# ============================================================================================
# C. Field-update timing
# ============================================================================================
banner('C. Field population: open (Dispatch) vs closed tickets, and by age at export')
FIELDS = {'Trouble Code': 'trouble_code', 'Trouble Code Category': 'category',
          'Trouble Code Sub Category': 'subcategory', 'Trouble Resolution': None, 'Administrative Notes': None,
          'Dispatch #': None, 'Case Owner': None, 'Model #': 'model', 'Product Name': 'product',
          'Case Record Type': 'record_type', 'Trouble Reported': None, 'Serial #': None,
          'Trouble Closed Date/Time': None}


def present(col):
    return raw[col].map(lambda x: x is not None and str(x).strip() != '')


pres = pd.DataFrame({f: present(f) for f in FIELDS})
cases['is_open'] = cases.status == 'Dispatch'
cases['age_days'] = (EXPORT_REF - cases.opened).dt.total_seconds() / 86400
AGE_BINS = [0, 7, 30, 90, 10_000]
AGE_LAB = ['<7d', '7-30d', '30-90d', '>=90d']
cases['age_bin'] = pd.cut(cases.age_days, AGE_BINS, labels=AGE_LAB, right=False)
frows = []
groups = {'open (Status=Dispatch)': cases.is_open, 'closed (all other statuses)': ~cases.is_open,
          'Trouble Closed': cases.status == 'Trouble Closed',
          'other closed (Ricoh-Closed/Closed/Case Closed)': cases.status.isin(['Ricoh-Closed', 'Closed', 'Case Closed'])}
for lab in AGE_LAB:
    groups[f'age {lab} (all statuses)'] = cases.age_bin == lab
    groups[f'age {lab} Trouble Closed only'] = (cases.age_bin == lab) & (cases.status == 'Trouble Closed')
for gname, gm in groups.items():
    r = {'group': gname, 'tickets': int(gm.sum()), 'open_tickets': int((gm & cases.is_open).sum())}
    for f in FIELDS:
        r[f] = round(float(pres.loc[gm, f].mean()), 4) if gm.sum() else None
    frows.append(r)
ftab = out(pd.DataFrame(frows), 'field_fill_rates')
print(ftab.T.to_string())
fact('C', 'other_closed_statuses_by_month',
     {s: cases[cases.status == s].opened.dt.strftime('%Y-%m').value_counts().sort_index().to_dict()
      for s in ('Ricoh-Closed', 'Closed', 'Case Closed')})
fact('C', 'record_type_open_vs_recent_trouble_closed (<20d)',
     {'open': cases[cases.is_open].record_type.value_counts().to_dict(),
      'trouble_closed_lt20d': cases[(cases.status == 'Trouble Closed') & (cases.age_days < 20)].record_type.value_counts().to_dict()})
fact('C', 'owner_10_months', cases[cases.owner == 'Owner 10'].opened.dt.strftime('%Y-%m').value_counts().to_dict())
fact('C', 'open_ticket_age_days_quantiles',
     {q: round(float(cases.loc[cases.is_open, 'age_days'].quantile(q)), 1) for q in (0, .25, .5, .75, 1)})
fact('C', 'open_tickets_by_month', cases[cases.is_open].opened.dt.strftime('%Y-%m').value_counts().sort_index().to_dict())
fact('C', 'open_tickets_record_type', cases[cases.is_open].record_type.value_counts().to_dict())
fact('C', 'open_tickets_with_trouble_code', int(cases[cases.is_open].trouble_code.notna().sum()))
fact('C', 'trouble_closed_without_trouble_code', int(((cases.status == 'Trouble Closed') & cases.trouble_code.isna()).sum()))
# Owner continuity: do open tickets sit with the same owners that close tickets?
open_owners = set(cases.loc[cases.is_open, 'owner'])
closed_owner_counts = cases.loc[~cases.is_open, 'owner'].value_counts()
fact('C', 'open_ticket_owners', cases.loc[cases.is_open, 'owner'].value_counts().to_dict())
fact('C', 'open_owners_never_on_closed_tickets', sorted(o for o in open_owners if o not in closed_owner_counts))
# Dispatch # population by record type and open/closed
disp = pd.crosstab([cases.record_type.fillna('[NULL]'), cases.is_open.map({True: 'open', False: 'closed'})],
                   pres['Dispatch #'], margins=False)
disp.columns = [f'dispatch_present_{c}' for c in disp.columns]
out(disp.reset_index(), 'dispatch_by_record_type')
# Is Dispatch # presence an outcome (tech dispatched) rather than an intake attribute?
tcl = cases[cases.status == 'Trouble Closed'].assign(dispatch=pres['Dispatch #'])
drows2 = []
for has, g in tcl.groupby('dispatch'):
    drows2.append({'dispatch_number_present': bool(has), 'tickets': len(g),
                   'median_open_to_close_h': round(float(g.dur_h.median()), 2),
                   'share_closed_within_4h': round(float((g.dur_h < 4).mean()), 4),
                   'share_No_Trouble_Found': round(float((g.category == 'No Trouble Found').mean()), 4),
                   'share_FCR_in_trouble_reported': round(float(reported[g.index].str.contains(r'\bFCR\b', case=False).mean()), 4),
                   'share_service_group_planned': round(float((g.service_group == 'Planned work').mean()), 4),
                   'top_trouble_codes': g.trouble_code.fillna('[NULL]').value_counts().head(4).to_dict()})
out(pd.DataFrame(drows2), 'dispatch_vs_outcome')
young = cases.age_days < 1.0                  # opened within ~24h of the export reference time
fact('C', 'dispatch_present_on_tickets_opened_last_24h_by_status',
     pd.crosstab(cases.status[young], pres['Dispatch #'][young]).to_dict('index'))
fact('C', 'dispatch_absent_trouble_closed_by_record_type',
     cases[(cases.status == 'Trouble Closed') & ~pres['Dispatch #']].record_type.fillna('[NULL]').value_counts().to_dict())

# ---- Administrative Notes: parse entry date stamps -------------------------------------------
STAMP_RE = re.compile(r'(?<![\d/.:])(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?(?![\d/])')


def infer_date(mo, da, yr, ref):
    mo, da = int(mo), int(da)
    if not (1 <= mo <= 12 and 1 <= da <= 31):
        return None
    if yr:
        y = int(yr) + (2000 if len(yr) == 2 else 0)
        try:
            return dt.date(y, mo, da)
        except ValueError:
            return None
    best = None
    for y in (ref.year - 1, ref.year, ref.year + 1):
        try:
            c = dt.date(y, mo, da)
        except ValueError:
            continue
        if best is None or abs((c - ref).days) < abs((best - ref).days):
            best = c
    return best


nrows = []
for i, t in notes.items():
    if not t.strip():
        continue
    ref = cases.opened.iat[i].date()
    entry, full = [], []
    for m in STAMP_RE.finditer(t):
        pre = t[max(0, m.start() - 12):m.start()].lower()
        dd = infer_date(m.group(1), m.group(2), m.group(3), ref)
        if dd is None:
            continue
        if m.group(3):
            full.append((dd, 'eta' in pre))
        else:
            entry.append(dd)
    cdate = cases.closed.iat[i].date() if pd.notna(cases.closed.iat[i]) else None
    r = {'idx': i, 'n_entry': len(entry), 'n_full': len(full)}
    if entry:
        deltas = [(x - ref).days for x in entry]
        r.update({'min_delta': min(deltas), 'max_delta': max(deltas), 'first_written_delta': deltas[0],
                  'last_written_delta': deltas[-1],
                  'desc_order': all(a >= b for a, b in zip(entry, entry[1:])) if len(entry) > 1 else None,
                  'asc_order': all(a <= b for a, b in zip(entry, entry[1:])) if len(entry) > 1 else None,
                  'after_close': (max(entry) > cdate) if cdate else None,
                  'max_minus_close': (max(entry) - cdate).days if cdate else None})
    nonEta = [x for x, is_eta in full if not is_eta]
    if entry or nonEta:
        r['any_after_open_incl_full_dates'] = max([(x - ref).days for x in entry + nonEta]) > 0
    nrows.append(r)
nd = pd.DataFrame(nrows).set_index('idx')
nd = nd.join(cases[['is_open', 'status', 'service_group', 'age_days']])
withstamp = nd[nd.n_entry > 0]
srow = []
for gname, g in (('all notes', withstamp), ('open tickets', withstamp[withstamp.is_open]),
                 ('closed tickets', withstamp[~withstamp.is_open])):
    srow.append({'group': gname, 'notes_present': int(len(nd[nd.is_open == (gname == 'open tickets')]) if gname != 'all notes' else len(nd)),
                 'notes_with_entry_stamp': len(g),
                 'share_any_stamp_after_open_date': round(float((g.max_delta > 0).mean()), 4),
                 'share_any_stamp_2plus_days_after_open': round(float((g.max_delta >= 2).mean()), 4),
                 'share_earliest_stamp_on_open_date': round(float((g.min_delta == 0).mean()), 4),
                 'share_earliest_stamp_before_open_date': round(float((g.min_delta < 0).mean()), 4),
                 'share_all_stamps_on_open_date': round(float(((g.min_delta == 0) & (g.max_delta == 0)).mean()), 4),
                 'median_latest_stamp_days_after_open': float(g.max_delta.median()),
                 'p90_latest_stamp_days_after_open': float(g.max_delta.quantile(.9)),
                 'share_latest_stamp_after_close_date': round(float(g.after_close.dropna().astype(bool).mean()), 4)
                 if g.after_close.notna().any() else None,
                 'multi_stamp_notes': int(g.desc_order.notna().sum()),
                 'share_multi_newest_first': round(float(g.desc_order.dropna().astype(bool).mean()), 4)
                 if g.desc_order.notna().any() else None,
                 'share_multi_oldest_first': round(float(g.asc_order.dropna().astype(bool).mean()), 4)
                 if g.asc_order.notna().any() else None})
notes_tab = out(pd.DataFrame(srow), 'notes_dates')
print(notes_tab.T.to_string())
fact('C', 'notes_present', int(len(nd)))
fact('C', 'notes_with_any_parsed_stamp', int(((nd.n_entry > 0) | (nd.n_full > 0)).sum()))
fact('C', 'notes_any_date_after_open_incl_full_dates_non_eta',
     int(nd.any_after_open_incl_full_dates.fillna(False).astype(bool).sum()))
fact('C', 'notes_present_but_no_entry_stamp', int((nd.n_entry == 0).sum()))
fact('C', 'notes_entry_stamp_delta_days_distribution_latest',
     withstamp.max_delta.clip(-5, 60).value_counts().sort_index().head(15).to_dict())

# ---- Trouble Reported vs Trouble Resolution: resolution vocabulary (counts only) -----------
WORDS = {'replace*': r'\breplac(?:e|ed|es|ing|ement)\b', 'resolve*': r'\bresolv(?:e|ed|es|ing)\b',
         'repaired/repairing': r'\brepair(?:ed|ing)\b', 'fixed': r'\bfixed\b', 'tech/technician': r'\btech(?:nician)?s?\b',
         'onsite/on site': r'\bon\s*-?\s*site\b', 'completed': r'\bcomplet(?:e|ed)\b', 'FCR (first-call troubleshooting)': r'\bFCR\b',
         'reboot/reset': r'\brebo+t(?:ed|ing)?\b|\breset\b', 'did not clear / no obstructions (intake triage)':
         r"\b(?:did\s*n[o']?t|does\s*not)\s+(?:clear|resolve)\b|\bno obstructions?\b",
         'call IPA once onsite (dispatch instruction)': r'\bcall ipa\b', 'past-tense repair phrase':
         r'\b(?:replaced|repaired|resolved|fixed|installed|adjusted)\b'}
wrows = []
for lab, rx in WORDS.items():
    a = reported.str.contains(rx, case=False, regex=True)
    b = resolution.str.contains(rx, case=False, regex=True)
    wrows.append({'pattern': lab, 'trouble_reported_tickets': int(a.sum()), 'trouble_reported_share': round(float(a.mean()), 4),
                  'trouble_reported_open_tickets': int((a & cases.is_open).sum()),
                  'trouble_resolution_tickets': int(b.sum()), 'trouble_resolution_share': round(float(b.mean()), 4)})
words = out(pd.DataFrame(wrows), 'reported_vs_resolution_vocabulary')
print(words.to_string(index=False))
rep_len = reported.str.len()
fact('C', 'trouble_reported_length_median_open_vs_closed',
     (float(rep_len[cases.is_open].median()), float(rep_len[~cases.is_open].median())))
# dates mentioned inside Trouble Reported relative to opening date
rep_after = 0
rep_dates = 0
for i, t in reported.items():
    ref = cases.opened.iat[i].date()
    ds = [infer_date(m.group(1), m.group(2), m.group(3), ref) for m in STAMP_RE.finditer(t)]
    ds = [x for x in ds if x]
    if ds:
        rep_dates += 1
        rep_after += int(max(ds) > ref)
fact('C', 'trouble_reported_with_date_mentions', rep_dates)
fact('C', 'trouble_reported_with_date_after_open_date', rep_after)

# ============================================================================================
# D. Monitoring-originated tickets
# ============================================================================================
banner('D. Monitoring-originated tickets')
VARIANTS = {
    "starts 'Monitoring'/'Monitor' (proactive template)": r'^\W*monitor(?:ing)?\b',
    "'Monitoring - Daily' cadence tag": r'monitor(?:ing)?\s*-?\s*\[?\s*daily',
    "'(14 Days)'/'14 day' monitoring-window tag": r'\(?\s*14\s*-?\s*days?\s*\)?',
    "'Poll'/'Poll Position' slot tag": r'\bpoll(?:\s*position)?\s*:',
    "pipe-delimited template ('a | b | c')": r'\|',
    "pipe template ending in a system name (Clearview/Clarify/Canopy)": r'\|\s*(?:clear\s*view|clari\s*fy|canopy)[^|]*$',
    "'found ... during monitoring'": r'during monitoring',
    "mentions clearView": r'clear\s*-?\s*view',
    "mentions clariFy": r'clari\s*fy',
    "mentions Canopy": r'\bcanopy\b',
    "mentions IoT": r'\biot\b',
    "'error(s) in clearView/clariFy'": r'errors?\s+(?:\w+\s+){0,3}in\s+(?:clear\s*view|clari\s*fy)',
    "'not communicating/connecting/showing ... clearView'": r'(?:not|no)\s+(?:communicat\w*|connect\w*|show\w*|transactions?)\b.{0,40}clear\s*view',
    "explicit numeric error/code reference": CODE_REF_RE,
    "'Device FW: x.y.z' suffix (system-appended)": r'device\s*fw\s*:',
    "'All Errors/All Issues' scope tag": r'\ball\s+(?:errors|issues)\b',
    "'SAM' error family": r'\bsam\b',
    "'Power'/'Inactivity' issue tag": r'power issues|inactivity',
    "'Communication Issues' tag": r'communication issues',
    "'Deposit Door Errors' tag": r'deposit door errors',
    "'FCR' first-call troubleshooting": r'\bFCR\b',
}
vrows = []
for lab, rx in VARIANTS.items():
    m = reported.str.contains(rx, case=False, regex=True)
    vrows.append({'pattern_variant': lab, 'tickets': int(m.sum()),
                  'of_which_monitoring_template': int((m & cases.mon_template).sum()),
                  'of_which_telemetry_ui_mention': int((m & cases.telemetry_ui).sum())})
out(pd.DataFrame(vrows), 'monitoring_patterns')
fact('D', 'monitoring_template_tickets', int(cases.mon_template.sum()))
fact('D', 'telemetry_ui_mention_tickets', int(cases.telemetry_ui.sum()))
fact('D', 'template_or_ui_mention', int(cases.monitoring_any.sum()))
fact('D', 'template_and_ui_mention', int((cases.mon_template & cases.telemetry_ui).sum()))
fact('D', 'ui_mention_without_template', int((cases.telemetry_ui & ~cases.mon_template).sum()))
fact('D', 'code_reference_tickets', int(cases.code_ref.sum()))
fact('D', 'code_reference_not_template_or_ui', int((cases.code_ref & ~cases.monitoring_any).sum()))
fact('D', 'device_fw_suffix_tickets', int(cases.device_fw.sum()))
fact('D', 'sibling_proactive_definition_tickets', int(cases.proactive_sibling.sum()))
fact('D', 'sibling_vs_template_overlap', int((cases.proactive_sibling & cases.mon_template).sum()))
cases['mon_class'] = np.select(
    [cases.mon_template, cases.telemetry_ui & cases.code_ref, cases.telemetry_ui, cases.code_ref],
    ['A monitoring template', 'B telemetry UI + code number', 'C telemetry UI mention', 'D code number only'],
    'E customer/other')
fact('D', 'mon_class_counts', cases.mon_class.value_counts().sort_index().to_dict())
# Intake-template markers over time (process changes matter for a text classifier)
MARKERS = {'monitoring template': cases.mon_template, 'mentions clearView': reported.str.contains(r'clear\s*-?\s*view', case=False),
           'mentions clariFy': reported.str.contains(r'clari\s*fy', case=False),
           'mentions Canopy': reported.str.contains(r'\bcanopy\b', case=False),
           'numeric code reference': cases.code_ref, 'Device FW suffix': cases.device_fw,
           'FCR': reported.str.contains(r'\bFCR\b', case=False), 'pipe-delimited': reported.str.contains(r'\|')}
mk = pd.DataFrame(MARKERS).astype(int).assign(month=cases.opened.dt.strftime('%Y-%m')).groupby('month').agg(['sum', 'mean'])
mk.columns = [f'{a} ({"n" if b == "sum" else "share"})' for a, b in mk.columns]
mk.insert(0, 'tickets', cases.groupby(cases.opened.dt.strftime('%Y-%m')).size())
out(mk.round(3).reset_index(), 'text_markers_by_month')
fact('D', 'markers_on_open_tickets', {k: round(float(v[cases.is_open].mean()), 3) for k, v in MARKERS.items()})
fact('D', 'first_month_device_fw', cases.loc[cases.device_fw, 'opened'].min().strftime('%Y-%m-%d'))
by_month = pd.crosstab(cases.opened.dt.strftime('%Y-%m'), cases.mon_class)
by_month['all'] = by_month.sum(axis=1)
out(by_month.reset_index().rename(columns={'opened': 'month', 'row_0': 'month'}), 'monitoring_by_month')
for dim, col in (('model', 'model'), ('record_type', 'record_type'), ('trouble_code', 'trouble_code'),
                 ('category', 'category'), ('service_group', 'service_group'), ('status', 'status'),
                 ('zone', 'zone'), ('owner', 'owner')):
    t = pd.crosstab(cases[col].fillna('[NULL]'), cases.mon_class)
    t['all'] = t.sum(axis=1)
    for c in [c for c in t.columns if c != 'all']:
        t[f'share_{c.split()[0]}'] = (t[c] / t['all']).round(3)
    t = t.sort_values('all', ascending=False)
    out(t.reset_index().rename(columns={col: dim}), f'monitoring_by_{dim}')
# opening-hour profile of monitoring tickets (desk-driven control)
mq = pd.DataFrame([{'class': c, **qstats(g.hf), 'weekend_share': round(float((~g.weekday).mean()), 4),
                    'share_eastern_hospitals': round(float((g.zone == 'Eastern').mean()), 3)}
                   for c, g in cases.groupby('mon_class')])
out(mq, 'monitoring_open_hour')
print(mq.to_string(index=False))
# Same-machine timing: monitoring tickets followed/preceded by another ticket on the same machine within 7 days
cs = cases.sort_values(['machine_id', 'opened'])
cs['prev_gap_d'] = cs.groupby('machine_id').opened.diff().dt.total_seconds() / 86400
cs['next_gap_d'] = -cs.groupby('machine_id').opened.diff(-1).dt.total_seconds() / 86400
arows2 = []
for c, g in cs.groupby('mon_class'):
    arows2.append({'class': c, 'tickets': len(g),
                   **{f'share_prev_same_machine_within_{k}d': round(float((g.prev_gap_d <= k).mean()), 4) for k in (7, 14)},
                   **{f'share_next_same_machine_within_{k}d': round(float((g.next_gap_d <= k).mean()), 4) for k in (7, 14)}})
out(pd.DataFrame(arows2), 'monitoring_adjacent_tickets')

# ============================================================================================
# E. Pilot implications
# ============================================================================================
banner('E. Pilot anchor conversions (cells 8/34)')
PILOT = ['T00705', 'T00783', 'T00951', 'T00957', 'T01157', 'T01287', 'T01629', 'T01795', 'T01796', 'T01797',
         'T02128', 'T02229', 'T02268', 'T03075', 'T03079', 'T03326', 'T03959', 'T04699', 'T04907', 'T05185',
         'T05506', 'T05683', 'T05924', 'T06107', 'T06354', 'T06445', 'T06663', 'T06672', 'T06712', 'T06912']
NO_TX = {'T01629', 'T03959', 'T05506', 'T05683'}
pil = cases[cases.case_id.isin(PILOT)].copy()
assert len(pil) == 30
CHI = 'America/Chicago'
prow = []
for r in pil.itertuples():
    t = r.opened.to_pydatetime()
    off_e, off_c, off_h = utc_off(NY, t), utc_off(CHI, t), r.off_hosp
    prow.append({'case_id': r.case_id, 'opened_at': r.opened_at, 'zone': r.zone, 'season': r.season,
                 'trouble_code': r.trouble_code, 'monitoring_class': r.mon_class,
                 'zac_window_empty': r.case_id in NO_TX,
                 # correction to ADD to the recorded opened_at to express it on the telemetry clock
                 'add_h_if_case_Eastern_tel_UTC': -off_e, 'add_h_if_case_Eastern_tel_machine_local': off_h - off_e,
                 'add_h_if_case_Central_tel_UTC': -off_c, 'add_h_if_case_Central_tel_machine_local': off_h - off_c})
ptab = out(pd.DataFrame(prow).sort_values('case_id'), 'pilot_anchor_conversions')
print(ptab.to_string(index=False))
corr_cols = [c for c in ptab.columns if c.startswith('add_h_')]
fact('E', 'pilot_zones', ptab.zone.value_counts().to_dict())
fact('E', 'pilot_seasons', ptab.season.value_counts().to_dict())
fact('E', 'pilot_max_abs_correction_h', float(ptab[corr_cols].abs().max().max()))
fact('E', 'population_correction_range_case_Eastern_tel_local',
     (float((cases.off_hosp - cases.off_east).min()), float((cases.off_hosp - cases.off_east).max())))
fact('E', 'population_correction_range_case_Eastern_tel_UTC', (float(-cases.off_east.max()), float(-cases.off_east.min())))
# The three tickets whose last-five codes the notebook printed (cell 34; values transcribed from its output)
PRINTED = {'T00705': [('43', '2025-09-07 16:03:14'), ('11', '2025-09-05 16:09:03'), ('03', '2025-09-04 15:16:19'),
                      ('34', '2025-09-03 23:49:29'), ('25', '2025-09-03 18:40:22')],
           'T00783': [('03', '2025-09-10 13:18:50'), ('77', '2025-09-09 12:29:51'), ('32', '2025-09-09 10:28:53'),
                      ('17', '2025-09-09 10:28:39'), ('11', '2025-09-02 10:12:00')],
           'T00951': [('19', '2025-09-18 23:24:49'), ('20', '2025-09-18 20:59:32'), ('01', '2025-09-18 12:09:58'),
                      ('04', '2025-09-18 12:04:00'), ('79', '2025-09-10 14:39:34')]}
grow = []
for cid, codes in PRINTED.items():
    r = ptab.set_index('case_id').loc[cid]
    a = pd.Timestamp(r.opened_at)
    for rank_, (code, seen) in enumerate(codes, 1):
        gap = (a - pd.Timestamp(seen)).total_seconds() / 3600
        row = {'case_id': cid, 'zone': r.zone, 'season': r.season, 'recency_rank': rank_, 'code': code,
               'hours_before_recorded_open': round(gap, 2)}
        for c in corr_cols:
            # code stays in the 30-day window iff last_seen < corrected anchor
            row[f'kept_{c[6:]}'] = bool(gap + r[c] > 0)
        grow.append(row)
gtab = out(pd.DataFrame(grow), 'pilot_last_seen_gaps')
print(gtab.to_string(index=False))
# Population: hours to ADD to opened_at under each (case clock, telemetry clock) hypothesis
crow2 = []
for clock, tzname in (('Eastern', NY), ('Central', CHI)):
    off_clock = np.array([utc_off(tzname, t.to_pydatetime()) for t in opened])
    for tel, add in (('UTC', -off_clock), ('machine-local', cases.off_hosp.to_numpy() - off_clock)):
        vc = pd.Series(add).value_counts().sort_index()
        for h, n in vc.items():
            crow2.append({'case_clock': f'US {clock} (DST-observing)', 'telemetry_clock': tel, 'add_hours': h,
                          'tickets': int(n), 'share': round(float(n / len(cases)), 4)})
corr = out(pd.DataFrame(crow2), 'anchor_correction_distribution')
print(corr.to_string(index=False))
fact('E', 'max_abs_correction_any_hypothesis_h', float(corr.add_hours.abs().max()))

# ============================================================================================
# C (summary). Field availability classification for an at-opening classifier
# ============================================================================================
banner('C. Field availability classification')
fr = ftab.set_index('group')
OPEN, CLOSED = 'open (Status=Dispatch)', 'closed (all other statuses)'
pct = lambda f, g: f'{100 * fr.loc[g, f]:.1f}%'
nall = notes_tab.set_index('group').loc['all notes']
vocab = words.set_index('pattern')
young_disp = pd.crosstab(cases.status[young], pres['Dispatch #'][young])
young_n, young_with = int(young_disp.to_numpy().sum()), int(young_disp.get(True, pd.Series(dtype=int)).sum())
classes = [
    ('Trouble Reported', 'available at open (intake text; may carry first-call troubleshooting)',
     f"present {pct('Trouble Reported', OPEN)} open / {pct('Trouble Reported', CLOSED)} closed; past-tense repair words "
     f"{100 * vocab.loc['past-tense repair phrase', 'trouble_reported_share']:.1f}% vs "
     f"{100 * vocab.loc['past-tense repair phrase', 'trouble_resolution_share']:.1f}% in Trouble Resolution; 'FCR' in "
     f"{100 * vocab.loc['FCR (first-call troubleshooting)', 'trouble_reported_share']:.1f}% (on {int(vocab.loc['FCR (first-call troubleshooting)', 'trouble_reported_open_tickets'])}/64 open tickets); "
     f"'Device FW' suffix on {100 * cases.loc[cases.is_open, 'device_fw'].mean():.0f}% of open tickets; dates after the opening date in "
     f"{rep_after} tickets. Edit history not in export.", 'Target leakage risk: telemetry codes typed into text (see D)'),
    ('Model # / Product Name / Serial #', 'available at open (asset attributes)',
     f"present 100% open and closed", 'value at export; asset reassignment not visible'),
    ('Case Record Type', 'available at open (likely)', 'present 100% open and closed; open tickets are all device record types',
     'General Case/Install Case never carry a Dispatch #'),
    ('Case Owner', 'available at open, value is owner at export',
     f"present 100%; 6 owners hold the 64 open tickets, all also own closed tickets", 'reassignment history not in export; not a sensible feature'),
    ('Dispatch #', 'assigned early but outcome-correlated (do not use as a feature)',
     f"present {pct('Dispatch #', OPEN)} open / {pct('Dispatch #', CLOSED)} closed; {young_with}/{young_n} tickets opened in the last 24h already "
     f"have one; never on General/Install Case; absent tickets close slower and are more often No Trouble Found",
     'presence encodes record type and whether a technician was dispatched'),
    ('Trouble Code', 'filled at closure (label, not feature)', f"present {pct('Trouble Code', OPEN)} open / {pct('Trouble Code', CLOSED)} closed", ''),
    ('Trouble Code Category', 'filled at closure (label)', f"present {pct('Trouble Code Category', OPEN)} open / {pct('Trouble Code Category', CLOSED)} closed", ''),
    ('Trouble Code Sub Category', 'filled at closure (label)', f"present {pct('Trouble Code Sub Category', OPEN)} open / {pct('Trouble Code Sub Category', CLOSED)} closed", ''),
    ('Trouble Resolution', 'filled during/after the repair (leakage)', f"present {pct('Trouble Resolution', OPEN)} open / {pct('Trouble Resolution', CLOSED)} closed", ''),
    ('Administrative Notes', 'appended over the ticket life (leakage)',
     f"present {pct('Administrative Notes', OPEN)} open / {pct('Administrative Notes', CLOSED)} closed; of {int(nall.notes_with_entry_stamp)} dated notes, "
     f"{100 * nall.share_any_stamp_after_open_date:.1f}% contain an entry dated after the opening date, "
     f"{100 * nall.share_any_stamp_2plus_days_after_open:.1f}% 2+ days after; only {100 * nall.share_earliest_stamp_on_open_date:.1f}% start on the opening date; "
     f"{100 * nall.share_multi_newest_first:.1f}% of multi-entry notes are newest-first logs", ''),
    ('Trouble Closed Date/Time', 'filled at closure', f"present {pct('Trouble Closed Date/Time', OPEN)} open / {pct('Trouble Closed Date/Time', CLOSED)} closed (only Trouble Closed rows have it)", ''),
    ('Status', 'snapshot at export', 'open tickets are all Status=Dispatch, all opened 2026-08', ''),
]
out(pd.DataFrame(classes, columns=['field', 'classification', 'evidence', 'caveat']), 'field_timing_classification')

# ============================================================================================
# Hypothesis scorecard (filled from the computed tables above)
# ============================================================================================
wr_shift = stab[stab.subset == 'weekday_reactive'].set_index('zone')
mon_shift = stab[stab.subset == 'monitoring_template'].set_index('zone')
dst_full = dst_tab[(dst_tab.subset == 'weekday_reactive') & (dst_tab.window == 'full_season')].iloc[0]
az = az_tab[(az_tab.subset == 'all') & (az_tab.zone == 'Arizona (no DST)')].iloc[0]
pooled = az_tab[(az_tab.subset == 'all') & (az_tab.zone.str.startswith('no-DST'))].iloc[0]
score = [
    {'test': 'Pacific vs Eastern opening-hour shift, weekday reactive (KS-min, 95% CI)',
     'H_local': 0, 'H_fixed_DST_wall_clock': 3, 'H_UTC_or_nonDST_fixed': 3,
     'observed': f"{wr_shift.loc['Pacific', 'ks_shift']} [{wr_shift.loc['Pacific', 'ks_shift_lo']}, {wr_shift.loc['Pacific', 'ks_shift_hi']}]"},
    {'test': 'Central vs Eastern shift, weekday reactive (KS-min, 95% CI)',
     'H_local': 0, 'H_fixed_DST_wall_clock': 1, 'H_UTC_or_nonDST_fixed': 1,
     'observed': f"{wr_shift.loc['Central', 'ks_shift']} [{wr_shift.loc['Central', 'ks_shift_lo']}, {wr_shift.loc['Central', 'ks_shift_hi']}]"},
    {'test': 'Mountain vs Eastern shift, weekday reactive (KS-min, 95% CI)',
     'H_local': 0, 'H_fixed_DST_wall_clock': 2, 'H_UTC_or_nonDST_fixed': 2,
     'observed': f"{wr_shift.loc['Mountain', 'ks_shift']} [{wr_shift.loc['Mountain', 'ks_shift_lo']}, {wr_shift.loc['Mountain', 'ks_shift_hi']}]"},
    {'test': 'Desk-driven control: monitoring-template tickets, Pacific minus Eastern median hour (95% CI)',
     'H_local': -3, 'H_fixed_DST_wall_clock': 0, 'H_UTC_or_nonDST_fixed': 0,
     'observed': (f"{mon_shift.loc['Pacific', 'median_diff']} [{mon_shift.loc['Pacific', 'median_diff_lo']}, "
                  f"{mon_shift.loc['Pacific', 'median_diff_hi']}] (n={int(mon_shift.loc['Pacific', 'n'])})")},
    {'test': 'Desk-driven control: monitoring-template tickets, all non-Eastern minus Eastern median hour (95% CI)',
     'H_local': mon_shift.loc['non-Eastern pooled', 'expected_shift_H_local'], 'H_fixed_DST_wall_clock': 0,
     'H_UTC_or_nonDST_fixed': 0,
     'observed': (f"{mon_shift.loc['non-Eastern pooled', 'median_diff']} [{mon_shift.loc['non-Eastern pooled', 'median_diff_lo']}, "
                  f"{mon_shift.loc['non-Eastern pooled', 'median_diff_hi']}] (n={int(mon_shift.loc['non-Eastern pooled', 'n'])})")},
    {'test': 'Close timestamps (desk closes the record): Pacific minus Eastern median weekday close hour (95% CI)',
     'H_local': '-3 if desk-entered, 0 if tech-entered', 'H_fixed_DST_wall_clock': '0 if desk-entered, +3 if tech-entered',
     'H_UTC_or_nonDST_fixed': 'same as fixed',
     'observed': (f"{close_zone.set_index('zone').loc['Pacific', 'median_diff']} "
                  f"[{close_zone.set_index('zone').loc['Pacific', 'median_diff_lo']}, "
                  f"{close_zone.set_index('zone').loc['Pacific', 'median_diff_hi']}]")},
    {'test': 'Eastern hospitals: standard-time minus DST-time opening hours (KS-min, 95% CI)',
     'H_local': 0, 'H_fixed_DST_wall_clock': 0, 'H_UTC_or_nonDST_fixed': 1,
     'observed': f"{dst_full.ks_shift} [{dst_full.ks_shift_lo}, {dst_full.ks_shift_hi}]"},
    {'test': 'Weekday desk-opening edge hour in DST vs standard season',
     'H_local': 'same', 'H_fixed_DST_wall_clock': 'same', 'H_UTC_or_nonDST_fixed': 'moves by 1h',
     'observed': '; '.join(f"{e.window} {e.season}: first ticket of day median {e.first_ticket_of_day_median}h, "
                           f"{e.tickets_before_06}/{e.tickets_06h}/{e.tickets_07h}/{e.tickets_08h} tickets in <06/06h/07h/08h"
                           for e in edge.itertuples())},
    {'test': 'Arizona (no DST): DiD of mean hour, (AZ-E)summer - (AZ-E)winter',
     'H_local': 0, 'H_fixed_DST_wall_clock': 1, 'H_UTC_or_nonDST_fixed': 1,
     'observed': f"{az.DiD_mean} [{az.DiD_mean_lo}, {az.DiD_mean_hi}], perm p={az.DiD_mean_perm_p_two_sided}, "
                 f"n={az.n_summer}+{az.n_winter}"},
    {'test': 'Arizona+Hawaii pooled DiD of mean hour',
     'H_local': 0, 'H_fixed_DST_wall_clock': 1, 'H_UTC_or_nonDST_fixed': 1,
     'observed': f"{pooled.DiD_mean} [{pooled.DiD_mean_lo}, {pooled.DiD_mean_hi}], perm p={pooled.DiD_mean_perm_p_two_sided}, "
                 f"n={pooled.n_summer}+{pooled.n_winter}"},
    {'test': 'Arizona level: summer minus winter mean hour',
     'H_local': 0, 'H_fixed_DST_wall_clock': 1, 'H_UTC_or_nonDST_fixed': 0,
     'observed': round(float(az.zone_mean_summer - az.zone_mean_winter), 2)},
]
out(pd.DataFrame(score), 'clock_hypothesis_scorecard')
out(pd.DataFrame(FACTS).astype(str), 'facts')

# No figure: matplotlib is not installed in this environment; every plotted quantity is in the CSVs.
print('\nDone.')
