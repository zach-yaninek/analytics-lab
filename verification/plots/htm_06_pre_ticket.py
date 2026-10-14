#!/usr/bin/env python3
"""Chart 6: telemetry in the 30 days before each unplanned ticket, by machine group (two figures).

Cumulative distributions (share of tickets at or below x) for three groups of device-matched machines: chronic
outliers, workload-outsized machines that are not chronic outliers, and all other machines.
  events:      telemetry events logged in the 30-day window before the ticket
  nonsuccess:  non-success events per 1,000 events in that window (tickets with no events left out); the footer
               adds each group's paired medians against the same machine's window 35 days earlier
Each legend entry gives the group's tickets, machines and median; the title compares chronic outliers with the
other machines. The x-axis is cut at a fixed value and the footer counts the tickets beyond it. The window length
(30 days) is read from the all_events_<N>d column name.

Inputs:
  verification/outputs/htm_pre_ticket.csv          one row per usable ticket: group, device_class,
                                                   workload_outsized, machine_id, serial_id, all_events_30d,
                                                   non_success_per_1000, control_clean_available,
                                                   control_non_success_per_1000
  verification/outputs/htm_pre_ticket_summary.csv  per group and window: tickets, machines, medians,
                                                   zero_events_share (paired medians are read from here)
  verification/outputs/htm_episodes.csv            tickets per serial (check of the workload_outsized flag only)
  verification/outputs/htm_summary.json            chronic_outlier_ids; definitions.control_offset_days; D1_workload
                                                   and definitions for the chronic-outlier and workload-outsized
                                                   definitions
Outputs:
  verification/outputs/figures/htm_06_pre_ticket_events.png
  verification/outputs/figures/htm_06_pre_ticket_nonsuccess.png

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/htm_06_pre_ticket.py
"""
import re
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

import style  # noqa: E402

class Group(NamedTuple):
    key: str      # group in htm_pre_ticket.csv
    summary: str  # group in htm_pre_ticket_summary.csv
    name: str     # legend
    short: str    # footer (no-break spaces keep it on one line)
    color: str
    z: int


class Spec(NamedTuple):
    key: str
    column: str   # htm_pre_ticket.csv column; {events} is the all_events_<N>d column
    xmax: float   # axis cut
    xlabel: str   # {days} is the window length
    unit: str     # after the median in the legend
    fmt: str      # median format
    png: str


GROUPS = [  # legend order
    Group('chronic', 'chronic', 'Chronic outliers', 'chronic', style.BLUE, 5),
    # Aqua, as for the same idea in chart 3 (workload-outsized, not a rate outlier); the legend labels it.
    Group('workload_outsized', 'workload_outsized_not_chronic', 'Workload-outsized only (not chronic)',
          'outsized\u00a0only', style.AQUA, 4),
    Group('other', 'other', 'Other machines', 'other', style.GRAY, 3),
]

SPECS = [
    Spec('events', '{events}', 8000, 'Telemetry events in the {days} days before the ticket', 'events', '{:,.0f}',
         'htm_06_pre_ticket_events.png'),
    Spec('nonsuccess', 'non_success_per_1000', 600,
         'Non-success events per 1,000 events in the {days} days before the ticket', 'per 1,000', '{:.1f}',
         'htm_06_pre_ticket_nonsuccess.png'),
]
XPAD = 0.005  # left x padding (share of the axis cut) so the zero-event jumps at x = 0 are not half clipped


def window_column(pt):
    """The all_events_<N>d column of htm_pre_ticket.csv and the window length N in days."""
    (col,) = [c for c in pt.columns if re.fullmatch(r'all_events_\d+d', c)]
    return col, int(col[len('all_events_'):-1])


def ecdf(ax, values, color, label, z):
    """Step line of the share of values at or below x, in percent, starting at (0, 0)."""
    v = np.sort(np.asarray(values, float))
    x = np.concatenate([[0.0], v])
    y = np.concatenate([[0.0], np.arange(1, len(v) + 1) / len(v)])
    ax.plot(x, 100 * y, drawstyle='steps-post', color=color, lw=2.0, label=label, zorder=z)


def consistency_checks(S, pt, ps, ep, events_col):
    """Groups match the chronic / workload-outsized flags both ways; the per-group summary matches the ticket rows."""
    chronic_ids = set(S['chronic_outlier_ids'])
    style.check('pre-ticket chronic machines are summary chronic outliers', 0,
                len(set(pt.machine_id[pt.group == 'chronic']) - chronic_ids))
    style.check('pre-ticket summary chronic outliers are all in the chronic group', 0,
                int((pt.machine_id.isin(chronic_ids) & (pt.group != 'chronic')).sum()))
    expect = np.select([pt.device_class.eq('chronic_outlier'), pt.workload_outsized], ['chronic', 'workload_outsized'],
                       'other')
    style.check('pre-ticket groups = chronic / outsized-not-chronic / other', 0, int((pt.group != expect).sum()))
    # The workload flag against the drawn threshold, through the serial's ticket count in htm_episodes.csv.
    tickets = pt.serial_id.map(ep.set_index('machine_id').tickets)
    style.check('pre-ticket serials found in htm_episodes.csv', 0, int(tickets.isna().sum()))
    style.check('pre-ticket workload_outsized = tickets >= threshold', 0,
                int((pt.workload_outsized != (tickets >= S['D1_workload']['threshold'])).sum()))
    for g in GROUPS:
        sub = pt[pt.group == g.key]
        row = ps.loc[(g.summary, 'ticket (all usable)')]
        style.check(f'pre-ticket {g.key} tickets', row.tickets, len(sub))
        style.check(f'pre-ticket {g.key} machines', row.machines, sub.machine_id.nunique())
        style.check(f'pre-ticket {g.key} median events', row.all_events_median, sub[events_col].median(), 0.05)
        style.check(f'pre-ticket {g.key} zero-event share', row.zero_events_share, (sub[events_col] == 0).mean(),
                    5e-5)
        style.check(f'pre-ticket {g.key} median non-success', row.non_success_per_1000_median,
                    sub.non_success_per_1000.median(), 0.05)
        paired = sub[sub.control_clean_available]
        for window, col in (('ticket (paired)', 'non_success_per_1000'),
                            ('control (paired)', 'control_non_success_per_1000')):
            prow = ps.loc[(g.summary, window)]
            style.check(f'pre-ticket {g.key} {window} tickets', prow.tickets, len(paired))
            style.check(f'pre-ticket {g.key} {window} median non-success', prow.non_success_per_1000_median,
                        paired[col].median(), 0.05)


