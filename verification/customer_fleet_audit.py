"""Customer-to-fleet ownership audit (Zac's notebook cells 24-25 and 40).

Question: can the case export's `Account Name` (Zac's `customer`) be used as the owner of a fleet of machines,
so that customer-level exposure rates (tickets per installed machine) can be reported?

What this script does, using only the case export (and, when present, the telemetry device dictionary):
  1. Serial -> account: classifies the serials that appear under more than one Account Name.
  2. Account granularity: estimates how many physical sites and parent health systems the accounts represent.
  3. Coverage: shows why ticket data alone cannot give customer-level denominators, and how a naive
     "tickets per ticketed machine" rate is biased.
  4. Interprets Zac's host audit (31 customers on >1 clearView host; 83 hosts with >1 customer).
  5. Runs, or writes the specification of, the decisive checks against the telemetry `devices` table.

Privacy: everything written under verification/outputs/ is pseudonymous (Customer NNN, S#####, Host NNN,
System NNN) or aggregate. Real names, addresses, serials, host URLs and free text are written only to
data/private/ (gitignored).

Inputs
  data/raw/IPA_CaseHistory_Aug 2025-Aug2026.xlsx                (required)
  data/private/fleet_private_system_review.csv                    (optional; hand-reviewed account->system map)
  data/raw/ipa_transaction_events_202508_202608.db                (optional; or pass --db PATH)

Run:  cd /home/user/analytics-lab && python3 -I verification/customer_fleet_audit.py [--db PATH] [--with-telemetry]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import (OUTPUTS, PRIVATE, RAW, SHARED_INTERNAL_HOST, build_cases, build_maps,  # noqa: E402
                    case_database, clean, load_raw)

PREFIX = 'fleet_'
DB_DEFAULT = RAW / 'ipa_transaction_events_202508_202608.db'
REVIEW_FILE = PRIVATE / 'fleet_private_system_review.csv'

# Zac's printed outputs (notebook cells 9, 11, 25, 27). Used only where the telemetry DB is required.
ZAC = {'devices': 7183, 'matched_machines': 3041, 'matched_cases': 6113, 'transacting_machines': 6951,
       'case_machines': 3773, 'cases': 7471, 'customers': 845,
       'customers_gt1_host': 31, 'hosts_gt1_customer': 83, 'models_gt1_type': 16,
       'shared_host_tickets_in_window': 18, 'missing_host_tickets_in_window': 48}

# Generic words that begin many unrelated facility names. A name whose first token is one of these gets no
# brand key (it stays a singleton) unless the second token is distinctive. These are dictionary words and common
# given/saint names, not organisation names.
GENERIC = set('''
st saint san santa new north south east west northern southern central university univ memorial community general
regional county childrens children medical hospital hospitals health healthcare center centre centers of and at
mount mt good holy our lady sisters methodist baptist presbyterian mercy christian lutheran advent adventist jewish
women womens family families heart cancer eye surgery surgical outpatient clinic clinics valley river lake bay city
national state doctors united texas california florida virginia mary marys joseph josephs john johns luke lukes
francis vincent vincents elizabeth anthony peter peters michael michaels charles david davids james clara agnes
barnabas catherine clare clares jefferson thomas henry washington franklin lincoln jackson la el las los fort
'''.split())

ERROR_NOTE = re.compile(r'wrong machine|wrong serial|wrong unit|wrong (?:site|location|account)|'
                        r'incorrect (?:machine|serial|site|location|account)|location was incorrect|called wrong',
                        re.I)
REPEAT_NOTE = re.compile(r'repeat issue', re.I)
FIRMWARE = re.compile(r'Device FW:\s*(\d+(?:\.\d+)+)', re.I)


# ----------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------
def out(df, name):
    path = OUTPUTS / f'{PREFIX}{name}.csv'
    df.to_csv(path, index=False)
    print(f'  wrote {path.relative_to(OUTPUTS.parents[1])} ({len(df)} rows)')
    return df


def private_out(df, name):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / f'fleet_private_{name}.csv'
    df.to_csv(path, index=False)
    print(f'  wrote {path.relative_to(PRIVATE.parents[1])} ({len(df)} rows) [PRIVATE]')
    return df


def name_tokens(name):
    """Lower-case word tokens; mis-encoded apostrophes ('?') and apostrophes removed, leading 'the' dropped."""
    s = name.replace('?', "'").lower().replace('&', ' and ')
    s = re.sub(r"['’`]", '', s)
    tokens = re.sub(r'[^a-z0-9]+', ' ', s).split()
    while tokens and tokens[0] == 'the':
        tokens = tokens[1:]
    return tokens


def brand_key(name):
    """First distinctive token; if the first token is generic, the first two tokens when the second is
    distinctive; otherwise None (no brand evidence -> singleton)."""
    t = name_tokens(name)
    if not t:
        return None
    if t[0] not in GENERIC:
        return t[0]
    if len(t) > 1 and t[1] not in GENERIC:
        return ' '.join(t[:2])
    return None


def parse_address(text):
    """'City,ST NNNNN-NNNN' -> (city, state, zip5_or_postal, zip_has_plus4)."""
    m = re.match(r'^(.*?),\s*([A-Za-z]+)\s+(.+)$', text)
    city, state, z = m.groups()
    z = z.strip().upper().replace(' ', '')
    if re.fullmatch(r'\d{4,5}(-\d{4})?', z):
        five = z.split('-')[0].zfill(5)          # restores dropped leading zero (e.g. NJ '7753')
        return city.strip().upper(), state.upper(), five, '-' in z
    return city.strip().upper(), state.upper(), z, len(z) == 6   # Canadian postal code (building-level)


def spearman(a, b):
    """Spearman rank correlation without scipy (average ranks for ties)."""
    return float(np.corrcoef(a.rank(), b.rank())[0, 1])


def version(v):
    """'7.1' -> (7, 1, 0) so that '7.1' and '7.1.0' compare equal."""
    parts = [int(x) for x in v.split('.')]
    return tuple(parts + [0] * (3 - len(parts)))


def cluster_by_key(acc, key_col, same_state):
    keys = acc[key_col].where(acc[key_col].notna(), acc['account'])
    group = keys + ('|' + acc['state'] if same_state else '')
    return group


# ----------------------------------------------------------------------------------------------------------
# load
# ----------------------------------------------------------------------------------------------------------
def load():
    raw = load_raw()
    maps = build_maps(raw)
    cases = build_cases(raw, maps)
    raw = raw.assign(account=raw['Account Name'].map(clean), serial=raw['Serial #'].map(clean),
                     address=raw['Hospital City, State, Zip'].map(clean))
    raw['customer'] = raw.account.map(maps['account'])
    raw['machine'] = raw.serial.map(maps['serial'])
    raw['case_id'] = raw['Case Number'].map(clean).map(maps['case'])
    raw['opened'] = pd.to_datetime(raw['Date/Time Opened'])
    return raw, maps, cases


# ----------------------------------------------------------------------------------------------------------
# 2. account granularity: sites and systems
# ----------------------------------------------------------------------------------------------------------
def account_table(raw):
    acc = (raw.groupby(['account', 'customer'])
           .agg(address=('address', lambda s: sorted(set(s))), tickets=('case_id', 'size'),
                ticketed_machines=('serial', 'nunique'), country=('Shipping Country', 'first'))
           .reset_index())
    assert acc.address.map(len).eq(1).all(), 'an account has more than one address'
    acc['address'] = acc.address.str[0]
    parsed = acc.address.map(parse_address)
    acc['city'] = parsed.str[0]
    acc['state'] = parsed.str[1]
    acc['zip5'] = parsed.str[2]
    acc['zip_precise'] = parsed.str[3]
    acc['brand_key'] = acc.account.map(brand_key)
    acc['sys_L2a'] = cluster_by_key(acc, 'brand_key', same_state=True)
    acc['sys_L2b'] = cluster_by_key(acc, 'brand_key', same_state=False)
    return acc


def apply_review(acc):
    """Merge the hand-reviewed account->system file (private). Returns acc with sys_name / sys_full columns."""
    if not REVIEW_FILE.exists():
        print(f'  NOTE: {REVIEW_FILE.name} not found; reviewed tiers fall back to L2a.')
        acc['sys_name'] = acc.sys_L2a
        acc['sys_full'] = acc.sys_L2a
        acc['segment'] = 'unreviewed'
        acc['full_evidence'] = 'unreviewed'
        acc['full_confidence'] = ''
        return acc, False
    rev = pd.read_csv(REVIEW_FILE, dtype=str, keep_default_na=False)
    missing = set(acc.account) - set(rev.account_name)
    extra = set(rev.account_name) - set(acc.account)
    assert not missing and not extra, f'review file mismatch: {len(missing)} missing, {len(extra)} extra'
    acc = acc.merge(rev.rename(columns={'account_name': 'account'})[
        ['account', 'sys_name', 'sys_full', 'segment', 'full_evidence', 'full_confidence']], on='account')
    return acc, True


def site_and_system_counts(acc, reviewed):
    rows = []

    def add(level, rule, n, evidence, note=''):
        rows.append({'level': level, 'rule': rule, 'count': int(n), 'evidence_type': evidence, 'note': note})

    add('L0 account', 'distinct cleaned Account Name', acc.account.nunique(), 'data',
        'Zac\'s "customer" unit; every account has exactly one address string')
    add('L1 site', 'distinct address string (City,State ZIP+4 / postal code)', acc.address.nunique(), 'data',
        'address field has no street line; ZIP+4 and Canadian postal codes are building-level')
    add('L1 site', 'distinct City+State+ZIP5 (any organisation)', acc[['city', 'state', 'zip5']].drop_duplicates().shape[0],
        'data', 'merges different organisations that share a ZIP5; lower bound on sites')
    add('L2a system', 'first distinctive name token, same state', acc.sys_L2a.nunique(), 'data (algorithmic)',
        'conservative across states; still contains same-state false merges')
    add('L2b system', 'first distinctive name token, any state', acc.sys_L2b.nunique(), 'data (algorithmic)',
        'allows multi-state systems; contains cross-state false merges')
    if reviewed:
        add('L3a system', 'reviewed: brand evident in names/addresses only', acc.sys_name.nunique(),
            'data + manual review', 'splits algorithmic false merges, adds name-evident members')
        add('L3b system', 'reviewed: + documented affiliations (external knowledge)', acc.sys_full.nunique(),
            'inferred (external knowledge)', 'best estimate of operating health systems; unverified by IPA')
        campus = acc[['sys_full', 'city', 'state', 'zip5']].drop_duplicates().shape[0]
        add('L1 site', 'distinct reviewed system + City+State+ZIP5 (campus within system)', campus,
            'inferred (external knowledge)', 'accounts of one system in one ZIP5 treated as one campus')
        va = acc.segment.eq('federal_veterans')
        dod = acc.segment.eq('federal_military')
        alt = acc.sys_full.where(~va, acc.account)
        add('L3b sensitivity', 'reviewed, each federal veterans facility its own system', alt.nunique(), 'inferred', '')
        alt2 = alt.where(~dod, acc.account)
        add('L3b sensitivity', 'reviewed, each federal veterans and military facility its own system', alt2.nunique(), 'inferred', '')
        hosp = ~acc.segment.isin(['industry_lab'])
        add('L3b sensitivity', 'reviewed, healthcare accounts only (industry/lab accounts dropped)',
            acc.loc[hosp, 'sys_full'].nunique(), 'inferred', f'{int((~hosp).sum())} industry/lab accounts dropped')
    return pd.DataFrame(rows)


def system_distribution(acc, col):
    g = acc.groupby(col).agg(accounts=('account', 'size'), tickets=('tickets', 'sum'),
                             machines=('ticketed_machines', 'sum'), states=('state', 'nunique'))
    g['size_bin'] = pd.cut(g.accounts, [0, 1, 2, 4, 9, 1000], labels=['1', '2', '3-4', '5-9', '10+']).astype(str)
    d = (g.groupby('size_bin', sort=False).agg(systems=('accounts', 'size'), accounts_in_bin=('accounts', 'sum'),
                                              tickets=('tickets', 'sum'), ticketed_machines=('machines', 'sum'))
         .reindex(['1', '2', '3-4', '5-9', '10+']).fillna(0).astype(int).reset_index()
         .rename(columns={'size_bin': 'accounts_per_system'}))
    d.insert(0, 'grouping', col)
    d['share_of_accounts_pct'] = (100 * d.accounts_in_bin / d.accounts_in_bin.sum()).round(2)
    d['share_of_tickets_pct'] = (100 * d.tickets / d.tickets.sum()).round(2)
    return d


def cluster_review(acc):
    """For every algorithmic L2b multi-account cluster: does the reviewed mapping keep it together?"""
    rows = []
    multi = acc.groupby('sys_L2b').filter(lambda g: len(g) > 1)
    for i, (_, g) in enumerate(sorted(multi.groupby('sys_L2b'), key=lambda kv: -len(kv[1])), 1):
        n_name = g.sys_name.nunique()
        n_full = g.sys_full.nunique()
        rows.append({'cluster': f'L2b-{i:03d}', 'accounts': len(g), 'states': g.state.nunique(),
                     'tickets': int(g.tickets.sum()),
                     'reviewed_systems_name_tier': n_name, 'reviewed_systems_full': n_full,
                     'verdict': 'confirmed' if n_full == 1 else 'false merge (split on review)',
                     'segment': ';'.join(sorted(set(g.segment)))})
    return pd.DataFrame(rows)


def shared_addresses(acc):
    rows = []
    for _, g in acc.groupby('address'):
        if len(g) < 2:
            continue
        rows.append({'customers': ' + '.join(sorted(g.customer)), 'state': g.state.iloc[0],
                     'address_precision': 'ZIP+4/postal code' if g.zip_precise.iloc[0] else 'ZIP5 only',
                     'same_reviewed_system': bool(g.sys_full.nunique() == 1),
                     'same_name_tier_system': bool(g.sys_name.nunique() == 1)})
    return pd.DataFrame(rows).sort_values('customers').reset_index(drop=True)


# ----------------------------------------------------------------------------------------------------------
# 1. serials under more than one account
# ----------------------------------------------------------------------------------------------------------
def firmware_list(text):
    return [version(v) for v in FIRMWARE.findall(str(text or ''))]


def multi_account_serials(raw, acc):
    sysmap = acc.set_index('account')[['sys_name', 'sys_full', 'state', 'city', 'zip5', 'address']]
    counts = raw.groupby('serial').account.nunique()
    serials = counts[counts > 1].index
    public, private = [], []
    for s in sorted(serials, key=lambda x: raw.loc[raw.serial == x, 'machine'].iloc[0]):
        t = raw[raw.serial == s].sort_values('opened')
        seq = t.account.tolist()
        switches = sum(a != b for a, b in zip(seq, seq[1:]))
        accounts = list(dict.fromkeys(seq))
        clean_split = switches == len(accounts) - 1
        info = sysmap.loc[accounts]
        per = t.groupby('account', sort=False).agg(n=('case_id', 'size'), first=('opened', 'min'),
                                                   last=('opened', 'max')).loc[accounts]
        first_switch = next(i for i in range(1, len(seq)) if seq[i] != seq[i - 1])
        before, after = t.iloc[:first_switch], t.iloc[first_switch:]
        fw_before = [v for x in before['Trouble Reported'] for v in firmware_list(x)]
        fw_after = [v for x in after['Trouble Reported'] for v in firmware_list(x)]
        fw_regress = bool(fw_before and fw_after and min(fw_after) < max(fw_before))
        fw_same = bool(fw_before and fw_after and set(fw_before) & set(fw_after))
        notes = (t['Administrative Notes'].fillna('').astype(str) + ' ' + t['Trouble Resolution'].fillna('').astype(str))
        error_note = bool(notes.str.contains(ERROR_NOTE).any())
        repeat_note = bool(notes.loc[after.index].str.contains(REPEAT_NOTE).any())
        same_sys_full = info.sys_full.nunique() == 1
        same_sys_name = info.sys_name.nunique() == 1
        # Evidence class (rule order = strength of evidence). Firmware strings are weak evidence: the same
        # 7.1.0 -> 4.2.1 change also occurs on serials that never change account (board replacements).
        if error_note:
            cls = 'A. Data-entry error noted on a switched ticket'
        elif repeat_note and same_sys_full:
            cls = 'B. Same machine, inconsistent account (repeat of same fault noted)'
        elif not same_sys_full:
            cls = ('E. Cross-system move; firmware regresses (possible wrong serial or redeployment)' if fw_regress
                   else 'E. Cross-system move, unexplained')
        elif clean_split and per.n.min() >= 2:
            cls = 'C. Probable transfer/re-assignment within system (clean time split, >=2 tickets each side)'
        else:
            cls = 'D. Within system, ambiguous (<2 tickets on one side)'
        if info.zip5.nunique() == 1 and same_sys_full:
            relation = 'same system, same campus (ZIP5)'
        elif same_sys_full:
            relation = 'same system, different site'
        else:
            relation = 'different system' + ('' if info.state.nunique() == 1 else ', different state')
        gap = (per['first'].iloc[1] - per['last'].iloc[0]).days if len(accounts) > 1 else None
        public.append({
            'machine': t.machine.iloc[0], 'model': t['Model #'].iloc[0], 'tickets': len(t),
            'customers_in_time_order': ' -> '.join(acc.set_index('account').customer.loc[accounts]),
            'tickets_per_customer': ' / '.join(map(str, per.n)),
            'first_ticket': t.opened.min().date().isoformat(), 'last_ticket': t.opened.max().date().isoformat(),
            'switch_after_ticket_n': first_switch, 'account_switches': switches, 'clean_time_split': clean_split,
            'days_between_accounts': gap,
            'same_state': info.state.nunique() == 1, 'same_city': info.city.nunique() == 1,
            'same_zip5': info.zip5.nunique() == 1, 'same_address': info.address.nunique() == 1,
            'same_system_name_tier': same_sys_name, 'same_system_reviewed': same_sys_full,
            'record_type_changes': t['Case Record Type'].nunique() > 1,
            'firmware_recorded_before_after': f'{len(fw_before)}/{len(fw_after)}',
            'firmware_regresses': fw_regress, 'firmware_value_repeats_across_switch': fw_same,
            'error_note_flag': error_note, 'repeat_note_flag': repeat_note, 'relationship': relation,
            'rule_class': cls})
        private.append({
            'machine': t.machine.iloc[0], 'serial': s, 'accounts_in_time_order': ' -> '.join(accounts),
            'customers_in_time_order': ' -> '.join(acc.set_index('account').customer.loc[accounts]),
            'addresses': ' -> '.join(info.address), 'reviewed_systems': ' -> '.join(info.sys_full),
            'ticket_dates': '; '.join(f"{a}: {d:%Y-%m-%d}" for a, d in zip(t.account, t.opened)),
            'firmware_before': ', '.join('.'.join(map(str, v)) for v in fw_before),
            'firmware_after': ', '.join('.'.join(map(str, v)) for v in fw_after),
            'error_or_repeat_notes': ' | '.join(n.strip()[:300] for n in notes[notes.str.contains(ERROR_NOTE) |
                                                                                 notes.str.contains(REPEAT_NOTE)]),
            'relationship': relation, 'rule_class': cls})
    return pd.DataFrame(public), pd.DataFrame(private)


def serial_integrity(raw):
    """Fleet-wide indicators that a ticket's serial may not identify the physical machine."""
    t = raw.sort_values(['serial', 'opened']).copy()
    t['fw'] = t['Trouble Reported'].map(lambda x: max(firmware_list(x)) if firmware_list(x) else None)
    rows = []
    with_fw = t.dropna(subset=['fw'])
    multi = with_fw.groupby('serial').filter(lambda g: len(g) >= 2)
    regress = multi.groupby('serial').fw.apply(lambda s: any(b < a for a, b in zip(s, s.iloc[1:])))
    major = multi.groupby('serial').fw.apply(lambda s: any(b[0] < a[0] for a, b in zip(s, s.iloc[1:])))
    notes = (t['Administrative Notes'].fillna('').astype(str) + ' ' + t['Trouble Resolution'].fillna('').astype(str))
    err = notes.str.contains(ERROR_NOTE)
    rows += [
        {'measure': 'tickets', 'value': len(t)},
        {'measure': 'tickets with a "Device FW: x.y.z" string in Trouble Reported', 'value': int(t.fw.notna().sum())},
        {'measure': 'serials with >=2 tickets carrying a firmware string', 'value': int(multi.serial.nunique())},
        {'measure': '... of which firmware decreases between consecutive tickets', 'value': int(regress.sum())},
        {'measure': '... of which the MAJOR firmware version decreases', 'value': int(major.sum())},
        {'measure': 'tickets whose notes/resolution state a wrong machine/serial/site/location was used',
         'value': int(err.sum())},
        {'measure': '... distinct serials affected', 'value': int(t.loc[err, 'serial'].nunique())},
        {'measure': '... coded No Trouble Found', 'value': int((t.loc[err, 'Trouble Code Category'] == 'No Trouble Found').sum())},
        {'measure': '... coded Cancelled Request', 'value': int((t.loc[err, 'Trouble Code Category'] == 'Cancelled Request').sum())},
        {'measure': '... category missing', 'value': int(t.loc[err, 'Trouble Code Category'].isna().sum())},
        {'measure': '... coded with a component/fault category (label may describe another machine)',
         'value': int((~t.loc[err, 'Trouble Code Category'].isin(['No Trouble Found', 'Cancelled Request'])
                       & t.loc[err, 'Trouble Code Category'].notna()).sum())},
        {'measure': 'serials with >1 Model # across their tickets', 'value': int((raw.groupby('serial')['Model #'].nunique() > 1).sum())},
        {'measure': 'serials with >1 Account Name across their tickets', 'value': int((raw.groupby('serial').account.nunique() > 1).sum())},
    ]
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------------------
# 3. coverage and the naive customer rate
# ----------------------------------------------------------------------------------------------------------
def naive_rates(raw, cases):
    conn = case_database(cases)
    svc = pd.read_sql_query('SELECT customer, COUNT(*) service_tickets, COUNT(DISTINCT machine_id) service_machines '
                            'FROM service_cases GROUP BY customer', conn)
    per = (raw.groupby('customer').agg(tickets=('case_id', 'size'), ticketed_machines=('serial', 'nunique'))
           .reset_index().merge(svc, on='customer', how='left').fillna({'service_tickets': 0, 'service_machines': 0}))
    per['naive_tickets_per_ticketed_machine'] = (per.tickets / per.ticketed_machines).round(4)
    per['naive_service_per_ticketed_machine'] = (per.service_tickets / per.service_machines.replace(0, np.nan)).round(4)
    per = per.sort_values(['tickets', 'customer'], ascending=[False, True]).reset_index(drop=True)
    per.insert(1, 'rank_by_tickets', range(1, len(per) + 1))
    r = per.naive_tickets_per_ticketed_machine
    summary = [
        ('customers (accounts with >=1 ticket; accounts with zero tickets are invisible)', len(per)),
        ('customers with naive rate >= 1.0 (true by construction)', int((r >= 1).sum())),
        ('customers with naive rate exactly 1.0 (every ticketed machine had one ticket)', int((r == 1).sum())),
        ('naive rate: minimum', round(r.min(), 3)), ('naive rate: median', round(r.median(), 3)),
        ('naive rate: mean of customers', round(r.mean(), 3)), ('naive rate: maximum', round(r.max(), 3)),
        ('customers with 1 ticketed machine', int((per.ticketed_machines == 1).sum())),
        ('customers with 1 ticket', int((per.tickets == 1).sum())),
        ('customers with >=2 ticketed machines (only these can span >1 host)', int((per.ticketed_machines >= 2).sum())),
        ('Spearman rho(tickets, naive rate)', round(spearman(per.tickets, r), 3)),
        ('Spearman rho(ticketed machines, naive rate)', round(spearman(per.ticketed_machines, r), 3)),
        ('pooled tickets / ticketed machines (all cases)', round(per.tickets.sum() / raw.serial.nunique(), 3)),
        ('customers with zero unplanned (service) tickets', int((per.service_tickets == 0).sum())),
    ]
    for k in (10, 50):
        top = per.head(k)
        summary.append((f'top-{k} customers by tickets: median naive rate', round(top.naive_tickets_per_ticketed_machine.median(), 3)))
    summary.append(('customers outside top-50: median naive rate', round(per.iloc[50:].naive_tickets_per_ticketed_machine.median(), 3)))
    return per, pd.DataFrame(summary, columns=['measure', 'value'])


