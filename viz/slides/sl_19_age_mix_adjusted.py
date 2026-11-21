#!/usr/bin/env python3
"""Slide chart 19 (follow-up to slide 4): do young machines' tickets differ in type, within model?

Mantel-Haenszel share ratio by request type (docs/09 §4 A2): a type's share of under-4 machines' tickets over its
share of 4+ machines' tickets of the same model, pooled over the support models, with the 95% account-bootstrap
interval. Blue = differs after the gate and Benjamini-Hochberg (A3).

Input:  verification/outputs/followups/ag_type_adjusted.csv, followups_summary.json
Output: viz/figures/slides/sl_19_age_mix_adjusted.png (half card, tall)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402

PNG = 'sl_19_age_mix_adjusted.png'
TERMS = ['share_ratio', 'interval', 'perm_test']


def plot(out_dir=S.FIG_DIR):
    d = pd.read_csv(T.FU / 'ag_type_adjusted.csv')
    d = d[(d.variant == 'primary') & (d.level == 'group')].sort_values('share_ratio_mh').reset_index(drop=True)
    s = T.summary()
    S.check('sl_19 nine groups in the family', 9, len(d))
    S.check('sl_19 significant groups = summary', 1,
            int(sorted(d.type[d.significant]) == sorted(s['facts']['part_a']['groups_significant'])))

    fig, ax = S.figure(S.HALF_TALL)
    y = np.arange(len(d))
    for i, r in d.iterrows():
        c = S.BLUE if r.significant else S.GRAY
        ax.plot([r.share_ratio_lo, r.share_ratio_hi], [i, i], color=c, lw=2.5, solid_capstyle='round', zorder=2)
        ax.scatter(r.share_ratio_mh, i, s=90, color=c, zorder=3, edgecolor=S.WHITE, linewidth=1.5)
        ax.text(5.9, i, f'{r.share_ratio_mh:.2f}', va='center', ha='right', fontsize=S.SMALL,
                color=S.INK if r.significant else S.INK2, weight='bold' if r.significant else 'normal')
        S.check(f'sl_19 {r.type} interval contains the estimate', 1,
                int(r.share_ratio_lo <= r.share_ratio_mh <= r.share_ratio_hi))
    ax.axvline(1, color=S.INK2, lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.set_xscale('log')
    ticks = [0.25, 0.5, 1, 2, 4]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f'{t:g}×' for t in ticks])
    ax.set_xlim(0.2, 6)
    ax.text(5.9, len(d) - 0.45, 'Ratio', ha='right', va='bottom', fontsize=S.SMALL, color=S.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(d.type)
    ax.set_ylim(-1.3, len(d) + 0.1)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Share ratio, under 4 vs 4+ years, same model (log scale)')
    ax.text(0.95, -1.05, '\u2190 more often on 4+', ha='right', va='center', fontsize=S.SMALL, color=S.INK2)
    ax.text(1.05, -1.05, 'more often under 4 \u2192', ha='left', va='center', fontsize=S.SMALL, color=S.INK2)
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
