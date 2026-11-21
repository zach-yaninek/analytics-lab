#!/usr/bin/env python3
"""Zac's figure 6: monthly ticket and fault-code rates in his comparison cohort, Aug 2025 to Jul 2026.

Recreates 06_monthly_rates.png from Zac's notebook (cell 29, query monthly_comparison over his view comparison_month,
cell 27). Same population (machine-months with at least one transaction, devices on known non-shared hosts; Aug 2026
left out because its telemetry is incomplete), same two panels on a shared month axis and the same metrics: unplanned
tickets per 100 active machine-months (top) and provisional fault codes per 1,000 transactions (bottom), both ratios
of monthly totals, both axes from zero as he drew them. Added: the value of each month (two decimals, as his printed
table and range), so the y grid is left out; the lowest and highest ticket month in bold; a line at the overall
rate for the window (the name zac_05 uses for the same cohort rate). The ticket series, which the title is about, is in
blue and the fault-code series in gray. Zac's reading is kept: the ticket rate moves within a band with no direction
(his printed min-max range is the title) and one year cannot show seasonality; the subtitle describes the fault-code
series separately.

Inputs:  zac_data.load_db('monthly_comparison')        one row per month (Zac's SQL, cell 29, re-run on the DB)
         zac_data.load_db('comparison_cohort')         cohort totals (cell 27), for the totals checks
         zac_data.load_db('machine_type_rates')        fault-code transactions by type (cell 27), for the window rate
         zac_data.load_db('ticket_cohort_exclusions')  tickets left out of the cohort, by reason (cell 27)
         zac_data.load_db('monthly_comparison_vs_expected')   Zac's notebook table next to the re-run, for a check
         zac_data.load('case_monthly')                 unplanned tickets per month in the case export (cell 29)
         zac_data.fault_code_definition()              the provisional fault codes (db_codes_buckets.csv)
Output:  viz/figures/zac_06_monthly_rates.png
Run:     cd /home/user/analytics-lab && python3 -I viz/zac_notebook/zac_06_monthly_rates.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

COHORT = 'Known nonshared hosts'   # Zac's comparison cohort (comparison_cohort, cell 27)
TICKETS = 'tickets_per_100_active_months'
FAULTS = 'fault_codes_per_1000_transactions'
# Zac's ticket_cohort_exclusions reasons (cell 27): every unplanned ticket in the window has exactly one.
INCLUDED = 'Included in comparison'
NO_MATCH = 'No device match'
QUIET = 'No transactions in ticket month'
HOST = ['Missing host', 'Shared/internal host']


def month_labels(months):
    """'Aug\\n2025', 'Sep', ... with the year under the first month and under each January."""
    return [f'{d:%b}\n{d:%Y}' if i == 0 or d.month == 1 else f'{d:%b}' for i, d in enumerate(months)]


def panel(ax, x, values, ref, title, color, emphasis=False):
    """One monthly series: line and points, each month's value (away from the overall-rate line, so labels never
    sit on it), and the overall rate labelled at the right end of its line. emphasis: lowest and highest month in
    bold. Every point carries its value, so there is no y grid for the labels to run into."""
    lo, hi = int(np.argmin(values)), int(np.argmax(values))
    ax.hlines(ref, x[0] - 0.4, x[-1] + 0.35, color=style.INK2, lw=1, zorder=1)  # as the overall lines in zac_05/07
    ax.text(x[-1] + 0.5, ref, f'Overall: {ref:.2f}', va='center', ha='left', fontsize=9, color=style.INK2)
    ax.plot(x, values, color=color, lw=2, zorder=2)
    ax.scatter(x, values, s=34, color=color, edgecolors=style.SURFACE, linewidths=1.2, zorder=3)
    for i, (xi, v) in enumerate(zip(x, values)):
        bold = emphasis and i in (lo, hi)
        above = v >= ref
        ax.annotate(f'{v:.2f}', xy=(xi, v), xytext=(0, 8 if above else -8), textcoords='offset points',
                    ha='center', va='bottom' if above else 'top', fontsize=9.5 if bold else 9,
                    color=style.INK if bold else style.INK2, weight='bold' if bold else 'normal')
    ax.set_ylim(0, max(values) * 1.2)
    ax.set_title(title, fontsize=10.5, color=style.INK, pad=8)
    style.style_axes(ax, grid=None, baseline='bottom')


def plot(out_dir=zac_data.FIG_DIR):
    out_dir = Path(out_dir)
    m = zac_data.load_db('monthly_comparison')
    cohort = zac_data.load_db('comparison_cohort').set_index('cohort').loc[COHORT]
    types = zac_data.load_db('machine_type_rates')
    excl = zac_data.load_db('ticket_cohort_exclusions').set_index('reason').tickets
    cm = zac_data.load('case_monthly').set_index('month')
    months = pd.to_datetime(m.month, format='%Y-%m')  # first day of each month
    first, last = months.iloc[0], months.iloc[-1]

    # Checks: consecutive months over the active-month definition's window that add up to Zac's cohort; the rates
    # are ratios of the monthly totals.
    expected = pd.date_range(first, periods=len(m), freq='MS')
    style.check('zac_06 consecutive months', 1, int((months.to_numpy() == expected).all()))
    style.check('zac_06 window = active machine-month definition', 1,
                int(f'{first:%b %Y} to {last:%b %Y}' in zac_data.ACTIVE_MONTH_DEFINITION))
    style.check('zac_06 active machine-months = comparison cohort', int(cohort.active_machine_months),
                int(m.active_machine_months.sum()))
    style.check('zac_06 tickets = comparison cohort', int(cohort.tickets), int(m.tickets.sum()))
    style.check('zac_06 transactions = comparison cohort', int(cohort.transactions), int(m.transactions.sum()))
    style.check('zac_06 ticket rates = 100 x tickets / active machine-months', 0,
                float((100 * m.tickets / m.active_machine_months - m[TICKETS]).abs().max()), 1e-9)
    # Zac's own table (his notebook output, 2 decimals; db_monthly_comparison_vs_expected.csv) has the same rates.
    zac = zac_data.load_db('monthly_comparison_vs_expected').set_index('month').loc[m.month]
    for col in (TICKETS, FAULTS):
        style.check(f'zac_06 {col} = Zac\'s notebook table (2 decimals)', 0,
                    float(np.abs(zac[f'{col}_expected'].to_numpy() - m[col].to_numpy()).max()), 0.005)
    # The monthly fault rates imply whole fault-code counts that add up to the by-type table's total.
    fault_tx = m[FAULTS] * m.transactions / 1000
    style.check('zac_06 implied fault-code transactions are whole numbers', 0,
                float((fault_tx - fault_tx.round()).abs().max()), 1e-6)
    style.check('zac_06 fault-code transactions = machine_type_rates total', int(types.fault_transactions.sum()),
                int(fault_tx.round().sum()))
    # Cohort tickets are a subset of each month's unplanned tickets; the rest are the cohort exclusions.
    unplanned = cm.loc[m.month, 'unplanned_tickets']
    style.check('zac_06 cohort tickets <= unplanned tickets, every month', 1,
                int((m.tickets.to_numpy() <= unplanned.to_numpy()).all()))
    style.check('zac_06 exclusion reasons as named here', 1, int(set(excl.index) == {INCLUDED, NO_MATCH, QUIET, *HOST}))
    style.check('zac_06 cohort tickets = tickets included in the comparison', int(excl[INCLUDED]), int(m.tickets.sum()))
    style.check('zac_06 unplanned tickets in the window = counted + excluded', int(unplanned.sum()), int(excl.sum()))

    # Rates over the whole window, as ratios of totals (Zac's method).
    ticket_ref = 100 * m.tickets.sum() / m.active_machine_months.sum()
    fault_ref = 1000 * types.fault_transactions.sum() / m.transactions.sum()
    t, f = m[TICKETS].to_numpy(), m[FAULTS].to_numpy()
    f_peak = int(np.argmax(f))
    f_low = f_peak + int(np.argmin(f[f_peak:]))  # lowest fault rate after the peak
    style.check('zac_06 fault rate peaks inside the window (rises, then falls back)', 1, int(0 < f_peak < len(f) - 1))

    style.apply_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 8.4), layout='constrained')
    x = np.arange(len(m))
    # Blue for the ticket series the title is about; gray for the fault-code series as context.
    panel(ax1, x, t, ticket_ref, 'Unplanned tickets per 100 active machine-months', style.BLUE, emphasis=True)
    panel(ax2, x, f, fault_ref, 'Provisional fault codes per 1,000 transactions', style.GRAY)
    ax2.set_xticks(x)
    ax2.set_xticklabels(month_labels(months))
    ax2.set_xlim(-0.5, len(m) + 0.5)

    style.frame(
        fig,
        f'No clear trend or seasonality in the monthly ticket rate: {t.min():.2f} to {t.max():.2f}',
        f'By month, {first:%b %Y} to {last:%b %Y}, for machines on known, non-shared hosts: '
        f'{int(m.active_machine_months.sum()):,} active machine-months, {int(m.tickets.sum()):,} unplanned tickets and '
        f'{m.transactions.sum() / 1e6:.0f} million transactions. Horizontal lines: the overall rate for the {len(m)} '
        f'months. The fault-code rate rises from {f[0]:.2f} in {first:%b %Y}, peaks at {f[f_peak]:.2f} in '
        f'{months.iloc[f_peak]:%b %Y}, then falls to {f[f_low]:.2f} in {months.iloc[f_low]:%b %Y}.',
        notes=[f'One year of data cannot establish seasonality, and changes in machine mix, reporting and which '
               f'machines report can move the series (Zac, cell 28). {last + pd.DateOffset(months=1):%b %Y} is left '
               f'out: its telemetry is incomplete.',
               f'Tickets counted: unplanned tickets opened in an active month of a machine on a known, non-shared '
               f'host, {int(m.tickets.sum()):,} of the {int(unplanned.sum()):,} opened in these months. The rest have '
               f'no device match ({int(excl[NO_MATCH]):,}), no transaction in the ticket\'s month '
               f'({int(excl[QUIET])}), or a shared or missing host ({int(excl[HOST].sum())}).',
               'Source: verification/outputs/db/db_monthly_comparison.csv (Zac\'s SQL, notebook cell 29, re-run on the '
               'full database); tickets counted from verification/outputs/repro_sql_case_monthly.csv and '
               'verification/outputs/db/db_ticket_cohort_exclusions.csv; fault-code total from '
               'verification/outputs/db/db_machine_type_rates.csv.'],
        definitions=[zac_data.UNPLANNED_DEFINITION, zac_data.ACTIVE_MONTH_DEFINITION, zac_data.fault_code_definition()])
    return [style.save(fig, out_dir / 'zac_06_monthly_rates.png')]


if __name__ == '__main__':
    plot()
