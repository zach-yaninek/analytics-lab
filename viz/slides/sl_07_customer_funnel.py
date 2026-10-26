#!/usr/bin/env python3
"""Slide chart 7: funnel plot of customers, standardised ticket ratio (STR) against expected tickets.

Slide version of viz/fleet_exposure/fx_07_customer_funnel.py. A customer with few machines can show a high STR by
chance alone, and customers differ from one another by more than Poisson chance allows (sites, users and reporting
differ). Each customer is one dot: x = expected tickets at fleet rates for its models and ages (the model + age fit;
log scale), y = STR = observed / expected. Gray lines: the 95% and 99.8% overdispersion-adjusted funnel limits
(fleet.funnel_limits with tau^2 from fx_summary.json), which allow for the normal spread between customers. Blue: the
63 customers flagged by the Poisson rule; light gray: the others. The one customer above the 99.8% limit is labelled
"just above" it: Customer 695 clears the line by under 0.1 STR, and the next customer (Customer 339) is on it.
As in fx_07, the y axis ends at ceil(highest flagged STR + 0.6) = 7 and the one customer above it (STR 16.2, not
flagged) is drawn as a triangle on the top edge.

Left out against the page chart: the split of the flagged customers into consistent outliers (18, blue) and other
flagged customers (45, orange), drawn here in one colour; the plain Poisson 99.8% limits (dashed; 48 customers above
them) and their label; the labels of the consistent outliers with 10 or more expected tickets. Pseudonymous version
only: no real-name variant is drawn here.

Input:  verification/outputs/fleet/fx_customer_rates.csv  (one row per customer: tickets, expected, STR, z_d, flags)
        verification/outputs/fleet/fx_summary.json        (tau^2, z95, z998, flag thresholds, customer counts)
Output: viz/figures/slides/sl_07_customer_funnel.png (half card)
"""
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullLocator  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_07_customer_funnel.png'
FLEET = S.OUT / 'fleet'
X_RIGHT = 2.4      # x axis ends at this multiple of the largest expected count (room for the line labels), as in fx_07
QUOTED = {'flagged': 63, 'beyond': 1, 'customer': 'Customer 695'}  # what the card header and speaker notes quote


def poisson_upper(k, mu):
    """P(X >= k) for X ~ Poisson(mu), summed in log space (fx_07's recomputation)."""
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


