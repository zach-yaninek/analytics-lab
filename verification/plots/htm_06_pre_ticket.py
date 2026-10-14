#!/usr/bin/env python3
"""Chart 6: telemetry in the 30 days before each unplanned ticket, by machine group (two figures).

Cumulative distributions (share of tickets at or below x) for three groups of device-matched machines: chronic
outliers, workload-outsized machines that are not chronic outliers, and all other machines.
  events:      telemetry events logged in the 30-day window before the ticket
  nonsuccess:  non-success events per 1,000 events in that window (tickets with no events left out); the footer
               adds the clean paired comparison with the same machine's window 35 days earlier
Each legend entry gives the group's tickets, machines and median; the title compares chronic outliers with the
other machines. The x-axis is cut at a fixed value and the footer counts the tickets beyond it.

Inputs:
  verification/outputs/htm_pre_ticket.csv          one row per usable ticket: group, device_class,
                                                   workload_outsized, machine_id, all_events_30d,
                                                   non_success_per_1000, control_clean_available,
                                                   control_non_success_per_1000
  verification/outputs/htm_pre_ticket_summary.csv  per group and window: tickets, machines, medians,
                                                   zero_events_share (paired medians are read from here)
  verification/outputs/htm_summary.json            chronic_outlier_ids; D1_workload and definitions.q_cut for the
                                                   chronic-outlier and workload-outsized definitions
Outputs:
  verification/outputs/figures/htm_06_pre_ticket_events.png
  verification/outputs/figures/htm_06_pre_ticket_nonsuccess.png

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_06_pre_ticket.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from matplotlib.text import Annotation  # noqa: E402

import style  # noqa: E402

# Control window offset: the 'control_minus35d' window in verification/high_ticket_machines.py (not in the htm_*
# outputs).
CONTROL_OFFSET_DAYS = 35

# (group in htm_pre_ticket.csv, group in htm_pre_ticket_summary.csv, legend name, short name for the footer,
# colour, z-order), in legend order.
GROUPS = [
    ('chronic', 'chronic', 'Chronic outliers', 'chronic', style.BLUE, 5),
    ('workload_outsized', 'workload_outsized_not_chronic', 'Workload-outsized, not chronic', 'outsized not chronic',
     style.ORANGE, 4),
    ('other', 'other', 'Other machines', 'other', style.GRAY, 3),
]

# (key, column, x-axis cut, x label, unit in the legend, median format, PNG)
SPECS = [
    ('events', 'all_events_30d', 8000, 'Telemetry events in the 30 days before the ticket', 'events', '{:,.0f}',
     'htm_06_pre_ticket_events.png'),
    ('nonsuccess', 'non_success_per_1000', 600,
     'Non-success events per 1,000 events in the 30 days before the ticket', 'per 1,000', '{:.1f}',
     'htm_06_pre_ticket_nonsuccess.png'),
]


def ecdf(ax, values, color, label, z):
    """Step line of the share of values at or below x, in percent, starting at (0, 0)."""
    v = np.sort(np.asarray(values, float))
    x = np.concatenate([[0.0], v])
    y = np.concatenate([[0.0], np.arange(1, len(v) + 1) / len(v)])
    ax.plot(x, 100 * y, drawstyle='steps-post', color=color, lw=2.0, label=label, zorder=z)


def separate_first_definition(fig, first):
    """Draw the first definition as a text artist of its own, directly above the remaining definition lines.

    style.frame() draws all definitions as one text block, but run_all.py's definition check looks for
    style.chronic_definition() as a whole drawn string. The block keeps its place (and the band frame() reserved
    for it) and keeps only the later definitions; the first one is re-drawn just above it, anchored to the block,
    so nothing is measured or positioned by hand. Does nothing when the first definition is already separate."""
    flat = ' '.join(first.split())
    for t in fig.texts:
        lines = t.get_text().split('\n')
        k = next((k for k in range(1, len(lines)) if ' '.join(' '.join(lines[:k]).split()) == flat), None)
        if k is None:
            continue
        t.set_text('\n'.join(lines[k:]))
        fig.add_artist(Annotation('\n'.join(lines[:k]), xy=(0, 1), xycoords=t, xytext=(0, 1),
                                  textcoords='offset points', ha='left', va='bottom', fontsize=t.get_fontsize(),
                                  color=t.get_color(), linespacing=t.get_linespacing()))
        return


def consistency_checks(S, pt, ps):
    """Groups match the chronic / workload-outsized flags; the per-group summary matches the ticket rows."""
    chronic_ids = set(S['chronic_outlier_ids'])
    style.check('pre-ticket chronic machines are summary chronic outliers', 0,
                len(set(pt.machine_id[pt.group == 'chronic']) - chronic_ids))
    expect = np.select([pt.device_class.eq('chronic_outlier'), pt.workload_outsized], ['chronic', 'workload_outsized'],
                       'other')
    style.check('pre-ticket groups = chronic / outsized-not-chronic / other', 0, int((pt.group != expect).sum()))
    for g, sg, *_ in GROUPS:
        sub = pt[pt.group == g]
        row = ps.loc[(sg, 'ticket (all usable)')]
        style.check(f'pre-ticket {g} tickets', row.tickets, len(sub))
        style.check(f'pre-ticket {g} machines', row.machines, sub.machine_id.nunique())
        style.check(f'pre-ticket {g} median events', row.all_events_median, sub.all_events_30d.median(), 0.05)
        style.check(f'pre-ticket {g} zero-event share', row.zero_events_share, (sub.all_events_30d == 0).mean(), 5e-5)
        style.check(f'pre-ticket {g} median non-success', row.non_success_per_1000_median,
                    sub.non_success_per_1000.median(), 0.05)
        paired = sub[sub.control_clean_available]
        for window, col in (('ticket (paired)', 'non_success_per_1000'),
                            ('control (paired)', 'control_non_success_per_1000')):
            prow = ps.loc[(sg, window)]
            style.check(f'pre-ticket {g} {window} tickets', prow.tickets, len(paired))
            style.check(f'pre-ticket {g} {window} median non-success', prow.non_success_per_1000_median,
                        paired[col].median(), 0.05)


def plot(out_dir=style.FIG_DIR):
    out_dir = Path(out_dir)
    S = style.summary()
    pt = style.load('pre_ticket')
    ps = style.load('pre_ticket_summary').set_index(['group', 'window'])
    consistency_checks(S, pt, ps)
    definitions = [style.chronic_definition(S), style.outsized_definition(S)]

    written = []
    for key, col, xmax, xlabel, unit, fmt, png in SPECS:
        fig, ax = style.figure(10, 7.4)
        med, beyond, n = {}, {}, {}
        for g, _, name, _, color, z in GROUPS:
            sub = pt[pt.group == g]
            v = sub[col].dropna()
            med[g], beyond[g], n[g] = v.median(), int((v > xmax).sum()), len(v)
            machines = sub.machine_id[sub[col].notna()].nunique()
            ecdf(ax, v, color, f'{name}: {len(v):,} tickets on {machines:,} machines, median '
                               f'{fmt.format(med[g])} {unit}', z)
        ax.set_xlim(0, xmax)
        ax.set_ylim(0, 101)
        style.style_axes(ax, grid='both')
        style.thousands_axis(ax.xaxis)
        style.pct_axis(ax.yaxis)
        ax.set_xlabel(xlabel)
        ax.set_ylabel('Share of tickets at or below x')
        # The lines reach 90% or more well before the axis cut, so the lower right of the plot is empty.
        ax.legend(loc='lower right', handlelength=2.2)

        beyond_txt = ', '.join(f'{short} {beyond[g]}' for g, _, _, short, _, _ in GROUPS)
        if key == 'events':
            zero = {g: (pt.loc[pt.group == g, col] == 0).mean() for g, *_ in GROUPS}
            zero_txt = ', '.join(f'{short} {style.pct(zero[g])}' for g, _, _, short, _, _ in GROUPS)
            title = (f'Chronic outliers were busier before tickets: median {med["chronic"]:,.0f} events vs '
                     f'{med["other"]:,.0f}')
            notes = [f'Lines start above 0 where the device logged no events in the window ({zero_txt}). Axis cut at '
                     f'{xmax:,}; tickets beyond: {beyond_txt}.',
                     'Source: htm_pre_ticket.csv; group definitions from htm_summary.json.']
        else:
            paired = {g: (ps.loc[(sg, 'ticket (paired)')].non_success_per_1000_median,
                          ps.loc[(sg, 'control (paired)')].non_success_per_1000_median) for g, sg, *_ in GROUPS}
            title = (f'Chronic outliers logged more non-success events: median {med["chronic"]:.0f} vs '
                     f'{med["other"]:.0f} per 1,000')
            earlier = f'{CONTROL_OFFSET_DAYS}\u00a0days earlier'  # no-break space: keeps the number with its unit
            notes = [f'Tickets with no events in the window are left out. Axis cut at {xmax:,}; tickets beyond: '
                     f'{beyond_txt}. Same machine {earlier} (clean paired controls): chronic '
                     f'{paired["chronic"][0]:.1f} before the ticket vs {paired["chronic"][1]:.1f} in the control '
                     f'window; other machines {paired["other"][0]:.1f} vs {paired["other"][1]:.1f}.',
                     'Source: htm_pre_ticket.csv, htm_pre_ticket_summary.csv; group definitions from '
                     'htm_summary.json.']
        style.frame(
            fig, title,
            f'Unplanned tickets on device-matched machines with a usable 30-day telemetry window '
            f'({sum(n.values()):,} tickets), by machine group. Telemetry in UTC; ticket time converted from US '
            f'Eastern.',
            definitions=definitions, notes=notes)
        separate_first_definition(fig, definitions[0])
        written.append(style.save(fig, out_dir / png))
    return written


if __name__ == '__main__':
    plot()
