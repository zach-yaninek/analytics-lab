#!/usr/bin/env python3
"""Slide chart 23 (follow-up to slide 4): did the young machines' excess narrow from the first half to the second?

For the three Categories the fixed rule picks (docs/09 §4 A6: the largest within-model excess over the year), the
within-model extra tickets per 100 under-4 machine-months on the support models (each model's own 4+ rate in the
same half), in the first half of the period (gray ring) and the second (blue dot), each with its 95% account-bootstrap
interval; the right-hand column gives the change, second minus first, with its interval, bold where it excludes 0.

Input:  verification/outputs/followups/ag_halves.csv, ag_decomposition.csv, followups_summary.json
Output: viz/figures/slides/sl_23_age_halves.png (half card, tall)
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

PNG = 'sl_23_age_halves.png'
TERMS = ['halves', 'fix_proof']
MINUS = '−'
OFFSET = 0.15
H1 = 'first half (Aug 2025 to 14 Feb 2026)'
H2 = 'second half (15 Feb to Aug 2026)'


def num(v, sign=False):
    """Two decimals with a typographic minus like the axis."""
    return (f'{v:+.2f}' if sign else f'{v:.2f}').replace('-', MINUS)


def plot(out_dir=S.FIG_DIR):
    h = pd.read_csv(T.FU / 'ag_halves.csv')
    d = h[h.category != 'All unplanned tickets'].reset_index(drop=True)
    s = T.summary()
    S.check('sl_23 three Categories', 3, len(d))
    S.check('sl_23 the Categories = summary (A6 rule), in order', 1,
            int(list(d.category) == s['facts']['a6_categories']))
    # The A6 rule recomputed: the three estimable Categories in the first seven groups with the largest positive
    # within-model excess over the full period.
    dec = pd.read_csv(T.FU / 'ag_decomposition.csv')
    adj = pd.read_csv(T.FU / 'ag_type_adjusted.csv')
    est = set(adj.type[(adj.variant == 'primary') & (adj.level == 'category') & (adj.estimable == True)])  # noqa: E712
    S.check('sl_23 ag_decomposition Categories = the estimable Categories', 1,
            int(set(dec.type[dec.level == 'category']) == est))
    cat = dec[(dec.level == 'category') & dec.type.isin(est)
              & dec.group.isin(['Door', 'Mechanical', 'Electronics', 'Network', 'Software', 'Operator error', 'Other'])]
    top3 = list(cat[cat.within_model_age_tickets > 0].nlargest(3, 'within_model_age_tickets').type)
    S.check('sl_23 the Categories = the three largest within-model excesses (A6 rule)', 1,
            int(top3 == list(d.category)))

    # The definition's and the legend's dates: the split on 15 Feb 2026 and the period Aug 2025 to Aug 2026.
    defs = s['definitions']
    halves_text = T.terms()['halves'][1]
    S.check('sl_23 definition: split 15 Feb 2026, period Aug 2025 to Aug 2026', 1,
            int(defs['split'] == '2026-02-15' and defs['period'] == ['2025-08-01', '2026-08-31']
                and 'first half (Aug 2025 to 14 Feb 2026) vs second (15 Feb to Aug 2026)' in halves_text))
    S.check('sl_23 legend dates = the definition', 1,
            int(H1 in halves_text and re.sub(r'^second half', 'second', H2) in halves_text))

    fig, ax = S.figure(S.HALF_TALL)
    n = len(d)
    XV = 2.62                                    # the value column (right-aligned)
    for k, r in d.iterrows():
        yi = n - 1 - k                           # file order, first at the top
        dm = dec[(dec.level == 'category') & (dec.type == r.category)].iloc[0]
        S.check(f'sl_23 {r.category} full-period excess = ag_decomposition', dm.within_model_age_tickets,
                r.full_period_within_model_age_tickets, 1e-6)
        for half in ('h1', 'h2'):
            rate = 100 * r[f'{half}_under4_tickets_support'] / r[f'{half}_under4_months_support']
            S.check(f'sl_23 {r.category} {half} under-4 rate = 100 x tickets / months', rate,
                    r[f'{half}_under4_rate_per_100_support'], 1e-6)
            S.check(f'sl_23 {r.category} {half} excess = under-4 rate - same-model 4+ rate',
                    rate - r[f'{half}_same_model_4plus_rate_per_100'], r[f'{half}_within_model_age_per_100'], 1e-6)
            S.check(f'sl_23 {r.category} {half} interval contains the estimate', 1,
                    int(r[f'{half}_lo'] <= r[f'{half}_within_model_age_per_100'] <= r[f'{half}_hi']))
        change = r.h2_within_model_age_per_100 - r.h1_within_model_age_per_100
        S.check(f'sl_23 {r.category} change = second - first', change, r.change_h2_minus_h1, 1e-6)
        S.check(f'sl_23 {r.category} change interval contains the change', 1,
                int(r.change_lo <= change <= r.change_hi))
        sig = r.change_lo > 0 or r.change_hi < 0
        label = f'{num(change, sign=True)} ({num(r.change_lo)} to {num(r.change_hi)})'
        parsed = [float(x.replace(MINUS, '-')) for x in re.findall(r'[+−]?\d+\.\d+', label)]
        S.check(f'sl_23 {r.category} label change {num(change, True)}', change, parsed[0], 0.005)
        S.check(f'sl_23 {r.category} label interval low', r.change_lo, parsed[1], 0.005)
        S.check(f'sl_23 {r.category} label interval high', r.change_hi, parsed[2], 0.005)

        y1, y2 = yi + OFFSET, yi - OFFSET
        ax.plot([r.h1_lo, r.h1_hi], [y1, y1], color=S.GRAY, lw=2, solid_capstyle='butt', zorder=2)
        ax.scatter(r.h1_within_model_age_per_100, y1, s=90, facecolor=S.WHITE, edgecolor=S.GRAY, linewidth=2,
                   zorder=3)
        ax.plot([r.h2_lo, r.h2_hi], [y2, y2], color=S.BLUE, lw=2, solid_capstyle='butt', zorder=2)
        ax.scatter(r.h2_within_model_age_per_100, y2, s=90, color=S.BLUE, edgecolor=S.WHITE, linewidth=1.2,
                   zorder=4)
        ax.text(XV, yi, label, va='center', ha='right', fontsize=S.SMALL, color=S.INK if sig else S.INK2,
                weight='bold' if sig else 'normal')
    lo = d[['h1_lo', 'h2_lo']].min().min()
    hi = d[['h1_hi', 'h2_hi']].max().max()
    S.check('sl_23 every interval inside the axes (-0.32 to 1.6)', 1, int(-0.32 < lo and hi < 1.6))

    ax.axvline(0, color=S.INK2, lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.text(XV, n - 1 + 0.85, f'Change, 2nd {MINUS} 1st (95% interval)', ha='right', va='top', fontsize=S.SMALL,
            color=S.INK2, bbox={'boxstyle': 'square,pad=0.1', 'facecolor': S.WHITE, 'edgecolor': 'none'})  # hides grid
    ax.set_xlim(-0.32, XV + 0.02)
    ax.set_xticks([0, 0.5, 1, 1.5])
    ax.set_xticklabels(['0', '0.5', '1', '1.5'])
    ax.set_yticks(np.arange(n))
    ax.set_yticklabels(d.category[::-1])
    ax.set_ylim(-0.6, n - 1 + 0.85)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Within-model extra tickets per 100 under-4 machine-months')
    handles = [Line2D([], [], color=S.GRAY, lw=2, marker='o', ms=9.5, mfc=S.WHITE, mec=S.GRAY, mew=2, label=H1),
               Line2D([], [], color=S.BLUE, lw=2, marker='o', ms=9.5, mfc=S.BLUE, mec=S.WHITE, mew=1.2, label=H2)]
    ax.legend(handles=handles, loc='lower left', bbox_to_anchor=(0, 1.0), ncol=1, handlelength=1.6,
              handletextpad=0.5, borderaxespad=0.2, labelspacing=0.3, fontsize=S.SMALL)
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
