#!/usr/bin/env python3
"""Slide chart 21 (follow-up to slide 4): where young machines' extra tickets come from, by request type.

Extra tickets on under-4 machines relative to 4+ machines' rates (docs/09 §4 A4), by request group: all of it, not
adjusted for model (gray ring), and the part within model, against each support model's own 4+ rate (blue dot), with
the within-model part's 95% account-bootstrap interval (light bar). The gap between ring and dot is model mix (plus
the few tickets on models outside the support). Rows sorted by the within-model part, which the right-hand column
gives; the note gives all unplanned tickets.

Input:  verification/outputs/followups/ag_decomposition.csv, ag_support.csv, followups_summary.json
Output: viz/figures/slides/sl_21_age_excess.png (half card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402

PNG = 'sl_21_age_excess.png'
TERMS = ['extra', 'support', 'under4']
MINUS = '−'


def signed(v):
    """'+535' / '−127', with a typographic minus like the axis."""
    return f'{v:+,.0f}'.replace('-', MINUS)


def unsigned(text):
    return float(text.replace(MINUS, '-').replace(',', ''))


def plot(out_dir=S.FIG_DIR):
    t = pd.read_csv(T.FU / 'ag_decomposition.csv')
    # Largest within-model part at the top (y = row index, so the largest comes last).
    d = t[t.level == 'group'].sort_values('within_model_age_tickets').reset_index(drop=True)
    a = t[t.level == 'all'].iloc[0]
    s = T.summary()
    f = s['facts']['part_a']
    S.check('sl_21 ten request groups', 10, len(d))
    S.check('sl_21 the groups are the summary\'s ten', 1, int(sorted(d.type) == sorted(s['definitions']['groups'])))
    S.check('sl_21 groups sum to the all row, extra', a.extra_tickets, d.extra_tickets.sum(), 1e-6)
    S.check('sl_21 groups sum to the all row, within model', a.within_model_age_tickets,
            d.within_model_age_tickets.sum(), 1e-6)
    S.check('sl_21 all row = summary, extra', f['extra_tickets'], a.extra_tickets, 1e-5)
    S.check('sl_21 all row = summary, within model', f['extra_within_model_age'], a.within_model_age_tickets, 1e-5)

    # The definitions' numbers: 1,447 extra tickets in all; the 15 support models.
    terms = T.terms()
    S.check('sl_21 definition: 1,447 in all', a.extra_tickets,
            unsigned(re.search(r'\(([\d,]+) in all\)', terms['extra'][1]).group(1)), 0.5)
    sup = pd.read_csv(T.FU / 'ag_support.csv')
    sup_models = sup[sup.in_support].groupby('model').months.agg(['min', 'size'])
    S.check('sl_21 support models have 100+ months in each age group', 1,
            int(((sup_models['size'] == 2) & (sup_models['min'] >= 100)).all()))
    S.check('sl_21 definition: 15 support models', len(sup_models),
            int(re.search(r'on the (\d+) models with 100\+', terms['support'][1]).group(1)))
    S.check('sl_21 definition: 100+ machine-months = the protocol minimum', s['definitions']['min_support_months'],
            int(re.search(r'with (\d+)\+ machine-months', terms['support'][1]).group(1)))
    S.check('sl_21 definition: under 4 = <1, 1-2, 2-4 in Aug 2025 to Aug 2026', 1,
            int(s['definitions']['young_bands'] == ['<1', '1-2', '2-4']
                and s['definitions']['period'] == ['2025-08-01', '2026-08-31']
                and '(Aug 2025 to Aug 2026)' in terms['under4'][1] and '(<1, 1-2 and 2-4 years)' in terms['under4'][1]))

    # The note.
    note = f'All: {a.extra_tickets:,.0f} extra tickets; {a.within_model_age_tickets:,.0f} within model'
    nums = re.findall(r'[\d,]+(?= extra| within)', note)
    S.check('sl_21 note: 1,447 extra tickets', a.extra_tickets, unsigned(nums[0]), 0.5)
    S.check('sl_21 note: 1,156 within model', a.within_model_age_tickets, unsigned(nums[1]), 0.5)

    fig, ax = S.figure(S.HALF_TALL)
    n = len(d)
    XV = 905                                     # the value column (right-aligned)
    for i, r in d.iterrows():
        S.check(f'sl_21 {r.type} extra = within model + model mix + outside support', r.extra_tickets,
                r.within_model_age_tickets + r.model_mix_tickets + r.outside_support_tickets, 1e-6)
        S.check(f'sl_21 {r.type} interval contains the within-model part', 1,
                int(r.within_model_age_lo <= r.within_model_age_tickets <= r.within_model_age_hi))
        ax.plot([r.within_model_age_lo, r.within_model_age_hi], [i, i], color=S.LIGHT, lw=6, solid_capstyle='butt',
                zorder=1)
        ax.scatter(r.extra_tickets, i, s=90, facecolor=S.WHITE, edgecolor=S.GRAY, linewidth=2, zorder=3)
        ax.scatter(r.within_model_age_tickets, i, s=90, color=S.BLUE, edgecolor=S.WHITE, linewidth=1.2, zorder=4)
        label = signed(r.within_model_age_tickets)
        S.check(f'sl_21 {r.type} label {label}', r.within_model_age_tickets, unsigned(label), 0.5)
        ax.text(XV, i, label, va='center', ha='right', fontsize=S.SMALL, color=S.INK2)
    S.check('sl_21 rows sorted by the within-model part', 1, int(d.within_model_age_tickets.is_monotonic_increasing))
    lo, hi = d.within_model_age_lo.min(), d[['within_model_age_hi', 'extra_tickets']].max().max()
    S.check('sl_21 every mark inside the axes (-470 to 760)', 1, int(-470 < lo and hi < 760))

    ax.axvline(0, color=S.INK2, lw=1.2, ls=(0, (4, 3)), zorder=2)
    ax.text(XV, n - 1 + 1.15, note, ha='right', va='center', fontsize=S.SMALL, color=S.INK2,
            bbox={'boxstyle': 'square,pad=0.1', 'facecolor': S.WHITE, 'edgecolor': 'none'})  # masks the grid
    ax.set_xlim(-470, XV + 10)
    ax.set_xticks([-400, -200, 0, 200, 400, 600])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'.replace('-', MINUS)))
    ax.set_yticks(np.arange(n))
    ax.set_yticklabels(d.type)
    ax.set_ylim(-0.6, n - 1 + 1.6)
    S.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel('Extra tickets on under-4 machines, vs 4+ rates')
    handles = [Line2D([], [], ls='', marker='o', ms=9.5, mfc=S.WHITE, mec=S.GRAY, mew=2, label='all extra tickets'),
               Line2D([], [], ls='', marker='o', ms=9.5, mfc=S.BLUE, mec=S.WHITE, mew=1.2, label='within model'),
               Line2D([], [], color=S.LIGHT, lw=6, solid_capstyle='butt', label='95% interval')]
    ax.legend(handles=handles, loc='lower left', bbox_to_anchor=(0, 1.0), ncol=3, handlelength=1.2,
              handletextpad=0.4, columnspacing=1.2, borderaxespad=0.2, fontsize=S.SMALL)
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
