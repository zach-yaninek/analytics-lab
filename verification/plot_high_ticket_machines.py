#!/usr/bin/env python3
"""Figures for high_ticket_machines.py (machines with an outsized share of unplanned service tickets).

Reads only the outputs that high_ticket_machines.py has already written:
  verification/outputs/htm_*.csv       every plotted series
  verification/outputs/htm_summary.json  four headline scalars that are simulation results and have no CSV column
                                         (D4 top-5% share null median / p95, D5 random-timing follow-up share)
  data/private/htm_private_customer_names.csv  real-name variant of chart 7 only (gitignored)
No database and no workbook. Every number printed on a chart is computed from these files at run time.

Writes (150 dpi PNG):
  verification/outputs/figures/htm_NN_<name>.png   pseudonymous (Customer NNN, M#####, models, categories)
  deliverables/htm_chronic_outliers_by_customer_REALNAMES.png   real customer names (gitignored; private=True only)

Run:  cd /home/user/analytics-lab && python3 -I verification/plot_high_ticket_machines.py
      (high_ticket_machines.py calls main() at the end of a normal run.)

Style: light surface #fcfcfb, ink #0b0b0b / #52514e / #898781, solid hairline grid #e1e0d9, baseline-only spine
#c3c2b7; emphasis blue #2a78d6 against gray; categorical blue / orange / aqua in that order (validated all-pairs on
the light surface; aqua is below 3:1, so every aqua mark has a legend entry); one-hue blue ramp for the heatmap.
"""
import json
import math
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / 'verification' / 'outputs'
FIG_DIR = OUTPUTS / 'figures'
PRIVATE = ROOT / 'data' / 'private'
DELIVERABLES = ROOT / 'deliverables'
SEED = 15072
DPI = 150

# Palette (fixed).
SURFACE = '#fcfcfb'
INK, INK2, MUTED = '#0b0b0b', '#52514e', '#898781'
GRID, BASE = '#e1e0d9', '#c3c2b7'
BLUE, ORANGE, AQUA = '#2a78d6', '#eb6834', '#1baf7a'
GRAY_LIGHT, GRAY = '#c3c2b7', '#898781'
ZERO_CELL = '#f2f1ec'
BLUE_RAMP = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf',
             '#1c5cab', '#184f95', '#104281']

CHECKS = []
TEXTS = {}  # figure path -> every text string drawn on it (for the privacy scan)


def _check(name, expected, actual, tol=0.0):
    ok = abs(float(expected) - float(actual)) <= tol
    CHECKS.append(ok)
    if not ok:
        print(f'  [WARN] {name}: summary {expected} vs CSV {actual}')


def pct(x, nd=1):
    return f'{100 * x:.{nd}f}%'


# ----------------------------------------------------------------------------------------------------------------
# Figure scaffolding
# ----------------------------------------------------------------------------------------------------------------
def setup(plt):
    plt.rcParams.update({
        'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
        'font.family': 'sans-serif', 'font.sans-serif': ['DejaVu Sans'], 'font.size': 10.5,
        'axes.edgecolor': BASE, 'axes.linewidth': 0.8, 'axes.labelcolor': MUTED, 'axes.labelsize': 10.5,
        'xtick.color': MUTED, 'ytick.color': MUTED, 'xtick.labelsize': 10, 'ytick.labelsize': 10,
        'xtick.major.size': 0, 'ytick.major.size': 0, 'xtick.major.pad': 6, 'ytick.major.pad': 6,
        'legend.frameon': False, 'legend.fontsize': 9.5, 'legend.labelcolor': INK2,
        'lines.solid_capstyle': 'round', 'lines.solid_joinstyle': 'round',
        'svg.fonttype': 'none', 'pdf.fonttype': 42,
    })


def new_fig(plt, w, h, left, bottom, right, top):
    """Figure of w x h inches with one axes inset by the given margins (inches)."""
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([left / w, bottom / h, 1 - (left + right) / w, 1 - (bottom + top) / h])
    return fig, ax


MARGIN = 0.35  # inches, left/right page margin for title, subtitle and footer


def _extent_in(fig, artist):
    """Bounding box of an artist in inches from the figure's lower-left corner: (x0, y0, x1, y1)."""
    r = fig.canvas.get_renderer()
    bb = artist.get_tightbbox(r) if hasattr(artist, 'get_tightbbox') else artist.get_window_extent(r)
    return bb.x0 / fig.dpi, bb.y0 / fig.dpi, bb.x1 / fig.dpi, bb.y1 / fig.dpi


def header(fig, title, subtitle, wrap=118):
    w, h = fig.get_size_inches()
    t = fig.text(MARGIN / w, 1 - 0.25 / h, title, ha='left', va='top', fontsize=15, weight='bold', color=INK)
    fig.canvas.draw()
    size = 15.0
    while _extent_in(fig, t)[2] > w - MARGIN and size > 12:  # safety net; titles are written to fit at 15 pt
        size -= 0.5
        t.set_fontsize(size)
        fig.canvas.draw()
    if size < 15:
        print(f'  [layout] title shrunk to {size} pt to fit: {title[:60]}...')
    s = fig.text(MARGIN / w, 1 - 0.62 / h, '\n'.join(textwrap.wrap(subtitle, wrap)), ha='left', va='top',
                 fontsize=10.5, color=INK2, linespacing=1.35)
    fig._htm_header = s


