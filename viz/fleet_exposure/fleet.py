"""Data and definitions for the fleet-exposure charts (viz/fleet_exposure/fx_*.py).

The charts read only the outputs that verification/fleet_exposure.py has already written:
  verification/outputs/fleet/fx_*.csv         every plotted series
  verification/outputs/fleet/fx_summary.json  definitions (period, split, thresholds) and headline counts
The term definitions drawn on the charts are built here from fx_summary.json, so they always match the analysis.
The look and page layout come from viz/style/ipa_style.py. Real-name variants read the gitignored
data/private/fx_private_customer_names.csv and write to deliverables/ (gitignored).
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / 'verification' / 'outputs'
FLEET = OUTPUTS / 'fleet'
FIG_DIR = ROOT / 'viz' / 'figures'
PRIVATE = ROOT / 'data' / 'private'
DELIVERABLES = ROOT / 'deliverables'
SEED = 15072


def load(name):
    """verification/outputs/fleet/fx_<name>.csv as a DataFrame."""
    return pd.read_csv(FLEET / f'fx_{name}.csv')


def summary():
    return json.loads((FLEET / 'fx_summary.json').read_text())


def htm_summary():
    return json.loads((OUTPUTS / 'htm_summary.json').read_text())


def source(*names):
    """Footer source line naming the CSVs a chart reads."""
    files = ', '.join(f'fx_{n}.csv' for n in names)
    return (f'Source: IPA installed-base list (19 Oct 2026) joined to the case export; '
            f'verification/outputs/fleet/{files}.')


def _d(x):
    return pd.Timestamp(x)


def period_text(S=None):
    """'Aug 2025 to Aug 2026' (the ticket and exposure period)."""
    S = S or summary()
    start, end = (_d(x).strftime('%b %Y') for x in S['definitions']['period'])
    return f'{start} to {end}'


def half_texts(S=None):
    """('1 Aug 2025 to 14 Feb 2026', '15 Feb to 31 Aug 2026') for the two halves of the period."""
    S = S or summary()
    start, end = (_d(x) for x in S['definitions']['period'])
    split = _d(S['definitions']['split'])
    before = split - pd.Timedelta(days=1)
    return (f'{start.day} {start:%b %Y} to {before.day} {before:%b %Y}',
            f'{split.day} {split:%b} to {end.day} {end:%b %Y}')


def fleet_rate(S=None):
    S = S or summary()
    return S['fleet']['rate_per_100']


# ---------------------------------------------------------------------------------------------------------------
# Definitions drawn on the charts (first footer lines)
# ---------------------------------------------------------------------------------------------------------------
def installed_month_definition(S=None):
    S = S or summary()
    start, end = (_d(x) for x in S['definitions']['period'])
    return (f'Installed machine-month = one month (30.4 days) that a machine on IPA\'s installed-base list was '
            f'installed during {period_text(S)}: from its install date, or {start.day} {start:%b %Y} if earlier, to '
            f'{end.day} {end:%b %Y}. Machines installed after the period count 0 months. Rates count unplanned '
            f'tickets on listed machines only, and leave out the {S["third_party"]["machines"]} machines on a '
            f'third-party service plan, whose service rarely reaches IPA\'s case export '
            f'({S["third_party"]["tickets"]} unplanned tickets in {S["third_party"]["months"]:,.0f} machine-months).')


def expected_definition(S=None):
    S = S or summary()
    return ('Expected tickets = what the machines would generate at fleet rates for their model and age: installed '
            'months × a model factor × an age factor (Poisson main-effects fit, models under '
            f'{S["definitions"]["min_type_months"]} months pooled), so the whole fleet has as many expected as '
            'observed tickets.')


AGE_STD_DEFINITION = ('Age-standardised ratio = a model\'s unplanned tickets ÷ the tickets its machines would '
                      'generate at the fleet\'s rate for their age (joint model + age fit): 1 = in line with the '
                      'fleet once machine age is allowed for.')

STR_DEFINITION = ('Standardised ticket ratio (STR) = observed ÷ expected tickets: 1 = in line with its fleet, '
                  '2 = twice the tickets its machines would generate at fleet rates.')


def flagged_customer_definition(S=None):
    S = S or summary()
    d = S['definitions']
    return (f'Flagged customer = {d["min_flag_tickets"]} or more unplanned tickets and more than its machines would '
            f'generate at fleet rates for their model and age, beyond chance (Poisson test, Benjamini-Hochberg '
            f'q < {d["q_cut"]:g}). A screening flag for follow-up, not proof of a problem.')


def flagged_machine_definition(S=None):
    S = S or summary()
    d = S['definitions']
    return (f'Flagged machine = {d["min_flag_tickets"]} or more unplanned tickets and more than its model and age '
            f'predict beyond chance (Poisson test, Benjamini-Hochberg q < {d["q_cut"]:g} over all listed machines).')


def funnel_definition(S=None):
    return ('Funnel limits allow for the normal spread between customers (overdispersion-adjusted funnel, '
            'Spiegelhalter 2005); a customer outside the 99.8% limit is unusual even among customers, not just '
            'beyond chance.')


def funnel_limits(expected, z, S=None):
    """(lower, upper) STR limits of the overdispersion-adjusted funnel at the given expected counts; z = 1.96 for
    95%, 3.09 for 99.8%. tau2 = 0 gives the plain Poisson (square-root scale) limits."""
    import numpy as np
    S = S or summary()
    e = np.asarray(expected, float)
    half = z * np.sqrt(1 / (4 * e) + S['customers']['tau2'])
    return np.maximum(0.0, 1 - half) ** 2, (1 + half) ** 2


def poisson_limits(expected, z):
    """Funnel limits with no allowance for spread between customers (tau2 = 0), square-root scale."""
    import numpy as np
    e = np.asarray(expected, float)
    half = z / (2 * np.sqrt(e))
    return np.maximum(0.0, 1 - half) ** 2, (1 + half) ** 2


def consistent_definition(S=None):
    S = S or summary()
    d = S['definitions']
    h1, h2 = half_texts(S)
    return (f'Consistent outlier = flagged in at least {d["min_variants"]} of {d["n_variants"]} method variants '
            f'(3 adjustments: model, model + age, model + age + coverage; tickets or {d["episode_gap_days"]}-day '
            f'episodes; with or without monitoring and No Trouble Found tickets) and above its expected tickets beyond '
            f'chance in both halves of the period ({h1}; {h2}; Poisson p < 0.05 in each): persistently above the '
            f'fleet\'s rate for the same models and ages.')


def span_month_definition():
    """Telemetry-span machine-month (interim telemetry-type rates, until the DB extract arrives)."""
    H = htm_summary()
    lo, hi = (_d(x) for x in H['definitions']['period'])
    return (f'Telemetry machine-month = a month of {lo:%b %Y} to {hi:%b %Y} within a telemetry device\'s '
            f'first-to-last-transaction span, quiet months included (devices on the shared internal host or with no '
            f'host excluded). Used until the device list can be joined to the installed-base list.')


def unplanned_definition():
    sys.path.insert(0, str(ROOT / 'viz' / 'zac_notebook'))
    import zac_data
    return zac_data.UNPLANNED_DEFINITION


# ---------------------------------------------------------------------------------------------------------------
# Real names (gitignored inputs; never drawn on the pseudonymous figures)
# ---------------------------------------------------------------------------------------------------------------
def real_customer_names():
    """Customer NNN -> real account name for the customers the real-name variants label. None if absent."""
    path = PRIVATE / 'fx_private_customer_names.csv'
    if not path.exists():
        return None
    df = pd.read_csv(path)
    return dict(zip(df.customer, df.real_account_name))


def real_strings():
    """Real account names and hospital addresses (list and case export) for the privacy scan; empty if
    the raw files are absent. Never printed."""
    sys.path.insert(0, str(ROOT / 'verification'))
    try:
        import common
        if not common.EQUIPMENT.exists() or not common.XLS.exists():
            return set()
        raw = common.load_raw()
        real = set(raw['Account Name'].map(common.clean).dropna().astype(str))
        real |= common.equipment_real_strings(columns=['Account Name', 'Hospital Address'])
    except ImportError:
        return set()
    return {r for r in real if len(r) >= 4 and not r.isdigit()}
