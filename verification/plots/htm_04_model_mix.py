#!/usr/bin/env python3
"""Chart 4: model mix of workload-outsized machines vs the other ticketed machines.

A dumbbell per model: share of the workload-outsized machines (blue) and of the other ticketed machines (gray)
that are that model, for the models with the largest gap, sorted by gap. The title states the largest gap over all
models; the footer bounds the gap of the models not shown.

Inputs:
  verification/outputs/htm_type_mix.csv   rows with field = model: value, outsized_machines, outsized_share,
                                          other_machines, other_share
  verification/outputs/htm_summary.json   D1_workload (threshold, rank_k, machines, outsized_machines) for the
                                          workload-outsized definition and the consistency checks
Output:
  verification/outputs/figures/htm_04_model_mix.png

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_04_model_mix.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

import style  # noqa: E402

PNG = 'htm_04_model_mix.png'
N_SHOWN = 10  # models with the largest gap


def plot(out_dir=style.FIG_DIR, n=N_SHOWN):
    out_dir = Path(out_dir)
    S = style.summary()
    tm = style.load('type_mix')
    m = tm[tm.field == 'model'].copy()
    n_out, n_oth = int(m.outsized_machines.sum()), int(m.other_machines.sum())
    W = S['D1_workload']
    style.check('D1 outsized machines (model mix)', W['outsized_machines'], n_out)
    style.check('D1 ticketed machines (model mix)', W['machines'], n_out + n_oth)
    # Shares are rounded to 4 decimals in the CSV.
    style.check('model mix: outsized shares = counts / total', 0,
                (m.outsized_share - m.outsized_machines / n_out).abs().max(), 1e-4)
    style.check('model mix: other shares = counts / total', 0,
                (m.other_share - m.other_machines / n_oth).abs().max(), 1e-4)

    m['gap'] = m.outsized_share - m.other_share
    m = m.reindex(m.gap.abs().sort_values(ascending=False, kind='mergesort').index)
    max_gap = 100 * m.gap.abs().max()
    rest_max = 100 * m.gap.abs().iloc[n:].max()
    rest_bound = math.floor(10 * rest_max) / 10 + 0.1  # smallest 0.1 step strictly above every gap not shown
    top = m.head(n).sort_values('gap', kind='mergesort')  # largest positive gap at the top of the chart
    y = np.arange(len(top))

    fig, ax = style.figure(10, 6.9)
    for yi, (a, b) in zip(y, zip(top.other_share, top.outsized_share)):
        ax.plot([100 * a, 100 * b], [yi, yi], color=style.GRAY_LIGHT, lw=2, zorder=2)
    ax.scatter(100 * top.other_share, y, s=70, color=style.GRAY, edgecolors=style.SURFACE, linewidths=1.6,
               zorder=3, label=f'Other ticketed machines ({n_oth:,})')
    ax.scatter(100 * top.outsized_share, y, s=70, color=style.BLUE, edgecolors=style.SURFACE, linewidths=1.6,
               zorder=4, label=f'Workload-outsized machines ({n_out:,})')
    lead = top.iloc[-1]
    ax.annotate(f'{style.pct(lead.outsized_share)} vs {style.pct(lead.other_share)}',
                xy=(100 * max(lead.outsized_share, lead.other_share), y[-1]), xytext=(10, 0),
                textcoords='offset points', va='center', fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(top.value, color=style.INK2)
    ax.set_ylim(-0.7, len(top) - 0.3)
    ax.set_xlim(0, 100 * max(top.outsized_share.max(), top.other_share.max()) + 4)
    style.style_axes(ax, grid='x', baseline=None)
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of machines in the group')
    # Rows below the top one end well left of the lead row's dots, so the right-hand middle of the plot is empty.
    ax.legend(loc='center right', handletextpad=0.4)

    style.frame(
        fig,
        f'Outsized machines\' model mix differs from the rest by {max_gap:.1f} points at most',
        f'Share of machines by model: {n_out} workload-outsized vs {n_oth:,} other ticketed machines (case-export '
        f'serials), unplanned tickets Aug 2025 to Aug 2026. The {n} models with the largest gap, sorted by gap.',
        definitions=[style.outsized_definition(S)],
        notes=[f'The other {len(m) - n} models differ by less than {rest_bound:.1f} points. Model as recorded in the '
               f'case export.',
               'Source: htm_type_mix.csv (field = model); threshold from htm_summary.json (D1).'])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