def footer(fig, lines, wrap=150):
    w, h = fig.get_size_inches()
    text = '\n'.join(textwrap.fill(s, wrap) for s in lines)
    f = fig.text(MARGIN / w, 0.16 / h, text, ha='left', va='bottom', fontsize=8.5, color=MUTED, linespacing=1.4)
    fig._htm_footer = f


def fit_axes(fig, ax, pad=0.18):
    """Shrink/move the axes so that its ticks, labels and legend sit between the subtitle and the footer and
    inside the page margins. Prints a note when it had to move something, so the change is visible."""
    w, h = fig.get_size_inches()
    for _ in range(3):
        fig.canvas.draw()
        x0, y0, x1, y1 = _extent_in(fig, ax)
        top_lim = _extent_in(fig, fig._htm_header)[1] - pad
        bot_lim = _extent_in(fig, fig._htm_footer)[3] + pad
        p = ax.get_position()
        L, B, R, T = p.x0 * w, p.y0 * h, p.x1 * w, p.y1 * h
        moved = False
        if y1 > top_lim + 1e-3:
            T -= y1 - top_lim
            moved = True
        if y0 < bot_lim - 1e-3:
            B += bot_lim - y0
            moved = True
        if x0 < MARGIN - 1e-3:
            L += MARGIN - x0
            moved = True
        if x1 > w - 0.15 + 1e-3:
            R -= x1 - (w - 0.15)
            moved = True
        if not moved:
            return
        ax.set_position([L / w, B / h, (R - L) / w, (T - B) / h])
    print('  [layout] axes could not be fitted fully between header and footer')


def style_axes(ax, grid='y', baseline='bottom'):
    for s in ax.spines.values():
        s.set_visible(False)
    if baseline:
        ax.spines[baseline].set_visible(True)
        ax.spines[baseline].set_color(BASE)
        ax.spines[baseline].set_linewidth(0.8)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.6, linestyle='-')
    ax.set_axisbelow(True)


def px_to_data_x(fig, ax, px):
    w_in = ax.get_position().width * fig.get_size_inches()[0]
    lo, hi = ax.get_xlim()
    return px * (hi - lo) / (w_in * DPI)


def px_to_data_y(fig, ax, px):
    h_in = ax.get_position().height * fig.get_size_inches()[1]
    lo, hi = ax.get_ylim()
    return px * abs(hi - lo) / (h_in * DPI)


def save(fig, plt, path, written, ax=None):
    if ax is not None:
        fit_axes(fig, ax)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw()
    from matplotlib.text import Text
    TEXTS[path] = [t.get_text() for t in fig.findobj(Text) if t.get_text()]
    fig.savefig(path, dpi=DPI, metadata={'Software': None})
    plt.close(fig)
    written.append(path)
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    print(f'  wrote {shown}')


def pct_axis(axis, nd=0):
    from matplotlib.ticker import FuncFormatter
    axis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:.{nd}f}%'))


def thousands_axis(axis):
    from matplotlib.ticker import FuncFormatter
    axis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))


# ----------------------------------------------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------------------------------------------
def load(outputs):
    rd = lambda n: pd.read_csv(outputs / f'htm_{n}.csv')  # noqa: E731
    d = {n: rd(n) for n in ('lorenz', 'machine_counts', 'device_exposure', 'type_mix', 'episodes', 'pre_ticket',
                            'pre_ticket_summary', 'customer_chronic', 'chronic_categories')}
    d['summary'] = json.loads((outputs / 'htm_summary.json').read_text())
    return d


# ----------------------------------------------------------------------------------------------------------------
# Charts
# ----------------------------------------------------------------------------------------------------------------
def chart_concentration(plt, D, out):
    L, dev, S = D['lorenz'], D['device_exposure'], D['summary']['D4_concentration']
    obs = np.sort(dev.tickets_obs.to_numpy())[::-1]
    k = math.ceil(0.05 * len(obs))
    top5_obs = obs[:k].sum() / obs.sum()
    _check('D4 top-5% share', S['top5_share_obs'], round(top5_obs, 4), 1e-4)
    _check('D4 devices', S['devices'], len(obs))
    gini_obs, gini_null = S['gini_obs'], S['gini_null_median']
    ge6 = int((obs >= 6).sum())
    _check('D4 devices >= 6', S['ge6_obs'], ge6)

    fig, ax = new_fig(plt, 10, 6.4, 0.95, 1.05, 0.4, 1.25)
    x = 100 * L.device_share
    ax.fill_between(x, 100 * L.ticket_share_null_p2_5, 100 * L.ticket_share_null_p97_5, color=GRAY_LIGHT,
                    alpha=0.45, linewidth=0, label='Chance: middle 95% of 1,000 draws')
    ax.plot(x, 100 * L.ticket_share_null_median, color=GRAY, lw=2, label='Chance: median draw')
    ax.plot(x, 100 * L.ticket_share_obs, color=BLUE, lw=2, label='Observed')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.axvline(5, color=MUTED, lw=0.8)
    y_obs, y_null = 100 * top5_obs, 100 * S['top5_share_null_median']
    ax.scatter([5, 5], [y_obs, y_null], s=60, c=[BLUE, GRAY], edgecolors=SURFACE, linewidths=1.6, zorder=5)
    # Labels sit below both curves (the area under the chance curve is empty right of x = 10%).
    ax.annotate(f'Top 5% of devices ({k:,})\nObserved: {pct(top5_obs)} of tickets',
                xy=(5, y_obs), xytext=(13, 27), fontsize=10, color=INK, va='center', linespacing=1.35,
                arrowprops=dict(arrowstyle='-', color=MUTED, lw=0.8, shrinkA=2, shrinkB=5))
    ax.annotate(f'Chance median: {pct(S["top5_share_null_median"])} '
                f'(95th percentile {pct(S["top5_share_null_p95"])})',
                xy=(5, y_null), xytext=(13, 15), fontsize=10, color=INK2, va='center',
                arrowprops=dict(arrowstyle='-', color=MUTED, lw=0.8, shrinkA=2, shrinkB=5))
    style_axes(ax, grid='both')
    pct_axis(ax.xaxis)
    pct_axis(ax.yaxis)
    ax.set_xlabel('Share of devices, ranked by tickets (most first)')
    ax.set_ylabel('Cumulative share of tickets')
    ax.legend(loc='lower right', handlelength=2.2)
    header(fig, f'The top 5% of devices hold {pct(top5_obs, 0)} of tickets; chance alone gives '
                f'{pct(S["top5_share_null_median"], 0)}',
           f'{len(obs):,} devices in the exposure population (non-shared hosts), {int(obs.sum()):,} unplanned tickets '
           f'Aug 2025 to Jul 2026. Chance = Poisson draws at each device\'s expected count (type rate x months '
           f'active), seed {SEED}.')
    footer(fig, [f'Gini over devices: {gini_obs:.3f} observed vs {gini_null:.3f} chance median. Devices with 6 or '
                 f'more tickets: {ge6} observed vs {S["ge6_null_median"]:.0f} chance median (95th percentile '
                 f'{S["ge6_null_p95"]:.0f}).',
                 'Source: htm_lorenz.csv, htm_device_exposure.csv, htm_summary.json (D4).'])
    save(fig, plt, out / 'htm_01_concentration_curve.png', D['written'], ax=ax)
    return {'top5_obs': top5_obs, 'top5_null': S['top5_share_null_median'], 'k': k}


