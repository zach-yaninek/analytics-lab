#!/usr/bin/env python3
"""Report figure 8 (Results, First look at codes): door codes appear before 68% of the 3,259 paired tickets vs. 61% of
their comparison windows, and electronics codes before 20% vs. 13%.

(a) For each code group, the share of the 3,259 paired tickets whose last 10 codes include a code of the group, in the
    ticket window (filled) and in the comparison window (open). Door and electronics codes, the report's two groups,
    are cobalt; mechanical codes, stock-out codes, and any non-success code, the other rows of the script's first look,
    are grey context.
(b) The same rows, split by pair: the paired tickets that show the group in the ticket window only (right) and in the
    comparison window only (left). The difference of the two bars over 3,259 is the gap between the two dots in (a).

Both windows are the 30-day ones of the first look; the 7-day association results are figure 9.

Inputs: verification/outputs/fu/fu_ticket_last10.csv (each ticket's four windows with their last 10 distinct
non-success codes; no customer column), db/db_codes_buckets.csv (each code's group), assoc/as_pairs.csv (the script's
paired tickets; read without its cluster column) and assoc/as_summary.json (the script's first-look check and pinned
counts). Notebook 06 checks the same numbers, with the same rule for paired tickets.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig08_first_look'
LABEL = 'fig:first-look'
SHORT = 'First look at codes'

TICKET, COMPARISON = 'corrected_guard0', 'control_minus35d'   # the 30 days before the ticket; the comparison window
NOT_UNPLANNED = ['Planned work', 'Cancelled request', 'Duplicate case']
WINDOW_COLS = ['case_id', 'window', 'service_group', 'lookback_truncated', 'after_telemetry_end', 'control_clean',
               'distinct_codes', 'last10_distinct']
GRID_TOP = -0.5               # the light grid stops above the top row, below the column headers
# (row label, team bucket in db_codes_buckets.csv or None for any non-success code, focal, y position)
ROWS = [('Door codes', 'Door issue', True, 0.0),
        ('Electronics codes', 'Electronics/software/comms', True, 1.0),
        ('Mechanical codes', 'Mechanical fault', False, 2.35),
        ('Stock-out codes', 'Stock-out', False, 3.35),
        ('Any non-success code', None, False, 4.35)]


def paired_windows():
    """The ticket and comparison windows of the paired tickets (notebook 06): unplanned, both windows inside the
    telemetry, and a clean comparison window."""
    windows = pd.read_csv(S.OUT / 'fu' / 'fu_ticket_last10.csv', dtype=str, keep_default_na=False,
                          usecols=WINDOW_COLS)
    win = {w: d.set_index('case_id').sort_index() for w, d in windows.groupby('window')}
    t0, c0 = win[TICKET], win[COMPARISON]
    S.check('fig08 one ticket and one comparison window per ticket', 1, int(t0.index.equals(c0.index)))

    def flag(column):
        return column.to_numpy() == 'True'

    unplanned = ~t0.service_group.isin(NOT_UNPLANNED).to_numpy()
    complete = (~flag(t0.lookback_truncated) & ~flag(t0.after_telemetry_end)
                & ~flag(c0.lookback_truncated) & ~flag(c0.after_telemetry_end))
    paired = unplanned & complete & flag(c0.control_clean)
    return t0[paired], c0[paired]


def plot(out_dir=S.FIG_DIR):
    t0, c0 = paired_windows()
    n_paired = len(t0)
    summary = json.loads((S.OUT / 'assoc' / 'as_summary.json').read_text())
    script = {c['check']: c['actual'] for c in summary['check_list']}
    pairs = pd.read_csv(S.OUT / 'assoc' / 'as_pairs.csv', dtype=str, keep_default_na=False,
                        usecols=['case_id', 'in_paired'])
    S.check('fig08 paired tickets = as_pairs.csv\'s', 1,
            int(set(t0.index) == set(pairs.case_id[pairs.in_paired == '1'])))
    S.check('fig08 paired tickets = the pinned count', summary['pinned_counts']['A2 paired tickets'], n_paired)

    codes = pd.read_csv(S.OUT / 'db' / 'db_codes_buckets.csv', dtype=str, keep_default_na=False)
    group_of = dict(zip(codes.transaction_code, codes.bucket))

    def shows(window, bucket):
        """Per paired ticket: the window's last 10 distinct non-success codes include a code of the bucket (any
        non-success code when bucket is None)."""
        if bucket is None:
            return (window.distinct_codes.astype(int) > 0).to_numpy()
        return np.array([any(group_of.get(c) == bucket for c in listed.split('|') if c)
                         for listed in window.last10_distinct])

    data = {}
    for name, bucket, focal, y in ROWS:
        t, c = shows(t0, bucket), shows(c0, bucket)
        data[name] = dict(ticket=t.mean(), comparison=c.mean(), ticket_only=int((t & ~c).sum()),
                          comparison_only=int((~t & c).sum()), focal=focal, y=y)
        key = f'first look: {bucket or "any code"} (ticket, control %)'
        S.check(f'fig08 {name}: ticket-window share = association.py\'s first look', script[key][0],
                round(100 * t.mean(), 1))
        S.check(f'fig08 {name}: comparison-window share = association.py\'s first look', script[key][1],
                round(100 * c.mean(), 1))
        S.check(f'fig08 {name}: the gap = (ticket only - comparison only) / paired', t.mean() - c.mean(),
                (data[name]['ticket_only'] - data[name]['comparison_only']) / n_paired, 1e-12)
    door, elec = data['Door codes'], data['Electronics codes']

    listed = [(len([c for c in s.split('|') if c]), int(n)) for w in (t0, c0)
              for s, n in zip(w.last10_distinct, w.distinct_codes)]
    S.report_check('fig08 the last 10 codes (Definitions)', '10', S.num(max(k for k, _ in listed)))
    S.check('fig08 windows with more than 10 distinct codes list exactly 10', 0,
            sum(k != min(n, 10) for k, n in listed))
    S.report_check('fig08 paired tickets', '3,259', S.num(n_paired))
    S.report_check('fig08 door codes before paired tickets', '68%', S.pct(door['ticket']))
    S.report_check('fig08 door codes in their comparison windows', '61%', S.pct(door['comparison']))
    S.report_check('fig08 electronics codes before paired tickets', '20%', S.pct(elec['ticket']))
    S.report_check('fig08 electronics codes in their comparison windows', '13%', S.pct(elec['comparison']))

    fig, (ax, bx) = S.figure(2.0, ncols=2, width_ratios=[1.25, 1])
    ys = [d['y'] for d in data.values()]

    # (a) the two shares per code group: ticket window filled, comparison window open
    for name, d in data.items():
        y, t, c = d['y'], d['ticket'], d['comparison']
        ax.plot([c, t], [y, y], color=S.COBALT if d['focal'] else S.GREY_FILL, lw=1.5, solid_capstyle='butt',
                zorder=2)
        ax.plot(c, y, 'o', mfc=S.WHITE, mec=S.GREY_DARK, mew=1.0, ms=4.5, zorder=3)
        ax.plot(t, y, 'o', color=S.COBALT if d['focal'] else S.GREY, ms=4.5, zorder=4)
        key = name == 'Door codes'                  # the one green readout: door codes before the ticket
        for value, x, ha, which in ((t, t + 0.022, 'left', 'ticket'), (c, c - 0.022, 'right', 'comparison')):
            text = S.pct(value)
            S.check(f'fig08 (a) {name} {which} label {text}', round(100 * value), float(text.rstrip('%')))
            bold = key and which == 'ticket'
            S.label(ax, x, y, text, ha=ha, size=S.FONT if bold else S.TICK, weight='bold' if bold else 'normal',
                    color=S.GREEN if bold else S.TEXT)
    S.label(ax, door['comparison'] + 0.004, -0.62, 'Comparison window', ha='right', va='bottom')
    S.label(ax, door['ticket'] - 0.004, -0.62, 'Ticket window', ha='left', va='bottom')
    ax.set_yticks(ys, list(data))
    ax.set_ylim(4.85, -1.15)
    ax.set_xlim(0, 1.03)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.vlines(ax.get_xticks(), GRID_TOP, ax.get_ylim()[0], color=S.GRID, lw=0.6, zorder=0)
    S.pct_axis(ax.xaxis)
    ax.set_xlabel('Share of paired tickets')
    S.clean(ax, left=False)
    S.panel(ax, 'a', 'Ticket vs. comparison window')

    # (b) the paired tickets with the group in one window only: ticket window to the right, comparison to the left
    for name, d in data.items():
        y, right, left = d['y'], d['ticket_only'], d['comparison_only']
        bx.barh(y, right, height=0.5, color=S.COBALT if d['focal'] else S.GREY, zorder=3)
        bx.barh(y, -left, height=0.5, color=S.GREY_FILL, zorder=3)
        for value, x, ha in ((right, right + 12, 'left'), (left, -left - 12, 'right')):
            text = S.num(value)
            S.check(f'fig08 (b) {name} label {text}', value, int(text.replace(',', '')))
            S.label(bx, x, y, text, ha=ha)
    bx.axvline(0, color=S.GREY_DARK, lw=0.6, zorder=4)
    S.label(bx, -14, -0.62, 'Comparison only', ha='right', va='bottom')
    S.label(bx, 14, -0.62, 'Ticket only', ha='left', va='bottom')
    bx.set_ylim(4.85, -1.15)
    bx.set_yticks([])
    bx.set_xlim(-350, 560)
    bx.set_xticks([-200, 0, 200, 400], ['200', '0', '200', '400'])
    bx.vlines([-200, 200, 400], GRID_TOP, bx.get_ylim()[0], color=S.GRID, lw=0.6, zorder=0)
    bx.set_xlabel('Paired tickets')
    S.clean(bx, left=False)
    S.panel(bx, 'b', 'Codes in one window only')

    # Nothing drawn is clipped: every dot and bar inside its panel's limits
    S.check('fig08 (a) dots inside the axis', 1, int(max(d['ticket'] for d in data.values()) < ax.get_xlim()[1]))
    S.check('fig08 (b) bars inside the axis', 1,
            int(max(d['ticket_only'] for d in data.values()) < bx.get_xlim()[1]
                and -max(d['comparison_only'] for d in data.values()) > bx.get_xlim()[0]))

    S.export(fig, NAME, out_dir)
    pc = lambda share: S.pct(share).replace('%', chr(92) + '%')  # noqa: E731
    return (f'Door codes appear before {pc(door["ticket"])} of the {S.num(n_paired)} paired tickets vs. '
            f'{pc(door["comparison"])} of their comparison windows, and electronics codes before {pc(elec["ticket"])} '
            f'vs. {pc(elec["comparison"])}. '
            f'(a)~Dots show the share of paired tickets with a code of each group among the last 10 codes of the '
            f'ticket window (filled) and the comparison window (open). '
            f'(b)~Bars show the paired tickets with the group in one window only.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
