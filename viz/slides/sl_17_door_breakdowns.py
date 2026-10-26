#!/usr/bin/env python3
"""Slide chart 17: door codes before No Trouble Found and cancelled tickets (descriptive, final 7 days).

The slide version of the door rows of viz/association/as_08_breakdowns.py: share of tickets with a door code in the
final 7 days before the ticket (dot) against the control (ring), for all 2,911 primary tickets (gray reference), the
209 No Trouble Found tickets and the 89 cancelled requests (S1's separate row). Unadjusted, descriptive rows.

Input:  verification/outputs/assoc/as_item2_buckets.csv, as_item2_breakdowns.csv, as_sensitivities.csv
Output: viz/figures/slides/sl_17_door_breakdowns.png (half card)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'association')]
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import deck_style as S  # noqa: E402

PNG = 'sl_17_door_breakdowns.png'
DOOR = 'Door issue'


def plot(out_dir=S.FIG_DIR):
    b = assoc.load('item2_buckets')
    allt = b[(b.k == assoc.K7) & (b.outcome == DOOR)].iloc[0]
    br = assoc.load('item2_breakdowns')
    ntf = br[(br.k == assoc.K7) & (br.level == 'category') & (br.group == 'No Trouble Found')
             & (br.outcome == DOOR)].iloc[0]
    s = assoc.load('sensitivities')
    can = s[(s.variant == 'S1 Cancelled request only') & (s.k == assoc.K7)].iloc[0]
    rows = [('All tickets', allt.pT, allt.pC, int(allt.n_pairs), True),
            ('No Trouble Found', ntf.pT, ntf.pC, int(ntf.n_pairs), False),
            ('Cancelled requests', can[f'bucket:{DOOR}:pT'], can[f'bucket:{DOOR}:pC'], int(can.n_pairs), False)]
    S.check('sl_17 all tickets 54.1% vs 42.6%, 2,911', 54.1 + 42.6 / 1000 + 2911 / 1e7,
            round(allt.pT * 100, 1) + round(allt.pC * 100, 1) / 1000 + int(allt.n_pairs) / 1e7, 1e-9)
    S.check('sl_17 NTF 44.0% vs 32.5%, 209', 44.0 + 32.5 / 1000 + 209 / 1e7,
            round(ntf.pT * 100, 1) + round(ntf.pC * 100, 1) / 1000 + int(ntf.n_pairs) / 1e7, 1e-9)
    S.check('sl_17 cancelled 58.4% vs 44.9%, 89', 58.4 + 44.9 / 1000 + 89 / 1e7,
            round(can[f'bucket:{DOOR}:pT'] * 100, 1) + round(can[f'bucket:{DOOR}:pC'] * 100, 1) / 1000
            + int(can.n_pairs) / 1e7, 1e-9)

    fig, ax = S.figure(S.HALF)
    y = np.arange(len(rows))[::-1].astype(float)
    y[0] += 0.3  # the reference row apart
    for yi, (label, pt, pc, n, ref) in zip(y, rows):
        col = S.GRAY if ref else S.BLUE
        ax.hlines(yi, 100 * pc, 100 * pt, color=S.GRAY_LIGHT if ref else S.BLUE, lw=4, zorder=1)
        ax.scatter(100 * pc, yi, s=150, facecolors=S.WHITE, edgecolors=S.GRAY, linewidths=2.4, zorder=2)
        ax.scatter(100 * pt, yi, s=150, color=col, edgecolors=S.WHITE, linewidths=1.2, zorder=3)
        ax.text(100 * pt + 2.2, yi, f'+{100 * (pt - pc):.1f} pts', va='center', ha='left', fontsize=S.FONT,
                color=S.INK2 if ref else S.INK, weight='normal' if ref else 'bold')
        ax.text(100 * pc - 2.2, yi, f'{100 * pc:.0f}% → {100 * pt:.0f}%', va='center', ha='right',
                fontsize=S.SMALL, color=S.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([f'{r[0]}\n({r[3]:,} tickets)' for r in rows], fontsize=S.SMALL, color=S.INK)
    ax.set_xlim(10, 80)
    ax.set_xticks([20, 40, 60, 80])
    S.pct_axis(ax.xaxis)
    ax.set_ylim(-0.6, y[0] + 0.6)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Share with a door code in the final 7 days (ring: control)')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