def chart_tickets_per_machine(plt, D, out):
    m = D['machine_counts']
    vc = m.unplanned_tickets.value_counts().sort_index()
    n_mach, n_tix = len(m), int(m.unplanned_tickets.sum())
    outs = m[m.workload_outsized]
    thr = int(outs.unplanned_tickets.min())
    share_out = outs.unplanned_tickets.sum() / n_tix
    fixed = m[m.unplanned_tickets >= 6]
    S = D['summary']['D1_workload']
    _check('D1 threshold', S['threshold'], thr)
    _check('D1 outsized machines', S['outsized_machines'], len(outs))
    _check('D1 outsized ticket share', S['outsized_ticket_share'], round(share_out, 4), 1e-4)

    fig, ax = new_fig(plt, 10, 6.2, 0.95, 1.05, 0.4, 1.25)
    ax.set_xlim(0.3, vc.index.max() + 0.7)
    ax.set_ylim(0, vc.max() * 1.08)
    bw = min(0.7, px_to_data_x(fig, ax, 22))
    ax.bar(vc.index, vc.values, width=bw, color=BLUE, linewidth=0)
    for xv, yv in vc.items():
        if xv >= thr:
            ax.text(xv, yv + vc.max() * 0.012, f'{yv:,}', ha='center', va='bottom', fontsize=9, color=INK2)
    ax.axvline(thr - 0.5, color=INK2, lw=1)
    ax.text(thr - 0.5 + 0.3, vc.max() * 0.98,
            f'Workload-outsized: {thr} or more tickets\n{len(outs):,} machines ({pct(len(outs) / n_mach)}) '
            f'hold {pct(share_out)} of tickets', ha='left', va='top', fontsize=10, color=INK, linespacing=1.4)
    style_axes(ax, grid='y')
    ax.set_xticks(range(1, int(vc.index.max()) + 1))
    thousands_axis(ax.yaxis)
    ax.set_xlabel('Unplanned tickets per machine')
    ax.set_ylabel('Machines')
    header(fig, f'The {len(outs)} machines with {thr} or more tickets carry {pct(share_out)} of the unplanned load',
           f'{n_mach:,} ticketed machines (case-export serials) and {n_tix:,} unplanned tickets (excludes planned work, '
           f'cancelled and duplicate cases), case export Aug 2025 to Aug 2026.')
    footer(fig, [f'Threshold = ticket count of the 185th machine (top 5% of {n_mach:,}), ties included. Fixed '
                 f'threshold of 6 or more: {len(fixed)} machines with {pct(fixed.unplanned_tickets.sum() / n_tix)} '
                 f'of tickets. Maximum {int(vc.index.max())} tickets.',
                 'Source: htm_machine_counts.csv.'])
    save(fig, plt, out / 'htm_02_tickets_per_machine.png', D['written'], ax=ax)
    return {'thr': thr, 'outsized': len(outs), 'share': share_out}


CLASS_STYLE = [  # drawing order: context first
    ('chronic_outlier', 'Chronic outlier (outsized and rate outlier)', BLUE),
    ('rate_outlier_only', 'Rate outlier only', ORANGE),
    ('high_volume_expected', 'High volume, as expected for exposure', AQUA),
]


