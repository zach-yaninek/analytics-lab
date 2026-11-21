#!/usr/bin/env python3
"""Report figure 5 (Results, Customers vs. their fleets): 63 customers exceed their fleets beyond chance (1,732 tickets
vs. 747 expected), and 1 lies outside the normal spread; the top 10% of customers hold 47% of tickets vs. 39% from
their fleets plus chance.

(a) Funnel plot: each of the 1,056 customers with expected tickets, its tickets ÷ expected tickets against its
    expected tickets (log axes; the 251 customers with no ticket sit on the row marked 0, as in figures 2 and 6).
    The 63 customers beyond chance are cobalt. The one outside the normal spread is drawn last with a black edge and
    named from straight above: its three nearest neighbours (18 vs. 3.60, 14 vs. 3.07 and 14 vs. 3.19 expected) sit
    2.0-2.4 pt from it, to its right and below, and the first of them lies 0.02% under the solid limit, so a ring
    round it would hold four customers. Two upper limits, each named by what lies above it:
      dashed, "Beyond chance": where beyond chance begins. A customer is beyond chance when it has at least 5 tickets
              and its one-sided exact Poisson p-value passes Benjamini-Hochberg at q < 0.05 over the 1,056
              customers. With k = 64 customers at q < 0.05, that is p <= t = k x 0.05 / 1,056, so the limit is the
              count c(E) at which the Poisson upper tail P(X >= c | E), continued to real c by the regularized
              incomplete gamma function, equals t, or 5 tickets if that is more. Every cobalt point lies above it and
              every grey point below it, which the checks confirm. It is not what chance alone produces (that is the
              median chance curve in figure 2 and the "Fleets plus chance" curve in (b)). It and the line at 1 end
              just past the last customer, and its name continues it from there; the x-axis runs on to leave room;
      solid, "Normal-spread limit": the 99.8% limit of the funnel widened by the spread between customers,
              (1 + z sqrt(1/(4E) + tau^2))^2 with z = 3.09 and the script's tau^2. Only the black-edged customer lies
              above it.
    Points are anonymous.
(b) Concentration: the share of tickets held by the top x% of the 1,056 customers, ranked most first, observed
    (cobalt) and from their fleets plus chance (dashed: the median over the script's 1,000 Poisson draws of every
    customer's tickets from its expected tickets, each draw ranked afresh; band: their middle 95%), up to the top 40%
    of customers. The top 10% is marked. The observed curve is recomputed from the customers' tickets; the chance curve
    and band come from the script's table, and our own redraw with another seed matches them within 0.3 points at
    10%, as in notebook 04.

Inputs: verification/outputs/fleet/fx_customer_rates.csv (one row per customer, read without its customer column),
fx_customer_lorenz.csv (the script's curves at each 1% of customers), and fx_summary.json (tau^2, z, draws, flag
thresholds, and counts for the checks). Notebook 04 checks the same numbers, and this script reuses its logic.
"""
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig05_customers'
LABEL = 'fig:customers'
SHORT = 'Customers vs. their fleets'

FLEET = S.OUT / 'fleet'
COLS = ['tickets', 'expected', 'months', 'machines', 'z_d', 'p_poisson', 'q_poisson', 'poisson_flagged',
        'beyond_funnel_998']
TOP = 0.10                    # the report's top 10% of customers
SEED = 2026                   # our redraw of the chance benchmark (notebook 04's seed)
ZERO_Y = 0.045                # panel (a): customers with no ticket sit on this row of the log axis, marked 0
LOG_LO = 0.07                 # panel (a): the log part of the y-axis starts here, above the 0 row
LOG_HI = 26                   # panel (a): and ends here, above every customer; the space above holds the readout
Y_TOP = 52                    # panel (a): the top of the axes, with room for the readout above the spine
RATIO_TICKS = [0.1, 0.3, 1, 3, 10]
X_LO, X_HI = 0.018, 500       # panel (a): the x-axis, run on past the last customer to hold the dashed limit's name
END = 1.06                    # panel (a): the dashed limit and the line at 1 end this factor past the last customer
OUT_S, OUT_EDGE = 11, 0.8     # panel (a): the customer outside the normal spread, a cobalt dot with a black edge (pt)
X_MAX = 0.40                  # panel (b): the curves up to the top 40% of customers