def bh(p):
    """Benjamini-Hochberg q-values."""
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p, kind='mergesort')
    q = np.minimum.accumulate((p[order] * n / np.arange(1, n + 1))[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out


def funnel_limits(expected, z, tau2):
    """(lower, upper) STR limits of the overdispersion-adjusted funnel (fleet.funnel_limits)."""
    e = np.asarray(expected, float)
    half = z * np.sqrt(1 / (4 * e) + tau2)
    return np.maximum(0.0, 1 - half) ** 2, (1 + half) ** 2


def checks(summ, cr):
    """fx_07's consistency checks; returns the plotted customers (expected > 0), their flags and what is drawn."""
    d, C = summ['definitions'], summ['customers']
    S.check('sl_07 customer tickets sum to the fleet', summ['fleet']['tickets'], int(cr.tickets.sum()))
    S.check('sl_07 expected sums to observed (fit property: 1 = fleet rate)', summ['fleet']['tickets'],
            float(cr.expected.sum()), 1e-6)
    S.check('sl_07 z95 = 95% two-sided normal quantile (line label 95%)', NormalDist().inv_cdf(0.975), d['z95'], 1e-5)
    S.check('sl_07 z998 = 99.8% two-sided normal quantile (line label 99.8%)', NormalDist().inv_cdf(0.999),
            d['z998'], 1e-5)
    S.check('sl_07 customers without expected tickets have no tickets', 0, int(cr.tickets[cr.expected <= 0].sum()))
    c = cr[cr.expected > 0].reset_index(drop=True)
    S.check('sl_07 customers plotted = summary', C['customers_with_E'], len(c))
    S.check('sl_07 customers plotted (1,056)', 1056, len(c))
    S.check('sl_07 STR = tickets / expected', 0, float((c.tickets / c.expected - c.STR).abs().max()), 1e-9)

    # Poisson rule recomputed: upper tail, BH over customers with expected > 0, at least min_flag_tickets.
    p = np.array([poisson_upper(o, e) for o, e in zip(c.tickets, c.expected)])
    S.check('sl_07 Poisson p recomputed', 0, float(np.abs(p - c.p_poisson.to_numpy()).max()), 1e-9)
    flag = (c.tickets.to_numpy() >= d['min_flag_tickets']) & (bh(p) < d['q_cut'])
    S.check('sl_07 flagged recomputed = poisson_flagged', 0, int((flag != c.poisson_flagged.to_numpy()).sum()))
    S.check('sl_07 flagged = summary', C['poisson_flagged'], int(flag.sum()))

    # tau^2 recomputed (random-effects moment estimator on winsorised Poisson z), then the funnel z and the customers
    # beyond the 99.8% funnel.
    e_, o_ = c.expected.to_numpy(), c.tickets.to_numpy(float)
    z0 = (np.sqrt(o_ / e_) - 1) * 2 * np.sqrt(e_)
    zw = np.clip(z0, *np.percentile(z0, [10, 90]))
    w = 4 * e_
    tau2 = max(0.0, (len(zw) * np.mean(zw ** 2) - (len(zw) - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    S.check('sl_07 tau^2 recomputed = summary', C['tau2'], tau2, 1e-9)
    z = (np.sqrt(o_ / e_) - 1) / np.sqrt(1 / (4 * e_) + C['tau2'])
    S.check('sl_07 funnel z recomputed = z_d', 0, float(np.abs(z - c.z_d.to_numpy()).max()), 1e-9)
    beyond = z > d['z998']
    S.check('sl_07 beyond the 99.8% funnel recomputed = beyond_funnel_998', 0,
            int((beyond != c.beyond_funnel_998.to_numpy()).sum()))
    S.check('sl_07 beyond the 99.8% funnel = summary', C['flagged_998'], int(beyond.sum()))
    S.check('sl_07 no customer below the 99.8% funnel', 0, int((z < -d['z998']).sum()))
    S.check('sl_07 customers beyond the funnel are flagged (blue)', 0, int((beyond & ~flag).sum()))
    lo998, hi998 = funnel_limits(e_, d['z998'], C['tau2'])
    S.check('sl_07 dots above the drawn 99.8% limit = beyond the funnel', int(beyond.sum()),
            int((c.STR.to_numpy() > hi998).sum()))
    S.check('sl_07 dots below the drawn lower 99.8% limit', 0, int((c.STR.to_numpy() < lo998).sum()))
    S.check('sl_07 tickets = first half + second half', 0, int((c.O_h1 + c.O_h2 != c.tickets).sum()))
    return c, flag, beyond


def plot(out_dir=S.FIG_DIR):
    summ = json.loads((FLEET / 'fx_summary.json').read_text())
    cr = pd.read_csv(FLEET / 'fx_customer_rates.csv')
    c, flag, beyond = checks(summ, cr)
    d, C = summ['definitions'], summ['customers']
    tau2 = C['tau2']

    # Numbers drawn: legend counts, the labelled customer.
    n_flag, n_rest = int(flag.sum()), int((~flag).sum())
    S.check('sl_07 legend: flagged (63)', QUOTED['flagged'], n_flag)
    S.check('sl_07 legend: not flagged (993) = plotted - flagged', 993, len(c) - C['poisson_flagged'])
    S.check('sl_07 legend: not flagged as drawn', 993, n_rest)
    S.check('sl_07 one customer beyond the 99.8% funnel (card header)', QUOTED['beyond'], int(beyond.sum()))
    lab = c[beyond].iloc[0]
    S.check('sl_07 the customer beyond the funnel is Customer 695', 1, int(lab.customer == QUOTED['customer']))
    # "Only 1" is a knife edge, so the label says "just above" and the speaker notes say why: Customer 695 (3 machines,
    # 17 tickets against 3.3 expected) clears the 99.8% limit by under 0.1 STR, and the next customer, Customer 339
    # (a consistent outlier), sits on the line, under 0.001 STR inside it.
    hi_lab = float(funnel_limits([lab.expected], d['z998'], tau2)[1][0])
    S.check('sl_07 Customer 695 just above the 99.8% limit (0 < STR - limit < 0.1)', 1,
            int(0 < lab.STR - hi_lab < 0.1))
    S.check('sl_07 Customer 695: 3 machines (notes)', 3, int(lab.machines))
    S.check('sl_07 Customer 695: 17 tickets (notes)', 17, int(lab.tickets))
    S.check('sl_07 Customer 695: 3.3 expected (notes)', 3.3, lab.expected, 0.05)
    nxt = c[~beyond].sort_values('z_d', ascending=False).iloc[0]
    hi_nxt = float(funnel_limits([nxt.expected], d['z998'], tau2)[1][0])
    S.check('sl_07 next nearest is Customer 339, a consistent outlier (notes)', 1,
            int(nxt.customer == 'Customer 339' and bool(nxt.consistent_outlier)))
    S.check('sl_07 Customer 339 inside the 99.8% limit by under 0.001 STR (notes)', 1,
            int(-0.001 < nxt.STR - hi_nxt < 0))
    S.check('sl_07 Customer 339: 18 tickets against 3.6 expected (notes)', 18 / 3.6, nxt.tickets / nxt.expected, 0.02)

    # Axis ranges as in fx_07; the dots above the top are drawn on the top edge.
    xlo, xhi = c.expected.min() / 1.4, c.expected.max() * X_RIGHT
    ytop = math.ceil(c[c.poisson_flagged | c.consistent_outlier].STR.max() + 0.6)
    S.check('sl_07 y axis top (7) = ceil(highest flagged STR + 0.6)', 7, ytop)
    over = c[c.STR > ytop].sort_values('STR', ascending=False)
    S.check('sl_07 one customer above the top edge', 1, len(over))
    o = over.iloc[0]
    over_txt = f'STR {o.STR:.1f}'
    S.check('sl_07 top-edge STR as drawn (16.2) = tickets / expected', 16.2, o.tickets / o.expected, 0.05)
    S.check('sl_07 top-edge STR as drawn = text', float(over_txt.split()[1]), o.STR, 0.05)
    S.check('sl_07 top-edge customer not flagged (gray)', 0, int(o.poisson_flagged))

    fig, ax = S.figure(S.HALF)
    ax.set_xscale('log')
    ax.set_xlim(xlo, xhi)
    ax.set_ylim(0, ytop)

    # Limits: the fleet rate and the 95% and 99.8% funnel (upper and lower).
    xs = np.logspace(math.log10(xlo), math.log10(xhi), 1500)
    lo95, hi95 = funnel_limits(xs, d['z95'], tau2)
    lo998, hi998 = funnel_limits(xs, d['z998'], tau2)
    ax.axhline(1, color=S.INK2, lw=1.0, zorder=1)
    for lo, hi, lw in ((lo95, hi95, 1.4), (lo998, hi998, 2.2)):
        for yv in (hi, lo):
            ax.plot(xs, yv, color=S.GRAY, lw=lw, zorder=2)
    # Line labels at the right end, above the upper limits (clear of the line over the label's width).
    for text, line in (('99.8% limit', hi998), ('95% limit', hi95)):
        span = line[xs >= xhi / 3.2]
        ax.annotate(text, xy=(xhi, float(span.max())), xytext=(-2, 4), textcoords='offset points', ha='right',
                    va='bottom', fontsize=S.SMALL, color=S.INK2)
    ax.annotate('1 = fleet rate', xy=(xlo, 1), xytext=(4, 4), textcoords='offset points', ha='left', va='bottom',
                fontsize=S.SMALL, color=S.INK2)

    # Dots: gray, then blue; the customer above the top edge as a triangle on it.
    high = (c.STR > ytop).to_numpy()
    y_draw = np.minimum(c.STR, ytop)
    rest = ~flag
    ax.scatter(c.expected[rest & ~high], y_draw[rest & ~high], s=20, color=S.GRAY_LIGHT, edgecolor=S.WHITE,
               linewidth=0.3, zorder=3, clip_on=False)
    ax.scatter(c.expected[rest & high], y_draw[rest & high], s=60, marker='^', color=S.GRAY, linewidth=0,
               zorder=3, clip_on=False)
    ax.scatter(c.expected[flag], c.STR[flag], s=52, color=S.BLUE, edgecolor=S.WHITE, linewidth=0.6, zorder=4,
               clip_on=False)
    ax.annotate(over_txt, xy=(o.expected, ytop), xytext=(-8, -2), textcoords='offset points', ha='right', va='top',
                fontsize=S.SMALL, color=S.INK2)

    # The customer beyond the 99.8% funnel: ring and label in the empty space above the limit, to its right.
    ax.scatter([lab.expected], [lab.STR], s=230, facecolor='none', edgecolor=S.NAVY, linewidth=1.8, zorder=5)
    ax.annotate(lab.customer, xy=(lab.expected, lab.STR), xytext=(lab.expected * 1.9, 6.45), ha='left',
                va='center', fontsize=S.FONT, color=S.INK, weight='bold', zorder=6,
                arrowprops=dict(arrowstyle='-', color=S.INK2, lw=0.9, shrinkA=2, shrinkB=9, relpos=(0, 0.5)))
    ax.annotate('just above the 99.8% limit', xy=(lab.expected * 1.9, 6.45), xytext=(0, -22),
                textcoords='offset points', ha='left', va='center', fontsize=S.SMALL, color=S.INK2, zorder=6)

    ax.set_xticks([t for t in (0.03, 0.1, 0.3, 1, 3, 10, 30, 100) if xlo <= t <= xhi])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.set_yticks(range(0, ytop + 1))
    S.style_axes(ax, grid='y', baseline='bottom')
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlabel('Expected tickets from the customer\'s fleet (log scale)')
    ax.set_ylabel('STR (observed ÷ expected)')
    handles = [Line2D([], [], marker='o', ls='', markersize=10, markerfacecolor=S.BLUE, markeredgewidth=0,
                      label=f'Flagged ({n_flag})'),
               Line2D([], [], marker='o', ls='', markersize=8, markerfacecolor=S.GRAY_LIGHT, markeredgewidth=0,
                      label=f'Not flagged ({n_rest})')]
    ax.legend(handles=handles, loc='lower left', bbox_to_anchor=(0, 1.025), ncol=2, handlelength=1.0,
              handletextpad=0.4, columnspacing=1.6, borderaxespad=0.1, borderpad=0.1, fontsize=S.SMALL)
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
