"""Shared style, data loading and definitions for the high-ticket-machine charts (verification/plots/htm_*.py).

Every chart script imports this module, draws one chart with ordinary matplotlib and saves it with save(). The
chart scripts read only the outputs that verification/high_ticket_machines.py has already written:
  verification/outputs/htm_*.csv         every plotted series
  verification/outputs/htm_summary.json  definitions (thresholds) and a few simulation results with no CSV column

Page layout: frame() writes the title and subtitle above the plot area and the definition and notes below it, then
reserves both bands through the constrained-layout rect. Band heights come from wrapped line counts and font sizes,
so nothing is measured after drawing.

Style: light surface #fcfcfb, ink #0b0b0b / #52514e / #898781, solid hairline grid #e1e0d9, baseline-only spine
#c3c2b7; emphasis blue #2a78d6 against gray; categorical blue / orange / aqua in that order (validated all-pairs on
the light surface; aqua is below 3:1, so every aqua mark has a legend entry); one-hue blue ramp for the heatmap.
"""
import json
import textwrap
from pathlib import Path

import matplotlib
import pandas as pd

if matplotlib.get_backend().lower() not in ('agg', 'module://matplotlib_inline.backend_inline'):
    matplotlib.use('Agg')  # headless runs; notebooks keep their inline backend
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
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
BAR_BACKGROUND = '#e8e7e1'
ZERO_CELL = '#f2f1ec'
BLUE_RAMP = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf',
             '#1c5cab', '#184f95', '#104281']

# Page geometry (inches / points).
MARGIN = 0.35         # left and right page margin for title, subtitle, definition and notes
TITLE_PT, SUB_PT, NOTE_PT = 15, 10.5, 8.5
SUB_CHARS_PER_IN = 13.2   # DejaVu Sans, average characters per inch at SUB_PT (conservative)
NOTE_CHARS_PER_IN = 16.0  # same at NOTE_PT

CHECKS = []  # (name, ok) from check(); reported by run_all.py
TEXTS = {}   # saved figure path -> every text string drawn on it (privacy scan and definition check)


# ---------------------------------------------------------------------------------------------------------------
# Data and definitions
# ---------------------------------------------------------------------------------------------------------------
def load(name):
    """verification/outputs/htm_<name>.csv as a DataFrame."""
    return pd.read_csv(OUTPUTS / f'htm_{name}.csv')


def summary():
    return json.loads((OUTPUTS / 'htm_summary.json').read_text())


def period_text(S=None, which='period'):
    """'Aug 2025 to Jul 2026' for S['definitions'][which]: 'period' = the rate-test / exposure window,
    'case_export_period' = first to last opened ticket in the case export."""
    S = S or summary()
    start, end = (pd.Timestamp(x).strftime('%b %Y') for x in S['definitions'][which])
    return f'{start} to {end}'


def outsized_definition(S=None):
    S = S or summary()
    w, d = S['D1_workload'], S['definitions']
    return (f'Workload-outsized = {w["threshold"]} or more unplanned tickets in the case export '
            f'({period_text(S, "case_export_period")}): the ticket count of the {w["rank_k"]}th busiest machine, i.e. '
            f'the top {d["top_share"]:.0%} of {w["machines"]:,} ticketed machines, ties included.')


def chronic_definition(S=None):
    S = S or summary()
    w, d = S['D1_workload'], S['definitions']
    return (f'Chronic outlier = a machine that is both workload-outsized ({w["threshold"]} or more unplanned '
            f'tickets, the top {d["top_share"]:.0%} of ticketed machines, ties included) and a rate outlier (more '
            f'tickets than its machine type\'s rate × months active predicts, small types pooled; Poisson test, '
            f'Benjamini-Hochberg q < {d["q_cut"]:g}). A screening flag for follow-up, not proof of a defect.')


def machine_month_definition(S=None):
    S = S or summary()
    return (f'Machine-month = one month of a machine being in service. Each telemetry device counts the calendar '
            f'months from its first to its last transaction within {period_text(S)}, both included (quiet months in '
            f'between count too), so a machine active all year adds 12. Devices on the shared internal host or with '
            f'no host are excluded.')