def chart_observed_expected(plt, D, out):
    d = D['device_exposure'].copy()
    rng = np.random.default_rng(SEED)
    d['yj'] = d.tickets_obs + rng.uniform(-0.22, 0.22, len(d))
    xmax = 3.4
    hidden = d[d.expected > xmax]
    zero = d[d.expected == 0]

    fig, ax = new_fig(plt, 10, 6.6, 0.95, 1.15, 0.4, 1.25)
    none = d[d['class'] == 'none']
    ax.scatter(none.expected, none.yj, s=7, color=GRAY_LIGHT, alpha=0.55, linewidths=0,
               label=f'Other devices ({len(none):,})', zorder=2)
    ax.plot([0, xmax], [0, xmax], color=MUTED, lw=1.2, label='Observed = expected', zorder=3)
    for cls, label, col in reversed(CLASS_STYLE):
        g = d[d['class'] == cls]
        ax.scatter(g.expected, g.yj, s=38, color=col, edgecolors=SURFACE, linewidths=0.9,
                   label=f'{label} ({len(g):,})', zorder=4)
    top = d.sort_values(['tickets_obs', 'machine_id'], ascending=[False, True]).iloc[0]
    ax.annotate(f'{top.machine_id} · {top.model}\n{int(top.tickets_obs)} tickets vs {top.expected:.2f} expected',
                xy=(top.expected, top.yj), xytext=(top.expected + 0.3, top.tickets_obs - 1.2), fontsize=9.5,
                color=INK2, va='center', linespacing=1.35,
                arrowprops=dict(arrowstyle='-', color=MUTED, lw=0.8, shrinkA=2, shrinkB=5))
    ax.set_xlim(-0.08, xmax)
    ax.set_ylim(-0.6, d.tickets_obs.max() + 1.5)
    style_axes(ax, grid='both')
    ax.set_xlabel('Expected tickets (type rate x months active)')
    ax.set_ylabel('Observed tickets in the period')
    handles, labels = ax.get_legend_handles_labels()
    order = [labels.index(lbl) for lbl in labels if lbl.startswith('Chronic')] + \
            [labels.index(lbl) for lbl in labels if lbl.startswith('Rate')] + \
            [labels.index(lbl) for lbl in labels if lbl.startswith('High')] + \
            [labels.index(lbl) for lbl in labels if lbl.startswith('Other')] + \
            [labels.index(lbl) for lbl in labels if lbl.startswith('Observed')]
    leg = ax.legend([handles[i] for i in order], [labels[i] for i in order], loc='upper right',
                    markerscale=1.0, handletextpad=0.6, borderaxespad=0.3)
    for h in leg.legend_handles:
        if hasattr(h, 'set_sizes'):
            h.set_sizes([38])
            h.set_alpha(1)
    ch = d[d['class'] == 'chronic_outlier']
    header(fig, f'Chronic outliers logged a median of {ch.tickets_obs.median():.0f} tickets where about '
                f'{ch.expected.median():.1f} was expected',
           f'{len(d):,} devices in the exposure population (non-shared hosts), unplanned tickets Aug 2025 to Jul 2026. '
           f'Rate outlier = Poisson BH q < 0.05 against same-type peers; outsized = top-5% workload serial.')
    footer(fig, [f'Points jittered vertically by up to 0.22 to show overlap. {len(zero)} devices with zero exposure '
                 f'months sit at x = 0 (not tested). {len(hidden)} devices with expected > {xmax} (pooled small '
                 f'types, none flagged) are off the right edge.',
                 'Source: htm_device_exposure.csv.'])
    save(fig, plt, out / 'htm_03_observed_vs_expected.png', D['written'], ax=ax)
    return {'chronic_obs_median': ch.tickets_obs.median(), 'chronic_exp_median': ch.expected.median()}


