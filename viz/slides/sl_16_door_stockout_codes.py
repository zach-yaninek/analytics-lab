#!/usr/bin/env python3
"""Slide chart 16: door and stock-out codes before service tickets (association item 2, final 7 days).

The slide version of viz/association/as_04_bucket_enrichment.py: for each of the team's provisional code buckets, the
share of the 2,911 primary tickets with a code of the bucket in the final 7 days before the ticket (dot) against the
same machine's control window (ring). Door codes in blue (they rise); stock-out codes in navy (the pre-specified
negative control: no rise); the other buckets in gray as context.

Input:  verification/outputs/assoc/as_item2_buckets.csv
Output: viz/figures/slides/sl_16_door_stockout_codes.png (half card)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'association')]
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import deck_style as S  # noqa: E402

PNG = 'sl_16_door_stockout_codes.png'
ROWS = [('Door issue', 'Door', S.BLUE), ('Stock-out', 'Stock-out', S.NAVY),
        ('Electronics/software/comms', 'Electronics', S.GRAY), ('Mechanical fault', 'Mechanical', S.GRAY),
        ('Operational status', 'Operational', S.GRAY), ('User behavior', 'User behavior', S.GRAY),
        ('Incomplete transaction', 'Incomplete', S.GRAY)]


def plot(out_dir=S.FIG_DIR):
    b = assoc.load('item2_buckets')
    b = b[b.k == assoc.K7].set_index('outcome')
    for key, _, _ in ROWS:
        r = b.loc[key]
        S.check(f'sl_16 {key}: pT = n_T / n', r.pT, r.n_T / r.n_pairs, 1e-12)
    door, stock = b.loc['Door issue'], b.loc['Stock-out']
    S.check('sl_16 door 54% vs 43%', 54 + 43 / 100, round(door.pT * 100) + round(door.pC * 100) / 100, 1e-9)
    S.check('sl_16 door enriched (b > c, BH q <= 0.05)', 1, int(door.b > door.c and door.bh_q <= 0.05))
    S.check('sl_16 stock-out 39% vs 40%', 39 + 40 / 100, round(stock.pT * 100) + round(stock.pC * 100) / 100, 1e-9)
    S.check('sl_16 stock-out not enriched (BH q > 0.05)', 1, int(stock.bh_q > 0.05))
    S.check('sl_16 2,911 primary tickets', 2911, int(door.n_pairs))

    fig, ax = S.figure(S.HALF)
    y = np.arange(len(ROWS))[::-1].astype(float)
    y[:2] += 0.35  # set the two buckets the slide is about apart from the context rows
    for yi, (key, label, col) in zip(y, ROWS):
        r = b.loc[key]
        pt, pc = 100 * r.pT, 100 * r.pC
        ax.hlines(yi, min(pt, pc), max(pt, pc), color=col if col != S.GRAY else S.GRAY_LIGHT, lw=3, zorder=1)
        ax.scatter(pc, yi, s=110, facecolors=S.WHITE, edgecolors=S.GRAY, linewidths=2.2, zorder=2)
        ax.scatter(pt, yi, s=110, color=col, edgecolors=S.WHITE, linewidths=1.2, zorder=3)
        ax.text(66, yi, f'{pt:.0f}% vs {pc:.0f}%', va='center', ha='left', fontsize=S.FONT,
                color=S.INK if col != S.GRAY else S.INK2, weight='bold' if col != S.GRAY else 'normal')
    ax.text(100 * door.pT, y[0] + 0.42, 'Before the ticket', ha='left', va='bottom', fontsize=S.SMALL, color=S.BLUE)
    ax.text(100 * door.pC, y[0] + 0.42, 'Control', ha='right', va='bottom', fontsize=S.SMALL, color=S.INK2)
    ax.text(100 * stock.pT, y[1] - 0.42, 'negative control: no rise', ha='center', va='top', fontsize=S.SMALL,
            color=S.NAVY)
    ax.set_yticks(y)
    ax.set_yticklabels([r[1] for r in ROWS], fontsize=S.FONT, color=S.INK)
    for t in ax.get_yticklabels()[:2]:
        t.set_fontweight('bold')
    ax.set_xlim(0, 84)
    ax.set_xticks([0, 20, 40, 60])
    S.pct_axis(ax.xaxis)
    ax.set_ylim(-0.6, y[0] + 1.0)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Share of tickets with a code of the bucket, final 7 days')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
