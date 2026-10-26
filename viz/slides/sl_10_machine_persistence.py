#!/usr/bin/env python3
"""Slide chart 10: machines that had tickets in the first half of the period, do they keep having them?

Slide version of viz/fleet_exposure/fx_11_machine_persistence.py, with the same data logic. The period is split at
its midpoint and the machines installed in both halves are grouped by their unplanned tickets in the first half (0,
1, 2, 3, 4 or more); one bar per group shows the group's second-half ratio, observed / expected unplanned tickets in
the second half (expected from the analysis' model + age fit within that half, so 1 = what machines of that model and
age have), with the machine count under each bar. The more tickets a machine had in the first half, the more it has
in the second. A separate bar at the right is fx_11's regression-to-the-mean note: the machines above their expected
tickets beyond chance on the first half alone (Poisson test, Benjamini-Hochberg q < 0.05, no ticket minimum), with
their second-half ratio as the bar and their first-half ratio as the annotation above it. The drawn text avoids the
word 'flagged', as fx_11 does: this first-half selection is not the full-period flagged-machine rule.
Blue = machines with 3 or more first-half tickets (the analysis' persistence statistic) and the first-half selection;
gray = the other groups.

Left out against the page chart: the 95% bootstrap intervals, the two shuffle references (within model and age;
within customer), the bracket with the pooled 3-or-more statistic, and the title, subtitle and footer (card header
and speaker notes).

Input:  verification/outputs/fleet/fx_outlier_machine_persistence.csv  (per first-half group: machines,
                                                                        second_half_tickets, second_half_expected,
                                                                        second_half_ratio)
        verification/outputs/fleet/fx_outlier_persistence.csv          (the second-half ratio of the machines
                                                                        selected on the first half alone, and their
                                                                        first-half ratio in the note)
        verification/outputs/fleet/fx_machine_flags.csv                (every machine with a ticket: months, tickets
                                                                        and expected tickets per half; recount)
        verification/outputs/fleet/fx_outlier_models.csv               (rate groups with no first-half ticket; recount)
        verification/outputs/fleet/fx_summary.json                     (period and split, fleet tickets per half,
                                                                        q_cut, persistence statistics; cross-check)
Output: viz/figures/slides/sl_10_machine_persistence.png (wide card)
"""
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator  # noqa: E402
from matplotlib.text import Text  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_10_machine_persistence.png'
FLEET = S.OUT / 'fleet'
GROUPS = ['0', '1', '2', '3', '4+']   # first_half_tickets values in the CSV, in order
HOT_FROM = 3                          # blue from this group on (the analysis' statistic: 3 or more)
STAT_H1 = 'h1_flagged_second_half_ratio'
H1_X = 5.1                            # x of the first-half selection's bar (the groups are at 0..4)
XLIM = (-0.45, 5.68)
BAR_W = 0.5
YMAX = 4.0


def poisson_sf(k, mu):
    """P(X >= k), X ~ Poisson(mu): the upper tail summed directly (fx_11's recount)."""
    k = int(k)
    if k <= 0:
        return 1.0
    if k <= mu:
        return max(0.0, 1.0 - sum(math.exp(-mu + j * math.log(mu) - math.lgamma(j + 1)) for j in range(k)))
    term = math.exp(-mu + k * math.log(mu) - math.lgamma(k + 1))
    total, j = term, k
    while term > total * 1e-17 and j < k + 10_000:
        j += 1
        term *= mu / j
        total += term
    return total


