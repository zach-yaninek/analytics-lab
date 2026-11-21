"""Slide versions of the charts: compact figures sized for the cards of the IPA meeting deck.

The page-style charts in viz/<section>/ are drawn 11 to 18 inches wide with a title band and a definitions footer;
placed in a half-slide card their text would shrink to about 9 px. The slide charts here read the same committed
outputs, draw only the plot (the card header on the slide carries the chart's title, the speaker notes carry the
definitions and caveats), and use the deck's palette and Arial-metric type at sizes that stay legible on a
1920 x 1080 slide.

Card sizes (inches at the slide's 100 px per inch): HALF = 8.3 x 5.2 (a card in a two-card row), WIDE = 11.2 x 5.2
(the wide card beside a narrow one), FULL = 17.4 x 5.2 (one card across the slide). Fonts: 16 pt text and 15 pt
ticks, which show at about 22 and 21 px.

The follow-up charts (sl_18 on, docs/09) print their definitions on the image: definitions(fig, items) reserves a
band under the plot and draws each "Term: text" at DEF = 13 pt (about 18 px), the term in bold; run_all.py checks
that every chart prints the definitions it declares (TERMS).

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

HALF, WIDE, FULL = (8.3, 5.2), (11.2, 5.2), (17.4, 5.2)
HALF_TALL, FULL_TALL = (8.3, 5.6), (17.4, 5.6)   # follow-up cards run down to the Key Takeaway band
FONT, TICK, SMALL = 16, 15, 14
DEF = 13

CHECKS = []  # (name, ok)
TEXTS = {}   # png path -> every text string drawn (privacy scan)
DEFS = {}    # png path -> (the (term, text) items given to definitions(), the definition text as drawn)


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


def definitions(fig, items, size=DEF, margin=0.14, pad=0.10):
    """Print definitions under the plot. items: [(term, text)]; each is drawn as "term: text" with the term in bold,
    wrapped to the figure width (greedy, measured with the renderer), in INK2 on white. Reserves the band through
    the constrained layout's rect, so the plot sits above it. Returns the band height as a figure fraction."""
    from matplotlib.font_manager import FontProperties
    renderer = fig.canvas.get_renderer()
    w_in, h_in = fig.get_size_inches()
    dpi = fig.dpi
    width = (w_in - 2 * margin) * dpi
    props = {w: FontProperties(family='sans-serif', size=size, weight=w) for w in ('bold', 'normal')}

    def measure(text, weight):
        return renderer.get_text_width_height_descent(text, props[weight], ismath=False)[0]

    lines = []                                   # each line: [(text, weight)] segments
    for term, text in items:
        words = [(w, 'bold') for w in f'{term}:'.split()] + [(w, 'normal') for w in text.split()]
        line, x = [], 0.0
        for word, weight in words:
            w = measure(word + ' ', weight)
            if line and x + w > width:
                lines.append(line)
                line, x = [], 0.0
            line.append((word, weight))
            x += w
        lines.append(line)
    line_h = size * 1.32 / 72 * dpi
    band = (len(lines) * line_h + 2 * pad * dpi) / (h_in * dpi)
    fig.get_layout_engine().set(rect=(0, band, 1, 1 - band))
    fig.add_artist(plt.Line2D([margin / w_in, 1 - margin / w_in], [band, band], color=GRID, lw=1.0,
                              transform=fig.transFigure))
    y = band - pad / h_in
    drawn = []
    for line in lines:
        x = margin * dpi
        segs = []
        for word, weight in line:                # merge runs of one weight into one Text
            if segs and segs[-1][1] == weight:
                segs[-1][0].append(word)
            else:
                segs.append(([word], weight))
        for words, weight in segs:
            text = ' '.join(words) + ' '
            fig.text(x / (w_in * dpi), y, text.rstrip(), ha='left', va='top', fontsize=size,
                     weight=weight, color=INK if weight == 'bold' else INK2, gid='definitions')
            drawn.append(text.rstrip())
            x += measure(text, weight)
        y -= line_h / (h_in * dpi)
    fig._definitions = (list(items), ' '.join(drawn))
    return band


def save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(fig, '_definitions'):
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        inv = fig.transFigure.inverted()
        boxes = [t.get_window_extent(renderer=r).transformed(inv) for t in fig.texts if t.get_gid() == 'definitions']
        check(f'{path.stem}: definitions fit inside the image', 1,
              int(all(b.x0 >= 0 and b.x1 <= 1.0 and b.y0 >= 0 for b in boxes)))
        DEFS[path] = fig._definitions
    fig.savefig(path, dpi=DPI, metadata={'Software': None})
    TEXTS[path] = [t.get_text() for t in fig.findobj(Text) if t.get_text()]
    plt.close(fig)
    print(f'  wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}')
    return path
