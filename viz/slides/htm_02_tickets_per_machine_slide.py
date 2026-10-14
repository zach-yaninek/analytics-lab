#!/usr/bin/env python3
"""Slide version of chart 2 (viz/high_ticket/htm_02_tickets_per_machine.py): unplanned tickets per ticketed machine,
with the workload-outsized threshold.

Same bars, colours, threshold rule and machine counts on the blue bars as the full chart. The threshold label is
shortened to the term; its definition, the population and the fixed-threshold note go to the speaker notes.

Output:  viz/figures/slides/htm_02_tickets_per_machine.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_02_tickets_per_machine_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import htm  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    S = htm.summary()
    W, fixed_thr = S['D1_workload'], S['definitions']['fixed_threshold']
    m = htm.load('machine_counts')
    t = m.unplanned_tickets
    vc = t.value_counts().sort_index()
    n_tix = int(t.sum())
    outs = m[m.workload_outsized]
    thr = W['threshold']
    share_out = outs.unplanned_tickets.sum() / n_tix
    fixed = t[t >= fixed_thr]
    style.check('slide D1 threshold', thr, outs.unplanned_tickets.min())
    style.check('slide D1 outsized ticket share', W['outsized_ticket_share'], round(share_out, 4), 1e-4)

    fig, ax = slides.figure()
    top = vc.max()
    ax.bar(vc.index, vc.values, width=0.4, linewidth=0,
           color=[style.BLUE if xv >= thr else style.GRAY_LIGHT for xv in vc.index])
    for xv, yv in vc.items():
        if xv >= thr:
            ax.text(xv, yv + top * 0.012, f'{yv:,}', ha='center', va='bottom', fontsize=9, color=style.INK2)
    ax.axvline(thr - 0.5, color=style.INK2, lw=1)
    ax.text(thr - 0.5 + 0.3, top * 0.98, f'Workload-outsized: {thr} or more tickets', ha='left', va='top',
            fontsize=10, color=style.INK)
    ax.set_xlim(0.3, vc.index.max() + 0.7)
    ax.set_ylim(0, top * 1.08)
    style.style_axes(ax, grid='y')
    ax.set_xticks(range(1, int(vc.index.max()) + 1))
    style.thousands_axis(ax.yaxis)
    ax.set_xlabel('Unplanned tickets per machine')
    ax.set_ylabel('Machines')

    title = f'The {len(outs)} machines with {thr} or more tickets carry {style.pct(share_out)} of the unplanned load'
    talk = [htm.outsized_definition(S),
            f'Population: {len(m):,} ticketed machines (case-export serials) and {n_tix:,} unplanned tickets '
            f'(planned work, cancelled and duplicate cases excluded), {htm.period_text(S, "case_export_period")}.',
            f'With a fixed threshold of {fixed_thr} or more: {len(fixed)} machines with '
            f'{style.pct(fixed.sum() / n_tix)} of tickets. The busiest machine has {int(vc.index.max())} tickets.']
    return [slides.finish(fig, Path(out_dir) / 'htm_02_tickets_per_machine.png', title,
                          f'Ticketed machines by number of unplanned tickets, '
                          f'{htm.period_text(S, "case_export_period")}', talk)]


if __name__ == '__main__':
    plot()