# ----------------------------------------------------------------------------------------------------------------
# Notebook 04's tests, reused: the Poisson upper tail, Benjamini-Hochberg, the funnel, and the top share
# ----------------------------------------------------------------------------------------------------------------
def poisson_upper(k, mu):
    """P(X >= k) for X ~ Poisson(mu) with mu > 0, summed over the upper tail so tiny p-values stay accurate."""
    k = int(k)
    if k <= 0:
        return 1.0
    if k <= mu:
        return max(0.0, 1.0 - sum(math.exp(-mu + j * math.log(mu) - math.lgamma(j + 1)) for j in range(k)))
    term = math.exp(-mu + k * math.log(mu) - math.lgamma(k + 1))
    total, j = term, k
    while term > total * 1e-17:
        j += 1
        term *= mu / j
        total += term
    return min(1.0, total)


def bh(p):
    """Benjamini-Hochberg q-values over the p-values that are not NaN."""
    p = np.asarray(p, float)
    q = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    n = int(ok.sum())
    order = np.argsort(p[ok], kind='mergesort')
    ranked = p[ok][order] * n / np.arange(1, n + 1)
    q_ok = np.empty(n)
    q_ok[order] = np.minimum(np.minimum.accumulate(ranked[::-1])[::-1], 1.0)
    q[ok] = q_ok
    return q


