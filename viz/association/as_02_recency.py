#!/usr/bin/env python3
"""Association chart 2: how far before a ticket its own codes appear (item 3, cumulative presence).

Share of tickets with their Category's code set present within k hours before the ticket (blue), against the same
machine's control window (gray), for k = 30 minutes to 30 days, on the H1 population (mapped tickets on machine types
that log their set). k up to 7 days uses one fixed set of 1,439 tickets (docs/07 A8); 30 days uses the last-10 list
on 1,469. The gap is widest relative to the control in the final hours: that is the excess presence fraction in the
footer (a lower bound on the share of present codes that come from the ticket's fault, if the control is valid).

Inputs:  verification/outputs/assoc/as_recency.csv, as_item4.csv
Output:  viz/figures/as_02_recency.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_02_recency.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_02_recency.png'
LABELS = {0.5: '30 min', 1.0: '1 h', 2.0: '2 h', 6.0: '6 h', 24.0: '1 day', 168.0: '7 days', 720.0: '30 days'}


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    r = assoc.load('recency')
    t = r[r.curve == 'target'].sort_values('k')
    i4 = assoc.load('item4')
    epf = i4[i4.measure == 'excess presence fraction'].set_index('k')
    tight = i4[i4.measure.str.startswith('tightest')].iloc[0]
    for row in t.itertuples():
        style.check(f'as_02 share at k={row.k:g} = n_T / n', row.pT, row.n_T / row.n_pairs, 1e-12)
        if row.k in epf.index:
            style.check(f'as_02 excess fraction at k={row.k:g}', epf.loc[row.k, 'estimate'],
                        (row.pT - row.pC) / row.pT, 1e-9)
    style.check('as_02 shares never fall with k (ticket)', 1, int((np.diff(t.pT) >= 0).all()))
    first = t.iloc[0]
    title = (f'A ticket\'s own codes appear in its final 30 minutes for {first.pT:.0%} of tickets, against '
             f'{first.pC:.0%} of controls')

    fig, ax = style.figure(max(10.5, 0.12 * len(title) + 2 * style.MARGIN), 6.2)
    x = np.arange(len(t))
    ax.plot(x, 100 * t.pT, color=style.BLUE, lw=2, marker='o', ms=6, zorder=3)
    ax.plot(x, 100 * t.pC, color=style.GRAY, lw=2, marker='o', ms=6, zorder=2)
    for xi, a, b in zip(x, t.pT, t.pC):
        ax.text(xi, 100 * a + 2.5, f'{a:.0%}', ha='center', va='bottom', fontsize=9.5, color=style.INK)
        ax.text(xi, 100 * b - 3, f'{b:.0%}', ha='center', va='top', fontsize=9.5, color=style.INK2)
    ax.text(x[-1] + 0.15, 100 * t.pT.iloc[-1], 'Before the ticket', color=style.BLUE, va='center', fontsize=10)
    ax.text(x[-1] + 0.15, 100 * t.pC.iloc[-1], 'Control, 35 days earlier', color=style.INK2, va='center', fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels([LABELS[k] for k in t.k], color=style.INK2)
    ax.set_xlim(-0.4, len(t) + 1.4)
    ax.set_ylim(-8, 90)
    style.pct_axis(ax.yaxis)
    style.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel('Code set present within this long before the ticket (or the control\'s end)')
    ax.set_ylabel('Share of tickets')
    note_k = [0.5, 2.0, 24.0, 168.0]
    epf_txt = ', '.join(f'{LABELS[k]} {epf.loc[k, "estimate"]:.2f}' for k in note_k)
    style.frame(
        fig, title,
        f'Tickets whose Category points at a code set, on machine types that log it ({int(first.n_pairs):,} '
        f'tickets; 1,469 at 30 days). The signal is concentrated in the final hours: within 7 days the code set is '
        f'present before {t[t.k == 168].pT.iloc[0]:.0%} of tickets and in {t[t.k == 168].pC.iloc[0]:.0%} of '
        f'controls.',
        definitions=[assoc.TARGET_DEFINITION, assoc.CONTROL_DEFINITION],
        notes=[f'Excess presence fraction (pT - pC) / pT, a lower bound on the share of present codes that come from '
               f'the ticket\'s fault if the control is valid: {epf_txt}. Tightest bound over the windows up to 7 days: '
               f'{tight.estimate:.2f} (95% {tight.ci_lo:.2f} to {tight.ci_hi:.2f}).',
               'Up to 7 days the same 1,439 tickets are used at every point (docs/07 A8). Codes logged in the final '
               '30-60 minutes could include the caller retrying the machine; the 30- and 60-minute guard bands leave '
               'H2a at 1.14-1.21 on the log scale (as_sensitivities.csv).',
               assoc.source('recency', 'item4')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