def bh_q(p, n):
    """Benjamini-Hochberg q-values of p when n tests were run in all (the others have p = 1) (fx_11's recount)."""
    order = np.argsort(p, kind='mergesort')
    ranked = p[order] * n / np.arange(1, len(p) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(len(p))
    out[order] = np.minimum(q, 1.0)
    return out


def checks(summ, mp, ps, mf, om):
    """fx_11's recount of the groups and of the first-half selection from the machine table; returns the numbers
    drawn: per group (machines, ratio) and the selection's (machines, first-half ratio, second-half ratio)."""
    D, F = summ['definitions'], summ['fleet']
    S.check('sl_10 first-half groups as expected', 1, int(mp.first_half_tickets.astype(str).tolist() == GROUPS))
    g = mp.set_index(mp.first_half_tickets.astype(str))

    both = mf[(mf.months_h1 > 0) & (mf.months_h2 > 0)].copy()
    both['group'] = np.minimum(both.tickets_h1, 4)
    S.check('sl_10 every listed machine with first-half exposure has second-half exposure', 0,
            int(((mf.months_h1 > 0) & (mf.months_h2 <= 0)).sum()))
    for i, name in enumerate(GROUPS[1:], start=1):
        sel = both[both.group == i]
        S.check(f'sl_10 machines in group {name} (recount)', g.loc[name, 'machines'], len(sel))
        S.check(f'sl_10 second-half tickets, group {name} (recount)', g.loc[name, 'second_half_tickets'],
                sel.tickets_h2.sum(), 1e-9)
        S.check(f'sl_10 second-half expected, group {name} (recount)', g.loc[name, 'second_half_expected'],
                sel.expected_h2.sum(), 1e-6)
    # Group 0 holds machines with no ticket at all, which the machine table leaves out: its tickets are recounted
    # two ways, its machines and expected tickets only bounded (as fx_11).
    zero = both[both.group == 0]
    h2_only = mf[mf.months_h1 <= 0]
    S.check('sl_10 second-half tickets, group 0 (recount)', g.loc['0', 'second_half_tickets'],
            zero.tickets_h2.sum(), 1e-9)
    S.check('sl_10 second-half tickets, group 0 = fleet second half - other groups - second-half installs',
            g.loc['0', 'second_half_tickets'],
            F['tickets_h2'] - mp.second_half_tickets.iloc[1:].sum() - h2_only.tickets_h2.sum(), 1e-9)
    p0, p1 = (pd.Timestamp(x) for x in D['period'])
    cut = pd.Timestamp(D['split'])
    len_h1 = (cut - p0).days / D['month_days']
    len_h2 = (p1 + pd.Timedelta(days=1) - cut).days / D['month_days']
    S.check('sl_10 no machine has more than a half of months in a half', 1,
            int(mf.months_h1.max() <= len_h1 + 1e-9 and mf.months_h2.max() <= len_h2 + 1e-9))
    months_h1 = 100 * F['tickets_h1'] / F['rate_h1']
    months_h2 = 100 * F['tickets_h2'] / F['rate_h2']
    S.check('sl_10 half months add up to the fleet months', F['months'], months_h1 + months_h2, 1e-6)
    n_lo_both = math.ceil(months_h1 / len_h1 - 1e-9)
    n_hi_both = math.floor((months_h2 - h2_only.months_h2.sum()) / len_h2 + 1e-9)
    n_ticket = len(both[both.group > 0])
    S.check('sl_10 machines in group 0 within the half-month bounds', 1,
            int(n_lo_both - n_ticket <= g.loc['0', 'machines'] <= n_hi_both - n_ticket))
    S.check('sl_10 expected, group 0 within bounds', 1,
            int(zero.expected_h2.sum() <= g.loc['0', 'second_half_expected'] <=
                F['tickets_h2'] - mp.second_half_expected.iloc[1:].sum() - h2_only.expected_h2.sum()))
    ratio = mp.second_half_tickets / mp.second_half_expected
    S.check('sl_10 ratio = second-half tickets / expected', 0, float((ratio - mp.second_half_ratio).abs().max()), 1e-12)

    # The first-half selection: Poisson test of every machine with first-half expected tickets, Benjamini-Hochberg
    # over all of them; the untested count is known only within bounds, so the selection is recounted at both ends.
    h1 = ps.loc[STAT_H1]
    h1_ratio_note = float(re.search(r'H1 ratio was ([0-9.]+)', h1.note).group(1))
    tested = both[both.expected_h1 > 0]
    p = np.array([poisson_sf(o, e) for o, e in zip(tested.tickets_h1, tested.expected_h1)])
    S.check('sl_10 first-half Poisson p (recount) = machine table', 0, float(np.nanmax(np.abs(p - tested.p_h1))), 1e-9)
    no_h1_groups = om.rate_group[om.tickets_h1 == 0]
    n_hi = int(mp.machines.sum()) - int((both.expected_h1 == 0).sum())
    n_lo = int(mp.machines.sum()) - int(om.machines[om.rate_group.isin(no_h1_groups)].sum())
    picks = []
    for n in (n_lo, n_hi):
        sel = tested[bh_q(p, n) < D['q_cut']]
        picks.append((len(sel), sel.tickets_h1.sum() / sel.expected_h1.sum(),
                      sel.tickets_h2.sum() / sel.expected_h2.sum()))
    S.check('sl_10 first-half selection does not depend on the untested count', 1, int(picks[0] == picks[1]))
    h1_n, h1_r1, h1_r2 = picks[1]
    S.check('sl_10 machines selected on the first half (recount) = CSV', h1.units, h1_n)
    S.check('sl_10 their first-half ratio (recount) = note', h1_ratio_note, h1_r1, 0.005)
    S.check('sl_10 their second-half ratio (recount) = CSV', h1.observed, h1_r2, 1e-9)
    js = summ['persistence'][STAT_H1]
    S.check('sl_10 selection: CSV = summary (machines)', js['units'], h1.units)
    S.check('sl_10 selection: CSV = summary (second-half ratio)', js['observed'], h1.observed, 5e-5)
    S.check('sl_10 they fell from the first half to the second', 1, int(h1_r2 < h1_r1))
    S.check('sl_10 they stayed above 1 in the second half', 1, int(h1_r2 > 1))
    return mp, (h1_n, h1_r1, h1_r2)


def times(v, nd):
    return f'{v:.{nd}f}×'


def plot(out_dir=S.FIG_DIR):
    summ = json.loads((FLEET / 'fx_summary.json').read_text())
    mp = pd.read_csv(FLEET / 'fx_outlier_machine_persistence.csv')
    ps = pd.read_csv(FLEET / 'fx_outlier_persistence.csv').set_index('statistic')
    mf = pd.read_csv(FLEET / 'fx_machine_flags.csv')
    om = pd.read_csv(FLEET / 'fx_outlier_models.csv')
    mp, (h1_n, h1_r1, h1_r2) = checks(summ, mp, ps, mf, om)
    n = len(mp)
    ratio = (mp.second_half_tickets / mp.second_half_expected).to_numpy()

    # The numbers drawn, as text, against the recount (and the values the deck quotes).
    bar_txt = [times(r, 2) for r in mp.second_half_ratio]
    for name, t, r, want in zip(GROUPS, bar_txt, ratio, (0.76, 1.35, 1.61, 2.84, 2.33)):
        S.check(f'sl_10 drawn ratio, group {name} ({want})', want, float(t[:-1]))
        S.check(f'sl_10 drawn ratio, group {name} = tickets / expected', float(t[:-1]), r, 0.005)
    for name, m, want in zip(GROUPS, mp.machines, (6330, 1407, 421, 142, 130)):
        S.check(f'sl_10 drawn machines, group {name} ({want})', want, m)
    r1_txt, r2_txt = times(h1_r1, 1), times(h1_r2, 1)
    S.check('sl_10 drawn selected machines (70)', 70, h1_n)
    S.check('sl_10 drawn first-half ratio (12.6)', 12.6, float(r1_txt[:-1]))
    S.check('sl_10 drawn first-half ratio = recount', float(r1_txt[:-1]), h1_r1, 0.05)
    S.check('sl_10 drawn second-half ratio (2.9)', 2.9, float(r2_txt[:-1]))
    S.check('sl_10 drawn second-half ratio = recount', float(r2_txt[:-1]), h1_r2, 0.05)
    S.check('sl_10 every bar inside the axes', 1, int(max(ratio.max(), h1_r2) < YMAX - 0.6))

    fig, ax = S.figure(S.WIDE)
    x = np.arange(n)
    hot = x >= HOT_FROM
    ax.axhline(1, color=S.INK2, lw=1.2, zorder=2)
    ax.bar(x, ratio, width=BAR_W, color=np.where(hot, S.BLUE, S.GRAY_LIGHT), linewidth=0, zorder=3)
    ax.bar([H1_X], [h1_r2], width=BAR_W, color=S.NAVY, linewidth=0, zorder=3)
    for xi, r, t, h in zip(x, ratio, bar_txt, hot):
        ax.annotate(t, xy=(xi + BAR_W / 2, r), xytext=(5, 0), textcoords='offset points', ha='left', va='center',
                    fontsize=S.FONT, color=S.INK if h else S.INK2, weight='bold' if h else 'normal', zorder=6)
    ax.annotate(r2_txt, xy=(H1_X + BAR_W / 2, h1_r2), xytext=(5, 0), textcoords='offset points', ha='left',
                va='center', fontsize=S.FONT, color=S.INK, weight='bold', zorder=6)
    # The selection's first-half ratio, off the scale: stated above its bar, with an arrow down to it.
    note = ax.annotate(f'{r1_txt} expected\nin the first half', xy=(H1_X, h1_r2 + 0.06), xytext=(H1_X, YMAX - 0.04),
                ha='center', va='top', fontsize=S.SMALL, color=S.INK, linespacing=1.15, zorder=6,
                arrowprops=dict(arrowstyle='-|>', color=S.INK2, lw=1.4, shrinkA=4, shrinkB=2, mutation_scale=14))
    ax.text(XLIM[0] + 0.08, 1.04, '1 = as expected', ha='left', va='bottom', fontsize=S.SMALL, color=S.INK2, zorder=6)
    # A divider between the continuum and the first-half selection, ending below the annotation.
    x_div, y_div = H1_X - BAR_W / 2 - 0.13, 3.25
    ax.plot([x_div, x_div], [0, y_div], color=S.BASE, lw=1.0, ls=(0, (4, 3)), zorder=1)

    ax.set_xticks([*x, H1_X])
    ax.set_xticklabels([f'{"4 or more" if k == "4+" else k}\n{m:,} machines' for k, m in zip(GROUPS, mp.machines)]
                       + [f'Picked on first half\n{h1_n} machines'], fontsize=S.TICK)
    for tick, h in zip(ax.get_xticklabels(), [*hot, True]):
        tick.set_color(S.INK if h else S.INK2)
        if h:
            tick.set_fontweight('bold')
    ax.set_xlim(*XLIM)
    ax.set_ylim(0, YMAX)
    ax.yaxis.set_major_locator(MultipleLocator(1))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: '0' if v == 0 else f'{v:g}×'))
    S.style_axes(ax, grid='y', baseline='bottom')
    ax.set_ylabel('Second-half tickets ÷ expected')
    # The x label belongs to the five groups only: centre it under them.
    ax.set_xlabel('Unplanned tickets in the first half', x=((n - 1) / 2 - XLIM[0]) / (XLIM[1] - XLIM[0]),
                  ha='center')

    # No text overlaps another (display coordinates, after layout).
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    texts = [t for t in ax.texts if t.get_text()] + [t for t in ax.get_xticklabels() if t.get_text()]
    boxes = [t.get_window_extent(r) for t in texts] + [ax.xaxis.label.get_window_extent(r)]
    overlaps = sum(boxes[i].overlaps(boxes[j]) for i in range(len(boxes)) for j in range(i + 1, len(boxes)))
    S.check('sl_10 no two texts overlap', 0, overlaps)
    # The text alone (an annotation's extent includes its arrow, which runs down past the divider's end by design).
    note_bottom = ax.transData.inverted().transform(Text.get_window_extent(note, r))[0][1]
    S.check('sl_10 annotation clear of the divider', 1, int(note_bottom > y_div + 0.05))
    ticks = sorted((t.get_window_extent(r) for t in ax.get_xticklabels() if t.get_text()), key=lambda b: b.x0)
    gap = min(b.x0 - a.x1 for a, b in zip(ticks, ticks[1:])) / fig.dpi
    S.check('sl_10 tick labels at least 0.15 in apart', 1, int(gap >= 0.15))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
