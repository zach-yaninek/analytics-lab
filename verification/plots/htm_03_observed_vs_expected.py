#!/usr/bin/env python3
"""Chart 3: observed vs expected unplanned tickets per device, coloured by outlier class.

Each device in the exposure population (shared internal host and devices with no host excluded) is one point: its observed unplanned tickets in the
period against the count its machine type's rate x months active predicts. Chronic outliers (workload-outsized and
rate outlier), rate outliers only and workload-outsized-only devices are drawn over the other devices, with the
observed = expected line for reference. The title states the chronic outliers' median observed vs expected count.
The footer explains why some workload-outsized devices sit below the ticket threshold on this axis: the threshold
counts the serial's tickets over the whole case export, the y-axis the device's tickets in the period.

Inputs:
  verification/outputs/htm_device_exposure.csv  expected, tickets_obs, class, workload_outsized, rate_outlier,
                                                serial_unplanned_tickets, machine_type, q_bh, machine_id, model
  verification/outputs/htm_summary.json         definitions.period, definitions.q_cut, D1_workload.threshold,
                                                D2_exposure (devices, devices_with_exposure, tickets,
                                                rate_outliers_poisson, pooled_small_types), D3_classes
Output:
  verification/outputs/figures/htm_03_observed_vs_expected.png

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_03_observed_vs_expected.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import style  # noqa: E402

PNG = 'htm_03_observed_vs_expected.png'
XMAX = 3.4      # right edge of the x-axis; the few devices beyond it are counted in the footer
JITTER = 0.22   # vertical jitter (tickets) to show overlapping integer counts

# (class value, name, colour), in legend order. The legend and the class-definition line use these names.
CLASSES = [
    ('chronic_outlier', 'Chronic outlier', style.BLUE),
    ('rate_outlier_only', 'Rate outlier only', style.ORANGE),
    ('high_volume_expected', 'Workload-outsized only', style.AQUA),  # high volume, as expected for its exposure
]
NAME = {c: n for c, n, _ in CLASSES}


def count_phrase(n, what):
    return f'{n} {what}' if n == 1 else f'{n} {what}s'


def class_definition(d, untested):
    """One line defining the two non-chronic classes."""
    hv0 = int(((d['class'] == 'high_volume_expected') & (d.expected == 0)).sum())
    zero_txt = (f', including {hv0} {"untested " if untested else ""}devices with zero exposure months (x = 0)'
                if hv0 else '')
    return (f'{NAME["rate_outlier_only"]} = a rate outlier that is not workload-outsized. '
            f'{NAME["high_volume_expected"]} = workload-outsized but not a rate outlier: high volume, as expected for '
            f'its type and months active{zero_txt}.')


def threshold_note(S, d):
    """The workload flag counts the serial's tickets over the whole case export, not the device's tickets in the
    period plotted, so a workload-outsized device can sit below the threshold here. Counts those devices."""
    thr = S['D1_workload']['threshold']
    low = d.tickets_obs < thr
    counts = [(int((low & (d['class'] == 'chronic_outlier')).sum()), 'chronic outlier'),
              (int((low & (d['class'] == 'high_volume_expected')).sum()), f'{NAME["high_volume_expected"].lower()} device')]
    text = ('Workload-outsized counts the serial\'s unplanned tickets over the whole case export, not the device\'s '
            'tickets in the period plotted here')
    if any(n for n, _ in counts):
        below = ' and '.join(count_phrase(n, what) for n, what in counts if n)
        text += f', so {below} {"sits" if sum(n for n, _ in counts) == 1 else "sit"} below {thr} on this axis'
    return text + '.'


def hidden_note(S, hidden):
    if hidden.empty:
        return ''
    n_pool = int(hidden.machine_type.isin(S['D2_exposure']['pooled_small_types']).sum())
    n_flag = int((hidden['class'] != 'none').sum())
    parts = []
    if n_pool == len(hidden):
        parts.append('pooled small types')
    elif n_pool:
        parts.append(f'{n_pool} in pooled small types')
    parts.append('none flagged' if n_flag == 0 else f'{n_flag} flagged')
    return (f' {count_phrase(len(hidden), "device")} with expected above {XMAX} ({", ".join(parts)}) '
            f'{"is" if len(hidden) == 1 else "are"} off the right edge.')


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
    # A device's tickets in the period are a subset of its serial's case-export tickets, so no "Rate outlier only"
    # device can sit at or above the threshold on the y-axis (the footer only counts flagged devices below it).
    style.check('device tickets in period <= serial case-export tickets', 0,
                int((d.tickets_obs > d.serial_unplanned_tickets).sum()))

    rng = np.random.default_rng(style.SEED)
    d['yj'] = d.tickets_obs + rng.uniform(-JITTER, JITTER, len(d))
    hidden = d[d.expected > XMAX]
    zero = d[d.expected == 0]
    untested = bool(zero.q_bh.isna().all())
    ch = d[d['class'] == 'chronic_outlier']

    fig, ax = style.figure(10, 8.2)
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

    style.frame(
        fig,
        f'Chronic outliers logged a median of {ch.tickets_obs.median():.0f} tickets where about '
        f'{ch.expected.median():.1f} was expected',
        f'{len(d):,} devices in the exposure population (shared internal host and devices with no host excluded), '
        f'unplanned tickets {style.period_text(S)}. '
        f'Points above the line logged more tickets than their type\'s rate × months active predicts.',
        definitions=[style.chronic_definition(S), class_definition(d, untested)],
        notes=[threshold_note(S, d),
               f'Points jittered vertically by up to {JITTER} to show overlap. {len(zero)} devices with zero '
               f'exposure months sit at x = 0{" (not tested)" if untested else ""}.{hidden_note(S, hidden)}',
               'Source: htm_device_exposure.csv; thresholds from htm_summary.json.'])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
