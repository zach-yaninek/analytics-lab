#!/usr/bin/env python3
"""Report figure 2 (Results, High-ticket machines): 113 chronic outliers at 82 customers; the top 5% of the 6,621
telemetry devices hold 32.9% of their tickets vs. 22.2% by chance; allowing for spread between machines, only 2 rate
outliers still stand out, so high-ticket machines form a continuum; and non-success codes rise before chronic
outliers' tickets no more than on other machines.

(a) Concentration: the share of unplanned tickets held by the devices with the most tickets, observed and by chance
    (the median of the analysis's 1,000 Poisson simulations, replayed with its seed), with the top 5% marked.
(b) Each device's tickets against its expected tickets (log axes; devices without a ticket on the row marked 0), for
    the 6,423 devices with months active. The 113 chronic outliers are cobalt, and the 2 rate outliers that keep
    q < 0.05 under the negative binomial (both chronic outliers) are ringed. Points are anonymous, and the grey
    context points are rasterized at 300 dpi inside the vector PDF.
(c) Median non-success codes per 1,000 transactions in the comparison windows and in the 30 days before the 3,259
    paired tickets, for chronic outliers (163 tickets), other top-5% machines (169), and all other machines
    (2,927), with each group's rise.

Inputs: verification/outputs/htm_device_exposure.csv (one row per device in the exposure population),
htm_machine_counts.csv (one row per ticketed machine: the top-5% cut), htm_pre_ticket.csv (one row per usable
unplanned ticket), htm_summary.json (seed, simulations, and the script's results for the checks), htm_lorenz.csv and
htm_pre_ticket_summary.csv (the script's curve and medians, for the checks), fu/fu_devices.csv and
db/db_host_level.csv (the exposure population and the device order the simulations depend on; ticket_customer
counts the chronic outliers' customers and is never printed). Notebook 02 checks the same numbers, and this script
reuses its logic.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, LogLocator, NullFormatter, NullLocator  # noqa: E402

import report_style as S  # noqa: E402

NAME = 'fig02_high_ticket'
LABEL = 'fig:high-ticket'
SHORT = 'High-ticket machines'

TOP = 0.05          # the report's top 5%
Q_CUT = 0.05        # Benjamini-Hochberg cut for rate outliers
CURVE_TO = 0.20     # panel (a) shows the top 20% of devices
ZERO_Y = 0.6        # panel (b): devices without a ticket are drawn on this row of the log axis, marked 0
ONE_LO = 0.85       # panel (b): the log part of the y-axis starts here, above the 0 row
GROUPS = [          # panel (c): htm_pre_ticket.csv group, htm_pre_ticket_summary.csv group, label, Definitions' rise
    ('chronic', 'chronic', 'Chronic outliers', '+20.3'),
    ('workload_outsized', 'workload_outsized_not_chronic', 'Other top 5%', '+21.6'),
    ('other', 'other', 'All other machines', '+21.5'),
]


# ----------------------------------------------------------------------------------------------------------------
# Notebook 02's tests, reused: Benjamini-Hochberg and the Poisson / negative-binomial upper tails
# ----------------------------------------------------------------------------------------------------------------
def bh(p):
    """Benjamini-Hochberg q-values, computed as in high_ticket_machines.py."""
    p = np.asarray(p, float)
    order = np.argsort(p, kind='mergesort')
    q = np.minimum.accumulate((p[order] * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    out = np.empty(len(p))
    out[order] = np.minimum(q, 1.0)
    return out


def upper_tail(k, mu, alpha=0.0):
    """P(X >= k) for a Poisson with mean mu (alpha = 0) or a negative binomial with mean mu and variance
    mu + alpha mu^2."""
    if alpha > 0:
        size = 1 / alpha

        def log_pmf(j):
            return (math.lgamma(j + size) - math.lgamma(size) - math.lgamma(j + 1)
                    + size * math.log(size / (size + mu)) + j * math.log(mu / (size + mu)))
    else:
        def log_pmf(j):
            return -mu + j * math.log(mu) - math.lgamma(j + 1)
    if k <= mu:
        return 1 - sum(math.exp(log_pmf(j)) for j in range(k))
    logs = [log_pmf(k)]
    while logs[-1] > logs[0] - 50:
        logs.append(log_pmf(k + len(logs)))
    return math.exp(logs[0]) * sum(math.exp(x - logs[0]) for x in logs)


def zero_log_axis(axis, zero_at, ticks):
    """A log axis whose first tick, at zero_at below the data range, reads 0 (for counts of zero)."""
    axis.set_major_locator(FixedLocator([zero_at] + list(ticks)))
    axis.set_major_formatter(FuncFormatter(lambda v, _: '0' if math.isclose(v, zero_at) else f'{v:g}'))
    axis.set_minor_locator(NullLocator())


def plot(out_dir=S.FIG_DIR):
    summary = json.loads((S.OUT / 'htm_summary.json').read_text())
    devices = pd.read_csv(S.OUT / 'fu' / 'fu_devices.csv', usecols=['machine_id', 'host', 'ticket_customer'])
    hosts = pd.read_csv(S.OUT / 'db' / 'db_host_level.csv', usecols=['host', 'shared_internal_host'])
    dev = pd.read_csv(S.OUT / 'htm_device_exposure.csv',
                      usecols=['machine_id', 'serial_id', 'machine_type', 'rate_group', 'months', 'tickets_obs',
                               'expected', 'p_poisson', 'p_nb', 'q_nb', 'class', 'nb_outlier'])
    machines = pd.read_csv(S.OUT / 'htm_machine_counts.csv', usecols=['machine_id', 'telemetry_id',
                                                                      'unplanned_tickets'])
    pre = pd.read_csv(S.OUT / 'htm_pre_ticket.csv',
                      usecols=['case_id', 'machine_id', 'group', 'control_clean_available', 'all_events_30d',
                               'non_success_events_30d', 'control_all_events_30d',
                               'control_non_success_events_30d'])
    pre_summary = pd.read_csv(S.OUT / 'htm_pre_ticket_summary.csv').set_index(['group', 'window'])
    lorenz = pd.read_csv(S.OUT / 'htm_lorenz.csv')

    # ---- the 6,621 devices: every device off IPA's shared internal host and with a host (notebook 02) ----
    on_shared = devices.host.isin(hosts.host[hosts.shared_internal_host == 1])
    population = devices.machine_id[~on_shared & devices.host.notna()]
    assert dev.machine_id.is_unique and set(dev.machine_id) == set(population)
    n_devices = len(population)
    S.check('fig02 devices = summary', summary['D4_concentration']['devices'], n_devices)
    S.check('fig02 tickets = summary', summary['D2_exposure']['tickets'], int(dev.tickets_obs.sum()))
    S.check('fig02 months active = summary', summary['D2_exposure']['exposure_months_total'], int(dev.months.sum()))

    # ---- chronic outliers: top 5% of ticketed machines and a rate outlier (Poisson, BH q < 0.05) ----
    rank_k = math.ceil(TOP * len(machines))
    cut = machines.unplanned_tickets.sort_values(ascending=False).iloc[rank_k - 1]
    top5_machines = machines.machine_id[machines.unplanned_tickets >= cut]
    top5 = dev.serial_id.isin(top5_machines)
    type_months = dev.groupby('machine_type').months.sum()
    rate_group = dev.machine_type.where(dev.machine_type.map(type_months) >= 100, '(pooled small types)')
    S.check('fig02 rate groups = script', 0, int((rate_group != dev.rate_group).sum()))
    totals = dev.groupby(rate_group)[['tickets_obs', 'months']].sum()
    expected = rate_group.map(totals.tickets_obs / totals.months) * dev.months
    S.check('fig02 expected tickets = script (CSV keeps 6 decimals)', 0,
            float((expected - dev.expected).abs().max()), 1e-6)
    tested = expected > 0
    y, mu = dev.tickets_obs[tested], expected[tested]
    p_poisson = pd.Series([upper_tail(k, m) for k, m in zip(y, mu)], index=mu.index)
    S.check('fig02 Poisson p-values = script', 0, float((p_poisson / dev.p_poisson[tested] - 1).abs().max()), 1e-9)
    q_poisson = pd.Series(np.nan, index=dev.index)
    q_poisson[tested] = bh(p_poisson)
    rate_outlier = q_poisson < Q_CUT
    chronic = top5 & rate_outlier
    n_chronic = int(chronic.sum())
    n_chronic_customers = int(dev.machine_id[chronic].map(devices.set_index('machine_id').ticket_customer).nunique())
    S.check('fig02 chronic outliers = script class', 0, int((chronic != (dev['class'] == 'chronic_outlier')).sum()))
    S.check('fig02 rate outliers = summary', summary['D2_exposure']['rate_outliers_poisson'], int(rate_outlier.sum()))
    S.check('fig02 chronic customers = summary', summary['clustering']['chronic_customers_holding'],
            n_chronic_customers)

    # ---- still outliers under the negative binomial (moment fit of the spread per rate group) ----
    fit = pd.DataFrame({'sq': (y - mu) ** 2 - mu, 'e2': mu ** 2}).groupby(rate_group[tested]).sum()
    alpha = rate_group[tested].map((fit.sq / fit.e2).clip(lower=0))
    p_nb = pd.Series([upper_tail(k, m, a) for k, m, a in zip(y, mu, alpha)], index=mu.index)
    S.check('fig02 negative-binomial p-values = script', 0, float((p_nb / dev.p_nb[tested] - 1).abs().max()), 1e-9)
    q_nb = pd.Series(np.nan, index=dev.index)
    q_nb[tested] = bh(p_nb)
    nb_kept = rate_outlier & (q_nb < Q_CUT)
    n_nb_kept = int(nb_kept.sum())
    S.check('fig02 still outliers = script flags', 0, int((nb_kept != dev.nb_outlier.astype(bool)).sum()))
    S.check('fig02 still outliers are chronic outliers (drawn as ringed cobalt points)', n_nb_kept,
            int((nb_kept & chronic).sum()))

    # ---- (a) concentration: observed and the chance median over the replayed simulations ----
    obs = np.sort(dev.tickets_obs.to_numpy())[::-1]
    top_k = math.ceil(TOP * n_devices)
    top_share = obs[:top_k].sum() / obs.sum()
    k_max = math.ceil(CURVE_TO * n_devices)
    share_x = np.arange(k_max + 1) / n_devices
    obs_curve = np.concatenate([[0.0], np.cumsum(obs[:k_max]) / obs.sum()])
    means = expected.set_axis(dev.machine_id).reindex(population).to_numpy()  # the draws depend on this order
    draws = np.random.default_rng(summary['seed']).poisson(means, size=(summary['n_sim'], n_devices))
    sims = -np.sort(-draws, axis=1)[:, :k_max]
    sim_curves = np.cumsum(sims, axis=1) / draws.sum(axis=1, keepdims=True)
    chance_median = float(np.median(sim_curves[:, top_k - 1]))
    chance_curve = np.concatenate([[0.0], np.median(sim_curves, axis=0)])
    d4 = summary['D4_concentration']
    S.check('fig02 top 5% share = summary', d4['top5_share_obs'], round(top_share, 4))
    S.check('fig02 chance median = summary', d4['top5_share_null_median'], round(chance_median, 4))
    S.check('fig02 simulations = 1,000 (the chance median)', 1000, summary['n_sim'])
    grid = lorenz[lorenz.device_share <= CURVE_TO + 1e-9]
    S.check('fig02 observed curve = htm_lorenz.csv', 0,
            float(np.abs(np.interp(grid.device_share, share_x, obs_curve) - grid.ticket_share_obs).max()), 1e-12)
    S.check('fig02 chance curve = htm_lorenz.csv (within 0.2 points)', 0,
            float(np.abs(np.interp(grid.device_share, share_x, chance_curve)
                         - grid.ticket_share_null_median).max()), 0.002)
    S.check('fig02 the top 5% mark is on the chance curve', round(chance_median, 6),
            round(float(chance_curve[top_k]), 6))

    # ---- (c) non-success codes per 1,000 transactions before paired tickets, by group ----
    top5_devices = set(machines.telemetry_id[machines.unplanned_tickets >= cut].dropna())
    own_group = np.select([pre.machine_id.isin(dev.machine_id[chronic]), pre.machine_id.isin(top5_devices)],
                          ['chronic', 'workload_outsized'], 'other')
    S.check('fig02 pre-ticket groups = chronic outliers and top 5%', 0, int((own_group != pre.group).sum()))
    paired = pre[pre.control_clean_available.astype(bool)]

    def per_1000(non_success, events):
        return (1000 * non_success / events).where(events > 0)

    paired = paired.assign(ticket=per_1000(paired.non_success_events_30d, paired.all_events_30d),
                           comparison=per_1000(paired.control_non_success_events_30d, paired.control_all_events_30d))
    rows = {}
    for key, summary_key, name, report in GROUPS:
        sub = paired[paired.group == key]
        med_c, med_t = float(sub.comparison.median()), float(sub.ticket.median())
        rows[key] = dict(name=name, comparison=med_c, ticket=med_t, rise=med_t - med_c, n=len(sub))
        S.report_check(f'fig02 rise in non-success codes, {name} (Definitions)', report, f'{med_t - med_c:+.1f}')
        S.check(f'fig02 paired tickets, {name} = script', pre_summary.loc[(summary_key, 'ticket (paired)'), 'tickets'],
                len(sub))
        S.check(f'fig02 median before tickets, {name} = script',
                pre_summary.loc[(summary_key, 'ticket (paired)'), 'non_success_per_1000_median'], med_t, 0.05)
        S.check(f'fig02 median in comparison windows, {name} = script',
                pre_summary.loc[(summary_key, 'control (paired)'), 'non_success_per_1000_median'], med_c, 0.05)
    no_more = rows['chronic']['rise'] <= min(rows['workload_outsized']['rise'], rows['other']['rise'])
    S.report_check("fig02 chronic outliers' rise vs. other machines'", 'no more than',
                   'no more than' if no_more else 'more than')
    rises = [r['rise'] for r in rows.values()]
    S.check("fig02 caption: the rises are alike (within 1.5 per 1,000)", 1, int(max(rises) - min(rises) <= 1.5))

    # ---- the report's numbers (Results, and the Definitions for the rises and paired tickets) ----
    n_tested = int(tested.sum())
    S.check('fig02 devices with months active = summary', summary['D2_exposure']['devices_with_exposure'], n_tested)
    n_paired = len(paired)
    S.report_check('fig02 chronic outliers', '113', S.num(n_chronic))
    S.report_check('fig02 customers with a chronic outlier', '82', S.num(n_chronic_customers))
    S.report_check('fig02 telemetry devices', '6,621', S.num(n_devices))
    S.report_check('fig02 top share', '5%', S.pct(top_k / n_devices))
    S.report_check("fig02 top 5%'s share of tickets", '32.9%', S.pct(top_share, 1))
    S.report_check('fig02 same share by chance', '22.2%', S.pct(chance_median, 1))
    S.report_check('fig02 rate outliers that still stand out', '2', S.num(n_nb_kept))
    S.report_check('fig02 paired tickets (Definitions)', '3,259', S.num(n_paired))

    fig, (ax, bx, cx) = S.figure(2.45, ncols=3, width_ratios=[1.0, 1.04, 0.74])

    # (a) concentration curves, the top 5% marked by a guide line that runs up to the observed share's readout
    x5 = top_k / n_devices
    y_read = top_share + 0.12
    blank = dict(fc=S.WHITE, ec='none', pad=0.8)   # keeps the light grid out of a label
    ax.plot(share_x, chance_curve, color=S.GREY_DARK, lw=1.2, ls=(0, (4, 2.5)), zorder=3)
    ax.plot(share_x, obs_curve, color=S.COBALT, lw=1.5, zorder=4)
    ax.plot([x5, x5], [0, chance_median], color=S.GRID, lw=0.8, zorder=1)
    ax.plot([x5, x5], [top_share, y_read - 0.015], color=S.GRID, lw=0.8, zorder=1)
    ax.plot([x5, x5], [chance_median, top_share], color=S.GREY_DARK, lw=0.6, zorder=2)
    ax.plot(x5, top_share, 'o', color=S.COBALT, ms=4, zorder=5)
    ax.plot(x5, chance_median, 'o', mfc=S.WHITE, mec=S.GREY_DARK, mew=1.0, ms=4, zorder=5)
    S.label(ax, x5 - 0.004, y_read, S.pct(top_share, 1), ha='center', va='bottom', size=S.FONT, weight='bold',
            color=S.GREEN, zorder=6)
    S.label(ax, x5 + 0.007, chance_median - 0.035, S.pct(chance_median, 1), ha='left', bbox=blank, zorder=6)
    S.label(ax, x5 + 0.006, 0.02, 'Top 5%', ha='left', va='bottom')
    xo, xc = 0.165, 0.15
    S.label(ax, xo - 0.004, np.interp(xo, share_x, obs_curve) + 0.035, 'Observed', ha='right', va='bottom',
            bbox=blank, zorder=6)
    S.label(ax, xc + 0.004, np.interp(xc, share_x, chance_curve) - 0.035, 'Chance', ha='left', va='top',
            bbox=blank, zorder=6)
    ax.set_xlim(0, CURVE_TO)
    ax.set_ylim(0, 0.8)
    ax.set_xticks([0, 0.05, 0.10, 0.15, 0.20])
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8])
    S.pct_axis(ax.xaxis)
    S.pct_axis(ax.yaxis)
    ax.set_xlabel('Devices, most tickets first')
    ax.set_ylabel('Share of tickets')
    S.clean(ax, grid='y')
    S.panel(ax, 'a', 'Concentration of tickets')

    # (b) tickets against expected tickets, log axes; devices without a ticket on the row marked 0
    xs, ys = expected[tested], dev.tickets_obs[tested].astype(float)
    ys = ys.where(ys > 0, ZERO_Y)
    on, kept = chronic[tested], nb_kept[tested]
    bx.scatter(xs[~on], ys[~on], s=3.5, color=S.GREY, alpha=0.4, linewidths=0, zorder=2, rasterized=True)
    bx.scatter(xs[on], ys[on], s=9, color=S.COBALT, linewidths=0, zorder=4)
    bx.scatter(xs[kept], ys[kept], s=58, facecolors='none', edgecolors=S.TEXT, linewidths=0.8, zorder=5)
    S.check('fig02 every chronic outlier above its expected tickets', n_chronic,
            int((dev.tickets_obs[chronic] > expected[chronic]).sum()))
    S.check('fig02 every device inside the x-axis', 1, int(xs.min() > 0.035 and xs.max() < 16))
    S.check('fig02 every device inside the y-axis', 1, int(ys.max() < 34))
    S.label(bx, 1.25, 17, f'{S.num(n_chronic)} chronic\noutliers', ha='left', va='center', linespacing=1.1)
    S.label(bx, 0.15, 21, f'{S.num(n_nb_kept)} still\nstand out', ha='center', va='center', linespacing=1.1)
    bx.set_xscale('log')
    bx.set_yscale('log')
    bx.set_xlim(0.035, 16)
    bx.set_ylim(0.47, 34)
    bx.xaxis.set_major_locator(FixedLocator([0.1, 1, 10]))
    bx.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    bx.xaxis.set_minor_locator(LogLocator(subs=np.arange(2, 10)))
    bx.xaxis.set_minor_formatter(NullFormatter())
    bx.tick_params(axis='x', which='minor', length=1.5, width=0.5)
    zero_log_axis(bx.yaxis, ZERO_Y, [1, 2, 5, 10, 20])
    bx.spines['left'].set_bounds(ONE_LO, 34)
    bx.set_xlabel('Expected tickets (log scale)')
    bx.set_ylabel('Tickets (log scale)')
    S.clean(bx)
    S.panel(bx, 'b', 'Tickets vs. expected tickets')

    # (c) median non-success codes per 1,000 transactions: comparison window, then the 30 days before the ticket;
    # the labels sit right of the axes, so the grid stays clear of them
    styles = {'chronic': dict(color=S.COBALT, lw=1.5, ls='-', marker='o', z=5),
              'workload_outsized': dict(color=S.GREY_DARK, lw=1.2, ls=(0, (4, 2.5)), marker='s', z=4),
              'other': dict(color=S.GREY, lw=1.2, ls='-', marker='^', z=3)}
    for key, r in rows.items():
        st = styles[key]
        cx.plot([0, 1], [r['comparison'], r['ticket']], color=st['color'], lw=st['lw'], ls=st['ls'],
                marker=st['marker'], ms=4.2, mec=S.WHITE, mew=0.6, zorder=st['z'], clip_on=False)
    order = sorted(rows, key=lambda k: rows[k]['ticket'], reverse=True)
    label_y = {}
    for i, key in enumerate(order):  # keep the end labels at least 7.5 units apart
        yv = rows[key]['ticket']
        label_y[key] = min(yv, label_y[order[i - 1]] - 7.5) if i else yv
    for key in order:
        r = rows[key]
        text = f"{r['rise']:+.1f}"
        S.check(f'fig02 (c) label {r["name"]} {text}', round(r['rise'], 1), float(text))
        S.label(cx, 1.1, label_y[key], f"{r['name']}  {text}", ha='left', va='center', clip_on=False)
    cx.set_xlim(-0.15, 1.1)
    cx.set_ylim(0, 90)
    cx.set_xticks([0, 1], ['Comparison\nwindow', '30 days\nbefore ticket'])
    cx.set_yticks([0, 20, 40, 60, 80])
    cx.spines['bottom'].set_bounds(0, 1)
    cx.set_ylabel('Median non-success codes\nper 1,000 transactions')
    S.clean(cx, grid='y')
    S.panel(cx, 'c', 'Codes before tickets')

    S.export(fig, NAME, out_dir)
    pc = chr(92) + '%'  # LaTeX: an escaped percent sign
    return (f'High-ticket machines form a continuum: the top {S.pct(top_k / n_devices).replace("%", pc)} of the '
            f'{S.num(n_devices)} telemetry devices hold {S.pct(top_share, 1).replace("%", pc)} of their tickets vs. '
            f'{S.pct(chance_median, 1).replace("%", pc)} by chance, and allowing for spread between machines, only '
            f'{S.num(n_nb_kept)} rate outliers still stand out. '
            f'(a)~Share of tickets held by the top devices. '
            f'(b)~Tickets vs. expected tickets for the {S.num(n_tested)} devices with months active, with the '
            f'{S.num(n_chronic)} chronic outliers at {S.num(n_chronic_customers)} customers. '
            f'(c)~Non-success codes before the {S.num(n_paired)} paired tickets, rising alike in each group.')


if __name__ == '__main__':
    print(plot())
    sys.exit(1 if S.summary() else 0)