def coverage_bounds(raw):
    ticketed = raw.serial.nunique()
    rows = [
        ('ticketed serials in case export (computed)', ticketed, 'data'),
        ('devices in telemetry dictionary (Zac cell 9)', ZAC['devices'], 'Zac printed'),
        ('transacting machines Aug 2025-Aug 2026 (Zac cell 11)', ZAC['transacting_machines'], 'Zac printed'),
        ('ticketed machines matched to device dictionary (Zac cell 11)', ZAC['matched_machines'], 'Zac printed'),
        ('ticketed serials NOT in device dictionary', ticketed - ZAC['matched_machines'], 'derived'),
        ('tickets NOT matched to device dictionary (Zac cell 11)', ZAC['cases'] - ZAC['matched_cases'], 'Zac printed'),
        ('share of devices with any ticket-based customer attribution (%)',
         round(100 * ZAC['matched_machines'] / ZAC['devices'], 2), 'derived upper bound'),
        ('devices with no ticket in 13 months -> no customer attribution', ZAC['devices'] - ZAC['matched_machines'], 'derived'),
        ('share of devices without attribution (%)', round(100 * (1 - ZAC['matched_machines'] / ZAC['devices']), 2), 'derived'),
        ('share of ticketed serials matched (%)', round(100 * ZAC['matched_machines'] / ticketed, 2), 'derived'),
        ('matched tickets per device (fleet denominator)', round(ZAC['matched_cases'] / ZAC['devices'], 3), 'derived'),
        ('matched tickets per matched ticketed device (naive denominator)',
         round(ZAC['matched_cases'] / ZAC['matched_machines'], 3), 'derived'),
        ('inflation factor of naive vs fleet denominator',
         round(ZAC['devices'] / ZAC['matched_machines'], 3), 'derived'),
    ]
    lam = ZAC['matched_cases'] / ZAC['devices']
    rows += [('Poisson check: expected share ticketed if all devices shared one rate (%)',
              round(100 * (1 - math.exp(-lam)), 2), 'model illustration'),
             ('observed share ticketed (%)', round(100 * ZAC['matched_machines'] / ZAC['devices'], 2), 'derived')]
    return pd.DataFrame(rows, columns=['measure', 'value', 'source'])


