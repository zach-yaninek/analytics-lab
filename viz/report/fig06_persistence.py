#!/usr/bin/env python3
"""Report figure 6 (Results, Persistence and outliers): customers above their fleets in the first half tend to stay
above them in the second (rank correlation 0.46 vs. 0.04 when shuffled), and machines with 3 or more first-half
tickets had 2.6 times their expected tickets in the second half; 18 customers and 36 machines are consistent
outliers; of the 106 chronic outliers on IPA's list, 93 stay flagged; and no flagged machine stands out as a separate
group.

(a) Each customer's tickets ÷ expected tickets in the first half against the second (log axes; a customer with no
    tickets in a half sits on the row or column marked 0), for the 311 customers expected to have at least 3 tickets
    in each half (the rank correlation's customers) and the 8 other consistent outliers. The 18 consistent outliers
    are cobalt. Points are anonymous. The shuffled value replays the script's 1,000 permutations with its seed.
(b) Machines installed in both halves, by first-half tickets (0, 1, 2, 3 or more): second-half tickets ÷ expected,
    with 95% cluster-bootstrap intervals over customers; only the focal 3-or-more bar is labelled. The 0 row comes
    from the script's table; the other rows are recounted from the machine table, and the 3-or-more interval replays
    the script's bootstrap weights, which reproduce the table's 1, 2, 3, and 4+ intervals.
(c) The 106 chronic outliers on IPA's list, 93 of them still flagged, and the 128 flagged machines, 36 of them
    consistent outliers; none of the flagged machines keeps q < 0.05 under the negative binomial.

Inputs: verification/outputs/fleet/fx_customer_rates.csv (one row per customer), fx_machine_flags.csv (one row per
fleet machine with a ticket or among the 113), fx_outlier_persistence.csv and fx_outlier_machine_persistence.csv (the
script's persistence statistics, for the checks and the 0-ticket row), fx_summary.json (seed, shuffles, bootstrap
draws, definitions, and counts for the checks), and htm_device_exposure.csv (the 113 chronic outliers). Notebook 04
checks the same numbers, and this script reuses its logic. The customer column only groups machines into the
bootstrap's clusters and orders the customers as the script does; it is never drawn.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import patheffects as pe  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig06_persistence'
LABEL = 'fig:persistence'
SHORT = 'Persistence and outliers'

MIN_E_HALF = 3      # the rank correlation's customers: at least 3 expected tickets in each half
CUT = 3             # the report's machines: 3 or more first-half tickets
P_HALF = 0.05       # consistent outliers: one-sided Poisson p below this in each half
LEVEL = 95          # panel (b): the bootstrap intervals' level, in percent (the script's 2.5th to 97.5th percentiles)
ZERO = 0.05         # panel (a): a ratio of 0 is drawn here, below the log range, and marked 0
LOG_LO, LOG_HI = 0.085, 40
RATIO_TICKS = [0.25, 0.5, 1, 2, 4, 8]


# ----------------------------------------------------------------------------------------------------------------
# Notebook 04's tests, reused: the Poisson upper tail and Benjamini-Hochberg over the p-values that are not NaN
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


def upper_p(observed, expected):
    """One-sided Poisson p-values; NaN where nothing is expected (those units are not tested)."""
    return np.array([poisson_upper(o, e) if e > 0 else np.nan for o, e in zip(observed, expected)])


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


def zero_log_axis(axis, zero_at, ticks):
    """A log axis whose first tick, at zero_at below the data range, reads 0 (for ratios of zero)."""
    axis.set_major_locator(FixedLocator([zero_at] + list(ticks)))
    axis.set_major_formatter(FuncFormatter(lambda v, _: '0' if math.isclose(v, zero_at) else f'{v:g}'))
    axis.set_minor_locator(NullLocator())


def plot(out_dir=S.FIG_DIR):
    fleet = S.OUT / 'fleet'
    summary = json.loads((fleet / 'fx_summary.json').read_text())
    customers = pd.read_csv(fleet / 'fx_customer_rates.csv',
                            usecols=['customer', 'machines', 'months', 'O_h1', 'E_h1', 'O_h2', 'E_h2',
                                     'variants_flagged', 'consistent_outlier'])
    machines = pd.read_csv(fleet / 'fx_machine_flags.csv',
                           usecols=['serial_id', 'customer', 'months_h1', 'months_h2', 'tickets', 'tickets_h1',
                                    'tickets_h2', 'expected', 'expected_h1', 'expected_h2', 'q_poisson', 'q_nb',
                                    'flagged', 'variants_flagged', 'consistent_outlier', 'in_docs05_113'])
    persistence = pd.read_csv(fleet / 'fx_outlier_persistence.csv').set_index('statistic')
    by_count = pd.read_csv(fleet / 'fx_outlier_machine_persistence.csv', dtype={'first_half_tickets': str})
    by_count = by_count.set_index('first_half_tickets')
    htm = pd.read_csv(S.OUT / 'htm_device_exposure.csv', usecols=['serial_id', 'class'])
    assert customers.customer.is_unique and machines.serial_id.is_unique

    # ---- (a) customers' tickets ÷ expected tickets by half; the rank correlation and its shuffled benchmark ----
    both_halves = customers[(customers.E_h1 >= MIN_E_HALF) & (customers.E_h2 >= MIN_E_HALF)].sort_values('customer')
    str_h1 = (both_halves.O_h1 / both_halves.E_h1).to_numpy()
    str_h2 = (both_halves.O_h2 / both_halves.E_h2).to_numpy()
    rank_h1, rank_h2 = (pd.Series(s).rank().to_numpy() for s in (str_h1, str_h2))
    dev_h1, dev_h2 = rank_h1 - rank_h1.mean(), rank_h2 - rank_h2.mean()
    scale = np.sqrt((dev_h1 @ dev_h1) * (dev_h2 @ dev_h2))
    rho = float(dev_h1 @ dev_h2 / scale)
    tenth = pd.qcut(both_halves.E_h2.rank(method='first'), 10, labels=False).to_numpy()
    tenths = [np.where(tenth == g)[0] for g in range(10)]
    rng = np.random.default_rng(summary['seed'])  # the script's own shuffles are the generator's first draws
    idx = np.tile(np.arange(len(both_halves)), (summary['n_null'], 1))
    for row in idx:
        for sel in tenths:
            row[sel] = rng.permutation(sel)
    rho_null = float(np.median(dev_h2[idx] @ dev_h1 / scale))
    sp = persistence.loc['spearman_STR_h1_h2']
    S.check('fig06 customers in the rank correlation = script', int(sp.units), len(both_halves))
    S.check('fig06 rank correlation = script', float(sp.observed), rho, 1e-9)
    S.check('fig06 shuffled rank correlation (replay) = script', float(sp.perm_null_median), rho_null, 1e-9)
    S.check('fig06 shuffles = 1,000', 1000, summary['n_null'])

    # ---- consistent outliers: flagged in 10+ of 12 variations and p < 0.05 in each half ----
    min_variants = summary['definitions']['min_variants']
    p1_c, p2_c = upper_p(customers.O_h1, customers.E_h1), upper_p(customers.O_h2, customers.E_h2)
    consistent_c = (customers.variants_flagged >= min_variants) & (p1_c < P_HALF) & (p2_c < P_HALF)
    p1_m = upper_p(machines.tickets_h1, machines.expected_h1)
    p2_m = upper_p(machines.tickets_h2, machines.expected_h2)
    consistent_m = (machines.variants_flagged >= min_variants) & (p1_m < P_HALF) & (p2_m < P_HALF)
    S.check('fig06 consistent customers = script', 0, int((consistent_c != customers.consistent_outlier).sum()))
    S.check('fig06 consistent machines = script', 0, int((consistent_m != machines.consistent_outlier).sum()))
    n_consistent_c, n_consistent_m = int(consistent_c.sum()), int(consistent_m.sum())
    S.check('fig06 consistent customers = summary', summary['customers']['consistent_outliers'], n_consistent_c)
    S.check('fig06 consistent machines = summary', summary['machines']['consistent_outliers'], n_consistent_m)
    in_corr = (customers.E_h1 >= MIN_E_HALF) & (customers.E_h2 >= MIN_E_HALF)
    n_other_consistent = int((consistent_c & ~in_corr).sum())
    S.check('fig06 consistent customers outside the correlation are above 0 in both halves', n_other_consistent,
            int((consistent_c & ~in_corr & (customers.O_h1 > 0) & (customers.O_h2 > 0)).sum()))

    # ---- (b) machines in both halves by first-half tickets: second-half tickets ÷ expected ----
    both = machines[(machines.months_h1 > 0) & (machines.months_h2 > 0)]
    S.check('fig06 every listed machine with first-half months has second-half months', 0,
            int(((machines.months_h1 > 0) & (machines.months_h2 <= 0)).sum()))
    h1 = both.tickets_h1.to_numpy()
    o2, e2 = both.tickets_h2.to_numpy(float), both.expected_h2.to_numpy(float)
    groups = [('0', None), ('1', h1 == 1), ('2', h1 == 2), (f'{CUT} or more', h1 >= CUT)]
    ratio_3 = o2[h1 >= CUT].sum() / e2[h1 >= CUT].sum()
    stat = persistence.loc[f'second_half_ratio_if_{CUT}plus_first_half']
    S.check('fig06 machines with 3 or more first-half tickets = script', int(stat.units), int((h1 >= CUT).sum()))
    S.check('fig06 their second-half ratio = script', float(stat.observed), ratio_3, 1e-9)
    for name in ('1', '2', '3', '4+'):
        sel = (h1 >= 4) if name == '4+' else (h1 == int(name))
        S.check(f'fig06 machines with {name} first-half tickets (recount)', by_count.loc[name, 'machines'],
                int(sel.sum()))
        S.check(f'fig06 second-half ratio, {name} first-half tickets (recount)',
                by_count.loc[name, 'second_half_ratio'], o2[sel].sum() / e2[sel].sum(), 1e-9)
    # The 0 row holds machines without a ticket, which the machine table leaves out: its tickets are recounted two
    # ways and its expected tickets bounded (each half's fit gives as many expected tickets as tickets).
    zero = by_count.loc['0']
    h2_only = machines[machines.months_h1 <= 0]
    S.check('fig06 second-half tickets, 0 first-half tickets (recount)', zero.second_half_tickets, o2[h1 == 0].sum())
    S.check('fig06 second-half tickets, 0 first-half tickets = fleet - other rows - second-half installs',
            zero.second_half_tickets, summary['fleet']['tickets_h2'] - by_count.second_half_tickets.drop('0').sum()
            - h2_only.tickets_h2.sum())
    S.check('fig06 second-half expected, 0 first-half tickets, within its bounds', 1,
            int(e2[h1 == 0].sum() <= zero.second_half_expected <= summary['fleet']['tickets_h2']
                - by_count.second_half_expected.drop('0').sum() - h2_only.expected_h2.sum()))
    S.check('fig06 ratio, 0 first-half tickets = tickets ÷ expected', zero.second_half_ratio,
            zero.second_half_tickets / zero.second_half_expected, 1e-12)
    # Cluster bootstrap over customers, as the script draws it: the clusters are the customers with a machine in both
    # halves (those with first-half expected tickets, with a ticketed machine in both halves, or whose installed
    # months exceed their machines' second halves), sorted, with the script's multinomial weights.
    definitions = summary['definitions']
    half_2 = ((pd.Timestamp(definitions['period'][1]) + pd.Timedelta(days=1) - pd.Timestamp(definitions['split'])).days
              / definitions['month_days'])
    has_h1 = customers.months > customers.machines * half_2 + 1e-9
    clusters = sorted(set(customers.customer[customers.E_h1 > 0]) | set(both.customer)
                      | set(customers.customer[has_h1]))
    cluster_of = both.customer.map({c: i for i, c in enumerate(clusters)}).to_numpy()
    weights = np.random.default_rng(summary['seed']).multinomial(
        len(clusters), np.full(len(clusters), 1 / len(clusters)), size=summary['n_boot']).astype(float)

    def boot_interval(sel):
        o, e = np.zeros(len(clusters)), np.zeros(len(clusters))
        np.add.at(o, cluster_of[sel], o2[sel])
        np.add.at(e, cluster_of[sel], e2[sel])
        with np.errstate(invalid='ignore', divide='ignore'):
            return np.nanpercentile((weights @ o) / (weights @ e), [(100 - LEVEL) / 2, (100 + LEVEL) / 2])

    for name in ('1', '2', '3', '4+'):
        sel = (h1 >= 4) if name == '4+' else (h1 == int(name))
        lo, hi = boot_interval(sel)
        S.check(f'fig06 bootstrap interval, {name} first-half tickets (replay) = script, low',
                by_count.loc[name, 'boot_lo'], lo, 1e-9)
        S.check(f'fig06 bootstrap interval, {name} first-half tickets (replay) = script, high',
                by_count.loc[name, 'boot_hi'], hi, 1e-9)
    bars = []
    for name, sel in groups:
        if sel is None:
            bars.append(dict(name=name, ratio=zero.second_half_ratio, lo=zero.boot_lo, hi=zero.boot_hi,
                             n=int(zero.machines)))
        else:
            lo, hi = boot_interval(sel)
            bars.append(dict(name=name, ratio=o2[sel].sum() / e2[sel].sum(), lo=lo, hi=hi, n=int(sel.sum())))
    script_ratio = {'0': by_count.loc['0', 'second_half_ratio'], '1': by_count.loc['1', 'second_half_ratio'],
                    '2': by_count.loc['2', 'second_half_ratio'], f'{CUT} or more': float(stat.observed)}
    for b in bars:
        S.check(f'fig06 ratio inside its interval, {b["name"]}', 1, int(b['lo'] <= b['ratio'] <= b['hi']))
    S.check('fig06 bootstrap draws = 2,000 (the intervals)', 2000, summary['n_boot'])

    # ---- (c) chronic outliers on IPA's list that stay flagged, and flagged machines that are consistent outliers ----
    n_fleet_machines = int(customers.machines.sum())
    p_machine = upper_p(machines.tickets, machines.expected)
    q_machine = bh(np.concatenate([p_machine, np.ones(n_fleet_machines - len(machines))]))[:len(machines)]
    flagged = (machines.tickets >= definitions['min_flag_tickets']) & (q_machine < definitions['q_cut'])
    S.check('fig06 machine q-values = script', 0, float(np.abs(q_machine - machines.q_poisson).max()), 1e-9)
    S.check('fig06 flagged machines = script', 0, int((flagged != machines.flagged).sum()))
    chronic = set(htm.serial_id[htm['class'] == 'chronic_outlier'])
    on_list = machines.serial_id.isin(chronic)
    S.check('fig06 chronic outliers on the list = script flag', 0, int((on_list != machines.in_docs05_113).sum()))
    overlap = summary['docs05_overlap']
    S.check('fig06 chronic outliers (docs/05)', overlap['docs05_flagged'], len(chronic))
    S.check('fig06 none on the third-party plan', 0, overlap['on_list_third_party'])
    n_on_list, n_still = int(on_list.sum()), int((on_list & flagged).sum())
    S.check('fig06 chronic outliers on the list = summary', overlap['in_population'], n_on_list)
    S.check('fig06 still flagged = summary', overlap['flagged_now'], n_still)
    S.check('fig06 consistent among them = summary', overlap['consistent_now'], int((on_list & consistent_m).sum()))
    n_flagged = int(flagged.sum())
    S.check('fig06 flagged machines = summary', summary['machines']['flagged'], n_flagged)
    S.check('fig06 consistent machines are flagged machines', n_consistent_m, int((consistent_m & flagged).sum()))
    n_nb = int((flagged & (machines.q_nb < definitions['q_cut'])).sum())
    S.check('fig06 caption: no chronic outlier on the list stands out under the negative binomial either', 0,
            int((on_list & (machines.q_nb < definitions['q_cut'])).sum()))
    S.check('fig06 machines with 5+ tickets that stand out under the negative binomial = summary',
            summary['machines']['flagged_nb'], int(((machines.tickets >= 5) & (machines.q_nb < 0.05)).sum()))

    # ---- the report's numbers (Results, and the Definitions for the 311 customers) ----
    S.report_check('fig06 rank correlation, first vs. second half', '0.46', S.num(rho, 2))
    S.report_check('fig06 same when shuffled', '0.04', S.num(rho_null, 2))
    S.report_check('fig06 machines with 3 or more first-half tickets (cut)', '3', S.num(CUT))
    S.report_check('fig06 their second-half tickets vs. expected (times)', '2.6', S.num(ratio_3, 1))
    S.report_check('fig06 consistent-outlier customers', '18', S.num(n_consistent_c))
    S.report_check('fig06 consistent-outlier machines', '36', S.num(n_consistent_m))
    S.report_check("fig06 chronic outliers on IPA's list", '106', S.num(n_on_list))
    S.report_check('fig06 of those, still flagged', '93', S.num(n_still))
    S.report_check('fig06 flagged machines that stand out as a separate group', 'no',
                   'no' if n_nb == 0 else S.num(n_nb))
    S.report_check('fig06 customers in the rank correlation (Definitions)', '311', S.num(len(both_halves)))

    fig, (ax, bx, cx) = S.figure(2.2, ncols=3, width_ratios=[1.74, 0.93, 0.82])

    # (a) customers by half, log axes with the zero row and column
    xs = np.where(str_h1 > 0, str_h1, ZERO)
    ys = np.where(str_h2 > 0, str_h2, ZERO)
    cons_in = both_halves.consistent_outlier.to_numpy()
    ax.plot([1, 1], [LOG_LO, 5.5], color=S.GRID, lw=0.8, zorder=1)  # kept below the annotations at the top
    ax.plot([LOG_LO, 11], [1, 1], color=S.GRID, lw=0.8, zorder=1)
    ax.scatter(xs[~cons_in], ys[~cons_in], s=6.5, color=S.GREY, alpha=0.6, linewidths=0, zorder=2)
    out = customers[consistent_c & ~in_corr]
    cx_all = np.concatenate([xs[cons_in], (out.O_h1 / out.E_h1).to_numpy()])
    cy_all = np.concatenate([ys[cons_in], (out.O_h2 / out.E_h2).to_numpy()])
    S.check('fig06 consistent outliers drawn', n_consistent_c, len(cx_all))
    S.check('fig06 customers drawn', len(both_halves) + n_other_consistent, len(xs) + len(out))
    S.check('fig06 every customer inside the spines', 1,
            int(max(cx_all.max(), xs.max()) < RATIO_TICKS[-1] and max(cy_all.max(), ys.max()) < 5.5))
    ax.scatter(cx_all, cy_all, s=12, color=S.COBALT, linewidths=0, zorder=4)
    # the readout top left and the cluster's label top right, both above the spines; the label's first line is level
    # with the readout's second, well to its right
    S.label(ax, 10.5, 21, f'{S.num(n_consistent_c)} consistent\noutliers', ha='right', va='top', linespacing=1.0)
    t1 = S.label(ax, 0.045, 39, 'Rank correlation ', ha='left', va='top', size=S.FONT)
    ax.annotate(S.num(rho, 2), xy=(1, 1), xycoords=t1, ha='left', va='top', fontsize=S.FONT,
                fontweight='bold', color=S.GREEN)
    S.label(ax, 0.045, 21, f'{S.num(rho_null, 2)} when shuffled', ha='left', va='top')
    ax.set_xscale('log')
    ax.set_yscale('log')
    for axis in (ax.xaxis, ax.yaxis):
        zero_log_axis(axis, ZERO, RATIO_TICKS)
    ax.set_xlim(0.04, 11)
    ax.set_ylim(0.04, LOG_HI)
    ax.spines['left'].set_bounds(LOG_LO, RATIO_TICKS[-1])     # each spine ends at its last tick
    ax.spines['bottom'].set_bounds(LOG_LO, RATIO_TICKS[-1])
    ax.set_xlabel('First half (log scale)')
    ax.set_ylabel('Second half (log scale)')
    S.clean(ax)
    S.panel(ax, 'a', 'Customers: tickets ÷ expected')

    # (b) machines' second-half tickets ÷ expected by first-half tickets, bars from zero with bootstrap intervals
    # (black, cased in white so they read on cobalt, as in figure 11)
    casing = [pe.Stroke(linewidth=2.0, foreground=S.WHITE), pe.Normal()]
    for i, b in enumerate(bars):
        hot = b['name'] == f'{CUT} or more'   # the focal bar, the only one labelled (as in figure 11)
        bx.bar(i, b['ratio'], width=0.62, color=S.COBALT if hot else S.GREY_FILL, zorder=3)
        line, = bx.plot([i, i], [b['lo'], b['hi']], color=S.TEXT, lw=0.8, solid_capstyle='butt', zorder=4)
        line.set_path_effects(casing)
        S.check(f'fig06 (b) bar {b["name"]} = the script\'s ratio', script_ratio[b['name']], b['ratio'], 1e-9)
        if hot:
            text = S.num(b['ratio'], 1)
            S.check(f'fig06 (b) label {b["name"]} {text}', round(script_ratio[b['name']], 1), float(text))
            S.label(bx, i, b['hi'] + 0.07, text, ha='center', va='bottom', size=S.FONT, weight='bold')
    bx.axhline(1, color=S.GREY_DARK, lw=0.8, ls=(0, (4, 2.5)), zorder=2)
    bx.set_xticks(np.arange(len(bars)), [f'{CUT}+' if b['name'] == f'{CUT} or more' else b['name'] for b in bars])
    bx.set_xlim(-0.55, len(bars) - 0.45)
    bx.set_ylim(0, 3.45)
    bx.set_yticks([0, 1, 2, 3])
    bx.set_xlabel('First-half tickets')
    bx.set_ylabel('Second-half tickets\n÷ expected')
    S.clean(bx, grid='y')
    S.panel(bx, 'b', 'Machines by first-half tickets')

    # (c) flagged machines: chronic outliers on IPA's list still flagged; flagged machines that are consistent
    rows = [('Chronic outliers\non IPA’s list', n_on_list, n_still, f'{S.num(n_still)} still flagged'),
            ('Flagged\nmachines', n_flagged, n_consistent_m, f'{S.num(n_consistent_m)} consistent outliers')]
    for i, (name, total, part, text) in enumerate(rows):
        cx.barh(-i, part, height=0.36, color=S.COBALT, zorder=3)
        cx.barh(-i, total - part, left=part, height=0.36, color=S.GREY_FILL, zorder=3)
        S.label(cx, 0, -i + 0.25, text, ha='left', va='bottom', bbox=dict(fc=S.WHITE, ec='none', pad=0.6))
        S.label(cx, total + 3, -i, S.num(total), ha='left', va='center')
    cx.set_yticks([-i for i in range(len(rows))], [r[0] for r in rows])
    cx.set_ylim(-1.5, 0.85)
    cx.set_xlim(0, 150)
    cx.set_xticks([0, 50, 100])
    cx.set_xlabel('Machines')
    S.clean(cx, grid='x', left=False)
    S.panel(cx, 'c', 'Machine flags')

    S.export(fig, NAME, out_dir)
    pc = chr(92) + '%'  # LaTeX: an escaped percent sign
    group = 'no separate group' if n_nb == 0 else 'a separate group'
    return (f'Customers above their fleets in the first half tend to stay above them in the second (rank correlation '
            f'{S.num(rho, 2)} vs. {S.num(rho_null, 2)} when shuffled), and machines with {CUT} or more first-half '
            f'tickets had {S.num(ratio_3, 1)} times their expected second-half tickets. '
            f'(a)~Customers; (b)~{S.num(LEVEL)}{pc} intervals; (c)~{group}.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