def chart_model_mix(plt, D, out, n=10):
    tm = D['type_mix']
    m = tm[tm.field == 'model'].copy()
    n_out, n_oth = int(m.outsized_machines.sum()), int(m.other_machines.sum())
    m['gap'] = m.outsized_share - m.other_share
    m = m.reindex(m.gap.abs().sort_values(ascending=False, kind='mergesort').index)
    rest_max = m.gap.abs().iloc[n:].max()
    top = m.head(n).sort_values('gap', kind='mergesort')  # largest positive gap at the top of the chart
    y = np.arange(len(top))

    fig, ax = new_fig(plt, 10, 6.4, 1.75, 1.05, 0.4, 1.35)
    for yi, (a, b) in zip(y, zip(top.other_share, top.outsized_share)):
        ax.plot([100 * a, 100 * b], [yi, yi], color=GRAY_LIGHT, lw=2, zorder=2)
    ax.scatter(100 * top.other_share, y, s=70, color=GRAY, edgecolors=SURFACE, linewidths=1.6, zorder=3,
               label=f'Other ticketed machines ({n_oth:,})')
    ax.scatter(100 * top.outsized_share, y, s=70, color=BLUE, edgecolors=SURFACE, linewidths=1.6, zorder=4,
               label=f'Workload-outsized machines ({n_out:,})')
    lead = top.iloc[-1]
    ax.text(100 * max(lead.outsized_share, lead.other_share) + 0.6, y[-1],
            f'{pct(lead.outsized_share)} vs {pct(lead.other_share)}', va='center', fontsize=9.5, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(top.value, color=INK2)
    ax.set_ylim(-0.7, len(top) - 0.3)
    ax.set_xlim(0, 100 * max(top.outsized_share.max(), top.other_share.max()) + 4)
    style_axes(ax, grid='x', baseline=None)
    pct_axis(ax.xaxis)
    ax.set_xlabel('Share of machines in the group')
    # Rows 2-9 end before 14%, so the right-hand middle of the plot is empty.
    ax.legend(loc='center right', bbox_to_anchor=(1.0, 0.5), handletextpad=0.4)
    header(fig, f'Outsized machines\' model mix differs from the rest by {100 * m.gap.abs().max():.0f} points '
                f'at most',
           f'Share of machines by model: {n_out} workload-outsized vs {n_oth:,} other ticketed machines (case-export '
           f'serials), unplanned tickets Aug 2025 to Aug 2026. The {n} models with the largest gap, sorted by gap.')
    footer(fig, [f'The other {len(m) - n} models differ by less than {100 * rest_max:.1f} points. Model as recorded in '
                 f'the case export.', 'Source: htm_type_mix.csv (field = model).'])
    save(fig, plt, out / 'htm_04_model_mix.png', D['written'], ax=ax)
    return {'lead': lead.value, 'lead_out': lead.outsized_share, 'lead_oth': lead.other_share,
            'max_gap': m.gap.abs().max()}


def chart_episodes(plt, D, out):
    ep = D['episodes']
    S = D['summary']['D5_episodes']
    rows = [('outsized', 'Workload-outsized machines', ep[ep.workload_outsized], BLUE),
            ('other', 'Other ticketed machines', ep[~ep.workload_outsized], GRAY)]
    vals = {}
    for key, _, g, _ in rows:
        t = g.tickets.sum()
        vals[key] = {gap: 1 - g[f'episodes_{gap}d'].sum() / t for gap in (3, 7, 14)}
        vals[key]['n'], vals[key]['t'] = len(g), int(t)
        _check(f'D5 {key} 7d follow-up share', S[key]['followup_share_7d'], round(vals[key][7], 4), 1e-4)

    # Each group gets two sub-rows on one shared x-axis: observed (7-day dot, 3-14-day range) and the random-timing
    # reference (median, 95% interval) just below, so the two never overlap.
    fig, ax = new_fig(plt, 10, 5.8, 2.75, 1.2, 0.5, 1.75)
    y_obs = {'outsized': 3.0, 'other': 1.0}
    gap_rt = 0.68
    rts = {}
    for key, label, g, col in rows:
        v, yv = vals[key], y_obs[key]
        lo, hi, mid = 100 * v[3], 100 * v[14], 100 * v[7]
        ax.plot([lo, hi], [yv, yv], color=GRAY_LIGHT, lw=2, zorder=2)
        for e in (lo, hi):
            ax.plot([e, e], [yv - 0.1, yv + 0.1], color=MUTED, lw=1.2, zorder=2)
        # 7-day value above the dot; the 3- and 14-day values below the range ends (never on the same line).
        ax.text(lo, yv - 0.17, f'3-day {lo:.1f}%', ha='center', va='top', fontsize=9, color=MUTED)
        ax.text(hi, yv - 0.17, f'14-day {hi:.1f}%', ha='center', va='top', fontsize=9, color=MUTED)
        ax.scatter([mid], [yv], s=120, color=col, edgecolors=SURFACE, linewidths=1.8, zorder=4)
        ax.text(mid, yv + 0.2, f'{mid:.1f}%', ha='center', va='bottom', fontsize=10.5, color=INK, weight='bold')
        rt_med, rt_lo, rt_hi = S[key]['followup_share_7d_random_timing']
        rts[key] = rt_med
        yr = yv - gap_rt
        ax.plot([100 * rt_lo, 100 * rt_hi], [yr, yr], color=MUTED, lw=1, zorder=2)
        ax.scatter([100 * rt_med], [yr], s=55, marker='D', facecolors=SURFACE, edgecolors=INK2, linewidths=1.3,
                   zorder=3)
        ax.text(100 * rt_hi + 0.6, yr, f'random timing {100 * rt_med:.1f}%', ha='left', va='center', fontsize=9,
                color=INK2)
    ax.set_yticks([y_obs[k] for k, _, _, _ in rows])
    ax.set_yticklabels([f'{lbl}\n{vals[k]["n"]:,} machines · {vals[k]["t"]:,} tickets' for k, lbl, _, _ in rows],
                       color=INK2, linespacing=1.35)
    ax.set_ylim(1.0 - gap_rt - 0.45, 3.0 + 0.75)
    ax.set_xlim(0, 100 * max(v[14] for v in vals.values()) + 4)
    style_axes(ax, grid='x', baseline=None)
    pct_axis(ax.xaxis)
    ax.set_xlabel('Share of tickets that are follow-ups (opened within the window after the machine\'s previous '
                  'ticket)')
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], marker='o', ls='', ms=9.5, mfc=INK2, mec=SURFACE, label='7-day rule'),
               Line2D([], [], color=GRAY_LIGHT, lw=2, label='3- to 14-day rule (range)'),
               Line2D([], [], marker='D', ls='-', lw=1, color=MUTED, ms=7, mfc=SURFACE, mec=INK2, mew=1.3,
                      label='Random timing, same counts (median, 95%)')]
    ax.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.45, 1.0), ncol=3, handletextpad=0.5,
              columnspacing=1.6)
    ratio = vals['outsized'][7] / vals['other'][7]
    header(fig, f'Outsized machines\' tickets are 7-day follow-ups {ratio:.1f}x as often '
                f'({pct(vals["outsized"][7])} vs {pct(vals["other"][7])})',
           f'All {sum(v["t"] for v in vals.values()):,} unplanned tickets on {len(ep):,} machines (case-export '
           f'serials), Aug 2025 to Aug 2026. A ticket is a follow-up if it opens within 7 days of the machine\'s '
           f'previous ticket (sensitivity: 3 and 14 days).')
    footer(fig, [f'Random timing: each machine\'s tickets placed uniformly at random over the period (200 draws, a '
                 f'rough null). More tickets alone produce more follow-ups: {pct(rts["outsized"])} for outsized '
                 f'machines and {pct(rts["other"])} for the rest.',
                 'Source: htm_episodes.csv; random timing from htm_summary.json (D5).'])
    save(fig, plt, out / 'htm_05_episode_followups.png', D['written'], ax=ax)
    return vals


