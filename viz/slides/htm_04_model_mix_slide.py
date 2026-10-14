#!/usr/bin/env python3
"""Slide version of chart 4 (viz/high_ticket/htm_04_model_mix.py): model mix of workload-outsized machines vs the
other ticketed machines.

Same dumbbells, models, order, colours and label on the largest gap as the full chart. Dropped for the slide: the
machine counts in the legend and the footer (definition, models not shown, source), which go to the speaker notes.

Output:  viz/figures/slides/htm_04_model_mix.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_04_model_mix_slide.py
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import numpy as np  # noqa: E402

import htm  # noqa: E402
import htm_04_model_mix as full  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    S = htm.summary()
    tm = htm.load('type_mix')
    m = tm[tm.field == 'model'].copy()
    n_out, n_oth = int(m.outsized_machines.sum()), int(m.other_machines.sum())
    style.check('slide D1 outsized machines (model mix)', S['D1_workload']['outsized_machines'], n_out)
    m['out_sh'], m['oth_sh'] = m.outsized_machines / n_out, m.other_machines / n_oth
    m['gap'] = m.out_sh - m.oth_sh
    m = m.reindex(m.gap.abs().sort_values(ascending=False, kind='mergesort').index)
    max_gap = 100 * m.gap.abs().max()
    top = m.head(full.N_SHOWN).sort_values('gap', kind='mergesort')  # largest positive gap at the top
    y = np.arange(len(top))

    fig, ax = slides.figure()
    for yi, (a, b) in zip(y, zip(top.oth_sh, top.out_sh)):
        ax.plot([100 * a, 100 * b], [yi, yi], color=style.GRAY_LIGHT, lw=2, zorder=2)
    ax.scatter(100 * top.oth_sh, y, s=70, color=style.GRAY, edgecolors=style.SURFACE, linewidths=1.6, zorder=3,
               label='Other ticketed machines')
    ax.scatter(100 * top.out_sh, y, s=70, color=style.BLUE, edgecolors=style.SURFACE, linewidths=1.6, zorder=4,
               label='Workload-outsized machines')
    i = int(np.argmax(top.gap.abs().to_numpy()))
    lead = top.iloc[i]
    ax.annotate(f'{style.pct(lead.out_sh)} vs {style.pct(lead.oth_sh)}',
                xy=(100 * max(lead.out_sh, lead.oth_sh), y[i]), xytext=(10, 0), textcoords='offset points',
                va='center', fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(top.value, color=style.INK2)
    ax.set_ylim(-0.7, len(top) - 0.3)
    ax.set_xlim(0, 100 * max(top.out_sh.max(), top.oth_sh.max()) + 4)
    style.style_axes(ax, grid='x', baseline=None)
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of machines in the group')
    # Data-dependent, as in the full chart: the middle rows end below 7%, so the legend covers no dots there.
    ax.legend(loc='center right', handletextpad=0.4)

    rest_bound = (math.floor(round(1000 * m.gap.abs().iloc[full.N_SHOWN:].max(), 6)) + 1) / 10
    title = f'Outsized machines\' model mix differs from the rest by about {max_gap:.0f} points at most'
    talk = [htm.outsized_definition(S),
            f'Groups: {n_out:,} workload-outsized vs {n_oth:,} other ticketed machines (case-export serials), '
            f'{htm.period_text(S, "case_export_period")}. Model as recorded in the case export.',
            f'Shown: the {len(top)} models with the largest gap; the other {len(m) - len(top)} differ by less than '
            f'{rest_bound:.1f} points.']
    return [slides.finish(fig, Path(out_dir) / full.PNG, title,
                          f'Share of machines by model, the {len(top)} models with the largest gap', talk)]


if __name__ == '__main__':
    plot()
