#!/usr/bin/env python3
"""Slide version of chart 3 (viz/high_ticket/htm_03_observed_vs_expected.py): observed vs expected unplanned tickets
per device, coloured by outlier class.

Same points, classes, colours, jitter and reference line as the full chart. Dropped for the slide: the counts in the
legend, the label on the busiest device and the footer (class definitions, threshold and jitter notes), which go to
the speaker notes.

Output:  viz/figures/slides/htm_03_observed_vs_expected.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_03_observed_vs_expected_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import htm  # noqa: E402
import htm_03_observed_vs_expected as full  # noqa: E402  (classes, colours and footer text of the full chart)
import ipa_style as style  # noqa: E402
import slides  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    S = htm.summary()
    d = htm.load('device_exposure')
    for cls, n in S['D3_classes'].items():
        style.check(f'slide D3 {cls} devices', n, int((d['class'] == cls).sum()))
    rng = np.random.default_rng(htm.SEED)  # the full chart's jitter, same seed
    d['yj'] = d.tickets_obs + rng.uniform(-full.JITTER, full.JITTER, len(d))
    ch = d[d['class'] == 'chronic_outlier']
    zero = d[d.expected == 0]
    untested = bool(zero.q_bh.isna().all())

    fig, ax = slides.figure()
    none = d[d['class'] == 'none']
    ax.scatter(none.expected, none.yj, s=7, color=style.GRAY_LIGHT, alpha=0.55, linewidths=0, zorder=2)
    ax.plot([0, full.XMAX], [0, full.XMAX], color=style.MUTED, lw=1.2, zorder=3)
    handles = []
    for cls, name, col in reversed(full.CLASSES):  # chronic drawn last, on top
        g = d[d['class'] == cls]
        ax.scatter(g.expected, g.yj, s=38, color=col, edgecolors=style.SURFACE, linewidths=0.9, zorder=4)
        handles.insert(0, Line2D([], [], ls='', marker='o', ms=7, mfc=col, mec=style.SURFACE, mew=0.9, label=name))
    handles += [Line2D([], [], ls='', marker='o', ms=4.5, mfc=style.GRAY_LIGHT, mew=0, label='Other devices'),
                Line2D([], [], color=style.MUTED, lw=1.2, label='Observed = expected')]
    ax.set_xlim(-0.08, full.XMAX)
    ax.set_ylim(-0.6, d.tickets_obs.max() + 1.5)
    style.style_axes(ax, grid='both')
    ax.set_xlabel('Expected tickets (type rate × months active)')
    ax.set_ylabel('Observed tickets')
    ax.legend(handles=handles, loc='upper right', handletextpad=0.6, borderaxespad=0.3)

    title = (f'Chronic outliers logged a median of {ch.tickets_obs.median():.0f} tickets where about '
             f'{ch.expected.median():.1f} was expected')
    talk = [htm.chronic_definition(S),
            full.class_definition(S, d, untested),
            f'Population: {len(d):,} devices in the exposure population (shared internal host and devices with no '
            f'host excluded), unplanned tickets {htm.period_text(S)}. Points above the line logged more tickets than '
            f'their type\'s rate × months active predicts.',
            full.threshold_note(S, d),
            f'Points are jittered vertically to show overlap. {len(zero)} devices with zero exposure months sit at '
            f'x = 0.{full.hidden_note(S, d[d.expected > full.XMAX])}']
    return [slides.finish(fig, Path(out_dir) / full.PNG, title,
                          f'Observed vs expected unplanned tickets per device, {htm.period_text(S)}', talk)]


if __name__ == '__main__':
    plot()
