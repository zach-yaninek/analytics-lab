#!/usr/bin/env python3
"""Slide chart 8: do customers that run high stay high? Each customer's STR in the first half against the second.

Slide version of viz/fleet_exposure/fx_10_customer_persistence.py, with the same data logic: the customers with at
least MIN_E_HALF expected tickets in each half (the population of the analysis' persistence statistics, F7 of
verification/fleet_exposure.py), one dot each at its standardised ticket ratio (STR = observed / expected tickets)
in the first half (x) and the second half (y), both axes logarithmic with the same range. A customer with no tickets
in a half (STR 0) is drawn at fx_10's floor value in a shaded strip whose tick reads 0; the customers with none in
either half sit on one point, which is labelled with their count. The lines at 1 mark "in line with the fleet".
Blue = consistent outliers; gray = every other customer. The legend gives the blue count as "10 of 18": the other 8
consistent outliers have under MIN_E_HALF expected tickets in a half and are not drawn (as in fx_10's footer), so
the 18 on the drivers slide do not read as a contradiction. The rank correlation between the halves and the median of
the analysis' permutation null (second halves shuffled among customers of similar size) are a direct label.

Left out against the page chart: the customer labels on the blue dots, the dark-gray class (customers above their
expected tickets beyond chance in both halves but flagged in fewer than 10 of 12 method variants; drawn gray here),
the quadrant counts, and the title, subtitle and footer (card header and speaker notes). Pseudonymous version only.

Input:  verification/outputs/fleet/fx_outlier_customers.csv    (per customer: O_h1, E_h1, STR_h1, p_h1, O_h2, E_h2,
                                                                STR_h2, p_h2, variants_flagged, consistent_outlier)
        verification/outputs/fleet/fx_outlier_persistence.csv  (rank correlation and its permutation null)
        verification/outputs/fleet/fx_summary.json             (definitions, consistent-outlier count, the same
                                                                persistence statistics, for checks)
Output: viz/figures/slides/sl_08_customer_persistence.png (half card)
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_08_customer_persistence.png'
FLEET = S.OUT / 'fleet'
MIN_E_HALF = 3            # customers with at least this many expected tickets in each half (fx_10, F7)
SPEARMAN = 'spearman_STR_h1_h2'
P_CUT = 0.05              # above expected beyond chance in a half: one-sided Poisson p below this (fx_10)
ZERO_GAP, EDGE, HEADROOM = 2.4, 1.35, 1.6  # fx_10's axis range: floor = smallest STR / ZERO_GAP, ends beyond
TICKS = [0.1, 0.2, 0.5, 1, 2, 5]
ZERO_FILL = '#F1F3F5'     # the zero-ticket strips: a tint lighter than the grid


def poisson_upper(k, mu):
    """P(X >= k) for X ~ Poisson(mu), summed in log space (fx_10's recomputation)."""
    k = int(k)
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    term = lambda j: math.exp(-mu + j * math.log(mu) - math.lgamma(j + 1))  # noqa: E731
    if k <= mu:
        return max(0.0, 1.0 - sum(term(j) for j in range(k)))
    total, j = 0.0, k
    while True:
        t = term(j)
        total += t
        if t < total * 1e-17 or j > k + 20_000:
            return total
        j += 1


def rank_correlation(a, b):
    """Spearman: Pearson correlation of the ranks, ties given their average rank."""
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    ra, rb = ra - ra.mean(), rb - rb.mean()
    return float((ra * rb).sum() / math.sqrt((ra * ra).sum() * (rb * rb).sum()))


def checks(summ, oc, pe):
    """fx_10's checks on the customer table; returns the plotted customers and the statistics drawn."""
    d, P = summ['definitions'], summ['persistence']
    S.check('sl_08 consistent outliers in the table = summary (18)', summ['customers']['consistent_outliers'],
            int(oc.consistent_outlier.sum()))
    p1 = np.array([poisson_upper(o, e) if e > 0 else 1.0 for o, e in zip(oc.O_h1, oc.E_h1)])
    p2 = np.array([poisson_upper(o, e) if e > 0 else 1.0 for o, e in zip(oc.O_h2, oc.E_h2)])
    cons = (oc.variants_flagged.to_numpy() >= d['min_variants']) & (p1 < P_CUT) & (p2 < P_CUT)
    S.check('sl_08 consistent outliers recomputed = consistent_outlier', 0,
            int((cons != oc.consistent_outlier.to_numpy()).sum()))

    keep = ((oc.E_h1 >= MIN_E_HALF) & (oc.E_h2 >= MIN_E_HALF)).to_numpy()
    c = oc[keep].copy()
    c['p1'], c['p2'], c['cons'] = p1[keep], p2[keep], cons[keep]
    sp = pe[pe.level == 'customer'].set_index('statistic').loc[SPEARMAN]
    S.check('sl_08 customers plotted = units of the rank correlation', int(sp.units), len(c))
    S.check('sl_08 customers plotted = summary units (311)', P[SPEARMAN]['units'], len(c))
    S.check('sl_08 p first half recomputed = p_h1', 0, float(np.abs(c.p1 - c.p_h1).max()), 1e-9)
    S.check('sl_08 p second half recomputed = p_h2', 0, float(np.abs(c.p2 - c.p_h2).max()), 1e-9)

    c['x'], c['y'] = c.O_h1 / c.E_h1, c.O_h2 / c.E_h2
    S.check('sl_08 STR first half = O_h1 / E_h1', 0, float((c.x - c.STR_h1).abs().max()), 1e-9)
    S.check('sl_08 STR second half = O_h2 / E_h2', 0, float((c.y - c.STR_h2).abs().max()), 1e-9)
    rho = rank_correlation(c.x, c.y)
    S.check('sl_08 rank correlation recomputed = persistence CSV', float(sp.observed), rho, 1e-9)
    S.check('sl_08 rank correlation = summary', P[SPEARMAN]['observed'], rho, 5e-5)
    S.check('sl_08 shuffled median: CSV = summary', P[SPEARMAN]['perm_null_median'], float(sp.perm_null_median), 5e-5)
    S.check('sl_08 rank correlation above the 97.5th percentile of the shuffles', 1, int(rho > sp.perm_null_p97_5))
    S.check('sl_08 consistent outliers plotted are above expected beyond chance in both halves', 0,
            int((c.cons & ~((c.p1 < P_CUT) & (c.p2 < P_CUT))).sum()))
    S.check('sl_08 no STR exactly 1', 0, int(((c.x == 1) | (c.y == 1)).sum()))
    z1, z2 = c.O_h1 == 0, c.O_h2 == 0
    S.check('sl_08 STR 0 in the first half = no tickets', int(z1.sum()), int((c.STR_h1 == 0).sum()))
    S.check('sl_08 STR 0 in the second half = no tickets', int(z2.sum()), int((c.STR_h2 == 0).sum()))
    zero_both = int((z1 & z2).sum())
    S.check('sl_08 no tickets in either half, from the CSV STR columns', zero_both,
            int(((c.STR_h1 == 0) & (c.STR_h2 == 0)).sum()))
    not_shown = int(cons.sum() - c.cons.sum())
    S.check('sl_08 consistent outliers not drawn = those under MIN_E_HALF in a half (8)', 8, not_shown)
    return c, {'rho': rho, 'null_med': float(sp.perm_null_median), 'null_hi': float(sp.perm_null_p97_5),
               'zero_both': zero_both, 'n_cons': int(c.cons.sum()), 'n_cons_csv': int(c.consistent_outlier.sum()),
               'n_cons_all': int(cons.sum())}


def plot(out_dir=S.FIG_DIR):
    summ = json.loads((FLEET / 'fx_summary.json').read_text())
    oc = pd.read_csv(FLEET / 'fx_outlier_customers.csv')
    pe = pd.read_csv(FLEET / 'fx_outlier_persistence.csv')
    c, k = checks(summ, oc, pe)
    n = len(c)

    # The numbers drawn, as text, against the recomputed values.
    rho_txt, null_txt = f'{k["rho"]:.2f}', f'{k["null_med"]:.2f}'
    S.check('sl_08 drawn rank correlation (0.46)', 0.46, float(rho_txt))
    S.check('sl_08 drawn rank correlation = recomputed', float(rho_txt), k['rho'], 0.005)
    S.check('sl_08 drawn shuffled median (0.04)', 0.04, float(null_txt))
    S.check('sl_08 drawn shuffled median = CSV', float(null_txt), k['null_med'], 0.005)
    S.check('sl_08 drawn consistent outliers (10) = recomputed rule', 10, k['n_cons'])
    S.check('sl_08 drawn consistent outliers = CSV column', k['n_cons'], k['n_cons_csv'])
    S.check('sl_08 drawn consistent outliers in all (18) = recomputed rule', 18, k['n_cons_all'])
    S.check('sl_08 drawn consistent outliers in all = summary', k['n_cons_all'],
            summ['customers']['consistent_outliers'])
    S.check('sl_08 drawn other customers (301)', 301, n - k['n_cons'])
    S.check('sl_08 drawn customers (311)', 311, n)
    S.check('sl_08 drawn no tickets in either half (9)', 9, k['zero_both'])

    # fx_10's axis range: the same on both axes, zero-ticket customers at a floor below the smallest STR.
    pos = np.concatenate([c.x[c.x > 0], c.y[c.y > 0]])
    zero_at = pos.min() / ZERO_GAP
    sep = math.sqrt(zero_at * pos.min())
    lo, hi = zero_at / EDGE, pos.max() * HEADROOM
    S.check('sl_08 floor below every positive STR', 1, int(zero_at < pos.min() and sep < pos.min()))
    S.check('sl_08 every STR inside the axes', 1, int(pos.max() < hi))
    xs, ys = np.where(c.x > 0, c.x, zero_at), np.where(c.y > 0, c.y, zero_at)

    fig, ax = S.figure(S.HALF)
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.axvspan(lo, sep, color=ZERO_FILL, lw=0, zorder=0)
    ax.axhspan(lo, sep, color=ZERO_FILL, lw=0, zorder=0)
    ax.axvline(1, color=S.INK2, lw=1.0, zorder=1)
    ax.axhline(1, color=S.INK2, lw=1.0, zorder=1)

    cons = c.cons.to_numpy()
    ax.scatter(xs[~cons], ys[~cons], s=24, color=S.GRAY_LIGHT, edgecolor=S.WHITE, linewidth=0.4, zorder=3,
               clip_on=False)
    ax.scatter(xs[cons], ys[cons], s=70, color=S.BLUE, edgecolor=S.WHITE, linewidth=0.7, zorder=4, clip_on=False)
    zero_lab = ax.annotate(f'{k["zero_both"]} with no tickets\nin either half', xy=(zero_at, zero_at), xytext=(5, 7),
                           textcoords='offset points', ha='left', va='bottom', fontsize=S.SMALL, color=S.INK2,
                           linespacing=1.1, zorder=6)

    # The finding as a direct label, in the empty top left of the plot.
    stat = ax.text(0.035, 0.965, f'Rank correlation {rho_txt}', transform=ax.transAxes, ha='left', va='top',
                   fontsize=S.FONT + 2, color=S.INK, weight='bold', zorder=6)
    stat2 = ax.annotate(f'{null_txt} when the halves are shuffled', xy=(0, 0), xycoords=stat, xytext=(0, -4),
                        textcoords='offset points', ha='left', va='top', fontsize=S.SMALL, color=S.INK2, zorder=6)

    ticks = [zero_at] + [t for t in TICKS if sep < t < hi]
    fmt = FuncFormatter(lambda v, _: '0' if v == zero_at else f'{v:g}')
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(FixedLocator(ticks))
        axis.set_minor_locator(NullLocator())
        axis.set_major_formatter(fmt)
    S.style_axes(ax, grid='both', baseline=None)
    ax.set_xlabel('STR, first half (log scale)')
    ax.set_ylabel('STR, second half (log scale)')
    handles = [Line2D([], [], marker='o', ls='', markersize=9, markerfacecolor=S.BLUE, markeredgewidth=0,
                      label=f'Consistent outlier ({k["n_cons"]} of {k["n_cons_all"]})'),
               Line2D([], [], marker='o', ls='', markersize=6.5, markerfacecolor=S.GRAY_LIGHT, markeredgewidth=0,
                      label=f'Other customer ({n - k["n_cons"]})')]
    # Just above the bottom zero strip at the right, where no customer sits (checked below).
    leg = ax.legend(handles=handles, loc='lower right', bbox_to_anchor=(hi, sep), bbox_transform=ax.transData,
                    handlelength=0.8, handletextpad=0.4, borderaxespad=0.2, labelspacing=0.3, frameon=True,
                    facecolor=S.WHITE, edgecolor='none', framealpha=1)
    leg.set_zorder(7)

    # No dot hidden under the direct labels or the legend (display coordinates, after layout).
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    pts = ax.transData.transform(np.column_stack([xs, ys]))
    for name, artist in (('rank label', stat), ('shuffled label', stat2), ('legend', leg), ('zero label', zero_lab)):
        bb = artist.get_window_extent(r).padded(3)
        under = (pts[:, 0] > bb.x0) & (pts[:, 0] < bb.x1) & (pts[:, 1] > bb.y0) & (pts[:, 1] < bb.y1)
        S.check(f'sl_08 no dot under the {name}', 0, int(under.sum()))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