PRE_GROUPS = [('chronic', 'Chronic outliers', BLUE), ('workload_outsized', 'Other outsized machines', ORANGE),
              ('other', 'Other machines', GRAY)]


def _ecdf(ax, values, color, label, lw=2.0, z=3):
    v = np.sort(np.asarray(values, float))
    n = len(v)
    x = np.concatenate([[0.0], v])
    y = np.concatenate([[0.0], np.arange(1, n + 1) / n])
    ax.plot(x, 100 * y, drawstyle='steps-post', color=color, lw=lw, label=label, zorder=z)


def chart_pre_ticket(plt, D, out):
    pt = D['pre_ticket']
    res = {}
    specs = [('all_events_30d', 8000, 'Telemetry events in the 30 days before the ticket', 'events', 'events',
              'htm_06_pre_ticket_events.png'),
             ('non_success_per_1000', 600, 'Non-success events per 1,000 events in the 30 days before the ticket',
              'per 1,000', 'nonsuccess', 'htm_06_pre_ticket_nonsuccess.png')]
    for col, xmax, xlabel, unit, key, fname in specs:
        fig, ax = new_fig(plt, 10, 6.2, 0.95, 1.3, 0.4, 1.25)
        med, beyond, ns, ms = {}, {}, {}, {}
        for z, (g, label, color) in zip((5, 4, 3), PRE_GROUPS):
            v = pt.loc[pt.group == g, col].dropna()
            med[g], beyond[g], ns[g] = v.median(), int((v > xmax).sum()), len(v)
            ms[g] = pt.loc[(pt.group == g) & pt[col].notna(), 'machine_id'].nunique()
            fmt = f'{med[g]:,.0f}' if key == 'events' else f'{med[g]:.1f}'
            _ecdf(ax, v, color, f'{label}: {len(v):,} tickets on {ms[g]:,} machines, median {fmt} {unit}', z=z)
        ax.set_xlim(0, xmax)
        ax.set_ylim(0, 101)
        style_axes(ax, grid='both')
        thousands_axis(ax.xaxis)
        pct_axis(ax.yaxis)
        ax.set_xlabel(xlabel)
        ax.set_ylabel('Share of tickets at or below x')
        ax.legend(loc='lower right', handlelength=2.2)
        res[key] = med
        out_txt = ', '.join(f'{lbl.split()[0].lower() if g != "workload_outsized" else "other outsized"} '
                            f'{beyond[g]}' for g, lbl, _ in PRE_GROUPS)
        if key == 'events':
            zs = {g: (pt.loc[pt.group == g, col] == 0).mean() for g, _, _ in PRE_GROUPS}
            title = (f'Chronic outliers were busier before tickets: median {med["chronic"]:,.0f} events vs '
                     f'{med["other"]:,.0f}')
            notes = [f'Lines start above 0 where the device logged no events in the window (chronic '
                     f'{pct(zs["chronic"])}, other outsized {pct(zs["workload_outsized"])}, other {pct(zs["other"])}). '
                     f'Axis cut at {xmax:,}; tickets beyond: {out_txt}.']
        else:
            ps = D['pre_ticket_summary'].set_index(['group', 'window'])
            pc = ps.loc[('chronic', 'ticket (paired)')], ps.loc[('chronic', 'control (paired)')]
            po = ps.loc[('other', 'ticket (paired)')], ps.loc[('other', 'control (paired)')]
            title = (f'Chronic outliers logged more non-success events: median {med["chronic"]:.0f} vs '
                     f'{med["other"]:.0f} per 1,000')
            notes = [f'Tickets with no events in the window are left out. Axis cut at {xmax}; tickets beyond: '
                     f'{out_txt}. Same machine 35 days earlier (clean paired controls): chronic '
                     f'{pc[0].non_success_per_1000_median:.1f} before the ticket vs {pc[1].non_success_per_1000_median:.1f}'
                     f' in the control window; other machines {po[0].non_success_per_1000_median:.1f} vs '
                     f'{po[1].non_success_per_1000_median:.1f}.']
        header(fig, title,
               f'Unplanned tickets on device-matched machines with a usable 30-day telemetry window '
               f'({sum(ns.values()):,} tickets), by machine group. Telemetry in UTC; ticket time converted from '
               f'US Eastern.')
        footer(fig, notes + ['Source: htm_pre_ticket.csv' + (', htm_pre_ticket_summary.csv.' if key != 'events'
                                                               else '.')])
        save(fig, plt, out / fname, D['written'], ax=ax)
    return res


