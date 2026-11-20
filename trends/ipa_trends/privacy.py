"""Privacy scan of everything a run publishes.

Real strings (ticket and list account names, serials, case numbers, and the equipment list's address, city, zip,
phone, location and credentialing columns) are collected in memory during the run and compared with every output:
tables, the manifest, chart text, the report, the email text and an executed notebook. Text names are compared as
normalised word n-grams, digit identifiers as whole cells and as 4+-digit tokens, with the copied
fleet_exposure.text_leaks. Generated formats (period labels, years, hexadecimal hashes, run ids) are masked first
so they cannot collide with a real number. A hit stops publication; only field names and counts are reported.
"""
import hashlib
import re

import numpy as np
import pandas as pd

from .definitions import fleet_exposure_copy as FX

HEX = re.compile(r'\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{8,64}\b')
YEAR = re.compile(r'\b(?:FY)?(?:19|20)\d{2}\b')
GENERATED = [HEX, YEAR, re.compile(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\b'), re.compile(r'\b\d+M\b')]


def real_sets(names, ids, cases, private):
    """followups.real_sets for the run's own inputs: {'text', 'digit', 'max_words'} (never written)."""
    names = {str(n) for n in names if n} | set(private.get('text', set()))
    ids = {str(i) for i in ids if i} | {str(c) for c in cases if c} | set(private.get('digit', set()))
    text = {n for n in map(FX.norm, names | {i for i in ids if not i.isdigit()}) if len(n) >= 4 and not n.isdigit()}
    digit = {i for i in ids if i.isdigit()} | {re.sub(r'\D', '', i) for i in ids if len(re.sub(r'\D', '', i)) >= 7}
    return {'text': text, 'digit': digit, 'max_words': max((len(t.split()) for t in text), default=1)}


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
