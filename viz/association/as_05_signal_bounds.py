#!/usr/bin/env python3
"""Association chart 5: how much of the code signal is owed to whatever led to the ticket (item 4).

On one base, the tickets with their own code set in the final 7 days (1,439 tickets on machine types that log their
set), the share with an own code in the final k hours that the control says would not otherwise be there:
(pT(k) - pC(k)) / pT(7 days), for k = 30 minutes to 7 days (blue). Its maximum is the protocol's "tightest lower
bound" (0.49 at 6 hours, with its 95% interval). The gray line is the same measure for codes of unrelated sets on the
same tickets (exploratory, added after unblinding): how much of the blue line is generic activity before any ticket.
The bracket on the right gives the whole-week bounds (lower 0.27 with its interval, upper 0.73).

Inputs:  verification/outputs/assoc/as_item4.csv
Output:  viz/figures/as_05_signal_bounds.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_05_signal_bounds.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_05_signal_bounds.png'
LABELS = {0.5: '30 min', 1.0: '1 h', 2.0: '2 h', 6.0: '6 h', 24.0: '1 day', 168.0: '7 days'}


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    i4 = assoc.load('item4')
    own = i4[(i4.measure == 'excess presence fraction') & (i4.k <= assoc.K7)].sort_values('k')
    unr = i4[i4.measure == 'exploratory: excess presence fraction, unrelated sets'].sort_values('k')
    tight = i4[i4.measure.str.startswith('tightest lower bound')].iloc[0]
    tight_u = i4[i4.measure == 'exploratory: tightest bound, unrelated sets'].iloc[0]
    week = own[own.k == assoc.K7].iloc[0]
    style.check('as_05 same k grid for both lines', 1, int(list(own.k) == list(unr.k)))
    y_own = ((own.pT - own.pC) / week.pT).to_numpy()
    y_unr = ((unr.pT - unr.pC) / unr[unr.k == assoc.K7].pT.iloc[0]).to_numpy()
    j = int(np.argmax(y_own))
    style.check('as_05 own-set maximum = tightest lower bound', tight.estimate, y_own[j], 1e-9)
    style.check('as_05 own-set maximum at the tightest bound\'s k', tight.k, own.k.iloc[j], 1e-9)
    style.check('as_05 unrelated maximum = exploratory tightest bound', tight_u.estimate, y_unr.max(), 1e-9)
    style.check('as_05 week lower bound = (pT - pC) / pT at 7 days', week.estimate, y_own[-1], 1e-9)
    style.check('as_05 week upper bound = (1 - pC) / pT', week.upper_bound, min(1, (1 - week.pC) / week.pT), 1e-9)
    title = (f'For {tight.estimate:.0%} of tickets with their own codes, the final {LABELS[tight.k]} hold one that '
             f'would not otherwise be there; for unrelated codes, {tight_u.estimate:.0%}')

    fig, ax = style.figure(max(10.5, 0.12 * len(title) + 2 * style.MARGIN), 6.2)
    x = np.arange(len(own))
    ax.plot(x, 100 * y_own, color=style.BLUE, lw=2, marker='o', ms=6, zorder=3)
    ax.plot(x, 100 * y_unr, color=style.GRAY, lw=2, marker='o', ms=6, zorder=2)
    ax.vlines(x[j], 100 * tight.ci_lo, 100 * tight.ci_hi, color=style.BLUE, lw=2, zorder=3)
    for xi, a in zip(x, y_own):
        ax.text(xi, 100 * a + 2.5, f'{a:.0%}', ha='center', va='bottom', fontsize=9.5,
                color=style.INK, weight='bold' if xi == x[j] else 'normal')
    for xi, a in zip(x, y_unr):
        ax.text(xi, 100 * a - 2.5, f'{a:.0%}', ha='center', va='top', fontsize=9.5, color=style.INK2)
    ax.text(x[-1] + 0.15, 100 * y_own[-1], 'Own code set', color=style.BLUE, ha='left', va='center', fontsize=10)
    ax.text(x[-1] + 0.15, 100 * y_unr[-1], 'Unrelated code sets\n(exploratory)', color=style.INK2, ha='left',
            va='center', fontsize=10)
    # whole-week bounds as a bracket to the right
    xb = len(own) + 0.9
    ax.vlines(xb, 100 * week.estimate, 100 * week.upper_bound, color=style.INK2, lw=2)
    ax.hlines([100 * week.estimate, 100 * week.upper_bound], xb - 0.1, xb + 0.1, color=style.INK2, lw=2)
    ax.text(xb + 0.2, 100 * week.upper_bound, f'{week.upper_bound:.0%} upper bound', va='center', fontsize=9.5,
            color=style.INK2)
    ax.text(xb + 0.2, 100 * week.estimate,
            f'{week.estimate:.0%} lower bound\n(95% {week.ci_lo:.0%} to {week.ci_hi:.0%})', va='center', fontsize=9.5,
            color=style.INK2)
    ax.text(xb, 100 * week.upper_bound + 6, 'Whole week: no own\ncode all week\nwithout it', ha='center', va='bottom',
            fontsize=9.5, color=style.INK2)
    ax.set_xticks(list(x) + [xb])
    ax.set_xticklabels([LABELS[k] for k in own.k] + ['bounds'], color=style.INK2)
    ax.set_xlim(-0.5, xb + 2.2)
    ax.set_ylim(0, 100)
    style.pct_axis(ax.yaxis)
    style.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel('Final span before the ticket')
    ax.set_ylabel('Share of tickets with own codes in 7 days')
    style.frame(
        fig, title,
        f'Base: the {int(week.n_pairs):,} tickets whose Category has a code set their machine type logs, counting those '
        f'with an own code in the final 7 days ({week.pT:.0%} of them). The blue line peaks at {LABELS[tight.k]} '
        f'({tight.estimate:.0%}, 95% {tight.ci_lo:.0%} to {tight.ci_hi:.0%}); the gray line shows how much of it any '
        f'code set would show before a ticket. Over the whole week, between {week.estimate:.0%} and '
        f'{week.upper_bound:.0%} of these tickets would have had no own code at all without whatever led to the ticket.',
        definitions=[assoc.OWED_DEFINITION, assoc.TARGET_DEFINITION, assoc.RECENCY_CONTROL_DEFINITION],
        notes=['The peak is the best of six windows, which makes it slightly optimistic. Bounds, not estimates: both '
               'assume the control is a fair stand-in, and docs/07 A3 lists two ways it may not be, pushing in '
               'opposite directions. Whether the codes match the Category is H2a (chart as_01).',
               assoc.source('item4')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
