#!/usr/bin/env python3
"""Chart 4: model mix of workload-outsized machines vs the other ticketed machines.

A dumbbell per model: share of the workload-outsized machines (blue) and of the other ticketed machines (gray)
that are that model, for the models with the largest gap, sorted by gap. The title states the largest gap over all
models (labelled on its row); the footer bounds the gap of the models not shown. Shares and gaps are recomputed
from the machine counts, since the CSV's shares are rounded to 4 decimals.

Inputs:
  verification/outputs/htm_type_mix.csv   rows with field = model: value, outsized_machines, outsized_share,
                                          other_machines, other_share
  verification/outputs/htm_summary.json   D1_workload (threshold, rank_k, machines, outsized_machines) for the
                                          workload-outsized definition and the consistency checks
Output:
  viz/figures/htm_04_model_mix.png

Run:  cd /home/user/analytics-lab && python3 -I viz/high_ticket/htm_04_model_mix.py
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402

import htm  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'htm_04_model_mix.png'
N_SHOWN = 10  # models with the largest gap


def plot(out_dir=htm.FIG_DIR):
    out_dir = Path(out_dir)
    S = htm.summary()
    tm = htm.load('type_mix')
    m = tm[tm.field == 'model'].copy()
    n_out, n_oth = int(m.outsized_machines.sum()), int(m.other_machines.sum())
    W = S['D1_workload']
    style.check('D1 outsized machines (model mix)', W['outsized_machines'], n_out)
    style.check('D1 ticketed machines (model mix)', W['machines'], n_out + n_oth)
    m['out_sh'], m['oth_sh'] = m.outsized_machines / n_out, m.other_machines / n_oth
    # Shares are rounded to 4 decimals in the CSV.
    style.check('model mix: outsized shares = counts / total', 0, (m.outsized_share - m.out_sh).abs().max(), 1e-4)
    style.check('model mix: other shares = counts / total', 0, (m.other_share - m.oth_sh).abs().max(), 1e-4)

    m['gap'] = m.out_sh - m.oth_sh
    m = m.reindex(m.gap.abs().sort_values(ascending=False, kind='mergesort').index)
    max_gap = 100 * m.gap.abs().max()
    top = m.head(N_SHOWN).sort_values('gap', kind='mergesort')  # largest positive gap at the top of the chart
    y = np.arange(len(top))

    fig, ax = style.figure(10, 6.9)
    for yi, (a, b) in zip(y, zip(top.oth_sh, top.out_sh)):
        ax.plot([100 * a, 100 * b], [yi, yi], color=style.GRAY_LIGHT, lw=2, zorder=2)
    ax.scatter(100 * top.oth_sh, y, s=70, color=style.GRAY, edgecolors=style.SURFACE, linewidths=1.6, zorder=3,
               label=f'Other ticketed machines ({n_oth:,})')
    ax.scatter(100 * top.out_sh, y, s=70, color=style.BLUE, edgecolors=style.SURFACE, linewidths=1.6, zorder=4,
               label=f'Workload-outsized machines ({n_out:,})')
    # Label the row with the largest gap, the one the title quotes.
    i = int(np.argmax(top.gap.abs().to_numpy()))
    lead = top.iloc[i]
    ax.annotate(f'{style.pct(lead.out_sh)} vs {style.pct(lead.oth_sh)}', xy=(100 * max(lead.out_sh, lead.oth_sh), y[i]),
                xytext=(10, 0), textcoords='offset points', va='center', fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(top.value, color=style.INK2)
    ax.set_ylim(-0.7, len(top) - 0.3)
    ax.set_xlim(0, 100 * max(top.out_sh.max(), top.oth_sh.max()) + 4)
    style.style_axes(ax, grid='x', baseline=None)
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of machines in the group')
    # Data-dependent: with these data the two middle rows (SD-64, MV) end below 7%, so a legend at the right of the
    # middle of the plot covers no dots. Check the PNG if the data change.
    ax.legend(loc='center right', handletextpad=0.4)

    notes = ['Model as recorded in the case export.',
             'Source: htm_type_mix.csv (field = model); threshold from htm_summary.json (D1).']
    if len(m) > N_SHOWN:
        # Smallest 0.1-point step strictly above every gap not shown. 1000 * gap = tenths of a point, rounded first
        # so float noise cannot drop the floor by a step.
        rest_bound = (math.floor(round(1000 * m.gap.abs().iloc[N_SHOWN:].max(), 6)) + 1) / 10
        notes[0] = f'The other {len(m) - N_SHOWN} models differ by less than {rest_bound:.1f} points. ' + notes[0]
    style.frame(
        fig,
        f'Outsized machines\' model mix differs from the rest by about {max_gap:.0f} points at most',
        f'Share of machines by model: {n_out:,} workload-outsized vs {n_oth:,} other ticketed machines (case-export '
        f'serials), unplanned tickets {htm.period_text(S, "case_export_period")}. '
        f'The {min(N_SHOWN, len(m))} models with the largest gap, '
        f'sorted by gap.',
        definitions=[htm.outsized_definition(S)],
        notes=notes)
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
