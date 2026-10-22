#!/usr/bin/env python3
"""Association chart 1: does a ticket's Category pick out its own codes? H2a per code set and pooled (7 days).

One row per code set that entered H2a, plus the pooled estimate on top: the specificity ratio (exp of the log
Mantel-Haenszel ratio in as_h2a.csv) with its 95% account-cluster bootstrap interval, on a log axis. A ratio of 1
means the set rises before its own tickets no more than before tickets for other faults. Blue = interval wholly
above 1; gray = includes 1. Sets that did not enter (too few discordant pairs, or a zero in the ratio) are named in
the footer with the reason, so that the strongest set left out by the entry rule (Packer, all discordant pairs one
way) is not hidden.

Inputs:  verification/outputs/assoc/as_h2a.csv, as_summary.json
Output:  viz/figures/as_01_specificity_by_set.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_01_specificity_by_set.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_01_specificity_by_set.png'
LO, HI = 0.15, 60.0


def fmt(x):
    return f'{x:.2f}' if x < 10 else f'{x:.1f}'


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    S = assoc.summary()
    h = assoc.load('h2a')
    h = h[h.k == assoc.K7]
    pooled = h[h.set == 'POOLED'].iloc[0]
    sets = h[h.set != 'POOLED'].copy()
    entered = sets[sets.entered == 1].copy()
    left_out = sets[sets.entered == 0]
    style.check('as_01 decision = pooled > 0 and p <= 0.05', int(S['decision']['h2a_success']),
                int(pooled.estimate > 0 and pooled.perm_p <= 0.05))
    style.check('as_01 pooled b_T = sum over entering sets', pooled.b_T, entered.b_T.sum())
    for c in ('estimate', 'ci_lo', 'ci_hi'):
        entered[c + '_x'] = np.exp(entered[c])
    entered = entered.sort_values('estimate', kind='mergesort')
    ratio, lo, hi, p = (float(np.exp(pooled.estimate)), float(np.exp(pooled.ci_lo)), float(np.exp(pooled.ci_hi)),
                        float(pooled.perm_p))
    style.check('as_01 pooled interval contains the estimate', 1, int(lo <= ratio <= hi))
    above = entered[entered.ci_lo > 0]
    mapped = S['pinned_counts']['A8 mapped 7d']
    md = entered[entered.categories == 'Main Door']
    title = (f'A ticket\'s own codes show up before it rather than in its control at {ratio:.1f}x the odds seen for '
             f'other faults\' tickets')

    rows = [(assoc.set_label(r.categories, r.set), r.estimate_x, r.ci_lo_x, r.ci_hi_x, r.ci_lo > 0)
            for r in entered.itertuples()]
    rows.append((f'Pooled over the {len(entered)} sets', ratio, lo, hi, True))
    n = len(rows)
    fig, ax = style.figure(max(11.0, 0.12 * len(title) + 2 * style.MARGIN), 3.6 + 0.42 * n)
    y = np.arange(n)
    ax.axvline(1, color=style.INK2, lw=1, zorder=1)
    for yi, (lab, est, l, u, hot) in zip(y, rows):
        col = style.BLUE if hot else style.GRAY
        ax.hlines(yi, assoc.x_of(l, LO, HI), assoc.x_of(u, LO, HI), color=col if hot else style.GRAY_LIGHT, lw=2)
        ax.scatter(assoc.x_of(est, LO, HI), yi, s=70 if yi == n - 1 else 50, color=col, edgecolors=style.SURFACE,
                   linewidths=1.2, zorder=3, marker='D' if yi == n - 1 else 'o')
        txt = f'{est:.1f}x  ({fmt(l)} to {"unbounded" if np.isinf(u) else fmt(u)})'
        ax.text(assoc.x_of(u, LO, HI) * 1.08, yi, txt, va='center', ha='left', fontsize=9.5,
                color=style.INK if hot else style.INK2, weight='bold' if yi == n - 1 else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], color=style.INK2)
    ax.set_xscale('log')
    ax.set_xlim(LO, HI * 4)
    ax.set_xticks([0.25, 0.5, 1, 2, 4, 8, 16, 32])
    ax.set_xticklabels(['0.25', '0.5', '1', '2', '4', '8', '16', '32'])
    ax.set_ylim(-0.7, n - 0.3)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Specificity ratio (log scale; 1 = no more specific than other faults)')

    reasons = []
    for r in left_out.itertuples():
        disc = int(r.b_T + r.c_T)
        if r.n_T == 0:
            why = 'no tickets on machine types that log these codes'
        elif disc < 10:
            why = f'{disc} discordant pairs (needs 10)'
        elif r.c_T == 0:
            why = (f'all {disc} discordant pairs point to the ticket window, so the ratio has a zero and is left '
                   f'out; including it would raise the pooled ratio')
        else:
            why = 'a zero in the comparator ratio'
        reasons.append(f'{r.categories} ({why})')
    style.check('as_01 every set accounted for', len(sets), len(entered) + len(left_out))
    style.frame(
        fig, title,
        f'H2a, the protocol\'s primary test, final 7 days: the {mapped:,} of 2,911 paired tickets whose Category has a '
        f'code set ({int(pooled.n_T):,} ticket-set combinations as targets), each against a clean control on the same '
        f'machine. Pooled specificity ratio {ratio:.1f}x (95% interval {lo:.1f} to {hi:.1f}); permutation p = {p:.4f} '
        f'(Category shuffled within machine type x quarter, 2,000 times), so H2a succeeds. {len(above)} of '
        f'{len(entered)} sets have intervals above 1 on their own'
        + (f'; Main Door only just (lower end {np.exp(md.ci_lo.iloc[0]):.2f}, permutation p {md.perm_p.iloc[0]:.2f})'
           if len(md) and md.ci_lo.iloc[0] > 0 else '') + '.',
        definitions=[assoc.SPECIFICITY_DEFINITION, assoc.TARGET_DEFINITION, assoc.CONTROL_DEFINITION],
        notes=['Not in the pooled test (entry rule, docs/07 §4): ' + '; '.join(reasons) + '.',
               '95% intervals: bootstrap over 610 account clusters. Per-set results are descriptive; only the pooled '
               'test decides H2a.',
               assoc.source('h2a')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
