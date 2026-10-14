#!/usr/bin/env python3
"""Chart 5: share of unplanned tickets that are follow-ups, workload-outsized machines vs the rest.

A ticket is a follow-up if it opens within the gap (7 days; sensitivity 3 and 14 days) after the same machine's
previous ticket. For each group one row shows the 7-day share (dot) on the 3- to 14-day range, and a second row
just below it the share expected if each machine's tickets fell at random times over the period (median and 95%
interval, from the analysis run). The title states the 7-day ratio between the groups.

Inputs:
  verification/outputs/htm_episodes.csv   one row per ticketed machine: tickets, episodes_<gap>d,
                                          workload_outsized
  verification/outputs/htm_summary.json   definitions.episode_gaps_days; D5_episodes (outsized / other: machines,
                                          tickets, followup_share_<gap>d, followup_share_7d_random_timing);
                                          D1_workload (threshold, rank_k, machines, tickets, outsized_machines)
Output:
  verification/outputs/figures/htm_05_episode_followups.png

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_05_episode_followups.py
"""
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matplotlib.lines import Line2D  # noqa: E402

import style  # noqa: E402

PNG = 'htm_05_episode_followups.png'
RT_OFFSET = 0.68  # the random-timing row sits this far (y units) below its group's observed row


class Group(NamedTuple):
    key: str    # D5_episodes key
    label: str  # y tick label
    color: str  # dot
    y: float    # observed row


GROUPS = [Group('outsized', 'Workload-outsized machines', style.BLUE, 3.0),  # top to bottom
          Group('other', 'Other ticketed machines', style.GRAY, 1.0)]


def plot(out_dir=style.FIG_DIR):
    out_dir = Path(out_dir)
    S = style.summary()
    W, D5 = S['D1_workload'], S['D5_episodes']
    lo_gap, gap, hi_gap = S['definitions']['episode_gaps_days']
    ep = style.load('episodes')

    style.check('D1 machines (episodes)', W['machines'], len(ep))
    style.check('D1 tickets (episodes)', W['tickets'], int(ep.tickets.sum()))
    style.check('D1 outsized machines (episodes)', W['outsized_machines'], int(ep.workload_outsized.sum()))
    style.check('D1 outsized flag = tickets >= threshold (episodes)', 0,
                int((ep.workload_outsized != (ep.tickets >= W['threshold'])).sum()))
    # Per group: machines, tickets, and share[group][gap days] = follow-up share = 1 - episodes / tickets.
    machines, tickets, share = {}, {}, {}
    for grp in GROUPS:
        k = grp.key
        g = ep[ep.workload_outsized] if k == 'outsized' else ep[~ep.workload_outsized]
        machines[k], tickets[k] = len(g), int(g.tickets.sum())
        share[k] = {d: 1 - g[f'episodes_{d}d'].sum() / tickets[k] for d in (lo_gap, gap, hi_gap)}
        style.check(f'D5 {k} machines', D5[k]['machines'], machines[k])
        style.check(f'D5 {k} tickets', D5[k]['tickets'], tickets[k])
        for d in (lo_gap, gap, hi_gap):
            style.check(f'D5 {k} {d}d follow-up share', D5[k][f'followup_share_{d}d'], round(share[k][d], 4), 1e-4)

    fig, ax = style.figure(10, 6.5)
    rts = {}
    for grp in GROUPS:
        key, yv = grp.key, grp.y
        lo, mid, hi = (100 * share[key][d] for d in (lo_gap, gap, hi_gap))
        ax.plot([lo, hi], [yv, yv], color=style.GRAY_LIGHT, lw=2, zorder=2)
        ax.plot([lo, hi], [yv, yv], ls='', marker='|', ms=13, mew=1.2, color=style.MUTED, zorder=2)
        # Main-rule value above the dot; the range-end values below the ends (never on the same line).
        for x, txt in ((lo, f'{lo_gap}-day {lo:.1f}%'), (hi, f'{hi_gap}-day {hi:.1f}%')):
            ax.annotate(txt, xy=(x, yv), xytext=(0, -10), textcoords='offset points', ha='center', va='top',
                        fontsize=9, color=style.MUTED)
        ax.scatter([mid], [yv], s=120, color=grp.color, edgecolors=style.SURFACE, linewidths=1.8, zorder=4)
        ax.annotate(f'{mid:.1f}%', xy=(mid, yv), xytext=(0, 9), textcoords='offset points', ha='center',
                    va='bottom', fontsize=10.5, color=style.INK, weight='bold')

        rt = D5[key][f'followup_share_{gap}d_random_timing']  # median, 2.5th and 97.5th percentile
        rts[key] = rt[0]
        rt_med, rt_lo, rt_hi = (100 * x for x in rt)
        yr = yv - RT_OFFSET
        ax.plot([rt_lo, rt_hi], [yr, yr], color=style.MUTED, lw=1, zorder=2)
        ax.scatter([rt_med], [yr], s=55, marker='D', facecolors=style.SURFACE, edgecolors=style.INK2,
                   linewidths=1.3, zorder=3)
        ax.annotate(f'random timing {rt_med:.1f}%', xy=(rt_hi, yr), xytext=(8, 0), textcoords='offset points',
                    ha='left', va='center', fontsize=9, color=style.INK2)

    ys = [grp.y for grp in GROUPS]
    ax.set_yticks(ys)
    ax.set_yticklabels([f'{grp.label}\n{machines[grp.key]:,} machines · {tickets[grp.key]:,} tickets'
                        for grp in GROUPS], color=style.INK2, linespacing=1.35)
    ax.set_ylim(min(ys) - RT_OFFSET - 0.45, max(ys) + 0.75)
    ax.set_xlim(0, 100 * max(s[hi_gap] for s in share.values()) + 4)
    style.style_axes(ax, grid='x', baseline=None)
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Follow-up share: tickets opened within the window after the machine\'s previous ticket')
    handles = [Line2D([], [], marker='o', ls='', ms=9.5, mfc=style.INK2, mec=style.SURFACE, label=f'{gap}-day rule'),
               Line2D([], [], color=style.GRAY_LIGHT, lw=2, label=f'{lo_gap}- to {hi_gap}-day rule (range)'),
               Line2D([], [], marker='D', ls='-', lw=1, color=style.MUTED, ms=7, mfc=style.SURFACE,
                      mec=style.INK2, mew=1.3, label='Random timing, same counts (median, 95%)')]
    ax.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=3, handletextpad=0.5,
              columnspacing=1.6)

    ratio = share['outsized'][gap] / share['other'][gap]
    style.frame(
        fig,
        f'Outsized machines\' tickets are {gap}-day follow-ups {ratio:.1f}× as often '
        f'({style.pct(share["outsized"][gap])} vs {style.pct(share["other"][gap])})',
        f'All {sum(tickets.values()):,} unplanned tickets on {len(ep):,} machines (case-export serials), '
        f'{style.period_text(S, "case_export_period")}. A ticket is a follow-up if it opens within {gap} days of the machine\'s previous '
        f'ticket (sensitivity: {lo_gap} and {hi_gap} days).',
        definitions=[style.outsized_definition(S)],
        notes=[f'Random timing: each machine\'s tickets placed uniformly at random over the period '
               f'({S["definitions"]["n_sim_episodes"]} draws, a rough null). More tickets alone produce more follow-ups: '
               f'{style.pct(rts["outsized"])} for outsized machines and {style.pct(rts["other"])} for the rest.',
               'Source: htm_episodes.csv; random timing and threshold from htm_summary.json (D5, D1).'])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
