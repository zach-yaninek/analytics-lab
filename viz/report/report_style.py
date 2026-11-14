"""The report's figures, in the Clear Visuals style (zacbaylis/clear-visuals v1.5.1; see clear_visuals/SOURCE.md).

Computer Modern serif type, deep cobalt as the one accent (focal bars, lines and points), lighter neutral grey for
context, black text, and green only for one chosen key readout, on pure white. Figures are drawn at the report's text
width (6.5 in: US letter with 1-inch margins) with 9 pt labels and 8 pt ticks, saved at that exact size (no tight
cropping) as vector PDF with embedded fonts, path-outlined SVG and a 300 dpi PNG preview, into report/figures/.

The report's Definitions section defines the terms, so the figures carry no definition footers. Each figure script
holds the caption that goes with it, and run_all.py writes the LaTeX for all of them (report/ipa_figures.tex).

Every figure script:
  NAME, LABEL, SHORT        file stem (fig01_ownership), LaTeX label (fig:ownership), short caption for the lists
  plot() -> caption         draws the figure, check()s every number it draws, exports it, returns the LaTeX caption
Rules: numbers come from the committed outputs in verification/outputs/ and are checked against the report's text
(report_check); pseudonyms only, and customer-level charts carry no customer labels at all.
"""
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path

import matplotlib

if matplotlib.get_backend().lower() not in ('agg', 'module://matplotlib_inline.backend_inline'):
    matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / 'verification' / 'outputs'
FIG_DIR = ROOT / 'report' / 'figures'
CV = HERE / 'clear_visuals'
TTF_CACHE = CV / 'fonts' / 'truetype'   # TrueType conversions of the bundled faces, built on first use (gitignored)
STYLE = json.loads((CV / 'style.json').read_text())
P = STYLE['themes']['light']

# Colour roles (Clear Visuals, light theme). Text is always black; reduce prominence with size or weight.
COBALT = P['primary']        # #164BAE  the one accent: focal bars, lines, points
GREY = P['data']             # #8A8A8A  context observations, comparison marks
GREY_DARK = P['secondary']   # #666666  context lines that need more weight (reference lines, interval whiskers)
GREY_FILL = '#D2D2D2'        # a lighter tint of the data grey for large context fills (bars, bands)
GRID = P['grid']             # #DEDEDE
TEXT = P['text']             # #000000
GREEN = P['highlight']       # #408440  one key numerical readout per figure, at most
RED = P['negative']          # #A73D42  a meaningful negative or failed mark only, never text
WHITE = P['background']      # #FFFFFF

WIDTH = 6.5                  # the report's text width in inches
FONT, TICK = 9, 8            # body and tick sizes in points, at final size
DPI = STYLE['figure']['dpi']

CHECKS = []                  # (name, ok, detail)
TEXTS = {}                   # figure stem -> every text string drawn (for the privacy scan)


