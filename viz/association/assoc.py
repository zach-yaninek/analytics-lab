"""Data and definitions for the association charts (viz/association/as_*.py).

The charts read only what verification/association.py has already written:
  verification/outputs/assoc/as_*.csv         every plotted series
  verification/outputs/assoc/as_summary.json  pinned counts and the H2a / H1 decisions
The term definitions drawn on the charts are kept here, so every chart words them the same way (docs/07 §2, §4).
The look and page layout come from viz/style/ipa_style.py. There are no real-name variants: no customer is shown.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ASSOC = ROOT / 'verification' / 'outputs' / 'assoc'
FIG_DIR = ROOT / 'viz' / 'figures'
K7, K30 = 168.0, 720.0

TARGET_DEFINITION = ('Code set: the telemetry codes a ticket\'s Category points at in crosswalk v0, drafted from the '
                     'code descriptions alone and approved by the team before any result was computed (docs/07 §3).')
CONTROL_DEFINITION = ('Control: the same machine\'s ticket-free 30 days ending 35 days before the ticket. The final 7 '
                      'days of the ticket window are compared with the final 7 days of the control.')
MOR_DEFINITION = ('Matched odds ratio: tickets with the codes present only before the ticket, divided by tickets with '
                  'them present only in the control. Above 1 means present before tickets more often.')
SPECIFICITY_DEFINITION = ('Specificity ratio: the matched odds ratio for tickets whose Category points at the set, '
                          'divided by the same ratio for tickets of other faults on the same machine types '
                          '(Mantel-Haenszel within machine type x quarter).')


def load(name):
    """verification/outputs/assoc/as_<name>.csv as a DataFrame."""
    return pd.read_csv(ASSOC / f'as_{name}.csv')


def summary():
    return json.loads((ASSOC / 'as_summary.json').read_text())


def source(*names):
    files = ', '.join(f'as_{n}.csv' for n in names)
    return (f'Source: committed last-10 code windows (fu_ticket_last10.csv) and crosswalk v0; '
            f'verification/outputs/assoc/{files}. Provisional until IPA confirms the code meanings (crosswalk v1).')


def set_label(categories, codes):
    """'SAM (14, 17, 18, 32-35)': the Category and its codes, consecutive runs collapsed."""
    nums = sorted(int(c) for c in codes.split('|'))
    runs, start = [], nums[0]
    for a, b in zip(nums, nums[1:] + [None]):
        if b != a + 1:
            runs.append(f'{start:02d}' if start == a else f'{start:02d}-{a:02d}')
            start = b
    return f'{categories} ({", ".join(runs)})'


def x_of(v, lo, hi):
    """Clip a ratio to the plotted range; +inf goes to the right edge."""
    if np.isinf(v):
        return hi
    return min(max(v, lo), hi)
