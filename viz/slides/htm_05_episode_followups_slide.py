#!/usr/bin/env python3
"""Slide version of chart 5 (viz/high_ticket/htm_05_episode_followups.py): share of unplanned tickets that are
follow-ups, workload-outsized machines vs the rest.

Same rows, dots, sensitivity ranges and random-timing markers as the full chart. Dropped for the slide: the 3- and
14-day values at the range ends, the machine and ticket counts under the group names, the "random timing" words
next to its values (the legend names the marker) and the footer, which go to the speaker notes.

Output:  viz/figures/slides/htm_05_episode_followups.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_05_episode_followups_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
from matplotlib.lines import Line2D  # noqa: E402

import htm  # noqa: E402
import htm_05_episode_followups as full  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402


def plot(out_dir=slides.FIG_DIR):
    S = htm.summary()
    D5 = S['D5_episodes']
    lo_gap, gap, hi_gap = S['definitions']['episode_gaps_days']
    ep = htm.load('episodes')
    machines, tickets, share = {}, {}, {}
    for grp in full.GROUPS:
        k = grp.key
        g = ep[ep.workload_outsized] if k == 'outsized' else ep[~ep.workload_outsized]
        machines[k], tickets[k] = len(g), int(g.tickets.sum())
        share[k] = {d: 1 - g[f'episodes_{d}d'].sum() / tickets[k] for d in (lo_gap, gap, hi_gap)}
        style.check(f'slide D5 {k} {gap}d follow-up share', D5[k][f'followup_share_{gap}d'], round(share[k][gap], 4),
                    1e-4)

    fig, ax = slides.figure()
    rts = {}
    for grp in full.GROUPS:
        key, yv = grp.key, grp.y
        lo, mid, hi = (100 * share[key][d] for d in (lo_gap, gap, hi_gap))
        ax.plot([lo, hi], [yv, yv], color=style.GRAY_LIGHT, lw=2, zorder=2)
        ax.plot([lo, hi], [yv, yv], ls='', marker='|', ms=13, mew=1.2, color=style.MUTED, zorder=2)
        ax.scatter([mid], [yv], s=120, color=grp.color, edgecolors=style.SURFACE, linewidths=1.8, zorder=4)
        ax.annotate(f'{mid:.1f}%', xy=(mid, yv), xytext=(0, 9), textcoords='offset points', ha='center',
                    va='bottom', fontsize=10.5, color=style.INK, weight='bold')

        rt = D5[key][f'followup_share_{gap}d_random_timing']  # median, 2.5th and 97.5th percentile
        rts[key] = rt[0]
        rt_med, rt_lo, rt_hi = (100 * x for x in rt)
        yr = yv - full.RT_OFFSET
        ax.plot([rt_lo, rt_hi], [yr, yr], color=style.MUTED, lw=1, zorder=2)
        ax.scatter([rt_med], [yr], s=55, marker='D', facecolors=style.SURFACE, edgecolors=style.INK2,
                   linewidths=1.3, zorder=3)
        ax.annotate(f'{rt_med:.1f}%', xy=(rt_hi, yr), xytext=(8, 0), textcoords='offset points', ha='left',
                    va='center', fontsize=9, color=style.INK2)

    ys = [grp.y for grp in full.GROUPS]
    ax.set_yticks(ys)
    ax.set_yticklabels([grp.label for grp in full.GROUPS], color=style.INK2)
    ax.set_ylim(min(ys) - full.RT_OFFSET - 0.45, max(ys) + 0.75)
    ax.set_xlim(0, 100 * max(s[hi_gap] for s in share.values()) + 4)
    style.style_axes(ax, grid='x', baseline=None)
    style.pct_axis(ax.xaxis)
    ax.set_xlabel('Follow-up share of unplanned tickets')
    handles = [Line2D([], [], marker='o', ls='', ms=9.5, mfc=style.INK2, mec=style.SURFACE, label=f'{gap}-day rule'),
               Line2D([], [], color=style.GRAY_LIGHT, lw=2, label=f'{lo_gap}- to {hi_gap}-day range'),
               Line2D([], [], marker='D', ls='-', lw=1, color=style.MUTED, ms=7, mfc=style.SURFACE,
                      mec=style.INK2, mew=1.3, label='Random timing')]
    ax.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=3, handletextpad=0.5,
              columnspacing=1.6)

    ratio = share['outsized'][gap] / share['other'][gap]
    title = (f'Outsized machines\' tickets are {gap}-day follow-ups {ratio:.1f}× as often '
             f'({style.pct(share["outsized"][gap])} vs {style.pct(share["other"][gap])})')
    range_txt = '; '.join(f'{grp.label.lower()} {100 * share[grp.key][lo_gap]:.1f}% to '
                          f'{100 * share[grp.key][hi_gap]:.1f}%' for grp in full.GROUPS)
    talk = [htm.outsized_definition(S),
            f'Follow-up = a ticket that opens within {gap} days of the same machine\'s previous ticket. The gray range '
            f'shows the {lo_gap}- and {hi_gap}-day rules: {range_txt}.',
            f'Population: all {sum(tickets.values()):,} unplanned tickets on {len(ep):,} machines (case-export '
            f'serials), {htm.period_text(S, "case_export_period")}: {machines["outsized"]:,} outsized machines with '
            f'{tickets["outsized"]:,} tickets, {machines["other"]:,} others with {tickets["other"]:,}.',
            f'Random timing = each machine\'s tickets placed uniformly at random over the period '
            f'({S["definitions"]["n_sim_episodes"]} draws, a rough null; median and 95% interval). More tickets alone '
            f'produce more follow-ups: {style.pct(rts["outsized"])} for outsized machines and '
            f'{style.pct(rts["other"])} for the rest.']
    return [slides.finish(fig, Path(out_dir) / full.PNG, title,
                          f'Share of unplanned tickets opened within {gap} days of the machine\'s previous ticket',
                          talk)]


if __name__ == '__main__':
    plot()
