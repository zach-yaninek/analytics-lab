#!/usr/bin/env python3
"""Slide chart 12: does a ticket's Category pick out its own codes? H2a per code set and pooled (final 7 days).

The slide version of viz/association/as_01_specificity_by_set.py: the pooled specificity ratio (exp of the log
Mantel-Haenszel ratio) on top, then each code set that entered H2a, with 95% account-cluster bootstrap intervals on a
log axis. Blue where the interval is wholly above 1, gray otherwise. Sets left out by the entry rule (Packer and four
small sets) are named in the speaker notes, as on the page chart's footer.

Input:  verification/outputs/assoc/as_h2a.csv, as_summary.json
Output: viz/figures/slides/sl_12_specificity.png (wide card)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'association')]
import numpy as np  # noqa: E402
from matplotlib.ticker import NullLocator  # noqa: E402

import assoc  # noqa: E402
import deck_style as S  # noqa: E402

PNG = 'sl_12_specificity.png'
NAMES = {'SAM': 'SAM', 'User Door': 'User Door', 'Deposit Door': 'Deposit Door', 'Main Door': 'Main Door',
         'Computer Board': 'Computer Board'}


def plot(out_dir=S.FIG_DIR):
    h = assoc.load('h2a')
    h = h[h.k == assoc.K7]
    pooled = h[h.set == 'POOLED'].iloc[0]
    sets = h[(h.set != 'POOLED') & (h.entered == 1)].sort_values('estimate', ascending=False)
    rows = [('Pooled, 5 code sets', pooled)] + [(NAMES[r.categories], r) for r in sets.itertuples()]
    S.check('sl_12 pooled ratio 3.2x', 3.2, round(float(np.exp(pooled.estimate)), 1))
    S.check('sl_12 pooled interval 2.3 to 4.8', 2.3, round(float(np.exp(pooled.ci_lo)), 1))
    S.check('sl_12 pooled interval upper 4.8', 4.8, round(float(np.exp(pooled.ci_hi)), 1))
    S.check('sl_12 five sets entered', 5, len(sets))
    S.check('sl_12 H2a decision = success', 1, int(assoc.summary()['decision']['h2a_success']))

    fig, ax = S.figure(S.WIDE)
    n = len(rows)
    y = np.arange(n)[::-1].astype(float)
    y[0] += 0.35  # set the pooled row apart
    ax.axvline(1, color=S.INK2, lw=1.4, zorder=1)
    for yi, (lab, r) in zip(y, rows):
        est, lo, hi = (float(np.exp(getattr(r, c))) for c in ('estimate', 'ci_lo', 'ci_hi'))
        hot = lo > 1
        first = lab.startswith('Pooled')
        col = S.BLUE if hot else S.GRAY
        ax.hlines(yi, lo, hi, color=col if hot else S.GRAY_LIGHT, lw=4 if first else 3, zorder=2)
        ax.scatter(est, yi, s=200 if first else 120, color=col, marker='D' if first else 'o', edgecolors=S.WHITE,
                   linewidths=1.5, zorder=3)
        note = ''
        if lab == 'Main Door':
            note = '  borderline'
        elif lab == 'Computer Board':
            note = '  includes 1'
        ax.text(hi * 1.1, yi, f'{est:.1f}x  ({lo:.2f} to {hi:.1f}){note}' if lo < 1.1 else
                f'{est:.1f}x  ({lo:.1f} to {hi:.1f}){note}', va='center', ha='left', fontsize=S.FONT,
                color=S.INK if hot else S.INK2, weight='bold' if first else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=S.FONT, color=S.INK)
    ax.get_yticklabels()[0].set_fontweight('bold')
    ax.set_xscale('log')
    ax.set_xlim(0.15, 400)
    ax.set_xticks([0.25, 0.5, 1, 2, 4, 8, 16, 32])
    ax.set_xticklabels(['0.25', '0.5', '1', '2', '4', '8', '16', '32'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_ylim(-0.6, y[0] + 0.6)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Specificity ratio (log scale; 1 = no more specific than other faults)')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
