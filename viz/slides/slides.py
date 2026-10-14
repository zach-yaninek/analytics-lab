"""Slide versions of the charts: the same IPA style with less on the page, for PowerPoint.

Each viz/slides/*_slide.py script redraws one chart of viz/high_ticket/ or viz/zac_notebook/ from the same data:
  - 16:9 page (10 x 5.625 in at 200 dpi), so every chart scales the same when it fills a slide;
  - the full chart's title (the finding) and a one-line subtitle (what is plotted, and when);
  - no footer: the definitions, caveats and sources are said aloud instead. Each script passes them as talking points
    (talk=[...]), and run_all.py writes them to viz/figures/slides/speaker_notes.md;
  - fewer labels in the plot: no counts in legends or axis labels, secondary annotations dropped, long tables cut to
    the rows a slide can hold.
Marks, colours, fonts and layout are those of the full chart, which stays the reference.
"""
from pathlib import Path

import ipa_style as style

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / 'viz' / 'figures' / 'slides'
DELIVERABLES = ROOT / 'deliverables'
WIDTH, HEIGHT = 10, 5.625  # inches, 16:9
DPI = 200
SUBTITLE_CHARS = int((WIDTH - 2 * style.MARGIN) * style.SUB_CHARS_PER_IN)  # one subtitle line, as frame() wraps it
NOTES = {}  # saved path -> (title, talking points); speaker notes and checks in run_all.py


def figure():
    """A 16:9 slide figure with one axes, in the chart style."""
    return style.figure(WIDTH, HEIGHT)


def finish(fig, path, title, subtitle, talk=(), warning=None):
    """Title and a one-line subtitle above the plot, no footer; save at slide resolution; record the talking points.

    talk: the definitions and caveats the presenter says aloud (the full chart prints them in its footer).
    warning: one muted footer line, used only for the real-name variants' privacy warning."""
    style.check(f'{Path(path).name}: subtitle fits on one line', 1, int(len(subtitle) <= SUBTITLE_CHARS))
    style.frame(fig, title, subtitle, notes=[warning] if warning else ())
    path = style.save(fig, path, dpi=DPI)
    NOTES[path] = (title, list(talk))
    return path
