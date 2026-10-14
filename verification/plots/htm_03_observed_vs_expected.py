#!/usr/bin/env python3
"""Chart 3: observed vs expected unplanned tickets per device, coloured by outlier class.

Each device in the exposure population (non-shared hosts) is one point: its observed unplanned tickets in the
period against the count its machine type's rate x months active predicts. Chronic outliers (workload-outsized and
rate outlier), rate outliers only and high-volume-as-expected devices are drawn over the other devices, with the
observed = expected line for reference. The title states the chronic outliers' median observed vs expected count.

Inputs:
  verification/outputs/htm_device_exposure.csv  expected, tickets_obs, class, workload_outsized, rate_outlier,
                                                serial_unplanned_tickets, rate_group, q_bh, machine_id, model
  verification/outputs/htm_summary.json         definitions.period, definitions.q_cut, D1_workload.threshold,
                                                D2_exposure (devices, devices_with_exposure, tickets,
                                                rate_outliers_poisson), D3_classes
Output:
  verification/outputs/figures/htm_03_observed_vs_expected.png

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_03_observed_vs_expected.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.text import Annotation  # noqa: E402

import style  # noqa: E402

PNG = 'htm_03_observed_vs_expected.png'
XMAX = 3.4      # right edge of the x-axis; the few devices beyond it are counted in the footer
JITTER = 0.22   # vertical jitter (tickets) to show overlapping integer counts

# (class value, legend name, colour), in legend order. The names are the ones the definition lines use.
CLASSES = [
    ('chronic_outlier', 'Chronic outlier', style.BLUE),
    ('rate_outlier_only', 'Rate outlier only', style.ORANGE),
    ('high_volume_expected', 'High volume, as expected', style.AQUA),
]


def class_definition(S):
    """One line defining the two non-chronic classes, from the summary threshold."""
    names = {c: n for c, n, _ in CLASSES}
    thr = S['D1_workload']['threshold']
    return (f'{names["rate_outlier_only"]} = a rate outlier with fewer than {thr} unplanned tickets; '
            f'{names["high_volume_expected"]} = workload-outsized but not a rate outlier.')


def separate_first_definition(fig, first):
    """Draw the first definition as a text artist of its own, directly above the remaining definition lines.

    style.frame() draws all definitions as one text block, but run_all.py's definition check looks for
    style.chronic_definition() as a whole drawn string. The block keeps its place (and the band frame() reserved
    for it) and keeps only the later definitions; the first one is re-drawn just above it, anchored to the block,
    so nothing is measured or positioned by hand. Does nothing when the first definition is already separate."""
    flat = ' '.join(first.split())
    for t in fig.texts:
        lines = t.get_text().split('\n')
        k = next((k for k in range(1, len(lines)) if ' '.join(' '.join(lines[:k]).split()) == flat), None)
        if k is None:
            continue
        t.set_text('\n'.join(lines[k:]))
        fig.add_artist(Annotation('\n'.join(lines[:k]), xy=(0, 1), xycoords=t, xytext=(0, 1),
                                  textcoords='offset points', ha='left', va='bottom', fontsize=t.get_fontsize(),
                                  color=t.get_color(), linespacing=t.get_linespacing()))
        return


def period_text(S):
    lo, hi = (pd.Timestamp(x) for x in S['definitions']['period'])
    return f'{lo:%b %Y} to {hi:%b %Y}'


def plot(out_dir=style.FIG_DIR):
    out_dir = Path(out_dir)
    S = style.summary()
    d = style.load('device_exposure')
    thr = S['D1_workload']['threshold']

    # Consistency with htm_summary.json (D2 exposure population, D3 classes).
    E = S['D2_exposure']
    style.check('D2 exposure devices', E['devices'], len(d))
    style.check('D2 exposure tickets', E['tickets'], int(d.tickets_obs.sum()))
    style.check('D2 zero-exposure devices', E['devices'] - E['devices_with_exposure'], int((d.expected == 0).sum()))
    style.check('D2 Poisson rate outliers', E['rate_outliers_poisson'], int(d.rate_outlier.sum()))
    for cls, n in S['D3_classes'].items():
        style.check(f'D3 {cls} devices', n, int((d['class'] == cls).sum()))
    # The class definitions drawn in the footer must describe the CSV's classes.
    expect = np.select([d.workload_outsized & d.rate_outlier, d.rate_outlier, d.workload_outsized],
                       ['chronic_outlier', 'rate_outlier_only', 'high_volume_expected'], 'none')
    style.check('D3 classes = outsized x rate-outlier flags', 0, int((d['class'] != expect).sum()))
    style.check('D1 outsized flag = serial tickets >= threshold', 0,
                int((d.workload_outsized != (d.serial_unplanned_tickets >= thr)).sum()))

    rng = np.random.default_rng(style.SEED)
    d['yj'] = d.tickets_obs + rng.uniform(-JITTER, JITTER, len(d))
    hidden = d[d.expected > XMAX]
    zero = d[d.expected == 0]
    ch = d[d['class'] == 'chronic_outlier']

    fig, ax = style.figure(10, 7.6)
    none = d[d['class'] == 'none']
    ax.scatter(none.expected, none.yj, s=7, color=style.GRAY_LIGHT, alpha=0.55, linewidths=0, zorder=2)
    ax.plot([0, XMAX], [0, XMAX], color=style.MUTED, lw=1.2, zorder=3)
    handles = []
    for cls, name, col in reversed(CLASSES):  # chronic drawn last, on top
        g = d[d['class'] == cls]
        ax.scatter(g.expected, g.yj, s=38, color=col, edgecolors=style.SURFACE, linewidths=0.9, zorder=4)
        handles.insert(0, Line2D([], [], ls='', marker='o', ms=7, mfc=col, mec=style.SURFACE, mew=0.9,
                                 label=f'{name} ({len(g):,})'))
    handles += [Line2D([], [], ls='', marker='o', ms=4.5, mfc=style.GRAY_LIGHT, mew=0,
                       label=f'Other devices ({len(none):,})'),
                Line2D([], [], color=style.MUTED, lw=1.2, label='Observed = expected')]

    top = d.sort_values(['tickets_obs', 'machine_id'], ascending=[False, True]).iloc[0]
    ax.annotate(f'{top.machine_id} · {top.model}\n{int(top.tickets_obs)} tickets vs {top.expected:.2f} expected',
                xy=(top.expected, top.yj), xytext=(28, -14), textcoords='offset points', fontsize=9.5,
                color=style.INK2, va='center', linespacing=1.35,
                arrowprops=dict(arrowstyle='-', color=style.MUTED, lw=0.8, shrinkA=2, shrinkB=5))
    ax.set_xlim(-0.08, XMAX)
    ax.set_ylim(-0.6, d.tickets_obs.max() + 1.5)
    style.style_axes(ax, grid='both')
    ax.set_xlabel('Expected tickets (type rate × months active)')
    ax.set_ylabel('Observed tickets in the period')
    ax.legend(handles=handles, loc='upper right', handletextpad=0.6, borderaxespad=0.3)

    if hidden.empty:
        hidden_txt = ''
    else:
        pooled = '(pooled small types)'
        kind = 'pooled small types' if (hidden.rate_group == pooled).all() else 'incl. pooled small types'
        n_flag = int((hidden['class'] != 'none').sum())
        hidden_txt = (f' {len(hidden)} devices with expected above {XMAX} ({kind}, '
                      f'{"none" if n_flag == 0 else n_flag} flagged) are off the right edge.')
    zero_txt = ' (not tested)' if zero.q_bh.isna().all() else ''
    style.frame(
        fig,
        f'Chronic outliers logged a median of {ch.tickets_obs.median():.0f} tickets where about '
        f'{ch.expected.median():.1f} was expected',
        f'{len(d):,} devices in the exposure population (non-shared hosts), unplanned tickets {period_text(S)}. '
        f'Points above the line logged more tickets than their type\'s rate × months active predicts.',
        definitions=[style.chronic_definition(S), class_definition(S)],
        notes=[f'Points jittered vertically by up to {JITTER} to show overlap. {len(zero)} devices with zero exposure '
               f'months sit at x = 0{zero_txt}.{hidden_txt}',
               'Source: htm_device_exposure.csv; thresholds from htm_summary.json.'])
    separate_first_definition(fig, style.chronic_definition(S))
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
