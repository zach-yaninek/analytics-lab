#!/usr/bin/env python3
"""Slide chart 5: how concentrated unplanned tickets are across customers, against what their fleets predict.

Slide version of viz/fleet_exposure/fx_08_customer_concentration.py, for the slide that replaces the midterm deck's
ranking of sites by raw workload (which did not allow for fleet size). Customers are ranked most first and each curve
gives the cumulative share of the unplanned tickets on listed machines held by the top x% of them:
  blue = observed tickets, customers ranked by tickets;
  gray = fleets plus chance: the median (line) and middle 95% (band) of Poisson draws of every customer's tickets
         from its expected count (model + age fit), each draw ranked afresh.
The top 10% is marked: 47% observed against 39% from fleets plus chance (the page chart's title compares the same
two numbers). The page chart's third curve, expected tickets ranked by expected tickets (37.9% at the top 10%), is
left out: ranking noisy counts adds concentration by itself, so the comparison is with the chance median.

Input:  verification/outputs/fleet/fx_customer_lorenz.csv  (the drawn curves, as in fx_08)
        verification/outputs/fleet/fx_customer_rates.csv   (tickets, expected, months per customer: recomputation)
        verification/outputs/fleet/fx_summary.json         (fleet tickets, customers with expected tickets)
Output: viz/figures/slides/sl_05_concentration.png (half card)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import deck_style as S  # noqa: E402

PNG = 'sl_05_concentration.png'
FLEET = S.OUT / 'fleet'
TOP = 0.10          # the share of customers marked (a grid point of fx_customer_lorenz.csv), as in fx_08
SEED = 15072        # fleet.SEED: the same independent Poisson draws as fx_08's check
N_CHECK = 1000      # Poisson draws for the independent check of the chance curve and band (not drawn)
BAND_TOL = 0.005    # Monte Carlo tolerance of that check, in share units (0.5 percentage points), as in fx_08


def top_share(x, grid):
    """Share of the total held by the top g share of customers (ranked by x, most first), linear between customers:
    the definition of the curves in fx_customer_lorenz.csv (fx_08's re-implementation)."""
    x = np.sort(np.asarray(x, float))[::-1]
    xs = np.arange(len(x) + 1) / len(x)
    ys = np.concatenate([[0.0], np.cumsum(x) / x.sum()])
    return np.interp(grid, xs, ys)


def plot(out_dir=S.FIG_DIR):
    L = pd.read_csv(FLEET / 'fx_customer_lorenz.csv')
    c = pd.read_csv(FLEET / 'fx_customer_rates.csv')
    summ = json.loads((FLEET / 'fx_summary.json').read_text())

    # The population fx_08 ranks: customers with installed months in the period.
    cc = c[c.months > 0]
    n, tickets = len(cc), int(cc.tickets.sum())
    S.check('sl_05 customers ranked (1,056) = customers with expected tickets', summ['customers']['customers_with_E'], n)
    S.check('sl_05 customers ranked as drawn', 1056, n)
    S.check('sl_05 tickets (6,750) = fleet tickets', summ['fleet']['tickets'], tickets)
    S.check('sl_05 tickets as drawn', 6750, tickets)
    S.check('sl_05 no tickets at customers without installed months', 0, int(c[c.months <= 0].tickets.sum()))

    grid = L.customer_share.to_numpy()
    S.check('sl_05 grid runs 0 to 1 in steps of 0.01', 0,
            float(np.abs(grid - np.linspace(0, 1, len(grid))).max()) + abs(len(grid) - 101), 1e-12)
    obs = top_share(cc.tickets, grid)
    S.check('sl_05 observed curve = recomputed from customer tickets', 0,
            float(np.abs(obs - L.ticket_share_obs).max()), 1e-9)

    # The chance curve and band: independent Poisson draws (fx_08's seed), each draw ranked afresh, compared with the
    # CSV's median and percentiles at every grid point within Monte Carlo error.
    rng = np.random.default_rng(SEED)
    sims = rng.poisson(cc.expected.to_numpy(), size=(N_CHECK, n))
    curves = np.array([top_share(s, grid) for s in sims])
    lo, mid, hi = np.percentile(curves, [2.5, 50, 97.5], axis=0)
    S.check('sl_05 chance median curve = independent draws (every grid point)', 0,
            float(np.abs(mid - L.ticket_share_null_median).max()), BAND_TOL)
    S.check('sl_05 chance band low = independent draws (every grid point)', 0,
            float(np.abs(lo - L.ticket_share_null_p2_5).max()), BAND_TOL)
    S.check('sl_05 chance band high = independent draws (every grid point)', 0,
            float(np.abs(hi - L.ticket_share_null_p97_5).max()), BAND_TOL)

    i = int(np.flatnonzero(np.isclose(grid, TOP))[0])
    row = L.iloc[i]
    obs_top, mid_top = 100 * float(row.ticket_share_obs), 100 * float(row.ticket_share_null_median)
    obs_re, mid_re = 100 * float(obs[i]), 100 * float(mid[i])
    obs_txt, mid_txt = f'{obs_top:.0f}%', f'{mid_top:.0f}%'
    S.check('sl_05 drawn observed share of the top 10% (47%)', 47, round(obs_re), 0)
    S.check('sl_05 drawn observed share = recomputed', float(obs_txt[:-1]), obs_re, 0.5)
    S.check('sl_05 drawn chance median at the top 10% (39%)', 39, float(mid_txt[:-1]), 0)
    S.check('sl_05 drawn chance median = independent draws', float(mid_txt[:-1]), mid_re, 0.5 + 100 * BAND_TOL)
    S.check('sl_05 observed above the chance band at the top 10%', 1, int(row.ticket_share_obs > row.ticket_share_null_p97_5))
    S.check('sl_05 chance median above the expected-ticket curve (left out) at the top 10%', 1,
            int(row.ticket_share_null_median > row.expected_share))

    fig, ax = S.figure(S.HALF)
    x = 100 * grid
    ax.fill_between(x, 100 * L.ticket_share_null_p2_5, 100 * L.ticket_share_null_p97_5, color=S.GRAY_LIGHT,
                    linewidth=0, zorder=2)
    ax.plot(x, 100 * L.ticket_share_null_median, color=S.GRAY, lw=2.5, zorder=3)
    ax.plot(x, 100 * L.ticket_share_obs, color=S.BLUE, lw=3.2, zorder=4)
    x_top = 100 * TOP
    ax.axvline(x_top, color=S.BASE, lw=1.0, zorder=1)
    ax.scatter([x_top, x_top], [obs_top, mid_top], s=90, c=[S.BLUE, S.GRAY], edgecolors=S.WHITE, linewidths=2,
               zorder=5)
    line = dict(arrowstyle='-', color=S.INK2, lw=0.9, shrinkA=3, shrinkB=6, relpos=(0, 0.5))
    ax.annotate(f'Observed: {obs_txt}', xy=(x_top, obs_top), xytext=(x_top + 3.5, 93), fontsize=S.FONT,
                color=S.BLUE, weight='bold', va='center', ha='left', arrowprops=line)
    ax.annotate(f'Fleets plus chance: {mid_txt}', xy=(x_top, mid_top), xytext=(x_top + 6, 24), fontsize=S.FONT,
                color=S.INK2, weight='bold', va='center', ha='left', arrowprops=line)
    ax.text(x_top + 1.2, 3, 'Top 10%', fontsize=S.SMALL, color=S.INK2, ha='left', va='bottom')

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.set_xticks(np.arange(20, 101, 20))  # no 0% on x: it would touch the 0% of the y axis
    ax.set_yticks(np.arange(0, 101, 20))
    S.pct_axis(ax.xaxis)
    S.pct_axis(ax.yaxis)
    S.style_axes(ax, grid='both', baseline='bottom')
    ax.set_xlabel(f'Top x% of the {n:,} customers, ranked most first')
    ax.set_ylabel(f'Share of the {tickets:,} unplanned tickets')
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
