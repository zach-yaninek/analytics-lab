#!/usr/bin/env python3
"""Fleet chart 5: unplanned tickets per 100 machine-months by telemetry machine type, with 95% intervals.

The telemetry machine type is the second way of grouping machines besides the model on IPA's list. Dividing each
type's unplanned tickets by its machine-months gives a rate that can be compared across types, and the interval
shows whether a type's rate is really different from its fleet's or within the noise. One dot per type with its own
rate (at least 100 machine-months) and at least MIN_TICKETS tickets, sorted by rate, with the type's machine (or
device) count on the axis label. The line through each dot is the 95% interval (cluster bootstrap over customers;
the wider of the bootstrap and Byar's Poisson interval for types in fewer than 10 customers). Blue = interval
wholly above the fleet rate, orange = wholly below, gray = the interval includes it (a lower-right legend, or a
colour key in the subtitle when the legend would cover the fleet line or the lowest rows). The vertical line is the
fleet rate of the same table. The title counts the types above and below that fleet (named: telemetry or networked,
since the other fx charts' "fleet" is the whole listed fleet) and names the highest-rate type with its multiple of
the fleet; the subtitle gives that type's tickets and devices, and the interval note names any type not shown whose
(unstable) rate is higher still. Value labels sit right of each interval, or left of it when that lands on the fleet
line, or right of the fleet line when the left side has no room.

The chart handles both exposure bases of fx_type_rates.csv (column exposure_basis):
  'telemetry-span' (interim, now): telemetry machine-months, i.e. months of Aug 2025 to Jul 2026 within each
     device's first-to-last-transaction span, and only the tickets inside a device's span. The fleet line is the
     telemetry fleet (all devices, all types). Defined by fleet.span_month_definition().
  'installed' (once verification/fleet_db_extract.py has joined the telemetry devices to IPA's installed-base
     list): installed machine-months of the listed machines with a telemetry device over the full period. The
     fleet line is those networked machines. Defined by fleet.installed_month_definition().
The period, axis label, definition, the source line and the basis note follow the basis. This chart replaces
high_ticket chart 10 (telemetry-span rates that also counted tickets outside a device's span and on devices with
no machine-months); the first note says so and, on the span basis, how chart 10's fleet rate differs.

Inputs (computed by verification/fleet_exposure.py; nothing is recomputed here except for the checks):
  verification/outputs/fleet/fx_type_rates.csv    one row per telemetry machine type: machines, clusters (span
                                                  basis) or accounts (installed basis), months, tickets,
                                                  rate_per_100, ci_lo/ci_hi (ci_method), byar_lo/hi, boot_lo/hi,
                                                  ratio_to_fleet, vs_fleet, fleet_rate_per_100, ratio_basis,
                                                  exposure_basis, own_rate
  verification/outputs/fleet/fx_summary.json      type_exposure_basis, type_span_tickets_outside_span, period,
                                                  min_type_months, min_clusters, z95, fleet totals
  span basis, for the checks and the chart-10 note:
    verification/outputs/htm_device_exposure.csv  months and tickets per device (recomputes every type's months,
                                                  tickets and devices independently)
    verification/outputs/htm_summary.json         the telemetry period and chart 10's fleet totals
    verification/outputs/htm_type_rates.csv       chart 10's tickets and machine-months
  installed basis, for a check (when present):
    verification/outputs/fleet/db/fxdb_devices.csv + fx_machine_flags.csv   tickets per type, recomputed
Output:  viz/figures/fx_05_rate_by_telemetry_type.png
Run:     cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/fx_05_rate_by_telemetry_type.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'fx_05_rate_by_telemetry_type.png'
MIN_TICKETS = 20          # types shown: own rate (min_type_months) and at least this many tickets
ROW_IN = 0.29             # inches per type row
TITLE_IN_PER_CHAR = 0.12  # approximate width of one title character (15 pt bold), for the figure width
CHAR_EM = 0.6             # conservative average character width in em (DejaVu Sans), for the legend-fit estimate
LEGEND_PT, TICK_PT = 9.5, 10  # legend and tick label sizes (ipa.mplstyle)
SPAN, INSTALLED = 'telemetry-span', 'installed'
BOOT = 'cluster bootstrap'
WIDER = 'wider of bootstrap and Byar'
UNKNOWN = 'Unknown'
CLASSES = [  # vs_fleet value, colour of the dot, colour of the interval, legend text, subtitle key (no legend)
    ('above', style.BLUE, style.BLUE, 'Above the fleet: 95% interval wholly above the fleet rate',
     'blue = 95% interval wholly above the fleet rate'),
    ('below', style.ORANGE, style.ORANGE, 'Below the fleet: interval wholly below', 'orange = wholly below it'),
    ('not different', style.GRAY, style.GRAY_LIGHT, 'Not different: interval includes the fleet rate',
     'gray = interval includes it'),
    ('not estimable (one account)', style.GRAY, style.GRAY_LIGHT, 'Not estimable: one customer',
     'gray = one customer, not estimable'),
]
Y_LO = -0.7               # lower y limit (rows at 0, 1, ...)
HTM_DEVICES = fleet.OUTPUTS / 'htm_device_exposure.csv'
HTM_TYPES = fleet.OUTPUTS / 'htm_type_rates.csv'
FXDB = fleet.FLEET / 'db' / 'fxdb_devices.csv'


def names(items):
    """'A', 'A and B', 'A, B and C'."""
    items = list(items)
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


def legend_fits(fig_w, ticks, legend_labels, xmax, f, right):
    """Whether a lower-right legend clears the fleet line and the intervals and value labels of the rows it covers.
    Sizes are estimated from character counts and font sizes before drawing, conservatively (nothing is measured):
    legend width against the axes width (figure less page margins and tick labels), legend height in rows of
    ROW_IN. right: each row's rightmost interval or label edge, in data units."""
    em = LEGEND_PT / 72
    leg_w = (max(map(len, legend_labels)) * CHAR_EM + 2.2 + 0.8 + 2 * 0.4 + 0.5) * em  # text, handle, pads
    leg_h = (len(legend_labels) * 1.5 + 2 * 0.4 + 0.5) * em                            # rows, pads
    axes_w = fig_w - 2 * style.MARGIN - (max(map(len, ticks)) * CHAR_EM * TICK_PT / 72 + 6 / 72)
    x_left = xmax * (1 - leg_w / axes_w)
    covered = np.arange(len(right)) - 0.35 < Y_LO + leg_h / ROW_IN
    return bool(f < x_left and (right[covered] < x_left).all())


