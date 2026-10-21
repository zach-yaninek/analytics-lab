#!/usr/bin/env python3
"""Fleet chart 8: how concentrated unplanned tickets are across customers, against what their fleets predict.

A few customers always hold a large share of the tickets, if only because a few customers own a large share of the
machines. This chart separates the two. Customers are ranked (most first) and each curve gives the share held by the
top x% of them:
  blue  = unplanned tickets, customers ranked by tickets;
  gray  = expected tickets (the model + age fit of verification/fleet_exposure.py: what each customer's machines would
          generate at fleet rates for their model and age), customers ranked by expected tickets. This is how
          concentrated tickets would be if they followed fleet size, model and age alone;
  shaded = "fleets plus chance": the middle 95% of Poisson draws of each customer's tickets from its expected count,
          each draw ranked afresh: the extra concentration that chance alone adds to the gray curve.
A blue curve above the shaded band means tickets are more concentrated across customers than fleets plus chance
explain. A labelled hairline marks the top TOP% of customers. The title compares the blue share there with the
median of the Poisson draws (what fleets plus chance predict for a ranking of observed counts), not with the gray
curve: ranking noisy counts always adds some concentration, so the gray curve alone would overstate the gap. The
labels give the gray share and the band there too.
The subtitle adds the customers with no unplanned ticket (where the blue curve reaches 100%), how many customers
fleets plus chance would leave with none (the sum of exp(-expected) over customers), and the zero-ticket customers'
expected tickets. No customer is named, so there is no real-name variant.

Each curve ranks customers by its own count, so the top 10% on the blue curve and on the gray curve are not
necessarily the same customers; the comparison is between distributions, not of a customer with its own fleet
(charts fx_06 and fx_07 do that).

Inputs (computed by verification/fleet_exposure.py; nothing is recomputed here except for the checks):
  verification/outputs/fleet/fx_customer_lorenz.csv  customer_share (0..1, step 0.01), ticket_share_obs,
                                                     expected_share, ticket_share_null_median,
                                                     ticket_share_null_p2_5, ticket_share_null_p97_5
  verification/outputs/fleet/fx_customer_rates.csv   tickets, expected, months per customer: independent
                                                     recomputation of both curves, the zero-ticket customers and a
                                                     Monte Carlo check of the chance band
  verification/outputs/fleet/fx_summary.json         period; fleet tickets, customers_with_E and the match counts
                                                     (listed and third-party accounts and tickets) for the checks
Output:  viz/figures/fx_08_customer_concentration.png
Run:     cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_08_customer_concentration.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_08_customer_concentration.png'
TOP = 0.10          # the share of customers the title compares (a grid point of fx_customer_lorenz.csv)
N_CHECK = 1000      # Poisson draws for the independent check of the chance band (not drawn)
BAND_TOL = 0.005    # Monte Carlo tolerance of that check, in share units (0.5 percentage points)


def top_share(x, grid):
    """Share of the total held by the top g share of customers (ranked by x, most first), linear between customers:
    an independent re-implementation of the curves in fx_customer_lorenz.csv."""
    x = np.sort(np.asarray(x, float))[::-1]
    xs = np.arange(len(x) + 1) / len(x)
    ys = np.concatenate([[0.0], np.cumsum(x) / x.sum()])
    return np.interp(grid, xs, ys)


def checks(S, L, c):
    """Recompute everything drawn from fx_customer_rates.csv and fx_summary.json; return the numbers to draw."""
    cc = c[c.months > 0]            # the customers the analysis ranks: those with installed months in the period
    n, tickets, expected = len(cc), int(cc.tickets.sum()), float(cc.expected.sum())
    style.check('fx_08 customers ranked = customers with expected tickets', S['customers']['customers_with_E'], n)
    style.check('fx_08 every ranked customer has expected tickets > 0', 0, int((cc.expected <= 0).sum()))
    style.check('fx_08 tickets = fleet tickets', S['fleet']['tickets'], tickets)
    style.check('fx_08 no tickets at customers without installed months', 0, int(c[c.months <= 0].tickets.sum()))
    style.check('fx_08 expected tickets total = observed (fit property)', tickets, expected, 1e-6)

    grid = L.customer_share.to_numpy()
    style.check('fx_08 grid runs 0 to 1 in steps of 0.01', 0,
                float(np.abs(grid - np.linspace(0, 1, len(grid))).max()) + abs(len(grid) - 101), 1e-12)
    obs, exp_ = top_share(cc.tickets, grid), top_share(cc.expected, grid)
    style.check('fx_08 observed curve = recomputed from customer tickets', 0,
                float(np.abs(obs - L.ticket_share_obs).max()), 1e-9)
    style.check('fx_08 expected curve = recomputed from customer expected', 0,
                float(np.abs(exp_ - L.expected_share).max()), 1e-9)
    i = int(np.flatnonzero(np.isclose(grid, TOP))[0])
    row = L.iloc[i]
    style.check(f'fx_08 observed share of the top {TOP:.0%}', float(top_share(cc.tickets, [TOP])[0]),
                row.ticket_share_obs, 1e-9)
    style.check(f'fx_08 expected share of the top {TOP:.0%}', float(top_share(cc.expected, [TOP])[0]),
                row.expected_share, 1e-9)

    # The chance band: an independent set of Poisson draws (own generator) must give the same percentiles at TOP
    # within Monte Carlo error. Every draw is ranked afresh, as in the analysis.
    rng = np.random.default_rng(fleet.SEED)
    sims = rng.poisson(cc.expected.to_numpy(), size=(N_CHECK, n))
    tops = np.array([top_share(s, [TOP])[0] for s in sims])
    lo, mid, hi = np.percentile(tops, [2.5, 50, 97.5])
    style.check(f'fx_08 chance band low at {TOP:.0%} (independent draws)', row.ticket_share_null_p2_5, lo, BAND_TOL)
    style.check(f'fx_08 chance median at {TOP:.0%} (independent draws)', row.ticket_share_null_median, mid, BAND_TOL)
    style.check(f'fx_08 chance band high at {TOP:.0%} (independent draws)', row.ticket_share_null_p97_5, hi,
                BAND_TOL)
    style.check(f'fx_08 observed above the chance band at {TOP:.0%}', 1,
                int(row.ticket_share_obs > row.ticket_share_null_p97_5))
    style.check('fx_08 band contains its median everywhere', 1,
                int(((L.ticket_share_null_p2_5 <= L.ticket_share_null_median + 1e-12)
                     & (L.ticket_share_null_median <= L.ticket_share_null_p97_5 + 1e-12)).all()))

    # Customers with no unplanned ticket: the blue curve reaches 100% where they begin.
    zero = cc[cc.tickets == 0]
    n_zero, zero_expected = len(zero), float(zero.expected.sum())
    start = (n - n_zero) / n
    style.check('fx_08 observed curve is 100% from the zero-ticket customers on', 1,
                int(np.all(L.ticket_share_obs[grid >= start - 1e-12] >= 1 - 1e-12)
                    and np.all(L.ticket_share_obs[grid < start - 1e-12] < 1)))
    style.check('fx_08 zero-ticket customers\' expected = total - expected of customers with tickets',
                zero_expected, expected - float(cc[cc.tickets > 0].expected.sum()), 1e-6)
    # How many customers fleets plus chance leave at zero: sum of P(0) = exp(-E), against the same Poisson draws.
    zero_chance = float(np.exp(-cc.expected.to_numpy()).sum())
    sim_zeros = (sims == 0).sum(axis=1)
    style.check('fx_08 customers with no ticket under chance: exp(-E) sum = mean of the draws', zero_chance,
                float(sim_zeros.mean()), 1.5)
    style.check('fx_08 observed zero-ticket customers above the 97.5th percentile of the draws', 1,
                int(n_zero > np.percentile(sim_zeros, 97.5)))

    # Above the band: the grid points where the blue curve lies above the shaded band (customer shares > 0).
    inner = (grid > 0) & (L.ticket_share_obs < 1 - 1e-12)
    above_all = bool((L.ticket_share_obs[inner] > L.ticket_share_null_p97_5[inner]).all())
    style.check('fx_08 blue curve above the band wherever it is below 100%', 1, int(above_all))
    return dict(n=n, tickets=tickets, obs=float(row.ticket_share_obs), exp=float(row.expected_share),
                lo=float(row.ticket_share_null_p2_5), mid=float(row.ticket_share_null_median),
                hi=float(row.ticket_share_null_p97_5), n_zero=n_zero,
                zero_share=n_zero / n, zero_expected=zero_expected, zero_chance=zero_chance,
                zero_chance_sim=float(sim_zeros.mean()), start=start,
                obs_re=float(top_share(cc.tickets, [TOP])[0]), exp_re=float(top_share(cc.expected, [TOP])[0]),
                lo_re=float(lo), mid_re=float(mid), hi_re=float(hi))


def drawn(text):
    """'47.1%' -> 0.471: a percentage as drawn, back in share units."""
    return float(text.rstrip('%')) / 100


def plot(out_dir=fleet.FIG_DIR):
    out_dir = Path(out_dir)
    S = fleet.summary()
    L = fleet.load('customer_lorenz')
    c = fleet.load('customer_rates')
    v = checks(S, L, c)

    # ---------------------------------------------------------------------------------------------- Drawing
    fig, ax = style.figure(11.5, 7.6)
    x = 100 * L.customer_share
    # alpha 0.7: at 0.5 the band is the colour of the grid lines (style.GRID) and reads as one of them.
    ax.fill_between(x, 100 * L.ticket_share_null_p2_5, 100 * L.ticket_share_null_p97_5, color=style.GRAY_LIGHT,
                    alpha=0.7, linewidth=0, label='Fleets plus chance: middle 95% of Poisson draws from expected')
    ax.plot(x, 100 * L.expected_share, color=style.GRAY, lw=2, label='Expected tickets (fleet size, model, age)')
    ax.plot(x, 100 * L.ticket_share_obs, color=style.BLUE, lw=2, label='Unplanned tickets')
    x_top = 100 * TOP
    ax.axvline(x_top, color=style.MUTED, lw=0.8, zorder=1)
    y_obs, y_exp = 100 * v['obs'], 100 * v['exp']
    ax.scatter([x_top, x_top], [y_obs, y_exp], s=60, c=[style.BLUE, style.GRAY], edgecolors=style.SURFACE,
               linewidths=1.6, zorder=5)
    # Observed label in the empty area above the blue curve, expected label in the empty area below the gray one,
    # so neither connector crosses a curve; surface-coloured boxes keep grid lines out of the text.
    line = dict(arrowstyle='-', color=style.MUTED, lw=0.8, shrinkA=2, shrinkB=4, relpos=(0, 0.5))
    box = dict(fc=style.SURFACE, ec='none', pad=1)
    ax.annotate(f'Top {x_top:g}% by tickets:\n{style.pct(v["obs"])} of unplanned tickets',
                xy=(x_top, y_obs), xytext=(x_top + 3, 93), fontsize=10, color=style.INK, weight='bold',
                va='center', linespacing=1.35, bbox=box, arrowprops=line)
    ax.annotate(f'Top {x_top:g}% by expected tickets: {style.pct(v["exp"])}\n'
                f'Fleets plus chance: {style.pct(v["mid"])} (band {style.pct(v["lo"])} to {style.pct(v["hi"])})',
                xy=(x_top, y_exp), xytext=(x_top + 5, 32), fontsize=10, color=style.INK2, va='center',
                linespacing=1.35, bbox=box, arrowprops=line)
    style.style_axes(ax, grid='both')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.set_xticks(np.arange(0, 101, 10))
    ax.set_yticks(np.arange(0, 101, 20))
    style.pct_axis(ax.xaxis)
    style.pct_axis(ax.yaxis)
    ax.set_xlabel('Share of customers, ranked most first (by tickets for the blue curve, by expected tickets for '
                  'the gray)')
    ax.set_ylabel('Cumulative share of tickets')
    handles, labels = ax.get_legend_handles_labels()
    order = [2, 1, 0]  # blue, gray, band: the order the reader meets them from the top
    ax.legend([handles[k] for k in order], [labels[k] for k in order], loc='lower right', handlelength=2.2,
              frameon=True, facecolor=style.SURFACE, edgecolor='none', framealpha=1)

    # ---------------------------------------------------------------------------------------------- Text
    # The title compares with the median of the Poisson draws, not the gray curve: ranking noisy counts adds
    # concentration by itself, so "fleets plus chance" is what a ranking of observed tickets should be measured against.
    title = (f'The top {x_top:g}% of customers hold {style.pct(v["obs"], 0)} of unplanned tickets; fleets plus chance '
             f'predict {style.pct(v["mid"], 0)}')
    # Drawn numbers (as rounded on the chart) against the recomputation from fx_customer_rates.csv.
    style.check('fx_08 title: observed share as drawn', drawn(style.pct(v['obs'], 0)), v['obs_re'], 0.005)
    style.check('fx_08 title: chance median as drawn', drawn(style.pct(v['mid'], 0)), v['mid_re'], 0.005 + BAND_TOL)
    style.check('fx_08 title: chance median above the gray share', 1, int(v['mid_re'] > v['exp_re']))
    style.check('fx_08 label: observed share as drawn', drawn(style.pct(v['obs'])), v['obs_re'], 0.0005)
    style.check('fx_08 label: expected share as drawn', drawn(style.pct(v['exp'])), v['exp_re'], 0.0005)
    style.check('fx_08 label: chance median as drawn', drawn(style.pct(v['mid'])), v['mid_re'], 0.0005 + BAND_TOL)
    style.check('fx_08 label: chance band low as drawn', drawn(style.pct(v['lo'])), v['lo_re'], 0.0005 + BAND_TOL)
    style.check('fx_08 label: chance band high as drawn', drawn(style.pct(v['hi'])), v['hi_re'], 0.0005 + BAND_TOL)
    # Subtitle population: every account in the population (listed accounts less the third-party-only ones) is a row
    # of fx_customer_rates.csv; the ones ranked are those with machines in place during the period.
    M = S['match']
    style.check('fx_08 customer rows = listed accounts - third-party-only accounts',
                M['listed accounts'] - M['accounts with only third-party machines (excluded)'], len(c))
    style.check('fx_08 tickets = unplanned tickets on listed machines - third-party tickets',
                M['unplanned tickets on listed machines'] - M['unplanned tickets on third-party machines (excluded)'],
                v['tickets'])
    subtitle = [f'Cumulative share of the {v["tickets"]:,} unplanned tickets on listed machines (blue) and of expected '
                f'tickets (gray) held by the top x% of the {v["n"]:,} customers with machines on IPA\'s '
                f'installed-base list in place during {fleet.period_text(S)} (third-party service plan excluded). '
                f'Shaded, fleets plus chance: how concentrated tickets would look if each customer\'s tickets varied '
                f'only by chance around its expected count.',
                f'The blue curve reaches 100% at {style.pct(v["start"], 0)}: the other {v["n_zero"]} customers '
                f'({style.pct(v["zero_share"], 0)}) had no unplanned ticket, against {v["zero_expected"]:,.0f} '
                f'expected tickets.',
                f'Fleets plus chance would leave about {v["zero_chance"]:,.0f} customers with none.']
    style.check('fx_08 subtitle: customers left at zero by chance as drawn', round(v['zero_chance']),
                v['zero_chance_sim'], 1.5)
    notes = [f'Each curve ranks customers by its own count, so the top {x_top:g}% by tickets and by expected '
             f'tickets are not all the same customers. Expected tickets allow for fleet size, model and age, not '
             f'for service coverage or how a site reports problems; charts fx_06 and fx_07 compare customers one by '
             f'one.',
             'Shaded band: the 2.5th to 97.5th percentile at each customer share over Poisson draws of every '
             'customer\'s tickets from its expected count, each draw ranked afresh; the title and label give the '
             'median.',
             fleet.source('customer_lorenz', 'customer_rates')]
    style.frame(fig, title, subtitle, notes=notes,
                definitions=[fleet.unplanned_definition(), fleet.expected_definition(S)])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
