"""Data and definitions for the high-ticket-machine charts (viz/high_ticket/htm_*.py).

The charts read only the outputs that verification/high_ticket_machines.py has already written:
  verification/outputs/htm_*.csv         every plotted series
  verification/outputs/htm_summary.json  definitions (thresholds) and a few simulation results with no CSV column
The term definitions drawn on the charts (workload-outsized, chronic outlier, machine-month) are built here from
htm_summary.json, so they always match the analysis. The look and page layout come from viz/style/ipa_style.py.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / 'verification' / 'outputs'
FIG_DIR = ROOT / 'viz' / 'figures'
PRIVATE = ROOT / 'data' / 'private'
DELIVERABLES = ROOT / 'deliverables'
SEED = 15072


def load(name):
    """verification/outputs/htm_<name>.csv as a DataFrame."""
    return pd.read_csv(OUTPUTS / f'htm_{name}.csv')


def summary():
    return json.loads((OUTPUTS / 'htm_summary.json').read_text())


def period_text(S=None, which='period'):
    """'Aug 2025 to Jul 2026' for S['definitions'][which]: 'period' = the rate-test / exposure window,
    'case_export_period' = first to last opened ticket in the case export."""
    S = S or summary()
    start, end = (pd.Timestamp(x).strftime('%b %Y') for x in S['definitions'][which])
    return f'{start} to {end}'


def outsized_definition(S=None):
    S = S or summary()
    w, d = S['D1_workload'], S['definitions']
    return (f'Workload-outsized = {w["threshold"]} or more unplanned tickets in the case export '
            f'({period_text(S, "case_export_period")}): the ticket count of the {w["rank_k"]}th busiest machine, i.e. '
            f'the top {d["top_share"]:.0%} of {w["machines"]:,} ticketed machines, ties included.')


def chronic_definition(S=None):
    S = S or summary()
    w, d = S['D1_workload'], S['definitions']
    return (f'Chronic outlier = a machine that is both workload-outsized ({w["threshold"]} or more unplanned '
            f'tickets in the case export, {period_text(S, "case_export_period")}: the top {d["top_share"]:.0%} of '
            f'ticketed machines, ties included) and a rate outlier (more tickets from {period_text(S)} than its '
            f'machine type\'s rate × months active predicts, small types pooled; Poisson test, Benjamini-Hochberg '
            f'q < {d["q_cut"]:g}). A screening flag for follow-up, not proof of a defect.')


def machine_month_definition(S=None):
    S = S or summary()
    lo, hi = (pd.Timestamp(x) for x in S['definitions']['period'])
    n_months = (hi.year - lo.year) * 12 + hi.month - lo.month + 1
    return (f'Machine-month = one month of a machine in service. Each telemetry device counts the months of '
            f'{period_text(S)} that fall within its first-to-last-transaction span, both end months included and quiet '
            f'months in between too, so a machine active throughout adds {n_months}. Devices with no transaction in '
            f'that window count 0 months but stay in the device counts and rates. Devices on the shared internal host '
            f'or with no host are excluded.')
