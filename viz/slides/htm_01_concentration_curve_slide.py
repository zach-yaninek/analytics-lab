#!/usr/bin/env python3
"""Slide version of chart 1 (viz/high_ticket/htm_01_concentration_curve.py): concentration curve of unplanned tickets
over devices, observed vs chance.

Same curves, band, marker line and points as the full chart. Dropped for the slide: the counts in the annotations and
legend, the long subtitle and the footer (Gini, devices with 6 or more tickets, source), which go to the speaker notes.

Output:  viz/figures/slides/htm_01_concentration_curve.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_01_concentration_curve_slide.py
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import numpy as np  # noqa: E402

import htm  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    S = htm.summary()
    L, dev, C = htm.load('lorenz'), htm.load('device_exposure'), S['D4_concentration']
    share, fixed = S['definitions']['top_share'], S['definitions']['fixed_threshold']
    obs = np.sort(dev.tickets_obs.to_numpy())[::-1]
    top_obs = obs[:math.ceil(share * len(obs))].sum() / obs.sum()
    style.check(f'slide D4 top {100 * share:g}% share', C['top5_share_obs'], round(top_obs, 4), 1e-4)

    fig, ax = slides.figure()
    x = 100 * L.device_share
    ax.fill_between(x, 100 * L.ticket_share_null_p2_5, 100 * L.ticket_share_null_p97_5, color=style.GRAY_LIGHT,
                    alpha=0.45, linewidth=0, label='Chance: middle 95%')
    ax.plot(x, 100 * L.ticket_share_null_median, color=style.GRAY, lw=2, label='Chance: median')
    ax.plot(x, 100 * L.ticket_share_obs, color=style.BLUE, lw=2, label='Observed')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    x_top = 100 * share
    ax.axvline(x_top, color=style.MUTED, lw=0.8)
    y_obs, y_null = 100 * top_obs, 100 * C['top5_share_null_median']
    ax.scatter([x_top, x_top], [y_obs, y_null], s=60, c=[style.BLUE, style.GRAY], edgecolors=style.SURFACE,
               linewidths=1.6, zorder=5)
    # As in the full chart: observed label above the blue curve, chance label below the gray one.
    line = dict(arrowstyle='-', color=style.MUTED, lw=0.8, shrinkA=2, shrinkB=4)
    box = dict(fc=style.SURFACE, ec='none', pad=1)
    ax.annotate(f'Top {x_top:g}% of devices\n{style.pct(top_obs)} of tickets', xy=(x_top, y_obs),
                xytext=(x_top + 4, 90), fontsize=10, color=style.INK, va='center', linespacing=1.35, bbox=box,
                arrowprops=dict(line, relpos=(0, 0.5)))
    ax.annotate(f'Chance: {style.pct(C["top5_share_null_median"])}', xy=(x_top, y_null),
                xytext=(x_top + 8, y_null - 8), fontsize=10, color=style.INK2, va='center', bbox=box,
                arrowprops=line)
    style.style_axes(ax, grid='both')
    ax.set_yticks(np.arange(0, 101, 20))
    style.pct_axis(ax.xaxis)
    style.pct_axis(ax.yaxis)
    ax.set_xlabel('Share of devices, ranked by tickets (most first)')
    ax.set_ylabel('Cumulative share of tickets')
    ax.legend(loc='lower right', handlelength=2.2, frameon=True, facecolor=style.SURFACE, edgecolor='none',
              framealpha=1)

    title = (f'The top {x_top:g}% of devices hold {style.pct(top_obs, 0)} of tickets; chance alone gives '
             f'{style.pct(C["top5_share_null_median"], 0)}')
    talk = [f'Population: {len(obs):,} devices in the exposure population (shared internal host and devices with no '
            f'host excluded), {int(obs.sum()):,} unplanned tickets {htm.period_text(S)}.',
            f'Chance = {S["n_sim"]:,} Poisson draws at each device\'s expected count (its machine type\'s rate × '
            f'months active). The band is the middle 95% of the draws; for the top {x_top:g}% the 95th percentile '
            f'is {style.pct(C["top5_share_null_p95"])}.',
            f'Gini over devices: {C["gini_obs"]:.3f} observed vs {C["gini_null_median"]:.3f} by chance. Devices with '
            f'{fixed} or more tickets: {int((obs >= fixed).sum())} observed vs {C["ge6_null_median"]:.0f} by chance.']
    return [slides.finish(fig, Path(out_dir) / 'htm_01_concentration_curve.png', title,
                          f'Cumulative share of unplanned tickets across devices, {htm.period_text(S)}', talk)]


if __name__ == '__main__':
    plot()
