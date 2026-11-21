#!/usr/bin/env python3
"""Slide chart 20 (follow-up to slide 4): do young machines' tickets differ in Category, within model?

Mantel-Haenszel share ratio by Category (docs/09 §4 A2, the Category level): a Category's share of under-4 machines'
tickets over its share of 4+ machines' tickets of the same model, pooled over the support models, with the 95%
account-bootstrap interval, for the 12 estimable Categories with the most tickets. Categories are tested only within
the groups that pass the gate (A3): blue = differs after Benjamini-Hochberg within its group, gray = tested and not
significant, open ring = not tested (its group did not differ).

Input:  verification/outputs/followups/ag_type_adjusted.csv, ag_support.csv, followups_summary.json
Output: viz/figures/slides/sl_20_age_categories.png (half card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402

PNG = 'sl_20_age_categories.png'
TERMS = ['share_ratio_cat', 'interval', 'cat_test']
N_SHOWN = 12
SIG_LABEL = 'differs (q < 0.05)'


def plot(out_dir=S.FIG_DIR):
    t = pd.read_csv(T.FU / 'ag_type_adjusted.csv')
    p = t[t.variant == 'primary']
    cats = p[(p.level == 'category') & (p.estimable == True)].copy()  # noqa: E712 (object column of bools)
    cats['tickets'] = cats.under4_tickets + cats.plus4_tickets
    cats = cats.sort_values(['tickets', 'type'], ascending=[False, True]).reset_index(drop=True)
    d = cats.head(N_SHOWN).sort_values('share_ratio_mh').reset_index(drop=True)
    s = T.summary()
    a = s['facts']['part_a']
    groups_sig = sorted(p.type[(p.level == 'group') & (p.significant == True)])  # noqa: E712
    S.check('sl_20 twelve Categories', N_SHOWN, len(d))
    S.check('sl_20 the 12th has more tickets than the 13th (no tie at the cut)', 1,
            int(cats.tickets.iloc[N_SHOWN - 1] > cats.tickets.iloc[N_SHOWN]))
    S.check('sl_20 significant groups = summary', 1, int(groups_sig == sorted(a['groups_significant'])))
    S.check('sl_20 tested = in a significant group', 1,
            int(all(bool(r.tested) == (r.group in groups_sig) for _, r in d.iterrows())))
    S.check('sl_20 significant Categories shown = summary', 1,
            int(sorted(d.type[d.significant == True]) ==  # noqa: E712
                sorted(c for c in a['categories_significant'] if c in set(d.type))))
    S.check('sl_20 significant only if tested', 1, int(all(bool(r.tested) for _, r in d.iterrows() if r.significant)))

    # The definitions' numbers: the support models, the 12 Categories, the groups tested, the bootstrap draws.
    sup = pd.read_csv(T.FU / 'ag_support.csv')
    sup_models = sup[sup.in_support].groupby('model').months.agg(['min', 'size'])
    S.check('sl_20 support models have 100+ months in each age group', 1,
            int(((sup_models['size'] == 2) & (sup_models['min'] >= 100)).all()))
    terms = T.terms()
    m = re.search(r'over (\d+) models\); the (\d+) most frequent', terms['share_ratio_cat'][1])
    S.check('sl_20 definition: 15 support models', len(sup_models), int(m.group(1)))
    S.check('sl_20 definition: the 12 most frequent Categories', len(d), int(m.group(2)))
    named = re.search(r'groups that differ \(([^)]*)\)', terms['cat_test'][1]).group(1).split(', ')
    S.check('sl_20 definition: the groups tested = the significant groups', 1, int(sorted(named) == groups_sig))
    S.check('sl_20 legend: q < 0.05 = the protocol alpha', s['definitions']['alpha'],
            float(re.search(r'q < ([\d.]+)', SIG_LABEL).group(1)))
    S.check('sl_20 definition: 2,000 bootstrap draws', s['n_boot'],
            int(re.search(r'\(([\d,]+) draws\)', terms['interval'][1]).group(1).replace(',', '')))

    fig, ax = S.figure(S.HALF_TALL)
    y = np.arange(len(d))
    for i, r in d.iterrows():
        if r.significant:
            line, face, edge = S.BLUE, S.BLUE, S.WHITE
        elif r.tested:
            line, face, edge = S.GRAY, S.GRAY, S.WHITE
        else:
            line, face, edge = S.GRAY_LIGHT, S.WHITE, S.GRAY
        ax.plot([r.share_ratio_lo, r.share_ratio_hi], [i, i], color=line, lw=2.5, solid_capstyle='round', zorder=2)
        ax.scatter(r.share_ratio_mh, i, s=90, facecolor=face, edgecolor=edge, linewidth=1.5 if r.tested else 2,
                   zorder=3)
        label = f'{r.share_ratio_mh:.2f}'
        ax.text(5.9, i, label, va='center', ha='right', fontsize=S.SMALL,
                color=S.INK if r.significant else S.INK2, weight='bold' if r.significant else 'normal')
        S.check(f'sl_20 {r.type} label {label}', r.share_ratio_mh, float(label), 0.005)
        S.check(f'sl_20 {r.type} interval contains the estimate', 1,
                int(r.share_ratio_lo <= r.share_ratio_mh <= r.share_ratio_hi))
        S.check(f'sl_20 {r.type} interval inside the axes, left of the value column (0.2 to 4.5)', 1,
                int(0.2 < r.share_ratio_lo and r.share_ratio_hi < 4.5))
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
    mask = {'boxstyle': 'square,pad=0.1', 'facecolor': S.WHITE, 'edgecolor': 'none'}  # hides the grid behind the text
    ax.text(0.95, -1.05, '← more often on 4+', ha='right', va='center', fontsize=S.SMALL, color=S.INK2,
            bbox=mask)
    ax.text(1.05, -1.05, 'more often under 4 →', ha='left', va='center', fontsize=S.SMALL, color=S.INK2,
            bbox=mask)
    handles = [Line2D([], [], color=S.BLUE, lw=2.5, marker='o', ms=9.5, mfc=S.BLUE, mec=S.WHITE, mew=1.5,
                      label=SIG_LABEL),
               Line2D([], [], color=S.GRAY, lw=2.5, marker='o', ms=9.5, mfc=S.GRAY, mec=S.WHITE, mew=1.5,
                      label='tested, not significant'),
               Line2D([], [], color=S.GRAY_LIGHT, lw=2.5, marker='o', ms=9.5, mfc=S.WHITE, mec=S.GRAY, mew=2,
                      label='not tested')]
    ax.legend(handles=handles, loc='lower left', bbox_to_anchor=(0, 1.0), ncol=3, handlelength=1.6,
              handletextpad=0.4, columnspacing=1.2, borderaxespad=0.2, fontsize=S.SMALL)
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