def truncation_illustration():
    rows = []
    for lam in (0.1, 0.25, 0.5, 0.85, 1.0, 2.0):
        p = 1 - math.exp(-lam)
        rows.append({'true_tickets_per_machine': lam, 'share_of_fleet_ticketed_pct': round(100 * p, 1),
                     'naive_tickets_per_ticketed_machine': round(lam / p, 3)})
    df = pd.DataFrame(rows)
    df['note'] = ('Poisson, equal machines, homogeneous rate. True rates differ 20x (0.1 vs 2.0) but naive rates '
                  f'differ {df.naive_tickets_per_ticketed_machine.iloc[-1] / df.naive_tickets_per_ticketed_machine.iloc[0]:.2f}x')
    return df


# ----------------------------------------------------------------------------------------------------------
# 4. interpreting Zac's 31 / 83
# ----------------------------------------------------------------------------------------------------------
def host_expectations(acc, per, reviewed):
    rows = []
    elig = int((per.ticketed_machines >= 2).sum())
    rows.append(('Zac: customers spanning >1 observed host', ZAC['customers_gt1_host'], 'Zac printed'))
    rows.append(('customers with >=2 ticketed serials (upper bound on eligible customers)', elig, 'data'))
    rows.append(('31 as % of eligible customers (lower bound on rate)', round(100 * ZAC['customers_gt1_host'] / elig, 2), 'derived'))
    rows.append(('Zac: hosts linked to >1 case customer', ZAC['hosts_gt1_customer'], 'Zac printed'))
    rows.append(('max contribution of the shared internal host to the 83', 1, 'logic (counted once in GROUP BY host)'))
    rows.append(('Zac: in-window unplanned tickets on the shared internal host', ZAC['shared_host_tickets_in_window'], 'Zac printed'))
    if reviewed:
        for col, label in (('sys_name', 'name-tier'), ('sys_full', 'reviewed')):
            g = acc.groupby(col).account.nunique()
            rows.append((f'{label} systems with >=2 accounts (expected multi-customer hosts if one host per system)',
                         int((g >= 2).sum()), 'inferred'))
            g2 = acc[acc.ticketed_machines >= 1].groupby(col).agg(a=('account', 'nunique'), m=('ticketed_machines', 'sum'))
            rows.append((f'{label} systems with >=2 accounts and >=3 ticketed machines', int(((g2.a >= 2) & (g2.m >= 3)).sum()), 'inferred'))
        nonfed = acc[~acc.segment.isin(['federal_veterans', 'federal_military'])]
        g = nonfed.groupby('sys_full').account.nunique()
        rows.append(('reviewed non-federal systems with >=2 accounts', int((g >= 2).sum()), 'inferred'))
        rows.append(('federal veterans facility accounts (one host or many? decides 1 vs 0 of the 83)',
                     int(acc.segment.eq('federal_veterans').sum()), 'data'))
        rows.append(('federal military facility accounts', int(acc.segment.eq('federal_military').sum()), 'inferred'))
    return pd.DataFrame(rows, columns=['measure', 'value', 'source'])


