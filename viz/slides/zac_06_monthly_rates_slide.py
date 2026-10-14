#!/usr/bin/env python3
"""Slide version of Zac's figure 6 (viz/zac_notebook/zac_06_monthly_rates.py): monthly ticket and fault-code rates,
Aug 2025 to Jul 2026.

Same two panels, lines, points, colours and overall-rate lines as the full chart. Only the lowest and highest month
of each panel keep their value labels (the full chart labels every month), so the panels get a hairline y grid; the
definitions, the population and the notes go to the speaker notes.

Output:  viz/figures/slides/zac_06_monthly_rates.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_06_monthly_rates_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_06_monthly_rates as full  # noqa: E402
import zac_data  # noqa: E402


def panel(ax, x, values, ref, title, color, emphasis=False):
    """One monthly series: line and points, the overall-rate line labelled at its right end, and value labels on
    the lowest and highest month (away from the overall line; bold when emphasis)."""
    lo, hi = int(np.argmin(values)), int(np.argmax(values))
    ax.hlines(ref, x[0] - 0.4, x[-1] + 0.35, color=style.INK2, lw=1, zorder=1)
    ax.text(x[-1] + 0.5, ref, f'Overall: {ref:.2f}', va='center', ha='left', fontsize=9, color=style.INK2)
    ax.plot(x, values, color=color, lw=2, zorder=2)
    ax.scatter(x, values, s=34, color=color, edgecolors=style.SURFACE, linewidths=1.2, zorder=3)
    for i in (lo, hi):
        above = values[i] >= ref
        ax.annotate(f'{values[i]:.2f}', xy=(x[i], values[i]), xytext=(0, 8 if above else -8),
                    textcoords='offset points', ha='center', va='bottom' if above else 'top',
                    fontsize=9.5 if emphasis else 9, color=style.INK if emphasis else style.INK2,
                    weight='bold' if emphasis else 'normal')
    ax.set_ylim(0, max(values) * 1.2)
    ax.set_title(title, fontsize=10.5, color=style.INK, pad=8)
    style.style_axes(ax, grid='y', baseline='bottom')


def plot(out_dir=slides.FIG_DIR):
    m = zac_data.load_db('monthly_comparison')
    types = zac_data.load_db('machine_type_rates')
    excl = zac_data.load_db('ticket_cohort_exclusions').set_index('reason').tickets
    unplanned = int(zac_data.load('case_monthly').set_index('month').loc[m.month, 'unplanned_tickets'].sum())
    months = pd.to_datetime(m.month, format='%Y-%m')
    first, last = months.iloc[0], months.iloc[-1]
    style.check('slide zac_06 ticket rates = 100 x tickets / active machine-months', 0,
                float((100 * m.tickets / m.active_machine_months - m[full.TICKETS]).abs().max()), 1e-9)
    ticket_ref = 100 * m.tickets.sum() / m.active_machine_months.sum()
    fault_ref = 1000 * types.fault_transactions.sum() / m.transactions.sum()
    t, f = m[full.TICKETS].to_numpy(), m[full.FAULTS].to_numpy()
    f_peak = int(np.argmax(f))
    f_low = f_peak + int(np.argmin(f[f_peak:]))

    style.apply_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(slides.WIDTH, slides.HEIGHT), layout='constrained')
    x = np.arange(len(m))
    panel(ax1, x, t, ticket_ref, 'Unplanned tickets per 100 active machine-months', style.BLUE, emphasis=True)
    panel(ax2, x, f, fault_ref, 'Provisional fault codes per 1,000 transactions', style.GRAY)
    ax2.set_xticks(x)
    ax2.set_xticklabels(full.month_labels(months))
    ax2.set_xlim(-0.5, len(m) + 0.5)

    talk = [zac_data.UNPLANNED_DEFINITION, zac_data.ACTIVE_MONTH_DEFINITION, zac_data.fault_code_definition(),
            f'Population: machines on known, non-shared hosts, {first:%b %Y} to {last:%b %Y}: '
            f'{int(m.active_machine_months.sum()):,} active machine-months, {int(m.tickets.sum()):,} unplanned tickets '
            f'and {m.transactions.sum() / 1e6:.0f} million transactions. Horizontal lines: the overall rate for the '
            f'{len(m)} months.',
            f'The fault-code rate rises from {f[0]:.2f} in {first:%b %Y}, peaks at {f[f_peak]:.2f} in '
            f'{months.iloc[f_peak]:%b %Y}, then falls to {f[f_low]:.2f} in {months.iloc[f_low]:%b %Y}.',
            f'One year of data cannot establish seasonality, and changes in machine mix, reporting and which machines '
            f'report can move the series. {last + pd.DateOffset(months=1):%b %Y} is left out: its telemetry is '
            f'incomplete.',
            f'Tickets counted: {int(m.tickets.sum()):,} of the {unplanned:,} unplanned tickets opened in these months. '
            f'The rest have no device match ({int(excl[full.NO_MATCH]):,}), no transaction in the ticket\'s month '
            f'({int(excl[full.QUIET])}), or a shared or missing host ({int(excl[full.HOST].sum())}).']
    return [slides.finish(fig, Path(out_dir) / 'zac_06_monthly_rates.png',
                          f'No clear trend or seasonality in the monthly ticket rate: {t.min():.2f} to {t.max():.2f}',
                          f'Monthly ticket and fault-code rates, {first:%b %Y} to {last:%b %Y}', talk)]


if __name__ == '__main__':
    plot()
