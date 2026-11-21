"""Verbatim copies from verification/flags.py. Do not edit by hand: regenerate with
trends/tests/sync_definitions.py --write (MIT side) and check with trends/tests/test_parity.py.
"""
import re


TEMPLATE_RE = re.compile(
    r'^\W*(?:14\s*-?\s*days?\s+)?monitor(?:ing)?\b[^.;\n]{0,40}?\b(?:daily|weekly|poll(?:ing)?)\b', re.I)

def _text(text):
    if text is None:
        return ''
    if isinstance(text, float) and text != text:  # NaN
        return ''
    return str(text)

def monitoring_template(text):
    """True if a Trouble Reported text starts with the proactive-monitoring header (see module doc)."""
    return bool(TEMPLATE_RE.search(_text(text)))
