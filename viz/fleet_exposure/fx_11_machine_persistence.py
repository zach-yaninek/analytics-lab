#!/usr/bin/env python3
"""Fleet chart 11: machines that had tickets in the first half of the period, do they keep having them?

Chart 9 asks whether model differences hold in both halves and chart 10 asks it of customers; this chart asks it of
single machines. The period is split at its midpoint and the machines installed in both halves are grouped by their
unplanned tickets in the first half (0, 1, 2, 3, 4 or more). One vertical bar per group shows the group's
second-half ratio, observed ÷ expected unplanned tickets in the second half (expected from the analysis' own model +
age fit within that half, so 1 = what machines of that model and age have), with its 95% interval as a whisker
(cluster bootstrap over accounts) and the value beside the bar top; the machine count is on the axis label. The
horizontal line is 1.

Two shuffles say how much of the pattern a machine's own history explains (F7 of verification/fleet_exposure.py):
  gray band  first-half counts permuted among machines of the same model and age band, 95% of the shuffles, line =
             median: what model and age alone give (about 1, by construction of the expected tickets);
  orange     first-half counts permuted among machines of the same customer, median and 95%: what site effects
             alone give (busy sites keep being busy, whichever of their machines had the tickets).
A group that sits above the orange interval keeps its tickets beyond what its site explains.

The title states the pooled result for machines with 3 or more first-half tickets (the analysis' persistence
statistic), against the median of the same-customer shuffles; a bracket over the 3 and 4+ bars draws the same
numbers plus the model-and-age median, so the title's numbers are on the chart. Those two bars are blue, the others
gray. The footer's regression-to-the-mean note follows the machines that were above expected beyond chance on the
first half alone: how far their ratio fell from the first half to the second.

The drawn text avoids the defined word 'flagged': the machines in the regression-to-the-mean note are selected on
the first half alone (Benjamini-Hochberg q < 0.05, no ticket minimum), which is not the full-period flagged-machine
rule that fleet.flagged_machine_definition() states, so the note spells the rule out instead.

Every number drawn is checked against an independent recount from fx_machine_flags.csv (every machine with a ticket,
with its tickets and expected tickets per half): the 1, 2, 3 and 4+ groups are recounted exactly, the 0 group's
second-half tickets two ways, and the first-half selection of the note by a local Poisson test and
Benjamini-Hochberg step. The shuffle and bootstrap results are random draws of the analysis and are checked only for
internal consistency (each median inside its band, the pooled 3+ median inside the groups' bands, CSV = summary).

Inputs (computed by verification/fleet_exposure.py; nothing is recomputed here):
  verification/outputs/fleet/fx_outlier_machine_persistence.csv  one row per first-half group: machines,
                                                                 second_half_tickets, second_half_expected,
                                                                 second_half_ratio, boot_lo/hi, cell_null_*,
                                                                 customer_null_* (median, p2_5, p97_5)
  verification/outputs/fleet/fx_outlier_persistence.csv          machine rows: the pooled 3+ ratio against each
                                                                 shuffle (median, 95%, p value) and the
                                                                 second-half ratio of machines selected on the
                                                                 first half alone (note: their first-half ratio)
  verification/outputs/fleet/fx_machine_flags.csv                every machine with a ticket: months, tickets and
                                                                 expected tickets per half (recount)
  verification/outputs/fleet/fx_outlier_models.csv               rate groups with no first-half ticket (their
                                                                 machines have no first-half expected; recount)
  verification/outputs/fleet/fx_summary.json                     period and split, fleet tickets per half,
                                                                 machines with exposure, n_boot, n_null, q_cut, and
                                                                 the persistence statistics (cross-check)
Output:  viz/figures/fx_11_machine_persistence.png
Run:     cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_11_machine_persistence.py
"""
import math
import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.legend_handler import HandlerTuple  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_11_machine_persistence.png'
GROUPS = ['0', '1', '2', '3', '4+']   # first_half_tickets values in the CSV, in order
HOT_FROM = 3                          # the title's group: 3 or more first-half tickets (the analysis' statistic)
STAT = 'second_half_ratio_if_3plus_first_half'          # fx_outlier_persistence rows
STAT_SITE = 'second_half_ratio_if_3plus_first_half_within_customer'
STAT_H1 = 'h1_flagged_second_half_ratio'
TITLE_IN_PER_CHAR = 0.12  # approximate width of one title character (15 pt bold), for the figure width
HEIGHT = 7.9              # figure height, inches
BAR_PX = 22               # bar thickness, pixels at style.DPI
AXIS_LABEL_IN = 0.95      # approximate width of the y tick labels and two-line axis label, inches
X_PAD = 0.6               # space left of the first bar and right of the last, in bar slots
BAND_HALF = 0.27          # half-width of the model-and-age shuffle band, bar slots
SITE_DX = 0.15            # the same-customer shuffle marker sits this far right of the bar centre, bar slots
NBSP = '\u00a0'           # keeps a number with its unit when frame() wraps the subtitle
SUB_CHARS_PER_IN = 12.2   # subtitle wrap width, characters per inch: tighter than frame()'s estimate, because
                          # these lines are dense in digits and '×' and ran past the right margin at its width