def model_type_note():
    """Zac's 16 'case models spanning >1 telemetry type' counts 'Unknown' (NULL machine_type) as a type."""
    shown = pd.DataFrame([
        ('A-LC', 'alc-1 + Unknown', 'Unknown only'),
        ('LC-24', 'mlc-1', 'single type (in shown rows)'),
        ('LC-30', 'mlc-1 + Unknown', 'Unknown only'),
        ('LVD-Remote', 'scrubex-2 + scrubex-1 + Unknown', 'genuine second type (16 machines)'),
        ('LVD-Remote-2.0', 'scrubex2.0-2 + Unknown + scrubex2.0-3 + sd2.0-49', 'two 1-machine anomalies + Unknown'),
    ], columns=['model', 'types_in_zac_first_15_rows', 'why_counted_as_multi_type'])
    shown['note'] = ('Zac maps NULL machine_type to the string Unknown before COUNT(DISTINCT), so Unknown makes a '
                     'model "multi-type"; only the first 15 rows were printed, so the full 16 cannot be checked here')
    return shown


# ----------------------------------------------------------------------------------------------------------
# 5. decisive DB checks
# ----------------------------------------------------------------------------------------------------------
DB_CHECKS = [
    ('D1', 'Host key hygiene',
     'SELECT clearview_url, COUNT(*) FROM devices GROUP BY clearview_url; then normalise lower(), strip scheme, '
     'trailing "/" and "www."',
     'Number of raw URLs vs normalised hosts; URLs that collapse. Zac keyed Host NNN on the raw URL (no strip) '
     'while flagging the shared host with rstrip("/"); any collapse means his 31/83 count duplicate hosts.'),
    ('D2', "Recompute Zac's 31/83/16 and variants",
     'Zac cell 25 SQL on (a) raw hosts, (b) normalised hosts, (c) excluding the shared internal host, '
     '(d) excluding Unknown machine_type, (e) at reviewed-system level instead of facility account',
     'If (c)+(e) drive both counts toward 0, host = health system and facility accounts explain the overlap.'),
    ('D3', 'Decompose the multi-host customers',
     'For each customer with >1 host: hosts, machines per host, whether one host is the shared host, whether the '
     'minority host holds a single machine with a single ticket, whether a multi-account serial is involved',
     'Share explained by shared host / single-ticket strays (serial errors) / transfers / genuinely split fleets.'),
    ('D4', 'Classify every host',
     'Per host: devices, ticketed devices, ticket customers, reviewed systems, states of ticket customers',
     'Classes: no tickets / single customer / single system many customers / multi-system. Device share on '
     'single-system hosts = share of fleet with a usable system-level denominator.'),
    ('D5', 'One host per system?',
     'Per reviewed system: distinct non-shared hosts among its ticketed devices; devices on those hosts',
     'If >=90% of systems (and of devices) sit on exactly one host, host can serve as the system key.'),
    ('D6', 'Unmatched ticket serials',
     'Ticket serials absent from devices: count by model, record type, country, account; tolerant re-match '
     '(leading zeros, hyphens, prefixes)',
     'Whether the 732 unmatched serials are non-networked models, Canada, retired machines or entry errors.'),
    ('D7', 'Invisible fleet per host',
     'Per host: devices with no ticket in 13 months, device_status mix, transacting months',
     'Shows how far ticket-derived customer fleets understate installed fleets.'),
    ('D8', 'Host-level exposure (optional, heavy)',
     'Per host and month: distinct transacting devices from transaction_events',
     'System-level denominators (active machine-months) for hosts that pass D4/D5.'),
]


