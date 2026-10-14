#!/usr/bin/env python3
"""Chart 1: concentration curve of unplanned tickets over devices, observed vs chance.

Devices in the exposure population are ranked by ticket count (most first); the curve shows the cumulative share of
tickets they hold. The observed curve is drawn against the median and middle 95% of Poisson draws at each device's
expected count (type rate x months active). Markers show the share held by the top-share devices.

Inputs:
  verification/outputs/htm_lorenz.csv            device_share, ticket_share_obs, ticket_share_null_median,
                                                 ticket_share_null_p2_5, ticket_share_null_p97_5
  verification/outputs/htm_device_exposure.csv   tickets_obs (one row per exposure-population device)
  verification/outputs/htm_summary.json          D4_concentration (top5_share_*, gini_*, ge6_*, devices),
                                                 D1_workload (rank_k, machines), definitions (period,
                                                 fixed_threshold), n_sim, seed
Output:
  verification/outputs/figures/htm_01_concentration_curve.png

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_01_concentration_curve.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import style  # noqa: E402


def top_share(S):
    """The 'top 5%' cut of the analysis. htm_summary.json stores the workload rank, ceil(share x ticketed machines),
    with share a whole percent, so rank / machines rounded to a whole percent recovers it."""
    w = S['D1_workload']
    share = round(100 * w['rank_k'] / w['machines']) / 100
    style.check('D1 rank = ceil(top share x machines)', w['rank_k'], math.ceil(share * w['machines']))
    return share


def month(day):
    return pd.Timestamp(day).strftime('%b %Y')


def plot(out_dir=style.FIG_DIR):
    S = style.summary()
    L, dev, C = style.load('lorenz'), style.load('device_exposure'), S['D4_concentration']
    share, fixed = top_share(S), S['definitions']['fixed_threshold']
    obs = np.sort(dev.tickets_obs.to_numpy())[::-1]
    k = math.ceil(share * len(obs))
    top_obs = obs[:k].sum() / obs.sum()
    ge_fixed = int((obs >= fixed).sum())
    style.check('D4 top-5% share', C['top5_share_obs'], round(top_obs, 4), 1e-4)
    style.check('D4 devices', C['devices'], len(obs))
    style.check('D4 tickets', C['tickets_obs'], int(obs.sum()))
    style.check(f'D4 devices >= {fixed}', C['ge6_obs'], ge_fixed)

    fig, ax = style.figure(10, 6.4)
    x = 100 * L.device_share
    ax.fill_between(x, 100 * L.ticket_share_null_p2_5, 100 * L.ticket_share_null_p97_5, color=style.GRAY_LIGHT,
                    alpha=0.45, linewidth=0, label=f'Chance: middle 95% of {S["n_sim"]:,} draws')
    ax.plot(x, 100 * L.ticket_share_null_median, color=style.GRAY, lw=2, label='Chance: median draw')
    ax.plot(x, 100 * L.ticket_share_obs, color=style.BLUE, lw=2, label='Observed')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    x_top = 100 * share
    ax.axvline(x_top, color=style.MUTED, lw=0.8)
    y_obs, y_null = 100 * top_obs, 100 * C['top5_share_null_median']
    ax.scatter([x_top, x_top], [y_obs, y_null], s=60, c=[style.BLUE, style.GRAY], edgecolors=style.SURFACE,
               linewidths=1.6, zorder=5)
    # Labels sit right of and below their points, under both curves (empty area right of x = 10%).
    line = dict(arrowstyle='-', color=style.MUTED, lw=0.8, shrinkA=2, shrinkB=5)
    ax.annotate(f'Top {x_top:g}% of devices ({k:,})\nObserved: {style.pct(top_obs)} of tickets',
                xy=(x_top, y_obs), xytext=(x_top + 8, y_obs - 6), fontsize=10, color=style.INK, va='center',
                linespacing=1.35, arrowprops=line)
    ax.annotate(f'Chance median: {style.pct(C["top5_share_null_median"])} '
                f'(95th percentile {style.pct(C["top5_share_null_p95"])})',
                xy=(x_top, y_null), xytext=(x_top + 8, y_null - 7), fontsize=10, color=style.INK2, va='center',
                arrowprops=line)
    style.style_axes(ax, grid='both')
    ax.set_yticks(np.arange(0, 101, 20))
    style.pct_axis(ax.xaxis)
    style.pct_axis(ax.yaxis)
    ax.set_xlabel('Share of devices, ranked by tickets (most first)')
    ax.set_ylabel('Cumulative share of tickets')
    ax.legend(loc='lower right', handlelength=2.2)

    start, end = S['definitions']['period']
    style.frame(
        fig,
        f'The top {x_top:g}% of devices hold {style.pct(top_obs, 0)} of tickets; chance alone gives '
        f'{style.pct(C["top5_share_null_median"], 0)}',
        f'{len(obs):,} devices in the exposure population (non-shared hosts), {int(obs.sum()):,} unplanned tickets '
        f'{month(start)} to {month(end)}. Chance = Poisson draws at each device\'s expected count (type rate × '
        f'months active), seed {S["seed"]}.',
        notes=[f'Gini over devices: {C["gini_obs"]:.3f} observed vs {C["gini_null_median"]:.3f} chance median. '
               f'Devices with {fixed} or more tickets: {ge_fixed} observed vs {C["ge6_null_median"]:.0f} chance '
               f'median (95th percentile {C["ge6_null_p95"]:.0f}).',
               'Source: htm_lorenz.csv, htm_device_exposure.csv, htm_summary.json (D4).'])
    return [style.save(fig, Path(out_dir) / 'htm_01_concentration_curve.png')]


if __name__ == '__main__':
    plot()
