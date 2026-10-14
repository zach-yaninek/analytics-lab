#!/usr/bin/env python3
"""Slide version of Zac's figure 8 (viz/zac_notebook/zac_08_customer_concentration.py): how concentrated the ticket
workload is across customers.

Same curve, shading, 50% hairline, marked points and labels as the full chart. The customer definition, the workload
note and the population go to the speaker notes.

Output:  viz/figures/slides/zac_08_customer_concentration.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_08_customer_concentration_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_08_customer_concentration as full  # noqa: E402
import zac_data  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    cw, rq = zac_data.load('customer_workload'), zac_data.load('record_quality')
    v = cw.sort_values(['cases', 'customer'], ascending=[False, True], kind='mergesort').reset_index(drop=True)
    total, n = int(v.cases.sum()), len(v)
    x = np.arange(1, n + 1)
    y = 100 * v.cases.cumsum().to_numpy() / total
    k = int(np.searchsorted(y, full.HALF) + 1)
    top_share, k_share = y[full.TOP_N - 1], y[k - 1]
    style.check('slide zac_08 k = Zac\'s annotation', int(full.zac_printed('C18_concentration_k')), k)
    n_low = n // 2
    low_share = 100 * v.cases.tail(n_low).sum() / total

    fig, ax = slides.figure()
    xs, ys = np.r_[0, x], np.r_[0, y]
    ax.fill_between(xs, ys, color=style.BLUE, alpha=0.08, linewidth=0)
    ax.plot(xs, ys, color=style.BLUE, lw=2.2, zorder=3)
    ax.axhline(full.HALF, color=style.MUTED, lw=0.8, zorder=2)
    ax.text(n, full.HALF + 1.2, f'{full.HALF}% of tickets', ha='right', va='bottom', fontsize=9, color=style.MUTED)
    marker = dict(s=60, edgecolors=style.SURFACE, linewidths=1.6, zorder=5)
    ax.scatter([full.TOP_N], [top_share], c=style.GRAY, **marker)
    ax.scatter([k], [k_share], c=style.BLUE, **marker)
    line = dict(arrowstyle='-', color=style.MUTED, lw=0.8, shrinkA=2, shrinkB=4, relpos=(0, 0.5))
    ax.annotate(f'{k} customers: {full.HALF}% of tickets', xy=(k, k_share), xytext=(k + 15, full.HALF - 6),
                fontsize=10, color=style.INK, va='center', arrowprops=line)
    ax.annotate(f'Top {full.TOP_N} customers: {style.pct(top_share / 100)} of tickets', xy=(full.TOP_N, top_share),
                xytext=(full.TOP_N + 35, 7), fontsize=10, color=style.INK2, va='center', arrowprops=line)
    ax.set_xlim(0, n)
    ax.set_ylim(0, 102)
    ax.set_yticks(np.arange(0, 101, 20))
    style.style_axes(ax, grid='y')
    style.pct_axis(ax.yaxis)
    ax.set_xlabel('Customers, ranked by ticket count (most first)')
    ax.set_ylabel('Cumulative share of tickets')

    period = zac_data.period_text(rq)
    talk = [zac_data.CUSTOMER_DEFINITION, zac_data.WORKLOAD_NOTE,
            f'Population: all {total:,} tickets in the case export ({period}), including planned work, cancelled '
            f'requests and duplicate cases, from {n} customers with tickets.',
            f'The bottom half (the {n_low} customers with the fewest tickets) accounts for '
            f'{style.pct(low_share / 100)} of tickets.']
    return [slides.finish(fig, Path(out_dir) / 'zac_08_customer_concentration.png',
                          f'Half of all tickets come from {k} customers, {style.pct(k / n, 0)} of the {n} with '
                          f'tickets',
                          f'Cumulative share of tickets across customers, {period}', talk)]


if __name__ == '__main__':
    plot()
