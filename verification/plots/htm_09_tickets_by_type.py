#!/usr/bin/env python3
"""Which machine types generate the most unplanned tickets (raw counts, NOT adjusted for fleet size).

Two charts, same form (horizontal bars, most tickets first, the tail grouped as "Other"):
  htm_09_tickets_by_model.png         by model as recorded in the case export (all unplanned tickets)
  htm_09_tickets_by_machine_type.png  by telemetry machine type (device-matched unplanned tickets)

Both carry a disclaimer: the counts are not adjusted for how many machines of each type are in the fleet, so a type
can rank high simply because many of its machines are installed. Chart 10 (htm_10_ticket_rate_by_machine_type.py)
shows the exposure-adjusted rates per 100 machine-months by telemetry type.

Inputs:  verification/outputs/htm_type_mix.csv (field = model / machine_type: unplanned_tickets per value)
         verification/outputs/htm_summary.json (D1_workload: total tickets and machines, for consistency checks)
Run:     cd /home/user/analytics-lab && python3 -I verification/plots/htm_09_tickets_by_type.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

import style  # noqa: E402

N_SHOWN = 12      # bars before the tail is grouped as "Other"
N_HIGHLIGHT = 3   # top bars in emphasis blue; the titles say "Three" and the subtitles name them
NOT_MATCHED = '(not device-matched)'

DISCLAIMER = ('Not adjusted for fleet size: these are raw ticket counts, so a type can rank high simply because many '
              'machines of that type are installed.')


def tickets_by(field):
    tm = style.load('type_mix')
    d = tm.loc[tm.field == field, ['value', 'unplanned_tickets']]
    return d.sort_values(['unplanned_tickets', 'value'], ascending=[False, True], kind='mergesort')


def draw(d, total, noun, title, subtitle, notes, disclaimer, path):
    shown, rest = d.head(N_SHOWN), d.iloc[N_SHOWN:]
    labels = shown.value.tolist() + ([f'Other ({len(rest)} {noun})'] if len(rest) else [])
    counts = shown.unplanned_tickets.tolist() + ([int(rest.unplanned_tickets.sum())] if len(rest) else [])
    colors = [style.BLUE] * N_HIGHLIGHT + [style.GRAY_LIGHT] * (len(shown) - N_HIGHLIGHT)
    colors += [style.BAR_BACKGROUND] * (len(labels) - len(shown))

    fig, ax = style.figure(10, 1.9 + 0.36 * len(labels) + 1.6)
    y = np.arange(len(labels))[::-1]
    ax.barh(y, counts, height=0.5, color=colors, linewidth=0)
    for yi, n in zip(y, counts):
        ax.text(n + max(counts) * 0.01, yi, f'{n:,}  ({style.pct(n / total)})', va='center', ha='left',
                fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    ax.set_ylim(-0.6, len(labels) - 0.4)
    ax.set_xlim(0, max(counts) * 1.2)
    style.style_axes(ax, grid='x', baseline='left')
    style.thousands_axis(ax.xaxis)
    ax.set_xlabel('Unplanned tickets')
    style.frame(fig, title, subtitle, notes=notes, definitions=[disclaimer])
    return style.save(fig, path)


def plot(out_dir=style.FIG_DIR):
    out_dir = Path(out_dir)
    S = style.summary()['D1_workload']
    written = []

    # By model (case export): every unplanned ticket has one.
    m = tickets_by('model')
    total = int(m.unplanned_tickets.sum())
    style.check('htm_09 model tickets = D1 tickets', S['tickets'], total)
    top = m.head(N_HIGHLIGHT)
    written.append(draw(
        m, total, 'models',
        f'Three models generate {style.pct(top.unplanned_tickets.sum() / total, 0)} of unplanned tickets',
        f'Raw counts, not adjusted for fleet size (see the note below). Blue: {", ".join(top.value)}. '
        f'All {total:,} unplanned tickets on {S["machines"]:,} ticketed machines (case-export '
        f'serials), Aug 2025 to Aug 2026. Excludes planned work, cancelled and duplicate cases. Share of all '
        f'unplanned tickets in brackets.',
        [f'Each machine is counted under its most frequently recorded model. Other = the {len(m) - N_SHOWN} models '
         f'with the fewest tickets.', 'Source: htm_type_mix.csv (field = model).'],
        DISCLAIMER + ' The number of installed machines per model is not in the data (model is recorded only on '
        'tickets), so per-machine rates by model cannot be computed.',
        out_dir / 'htm_09_tickets_by_model.png'))

    # By telemetry machine type: only tickets whose serial matches a telemetry device.
    t = tickets_by('machine_type')
    style.check('htm_09 machine-type tickets = D1 tickets', S['tickets'], int(t.unplanned_tickets.sum()))
    unmatched = int(t.loc[t.value == NOT_MATCHED, 'unplanned_tickets'].sum())
    t = t[t.value != NOT_MATCHED]
    matched = int(t.unplanned_tickets.sum())
    top = t.head(N_HIGHLIGHT)
    written.append(draw(
        t, matched, 'types',
        f'Three telemetry types generate {style.pct(top.unplanned_tickets.sum() / matched, 0)} of device-matched '
        f'tickets',
        f'Raw counts, not adjusted for fleet size (see the note below). Blue: {", ".join(top.value)}. '
        f'{matched:,} unplanned tickets whose serial matches a telemetry device, '
        f'Aug 2025 to Aug 2026. Share of device-matched tickets in brackets.',
        [f'Not shown: {unmatched:,} tickets on machines not matched to a telemetry device. Other = the '
         f'{len(t) - N_SHOWN} types with the fewest tickets.',
         'Source: htm_type_mix.csv (field = machine_type).'],
        DISCLAIMER + ' Chart 10 adjusts for this: ticket rates per 100 machine-months by telemetry type '
        '(htm_10_ticket_rate_by_machine_type.png).',
        out_dir / 'htm_09_tickets_by_machine_type.png'))
    return written


if __name__ == '__main__':
    plot()
