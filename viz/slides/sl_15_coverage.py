#!/usr/bin/env python3
"""Slide chart 15: which tickets the Category results can speak to (a funnel).

The slide version of viz/association/as_07_coverage.py: of the 2,911 primary tickets used at 7 days, those whose
Category has a code set (crosswalk v0), those on machine types that log that set (docs/07 A10; the base of H1 and of
every per-set result), and those of them on scrubex machines.

Input:  verification/outputs/assoc/as_pairs.csv, as_sets.csv, as_by_type.csv, as_summary.json
Output: viz/figures/slides/sl_15_coverage.png (half card)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'association')]
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import assoc  # noqa: E402
import deck_style as S  # noqa: E402

PNG = 'sl_15_coverage.png'


def plot(out_dir=S.FIG_DIR):
    p = pd.read_csv(assoc.ASSOC / 'as_pairs.csv', dtype=str, keep_default_na=False)
    p = p[(p.in_primary == '1') & (p.determined_7d == '1')]
    pins = assoc.summary()['pinned_counts']
    sets = assoc.load('sets')
    bt = assoc.load('by_type')
    bt = bt[(bt.k == assoc.K7) & (bt.set == 'own set')]
    emit = bt[bt.scope.str.startswith('emitting')].set_index('type').n_pairs
    paired, mapped = len(p), int((p.target_codes != '').sum())
    checkable = int(sets[sets.k == assoc.K7].n_pairs.sum())
    scrubex = int(emit[[t for t in emit.index if t.startswith('scrubex')]].sum())
    S.check('sl_15 paired = pinned 7-day pairs (2,911)', pins['A8 determined pairs 7d'], paired)
    S.check('sl_15 mapped = pinned (1,706)', pins['A8 mapped 7d'], mapped)
    S.check('sl_15 checkable = pinned H1 population (1,439)', pins['H1 population 7d'], checkable)
    S.check('sl_15 scrubex = 1,402', 1402, scrubex)

    stages = [('Paired tickets,\nfinal 7 days', paired, False), ('Category has\na code set', mapped, False),
              ('Machine type\nlogs that set', checkable, False), ('...on scrubex\nmachines', scrubex, True)]
    fig, ax = S.figure(S.HALF)
    y = np.arange(len(stages))[::-1]
    for yi, (lab, v, hot) in zip(y, stages):
        ax.barh(yi, v, height=0.6, color=S.BLUE if hot else S.GRAY_LIGHT, zorder=2)
        ax.text(v + paired * 0.015, yi, f'{v:,}  ({v / paired:.0%})', va='center', ha='left', fontsize=S.FONT,
                color=S.INK, weight='bold' if hot else 'normal')
    ax.set_yticks(y)
    ax.set_yticklabels([s[0] for s in stages], fontsize=S.SMALL, color=S.INK)
    ax.set_xlim(0, paired * 1.42)
    ax.set_xticks([0, 1000, 2000, 3000])
    S.thousands_axis(ax.xaxis)
    S.style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel('Tickets')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
