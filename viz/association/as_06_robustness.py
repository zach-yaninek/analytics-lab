#!/usr/bin/env python3
"""Association chart 6: the pooled specificity ratio under every sensitivity check that could be computed (7 days).

One row per pre-specified variant (docs/07 §6): the pooled H2a specificity ratio (exp of the log Mantel-Haenszel
ratio) with its 95% account-cluster bootstrap interval (machine clusters for S8), on a log axis, with the primary
analysis on top and a light line at its value. For the guard bands (S3) the control-side lower-bound variant is drawn
and the footer gives the upper-bound values. The footer also states the one secondary result whose interval reaches 1
(S4 at 30 days), the S6 caveat, and which sensitivities are pending or give no ratio.

Inputs:  verification/outputs/assoc/as_sensitivities.csv
Output:  viz/figures/as_06_robustness.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_06_robustness.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]
import numpy as np  # noqa: E402
from matplotlib.ticker import NullLocator  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_06_robustness.png'
VARIANTS = [  # (variant prefix in as_sensitivities.csv, label)
    ('primary', 'Primary analysis'),
    ('S1 planned', 'Planned, cancelled, duplicate put back (S1)'),
    ('S3 guard 0.5 h, control lower', 'Final 30 minutes dropped (S3)'),
    ('S3 guard 1 h, control lower', 'Final 60 minutes dropped (S3)'),
    ('S4 ', 'Ticket-free lead-in, from 11 Nov 2025 (S4)'),
    ('S5 recently', 'Recently activated machines dropped (S5)'),
    ('S5b', 'Machines installed 2025 or later dropped (S5)'),
    ('S6 ', 'Lookback-truncated windows included (S6)'),
    ('S7 undetermined pairs counted absent', 'Undetermined pairs counted absent (S7)'),
    ('S7 undetermined pairs counted present', 'Undetermined pairs counted present (S7)'),
    ('S8 ', 'Machine-level clusters (S8)'),
    ('S13 ', 'Deposit Door without codes 19, 78 (S13)'),
]


def row(s, prefix, k):
    m = s[s.variant.str.startswith(prefix) & (s.k == k)]
    assert len(m) == 1, (prefix, k, len(m))
    r = m.iloc[0]
    return float(r.h2a), float(r.h2a_lo), float(r.h2a_hi), int(r.n_pairs)


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    s = assoc.load('sensitivities')
    rows = [(lab,) + row(s, pre, assoc.K7) for pre, lab in VARIANTS]
    h2a = assoc.load('h2a')
    pooled = h2a[(h2a.k == assoc.K7) & (h2a.set == 'POOLED')].iloc[0]
    style.check('as_06 primary row = pooled H2a', pooled.estimate, rows[0][1], 1e-9)
    ratios = np.exp([r[1] for r in rows])
    los = np.exp([r[2] for r in rows])
    style.check('as_06 every interval above 1 at 7 days', 1, int((los > 1).all()))
    up = [row(s, p, assoc.K7)[0] for p in ('S3 guard 0.5 h, control upper', 'S3 guard 1 h, control upper')]
    s4 = row(s, 'S4 ', assoc.K30)
    style.check('as_06 S4 at 30 days reaches 1', 1, int(np.exp(s4[1]) < 1))
    title = (f'At 7 days the main result holds in all {len(rows) - 1} sensitivity variants run so far: the pooled '
             f'specificity ratio stays between {ratios.min():.1f}x and {ratios.max():.1f}x')

    n = len(rows)
    fig, ax = style.figure(max(11.0, 0.12 * len(title) + 2 * style.MARGIN), 3.4 + 0.42 * n)
    y = np.arange(n)[::-1]
    ax.axvline(1, color=style.INK2, lw=1, zorder=1)
    ax.axvline(ratios[0], color=style.GRAY_LIGHT, lw=1, zorder=1)
    for yi, (lab, est, lo, hi, npairs) in zip(y, rows):
        first = lab == rows[0][0]
        ax.hlines(yi, np.exp(lo), np.exp(hi), color=style.BLUE, lw=2, zorder=2)
        ax.scatter(np.exp(est), yi, s=70 if first else 50, color=style.BLUE, edgecolors=style.SURFACE,
                   linewidths=1.2, zorder=3, marker='D' if first else 'o')
        ax.text(np.exp(hi) * 1.06, yi, f'{np.exp(est):.1f}x  ({np.exp(lo):.1f} to {np.exp(hi):.1f}; {npairs:,} tickets)',
                va='center', ha='left', fontsize=9.5, color=style.INK, weight='bold' if first else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], color=style.INK2)
    ax.set_xscale('log')
    ax.set_xlim(0.9, 14)
    ax.set_xticks([1, 2, 4, 8])
    ax.set_xticklabels(['1', '2', '4', '8'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_ylim(-0.7, n - 0.3)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Pooled specificity ratio, final 7 days (log scale; 1 = no more specific than other faults)')
    style.frame(
        fig, title,
        f'H2a re-run under each pre-specified sensitivity check, final 7 days, with 95% intervals (bootstrap over '
        f'account clusters; machines for S8). The light line marks the primary result, {ratios[0]:.1f}x. Every '
        f'interval stays above 1.',
        definitions=[assoc.SENSITIVITY_DEFINITION, assoc.SPECIFICITY_DEFINITION, assoc.CONTROL_DEFINITION],
        notes=[f'Guard bands (S3): drawn with the control-side lower bound; the upper-bound variants give '
               f'{np.exp(up[0]):.2f}x and {np.exp(up[1]):.2f}x. Truncated windows (S6): most added pairs have a control '
               f'window with no events at all, so this mainly checks that empty controls do not reverse the result.',
               f'At 30 days (secondary) one check reaches 1: the ticket-free lead-in (S4) gives {np.exp(s4[0]):.2f}x '
               f'({np.exp(s4[1]):.2f} to {np.exp(s4[2]):.2f}). Pending: text-flag exclusions (S2), the interval-based '
               f'clean rule (S10) and crosswalk v1 (S12). S9 (ticket side only) and S11 (calendar drift) give no ratio.',
               assoc.source('sensitivities', 'h2a')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
