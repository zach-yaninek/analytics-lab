#!/usr/bin/env python3
"""Association chart 8: code rises before tickets that recorded no fault, and before repeat tickets (descriptive).

Dumbbells (control share, ticket share; final 7 days) for door codes before No Trouble Found tickets and before
cancelled requests, and for electronics codes before the 157 tickets left out because another ticket came in the 5
days before them, each under its all-ticket reference row. Descriptive breakdown rows with unadjusted p-values; the
footer gives the caveats docs/08 §4 states.

Inputs:  verification/outputs/assoc/as_item2_buckets.csv, as_item2_breakdowns.csv, as_sensitivities.csv (S1 Cancelled
         request row)
Output:  viz/figures/as_08_breakdowns.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_08_breakdowns.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_08_breakdowns.png'
DOOR, ELEC = 'Door issue', 'Electronics/software/comms'


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    b = assoc.load('item2_buckets')
    b = b[b.k == assoc.K7].set_index('outcome')
    br = assoc.load('item2_breakdowns')
    ntf30 = br[(br.k == assoc.K30) & (br.level == 'category') & (br.group == 'No Trouble Found')
               & (br.outcome == DOOR)].iloc[0]
    br = br[br.k == assoc.K7]
    ntf = br[(br.level == 'category') & (br.group == 'No Trouble Found') & (br.outcome == DOOR)].iloc[0]
    rep = br[(br.level == 'excluded157') & (br.outcome == ELEC)].iloc[0]
    s = assoc.load('sensitivities')
    can = s[(s.variant == 'S1 Cancelled request only') & (s.k == assoc.K7)].iloc[0]
    rows = [  # label, pT, pC, OR, n, reference row?
        ('Door codes: all tickets', b.loc[DOOR].pT, b.loc[DOOR].pC, b.loc[DOOR].mor, int(b.loc[DOOR].n_pairs), True),
        ('Door codes: No Trouble Found', ntf.pT, ntf.pC, ntf.mor, int(ntf.n_pairs), False),
        ('Door codes: cancelled requests', can[f'bucket:{DOOR}:pT'], can[f'bucket:{DOOR}:pC'],
         can[f'bucket:{DOOR}:mor'], int(can.n_pairs), False),
        ('Electronics codes: all tickets', b.loc[ELEC].pT, b.loc[ELEC].pC, b.loc[ELEC].mor, int(b.loc[ELEC].n_pairs),
         True),
        ('Electronics codes: repeat tickets', rep.pT, rep.pC, rep.mor, int(rep.n_pairs), False),
    ]
    style.check('as_08 NTF OR = b / c', ntf.mor, ntf.b / ntf.c, 1e-9)
    style.check('as_08 repeat OR = b / c', rep.mor, rep.b / rep.c, 1e-9)
    style.check('as_08 repeat tickets after A8 and the span rule', 146, int(rep.n_pairs))
    style.check('as_08 cancelled pairs at 7 days', 89, int(can.n_pairs))
    rise = {lab: (pt - pc) * 100 for lab, pt, pc, *_ in rows}
    title = (f'Door codes rise before No Trouble Found and cancelled tickets about as much as before all tickets '
             f'(+{rise[rows[1][0]]:.1f} and +{rise[rows[2][0]]:.1f} points, against +{rise[rows[0][0]]:.1f})')

    n = len(rows)
    fig, ax = style.figure(max(11.0, 0.12 * len(title) + 2 * style.MARGIN), 3.4 + 0.55 * n)
    y = np.arange(n)[::-1].astype(float)
    y[3:] -= 0.4  # a gap between the door and electronics groups
    for yi, (lab, pt, pc, mor, npairs, ref) in zip(y, rows):
        col = style.GRAY if ref else style.BLUE
        ax.hlines(yi, pc * 100, pt * 100, color=style.GRAY_LIGHT if ref else style.BLUE, lw=2, zorder=1)
        ax.scatter(pc * 100, yi, s=55, color=style.GRAY, edgecolors=style.SURFACE, linewidths=1.2, zorder=2)
        ax.scatter(pt * 100, yi, s=55, color=col, edgecolors=style.SURFACE, linewidths=1.2, zorder=3)
        ax.text(66, yi, f'{pt:.1%} vs {pc:.1%}   OR {mor:.1f}   ({npairs:,} tickets)', va='center', ha='left',
                fontsize=9.5, color=style.INK2 if ref else style.INK)
    ax.text(rows[0][1] * 100, y[0] + 0.45, 'Before the ticket', color=style.INK2, ha='center', va='bottom',
            fontsize=9.5)
    ax.text(rows[0][2] * 100, y[0] + 0.45, 'Control', color=style.INK2, ha='center', va='bottom', fontsize=9.5)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], color=style.INK2)
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 20, 40, 60])
    style.pct_axis(ax.xaxis)
    ax.set_ylim(y.min() - 0.6, y.max() + 0.9)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Share of windows with a code of the bucket in the final 7 days')
    style.frame(
        fig, title,
        'Descriptive breakdowns, final 7 days (unadjusted). No Trouble Found and cancelled tickets show the door-code '
        'rise seen before tickets in general; the repeat tickets left out of the primary population show a steep '
        'electronics rise.',
        definitions=[assoc.BUCKET_DEFINITION, assoc.MOR_DEFINITION, assoc.CONTROL_DEFINITION],
        notes=['Door codes fit both readings of No Trouble Found: a door left open or blocked that was not a fault, or '
               'an intermittent fault the technician could not reproduce. Which applies is an IPA question. At 30 days '
               f'there is no clear No Trouble Found door difference ({ntf30.pT:.1%} vs {ntf30.pC:.1%}); the '
               f'cancelled row is small.',
               'Repeat tickets: the 157 tickets left out because another ticket on the machine opened in the 5 days '
               'before them (146 with a determinable 7-day window). Their window contains the earlier ticket and '
               'possibly its service visit, so their codes may come from the earlier fault or its repair as much as '
               'from the new call.',
               assoc.source('item2_buckets', 'item2_breakdowns', 'sensitivities')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