def span_period():
    """'Aug 2025 to Jul 2026': the telemetry period of the span basis (htm_summary.json), not the case period."""
    lo, hi = (pd.Timestamp(x) for x in fleet.htm_summary()['definitions']['period'])
    return f'{lo:%b %Y} to {hi:%b %Y}'


def span_recount():
    """Devices, telemetry machine-months and in-span tickets per type, recomputed from the per-device exposure
    table (htm_device_exposure.csv): devices with months > 0, minus the tickets opened before the device's first or
    after its last transaction. Also the tickets that fall outside a span and those on 0-month devices."""
    h = pd.read_csv(HTM_DEVICES)
    e = h[h.months > 0].copy()
    e['machine_type'] = e.machine_type.astype(str).str.replace(r'^package name:\s*', '', regex=True)
    e['in_span'] = e.tickets_obs - e.tickets_before_first_active.fillna(0) - e.tickets_after_last_active.fillna(0)
    g = e.groupby('machine_type').agg(devices=('machine_id', 'size'), months=('months', 'sum'),
                                      tickets=('in_span', 'sum'))
    outside = int(e.tickets_obs.sum() - e.in_span.sum())
    zero_month = int(h.loc[h.months <= 0, 'tickets_obs'].sum())
    return g, outside, zero_month