def plot(out_dir=style.FIG_DIR):
    out_dir = Path(out_dir)
    S = style.summary()
    pt = style.load('pre_ticket')
    ps = style.load('pre_ticket_summary').set_index(['group', 'window'])
    events_col, days = window_column(pt)
    consistency_checks(S, pt, ps, style.load('episodes'), events_col)
    usable = int(pt.group.isin([g.key for g in GROUPS]).sum())
    definitions = [style.chronic_definition(S), style.outsized_definition(S)]

    written = []
    for spec in SPECS:
        col = spec.column.format(events=events_col)
        fig, ax = style.figure(10, 7.4)
        med, beyond, n = {}, {}, {}
        for g in GROUPS:
            sub = pt[pt.group == g.key]
            v = sub[col].dropna()
            med[g.key], beyond[g.key], n[g.key] = v.median(), int((v > spec.xmax).sum()), len(v)
            machines = sub.machine_id[sub[col].notna()].nunique()
            ecdf(ax, v, g.color, f'{g.name}: {len(v):,} tickets on {machines:,} machines, median '
                                 f'{spec.fmt.format(med[g.key])} {spec.unit}', g.z)
        ax.set_xlim(-XPAD * spec.xmax, spec.xmax)
        ax.set_ylim(0, 101)
        style.style_axes(ax, grid='both')
        style.thousands_axis(ax.xaxis)
        style.pct_axis(ax.yaxis)
        ax.set_xlabel(spec.xlabel.format(days=days))
        ax.set_ylabel('Share of tickets at or below x')
        # Lower right: every line is above 60% there. The surface-coloured box keeps the gridlines out of the text.
        ax.legend(loc='lower right', handlelength=2.2, frameon=True, facecolor=style.SURFACE, edgecolor='none',
                  framealpha=1)

        beyond_txt = ', '.join(f'{g.short}\u00a0{beyond[g.key]}' for g in GROUPS)
        if spec.key == 'events':
            zero = {g.key: (pt.loc[pt.group == g.key, col] == 0).mean() for g in GROUPS}
            zero_txt = ', '.join(f'{g.short}\u00a0{style.pct(zero[g.key])}' for g in GROUPS)
            title = (f'Chronic outliers were busier before tickets: median {med["chronic"]:,.0f} events vs '
                     f'{med["other"]:,.0f}')
            population = f'({sum(n.values()):,} tickets)'
            notes = [f'Lines start above 0 where the device logged no events in the window ({zero_txt}). Axis cut at '
                     f'{spec.xmax:,}; tickets beyond: {beyond_txt}.',
                     'Source: htm_pre_ticket.csv; group definitions from htm_summary.json.']
        else:
            paired = {g.key: (ps.loc[(g.summary, 'ticket (paired)')].non_success_per_1000_median,
                              ps.loc[(g.summary, 'control (paired)')].non_success_per_1000_median) for g in GROUPS}
            title = (f'Chronic outliers logged more non-success events: median {med["chronic"]:.0f} vs '
                     f'{med["other"]:.0f} per 1,000')
            # No-break spaces (\u00a0) keep each paired comparison, the counts and the offset whole when frame() wraps.
            paired_txt = ', '.join(f'{g.short}\u00a0{paired[g.key][0]:.1f}\u00a0vs\u00a0{paired[g.key][1]:.1f}'
                                   for g in GROUPS)
            population = f'that logged at least one event ({sum(n.values()):,}\u00a0of\u00a0{usable:,}\u00a0tickets)'
            earlier = f'{S["definitions"]["control_offset_days"]}\u00a0days earlier'
            notes = [f'Tickets with no events in the window are left out. Axis cut at {spec.xmax:,}; tickets beyond: '
                     f'{beyond_txt}. Clean paired controls on the same machine {earlier}, median before the ticket vs '
                     f'in the control window: {paired_txt}.',
                     'Source: htm_pre_ticket.csv, htm_pre_ticket_summary.csv; group definitions from '
                     'htm_summary.json.']
        style.frame(
            fig, title,
            f'Unplanned tickets on device-matched machines with a usable {days}-day telemetry window {population}, by '
            f'machine group. Telemetry in UTC; ticket time converted from US Eastern.',
            definitions=definitions, notes=notes)
        written.append(style.save(fig, out_dir / spec.png))
    return written


if __name__ == '__main__':
    plot()
