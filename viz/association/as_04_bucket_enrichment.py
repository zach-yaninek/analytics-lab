#!/usr/bin/env python3
"""Association chart 4: which kinds of code rise before tickets (item 2, final 7 days).

One row per team bucket (Undefined and Malformed left out) plus "any code" as context: the share of control windows
(gray dot) and of ticket windows (blue dot if the bucket is enriched, i.e. b > c and BH q <= 0.05; gray otherwise)
with a code of the bucket in the final 7 days, on the 2,911 primary pairs. The label gives the matched odds ratio
with its 95% machine-cluster interval. Stock-out is the pre-specified negative control: the footer gives its
negative-control row (tickets whose own set has neither stock-out code; account clusters) at 7 and 30 days.

Inputs:  verification/outputs/assoc/as_item2_buckets.csv, as_negative_controls.csv
Output:  viz/figures/as_04_bucket_enrichment.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_04_bucket_enrichment.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_04_bucket_enrichment.png'
ROWS = ['Electronics/software/comms', 'Door issue', 'Operational status', 'Mechanical fault', 'Incomplete transaction',
        'User behavior', 'Stock-out', 'any code']


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    b = assoc.load('item2_buckets')
    b = b[b.k == assoc.K7].set_index('outcome')
    neg = assoc.load('negative_controls')
    neg = neg[neg.control.str.startswith('Stock-out')].set_index('k')
    for o in ROWS:
        r = b.loc[o]
        style.check(f'as_04 {o}: pT = n_T / n', r.pT, r.n_T / r.n_pairs, 1e-12)
        style.check(f'as_04 {o}: OR = b / c', r.mor, r.b / r.c, 1e-9)
    style.check('as_04 one pair count for every row', 1, int(b.loc[ROWS].n_pairs.nunique() == 1))
    enriched = {o: bool(b.loc[o].bh_q <= 0.05 and b.loc[o].b > b.loc[o].c) for o in ROWS[:-1]}
    e = b.loc['Electronics/software/comms']
    s7 = neg.loc[assoc.K7]
    title = (f'Electronics codes appear before {e.pT:.0%} of tickets against {e.pC:.0%} of controls; stock-out codes, '
             f'the negative control, do not rise')

    rows = ROWS[::-1]  # top to bottom as listed
    n = len(rows)
    fig, ax = style.figure(max(11.0, 0.12 * len(title) + 2 * style.MARGIN), 3.6 + 0.48 * n)
    y = np.arange(n)
    for yi, o in zip(y, rows):
        r = b.loc[o]
        hot = enriched.get(o, False)
        ax.hlines(yi, min(r.pC, r.pT) * 100, max(r.pC, r.pT) * 100, color=style.BLUE if hot else style.GRAY_LIGHT,
                  lw=2, zorder=1)
        ax.scatter(r.pC * 100, yi, s=55, color=style.GRAY, edgecolors=style.SURFACE, linewidths=1.2, zorder=2)
        ax.scatter(r.pT * 100, yi, s=55, color=style.BLUE if hot else style.GRAY, edgecolors=style.SURFACE,
                   linewidths=1.2, zorder=3)
        if o == 'Stock-out':
            note = '  negative control'
        elif o == 'any code':
            note = '  context'
        elif o == 'User behavior' and r.b < r.c:
            note = '  falls'
        else:
            note = ''
        ax.text(102, yi, f'{r.pT:.0%} vs {r.pC:.0%}   OR {r.mor:.2f} ({r.mor_lo:.2f} to {r.mor_hi:.2f}){note}',
                va='center', ha='left', fontsize=9.5, color=style.INK if hot else style.INK2)
    d = b.loc['Door issue']  # widest gap: header the two columns there
    yd = n - 1 - ROWS.index('Door issue')
    ax.text(d.pT * 100 + 1, yd + 0.32, 'Before the ticket', color=style.BLUE, ha='left', va='bottom', fontsize=9.5)
    ax.text(d.pC * 100 - 1, yd + 0.32, 'Control', color=style.INK2, ha='right', va='bottom', fontsize=9.5)
    ax.set_yticks(y)
    ax.set_yticklabels(rows, color=style.INK2)
    ax.set_xlim(0, 160)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    style.pct_axis(ax.xaxis)
    ax.set_ylim(-0.6, n + 0.1)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Share of windows with a code of the bucket in the final 7 days')
    s30 = neg.loc[assoc.K30]
    style.frame(
        fig, title,
        f'Each bucket on the {int(e.n_pairs):,} primary tickets: control (gray) and ticket window (blue where the '
        f'bucket is clearly more common before tickets: more tickets with it only before the ticket than only in '
        f'the control, BH q <= 0.05). Matched odds ratios with 95% intervals (bootstrap over machines).',
        definitions=[assoc.BUCKET_DEFINITION, assoc.NEGATIVE_CONTROL_DEFINITION, assoc.MOR_DEFINITION,
                     assoc.CONTROL_DEFINITION],
        notes=[f'Negative-control row (tickets whose Category points at neither stock-out code, account clusters): '
               f'{s7.pT:.1%} vs {s7.pC:.1%} at 7 days, OR {s7.mor:.2f} ({s7.mor_lo:.2f} to {s7.mor_hi:.2f}); at 30 '
               f'days {s30.pT:.1%} vs {s30.pC:.1%}, OR {s30.mor:.2f} ({s30.mor_lo:.2f} to {s30.mor_hi:.2f}), so the '
               f'30-day window picks up generic differences between the two periods that 7 days does not.',
               'Not a blind result: these bucket shares were seen while the protocol was planned (docs/07 §10). Buckets '
               'cut across components, so the test of whether a Category picks out its own codes is chart as_01.',
               assoc.source('item2_buckets', 'negative_controls')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
