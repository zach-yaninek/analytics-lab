#!/usr/bin/env python3
"""Ticket rate by telemetry machine type, adjusted for exposure: unplanned tickets per 100 machine-months.

The companion to chart 9's raw counts. Dividing each type's tickets by its machine-months removes the effect of how
many machines of that type are installed and how long each was in service, so types can be compared fairly.

One dot per machine type with at least the analysis's minimum exposure (100 machine-months); the line through it is
a 95% Poisson interval (Byar's approximation). The vertical line is the fleet rate. The three types with the most
tickets in raw counts (chart 9) are drawn in blue so the change in ranking is visible. The machine-month definition
is printed on the chart (style.machine_month_definition).

Inputs:  verification/outputs/htm_type_rates.csv (machine_type, devices, exposure_months, tickets_used_for_rate,
         rate_group), htm_type_mix.csv (raw ticket counts by machine type, for the blue highlight),
         htm_summary.json (period, minimum type exposure, fleet rate)
Output:  verification/outputs/figures/htm_10_ticket_rate_by_machine_type.png
Run:     cd /home/user/analytics-lab && python3 -I verification/plots/htm_10_ticket_rate_by_machine_type.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import style  # noqa: E402

Z = 1.96          # 95% interval
N_RAW_TOP = 3     # types highlighted as the raw-count leaders (chart 9)
NOT_MATCHED = '(not device-matched)'


def poisson_interval(k, z=Z):
    """Byar's approximation to the exact Poisson interval for a count k (accurate to a few % even for small k)."""
    k = np.asarray(k, float)
    lo = np.where(k > 0, k * (1 - 1 / (9 * np.maximum(k, 1)) - z / (3 * np.sqrt(np.maximum(k, 1)))) ** 3, 0.0)
    hi = (k + 1) * (1 - 1 / (9 * (k + 1)) + z / (3 * np.sqrt(k + 1))) ** 3
    return lo, hi


def plot(out_dir=style.FIG_DIR):
    out_dir = Path(out_dir)
    S = style.summary()
    D2, min_months = S['D2_exposure'], S['definitions']['min_type_months']
    r = style.load('type_rates')

    # Fleet rate over every type, as in the analysis (tickets incl. those on devices with no machine-months).
    fleet = 100 * r.tickets_used_for_rate.sum() / r.exposure_months.sum()
    style.check('htm_10 fleet rate per 100 machine-months', D2['overall_rate_per_100_months'], round(fleet, 4), 1e-4)
    style.check('htm_10 machine-months', D2['exposure_months_total'], int(r.exposure_months.sum()))

    d = r[r.exposure_months >= min_months].copy()
    small = r[r.exposure_months < min_months]
    d['rate'] = 100 * d.tickets_used_for_rate / d.exposure_months
    style.check('htm_10 rates = analysis type rates', 0,
                float((d.rate - d.rate_per_100_months).abs().max()), 1e-9)
    lo, hi = poisson_interval(d.tickets_used_for_rate)
    d['lo'], d['hi'] = 100 * lo / d.exposure_months, 100 * hi / d.exposure_months
    d = d.sort_values(['rate', 'machine_type'], ascending=[True, True], kind='mergesort')  # highest rate at the top

    tm = style.load('type_mix')
    raw = tm[(tm.field == 'machine_type') & (tm.value != NOT_MATCHED)]
    raw_top = raw.sort_values(['unplanned_tickets', 'value'], ascending=[False, True], kind='mergesort') \
        .value.head(N_RAW_TOP).tolist()
    d['raw_top'] = d.machine_type.isin(raw_top)

    fig, ax = style.figure(10, 1.9 + 0.34 * len(d) + 2.2)
    y = np.arange(len(d))
    colors = np.where(d.raw_top, style.BLUE, style.GRAY)
    ax.axvline(fleet, color=style.INK2, lw=1, zorder=1)
    ax.hlines(y, d.lo, d.hi, color=style.GRAY_LIGHT, lw=2, zorder=2)
    ax.scatter(d.rate, y, s=60, c=colors, edgecolors=style.SURFACE, linewidths=1.4, zorder=3)
    for yi, row in zip(y, d.itertuples()):
        x = row.hi + 0.4
        if fleet - 1.3 < x < fleet + 0.3:  # the label would sit on the fleet line: move it just right of the line
            x = fleet + 0.3
        ax.text(x, yi, f'{row.rate:.1f}', va='center', ha='left', fontsize=9.5,
                color=style.INK if row.raw_top else style.INK2, weight='bold' if row.raw_top else 'normal')
    ax.text(fleet + 0.3, len(d) - 0.35, f'Fleet: {fleet:.1f}', va='bottom', ha='left', fontsize=9.5,
            color=style.INK2)
    labels = [('Unknown (no type recorded)' if t == 'Unknown' else t) + f'  ·  {n:,} devices'
              for t, n in zip(d.machine_type, d.devices)]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    ax.set_ylim(-0.7, len(d) + 0.3)
    ax.set_xlim(0, d.hi.max() + 3)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Unplanned tickets per 100 machine-months')
    ax.legend(handles=[Line2D([], [], marker='o', ls='', ms=8, mfc=style.BLUE, mec=style.SURFACE,
                              label=f'Top {N_RAW_TOP} by raw ticket count (chart 9)'),
                       Line2D([], [], marker='o', ls='', ms=8, mfc=style.GRAY, mec=style.SURFACE,
                              label='Other machine types'),
                       Line2D([], [], color=style.GRAY_LIGHT, lw=2, label='95% Poisson interval')],
              loc='lower right')

    top = d.iloc[-1]
    raw_rates = d[d.raw_top].sort_values('rate', ascending=False).rate
    style.frame(
        fig,
        f'Per machine-month, {top.machine_type} has the highest ticket rate: {top.rate:.1f}, '
        f'{top.rate / fleet:.1f}× the fleet',
        f'Unplanned tickets per 100 machine-months by telemetry machine type, {style.period_text(S)}: '
        f'{int(d.tickets_used_for_rate.sum()):,} tickets over {int(d.exposure_months.sum()):,} machine-months. '
        f'Adjusting for exposure, the three types with the most tickets sit near the fleet rate of {fleet:.1f} '
        f'({", ".join(f"{v:.1f}" for v in raw_rates)}): their lead in raw counts is mostly fleet size.',
        notes=[f'The fleet rate of {fleet:.1f} per 100 machine-months is about {12 * fleet / 100:.1f} tickets per '
               f'machine per year. The Poisson interval understates uncertainty because machines of one type differ '
               f'from each other (see chart 3). Tickets include those on devices with no machine-months '
               f'({int(r.tickets_on_zero_exposure_devices.sum())} fleet-wide).',
               f'Not shown: {len(small)} types with fewer than {min_months} machine-months ('
               f'{int(small.exposure_months.sum()):,} machine-months, {int(small.tickets_used_for_rate.sum())} '
               f'tickets in all); their rates are too unstable to compare.',
               'Source: htm_type_rates.csv; raw counts from htm_type_mix.csv.'],
        definitions=[style.machine_month_definition(S)])
    return [style.save(fig, out_dir / 'htm_10_ticket_rate_by_machine_type.png')]


if __name__ == '__main__':
    plot()