def norm_host(url):
    if url is None or (isinstance(url, float) and math.isnan(url)):
        return None
    u = str(url).strip().lower()
    u = re.sub(r'^[a-z]+://', '', u)
    u = u.split('/')[0]
    return u[4:] if u.startswith('www.') else u


def run_db_checks(db_path, raw, acc, with_telemetry):
    src = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
    src.execute('PRAGMA query_only=ON')
    cols = [r[1] for r in src.execute('PRAGMA table_info(devices)')]
    keep = [c for c in ('external_device_id', 'device_status', 'machine_type', 'clearview_url') if c in cols]
    dev = pd.read_sql_query(f'SELECT {",".join(keep)} FROM devices', src)
    dev['serial'] = dev.external_device_id.map(clean)
    assert dev.serial.is_unique
    maps = build_maps(raw, dev.external_device_id)                           # Zac's M##### labels
    dev['machine'] = dev.serial.map(maps['serial'])
    hosts = sorted(set(dev.clearview_url.dropna()))
    hostmap = {h: f'Host {i:03d}' for i, h in enumerate(hosts, 1)}            # Zac's exact host labels
    dev['host'] = dev.clearview_url.map(hostmap)
    dev['host_norm'] = dev.clearview_url.map(norm_host)
    shared_norm = norm_host(SHARED_INTERNAL_HOST)
    dev['shared'] = dev.host_norm.eq(shared_norm)
    dev['machine_type_n'] = dev.machine_type.map(lambda x: clean(x).lower() if clean(x) else 'Unknown')
    t = raw[['case_id', 'customer', 'account', 'serial', 'Model #', 'Case Record Type', 'Shipping Country']].merge(
        acc[['account', 'sys_full', 'sys_name', 'state']], on='account')
    sysid = {s: f'System {i:03d}' for i, s in enumerate(sorted(acc.sys_full.unique()), 1)}
    t['system'] = t.sys_full.map(sysid)
    j = t.merge(dev, on='serial', how='inner')

    res = {}
    # D1
    raw_urls = dev.clearview_url.dropna().nunique()
    nh = dev.host_norm.dropna().nunique()
    coll = dev.dropna(subset=['clearview_url']).groupby('host_norm').clearview_url.nunique()
    res['D1'] = pd.DataFrame([
        ('devices', len(dev)), ('devices with NULL clearview_url', int(dev.clearview_url.isna().sum())),
        ('distinct raw clearview_url (Zac Host NNN count)', raw_urls), ('distinct normalised hosts', nh),
        ('normalised hosts with >1 raw spelling', int((coll > 1).sum())),
        ('devices on shared internal host', int(dev.shared.sum())),
        ('ticketed serials matched to devices', int(j.serial.nunique())), ('tickets matched', int(j.case_id.nunique())),
    ], columns=['measure', 'value'])

    # D2
    def multi(df, grp, item):
        return int((df.dropna(subset=[item]).groupby(grp)[item].nunique() > 1).sum())
    variants = {'as Zac (raw URL hosts)': (j, 'host'), 'normalised hosts': (j, 'host_norm'),
                'normalised, excl. shared host': (j[~j.shared], 'host_norm')}
    rows = []
    for v, (df, hcol) in variants.items():
        rows.append({'variant': v, 'unit': 'facility account',
                     'customers_gt1_host': multi(df, 'customer', hcol),
                     'hosts_gt1_customer': multi(df.dropna(subset=[hcol]), hcol, 'customer')})
        rows.append({'variant': v, 'unit': 'reviewed system',
                     'customers_gt1_host': multi(df, 'system', hcol),
                     'hosts_gt1_customer': multi(df.dropna(subset=[hcol]), hcol, 'system')})
    d2 = pd.DataFrame(rows)
    mt = j.groupby('Model #').machine_type_n.nunique()
    mt_known = j[j.machine_type_n != 'Unknown'].groupby('Model #').machine_type_n.nunique()
    d2_models = pd.DataFrame([('case models spanning >1 type (as Zac)', int((mt > 1).sum())),
                              ('... excluding Unknown type', int((mt_known > 1).sum()))], columns=['measure', 'value'])
    res['D2'] = d2
    res['D2_models'] = d2_models

    # D3
    jj = j.dropna(subset=['host_norm'])
    mh = jj.groupby('customer').host_norm.nunique()
    multi_serials = set(raw.groupby('serial').account.nunique().loc[lambda s: s > 1].index)
    rows = []
    for cust in mh[mh > 1].index:
        g = jj[jj.customer == cust]
        per_host = g.groupby('host_norm').agg(machines=('serial', 'nunique'), tickets=('case_id', 'nunique'))
        main = per_host.machines.idxmax()
        minor = per_host.drop(index=main)
        rows.append({'customer': cust, 'hosts': len(per_host), 'machines': int(g.serial.nunique()),
                     'involves_shared_host': bool(g.shared.any()),
                     'minority_hosts_single_machine_single_ticket': bool(((minor.machines == 1) & (minor.tickets == 1)).all()),
                     'involves_multi_account_serial': bool(set(g.serial) & multi_serials),
                     'only_shared_host_explains': bool(g[~g.shared].host_norm.nunique() <= 1)})
    res['D3'] = pd.DataFrame(rows)

    # D4/D5/D7
    dh = dev.dropna(subset=['host_norm']).groupby('host_norm').agg(devices=('serial', 'size'), shared=('shared', 'max'))
    th = jj.groupby('host_norm').agg(ticketed_devices=('serial', 'nunique'), customers=('customer', 'nunique'),
                                     systems=('system', 'nunique'), states=('state', 'nunique'), tickets=('case_id', 'nunique'))
    h = dh.join(th, how='left').fillna({'ticketed_devices': 0, 'customers': 0, 'systems': 0, 'states': 0, 'tickets': 0})
    h['host_class'] = np.select(
        [h.shared, h.customers == 0, h.customers == 1, h.systems == 1],
        ['shared internal', 'no tickets', 'single customer', 'single system, several customers'], 'multi-system')
    h['unticketed_device_share_pct'] = (100 * (1 - h.ticketed_devices / h.devices)).round(1)
    host_label = {hn: f'Host {i:03d}n' for i, hn in enumerate(sorted(h.index), 1)}
    res['D4_hosts'] = h.reset_index().assign(host=lambda d: d.host_norm.map(host_label)).drop(columns='host_norm')
    res['D4_summary'] = h.groupby('host_class').agg(hosts=('devices', 'size'), devices=('devices', 'sum'),
                                                   ticketed_devices=('ticketed_devices', 'sum')).reset_index()
    res['D4_summary']['device_share_pct'] = (100 * res['D4_summary'].devices / res['D4_summary'].devices.sum()).round(2)
    s5 = jj[~jj.shared].groupby('system').host_norm.nunique()
    res['D5'] = pd.DataFrame([('reviewed systems with matched ticketed devices on non-shared hosts', len(s5)),
                              ('... on exactly one host', int((s5 == 1).sum())),
                              ('... on 2 hosts', int((s5 == 2).sum())), ('... on 3+ hosts', int((s5 >= 3).sum()))],
                             columns=['measure', 'value'])
    # D6
    un = t[~t.serial.isin(set(dev.serial))]
    dev_canon = {re.sub(r'[^0-9A-Z]', '', s.upper()).lstrip('0'): s for s in dev.serial.dropna()}
    un_serials = un.serial.drop_duplicates()
    rematch = un_serials.map(lambda s: re.sub(r'[^0-9A-Z]', '', s.upper()).lstrip('0') in dev_canon)
    res['D6'] = pd.concat([
        un.groupby('Model #').agg(serials=('serial', 'nunique'), tickets=('case_id', 'size')).reset_index()
          .rename(columns={'Model #': 'value'}).assign(dimension='model'),
        un.groupby('Shipping Country').agg(serials=('serial', 'nunique'), tickets=('case_id', 'size')).reset_index()
          .rename(columns={'Shipping Country': 'value'}).assign(dimension='country'),
        un.groupby('Case Record Type').agg(serials=('serial', 'nunique'), tickets=('case_id', 'size')).reset_index()
          .rename(columns={'Case Record Type': 'value'}).assign(dimension='record type'),
        pd.DataFrame([{'dimension': 'tolerant re-match', 'value': 'serials recoverable',
                       'serials': int(rematch.sum()), 'tickets': None}]),
    ])[['dimension', 'value', 'serials', 'tickets']]
    # D7: device_status mix by host class, and never-ticketed share
    ticketed = set(jj.serial)
    d7 = dev.dropna(subset=['host_norm']).assign(
        host_class=lambda d: d.host_norm.map(h.host_class), ticketed=lambda d: d.serial.isin(ticketed))
    res['D7'] = (d7.groupby(['host_class', 'device_status'], dropna=False)
                 .agg(devices=('serial', 'size'), never_ticketed=('ticketed', lambda x: int((~x).sum())))
                 .reset_index())
    if with_telemetry:
        q = ('SELECT external_device_id, COUNT(DISTINCT substr(transaction_date_local,1,7)) active_months, '
             'COUNT(*) transactions FROM transaction_events GROUP BY external_device_id')
        act = pd.read_sql_query(q, src)
        act['serial'] = act.external_device_id.map(clean)
        a = dev.merge(act, on='serial', how='left')
        res['D8'] = a.dropna(subset=['host_norm']).groupby('host_norm').agg(
            devices=('serial', 'size'), transacting_devices=('active_months', 'count'),
            active_machine_months=('active_months', 'sum')).reset_index().assign(
            host=lambda d: d.host_norm.map(host_label)).drop(columns='host_norm')
    src.close()
    for k, v in res.items():
        out(v, f'db_{k}')
    # private: host URL -> label -> ticket accounts (for manual check that a host is one health system)
    priv = jj.groupby('host_norm').agg(accounts=('account', lambda s: ' | '.join(sorted(set(s)))),
                                       reviewed_systems=('sys_full', lambda s: ' | '.join(sorted(set(s)))))
    priv = h.join(priv, how='left').reset_index().assign(host=lambda d: d.host_norm.map(host_label))
    private_out(priv, 'db_hosts')
    sys_map = acc[['customer', 'sys_full']].assign(system=lambda d: d.sys_full.map(sysid))[['customer', 'system']]
    private_out(sys_map, 'customer_system_map')


