#!/usr/bin/env python3
"""Slide version of chart 10 (viz/high_ticket/htm_10_ticket_rate_by_machine_type.py): unplanned tickets per 100
machine-months by telemetry machine type.

Same types, order, dots, 95% intervals, colours and fleet line as the full chart. Dropped for the slide: the device
counts in the type labels and the rate labels of the gray types (the blue types and the top type keep theirs); the
machine-month definition, the population and the notes go to the speaker notes.

Output:  viz/figures/slides/htm_10_ticket_rate_by_machine_type.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_10_ticket_rate_by_machine_type_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import htm  # noqa: E402
import htm_10_ticket_rate_by_machine_type as full  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402

PNG = 'htm_10_ticket_rate_by_machine_type.png'


def plot(out_dir=slides.FIG_DIR):
    S = htm.summary()
    D2, min_months = S['D2_exposure'], S['definitions']['min_type_months']
    r = htm.load('type_rates')
    fleet = 100 * r.tickets_used_for_rate.sum() / r.exposure_months.sum()
    style.check('slide htm_10 fleet rate per 100 machine-months', D2['overall_rate_per_100_months'], round(fleet, 4),
                1e-4)

    d = r[r.exposure_months >= min_months].copy()
    small = r[r.exposure_months < min_months]
    d['rate'] = 100 * d.tickets_used_for_rate / d.exposure_months
    lo, hi = full.poisson_interval(d.tickets_used_for_rate)
    d['lo'], d['hi'] = 100 * lo / d.exposure_months, 100 * hi / d.exposure_months
    d = d.sort_values(['rate', 'machine_type'], ascending=[True, True], kind='mergesort')  # highest rate at the top
    tm = htm.load('type_mix')
    raw = tm[(tm.field == 'machine_type') & (tm.value != full.NOT_MATCHED)]
    raw_top = raw.sort_values(['unplanned_tickets', 'value'], ascending=[False, True], kind='mergesort') \
        .value.head(full.N_RAW_TOP).tolist()
    d['raw_top'] = d.machine_type.isin(raw_top)
    top = d.iloc[-1]

    fig, ax = slides.figure()
    y = np.arange(len(d))
    ax.axvline(fleet, color=style.INK2, lw=1, zorder=1)
    ax.hlines(y, d.lo, d.hi, color=style.GRAY_LIGHT, lw=2, zorder=2)
    ax.scatter(d.rate, y, s=50, c=np.where(d.raw_top, style.BLUE, style.GRAY), edgecolors=style.SURFACE,
               linewidths=1.4, zorder=3)
    for yi, row in zip(y, d.itertuples()):
        if row.raw_top or row.machine_type == top.machine_type:
            ax.text(row.hi + 0.4, yi, f'{row.rate:.1f}', va='center', ha='left', fontsize=9.5,
                    color=style.INK if row.raw_top else style.INK2, weight='bold' if row.raw_top else 'normal')
    ax.text(fleet + 0.3, len(d) - 0.35, f'Fleet: {fleet:.1f}', va='bottom', ha='left', fontsize=9.5,
            color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(['Unknown (no type recorded)' if t == 'Unknown' else t for t in d.machine_type],
                       color=style.INK2, fontsize=9.5)
    ax.set_ylim(-0.7, len(d) + 0.3)
    ax.set_xlim(0, d.hi.max() + 3)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Unplanned tickets per 100 machine-months')
    ax.legend(handles=[Line2D([], [], marker='o', ls='', ms=8, mfc=style.BLUE, mec=style.SURFACE,
                              label=f'Top {full.N_RAW_TOP} by raw ticket count'),
                       Line2D([], [], marker='o', ls='', ms=8, mfc=style.GRAY, mec=style.SURFACE,
                              label='Other machine types'),
                       Line2D([], [], color=style.GRAY_LIGHT, lw=2, label='95% interval')],
              loc='lower right')

    top3 = d[d.raw_top].sort_values('rate', ascending=False)
    vs_fleet = ', '.join(f'{u.machine_type} {100 * (u.rate / fleet - 1):+.0f}%' for u in top3.itertuples())
    talk = [htm.machine_month_definition(S),
            f'Shown: the {len(d)} types with at least {min_months} machine-months (the analysis\'s minimum for a type '
            f'to get its own rate). Not shown: {len(small)} smaller types ({int(small.exposure_months.sum()):,} '
            f'machine-months, {int(small.tickets_used_for_rate.sum())} tickets), too unstable to compare.',
            f'Fleet rate {fleet:.1f} = {int(r.tickets_used_for_rate.sum()):,} tickets over '
            f'{int(r.exposure_months.sum()):,} machine-months, all types; about {12 * fleet / 100:.1f} tickets per '
            f'machine per year.',
            f'Blue = the three types with the most tickets in raw counts (chart 9). They run only modestly above the '
            f'fleet rate ({vs_fleet}): their lead in raw counts is mostly fleet size.',
            '95% Poisson intervals show how precise each rate is; they understate uncertainty because machines of one '
            'type differ from each other.']
    return [slides.finish(fig, Path(out_dir) / PNG,
                          f'{top.machine_type} has the highest ticket rate of the {len(d)} types shown: '
                          f'{top.rate / fleet:.1f}× the fleet',
                          f'Unplanned tickets per 100 machine-months by telemetry machine type, {htm.period_text(S)}',
                          talk)]


if __name__ == '__main__':
    plot()
