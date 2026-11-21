"""Privacy scan of everything a run publishes.

Real strings (ticket and list account names, serials, case numbers, and the equipment list's address, city, zip,
phone, location and credentialing columns) are collected in memory during the run and compared with every output:
tables, the manifest, chart text, the report, the email text and an executed notebook. Text names are compared as
normalised word n-grams, digit identifiers as whole cells and as 4+-digit tokens, with the copied
fleet_exposure.text_leaks. Generated formats (period labels, years, hexadecimal hashes, run ids) are masked first
so they cannot collide with a real number. A hit stops publication; only field names and counts are reported.

A one-word real string that is also a trusted word (one the package writes itself, or a request-type label) is not
counted on its own. Trusted words never come from the data: models, families, Categories and trouble codes outside
the reference are scanned like any other text, so a city typed into the Model column stops publication.
"""
import ast
import functools
import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .definitions import fleet_exposure_copy as FX

PACKAGE_DIR = Path(__file__).resolve().parent
REQUEST_TYPES = PACKAGE_DIR / 'definitions' / 'request_types_v0.csv'
REQUEST_TYPE_COLUMNS = ('trouble_code', 'category', 'group')
HEX = re.compile(r'\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{8,64}\b')
YEAR = re.compile(r'\b(?:FY)?(?:19|20)\d{2}\b')
GENERATED = [HEX, YEAR, re.compile(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\b'), re.compile(r'\b\d+M\b')]


def real_sets(names, ids, cases, private):
    """followups.real_sets for the run's own inputs: {'text', 'digit', 'max_words', 'accounts'} (never written).
    `names` are account names; private['text'] adds the equipment list's address, city, location and notes."""
    accounts = {FX.norm(n) for n in names if n}
    names = {str(n) for n in names if n} | set(private.get('text', set()))
    ids = {str(i) for i in ids if i} | {str(c) for c in cases if c} | set(private.get('digit', set()))
    text = {n for n in map(FX.norm, names | {i for i in ids if not i.isdigit()}) if len(n) >= 4 and not n.isdigit()}
    digit = {i for i in ids if i.isdigit()} | {re.sub(r'\D', '', i) for i in ids if len(re.sub(r'\D', '', i)) >= 7}
    return {'text': text, 'digit': digit, 'max_words': max((len(t.split()) for t in text), default=1),
            'accounts': accounts}


@functools.lru_cache(maxsize=1)
def package_words():
    """Every word of every string literal in the package's modules (definitions/ included). Generated period and
    install-cohort labels are made of these words (the month names, FY, Q, H, Before, From, Unknown) and of years
    and numbers, which the scan masks or never holds as names."""
    words = set()
    for p in sorted(PACKAGE_DIR.rglob('*.py')):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                words.update(FX.norm(node.value).split())
    return frozenset(words)


def request_type_words(path):
    """Words of the trouble codes, Categories and request groups of a request-type file (the v0 reference or
    REQUEST_TYPES_LOCAL). A file that cannot be read adds nothing, which only makes the scan stricter."""
    try:
        ref = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, ValueError):
        return set()
    return {w for c in REQUEST_TYPE_COLUMNS if c in ref.columns for v in ref[c] for w in FX.norm(v).split()}


def trusted_vocabulary(params=None):
    """The words a one-word real string may equal without counting as a hit on its own, from trusted sources only:
    the package's own literals (and with them the words of generated period and cohort labels), the request-type
    reference and REQUEST_TYPES_LOCAL. Labels taken from the data (models, families, Categories and trouble codes
    outside the reference, service statuses, countries) never add words."""
    words = set(package_words()) | request_type_words(REQUEST_TYPES)
    local = getattr(params, 'REQUEST_TYPES_LOCAL', None)
    if local:
        words |= request_type_words(params.path(local))
    return words


def for_outputs(real, vocab, allow=()):
    """The real strings to scan generated outputs for. A one-word real string that is a trusted word (a hospital
    city named Normal or Orange, say) is not counted on its own; account names always are, and every multi-word
    name (an account, an address) is matched in full. `allow` (PRIVACY_ALLOW) names strings that may be published
    although a real field holds them too, such as a model named like a city; it never covers an account name."""
    accounts = real.get('accounts', set())
    allow = {FX.norm(a) for a in allow or ()} - accounts
    text = {t for t in real['text'] if t in accounts or (t not in allow and (' ' in t or t not in vocab))}
    return {'text': text, 'digit': real['digit'], 'max_words': max((len(t.split()) for t in text), default=1)}


def output_strings(real, params):
    """The real strings every output scan looks for: the published files and an executed notebook use this one
    builder, so both exempt exactly the same words (the trusted vocabulary and PRIVACY_ALLOW)."""
    return for_outputs(real, trusted_vocabulary(params), getattr(params, 'PRIVACY_ALLOW', None) or ())


def mask(text):
    s = str(text)
    for pat in GENERATED:
        s = pat.sub(' ', s)
    return s


def scan_frame(df, real, name):
    """{f'{name}.{column}': hits} for the text columns of a table (generated formats masked)."""
    if df is None or len(df) == 0:
        return {}
    txt = pd.DataFrame({c: df[c].map(lambda v: mask(v) if isinstance(v, str) else v)
                        for c in df.columns if not (pd.api.types.is_numeric_dtype(df[c])
                                                    or pd.api.types.is_bool_dtype(df[c]))})
    if txt.empty:
        return {}
    return {f'{name}.{k}': v for k, v in FX.text_leaks(txt, real).items()}


def scan_texts(texts, real, name):
    """Hits in free text (report, email, chart labels, manifest strings)."""
    texts = [mask(t) for t in texts if isinstance(t, str) and t.strip()]
    if not texts:
        return {}
    hits = FX.text_leaks(pd.DataFrame({'text': texts}), real)
    return {name: hits['text']} if hits else {}


def redact(text, real):
    """The message with any real identifier replaced (for console output of warnings and errors)."""
    if not real or not isinstance(text, str):
        return text
    words = text.split()
    out = text
    for k in range(min(real['max_words'], len(words)), 0, -1):
        for i in range(len(words) - k + 1):
            phrase = ' '.join(words[i:i + k])
            if FX.norm(phrase) in real['text']:
                out = out.replace(phrase, '[redacted]')
    for tok in re.findall(r'\d{4,}', out):
        if tok in real['digit']:
            out = out.replace(tok, '[redacted]')
    return out


def weights_fingerprint(W):
    """A short fingerprint of the bootstrap weight matrix (clusters, draws, seed), so a reconciliation can tell a
    definition difference from a random-stream difference."""
    h = hashlib.sha256(np.asarray(W, np.int16).tobytes() + str(W.shape).encode())
    return h.hexdigest()[:16]
