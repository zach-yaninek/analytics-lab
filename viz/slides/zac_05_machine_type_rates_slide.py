#!/usr/bin/env python3
"""Slide version of Zac's figure 5 (viz/zac_notebook/zac_05_machine_type_rates.py): unplanned ticket rate by
telemetry machine type, per 100 active machine-months.

Same types, bars, values, colours and overall-rate line as the full chart. The type labels drop the machine counts;
the definitions, Zac's screens, the tickets counted and the comparison with chart 10 go to the speaker notes.

Output:  viz/figures/slides/zac_05_machine_type_rates.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_05_machine_type_rates_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_05_machine_type_rates as full  # noqa: E402
import zac_data  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    r = zac_data.load_db('machine_type_rates').rename(columns={'tickets_per_100_active_months': 'rate'})
    cohort = zac_data.load_db('comparison_cohort').set_index('cohort').loc[full.COHORT]
    excl = zac_data.load_db('ticket_cohort_exclusions').set_index('reason').tickets
    period = full.window_text(zac_data.load_db('monthly_comparison').month)
    tickets, active = int(r.tickets.sum()), int(r.active_machine_months.sum())
    style.check('slide zac_05 tickets = comparison cohort tickets', int(cohort.tickets), tickets)
    all_rate = 100 * tickets / active

    eligible = r[(r.active_machine_months >= full.MIN_MONTHS) & (r.tickets >= full.MIN_TICKETS)
                 & (r.machine_type != full.UNKNOWN)]
    ranked = eligible.sort_values(['rate', 'machine_type'], ascending=[False, True], kind='mergesort')
    shown, rest = ranked.head(full.TOP_N), ranked.iloc[full.TOP_N:]
    lead, runner = shown.iloc[0], shown.iloc[1]

    d = shown.iloc[::-1]  # highest rate on top
    fig, ax = slides.figure()
    y = np.arange(len(d))
    xmax = d.rate.max() * 1.12
    pad, label_w = xmax * 0.01, xmax * 0.045  # value-label offset and approximate width (3 characters), data units
    ax.axvline(all_rate, color=style.INK2, lw=1, zorder=1)
    ax.barh(y, d.rate, height=0.5, linewidth=0, zorder=2,
            color=[style.BLUE if t == lead.machine_type else style.GRAY_LIGHT for t in d.machine_type])
    ax.text(all_rate + pad, len(d) - 0.45, f'Overall: {all_rate:.1f}', va='bottom', ha='left', fontsize=9.5,
            color=style.INK2)
    for yi, row in zip(y, d.itertuples()):
        is_lead = row.machine_type == lead.machine_type
        # Right of the bar end, unless that lands on the overall line: then inside the bar end (as the full chart).
        on_line = row.rate < all_rate < row.rate + 2 * pad + label_w
        x, ha = (row.rate - pad, 'right') if on_line else (row.rate + pad, 'left')
        ax.text(x, yi, f'{row.rate:.1f}', va='center', ha=ha, fontsize=9.5,
                color=style.SURFACE if on_line and is_lead else style.INK if is_lead else style.INK2,
                weight='bold' if is_lead else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels(d.machine_type, color=style.INK2)
    ax.set_ylim(-0.6, len(d) + 0.1)
    ax.set_xlim(0, xmax)
    style.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel('Unplanned tickets per 100 active machine-months')

    host = int(excl[full.HOST].sum())
    talk = [zac_data.UNPLANNED_DEFINITION, zac_data.ACTIVE_MONTH_DEFINITION,
            f'Shown: the {full.TOP_N} highest rates among the {len(eligible)} types that pass Zac\'s screens (at least '
            f'{full.MIN_MONTHS} active machine-months and {full.MIN_TICKETS} tickets, type known; descriptive '
            f'stability screens, not significance tests). {len(rest)} more eligible types have lower rates '
            f'({rest.rate.min():.1f} to {rest.rate.max():.1f}).',
            f'{lead.machine_type}: {int(lead.tickets)} tickets in {int(lead.active_machine_months):,} active '
            f'machine-months on {int(lead.machines)} machines.',
            f'Overall rate {all_rate:.1f} = {tickets:,} tickets over {active:,} active machine-months, all types. '
            f'Tickets counted: unplanned tickets opened in an active month of a machine on a known, non-shared host. '
            f'Left out: no device match ({int(excl[full.NO_MATCH]):,}), no transaction in the ticket\'s month '
            f'({int(excl[full.QUIET])}), shared or missing host ({host}).',
            'Ratios of totals, not adjusted for machine age, customer mix or reporting. High-ticket chart 10 also '
            'counts quiet months and the tickets opened in them, so its rates differ slightly.']
    return [slides.finish(fig, Path(out_dir) / 'zac_05_machine_type_rates.png',
                          f'{lead.machine_type} has the top ticket rate: {lead.rate / runner.rate:.1f}× the next '
                          f'type, {lead.rate / all_rate:.1f}× the overall rate',
                          f'Unplanned tickets per 100 active machine-months, the {full.TOP_N} highest-rate machine '
                          f'types, {period}', talk)]


if __name__ == '__main__':
    plot()