def chart_customers(plt, D, out, names=None, path=None, max_rows=25):
    cu = D['customer_chronic']
    c = cu[cu.chronic_outlier_machines > 0].copy()
    n_cust, n_mach = len(c), int(c.chronic_outlier_machines.sum())
    singles = int((c.chronic_outlier_machines == 1).sum())
    c = c.sort_values(['chronic_outlier_machines', 'exposure_devices', 'customer'], ascending=[False, False, True],
                      kind='mergesort')
    shown = c[c.chronic_outlier_machines >= 2]
    if len(shown) > max_rows or len(shown) < 10:
        shown = c.head(max_rows)
    rest = c.iloc[len(shown):]
    labels = shown.customer.tolist()
    if names is not None:
        labels = [names.get(x, x) for x in labels]
    label_w = max(1.5, 0.075 * max(len(s) for s in labels) + 0.3)
    h = 1.9 + 0.38 * len(shown) + 0.9
    fig, ax = new_fig(plt, 10 + max(0.0, label_w - 1.5), h, label_w, 1.2, 0.5, 1.45)
    y = np.arange(len(shown))[::-1]
    ax.set_ylim(-0.6, len(shown) - 0.4)
    xmax = shown.exposure_devices.max()
    ax.set_xlim(0, xmax * 1.16)
    bh = min(0.7, px_to_data_y(fig, ax, 22))
    ax.barh(y, shown.exposure_devices, height=bh, color='#e8e7e1', linewidth=0,
            label='Customer\'s devices in the exposure population')
    ax.barh(y, shown.chronic_outlier_machines, height=bh, color=BLUE, linewidth=0,
            label='Chronic-outlier machines')
    for yi, (k, tot) in zip(y, zip(shown.chronic_outlier_machines, shown.exposure_devices)):
        ax.text(tot + xmax * 0.012, yi, f'{k} of {tot}', va='center', ha='left', fontsize=9.5, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=INK2)
    style_axes(ax, grid='x', baseline='left')
    ax.set_xlabel('Devices')
    # The bottom rows are short bars, so the lower right of the plot is empty.
    ax.legend(loc='lower right', handlelength=1.4)
    top = c.iloc[0]
    title = f'Chronic outliers are spread thinly: {singles} of {n_cust} customers have just one'
    sub = (f'{n_mach} chronic-outlier machines across {n_cust} customers, unplanned tickets Aug 2025 to Jul 2026. '
           f'Customers with 2 or more shown against their devices in the exposure population (non-shared hosts).')
    if len(rest) == 0:
        rest_txt = 'none.'
    elif rest.chronic_outlier_machines.max() == 1:
        rest_txt = f'{len(rest)} customers with 1 chronic outlier each.'
    else:
        rest_txt = (f'{len(rest)} customers with {int(rest.chronic_outlier_machines.min())} to '
                    f'{int(rest.chronic_outlier_machines.max())} chronic outliers.')
    notes = [f'Not shown: {rest_txt} Customer = the device location\'s customer (ticket account where missing). '
             f'Rows sorted by chronic outliers, then devices.',
             'Source: htm_customer_chronic.csv.']
    if names is not None:
        notes.insert(0, 'Contains IPA customer names: for the project team and IPA only. Keep in deliverables/ '
                        '(gitignored); never commit.')
    header(fig, title, sub, wrap=int(118 * fig.get_size_inches()[0] / 10))
    footer(fig, notes, wrap=int(150 * fig.get_size_inches()[0] / 10))
    save(fig, plt, path or (out / 'htm_07_chronic_outliers_by_customer.png'), D['written'], ax=ax)
    return {'customers': n_cust, 'singles': singles, 'shown': len(shown), 'top': top.customer,
            'top_k': int(top.chronic_outlier_machines), 'top_dev': int(top.exposure_devices)}


def chart_categories(plt, D, out, n_rows=30, n_cols=10):
    from matplotlib.colors import BoundaryNorm, ListedColormap
    cc = D['chronic_categories'].copy()
    cc['category'] = cc.category.replace({'[Missing]': 'Category missing'})
    tot = cc.groupby('category').tickets.sum().reset_index()
    tot = tot.sort_values(['tickets', 'category'], ascending=[False, True], kind='mergesort')
    cols = tot.category.head(n_cols).tolist()
    n_other_cats = len(tot) - len(cols)
    cc['col'] = cc.category.where(cc.category.isin(cols), 'Other')
    mach = cc.groupby(['machine_id', 'model', 'total_tickets'], as_index=False).size()
    mach = mach.sort_values(['total_tickets', 'machine_id'], ascending=[False, True], kind='mergesort')
    dom = cc.groupby('machine_id').tickets.max() / cc.groupby('machine_id').total_tickets.first()
    n_dom = int((dom >= 0.5).sum())
    rows = mach.head(n_rows)
    rest = mach.iloc[n_rows:]
    piv = cc[cc.machine_id.isin(rows.machine_id)].pivot_table(index='machine_id', columns='col', values='tickets',
                                                              aggfunc='sum', fill_value=0)
    piv = piv.reindex(index=rows.machine_id, columns=cols + ['Other'], fill_value=0)
    _check('heatmap rows sum to totals', 0, int((piv.sum(axis=1).to_numpy() - rows.total_tickets.to_numpy()).sum()))
    vals = piv.to_numpy()
    vmax = int(vals.max())

    w, h = 10.5, 1.6 + 0.3 * len(rows) + 2.3
    fig, ax = new_fig(plt, w, h, 3.05, 0.95, 1.25, 2.55)
    # Discrete one-hue ramp: one step per count (1..vmax), zero = neutral off-surface cell.
    idx = np.linspace(0, len(BLUE_RAMP) - 1, vmax).round().astype(int)
    cmap = ListedColormap([ZERO_CELL] + [BLUE_RAMP[i] for i in idx])
    norm = BoundaryNorm(np.arange(-0.5, vmax + 1.5), cmap.N)
    mesh = ax.pcolormesh(np.arange(vals.shape[1] + 1), np.arange(vals.shape[0] + 1), vals, cmap=cmap, norm=norm,
                         edgecolors=SURFACE, linewidth=2.0)
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            v = int(vals[i, j])
            if v:
                dark = idx[v - 1] >= 6
                ax.text(j + 0.5, i + 0.5, str(v), ha='center', va='center', fontsize=9.5,
                        color='white' if dark else INK, weight='bold' if dark else 'normal')
    ax.set_ylim(vals.shape[0], 0)
    ax.set_xlim(0, vals.shape[1])
    ax.set_yticks(np.arange(vals.shape[0]) + 0.5)
    ax.set_yticklabels([f'{r.machine_id} · {r.model} · {r.total_tickets} tickets' for r in rows.itertuples()],
                       color=INK2, fontsize=9.5)
    ax.xaxis.tick_top()
    ax.set_xticks(np.arange(vals.shape[1]) + 0.5)
    col_n = dict(zip(tot.category, tot.tickets))
    other_n = int(tot.tickets.iloc[n_cols:].sum())
    ax.set_xticklabels([f'{c} ({col_n[c]})' for c in cols] + [f'Other ({other_n})'], rotation=40, ha='left',
                       rotation_mode='anchor', color=INK2, fontsize=9.5)
    style_axes(ax, grid=None, baseline=None)
    header(fig, f'One category makes up half or more of the tickets on {n_dom} of {len(mach)} chronic outliers',
           f'Unplanned tickets by category for the {len(rows)} chronic-outlier machines with the most tickets '
           f'(case-export serials, Aug 2025 to Aug 2026). Columns: the {n_cols} most frequent categories across all '
           f'{len(mach)} chronic outliers, with their totals.', wrap=126)
    footer(fig, [f'Rows sorted by total tickets, then machine id. Not shown: {len(rest)} chronic outliers with '
                 f'{int(rest.total_tickets.min())} to {int(rest.total_tickets.max())} tickets. Other = {n_other_cats} '
                 f'further categories.', 'Source: htm_chronic_categories.csv (full table, all 113 machines).'],
           wrap=158)
    fit_axes(fig, ax)
    p = ax.get_position()
    cax = fig.add_axes([p.x1 + 0.3 / w, p.y1 - p.height * 0.4, 0.16 / w, p.height * 0.4])
    cb = fig.colorbar(mesh, cax=cax, ticks=range(0, vmax + 1, 2 if vmax > 8 else 1))
    cb.outline.set_visible(False)
    cb.ax.tick_params(length=0, labelsize=9, colors=MUTED)
    cb.set_label('tickets', color=MUTED, fontsize=10)
    save(fig, plt, out / 'htm_08_chronic_categories_heatmap.png', D['written'])
    return {'n_dom': n_dom, 'n_mach': len(mach), 'cols': cols[:3], 'rows': len(rows)}


