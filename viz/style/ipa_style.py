"""IPA chart style: a light, quiet matplotlib look with a title band, a footer for definitions and notes, and a
small validated palette. Reusable for any chart; nothing here is specific to one analysis.

Two ways to use it (see viz/README.md):
  1. Style sheet only:  plt.style.use('viz/style/ipa.mplstyle')   colours, fonts, grid, spines, legend
  2. Full page layout:  import ipa_style as S
                        fig, ax = S.figure(10, 6)               style sheet + constrained layout
                        ... ordinary matplotlib on ax ...
                        S.style_axes(ax, grid='y')               hairline grid, baseline-only spine
                        S.frame(fig, title, subtitle, notes=[...], definitions=[...])
                        S.save(fig, 'out.png')

Page layout: frame() writes the title and subtitle above the plot area and the definitions and notes below it, then
reserves both bands through the constrained-layout rect. Band heights come from wrapped line counts and font sizes,
so nothing is measured after drawing.

Palette: light surface #fcfcfb, ink #0b0b0b / #52514e / #898781, solid hairline grid #e1e0d9, baseline-only spine
#c3c2b7; emphasis blue #2a78d6 against gray; categorical blue / orange / aqua in that order (validated all-pairs on
the light surface; aqua is below 3:1, so every aqua mark needs a label or legend entry); one-hue blue ramp for
heatmaps and other ordered values.
"""
import textwrap
from pathlib import Path

import matplotlib

if matplotlib.get_backend().lower() not in ('agg', 'module://matplotlib_inline.backend_inline'):
    matplotlib.use('Agg')  # headless runs; notebooks keep their inline backend
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

STYLE_SHEET = Path(__file__).resolve().parent / 'ipa.mplstyle'
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


def check(name, expected, actual, tol=0.0):
    """Record a consistency check: a value stated on a chart (expected) against the same value recomputed from the
    data (actual). run_all.py scripts report the tally."""
    ok = abs(float(expected) - float(actual)) <= tol
    CHECKS.append((name, ok))
    if not ok:
        print(f'  [WARN] {name}: expected {expected}, got {actual}')
    return ok


# ---------------------------------------------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------------------------------------------
def apply_style():
    """Load the style sheet (viz/style/ipa.mplstyle) into matplotlib's rcParams."""
    plt.style.use(STYLE_SHEET)


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
    """Save at DPI, record every drawn text string (TEXTS, for privacy and definition checks), close the figure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, metadata={'Software': None})
    TEXTS[path] = [t.get_text() for t in fig.findobj(Text) if t.get_text()]
    plt.close(fig)
    try:
        shown = path.resolve().relative_to(Path.cwd())
    except ValueError:
        shown = path
    print(f'  wrote {shown}')
    return path