# ----------------------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=str(DB_DEFAULT))
    ap.add_argument('--with-telemetry', action='store_true', help='also scan transaction_events (slow, 17 GB)')
    args = ap.parse_args()
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    raw, maps, cases = load()
    print(f'cases {len(raw)}, accounts {raw.account.nunique()}, ticketed serials {raw.serial.nunique()}')

    print('2. account granularity')
    acc = account_table(raw)
    acc, reviewed = apply_review(acc)
    out(site_and_system_counts(acc, reviewed), 'account_granularity')
    dist = pd.concat([system_distribution(acc, c) for c in
                      (['sys_L2a', 'sys_L2b'] + (['sys_name', 'sys_full'] if reviewed else []))])
    out(dist, 'system_size_distribution')
    if reviewed:
        out(cluster_review(acc), 'l2b_cluster_review')
        seg = acc.groupby('segment').agg(accounts=('account', 'size'), systems=('sys_full', 'nunique'),
                                         tickets=('tickets', 'sum'), ticketed_machines=('ticketed_machines', 'sum')).reset_index()
        out(seg, 'segments')
        ev = acc.groupby(['full_evidence', 'full_confidence']).size().rename('accounts').reset_index()
        out(ev, 'review_evidence')
    out(shared_addresses(acc), 'shared_addresses')
    country = raw.groupby('Shipping Country').agg(tickets=('case_id', 'size'), accounts=('account', 'nunique')).reset_index()
    out(country, 'shipping_country')

    print('1. serials under more than one account')
    pub, priv = multi_account_serials(raw, acc)
    out(pub, 'multi_account_serials')
    out(pub.groupby(['relationship', 'rule_class']).size().rename('serials').reset_index(), 'multi_account_serial_classes')
    manual = PRIVATE / 'fleet_private_serial_manual_review.csv'      # optional hand-written readings (private)
    if manual.exists():
        priv = priv.merge(pd.read_csv(manual, dtype=str), on='machine', how='left')
    private_out(priv, 'multi_account_serials')
    out(serial_integrity(raw), 'serial_integrity')

    print('3. coverage and naive rates')
    per, summ = naive_rates(raw, cases)
    out(summ, 'naive_rate_summary')
    out(coverage_bounds(raw), 'coverage_bounds')
    out(truncation_illustration(), 'truncation_illustration')

    sys_size = acc.groupby('sys_full').account.transform('size')
    per = per.merge(acc.assign(reviewed_system_accounts=sys_size, name_tier_system_accounts=acc.groupby('sys_name')
                               .account.transform('size'))[['customer', 'reviewed_system_accounts',
                                                            'name_tier_system_accounts', 'segment']], on='customer')
    out(per.assign(in_reviewed_multi_account_system=per.reviewed_system_accounts > 1,
                   in_name_tier_multi_account_system=per.name_tier_system_accounts > 1)
        .drop(columns=['reviewed_system_accounts', 'name_tier_system_accounts', 'segment']), 'customer_naive_rates')
    top10 = per.head(10)
    out(pd.DataFrame([
        ('top-10 customers in a reviewed multi-account system', int((top10.reviewed_system_accounts > 1).sum())),
        ('top-10 customers in a name-tier multi-account system', int((top10.name_tier_system_accounts > 1).sum())),
        ('all customers in a reviewed multi-account system', int((per.reviewed_system_accounts > 1).sum())),
        ('tickets from customers in a reviewed multi-account system (%)',
         round(100 * per.loc[per.reviewed_system_accounts > 1, 'tickets'].sum() / per.tickets.sum(), 2)),
        ('tickets from customers in a name-tier multi-account system (%)',
         round(100 * per.loc[per.name_tier_system_accounts > 1, 'tickets'].sum() / per.tickets.sum(), 2)),
    ], columns=['measure', 'value']), 'facility_vs_system')
    print('4. interpreting the host audit')
    out(host_expectations(acc, per, reviewed), 'host_expectations')
    out(model_type_note(), 'model_type_note')
    out(pd.DataFrame(DB_CHECKS, columns=['check', 'name', 'query', 'decision_rule']), 'db_checks_spec')

    print('5. DB checks')
    db = Path(args.db)
    if db.exists():
        run_db_checks(db, raw, acc, args.with_telemetry)
    else:
        print(f'  telemetry DB not found at {db}; DB checks D1-D8 pending (spec in fleet_db_checks_spec.csv)')

    # private outputs with real names
    sysid = {s: f'System {i:03d}' for i, s in enumerate(sorted(acc.sys_full.unique()), 1)}
    private_out(acc.assign(system=acc.sys_full.map(sysid))[
        ['customer', 'account', 'address', 'city', 'state', 'zip5', 'tickets', 'ticketed_machines', 'brand_key',
         'sys_L2a', 'sys_L2b', 'sys_name', 'sys_full', 'system', 'segment', 'full_evidence', 'full_confidence']]
        .sort_values('customer'), 'systems')
    private_out(acc[['customer', 'sys_full']].assign(system=lambda d: d.sys_full.map(sysid))[['customer', 'system']]
                .sort_values('customer'), 'customer_system_map')
    top = per.head(10).merge(acc[['customer', 'account', 'address', 'sys_full']], on='customer')
    top_rows = top.assign(section='top10_customers_by_tickets', item=top.customer,
                          real_name=top.account, detail=top.apply(
                              lambda r: f"rank {r.rank_by_tickets}; tickets {r.tickets}; ticketed machines "
                                        f"{r.ticketed_machines}; reviewed system {r.sys_full}; {r.address}", axis=1))
    ser_rows = priv.assign(section='multi_account_serial', item=priv.machine,
                           real_name=priv.accounts_in_time_order,
                           detail=priv.apply(lambda r: f"serial {r.serial}; {r.relationship}; {r.rule_class}; systems "
                                                       f"{r.reviewed_systems}; manual: {r.get('manual_reading', '')}", axis=1))
    private_out(pd.concat([top_rows, ser_rows])[['section', 'item', 'real_name', 'detail']], 'top_customers')
    print('done')


if __name__ == '__main__':
    main()