def _truetype(otf):
    """The bundled face at otf with its outlines converted to TrueType, cached by the face's content hash.

    matplotlib's PDF writer embeds every Type 42 font as a TrueType font (CIDFontType2 with FontFile2). The bundled
    CMU faces have CFF (PostScript) outlines, so embedding them as they are puts CFF data where the PDF standard
    requires TrueType data: Poppler warns ('Mismatch between font type and embedded font file'), and stricter readers
    can refuse the font. Converting the outlines (fontTools' cu2qu, within 1 font unit of 1,000) keeps every glyph,
    advance width, and name, so the figures look the same and their embedded fonts are valid.
    """
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont, newTable

    data = otf.read_bytes()
    dst = TTF_CACHE / f'{otf.stem}-{hashlib.sha256(data).hexdigest()[:12]}.ttf'
    if dst.exists():
        return dst
    font = TTFont(otf)
    order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(glyph_set)
        glyph_set[name].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
        glyphs[name] = pen.glyph()
    font['loca'] = newTable('loca')
    font['glyf'] = glyf = newTable('glyf')
    glyf.glyphOrder, glyf.glyphs = order, glyphs
    for tag in ('CFF ', 'VORG'):
        if tag in font:
            del font[tag]
    glyf.compile(font)
    hmtx = font['hmtx']
    for name, glyph in glyphs.items():
        if hasattr(glyph, 'xMin'):              # the left side bearing follows the new outline's extent
            hmtx[name] = (hmtx[name][0], glyph.xMin)
    maxp = font['maxp'] = newTable('maxp')     # version 1.0, recalculated from the outlines on save
    maxp.tableVersion = 0x00010000
    maxp.maxZones = 1
    for field in ('maxTwilightPoints', 'maxStorage', 'maxFunctionDefs', 'maxInstructionDefs', 'maxStackElements',
                  'maxSizeOfInstructions', 'maxComponentElements'):
        setattr(maxp, field, 0)
    post = font['post']
    post.formatType, post.extraNames, post.mapping, post.glyphOrder = 2.0, [], {}, order
    font.sfntVersion = '\x00\x01\x00\x00'
    TTF_CACHE.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(f'.{os.getpid()}.tmp')
    font.save(tmp)
    tmp.replace(dst)                            # atomic, so parallel runs never read a half-written face
    return dst


def _register_fonts():
    """Use the bundled Computer Modern Unicode faces in place of any installed copies.

    Each face is registered as its TrueType conversion (see _truetype). The bold faces (cmunbx, cmunbi) are CMU's
    'bold extended' and register with stretch 'expanded', and the regular faces register at weight 500, so
    matplotlib's font matching would pick the regular face for bold text and warn on every normal-weight request.
    Registering the regular faces at weight 400 and every face at normal stretch makes 'normal' and 'bold' resolve
    exactly, as they do for the mathtext fonts.
    """
    fm = font_manager.fontManager
    fm.ttflist = [f for f in fm.ttflist if f.name != STYLE['font']]
    for path in sorted((CV / 'fonts').glob('*.otf')):
        fm.addfont(str(_truetype(path)))
    fm.ttflist = [dataclasses.replace(f, stretch='normal', weight=400 if f.weight == 500 else f.weight)
                  if f.name == STYLE['font'] else f for f in fm.ttflist]
    font_manager._get_font.cache_clear()
    fm._findfont_cached.cache_clear()


_register_fonts()
plt.rcParams.update({
    'font.family': STYLE['font'], 'font.size': FONT, 'mathtext.fontset': STYLE['math_font'],
    'axes.titlesize': FONT, 'axes.labelsize': FONT, 'xtick.labelsize': TICK, 'ytick.labelsize': TICK,
    'legend.fontsize': TICK, 'axes.unicode_minus': True, 'axes.formatter.use_mathtext': False,
    'figure.facecolor': WHITE, 'axes.facecolor': WHITE, 'savefig.facecolor': WHITE,
    'text.color': TEXT, 'axes.labelcolor': TEXT, 'xtick.color': TEXT, 'ytick.color': TEXT,
    'axes.edgecolor': GREY, 'axes.linewidth': 0.6, 'xtick.major.width': 0.6, 'ytick.major.width': 0.6,
    'xtick.major.size': 2.5, 'ytick.major.size': 2.5, 'grid.color': GRID, 'grid.linewidth': 0.6,
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': False, 'axes.axisbelow': True,
    'lines.linewidth': 1.5, 'lines.markersize': 4, 'legend.frameon': False,
    'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'path', 'savefig.dpi': DPI,
    'figure.constrained_layout.h_pad': 0.04, 'figure.constrained_layout.w_pad': 0.06,
})


# ----------------------------------------------------------------------------------------------------------------
# Checks: every number a figure draws or its caption states
# ----------------------------------------------------------------------------------------------------------------
def check(name, expected, actual, tol=0.0):
    """A drawn number (expected) against the same number recomputed from the outputs (actual)."""
    try:
        ok = abs(float(expected) - float(actual)) <= tol
    except (TypeError, ValueError):
        ok = expected == actual
    CHECKS.append((name, ok, f'expected {expected}, got {actual}'))
    if not ok:
        print(f'  [FAIL] {name}: expected {expected}, got {actual}')
    return ok


