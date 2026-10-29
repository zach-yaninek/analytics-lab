"""Real customer names for the real-name deliverables: the Word memo, the deck PDF and the real-name slide charts.

Real names come only from the gitignored data/private/fx_private_customer_names.csv (written by
verification/fleet_exposure.py) and go only to deliverables/ (gitignored) or a scratch folder. Nothing here prints or
returns a name in a message: errors and counts name pseudonyms only.

Twin names: to check a layout without looking at real names, twin() gives each customer a placeholder of the same
length and word lengths, starting with the customer number ("C171 Xxxxxx Xxxxxxxx"), so text wraps and fits as the
real name would.
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAMES_FILE = ROOT / 'data' / 'private' / 'fx_private_customer_names.csv'
DELIVERABLES = ROOT / 'deliverables'

PSEUDONYM = re.compile(r'\bCustomer \d{3}\b')
OTHER_PSEUDONYMS = re.compile(r'\b(?:System \d{3}|[MST]\d{5})\b')   # health systems, machines, serials, telemetry ids
MD_SPECIAL = re.compile(r'([\\`*_{}\[\]<>()#+!|~$])')


def real_names():
    """{'Customer NNN': real account name}, or None when the private table is absent. A customer whose name cell is
    blank is left out, so substitute() fails on it instead of writing an empty or 'nan' name."""
    if not NAMES_FILE.exists():
        return None
    import pandas as pd
    df = pd.read_csv(NAMES_FILE, dtype=str, keep_default_na=False)
    return {c: n.strip() for c, n in zip(df.customer, df.real_account_name) if n.strip()}


def twin(names):
    """The same customers, each with a placeholder of its real name's length and word lengths."""
    out = {}
    for customer, name in names.items():
        name = str(name)
        shape = ''.join(' ' if ch.isspace() else ('X' if i == 0 or name[i - 1].isspace() else 'x')
                        for i, ch in enumerate(name))
        tag = f"C{customer.split()[-1]} "
        out[customer] = tag + shape[len(tag):] if len(shape) > len(tag) + 1 else shape
    return out


def md_escape(text):
    """Text safe to put into Markdown as literal characters."""
    return MD_SPECIAL.sub(r'\\\1', text)


def substitute(text, names, escape=None):
    """Replace every 'Customer NNN' in text with its name, passed through escape (e.g. html.escape or md_escape).

    Returns (new text, replacements). Raises KeyError, naming only the pseudonyms, if any lacks a name.
    """
    missing = sorted({m.group(0) for m in PSEUDONYM.finditer(text) if not names.get(m.group(0))})
    if missing:
        raise KeyError(f"{len(missing)} pseudonym(s) without a real name: {', '.join(missing)}")
    esc = escape or (lambda s: s)
    count = 0

    def put(m):
        nonlocal count
        count += 1
        return esc(str(names[m.group(0)]))
    return PSEUDONYM.sub(put, text), count


def html_escape(text):
    """For names put into HTML text or attributes."""
    return html.escape(text, quote=True)


def pseudonyms_left(text):
    """How many pseudonyms (customer, health system, machine, serial or telemetry id) remain in text."""
    return len(PSEUDONYM.findall(text)) + len(OTHER_PSEUDONYMS.findall(text))


def names_found(text, names):
    """How many times the given customers' names appear in text: a count, never the names."""
    return sum(text.count(str(v)) for v in set(names.values()))