def funnel(observed, expected, winsor=0.10):
    """Overdispersion-adjusted funnel scores z_D and tau^2 (Spiegelhalter 2005, square-root scale)."""
    O, E = np.asarray(observed, float), np.asarray(expected, float)
    ok = E > 0
    y, s = np.sqrt(O[ok] / E[ok]), 1 / (2 * np.sqrt(E[ok]))
    z = (y - 1) / s
    zw = np.clip(z, *np.percentile(z, [100 * winsor, 100 * (1 - winsor)]))
    w, n = 1 / s ** 2, int(ok.sum())
    tau2 = max(0.0, (n * np.mean(zw ** 2) - (n - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    zd = np.full(len(O), np.nan)
    zd[ok] = (y - 1) / np.sqrt(s ** 2 + tau2)
    return zd, tau2


def top_share(x, share=TOP):
    """Share of the total held by the top share of units, ranked by value and interpolated between whole units, as
    on the script's curve in fx_customer_lorenz.csv."""
    x = np.sort(np.asarray(x, float))[::-1]
    curve = np.concatenate([[0.0], np.cumsum(x) / x.sum()])
    return np.interp(share, np.linspace(0, 1, len(x) + 1), curve)


# ----------------------------------------------------------------------------------------------------------------
# The beyond-chance limit: the Poisson upper tail continued to real counts
# ----------------------------------------------------------------------------------------------------------------
def upper_tail(a, x):
    """P(a, x), the regularized lower incomplete gamma function, for real a > 0 and x > 0. For a whole number a it is
    the Poisson upper tail P(X >= a | x): a series below a + 1, a continued fraction (Lentz) above."""
    log_front = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1:
        term = total = 1.0 / a
        n = 0
        while term > total * 1e-16:
            n += 1
            term *= x / (a + n)
            total += term
        return min(1.0, total * math.exp(log_front))
    tiny = 1e-300
    b = x + 1 - a
    c, d = 1 / tiny, 1 / b
    h, i = d, 0
    while True:
        i += 1
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1 / (d if abs(d) > tiny else tiny)
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return 1.0 - math.exp(log_front) * h


def chance_count(E, t):
    """The real count c at which P(X >= c | E) = t: tickets at or above it are improbably many at that cut."""
    lo, hi = 1e-6, E + 60 * math.sqrt(E) + 60
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if upper_tail(mid, E) > t else (lo, mid)
    return (lo + hi) / 2


def zero_log_axis(axis, zero_at, ticks):
    """A log axis whose first tick, at zero_at below the data range, reads 0 (figures 2 and 6)."""
    axis.set_major_locator(FixedLocator([zero_at] + list(ticks)))
    axis.set_major_formatter(FuncFormatter(lambda v, _: '0' if math.isclose(v, zero_at) else f'{v:g}'))
    axis.set_minor_locator(NullLocator())


def gap_to_points(fig, ax, artist, x, y, sizes):
    """The smallest gap in points between an artist's box, in the final layout, and markers of the given areas (pt^2)
    at (x, y) in ax's data coordinates; negative where a marker reaches into the box."""
    fig.canvas.draw()
    box = artist.get_window_extent(fig.canvas.get_renderer())
    pts = ax.transData.transform(np.c_[x, y])
    dx = np.maximum(np.maximum(box.x0 - pts[:, 0], 0), pts[:, 0] - box.x1)
    dy = np.maximum(np.maximum(box.y0 - pts[:, 1], 0), pts[:, 1] - box.y1)
    return float((np.hypot(dx, dy) * 72 / fig.dpi - np.sqrt(sizes) / 2).min())


def plot(out_dir=S.FIG_DIR):
    summary = json.loads((FLEET / 'fx_summary.json').read_text())
    defs, cs = summary['definitions'], summary['customers']
    customers = pd.read_csv(FLEET / 'fx_customer_rates.csv', usecols=COLS)
    lorenz = pd.read_csv(FLEET / 'fx_customer_lorenz.csv')
    S.check('fig05 one row per customer in the population', summary['fleet']['accounts'], len(customers))
    S.check('fig05 customer tickets = fleet tickets', summary['fleet']['tickets'], int(customers.tickets.sum()))
    S.check('fig05 customers without expected tickets have no tickets', 0,
            int(customers.tickets[customers.expected <= 0].sum()))
    c = customers[customers.expected > 0].reset_index(drop=True)
    n = len(c)
    S.check('fig05 customers with expected tickets = fx_summary.json', cs['customers_with_E'], n)
    S.check('fig05 the customers with installed months are those with expected tickets', 1,
            int(((customers.months > 0) == (customers.expected > 0)).all()))
    S.check('fig05 (a) the customers drawn are those with machines in the fleet', 1,
            int(((customers.machines > 0) == (customers.expected > 0)).all()
                and customers.machines.sum() == summary['fleet']['machines_exposed']))
    O, E = c.tickets.to_numpy(float), c.expected.to_numpy(float)
    ratio = O / E
    S.check('fig05 (a) customers on the 0 row (docstring)', 251, int((O == 0).sum()))

    # Beyond chance (notebook 04): one-sided exact Poisson p, Benjamini-Hochberg, and at least 5 tickets
    p = np.array([poisson_upper(o, e) for o, e in zip(O, E)])
    q = bh(p)
    q_cut, min_tickets = defs['q_cut'], defs['min_flag_tickets']
    flagged = (O >= min_tickets) & (q < q_cut)
    S.check('fig05 p-values = fx_customer_rates.csv', 0, float(np.abs(p - c.p_poisson).max()), 1e-9)
    S.check('fig05 q-values = fx_customer_rates.csv', 0, float(np.abs(q - c.q_poisson).max()), 1e-9)
    S.check('fig05 flags = fx_customer_rates.csv', 0, int((flagged != c.poisson_flagged).sum()))
    S.check('fig05 flagged customers = fx_summary.json', cs['poisson_flagged'], int(flagged.sum()))
    n_flagged = int(flagged.sum())
    flagged_tickets, flagged_expected = int(O[flagged].sum()), float(E[flagged].sum())

    # Outside the normal spread (notebook 04): above the 99.8% limit of the funnel widened by tau^2
    z_d, tau2 = funnel(O, E)
    z998 = defs['z998']
    beyond = z_d > z998
    S.check('fig05 tau^2 = fx_summary.json', cs['tau2'], tau2, 1e-12)
    S.check('fig05 funnel scores = fx_customer_rates.csv', 0, float(np.abs(z_d - c.z_d).max()), 1e-9)
    S.check('fig05 outside the normal spread = fx_customer_rates.csv', 0, int((beyond != c.beyond_funnel_998).sum()))
    S.check('fig05 outside the normal spread = fx_summary.json', cs['flagged_998'], int(beyond.sum()))
    S.check('fig05 the customer outside the normal spread is beyond chance', 0, int((beyond & ~flagged).sum()))
    n_beyond = int(beyond.sum())

    # The two drawn limits put the same customers above them
    k = int((q < q_cut).sum())
    t = k * q_cut / n                          # the Benjamini-Hochberg cut on the p-values
    S.check('fig05 customers at q < 0.05, one with fewer than 5 tickets = fx_summary.json',
            cs['poisson_q_lt_0.05_high'], k)
    S.check('fig05 p <= the BH cut exactly where q < 0.05', 0, int(((p <= t) != (q < q_cut)).sum()))
    for a, x in ((1, 0.3), (5, 1.0), (9, 1.43), (17, 3.28), (40, 25.0), (114, 102.0)):
        S.check(f'fig05 the continued tail = the Poisson tail at {a} tickets vs. {x} expected',
                poisson_upper(a, x), upper_tail(a, x), 1e-12)
    chance_at = np.array([max(chance_count(e, t), min_tickets) / e for e in E])
    S.check('fig05 every customer beyond chance is above the dashed limit', 1, int((ratio[flagged] > chance_at[flagged])
                                                                                    .all()))
    S.check('fig05 every other customer is below it', 1, int((ratio[~flagged] < chance_at[~flagged]).all()))
    spread_at = (1 + z998 * np.sqrt(1 / (4 * E) + tau2)) ** 2
    S.check('fig05 the customers above the solid limit = outside the normal spread', 0,
            int(((ratio > spread_at) != beyond).sum()))
    S.check('fig05 z998 = the 99.8% two-sided normal quantile', NormalDist().inv_cdf(0.999), z998, 1e-5)

    # (b) The top 10% (notebook 04): observed, recomputed; fleets plus chance from the script's 1,000 draws
    top_obs = float(top_share(O))
    grid = lorenz.customer_share.to_numpy()
    S.check('fig05 the script\'s grid runs 0 to 1 in steps of 0.01', 0,
            float(np.abs(grid - np.linspace(0, 1, len(grid))).max()) + abs(len(grid) - 101), 1e-12)
    obs_curve = top_share(O, grid)
    S.check('fig05 observed curve = fx_customer_lorenz.csv', 0,
            float(np.abs(obs_curve - lorenz.ticket_share_obs).max()), 1e-9)
    at10 = lorenz[np.isclose(lorenz.customer_share, TOP)].iloc[0]
    chance_share = float(at10.ticket_share_null_median)
    S.check('fig05 observed top 10% = fx_customer_lorenz.csv', at10.ticket_share_obs, top_obs, 1e-9)
    draws = np.random.default_rng(SEED).poisson(E, size=(summary['n_null'], n))
    redraw = np.array([top_share(d) for d in draws])
    for name, ours, theirs in (('median', np.median(redraw), chance_share),
                               ('2.5th percentile', np.percentile(redraw, 2.5), at10.ticket_share_null_p2_5),
                               ('97.5th percentile', np.percentile(redraw, 97.5), at10.ticket_share_null_p97_5)):
        S.check(f'fig05 our redraw\'s {name} at 10% = the script\'s, within 0.3 points', theirs, ours, 0.003)
    S.check('fig05 caption: the band is the middle 95% (the 2.5th to 97.5th percentiles of the draws)', 1,
            int({'ticket_share_null_p2_5', 'ticket_share_null_p97_5'} <= set(lorenz.columns)))
    S.check('fig05 the band holds its median everywhere', 1,
            int(((lorenz.ticket_share_null_p2_5 <= lorenz.ticket_share_null_median + 1e-12)
                 & (lorenz.ticket_share_null_median <= lorenz.ticket_share_null_p97_5 + 1e-12)).all()))
    S.check('fig05 observed above the band at the top 10%', 1, int(top_obs > at10.ticket_share_null_p97_5))

    S.report_check('fig05 customers beyond chance', '63', S.num(n_flagged))
    S.report_check('fig05 their tickets', '1,732', S.num(flagged_tickets))
    S.report_check('fig05 their expected tickets', '747', S.num(flagged_expected))
    S.report_check('fig05 customers outside the normal spread', '1', S.num(n_beyond))
    S.report_check('fig05 the top share of customers', '10%', S.pct(TOP))
    S.report_check('fig05 their share of tickets', '47%', S.pct(top_obs))
    S.report_check('fig05 the same share from their fleets plus chance', '39%', S.pct(chance_share))

    fig, (ax, bx) = S.figure(2.1, ncols=2, width_ratios=[1.4, 1])

    # (a) the funnel: log axes, the customers with no ticket on the 0 row
    ys = np.where(O > 0, ratio, ZERO_Y)
    S.check('fig05 (a) every customer with a ticket above the 0 row', 1, int(ratio[O > 0].min() > LOG_LO))
    x_lo, x_hi = X_LO, X_HI
    e_end = END * E.max()     # where the dashed limit and the line at 1 end, just past the last customer
    es = np.logspace(math.log10(x_lo), math.log10(x_hi), 700)
    ed = np.logspace(math.log10(x_lo), math.log10(e_end), 600)
    spread_line = (1 + z998 * np.sqrt(1 / (4 * es) + tau2)) ** 2
    chance_line = np.array([max(chance_count(e, t), min_tickets) / e for e in ed])
    # each limit ends at the top where the y-axis does, below the readout
    ax.plot(es, np.where(spread_line <= LOG_HI, spread_line, np.nan), color=S.GREY_DARK, lw=1.0, zorder=2)
    ax.plot(ed, np.where(chance_line <= LOG_HI, chance_line, np.nan), color=S.GREY_DARK, lw=1.0, ls=(0, (4, 2.5)),
            zorder=2)
    ax.plot([x_lo, e_end], [1, 1], color=S.GRID, lw=0.8, zorder=1)
    ax.scatter(E[~flagged], ys[~flagged], s=5, color=S.GREY, alpha=0.55, linewidths=0, zorder=3)
    # the customer outside the normal spread is drawn last, on its own: a ring round it would hold three more cobalt
    # customers 2.0-2.4 pt away, to its right and below, one of them on the solid limit
    (i_out,) = np.flatnonzero(beyond)
    plain = flagged & ~beyond
    ax.scatter(E[plain], ys[plain], s=11, color=S.COBALT, linewidths=0, zorder=4)
    ax.scatter(E[i_out], ys[i_out], s=OUT_S, color=S.COBALT, edgecolors=S.TEXT, linewidths=OUT_EDGE, zorder=6)
    S.check('fig05 (a) cobalt customers drawn = beyond chance', n_flagged, int(plain.sum()) + 1)
    # named from straight above, in the empty space over the normal-spread limit: the leader comes down to the edge of
    # its dot, away from its neighbours
    ax.annotate('Outside the\nnormal spread', xy=(E[i_out], ys[i_out]), xytext=(E[i_out], 13), textcoords='data',
                ha='center', va='bottom', fontsize=S.TICK, linespacing=1.0,
                arrowprops=dict(arrowstyle='-', color=S.TEXT, lw=0.5, shrinkA=1,
                                shrinkB=(math.sqrt(OUT_S) + OUT_EDGE) / 2 + 0.6))
    # the one green readout, top right above the limits: the customers beyond chance (their tickets vs. expected are
    # in the caption)
    x_text = x_hi / 1.06
    t1 = S.label(ax, x_text, Y_TOP * 0.93, ' beyond chance', ha='right', va='top', size=S.FONT)
    ax.annotate(S.num(n_flagged), xy=(0, 1), xycoords=t1, ha='right', va='top', fontsize=S.FONT, fontweight='bold',
                color=S.GREEN)
    # the limits, each named by what lies above it: the solid one just above its right end (the descender of 'p'
    # clear of it); the dashed one where it ends, the line running into 'chance', the name's bottom just above the line
    # at 1 (which it does not name) and its top under the solid limit
    spread_name = S.label(ax, x_text, 4.6, 'Normal-spread limit', ha='right', va='bottom')
    y_end = max(chance_count(e_end, t), min_tickets) / e_end
    beyond_name = S.label(ax, e_end * 1.13, 1.06, 'Beyond\nchance', ha='left', va='bottom', linespacing=1.0)
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(0.032, Y_TOP)
    ax.xaxis.set_major_locator(FixedLocator([0.1, 1, 10, 100]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.xaxis.set_minor_locator(NullLocator())
    zero_log_axis(ax.yaxis, ZERO_Y, RATIO_TICKS)
    ax.spines['left'].set_bounds(LOG_LO, LOG_HI)
    ax.set_xlabel('Expected tickets (log scale)')
    ax.set_ylabel('Tickets ÷ expected\n(log scale)')
    S.clean(ax)
    S.panel(ax, 'a', 'Customers vs. their fleets')

    # (b) concentration: observed (recomputed, fine grid) and fleets plus chance (the script's 1% grid)
    fine = np.linspace(0, X_MAX, 401)
    sel = grid <= X_MAX + 1e-12
    bx.fill_between(grid[sel], lorenz.ticket_share_null_p2_5[sel], lorenz.ticket_share_null_p97_5[sel],
                    color=S.GREY_FILL, linewidth=0, zorder=2)
    bx.plot(grid[sel], lorenz.ticket_share_null_median[sel], color=S.GREY_DARK, lw=1.2, ls=(0, (4, 2.5)), zorder=3)
    bx.plot(fine, top_share(O, fine), color=S.COBALT, lw=1.5, zorder=4)
    # the top 10%: a guide line, the two shares joined, as in figure 2
    blank = dict(fc=S.WHITE, ec='none', pad=0.8)   # keeps the light grid out of a label
    bx.plot([TOP, TOP], [0, chance_share], color=S.GRID, lw=0.8, zorder=1)
    bx.plot([TOP, TOP], [chance_share, top_obs], color=S.GREY_DARK, lw=0.6, zorder=2)
    bx.plot(TOP, top_obs, 'o', color=S.COBALT, ms=4, zorder=5)
    bx.plot(TOP, chance_share, 'o', mfc=S.WHITE, mec=S.GREY_DARK, mew=1.0, ms=4, zorder=5)
    obs_text, chance_text = S.pct(top_obs), S.pct(chance_share)
    S.check(f'fig05 (b) label {obs_text}', round(100 * top_obs), float(obs_text.rstrip('%')))
    S.check(f'fig05 (b) label {chance_text}', round(100 * chance_share), float(chance_text.rstrip('%')))
    S.label(bx, TOP - 0.01, top_obs + 0.025, obs_text, ha='right', va='bottom', bbox=blank, zorder=6)
    S.label(bx, TOP + 0.01, chance_share - 0.03, chance_text, ha='left', va='top', bbox=blank, zorder=6)
    S.label(bx, TOP + 0.007, 0.02, f'Top {S.pct(TOP)}', ha='left', va='bottom')
    xo, xc = 0.19, 0.21   # each label between two gridlines
    S.label(bx, xo - 0.006, float(top_share(O, xo)) + 0.035, 'Observed', ha='right', va='bottom', bbox=blank,
            zorder=6)
    S.label(bx, xc + 0.006, float(np.interp(xc, grid, lorenz.ticket_share_null_p2_5)) - 0.035, 'Fleets plus chance',
            ha='left', va='top', bbox=blank, zorder=6)
    bx.set_xlim(0, X_MAX)
    bx.set_ylim(0, 1)
    bx.set_xticks([0, 0.1, 0.2, 0.3, 0.4])
    bx.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    S.pct_axis(bx.xaxis)
    S.pct_axis(bx.yaxis)
    bx.set_xlabel('Customers, most tickets first')
    bx.set_ylabel('Share of tickets')
    S.clean(bx, grid='y')
    S.panel(bx, 'b', 'Concentration of tickets')

    # Nothing drawn is clipped
    S.check('fig05 (a) every customer inside the axes', 1,
            int(E.min() > x_lo and E.max() < x_hi and ratio.max() < LOG_HI))
    S.check('fig05 (b) curves inside the axes', 1, int(float(top_share(O, X_MAX)) < 1))

    # Panel (a)'s marks, in the final layout (points at final size)
    sizes = np.where(flagged, 11.0, 5.0)
    sizes[i_out] = (math.sqrt(OUT_S) + OUT_EDGE) ** 2
    others = np.arange(n) != i_out
    gap = gap_to_points(fig, ax, beyond_name, E, ys, sizes)
    S.check('fig05 (a) the name "Beyond chance" clears every customer by 1 pt', 1, int(gap > 1))
    box = beyond_name.get_window_extent(fig.canvas.get_renderer()).transformed(ax.transData.inverted())
    S.check('fig05 (a) the name "Beyond chance" lies right of the dashed limit\'s end, inside the axes, under the '
            'solid limit', 1, int(e_end < box.x0 and box.x1 < x_hi and box.y0 < y_end < box.y1
                                  and box.y1 < spread_line[(es >= box.x0) & (es <= box.x1)].min()))
    p = ax.transData.transform(np.c_[E, ys]) * 72 / fig.dpi
    dist = np.hypot(*(p - p[i_out]).T)
    near = np.argsort(dist)[1:4]
    S.report_check('fig05 (a) docstring: the three customers nearest the black-edged one',
                   '18 vs. 3.60, 14 vs. 3.07 and 14 vs. 3.19',
                   f'{O[near[0]]:.0f} vs. {E[near[0]]:.2f}, {O[near[1]]:.0f} vs. {E[near[1]]:.2f} and '
                   f'{O[near[2]]:.0f} vs. {E[near[2]]:.2f}')
    S.report_check('fig05 (a) docstring: they lie 2.0-2.4 pt from it, all below it', '2.0-2.4 pt, all below',
                   f'{dist[near].min():.1f}-{dist[near].max():.1f} pt, '
                   + ('all below' if (p[near, 1] < p[i_out, 1]).all() else 'not all below'))
    S.report_check('fig05 (a) docstring: the nearest lies 0.02% under the solid limit', '0.02% under',
                   f'{100 * (1 - ratio[near[0]] / spread_at[near[0]]):.2f}% under')
    box = spread_name.get_window_extent(fig.canvas.get_renderer()).transformed(ax.transData.inverted())
    S.check('fig05 (a) the name "Normal-spread limit" lies above its line, inside the axes', 1,
            int(box.y0 > spread_line[(es >= box.x0) & (es <= box.x1)].max() and box.x1 < x_hi))
    top = ax.transData.transform((E[i_out], 13))[1] * 72 / fig.dpi
    strip = others & (np.abs(p[:, 0] - p[i_out, 0]) < np.sqrt(sizes) / 2 + 0.5) & (p[:, 1] > p[i_out, 1]) & \
        (p[:, 1] < top)
    S.check('fig05 (a) the leader comes straight down to it, clear of every other customer', 0, int(strip.sum()))

    S.export(fig, NAME, out_dir)
    pc = lambda share: S.pct(share).replace('%', chr(92) + '%')  # noqa: E731
    return (f'{S.num(n_flagged)} customers exceed their fleets beyond chance ({S.num(flagged_tickets)} tickets vs. '
            f'{S.num(flagged_expected)} expected), and {S.num(n_beyond)} lies outside the normal spread; the top '
            f'{pc(TOP)} of customers hold {pc(top_obs)} of tickets vs. {pc(chance_share)} from their fleets plus '
            f'chance. '
            f'(a)~{S.num(n)} customers; (b)~band, the middle 95\\% of {S.num(summary["n_null"])} chance draws.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
