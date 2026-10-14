#!/usr/bin/env python3
"""Chart 2: distribution of unplanned tickets per ticketed machine, with the workload-outsized threshold.

Bars count machines by their number of unplanned tickets in the case export; a vertical rule marks the
workload-outsized threshold (ticket count of the rank_k-th busiest machine, ties included). Bars at or above it are
blue and carry their machine counts; bars below it are gray context.

Inputs:
  verification/outputs/htm_machine_counts.csv   unplanned_tickets, workload_outsized (one row per ticketed machine)
  verification/outputs/htm_summary.json         D1_workload (threshold, rank_k, machines, tickets,
                                                outsized_machines, outsized_ticket_share, fixed_machines,
                                                fixed_ticket_share, max), definitions (fixed_threshold)
Output:
  verification/outputs/figures/htm_02_tickets_per_machine.png

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_02_tickets_per_machine.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402


def plot(out_dir=style.FIG_DIR):
    S = style.summary()
    W, fixed_thr = S['D1_workload'], S['definitions']['fixed_threshold']
    m = style.load('machine_counts')
    t = m.unplanned_tickets
    vc = t.value_counts().sort_index()
    n_mach, n_tix = len(m), int(t.sum())
    outs = m[m.workload_outsized]
    thr = W['threshold']
    share_out = outs.unplanned_tickets.sum() / n_tix
    fixed = t[t >= fixed_thr]
    style.check('D1 machines', W['machines'], n_mach)
    style.check('D1 tickets', W['tickets'], n_tix)
    style.check('D1 threshold', thr, outs.unplanned_tickets.min())
    style.check('D1 threshold = count of the rank_k-th machine', thr,
                t.sort_values(ascending=False).iloc[W['rank_k'] - 1])
    style.check('D1 outsized machines', W['outsized_machines'], len(outs))
    style.check('D1 outsized ticket share', W['outsized_ticket_share'], round(share_out, 4), 1e-4)
    style.check('D1 fixed-threshold machines', W['fixed_machines'], len(fixed))
    style.check('D1 fixed-threshold ticket share', W['fixed_ticket_share'], round(fixed.sum() / n_tix, 4), 1e-4)
    style.check('D1 max', W['max'], int(vc.index.max()))

    fig, ax = style.figure(10, 6.6)
    top = vc.max()
    ax.bar(vc.index, vc.values, width=0.4, linewidth=0,
           color=[style.BLUE if xv >= thr else style.GRAY_LIGHT for xv in vc.index])
    for xv, yv in vc.items():
        if xv >= thr:
            ax.text(xv, yv + top * 0.012, f'{yv:,}', ha='center', va='bottom', fontsize=9, color=style.INK2)
    ax.axvline(thr - 0.5, color=style.INK2, lw=1)
    ax.text(thr - 0.5 + 0.3, top * 0.98,
            f'Workload-outsized: {thr} or more tickets\n{len(outs):,} machines ({style.pct(len(outs) / n_mach)}) '
            f'hold {style.pct(share_out)} of tickets', ha='left', va='top', fontsize=10, color=style.INK,
            linespacing=1.4)
    ax.set_xlim(0.3, vc.index.max() + 0.7)
    ax.set_ylim(0, top * 1.08)
    style.style_axes(ax, grid='y')
    ax.set_xticks(range(1, int(vc.index.max()) + 1))
    style.thousands_axis(ax.yaxis)
    ax.set_xlabel('Unplanned tickets per machine')
    ax.set_ylabel('Machines')

    style.frame(
        fig,
        f'The {len(outs)} machines with {thr} or more tickets carry {style.pct(share_out)} of the unplanned load',
        f'{n_mach:,} ticketed machines (case-export serials) and {n_tix:,} unplanned tickets (excludes planned work, '
        f'cancelled and duplicate cases), case export {style.period_text(S, "case_export_period")}.',
        definitions=[style.outsized_definition(S)],
        notes=[f'Fixed threshold of {fixed_thr} or more: {len(fixed)} machines with {style.pct(fixed.sum() / n_tix)} '
               f'of tickets. Maximum {int(vc.index.max())} tickets.',
               'Source: htm_machine_counts.csv, htm_summary.json (D1).'])
    return [style.save(fig, Path(out_dir) / 'htm_02_tickets_per_machine.png')]


if __name__ == '__main__':
    plot()
