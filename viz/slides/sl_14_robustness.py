#!/usr/bin/env python3
"""Slide chart 14: the pooled specificity ratio under each sensitivity check (final 7 days).

The slide version of viz/association/as_06_robustness.py: the primary analysis and the 11 drawn variants with their
95% intervals (account-cluster bootstrap; machine clusters for S8), log axis, line at 1. The two S3 control-side
upper-bound variants are not drawn (as on the page chart); both lie inside the drawn range with intervals above 1.

Input:  verification/outputs/assoc/as_sensitivities.csv, as_h2a.csv
Output: viz/figures/slides/sl_14_robustness.png (half card)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'association')]
import numpy as np  # noqa: E402
from matplotlib.ticker import NullLocator  # noqa: E402

import assoc  # noqa: E402
import deck_style as S  # noqa: E402

PNG = 'sl_14_robustness.png'
VARIANTS = [  # (variant prefix in as_sensitivities.csv, short label), as in as_06
    ('primary', 'Primary analysis'),
    ('S1 planned', 'Planned/cancelled put back'),
    ('S3 guard 0.5 h, control lower', 'Final 30 min dropped'),
    ('S3 guard 1 h, control lower', 'Final 60 min dropped'),
    ('S4 ', 'Ticket-free lead-in'),
    ('S5 recently', 'Recently activated dropped'),
    ('S5b', 'Installed 2025+ dropped'),
    ('S6 ', 'Truncated windows added'),
    ('S7 undetermined pairs counted absent', 'Undetermined = absent'),
    ('S7 undetermined pairs counted present', 'Undetermined = present'),
    ('S8 ', 'Machine-level clusters'),
    ('S13 ', 'Deposit Door w/o 19, 78'),
]


def row(s, prefix):
    m = s[s.variant.str.startswith(prefix) & (s.k == assoc.K7)]
    assert len(m) == 1, (prefix, len(m))
    r = m.iloc[0]
    return float(np.exp(r.h2a)), float(np.exp(r.h2a_lo)), float(np.exp(r.h2a_hi))


def plot(out_dir=S.FIG_DIR):
    s = assoc.load('sensitivities')
    rows = [(lab,) + row(s, pre) for pre, lab in VARIANTS]
    est = np.array([r[1] for r in rows])
    los = np.array([r[2] for r in rows])
    h = assoc.load('h2a')
    pooled = h[(h.k == assoc.K7) & (h.set == 'POOLED')].iloc[0]
    S.check('sl_14 primary = pooled H2a', float(np.exp(pooled.estimate)), rows[0][1], 1e-9)
    S.check('sl_14 every interval above 1', 1, int((los > 1).all()))
    S.check('sl_14 range 2.3x to 3.5x', 2.3 + 3.5 / 10, round(est.min(), 1) + round(est.max(), 1) / 10, 1e-9)
    ran = s[(s.k == assoc.K7) & s.h2a.notna() & (s.variant != 'primary')]
    S.check('sl_14 undrawn variants inside the drawn range and above 1', 1,
            int(est.min() <= np.exp(ran.h2a).min() and np.exp(ran.h2a).max() <= est.max()
                and (np.exp(ran.h2a_lo) > 1).all()))

    fig, ax = S.figure(S.HALF)
    n = len(rows)
    y = np.arange(n)[::-1]
    ax.axvline(1, color=S.INK2, lw=1.4, zorder=1)
    ax.axvline(rows[0][1], color=S.GRAY_LIGHT, lw=1.2, zorder=1)
    for yi, (lab, e, lo, hi) in zip(y, rows):
        first = yi == n - 1
        ax.hlines(yi, lo, hi, color=S.BLUE, lw=3, zorder=2)
        ax.scatter(e, yi, s=150 if first else 80, color=S.BLUE, marker='D' if first else 'o', edgecolors=S.WHITE,
                   linewidths=1.2, zorder=3)
        ax.text(hi * 1.06, yi, f'{e:.1f}x', va='center', ha='left', fontsize=S.SMALL,
                color=S.INK, weight='bold' if first else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=S.SMALL, color=S.INK)
    ax.get_yticklabels()[0].set_fontweight('bold')
    ax.set_xscale('log')
    ax.set_xlim(0.9, 9)
    ax.set_xticks([1, 2, 4, 8])
    ax.set_xticklabels(['1', '2', '4', '8'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_ylim(-0.7, n - 0.3)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Pooled specificity ratio, 7 days (log scale)')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