def installed_recount():
    """Tickets per telemetry type on the installed basis, recomputed from the device extract (listed devices,
    one per serial) and the per-machine tickets in fx_machine_flags.csv (every machine with a ticket). None if the
    extract is absent."""
    if not FXDB.exists():
        return None
    db = pd.read_csv(FXDB)
    on = db[db.on_list.astype(str).isin(['1', 'True', 'true'])].drop_duplicates('serial_id')
    t = on.machine_type.map(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() else UNKNOWN)
    on = on.assign(machine_type=t.map(lambda x: UNKNOWN if x in (UNKNOWN, 'unknown') else x.lower()))  # as the analysis
    mf = fleet.load('machine_flags')[['serial_id', 'tickets']]
    return on.merge(mf, on='serial_id', how='left').fillna({'tickets': 0}).groupby('machine_type').tickets.sum()


def plot(out_dir=fleet.FIG_DIR):
    out_dir = Path(out_dir)
    S = fleet.summary()
    F, D = S['fleet'], S['definitions']
    t = fleet.load('type_rates')
    clusters = t['clusters'] if 'clusters' in t else t['accounts']

    basis = t.exposure_basis.iloc[0]
    style.check('fx_05 one exposure basis in the table', 1, int(t.exposure_basis.nunique() == 1))
    style.check('fx_05 exposure basis is known', 1, int(basis in (SPAN, INSTALLED)))
    style.check('fx_05 exposure basis = summary', 1, int(basis == S.get('type_exposure_basis', basis)))
    span = basis == SPAN
    unit = 'telemetry machine-month' if span else 'installed machine-month'
    who = 'devices' if span else 'machines'
    period = span_period() if span else fleet.period_text(S)

    # Fleet line: the table's own fleet (telemetry fleet, or the networked machines on the list), a ratio of totals.
    f = float(t.fleet_rate_per_100.iloc[0])
    style.check('fx_05 one fleet rate in the table', 0, float((t.fleet_rate_per_100 - f).abs().max()), 1e-9)
    style.check('fx_05 fleet rate = 100 x tickets / months (all type rows)', f,
                100 * t.tickets.sum() / t.months.sum(), 1e-9)
    style.check('fx_05 own rate = at least min_type_months months', 0,
                int((t.own_rate != (t.months >= D['min_type_months'])).sum()))
    style.check('fx_05 rates = 100 x tickets / months', 0,
                float((100 * t.tickets / t.months - t.rate_per_100).abs().max()), 1e-9)
    style.check('fx_05 ratio to fleet = rate / fleet rate', 0,
                float((t.rate_per_100 / f - t.ratio_to_fleet).abs().max()), 1e-9)

    if span:
        # Every type's devices, months and tickets, recounted from the per-device table.
        g, outside, zero_month = span_recount()
        g = g.reindex(t.machine_type)
        style.check('fx_05 span: every type in the device table', 0, int(g.months.isna().sum()))
        style.check('fx_05 span: months per type = device table', 0,
                    float(np.abs(g.months.to_numpy() - t.months.to_numpy()).max()), 1e-6)
        style.check('fx_05 span: tickets per type = in-span tickets of the device table', 0,
                    float(np.abs(g.tickets.to_numpy() - t.tickets.to_numpy()).max()))
        style.check('fx_05 span: devices per type = device table', 0,
                    float(np.abs(g.devices.to_numpy() - t.machines.to_numpy()).max()))
        style.check('fx_05 span: tickets outside a span = summary', S['type_span_tickets_outside_span'], outside)
        H = fleet.htm_summary()['D2_exposure']
        style.check('fx_05 span: devices = chart 10 devices with exposure', H['devices_with_exposure'],
                    int(t.machines.sum()))
        style.check('fx_05 span: months = chart 10 months', H['exposure_months_total'], t.months.sum(), 1e-6)
        style.check('fx_05 span: zero-month tickets = chart 10', H['tickets_on_zero_exposure_devices'], zero_month)
        h10 = pd.read_csv(HTM_TYPES)
        h10_tickets, h10_months = int(h10.tickets_used_for_rate.sum()), float(h10.exposure_months.sum())
        h10_rate = 100 * h10_tickets / h10_months
        style.check('fx_05 span: chart 10 fleet rate (htm_type_rates) = htm summary', H['overall_rate_per_100_months'],
                    h10_rate, 1e-4)
        style.check('fx_05 span: chart 10 tickets = these + outside spans + on 0-month devices', h10_tickets,
                    int(t.tickets.sum()) + outside + zero_month)
        style.check('fx_05 span: period in the table\'s ratio basis', 1, int(all(period in s for s in t.ratio_basis)))
        style.check('fx_05 span: period in the telemetry machine-month definition', 1,
                    int(period in fleet.span_month_definition()))
    else:
        rec = installed_recount()
        if rec is not None:
            rec = rec.reindex(t.machine_type).fillna(0)
            style.check('fx_05 installed: tickets per type = device extract x machine tickets', 0,
                        float(np.abs(rec.to_numpy() - t.tickets.to_numpy()).max()))
        style.check('fx_05 installed: networked tickets within the fleet', 1, int(t.tickets.sum() <= F['tickets']))
        style.check('fx_05 installed: networked months within the fleet', 1,
                    int(t.months.sum() <= F['months'] + 1e-6))
        style.check('fx_05 installed: networked machines within the fleet', 1,
                    int(t.machines.sum() <= F['machines_exposed']))

    # Types shown: own rate and at least MIN_TICKETS tickets.
    keep = t.own_rate & (t.tickets >= MIN_TICKETS)
    d, rest = t[keep].copy(), t[~keep]
    d['clusters'] = clusters[keep]
    weak =(d.clusters < D['min_clusters']) | (d.tickets == 0)
    style.check('fx_05 interval method = rule (clusters < min_clusters or no tickets)', 0,
                int((d.ci_method != np.where(weak, WIDER, BOOT)).sum()))
    lo = np.where(weak, np.fmin(d.boot_lo, d.byar_lo), d.boot_lo)
    hi = np.where(weak, np.fmax(d.boot_hi, d.byar_hi), d.boot_hi)
    style.check('fx_05 drawn intervals = bootstrap / wider-of rule', 0,
                float(max(np.abs(lo - d.ci_lo).max(), np.abs(hi - d.ci_hi).max())), 1e-9)
    # The colour comes from vs_fleet (the interval of the ratio to the fleet); it must agree with where the drawn
    # rate interval sits against the fleet line.
    drawn = np.select([d.ci_lo > f, d.ci_hi < f], ['above', 'below'], 'not different')
    single = d.vs_fleet.str.startswith('not estimable')
    style.check('fx_05 colour class = drawn interval against the fleet line', 0,
                int(((drawn != d.vs_fleet) & ~single).sum()))
    style.check('fx_05 every class has a colour', 1, int(set(d.vs_fleet) <= {c[0] for c in CLASSES}))
    style.check('fx_05 interval level 95% (z95 of the analysis)', 1.96, D['z95'], 0.001)

    d = d.sort_values(['rate_per_100', 'machine_type'], ascending=[True, False], kind='mergesort')  # highest on top
    n = len(d)
    top = d.iloc[-1]
    top_ratio = top.rate_per_100 / f
    style.check('fx_05 top ratio = ratio_to_fleet', top.ratio_to_fleet, top_ratio, 1e-9)
    style.check('fx_05 top type has the highest rate shown', 1, int(top.rate_per_100 == d.rate_per_100.max()))
    counts = d.vs_fleet.value_counts()
    n_above, n_below = int(counts.get('above', 0)), int(counts.get('below', 0))
    style.check('fx_05 types above (drawn intervals)', n_above, int((d.ci_lo > f).sum()))
    style.check('fx_05 types below (drawn intervals)', n_below, int((d.ci_hi < f).sum()))
    # The same counts from the analysis's ratio-to-fleet interval columns, independently of the vs_fleet labels.
    est = (d.clusters >= 2).to_numpy()
    style.check('fx_05 types above = ratio interval wholly above 1', n_above, int(((d.ratio_lo > 1) & est).sum()))
    style.check('fx_05 types below = ratio interval wholly below 1', n_below, int(((d.ratio_hi < 1) & est).sum()))
    style.check('fx_05 types not different = ratio interval includes 1', int(counts.get('not different', 0)),
                int(((d.ratio_lo <= 1) & (d.ratio_hi >= 1) & est).sum()))
    months_share = d.months.sum() / t.months.sum()
    style.check('fx_05 share of months shown = share_of_months column', d.share_of_months.sum(), months_share, 1e-9)
    tickets_share = d.tickets.sum() / t.tickets.sum()
    style.check('fx_05 share of tickets shown = share_of_tickets column', d.share_of_tickets.sum(), tickets_share,
                1e-9)
    # Types not shown whose (unstable) point rate is above the top type shown: named so "led by" is not misread.
    higher = rest[rest.rate_per_100 > top.rate_per_100].sort_values(['rate_per_100', 'machine_type'],
                                                                    ascending=[False, True], kind='mergesort')
    if span:
        # The selection and every count drawn, recounted from the per-device table (span_recount).
        gk = (g.months >= D['min_type_months']) & (g.tickets >= MIN_TICKETS)
        style.check('fx_05 span: types shown = device-table recount', n, int(gk.sum()))
        style.check('fx_05 span: same types as the device-table recount', 1,
                    int(set(g.index[gk]) == set(d.machine_type)))
        style.check('fx_05 span: rates shown = device table', 0,
                    float(np.abs(100 * g.tickets / g.months - t.set_index('machine_type').rate_per_100)[gk].max()),
                    1e-9)
        style.check('fx_05 span: fleet rate = device table', 100 * g.tickets.sum() / g.months.sum(), f, 1e-9)
        style.check('fx_05 span: share of months shown = device table', g.months[gk].sum() / g.months.sum(),
                    months_share, 1e-9)
        style.check('fx_05 span: share of tickets shown = device table', g.tickets[gk].sum() / g.tickets.sum(),
                    tickets_share, 1e-9)
        style.check('fx_05 span: types not shown = device table', len(g) - int(gk.sum()), len(rest))
        style.check('fx_05 span: devices not shown = device table', int(g.devices[~gk].sum()),
                    int(rest.machines.sum()))
        style.check('fx_05 span: tickets not shown = device table', int(g.tickets[~gk].sum()),
                    int(rest.tickets.sum()))
        for r in [top, *higher.itertuples(index=False)]:
            style.check(f'fx_05 span: {r.machine_type} tickets = device table', g.tickets[r.machine_type], r.tickets)
            style.check(f'fx_05 span: {r.machine_type} devices = device table', g.devices[r.machine_type],
                        r.machines)
        style.check('fx_05 span: types with a higher rate than the top type shown, not shown = device table',
                    len(higher), int(((100 * g.tickets / g.months) > top.rate_per_100)[~gk].sum()))

    def label(mt):
        return f'{UNKNOWN} (no type recorded)' if mt == UNKNOWN else mt

    def run(k):
        return 'runs' if k == 1 else 'run'

    fleet_word = 'telemetry' if span else 'networked'
    lead = (f'{n_above} of {n} telemetry types {run(n_above)}' if n_above else
            f'None of the {n} telemetry types runs')
    if top.vs_fleet == 'above':
        below = f'{n_below} {run(n_below)} below' if n_below else 'none runs below'
        title = (f'{lead} above the {fleet_word} fleet\'s ticket rate, led by {label(top.machine_type)} at '
                 f'{top_ratio:.1f}×; {below}')
    else:
        title = (f'{lead} above the {fleet_word} fleet\'s ticket rate and {n_below} below; the highest, '
                 f'{label(top.machine_type)} ({top_ratio:.1f}×), is within the noise')

    # ---- draw ----
    fig_w = max(10.0, TITLE_IN_PER_CHAR * len(title) + 2 * style.MARGIN)
    fig, ax = style.figure(fig_w, 4.6 + ROW_IN * n)
    y = np.arange(n)
    xmax = d.ci_hi.max() * 1.1
    pad, label_w = xmax * 0.012, xmax * 0.045  # value-label offset and approximate width (4 characters)
    ax.axvline(f, color=style.INK2, lw=1, zorder=1)
    handles = []
    for cls, dot, line, text, _ in CLASSES:
        sel = (d.vs_fleet == cls).to_numpy()
        if not sel.any():
            continue
        ax.hlines(y[sel], d.ci_lo[sel], d.ci_hi[sel], color=line, lw=2, zorder=2)
        ax.scatter(d.rate_per_100[sel], y[sel], s=55, color=dot, edgecolors=style.SURFACE, linewidths=1.2,
                   zorder=3)
        handles.append(Line2D([], [], color=line, lw=2, marker='o', ms=7.5, mfc=dot, mec=style.SURFACE,
                              label=f'{text} ({int(sel.sum())})'))
    right = np.empty(n)  # right edge of each row's interval and value label, for the legend-fit estimate
    for yi, row in zip(y, d.itertuples()):
        # Right of the interval; left of it if that lands on the fleet line; right of the fleet line if the left side
        # has no room either (the label would cross the axis at 0).
        if not row.ci_hi + pad < f < row.ci_hi + pad + label_w:
            x, ha = row.ci_hi + pad, 'left'
        elif row.ci_lo - pad - label_w > 0:
            x, ha = row.ci_lo - pad, 'right'
        else:
            x, ha = f + pad, 'left'
        right[yi] = max(row.ci_hi, x + label_w if ha == 'left' else x)
        hot = row.vs_fleet == 'above'
        ax.text(x, yi, f'{row.rate_per_100:.1f}', va='center', ha=ha, fontsize=9.5,
                color=style.INK if hot else style.INK2,
                weight='bold' if row.machine_type == top.machine_type else 'normal')
    fleet_name = 'Telemetry fleet' if span else 'Networked fleet'
    ax.text(f + pad, n - 0.45, f'{fleet_name}: {f:.1f}', va='bottom', ha='left', fontsize=9.5, color=style.INK2)
    ticks = [f'{label(mt)}  ·  {k:,} {who}' for mt, k in zip(d.machine_type, d.machines)]
    ax.set_yticks(y)
    ax.set_yticklabels(ticks, color=style.INK2)
    ax.set_ylim(Y_LO, n + 0.25)
    ax.set_xlim(0, xmax)
    style.style_axes(ax, grid='x', baseline=None)
    ax.set_xlabel(f'Unplanned tickets per 100 {unit}s')
    if legend_fits(fig_w, ticks, [h.get_label() for h in handles], xmax, f, right):
        ax.legend(handles=handles, loc='lower right', handlelength=2.2, frameon=True, facecolor=style.SURFACE,
                  edgecolor='none', framealpha=1)
        key = ''
    else:  # the legend would cover the fleet line or the lowest rows: colour key in the subtitle instead
        key = '; '.join(k for c, _, _, _, k in CLASSES if (d.vs_fleet == c).any())
        key = f' {key[0].upper()}{key[1:]}.'

    # ---- text ----
    if span:
        fleet_txt = (f'{f:.1f} = {int(t.tickets.sum()):,} tickets over {t.months.sum():,.0f} {unit}s on '
                     f'{int(t.machines.sum()):,} devices, all types (the telemetry fleet)')
        basis_note = (f'Replaces high_ticket chart 10 (fleet {h10_rate:.1f}), which also counted the {zero_month} '
                      f'tickets on devices with no {unit} and the {outside} opened outside a device\'s span. Interim '
                      f'exposure: telemetry devices, not the machines on IPA\'s installed-base list. Rates by type on '
                      f'installed-base exposure need the database extract (verification/fleet_db_extract.py), which '
                      f'joins the devices to the list.')
        source_note = ('Source: telemetry device spans (verification/outputs/htm_device_exposure.csv) joined to the '
                       'case export; verification/outputs/fleet/fx_type_rates.csv; chart 10 from '
                       'verification/outputs/htm_type_rates.csv.')
        cluster_txt = 'customers (a device with no customer counts under its host)'
        definition = fleet.span_month_definition()
    else:
        unnetworked = int(F['machines_exposed'] - t.machines.sum())
        style.check('fx_05 installed: listed fleet rate = 100 x fleet tickets / months', fleet.fleet_rate(S),
                    100 * F['tickets'] / F['months'], 1e-9)
        fleet_txt =(f'{f:.1f} = {int(t.tickets.sum()):,} tickets over {t.months.sum():,.0f} {unit}s on '
                     f'{int(t.machines.sum()):,} listed machines with a telemetry device, all types')
        basis_note = (f'Replaces high_ticket chart 10, which used telemetry-span exposure. Types come from the '
                      f'database extract (verification/fleet_db_extract.py), which joins the telemetry devices to '
                      f'IPA\'s installed-base list; the {unnetworked:,} listed machines without a device are in no '
                      f'type. Fleet line: the networked machines ({f:.1f}); the whole listed fleet runs at '
                      f'{fleet.fleet_rate(S):.1f}.')
        source_note = fleet.source('type_rates')
        cluster_txt = 'customers'
        definition = fleet.installed_month_definition(S)
    wider = d[d.ci_method == WIDER]
    wider_txt = (f'; for {names([label(x) for x in wider.machine_type])} (fewer than {D["min_clusters"]} customers), '
                 f'the wider of that and Byar\'s Poisson interval' if len(wider) else '')
    higher_txt = ''
    if len(higher):
        each = [f'{label(r.machine_type)} ({r.rate_per_100:.1f}, from {int(r.tickets)} tickets on {int(r.machines)} '
                f'{who})' for r in higher.itertuples()]
        higher_txt = (f'; {names(each)} {"has a higher rate" if len(higher) == 1 else "have higher rates"} than any '
                      f'type shown')
    ci_note = (f'95% intervals: cluster bootstrap over {cluster_txt}, since tickets cluster within customers'
               f'{wider_txt}. Not shown: {len(rest)} types with fewer than {D["min_type_months"]} {unit}s or fewer '
               f'than {MIN_TICKETS} tickets ({int(rest.machines.sum()):,} {who}, {int(rest.tickets.sum())} tickets '
               f'in all), too few for a stable rate{higher_txt}.')
    top_txt = (f'{label(top.machine_type)}\'s {top.rate_per_100:.1f} comes from {int(top.tickets)} tickets on '
               f'{int(top.machines)} {who}')
    style.frame(
        fig,
        title,
        f'Unplanned tickets per 100 {unit}s by telemetry machine type, {period}: the {n} types with at least '
        f'{D["min_type_months"]} {unit}s and {MIN_TICKETS} tickets ({months_share:.1%} of the months, '
        f'{tickets_share:.1%} of the tickets), sorted by rate, with 95% intervals. Fleet rate {fleet_txt}; '
        f'{top_txt}.{key}',
        definitions=[fleet.unplanned_definition(), definition],
        notes=[basis_note, ci_note, source_note])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
