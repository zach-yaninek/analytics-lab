"""Slide versions of the charts: compact figures sized for the cards of the IPA meeting deck.

The page-style charts in viz/<section>/ are drawn 11 to 18 inches wide with a title band and a definitions footer;
placed in a half-slide card their text would shrink to about 9 px. The slide charts here read the same committed
outputs, draw only the plot (the card header on the slide carries the chart's title, the speaker notes carry the
definitions and caveats), and use the deck's palette and Arial-metric type at sizes that stay legible on a
1920 x 1080 slide.

Card sizes (inches at the slide's 100 px per inch): HALF = 8.3 x 5.2 (a card in a two-card row), WIDE = 11.2 x 5.2
(the wide card beside a narrow one). Fonts: 16 pt text and 15 pt ticks, which show at about 22 and 21 px.

Every chart script: plot(out_dir) -> [png path]; style.check() for every number it draws; nothing but pseudonyms.
"""
from pathlib import Path

import matplotlib

if matplotlib.get_backend().lower() not in ('agg', 'module://matplotlib_inline.backend_inline'):
    matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullLocator  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification' / 'outputs'
FIG_DIR = ROOT / 'viz' / 'figures' / 'slides'
DPI = 200

# The deck's palette (the A-Lab midterm theme): blue emphasis, light blue and gray context.
BLUE, NAVY, LIGHT = '#215F9B', '#13326E', '#A9BFD8'
GRAY, GRAY_LIGHT = '#9AA3AD', '#C9CFD6'
INK, INK2 = '#20252B', '#64717D'
GRID, BASE = '#E3E7EB', '#B8C0C8'
WHITE = '#FFFFFF'

HALF, WIDE = (8.3, 5.2), (11.2, 5.2)
FONT, TICK, SMALL = 16, 15, 14

CHECKS = []  # (name, ok)
TEXTS = {}   # png path -> every text string drawn (privacy scan)


def check(name, expected, actual, tol=0.0):
    """A number drawn on a slide chart (expected) against the same number recomputed from the data (actual)."""
    ok = abs(float(expected) - float(actual)) <= tol
    CHECKS.append((name, ok))
    if not ok:
        print(f'  [WARN] {name}: expected {expected}, got {actual}')
    return ok


def figure(size=HALF):
    plt.rcParams.update({
        'font.family': 'sans-serif', 'font.sans-serif': ['Liberation Sans', 'Arial', 'DejaVu Sans'],
        'font.size': FONT, 'axes.labelsize': FONT, 'axes.labelcolor': INK2, 'xtick.labelsize': TICK,
        'ytick.labelsize': TICK, 'xtick.color': INK2, 'ytick.color': INK2, 'xtick.major.size': 0,
        'ytick.major.size': 0, 'axes.edgecolor': BASE, 'axes.linewidth': 1.0, 'text.color': INK,
        'figure.facecolor': WHITE, 'axes.facecolor': WHITE, 'savefig.facecolor': WHITE, 'legend.frameon': False,
        'legend.fontsize': SMALL,
    })
    return plt.subplots(figsize=size, layout='constrained')


def style_axes(ax, grid='x', baseline='left'):
    """Hairline grid on one axis, one baseline spine, no tick marks."""
    for s in ax.spines.values():
        s.set_visible(False)
    if baseline:
        ax.spines[baseline].set_visible(True)
        ax.spines[baseline].set_color(BASE)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=1.0)
    ax.set_axisbelow(True)
    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_locator(NullLocator())


def pct_axis(axis, nd=0):
    """Tick labels as percentages; the data are in percent units."""
    axis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:.{nd}f}%'))


def thousands_axis(axis):
    axis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))


def save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, metadata={'Software': None})
    TEXTS[path] = [t.get_text() for t in fig.findobj(Text) if t.get_text()]
    plt.close(fig)
    print(f'  wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}')
    return path
