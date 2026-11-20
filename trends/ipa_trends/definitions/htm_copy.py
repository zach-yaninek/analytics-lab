"""Verbatim copies from verification/high_ticket_machines.py. Do not edit by hand: regenerate with
trends/tests/sync_definitions.py --write (MIT side) and check with trends/tests/test_parity.py.
"""
import math

import numpy as np


SEED = 15072

MIN_TYPE_MONTHS = 100

Q_CUT = 0.05

def poisson_sf(k, mu):
    """P(X >= k) for X ~ Poisson(mu), summed directly over the upper tail (accurate for tiny p)."""
    k = int(k)
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    if k <= mu:  # tail is large: complement of the lower sum is accurate
        lower = sum(math.exp(-mu + j * math.log(mu) - math.lgamma(j + 1)) for j in range(k))
        return max(0.0, 1.0 - lower)
    term = math.exp(-mu + k * math.log(mu) - math.lgamma(k + 1))
    total, j = term, k
    while term > total * 1e-17 and j < k + 10_000:
        j += 1
        term *= mu / j
        total += term
    return min(1.0, total)

def bh(p):
    """Benjamini-Hochberg q-values (monotone, capped at 1)."""
    p = np.asarray(p, float)
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p, kind='mergesort')
    ranked = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out