# ----------------------------------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------------------------------
def main(out_dir=FIG_DIR, private=True, outputs=OUTPUTS, deliverables=DELIVERABLES):
    try:
        import matplotlib
    except ImportError:
        print('Plots skipped: matplotlib is not installed.')
        return []
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    setup(plt)
    out_dir = Path(out_dir)
    print(f'Plots -> {out_dir} ...')
    D = load(Path(outputs))
    D['written'] = []
    CHECKS.clear()
    chart_concentration(plt, D, out_dir)
    chart_tickets_per_machine(plt, D, out_dir)
    chart_observed_expected(plt, D, out_dir)
    chart_model_mix(plt, D, out_dir)
    chart_episodes(plt, D, out_dir)
    chart_pre_ticket(plt, D, out_dir)
    chart_customers(plt, D, out_dir)
    if private:
        names_path = PRIVATE / 'htm_private_customer_names.csv'
        if names_path.exists():
            pn = pd.read_csv(names_path)
            names = dict(zip(pn.customer, pn.real_account_name))
            chart_customers(plt, D, out_dir, names=names,
                            path=Path(deliverables) / 'htm_chronic_outliers_by_customer_REALNAMES.png')
        else:
            print(f'  real-name variant skipped: {names_path.relative_to(ROOT)} not found')
    chart_categories(plt, D, out_dir)
    bad = len(CHECKS) - sum(CHECKS)
    print(f'  {len(D["written"])} figures; CSV-vs-summary consistency checks: {sum(CHECKS)} pass, {bad} warn')
    leaks = privacy_scan([q for q in D['written'] if q.parent == out_dir])
    if leaks is not None:
        print(f'  privacy scan of pseudonymous figures: {leaks} real name/serial strings found '
              f'({"PASS" if leaks == 0 else "FAIL"})')
        if leaks:
            raise RuntimeError('a pseudonymous figure contains a real customer name or serial')
    return D['written']


def privacy_scan(paths):
    """Count real customer names / serials (from the gitignored private tables) that appear in any text drawn on
    the given figures. Returns None when the private tables are absent. Never prints the matched strings."""
    files = [PRIVATE / 'htm_private_customer_names.csv', PRIVATE / 'htm_private_outsized_machines.csv']
    if not all(f.exists() for f in files):
        return None
    pn, pm = (pd.read_csv(f) for f in files)
    real = set(pn.real_account_name.dropna().astype(str))
    real |= set(pm.real_serial.dropna().astype(str)) | set(pm.customer_real_name.dropna().astype(str))
    for col in ('real_account_modal', 'real_accounts_all'):
        for v in pm[col].dropna().astype(str):
            real |= {x.strip() for x in v.split(' | ')}
    real = {r for r in real if len(r) >= 4 and not r.isdigit()}  # short / all-digit strings collide with counts
    hits = 0
    for path in paths:
        blob = '\n'.join(TEXTS.get(path, []))
        hits += sum(r in blob for r in real)
    return hits


if __name__ == '__main__':
    main()
    sys.exit(0)
