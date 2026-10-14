#!/usr/bin/env python3
"""Slide version of Zac's figure 3 (viz/zac_notebook/zac_03_model_workload.py): the 10 machine models with the most
tickets in the full case export (raw counts).

Same models, bars and colours as the full chart. The value labels keep the ticket counts and drop the shares; the
fleet-size caveat, the population and the notes go to the speaker notes.

Output:  viz/figures/slides/zac_03_model_workload.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/zac_03_model_workload_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'zac_notebook')]
import numpy as np  # noqa: E402

import ipa_style as style  # noqa: E402
import slides  # noqa: E402
import zac_03_model_workload as full  # noqa: E402
import zac_data  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    mw, rq = zac_data.load('model_workload'), zac_data.load('record_quality')
    d = mw.sort_values(['cases', 'model'], ascending=[False, True], kind='mergesort').reset_index(drop=True)
    total = int(d.cases.sum())
    style.check('slide zac_03 tickets = record_quality cases', int(rq.cases.iloc[0]), total)
    top, rest = d.head(full.TOP_N), d.iloc[full.TOP_N:]
    lead = top.head(full.N_HIGHLIGHT)

    p = top.iloc[::-1]  # most tickets on top
    fig, ax = slides.figure()
    y = np.arange(len(p))
    ax.barh(y, p.cases, height=full.BAR_H,
            color=np.where(p.model.isin(lead.model).to_numpy(), style.BLUE, style.GRAY_LIGHT), linewidth=0)
    for yi, n in zip(y, p.cases):
        ax.text(n + p.cases.max() * 0.01, yi, f'{n:,}', va='center', ha='left', fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(p.model, color=style.INK2)
    ax.set_ylim(-0.6, len(p) - 0.4)
    ax.set_xlim(0, p.cases.max() * 1.1)
    style.style_axes(ax, grid='x', baseline='left')
    style.thousands_axis(ax.xaxis)
    ax.set_xlabel('Tickets')

    period = zac_data.period_text(rq)
    talk = [full.NOT_ADJUSTED,
            f'Population: all {total:,} tickets in the case export ({period}), planned work, cancelled and duplicate '
            f'cases included. Model = the model recorded on the ticket. The {full.TOP_N} models shown hold '
            f'{style.pct(top.cases.sum() / total)}; blue = the top {full.N_HIGHLIGHT}.',
            f'Not shown: the other {len(rest)} models, {int(rest.cases.sum()):,} tickets in all; the largest is '
            f'{rest.model.iloc[0]} ({int(rest.cases.iloc[0]):,} tickets).']
    return [slides.finish(fig, Path(out_dir) / full.PNG,
                          f'Top {full.N_HIGHLIGHT} of {len(d)} models hold {style.pct(lead.cases.sum() / total)} of '
                          f'all tickets; {lead.model.iloc[0]} alone has {style.pct(lead.cases.iloc[0] / total)}',
                          f'Raw ticket counts by model, the {full.TOP_N} models with the most, {period}', talk)]


if __name__ == '__main__':
    plot()
