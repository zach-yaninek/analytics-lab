"""Real customer names for the real-name deliverables: the Word memo, the deck PDF and the real-name slide charts.

Real names come only from the gitignored data/private/fx_private_customer_names.csv (written by
verification/fleet_exposure.py) and go only to deliverables/ (gitignored) or a scratch folder. Nothing here prints or
returns a name in a message: errors and counts name pseudonyms only.

Twin names: to check a layout without looking at real names, twin() gives each customer a placeholder with exactly
the real name's word lengths and spacing, its first word of 4+ letters starting with the customer number ("C171xx
Xxxxxxxx"), so text wraps and fits as the real name would.

A pseudonym is 'Customer NNN' with any whitespace between the two parts (a line break in wrapped text included);
found() and substitute() read it in its canonical form, 'Customer NNN'.
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAMES_FILE = ROOT / 'data' / 'private' / 'fx_private_customer_names.csv'
DELIVERABLES = ROOT / 'deliverables'

PSEUDONYM = re.compile(r'\bCustomer\s+(\d{3})\b')
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


def canonical(match):
    """'Customer NNN' for a PSEUDONYM match, whatever whitespace it was written with."""
    return f'Customer {match.group(1)}'


def found(text):
    """The customers named in text by pseudonym, in canonical form, sorted."""
    return sorted({canonical(m) for m in PSEUDONYM.finditer(text)})


def twin(names):
    """The same customers, each with a placeholder of exactly its real name's word lengths and spacing; the first word
    of at least 4 letters starts with the customer number (C171), so the placeholders can be told apart."""
    out = {}
    for customer, name in names.items():
        tag = f"C{customer.split()[-1]}"
        tokens = re.split(r'(\s+)', str(name))
        shapes = [tok if not tok or tok.isspace() else 'X' + 'x' * (len(tok) - 1) for tok in tokens]
        first = next((i for i, tok in enumerate(tokens) if len(tok) >= len(tag) and not tok.isspace()), None)
        if first is not None:
            shapes[first] = tag + shapes[first][len(tag):]
        out[customer] = ''.join(shapes)
    return out


def md_escape(text):
    """Text safe to put into Markdown as literal characters."""
    return MD_SPECIAL.sub(r'\\\1', text)


def substitute(text, names, escape=None):
    """Replace every 'Customer NNN' in text with its name, passed through escape (e.g. html.escape or md_escape).

    Returns (new text, replacements). Raises KeyError, naming only the pseudonyms, if any lacks a name.
    """
    missing = sorted({canonical(m) for m in PSEUDONYM.finditer(text) if not names.get(canonical(m))})
    if missing:
        raise KeyError(f"{len(missing)} pseudonym(s) without a real name: {', '.join(missing)}")
    esc = escape or (lambda s: s)
    count = 0

    def put(m):
        nonlocal count
        count += 1
        return esc(str(names[canonical(m)]))
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