def wrapped(items, width):
    """Each subtitle item wrapped at SUB_CHARS_PER_IN for a figure this wide; frame() keeps every (shorter) line."""
    chars = int((width - 2 * style.MARGIN) * SUB_CHARS_PER_IN)
    return [line for item in items for line in textwrap.wrap(item, chars, break_on_hyphens=False)]


def poisson_sf(k, mu):
    """P(X >= k), X ~ Poisson(mu): the upper tail summed directly (accurate for tiny p), local to this chart."""
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
    """Benjamini-Hochberg q-values of p when n tests were run in all (the n - len(p) tests not in p have p = 1,
    which cannot bring any q below 1), local to this chart."""
    order = np.argsort(p, kind='mergesort')
    ranked = p[order] * n / np.arange(1, len(p) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]  # the p = 1 tests beyond len(p) only raise q to <= 1
    out = np.empty(len(p))
    out[order] = np.minimum(q, 1.0)
    return out


def plot(out_dir=fleet.FIG_DIR):
    out_dir = Path(out_dir)
    S = fleet.summary()
    D, F = S['definitions'], S['fleet']
    h1_text, h2_text = fleet.half_texts(S)
    mp = fleet.load('outlier_machine_persistence')
    ps = fleet.load('outlier_persistence').set_index('statistic')
    mf = fleet.load('machine_flags')
    om = fleet.load('outlier_models')
    style.check('fx_11 first-half groups as expected', 1, int(mp.first_half_tickets.astype(str).tolist() == GROUPS))
    g = mp.set_index(mp.first_half_tickets.astype(str))

    # ---- recount from the machine table: machines with exposure in both halves, by first-half tickets ----
    both = mf[(mf.months_h1 > 0) & (mf.months_h2 > 0)].copy()
    both['group'] = np.minimum(both.tickets_h1, 4)
    style.check('fx_11 every listed machine with first-half exposure has second-half exposure', 0,
                int(((mf.months_h1 > 0) & (mf.months_h2 <= 0)).sum()))
    for i, name in enumerate(GROUPS[1:], start=1):
        sel = both[both.group == i]
        style.check(f'fx_11 machines in group {name} (recount)', g.loc[name, 'machines'], len(sel))
        style.check(f'fx_11 second-half tickets, group {name} (recount)', g.loc[name, 'second_half_tickets'],
                    sel.tickets_h2.sum(), 1e-9)
        style.check(f'fx_11 second-half expected, group {name} (recount)', g.loc[name, 'second_half_expected'],
                    sel.expected_h2.sum(), 1e-6)
    # Group 0 holds machines with no ticket at all, which the machine table leaves out: its tickets are recounted
    # two ways, its machines and expected tickets only bounded.
    zero = both[both.group == 0]
    h2_only = mf[mf.months_h1 <= 0]  # installed in the second half
    style.check('fx_11 second-half tickets, group 0 (recount)', g.loc['0', 'second_half_tickets'],
                zero.tickets_h2.sum(), 1e-9)
    style.check('fx_11 second-half tickets, group 0 = fleet second half - other groups - second-half installs',
                g.loc['0', 'second_half_tickets'],
                F['tickets_h2'] - mp.second_half_tickets.iloc[1:].sum() - h2_only.tickets_h2.sum(), 1e-9)
    style.check('fx_11 machines in group 0 >= those with a second-half ticket', 1,
                int(g.loc['0', 'machines'] >= len(zero)))
    style.check('fx_11 machines in both halves <= machines with exposure', 1,
                int(mp.machines.sum() + len(h2_only) <= F['machines_exposed']))
    # Each half's fit gives as many expected as observed tickets over the population, so the groups' expected
    # tickets plus those of the second-half installs with a ticket cannot exceed the fleet's second-half tickets.
    style.check('fx_11 expected, group 0 within bounds', 1,
                int(zero.expected_h2.sum() <= g.loc['0', 'second_half_expected'] <=
                    F['tickets_h2'] - mp.second_half_expected.iloc[1:].sum() - h2_only.expected_h2.sum()))
    style.check('fx_11 ratio = second-half tickets / expected', 0,
                float((mp.second_half_tickets / mp.second_half_expected - mp.second_half_ratio).abs().max()), 1e-12)
    style.check('fx_11 every ratio inside its interval', 0,
                int(((mp.second_half_ratio < mp.boot_lo) | (mp.second_half_ratio > mp.boot_hi)).sum()))
    for pre in ('cell_null', 'customer_null'):
        style.check(f'fx_11 {pre} median inside its band', 0,
                    int(((mp[f'{pre}_median'] < mp[f'{pre}_p2_5']) | (mp[f'{pre}_median'] > mp[f'{pre}_p97_5'])).sum()))

    # ---- the title's statistic: machines with 3 or more first-half tickets ----
    hot = mp.iloc[HOT_FROM:]
    hot_n = int(hot.machines.sum())
    r3 = hot.second_half_tickets.sum() / hot.second_half_expected.sum()
    r3_recount = (both.tickets_h2[both.tickets_h1 >= HOT_FROM].sum() /
                  both.expected_h2[both.tickets_h1 >= HOT_FROM].sum())
    cell, site = ps.loc[STAT], ps.loc[STAT_SITE]
    style.check('fx_11 3+ ratio = groups 3 and 4+ (persistence table)', cell.observed, r3, 1e-9)
    style.check('fx_11 3+ ratio (recount)', r3, r3_recount, 1e-9)
    style.check('fx_11 3+ machines = groups 3 and 4+', cell.units, hot_n)
    style.check('fx_11 3+ machines (recount)', hot_n, int((both.tickets_h1 >= HOT_FROM).sum()))
    style.check('fx_11 both shuffles test the same 3+ ratio', cell.observed, site.observed, 1e-12)
    for key, row in ((STAT, cell), (STAT_SITE, site)):
        js = S['persistence'][key]
        for col in ('observed', 'perm_null_median', 'perm_null_p2_5', 'perm_null_p97_5', 'perm_p_value'):
            style.check(f'fx_11 {key} {col}: CSV = summary', js[col], row[col], 5e-5)
    # Each shuffle's 3+ ratio is a weighted mean of its 3 and 4+ ratios, so the pooled median lies inside the span
    # of the two groups' 95% bands.
    for pre, row in (('cell_null', cell), ('customer_null', site)):
        style.check(f'fx_11 3+ {pre} median inside the 3 and 4+ bands', 1,
                    int(hot[f'{pre}_p2_5'].min() <= row.perm_null_median <= hot[f'{pre}_p97_5'].max()))
    # How many of the shuffles reached the observed ratio: p = (count + 1) / (n_null + 1).
    n_null = S['n_null']
    reached = site.perm_p_value * (n_null + 1) - 1
    style.check('fx_11 same-customer p value = (shuffles reaching it + 1) / (n_null + 1)', round(reached), reached,
                1e-6)
    reached = int(round(reached))
    style.check('fx_11 3+ ratio above the same-customer 95% band', 1, int(r3 > site.perm_null_p97_5))

    # ---- the regression-to-the-mean note: machines above expected beyond chance on the first half alone ----
    h1 = ps.loc[STAT_H1]
    h1_ratio_note = float(re.search(r'H1 ratio was ([0-9.]+)', h1.note).group(1))
    # Recount: Poisson test of every machine with first-half expected tickets, Benjamini-Hochberg over all of them.
    # Machines with no first-half ticket have p = 1; machines of a rate group with no first-half ticket at all have
    # no first-half expected and are not tested. Their count is known only within bounds, so the selection is
    # recounted at both ends.
    tested = both[both.expected_h1 > 0]
    p = np.array([poisson_sf(o, e) for o, e in zip(tested.tickets_h1, tested.expected_h1)])
    style.check('fx_11 first-half Poisson p (recount) = machine table', 0, float(np.nanmax(np.abs(p - tested.p_h1))),
                1e-9)
    no_h1_groups = om.rate_group[om.tickets_h1 == 0]
    n_hi = int(mp.machines.sum()) - int((both.expected_h1 == 0).sum())
    n_lo = int(mp.machines.sum()) - int(om.machines[om.rate_group.isin(no_h1_groups)].sum())
    picks = []
    for n in (n_lo, n_hi):
        q = bh_q(p, n)
        sel = tested[q < D['q_cut']]
        picks.append((len(sel), sel.tickets_h1.sum() / sel.expected_h1.sum(),
                      sel.tickets_h2.sum() / sel.expected_h2.sum()))
    style.check('fx_11 first-half selection does not depend on the untested count', 1, int(picks[0] == picks[1]))
    h1_n, h1_r1, h1_r2 = picks[1]
    style.check('fx_11 machines selected on the first half (recount)', h1.units, h1_n)
    style.check('fx_11 their first-half ratio (recount) = note', h1_ratio_note, h1_r1, 0.005)
    style.check('fx_11 their second-half ratio (recount)', h1.observed, h1_r2, 1e-9)
    style.check('fx_11 they fell from the first half to the second', 1, int(h1_r2 < h1_r1))

    # ---- half dates drawn on the axes ----
    start, end, split = (pd.Timestamp(x) for x in (*D['period'], D['split']))
    last1 = split - pd.Timedelta(days=1)
    style.check('fx_11 first-half dates = period start to the day before the split', 1,
                int(h1_text == f'{start.day} {start:%b %Y} to {last1.day} {last1:%b %Y}'))
    style.check('fx_11 second-half dates = split to period end', 1,
                int(h2_text == f'{split.day} {split:%b} to {end.day} {end:%b %Y}'))

    # ---- numbers drawn (rounded as drawn) ----
    n_both = int(mp.machines.sum())
    cell_med, site_med = mp.cell_null_median, mp.customer_null_median
    for name, drawn, actual, tol in [
            ('title 3+ ratio', f'{r3:.1f}', r3_recount, 0.05),
            ('title same-customer median', f'{site.perm_null_median:.1f}', site.perm_null_median, 0.05),
            ('bracket 3+ ratio', f'{r3:.2f}', r3_recount, 0.005),
            ('bracket same-customer median', f'{site.perm_null_median:.2f}', site.perm_null_median, 0.005),
            ('bracket model-and-age median', f'{cell.perm_null_median:.2f}', cell.perm_null_median, 0.005),
            ('note first-half ratio', f'{h1_ratio_note:.1f}', h1_r1, 0.05),
            ('note second-half ratio', f'{h1.observed:.1f}', h1_r2, 0.05)]:
        style.check(f'fx_11 drawn {name}', float(drawn), actual, tol)

    # ---------------------------------------------------------------------------------------------- Drawing
    title = (f'Machines with {HOT_FROM}+ first-half tickets had {r3:.1f}× their expected second-half tickets; '
             f'their sites alone would give {site.perm_null_median:.1f}×')
    width = max(10.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN)
    fig, ax = style.figure(width, HEIGHT)
    n = len(mp)
    x = np.arange(n)
    span = n - 1 + 2 * X_PAD
    bar_w = (BAR_PX / style.DPI) / ((width - 2 * style.MARGIN - AXIS_LABEL_IN) / span)  # data units
    is_hot = x >= HOT_FROM
    colors = np.where(is_hot, style.BLUE, style.GRAY_LIGHT)

    ax.axhline(1, color=style.INK2, lw=1, zorder=2)
    for xi, row in zip(x, mp.itertuples()):
        ax.add_patch(Rectangle((xi - BAND_HALF, row.cell_null_p2_5), 2 * BAND_HALF,
                               row.cell_null_p97_5 - row.cell_null_p2_5, facecolor=style.BAR_BACKGROUND,
                               edgecolor='none', zorder=1))
        ax.plot([xi - BAND_HALF, xi + BAND_HALF], [row.cell_null_median] * 2, color=style.GRAY, lw=1.2,
                solid_capstyle='butt', zorder=1.5)
    ax.bar(x, mp.second_half_ratio, width=bar_w, color=colors, linewidth=0, zorder=3)
    ax.errorbar(x, mp.second_half_ratio, yerr=[mp.second_half_ratio - mp.boot_lo, mp.boot_hi - mp.second_half_ratio],
                fmt='none', ecolor=style.INK2, elinewidth=1.2, capsize=3.5, capthick=1.2, zorder=4)
    xs = x + SITE_DX
    ax.vlines(xs, mp.customer_null_p2_5, mp.customer_null_p97_5, color=style.ORANGE, lw=1.6, zorder=4)
    ax.plot(xs, site_med, 'D', ms=5.5, mfc=style.ORANGE, mec=style.SURFACE, mew=0.8, ls='none', zorder=5)
    for xi, row, h in zip(x, mp.itertuples(), is_hot):
        label = f'{row.second_half_ratio:.2f}×'
        style.check(f'fx_11 drawn ratio, group {row.first_half_tickets}', float(label[:-1]), row.second_half_ratio,
                    0.005)
        # Left of the bar top: the shuffle marks sit right of the bar and around 1.
        ax.text(xi - bar_w / 2 - 0.035, row.second_half_ratio, label, ha='right', va='center', fontsize=9.5,
                color=style.INK if h else style.INK2, weight='bold' if h else 'normal', zorder=6)

    # Bracket over the 3 and 4+ bars with the pooled statistic the title states.
    top = float(hot.boot_hi.max())
    yb = top + 0.22
    x0, x1 = HOT_FROM - BAND_HALF, n - 1 + BAND_HALF
    ax.plot([x0, x0, x1, x1], [yb - 0.08, yb, yb, yb - 0.08], color=style.INK2, lw=1, solid_capstyle='butt',
            zorder=4)
    ax.text((x0 + x1) / 2, yb + 0.06,
            f'{HOT_FROM} or more together ({hot_n} machines): {r3:.2f}×\n'
            f'shuffled within customer {site.perm_null_median:.2f}×, within model and age '
            f'{cell.perm_null_median:.2f}×',
            ha='center', va='bottom', fontsize=9.5, color=style.INK, linespacing=1.35, zorder=6)
    ax.text(-X_PAD + 0.02, 1, ' 1 = as expected', ha='left', va='bottom', fontsize=9.5, color=style.INK2, zorder=6)

    ax.set_xticks(x)
    names = [f'{k}' if k != f'{n - 1}+' else f'{n - 1} or more' for k in GROUPS]
    ax.set_xticklabels([f'{s}\n{m:,} machines' for s, m in zip(names, mp.machines)], color=style.INK2)
    for tick, h in zip(ax.get_xticklabels(), is_hot):
        if h:
            tick.set_fontweight('bold')
            tick.set_color(style.INK)
    ax.set_xlim(-X_PAD, n - 1 + X_PAD)
    ax.set_ylim(0, yb + 0.75)
    ax.yaxis.set_major_locator(MultipleLocator(0.5))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: '0' if v == 0 else f'{v:g}×'))
    style.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel(f'Unplanned tickets in the first half ({h1_text})')
    ax.set_ylabel(f'Second-half tickets ÷ expected\n({h2_text})')

    handles = [(Patch(facecolor=style.GRAY_LIGHT, edgecolor='none'), Patch(facecolor=style.BLUE, edgecolor='none')),
               Patch(facecolor=style.BAR_BACKGROUND, edgecolor=style.GRAY, linewidth=0.8),
               Line2D([], [], color=style.ORANGE, lw=1.6, marker='D', ms=5.5, mfc=style.ORANGE,
                      mec=style.SURFACE, mew=0.8)]
    labels = ['Observed ÷ expected in the second half (whisker: 95% interval)',
              'First-half counts shuffled within model and age: 95% of shuffles (line: median)',
              'Shuffled within customer, what site effects alone give: median and 95%']
    ax.legend(handles, labels, loc='upper left', handler_map={tuple: HandlerTuple(ndivide=None, pad=0)},
              handlelength=2.2, frameon=True, facecolor=style.SURFACE, edgecolor='none', framealpha=1)

    # ---------------------------------------------------------------------------------------------- Text
    subtitle = [f'Observed ÷ expected unplanned tickets in the second half of {fleet.period_text(S)}, by each '
                f'machine\'s unplanned tickets in the first half: the {n_both:,}{NBSP}machines installed in both '
                f'halves, with 95% intervals.',
                f'Shuffling first-half counts among machines of the same model and age gives about 1 in every group '
                f'(medians {cell_med.min():.2f}× to {cell_med.max():.2f}×); shuffling them among machines of the same '
                f'customer gives {site_med.min():.2f}× to {site_med.max():.2f}×, the part that comes from the site. '
                f'{"None" if reached == 0 else reached} of {n_null:,} same-customer shuffles '
                f'reach{"es" if reached == 1 else ""} the {r3:.2f}× of machines with {HOT_FROM} or more.']
    method = (f'Expected tickets in each half come from a model + age fit within that half, so 1 = machines of the '
              f'same model and age in that half. Whiskers: cluster bootstrap over accounts ({S["n_boot"]:,} draws), '
              f'since tickets cluster within accounts. Shuffles: first-half counts permuted {n_null:,} times among '
              f'machines of the same model group and age band (gray band) or of the same customer (orange).')
    regression = (f'Regression to the mean: the {h1_n} machines above their expected tickets beyond chance on the '
                  f'first half alone (Poisson test, Benjamini-Hochberg q < {D["q_cut"]:g}) had '
                  f'{h1_ratio_note:.1f}× their expected tickets in the first half and {h1.observed:.1f}× in the '
                  f'second: they stay high, but picking machines on one extreme half overstates how high.')
    source_note = (fleet.source('outlier_machine_persistence', 'outlier_persistence', 'machine_flags',
                                 'outlier_models').rstrip('.')
                   + '; draws and half dates from fx_summary.json.')
    style.frame(fig, title, wrapped(subtitle, width),
                definitions=[fleet.expected_definition(S), fleet.unplanned_definition()],
                notes=[method, regression, source_note])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
