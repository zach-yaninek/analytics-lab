#!/usr/bin/env python3
"""Fleet chart 3: unplanned tickets per 100 installed machine-months by machine age, with 95% intervals.

Age is the second axis of the fleet besides model: the same installed-base list that gives each machine's installed
months gives its install date, so every machine falls in one age band (years since install at the midpoint of its
exposure in the period, cut at 1, 2, 4, 6, 8 and 10 years). One vertical bar per band, youngest on the left, with
its rate labelled beside the bar top and its 95% interval as a whisker (cluster bootstrap over accounts); the band's
machine count is on the axis label. The horizontal line is the fleet rate. The title compares the youngest band
with the oldest (the multiple is computed); those two bars are blue, the others gray. The subtitle groups the bands
by the data: the leading bands whose interval is wholly above the fleet line, the oldest band, and the bands
between. The footer says why this chart does not compare models: age and model overlap (newer models have younger
machines), so model comparisons are age-standardised (charts fx_02 and fx_09), and service status overlaps with age
as well (chart fx_04).

Inputs (computed by verification/fleet_exposure.py; nothing is recomputed here):
  verification/outputs/fleet/fx_age_rates.csv      one row per age band: machines, accounts, months, tickets,
                                                   rate_per_100, ci_lo/ci_hi (ci_method), boot_lo/boot_hi,
                                                   ratio_to_fleet, fleet_rate_per_100
  verification/outputs/fleet/fx_summary.json       fleet rate and totals, period, age_bands, min_clusters, n_boot
  verification/outputs/fleet/fx_model_rates.csv    ratio_to_fleet and age_std_ratio per model (their quotient is the
                                                   model's age mix, for the overlap note)
  verification/outputs/fleet/fx_machine_flags.csv  age band, service status and install year of every machine with
                                                   a ticket (status overlap note, and a check that newer models have
                                                   younger machines)
Output:  viz/figures/fx_03_rate_by_age.png
Run:     cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_03_rate_by_age.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_03_rate_by_age.png'
BOOT = 'cluster bootstrap'
WARRANTY, NOT_SERVICEABLE = 'Under Warranty', 'Not Serviceable'  # service-status labels on the list
TITLE_IN_PER_CHAR = 0.12  # approximate width of one title character (15 pt bold), for the figure width
HEIGHT = 7.4              # figure height, inches
BAR_PX = 22               # bar thickness, pixels at style.DPI
AXIS_LABEL_IN = 0.95      # approximate width of the y tick labels and two-line axis label, inches
X_PAD = 0.6               # space left of the first bar and right of the last, in bar slots
Y_STEP = 2.5              # y gridline step: keeps a gridline from sitting just beside the fleet line
NBSP = '\u00a0'           # keeps a number with its unit when frame() wraps the subtitle


def edges(label):
    """Age-band label -> (lower, upper) years: '<1' -> (0, 1), '1-2' -> (1, 2), '10+' -> (10, inf)."""
    if label.startswith('<'):
        return 0.0, float(label[1:])
    if label.endswith('+'):
        return float(label[:-1]), float('inf')
    lo, hi = label.split('-')
    return float(lo), float(hi)


def years(x):
    return f'{x:g}{NBSP}year' + ('' if x == 1 else 's')


def plot(out_dir=fleet.FIG_DIR):
    out_dir = Path(out_dir)
    S = fleet.summary()
    F, D = S['fleet'], S['definitions']
    f = fleet.fleet_rate(S)
    a = fleet.load('age_rates')
    bands = a.age_band.tolist()

    # The bands, in the analysis order, cover the exposed fleet; the fleet rate is a ratio of totals.
    style.check('fx_03 age bands = analysis age bands, in order', 1, int(bands == D['age_bands']))
    lims = [edges(b) for b in bands]
    style.check('fx_03 age bands are contiguous, youngest first, from 0', 1,
                int(lims[0][0] == 0 and all(lims[i][1] == lims[i + 1][0] for i in range(len(lims) - 1))
                    and np.isinf(lims[-1][1])))
    style.check('fx_03 band tickets = fleet tickets', F['tickets'], a.tickets.sum(), 1e-6)
    style.check('fx_03 band months = fleet installed machine-months', F['months'], a.months.sum(), 1e-6)
    style.check('fx_03 band machines = exposed machines', F['machines_exposed'], int(a.machines.sum()))
    style.check('fx_03 machines with no band = machines installed after the period',
                F['machines'] - F['machines_exposed'], F['machines_zero_months'])
    style.check('fx_03 fleet rate = 100 x tickets / months (summary)', f, 100 * F['tickets'] / F['months'], 1e-9)
    style.check('fx_03 fleet rate = 100 x tickets / months (all bands)', f, 100 * a.tickets.sum() / a.months.sum(),
                1e-9)
    style.check('fx_03 fleet rate column = summary', 0, float((a.fleet_rate_per_100 - f).abs().max()), 1e-9)
    style.check('fx_03 rates = 100 x tickets / months', 0,
                float((100 * a.tickets / a.months - a.rate_per_100).abs().max()), 1e-9)
    style.check('fx_03 ratio_to_fleet = rate / fleet rate', 0,
                float((a.rate_per_100 / f - a.ratio_to_fleet).abs().max()), 1e-9)
    # Intervals: every band is in enough accounts and has tickets, so the drawn interval is the cluster bootstrap.
    style.check('fx_03 every band: cluster-bootstrap interval (enough accounts, tickets > 0)', 0,
                int(((a.ci_method != BOOT) | (a.accounts < D['min_clusters']) | (a.tickets == 0)).sum()))
    style.check('fx_03 drawn intervals = bootstrap columns', 0,
                float(max((a.ci_lo - a.boot_lo).abs().max(), (a.ci_hi - a.boot_hi).abs().max())), 1e-12)
    style.check('fx_03 every interval contains its rate', 0,
                int(((a.ci_lo > a.rate_per_100) | (a.ci_hi < a.rate_per_100)).sum()))

    # Title: the youngest band against the oldest.
    young, old = a.iloc[0], a.iloc[-1]
    multiple = young.rate_per_100 / old.rate_per_100
    style.check('fx_03 title multiple = ratio of the two ratios to the fleet',
                young.ratio_to_fleet / old.ratio_to_fleet, multiple, 1e-9)
    style.check('fx_03 title multiple = from tickets and months',
                (young.tickets / young.months) / (old.tickets / old.months), multiple, 1e-9)
    style.check('fx_03 oldest band has the lowest rate', 1, int(old.rate_per_100 == a.rate_per_100.min()))
    style.check('fx_03 oldest band interval wholly below the youngest band interval', 1,
                int(old.ci_hi < young.ci_lo))

    # Subtitle groups: the leading bands whose drawn interval is wholly above the fleet line, the oldest band, and
    # the bands between.
    above = (a.ci_lo > f).to_numpy()
    n_lead = int(np.argmin(above)) if not above.all() else len(a)
    style.check('fx_03 the bands above the fleet are the leading ones', int(above.sum()), n_lead)
    style.check('fx_03 at least one band between the leading ones and the oldest', 1, int(0 < n_lead < len(a) - 1))
    lead, mid = a.iloc[:n_lead], a.iloc[n_lead:-1]
    style.check('fx_03 every band between is below the leading bands', 1,
                int(mid.rate_per_100.max() < lead.rate_per_100.min()))
    style.check('fx_03 oldest band below every band between', 1, int(old.rate_per_100 < mid.rate_per_100.min()))
    lead_upper = lims[n_lead - 1][1]
    mid_lo, mid_hi = lims[n_lead][0], lims[len(a) - 2][1]
    old_lo = lims[-1][0]

    # Note: age and model overlap. A model's age mix = the rate its machines would have at the fleet's age rates,
    # over the fleet rate = crude ratio / age-standardised ratio.
    m = fleet.load('model_rates')
    m['mix'] = m.ratio_to_fleet / m.age_std_ratio.where(m.age_std_ratio > 0)
    own = m[m.own_rate]
    style.check('fx_03 age mix = expected (age only) / (months x fleet rate)', 0,
                float((own.mix - own.expected_age_only / (own.months * f / 100)).abs().max()), 1e-9)
    style.check('fx_03 age-only expected tickets add up to the fleet\'s tickets', F['tickets'],
                m.expected_age_only.sum(), 1e-6)
    biggest = own.sort_values(['months', 'model'], ascending=[False, True], kind='mergesort').iloc[0]
    style.check('fx_03 largest model by installed months', float(m.months.max()), biggest.months)
    mf = fleet.load('machine_flags')
    # Per-band counts drawn (tick labels, subtitle), recomputed: tickets and machines with a ticket from the
    # per-machine table, machines from the share column and the fleet total.
    by_band = mf.groupby('age_band').agg(tickets=('tickets', 'sum'), n=('serial_id', 'size')).reindex(bands)
    style.check('fx_03 band tickets = per-machine tickets by band', 0,
                float(np.abs(by_band.tickets.to_numpy() - a.tickets.to_numpy()).max()), 1e-9)
    style.check('fx_03 band machines with a ticket = per-machine rows by band', 0,
                int((by_band.n.to_numpy() != a.machines_with_ticket.to_numpy()).sum()))
    style.check('fx_03 band machines = share_of_machines x exposed machines', 0,
                float((a.machines - a.share_of_machines * F['machines_exposed']).abs().max()), 1e-6)
    style.check('fx_03 models with their own rate = models with min_type_months', len(own),
                int((m.months >= D['min_type_months']).sum()))
    first_year = mf[mf.model.isin(own.model)].groupby('model').install_year.min()
    rho = own.set_index('model').mix.rank().corr(first_year.reindex(own.model).rank())
    style.check('fx_03 newer models (later first install) have a younger age mix (rank correlation > 0.5)', 1,
                int(rho > 0.5))
    # Service status by age band, among the machines with a ticket (all that fx_machine_flags.csv holds).
    style.check('fx_03 machine flags = the machines with a ticket', F['machines_with_ticket'], len(mf))
    status = set(mf.service_status)
    style.check('fx_03 status labels named here exist', 1, int({WARRANTY, NOT_SERVICEABLE} <= status))
    style.check('fx_03 every machine with a ticket under warranty is in the youngest band', 0,
                int((mf[mf.service_status == WARRANTY].age_band != bands[0]).sum()))
    ns_bands = set(mf[mf.service_status == NOT_SERVICEABLE].age_band)
    ns_from = min(edges(b)[0] for b in ns_bands)
    style.check('fx_03 not serviceable machines with a ticket: none younger than stated', 0,
                int(sum(edges(b)[0] < ns_from for b in mf[mf.service_status == NOT_SERVICEABLE].age_band)))

    # ---------------------------------------------------------------------------------------------- Drawing
    title = (f'Machines under {years(lims[0][1])} old have {multiple:.1f}× the ticket rate of machines '
             f'{years(old_lo)} or older')
    width = max(10.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN)
    fig, ax = style.figure(width, HEIGHT)
    n = len(a)
    x = np.arange(n)
    span = n - 1 + 2 * X_PAD
    bar_w = (BAR_PX / style.DPI) / ((width - 2 * style.MARGIN - AXIS_LABEL_IN) / span)  # data units
    hot = np.isin(x, [0, n - 1])
    colors = np.where(hot, style.BLUE, style.GRAY_LIGHT)
    ymax = a.ci_hi.max() * 1.12

    ax.axhline(f, color=style.INK2, lw=1, zorder=1)
    ax.bar(x, a.rate_per_100, width=bar_w, color=colors, linewidth=0, zorder=2)
    ax.errorbar(x, a.rate_per_100, yerr=[a.rate_per_100 - a.ci_lo, a.ci_hi - a.rate_per_100], fmt='none',
                ecolor=style.INK2, elinewidth=1.2, capsize=3.5, capthick=1.2, zorder=3)
    for xi, row, h in zip(x, a.itertuples(), hot):
        label = f'{row.rate_per_100:.1f}'
        style.check(f'fx_03 drawn rate {row.age_band}', float(label), row.rate_per_100, 0.05)
        # Beside the bar top; a surface-coloured box keeps the fleet line from running through the digits.
        ax.text(xi + bar_w / 2 + 0.05, row.rate_per_100, label, ha='left', va='center', fontsize=9.5,
                color=style.INK if h else style.INK2, weight='bold' if h else 'normal', zorder=4,
                bbox=dict(boxstyle='square,pad=0.12', fc=style.SURFACE, ec='none'))
    ax.text(n - 1 + X_PAD, f, f'Fleet: {f:.1f}', ha='right', va='bottom', fontsize=9.5, color=style.INK2)

    ax.set_xticks(x)
    ax.set_xticklabels([f'{b.replace("-", "–")}\n{k:,} machines' for b, k in zip(bands, a.machines)],
                       color=style.INK2)
    for tick, h in zip(ax.get_xticklabels(), hot):
        if h:
            tick.set_fontweight('bold')
            tick.set_color(style.INK)
    ax.set_xlim(-X_PAD, n - 1 + X_PAD)
    ax.set_ylim(0, ymax)
    ax.yaxis.set_major_locator(MultipleLocator(Y_STEP))
    ax.yaxis.set_major_formatter(lambda v, _: f'{v:g}')
    style.check('fx_03 no gridline within half a step of the fleet line', 1,
                int(abs(f / Y_STEP - round(f / Y_STEP)) > 0.25))
    style.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel('Machine age band, years since install (at the midpoint of the machine\'s exposure)')
    ax.set_ylabel('Unplanned tickets per 100\ninstalled machine-months')

    # ---------------------------------------------------------------------------------------------- Text
    rng = lambda s: f'{s.min():.1f} to {s.max():.1f}' if len(s) > 1 else f'{s.iloc[0]:.1f}'  # noqa: E731
    subtitle = [f'Unplanned tickets per 100 installed machine-months by machine age band, {fleet.period_text(S)}, '
                f'with 95% intervals ({int(a.machines.sum()):,}{NBSP}machines, {int(a.tickets.sum()):,}{NBSP}tickets).',
                f'Under {years(lead_upper)} old: {rng(lead.rate_per_100)}, every interval above the fleet rate of '
                f'{f:.1f}. {mid_lo:g} to {years(mid_hi)}: {rng(mid.rate_per_100)}. {years(old_lo)} or older: '
                f'{old.rate_per_100:.1f} ({int(old.tickets):,}{NBSP}tickets on {int(old.machines):,}{NBSP}machines).']
    overlap = (f'Age overlaps with model and service status. Newer models have younger machines: on age mix alone, '
               f'the {len(own)} models with their own rate would run at {own.mix.min():.2f}× to {own.mix.max():.2f}× '
               f'the fleet rate ({biggest.model}, most installed months: {biggest.mix:.2f}×), so model comparisons '
               f'are age-standardised (charts fx_02, fx_09). Among machines with a ticket, all {WARRANTY} ones are '
               f'under {years(lims[0][1])} old and all {NOT_SERVICEABLE} ones {years(ns_from)} or older (chart '
               f'fx_04).')
    ci_note = (f'95% intervals: cluster bootstrap over accounts ({S["n_boot"]:,} draws), since tickets cluster '
               f'within accounts; each band spans {int(a.accounts.min())} or more accounts. The '
               f'{F["machines_zero_months"]} machines installed after the period have no age band.')
    source_note = (fleet.source('age_rates', 'model_rates', 'machine_flags').rstrip('.') +
                   '; fleet rate and totals from fx_summary.json.')
    style.frame(fig, title, subtitle,
                definitions=[fleet.unplanned_definition(), fleet.installed_month_definition(S),
                             fleet.AGE_STD_DEFINITION],
                notes=[overlap, ci_note, source_note])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
