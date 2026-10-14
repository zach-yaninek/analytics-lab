#!/usr/bin/env python3
"""Slide version of chart 6 (viz/high_ticket/htm_06_pre_ticket.py): telemetry in the 30 days before each unplanned
ticket, by machine group (two figures).

Same cumulative distributions, groups, colours and axis cuts as the full charts. Dropped for the slides: the ticket
and machine counts in the legend (each entry keeps its group's median) and the footer (definitions, zero-event and
axis-cut notes, paired controls), which go to the speaker notes.

Outputs: viz/figures/slides/htm_06_pre_ticket_events.png
         viz/figures/slides/htm_06_pre_ticket_nonsuccess.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_06_pre_ticket_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import htm  # noqa: E402
import htm_06_pre_ticket as full  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402

LEGEND = {'chronic': 'Chronic outliers', 'workload_outsized': 'Workload-outsized only', 'other': 'Other machines'}
SUBJECT = {'events': 'telemetry events', 'nonsuccess': 'non-success rate'}  # subtitle: "... by <subject> in the ..."


def plot(out_dir=slides.FIG_DIR):
    out_dir = Path(out_dir)
    S = htm.summary()
    pt = htm.load('pre_ticket')
    ps = htm.load('pre_ticket_summary').set_index(['group', 'window'])
    events_col, days = full.window_column(pt)
    usable = int(pt.group.isin([g.key for g in full.GROUPS]).sum())
    population = (f'Population: unplanned tickets on device-matched machines with a usable {days}-day telemetry '
                  f'window. Telemetry is in UTC; ticket times are converted from US Eastern.')

    written = []
    for spec in full.SPECS:
        col = spec.column.format(events=events_col)
        fig, ax = slides.figure()
        med, beyond, n, counts = {}, {}, {}, []
        for g in full.GROUPS:
            sub = pt[pt.group == g.key]
            v = sub[col].dropna()
            med[g.key], beyond[g.key], n[g.key] = v.median(), int((v > spec.xmax).sum()), len(v)
            row = ps.loc[(g.summary, 'ticket (all usable)')]
            median_col = 'all_events_median' if spec.key == 'events' else 'non_success_per_1000_median'
            style.check(f'slide pre-ticket {g.key} median {spec.key}', row[median_col], med[g.key], 0.05)
            counts.append(f'{g.short} {len(v):,} tickets on {sub.machine_id[sub[col].notna()].nunique():,} machines')
            full.ecdf(ax, v, g.color, f'{LEGEND[g.key]}: median {spec.fmt.format(med[g.key])}', g.z)
        ax.set_xlim(-full.XPAD * spec.xmax, spec.xmax)
        ax.set_ylim(0, 101)
        style.style_axes(ax, grid='both')
        style.thousands_axis(ax.xaxis)
        style.pct_axis(ax.yaxis)
        ax.set_xlabel(spec.xlabel.format(days=days))
        ax.set_ylabel('Share of tickets at or below x')
        ax.legend(loc='lower right', handlelength=2.2, frameon=True, facecolor=style.SURFACE, edgecolor='none',
                  framealpha=1)

        beyond_txt = ', '.join(f'{g.short} {beyond[g.key]}' for g in full.GROUPS)
        talk = [htm.chronic_definition(S), htm.outsized_definition(S), population,
                f'Tickets per group: {"; ".join(counts)}.']
        if spec.key == 'events':
            zero = {g.key: (pt.loc[pt.group == g.key, col] == 0).mean() for g in full.GROUPS}
            title = (f'Chronic outliers were busier before tickets: median {med["chronic"]:,.0f} events vs '
                     f'{med["other"]:,.0f}')
            talk += [f'Lines start above 0 where the device logged no events in the window '
                     f'({", ".join(f"{g.short} {style.pct(zero[g.key])}" for g in full.GROUPS)}). Axis cut at '
                     f'{spec.xmax:,}; tickets beyond it: {beyond_txt}.']
        else:
            paired = {g.key: (ps.loc[(g.summary, 'ticket (paired)')].non_success_per_1000_median,
                              ps.loc[(g.summary, 'control (paired)')].non_success_per_1000_median)
                      for g in full.GROUPS}
            title = (f'Chronic outliers logged more non-success events: median {med["chronic"]:.0f} vs '
                     f'{med["other"]:.0f} per 1,000')
            talk += [f'Tickets with no events in the window are left out ({sum(n.values()):,} of {usable:,} tickets '
                     f'shown). Axis cut at {spec.xmax:,}; tickets beyond it: {beyond_txt}.',
                     f'Paired control on the same machine {S["definitions"]["control_offset_days"]} days earlier, '
                     f'median before the ticket vs in the control window: '
                     + ', '.join(f'{g.short} {paired[g.key][0]:.1f} vs {paired[g.key][1]:.1f}' for g in full.GROUPS)
                     + '.']
        written.append(slides.finish(
            fig, out_dir / spec.png, title,
            f'Unplanned tickets by {SUBJECT[spec.key]} in the {days} days before the ticket, by machine group', talk))
    return written


if __name__ == '__main__':
    plot()