def report_check(name, report, recomputed):
    """A value as the report prints it against the recomputed value formatted the same way."""
    ok = str(report) == str(recomputed)
    CHECKS.append((name, ok, f'report {report!r}, recomputed {recomputed!r}'))
    if not ok:
        print(f'  [FAIL] {name}: the report says {report!r}, the outputs give {recomputed!r}')
    return ok


# ----------------------------------------------------------------------------------------------------------------
# Number formats, as the report prints them
# ----------------------------------------------------------------------------------------------------------------
def num(x, nd=0):
    """3041 -> '3,041'."""
    return f'{x:,.{nd}f}'


def pct(share, nd=0):
    """0.4234 -> '42%' (a share, not a percentage)."""
    return f'{100 * share:.{nd}f}%'


def span(lo, hi, nd=0):
    """(725, 837) -> '725–837'."""
    return f'{lo:,.{nd}f}–{hi:,.{nd}f}'


def pct_axis(axis, nd=0):
    """Tick labels as percentages for an axis holding shares (0.25 -> '25%')."""
    axis.set_major_formatter(FuncFormatter(lambda v, _: f'{100 * v:.{nd}f}%'))


def thousands_axis(axis):
    axis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'))


# ----------------------------------------------------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------------------------------------------------
def figure(height, ncols=1, nrows=1, width_ratios=None, height_ratios=None, **kw):
    """A figure at the report's text width and the given height (inches), with constrained layout."""
    gs = {}
    if width_ratios:
        gs['width_ratios'] = width_ratios
    if height_ratios:
        gs['height_ratios'] = height_ratios
    fig, axes = plt.subplots(nrows, ncols, figsize=(WIDTH, height), layout='constrained', gridspec_kw=gs or None,
                             squeeze=False, **kw)
    return fig, (axes[0, 0] if nrows * ncols == 1 else axes.ravel())


def panel(ax, letter, title):
    """The panel's heading at its top left: a bold letter, then a short title (black, body size)."""
    ax.set_title(r'$\mathbf{' + letter + '}$' + f'   {title}', loc='left', fontsize=FONT, pad=6)


def clean(ax, grid=None, left=True, bottom=True):
    """Restrained axes: optional light grid on one axis, spines only where they carry a baseline or scale."""
    ax.spines['left'].set_visible(left)
    ax.spines['bottom'].set_visible(bottom)
    if grid in ('x', 'y', 'both'):
        ax.grid(axis=grid, color=GRID, lw=0.6, zorder=0)
    if not left:
        ax.tick_params(axis='y', length=0)
    if not bottom:
        ax.tick_params(axis='x', length=0)


def label(ax, x, y, text, ha='left', va='center', size=TICK, color=TEXT, weight='normal', **kw):
    """A direct label (black by default)."""
    return ax.text(x, y, text, ha=ha, va=va, fontsize=size, color=color, fontweight=weight, **kw)


# ----------------------------------------------------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------------------------------------------------
def export(fig, stem, out_dir=FIG_DIR):
    """Save at the exact figure size: PDF (fonts embedded), SVG (text as paths) and a 300 dpi PNG."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    TEXTS[stem] = [t.get_text() for t in fig.findobj(Text) if t.get_text()]
    paths = {}
    for fmt, meta in (('pdf', {'Creator': None, 'Producer': None, 'CreationDate': None}),
                      ('svg', {'Creator': None, 'Date': None}), ('png', None)):
        path = out_dir / f'{stem}.{fmt}'
        fig.savefig(path, dpi=DPI, transparent=False, metadata=meta)
        paths[fmt] = path
    plt.close(fig)
    return paths


def summary():
    """Print the checks; return the number that failed."""
    bad = [c for c in CHECKS if not c[1]]
    print(f'{len(CHECKS) - len(bad)}/{len(CHECKS)} checks pass')
    return len(bad)


def ceil_to(x, step):
    return step * math.ceil(x / step)
