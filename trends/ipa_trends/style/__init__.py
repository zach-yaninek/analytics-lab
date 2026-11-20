"""The IPA chart style for the run's charts and PDF.

ipa_style.py and ipa.mplstyle are byte-identical copies of viz/style/ (a test compares the bytes), so the charts a
run draws look like every other IPA chart. This wrapper only loads them safely:

    from ipa_trends import style
    S = style.load()       # the ipa_style module, or None when matplotlib is not installed
"""
import os
import sys


def _inline(matplotlib):
    """True when running inline in Jupyter, whose backend shows figures in the notebook and is left alone."""
    try:
        raw = dict.__getitem__(matplotlib.rcParams, 'backend')    # read without resolving (no GUI probing)
    except KeyError:
        raw = None
    names = (raw if isinstance(raw, str) else '', os.environ.get('MPLBACKEND', ''))
    return 'ipykernel' in sys.modules and any('inline' in n.lower() for n in names)


def load():
    """Import matplotlib lazily and return the ipa_style module, or None when matplotlib is not installed.

    Forces the headless 'Agg' backend unless running inline in Jupyter, and empties ipa_style.TEXTS and
    ipa_style.CHECKS, which otherwise keep growing across runs in one kernel."""
    try:
        import matplotlib
    except ImportError:
        return None
    if not _inline(matplotlib):
        matplotlib.use('Agg', force=True)
    from . import ipa_style
    ipa_style.TEXTS.clear()
    del ipa_style.CHECKS[:]
    return ipa_style