def check(name, expected, actual, tol=0.0):
    """Record a consistency check between htm_summary.json and a value recomputed from a CSV."""
    ok = abs(float(expected) - float(actual)) <= tol
    CHECKS.append((name, ok))
    if not ok:
        print(f'  [WARN] {name}: summary {expected} vs CSV {actual}')
    return ok


# ---------------------------------------------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------------------------------------------
def apply_style():
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


def figure(width=10, height=6.2):
    """A figure with one axes under constrained layout, in the chart style."""
    apply_style()
    return plt.subplots(figsize=(width, height), layout='constrained')


def style_axes(ax, grid='y', baseline='bottom'):
    """Hide all spines except an optional baseline; hairline grid on the given axis ('x', 'y', 'both' or None)."""
    for s in ax.spines.values():
        s.set_visible(False)
    if baseline:
        ax.spines[baseline].set_visible(True)
        ax.spines[baseline].set_color(BASE)
        ax.spines[baseline].set_linewidth(0.8)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.6, linestyle='-')
    ax.set_axisbelow(True)


def pct(x, nd=1):
    """0.229 -> '22.9%'."""
    return f'{100 * x:.{nd}f}%'


def pct_axis(axis, nd=0):
    """Tick labels as percentages; the data are already in percent units."""
    axis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:.{nd}f}%'))


def thousands_axis(axis):
    axis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))


def _lines(text_or_lines, chars):
    items = [text_or_lines] if isinstance(text_or_lines, str) else list(text_or_lines)
    return [line for item in items for line in textwrap.wrap(item, chars, break_on_hyphens=False)]


def frame(fig, title, subtitle, notes=(), definitions=()):
    """Title and subtitle above the plot area; definitions (darker) and notes (muted) below it.

    Each definition is drawn as its own text, first in the footer so the reader sees it before the source notes;
    run_all.py checks that every term a chart uses has its definition drawn. The bands are reserved through the
    constrained-layout rect, so the axes, tick labels and legends are laid out in the space between them."""
    w, h = fig.get_size_inches()
    usable = w - 2 * MARGIN
    sub = _lines(subtitle, int(usable * SUB_CHARS_PER_IN))
    defs = [_lines(d, int(usable * NOTE_CHARS_PER_IN)) for d in definitions]
    note = _lines(notes, int(usable * NOTE_CHARS_PER_IN))
    title_h = TITLE_PT / 72 * 1.25
    sub_h = len(sub) * SUB_PT / 72 * 1.35
    note_lh = NOTE_PT / 72 * 1.4

    top = 0.25
    fig.text(MARGIN / w, 1 - top / h, title, ha='left', va='top', fontsize=TITLE_PT, weight='bold', color=INK)
    fig.text(MARGIN / w, 1 - (top + title_h + 0.08) / h, '\n'.join(sub), ha='left', va='top', fontsize=SUB_PT,
             color=INK2, linespacing=1.35)
    top_band = top + title_h + 0.08 + sub_h + 0.2

    # Footer, drawn bottom-up: notes, then the definitions in reverse so the first one ends up on top.
    y = 0.16
    if note:
        fig.text(MARGIN / w, y / h, '\n'.join(note), ha='left', va='bottom', fontsize=NOTE_PT, color=MUTED,
                 linespacing=1.4)
        y += len(note) * note_lh + 0.06
    for lines in reversed(defs):
        fig.text(MARGIN / w, y / h, '\n'.join(lines), ha='left', va='bottom', fontsize=NOTE_PT, color=INK2,
                 linespacing=1.4)
        y += len(lines) * note_lh + 0.04
    bottom_band = y + 0.16

    left, right = (MARGIN - 0.12) / w, MARGIN / w  # tick labels may sit a little left of the text margin
    fig.get_layout_engine().set(rect=(left, bottom_band / h, 1 - left - right, 1 - (top_band + bottom_band) / h))


def save(fig, path):
    """Save at DPI, record every drawn text string for run_all.py's checks, close the figure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, metadata={'Software': None})
    TEXTS[path] = [t.get_text() for t in fig.findobj(Text) if t.get_text()]
    plt.close(fig)
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    print(f'  wrote {shown}')
    return path
