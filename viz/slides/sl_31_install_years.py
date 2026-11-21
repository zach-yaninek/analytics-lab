#!/usr/bin/env python3
"""Slide chart 31 (follow-up to slide 4): were young machines' problems fixed in newer production?

The install-year view (docs/09 §4 A6 and §12 item 7): on the 15 support models, unplanned tickets per 100 installed
machine-months (Aug 2025 to Aug 2026) by the machine's install year, for all unplanned tickets and for the three
Categories A6's rule picked (Deposit Door, Touchscreen, Computer Board). Four panels: all tickets (own y axis), then
the three Categories (one shared y axis). Each install year: the rate (blue dot, joined by a thin blue line) and its
95% account-bootstrap interval (thin blue line); each install cohort's pooled rate as a gray step behind (2016-18,
2019-21, 2022-23, 2024-26). The install years whose machines are under 4 this year (2022 to 2026: the first three
bars of slide 4) are shaded. Each panel names the 2022-23 cohort's rate as a multiple of the 2024-26 cohort's.

Input:  verification/outputs/followups/ag_install_pooled.csv, ag_halves.csv, followups_summary.json
Output: viz/figures/slides/sl_31_install_years.png (full card, tall)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402

PNG = 'sl_31_install_years.png'
TERMS = ['install_rate', 'install_band', 'install_ratio', 'install_reading']
ALL = 'All unplanned tickets'
ORDER = ['Touchscreen', 'Deposit Door', 'Computer Board']   # the A6 Categories, the one that peaks first
YEARS = list(range(2016, 2027))                              # install years drawn (earlier years: few machines)
PEAK, NEWEST = '2022-23', '2024-26'


def ratio_text(r):
    return f'×{r.ratio_to_newest_cohort:.2f} ({r.ratio_lo:.2f}–{r.ratio_hi:.2f})' \
        if r.ratio_to_newest_cohort < 1 else f'×{r.ratio_to_newest_cohort:.1f} ({r.ratio_lo:.1f}–{r.ratio_hi:.1f})'


def plot(out_dir=S.FIG_DIR):
    d = pd.read_csv(T.FU / 'ag_install_pooled.csv', dtype={'install': str})
    s = T.summary()
    a6 = s['facts']['a6_categories']
    S.check('sl_31 the three Categories = A6 rule', 1, int(sorted(a6) == sorted(ORDER)))
    S.check('sl_31 the table holds the A6 Categories and all tickets', 1,
            int(set(d.category) == set(ORDER) | {ALL}))
    years = d[d.unit == 'year']
    cohorts = d[d.unit == 'cohort'].set_index(['category', 'install'])
    for c in ORDER + [ALL]:
        y = years[years.category == c]
        S.check(f'sl_31 {c}: cohort tickets = the sum of their years', int(y.tickets.sum()),
                int(cohorts.loc[c].tickets.sum()) + int(y[y.install.astype(int) < 2016].tickets.sum()))
        S.check(f'sl_31 {c}: every drawn year has an interval around its rate', 1,
                int(((y.rate_lo <= y.rate_per_100 + 1e-12) & (y.rate_per_100 <= y.rate_hi + 1e-12))
                    [y.install.astype(int).isin(YEARS)].all()))
    # The shaded years: machines under 4 at the midpoint (90% of 2022 installs, all later ones, none earlier).
    u4 = years[years.category == ALL].set_index('install').under4_share_of_machines
    S.check('sl_31 install years 2023-2026 are all under 4', 1,
            int((u4[[str(y) for y in range(2023, 2027)]] == 1).all()))
    S.check('sl_31 install years up to 2021 are all 4+', 1,
            int((u4[[str(y) for y in range(2016, 2022)]] == 0).all()))
    share22 = float(u4['2022'])

    fig, ax0 = S.figure(S.FULL_TALL)
    ax0.remove()
    axes = fig.subplots(1, 4, gridspec_kw={'width_ratios': [1, 1, 1, 1]})
    fig.get_layout_engine().set(wspace=0.06)
    cat_max = max(years[years.category.isin(ORDER) & years.install.astype(int).isin(YEARS)].rate_hi.max(), 1)
    ylim_cat = (0, np.ceil(cat_max + 0.25))
    for ax, c in zip(axes, [ALL] + ORDER):
        S.style_axes(ax, grid='y', baseline='bottom')
        y = years[(years.category == c) & years.install.astype(int).isin(YEARS)].copy()
        y['yr'] = y.install.astype(int)
        y = y.sort_values('yr')
        ax.axvspan(2021.5, max(YEARS) + 0.5, color=S.GRID, alpha=0.55, lw=0, zorder=0)
        # Each cohort's pooled rate, as a gray step over its years.
        for (lab, r) in cohorts.loc[c].iterrows():
            a, b = int(lab[:4]), int(lab[:2] + lab[-2:])
            a, b = max(a, min(YEARS)), min(b, max(YEARS))
            ax.plot([a - 0.45, b + 0.45], [r.rate_per_100] * 2, color=S.GRAY, lw=2.0, solid_capstyle='butt',
                    zorder=1)
        ax.vlines(y.yr, y.rate_lo, y.rate_hi, color=S.BLUE, lw=1.4, zorder=2)
        ax.plot(y.yr, y.rate_per_100, color=S.BLUE, lw=1.2, zorder=3)
        ax.plot(y.yr, y.rate_per_100, 'o', ms=6.5, color=S.BLUE, mec=S.WHITE, mew=1.0, zorder=4)
        ax.set_xlim(min(YEARS) - 0.6, max(YEARS) + 0.6)
        ax.set_xticks([2016, 2018, 2020, 2022, 2024, 2026])
        ax.set_xticklabels(['2016', '2018', '2020', '2022', '2024', '2026'])
        top = np.ceil(y.rate_hi.max() + 0.5) if c == ALL else ylim_cat[1]
        ax.set_ylim(0, top)
        if c == ALL:
            ax.set_ylabel('Tickets per 100 machine-months')
        ax.set_title(c, loc='left', fontsize=S.FONT, color=S.INK, pad=26)
        r = cohorts.loc[(c, PEAK)]
        txt = f"{PEAK.replace('-', '–')} vs {NEWEST.replace('-', '–')} installs: {ratio_text(r)}"
        ax.text(0, 1.015, txt, transform=ax.transAxes, ha='left', va='bottom', fontsize=S.DEF, color=S.INK2,
                weight='bold' if (r.ratio_lo > 1 or r.ratio_hi < 1) else 'normal')
        S.check(f'sl_31 {c}: ratio drawn = cohort rates', r.rate_per_100 / cohorts.loc[(c, NEWEST)].rate_per_100,
                r.ratio_to_newest_cohort, 1e-9)
        nd = 2 if r.ratio_to_newest_cohort < 1 else 1
        S.check(f'sl_31 {c}: ratio label', r.ratio_to_newest_cohort, float(txt.split('×')[1].split(' ')[0]),
                0.5 * 10 ** -nd)
        S.check(f'sl_31 {c}: ratio interval contains the ratio', 1,
                int(r.ratio_lo <= r.ratio_to_newest_cohort <= r.ratio_hi))
    for ax in axes[2:]:
        ax.sharey(axes[1])
        ax.tick_params(axis='y', labelleft=True)        # each panel reads its own values
    axes[1].set_ylim(*ylim_cat)
    S.check('sl_31 every Category interval inside its axes', 1,
            int(years[years.category.isin(ORDER) & years.install.astype(int).isin(YEARS)].rate_hi.max() < ylim_cat[1]))

    handles = [Line2D([], [], color=S.BLUE, lw=1.2, marker='o', ms=6.5, mec=S.WHITE,
                      label='install year, with 95% interval'),
               Line2D([], [], color=S.GRAY, lw=2.0, label='install cohort (2016–18, 2019–21, 2022–23, 2024–26)'),
               Patch(facecolor=S.GRID, alpha=0.55, label='under 4 this year')]
    fig.legend(handles=handles, loc='outside upper center', ncols=3, fontsize=S.SMALL, handlelength=2.2,
               columnspacing=2.0)

    # The definitions' numbers.
    t = T.terms()
    S.check('sl_31 definition: 90% of 2022 installs are under 4', round(100 * share22),
            int(t['install_band'][1].split('% of 2022')[0].split('(')[-1]))
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
